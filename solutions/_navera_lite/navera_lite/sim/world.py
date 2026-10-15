"""navera_lite/sim/world.py — the simulated world NAVERA Lite flies in: the vehicle's true motion, the sensors with
their errors and the faults you inject, and an autopilot whose ONLY position input is the GPS_INPUT bytes the
messenger sends. Part of NAVERA Lite, the course's teaching stack (mission 31). Written for the course; it is not
NAVERA code. Pure Python (math, random) plus the parts it is given: the same file can run in a browser (Sim Lite).

What is REAL and what is SIMULATED (lesson §2):
    REAL   the judge (mission 29's Arbiter, with mission 30's guard in front of it), the messenger
           (navera_lite.output: encode → bytes → YOUR parse_frames and decode_gps_input), the autopilot's
           Kalman filter (mission 28's kf_predict / kf_update), and — with vision "mine" — your trained networks
    SIM    the truth (simple kinematics: turn rate and acceleration limits, no wind, no terrain), the GPS receiver
           (Gauss–Markov noise, jam, off, jump and drift spoofing), the cameras (an error profile, or your networks
           on pictures cut from the corridor), the IMU (only its faults matter here), the clock (simulated time).

One step is DT = 0.1 s. Every step, in this order: faults → sensors → arrivals at the judge → the judge decides
(on every arrival and at 5 Hz) → the messenger sends each NEW position once (NAVERA's OUT-3) or "no fix" once a
second → the autopilot reads the bytes, predicts and updates its filter → guidance and motion → one CSV row every
0.2 s. Scenario times are MISSION times: seconds since take-off (the autopilot's first usable position).
"""
import math
import random
from collections import deque

from navera_lite.estimate import COV_APPROXIMATED, COV_DIAGONAL_KNOWN, COV_UNKNOWN, Estimate

# @part 31
M_PER_DEG = 111_320.0
# @part 31
DT = 0.1                          # simulation step (s)
# @part 31
VEHICLES = {  # cruise m/s, altitude m, turn rate deg/s, acceleration m/s²   (the judge's top speed: vehicle.VEHICLES)
    "drone": (15.0, 150.0, 45.0, 3.0),
    "plane": (40.0, 300.0, 12.0, 4.0),
    "boat": (8.0, 0.0, 10.0, 1.0),
    "robot": (4.0, 0.0, 40.0, 1.5),
}
# @part 31
GPS_SIGMA_M = 1.8                 # the receiver states HDOP 0.9 → σ = 2 × HDOP (mission 15's rule)
# @part 31
SPOOF_JUMP_M = 2000.0             # spoof_jump: a fixed offset, in a direction drawn from the seed
# @part 31
SPOOF_DRIFT_MPS = (3.2, 2.4)      # spoof_drift: the offset grows by 4 m/s (east 3.2, north 2.4)
# @part 31
DAY_TARGET_SIGMA_M = 15.0         # vision profiles: the accuracy GOAL (stated), not a measurement
# @part 31
NIGHT_TARGET_SIGMA_M = 25.0
# @part 31
DAY_MEASURED_SIGMA_M = 373.7      # sigma_for_median(440): median 440 m, NAVERA's measured day retrieval (2026-10-03); no σ stated
# @part 31
NIGHT_MEASURED_GAIN = 0.25        # 'measured' night: the estimate follows only 25 % of the true motion (no σ stated)
# @part 31
VISION_PERIOD_S = 1.0             # one vision fix per second, taken 0.1 s after a GPS fix …
# @part 31
VISION_LATENCY_S = 0.3            # … and reaching the judge 0.3 s after the picture
# @part 31
CAMERA_LATE_S = 1.5               # camera "late" / "delayed": the picture is 1.5 s old when it is processed
# @part 31
IMU_TILT_BIAS_DEG = 3.0           # imu "bias": the attitude is 3° off: the ground point under the camera is not
                                  # where the pipeline believes (altitude × tan 3°, ahead of the vehicle)
# @part 31
AP_Q = 0.25                       # the autopilot's filter: what its IMU misses, as an acceleration variance (m²/s⁴)
# @part 31
AP_UNKNOWN_SIGMA_M = 100.0        # … the σ it assumes when GPS_INPUT says "ignore horiz_accuracy"
# @part 31
AP_GATE_D2 = 9.21                 # … its innovation gate (χ², 2 dof, 99 %): a fix beyond it is refused
# @part 31
AP_RESET_S = 5.0                  # … refused fixes for this long → it resets its position on the fix (glitch reset)
# @part 31
FAILSAFE_S = 5.0                  # no usable GPS_INPUT for this long → failsafe: LAND (drone, plane) / HOLD
# @part 31
ROW_S = 0.2
# @part 31
FAULTS = {"gps": ("ok", "jammed", "off", "spoof_jump", "spoof_drift"),
          "camera": ("ok", "blackout", "late", "delayed"),
          "imu": ("ok", "bias", "off"),
          "light": ("day", "night")}
