"""Celestial position from the Insta360's full 360 frame and its own gravity, at any camera attitude.

The camera can stand: each lens sees the sky above it. For each lens a flat (pinhole) window of
sky is cut out of its fisheye circle, tilted from the zenith towards that lens, and plate-solved.
The plate solution gives the window's orientation among the stars; the camera's accelerometer
gives where 'up' is in the same window. Putting the zenith through the solution gives the
sky point straight overhead: its declination is the latitude, its right ascension minus the
sidereal time the longitude. No compass and no heading are needed, and the zenith does not
have to be inside the window (simulated: 5-8 km with the zenith 35-60 degrees outside).

Frames: IMU (the camera's accelerometer axes; at rest it reads +1 g along the axis pointing
up), lens (x image right, y image down, z optical axis). Measured on the user's One R
(2026-10-17, 6 static positions): +y is the LEFT circle's optical axis, the RIGHT circle looks
along -y, +x is up when the camera stands, +z is image-down in both circles.

The lens model (centre, focal length, radial term, lens-to-IMU rotation) is a first guess
until stars calibrate it: every frame is saved so it can be solved again with a better model.

Shared by the flight node (cn_pkg cn_subscriber, 360 mode) and the field tools
(navera_tools.field.sky360 is this very module).
"""
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from cn_pkg.nodes.celestial_math import apparent_radec, gast_deg

ASTROMETRY_CFG = os.environ.get("NAVERA_ASTROMETRY_CFG") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "nodes", "astrometry.cfg")


