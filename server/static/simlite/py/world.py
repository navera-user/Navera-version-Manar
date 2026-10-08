"""NAVERA Sim Lite — the world, in the browser.

What runs, and what is simulated (same split as NAVERA's full mission simulator):

    REAL  the student's navera_estimator (their own estimator_node.py and navera_common,
          loaded from their copy), on a stand-in for rclpy with simulated time.
    SIM   the vehicle's true motion (simple kinematics instead of ArduPilot's physics),
          the GPS estimate gps_node would publish (noise, jamming, jump and drift spoofing),
          the vision fixes with the same error profiles as the full simulator
          ("measured": what day/night vision measure today; "target": the accuracy goal),
          the IMU (liveness), and an autopilot whose ONLY position input is NAVERA's output.

So when NAVERA is wrong, the vehicle goes the wrong way — exactly the closed loop of the
real system. Simplified on purpose: no wind, no terrain, no camera images.
"""
import json
import math
import os
import random
import sys
import traceback

import rclpy
from rclpy._core import BUS, NS
from rclpy.node import Node

M_PER_DEG = 111_320.0
DT = 0.1                                          # simulation step (s)
DAY_MEASURED_SIGMA = 440.0 / math.sqrt(2.0 * math.log(2.0))   # docs/VALIDATION_STATUS.md, day ~440 m median
DAY_TARGET_SIGMA = 15.0
NIGHT_TARGET_SIGMA = 25.0
NIGHT_MEASURED_GAIN = 0.25                        # night estimate advanced ~25 % of the true motion
VEHICLES = {  # cruise m/s, altitude m, NAVERA max_speed_mps, turn rate deg/s, accel m/s²
    "drone": (15.0, 150.0, 30.0, 45.0, 3.0),
    "plane": (40.0, 300.0, 100.0, 12.0, 4.0),
    "boat": (8.0, 0.0, 20.0, 10.0, 1.0),
    "robot": (4.0, 0.0, 10.0, 40.0, 1.5),
}
PLACES = {
    "sousse": (35.8256, 10.6360), "sousse medina": (35.8270, 10.6380), "port el kantaoui": (35.8920, 10.5980),
    "monastir": (35.7643, 10.8113), "monastir harbour": (35.7778, 10.8317), "monastir marina": (35.7778, 10.8317),
    "monastir airport": (35.7581, 10.7547), "skanes": (35.7560, 10.7680), "hammam sousse": (35.8606, 10.5944),
    "kantaoui": (35.8920, 10.5980),
}
SRC = {1: "GPS", 2: "DAY VISION", 3: "NIGHT VISION", 4: "CELESTIAL", 5: "INERTIAL"}
STATE = {0: "STARTING", 1: "NO FIX", 2: "FIX", 3: "DEGRADED"}


def offset(lat, lon, east_m, north_m):
    return lat + north_m / M_PER_DEG, lon + east_m / (M_PER_DEG * math.cos(math.radians(lat)))


def enu(lat0, lon0, lat, lon):
    return (lon - lon0) * M_PER_DEG * math.cos(math.radians(lat0)), (lat - lat0) * M_PER_DEG


def dist(a, b):
    e, n = enu(a[0], a[1], b[0], b[1])
    return math.hypot(e, n)


def bearing(a, b):
    e, n = enu(a[0], a[1], b[0], b[1])
    return math.degrees(math.atan2(e, n)) % 360


def place(where):
    if isinstance(where, (tuple, list)) and len(where) >= 2:
        return float(where[0]), float(where[1])
    key = str(where).strip().lower()
    if key in PLACES:
        return PLACES[key]
    raise ValueError(f"unknown place '{where}': use (lat, lon) or one of {sorted(PLACES)}")


