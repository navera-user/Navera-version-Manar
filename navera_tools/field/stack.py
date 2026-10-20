"""Stop-frame stacking for the 360 star solve: the camera's live video keeps few faint stars (a short video
exposure, H.264), but while the car is stopped the sky stands still in the frame (the stars drift 0.04 px/s), so
the key frames of the last seconds can be averaged: the noise drops as 1/sqrt(N), the stars stay.

Only key frames are kept (2/s): the live driver decodes them anyway, and they are the stream's best-quality
pictures; decoding every frame of the 3840x1920 stream runs at 11 fps on one Jetson core (20 fps on two),
too slow for the 4 s cadence of the stopped solves (measured 2026-10-20).

The average drops each pixel's brightest sample (a plane, a satellite or a bird crosses a pixel in one frame),
then the difference to the background is amplified by sqrt(N) (at most MAX_GAIN), so the detector's noise floor
(allsky.NOISE_FLOOR, 1 DN) and the 8-bit rounding do not eat the gain; a pixel saturated in the mean stays as it
was, so a bright lamp is not made a 'saturated' blob it was not.
"""
import collections
import math
import threading
from typing import List, Optional, Tuple

import numpy as np

MAX_GAIN = 4.0
SATURATED = 250.0


class StackRing:
    """The last key frames (camera ms of the exposure, grey uint8), kept for stacking."""

    def __init__(self, size: int):
        self.size = int(size)
        self._d = collections.deque(maxlen=self.size)
        self._lock = threading.Lock()

    def keep(self, ms, grey: np.ndarray):
        if ms is None:
            return
        with self._lock:
            if self._d and ms <= self._d[-1][0]:
                return                                   # the same frame again (or out of order)
            self._d.append((ms, grey))

    def window(self, t0_ms: float, t1_ms: float) -> List[Tuple[float, np.ndarray]]:
        with self._lock:
            return [(ms, g) for ms, g in self._d if t0_ms - 1 <= ms <= t1_ms + 1]

    def __len__(self):
        return len(self._d)


def ring_size(seconds: float, key_fps: float = 2.0) -> int:
    """Key frames needed for a window of `seconds` (0: no ring)."""
    return 0 if seconds <= 0 else int(math.ceil(seconds * key_fps)) + 1


def stack_frames(frames: List[np.ndarray], reject_brightest: Optional[bool] = None,
                 max_gain: float = MAX_GAIN) -> np.ndarray:
    """Average of grey frames (float32, same scale as one frame), brightest sample per pixel dropped from 4
    frames on, faint signal amplified by min(sqrt(N), max_gain) about the background."""
    import cv2
    n = len(frames)
    if n == 0:
        raise ValueError("no frame to stack")
    if n == 1:
        return frames[0].astype(np.float32)
    reject = n >= 4 if reject_brightest is None else reject_brightest
    acc = np.zeros(frames[0].shape, np.float32)
    top = np.zeros(frames[0].shape, np.float32) if reject else None
    for f in frames:
        f32 = f.astype(np.float32)
        acc += f32
        if reject:
            np.maximum(top, f32, out=top)
    mean = (acc - top) / (n - 1) if reject else acc / n
    m = n - 1 if reject else n
    gain = min(math.sqrt(m), max_gain)
    bg = cv2.blur(mean, (65, 65))                        # the sky's own level (glow, moon) stays where it was
    out = bg + gain * (mean - bg)
    sat = mean >= SATURATED
    out = np.where(sat, mean, np.minimum(out, SATURATED - 1.0))
    return np.clip(out, 0.0, None).astype(np.float32)


def window_is_still(stopped_at, t0_ms: float, t1_ms: float, step_ms: float = 2000.0) -> bool:
    """stopped_at(ms) -> {'stopped': bool} judges [ms - 2 s, ms + 0.5 s]: True when every check over the window says
    stopped (the window's end, then every step_ms back until its start is covered)."""
    m = t1_ms
    while True:
        if not stopped_at(m).get("stopped"):
            return False
        if m - step_ms <= t0_ms:
            return True
        m -= step_ms