@dataclass
class Lens:
    """Equidistant fisheye r = f (theta + k1 theta^3), centre (cx, cy) in the full frame."""
    name: str
    cx: float
    cy: float
    f: float
    R_lens_imu: np.ndarray                      # lens-frame vector = R_lens_imu @ IMU-frame vector
    k1: float = 0.0
    radius: float = 1040.0                      # image circle radius (px)

    def project(self, v_lens: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Lens-frame rays (N,3) → pixel x, y and the angle from the optical axis."""
        v = v_lens / np.linalg.norm(v_lens, axis=-1, keepdims=True)
        theta = np.arccos(np.clip(v[..., 2], -1.0, 1.0))
        rho = np.hypot(v[..., 0], v[..., 1])
        r = self.f * (theta + self.k1 * theta ** 3)
        with np.errstate(invalid="ignore", divide="ignore"):
            ux = np.where(rho > 1e-12, v[..., 0] / rho, 0.0)
            uy = np.where(rho > 1e-12, v[..., 1] / rho, 0.0)
        return self.cx + r * ux, self.cy + r * uy, theta


# lens frame from the IMU frame (rows = lens x, y, z expressed in IMU axes)
R_LEFT = np.array([[-1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
R_RIGHT = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
F_GUESS = 1040.0 / math.radians(100.0)         # circle edge taken as 100 degrees off axis (not yet measured)


LENS_FILE = os.environ.get("NAVERA_INSTA360_LENS", os.path.expanduser("~/.navera_sim/insta360_usb_lens.json"))


def default_lenses() -> List[Lens]:
    """The two lenses: measured values (bench/lens_calib_screen.py) where there are some, else the first guess."""
    lenses = [Lens("left", 938.5, 969.5, F_GUESS, R_LEFT), Lens("right", 2906.7, 966.2, F_GUESS, R_RIGHT)]
    try:
        import json
        with open(LENS_FILE) as fh:
            measured = json.load(fh)
    except (OSError, ValueError):
        return lenses
    for lens in lenses:
        m = measured.get(lens.name)
        if isinstance(m, dict):
            lens.f, lens.k1 = float(m.get("f", lens.f)), float(m.get("k1", 0.0))
            lens.cx = float(m.get("cx", lens.cx))
            lens.cy = float(m.get("cy", lens.cy))
    return lenses


@dataclass
class Window:
    """A pinhole view cut from a lens: pixel (u, v) ↔ ray R_win_imu.T @ ((u-c)/f, (v-c)/f, 1)."""
    lens: Lens
    R_win_imu: np.ndarray
    size: int
    hfov_deg: float
    image: Optional[np.ndarray] = field(default=None, repr=False)

    @property
    def f(self) -> float:
        return (self.size / 2.0) / math.tan(math.radians(self.hfov_deg) / 2.0)

    def pixel_of(self, v_imu: np.ndarray) -> Optional[Tuple[float, float]]:
        w = self.R_win_imu @ v_imu
        if w[2] <= 1e-6:
            return None
        c = (self.size - 1) / 2.0
        return c + self.f * w[0] / w[2], c + self.f * w[1] / w[2]


class PinholeView:
    """A fixed straight view cut from one lens (maps computed once): looks along fwd_imu, image-up towards
    up_hint_imu. apply(frame) → width x height image; R_view_imu maps IMU vectors into the view frame."""

    def __init__(self, lens: Lens, fwd_imu, up_hint_imu, hfov_deg: float, width: int, height: int):
        fwd = np.asarray(fwd_imu, float) / np.linalg.norm(fwd_imu)
        up = np.asarray(up_hint_imu, float)
        down = -(up - (up @ fwd) * fwd)
        if np.linalg.norm(down) < 1e-6:
            raise ValueError("the up hint is along the view direction")
        down /= np.linalg.norm(down)
        right = np.cross(down, fwd)
        self.R_view_imu = np.stack([right, down, fwd])
        self.lens, self.hfov_deg, self.width, self.height = lens, hfov_deg, width, height
        self.f = (width / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
        jj, ii = np.meshgrid(np.arange(width), np.arange(height))
        rays = np.stack([(jj - (width - 1) / 2.0) / self.f, (ii - (height - 1) / 2.0) / self.f,
                         np.ones((height, width))], axis=-1) @ self.R_view_imu
        x, y, _ = lens.project(rays @ lens.R_lens_imu.T)
        bad = np.hypot(x - lens.cx, y - lens.cy) > lens.radius
        self.mx = np.where(bad, -1, x).astype(np.float32)
        self.my = np.where(bad, -1, y).astype(np.float32)

    def apply(self, frame: np.ndarray) -> np.ndarray:
        import cv2
        return cv2.remap(frame, self.mx, self.my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def sky_window(frame: np.ndarray, lens: Lens, up_imu: np.ndarray, tilt_deg: float = 30.0,
               hfov_deg: float = 50.0, size: int = 640) -> Window:
    """The window centred tilt_deg from the zenith towards the lens axis, image-up towards the zenith."""
    import cv2
    up = up_imu / np.linalg.norm(up_imu)
    axis = lens.R_lens_imu[2]                                     # optical axis in IMU frame
    horiz = axis - (axis @ up) * up                               # the lens axis's horizontal part
    if np.linalg.norm(horiz) < 1e-6:                              # lens looking straight up or down
        horiz = np.cross(up, lens.R_lens_imu[0])
    horiz /= np.linalg.norm(horiz)
    t = math.radians(tilt_deg)
    fwd = math.cos(t) * up + math.sin(t) * horiz
    img_down = np.cross(fwd, np.cross(up, fwd))                   # image-up = towards the zenith
    img_down = -img_down / np.linalg.norm(img_down)
    img_right = np.cross(img_down, fwd)
    R = np.stack([img_right, img_down, fwd])                      # window-frame from IMU frame
    win = Window(lens, R, size, hfov_deg)
    c = (size - 1) / 2.0
    jj, ii = np.meshgrid(np.arange(size), np.arange(size))
    rays_win = np.stack([(jj - c) / win.f, (ii - c) / win.f, np.ones_like(jj, dtype=float)], axis=-1)
    rays_imu = rays_win @ R                                        # R.T applied to each ray
    x, y, theta = lens.project(rays_imu @ lens.R_lens_imu.T)
    r = np.hypot(x - lens.cx, y - lens.cy)
    bad = (r > lens.radius) | (x < 0) | (x > frame.shape[1] - 1) | (y < 0) | (y > frame.shape[0] - 1)
    x, y = np.where(bad, -1, x), np.where(bad, -1, y)
    win.image = cv2.remap(frame, x.astype(np.float32), y.astype(np.float32), cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return win


def solve_window(win: Window, up_imu: np.ndarray, utc: str, scale_margin: float = 0.2,
                 cpulimit_s: int = 60) -> dict:
    """Plate-solve the window and put the zenith through the solution → latitude, longitude."""
    import cv2
    from astropy.io import fits
    from astropy.wcs import WCS
    out = {"lens": win.lens.name, "solved": False}
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "w.png")
        img = win.image if win.image.ndim == 2 else cv2.cvtColor(win.image, cv2.COLOR_BGR2GRAY)
        cv2.imwrite(p, img)
        r = subprocess.run(["solve-field", p, "--config", ASTROMETRY_CFG, "--overwrite", "--no-plots", "--no-verify",
                            "--scale-units", "degwidth", "--scale-low", str(win.hfov_deg * (1 - scale_margin)),
                            "--scale-high", str(win.hfov_deg * (1 + scale_margin)), "--crpix-center",
                            "--tweak-order", "2", "--downsample", "1", "--objs", "400", "--cpulimit", str(cpulimit_s),
                            "--no-remove-lines", "--uniformize", "0"],
                           capture_output=True, text=True, cwd=d, timeout=cpulimit_s + 30)
        wf = os.path.join(d, "w.wcs")
        if not os.path.exists(wf):
            out["why"] = "not solved"
            return out
        hdr = fits.getheader(wf)
        w = WCS(hdr)
    zp = win.pixel_of(up_imu / np.linalg.norm(up_imu))
    if zp is None:
        out["why"] = "zenith behind the window"
        return out
    ra, dec = (float(v) for v in w.wcs_pix2world([[zp[0], zp[1]]], 0)[0])
    ra_a, dec_a = apparent_radec(ra, dec, utc)
    scale = abs(float(hdr.get("CD1_1", 0.0)) ** 2 + float(hdr.get("CD1_2", 0.0)) ** 2) ** 0.5
    out.update(solved=True, lat=dec_a, lon=(ra_a - gast_deg(utc) + 540.0) % 360.0 - 180.0,
               zenith_px=[round(zp[0], 1), round(zp[1], 1)],
               # solved degrees per pixel / the window's own: != 1 means the lens focal length guess is off
               scale_ratio=round(scale / math.degrees(1.0 / win.f), 4) if scale else None)
    return out


def locate(frame: np.ndarray, up_imu: np.ndarray, utc: str, lenses: Optional[List[Lens]] = None,
           tilt_deg: float = 30.0, hfov_deg: float = 50.0) -> List[dict]:
    """One answer per lens that sees enough sky (the two are independent checks of each other)."""
    out = []
    for lens in lenses or default_lenses():
        axis_up = float(lens.R_lens_imu[2] @ (up_imu / np.linalg.norm(up_imu)))
        if axis_up < -0.5:                                          # this lens looks at the ground
            continue
        out.append(solve_window(sky_window(frame, lens, up_imu, tilt_deg, hfov_deg), up_imu, utc))
    return out