# ---------------------------------------------------------------- loading the student's NAVERA
def install_navera(files, root):
    """Write the student's NAVERA files (navera_common, the estimator, navera_msgs/*.msg) under
    root and build the navera_msgs package from the .msg definitions."""
    for mod in [m for m in list(sys.modules) if m.split(".")[0] in ("navera_common", "navera_estimator", "navera_msgs")]:
        del sys.modules[mod]
    msgs = {}
    for rel, text in files.items():
        if rel.startswith("navera_msgs/msg/") and rel.endswith(".msg"):
            msgs[os.path.basename(rel)[:-4]] = text
            continue
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
    for pkg in ("navera_common", "navera_estimator", "navera_estimator/nodes"):
        init = os.path.join(root, pkg, "__init__.py")
        if not os.path.exists(init):
            os.makedirs(os.path.dirname(init), exist_ok=True)
            open(init, "w").close()
    d = os.path.join(root, "navera_msgs", "msg")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(root, "navera_msgs", "__init__.py"), "w").close()
    with open(os.path.join(d, "__init__.py"), "w") as f:
        f.write("from _rosmsg import define\n")
        # SourceHealth first: NavStatus uses it
        for name in sorted(msgs, key=lambda n: (n != "SourceHealth", n)):
            f.write(f"{name} = define('navera_msgs', {name!r}, {msgs[name]!r})\n")
    if root not in sys.path:
        sys.path.insert(0, root)
    import importlib
    importlib.invalidate_caches()