# @part 31
COLUMNS = ("t_s", "phase", "gps_mode", "camera", "imu", "light", "lite_state", "lite_source", "lite_sigma_m",
           "lite_err_m", "guard", "gps_err_m", "vis_err_m", "ap_mode", "ap_err_m", "truth_lat", "truth_lon",
           "truth_speed_mps", "lite_lat", "lite_lon", "reason")


# @part 31
class LocalFrame:
    """East/north metres around (lat0, lon0) ↔ latitude/longitude (a flat frame: fine over a few km).
    Example: LocalFrame(35.8, 10.5).latlon(0.0, 111.32) → (35.801, 10.5)
    """

    def __init__(self, lat0, lon0):
        self.lat0, self.lon0 = float(lat0), float(lon0)
        self.k = M_PER_DEG * math.cos(math.radians(self.lat0))

    def latlon(self, e, n):
        return self.lat0 + n / M_PER_DEG, self.lon0 + e / self.k

    def en(self, lat, lon):
        return (lon - self.lon0) * self.k, (lat - self.lat0) * M_PER_DEG


# @part 31
def cov_of(sigma_m):
    """The 9-number covariance a source states for a σ (m) per horizontal axis (vertical 2σ), or zeros."""
    if sigma_m is None:
        return (0.0,) * 9
    s2 = float(sigma_m) ** 2
    return (s2, 0.0, 0.0, 0.0, s2, 0.0, 0.0, 0.0, 4.0 * s2)


# @part 31
class ProfileVision:
    """A camera + matcher replaced by an ERROR PROFILE (lesson §4): truth + a 2-D Gaussian error.
    kind "target": day σ 15 m / night σ 25 m, stated (the accuracy goal); "measured": day σ 373.7 m (median
    440 m) and a night estimate that follows only 25 % of the motion, both with NO stated σ; "profile": a dict
    {"day": {"sigma_m": …, "stated_sigma_m": … or None, "fail": share of pictures with no fix}, "night": {…}} —
    the profile you measured for your own networks (my_vision_profile.json).
    locate(seen_en, prior_en, light, heading_deg, alt_m, rng) → ((e, n), stated σ or None) or (None, reason).
    """

    def __init__(self, kind="target", profile=None):
        self.kind, self.profile = kind, profile
        self.night_state = None

    def locate(self, seen_en, prior_en, light, heading_deg, alt_m, rng):
        if self.kind == "profile":
            p = self.profile.get(light) or {}
            if not p:
                return None, f"no {light} profile"
            if rng.random() < float(p.get("fail", 0.0)):
                return None, "no match"
            s = float(p["sigma_m"])
            return (seen_en[0] + rng.gauss(0, s), seen_en[1] + rng.gauss(0, s)), p.get("stated_sigma_m")
        if light == "day":
            self.night_state = None
            if self.kind == "target":
                s = DAY_TARGET_SIGMA_M
                return (seen_en[0] + rng.gauss(0, s), seen_en[1] + rng.gauss(0, s)), s
            s = DAY_MEASURED_SIGMA_M
            return (seen_en[0] + rng.gauss(0, s), seen_en[1] + rng.gauss(0, s)), None
        if self.kind == "target":
            s = NIGHT_TARGET_SIGMA_M
            return (seen_en[0] + rng.gauss(0, s), seen_en[1] + rng.gauss(0, s)), s
        if self.night_state is None:
            self.night_state = [list(prior_en), list(seen_en)]
        est, prev = self.night_state
        de, dn = seen_en[0] - prev[0], seen_en[1] - prev[1]
        est = [est[0] + NIGHT_MEASURED_GAIN * de + rng.gauss(0, 10), est[1] + NIGHT_MEASURED_GAIN * dn + rng.gauss(0, 10)]
        self.night_state = [est, list(seen_en)]
        return (est[0], est[1]), None

    def anchor(self, prior_en):
        """The judge flies on GPS again: the 'measured' night estimate restarts from there."""
        if self.night_state is not None:
            self.night_state[0] = list(prior_en)


