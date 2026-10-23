"""The frame heading carried by the gyro between vision fixes, for the day pipeline's carry.

Without an attitude in the frame meta (attitude_source "none": no IMU attitude at the exposure, or
one the installation does not trust) the day pipeline carried its position straight on along the
last measured velocity: on a turn, after a gap of a few seconds, it lands outside its own search
circle (screen bench 2026-10-20, heavy rain 60 m/s on a 900 m circuit: 264 m max error straight on,
35.7 m with a gyro heading). Here the heading the vision measures on a good fix (the matcher's fitted
rotation: the azimuth of the frame top) is carried on by integrating the gyro's rate about the
vertical until the next good fix.

The carried heading ages out: its 1-sigma grows from the vision heading's with the gyro bias
(bias x time) and its noise (random walk); beyond max_sigma_deg, or across a gap in the gyro
samples, there is no heading (the carry goes straight on, as without a gyro). A vision heading
that disagrees with a still-valid carried one by more than 3 sigma is not taken (a wrong-place
match has a meaningless rotation): the carried heading keeps ageing until one agrees or it expires.

While the GPS is trusted the heading is also reset from the GPS course (CourseReset): above
~5 m/s, on a steady course (the gyro turned less than a few degrees over the window), the frame
top's azimuth is the course plus the camera's offset from it — learned from vision headings
measured while the course was known, else the camera mount's yaw for a vehicle flying nose first.
Without it a frame with no attitude got no heading until a vision fix, and the learned matcher
gets none without a heading: a real flight (MARS-LVIG AMvalley03, no attitude in the frames) gave 0
fixes in 310 s after the GPS loss.

Pure Python, no ROS: the day node and the bench replay use the same code.
"""
import math
import threading
from collections import deque
from typing import Optional, Sequence, Tuple


def _wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def heading_rate_dps(w_body: Sequence[float], q_xyzw: Optional[Sequence[float]] = None) -> float:
    """Rate of the heading (deg/s, clockwise seen from above) from a body angular rate (rad/s,
    sensor_msgs/Imu: ENU, z up). With the attitude quaternion, the rate about the vertical (its yaw,
    possibly wrong without a magnetometer, does not enter: only roll and pitch tilt the axis);
    without, the body z rate (a level vehicle)."""
    wx, wy, wz = (float(c) for c in w_body)
    if q_xyzw is not None:
        x, y, z, w = (float(c) for c in q_xyzw)
        n = x * x + y * y + z * z + w * w
        if 0.9 < n < 1.1:
            # third row of R(q): the world vertical expressed in the body frame
            wz = (2 * (x * z - w * y)) * wx + (2 * (y * z + w * x)) * wy + (1 - 2 * (x * x + y * y)) * wz
    return -math.degrees(wz)


