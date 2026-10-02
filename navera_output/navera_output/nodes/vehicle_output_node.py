#!/usr/bin/env python3
"""
vehicle_output_node.py — NAVERA output to the vehicle's autopilot.

Turns the arbiter's decision (/navera/position + /navera/nav_status) into what
an autopilot understands as a GPS:

  * NMEA 0183 (GGA + RMC) on a serial port — any system that takes a GPS
    receiver (drones, boats, ground robots);
  * MAVLink GPS_INPUT — PX4 / ArduPilot with GPS_TYPE = MAV;
  * ROS: sensor_msgs/NavSatFix on ros_fix_topic (default /navera/fix), for vehicles
    whose software runs on ROS — the same decision, accuracy as the covariance.

What is sent, and when a position is NOT sent, is decided in
navera_output.policy (see its docstring): FIX is a fix; DEGRADED is withheld
unless forward_degraded is set with a declared degraded_sigma_m; everything
else — including a stale or silent arbiter — is an explicit "no fix".

Parameters:
    rate_hz              (5.0)   output rate
    nmea_port            ("")    serial device for NMEA, "" = disabled
    nmea_baud            (9600)
    mavlink_url          ("")    e.g. "serial:/dev/ttyTHS2:921600" (navera_output.mavlink_url) or
                                 "udpout:127.0.0.1:14550"; "" = disabled
    mavlink_system_id    (1)     MAVLink ids of this box (companion computer)
    mavlink_component_id (191)
    ros_fix_topic        ("/navera/fix")  "" = disabled
    forward_degraded     (False) send DEGRADED positions as "estimated"
    degraded_sigma_m     (NaN)   accuracy stated for them (required if forwarded)
    max_forward_sigma_m  (1000)  a forwarded position coarser than this is withheld
    position_timeout_s   (2.0)   an older position is not current
    max_measurement_age_s (2.0)  a position measured longer ago is not sent; the rest
                                 are sent stamped with their measurement instant
    nav_status_timeout_s (2.0)   a silent arbiter means "no fix"
    gps_vel_timeout_s    (1.0)   the GPS velocity (/navera/sensors/gps_vel) sent with
                                 a GPS position must be younger than this
    fix_type_without_alt (3)     MAVLink fix_type for a position with no altitude
                                 (vision / celestial): 3 = usable by ArduPilot / PX4,
                                 which then take height from the barometer; 2 = the
                                 literal label, which they ignore (mavlink_out)

Each position is sent ONCE, as soon as it arrives (a 1 Hz vision fix is not repeated
5 times with fresh timestamps: an autopilot filter would read the repeats as
"stopped, then jumped"). "No fix" is sent at rate_hz, so the autopilot always
hears from NAVERA.

If an enabled output cannot be opened, the node exits with code 1 so the
service restarts it.
"""
import math
import sys
import time
from datetime import datetime, timedelta, timezone

import rclpy
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from geometry_msgs.msg import TwistStamped
from sensor_msgs.msg import NavSatFix, NavSatStatus
from navera_msgs.msg import NavStatus, PositionEstimate
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from navera_output import mavlink_out, mavlink_url, nmea
from navera_output.policy import KIND_NONE, Config, decide


