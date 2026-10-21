#!/usr/bin/env python3
"""gps_node.py — NAVERA GPS sensor driver.

Reads NMEA sentences from a serial GPS (e.g. /dev/ttyTHS1 on Jetson UART, or
/dev/ttyUSB0 for a USB GPS) and publishes:
    /navera/sensors/gps_fix    sensor_msgs/NavSatFix       (unchanged, legacy sensor topic)
    /navera/sensors/gps_vel    geometry_msgs/TwistStamped  (ENU: linear.x east, linear.y north, m/s)
    /navera/estimate/gps       navera_msgs/PositionEstimate (NEW: the source contract)
    /navera/sensors/gnss_time  sensor_msgs/TimeReference   (RMC status A: time_ref = GNSS UTC,
                               header.stamp = system clock at reception; the trusted-time source
                               of celestial when no RTC / NTP — navera_common.trusted_time)

The PositionEstimate output is the typed contract consumed by navera_estimator.
It is strictly additive: gps_fix / gps_vel are untouched. GPS always reports
SOURCE_GPS / MODE_MEASURED (it is a live sensor, never replayed) and carries the
SAME HDOP-derived covariance as gps_fix (COVARIANCE_TYPE_APPROXIMATED); with no
HDOP the covariance is UNKNOWN rather than invented.

Only checksummed sentences are used, and only GGA fix qualities 1, 2, 4 and 5
(GPS, DGPS, RTK fixed, RTK float) count as a fix: 6 (the receiver's own dead
reckoning), 7 (manual) and 8 (simulator) are reported as invalid. Altitude is
height above the WGS84 ellipsoid (GGA altitude + geoid separation), NaN when
unknown.

If the serial port cannot be opened or fails, the node exits with code 1 so the
launch/systemd service restarts it (and so reconnects) instead of idling.

Parameters:
    serial_port  (default "/dev/ttyTHS1") — serial device
    baud_rate    (default 9600)            — typical for NMEA GPS modules
"""
import rclpy
from navera_common.lifecycle import die_with_parent
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus, TimeReference
from geometry_msgs.msg import TwistStamped
from navera_msgs.msg import PositionEstimate
import datetime
import json
import math
import sys
import threading
import traceback

import pynmea2
import serial

KNOTS_TO_MPS = 0.514444
# GGA quality indicators that are a real satellite fix.
_VALID_GPS_QUAL = {1, 2, 4, 5}


def _field_float(value):
    """Float from an NMEA field, or None when empty/invalid."""
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def rmc_utc_epoch(msg):
    """UTC epoch seconds of a valid RMC sentence (status A, date and time present), else None."""
    if getattr(msg, "status", None) != "A":
        return None
    d, t = getattr(msg, "datestamp", None), getattr(msg, "timestamp", None)
    if not isinstance(d, datetime.date) or not isinstance(t, datetime.time):
        return None
    return datetime.datetime.combine(d, t.replace(tzinfo=None), tzinfo=datetime.timezone.utc).timestamp()


