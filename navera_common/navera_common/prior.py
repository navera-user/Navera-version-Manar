"""Last valid GPS position, used as the prior for the vision localizers.

On a vehicle the vision pipelines do not know where they are when GPS drops:
they need the last good GPS fix to centre their search. This tracker keeps it,
from the same /navera/estimate/gps contract the estimator consumes.

A GPS message that LOOKS valid is not necessarily trusted: the arbiter refuses
a spoofed or implausible GPS. While the arbiter's latest decision (NavStatus)
says GPS is not the active source, GPS messages are not taken as the prior —
so vision starts from the last TRUSTED position instead of idling behind a
spoofed "healthy" GPS and re-centring its search on it (found in the mission
simulator: spoofing then gave NO FIX and the drone landed). Without any
recent decision (no arbiter running) every valid GPS message is accepted.
"""
import time
from typing import Optional, Tuple

from navera_common.geo import is_finite_latlon


class GpsPrior:
    """Remembers the last valid, measured GPS position and when it arrived."""

    def __init__(self, timeout_s: float = 2.0):
        self.timeout_s = float(timeout_s)
        self._pos: Optional[Tuple[float, float]] = None
        self._t: Optional[float] = None
        self._arbiter: Optional[Tuple[bool, float]] = None   # (GPS in use, time)
        self.arbiter_timeout_s = 2.0

    def arbiter(self, gps_in_use: bool, now: Optional[float] = None) -> None:
        """Record the arbiter's decision: is GPS the source it is using?"""
        self._arbiter = (bool(gps_in_use), time.monotonic() if now is None else now)

    def refused_by_arbiter(self, now: Optional[float] = None) -> bool:
        if self._arbiter is None:
            return False
        now = time.monotonic() if now is None else now
        return not self._arbiter[0] and now - self._arbiter[1] <= self.arbiter_timeout_s

    def update(self, lat, lon, valid: bool, measured: bool = True,
               now: Optional[float] = None) -> bool:
        """Record a GPS estimate. Returns True if it was accepted as a prior."""
        if not (valid and measured and is_finite_latlon(lat, lon)):
            return False
        if self.refused_by_arbiter(now):
            return False
        self._pos = (float(lat), float(lon))
        self._t = time.monotonic() if now is None else now
        return True

    def fresh(self, now: Optional[float] = None) -> Optional[Tuple[float, float]]:
        """The last position if it is younger than timeout_s (GPS is healthy), else None."""
        if self._pos is None:
            return None
        now = time.monotonic() if now is None else now
        if self.refused_by_arbiter(now):
            return None               # the arbiter stopped using GPS: vision starts now
        return self._pos if now - self._t <= self.timeout_s else None

    def last(self) -> Optional[Tuple[float, float]]:
        """The last valid position, however old (None if GPS never had a fix)."""
        return self._pos
