#!/usr/bin/env python3
"""Offline stress test of day vision under realistic conditions, with ground truth.

Query frames are RENDERED, not flown: a perspective camera (default 960x540, 85 deg
horizontal field of view, the straightened view NAVERA's camera node publishes) is placed
at a known position, height and attitude over imagery of the place, the frame is degraded
(light, clouds, objects, blur...), straightened with an attitude carrying an IMU error,
and located by day vision (day_pkg LearnedMatcher = production "auto": DISK+LightGlue,
SIFT fallback; or --matcher sift) against the z17 satellite map around a prior.

Imagery used for the query frames (the map is always the prepared z17 map):
  * xdate2022 / xdate2017 — Esri Wayback 2022 / 2017 tiles (z18) of Kalaa Kebira: ANOTHER
    DATE than the map (Sousse MBTiles, Esri, ~2025). The realistic case.
  * urban, coast, farms, olives, hills — the map's own source at z18 (same date: the
    appearance change is synthetic only, a fixed colour / gamma / blur / noise change).
  * desert, forest — the map's own z17 tiles (same source AND resolution, synthetic
    appearance change): optimistic.
None of this is NAVERA's camera: lens, rolling shutter, real clouds, real 3-D relief
(buildings lean in a tilted view, the map is a flat orthophoto) are not modelled.

A result is WRONG when day vision accepted it and it is > 50 m from the truth (the camera's
nadir point). "gated" columns also apply the day node's stateless spread gate
(day_subscriber._check_local_fix: < 30 inliers covering < 25 % of the frame, or < 50
inliers on <= 1/8 of it, rejected); the node's other gates need a track and are not run.

    python3 navera_tools/sim/dayvision_conditions.py --setup          # once: export the map
    python3 navera_tools/sim/dayvision_conditions.py [--groups light,clouds] [--frames 10]
            [--matcher learned|sift] [--out results.json]

Needs TORCH_HOME with the DISK / LightGlue weights (learned matcher) and the data below;
never uses a camera or a display.
"""
import argparse
import json
import math
import os
import sqlite3
import sys
import time
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "navera_common")):
    if p not in sys.path:
        sys.path.insert(0, p)

from navera_common.camera_model import (R_BODY_NADIR_CAM, heading_of_image_up_deg,  # noqa: E402
                                        nadir_homography, rpy_to_matrix)

EQUATOR_M = 40075016.7
SIM = os.path.expanduser("~/.navera_sim")
BENCH = os.path.join(SIM, "bench_2026-10-06")
DATA = os.path.join(SIM, "dayv_conditions")
MBTILES = os.environ.get("NAVERA_MBTILES", os.path.expanduser("~/navera_data_map.mbtiles"))
WRONG_M = 50.0
POSE = True                                        # pass hfov_deg: position from the camera pose

# name: map z17 images dir, query imagery (dir or "mbtiles"), query zoom, centre, sample radius (m),
# synthetic appearance change on top (same-source imagery), what the imagery is
SCENES = {
    "xdate2022": dict(map=os.path.join(DATA, "kalaa_map", "images"), query=os.path.join(BENCH, "wb2022"), qz=18,
                      centre=(35.8685, 10.5352), spread_m=500.0, app=False, note="Wayback 2022 vs map ~2025"),
    "xdate2017": dict(map=os.path.join(DATA, "kalaa_map", "images"), query=os.path.join(BENCH, "wb2017"), qz=18,
                      centre=(35.8685, 10.5352), spread_m=500.0, app=False, note="Wayback 2017 vs map ~2025"),
    "urban": dict(map=os.path.join(BENCH, "area_bench", "images"), query="mbtiles", qz=18,
                  centre=(35.8255, 10.6330), spread_m=800.0, app=True, note="Sousse city, same source"),
    "coast": dict(map=os.path.join(BENCH, "map_coast", "images"), query="mbtiles", qz=18,
                  centre=(35.8552, 10.6269), spread_m=1000.0, app=True, note="shore + sea, same source"),
    "farms": dict(map=os.path.join(BENCH, "map_farms", "images"), query="mbtiles", qz=18,
                  centre=(35.9389, 10.4590), spread_m=1000.0, app=True, note="fields, same source"),
    "olives": dict(map=os.path.join(BENCH, "map_olives", "images"), query="mbtiles", qz=18,
                   centre=(35.6930, 10.6348), spread_m=1000.0, app=True, note="olive groves, same source"),
    "hills": dict(map=os.path.join(BENCH, "map_hills", "images"), query="mbtiles", qz=18,
                  centre=(35.8000, 10.3711), spread_m=1000.0, app=True, note="hills, same source"),
    "desert": dict(map=os.path.join(SIM, "areas", "ce971ba791ec", "images"), query="map", qz=17,
                   centre=(33.9000, 9.3800), spread_m=300.0, app=True, note="Kebili desert, map's own tiles"),
    "forest": dict(map=os.path.join(SIM, "areas", "c3d4e06f58e8", "images"), query="map", qz=17,
                   centre=(48.3620, 2.6450), spread_m=300.0, app=True, note="Fontainebleau, map's own tiles"),
}