class GPSNode(Node):
    def __init__(self):
        super().__init__("gps_node")
        self.declare_parameter("serial_port", "/dev/ttyTHS1")
        self.declare_parameter("baud_rate", 9600)
        port = self.get_parameter("serial_port").value
        baud = self.get_parameter("baud_rate").value

        self.pub_fix = self.create_publisher(NavSatFix,    "/navera/sensors/gps_fix", 10)
        self.pub_vel = self.create_publisher(TwistStamped, "/navera/sensors/gps_vel", 10)
        # Additive: the typed source contract for navera_estimator. RELIABLE
        # depth 10, same class as the sensor data topics (CLAUDE.md QoS rule).
        self.pub_est = self.create_publisher(PositionEstimate, "/navera/estimate/gps", 10)
        self.pub_time = self.create_publisher(TimeReference, "/navera/sensors/gnss_time", 10)
        self.fix_count = 0
        self.failed = False

        # Raises on failure: main() turns that into exit code 1 → restart.
        self.ser = serial.Serial(port, baud, timeout=2)
        self.get_logger().info(f"Port open OK: {port} @ {baud}")

        self.running = True
        threading.Thread(target=self._read_loop, daemon=True).start()
        self.get_logger().info("Read thread started")

    def _read_loop(self):
        self.get_logger().info("READ LOOP RUNNING")
        count = 0
        while self.running:
            try:
                raw = self.ser.readline().decode("ascii", errors="replace").strip()
                count += 1
                if count <= 5:
                    self.get_logger().info(f"LINE {count}: {raw[:80]}")
                if not raw.startswith("$"):
                    continue
                try:
                    # check=True: a truncated or corrupted line (no/bad *hh
                    # checksum) must never become a fix.
                    msg = pynmea2.parse(raw, check=True)
                except pynmea2.ParseError:
                    continue
                if isinstance(msg, pynmea2.types.talker.GGA):
                    self._publish_fix(msg)
                elif isinstance(msg, pynmea2.types.talker.RMC):
                    self._publish_vel(msg)
                    self._publish_time(msg)
            except serial.SerialException as e:
                if self.running:
                    self.get_logger().fatal(f"Serial error: {e} — exiting so the service restarts")
                    self.failed = True
                    self.context.try_shutdown()
                return
            except Exception as e:
                self.get_logger().error(f"Loop error: {e}\n{traceback.format_exc()}")

    def _publish_fix(self, msg):
        fix = NavSatFix()
        fix.header.stamp = self.get_clock().now().to_msg()
        fix.header.frame_id = "gps"
        try:
            gps_qual = int(msg.gps_qual) if msg.gps_qual else 0
        except (TypeError, ValueError):
            gps_qual = 0
        has_pos = bool(msg.lat) and bool(msg.lon)
        if not has_pos or gps_qual not in _VALID_GPS_QUAL:
            fix.status.status = NavSatStatus.STATUS_NO_FIX
            fix.latitude = fix.longitude = fix.altitude = math.nan
            fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
            self.pub_fix.publish(fix)
            # Contract: an invalid fix is published, not swallowed. valid=False,
            # NaN position, covariance UNKNOWN. Still MODE_MEASURED: it IS a live reading.
            reason = (f"no GPS fix (qual={gps_qual})" if gps_qual not in (6, 7, 8) else
                      f"receiver reports a non-satellite position (qual={gps_qual}) — not used")
            self._publish_estimate(
                fix.header, valid=False,
                lat=math.nan, lon=math.nan, alt=math.nan,
                cov=None, reason=reason,
                extras={"gps_qual": gps_qual},
            )
            self.get_logger().info(f"No fix (qual={gps_qual})", throttle_duration_sec=10.0)
            return
        fix.status.status = (NavSatStatus.STATUS_GBAS_FIX if gps_qual in (2, 4, 5)
                             else NavSatStatus.STATUS_FIX)
        fix.status.service = NavSatStatus.SERVICE_GPS
        fix.latitude = msg.latitude
        fix.longitude = msg.longitude
        msl = _field_float(msg.altitude)
        geo_sep = _field_float(msg.geo_sep)
        # GGA altitude is above mean sea level; the contract is ellipsoidal height.
        fix.altitude = msl + geo_sep if (msl is not None and geo_sep is not None) else math.nan
        hdop = _field_float(msg.horizontal_dil)
        if hdop is not None and hdop > 0:
            # sigma = HDOP x 2 m (assumed user range error); vertical ~2x horizontal.
            cov = (hdop * 2.0) ** 2
            fix.position_covariance = [cov, 0.0, 0.0, 0.0, cov, 0.0, 0.0, 0.0, cov * 4]
            fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_APPROXIMATED
            est_cov = list(fix.position_covariance)
        else:
            fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
            est_cov = None
        self.pub_fix.publish(fix)
        self.fix_count += 1
        try:
            num_sats = int(msg.num_sats) if msg.num_sats else 0
        except (TypeError, ValueError):
            num_sats = 0
        self._publish_estimate(
            fix.header, valid=True,
            lat=msg.latitude, lon=msg.longitude, alt=fix.altitude,
            cov=est_cov, reason="",
            extras={"hdop": hdop, "num_sats": num_sats, "gps_qual": gps_qual,
                    "geo_sep_m": geo_sep},
        )
        self.get_logger().info(
            f"FIX #{self.fix_count}: lat={msg.latitude:.6f} lon={msg.longitude:.6f} "
            f"alt={fix.altitude:.1f}m sats={num_sats} hdop={hdop}",
            throttle_duration_sec=10.0,
        )

    def _publish_estimate(self, header, valid, lat, lon, alt, cov, reason, extras):
        """Emit the GPS PositionEstimate. GPS is always SOURCE_GPS / MODE_MEASURED."""
        est = PositionEstimate()
        est.header = header                       # same stamp + frame_id as the NavSatFix
        est.latitude = float(lat)
        est.longitude = float(lon)
        est.altitude = float(alt)
        if cov is None:
            est.position_covariance = [0.0] * 9
            est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        else:
            est.position_covariance = cov
            est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
        est.source = PositionEstimate.SOURCE_GPS
        est.mode = PositionEstimate.MODE_MEASURED
        est.valid = valid
        # confidence stays 0.0 on purpose: any HDOP->confidence curve needs a
        # CHOSEN constant we have not measured (same reason we reject the 0.95
        # celestial constant). The real, fusable uncertainty already lives in
        # position_covariance. Populate this only once a field-measured
        # HDOP<->error relation exists. Raw HDOP is kept in details_json.
        est.confidence = 0.0
        est.reason = reason
        # TODO(step 6): true measurement instant = GGA UTC + date(RMC)/RTC.
        # Until then sensor_stamp = publication stamp (zero apparent latency).
        est.sensor_stamp = header.stamp
        est.producer = "gps_node"
        est.model_id = "nmea_gga"
        est.frame_index = -1                      # not a camera-pipeline frame
        est.details_json = json.dumps(extras)
        self.pub_est.publish(est)

    def _publish_time(self, msg):
        """RMC (status A) → the receiver's UTC, with the system time it arrived at."""
        epoch = rmc_utc_epoch(msg)
        if epoch is None:
            return
        ref = TimeReference()
        ref.header.stamp = self.get_clock().now().to_msg()
        ref.header.frame_id = "gps"
        ref.time_ref.sec = int(epoch)
        ref.time_ref.nanosec = int(round((epoch - int(epoch)) * 1e9)) % 1_000_000_000
        ref.source = "gnss"
        self.pub_time.publish(ref)

    def _publish_vel(self, msg):
        """RMC → ground velocity in ENU (linear.x east, linear.y north), m/s."""
        try:
            if msg.status != "A":
                return
            spd = _field_float(msg.spd_over_grnd)
            course = _field_float(msg.true_course)
            if spd is None:
                return
            if course is None:
                if spd > 0.05:
                    return          # moving with unknown direction: no velocity
                course = 0.0        # stationary: direction irrelevant
            v = spd * KNOTS_TO_MPS
            vel = TwistStamped()
            vel.header.stamp = self.get_clock().now().to_msg()
            vel.header.frame_id = "gps"
            vel.twist.linear.x = v * math.sin(math.radians(course))
            vel.twist.linear.y = v * math.cos(math.radians(course))
            self.pub_vel.publish(vel)
        except Exception as e:
            self.get_logger().error(f"vel error: {e}")

    def destroy_node(self):
        self.running = False
        if hasattr(self, "ser") and self.ser.is_open:
            self.ser.close()
        super().destroy_node()


def main(args=None):
    """Entry point. Exit code 0 on SIGINT/SIGTERM, 1 when the serial port fails."""
    die_with_parent()  # orphan guard: die if our launcher/systemd unit is killed
    rclpy.init(args=args)
    try:
        node = GPSNode()
    except (serial.SerialException, OSError) as e:
        rclpy.logging.get_logger("gps_node").fatal(
            f"cannot open GPS serial port: {e} — exiting so the service restarts")
        rclpy.try_shutdown()
        sys.exit(1)
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        failed = node.failed
        node.destroy_node()
        rclpy.try_shutdown()
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
