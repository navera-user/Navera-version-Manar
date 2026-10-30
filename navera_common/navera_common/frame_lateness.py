"""A camera frame that arrives later than the camera's usual delay (jitter), and what to do with it.

A frame is dated arrival - the learned camera delay (live_camera's capture_latency_s, the day
node's latency_cal correction). A frame held 0.5-2.2 s longer than usual in a queue (USB, a
GStreamer jitter buffer, a starved grab thread, an IP camera's network) is then dated that much
too late, and at 60 m/s its fix lands 30-130 m along the track (Isaac Sim plane60 2026-10-30:
100-160 m spikes). Two ways to see it, per frame, at the grab:

* the camera's own stamp (V4L2 buffer time, GStreamer PTS, an RTP stamp): d = arrival - source
  stamp; its low quantile over the recent frames is the usual queueing, d above it is how late
  this frame is. The source stamp is the true time base, so the frame is re-dated: its stamp moves
  back by that much ("camera_stamp"; nothing uncertain is left).
* without one, the frame interval: the arrivals' gap minus the usual frame period is how late the
  frame can be (a dropped frame gives the same gap and is on time: an upper bound, "interval").
  The bound is carried: frames queued behind a stall then arrive in a burst (gaps shorter than
  the period), each later in exposure by a period, so each is less late by period - gap; a
  frame k is at most U_k = max(0, U_k-1 + gap - period) late. settle_n frames in a row at the
  usual period end it (a camera that dropped the stale frames, or a lasting delay change, which
  delay_monitor / latency_cal handle).
  It cannot be re-dated; the localizer states it instead (fix sigma widened by speed x lateness,
  or no fix when speed x lateness is beyond its gate: lateness_sigma).

Lateness at most late_s (default 0.3 s) changes nothing: frames on time behave as before. Once a
frame is beyond it, the frames after it are handled the same way until one is late by at most
release_s (default 0.05 s): the tail of a burst (0.05-0.3 s late, 3-18 m at 60 m/s) is not
taken as on time.
"""
import math
from collections import deque
from typing import Optional, Tuple

MAX_REDATE_S = 1.5   # a frame later than this is never re-dated (attitude history, review M5)

DEFAULT_LATE_S = 0.3
DEFAULT_GATE_M = 60.0


def _quantile(xs, q):
    s = sorted(xs)
    if not s:
        return None
    k = (len(s) - 1) * q
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


class FrameLateness:
    """Per grabbed frame: how late it is beyond the camera's usual delay."""

    def __init__(self, late_s: float = DEFAULT_LATE_S, window: int = 60, q: float = 0.2, min_n: int = 8,
                 jump_s: float = 5.0, settle_n: int = 10, release_s: float = 0.05):
        self.late_s, self.window, self.q, self.min_n, self.jump = (float(late_s), int(window), float(q),
                                                                   int(min_n), float(jump_s))
        self._d: deque = deque(maxlen=self.window)       # arrival - source stamp
        self._gaps: deque = deque(maxlen=self.window)    # arrival intervals
        self._prev_arrival: Optional[float] = None
        self.settle_n, self.release_s = int(settle_n), float(release_s)
        self._episode = False                            # a frame was beyond late_s, none at release_s since
        self._bound = 0.0                                # interval mode: carried lateness bound (s)
        self._regular = 0                                # frames in a row at the usual period

    def observe(self, t_arrival: float, t_source: Optional[float] = None) -> Tuple[float, float, str]:
        """One grabbed frame (arrival on any steady clock; source stamp on the camera's clock, or None).

        Returns (shift_s, uncertain_s, basis): shift_s to move the frame's stamp back by (the
        camera's stamp says it is that late), uncertain_s the lateness that could not be dated
        (frame interval only), basis "camera_stamp" / "interval" / "" (on time or no history).
        Both are 0.0 while the frame is at most late_s late.
        """
        if not math.isfinite(t_arrival):
            return 0.0, 0.0, ""
        gap = None if self._prev_arrival is None else t_arrival - self._prev_arrival
        self._prev_arrival = t_arrival
        if t_source is not None and math.isfinite(t_source):
            d = t_arrival - t_source
            if self._d and abs(d - self._d[-1]) > self.jump:
                self._d.clear()                          # the source clock was reset / re-based
            base = _quantile(self._d, self.q) if len(self._d) >= self.min_n else None
            self._d.append(d)
            if base is None:
                return 0.0, 0.0, ""
            late = d - base
            if not self._late(late):
                return 0.0, 0.0, ""
            if late > MAX_REDATE_S:              # too far back for the attitude history: not re-dated,
                return 0.0, late, "camera_stamp"   # the day node widens or refuses it (review M5)
            return late, 0.0, "camera_stamp"
        if gap is None or gap < 0.0:
            return 0.0, 0.0, ""
        period = _quantile(self._gaps, 0.5) if len(self._gaps) >= self.min_n else None
        if period is None:
            self._gaps.append(gap)
            return 0.0, 0.0, ""
        if abs(gap - period) <= 0.25 * period:
            self._gaps.append(gap)                       # the period is learned from regular gaps only
            self._regular += 1
        else:
            self._regular = 0
        self._bound = max(0.0, self._bound + gap - period)
        if self._regular >= self.settle_n:
            self._bound = 0.0
        late = self._bound
        return (0.0, late, "interval") if self._late(late) else (0.0, 0.0, "")

    def _late(self, late: float) -> bool:
        """Beyond late_s, or still beyond release_s since a frame was (hysteresis)."""
        self._episode = late > self.late_s or (self._episode and late > self.release_s)
        return self._episode


def meta_fields(shift_s: float, uncertain_s: float, basis: str) -> dict:
    """What live_camera adds to the frame meta (nothing for a frame on time)."""
    if not basis:
        return {}
    return {"late_s": round(shift_s or uncertain_s, 3), "late_basis": basis, "late_redated": shift_s > 0.0}


def lateness_sigma(meta: dict, speed_mps: float, sigma_m: float, gate_m: float = DEFAULT_GATE_M,
                   min_late_s: float = 0.0) -> Tuple[float, Optional[str]]:
    """A fix's stated sigma with the frame's undated lateness, or a reason for no fix.

    The camera decides which frames are late (FrameLateness: late_s and its hysteresis); a frame
    re-dated from the camera's stamp (late_redated), without late_s, or at most min_late_s: unchanged.
    Otherwise the position is up to speed x lateness off along the track: sigma widened by it in
    quadrature, or (sigma, reason) when speed x lateness is beyond gate_m (no fix from it).
    """
    if not isinstance(meta, dict) or meta.get("late_redated"):
        return sigma_m, None
    try:
        late = float(meta.get("late_s") or 0.0)
    except (TypeError, ValueError):
        return sigma_m, None
    if not math.isfinite(late) or late <= max(0.0, float(min_late_s)):
        return sigma_m, None
    along = max(0.0, float(speed_mps)) * late
    if along > gate_m:
        return sigma_m, (f"frame {late:.2f} s late ({meta.get('late_basis', '?')}): up to {along:.0f} m along "
                         f"the track at {speed_mps:.0f} m/s, beyond the {gate_m:.0f} m gate")
    return math.hypot(sigma_m, along), None
