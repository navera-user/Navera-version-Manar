"""A physical camera for the simulator: lens, attitude, light — what a real camera sends.

Each frame is computed ray by ray: every pixel of a real lens (fisheye model, the
Insta360 ONE R 4K wide-angle class until the real calibration replaces it) is turned
into a direction, rotated by the vehicle's TRUE attitude (flight physics) and the
camera mount, and intersected with the ground at the true height; the satellite map
gives that ground point's colour. Then the light of the day (brightness, contrast,
colour), lens shading, motion blur, sensor noise and JPEG are applied.

So the frames reaching NAVERA are distorted, tilted, differently lit raw frames,
stamped at exposure: NAVERA's live camera node must undistort and straighten them
with its OWN, imperfect, sensors (the simulated BNO085 has a bias) — as on the box.

Still optimistic: the ground is flat at the map's level and the map is the camera's
own imagery source (no season, buildings' lean, or new roads).
"""
import io
import math
from collections import OrderedDict
from typing import Callable, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image as PILImage

from navera_common.camera_model import camera_rotation

# The simulated lens: equidistant-like fisheye, 960x540, ~105 deg wide. Replaced by
# the real Insta360 calibration file once measured (navera_tools/calibrate_camera.py).
SIM_LENS = dict(model="fisheye", image_width=960, image_height=540,
                camera_matrix=[525.0, 0.0, 480.0, 0.0, 525.0, 270.0, 0.0, 0.0, 1.0],
                distortion=[0.02, -0.01, 0.003, -0.0005])
THERMAL_LENS = dict(model="pinhole", image_width=640, image_height=512,
                    camera_matrix=[570.0, 0.0, 320.0, 0.0, 570.0, 256.0, 0.0, 0.0, 1.0],
                    distortion=[-0.12, 0.05, 0.0, 0.0, 0.0])


