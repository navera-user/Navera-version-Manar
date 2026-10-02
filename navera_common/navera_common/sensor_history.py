"""Short time-indexed histories of sensor samples, read at a frame's exposure time.

A camera frame must be paired with the attitude and position of the instant it was
taken, not with whatever arrived last: at 50 deg/s of roll, 100 ms of mismatch is a
5 deg attitude error (13 m on the ground at 150 m).

* History — samples (t, value) in time order; `at(t)` interpolates between the two
  samples around t (linear for numbers, slerp for quaternions), or returns None when
  t is outside the recorded span by more than `max_gap_s`.
"""
import bisect
import math
import threading
from collections import deque
from typing import Callable, Optional, Sequence, Tuple


def slerp(q0: Sequence[float], q1: Sequence[float], f: float) -> Tuple[float, ...]:
    """Spherical interpolation of (x, y, z, w) quaternions, shortest path."""
    d = sum(a * b for a, b in zip(q0, q1))
    if d < 0:
        q1, d = [-c for c in q1], -d
    if d > 0.9995:
        q = [a + f * (b - a) for a, b in zip(q0, q1)]
    else:
        th = math.acos(min(1.0, d))
        s0, s1 = math.sin((1 - f) * th) / math.sin(th), math.sin(f * th) / math.sin(th)
        q = [s0 * a + s1 * b for a, b in zip(q0, q1)]
    n = math.sqrt(sum(c * c for c in q))
    return tuple(c / n for c in q)


def lerp(v0, v1, f: float):
    if isinstance(v0, (int, float)):
        return v0 + f * (v1 - v0)
    return tuple(a + f * (b - a) for a, b in zip(v0, v1))


class History:
    """Time-ordered samples with interpolation at any instant inside their span."""

    def __init__(self, maxlen: int = 2000, max_gap_s: float = 0.25,
                 interp: Optional[Callable] = lerp):
        self._t = deque(maxlen=maxlen)
        self._v = deque(maxlen=maxlen)
        self.max_gap_s, self.interp = max_gap_s, interp
        self._lock = threading.Lock()

    def add(self, t: float, value) -> None:
        with self._lock:
            if self._t and t < self._t[-1] - 1.0:       # the clock stepped back (RTC/NTP set): restart
                self._t.clear()
                self._v.clear()
            if self._t and t <= self._t[-1]:            # out of order or duplicate: keep order
                if t == self._t[-1]:
                    self._v[-1] = value
                return
            self._t.append(t)
            self._v.append(value)

    def latest(self) -> Optional[Tuple[float, object]]:
        with self._lock:
            return (self._t[-1], self._v[-1]) if self._t else None

    def at(self, t: float):
        """The value at time t, or None when no sample is within max_gap_s of t
        (before the first, after the last, or across a gap in the data)."""
        with self._lock:
            ts, vs = list(self._t), list(self._v)
        if not ts:
            return None
        i = bisect.bisect_left(ts, t)
        if i == 0:
            return vs[0] if ts[0] - t <= self.max_gap_s else None
        if i == len(ts):
            return vs[-1] if t - ts[-1] <= self.max_gap_s else None
        t0, t1 = ts[i - 1], ts[i]
        if t1 - t0 > 2 * self.max_gap_s and min(t - t0, t1 - t) > self.max_gap_s:
            return None
        if self.interp is None:
            return vs[i - 1] if t - t0 <= t1 - t else vs[i]
        return self.interp(vs[i - 1], vs[i], (t - t0) / (t1 - t0))