# ---------------------------------------------------------------- the world
class World(Node):
    def __init__(self, cfg):
        super().__init__("navera_sim_lite")
        from navera_msgs.msg import NavStatus, PositionEstimate
        from sensor_msgs.msg import Imu
        self.PE, self.Imu = PositionEstimate, Imu
        self.cfg = cfg
        self.rng = random.Random(cfg.get("seed", 7))
        cruise, alt, self.max_speed, self.turn_rate, self.accel = VEHICLES[cfg["vehicle"]]
        self.cruise = float(cfg.get("speed") or cruise)
        self.alt = float(cfg.get("alt") if cfg.get("alt") is not None else alt)
        self.start, self.dest = place(cfg["start"]), place(cfg["dest"])
        self.truth = list(self.start)
        self.heading = bearing(self.start, self.dest)
        self.speed = 0.0
        self.phase = "waiting"                     # waiting (for a NAVERA position) → flying → arrived
        self.faults = {"gps": "ok", "camera": "ok", "light": cfg.get("light", "day"), "imu": "ok"}
        self.spoof = [0.0, 0.0]
        self.gps_noise = [0.0, 0.0]
        self.night_est = None
        self.had_gps = False
        self.nav = {"state": 0, "source": 0, "reason": "", "lat": None, "lon": None, "t": None, "mode": 0}
        self.belief = None                         # the autopilot's own position: NAVERA + dead reckoning
        self.vel = (0.0, 0.0)
        self.events, self.trail, self.gps_pts, self.vis_pts, self.nav_pts = [], [], [], [], []
        self.err_hist = []
        self.t = 0.0
        self.arrival = None
        self.pub_gps = self.create_publisher(PositionEstimate, "/navera/estimate/gps", 10)
        self.pub_day = self.create_publisher(PositionEstimate, "/navera/estimate/day", 10)
        self.pub_night = self.create_publisher(PositionEstimate, "/navera/estimate/night", 10)
        self.pub_imu = self.create_publisher(Imu, "/navera/sensors/imu", 50)
        self.create_subscription(PositionEstimate, "/navera/position", self._on_pos, 10)
        self.create_subscription(NavStatus, "/navera/nav_status", self._on_status, 10)
        self.create_timer(0.2, self._gps)          # 5 Hz receiver
        self.create_timer(1.0, self._vision)       # 1 vision fix per second
        self.create_timer(0.05, self._imu)         # 20 Hz IMU (liveness)
        self.event("info", f"{cfg['vehicle']} ready at the start, {self.cruise:.0f} m/s — waiting for NAVERA's first position")

    # -- log
    def event(self, level, text):
        self.events.append({"t": round(self.t, 1), "level": level, "text": text})

    # -- NAVERA's outputs
    def _on_pos(self, m):
        first = self.nav["lat"] is None
        self.nav.update(lat=m.latitude, lon=m.longitude, t=self.t, mode=m.mode)
        self.belief = [m.latitude, m.longitude]
        self.nav_pts.append((round(m.latitude, 7), round(m.longitude, 7), m.source))
        if first:
            self.event("ok", f"NAVERA: first position ({SRC.get(m.source, m.source)})")

    def _on_status(self, m):
        if m.state != self.nav["state"] or m.active_source != self.nav["source"]:
            lvl = "ok" if m.state == 2 else ("warn" if m.state == 3 else "bad")
            src = SRC.get(m.active_source, "none")
            self.event(lvl, f"NAVERA: {STATE.get(m.state, m.state)} — source {src}" + (f" ({m.reason})" if m.reason else ""))
        self.nav.update(state=m.state, source=m.active_source, reason=m.reason)

    # -- sensors
    def _stamp(self, m):
        now = self.get_clock().now().to_msg()
        m.header.stamp = now
        if hasattr(m, "sensor_stamp"):
            m.sensor_stamp = now

    def _gps(self):
        mode = self.faults["gps"]
        if mode == "off":
            return
        dt = 0.2
        for i in (0, 1):                           # first-order Gauss-Markov noise (as the full simulator)
            self.gps_noise[i] += -self.gps_noise[i] * dt / 20.0 + self.rng.gauss(0, 0.6) * math.sqrt(dt)
        m = self.PE()
        self._stamp(m)
        m.header.frame_id = "gps"
        m.source, m.mode, m.producer, m.model_id, m.frame_index = self.PE.SOURCE_GPS, self.PE.MODE_MEASURED, "gps_node", "nmea_gga", -1
        if mode == "jammed":                       # receiver reports "no fix": gps_node publishes valid=false
            m.valid, m.reason = False, "no fix (qual=0)"
            m.latitude = m.longitude = m.altitude = math.nan
            self.pub_gps.publish(m)
            self.gps_pts.append(None)
            return
        if mode == "spoof_drift":
            self.spoof[0] += 4.0 * dt * 0.8
            self.spoof[1] += 4.0 * dt * 0.6
        e, n = self.gps_noise[0] + self.spoof[0], self.gps_noise[1] + self.spoof[1]
        m.latitude, m.longitude = offset(self.truth[0], self.truth[1], e, n)
        m.altitude = self.alt
        hdop = 0.9
        cov = (hdop * 2.0) ** 2                    # gps_node: sigma = HDOP x 2 m
        m.position_covariance = [cov, 0.0, 0.0, 0.0, cov, 0.0, 0.0, 0.0, cov * 4]
        m.position_covariance_type = self.PE.COVARIANCE_TYPE_APPROXIMATED
        m.valid, m.confidence = True, 0.0
        m.details_json = json.dumps({"hdop": hdop, "num_sats": 9, "gps_qual": 1, "simulated": True})
        self.pub_gps.publish(m)
        self.had_gps = True
        self.gps_pts.append((round(m.latitude, 7), round(m.longitude, 7), mode != "ok"))

    def _vision(self):
        if not self.had_gps or self.faults["camera"] != "ok":
            self.night_est = None if self.faults["camera"] != "ok" else self.night_est
            return                                 # like the real nodes: no prior, no position
        lat, lon = self.truth
        night = self.faults["light"] == "night"
        target = self.cfg.get("profile") == "target"
        nav_gps = self.nav["source"] == 1 and self.nav["lat"] is not None
        if night:
            if target:
                sig = NIGHT_TARGET_SIGMA
                vlat, vlon = offset(lat, lon, self.rng.gauss(0, sig), self.rng.gauss(0, sig))
            else:
                if nav_gps or self.night_est is None:
                    self.night_est = [(self.nav["lat"], self.nav["lon"]) if nav_gps else (lat, lon), (lat, lon)]
                est, prev = self.night_est
                de, dn = enu(prev[0], prev[1], lat, lon)
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
        m = self.PE()
        self._stamp(m)
        m.header.frame_id = "night_camera" if night else "day_camera"
        m.latitude, m.longitude, m.altitude = vlat, vlon, math.nan
        if sig is not None:
            m.position_covariance = [sig ** 2, 0.0, 0.0, 0.0, sig ** 2, 0.0, 0.0, 0.0, (2 * sig) ** 2]
            m.position_covariance_type = self.PE.COVARIANCE_TYPE_DIAGONAL_KNOWN
        else:
            m.position_covariance_type = self.PE.COVARIANCE_TYPE_UNKNOWN
        m.source = self.PE.SOURCE_NIGHT_VISION if night else self.PE.SOURCE_DAY_VISION
        m.mode, m.valid = self.PE.MODE_MEASURED, True
        m.confidence = 0.9 if target else 0.3
        m.producer, m.model_id, m.frame_index = "navera_sim_lite", f"sim-{self.cfg.get('profile', 'measured')}", -1
        m.details_json = json.dumps({"simulated": True, "profile": self.cfg.get("profile", "measured")})
        (self.pub_night if night else self.pub_day).publish(m)
        self.vis_pts.append((round(vlat, 7), round(vlon, 7), "night" if night else "day"))

    def _imu(self):
        if self.faults["imu"] != "ok":
            return
        m = self.Imu()
        self._stamp(m)
        m.header.frame_id = "imu"
        m.linear_acceleration.z = 9.81
        m.orientation_covariance[0] = -1.0          # no orientation
        self.pub_imu.publish(m)

    # -- faults (also used by the flight script)
    def set_fault(self, key, value):
        if key not in self.faults:
            raise ValueError(f"unknown fault '{key}'")
        if self.faults[key] == value:
            return
        if key == "gps":
            self.spoof = [0.0, 0.0]
            if value == "spoof_jump":
                ang = self.rng.uniform(0, 2 * math.pi)
                self.spoof = [2000.0 * math.cos(ang), 2000.0 * math.sin(ang)]
        self.faults[key] = value
        names = {"ok": "normal", "jammed": "JAMMED", "spoof_jump": "SPOOFED (2 km jump)", "spoof_drift": "SPOOFED (slow drift)",
                 "off": "OFF", "failed": "FAILED", "day": "day", "night": "NIGHT"}
        self.event("warn" if value not in ("ok", "day") else "info", f"{key.upper()} → {names.get(value, value)}")

    # -- the vehicle and its autopilot
    def step(self):
        """Advance the world by DT: autopilot (from NAVERA's position only), then true motion."""
        self.t += DT
        if self.phase == "waiting" and self.belief is not None:
            self.phase = "flying"
            self.event("info", "take-off: the autopilot follows NAVERA's position")
        target_speed = 0.0
        if self.phase == "flying":
            # the autopilot's belief: NAVERA's last position, carried forward with its own velocity
            if self.belief is not None:
                self.belief = list(offset(self.belief[0], self.belief[1], self.vel[0] * DT, self.vel[1] * DT))
            togo = dist(self.belief, self.dest)
            if togo < max(10.0, self.cruise * 1.5):
                self.phase = "arrived"
                miss = dist(self.truth, self.dest)
                self.arrival = {"t": round(self.t, 1), "miss_m": round(miss, 1)}
                self.event("ok" if miss < 50 else "bad",
                           f"arrived (by its own estimate) — really {miss:.0f} m from the destination")
            else:
                want = bearing(self.belief, self.dest)
                diff = (want - self.heading + 540) % 360 - 180
                turn = max(-self.turn_rate * DT, min(self.turn_rate * DT, diff))
                self.heading = (self.heading + turn) % 360
                target_speed = self.cruise
        dv = max(-self.accel * DT, min(self.accel * DT, target_speed - self.speed))
        self.speed = max(0.0, self.speed + dv)
        ve = self.speed * math.sin(math.radians(self.heading))
        vn = self.speed * math.cos(math.radians(self.heading))
        self.vel = (ve, vn)
        self.truth = list(offset(self.truth[0], self.truth[1], ve * DT, vn * DT))
        if int(self.t / DT) % 10 == 0:
            self.trail.append((round(self.truth[0], 7), round(self.truth[1], 7)))
            if self.nav["lat"] is not None:
                self.err_hist.append((round(self.t, 1), round(self.error_m(), 1)))

    def error_m(self):
        if self.nav["lat"] is None:
            return None
        return dist(self.truth, (self.nav["lat"], self.nav["lon"]))

    def snapshot(self, since):
        """What the page draws. `since` = counts already sent, so only new points travel."""
        s = since or {}
        out = {
            "t": round(self.t, 1), "phase": self.phase, "truth": self.truth, "heading": self.heading,
            "speed": round(self.speed, 1), "alt": self.alt, "belief": self.belief,
            "nav": {"state": STATE.get(self.nav["state"]), "source": SRC.get(self.nav["source"], "none"),
                    "reason": self.nav["reason"], "lat": self.nav["lat"], "lon": self.nav["lon"],
                    "age": None if self.nav["t"] is None else round(self.t - self.nav["t"], 1)},
            "error_m": None if self.error_m() is None else round(self.error_m(), 1),
            "togo_m": round(dist(self.truth, self.dest)), "faults": dict(self.faults), "arrival": self.arrival,
            "gps_lost_for": None,
        }
        for k in ("trail", "gps_pts", "vis_pts", "nav_pts", "events", "err_hist"):
            arr = getattr(self, k)
            out[k] = arr[s.get(k, 0):]
            s[k] = len(arr)
        return out, s


