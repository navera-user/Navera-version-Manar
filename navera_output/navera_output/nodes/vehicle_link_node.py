#!/usr/bin/env python3
"""vehicle_link_node.py — read the vehicle's own sensors from its autopilot (MAVLink).

For installations where NAVERA uses the vehicle's sensors instead of (or as well as)
its own: any MAVLink autopilot (ArduPilot, PX4, ...). Publishes, stamped on receipt:

    /navera/vehicle/imu            sensor_msgs/Imu          attitude (ENU, body FLU) + rates
    /navera/vehicle/altitude_agl   sensor_msgs/Range        downward rangefinder, tilt-corrected
    /navera/vehicle/relative_alt   geometry_msgs/PointStamped  z = height above home (barometer)
    /navera/vehicle/gps2           sensor_msgs/NavSatFix    the vehicle's second GPS, if any
    /navera/vehicle/status         std_msgs/String (JSON)   link, autopilot, armed, message rates

The live camera takes its attitude from /navera/vehicle/imu when NAVERA_SENSOR_SOURCE
is "vehicle" (camera_pkg live_camera.launch.py). The autopilot's own GPS position is
NOT read: when NAVERA feeds it, that would be NAVERA's output coming back.

Parameters:
    mavlink_url     e.g. serial:/dev/ttyTHS2:921600, udpin:0.0.0.0:14551, tcp:127.0.0.1:5763
                    (one port of the autopilot for NAVERA's reading; mavlink-router can
                    share one link between vehicle_output and this node)
    attitude_hz     requested attitude rate (default 50)
    source_system   NAVERA's MAVLink system id (default 1 = the vehicle's; component 192)
    relay_port      local UDP port (default 14650; 0 = off) whose MAVLink packets are passed
                    on to the autopilot: with a single autopilot port, vehicle_output sends
                    its GPS_INPUT to udpout:127.0.0.1:14650 and this node, which owns the
                    link, relays it (no mavlink-router needed)
"""
import json
import math
import socket
import threading
import time

import rclpy
from geometry_msgs.msg import PointStamped
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from sensor_msgs.msg import Imu, NavSatFix, NavSatStatus, Range
from std_msgs.msg import String

from navera_output import mavlink_url
from navera_output.mavlink_in import (attitude_euler, attitude_quaternion, downward_range_agl,
                                      rates_frd_to_flu)

MSG_IDS = {"ATTITUDE": 30, "ATTITUDE_QUATERNION": 31, "GLOBAL_POSITION_INT": 33,
           "DISTANCE_SENSOR": 132, "GPS2_RAW": 124, "SYSTEM_TIME": 2}