# @part 31
class World:
    """One simulated flight (see the top of this file). scenario: a dict (my_scenario.json's fields: name, vehicle,
    vision, light, seed, faults, duration_s, speed, max_speed_mps); judge: an object with receive(est, now_s) and
    step(now_s) → Decision (mission 29's Arbiter, or mission 30's GuardedArbiter); output: the module
    navera_lite.output (its encoder sends, its parse_frames + decode_gps_input read on the autopilot's side);
    kalman: a module with cv_model, kf_predict, kf_update (mission 28); vision: an object with locate() (a
    ProfileVision, or your networks: navera_lite.sim.vision.NetworkVision); frame: a LocalFrame; route: (start_en,
    dest_en). step() advances DT; run() flies to the end; rows / events / outcome hold the results.
    """

    def __init__(self, scenario, judge, output, kalman, vision, frame, route, t_unix0=1792054800.0):
        sc = dict(scenario)
        self.sc, self.judge, self.out, self.kf, self.vision, self.frame = sc, judge, output, kalman, vision, frame
        self.vehicle = sc.get("vehicle", "drone")
        if self.vehicle not in VEHICLES:
            raise ValueError(f"unknown vehicle {self.vehicle!r}: use one of {sorted(VEHICLES)}")
        cruise, self.alt, self.turn_rate, self.accel = VEHICLES[self.vehicle]
        self.cruise = float(sc.get("speed") or cruise)
        self.rng = random.Random(int(sc.get("seed", 7)))
        self.vrng = random.Random(int(sc.get("seed", 7)) * 7919 + 1)       # vision draws: their own stream
        self.t_unix0 = float(t_unix0)
        self.start, self.dest = tuple(route[0]), tuple(route[1])
        self.truth = list(self.start)
        self.heading = math.degrees(math.atan2(self.dest[0] - self.start[0], self.dest[1] - self.start[1])) % 360
        self.speed, self.vel, self.acc = 0.0, (0.0, 0.0), (0.0, 0.0)
        self.history = deque(maxlen=int(round(CAMERA_LATE_S / DT)) + 2)
        self.k = 0
        self.t_takeoff = None
        self.phase = "waiting"
        self.faults = {"gps": "ok", "camera": "ok", "imu": "ok", "light": sc.get("light", "day")}
        self.pending = sorted([list(f) for f in sc.get("faults", [])], key=lambda f: f[0])
        for f in self.pending:
            if len(f) != 3 or f[1] not in FAULTS or f[2] not in FAULTS[f[1]]:
                raise ValueError(f"fault {f}: use [seconds, sensor, mode] with sensor/mode in {FAULTS}")
        self.duration = float(sc.get("duration_s") or ((self.pending[-1][0] if self.pending else 0.0) + 40.0))
        from navera_lite.sim.sensors import GaussMarkov
        self.noise = [GaussMarkov(), GaussMarkov()]
        self.spoof = [0.0, 0.0]
        self.arrivals = []            # (k due, Estimate, vel or None)
        self.vel_of = {}              # stamp → receiver velocity (for the messenger)
        self.decision = None
        self.lite = None              # (e, n, source, stamp) of the judge's current winner
        self.last_sent = None
        self.seq = 0
        self.link = bytearray()       # bytes on the serial link, not read yet by the autopilot
        self.sent_frames = []
        self.ap_x = self.ap_P = None
        self.ap_last_fix_t = None
        self.ap_refused_since = None
        self.ap_mode = "WAIT"
        self.failsafe_t = self.arrived_t = None
        self.gps_err = self.vis_err = None
        self.rows, self.events = [], []
        self.done = False
        self.counts = {"gps_sent": 0, "vision_fixes": 0, "vision_refused": 0, "frames": 0, "ap_refused": 0,
                       "ap_resets": 0}
        self.event(f"{self.vehicle}, {self.cruise:g} m/s, vision '{sc.get('vision', 'target')}', "
                   f"{self.faults['light']} — waiting for NAVERA Lite's first position")

    # ------------------------------------------------------------------ helpers
    @property
    def t(self):
        return self.k * DT

    @property
    def mission_t(self):
        return None if self.t_takeoff is None else round(self.t - self.t_takeoff, 3)

    def event(self, text):
        m = self.mission_t
        self.events.append((round(self.t, 1), None if m is None else round(m, 1), text))

    def dist_truth(self, e, n):
        return math.hypot(e - self.truth[0], n - self.truth[1])

    # ------------------------------------------------------------------ faults
    def set_fault(self, key, value):
        if key not in FAULTS or value not in FAULTS[key]:
            raise ValueError(f"unknown fault {key}={value}")
        if self.faults[key] == value:
            return
        if key == "gps":
            self.spoof = [0.0, 0.0]
            if value == "spoof_jump":
                ang = self.rng.uniform(0, 2 * math.pi)
                self.spoof = [SPOOF_JUMP_M * math.sin(ang), SPOOF_JUMP_M * math.cos(ang)]
        self.faults[key] = value
        self.event(f"FAULT {key} → {value}")

    # ------------------------------------------------------------------ sensors
    def gps_fix(self):
        mode = self.faults["gps"]
        for g in self.noise:
            g.step(self.rng.gauss(0.0, 1.0))
        if mode == "off":
            self.gps_err = None
            return
        t = round(self.t, 3)
        if mode == "jammed":
            self.gps_err = None
            est = Estimate("gps", math.nan, math.nan, t, valid=False, reason="no fix (quality 0)")
            self.arrivals.append((self.k, est, None))
            return
        if mode == "spoof_drift":
            self.spoof[0] += SPOOF_DRIFT_MPS[0] * 0.2
            self.spoof[1] += SPOOF_DRIFT_MPS[1] * 0.2
        e = self.truth[0] + self.noise[0].x + self.spoof[0]
        n = self.truth[1] + self.noise[1].x + self.spoof[1]
        self.gps_err = self.dist_truth(e, n)
        lat, lon = self.frame.latlon(e, n)
        est = Estimate("gps", lat, lon, t, cov=cov_of(GPS_SIGMA_M), cov_type=COV_APPROXIMATED,
                       alt_m=self.alt + 34.0)
        vel = (self.vel[0] + self.rng.gauss(0, 0.1), self.vel[1] + self.rng.gauss(0, 0.1))
        self.arrivals.append((self.k, est, vel))
        self.counts["gps_sent"] += 1

    def vision_fix(self):
        cam, imu, light = self.faults["camera"], self.faults["imu"], self.faults["light"]
        if self.lite is None or cam == "blackout":
            return
        if imu == "off":
            self.counts["vision_refused"] += 1
            return
        old = cam in ("late", "delayed")
        seen = list(self.history[0]) if old and len(self.history) == self.history.maxlen else list(self.truth)
        if old and len(self.history) < self.history.maxlen:
            return
        if imu == "bias":
            d = self.alt * math.tan(math.radians(IMU_TILT_BIAS_DEG))
            h = math.radians(self.heading)
            seen = [seen[0] + d * math.sin(h), seen[1] + d * math.cos(h)]
        prior = (self.lite[0], self.lite[1])
        got, stated = self.vision.locate(tuple(seen), prior, light, self.heading, self.alt, self.vrng)
        if got is None:
            self.counts["vision_refused"] += 1
            return
        stamp = round(self.t - (CAMERA_LATE_S if cam == "delayed" else 0.0), 3)
        truth_then = self.history[0] if old else self.truth
        self.vis_err = math.hypot(got[0] - (truth_then[0] if cam == "delayed" else self.truth[0]),
                                  got[1] - (truth_then[1] if cam == "delayed" else self.truth[1]))
        lat, lon = self.frame.latlon(*got)
        src = "day" if light == "day" else "night"
        est = Estimate(src, lat, lon, stamp, cov=cov_of(stated),
                       cov_type=COV_DIAGONAL_KNOWN if stated is not None else COV_UNKNOWN)
        self.arrivals.append((self.k + int(round(VISION_LATENCY_S / DT)), est, None))
        self.counts["vision_fixes"] += 1

    # ------------------------------------------------------------------ the judge and the messenger
    def judge_and_send(self, arrived):
        now = round(self.t, 3)
        for est, vel in arrived:
            if vel is not None:
                self.vel_of[est.stamp_s] = vel
            self.judge.receive(est, now)
        if not arrived and self.k % 2:
            return
        d = self.judge.step(now)
        old = self.decision
        if old is None or d.state != old.state or d.source != old.source:
            self.event(f"NAVERA Lite: {d.state} {d.source or '-'} ({d.reason})")
        self.decision = d
        est = d.estimate if d.state in ("FIX", "DEGRADED") else None
        if est is not None:
            e, n = self.frame.en(est.lat, est.lon)
            self.lite = (e, n, d.source, est.stamp_s)
            if d.source == "gps" and hasattr(self.vision, "anchor"):
                self.vision.anchor((e, n))
            key = (d.source, est.stamp_s)
            if key != self.last_sent:
                self.last_sent = key
                vel = self.vel_of.get(est.stamp_s) if d.source == "gps" else None
                self.send(self.out.gps_input_fields(d, self.t_unix0, vel))
        elif self.k % 10 == 0 and self.lite is not None:
            self.send(self.out.gps_input_fields(d, self.t_unix0 + now))
        if len(self.vel_of) > 50:
            for s in sorted(self.vel_of)[:-20]:
                del self.vel_of[s]

    def send(self, fields):
        f = self.out.encode_gps_input(fields, self.seq)
        self.seq = (self.seq + 1) % 256
        self.link += f
        self.sent_frames.append(bytes(f))
        self.counts["frames"] += 1

    # ------------------------------------------------------------------ the autopilot
    def autopilot(self, read_messages):
        """Read the link (YOUR decoder), then the filter: predict DT, update with each usable fix (gate, reset)."""
        msgs = read_messages(bytes(self.link)) if self.link else []
        self.link = bytearray()
        self.ap_update(msgs)

    def ap_update(self, msgs):
        """The autopilot's filter for one step: predict DT, then update with each decoded GPS_INPUT (a dict with
        lat, lon in degrees, fix_type, horiz_accuracy, ignore_flags)."""
        kf = self.kf
        if self.ap_x is not None:
            F, Q = kf.cv_model(DT, AP_Q, dims=2)
            x, self.ap_P = kf.kf_predict(self.ap_x, self.ap_P, F, Q)
            # the autopilot's IMU measures the acceleration of the last step (a little noise): it moves the
            # prediction by it, like an inertial navigation system (the filter only models what the IMU misses)
            ax, ay = (a + self.rng.gauss(0.0, 0.05) for a in self.acc)
            self.ap_x = [float(x[0]) + 0.5 * ax * DT * DT, float(x[1]) + 0.5 * ay * DT * DT,
                         float(x[2]) + ax * DT, float(x[3]) + ay * DT]
        for m in msgs:
            if m.get("fix_type", 0) < 3:
                continue
            e, n = self.frame.en(m["lat"], m["lon"])
            sigma = AP_UNKNOWN_SIGMA_M if (m["ignore_flags"] & 64 or m["horiz_accuracy"] <= 0) else m["horiz_accuracy"]
            self.ap_last_fix_t = self.t
            if self.ap_x is None:
                self.ap_x = [e, n, 0.0, 0.0]
                self.ap_P = [[sigma ** 2, 0, 0, 0], [0, sigma ** 2, 0, 0], [0, 0, 4.0, 0], [0, 0, 0, 4.0]]
                continue
            H = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
            R = [[sigma ** 2, 0.0], [0.0, sigma ** 2]]
            x, P, d2 = kf.kf_update(self.ap_x, self.ap_P, [e, n], H, R)
            if d2 <= AP_GATE_D2:
                self.ap_x, self.ap_P, self.ap_refused_since = x, P, None
                continue
            self.counts["ap_refused"] += 1
            if self.ap_refused_since is None:
                self.ap_refused_since = self.t
            elif self.t - self.ap_refused_since >= AP_RESET_S:
                self.ap_x = [e, n, float(self.ap_x[2]), float(self.ap_x[3])]
                self.ap_P = [[sigma ** 2, 0, 0, 0], [0, sigma ** 2, 0, 0], [0, 0, 4.0, 0], [0, 0, 0, 4.0]]
                self.ap_refused_since = None
                self.counts["ap_resets"] += 1
                self.event(f"autopilot: position reset on the GPS_INPUT fix (refused for {AP_RESET_S:g} s)")

    def belief(self):
        return None if self.ap_x is None else (float(self.ap_x[0]), float(self.ap_x[1]))

    # ------------------------------------------------------------------ guidance and motion
    def move(self):
        b = self.belief()
        target = 0.0
        if self.phase == "waiting" and b is not None:
            self.phase, self.ap_mode, self.t_takeoff = "enroute", "MISSION", self.t
            self.event("take-off: the autopilot follows NAVERA Lite's position")
        if self.phase == "enroute":
            if self.ap_last_fix_t is not None and self.t - self.ap_last_fix_t > FAILSAFE_S:
                self.phase = "failsafe"
                self.ap_mode = "LAND" if self.vehicle in ("drone", "plane") else "HOLD"
                self.failsafe_t = self.mission_t
                self.event(f"autopilot FAILSAFE → {self.ap_mode} (no usable position for {FAILSAFE_S:g} s)")
            elif math.hypot(self.dest[0] - b[0], self.dest[1] - b[1]) < max(10.0, 1.5 * self.cruise):
                self.phase, self.ap_mode, self.arrived_t = "arrived", "ARRIVED", self.mission_t
                miss = math.hypot(self.dest[0] - self.truth[0], self.dest[1] - self.truth[1])
                self.event(f"arrived (by its own estimate) — really {miss:.0f} m from the destination")
            else:
                want = math.degrees(math.atan2(self.dest[0] - b[0], self.dest[1] - b[1])) % 360
                diff = (want - self.heading + 540) % 360 - 180
                turn = max(-self.turn_rate * DT, min(self.turn_rate * DT, diff))
                self.heading = (self.heading + turn) % 360
                target = self.cruise
        dv = max(-self.accel * DT, min(self.accel * DT, target - self.speed))
        self.speed = max(0.0, self.speed + dv)
        h = math.radians(self.heading)
        old = self.vel
        self.vel = (self.speed * math.sin(h), self.speed * math.cos(h))
        self.acc = ((self.vel[0] - old[0]) / DT, (self.vel[1] - old[1]) / DT)
        self.truth = [self.truth[0] + self.vel[0] * DT, self.truth[1] + self.vel[1] * DT]

    # ------------------------------------------------------------------ one step, one row
    def step(self, read_messages):
        m = self.mission_t
        while m is not None and self.pending and self.pending[0][0] <= m + 1e-9:
            _, key, value = self.pending.pop(0)
            self.set_fault(key, value)
        self.history.append(tuple(self.truth))
        if self.k % 2 == 0:
            self.gps_fix()
        if self.k % int(round(VISION_PERIOD_S / DT)) == 1:
            self.vision_fix()
        due = [(e, v) for k, e, v in self.arrivals if k <= self.k]
        self.arrivals = [a for a in self.arrivals if a[0] > self.k]
        self.judge_and_send(due)
        self.autopilot(read_messages)
        self.move()
        if self.t_takeoff is not None and self.k % int(round(ROW_S / DT)) == 0:
            self.rows.append(self.row())
        self.k += 1
        m = self.mission_t
        if m is not None and (m >= self.duration - 1e-9 or (self.arrived_t is not None and m >= self.arrived_t + 5.0)
                              or (self.failsafe_t is not None and m >= self.failsafe_t + 10.0)):
            self.done = True
        if self.t > self.duration + 120.0:
            self.done = True
            self.event("stopped: no take-off (NAVERA Lite never gave a usable position)")

    def row(self):
        f = lambda v, d=1: "" if v is None else f"{v:.{d}f}"           # noqa: E731
        d = self.decision
        lite_e = None
        if self.lite is not None and d is not None and d.state in ("FIX", "DEGRADED"):
            lite_e = self.dist_truth(self.lite[0], self.lite[1])
        b = self.belief()
        tl = self.frame.latlon(*self.truth)
        ll = self.frame.latlon(self.lite[0], self.lite[1]) if lite_e is not None else (None, None)
        guard = getattr(getattr(self.judge, "guard", None), "state", "")
        return {"t_s": f(self.mission_t), "phase": self.phase, "gps_mode": self.faults["gps"],
                "camera": self.faults["camera"], "imu": self.faults["imu"], "light": self.faults["light"],
                "lite_state": d.state if d else "STARTING", "lite_source": (d.source or "") if d else "",
                "lite_sigma_m": f(d.sigma_m if d else None), "lite_err_m": f(lite_e), "guard": guard,
                "gps_err_m": f(self.gps_err), "vis_err_m": f(self.vis_err), "ap_mode": self.ap_mode,
                "ap_err_m": f(None if b is None else self.dist_truth(*b)), "truth_lat": f(tl[0], 7),
                "truth_lon": f(tl[1], 7), "truth_speed_mps": f(self.speed), "lite_lat": f(ll[0], 7),
                "lite_lon": f(ll[1], 7), "reason": d.reason if d else ""}

    def run(self, read_messages):
        while not self.done:
            self.step(read_messages)
        return self

    def outcome(self):
        """A short summary of the flight (also written at the end of the events log)."""
        miss = math.hypot(self.dest[0] - self.truth[0], self.dest[1] - self.truth[1])
        return {"arrived_s": self.arrived_t, "failsafe_s": self.failsafe_t, "ap_mode": self.ap_mode,
                "miss_m": round(miss, 1), "rows": len(self.rows), **self.counts}
