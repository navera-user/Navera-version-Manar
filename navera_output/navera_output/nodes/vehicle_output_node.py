#!/usr/bin/env python3
"""vehicle_output_node.py — NAVERA output to the vehicle's autopilot.

Turns the arbiter's decision (/navera/position + /navera/nav_status) into what
an autopilot understands as a GPS:

  * NMEA 0183 (GGA + RMC) on a serial port — any system that takes a GPS
    receiver (drones, boats, ground robots);
  * MAVLink GPS_INPUT — ArduPilot with GPS_TYPE = MAV — or HIL_GPS — PX4 with
    MAV_USEHILGPS = 1 (PX4 ignores GPS_INPUT; mavlink_out.hil_gps_fields);
  * ROS: sensor_msgs/NavSatFix on ros_fix_topic (default /navera/fix), for vehicles
    whose software runs on ROS — the same decision, accuracy as the covariance.

What is sent, and when a position is NOT sent, is decided in
navera_output.policy (see its docstring): FIX is a fix; DEGRADED is withheld
unless forward_degraded is set with a declared degraded_sigma_m; everything
else — including a stale or silent arbiter — is an explicit "no fix".

Parameters:
    rate_hz              (5.0)   output rate
    nmea_port            ("")    serial device for the GPS emulation (NMEA or UBX), "" = disabled
    nmea_baud            (9600)
    nmea_protocol        ("nmea") nmea: GGA + RMC; ubx: u-blox NAV-PVT etc. (navera_output.ubx_out),
                                 for flight controllers that take a u-blox GPS (PX4, INAV, Betaflight,
                                 ArduPilot GPS_TYPE 2). UBX carries the accuracy: vision positions go out
                                 under forward_degraded as over MAVLink (nmea_forward_degraded not needed)
    ubx_estimated_satellites (0) satellite count stated in UBX with a non-GNSS position
    mavlink_url          ("")    e.g. "serial:/dev/ttyTHS2:921600" (navera_output.mavlink_url) or
                                 "udpout:127.0.0.1:14550"; "" = disabled
    mavlink_message      ("auto") gps_input (ArduPilot) | hil_gps (PX4) | auto: hil_gps once the
                                 autopilot's heartbeat says PX4 (MAV_AUTOPILOT_PX4 = 12, heard on
                                 this node's own link or in navera-vehicle-link's status), else
                                 gps_input
    mavlink_system_id    (1)     MAVLink ids of this box (companion computer); PX4 reads HIL_GPS
                                 only from its own system id (NAVERA_MAVLINK_SYSID)
    mavlink_component_id (191)
    ros_fix_topic        ("/navera/fix")  "" = disabled
    forward_degraded     (False) send DEGRADED positions as "estimated"
    nmea_forward_degraded (False) ALSO over NMEA. NMEA carries no accuracy an autopilot
                                 uses (ArduPilot fuses GGA/RMC with its own ~0.5 m GPS
                                 noise): a 30 m vision position would be trusted as a
                                 0.5 m GPS. Off: NMEA says "no fix" for them.
    degraded_sigma_m     (NaN)   accuracy stated for them (required if forwarded)
    max_forward_sigma_m  (1000)  a forwarded position coarser than this is withheld
    bridge_max_s         (10.0)  a gap in the forwarded vision positions is bridged this long
                                 (the last one carried along its velocity, sent about once a
                                 second with an accuracy growing with the gap), then "no fix".
                                 0 = never. Only with forward_degraded; never for a GPS fix
                                 (a vision FIX is bridged like an estimate)
    bridge_after_s       (2.5)   the bridge starts when nothing was sent for this long
    bridge_period_s      (1.0)   and repeats at this period
    bridge_accel_mps2    (0.5)   unseen acceleration of the vehicle in the accuracy growth
    bridge_heading_sigma_deg (5.0) heading error in the accuracy growth
    gnss_speed_sigma_mps (0.5)   accuracy stated for the GPS receiver's velocity
    reacquire_after_s    (5.0)   after nothing was sent for this long, a vision position waits
                                 until the velocity of the new fixes is known (0 = never wait) ...
    reacquire_vel_sigma_mps (8.0) ... to this 1-sigma (policy.reacquire, F28)
    drift_alarm_sigma_m  (100)   a forwarded (estimated) position this coarse raises a drift
                                 alarm in the log every 5 s: the vehicle is flying on a
                                 position that may be this far off (dead-reckoned, bridged)
    position_timeout_s   (5.0)   an older position is not current
    (mission-area guard) NavStatus.map_area NEAR_EDGE / OUTSIDE is passed on to the autopilot
                                 as a MAVLink STATUSTEXT (navera_output.map_guard), when it
                                 changes and every 30 s while it lasts: reported, never acted on
    max_measurement_age_s (5.0)  a position measured longer ago is not sent; the rest
                                 are sent stamped with their measurement instant
    nav_status_timeout_s (2.0)   a silent arbiter means "no fix"
    gps_vel_timeout_s    (1.0)   the GPS velocity (/navera/sensors/gps_vel) sent with
                                 a GPS position must be younger than this
    fix_type_without_alt (3)     MAVLink fix_type for a position with no altitude
                                 (vision / celestial): 3 = usable by ArduPilot / PX4,
                                 which then take height from the barometer; 2 = the
                                 literal label, which they ignore (mavlink_out)

Restart (B23): the last forwarded vision position (and the velocity sent with it) is kept in
the NAVERA state directory (navera_common.state_store "output_held", at most once a second). A
restarted output (crash, watchdog) resumes the bridge from it at once when it is younger than
bridge_max_s — the autopilot is given the carried position with its grown accuracy, not "no
fix" — and the next vision positions are not held back for their velocity (policy.reacquire):
the autopilot never timed its position out. A held position older than the bridge is never reused.

Each position is sent ONCE, as soon as it arrives (a 1 Hz vision fix is not repeated
5 times with fresh timestamps: an autopilot filter would read the repeats as
"stopped, then jumped"). "No fix" is sent at rate_hz, so the autopilot always
hears from NAVERA.

If an enabled output cannot be opened, the node exits with code 1 so the
service restarts it.
"""
import dataclasses
import json
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import rclpy
from navera_common import state_store
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from navera_common.track import TrackVelocity
from geometry_msgs.msg import TwistStamped
from sensor_msgs.msg import NavSatFix, NavSatStatus
from std_msgs.msg import String
from navera_msgs.msg import NavStatus, PositionEstimate
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from navera_output import mavlink_out, mavlink_url, nmea, ubx_out
from navera_output.map_guard import MapGuard
from navera_output.policy import (KIND_ESTIMATED, KIND_FIX, KIND_NONE, Config, Held, bridge, bridgeable,
                                  decide, for_nmea, hold, reacquire)


