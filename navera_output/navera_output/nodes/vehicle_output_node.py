#!/usr/bin/env python3
"""
vehicle_output_node.py — NAVERA output to the vehicle's autopilot.

Turns the arbiter's decision (/navera/position + /navera/nav_status) into what
an autopilot understands as a GPS:

  * NMEA 0183 (GGA + RMC) on a serial port — any system that takes a GPS
    receiver (drones, boats, ground robots);
  * MAVLink GPS_INPUT — PX4 / ArduPilot with GPS_TYPE = MAV.

What is sent, and when a position is NOT sent, is decided in
navera_output.policy (see its docstring): FIX is a fix; DEGRADED is withheld
unless forward_degraded is set with a declared degraded_sigma_m; everything
else — including a stale or silent arbiter — is an explicit "no fix".

Parameters:
    rate_hz              (5.0)   output rate
    nmea_port            ("")    serial device for NMEA, "" = disabled
    nmea_baud            (9600)
    mavlink_url          ("")    pymavlink URL, e.g. "/dev/ttyTHS2,57600" or
                                 "udpout:127.0.0.1:14550"; "" = disabled
    mavlink_system_id    (1)     MAVLink ids of this box (companion computer)
    mavlink_component_id (191)
    forward_degraded     (False) send DEGRADED positions as "estimated"
    degraded_sigma_m     (NaN)   accuracy stated for them (required if forwarded)
    position_timeout_s   (2.0)   an older position is not current
    nav_status_timeout_s (2.0)   a silent arbiter means "no fix"

If an enabled output cannot be opened, the node exits with code 1 so the
service restarts it.
"""
import sys
import time
from datetime import datetime, timezone

import rclpy
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from navera_msgs.msg import NavStatus, PositionEstimate
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from navera_output import mavlink_out, nmea
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
        declare_float(self, "nav_status_timeout_s", 2.0)

        self.cfg = Config(
            forward_degraded=bool(self.get_parameter("forward_degraded").value),
            degraded_sigma_m=float(self.get_parameter("degraded_sigma_m").value),
            position_timeout_s=float(self.get_parameter("position_timeout_s").value),
            nav_status_timeout_s=float(self.get_parameter("nav_status_timeout_s").value))
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
            from pymavlink import mavutil
            self._mav = mavutil.mavlink_connection(
                url, source_system=int(self.get_parameter("mavlink_system_id").value),
                source_component=int(self.get_parameter("mavlink_component_id").value))
        if self._serial is None and self._mav is None:
            self.get_logger().warn("no output enabled (nmea_port and mavlink_url are empty)")

        self._status = None
        self._status_rx = None
        self._pos = None
        self._pos_rx = None
        self._last_kind = None
        self.failed = False
        self.create_subscription(NavStatus, "/navera/nav_status", self._on_status, 10)
        self.create_subscription(PositionEstimate, "/navera/position", self._on_position, 10)
        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(
            f"vehicle output: nmea={port or 'off'} mavlink={url or 'off'} rate={rate:.1f}Hz "
            f"forward_degraded={self.cfg.forward_degraded}")

    def _on_status(self, msg: NavStatus) -> None:
        self._status, self._status_rx = msg, time.monotonic()

    def _on_position(self, msg: PositionEstimate) -> None:
        self._pos, self._pos_rx = msg, time.monotonic()

    def _tick(self) -> None:
        now = time.monotonic()
        st = self._status
        out = decide(self.cfg,
                     st.state if st else None,
                     now - self._status_rx if st else None,
                     self._pos,
                     now - self._pos_rx if self._pos else None,
                     st.active_source if st else None)
        if out.kind != self._last_kind:
            # Separate call sites: rclpy refuses one call site changing severity.
            if out.kind == KIND_NONE:
                self.get_logger().warn(f"output → no fix ({out.reason})")
            else:
                self.get_logger().info(f"output → {out.kind} ({out.reason})")
            self._last_kind = out.kind
        t_utc = datetime.now(timezone.utc)
        try:
            if self._serial is not None:
                self._serial.write((nmea.gga(out, t_utc) + nmea.rmc(out, t_utc)).encode("ascii"))
            if self._mav is not None:
                self._mav.mav.gps_input_send(**mavlink_out.gps_input_fields(out, t_utc))
        except Exception as e:     # serial unplugged, socket error...
            self.get_logger().fatal(f"output failed: {e} — exiting so the service restarts")
            self.failed = True
            self.context.try_shutdown()


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