class GyroHeading:
    def __init__(self, bias_dps: float = 0.1, noise_dps_rthz: float = 0.02, reset_sigma_deg: float = 2.0,
                 max_sigma_deg: float = 10.0, max_gap_s: float = 0.5, history_s: float = 300.0):
        """bias_dps: the gyro bias left after its calibration (the heading drifts by it);
        noise_dps_rthz: rate noise density (random walk of the heading); reset_sigma_deg: 1-sigma
        of a vision heading; max_sigma_deg: beyond it the carried heading is not given (with the
        defaults: ~100 s after the last good fix); max_gap_s: gyro samples further apart are a gap."""
        self.bias, self.noise = bias_dps, noise_dps_rthz
        self.reset_sigma, self.max_sigma, self.max_gap, self.history_s = \
            reset_sigma_deg, max_sigma_deg, max_gap_s, history_s
        self._cum = deque()            # (t, integrated heading change since the first sample, deg)
        self._gaps = deque()           # (t0, t1): no samples in between
        self._ref = None               # (t, heading_deg, sigma_deg) of the last vision heading taken
        self._lock = threading.Lock()  # the IMU is read in its own thread

    def add_rate(self, t: float, rate_dps: float) -> None:
        """One gyro sample: the heading rate (deg/s clockwise) at sensor time t."""
        if not math.isfinite(rate_dps):
            return
        with self._lock:
            if not self._cum:
                self._cum.append((t, 0.0, rate_dps))
                return
            t0, c0, r0 = self._cum[-1]
            if t <= t0:
                if t < t0 - 1.0:                     # clock stepped back: start again
                    self._cum.clear(); self._gaps.clear(); self._ref = None
                    self._cum.append((t, 0.0, rate_dps))
                return
            if t - t0 > self.max_gap:
                self._gaps.append((t0, t))
                c = c0                               # nothing known about the turn in the gap
            else:
                c = c0 + 0.5 * (r0 + rate_dps) * (t - t0)
            self._cum.append((t, c, rate_dps))
            while self._cum and self._cum[0][0] < t - self.history_s:
                self._cum.popleft()
            while self._gaps and self._gaps[0][1] < t - self.history_s:
                self._gaps.popleft()

    def _integral(self, t: float) -> Optional[float]:
        """Integrated heading change at t (interpolated), or None outside the samples (a little
        past the last one: extrapolated at its rate, the samples arrive after the frame)."""
        if not self._cum or t < self._cum[0][0]:
            return None
        last = self._cum[-1]
        if t >= last[0]:
            return last[1] + last[2] * (t - last[0]) if t - last[0] <= self.max_gap else None
        lo, hi = 0, len(self._cum) - 1                # binary search in the deque (indexable)
        while hi - lo > 1:
            m = (lo + hi) // 2
            if self._cum[m][0] <= t:
                lo = m
            else:
                hi = m
        (ta, ca, _), (tb, cb, _) = self._cum[lo], self._cum[hi]
        return ca + (cb - ca) * (t - ta) / (tb - ta) if tb > ta else ca

    def _sigma(self, dt: float, s0: float) -> float:
        dt = abs(dt)
        return math.sqrt(s0 * s0 + (self.bias * dt) ** 2 + self.noise * self.noise * dt)

    def at(self, t: float) -> Optional[Tuple[float, float]]:
        """(heading_deg, sigma_deg) carried to t from the last vision heading, or None (no vision
        heading yet, a gyro gap since, outside the samples, or aged beyond max_sigma_deg)."""
        with self._lock:
            if self._ref is None:
                return None
            tr, hr, sr = self._ref
            sig = self._sigma(t - tr, sr)
            if sig > self.max_sigma:
                return None
            lo, hi = min(tr, t), max(tr, t)
            if any(g0 < hi and g1 > lo for g0, g1 in self._gaps):
                return None
            ca, cb = self._integral(tr), self._integral(t)
            if ca is None or cb is None:
                return None
            return (hr + cb - ca) % 360.0, sig

    def turn(self, t0: float, t1: float) -> Optional[float]:
        """Heading change (deg) integrated from t0 to t1, or None (outside the samples, or a gap)."""
        with self._lock:
            if any(g0 < t1 and g1 > t0 for g0, g1 in self._gaps):
                return None
            a, b = self._integral(t0), self._integral(t1)
        return None if a is None or b is None else b - a

    def reset(self, t: float, heading_deg: float, sigma_deg: Optional[float] = None) -> bool:
        """A vision heading at t. Taken unless a still-valid carried heading disagrees with it by
        more than 3 sigma (both); True when taken."""
        s = self.reset_sigma if sigma_deg is None else float(sigma_deg)
        cur = self.at(t)
        if cur is not None and abs(_wrap(heading_deg - cur[0])) > 3.0 * math.hypot(cur[1], s):
            return False
        with self._lock:
            self._ref = (t, float(heading_deg) % 360.0, s)
        return True

    def clear(self) -> None:
        """Forget the vision heading (mission rewind)."""
        with self._lock:
            self._ref = None


def _bearing_deg(p0, p1) -> Tuple[float, float]:
    """(bearing deg clockwise from north, distance m) from p0 to p1 (lat, lon), locally flat."""
    dn = (p1[0] - p0[0]) * 111_320.0
    de = (p1[1] - p0[1]) * 111_320.0 * math.cos(math.radians(p0[0]))
    return math.degrees(math.atan2(de, dn)) % 360.0, math.hypot(de, dn)