# ── geometry ─────────────────────────────────────────────────────────────
def tile_xy(lat: float, lon: float, z: int) -> Tuple[float, float]:
    n = 2 ** z
    r = math.radians(lat)
    return (lon + 180.0) / 360.0 * n, (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n


def mpp(lat: float, z: int) -> float:
    return EQUATOR_M * math.cos(math.radians(lat)) / 2 ** z / 256.0


def move(ll: Tuple[float, float], de: float, dn: float) -> Tuple[float, float]:
    return ll[0] + dn / 111320.0, ll[1] + de / (111320.0 * math.cos(math.radians(ll[0])))


def dist_m(a, b) -> float:
    dn = (b[0] - a[0]) * 111320.0
    de = (b[1] - a[1]) * 111320.0 * math.cos(math.radians(a[0]))
    return math.hypot(de, dn)


class Imagery:
    """Tiles tile_{z}_{x}_{y}.jpg from a directory, or from the MBTiles map."""

    def __init__(self, src: str):
        self.dir, self.db = (None, sqlite3.connect(MBTILES)) if src == "mbtiles" else (src, None)
        self.cache: Dict = {}

    def tile(self, z: int, x: int, y: int) -> Optional[np.ndarray]:
        k = (z, x, y)
        if k not in self.cache:
            im = None
            if self.db is not None:
                r = self.db.execute("select tile_data from tiles where zoom_level=? and tile_column=? and tile_row=?",
                                    (z, x, 2 ** z - 1 - y)).fetchone()
                if r:
                    im = cv2.imdecode(np.frombuffer(r[0], np.uint8), cv2.IMREAD_COLOR)
            else:
                im = cv2.imread(os.path.join(self.dir, f"tile_{z}_{x}_{y}.jpg"), cv2.IMREAD_COLOR)
            if im is not None and im.shape[:2] != (256, 256):
                im = cv2.resize(im, (256, 256), interpolation=cv2.INTER_AREA)
            if len(self.cache) > 3000:
                self.cache.clear()
            self.cache[k] = im
        return self.cache[k]

    def mosaic(self, lat: float, lon: float, half_m: float, z: int):
        """(BGR mosaic, (cx, cy) pixel of (lat, lon), metres per pixel, valid fraction)."""
        m = mpp(lat, z)
        fx, fy = tile_xy(lat, lon, z)
        r = half_m / m / 256.0
        x0, x1, y0, y1 = int(fx - r), int(fx + r), int(fy - r), int(fy + r)
        img = np.zeros(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256, 3), np.uint8)
        have = 0
        for tx in range(x0, x1 + 1):
            for ty in range(y0, y1 + 1):
                t = self.tile(z, tx, ty)
                if t is not None:
                    have += 1
                    img[(ty - y0) * 256:(ty - y0 + 1) * 256, (tx - x0) * 256:(tx - x0 + 1) * 256] = t
        return img, ((fx - x0) * 256.0, (fy - y0) * 256.0), m, have / float((x1 - x0 + 1) * (y1 - y0 + 1))


def camera_R(heading_deg: float, tilt_deg: float, tilt_dir_deg: float) -> np.ndarray:
    """R_world_cam of a nadir camera on a body with this heading, tilted tilt_deg towards
    tilt_dir_deg (body frame: 0 = nose down)."""
    a = math.radians(tilt_deg)
    roll, pitch = a * math.sin(math.radians(tilt_dir_deg)), a * math.cos(math.radians(tilt_dir_deg))
    return rpy_to_matrix(roll, pitch, math.radians(90.0 - heading_deg)) @ R_BODY_NADIR_CAM


def small_rotation(err_deg: float, rng) -> np.ndarray:
    """A rotation of err_deg about a random horizontal world axis (an IMU tilt error)."""
    if err_deg <= 0:
        return np.eye(3)
    ax = rng.uniform(0, 2 * math.pi)
    v = np.array([math.cos(ax), math.sin(ax), 0.0]) * math.radians(err_deg)
    return cv2.Rodrigues(v)[0]