def _tile_xy(lat: float, lon: float, z: int) -> Tuple[float, float]:
    n = 2 ** z
    r = math.radians(lat)
    return (lon + 180.0) / 360.0 * n, (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n


class PhysicalCamera:
    """Renders what a camera with `lens` (calibration dict) sees from a pose."""

    def __init__(self, lens: dict, get_tile: Callable[[int, int, int], Optional[bytes]],
                 mount_rpy_deg: Sequence[float] = (0.0, 0.0, 0.0), thermal: bool = False, seed: int = 0):
        self.lens, self.get_tile, self.mount = lens, get_tile, tuple(mount_rpy_deg)
        self.thermal = thermal
        self.w, self.h = int(lens["image_width"]), int(lens["image_height"])
        K = np.array(lens["camera_matrix"], float).reshape(3, 3)
        D = np.array(lens["distortion"], float)
        # the ray geometry is smooth: computed on a half-resolution grid, then interpolated
        self.gw, self.gh = self.w // 2 + 1, self.h // 2 + 1
        u, v = np.meshgrid(np.linspace(0, self.w - 1, self.gw), np.linspace(0, self.h - 1, self.gh))
        pts = np.stack([u.ravel(), v.ravel()], axis=1).reshape(-1, 1, 2)
        if lens["model"] == "fisheye":
            n = cv2.fisheye.undistortPoints(pts, K, D[:4]).reshape(-1, 2)
        else:
            n = cv2.undistortPoints(pts, K, D).reshape(-1, 2)
        rays = np.concatenate([n, np.ones((len(n), 1))], axis=1)
        self.rays = (rays / np.linalg.norm(rays, axis=1, keepdims=True)).astype(np.float32)   # camera frame
        yy, xx = np.mgrid[0:self.h, 0:self.w]
        r2 = ((xx - self.w / 2) ** 2 + (yy - self.h / 2) ** 2) / ((self.w / 2) ** 2 + (self.h / 2) ** 2)
        self.vignette = (1.0 - 0.35 * r2).astype(np.float32)[..., None]   # lens shading
        rng = np.random.default_rng(seed)
        # the light of this mission: not the map's
        self.gain, self.gamma = rng.uniform(0.8, 1.15), rng.uniform(0.85, 1.2)
        self.tint = rng.uniform(0.92, 1.08, 3).astype(np.float32)
        self.rng = rng
        self.noise = [rng.normal(0, 0.012 if not thermal else 0.03, (self.h, self.w, 3)).astype(np.float32)
                      for _ in range(4)]                   # sensor noise, reused in turn
        self._k = 0
        self.tiles = OrderedDict()                         # decoded tiles, most recent last

    def render(self, lat: float, lon: float, agl_m: float, q_body_enu: Sequence[float],
               speed_mps: float = 0.0, heading_deg: float = 0.0, exposure_s: float = 0.004,
               night_day_camera: bool = False) -> np.ndarray:
        """BGR (or grey-as-BGR for thermal) frame from this pose."""
        agl = max(float(agl_m), 1.0)
        R = camera_rotation(q_body_enu, self.mount)
        d = self.rays @ R.T.astype(np.float32)                 # world (ENU) directions
        down = -d[:, 2]
        ok = down > 0.08                                        # beyond ~85 deg: horizon / sky
        t = np.where(ok, agl / np.maximum(down, 1e-6), 0.0)
        east, north = d[:, 0] * t, d[:, 1] * t
        dist = np.hypot(east, north)
        reach = min(float(dist[ok].max()) if ok.any() else agl, 4.0 * agl)
        ok &= dist <= reach
        # map resolution about the frame's at its centre (z19 only very low)
        ground_px = 2.0 * agl * math.tan(math.radians(50)) / self.w
        z = 19 if ground_px < 0.25 else 18 if ground_px < 0.9 else 17
        mosaic, mpp, cx, cy = self._mosaic(lat, lon, reach, z)
        gx = np.where(ok, cx + east / mpp, -1e4).astype(np.float32).reshape(self.gh, self.gw)
        gy = np.where(ok, cy - north / mpp, -1e4).astype(np.float32).reshape(self.gh, self.gw)
        mapx = cv2.resize(gx, (self.w, self.h), interpolation=cv2.INTER_LINEAR)
        mapy = cv2.resize(gy, (self.w, self.h), interpolation=cv2.INTER_LINEAR)
        ok = cv2.resize(ok.reshape(self.gh, self.gw).astype(np.uint8), (self.w, self.h),
                        interpolation=cv2.INTER_NEAREST).astype(bool)
        img = cv2.remap(mosaic, mapx, mapy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                        borderValue=(205, 190, 175))           # haze / sky
        return self._photometric(img, ok, speed_mps, heading_deg, exposure_s, agl, night_day_camera)

    def _mosaic(self, lat, lon, reach_m, z):
        tile_m = 40_075_016.7 * math.cos(math.radians(lat)) / 2 ** z
        half = int(math.ceil(reach_m / tile_m)) + 1
        x, y = _tile_xy(lat, lon, z)
        tx, ty = int(x), int(y)
        side = (2 * half + 1) * 256
        mosaic = np.full((side, side, 3), (60, 70, 65), np.uint8)
        found = 0
        for dx in range(-half, half + 1):
            for dy in range(-half, half + 1):
                t = self._tile(z, tx + dx, ty + dy)
                if t is not None:
                    mosaic[(dy + half) * 256:(dy + half + 1) * 256, (dx + half) * 256:(dx + half + 1) * 256] = t
                    found += 1
        if found == 0 and z > 17:
            return self._mosaic(lat, lon, reach_m, 17)
        return mosaic, tile_m / 256.0, (x - tx + half) * 256.0, (y - ty + half) * 256.0

    def _tile(self, z, x, y):
        key = (z, x, y)
        if key in self.tiles:
            self.tiles.move_to_end(key)
            return self.tiles[key]
        data, t = self.get_tile(z, x, y), None
        if data:
            try:
                t = np.array(PILImage.open(io.BytesIO(data)).convert("RGB"))[:, :, ::-1]
            except Exception:
                t = None
        self.tiles[key] = t
        if len(self.tiles) > 1500:
            self.tiles.popitem(last=False)
        return t

    def _photometric(self, img, ok, speed, heading_deg, exposure_s, agl, night_day_camera):
        f = img.astype(np.float32) / 255.0
        if self.thermal:                                          # thermal look: grey, stretched, soft
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            lo, hi = np.percentile(g[ok], (1, 99)) if ok.any() else (0.0, 1.0)
            g = np.clip((g - lo) / max(hi - lo, 1e-3), 0, 1)
            g = cv2.GaussianBlur(g, (0, 0), 1.2)
            f = np.repeat(g[..., None], 3, axis=2)
        else:
            f = np.clip((f * self.tint) ** self.gamma * self.gain, 0, 1)
            if night_day_camera:
                f *= 0.08
        f *= self.vignette
        blur_px = speed * exposure_s / (2.0 * agl * math.tan(math.radians(50)) / self.w)
        if blur_px > 1.0:                                         # motion blur along the track
            k = int(min(blur_px, 25)) | 1
            ker = np.zeros((k, k), np.float32)
            a = math.radians(90.0 - heading_deg)
            for i in range(k):
                o = i - k // 2
                ker[int(round(k // 2 - o * math.sin(a))) % k, int(round(k // 2 + o * math.cos(a))) % k] = 1
            f = cv2.filter2D(f, -1, ker / ker.sum())
        self._k = (self._k + 1) % len(self.noise)
        f += self.noise[self._k]
        out = (np.clip(f, 0, 1) * 255).astype(np.uint8)
        ok_jpeg, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)
