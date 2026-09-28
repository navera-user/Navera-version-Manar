"""Sensor health helpers shared by the NAVERA drivers."""
import time
from typing import Hashable, Optional


class FrozenSampleDetector:
    """Detects a sensor that keeps returning the exact same sample.

    Drivers that poll a library cache (e.g. the Adafruit BNO08x driver returns
    the last report it parsed) keep "reading" successfully after the sensor
    itself has stopped reporting. Real measurements always carry noise, so a
    sample repeated bit-for-bit for `max_repeats` consecutive reads means the
    data is frozen.
    """

    def __init__(self, max_repeats: int):
        self.max_repeats = int(max_repeats)
        self._last: Optional[Hashable] = None
        self._repeats = 0

    def update(self, sample: Hashable) -> bool:
        """Feed one sample. Returns True when the data is considered frozen."""
        if sample == self._last:
            self._repeats += 1
        else:
            self._last = sample
            self._repeats = 0
        return self._repeats >= self.max_repeats

    def reset(self) -> None:
        self._last = None
        self._repeats = 0


class RetryTimer:
    """Rate-limits reconnection attempts (monotonic clock)."""

    def __init__(self, period_s: float):
        self.period_s = float(period_s)
        self._next = 0.0

    def ready(self, now: Optional[float] = None) -> bool:
        """True at most once per period."""
        now = time.monotonic() if now is None else now
        if now >= self._next:
            self._next = now + self.period_s
            return True
        return False
