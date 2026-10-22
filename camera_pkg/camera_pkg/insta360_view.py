"""The day camera of the Insta360 kit: a straight-down pinhole view cut from the One R's 360
dual fisheye (3840x1920, USB Android mode), fixed to the vehicle body.

The view is a VIRTUAL downward camera rigid with the body (image top = the vehicle's nose, image
right = its right, optical axis = body down: navera_common.camera_model.R_BODY_NADIR_CAM), so the
live camera treats it like any fixed downward camera with an ideal lens of `hfov_deg`, no mount
offset, and straightens it with the attitude at the exposure (navera_common.frame_builder).
Every pixel's ray is taken from the lens that sees it furthest from its edge (smallest angle from
its optical axis); the maps are computed once.

Mount: the camera's IMU axes in the body (camera_pkg.insta360_imu.mount_rotation). For day vision
mount the camera LYING, one lens looking straight down: the nadir is then the centre of that lens
(its best resolution, ~9.8 px/deg). A STANDING camera (lenses horizontal) has the nadir on the seam
between the two circles, each lens ~87 deg off axis there (the circle edge): the view is then
mostly the mount and the seam — it is reported (coverage, centre_theta_deg) and warned.

Lens model (shared with the celestial 360 mode, cn_pkg/cn_pkg/sky360.py, and the same file): an
equidistant fisheye r = f (theta + k1 theta^3) around (cx, cy) in the full frame; lens frame from
the camera IMU frame by R_LEFT / R_RIGHT (measured 2026-10-17: +y is the LEFT circle's optical
axis, the right circle looks along -y). Calibrated on the screen dot grid 2026-10-19
(navera_tools/bench/lens_calib_wide.py: rms 0.03 deg at the centre, ~0.2 deg at 60-90 deg).
"""
import json
import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from navera_common.camera_model import R_BODY_NADIR_CAM