# ---------------------------------------------------------------- the flight script's view
class _NavView:
    def __init__(self, w): self._w = w
    @property
    def state(self): return STATE.get(self._w.nav["state"])
    @property
    def source(self):
        return {1: "gps", 2: "vision", 3: "vision", 4: "celestial"}.get(self._w.nav["source"], "none")
    @property
    def error_m(self):
        e = self._w.error_m()
        return float("inf") if e is None else e
    @property
    def position(self): return None if self._w.nav["lat"] is None else (self._w.nav["lat"], self._w.nav["lon"])
    @property
    def reason(self): return self._w.nav["reason"]


class SimAPI:
    """`sim` in the student's flight script."""

    def __init__(self, w):
        self._w = w
        self.navera = _NavView(w)

    @property
    def t(self): return round(self._w.t, 1)
    @property
    def truth(self): return tuple(self._w.truth)
    @property
    def speed(self): return self._w.speed
    @property
    def phase(self): return self._w.phase

    def goto(self, where, speed=None, alt=None):
        self._w.dest = place(where)
        if speed is not None:
            self._w.cruise = float(speed)
        if alt is not None:
            self._w.alt = float(alt)
        if self._w.phase == "arrived":
            self._w.phase = "flying"
        self._w.event("info", f"new destination {where}" + (f" at {speed} m/s" if speed else ""))

    def set_speed(self, mps): self._w.cruise = float(mps)
    def jam_gps(self, **_): self._w.set_fault("gps", "jammed")
    def spoof_gps(self, kind="jump"): self._w.set_fault("gps", "spoof_jump" if kind == "jump" else "spoof_drift")
    def restore_gps(self): self._w.set_fault("gps", "ok")
    def gps_off(self): self._w.set_fault("gps", "off")
    def camera_fail(self): self._w.set_fault("camera", "failed")
    def camera_ok(self): self._w.set_fault("camera", "ok")
    def night(self): self._w.set_fault("light", "night")
    def day(self): self._w.set_fault("light", "day")
    def log(self, *a): self._w.event("script", " ".join(str(x) for x in a))
    def distance_to(self, where): return dist(self._w.truth, place(where))


