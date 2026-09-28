"""Last valid GPS position, used as the prior for the vision localizers.

On a vehicle the vision pipelines do not know where they are when GPS drops:
they need the last good GPS fix to centre their search. This tracker keeps it,
from the same /navera/estimate/gps contract the estimator consumes.
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

    def update(self, lat, lon, valid: bool, measured: bool = True,
               now: Optional[float] = None) -> bool:
        """Record a GPS estimate. Returns True if it was accepted as a prior."""
        if not (valid and measured and is_finite_latlon(lat, lon)):
            return False
        self._pos = (float(lat), float(lon))
        self._t = time.monotonic() if now is None else now
        return True

    def fresh(self, now: Optional[float] = None) -> Optional[Tuple[float, float]]:
        """The last position if it is younger than timeout_s (GPS is healthy), else None."""
        if self._pos is None:
            return None
        now = time.monotonic() if now is None else now
        return self._pos if now - self._t <= self.timeout_s else None

    def last(self) -> Optional[Tuple[float, float]]:
        """The last valid position, however old (None if GPS never had a fix)."""
        return self._pos
