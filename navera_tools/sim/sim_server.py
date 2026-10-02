#!/usr/bin/env python3
"""NAVERA mission simulator — the whole system, no hardware.

    navera_tools/run_sim.sh            (then open http://<jetson-ip>:8190)

What runs, and what is simulated:

    REAL  navera_estimator, gps_node (NMEA driver), vehicle_output (MAVLink
          GPS_INPUT), the web bridge and operator view (:8181), and an
          ArduPilot autopilot (SITL: copter for the drone, rover for the boat
          and the ground robot) whose ONLY position input is NAVERA's output.
    SIM   the world: the vehicle's true motion (ArduPilot's physics), the GPS
          receiver (NMEA on a pseudo-terminal, with jamming and spoofing), the
          IMU and clock samples, and the vision fixes, whose error follows a
          chosen profile: "measured" (what day/night vision measure today) or
          "target" (the accuracy goal, NOT measured).

The control page (:8190) sets the start point and destination on the map,
the vehicle, speed and altitude, injects faults, and shows the truth, NAVERA's
decision, the autopilot's own belief, every sensor and an event log.
Everything published is labelled simulated; the operator view shows a
SIMULATION banner.
"""
import json
import math
import os
import random
import signal
import subprocess
import sys
import shutil
import threading
import time
import traceback
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

if os.environ.get("NAVERA_ALLOW_SIM") != "1":
    sys.exit("refusing to run: the simulator publishes simulated data on the NAVERA topics. "
             "Start it with navera_tools/run_sim.sh.")

import rclpy  # noqa: E402
from rclpy.executors import MultiThreadedExecutor  # noqa: E402
from rclpy.node import Node  # noqa: E402
from sensor_msgs.msg import Imu, NavSatFix, TimeReference  # noqa: E402
from std_msgs.msg import String  # noqa: E402

from navera_msgs.msg import NavStatus, PositionEstimate  # noqa: E402
from simulation_web.web_common import MBTilesReader, parse_tile_path  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from autopilot import FLYING, NAVERA_URL, VEHICLES, Autopilot  # noqa: E402
from camera_view import CameraView  # noqa: E402
from nmea_gps import MODES as GPS_MODES, NmeaGps  # noqa: E402
from vision_link import TILE_URL, TOPICS, AreaManager, MultiTiles, StarCamera, VisionCamera  # noqa: E402
from cn_pkg.nodes.celestial_math import boresight_altaz  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
M_PER_DEG = 111_320.0
SRC_NAME = {NavStatus.SOURCE_GPS: "GPS", NavStatus.SOURCE_DAY_VISION: "DAY VISION",
            NavStatus.SOURCE_NIGHT_VISION: "NIGHT VISION", NavStatus.SOURCE_CELESTIAL: "CELESTIAL",
            NavStatus.SOURCE_INERTIAL: "INERTIAL"}
STATE_NAME = {NavStatus.STATE_INITIALIZING: "STARTING", NavStatus.STATE_NO_FIX: "NO FIX",
              NavStatus.STATE_FIX: "FIX", NavStatus.STATE_DEGRADED: "DEGRADED"}
# Vision error profiles. measured: docs/VALIDATION_STATUS.md (day ~440 m median,
# night drifts: its estimate advanced ~25 % of the true motion on the replay set).
DAY_MEASURED_SIGMA = 440.0 / math.sqrt(2.0 * math.log(2.0))
DAY_TARGET_SIGMA = 15.0
NIGHT_TARGET_SIGMA = 25.0
NIGHT_MEASURED_GAIN = 0.25
DEFAULTS = {"drone": (15.0, 150.0), "boat": (8.0, 0.0), "robot": (4.0, 0.0), "plane": (40.0, 300.0)}
# Default top speed of each vehicle type (m/s): NAVERA's max_speed_mps — the GPS
# plausibility gate and the vision motion gates. The operator sets the real
# vehicle's top speed (a fast aircraft: hundreds of m/s).
MAX_SPEED = {"drone": 30.0, "boat": 20.0, "robot": 10.0, "plane": 100.0}
MAX_SPEED_LIMIT = 525.0     # m/s (1890 km/h = 1260 km/h cruise + 50 %): highest top speed accepted
# What the simulated autopilot can actually fly (ArduCopter WPNAV_SPEED ≤ 20 m/s,
# ArduPilot Rover models): the cruise speed is capped here, whatever the top speed.
SIM_CRUISE_MAX = {"drone": 20.0, "boat": 15.0, "robot": 8.0, "plane": 75.0}
# the simulated ceiling (m); the page states it. The plane is capped where the simulated
# camera still renders a sensible view (NAVERA's vision is tested up to ~400 m only).
SIM_ALT_MAX = {"drone": 400.0, "plane": 1000.0}
SIM_ALT_MIN = {"drone": 30.0, "plane": 100.0}


def _legs(route):
    from day_pkg.prepare_area import densify_route
    return densify_route(route)


def _route_dist(p, route):
    from day_pkg.prepare_area import _dist_to_route_m
    return _dist_to_route_m(p[0], p[1], route)


def haversine_m(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, h)))


def offset(lat, lon, east, north):
    return (lat + north / M_PER_DEG, lon + east / (M_PER_DEG * math.cos(math.radians(lat))))


SIM_TAG = "NAVERA_SIM_CHILD"   # in the environment of every node the simulator starts


def kill_leftover_nodes(log=print):
    """Stop the NAVERA nodes a previous simulator left running (tagged with SIM_TAG):
    an orphan estimator would compete with the new one ("2 publishers on
    /navera/position") and its decisions would interleave with the real ones."""
    me, killed = os.getpid(), []
    for pid in (int(p) for p in os.listdir("/proc") if p.isdigit()):
        if pid == me:
            continue
        try:
            with open(f"/proc/{pid}/environ", "rb") as f:
                if (SIM_TAG + "=1").encode() not in f.read().split(b"\0"):
                    continue
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except (OSError, PermissionError):
            continue
    if killed:
        log(f"stopped {len(killed)} NAVERA process(es) left running by a previous simulator")
        time.sleep(2.0)
        for pid in killed:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass


class Proc:
    """A NAVERA node run as in production, in its own process group.

    start/stop/restart_if_dead share one lock: the mission (which restarts the
    estimator) and the process watchdog must never both start it — the second
    start would replace the handle of the first and leave an orphan node."""

    def __init__(self, name, cmd, log_dir, env=None):
        self.name, self.cmd, self.env = name, cmd, env
        self.log_path = os.path.join(log_dir, f"{name}.log")
        self.p = None
        self.t_start = None
        self.lock = threading.Lock()

    def start(self):
        with self.lock:
            self._start()

    def restart_if_dead(self) -> bool:
        """Start it again if it died (watchdog); False when it is running or busy."""
        if not self.lock.acquire(blocking=False):
            return False                       # being (re)started by the mission right now
        try:
            if self.p is not None and self.p.poll() is None:
                return False
            self._start()
            return True
        finally:
            self.lock.release()

    def _start(self):
        self._stop()
        log = open(self.log_path, "a")                # kept across restarts, for diagnosis
        log.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} start: {' '.join(self.cmd)}\n")
        log.flush()
        self.t_start = time.monotonic()
        self.p = subprocess.Popen(self.cmd, stdout=log, stderr=subprocess.STDOUT,
                                  start_new_session=True,
                                  env=dict(os.environ, **(self.env or {}), **{SIM_TAG: "1"}))

    def alive(self):
        return self.p is not None and self.p.poll() is None

    def stop(self):
        with self.lock:
            self._stop()

    def _stop(self):
        if self.alive():
            try:
                os.killpg(self.p.pid, signal.SIGINT)
                self.p.wait(timeout=8)
            except Exception:
                os.killpg(self.p.pid, signal.SIGKILL)
        self.p = None


