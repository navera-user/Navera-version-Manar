"""Frames not worth matching: taken while the camera turned fast, or blurred (F20).

Wind and turbulence turn a light aircraft's camera at tens of degrees per second for a fraction of a
second. Such a frame is smeared (the rotation during the exposure) and, worse, its attitude (the
straightening, the camera pose) is read from the IMU at a time known to some milliseconds only: a
pointing error of rate x timing error, h x that on the ground. The real-camera screen bench
(2026-10-19/20, 'wind' overlay: the scene shaken 0.5-3 deg at 2-10 Hz) gave 2-7 fixes > 50 m per
run; the frames taken while the scene turned fastest carried most of them.

FrameGate decides before matching:

- **angular rate** at the exposure (the camera IMU's |gyro|, the largest sample within
  +-rate_window_s of the frame time): refused when the smear it makes over the exposure
  (image_quality.gyro_blur_px) exceeds max_blur_px. Without gyro samples near the frame: no opinion.
- **sharpness** (image_quality.sharpness) against this flight's own running baseline (median of the
  last baseline_n frames, at least min_baseline of them): refused below sharp_rel x the baseline.
  Relative, not absolute: haze, terrain and the camera change the absolute value.

Both cost < 5 ms (one small Laplacian, a deque scan). Pure Python / OpenCV, no ROS: the day node
and the bench replay (navera_tools/bench/replay_day_guards.py) use the same code.
"""
import math
from collections import deque
from typing import Optional, Sequence

import numpy as np

from day_pkg import image_quality


class FrameGate:
    """Refuse frames taken at a high angular rate or blurred against the flight's baseline."""

    def __init__(self, max_blur_px: float = 6.0, exposure_s: float = 1.0 / 60.0, rate_window_s: float = 0.02,
                 sharp_rel: float = 0.0, baseline_n: int = 30, min_baseline: int = 10, history_s: float = 5.0):
        self.max_blur_px, self.exposure_s, self.rate_window_s = max_blur_px, exposure_s, rate_window_s
        self.sharp_rel, self.min_baseline = sharp_rel, min_baseline
        self.history_s = history_s
        self._rates = deque()                      # (t, |omega| deg/s)
        self._sharp = deque(maxlen=baseline_n)     # sharpness of recent frames
        self.refused_rate = 0
        self.refused_sharp = 0

    # ── inputs ───────────────────────────────────────────────────────────
    def add_rate(self, t: float, w_dps: Sequence[float]) -> None:
        """One gyro sample at sensor time t: angular velocity (x, y, z) in deg/s."""
        m = math.sqrt(sum(float(x) * float(x) for x in w_dps))
        if not math.isfinite(m):
            return
        self._rates.append((float(t), m))
        while self._rates and self._rates[0][0] < t - self.history_s:
            self._rates.popleft()

    def rate_at(self, t: float) -> Optional[float]:
        """The largest |omega| (deg/s) within +-rate_window_s of t, or None (no samples there)."""
        near = [m for ts, m in self._rates if abs(ts - t) <= self.rate_window_s]
        return max(near) if near else None

    # ── the decision ─────────────────────────────────────────────────────
    def check(self, t: Optional[float], grey: Optional[np.ndarray], focal_px: Optional[float]) -> dict:
        """{'refuse': why or None, 'rate_dps', 'blur_px', 'sharpness', 'sharp_baseline'} for the frame
        taken at t (sensor time; None: no rate check) with image grey (None: no sharpness check) through
        a lens of focal_px (the straightened frame's focal length in pixels)."""
        out = {"refuse": None, "rate_dps": None, "blur_px": None, "sharpness": None, "sharp_baseline": None}
        if t is not None and focal_px and self.max_blur_px > 0:
            r = self.rate_at(t)
            if r is not None:
                b = image_quality.gyro_blur_px(r, self.exposure_s, focal_px)
                out["rate_dps"], out["blur_px"] = round(r, 1), round(b, 1)
                if b > self.max_blur_px:
                    self.refused_rate += 1
                    out["refuse"] = (f"camera turning {r:.0f} deg/s at the exposure ({b:.1f} px smear "
                                     f"> {self.max_blur_px:.1f}): frame not used")
                    return out
        if grey is not None and self.sharp_rel > 0:
            s = image_quality.sharpness(grey)
            base = float(np.median(self._sharp)) if len(self._sharp) >= self.min_baseline else None
            out["sharpness"], out["sharp_baseline"] = round(s, 3), None if base is None else round(base, 3)
            self._sharp.append(s)
            if base is not None and s < self.sharp_rel * base:
                self.refused_sharp += 1
                out["refuse"] = (f"blurred frame (sharpness {s:.2f} < {self.sharp_rel:.2f} x the flight's "
                                 f"{base:.2f}): frame not used")
        return out


def focal_px(width_px: int, hfov_deg: float) -> Optional[float]:
    """Pinhole focal length (px) of a straightened frame width_px wide over hfov_deg."""
    if not width_px or not hfov_deg or not 0.0 < hfov_deg < 180.0:
        return None
    return 0.5 * width_px / math.tan(math.radians(hfov_deg) / 2.0)
