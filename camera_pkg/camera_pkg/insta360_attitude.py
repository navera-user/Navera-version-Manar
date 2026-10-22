"""The vehicle's attitude from the Insta360 One R's own IMU, for the Insta360 kit (the camera is
also the IMU: no BNO085, no autopilot needed).

Input: body-frame samples from camera_pkg.insta360_imu.ImuStream (host time, gyro rad/s with the
bias at rest removed, specific force m/s^2 with gravity, REP-145: +9.81 up at rest). Output: the
body attitude (body FLU -> world ENU, sensor_msgs/Imu convention) with honest 1-sigma values.

Roll and pitch — a Mahony complementary filter: the gyro is integrated, and the tilt is pulled
towards the accelerometer's 'up' with a time constant of 1/kp (20 s by default). The accelerometer
only measures 'up' when the vehicle does not accelerate (D8 in the problems doc: 0.1 g of braking
or a curve tilts 'up' by ~6 deg with |a| unchanged), so the pull is:
  * off while |specific force| is more than acc_gate_g from 1 g, while the body turns faster than
    rate_gate_dps, or while it turns about the vertical faster than turn_gate_dps (a curve: the
    centripetal acceleration is horizontal, |a| barely changes) — unless the speed is known;
  * with the speed known (GPS track while the GPS is trusted): the turn's centripetal acceleration
    (speed x turn rate about the vertical, across the nose's track) and the along-track one (dv/dt)
    of a vehicle moving nose first are removed first, and the turn gate is replaced by the residual
    check;
  * strong (kp_still, 2 s) only when the vehicle is STOPPED: rotation under 1 deg/s and the
    accelerometer's 0.2 s means steady within 0.003 g over 2 s (the field driver's rule,
    navera_tools/field/insta360_usb.STILL_*), and the GPS speed (when known) under 0.5 m/s.
  ki estimates what is left of the gyro bias on the roll / pitch axes.
The tilt 1-sigma: tilt_floor_deg while the accelerometer is used (the error a slow undetected
acceleration leaves, plus the lens-to-IMU mount), growing with the gyro noise and bias residual
while it is gated out, coming back with the time constant when it is used again.

Yaw — the gyro integrated (it needs no magnetometer and has none). It is NOT a heading until a
heading source sets it: heading_sigma_deg is infinite (the published yaw variance is pi^2) until
  * the GPS course, while the GPS is trusted: on a straight, fast enough leg the vehicle's heading
    is its course (a vehicle moving nose first; crab in wind is in course_sigma_deg), or
  * a vision heading: the day matcher's fitted rotation of a good fix (the frame top's azimuth);
then it is carried by the gyro, its sigma growing with the bias left about the vertical (the bias
at rest is re-measured at every stop; moving, it creeps by up to ~0.05 deg/s, measured) and the
noise. A heading that disagrees with a still-valid one by more than 3 sigma is refused (a wrong
match's rotation is meaningless). Both are blended as a 1-D Kalman update.

Pure Python + numpy, no ROS: camera_pkg.nodes.insta360_node and the tests use it.
"""
import math
from collections import deque
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import numpy as np

G = 9.80665
STILL_BLOCK_S = 0.2           # the field driver's stillness rule (navera_tools/field/insta360_usb.py)
STILL_WINDOW_S = 2.0
STILL_ACC_STD_G = 0.003
STILL_RATE_DPS = 1.0


def _wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def _rodrigues(v: np.ndarray) -> np.ndarray:
    """Rotation matrix of a rotation vector (rad)."""
    t = float(np.linalg.norm(v))
    if t < 1e-12:
        return np.eye(3)
    k = v / t
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + math.sin(t) * K + (1.0 - math.cos(t)) * (K @ K)


