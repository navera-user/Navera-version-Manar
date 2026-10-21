"""Sensor health helpers shared by the NAVERA drivers."""
import hashlib
import time
from typing import Hashable, Optional

import numpy as np


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


class FrozenFrameDetector:
    """Detects a camera that delivers the same picture again (problems log D24, hazard H-01b).

    A stuck driver, a USB hiccup or a stalled RTSP stream keeps handing over the last
    picture while the vehicle moves on; matched again, it is an old position stated as
    fresh. Any one of three signs marks a frame frozen:

    * its timestamp does not advance past the previous frame's (the same frame delivered
      again by a ROS camera topic or a replaying driver);
    * its content is bit-identical to the previous frame's (a real sensor adds noise to
      every exposure: two exposures are never equal);
    * its content is nearly identical (mean absolute difference of a sub-sampled grey
      copy below ``still_diff`` grey levels) while the vehicle is known to have moved
      (IMU attitude change or GPS displacement between the two exposures).

    The first frame that differs ends the freeze (the camera recovered).
    """

    def __init__(self, still_diff: float = 0.5, step: int = 4):
        self.still_diff = float(still_diff)
        self.step = max(1, int(step))
        self._digest: Optional[bytes] = None
        self._small: Optional[np.ndarray] = None
        self._stamp: Optional[float] = None
        self.frozen_since: Optional[float] = None   # stamp of the first frozen frame of the streak
        self.repeats = 0                             # frozen frames in a row
        self.reason: Optional[str] = None

    def _small_grey(self, frame: np.ndarray) -> np.ndarray:
        small = frame[::self.step, ::self.step]
        if small.ndim == 3:
            small = small.mean(axis=2)
        return small.astype(np.float32)

    def update(self, frame: np.ndarray, stamp_s: float, moving: Optional[bool] = None) -> Optional[str]:
        """Feed one frame (its exposure time, and whether the vehicle moved since the last one:
        True / False / None = unknown). Returns why it is frozen, or None for a fresh frame.
        """
        digest = hashlib.blake2b(np.ascontiguousarray(frame).tobytes(), digest_size=16).digest()
        small = self._small_grey(frame)
        reason = None
        if self._stamp is not None and stamp_s <= self._stamp:
            reason = (f"frame time did not advance ({stamp_s - self._stamp:+.3f} s): "
                      "the same frame delivered again")
        elif self._digest is not None and digest == self._digest:
            reason = "picture identical to the previous one (camera driver or stream stuck)"
        elif moving and self._small is not None and self._small.shape == small.shape:
            diff = float(np.abs(small - self._small).mean())
            if diff < self.still_diff:
                reason = (f"picture unchanged ({diff:.2f} grey levels) while the vehicle moved "
                          "(camera driver or stream stuck)")
        # the last stamp, not the largest: after a wall-clock step back the next frames advance again
        self._digest, self._small, self._stamp = digest, small, stamp_s
        if reason is None:
            self.frozen_since, self.repeats, self.reason = None, 0, None
        else:
            if self.frozen_since is None:
                self.frozen_since = stamp_s
            self.repeats += 1
            self.reason = reason
        return reason

    @property
    def frozen(self) -> bool:
        """True while the last frame fed was frozen."""
        return self.reason is not None

    def reset(self) -> None:
        """Forget the previous frame (camera reopened)."""
        self.__init__(self.still_diff, self.step)