FRAME_W, FRAME_H = 3840, 1920
R_LEFT = np.array([[-1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
R_RIGHT = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
F_GUESS = 1040.0 / math.radians(100.0)        # before any calibration (cn_pkg sky360's first guess)
LENS_PATHS = ("/var/lib/navera/insta360_lens.json", os.path.expanduser("~/.navera_sim/insta360_usb_lens.json"))


@dataclass
class Lens:
    name: str
    cx: float
    cy: float
    f: float
    k1: float
    R_lens_imu: np.ndarray
    x_range: Tuple[float, float]               # its half of the frame (the other circle is not it)

    def project(self, v_lens: np.ndarray):
        """Lens-frame rays (..., 3) -> pixel x, y and the angle from the optical axis (rad)."""
        v = v_lens / np.linalg.norm(v_lens, axis=-1, keepdims=True)
        theta = np.arccos(np.clip(v[..., 2], -1.0, 1.0))
        rho = np.hypot(v[..., 0], v[..., 1])
        r = self.f * (theta + self.k1 * theta ** 3)
        with np.errstate(invalid="ignore", divide="ignore"):
            ux = np.where(rho > 1e-12, v[..., 0] / rho, 0.0)
            uy = np.where(rho > 1e-12, v[..., 1] / rho, 0.0)
        return self.cx + r * ux, self.cy + r * uy, theta


def lens_file(path: str = "") -> Optional[str]:
    """The lens calibration in use: path, else NAVERA_INSTA360_LENS, else the box's
    /var/lib/navera/insta360_lens.json, else the bench's ~/.navera_sim file; None if none exists."""
    for p in ([path] if path else []) + [os.environ.get("NAVERA_INSTA360_LENS", "")] + list(LENS_PATHS):
        if p and os.path.isfile(p):
            return p
    return None


def load_lenses(path: str = "") -> Tuple[List[Lens], str]:
    """The two lenses ([left, right]) and where their values come from ("first guess" when no
    calibration file is found: the view is then only roughly straight)."""
    lenses = [Lens("left", 960.0, 960.0, F_GUESS, 0.0, R_LEFT, (0.0, FRAME_W / 2)),
              Lens("right", 2880.0, 960.0, F_GUESS, 0.0, R_RIGHT, (FRAME_W / 2, float(FRAME_W)))]
    p = lens_file(path)
    if p is None:
        return lenses, "first guess (no lens calibration file)"
    with open(p) as fh:
        d = json.load(fh)
    for lens in lenses:
        m = d.get(lens.name)
        if isinstance(m, dict):
            lens.f, lens.k1 = float(m.get("f", lens.f)), float(m.get("k1", 0.0))
            lens.cx, lens.cy = float(m.get("cx", lens.cx)), float(m.get("cy", lens.cy))
    return lenses, p


class NadirView:
    """The body-fixed downward pinhole view (width x height, hfov_deg wide) of a full 360 frame."""

    def __init__(self, lenses: List[Lens], R_body_cam: np.ndarray, hfov_deg: float = 100.0,
                 width: int = 1200, height: int = 900, max_theta_deg: float = 88.0):
        if not 10.0 <= hfov_deg <= 150.0:
            raise ValueError(f"view hfov {hfov_deg} deg: expected 10-150")
        self.hfov_deg, self.width, self.height = float(hfov_deg), int(width), int(height)
        self.f = (self.width / 2.0) / math.tan(math.radians(self.hfov_deg) / 2.0)
        jj, ii = np.meshgrid(np.arange(self.width), np.arange(self.height))
        rays_cam = np.stack([(jj - (self.width - 1) / 2.0) / self.f, (ii - (self.height - 1) / 2.0) / self.f,
                             np.ones((self.height, self.width))], axis=-1)
        # virtual camera -> body -> camera IMU frame (row vectors: v @ M.T = M @ v)
        rays_imu = rays_cam @ R_BODY_NADIR_CAM.T @ np.asarray(R_body_cam, float)
        best = np.full((self.height, self.width), np.inf)
        mx = np.full((self.height, self.width), -1.0, np.float32)
        my = np.full((self.height, self.width), -1.0, np.float32)
        which = np.full((self.height, self.width), -1, np.int8)
        lim = math.radians(max_theta_deg)
        for k, lens in enumerate(lenses):
            x, y, th = lens.project(rays_imu @ lens.R_lens_imu.T)
            ok = (th < lim) & (th < best) & (x >= lens.x_range[0]) & (x < lens.x_range[1] - 1) & \
                 (y >= 0) & (y < FRAME_H - 1)
            mx[ok], my[ok], best[ok], which[ok] = x[ok], y[ok], th[ok], k
        self.mx, self.my = mx, my
        self.coverage = float((which >= 0).mean())
        self.lens_share = {lens.name: round(float((which == k).mean()), 3) for k, lens in enumerate(lenses)}
        c = (self.height // 2, self.width // 2)
        self.centre_lens = lenses[which[c]].name if which[c] >= 0 else None
        self.centre_theta_deg = round(math.degrees(best[c]), 1) if math.isfinite(best[c]) else None

    def warning(self) -> Optional[str]:
        """Why this view is poor for day vision, or None."""
        if self.coverage < 0.9:
            return (f"only {self.coverage:.0%} of the downward view is seen by a lens: mount the camera "
                    f"LYING with one lens looking down (NAVERA_INSTA360_MOUNT_AXES)")
        if self.centre_theta_deg is None:
            return "straight down is seen by no lens (on the seam): mount one lens looking down"
        if self.centre_theta_deg > 45.0:
            return (f"straight down is {self.centre_theta_deg:.0f} deg off the {self.centre_lens} lens' axis "
                    f"(low resolution, near the seam): mount one lens looking down")
        return None

    def apply(self, frame: np.ndarray) -> np.ndarray:
        import cv2
        if frame.shape[1] != FRAME_W or frame.shape[0] != FRAME_H:
            raise ValueError(f"360 frame {frame.shape[1]}x{frame.shape[0]}: expected {FRAME_W}x{FRAME_H} "
                             "(the full-resolution live stream)")
        return cv2.remap(frame, self.mx, self.my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