class VehicleLink(Node):
    def __init__(self, **kwargs):
        super().__init__("vehicle_link", **kwargs)
        self.declare_parameter("mavlink_url", "")
        declare_float(self, "attitude_hz", 50.0)
        self.declare_parameter("source_system", 1)
        # MAV_COMP_ID_ONBOARD_COMPUTER2: vehicle_output is 191 — two NAVERA connections
        # behind one mavlink-router must not share an identity
        self.declare_parameter("source_component", 192)
        self.declare_parameter("relay_port", 14650)
        self.url = str(self.get_parameter("mavlink_url").value)
        if not self.url:
            raise ValueError("mavlink_url is not set (e.g. serial:/dev/ttyTHS2:921600)")
        mavlink_url.parse(self.url)                  # a malformed address fails at start, not in the loop
        self.att_hz = float(self.get_parameter("attitude_hz").value)
        self.pub_imu = self.create_publisher(Imu, "/navera/vehicle/imu", 50)
        self.pub_agl = self.create_publisher(Range, "/navera/vehicle/altitude_agl", 10)
        self.pub_rel = self.create_publisher(PointStamped, "/navera/vehicle/relative_alt", 10)
        self.pub_gps2 = self.create_publisher(NavSatFix, "/navera/vehicle/gps2", 10)
        self.pub_status = self.create_publisher(String, "/navera/vehicle/status", 10)
        self.counts, self.last_hb, self.autopilot = {}, 0.0, None
        self.armed = None                  # from the autopilot heartbeat (None = unknown)
        self.q_last, self.q_t = None, 0.0
        self.quat_t = 0.0                  # last ATTITUDE_QUATERNION (monotonic); ATTITUDE used without it
        self._stop = threading.Event()
        self._link, self._write_lock, self.relayed = None, threading.Lock(), 0
        self._relay_sock = None
        port = int(self.get_parameter("relay_port").value)
        if port:
            try:
                self._relay_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._relay_sock.bind(("127.0.0.1", port))
                self._relay_sock.settimeout(0.5)
                threading.Thread(target=self._relay, daemon=True).start()
            except OSError as e:
                self.get_logger().error(f"relay port {port} unavailable ({e}): no relay")
                self._relay_sock = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.create_timer(1.0, self._status)
        self.get_logger().info(f"vehicle link on {self.url} (attitude {self.att_hz:.0f} Hz requested)")

    # ── link ──────────────────────────────────────────────────────────────
    def _connect(self):
        return mavlink_url.connect(self.url, int(self.get_parameter("source_system").value),
                                   int(self.get_parameter("source_component").value))

    def _request_streams(self, m):
        from pymavlink import mavutil
        rates = {"ATTITUDE_QUATERNION": self.att_hz, "ATTITUDE": self.att_hz, "GLOBAL_POSITION_INT": 10.0,
                 "DISTANCE_SENSOR": 10.0, "GPS2_RAW": 5.0, "SYSTEM_TIME": 1.0}
        for name, hz in rates.items():
            m.mav.command_long_send(m.target_system, m.target_component,
                                    mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                                    MSG_IDS[name], int(1e6 / hz), 0, 0, 0, 0, 0)
        # older autopilots: data streams (ignored by those that support message intervals)
        m.mav.request_data_stream_send(m.target_system, m.target_component,
                                       mavutil.mavlink.MAV_DATA_STREAM_ALL, int(min(self.att_hz, 50)), 1)

    def _run(self):
        from pymavlink import mavutil
        while not self._stop.is_set():
            try:
                m = self._connect()
                hb = self._wait_autopilot(m, timeout=10.0)
                if hb is None:
                    self.get_logger().warn(f"no heartbeat from an autopilot on {self.url} — retrying",
                                           throttle_duration_sec=30.0)
                    m.close()
                    continue
                self.autopilot = {mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA: "ArduPilot",
                                  mavutil.mavlink.MAV_AUTOPILOT_PX4: "PX4"}.get(
                                      hb.autopilot, f"MAVLink autopilot {hb.autopilot}")
                self.get_logger().info(f"connected to {self.autopilot} (system {m.target_system})")
                raw_write = m.write
                # two writers (this loop's heartbeats, the relay): never interleave packets
                m.write = lambda b, _w=raw_write: self._locked_write(_w, b)
                self._link = m
                self.last_hb, self.quat_t, self.q_last = time.monotonic(), 0.0, None
                self._request_streams(m)
                t_hb = 0.0
                while not self._stop.is_set():
                    if time.monotonic() - t_hb > 1.0:           # companion heartbeat: keeps streams on
                        m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                                             mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                        t_hb = time.monotonic()
                    msg = m.recv_match(blocking=True, timeout=0.5)
                    if msg is None:
                        if time.monotonic() - self.last_hb > 5.0:
                            raise ConnectionError("autopilot silent for 5 s")
                        continue
                    self._handle(msg, m.target_system)
            except Exception as e:                               # noqa: BLE001 — reconnect on anything
                self._link = None
                self.get_logger().error(f"vehicle link: {e} — reconnecting", throttle_duration_sec=10.0)
                time.sleep(2.0)

    def _locked_write(self, write, data):
        with self._write_lock:
            return write(data)

    def _relay(self):
        """Pass MAVLink packets from local NAVERA nodes (vehicle_output's GPS_INPUT) to the
        autopilot over this node's link.
        """
        while not self._stop.is_set():
            try:
                data, _ = self._relay_sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                return
            link = self._link
            if link is not None and data:
                try:
                    link.write(data)
                    self.relayed += 1
                except Exception as e:                           # noqa: BLE001 — the link loop reconnects
                    self.get_logger().warn(f"relay: {e}", throttle_duration_sec=10.0)

    @staticmethod
    def _wait_autopilot(m, timeout):
        """The first heartbeat FROM AN AUTOPILOT (a ground station, camera or another
        companion on a shared link also sends heartbeats): sets the link's target to it.
        """
        from pymavlink import mavutil
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=max(0.1, end - time.monotonic()))
            if hb is None:
                return None
            if hb.autopilot == mavutil.mavlink.MAV_AUTOPILOT_INVALID or hb.type in (
                    mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                    mavutil.mavlink.MAV_TYPE_GIMBAL, mavutil.mavlink.MAV_TYPE_CAMERA):
                continue
            m.target_system, m.target_component = hb.get_srcSystem(), hb.get_srcComponent()
            return hb
        return None

    # ── messages ──────────────────────────────────────────────────────────
    def _handle(self, msg, target_system):
        t = msg.get_type()
        if msg.get_srcSystem() != target_system:
            return
        self.counts[t] = self.counts.get(t, 0) + 1
        now = self.get_clock().now().to_msg()
        if t == "HEARTBEAT":
            if msg.autopilot != 8:                          # not MAV_AUTOPILOT_INVALID (a GCS on the same id)
                self.last_hb = time.monotonic()
                self.armed = bool(msg.base_mode & 128)      # MAV_MODE_FLAG_SAFETY_ARMED
        elif t == "ATTITUDE_QUATERNION":
            self.quat_t = time.monotonic()
            self._publish_imu(now, attitude_quaternion(msg.q1, msg.q2, msg.q3, msg.q4),
                              rates_frd_to_flu(msg.rollspeed, msg.pitchspeed, msg.yawspeed))
        elif t == "ATTITUDE" and time.monotonic() - self.quat_t > 1.0:     # no quaternion stream
            self._publish_imu(now, attitude_euler(msg.roll, msg.pitch, msg.yaw),
                              rates_frd_to_flu(msg.rollspeed, msg.pitchspeed, msg.yawspeed))
        elif t == "DISTANCE_SENSOR":
            # tilt-corrected with a CURRENT attitude only (a stale one would mis-correct)
            q = self.q_last if time.monotonic() - self.q_t <= 0.5 else None
            agl = downward_range_agl(msg.current_distance, msg.min_distance, msg.max_distance,
                                     msg.orientation, q)
            if q is None and self.q_last is not None:
                agl = None                                  # tilt unknown now: not a height
            if agl is not None:
                r = Range()
                r.header.stamp, r.header.frame_id = now, "vehicle_rangefinder"
                r.radiation_type = Range.INFRARED
                r.min_range, r.max_range, r.range = msg.min_distance / 100.0, msg.max_distance / 100.0, float(agl)
                self.pub_agl.publish(r)
        elif t == "GLOBAL_POSITION_INT":
            p = PointStamped()
            p.header.stamp, p.header.frame_id = now, "vehicle_home"
            p.point.z = msg.relative_alt / 1000.0
            self.pub_rel.publish(p)
        elif t == "GPS2_RAW" and msg.fix_type >= 3:
            f = NavSatFix()
            f.header.stamp, f.header.frame_id = now, "vehicle_gps2"
            f.status.status = NavSatStatus.STATUS_FIX
            f.latitude, f.longitude = msg.lat / 1e7, msg.lon / 1e7
            # NavSatFix altitude is above the WGS84 ellipsoid; GPS2_RAW.alt is above mean sea
            # level (tens of metres apart): the ellipsoid one when the autopilot gives it
            alt_e = getattr(msg, "alt_ellipsoid", 0) or 0
            if alt_e:
                f.altitude = alt_e / 1000.0
            else:
                f.altitude = msg.alt / 1000.0
                self.get_logger().warn("second GPS gives its altitude above sea level only: heights from "
                                       "it are MSL (set NAVERA_GROUND_ALTITUDE_M as MSL too)",
                                       throttle_duration_sec=600.0)
            h_acc, v_acc = getattr(msg, "h_acc", 0) or 0, getattr(msg, "v_acc", 0) or 0
            if h_acc > 0:                                   # mm: the receiver's own accuracy
                hv, vv = (h_acc / 1000.0) ** 2, (v_acc / 1000.0) ** 2 if v_acc > 0 else 4 * (h_acc / 1000.0) ** 2
                f.position_covariance = [hv, 0.0, 0.0, 0.0, hv, 0.0, 0.0, 0.0, vv]
                f.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
            self.pub_gps2.publish(f)

    def _publish_imu(self, stamp, q, rates):
        if not all(math.isfinite(c) for c in q):
            return
        self.q_last, self.q_t = q, time.monotonic()
        m = Imu()
        m.header.stamp, m.header.frame_id = stamp, "vehicle_base_link"
        m.orientation.x, m.orientation.y, m.orientation.z, m.orientation.w = q
        m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z = rates
        m.linear_acceleration_covariance[0] = -1.0                 # not provided
        self.pub_imu.publish(m)

    def _status(self):
        alive = time.monotonic() - self.last_hb < 3.0 if self.last_hb else False
        rates, self.counts = dict(self.counts), {}
        self.pub_status.publish(String(data=json.dumps(
            {"link": alive, "autopilot": self.autopilot, "armed": self.armed if alive else None,
             "url": self.url, "rates_hz": rates, "relayed_packets": self.relayed})))

    def destroy_node(self):
        self._stop.set()
        self._thread.join(timeout=3.0)
        super().destroy_node()


def main(args=None):
    die_with_parent()
    rclpy.init(args=args)
    node = VehicleLink()
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