def _rz(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def quat_from_matrix(R: np.ndarray) -> Tuple[float, float, float, float]:
    """(x, y, z, w) of a rotation matrix."""
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w, x, y, z = 0.25 * s, (R[2, 1] - R[1, 2]) / s, (R[0, 2] - R[2, 0]) / s, (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        w, x, y, z = (R[2, 1] - R[1, 2]) / s, 0.25 * s, (R[0, 1] + R[1, 0]) / s, (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        w, x, y, z = (R[0, 2] - R[2, 0]) / s, (R[0, 1] + R[1, 0]) / s, 0.25 * s, (R[1, 2] + R[2, 1]) / s
    else:
        s = math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        w, x, y, z = (R[1, 0] - R[0, 1]) / s, (R[0, 2] + R[2, 0]) / s, (R[1, 2] + R[2, 1]) / s, 0.25 * s
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if w < 0:
        n = -n
    return x / n, y / n, z / n, w / n


def heading_of(R: np.ndarray) -> float:
    """Azimuth of the body's nose (deg clockwise from north) for R body -> ENU."""
    return math.degrees(math.atan2(R[0, 0], R[1, 0])) % 360.0


def tilt_from_up(up_body: np.ndarray, heading_deg: float = 0.0) -> np.ndarray:
    """R body -> ENU with the body's 'up' (unit, body frame) and a heading (deg from north)."""
    u = np.asarray(up_body, float) / np.linalg.norm(up_body)
    roll = math.atan2(u[1], u[2])
    pitch = math.atan2(-u[0], math.hypot(u[1], u[2]))           # ROS: positive = nose down
    cr, sr, cp, sp = math.cos(roll), math.sin(roll), math.cos(pitch), math.sin(pitch)
    Ry = np.array([[cp, 0.0, sp], [0.0, 1.0, 0.0], [-sp, 0.0, cp]])
    Rx = np.array([[1.0, 0.0, 0.0], [0.0, cr, -sr], [0.0, sr, cr]])
    return _rz(math.radians(90.0 - heading_deg)) @ Ry @ Rx


@dataclass
class AttitudeState:
    """One output: host time, body -> ENU quaternion (x, y, z, w), roll / pitch (deg, ROS: pitch
    positive nose DOWN), heading (deg from north; meaningless while heading_sigma_deg is inf), the
    1-sigma values, and why."""
    t: float
    q: Tuple[float, float, float, float]
    roll_deg: float
    pitch_deg: float
    heading_deg: float
    tilt_sigma_deg: float
    heading_sigma_deg: float
    accel_used: bool
    still: bool
    heading_source: str

    def covariance(self) -> list:
        """sensor_msgs/Imu orientation_covariance (row-major 3x3, rad^2, about x, y, z): roll and
        pitch from the tilt sigma, yaw from the heading sigma (pi^2 when unknown)."""
        vt = math.radians(self.tilt_sigma_deg) ** 2
        vy = math.pi ** 2 if not math.isfinite(self.heading_sigma_deg) else \
            min(math.pi ** 2, math.radians(self.heading_sigma_deg) ** 2)
        return [vt, 0.0, 0.0, 0.0, vt, 0.0, 0.0, 0.0, vy]


class AttitudeFilter:
    def __init__(self, kp: float = 0.05, ki: float = 0.0005, kp_still: float = 0.5,
                 acc_gate_g: float = 0.03, rate_gate_dps: float = 20.0, turn_gate_dps: float = 1.0,
                 tilt_floor_deg: float = 0.5, tilt_floor_blind_deg: float = 1.0,
                 gyro_noise_dps_rthz: float = 0.0033,
                 tilt_bias_dps: float = 0.02, heading_bias_dps: float = 0.05,
                 heading_noise_dps_rthz: float = 0.004, init_s: float = 0.5, history_s: float = 30.0,
                 max_gap_s: float = 0.25):
        """kp, ki: Mahony gains (1/s, 1/s^2) while moving; kp_still: while stopped. acc_gate_g,
        rate_gate_dps, turn_gate_dps: when the accelerometer is not used (module doc).
        tilt_floor_deg: tilt 1-sigma while the accelerometer is used and the speed is known (or the
        vehicle is stopped); tilt_floor_blind_deg: moving without the speed (GPS lost), when slow
        accelerations under the gate go unnoticed (synthetic copter / car runs: 1.4-1.9 deg max);
        gyro_noise_dps_rthz,
        tilt_bias_dps: its growth while gated out. heading_bias_dps, heading_noise_dps_rthz: the
        carried heading's sigma growth. init_s: the first samples averaged for the first tilt.
        max_gap_s: samples further apart are a gap (no integration across it, sigmas grow)."""
        self.kp, self.ki, self.kp_still = kp, ki, kp_still
        self.acc_gate, self.rate_gate = acc_gate_g, math.radians(rate_gate_dps)
        self.turn_gate = math.radians(turn_gate_dps)
        self.tilt_floor, self.gyro_noise, self.tilt_bias = tilt_floor_deg, gyro_noise_dps_rthz, tilt_bias_dps
        self.tilt_floor_blind = max(tilt_floor_deg, tilt_floor_blind_deg)
        self.h_bias, self.h_noise = heading_bias_dps, heading_noise_dps_rthz
        self.init_s, self.history_s, self.max_gap = init_s, history_s, max_gap_s
        self.R: Optional[np.ndarray] = None
        self.b = np.zeros(3)                       # gyro bias left (rad/s), from ki
        self.t: Optional[float] = None
        self.tilt_sigma = 90.0
        self._init = []
        self._href: Optional[Tuple[float, float]] = None    # (t, sigma deg) of the last heading taken
        self.heading_source = "none"
        self._hist = deque()                       # (t, unwrapped heading deg, R)
        self._unwrapped = 0.0
        self._blocks = deque()                     # (t, mean accel g, max rate) of STILL_BLOCK_S blocks
        self._blk = []
        self._blk_t0 = None
        self.still = False
        self.accel_used = False
        self.gaps = 0

    # ── propagation ───────────────────────────────────────────────────────
    def update(self, t: float, w: Sequence[float], f: Sequence[float], speed_mps: Optional[float] = None,
               accel_fwd_mps2: Optional[float] = None) -> Optional[AttitudeState]:
        """One body-frame sample (host time t, gyro rad/s, specific force m/s^2). speed_mps,
        accel_fwd_mps2: the vehicle's ground speed and its rate of change when known (GPS), for
        removing the turn and along-track accelerations from the accelerometer."""
        w, f = np.asarray(w, float), np.asarray(f, float)
        if self.R is None:
            self._init.append((t, f))
            if t - self._init[0][0] < self.init_s:
                return None
            up = np.mean([x[1] for x in self._init], axis=0)
            self.R = tilt_from_up(up)
            self.t, self.tilt_sigma = t, 2.0 * self.tilt_floor
            self._init = []
            self._remember(t)
            return self.state(t)
        dt = t - self.t
        if dt <= 0.0:
            return None
        self.t = t
        self._still_update(t, w, f, speed_mps)
        if dt > self.max_gap:                      # nothing known in the gap: no integration
            self.gaps += 1
            self.tilt_sigma = math.hypot(self.tilt_sigma, 5.0)      # a turn in the gap is unknown
            self.forget_heading()
            self._remember(t)
            return self.state(t)
        up_hat = self.R[2, :]                      # world up in the body frame
        fc = f.copy()
        if speed_mps is not None and math.isfinite(speed_mps):
            # the vehicle's acceleration on the ground track: along it (dv/dt) and across it
            # (speed x turn rate about the vertical), both horizontal; pitch / roll oscillations do
            # not turn the track (a body-axis w x v would read them as accelerations)
            x_w = self.R[:, 0].copy()
            x_w[2] = 0.0
            nx = float(np.linalg.norm(x_w))
            if nx > 0.2:
                x_w /= nx
                left_w = np.array([-x_w[1], x_w[0], 0.0])
                along = float(accel_fwd_mps2) if accel_fwd_mps2 is not None and math.isfinite(accel_fwd_mps2) else 0.0
                a_w = along * x_w + float(speed_mps) * float(w @ up_hat) * left_w
                fc = fc - self.R.T @ a_w
        n = float(np.linalg.norm(fc))
        rate = float(np.linalg.norm(w))
        vert = abs(float(w @ up_hat))
        use = (n > 0.0 and abs(n / G - 1.0) < self.acc_gate and rate < self.rate_gate
               and (speed_mps is not None or vert < self.turn_gate or self.still))
        kp = self.kp_still if self.still else self.kp
        wc = w - self.b
        if use:
            e = np.cross(fc / n, up_hat)          # small rotation taking the estimate onto the measurement
            wc = wc + kp * e
            if not self.still:
                self.b = self.b - self.ki * e * dt
            tau = 1.0 / kp
            floor = self.tilt_floor if (self.still or speed_mps is not None) else self.tilt_floor_blind
            self.tilt_sigma = floor + (self.tilt_sigma - floor) * math.exp(-dt / tau)
        else:
            self.tilt_sigma = math.sqrt(self.tilt_sigma ** 2 + (self.gyro_noise ** 2) * dt) + self.tilt_bias * dt
        self.accel_used = use
        self.R = self.R @ _rodrigues(wc * dt)
        u, _, vt = np.linalg.svd(self.R)           # keep it a rotation
        self.R = u @ vt
        self._remember(t)
        return self.state(t)

    def _still_update(self, t, w, f, speed):
        """The field driver's stillness: 0.2 s accelerometer means steady within 0.003 g and the
        rotation under 1 deg/s over 2 s, and not moving by the GPS when it is known."""
        if self._blk_t0 is None:
            self._blk_t0 = t
        self._blk.append((f / G, float(np.linalg.norm(w))))
        if t - self._blk_t0 >= STILL_BLOCK_S:
            self._blocks.append((t, np.mean([b[0] for b in self._blk], axis=0), max(b[1] for b in self._blk)))
            self._blk, self._blk_t0 = [], t
            while self._blocks and self._blocks[0][0] < t - STILL_WINDOW_S:
                self._blocks.popleft()
        blocks = list(self._blocks)
        if len(blocks) < int(STILL_WINDOW_S / STILL_BLOCK_S) - 1 or (blocks and t - blocks[-1][0] > 2 * STILL_BLOCK_S):
            self.still = False
            return
        means = np.array([b[1] for b in blocks])
        self.still = (float(means.std(axis=0).max()) < STILL_ACC_STD_G
                      and max(b[2] for b in blocks) < math.radians(STILL_RATE_DPS)
                      and (speed is None or not math.isfinite(speed) or speed < 0.5))

    def _remember(self, t):
        h = heading_of(self.R)
        if self._hist:
            self._unwrapped += _wrap(h - self._hist[-1][1] % 360.0)
        else:
            self._unwrapped = h
        self._hist.append((t, self._unwrapped, self.R.copy()))
        while self._hist and self._hist[0][0] < t - self.history_s:
            self._hist.popleft()

    # ── outputs ───────────────────────────────────────────────────────────
    def heading_sigma(self, t: float) -> float:
        """1-sigma (deg) of the heading at t, inf when no heading source set it (or after a gap)."""
        if self._href is None:
            return math.inf
        tr, s0 = self._href
        dt = abs(t - tr)
        return math.sqrt(s0 * s0 + (self.h_bias * dt) ** 2 + self.h_noise ** 2 * dt)

    def state(self, t: float) -> AttitudeState:
        R = self.R
        roll = math.degrees(math.atan2(R[2, 1], R[2, 2]))
        pitch = math.degrees(-math.asin(max(-1.0, min(1.0, R[2, 0]))))
        return AttitudeState(t, quat_from_matrix(R), roll, pitch, heading_of(R), self.tilt_sigma,
                             self.heading_sigma(t), self.accel_used, self.still, self.heading_source)

    def _at(self, t: float):
        """(unwrapped heading, R) at t from the history (nearest sample within max_gap), or None."""
        if not self._hist or t < self._hist[0][0] - self.max_gap or t > self._hist[-1][0] + self.max_gap:
            return None
        lo, hi = 0, len(self._hist) - 1
        while hi - lo > 1:
            m = (lo + hi) // 2
            if self._hist[m][0] <= t:
                lo = m
            else:
                hi = m
        a, b = self._hist[lo], self._hist[hi]
        if b[0] > a[0] and a[0] <= t <= b[0]:
            f = (t - a[0]) / (b[0] - a[0])
            return a[1] + f * (b[1] - a[1]), (a[2] if f < 0.5 else b[2])
        near = min((a, b), key=lambda x: abs(x[0] - t))
        return near[1], near[2]

    def matrix_at(self, t: float) -> Optional[np.ndarray]:
        x = self._at(t)
        return None if x is None else x[1]

    def heading_at(self, t: float) -> Optional[float]:
        x = self._at(t)
        return None if x is None else x[0] % 360.0

    def turn(self, t0: float, t1: float) -> Optional[float]:
        """Heading change (deg, clockwise) from t0 to t1, or None outside the history."""
        a, b = self._at(t0), self._at(t1)
        return None if a is None or b is None else b[0] - a[0]

    # ── heading sources ───────────────────────────────────────────────────
    def set_heading(self, t: float, heading_deg: float, sigma_deg: float, source: str,
                    only_if_better: bool = False) -> bool:
        """A measured heading of the body's nose at time t (deg from north, its 1-sigma). Refused
        when the carried heading is valid and disagrees by more than 3 sigma (both), or, with
        only_if_better, when the carried one is already more certain. True when taken."""
        if self.R is None or not (math.isfinite(heading_deg) and sigma_deg > 0):
            return False
        cur = self._at(t)
        if cur is None:
            return False
        s_cur = self.heading_sigma(t)
        if only_if_better and s_cur <= sigma_deg:
            return False
        d = _wrap(heading_deg - cur[0] % 360.0)
        if math.isfinite(s_cur):
            if abs(d) > 3.0 * math.hypot(s_cur, sigma_deg):
                return False
            k = s_cur ** 2 / (s_cur ** 2 + sigma_deg ** 2)
            s_new = math.sqrt(s_cur ** 2 * sigma_deg ** 2 / (s_cur ** 2 + sigma_deg ** 2))
        else:
            k, s_new = 1.0, sigma_deg
        rot = _rz(-math.radians(k * d))            # clockwise heading = negative ENU yaw
        self.R = rot @ self.R
        self._hist = deque((tt, u + k * d, rot @ RR) for tt, u, RR in self._hist)
        self._unwrapped += k * d
        self._href = (t, s_new)
        self.heading_source = source
        return True

    def forget_heading(self) -> None:
        self._href = None
        self.heading_source = "none"


def _bearing(p0, p1) -> Tuple[float, float]:
    """(bearing deg from north, distance m) from p0 to p1 (lat, lon), locally flat."""
    dn = (p1[0] - p0[0]) * 111_320.0
    de = (p1[1] - p0[1]) * 111_320.0 * math.cos(math.radians(p0[0]))
    return math.degrees(math.atan2(de, dn)) % 360.0, math.hypot(de, dn)


class GpsCourse:
    """The trusted GPS track: the vehicle's speed and along-track acceleration (for the tilt) and
    its course (for the heading) — the day node's CourseReset rule (day_pkg/gyro_heading.py):
    above min_speed_mps, on a straight leg (the gyro turned less than max_turn_deg over window_s),
    the heading is the course of the chord over window_s; its sigma is the chord's from the GPS
    noise, with course_sigma_deg for crab (wind, sideslip)."""

    def __init__(self, window_s: float = 2.0, min_speed_mps: float = 5.0, max_turn_deg: float = 3.0,
                 pos_noise_m: float = 0.5, course_sigma_deg: float = 10.0, max_age_s: float = 1.5,
                 min_interval_s: float = 1.0):
        self.window, self.min_speed, self.max_turn = window_s, min_speed_mps, max_turn_deg
        self.pos_noise, self.course_sigma, self.max_age = pos_noise_m, course_sigma_deg, max_age_s
        self.min_interval = min_interval_s
        self._fixes = deque(maxlen=200)            # (t, lat, lon)
        self._speeds = deque(maxlen=20)            # (t, speed)
        self._last_set = -math.inf
        self.sets = 0

    def add_fix(self, t: float, lat: float, lon: float) -> None:
        if self._fixes and t <= self._fixes[-1][0]:
            if t < self._fixes[-1][0] - 1.0:
                self._fixes.clear()
                self._speeds.clear()
            return
        self._fixes.append((t, lat, lon))
        s = self._chord(t)
        if s is not None:
            self._speeds.append((t, s[1] / s[2]))

    def clear(self) -> None:
        """The GPS is no longer trusted: nothing from it."""
        self._fixes.clear()
        self._speeds.clear()

    def _chord(self, t: float):
        """(bearing, distance, duration) of the track over the window ending at t."""
        pts = [p for p in self._fixes if t - self.window - 0.25 <= p[0] <= t + 1e-6]
        if len(pts) < 2 or pts[-1][0] - pts[0][0] < 0.5 * self.window:
            return None
        b, d = _bearing(pts[0][1:], pts[-1][1:])
        return b, d, pts[-1][0] - pts[0][0]

    def speed(self, now: float) -> Tuple[Optional[float], Optional[float]]:
        """(ground speed m/s, its rate m/s^2) when the newest fix is fresh, else (None, None)."""
        if not self._speeds or now - self._speeds[-1][0] > self.max_age:
            return None, None
        t1, v1 = self._speeds[-1]
        old = [s for s in self._speeds if s[0] <= t1 - 1.0]
        acc = (v1 - old[-1][1]) / (t1 - old[-1][0]) if old else 0.0
        return v1, acc

    def maybe_set(self, flt: AttitudeFilter) -> Optional[Tuple[float, float]]:
        """Set the filter's heading from the course when it is known and more certain than the
        carried heading; (heading, sigma) when it did."""
        if not self._fixes:
            return None
        t = self._fixes[-1][0]
        if t - self._last_set < self.min_interval:
            return None
        c = self._chord(t)
        if c is None or c[1] < self.min_speed * c[2]:
            return None
        turn = flt.turn(t - c[2], t)
        if turn is None or abs(turn) > self.max_turn:
            return None
        sig = math.hypot(math.degrees(math.atan2(math.sqrt(2.0) * self.pos_noise, c[1])), self.course_sigma)
        # the chord is the mean course over the window: its middle instant
        if not flt.set_heading(t - c[2] / 2.0, c[0], sig, "gps course", only_if_better=True):
            return None
        self._last_set = t
        self.sets += 1
        return c[0], sig