def K_of(w: int, h: int, hfov: float) -> np.ndarray:
    f = (w / 2.0) / math.tan(math.radians(hfov) / 2.0)
    return np.array([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1.0]])


def render(imagery: Imagery, z: int, pos: Tuple[float, float], h_m: float, R: np.ndarray, K: np.ndarray,
           size: Tuple[int, int]) -> Tuple[Optional[np.ndarray], float]:
    """The camera's view of the flat ground (the imagery) from h_m above pos; (frame, valid)."""
    w, hh = size
    Minv = R @ np.linalg.inv(K)
    corners = np.array([[0, 0, 1], [w, 0, 1], [0, hh, 1], [w, hh, 1]], float).T
    d = Minv @ corners
    if (d[2] >= -0.05).any():
        return None, 0.0
    ground = d[:2] * (h_m / -d[2])
    half = float(np.abs(ground).max()) + 50.0
    near_mpp = 2.0 * h_m * K[0, 2] / K[0, 0] / w            # nadir ground resolution
    mos, (cx, cy), m, valid = imagery.mosaic(pos[0], pos[1], half, z)
    f = max(1.0, 0.7 * near_mpp / m)                         # avoid aliasing: shrink first
    if f > 1.0:
        mos = cv2.resize(mos, None, fx=1.0 / f, fy=1.0 / f, interpolation=cv2.INTER_AREA)
        cx, cy, m = cx / f, cy / f, m * f
    G = np.vstack([h_m * Minv[0], h_m * Minv[1], -Minv[2]])  # image -> (E, N, 1)
    A = np.array([[1.0 / m, 0, cx], [0, -1.0 / m, cy], [0, 0, 1.0]])
    frame = cv2.warpPerspective(mos, A @ G, (w, hh), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                borderMode=cv2.BORDER_CONSTANT)
    return frame, valid


# ── degradations (on the raw camera frame, before straightening) ─────────
def _noise_field(shape, rng, scale_px: float) -> np.ndarray:
    """Smooth random field in [0, 1] (sum of blurred noise octaves): clouds, shadows."""
    h, w = shape[:2]
    acc = np.zeros((h, w), np.float32)
    amp, s = 1.0, scale_px
    for _ in range(4):
        sh, sw = max(2, int(h / s) + 2), max(2, int(w / s) + 2)
        acc += amp * cv2.resize(rng.standard_normal((sh, sw)).astype(np.float32), (w, h),
                                interpolation=cv2.INTER_CUBIC)
        amp, s = amp * 0.5, s / 2.5
    acc -= acc.min()
    return acc / max(acc.max(), 1e-6)


def _cover_mask(field: np.ndarray, frac: float, soft_px: float = 6.0) -> np.ndarray:
    thr = np.quantile(field, 1.0 - frac)
    m = np.clip((field - thr) / 0.03, 0, 1).astype(np.float32)
    return cv2.GaussianBlur(m, (0, 0), soft_px)


def appearance(img, rng):
    """The fixed 'other camera / other day' change used on same-source imagery: white
    balance, gamma, contrast, slight blur, sensor noise, JPEG."""
    f = img.astype(np.float32)
    f *= np.array([0.85, 1.0, 1.12], np.float32)
    f = 255.0 * (np.clip(f, 0, 255) / 255.0) ** 1.25
    f = (f - 128.0) * 0.85 + 128.0 + 10.0
    f = cv2.GaussianBlur(f, (0, 0), 0.8)
    f += rng.normal(0, 4.0, f.shape)
    return _jpeg(np.clip(f, 0, 255).astype(np.uint8), 70)


def _jpeg(img, q):
    return cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(q)])[1], cv2.IMREAD_COLOR)


def d_low_sun(img, rng, shadow_px=12, sun_az=None):
    """Low sun: warm, darker, low contrast in shade + long cast shadows behind raised bright
    objects (roofs, trees approximated by local bright / dark top-hat blobs) — crude."""
    f = img.astype(np.float32)
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    raised = (cv2.morphologyEx(grey, cv2.MORPH_TOPHAT, k) > 25) | (cv2.morphologyEx(grey, cv2.MORPH_BLACKHAT, k) > 35)
    az = rng.uniform(0, 2 * math.pi) if sun_az is None else sun_az
    shadow = np.zeros(grey.shape, np.float32)
    m = raised.astype(np.float32)
    for i in range(1, int(shadow_px) + 1):
        M = np.float32([[1, 0, i * math.cos(az)], [0, 1, i * math.sin(az)]])
        shadow = np.maximum(shadow, cv2.warpAffine(m, M, (grey.shape[1], grey.shape[0])))
    shadow = cv2.GaussianBlur(shadow * (1 - m), (0, 0), 1.5)
    f *= (1.0 - 0.55 * shadow)[..., None]
    f *= np.array([0.75, 0.9, 1.1], np.float32) * 0.8
    return np.clip(f, 0, 255).astype(np.uint8)


