"""Image quality of a day frame before it is matched: blur, and what sits on the lens.

A camera on an aircraft is never still: rotor/engine vibration faster than the exposure blurs the frame
symmetrically, turbulence turns it during the exposure, and water drops or a low sun's flare stay at the
same place in the image while the ground moves under them. (Rain streaks take most of the matcher's
feature budget instead: see LocalMatcher's retry_features.) These helpers measure that:

- sharpness(): high-frequency energy relative to the frame's contrast (haze lowers both, so it does
  not read as blur); low = blurred. Real camera on the screen bench (2026-10-20): clear frames ~0.75,
  every vibration frame the matcher refused < 0.53, accepted ones >= 0.54.
- gyro_blur_px(): the blur a measured angular rate makes during the exposure (camera IMU at the
  exposure time): the frames the rate says are smeared can be skipped without looking at them.
- LensMask: pixels that do not change between frames while the scene does (drops, flare ghosts, dirt)
  and large saturated areas (the sun's glow), as a SIFT mask. Off while the scene itself does not move
  (hover). NOT validated: on the screen bench most of the view is the static room (off by default).

Pure OpenCV/NumPy, no ROS: the day node and the bench use the same code.
"""
import math
from typing import Optional

import cv2
import numpy as np


def sharpness(grey: np.ndarray, width: int = 480) -> float:
    """Mean |Laplacian| / (std + 1) on the frame scaled to `width` px: ~0.3-0.6 for a sharp aerial frame,
    lower when blurred (the ratio removes the contrast, so haze or dusk alone do not look blurred)."""
    g = grey if grey.ndim == 2 else cv2.cvtColor(grey, cv2.COLOR_BGR2GRAY)
    if g.shape[1] > width:
        g = cv2.resize(g, (width, int(round(g.shape[0] * width / g.shape[1]))), interpolation=cv2.INTER_AREA)
    g = g.astype(np.float32)
    lap = cv2.Laplacian(g, cv2.CV_32F, ksize=3)
    return float(np.mean(np.abs(lap)) / (float(g.std()) + 1.0))


def gyro_blur_px(rate_dps: float, exposure_s: float, focal_px: float) -> float:
    """Image smear (px) of a rotation at rate_dps during the exposure, for a lens of focal_px."""
    return math.radians(abs(rate_dps)) * exposure_s * focal_px


class LensMask:
    """What stays fixed in the frame while the ground moves under it: drops and flare ghosts on the lens,
    plus saturated glow. update() with each frame (any size: worked at `size`); mask() is the SIFT mask
    (255 = use) for a frame of the given shape, None when nothing is masked."""

    def __init__(self, size=(160, 120), alpha: float = 0.35, rel: float = 0.3, sat: int = 250,
                 sat_grow_px: int = 25, min_fixed: float = 0.02, max_fixed: float = 0.6):
        self.size, self.alpha, self.rel, self.sat, self.grow = size, alpha, rel, sat, sat_grow_px
        self.min_fixed, self.max_fixed = min_fixed, max_fixed
        self.prev: Optional[np.ndarray] = None
        self.change: Optional[np.ndarray] = None       # running mean of |frame - previous frame|
        self.n = 0
        self.fixed_share = 0.0
        self._last: Optional[np.ndarray] = None

    def update(self, frame: np.ndarray) -> None:
        g = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(g, self.size, interpolation=cv2.INTER_AREA).astype(np.float32)
        self._last = g
        if self.prev is not None:
            d = cv2.GaussianBlur(np.abs(small - self.prev), (0, 0), 1.5)
            self.change = d if self.change is None else (1 - self.alpha) * self.change + self.alpha * d
            self.n += 1
        self.prev = small

    def mask(self, shape) -> Optional[np.ndarray]:
        h, w = shape[:2]
        m = np.full((h, w), 255, np.uint8)
        used = False
        if self.change is not None and self.n >= 3:
            med = float(np.median(self.change))
            if med > 2.0:                               # the scene moves: what does not is on the lens
                fixed = (self.change < self.rel * med).astype(np.uint8)
                share = float(fixed.mean())
                self.fixed_share = share
                if self.min_fixed <= share <= self.max_fixed:
                    fixed = cv2.dilate(fixed, np.ones((3, 3), np.uint8))
                    m[cv2.resize(fixed, (w, h), interpolation=cv2.INTER_NEAREST) > 0] = 0
                    used = True
        if self._last is not None:
            g = self._last if self._last.shape[:2] == (h, w) else cv2.resize(self._last, (w, h))
            # glow: large saturated areas only (a white roof or a car is a few saturated pixels, not a sun)
            hot = cv2.morphologyEx((g >= self.sat).astype(np.uint8), cv2.MORPH_OPEN,
                                   cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
            if hot.mean() > 0.002:
                hot = cv2.dilate(hot, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * self.grow + 1,) * 2))
                m[hot > 0] = 0
                used = True
        return m if used else None