MAVLINK_MESSAGES = ("auto", "gps_input", "hil_gps")
HELD_STATE = "output_held"        # state_store name of the last forwarded vision position
HELD_SAVE_PERIOD_S = 1.0


def held_to_state(held: Held, t_wall: float) -> dict:
    """The held position as a state_store record; t_wall = the wall-clock instant of held.t."""
    return dict(lat=held.lat, lon=held.lon, sigma_h_m=held.sigma_h_m, t_wall=t_wall,
                ground_vel=list(held.ground_vel) if held.ground_vel is not None else None,
                sent_vel=list(held.sent_vel) if held.sent_vel is not None else None)


def held_from_state(d, now_mono: float, now_wall: float, max_age_s: float) -> Optional[Held]:
    """The Held of a state_store record carried onto this process's monotonic clock, or None when
    there is none, it is malformed, not finite, from the future or older than max_age_s.
    """
    if not isinstance(d, dict) or d.get("lat") is None:
        return None
    try:
        lat, lon, sig, t_wall = (float(d["lat"]), float(d["lon"]), float(d["sigma_h_m"]),
                                 float(d["t_wall"]))
        vecs = []
        for k in ("ground_vel", "sent_vel"):
            v = d.get(k)
            vecs.append(tuple(float(x) for x in v) if v is not None else None)
    except (KeyError, TypeError, ValueError):
        return None
    age = now_wall - t_wall
    if not (all(math.isfinite(x) for x in (lat, lon, sig, age)) and sig > 0 and 0.0 <= age <= max_age_s):
        return None
    if any(v is not None and (len(v) != 3 or not all(math.isfinite(x) for x in v)) for v in vecs):
        return None
    return Held(lat, lon, sig, now_mono - age, vecs[0], vecs[1])


