"""IMU heading at a frame's exposure (D20), pure Python (no ROS).

The night pipeline turns each thermal frame north-up with the heading. frame_meta carries the
attitude at the exposure when the camera chain has it (FrameBuilder); without it the node used
the LATEST IMU heading, read when the frame is processed — 0.1-1 s after the exposure, i.e.
several degrees off in a turn (STHN does not absorb more than ~5-10 deg). The IMU samples are
kept with their own stamps and the heading is interpolated at the exposure stamp.
"""
from collections import deque
from typing import Optional, Tuple


def _wrap180(d: float) -> float:
    return (d + 180.0) % 360.0 - 180.0


class HeadingHistory:
    """The last `keep_s` seconds of IMU headings (deg clockwise from north) on the sensor clock."""

    def __init__(self, keep_s: float = 5.0, max_gap_s: float = 0.25):
        """max_gap_s: an exposure farther than this from every sample is not answered from the
        history (outside it, or in a hole between two samples).
        """
        self.keep_s = float(keep_s)
        self.max_gap_s = float(max_gap_s)
        self._s = deque()                       # (stamp_s, heading_deg), increasing stamps

    def add(self, stamp_s: float, heading_deg: float) -> None:
        stamp_s = float(stamp_s)
        if self._s and stamp_s <= self._s[-1][0]:
            if stamp_s < self._s[-1][0] - self.keep_s:   # the clock went back (replay rewind)
                self._s.clear()
            else:
                return                                   # out of order / duplicate: ignored
        self._s.append((stamp_s, float(heading_deg) % 360.0))
        while self._s and self._s[0][0] < stamp_s - self.keep_s:
            self._s.popleft()

    def at(self, stamp_s: float) -> Optional[Tuple[float, float]]:
        """(heading_deg at stamp_s, distance in s to the nearest sample), or None."""
        if not self._s or stamp_s is None:
            return None
        t = float(stamp_s)
        s = self._s
        if t <= s[0][0]:
            gap = s[0][0] - t
            return (s[0][1], gap) if gap <= self.max_gap_s else None
        if t >= s[-1][0]:
            gap = t - s[-1][0]
            return (s[-1][1], gap) if gap <= self.max_gap_s else None
        lo, hi = 0, len(s) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if s[mid][0] <= t:
                lo = mid
            else:
                hi = mid
        (t0, h0), (t1, h1) = s[lo], s[hi]
        gap = min(t - t0, t1 - t)
        if gap > self.max_gap_s:
            return None
        w = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
        return ((h0 + w * _wrap180(h1 - h0)) % 360.0, gap)