def d_exposure(img, rng, gain=1.0, noise=0.0):
    f = img.astype(np.float32) * gain
    if noise:
        f += rng.normal(0, noise, f.shape)
    return np.clip(f, 0, 255).astype(np.uint8)


def d_haze(img, rng, t=0.5, airlight=205.0):
    return np.clip(img.astype(np.float32) * t + airlight * (1 - t), 0, 255).astype(np.uint8)


def d_glare(img, rng, radius_frac=0.25):
    """Sun reflection: a saturated blob with a halo and a streak, somewhere in the frame."""
    h, w = img.shape[:2]
    cx, cy = rng.uniform(0.2, 0.8) * w, rng.uniform(0.2, 0.8) * h
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / (radius_frac * w) ** 2
    halo = np.exp(-r2 * 2.0) + 0.35 * np.exp(-((yy - cy) ** 2) / (0.01 * h) ** 2) * np.exp(-r2 * 0.3)
    f = img.astype(np.float32) + 255.0 * 1.6 * np.clip(halo, 0, 1)[..., None]
    return np.clip(f, 0, 255).astype(np.uint8)


def d_wb(img, rng, gains=(1.35, 1.0, 0.7)):
    return np.clip(img.astype(np.float32) * np.array(gains, np.float32), 0, 255).astype(np.uint8)


def d_jpeg_noise(img, rng, q=15, sigma=12.0):
    f = img.astype(np.float32) + rng.normal(0, sigma, img.shape)
    return _jpeg(np.clip(f, 0, 255).astype(np.uint8), q)


def d_motion(img, rng, length_px=0.0, angle_deg=-90.0):
    """Linear motion blur of length_px (camera pixels) along angle_deg (image -90 = up)."""
    if length_px < 0.5:
        return img
    n = int(math.ceil(length_px)) * 2 + 1
    k = np.zeros((n, n), np.float32)
    c = n // 2
    dx, dy = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    for t in np.linspace(-length_px / 2, length_px / 2, 4 * n):
        k[int(round(c + t * dy)), int(round(c + t * dx))] = 1.0
    return cv2.filter2D(img, -1, k / k.sum())


def d_clouds(img, rng, cover=0.3, opacity=1.0, shadows=False):
    """Cumulus patches covering `cover` of the frame (opacity 1: opaque, < 1: thin);
    shadows: their shadows on the ground elsewhere in the frame."""
    h, w = img.shape[:2]
    f = img.astype(np.float32)
    if shadows:
        sm = _cover_mask(_noise_field((h, w), rng, w / 3.0), cover, 10.0)
        f *= (1.0 - 0.55 * sm)[..., None]
    if opacity > 0:
        m = _cover_mask(_noise_field((h, w), rng, w / 3.0), cover) * opacity
        tex = 225.0 + 25.0 * (_noise_field((h, w), rng, w / 20.0) - 0.5)
        f = f * (1 - m[..., None]) + tex[..., None] * m[..., None]
    return np.clip(f, 0, 255).astype(np.uint8)


