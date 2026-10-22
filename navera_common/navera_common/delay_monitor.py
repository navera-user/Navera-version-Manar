"""Notice a change of the camera delay in flight, without GPS.

The camera delay (exposure -> arrival) is measured once — on the bench (calibration file
latency_s), or against the GPS early in the flight (latency_cal) — and must hold for hours after
the GPS is lost. What can move it:

* queueing after the source stamps the frame: a USB frame waiting in the V4L2 queue, a frame
  waiting in a GStreamer queue / jitter buffer, the grab thread starved by CPU load;
* the network of an IP camera (retransmissions, a Wi-Fi link) between its RTP stamp and here.

These show in the time between the source's own stamp of a frame (the V4L2 buffer timestamp,
the GStreamer buffer PTS) and its arrival at NAVERA: d = arrival - source stamp. Its constant
part (clock offset) is unknown and irrelevant; a CHANGE of d is a change of the delay. What
happens before the source stamps the frame (sensor readout, the camera's own encoder) is not
seen: a camera whose encoder delay changes while its stamps do not cannot be noticed here.

The reference level is a low quantile (q) of d over the first ref_s seconds (the conditions the
delay was measured in: ground and GPS phase), the current level the same quantile over the last
recent_s seconds; change = current - reference. Two clocks drift (skew_ppm of the time since the
reference) and a level has its own noise: the change is "significant" only beyond those plus
min_change_s. A step of d by more than jump_s (a clock reset) restarts the reference.
"""
import math
from collections import deque
from typing import Optional


def _quantile(xs, q):
    s = sorted(xs)
    if not s:
        return None
    k = (len(s) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


class DelayChangeMonitor:
    """Change (s) of arrival - source stamp since the reference period."""

    def __init__(self, ref_s: float = 60.0, recent_s: float = 10.0, q: float = 0.2, min_n: int = 8,
                 skew_ppm: float = 100.0, min_change_s: float = 0.05, jump_s: float = 5.0):
        self.ref_s, self.recent_s, self.q, self.min_n = float(ref_s), float(recent_s), float(q), int(min_n)
        self.skew, self.min_change, self.jump = float(skew_ppm) * 1e-6, float(min_change_s), float(jump_s)
        self.reset()

    def reset(self) -> None:
        """Forget everything (a new reference starts with the next frame)."""
        self._t0: Optional[float] = None
        self._ref: list = []
        self._ref_level: Optional[float] = None
        self._ref_spread = 0.0
        self._recent: deque = deque()
        self.change_s: Optional[float] = None
        self.allowance_s: Optional[float] = None

    def add(self, t_arrival: float, t_source: float) -> Optional[float]:
        """One frame: its arrival (s, NAVERA's clock) and its source stamp (s, the source's clock).

        Returns the current change (s) or None while there is no reference / too few frames.
        """
        if not (math.isfinite(t_arrival) and math.isfinite(t_source)):
            return self.change_s
        d = t_arrival - t_source
        last = self._recent[-1][1] if self._recent else (self._ref[-1] if self._ref else None)
        if last is not None and abs(d - last) > self.jump:
            self.reset()                                   # the source clock was reset / re-based
        if self._t0 is None:
            self._t0 = t_arrival
        if self._ref_level is None:
            self._ref.append(d)
            if t_arrival - self._t0 >= self.ref_s and len(self._ref) >= self.min_n:
                self._ref_level = _quantile(self._ref, self.q)
                # the level's own noise: the quantile's scatter, from the spread above the low quantile
                hi = _quantile(self._ref, 0.5)
                self._ref_spread = max(0.0, hi - self._ref_level) / math.sqrt(len(self._ref)) * 2.0
            self._recent.append((t_arrival, d))
            while self._recent and self._recent[0][0] < t_arrival - self.recent_s:
                self._recent.popleft()
            return None
        self._recent.append((t_arrival, d))
        while self._recent and self._recent[0][0] < t_arrival - self.recent_s:
            self._recent.popleft()
        if len(self._recent) < self.min_n:
            return self.change_s
        cur = _quantile([x for _, x in self._recent], self.q)
        self.change_s = cur - self._ref_level
        self.allowance_s = self.skew * (t_arrival - self._t0) + 2.0 * self._ref_spread + self.min_change
        return self.change_s

    @property
    def significant(self) -> bool:
        """The delay moved by more than clock drift and noise explain."""
        return self.change_s is not None and abs(self.change_s) > self.allowance_s

    def state(self) -> dict:
        """For the frame meta / status JSON."""
        r = (lambda x: None if x is None else round(x, 3))
        return {"change_s": r(self.change_s), "allowance_s": r(self.allowance_s), "significant": self.significant,
                "reference": self._ref_level is not None}
