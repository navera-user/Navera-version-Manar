#!/usr/bin/env python3
"""
gps_node.py — NAVERA GPS sensor driver.

Reads NMEA sentences from a serial GPS (e.g. /dev/ttyTHS1 on Jetson UART, or
/dev/ttyUSB0 for a USB GPS) and publishes:
    /navera/sensors/gps_fix    sensor_msgs/NavSatFix       (unchanged, legacy sensor topic)
    /navera/sensors/gps_vel    geometry_msgs/TwistStamped  (unchanged)
    /navera/estimate/gps       navera_msgs/PositionEstimate (NEW: the source contract)

The PositionEstimate output is the typed contract consumed by navera_estimator.
It is strictly additive: gps_fix / gps_vel are untouched. GPS always reports
SOURCE_GPS / MODE_MEASURED (it is a live sensor, never replayed) and carries the
SAME HDOP-derived covariance as gps_fix (COVARIANCE_TYPE_APPROXIMATED) — no
fabricated uncertainty.

Parameters:
    serial_port  (default "/dev/ttyTHS1") — serial device
    baud_rate    (default 9600)            — typical for NMEA GPS modules
"""
import rclpy
from navera_common.lifecycle import die_with_parent
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus
from geometry_msgs.msg import TwistStamped
from navera_msgs.msg import PositionEstimate
import serial, pynmea2, threading, traceback, json, math


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
        self.fix_count = 0

        try:
            self.ser = serial.Serial(port, baud, timeout=2)
            self.get_logger().info(f"Port open OK: {port} @ {baud}")
        except Exception as e:
            self.get_logger().error(f"FAILED to open port: {e}")
            return

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
                if count <= 5 or count % 30 == 0:
                    self.get_logger().info(f"LINE {count}: {raw[:80]}")
                if not raw.startswith("$"):
                    continue
                try:
                    msg = pynmea2.parse(raw)
                except pynmea2.ParseError:
                    continue
                if isinstance(msg, pynmea2.types.talker.GGA):
                    self._publish_fix(msg)
                elif isinstance(msg, pynmea2.types.talker.RMC):
                    self._publish_vel(msg)
            except serial.SerialException as e:
                self.get_logger().error(f"Serial error: {e}")
                break
            except Exception as e:
                self.get_logger().error(f"Loop error: {e}\n{traceback.format_exc()}")
        self.get_logger().error("READ LOOP EXITED")

    def _publish_fix(self, msg):
        fix = NavSatFix()
        fix.header.stamp = self.get_clock().now().to_msg()
        fix.header.frame_id = "gps"
        try:
            gps_qual = int(msg.gps_qual) if msg.gps_qual else 0
        except Exception:
            gps_qual = 0
        if not msg.latitude or gps_qual == 0:
            fix.status.status = NavSatStatus.STATUS_NO_FIX
            fix.latitude = fix.longitude = fix.altitude = 0.0
            fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
            self.pub_fix.publish(fix)
            # Contract: an invalid fix is published, not swallowed. valid=False,
            # NaN position (0,0 is a real place — never emit it as a fix),
            # covariance UNKNOWN. Still MODE_MEASURED: it IS a live reading.
            self._publish_estimate(
                fix.header, valid=False,
                lat=math.nan, lon=math.nan, alt=math.nan,
                cov=None, reason=f"no GPS fix (qual={gps_qual})",
                extras={"gps_qual": gps_qual},
            )
            self.get_logger().info(f"No fix yet (qual={gps_qual})")
            return
        fix.status.status = NavSatStatus.STATUS_FIX
        fix.status.service = NavSatStatus.SERVICE_GPS | NavSatStatus.SERVICE_GLONASS
        fix.latitude = msg.latitude
        fix.longitude = msg.longitude
        fix.altitude = float(msg.altitude) if msg.altitude else 0.0
        hdop = float(msg.horizontal_dil) if msg.horizontal_dil else 2.0
        cov = (hdop * 2.0) ** 2
        fix.position_covariance = [float(cov),0.0,0.0, 0.0,float(cov),0.0, 0.0,0.0,float(cov*4)]
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_APPROXIMATED
        self.pub_fix.publish(fix)
        self.fix_count += 1
        # Same fix, same HDOP-derived covariance, on the typed contract.
        try:
            num_sats = int(msg.num_sats) if msg.num_sats else 0
        except (TypeError, ValueError):
            num_sats = 0
        self._publish_estimate(
            fix.header, valid=True,
            lat=msg.latitude, lon=msg.longitude, alt=fix.altitude,
            cov=list(fix.position_covariance), reason="",
            extras={"hdop": round(hdop, 2), "num_sats": num_sats, "gps_qual": gps_qual},
        )
        self.get_logger().info(
            f"FIX #{self.fix_count}: lat={msg.latitude:.6f} lon={msg.longitude:.6f} "
            f"alt={fix.altitude:.1f}m sats={msg.num_sats} hdop={hdop:.1f}"
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

    def _publish_vel(self, msg):
        try:
            if not msg.latitude or msg.status != "A":
                return
            vel = TwistStamped()
            vel.header.stamp = self.get_clock().now().to_msg()
            vel.header.frame_id = "gps"
            vel.twist.linear.x = float(msg.spd_over_grnd)*0.5144 if msg.spd_over_grnd else 0.0
            self.pub_vel.publish(vel)
        except Exception as e:
            self.get_logger().error(f"vel error: {e}")

    def destroy_node(self):
        self.running = False
        if hasattr(self, "ser") and self.ser.is_open:
            self.ser.close()
        super().destroy_node()


def main(args=None):
    """Entry point. Exits cleanly (code 0) on SIGINT and SIGTERM.

    rclpy installs handlers for both signals and shuts the context down itself,
    so spin() returns with the context already closed — an unconditional
    rclpy.shutdown() here would then raise RCLError. Hence the rclpy.ok() guard.
    """
    die_with_parent()  # orphan guard: die if our launcher/systemd unit is killed
    rclpy.init(args=args)
    node = GPSNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