def d_birds(img, rng, n=25, aircraft=1):
    """Birds (dark specks 3-9 px), aircraft (light cross shapes ~60-120 px) in the frame."""
    out = img.copy()
    h, w = img.shape[:2]
    for _ in range(n):
        c = (int(rng.uniform(0, w)), int(rng.uniform(0, h)))
        s = int(rng.uniform(3, 9))
        cv2.ellipse(out, c, (s, max(1, s // 3)), rng.uniform(0, 180), 0, 360, (30, 30, 35), -1)
    for _ in range(aircraft):
        c = np.array([rng.uniform(0.15, 0.85) * w, rng.uniform(0.15, 0.85) * h])
        L = rng.uniform(60, 120)
        a = rng.uniform(0, math.pi)
        u, v = np.array([math.cos(a), math.sin(a)]), np.array([-math.sin(a), math.cos(a)])
        col = (235, 235, 240)
        cv2.line(out, tuple((c - u * L / 2).astype(int)), tuple((c + u * L / 2).astype(int)), col, int(L / 10))
        cv2.line(out, tuple((c - v * L * 0.45).astype(int)), tuple((c + v * L * 0.45).astype(int)), col, int(L / 14))
    return out


def d_vehicle(img, rng, kind="propeller"):
    """Parts of the vehicle in the view: a spinning propeller (semi-transparent dark disk
    sector in a corner) or landing gear (opaque dark bars from a corner)."""
    h, w = img.shape[:2]
    out = img.astype(np.float32)
    m = np.zeros((h, w), np.float32)
    if kind == "propeller":
        cv2.circle(m, (int(0.05 * w), int(0.05 * h)), int(0.35 * h), 1.0, -1)
        m = cv2.GaussianBlur(m, (0, 0), 6) * 0.6
        out = out * (1 - m[..., None]) + 40.0 * m[..., None]
    else:
        for x0, x1 in ((0.0, 0.12), (0.88, 1.0)):
            pts = np.array([[x0 * w, h], [x1 * w, h], [(x0 + x1) / 2 * w + 0.03 * w, 0.62 * h],
                            [(x0 + x1) / 2 * w - 0.03 * w, 0.62 * h]], np.int32)
            cv2.fillConvexPoly(m, pts, 1.0)
        out = out * (1 - m[..., None]) + 25.0 * m[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def d_lowlight(img, rng, photons=60.0, lights=True, exposure_s=0.03, speed=25.0, height=300.0,
               hfov=85.0):
    """A visible camera at night (the Insta360 class): reflectance x a moonlight level,
    shot noise (`photons` electrons for a white surface per exposure), read noise 2 e-,
    street / window lights on man-made surfaces (grey and bright in the day image), a
    long exposure's motion blur along the track, auto-exposure on the 99th percentile,
    gamma 2.2, colour lost (sodium / moonlight: grey). Not a camera model: no colour
    noise, no ISP denoising, no lens flare around the lights."""
    f = img.astype(np.float32) / 255.0
    luma = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    sat = (f.max(axis=2) - f.min(axis=2)) / np.maximum(f.max(axis=2), 1e-3)
    e = luma * photons
    h, w = luma.shape
    if lights:
        cand = np.flatnonzero(((sat < 0.18) & (luma > 0.45)).ravel())
        if cand.size:
            lamp = np.zeros(h * w, np.float32)
            lamp[rng.choice(cand, size=min(cand.size, int(0.002 * h * w)), replace=False)] = 1.0
            lamp = cv2.GaussianBlur(lamp.reshape(h, w), (0, 0), 2.5)
            e = e + lamp / max(float(lamp.max()), 1e-6) * 60.0 * max(photons, 5.0)
    e = rng.poisson(np.clip(e, 0, None)).astype(np.float32) + rng.normal(0, 2.0, e.shape).astype(np.float32)
    L = blur_px(speed, exposure_s, height, hfov, w)
    if L >= 1.0:
        e = d_motion(np.clip(e / max(float(e.max()), 1e-3) * 255, 0, 255).astype(np.uint8)[..., None]
                     .repeat(3, axis=2), rng, length_px=L)[..., 0].astype(np.float32)
    g = np.clip(e / max(float(np.percentile(e, 99)), 1e-3), 0, 1) ** (1 / 2.2)
    return cv2.cvtColor((g * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)


DEGRADE = dict(low_sun=d_low_sun, exposure=d_exposure, haze=d_haze, glare=d_glare, wb=d_wb,
               jpeg_noise=d_jpeg_noise, motion=d_motion, clouds=d_clouds, birds=d_birds, vehicle=d_vehicle,
               lowlight=d_lowlight)


# ── conditions ───────────────────────────────────────────────────────────
BASE = dict(scene="xdate2022", height=300.0, tilt=0.0, straighten=True, imu_err=0.5, heading_err=3.0,
            heading=True, scale_err=0.0, prior_err=100.0, radius=None, spoof=False, degrade=[])


def blur_px(speed: float, exposure_s: float, height: float, hfov: float, width: int) -> float:
    return speed * exposure_s / (2 * height * math.tan(math.radians(hfov) / 2) / width)


def conditions(hfov: float, width: int) -> List[dict]:
    C = []

    def add(group, name, **kw):
        c = dict(BASE, group=group, name=name)
        c.update(kw)
        C.append(c)
    add("ref", "reference (xdate2022, 300 m, nadir)")
    # lighting
    add("light", "low sun, long shadows", degrade=[("low_sun", {})])
    add("light", "over-exposed x2.2", degrade=[("exposure", dict(gain=2.2))])
    add("light", "under-exposed x0.25 + noise", degrade=[("exposure", dict(gain=0.25, noise=3.0))])
    add("light", "haze thin (t=0.7)", degrade=[("haze", dict(t=0.7))])
    add("light", "haze thick (t=0.4)", degrade=[("haze", dict(t=0.4))])
    add("light", "glare / sun reflection", degrade=[("glare", {})])
    add("light", "white balance warm", degrade=[("wb", {})])
    add("light", "white balance cold", degrade=[("wb", dict(gains=(0.7, 1.0, 1.35)))])
    add("light", "JPEG q15 + noise 12", degrade=[("jpeg_noise", {})])
    for v in (10, 30, 60, 100):
        for exp_s, hgt in ((0.002, 300.0), (0.010, 150.0)):
            L = blur_px(v, exp_s, hgt, hfov, width)
            add("blur", f"motion {v} m/s, {exp_s * 1000:.0f} ms, {hgt:.0f} m ({L:.1f} px)", height=hgt,
                degrade=[("motion", dict(length_px=L))])
    # clouds
    for cov in (0.1, 0.3, 0.6):
        add("clouds", f"opaque clouds {cov:.0%}", degrade=[("clouds", dict(cover=cov))])
    add("clouds", "thin cloud veil 60% (opacity 0.5)", degrade=[("clouds", dict(cover=0.6, opacity=0.5))])
    add("clouds", "cloud shadows 30%", degrade=[("clouds", dict(cover=0.3, opacity=0.0, shadows=True))])
    add("clouds", "clouds 30% + their shadows", degrade=[("clouds", dict(cover=0.3, shadows=True))])
    # objects
    add("objects", "25 birds + 1 aircraft", degrade=[("birds", {})])
    add("objects", "80 birds + 3 aircraft", degrade=[("birds", dict(n=80, aircraft=3))])
    add("objects", "propeller in a corner", degrade=[("vehicle", dict(kind="propeller"))])
    add("objects", "landing gear legs", degrade=[("vehicle", dict(kind="gear"))])
    # geometry
    for hgt in (100, 200, 500, 800, 1000, 1500):
        add("height", f"height {hgt} m", height=float(hgt))
    for e in (5, 10, 20, 30):
        add("heading", f"heading error {e} deg", heading_err=float(e))
    add("heading", "no heading (no IMU)", heading=False)
    for t in (10, 20, 30):
        add("tilt", f"tilt {t} deg, straightened", tilt=float(t))
        add("tilt", f"tilt {t} deg, NOT straightened", tilt=float(t), straighten=False)
    for e in (1.0, 2.0, 3.0):
        add("tilt", f"tilt 20 deg, IMU error {e} deg", tilt=20.0, imu_err=e)
    for s in (-0.2, -0.1, 0.1, 0.2):
        add("scale", f"height error {s:+.0%}", scale_err=s)
    # terrain / date
    for sc in ("urban", "coast", "farms", "olives", "hills", "desert", "forest", "xdate2017"):
        add("terrain", f"terrain {sc}", scene=sc)
    # prior error / spoof
    for pe in (50, 300, 600, 1000, 1500):
        add("prior", f"prior error {pe} m (radius {max(1.3 * pe, 100):.0f} m)", prior_err=float(pe))
    for pe in (1500, 3000):
        add("spoof", f"GPS spoof: prior {pe} m off, radius 600 m", prior_err=float(pe), radius=600.0, spoof=True)
    # visible camera at night (2026-10-19): moonlight levels, street lights, 30 ms exposure
    for sc in ("urban", "xdate2022"):
        for lbl, ph in (("full moon", 60.0), ("quarter moon", 8.0), ("starlight", 0.5)):
            add("lowlight", f"night visible, {lbl}, lights, {sc}", scene=sc,
                degrade=[("lowlight", dict(photons=ph, hfov=hfov))])
    add("lowlight", "night visible, full moon, no lights, xdate2022",
        degrade=[("lowlight", dict(photons=60.0, lights=False, hfov=hfov))])
    add("lowlight", "night visible, full moon, lights, xdate2022, 1 ms (no blur, very noisy)",
        degrade=[("lowlight", dict(photons=2.0, exposure_s=0.001, hfov=hfov))])
    # combined worst-but-plausible
    add("combo", "500 m, tilt 15 straightened, IMU 2 deg, haze, clouds 30%, 60 m/s",
        height=500.0, tilt=15.0, imu_err=2.0,
        degrade=[("haze", dict(t=0.6)), ("clouds", dict(cover=0.3)),
                 ("motion", dict(length_px=blur_px(60, 0.004, 500, hfov, width)))])
    return C


# ── run ──────────────────────────────────────────────────────────────────
def make_matcher(kind: str, images_dir: str):
    if kind == "sift":
        from day_pkg.local_matcher import LocalMatcher
        return LocalMatcher(images_dir)
    from day_pkg.learned_matcher import LearnedMatcher
    return LearnedMatcher(images_dir)


def spread_gate(res: dict) -> bool:
    inl, sp = int(res.get("inliers") or 0), float(res.get("spread", 1.0))
    return not ((inl < 30 and sp < 0.25) or (inl < 50 and sp <= 0.125))


def run_one(matcher, imagery: Imagery, scene: dict, c: dict, i: int, size, hfov: float, seed: int = 0) -> dict:
    rng = np.random.default_rng(1000 * seed + i)
    ang, r = rng.uniform(0, 2 * math.pi), scene["spread_m"] * math.sqrt(rng.uniform(0, 1))
    heading = rng.uniform(0, 360)
    R = camera_R(heading, c["tilt"], rng.uniform(0, 360))
    K = K_of(size[0], size[1], hfov)
    for _ in range(6):                             # a high frame must fit in the imagery: closer in
        pos = move(scene["centre"], r * math.cos(ang), r * math.sin(ang))
        frame, valid = render(imagery, scene["qz"], pos, c["height"], R, K, size)
        if frame is not None and valid >= 0.98:
            break
        r *= 0.5
    else:
        return dict(skip=True)
    drng = np.random.default_rng(7 + 1000 * seed + i)
    if scene["app"]:
        frame = appearance(frame, drng)
    for name, kw in c["degrade"]:
        frame = DEGRADE[name](frame, drng, **kw)
    R_est = small_rotation(c["imu_err"], rng) @ R
    if c["straighten"]:
        frame = cv2.warpPerspective(frame, nadir_homography(K, R_est), size, flags=cv2.INTER_LINEAR,
                                    borderMode=cv2.BORDER_CONSTANT)
    hdg = (heading_of_image_up_deg(R_est) + rng.choice([-1, 1]) * c["heading_err"]) % 360 if c["heading"] else None
    h_est = c["height"] * (1.0 + c["scale_err"])
    mpp_f = 2.0 * h_est * math.tan(math.radians(hfov) / 2.0) / size[0]
    pa = rng.uniform(0, 2 * math.pi)
    prior = move(pos, c["prior_err"] * math.cos(pa), c["prior_err"] * math.sin(pa))
    radius = c["radius"] or max(1.3 * c["prior_err"], 100.0)
    if hasattr(matcher, "_heading"):
        matcher._heading = None                    # no memory between independent frames
    t0 = time.time()
    kw = dict(hfov_deg=hfov) if POSE else {}
    res = matcher.locate(frame, prior, radius, mpp_f, heading_deg=hdg, **kw)
    ms = (time.time() - t0) * 1000.0
    out = dict(skip=False, accepted=bool(res.get("accepted")), inliers=int(res.get("inliers") or 0),
               spread=float(res.get("spread") or 0.0), ms=ms, features=res.get("features"),
               reason=res.get("reason"), scale=res.get("scale_residual"), position_from=res.get("position_from"),
               pose_tilt=res.get("pose_tilt_deg"), pose_h=res.get("pose_height_m"), pose_rms=res.get("pose_rms_px"))
    if res.get("predicted_lat") is not None:
        out["err_m"] = dist_m(pos, (res["predicted_lat"], res["predicted_lon"]))
    out["gated"] = out["accepted"] and spread_gate(res)
    out["_frame"] = frame
    return out


def summarize(c: dict, rows: List[dict]) -> dict:
    rows = [r for r in rows if not r.get("skip")]
    n = len(rows)
    acc = [r for r in rows if r["accepted"]]
    gat = [r for r in rows if r["gated"]]
    ok_err = [r["err_m"] for r in acc if r["err_m"] <= WRONG_M]
    e = np.array([r["err_m"] for r in acc]) if acc else np.array([])
    return dict(group=c["group"], name=c["name"], n=n,
                ok=len(ok_err), wrong=sum(r["err_m"] > WRONG_M for r in acc),
                ok_g=sum(r["err_m"] <= WRONG_M for r in gat), wrong_g=sum(r["err_m"] > WRONG_M for r in gat),
                med=float(np.median(e)) if len(e) else None, p90=float(np.percentile(e, 90)) if len(e) else None,
                max=float(e.max()) if len(e) else None,
                ms=float(np.median([r["ms"] for r in rows])) if rows else None)


def fmt_row(s: dict) -> str:
    f = (lambda v: "-" if v is None else f"{v:.0f}" if v >= 10 else f"{v:.1f}")
    return (f"| {s['group']} | {s['name']} | {s['n']} | {s['ok']}/{s['n']} | {s['wrong']} | {s['ok_g']}/{s['n']} | "
            f"{s['wrong_g']} | {f(s['med'])} | {f(s['p90'])} | {f(s['max'])} | {f(s['ms'])} |")


HEADER = ("| group | condition | n | located (<=50 m) | WRONG accepted | located, gated | WRONG, gated | "
          "median m | p90 m | max m | ms/frame |\n|---|---|---|---|---|---|---|---|---|---|---|")


def setup():
    """Export the z17 map of the cross-date scene (Kalaa Kebira, 12 x 12 km) from the MBTiles."""
    out = os.path.dirname(SCENES["xdate2022"]["map"])
    img = os.path.join(out, "images")
    os.makedirs(img, exist_ok=True)
    db = sqlite3.connect(MBTILES)
    lat, lon = SCENES["xdate2022"]["centre"]
    fx, fy = tile_xy(lat, lon, 17)
    r = 6000.0 / mpp(lat, 17) / 256.0
    n = 0
    for x in range(int(fx - r), int(fx + r) + 1):
        for y in range(int(fy - r), int(fy + r) + 1):
            p = os.path.join(img, f"tile_17_{x}_{y}.jpg")
            if os.path.exists(p):
                continue
            row = db.execute("select tile_data from tiles where zoom_level=17 and tile_column=? and tile_row=?",
                             (x, 2 ** 17 - 1 - y)).fetchone()
            if row:
                with open(p, "wb") as fh:
                    fh.write(row[0])
                n += 1
    print(f"exported {n} z17 tiles to {img}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--setup", action="store_true", help="export the cross-date scene's map, then exit")
    ap.add_argument("--groups", default="", help="comma list of groups (default all)")
    ap.add_argument("--match", default="", help="only conditions whose name contains this")
    ap.add_argument("--frames", type=int, default=10)
    ap.add_argument("--matcher", choices=["learned", "sift"], default="learned")
    ap.add_argument("--hfov", type=float, default=85.0)
    ap.add_argument("--size", default="960x540")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="", help="JSON file for per-frame results and the table")
    ap.add_argument("--save-frames", default="", help="directory: save the first frame of each condition")
    ap.add_argument("--no-pose", action="store_true", help="locate the frame centre (no hfov_deg passed)")
    a = ap.parse_args()
    global POSE
    POSE = not a.no_pose
    if a.setup:
        setup()
        return
    size = tuple(int(v) for v in a.size.split("x"))
    conds = conditions(a.hfov, size[0])
    if a.groups:
        conds = [c for c in conds if c["group"] in a.groups.split(",")]
    if a.match:
        conds = [c for c in conds if a.match in c["name"]]
    by_map: Dict[str, List[dict]] = {}
    for c in conds:
        by_map.setdefault(SCENES[c["scene"]]["map"], []).append(c)
    summaries, per_frame = [], {}
    print(HEADER, flush=True)
    for map_dir, cs in by_map.items():
        matcher = make_matcher(a.matcher, map_dir)
        for c in cs:
            scene = SCENES[c["scene"]]
            imagery = Imagery(map_dir if scene["query"] == "map" else scene["query"])
            rows = []
            for i in range(a.frames):
                r = run_one(matcher, imagery, scene, c, i, size, a.hfov, a.seed)
                fr = r.pop("_frame", None)
                if a.save_frames and i == 0 and fr is not None:
                    os.makedirs(a.save_frames, exist_ok=True)
                    safe = "".join(ch if ch.isalnum() else "_" for ch in c["name"])[:60]
                    cv2.imwrite(os.path.join(a.save_frames, f"{c['group']}_{safe}.jpg"), fr)
                rows.append(r)
            s = summarize(c, rows)
            summaries.append(s)
            per_frame[c["name"]] = rows
            print(fmt_row(s), flush=True)
        del matcher
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:                          # noqa: BLE001 — SIFT only, no torch
            pass
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(dict(args=vars(a), summary=summaries, frames=per_frame), fh, indent=1, default=str)


if __name__ == "__main__":
    main()