def message_for_autopilot(autopilot) -> str:
    """The position message an autopilot takes: HIL_GPS for PX4 (MAV_AUTOPILOT_PX4 = 12), which has no
    GPS_INPUT handler; GPS_INPUT for ArduPilot and any other.
    """
    return "hil_gps" if autopilot == 12 else "gps_input"


class VehicleOutputNode(Node):
    def __init__(self):
        super().__init__("vehicle_output")
        declare_float(self, "rate_hz", 5.0)
        self.declare_parameter("nmea_port", "")
        self.declare_parameter("nmea_baud", 9600)
        self.declare_parameter("nmea_protocol", "nmea")
        self.declare_parameter("ubx_estimated_satellites", 0)
        self.declare_parameter("mavlink_url", "")
        self.declare_parameter("mavlink_message", "auto")
        self.declare_parameter("mavlink_system_id", 1)
        self.declare_parameter("mavlink_component_id", 191)
        self.declare_parameter("forward_degraded", False)
        self.declare_parameter("nmea_forward_degraded", False)
        declare_float(self, "degraded_sigma_m", float("nan"))
        declare_float(self, "position_timeout_s", 5.0)
        declare_float(self, "max_measurement_age_s", 5.0)
        # the vehicle's maximum speed (NAVERA_MAX_SPEED_KMH): a position whose ground velocity
        # is unknown grows its accuracy by this speed x its age
        declare_float(self, "max_speed_mps", 30.0)
        declare_float(self, "nav_status_timeout_s", 2.0)
        declare_float(self, "gps_vel_timeout_s", 1.0)
        declare_float(self, "max_forward_sigma_m", 1000.0)
        declare_float(self, "bridge_max_s", 10.0)
        declare_float(self, "bridge_after_s", 2.5)
        declare_float(self, "bridge_period_s", 1.0)
        declare_float(self, "bridge_accel_mps2", 0.5)
        declare_float(self, "bridge_heading_sigma_deg", 5.0)
        declare_float(self, "gnss_speed_sigma_mps", 0.5)
        declare_float(self, "reacquire_after_s", 5.0)
        declare_float(self, "reacquire_vel_sigma_mps", 8.0)
        declare_float(self, "drift_alarm_sigma_m", 100.0)
        self.declare_parameter("fix_type_without_alt", 3)
        self.declare_parameter("ros_fix_topic", "/navera/fix")
        # the frame of the vehicle's TF tree the fix refers to (robot_localization's
        # navsat_transform needs one it knows), and whether a ROS consumer gets the vision
        # positions: it reads their accuracy in the message itself, so by default it does —
        # only with a stated accuracy, never an invented one
        self.declare_parameter("ros_fix_frame_id", "navera")
        self.declare_parameter("ros_forward_degraded", True)
        self._fix_type_without_alt = int(self.get_parameter("fix_type_without_alt").value)
        if self._fix_type_without_alt not in (2, 3):
            raise ValueError("fix_type_without_alt must be 2 or 3")
        self._vel_timeout = float(self.get_parameter("gps_vel_timeout_s").value)

        self.cfg = Config(
            forward_degraded=bool(self.get_parameter("forward_degraded").value),
            degraded_sigma_m=float(self.get_parameter("degraded_sigma_m").value),
            position_timeout_s=float(self.get_parameter("position_timeout_s").value),
            max_measurement_age_s=float(self.get_parameter("max_measurement_age_s").value),
            max_speed_mps=float(self.get_parameter("max_speed_mps").value),
            nav_status_timeout_s=float(self.get_parameter("nav_status_timeout_s").value),
            max_forward_sigma_m=float(self.get_parameter("max_forward_sigma_m").value),
            bridge_max_s=float(self.get_parameter("bridge_max_s").value),
            bridge_after_s=float(self.get_parameter("bridge_after_s").value),
            bridge_period_s=float(self.get_parameter("bridge_period_s").value),
            bridge_accel_mps2=float(self.get_parameter("bridge_accel_mps2").value),
            bridge_heading_sigma_deg=float(self.get_parameter("bridge_heading_sigma_deg").value),
            gnss_speed_sigma_mps=float(self.get_parameter("gnss_speed_sigma_mps").value),
            reacquire_after_s=float(self.get_parameter("reacquire_after_s").value),
            reacquire_vel_sigma_mps=float(self.get_parameter("reacquire_vel_sigma_mps").value))
        self.cfg.validate()
        rate = float(self.get_parameter("rate_hz").value)
        if rate <= 0:
            raise ValueError(f"rate_hz must be > 0 (got {rate})")

        self._serial = None
        self._proto = str(self.get_parameter("nmea_protocol").value).strip().lower() or "nmea"
        if self._proto not in ("nmea", "ubx"):
            raise ValueError(f"nmea_protocol must be nmea or ubx (got {self._proto!r})")
        self._ubx_sats = int(self.get_parameter("ubx_estimated_satellites").value)
        self._ubx = ubx_out.Responder(int(self.get_parameter("nmea_baud").value)) if self._proto == "ubx" else None
        port = str(self.get_parameter("nmea_port").value)
        if port:
            import serial
            self._serial = serial.Serial(port, int(self.get_parameter("nmea_baud").value),
                                         timeout=1, write_timeout=1)
            if self._ubx is not None:
                self.create_timer(0.02, self._answer_ubx)       # the driver waits for its ACKs
        self._mav = None
        self._msg_mode = str(self.get_parameter("mavlink_message").value).strip().lower() or "auto"
        if self._msg_mode not in MAVLINK_MESSAGES:
            raise ValueError(f"mavlink_message must be one of {', '.join(MAVLINK_MESSAGES)} (got {self._msg_mode!r})")
        self._msg = "gps_input" if self._msg_mode == "auto" else self._msg_mode
        self._held_alt_msl = math.nan     # the last GNSS altitude sent (HIL_GPS needs one)
        url = str(self.get_parameter("mavlink_url").value)
        if url:
            if url.startswith("udpout:127.0.0.1:") or url.startswith("udpout:localhost:"):
                # to vehicle_link's relay: only useful while vehicle_link holds the autopilot link
                self._relay_link_rx = None
                self.create_subscription(String, "/navera/vehicle/status", self._on_link_status, 10)
                self.create_timer(5.0, self._check_relay)
            self._mav = mavlink_url.connect(url, int(self.get_parameter("mavlink_system_id").value),
                                            int(self.get_parameter("mavlink_component_id").value))
            if self._msg_mode == "auto":
                self.create_timer(1.0, self._poll_heartbeat)      # a direct link hears the autopilot
        topic = str(self.get_parameter("ros_fix_topic").value)
        self._pub_fix = self.create_publisher(NavSatFix, topic, 10) if topic else None
        if self._serial is None and self._mav is None and self._pub_fix is None:
            self.get_logger().warn("no output enabled (nmea_port, mavlink_url and ros_fix_topic are empty)")

        self._status = None
        self._status_rx = None
        self._pos = None
        self._track = TrackVelocity(window_s=20.0)   # ground velocity of the recent positions
        self._pos_rx = None
        self._last_kind = None
        self._sent_pos = None             # the last position message sent (sent once)
        self._held = None                 # the last forwarded estimate, for bridging a gap after it
        self._last_tx = None              # monotonic instant of the last position sent
        self._last_pos_tx = None          # same, kept across GPS fixes (policy.reacquire)
        self._bridging = False
        self._held_saved_at = None        # monotonic instant of the last held position saved
        self._restore_held()
        self._drift_alarm = float(self.get_parameter("drift_alarm_sigma_m").value)
        self._vel = None                  # (north, east) m/s from the GPS receiver
        self._vel_rx = None
        self.failed = False
        self._map_guard = MapGuard()      # mission-area guard -> STATUSTEXT (report only)
        self.create_subscription(NavStatus, "/navera/nav_status", self._on_status, 10)
        self.create_subscription(PositionEstimate, "/navera/position", self._on_position, 10)
        self.create_subscription(TwistStamped, "/navera/sensors/gps_vel", self._on_gps_vel, 10)
        self.create_timer(1.0 / rate, self._tick)
        self.get_logger().info(
            f"vehicle output: {self._proto}={port or 'off'} mavlink={url or 'off'}"
            f"{' (' + self._msg_mode + ')' if url else ''} ros={topic or 'off'} rate={rate:.1f}Hz "
            f"forward_degraded={self.cfg.forward_degraded}")
        self._nmea_degraded = bool(self.get_parameter("nmea_forward_degraded").value)
        if self._serial is not None and self.cfg.forward_degraded and self._proto == "nmea":
            if self._nmea_degraded:
                self.get_logger().warn("nmea_forward_degraded: vision positions go out over NMEA, which "
                                       "carries no accuracy — the autopilot will trust them as a precise GPS")
            else:
                self.get_logger().info("degraded positions: MAVLink/ROS only; NMEA says 'no fix' for them "
                                       "(NMEA carries no accuracy)")

    def _answer_ubx(self) -> None:
        """Acknowledge the flight controller's u-blox configuration (ubx_out.Responder)."""
        try:
            n = self._serial.in_waiting
            if not n:
                return
            reply, baud = self._ubx.feed(self._serial.read(n))
            if reply:
                self._serial.write(reply)
                self._serial.flush()
            if baud and baud != self._serial.baudrate:
                self.get_logger().info(f"UBX: the flight controller set the GPS port to {baud} baud")
                self._serial.baudrate = baud
        except Exception as e:     # serial unplugged...
            self.get_logger().fatal(f"output failed: {e} — exiting so the service restarts")
            self.failed = True
            self.context.try_shutdown()

    def _on_link_status(self, msg) -> None:
        try:
            st = json.loads(msg.data)
            if st.get("link"):
                self._relay_link_rx = time.monotonic()
                self._set_autopilot(12 if st.get("autopilot") == "PX4" else None)
        except (ValueError, AttributeError):
            pass

    def _poll_heartbeat(self) -> None:
        """mavlink_message auto on a direct link: the autopilot's heartbeats say which message it takes."""
        try:
            while True:
                hb = self._mav.recv_match(type="HEARTBEAT", blocking=False)
                if hb is None:
                    return
                if hb.autopilot != 8:                     # not MAV_AUTOPILOT_INVALID (a GCS)
                    self._set_autopilot(hb.autopilot)
        except Exception as e:     # a link without input (udpout before the first reply...)
            self.get_logger().debug(f"heartbeat poll: {e}")

    def _set_autopilot(self, autopilot) -> None:
        """mavlink_message auto: HIL_GPS for PX4 (MAV_AUTOPILOT_PX4 = 12), GPS_INPUT otherwise."""
        if self._msg_mode != "auto":
            return
        msg = message_for_autopilot(autopilot)
        if msg != self._msg:
            self._msg = msg
            self.get_logger().warn(f"MAVLink output: the autopilot is {'PX4' if msg == 'hil_gps' else 'not PX4'} "
                                   f"— sending {msg.upper()}"
                                   + (" (PX4 needs MAV_USEHILGPS = 1 and the EKF2 settings of "
                                      "docs/PX4_INTEGRATION.md)" if msg == "hil_gps" else ""))

    def _check_relay(self) -> None:
        rx = self._relay_link_rx
        if rx is None or time.monotonic() - rx > 10.0:
            self.get_logger().error(
                "MAVLink output goes to navera-vehicle-link's relay, but no vehicle link is connected "
                "to an autopilot: the autopilot receives NOTHING from NAVERA (enable navera-vehicle-link, "
                "check NAVERA_VEHICLE_MAVLINK_URL / the autopilot port)", throttle_duration_sec=30.0)

    def _on_status(self, msg: NavStatus) -> None:
        self._status, self._status_rx = msg, time.monotonic()
        say = self._map_guard.update(msg.map_area, msg.map_edge_m, self._status_rx)
        if say is not None:
            self.get_logger().warn(f"mission area: {say[1]}")
            if self._mav is not None:
                try:
                    self._mav.mav.statustext_send(say[0], say[1].encode("ascii")[:50])
                except Exception as e:     # noqa: BLE001 — the GPS_INPUT path reports link failures
                    self.get_logger().error(f"STATUSTEXT not sent: {e}", throttle_duration_sec=30.0)

    def _on_position(self, msg: PositionEstimate) -> None:
        self._pos, self._pos_rx = msg, time.monotonic()
        # the ground velocity of the recent positions (any source), to carry a vision
        # position from its photo's instant to now
        age = self._measured_age(msg)
        if age is not None and msg.valid and math.isfinite(msg.latitude):
            cov = list(msg.position_covariance)
            sig = math.sqrt(max(cov[0], cov[4])) if msg.position_covariance_type and cov[0] > 0 else 30.0
            self._track.add(time.time() - age, msg.latitude, msg.longitude, sig)
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
                     self._measured_age(self._pos), self._ground_velocity(), self._autopilot_velocity())
        out = self._bridged(out, now)
        if out is None:
            return                        # waiting: a bridge may start, nothing to send yet
        out = reacquire(self.cfg, out, None if self._last_pos_tx is None else now - self._last_pos_tx)
        if out.kind != self._last_kind:
            # Separate call sites: rclpy refuses one call site changing severity.
            if out.kind == KIND_NONE:
                self.get_logger().warn(f"output → no fix ({out.reason})")
            else:
                self.get_logger().info(f"output → {out.kind} ({out.reason})")
            self._last_kind = out.kind
        if out.kind != KIND_NONE and not out.bridged:
            if self._pos is self._sent_pos:
                return                    # already sent: wait for the next measurement
            self._sent_pos = self._pos
            self._held = hold(out, now, self._ground_velocity())
            self._bridging = False
            self._save_held(now)
        if out.kind != KIND_NONE:
            self._last_tx = self._last_pos_tx = now
        self._check_drift(out)
        # stamped with the measurement instant: GPS_INPUT time, NMEA time, NavSatFix stamp
        t_utc = datetime.now(timezone.utc) - timedelta(seconds=out.age_s)
        if out.gnss and math.isfinite(out.alt_msl_m):
            self._held_alt_msl = out.alt_msl_m
        try:
            if self._serial is not None and self._ubx is not None:
                self._serial.write(ubx_out.position_messages(out, t_utc, self._held_alt_msl, self._ubx_sats,
                                                             self._ubx.position_ids()))
            elif self._serial is not None:
                nmea_out = for_nmea(out, self._nmea_degraded)
                spd = crs = math.nan
                if out.has_velocity:
                    spd = math.hypot(out.vel_n_mps, out.vel_e_mps)
                    crs = math.degrees(math.atan2(out.vel_e_mps, out.vel_n_mps)) % 360.0
                self._serial.write((nmea.gga(nmea_out, t_utc) + nmea.rmc(nmea_out, t_utc, spd, crs))
                                   .encode("ascii"))
            if self._mav is not None:
                if self._msg == "hil_gps":
                    self._mav.mav.hil_gps_send(**mavlink_out.hil_gps_fields(out, t_utc, self._held_alt_msl))
                else:
                    self._mav.mav.gps_input_send(**mavlink_out.gps_input_fields(
                        out, t_utc, self._fix_type_without_alt))
            if self._pub_fix is not None:
                self._pub_fix.publish(self._navsatfix(self._ros_output(out)))
        except Exception as e:     # serial unplugged, socket error...
            self.get_logger().fatal(f"output failed: {e} — exiting so the service restarts")
            self.failed = True
            self.context.try_shutdown()

    def _check_drift(self, out) -> bool:
        """Drift alarm (F1/F6): an estimated position coarser than drift_alarm_sigma_m given to the
        vehicle is logged as an alarm, at most every 5 s. Returns True when it is one.
        """
        if out.kind != KIND_ESTIMATED or not out.sigma_h_m > self._drift_alarm:
            return False
        self.get_logger().warn(
            f"DRIFT ALARM: the vehicle is given a position of ±{out.sigma_h_m:.0f} m "
            f"({'bridged' if out.bridged else out.reason}) — it may be that far off",
            throttle_duration_sec=5.0)
        return True

    def _bridged(self, out, now):
        """`out`, or the held position carried to now when the positions stopped coming (policy.bridge),
        or None to wait (a bridge is pending: nothing is sent yet, the autopilot is not told "no fix"
        for a gap that may be bridged).
        """
        if out.kind == KIND_FIX and out.gnss:
            if self._held is not None:
                state_store.save(HELD_STATE, {"lat": None})     # a restart must not bridge it either
                self._held_saved_at = None
            self._held = self._last_tx = None
            self._bridging = False
            return out
        # a vision FIX (calibrated accuracy) is bridged like an estimate: its gaps are the camera's
        pending = (bridgeable(out) and self._pos is self._sent_pos) or (out.kind == KIND_NONE and out.soft)
        if not pending or self._held is None or self.cfg.bridge_max_s <= 0 or self._last_tx is None:
            if self._bridging and out.kind == KIND_NONE:
                self._bridging = False
            return out
        gap = now - self._last_tx
        if gap < (self.cfg.bridge_period_s if self._bridging else self.cfg.bridge_after_s):
            return None if out.kind == KIND_NONE else out
        b = bridge(self.cfg, self._held, now)
        if b.kind == KIND_NONE:
            if self._bridging:
                self.get_logger().warn(f"bridge ended: {b.reason}")
            self._bridging = False
            self._held = None             # over: plain "no fix" from here on, until a new position
            return b
        if not self._bridging:
            self.get_logger().warn(f"no new position for {gap:.1f} s: bridging along the last one "
                                   f"(at most {self.cfg.bridge_max_s:.0f} s)")
        self._bridging = True
        return b

    def _save_held(self, now) -> None:
        """Persist the held position (at most once a second) for a restart of this node."""
        if self._held is None or (self._held_saved_at is not None
                                  and now - self._held_saved_at < HELD_SAVE_PERIOD_S):
            return
        self._held_saved_at = now
        state_store.save(HELD_STATE, held_to_state(self._held, time.time() - (now - self._held.t)))

    def _restore_held(self) -> None:
        """Restarted in flight: bridge on from the last position this node gave the autopilot."""
        if not self.cfg.forward_degraded or self.cfg.bridge_max_s <= 0:
            return
        held = held_from_state(state_store.load(HELD_STATE, self.cfg.bridge_max_s + 1.0),
                               time.monotonic(), time.time(), self.cfg.bridge_max_s)
        if held is None:
            return
        self._held = held
        self._last_tx = self._last_pos_tx = held.t
        self.get_logger().warn(f"restart: the last position given to the autopilot "
                               f"{time.monotonic() - held.t:.1f} s ago (±{held.sigma_h_m:.0f} m) is "
                               f"bridged on until new positions come (at most {self.cfg.bridge_max_s:.0f} s)")

    def _ground_velocity(self):
        """(east, north, sigma) m/s of the vehicle at its latest position, or None: a quadratic fit
        of the last 15 s (a turn's heading at that fix, not the 20 s chord's — 37 m sideways at
        60 m/s carried 3 s, Isaac 2026-10-24), else the line fit of the last 20 s.
        """
        last = self._track.last_time()
        if last is None or time.time() - last > 5.0:
            return None
        return self._track.velocity_at_last_fix() or self._track.velocity(time.time())

    def _autopilot_velocity(self):
        """(east, north, sigma) m/s trustworthy enough for the autopilot, or None."""
        last = self._track.last_time()
        if last is None or time.time() - last > 5.0:
            return None
        return self._track.autopilot_velocity(time.time())

    def _measured_age(self, pos):
        """Seconds since the position was measured (sensor_stamp, else header stamp)."""
        if pos is None:
            return None
        s = pos.sensor_stamp if (pos.sensor_stamp.sec or pos.sensor_stamp.nanosec) else pos.header.stamp
        if not (s.sec or s.nanosec):
            return None
        return (self.get_clock().now().nanoseconds - (s.sec * 1_000_000_000 + s.nanosec)) / 1e9

    def _ros_output(self, out):
        """The decision for ROS: as for the autopilot, plus degraded positions with their
        stated accuracy when ros_forward_degraded (independent of forward_degraded).
        """
        if out.kind != KIND_NONE or self.cfg.forward_degraded or \
                not bool(self.get_parameter("ros_forward_degraded").value):
            return out
        st = self._status
        now = time.monotonic()
        return decide(dataclasses.replace(self.cfg, forward_degraded=True),
                      st.state if st else None, now - self._status_rx if st else None,
                      self._pos, now - self._pos_rx if self._pos else None,
                      st.active_source if st else None, None,
                      self._measured_age(self._pos), self._ground_velocity())

    def _navsatfix(self, out) -> NavSatFix:
        """The output decision as a ROS GPS message: a fix with its stated accuracy as the
        covariance, or STATUS_NO_FIX with NaN position.
        """
        f = NavSatFix()
        f.header.stamp = (self.get_clock().now() - Duration(seconds=out.age_s)).to_msg()
        f.header.frame_id = str(self.get_parameter("ros_fix_frame_id").value)
        # a vision / celestial position is no satellite service: a consumer can tell
        f.status.service = NavSatStatus.SERVICE_GPS if out.gnss else 0
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
