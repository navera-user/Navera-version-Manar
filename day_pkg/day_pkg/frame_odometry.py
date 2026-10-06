"""Visual odometry between consecutive frames: how far the camera moved, from the image alone.

Two frames a second or two apart overlap widely; the shift of the ground between them is
the vehicle's displacement. Measured by phase correlation (OpenCV, CPU, a few ms) on the
straightened frames: the previous frame is first turned by the heading change (IMU), so
only a translation remains; the shift in pixels times the ground size of a pixel (from the
height) is metres, turned to east/north by the heading. It keeps the velocity measured
through gaps in map matching (textured ground the map no longer resembles, fields, turns);
it cannot work over open water (nothing fixed to follow) — the response then stays low and
the result is not used.
"""
import math
from typing import Optional, Tuple

import cv2
import numpy as np


class FrameOdometry:
    def __init__(self, scale: float = 0.5, min_response: float = 0.08, max_dt_s: float = 5.0):
        self.scale, self.min_response, self.max_dt = scale, min_response, max_dt_s
        self._prev = None             # (grey image, heading deg, m per px, t)
        self._win = None

    def reset(self) -> None:
        self._prev = None

    def step(self, frame: np.ndarray, heading_deg: Optional[float], m_per_px: float,
             t: float) -> Optional[Tuple[float, float, float, float]]:
        """(east m, north m, dt s, quality 0-1) moved since the previous frame, or None."""
        g = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        g = cv2.resize(g, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA).astype(np.float32)
        hdg = 0.0 if heading_deg is None else float(heading_deg)
        prev, self._prev = self._prev, (g, hdg, m_per_px, t)
        if prev is None or not (0.0 < t - prev[3] <= self.max_dt) or prev[0].shape != g.shape:
            return None
        pg, phdg, pmpp, pt = prev
        h, w = g.shape
        # the previous frame turned into this one's orientation and scale (heading change, height change)
        dturn = (hdg - phdg + 180.0) % 360.0 - 180.0
        R = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), dturn, pmpp / m_per_px)
        pg = cv2.warpAffine(pg, R, (w, h), flags=cv2.INTER_LINEAR)
        mask = cv2.warpAffine(np.ones_like(g), R, (w, h), flags=cv2.INTER_NEAREST)
        if self._win is None or self._win.shape != g.shape:
            self._win = cv2.createHanningWindow((w, h), cv2.CV_32F)
        a = (pg - pg[mask > 0].mean()) * mask
        b = (g - g[mask > 0].mean()) * mask
        (dx, dy), resp = cv2.phaseCorrelate(a, b, self._win)
        if resp < self.min_response or abs(dx) > w / 3 or abs(dy) > h / 3:
            return None
        mpp = m_per_px / self.scale
        right, fwd = -dx * mpp, dy * mpp                  # the ground moved the other way
        th = math.radians(hdg)
        de = fwd * math.sin(th) + right * math.cos(th)
        dn = fwd * math.cos(th) - right * math.sin(th)
        return de, dn, t - pt, float(min(1.0, resp / 0.3))
