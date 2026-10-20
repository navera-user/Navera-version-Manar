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