class CourseReset:
    """The gyro heading reset from the GPS course while the GPS is trusted (module doc)."""

    def __init__(self, min_speed_mps: float = 5.0, window_s: float = 2.0, max_turn_deg: float = 3.0,
                 pos_noise_m: float = 0.5, crab_sigma_deg: float = 5.0, min_interval_s: float = 1.0,
                 min_offset_samples: int = 3):
        """min_speed_mps: below it the course is noise; window_s: the course is the chord of the GPS
        track over it; max_turn_deg: the gyro turned less than this over the window (on a turn the
        chord lags the heading); pos_noise_m: GPS noise between two fixes window_s apart (its
        absolute error cancels in the chord); crab_sigma_deg: 1-sigma of the frame-top offset from
        the course when it comes from the mount (crab, a vehicle not flying straight nose first);
        min_offset_samples: vision samples before the learned offset replaces the mount's."""
        self.min_speed, self.window, self.max_turn = min_speed_mps, window_s, max_turn_deg
        self.pos_noise, self.crab_sigma, self.min_interval = pos_noise_m, crab_sigma_deg, min_interval_s
        self.min_samples = min_offset_samples
        self._offsets = deque(maxlen=30)
        self._last_reset = -math.inf

    def course(self, track, gyro: Optional[GyroHeading], t: float) -> Optional[Tuple[float, float]]:
        """(course deg, its sigma deg) of the GPS track (a History of (lat, lon)) ending at t, or None:
        too slow, too few fixes, or turning (gyro) — or no gyro to tell."""
        p1, p0 = track.at(t), track.at(t - self.window)
        if p0 is None or p1 is None or gyro is None:
            return None
        crs, dist = _bearing_deg(p0, p1)
        if dist < self.min_speed * self.window:
            return None
        turn = gyro.turn(t - self.window, t)
        if turn is None or abs(turn) > self.max_turn:
            return None
        return crs, math.degrees(math.atan2(math.sqrt(2.0) * self.pos_noise, dist))

    def add_offset_sample(self, frame_heading_deg: float, course_deg: float) -> None:
        """A vision heading (the frame top's azimuth) measured while the course was known."""
        self._offsets.append(_wrap(frame_heading_deg - course_deg))

    def offset(self, mount_yaw_deg: Optional[float]) -> Optional[Tuple[float, float]]:
        """(frame top - course deg, sigma deg): learned from vision (circular mean, sigma its spread,
        at least 2 deg), else -mount yaw (a downward camera on a vehicle flying nose first), else None."""
        offs = list(self._offsets)          # a copy: samples are added from the frame thread
        if len(offs) >= self.min_samples:
            sn = sum(math.sin(math.radians(o)) for o in offs)
            cs = sum(math.cos(math.radians(o)) for o in offs)
            mean = math.degrees(math.atan2(sn, cs))
            spread = math.sqrt(sum(_wrap(o - mean) ** 2 for o in offs) / len(offs))
            return mean, max(2.0, spread)
        if mount_yaw_deg is None or not math.isfinite(mount_yaw_deg):
            return None
        return _wrap(-mount_yaw_deg), self.crab_sigma

    def maybe_reset(self, gyro: Optional[GyroHeading], track, t: float,
                    mount_yaw_deg: Optional[float]) -> Optional[Tuple[float, float]]:
        """Reset the gyro heading at t from the course when it is known and more certain than the
        carried heading; (heading, sigma) when it did."""
        if gyro is None or t - self._last_reset < self.min_interval:
            return None
        c = self.course(track, gyro, t)
        off = self.offset(mount_yaw_deg) if c is not None else None
        if off is None:
            return None
        h, sig = (c[0] + off[0]) % 360.0, math.hypot(c[1], off[1])
        cur = gyro.at(t)
        if cur is not None and cur[1] <= sig:
            return None                                 # a fresher vision heading is better
        if not gyro.reset(t, h, sig):
            return None
        self._last_reset = t
        return h, sig