class VehicleOutputNode(Node):
    def __init__(self):
        super().__init__("vehicle_output")
        declare_float(self, "rate_hz", 5.0)
        self.declare_parameter("nmea_port", "")
        self.declare_parameter("nmea_baud", 9600)
        self.declare_parameter("mavlink_url", "")
        self.declare_parameter("mavlink_system_id", 1)
        self.declare_parameter("mavlink_component_id", 191)
        self.declare_parameter("forward_degraded", False)
        declare_float(self, "degraded_sigma_m", float("nan"))
        declare_float(self, "position_timeout_s", 2.0)
        declare_float(self, "max_measurement_age_s", 2.0)
        declare_float(self, "nav_status_timeout_s", 2.0)
        declare_float(self, "gps_vel_timeout_s", 1.0)
        declare_float(self, "max_forward_sigma_m", 1000.0)
        self.declare_parameter("fix_type_without_alt", 3)
        self.declare_parameter("ros_fix_topic", "/navera/fix")
        self._fix_type_without_alt = int(self.get_parameter("fix_type_without_alt").value)
        if self._fix_type_without_alt not in (2, 3):
            raise ValueError("fix_type_without_alt must be 2 or 3")
        self._vel_timeout = float(self.get_parameter("gps_vel_timeout_s").value)

        self.cfg = Config(
            forward_degraded=bool(self.get_parameter("forward_degraded").value),
            degraded_sigma_m=float(self.get_parameter("degraded_sigma_m").value),
            position_timeout_s=float(self.get_parameter("position_timeout_s").value),
            max_measurement_age_s=float(self.get_parameter("max_measurement_age_s").value),
            nav_status_timeout_s=float(self.get_parameter("nav_status_timeout_s").value),
            max_forward_sigma_m=float(self.get_parameter("max_forward_sigma_m").value))
        self.cfg.validate()
        rate = float(self.get_parameter("rate_hz").value)
        if rate <= 0:
            raise ValueError(f"rate_hz must be > 0 (got {rate})")

        self._serial = None
        port = str(self.get_parameter("nmea_port").value)
        if port:
            import serial
            self._serial = serial.Serial(port, int(self.get_parameter("nmea_baud").value),
                                         timeout=1, write_timeout=1)
        self._mav = None
        url = str(self.get_parameter("mavlink_url").value)
        if url:
            self._mav = mavlink_url.connect(url, int(self.get_parameter("mavlink_system_id").value),
                                            int(self.get_parameter("mavlink_component_id").value))
        topic = str(self.get_parameter("ros_fix_topic").value)
        self._pub_fix = self.create_publisher(NavSatFix, topic, 10) if topic else None
        if self._serial is None and self._mav is None and self._pub_fix is None:
            self.get_logger().warn("no output enabled (nmea_port, mavlink_url and ros_fix_topic are empty)")

        self._status = None
        self._status_rx = None
        self._pos = None
        self._pos_rx = None
        self._last_kind = None
        self._sent_pos = None             # the last position message sent (sent once)
        self._vel = None                  # (north, east) m/s from the GPS receiver
        self._vel_rx = None
        self.failed = False
        self.create_subscription(NavStatus, "/navera/nav_status", self._on_status, 10)
        self.create_subscription(PositionEstimate, "/navera/position", self._on_position, 10)
        self.create_subscription(TwistStamped, "/navera/sensors/gps_vel", self._on_gps_vel, 10)
        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(
            f"vehicle output: nmea={port or 'off'} mavlink={url or 'off'} ros={topic or 'off'} rate={rate:.1f}Hz "
            f"forward_degraded={self.cfg.forward_degraded}")

    def _on_status(self, msg: NavStatus) -> None:
        self._status, self._status_rx = msg, time.monotonic()

    def _on_position(self, msg: PositionEstimate) -> None:
        self._pos, self._pos_rx = msg, time.monotonic()
        # Forward at once: waiting for the next timer tick adds latency and, with
        # both at 5 Hz, drops or doubles messages — an irregular stream that
        # ArduPilot reports as "GPS not healthy" and refuses to arm on (SITL).
        self._tick()

    def _on_gps_vel(self, msg: TwistStamped) -> None:
        # gps_node publishes ENU: linear.x east, linear.y north.
        self._vel, self._vel_rx = (msg.twist.linear.y, msg.twist.linear.x), time.monotonic()

    def _tick(self) -> None:
        now = time.monotonic()
        st = self._status
        vel = (self._vel if self._vel is not None and now - self._vel_rx <= self._vel_timeout
               else None)
        out = decide(self.cfg,
                     st.state if st else None,
                     now - self._status_rx if st else None,
                     self._pos,
                     now - self._pos_rx if self._pos else None,
                     st.active_source if st else None, vel,
                     self._measured_age(self._pos))
        if out.kind != self._last_kind:
            # Separate call sites: rclpy refuses one call site changing severity.
            if out.kind == KIND_NONE:
                self.get_logger().warn(f"output → no fix ({out.reason})")
            else:
                self.get_logger().info(f"output → {out.kind} ({out.reason})")
            self._last_kind = out.kind
        if out.kind != KIND_NONE:
            if self._pos is self._sent_pos:
                return                    # already sent: wait for the next measurement
            self._sent_pos = self._pos
        # stamped with the measurement instant: GPS_INPUT time, NMEA time, NavSatFix stamp
        t_utc = datetime.now(timezone.utc) - timedelta(seconds=out.age_s)
        try:
            if self._serial is not None:
                spd = crs = math.nan
                if out.has_velocity:
                    spd = math.hypot(out.vel_n_mps, out.vel_e_mps)
                    crs = math.degrees(math.atan2(out.vel_e_mps, out.vel_n_mps)) % 360.0
                self._serial.write((nmea.gga(out, t_utc) + nmea.rmc(out, t_utc, spd, crs))
                                   .encode("ascii"))
            if self._mav is not None:
                self._mav.mav.gps_input_send(**mavlink_out.gps_input_fields(
                    out, t_utc, self._fix_type_without_alt))
            if self._pub_fix is not None:
                self._pub_fix.publish(self._navsatfix(out))
        except Exception as e:     # serial unplugged, socket error...
            self.get_logger().fatal(f"output failed: {e} — exiting so the service restarts")
            self.failed = True
            self.context.try_shutdown()


    def _measured_age(self, pos):
        """Seconds since the position was measured (sensor_stamp, else header stamp)."""
        if pos is None:
            return None
        s = pos.sensor_stamp if (pos.sensor_stamp.sec or pos.sensor_stamp.nanosec) else pos.header.stamp
        if not (s.sec or s.nanosec):
            return None
        return (self.get_clock().now().nanoseconds - (s.sec * 1_000_000_000 + s.nanosec)) / 1e9

    def _navsatfix(self, out) -> NavSatFix:
        """The output decision as a ROS GPS message: a fix with its stated accuracy as the
        covariance, or STATUS_NO_FIX with NaN position."""
        f = NavSatFix()
        f.header.stamp = (self.get_clock().now() - Duration(seconds=out.age_s)).to_msg()
        f.header.frame_id = "navera"
        f.status.service = NavSatStatus.SERVICE_GPS
        if out.kind == KIND_NONE:
            f.status.status = NavSatStatus.STATUS_NO_FIX
            f.latitude = f.longitude = f.altitude = math.nan
            f.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
            return f
        f.status.status = NavSatStatus.STATUS_FIX
        f.latitude, f.longitude, f.altitude = out.lat, out.lon, out.alt_ellipsoid_m
        if math.isfinite(out.sigma_h_m):
            v = out.sigma_v_m if math.isfinite(out.sigma_v_m) else 10.0 * out.sigma_h_m
            f.position_covariance = [out.sigma_h_m ** 2, 0.0, 0.0, 0.0, out.sigma_h_m ** 2, 0.0, 0.0, 0.0, v ** 2]
            f.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
        else:
            f.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        return f


def main(args=None) -> None:
    """Entry point. Exit code 0 on SIGINT/SIGTERM, 1 if an output fails."""
    die_with_parent()
    rclpy.init(args=args)
    try:
        node = VehicleOutputNode()
    except Exception as e:
        rclpy.logging.get_logger("vehicle_output").fatal(f"cannot start: {e}")
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