# ---------------------------------------------------------------- one run
class Run:
    """A simulation: the world, the student's estimator, and their optional flight script."""

    def __init__(self, cfg, script_text="", log=None):
        BUS.reset()
        rclpy.init()
        self.logs = []
        BUS.log = lambda level, node, text: self.logs.append({"level": level, "node": node, "text": text})
        BUS.params["estimator_node"] = {"max_speed_mps": float(cfg.get("max_speed") or VEHICLES[cfg["vehicle"]][2])}
        self.world = World(cfg)
        from navera_estimator.nodes.estimator_node import EstimatorNode
        self.estimator = EstimatorNode()
        self.api = SimAPI(self.world)
        self.script = {}
        self.script_error = None
        if script_text.strip():
            try:
                exec(compile(script_text, "flight_script.py", "exec"), self.script)
                if "on_start" in self.script:
                    self.script["on_start"](self.api)
            except Exception:
                self.script_error = traceback.format_exc(limit=3)
                self.world.event("bad", "flight script error — see the console")
        self.sent = {}

    def advance(self, seconds):
        """Run `seconds` of simulated time; returns the new picture for the page."""
        steps = max(1, int(round(seconds / DT)))
        for _ in range(steps):
            BUS.advance(BUS.now_ns + int(DT * NS))
            self.world.step()
            tick = self.script.get("on_tick")
            if tick and not self.script_error:
                try:
                    tick(self.api, round(self.world.t, 1))
                except Exception:
                    self.script_error = traceback.format_exc(limit=3)
                    self.world.event("bad", "flight script error — see the console")
        snap, self.sent = self.world.snapshot(self.sent)
        snap["logs"], self.logs = self.logs, []
        snap["script_error"] = self.script_error
        self.script_error = None if not snap["script_error"] else self.script_error
        return snap