class Simulator(Node):
    def __init__(self, work_dir, mbtiles, ardupilot):
        super().__init__("navera_simulator")
        self.work = work_dir
        self.lock = threading.RLock()
        self.events = deque(maxlen=200)
        self.series = deque(maxlen=900)             # (t, navera_err, autopilot_err, source)
        self.rng = random.Random(7)
        self.t0 = time.monotonic()
        self.tiles = MultiTiles([MBTilesReader(mbtiles, self.get_logger()),
                                 MBTilesReader(os.path.join(work_dir, "world_tiles.mbtiles"),
                                               self.get_logger())])
        self.camera = CameraView(self.tiles)
        self.gps = NmeaGps()
        self.ap = Autopilot(ardupilot, work_dir, self.event)

        self.cfg = dict(vehicle="drone", start=[35.8256, 10.6385], dest=None, speed=15.0,
                        alt=150.0, profile="measured", vision="real", area=None,
                        forward_degraded=False, degraded_sigma_m=500.0, max_speed_mps=MAX_SPEED["drone"])
        self.faults = dict(gps="ok", camera="ok", light="day", imu="ok")
        self.phase = "idle"                     # idle, starting, waiting_gps, takeoff, enroute, arrived, ...
        self.phase_detail = "Choose a start point and a destination on the map, then Start."
        self.nav = dict(state="—", source="—", reason="", lat=None, lon=None, mode="", t=0.0)
        # ROS link watchdog (a plain thread: it must not depend on the ROS executor it checks)
        self._last_status_t = None
        self._wps, self._wp_i = [], 0              # the legs being flown
        self.ros_link = dict(ok=True, since=None, detail="")
        threading.Thread(target=self._watch_ros_link, daemon=True).start()
        self.gps_node_out = dict(valid=False, t=0.0, sats=0, hdop=None, reason="")
        self.sources = {}
        self.night_est = None
        self.mission_thread = None
        self._abort = threading.Event()
        self._last_state = None
        self._last_source = None
        self._closing = False
        self._had_gps = False             # a GPS fix was seen in this mission (vision prior)
        self.phase_t0 = time.monotonic()

        env_note = ", ".join(f"{k}={os.environ.get(k)}" for k in ("ROS_DOMAIN_ID", "ROS_LOCALHOST_ONLY"))
        self.procs = {
            "estimator": Proc("estimator", ["ros2", "run", "navera_estimator", "estimator_node.py",
                                            "--ros-args", "-p", "max_speed_mps:=60.0"], work_dir),
            "gps_node": Proc("gps_node", ["ros2", "run", "gps_pkg", "gps_node.py", "--ros-args",
                                          "-p", f"serial_port:={self.gps.port}"], work_dir),
            "web_bridge": Proc("web_bridge", ["ros2", "run", "simulation_web", "navera_web_bridge.py",
                                              "--ros-args", "-p", f"mbtiles_path:={mbtiles}"], work_dir),
        }
        for p in self.procs.values():
            p.start()
        self.event("info", f"NAVERA nodes started ({env_note}); GPS receiver on {self.gps.port}")

        self.areas = AreaManager(mbtiles, work_dir, self.event)
        # physical cameras: raw lens frames at the TRUE attitude, through NAVERA's live camera
        self.daycam = VisionCamera(self, self.tiles, self._truth, self.event, "day", self._true_attitude)
        self.nightcam = VisionCamera(self, self.tiles, self._truth, self.event, "night", self._true_attitude)
        self.starcam = StarCamera(self, work_dir, self._truth, self._true_boresight,
                                  self._sky_utc, self.event)
        self.sky_base = None                  # (utc epoch at switch, monotonic at switch)
        self.imu_bias = (0.0, 0.0, 0.0)       # roll, pitch, yaw (rad): drawn per mission
        self.pub_truth = self.create_publisher(NavSatFix, "/navera/sim/truth", 10)
        self.pub_imu = self.create_publisher(Imu, "/navera/sensors/imu", 10)
        self.pub_state_true = self.create_publisher(String, "/navera/sim/state_true", 10)
        self.pub_rtc = self.create_publisher(TimeReference, "/navera/sensors/rtc_time", 10)
        self.pub_rtcs = self.create_publisher(String, "/navera/sensors/rtc_status", 10)
        self.pub_day = self.create_publisher(PositionEstimate, "/navera/estimate/day", 10)
        self.pub_night = self.create_publisher(PositionEstimate, "/navera/estimate/night", 10)
        self.create_subscription(NavStatus, "/navera/nav_status", self._on_status, 10)
        self.create_subscription(PositionEstimate, "/navera/position", self._on_position, 10)
        self.create_subscription(PositionEstimate, "/navera/estimate/gps", self._on_gps_est, 10)
        self.create_timer(0.2, self._tick_gps)
        self.create_timer(0.05, self._tick_imu)
        self.create_timer(1.0, self._tick_slow)

    # ---------------- events ----------------
    def event(self, level, text):
        t = time.monotonic() - self.t0
        with self.lock:
            if self.events and self.events[-1]["text"] == text:
                return
            self.events.append({"t": round(t, 1), "level": level, "text": text,
                                "clock": time.strftime("%H:%M:%S")})
        self.get_logger().info(text)

    # ---------------- ROS inputs ----------------
    def _on_status(self, m):
        state, src = STATE_NAME.get(m.state, "?"), SRC_NAME.get(m.active_source, "—")
        self._last_status_t = time.monotonic()
        with self.lock:
            self.nav.update(state=state, reason=m.reason, source=src if m.state in (
                NavStatus.STATE_FIX, NavStatus.STATE_DEGRADED) else "—")
            self.sources = {SRC_NAME.get(s.source, str(s.source)): dict(alive=s.alive, contributing=s.contributing)
                            for s in m.sources}
        if (state, src) != (self._last_state, self._last_source) and state != "STARTING":
            lvl = "ok" if state == "FIX" else ("warn" if state == "DEGRADED" else "error")
            self.event(lvl, f"NAVERA: {state}" + (f" — {src}" if state in ("FIX", "DEGRADED") else "")
                       + (f" ({m.reason})" if m.reason else ""))
            self._last_state, self._last_source = state, src

    def _on_position(self, m):
        with self.lock:
            self.nav.update(lat=m.latitude, lon=m.longitude, t=time.monotonic(),
                            mode={0: "measured", 1: "dead-reckoned", 2: "held"}.get(m.mode, ""))

    def _on_gps_est(self, m):
        try:
            d = json.loads(m.details_json or "{}")
        except ValueError:
            d = {}
        if m.valid:
            self._had_gps = True
        with self.lock:
            self.gps_node_out = dict(valid=bool(m.valid), t=time.monotonic(), reason=m.reason,
                                     sats=d.get("num_sats"), hdop=d.get("hdop"))

    # ---------------- simulated sensors ----------------
    def _truth(self):
        s = self.ap.snapshot()
        return s["truth"] if s["link"] else None

    def _tick_gps(self):
        tr = self._truth()
        if tr is None:
            return
        lat, lon, alt = tr[0], tr[1], tr[2]
        fix = NavSatFix()
        fix.header.stamp = self.get_clock().now().to_msg()
        fix.header.frame_id = "sim_truth"
        fix.latitude, fix.longitude, fix.altitude = lat, lon, alt
        self.pub_truth.publish(fix)
        self.gps.tick(lat, lon, tr[9], tr[4], tr[5], 0.2)

    @staticmethod
    def _quat_enu(roll, pitch, yaw):
        """ArduPilot NED attitude (rad) → ROS ENU body (FLU) quaternion (x, y, z, w)."""
        y, p, r = math.pi / 2 - yaw, -pitch, roll
        cy, sy, cp, sp, cr, sr = (math.cos(y / 2), math.sin(y / 2), math.cos(p / 2),
                                  math.sin(p / 2), math.cos(r / 2), math.sin(r / 2))
        return (sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
                cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)

    def _true_attitude(self):
        """The vehicle's true attitude (flight physics), body ENU quaternion."""
        s = self.ap.snapshot()
        return self._quat_enu(*s["attitude"]) if s["link"] else None

    def _live_camera_cmd(self, kind):
        """NAVERA's live camera node fed by the simulated physical camera (box or vehicle
        sensors, as NAVERA_SENSOR_SOURCE on the box)."""
        import yaml
        cam = self.nightcam if kind == "night" else self.daycam
        calib = os.path.join(self.work, f"{kind}_lens.yaml")
        with open(calib, "w") as f:
            yaml.safe_dump(cam.lens, f)
        ns, ready = ("thermal", "/night/localizer_ready") if kind == "night" else ("day", "/day/localizer_ready")
        vehicle = self.cfg.get("sensor_source") == "vehicle"
        return ["ros2", "run", "camera_pkg", "live_camera.py", "--ros-args", "-r", f"__ns:=/{ns}",
                "-p", "input:=ros", "-p", f"input_topic:={TOPICS[kind]['raw']}",
                "-p", f"width:={cam.lens['image_width']}", "-p", f"height:={cam.lens['image_height']}",
                "-p", f"calibration_file:={calib}", "-p", "fps:=1.0",
                "-p", f"camera_type:={'thermal' if kind == 'night' else 'day'}",
                "-p", "wait_for_ready:=true", "-p", f"ready_topic:={ready}",
                "-p", f"imu_topic:={'/navera/vehicle/imu' if vehicle else '/navera/sensors/imu'}",
                "-p", f"attitude_source:={'vehicle' if vehicle else 'imu'}",
                "-p", f"gimbal:={'true' if self.cfg.get('camera_mount') == 'gimbal' else 'false'}"]

    def _sim_camera_cmd(self, kind):
        """The simulated physical camera, its own process (sim_camera_node.py)."""
        self._live_camera_cmd(kind)                    # writes the lens file
        return [sys.executable, os.path.join(HERE, "sim_camera_node.py"), "--ros-args",
                "-p", f"kind:={kind}", "-p", f"lens_file:={os.path.join(self.work, kind + '_lens.yaml')}",
                "-p", f"raw_topic:={TOPICS[kind]['raw']}",
                "-p", f"maps:={self.tiles.path}:{os.path.join(self.work, 'world_tiles.mbtiles')}",
                "-p", f"day_camera_at_night:={'true' if kind == 'day' and self.faults['light'] == 'night' else 'false'}"]

    def _true_boresight(self):
        """True (alt, az) of the upward star camera, from the physics attitude."""
        s = self.ap.snapshot()
        if not s["link"]:
            return None
        return boresight_altaz(self._quat_enu(*s["attitude"]), 90.0, 0.0, 0.0)

    def _night_map(self):
        """The map the night localizer reads: the onboard map when it covers the whole
        route corridor, else the cache (prepare_area makes it complete for the corridor)."""
        plan = self.areas.state()["plan"]
        if plan and plan["in_base"] < plan["tiles"] and os.path.exists(self.areas.cache):
            return self.areas.cache
        return self.tiles.path

    def _sky_utc(self):
        """Simulated sky time: tonight 20:30 UTC + elapsed since the switch to night."""
        if self.sky_base is None:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        return time.strftime("%Y-%m-%d %H:%M:%S",
                             time.gmtime(self.sky_base[0] + time.monotonic() - self.sky_base[1]))

    def _tick_imu(self):
        if self.faults["imu"] != "ok":
            return
        s = self.ap.snapshot()
        if not s["link"]:
            return
        roll, pitch, yaw = s["attitude"]
        # BNO085-class IMU: constant attitude bias drawn per mission + small noise
        br, bp, by = self.imu_bias
        n = lambda: self.rng.gauss(0.0, math.radians(0.05))     # noqa: E731
        qx, qy, qz, qw = self._quat_enu(roll + br + n(), pitch + bp + n(), yaw + by + n())
        imu = Imu()
        imu.header.stamp = self.get_clock().now().to_msg()
        imu.header.frame_id = "imu_link"
        imu.orientation.x, imu.orientation.y, imu.orientation.z, imu.orientation.w = qx, qy, qz, qw
        gx, gy, gz = s["gyro"]
        imu.angular_velocity.x, imu.angular_velocity.y, imu.angular_velocity.z = gx, -gy, -gz
        imu.linear_acceleration.z = 9.81
        self.pub_imu.publish(imu)
        tr = s["truth"]
        if tr is not None:                     # the true state, for the camera process
            gimbal = self.cfg.get("camera_mount") == "gimbal"   # a gimbal holds the camera level
            q_cam_body = self._quat_enu(0.0, 0.0, yaw) if gimbal else self._quat_enu(roll, pitch, yaw)
            self.pub_state_true.publish(String(data=json.dumps(dict(
                lat=tr[0], lon=tr[1], agl=tr[2], heading=tr[3], speed=tr[4], vn=tr[6], ve=tr[7], vd=tr[8],
                q=list(q_cam_body)))))

    def _tick_slow(self):
        now = self.get_clock().now().to_msg()
        tr = TimeReference()
        tr.header.stamp = now
        tr.time_ref = now
        tr.source = "simulator"
        self.pub_rtc.publish(tr)
        self.pub_rtcs.publish(String(data=json.dumps({"valid": True, "simulated": True})))
        truth = self._truth()
        if truth is not None:
            self._vision(truth, now)
        self._record(truth)
        self._watch_procs()

    def _vision(self, truth, now):
        if self.cfg["vision"] == "real":
            return                        # the real vision nodes do it (VisionCamera)
        if not self._had_gps:
            return                        # like the real nodes: no prior, no position
        lat, lon = truth[0], truth[1]
        night = self.faults["light"] == "night"
        if self.faults["camera"] != "ok":
            self.night_est = None
            return
        target = self.cfg["profile"] == "target"
        with self.lock:
            nav_gps = self.nav["source"] == "GPS" and self.nav["lat"] is not None
            gps_pos = (self.nav["lat"], self.nav["lon"])
        if night:
            if target:
                sig = NIGHT_TARGET_SIGMA
                vlat, vlon = offset(lat, lon, self.rng.gauss(0, sig), self.rng.gauss(0, sig))
            else:
                # Tracking model measured on the replay set: seeded by GPS, then the
                # estimate advances only a fraction of the true motion.
                if nav_gps or self.night_est is None:
                    self.night_est = [gps_pos if nav_gps else (lat, lon), (lat, lon)]
                est, prev = self.night_est
                de = (lon - prev[1]) * M_PER_DEG * math.cos(math.radians(lat))
                dn = (lat - prev[0]) * M_PER_DEG
                est = offset(est[0], est[1], NIGHT_MEASURED_GAIN * de + self.rng.gauss(0, 10),
                             NIGHT_MEASURED_GAIN * dn + self.rng.gauss(0, 10))
                self.night_est = [est, (lat, lon)]
                vlat, vlon = est
                sig = None
        else:
            self.night_est = None
            sig = DAY_TARGET_SIGMA if target else None
            s = DAY_TARGET_SIGMA if target else DAY_MEASURED_SIGMA
            vlat, vlon = offset(lat, lon, self.rng.gauss(0, s), self.rng.gauss(0, s))
        m = PositionEstimate()
        m.header.stamp = now
        m.sensor_stamp = now
        m.header.frame_id = "night_camera" if night else "day_camera"
        m.latitude, m.longitude, m.altitude = vlat, vlon, math.nan
        if sig is not None:
            m.position_covariance = [sig ** 2, 0.0, 0.0, 0.0, sig ** 2, 0.0, 0.0, 0.0, (2 * sig) ** 2]
            m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_DIAGONAL_KNOWN
        else:
            m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        m.source = PositionEstimate.SOURCE_NIGHT_VISION if night else PositionEstimate.SOURCE_DAY_VISION
        m.mode = PositionEstimate.MODE_MEASURED
        m.valid = True
        m.confidence = 0.9 if target else 0.3
        m.producer = "navera_simulator"
        m.model_id = f"sim-{self.cfg['profile']}"
        m.frame_index = -1
        m.details_json = json.dumps({"simulated": True, "profile": self.cfg["profile"]})
        (self.pub_night if night else self.pub_day).publish(m)

    def _record(self, truth):
        if truth is None:
            return
        s = self.ap.snapshot()
        with self.lock:
            nav_fresh = self.nav["lat"] is not None and time.monotonic() - self.nav["t"] < 3.0 \
                and self.nav["state"] in ("FIX", "DEGRADED")
            ne = haversine_m(truth, (self.nav["lat"], self.nav["lon"])) if nav_fresh else None
            be = (haversine_m(truth, s["belief"])
                  if s["belief"] and abs(s["belief"][0]) > 1 else None)
            self.series.append((round(time.monotonic() - self.t0, 1), ne, be,
                                self.nav["source"] if nav_fresh else "—"))

    LINK_GRACE_S = 10.0      # the estimator may take this long to publish after a (re)start
    LINK_SILENCE_S = 5.0     # it publishes nav_status at 5 Hz: 5 s of silence is a lost link

    def _watch_ros_link(self):
        """Detect that this simulator no longer receives NAVERA's messages while the
        estimator runs (seen once: a simulator process lost its ROS link silently and the
        dashboard showed 'no output'). Reports it on the dashboard and in the log."""
        while not getattr(self, "_closing", False):
            time.sleep(1.0)
            est = self.procs.get("estimator") if hasattr(self, "procs") else None
            if est is None or not est.alive() or est.t_start is None:
                continue
            now = time.monotonic()
            since_start = now - est.t_start
            last = self._last_status_t
            silent = now - (last if last is not None and last > est.t_start else est.t_start)
            lost = since_start > self.LINK_GRACE_S and silent > self.LINK_SILENCE_S
            if lost and self.ros_link["ok"]:
                self.ros_link = dict(ok=False, since=time.strftime("%H:%M:%S"), detail=(
                    f"no NAVERA status received for {silent:.0f} s although the estimator process runs — "
                    "the estimator is stuck or the simulator lost its ROS link; restart the simulator "
                    "(run_sim.sh)"))
                self.event("error", "ROS link lost: " + self.ros_link["detail"])
            elif not lost and not self.ros_link["ok"] and silent < 2.0:
                self.ros_link = dict(ok=True, since=None, detail="")
                self.event("ok", "ROS link back: NAVERA status received again")

    def _watch_procs(self):
        if self._closing:
            return
        with self.lock:
            procs = list(self.procs.items())
        for name, p in procs:
            if name == "vehicle_output":
                continue
            if not p.alive() and p.p is not None and p.restart_if_dead():
                self.event("error", f"{name} stopped — restarted (log: {p.log_path})")
        with self.lock:
            vo = self.procs.get("vehicle_output")
        if vo is not None and self.phase not in ("idle", "starting") and not vo.alive():
            self.event("error", "vehicle_output stopped — restarting")
            vo.start()

    # ---------------- mission ----------------
    def start_mission(self, cfg):
        with self.lock:
            if self.mission_thread and self.mission_thread.is_alive():
                self._abort.set()
        if self.mission_thread:
            self.mission_thread.join(timeout=20)
        self._abort.clear()
        # what the nodes remember across a restart (state_store) belongs to one mission
        shutil.rmtree(os.environ["NAVERA_STATE_DIR"], ignore_errors=True)
        self.cfg.update(cfg)
        self.series.clear()
        self.mission_thread = threading.Thread(target=self._mission, daemon=True)
        self.mission_thread.start()

    def _set_phase(self, phase, detail):
        with self.lock:
            self.phase, self.phase_detail = phase, detail
            self.phase_t0 = time.monotonic()
        self.event("info", f"mission: {detail}")

    def _wait(self, cond, timeout, what):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self._abort.is_set():
                raise InterruptedError()
            if cond():
                return
            time.sleep(0.5)
        raise TimeoutError(what)

    def _mission(self):
        c = self.cfg
        try:
            self._set_phase("starting", f"step 1/4 — starting the {c['vehicle']} autopilot "
                                        f"(ArduPilot) and NAVERA")
            with self.lock:
                old = self.procs.pop("vehicle_output", None)
            if old:
                old.stop()
            # A new mission is a fresh power-on of the box at a new place: NAVERA's
            # nodes restart (the arbiter's GPS plausibility gate must not compare
            # the new start with where the previous mission ended).
            self.procs["estimator"].cmd = [
                "ros2", "run", "navera_estimator", "estimator_node.py", "--ros-args",
                "-p", f"max_speed_mps:={c['max_speed_mps']}"]
            for name in ("estimator", "gps_node"):
                self.procs[name].start()
            self.gps.set_mode(self.faults["gps"])
            self.gps.noise = [0.0, 0.0]
            with self.lock:
                self.nav.update(state="—", source="—", reason="", lat=None, lon=None)
                self._last_state = self._last_source = None
            self._stop_vision()
            self._had_gps = False
            self.imu_bias = (self.rng.gauss(0, math.radians(0.3)), self.rng.gauss(0, math.radians(0.3)),
                             self.rng.gauss(0, math.radians(1.5)))
            self.event("info", "IMU (simulated, BNO085-class): attitude bias roll "
                               f"{math.degrees(self.imu_bias[0]):+.2f}°, pitch "
                               f"{math.degrees(self.imu_bias[1]):+.2f}°, heading "
                               f"{math.degrees(self.imu_bias[2]):+.2f}°")
            self._apply_pipelines()
            first = (c.get("waypoints") or [c["dest"]])[0]          # face the first leg
            self.ap.start(c["vehicle"], c["start"][0], c["start"][1], self._bearing(c["start"], first))
            self.ap.connect()
            # vehicle sensors: NAVERA's vehicle_link reads the autopilot on its SERIAL2
            with self.lock:
                old_link = self.procs.pop("vehicle_link", None)
            if old_link:
                old_link.stop()
            if c.get("sensor_source") == "vehicle":
                self._start_proc("vehicle_link", ["ros2", "run", "navera_output", "vehicle_link_node.py",
                                                  "--ros-args", "-p", "mavlink_url:=tcp:127.0.0.1:5763"])
                self.event("info", "sensors: the vehicle's own (autopilot attitude over MAVLink)")
            vo_cmd = ["ros2", "run", "navera_output", "vehicle_output_node.py", "--ros-args",
                      "-p", f"mavlink_url:={NAVERA_URL}", "-p", "rate_hz:=5.0"]
            if c["forward_degraded"]:
                vo_cmd += ["-p", "forward_degraded:=true",
                           "-p", f"degraded_sigma_m:={c['degraded_sigma_m']:.1f}"]
            vo = Proc("vehicle_output", vo_cmd, self.work)
            vo.start()
            with self.lock:
                self.procs["vehicle_output"] = vo
            self._set_phase("waiting_gps", "step 2/4 — the autopilot is aligning its navigation "
                                           "filter on NAVERA's GPS position")
            self._wait(lambda: self.ap.snapshot()["ekf_pos_ok"], 180,
                       "the autopilot never got a usable position from NAVERA (is GPS jammed?)")
            self.ap.set_speed(c["speed"])
            self.ap.set_mode("GUIDED")
            self._set_phase("arming", "step 3/4 — arming the motors")

            def armed():
                if not self.ap.snapshot()["armed"]:
                    self.ap.set_mode("GUIDED")
                    self.ap.arm()
                return self.ap.snapshot()["armed"]
            self._wait(armed, 60, "the autopilot refused to arm (see its messages)")
            if c["vehicle"] in FLYING:
                plane = c["vehicle"] == "plane"
                self._set_phase("takeoff", f"step 4/4 — {'take-off run and climb' if plane else 'taking off'} "
                                           f"to {c['alt']:.0f} m")
                self.ap.takeoff(c["alt"])
                self._wait(lambda: (self.ap.snapshot()["truth"] or (0, 0, 0))[2] > 0.9 * c["alt"],
                           (90 + c["alt"] / 5.0) if plane else (60 + c["alt"] / 2.0),
                           "takeoff did not complete")
            self._fly_to(self.cfg["dest"], legs=self.cfg.get("waypoints"))
            while not self._abort.is_set():
                time.sleep(0.5)
                s = self.ap.snapshot()
                if s["truth"] and self.phase == "enroute":
                    self._next_leg(s["truth"])
                if self.phase in ("enroute", "arrived") and s["armed"] and \
                        s["mode"] not in ("GUIDED", "—"):
                    why = ""
                    with self.lock:
                        nav_state = self.nav["state"]
                    if nav_state == "DEGRADED" and not self.cfg["forward_degraded"]:
                        why = (" NAVERA still has a vision position (DEGRADED) but, by default, does "
                               "not give it to the autopilot — tick 'Give vision positions to the "
                               "autopilot' to let it continue.")
                    elif nav_state == "NO FIX":
                        why = " NAVERA has no position to give (no GPS, no vision)."
                    self._set_phase("failsafe", f"the autopilot left the mission: {s['mode']} "
                                                f"(its own failsafe).{why} Click the map to resume.")
                if s["truth"] and self.phase == "enroute" and self.cfg["dest"] and \
                        haversine_m(s["truth"], self.cfg["dest"]) < (300 if self.cfg["vehicle"] == "plane" else 20):
                    self._set_phase("arrived", "arrived at the destination — holding. "
                                               "Click the map for a new destination.")
                if not s["link"]:
                    self._set_phase("error", "lost the link to the autopilot")
                    return
        except InterruptedError:
            return
        except Exception as e:
            self._set_phase("error", f"stopped: {e}")

    def _stop_vision(self, keep=()):
        for name, cam in (("day_vision", self.daycam), ("night_vision", self.nightcam),
                          ("celestial", self.starcam)):
            if name in keep:
                continue
            cam.stop()
            with self.lock:
                vps = [self.procs.pop(n, None) for n in (name, name.replace("_vision", "_camera"),
                                                         name.replace("_vision", "_simcam"))]
            for vp in vps:
                if vp:
                    vp.stop()

    def _start_proc(self, name, cmd, env=None):
        vp = Proc(name, cmd, self.work, env=env)
        vp.start()
        with self.lock:
            self.procs[name] = vp

    def _apply_pipelines(self):
        """Run the pipelines the box would run for this light, as on the vehicle:
        day → day vision (DINOv2, needs the prepared area); night → night vision
        (STHN, GPU — never both) + celestial (CPU, star camera)."""
        night = self.faults["light"] == "night"
        real = self.cfg["vision"] == "real"
        want = set()
        if real:
            want.add("night_vision" if night else "day_vision")
        if night:
            want.add("celestial")
        with self.lock:
            running = set(k for k in ("day_vision", "night_vision", "celestial") if k in self.procs)
        self._stop_vision(keep=want & running)
        if night and self.sky_base is None:
            # 20:30 local mean solar time at the start point (the night, anywhere)
            t = time.gmtime()
            midnight_utc = time.mktime((t.tm_year, t.tm_mon, t.tm_mday, 0, 0, 0, 0, 0, 0)) - time.timezone
            base = midnight_utc + (20.5 - self.cfg["start"][1] / 15.0) * 3600.0
            self.sky_base = (base, time.monotonic())
        if not night:
            self.sky_base = None
        if "day_vision" in want and "day_vision" not in running:
            area = self.cfg.get("area")
            if not (area and self.areas.is_prepared(area)):
                self.event("warn", "day vision: no prepared map area for this route — "
                                   "prepare the map to use day vision")
            else:
                self._start_proc("day_simcam", self._sim_camera_cmd("day"))
                self._start_proc("day_camera", self._live_camera_cmd("day"))
                self._start_proc("day_vision", ["ros2", "run", "day_pkg", "day_subscriber.py", "--ros-args",
                                                "-p", f"max_speed_mps:={self.cfg['max_speed_mps']}",
                                                "-p", "camera_hfov_deg:=84.0"],          # the simulated day camera
                                 env={"DAY_DATASET_DIR": self.areas.path(area)})
                self.daycam.start()
                self.event("info", "day vision: loading DINOv2 and the prepared area…")
        if "night_vision" in want and "night_vision" not in running:
            self._start_proc("night_simcam", self._sim_camera_cmd("night"))
            self._start_proc("night_camera", self._live_camera_cmd("night"))
            self._start_proc("night_vision", [
                "ros2", "run", "night_pkg", "night_subscriber.py", "--ros-args",
                "-p", f"mbtiles:={self._night_map()}", "-p", "camera_hfov_deg:=84.0",
                "-p", f"max_speed_mps:={self.cfg['max_speed_mps']}"])
            self.nightcam.start()
            self.event("info", "night vision: loading the STHN network (thermal camera, "
                               "84° field of view)…")
        if "celestial" in want and "celestial" not in running:
            astro = os.path.join(os.path.expanduser("~/.navera_sim"), "astrometry")
            env = {}
            if os.path.exists(os.path.join(astro, "solve-field")) and not shutil.which("solve-field"):
                env = {"NAVERA_SOLVE_FIELD": os.path.join(astro, "solve-field"),
                       "NAVERA_ASTROMETRY_CFG": os.path.join(astro, "astrometry.cfg")}
            self._start_proc("celestial", [
                "ros2", "run", "cn_pkg", "cn_subscriber.py", "--ros-args",
                "-p", "camera_fov_deg:=60.0", "-p", "attitude_sigma_deg:=0.5",
                "-p", "camera_mount_elevation_deg:=90.0"], env=env)
            self.starcam.start()
            self.event("info", f"celestial: star camera on (60°, pointing up); sky time "
                               f"{self._sky_utc()} UTC")

    WP_SWITCH_M = {"plane": 400.0, "drone": 60.0}    # next leg when this close (others: 25 m)

    def _goto_wp(self):
        wp = self._wps[self._wp_i]
        self.ap.goto(wp[0], wp[1], self.cfg["alt"] if self.cfg["vehicle"] in FLYING else 0)

    def _next_leg(self, truth):
        """Leg by leg: when close to the current waypoint, go to the next one."""
        if self._wp_i < len(self._wps) - 1 and \
                haversine_m(truth, self._wps[self._wp_i]) < self.WP_SWITCH_M.get(self.cfg["vehicle"], 25.0):
            self._wp_i += 1
            self._goto_wp()

    def _fly_to(self, dest, legs=None):
        """Fly to dest along short great-circle legs (the map corridor follows the same legs)."""
        self.cfg["dest"] = dest
        s = self.ap.snapshot()
        here = [s["truth"][0], s["truth"][1]] if s["truth"] else self.cfg["start"]
        self._wps = legs if legs else _legs([here, dest])[1:]
        self._wp_i = 0
        self.ap.set_mode("GUIDED")
        self._goto_wp()
        dist = haversine_m(s["truth"], dest) if s["truth"] else float("nan")
        plan = self.areas.state()["plan"]
        if self.cfg["vision"] == "real" and plan and _route_dist(dest, plan["route"]) > plan["buffer_m"]:
            self.event("warn", "new destination is OUTSIDE the prepared map area: day vision has "
                               "no tiles there and will report no position if GPS is lost")
        self._set_phase("enroute", f"flying to the destination ({dist / 1000:.2f} km)"
                        if self.cfg["vehicle"] in FLYING else f"heading to the destination ({dist / 1000:.2f} km)")

    @staticmethod
    def _bearing(a, b):
        if not b:
            return 0.0
        y = math.sin(math.radians(b[1] - a[1])) * math.cos(math.radians(b[0]))
        x = (math.cos(math.radians(a[0])) * math.sin(math.radians(b[0]))
             - math.sin(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.cos(math.radians(b[1] - a[1])))
        return math.degrees(math.atan2(y, x)) % 360

    def command(self, action, body):
        if action in ("plan", "prepare"):
            start, dest = body.get("start"), body.get("dest")
            if not (isinstance(start, list) and isinstance(dest, list) and len(start) == 2
                    and len(dest) == 2):
                raise ValueError("start and destination are required")
            route = [[float(start[0]), float(start[1])], [float(dest[0]), float(dest[1])]]
            if action == "plan":
                self.areas.make_plan(route)
            else:
                self.areas.start_prepare(route)
            return
        if action == "mission":
            vehicle = body.get("vehicle", "drone")
            if vehicle not in VEHICLES:
                raise ValueError("unknown vehicle")
            start, dest = body.get("start"), body.get("dest")
            for p in (start, dest):
                if not (isinstance(p, list) and len(p) == 2 and self.tiles.exists()):
                    raise ValueError("start and destination are required")
            if haversine_m(start, dest) < 50:
                raise ValueError("the destination is less than 50 m from the start")
            spd, alt = DEFAULTS[vehicle]
            vision = "real" if body.get("vision", "real") == "real" else "profile"
            light = "night" if body.get("light") == "night" else "day"
            route = [[float(start[0]), float(start[1])], [float(dest[0]), float(dest[1])]]
            area = self.areas.area_id(route)
            plan = self.areas.plan_for(route)["plan"]
            covered_offline = plan["missing_n"] == 0       # (the lists are trimmed on long routes)
            # start partway along the route (long routes): same map, legs from that point
            from day_pkg.prepare_area import point_along
            legs = _legs(route)
            start_km = max(0.0, float(body.get("start_km") or 0.0))
            if start_km > 0:
                if start_km * 1000.0 > plan["length_m"] - 100.0:
                    raise ValueError("the start along the route is beyond the destination")
                p, nxt = point_along(legs, start_km * 1000.0)
                legs = [p] + legs[nxt:]
            if vision == "real":
                if vehicle not in FLYING:
                    raise ValueError("real vision needs a downward camera at altitude: "
                                     "use the drone or the plane, or the simulated vision profile")
                if light == "day" and not self.areas.is_prepared(area):
                    raise ValueError("prepare the map for this route first (Prepare map)")
                if light == "night" and not (covered_offline or self.areas.is_prepared(area)):
                    raise ValueError("this route is outside the onboard map: prepare the map "
                                     "first (its tiles are downloaded)")
                if light == "night" and float(body.get("alt", 400)) < 350:
                    self.event("warn", "night vision needs about 350 m or more with this 84° "
                                       "camera: below, it will report 'fly higher'")
            vmax = float(body.get("max_speed_mps", MAX_SPEED[vehicle]))
            if not 1.0 <= vmax <= MAX_SPEED_LIMIT:
                raise ValueError(f"maximum speed must be between 1 and {MAX_SPEED_LIMIT:.0f} m/s "
                                 f"({MAX_SPEED_LIMIT * 3.6:.0f} km/h)")
            cruise = max(1.0, min(SIM_CRUISE_MAX[vehicle], vmax, float(body.get("speed", spd))))
            self.faults["light"] = light
            self.areas.current = area
            self.start_mission(dict(
                vision=vision, area=area,
                degraded_sigma_m=max(5.0, min(2000.0, float(body.get("degraded_sigma_m", 500.0)))),
                vehicle=vehicle, start=legs[0], waypoints=legs[1:], start_km=start_km,
                dest=[float(dest[0]), float(dest[1])],
                speed=cruise, max_speed_mps=vmax,
                # the operator's altitude (any aircraft); the simulated drone flies up to SIM_ALT_MAX
                req_alt=float(body.get("alt", alt)),
                alt=max(SIM_ALT_MIN.get(vehicle, 0.0), min(SIM_ALT_MAX.get(vehicle, 0.0), float(body.get("alt", alt)))),
                profile="target" if body.get("profile") == "target" else "measured",
                sensor_source="vehicle" if body.get("sensor_source") == "vehicle" else "box",
                camera_mount="gimbal" if body.get("camera_mount") == "gimbal" else "fixed",
                forward_degraded=bool(body.get("forward_degraded", False))))
        elif action == "goto":
            dest = body.get("dest")
            dest = [float(dest[0]), float(dest[1])]
            if self.phase in ("enroute", "arrived", "rtl", "landing", "failsafe"):
                self._fly_to(dest)
            elif self.phase in ("starting", "waiting_gps", "arming", "takeoff"):
                self.cfg["dest"] = dest                # used once airborne
                self.event("info", "mission: new destination set (applied after take-off)")
            else:
                raise ValueError("no mission running: press Start mission")
        elif action == "rtl":
            self.ap.set_mode("RTL")
            self._set_phase("rtl", "returning to the start point")
        elif action == "land":
            v = self.cfg["vehicle"]
            # a plane cannot stop in the air: it circles where it is
            self.ap.set_mode({"drone": "LAND", "plane": "LOITER"}.get(v, "HOLD"))
            self._set_phase("landing", {"drone": "landing", "plane": "circling where it is"}.get(v, "stopping"))
        elif action == "stop":
            self._abort.set()
            self._stop_vision()
            self.ap.stop()
            with self.lock:
                old = self.procs.pop("vehicle_output", None)
            if old:
                old.stop()
            self._set_phase("idle", "simulation stopped. Choose a start point and a destination, then Start.")
        elif action == "fault":
            for k, allowed in (("gps", GPS_MODES), ("camera", ("ok", "failed")),
                               ("light", ("day", "night")), ("imu", ("ok", "failed"))):
                if k in body:
                    if body[k] not in allowed:
                        raise ValueError(f"{k}: {body[k]}")
                    if self.faults[k] != body[k]:
                        self.faults[k] = body[k]
                        if k == "gps":
                            self.gps.set_mode(body[k])
                        for cam in (self.daycam, self.nightcam, self.starcam):
                            cam.failed = self.faults["camera"] != "ok"
                        self.daycam.night = self.faults["light"] == "night"
                        if k == "light" and self.phase not in ("idle", "error"):
                            threading.Thread(target=self._apply_pipelines, daemon=True).start()
                        label = {"gps": "GPS receiver", "camera": "camera", "light": "light",
                                 "imu": "IMU"}[k]
                        self.event("warn" if body[k] not in ("ok", "day") else "info",
                                   f"FAULT INJECTED: {label} → {body[k].replace('_', ' ')}"
                                   if body[k] not in ("ok", "day") else f"{label} → {body[k]}")
        else:
            raise ValueError("unknown action")

    # ---------------- state for the page ----------------
    def state(self):
        s = self.ap.snapshot()
        truth = s["truth"] if s["link"] else None
        with self.lock:
            nav = dict(self.nav)
            nav_fresh = nav["lat"] is not None and time.monotonic() - nav["t"] < 3.0 \
                and nav["state"] in ("FIX", "DEGRADED")
            gps_out = dict(self.gps_node_out)
            out = dict(
                phase=self.phase, detail=self._live_detail(s), cfg=self.cfg, faults=self.faults,
                phase_elapsed_s=round(time.monotonic() - self.phase_t0),
                truth=None, navera=nav, autopilot=None, sources=self.sources,
                procs={n: p.alive() for n, p in list(self.procs.items())},
                events=list(self.events)[-60:], series=list(self.series)[-600:],
                area=self.areas.state(),
                vision=(self.nightcam if self.faults["light"] == "night" else self.daycam).state(),
                celestial=self.starcam.state(), ros_link=dict(self.ros_link),
                imu_bias_deg=[round(math.degrees(b), 2) for b in self.imu_bias])
        nav["fresh"] = nav_fresh
        if truth:
            out["truth"] = dict(lat=truth[0], lon=truth[1], alt=truth[2], heading=truth[3], speed=truth[4])
            nav["err_m"] = haversine_m(truth, (nav["lat"], nav["lon"])) if nav_fresh else None
        gr = s["gps_raw"]
        ap = dict(link=s["link"], mode=s["mode"], armed=s["armed"], ekf_ok=s["ekf_pos_ok"],
                  fix_type=gr[0] if gr else 0, sats=gr[3] if gr else 0,
                  eph=gr[4] if gr and math.isfinite(gr[4]) else None, belief=None, err_m=None)
        if s["belief"] and abs(s["belief"][0]) > 1:
            ap["belief"] = list(s["belief"])
            if truth:
                ap["err_m"] = haversine_m(truth, s["belief"])
        if truth and self.cfg.get("dest"):
            ap["dist_to_dest_m"] = haversine_m(truth, self.cfg["dest"])
        out["autopilot"] = ap
        out["gps"] = dict(mode=self.faults["gps"], port=self.gps.port,
                          node_valid=gps_out["valid"] and time.monotonic() - gps_out["t"] < 3,
                          node_age=round(time.monotonic() - gps_out["t"], 1) if gps_out["t"] else None,
                          sats=gps_out["sats"], hdop=gps_out["hdop"], reason=gps_out["reason"])
        return out

    def _live_detail(self, s):
        """Phase text with what the user needs to know right now."""
        d = self.phase_detail
        if self.phase in ("starting", "waiting_gps", "arming", "takeoff") and self.faults["gps"] != "ok":
            return (d + f" — BLOCKED: the GPS receiver is set to '{self.faults['gps'].replace('_', ' ')}'. "
                    "The autopilot needs one real GPS fix to start: set GPS back to OK.")
        if self.phase == "waiting_gps":
            return d + " (usually 30–50 s)"
        if self.phase == "takeoff" and s.get("truth"):
            return d + f" — climbing {max(0, s['truth'][2]):.0f} m"
        return d

    def config(self):
        """What the dashboard needs to know about maps."""
        return dict(
            offline_map=os.path.basename(self.tiles.path or ""),
            offline_bounds=self._offline_bounds(),
            prepare_source=TILE_URL.split("/")[2] if "//" in TILE_URL else TILE_URL,
            imagery_note="Areas outside the onboard map are downloaded from online imagery "
                         "(Esri World Imagery by default). Development and demonstration only: "
                         "storing imagery offline in a product needs the provider's licence.")

    def _offline_bounds(self):
        try:
            import sqlite3 as _sq
            con = _sq.connect(f"file:{self.tiles.path}?mode=ro", uri=True)
            row = con.execute("SELECT value FROM metadata WHERE name='bounds'").fetchone()
            con.close()
            w, s_, e, n = (float(v) for v in row[0].split(","))
            return [[s_, w], [n, e]]
        except Exception:                            # noqa: BLE001
            return None

    def box_location(self):
        """The box's own position, if it has one: NAVERA's current output."""
        with self.lock:
            nav = dict(self.nav)
        if nav["lat"] is not None and time.monotonic() - nav["t"] < 5 and nav["state"] in ("FIX", "DEGRADED"):
            return dict(lat=nav["lat"], lon=nav["lon"], source=f"NAVERA ({nav['source']})")
        return dict(lat=None, lon=None, source=None)

    def camera_jpeg(self):
        cam = self.nightcam if self.faults["light"] == "night" else self.daycam
        if self.cfg["vision"] == "real" and cam.enabled and cam.last_jpeg:
            return cam.last_jpeg
        tr = self._truth()
        if tr is None:
            return None
        return self.camera.render(tr[0], tr[1], tr[3], night=self.faults["light"] == "night",
                                  failed=self.faults["camera"] != "ok")

    def shutdown(self):
        self._closing = True
        self._abort.set()
        for cam in (self.daycam, self.nightcam, self.starcam):
            cam.close()
        self.areas.stop()
        self.ap.stop()
        with self.lock:
            procs = list(self.procs.values())
        for p in procs:
            p.stop()
        self.gps.close()


def serve(sim, host, port, tls=None):
    """HTTP(S) server for the dashboard and its API. tls = (cert, key) for HTTPS —
    browsers give the page the device's location only over HTTPS (or localhost)."""
    page = os.path.join(HERE, "sim.html")

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj, allow_nan=False, default=lambda o: None).encode(),
                       "application/json")

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                with open(page, "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path.startswith("/leaflet/"):
                name = os.path.basename(path)
                f = os.path.join(HERE, "..", "..", "simulation_web", "simulation_web", "resources",
                                 "leaflet", name)
                if name in ("leaflet.min.js", "leaflet.min.css") and os.path.exists(f):
                    with open(f, "rb") as fh:
                        return self._send(200, fh.read(), "text/css" if name.endswith("css")
                                          else "application/javascript")
                return self._send(404, b"", "text/plain")
            if path == "/api/state":
                try:
                    return self._json(200, _clean(sim.state()))
                except Exception as e:
                    sim.get_logger().error("state: " + traceback.format_exc())
                    return self._json(500, {"error": str(e)})
            if path == "/api/config":
                return self._json(200, sim.config())
            if path == "/api/plan":
                try:
                    from urllib.parse import parse_qs
                    q = parse_qs(urlparse(self.path).query)
                    a_, b_ = ([float(v) for v in q[k][0].split(",")] for k in ("a", "b"))
                    if len(a_) != 2 or len(b_) != 2:
                        raise ValueError("a and b must be lat,lon")
                    return self._json(200, _clean(sim.areas.plan_for([a_, b_])))
                except (KeyError, ValueError) as e:
                    return self._json(400, {"error": f"bad route: {e}"})
            if path == "/api/location":
                return self._json(200, _clean(sim.box_location()))
            if path == "/api/star.jpg":
                img = sim.starcam.last_jpeg
                return self._send(200, img, "image/jpeg") if img else self._send(204, b"", "image/jpeg")
            if path == "/api/camera.jpg":
                img = sim.camera_jpeg()
                return self._send(200, img, "image/jpeg") if img else self._send(204, b"", "image/jpeg")
            zxy = parse_tile_path(path)
            if zxy:
                data = sim.tiles.get(*zxy)
                return self._send(200, data, "image/jpeg") if data else self._send(404, b"", "text/plain")
            self._send(404, b"not found", "text/plain")

        def do_POST(self):
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                return self._send(404, b"", "text/plain")
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
                sim.command(path[5:], body)
                self._json(200, {"ok": True})
            except (ValueError, TypeError, KeyError) as e:
                self._json(400, {"ok": False, "error": str(e)})
            except Exception as e:
                sim.get_logger().error(f"{path}: " + traceback.format_exc())
                self._json(500, {"ok": False, "error": str(e)})

    srv = ThreadingHTTPServer((host, port), H)
    srv.daemon_threads = True
    if tls:
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(*tls)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _clean(o):
    """NaN/inf -> None, recursively (the page parses strict JSON)."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, deque)):
        return [_clean(v) for v in o]
    return o


def main():
    work = os.environ.get("NAVERA_SIM_DIR", os.path.expanduser("~/.navera_sim"))
    os.makedirs(work, exist_ok=True)
    kill_leftover_nodes()
    rclpy.init()
    os.environ["NAVERA_STATE_DIR"] = os.path.join(work, "state")     # inherited by every node
    sim = Simulator(work, os.environ["NAVERA_MBTILES"], os.environ.get("NAVERA_ARDUPILOT", "~/ardupilot"))
    port = int(os.environ.get("NAVERA_SIM_PORT", "8190"))
    srv = serve(sim, "0.0.0.0", port)
    servers = [srv]
    cert, key = (os.path.join(work, "tls", n) for n in ("cert.pem", "key.pem"))
    if os.path.exists(cert) and os.path.exists(key):
        tls_port = int(os.environ.get("NAVERA_SIM_TLS_PORT", "8443"))
        servers.append(serve(sim, "0.0.0.0", tls_port, (cert, key)))
        sim.event("info", f"simulator ready on port {port} (HTTP) and {tls_port} (HTTPS: "
                          "needed for 'My location' from another device)")
    else:
        sim.event("info", f"simulator ready on port {port}")
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(sim)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    t = threading.Thread(target=ex.spin, daemon=True)
    t.start()
    stop.wait()
    for sv in servers:
        sv.shutdown()
    ex.shutdown()                 # no more timers (the process watchdog) before stopping nodes
    sim.shutdown()
    sim.destroy_node()
    rclpy.try_shutdown()


if __name__ == "__main__":
    main()
