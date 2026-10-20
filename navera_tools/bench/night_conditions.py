#!/usr/bin/env python3
"""Night vision (STHN) stress test under simulated conditions, with ground truth.

OFFLINE and SYNTHETIC: every frame is rendered from the same satellite map STHN
matches against (navera_tools/sim/physical_camera.py geometry: pinhole lens,
true attitude, flat ground), turned into a thermal-LIKE grey image, then degraded
by one condition at a time (thermal look, lights, weather, occluders, geometry,
terrain). Real LWIR imagery differs from a grey satellite photo (different
materials contrast, polarity flips over the night, no shadows of the sun):
these numbers bound what the matcher does with the geometry and photometry
modelled here, nothing more.

Each frame goes the live chain: rendered at the true pose, straightened by
navera_common.frame_builder with the MEASURED attitude (IMU error added), then
NightLocalizer.localize with the measured height (error added), measured heading
and a prior offset from the truth. The same poses (seeded per frame) are used in
every condition, so conditions compare frame for frame.

Per condition: accepted / refused, error median / p90 / max of accepted fixes,
wrong accepts (accepted and > WRONG_M from the truth; for a frame with no
information — noise, uniform — every accept is wrong), share of accepted fixes
within 3 stated sigma, and time per frame.

    python3 navera_tools/bench/night_conditions.py [--n 24] [--only nominal,fog]
        [--device cuda|cpu] [--csv out.csv] [--save-frames dir]

Data: NAVERA_MBTILES, NAVERA_STHN_DIR, NAVERA_STHN_WEIGHTS (see ~/navera_env.sh).
One STHN model is loaded; GPU memory is released at the end.
"""
import argparse
import csv
import math
import os
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for p in (ROOT / "night_pkg", ROOT / "navera_common", ROOT / "navera_tools" / "sim"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from navera_common.camera_model import CameraModel  # noqa: E402
from navera_common.frame_builder import FrameBuilder  # noqa: E402
from physical_camera import PhysicalCamera  # noqa: E402

WRONG_M = 50.0          # an accepted fix farther than this from the truth is a wrong accept
WRONG_HARD_M = 100.0    # "wrong3s": accepted and > 100 m off or outside 3 stated sigma
HFOV_DEG = 75.0         # the simulator's thermal camera (~75 x 63 deg, 640 x 512)
SIZE = (640, 512)
TAU_S = 0.012           # microbolometer thermal time constant (smear along the track)
HEADING_RETRY: tuple = ()   # --heading-retry: offsets tried when the map check fails
HEIGHT_RETRY: tuple = ()    # --height-retry: relative height changes tried after them

# Sites inside the Sousse map (ESRI imagery, z13-z19): centre lat, lon, radius (m)
SITES = {
    "urban":    (35.8280, 10.6320, 700.0),     # Sousse centre
    "farmland": (35.7450, 10.4500, 1500.0),    # field patchwork inland
    "coast":    (35.8800, 10.5900, 0.0),       # shoreline: sampled along it (see _coast_point)
    "sea":      (35.9200, 10.7500, 2000.0),    # open sea, no structure
    "desert":   (35.5850, 10.4300, 900.0),     # Sebkhet Sidi el Hani salt flat (uniform)
    "olives":   (35.6930, 10.6348, 1000.0),    # olive groves: the same tree pattern repeated
}
# The shoreline north of Sousse, roughly NW-SE (lat, lon): frames half sea / half land
COAST_LINE = [(35.9200, 10.5770), (35.9050, 10.5890), (35.8900, 10.6010), (35.8750, 10.6058),
              (35.8600, 10.6176)]


# ── map tiles ───────────────────────────────────────────────────────────────────

class Tiles:
    """XYZ tile bytes from an MBTiles file (read-only)."""

    def __init__(self, path: str):
        self.conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)

    def get(self, z: int, x: int, y: int) -> Optional[bytes]:
        row = self.conn.execute(
            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (z, x, (2 ** z - 1) - y)).fetchone()
        return row[0] if row else None


class _GeomCamera(PhysicalCamera):
    """The simulator's camera geometry, without its photometry (applied here)."""

    def _photometric(self, img, ok, *args):
        return img, ok


# ── poses ───────────────────────────────────────────────────────────────────────

def offset(lat: float, lon: float, north_m: float, east_m: float):
    return (lat + north_m / 111_320.0,
            lon + east_m / (111_320.0 * math.cos(math.radians(lat))))


def dist_m(a, b) -> float:
    n = (b[0] - a[0]) * 111_320.0
    e = (b[1] - a[1]) * 111_320.0 * math.cos(math.radians(a[0]))
    return math.hypot(n, e)


def quat_rpy(roll_deg: float, pitch_deg: float, heading_deg: float):
    """Body ENU quaternion (x, y, z, w) from roll, pitch (deg) and heading (deg cw from N)."""
    r, p, y = math.radians(roll_deg), math.radians(-pitch_deg), math.radians(90.0 - heading_deg)
    cr, sr, cp, sp, cy, sy = (math.cos(r / 2), math.sin(r / 2), math.cos(p / 2), math.sin(p / 2),
                              math.cos(y / 2), math.sin(y / 2))
    return (sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


def _coast_point(rng):
    i = int(rng.integers(0, len(COAST_LINE) - 1))
    t = float(rng.uniform(0, 1))
    a, b = COAST_LINE[i], COAST_LINE[i + 1]
    return a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])


@dataclass
class Pose:
    """One trial: truth, what the sensors report, and the prior."""
    site: str
    lat: float
    lon: float
    agl: float
    heading: float
    roll: float
    pitch: float
    speed: float
    alt_meas: float
    alt_sigma: float
    att_err: tuple          # (roll, pitch, heading) error of the measured attitude, deg
    prior: tuple
    hfov_factor: float = 1.0    # stated field of view / true field of view


TURN_BANK_DEG = 20.0        # timing-offset conditions: a coordinated turn at this bank


def make_pose(i: int, site: str = "mixed", agl: float = 400.0, prior_m=(100.0, 250.0),
              heading_err_deg: Optional[float] = None, tilt_deg: Optional[float] = None,
              alt_err: Optional[float] = None, speed: float = 25.0,
              hfov_err: Optional[float] = None, timing_s: Optional[float] = None) -> Pose:
    """Frame i's pose (seeded by i, so every condition sees the same poses).

    Defaults are a realistic small-error flight: tilt 0-5 deg, IMU attitude error
    0.5 deg (roll/pitch) and 2 deg (heading) 1-sigma, barometric height 3 % 1-sigma,
    prior 100-250 m off in a random direction.

    hfov_err: relative error of the configured field of view (+0.1 = states 10 % wider).
    timing_s: the attitude is read timing_s away from the exposure while the vehicle is in
    a coordinated turn (bank TURN_BANK_DEG at `speed`): the heading is off by the turn rate
    x timing_s (the bank does not change in a steady turn)."""
    rng = np.random.default_rng(1000 + i)
    if site == "mixed":
        site = ("urban", "farmland")[i % 2]
    if site == "coast":
        lat, lon = _coast_point(rng)
    else:
        c_lat, c_lon, rad = SITES[site]
        a, r = rng.uniform(0, 2 * math.pi), rad * math.sqrt(rng.uniform(0, 1))
        lat, lon = offset(c_lat, c_lon, r * math.cos(a), r * math.sin(a))
    heading = float(rng.uniform(0, 360))
    t = float(rng.uniform(0, 5)) if tilt_deg is None else float(tilt_deg)
    ta = rng.uniform(0, 2 * math.pi)
    roll, pitch = t * math.cos(ta), t * math.sin(ta)
    att_err = (float(rng.normal(0, 0.5)), float(rng.normal(0, 0.5)), float(rng.normal(0, 2.0)))
    if heading_err_deg is not None:
        att_err = (att_err[0], att_err[1], float(heading_err_deg) * (1 if rng.uniform() < 0.5 else -1))
    rel = float(rng.normal(0, 0.03)) if alt_err is None else float(alt_err)
    pm = float(rng.uniform(*prior_m)) if isinstance(prior_m, tuple) else float(prior_m)
    pa = rng.uniform(0, 2 * math.pi)
    prior = offset(lat, lon, pm * math.cos(pa), pm * math.sin(pa))
    if timing_s is not None:
        roll, pitch = TURN_BANK_DEG, 0.0
        rate = math.degrees(9.81 * math.tan(math.radians(TURN_BANK_DEG)) / speed)
        att_err = (att_err[0], att_err[1], att_err[2] + rate * float(timing_s))
    return Pose(site, lat, lon, agl, heading, roll, pitch, speed, agl * (1 + rel),
                max(0.03, abs(rel)) * agl, att_err, prior,
                1.0 + (float(hfov_err) if hfov_err is not None else 0.0))


# ── thermal-like rendering and conditions ──────────────────────────────────────

def agc(g: np.ndarray, lo_pct: float = 1.0, hi_pct: float = 99.0) -> np.ndarray:
    """Camera automatic gain: percentile stretch to [0, 1] (min-max with 0 / 100)."""
    lo, hi = np.percentile(g, (lo_pct, hi_pct))
    return np.clip((g - lo) / max(hi - lo, 1e-4), 0, 1)


def to_thermal(bgr: np.ndarray) -> np.ndarray:
    """Scene 'temperature' in [0, 1] from the visible render: the grey level (what the
    simulator uses). Not physics: real LWIR contrast follows materials, not albedo."""
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0


def material_remap(bgr: np.ndarray) -> np.ndarray:
    """A night-emission heuristic: man-made grey surfaces warm, vegetation cool, water
    warm (it keeps the day's heat). Tests a domain shift, it is not a radiometric model."""
    f = bgr.astype(np.float32) / 255.0
    b, g, r = f[..., 0], f[..., 1], f[..., 2]
    luma = 0.114 * b + 0.587 * g + 0.299 * r
    mx, mn = f.max(axis=2), f.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1e-3)
    veg = np.clip((g - r) / np.maximum(g + r, 1e-3) * 6, 0, 1)
    water = np.clip((b - r) / np.maximum(b + r, 1e-3) * 4, 0, 1) * (luma < 0.4)
    t = 0.45 + 0.6 * (1 - sat) * luma - 0.35 * veg - 0.15 * sat + 0.5 * water
    return np.clip(t, 0, 1).astype(np.float32)


def _vignette(h, w, k):
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = ((xx - w / 2) ** 2 + (yy - h / 2) ** 2) / ((w / 2) ** 2 + (h / 2) ** 2)
    return (1.0 - k * r2).astype(np.float32)


def _smooth_noise(rng, h, w, scale):
    n = rng.normal(0, 1, (max(2, h // scale), max(2, w // scale))).astype(np.float32)
    n = cv2.resize(n, (w, h), interpolation=cv2.INTER_CUBIC)
    return (n - n.mean()) / max(n.std(), 1e-6)


def _blobs(rng, h, w, n, r_px, val, img):
    for _ in range(n):
        x, y = int(rng.integers(0, w)), int(rng.integers(0, h))
        r = float(rng.uniform(*r_px))
        cv2.circle(img, (x, y), max(1, int(round(r))), float(val), -1, lineType=cv2.LINE_AA)
    return img


@dataclass
class Ctx:
    """What a condition can read: the pose, the ground size of a pixel, the RNG."""
    pose: Pose
    gsd: float
    rng: np.random.Generator


def finish(t: np.ndarray, ctx: Ctx, noise=0.02, vignette=0.15, agc_pct=(1.0, 99.0)) -> np.ndarray:
    """Sensor: lens shading, temporal noise (NETD), AGC, 8-bit."""
    h, w = t.shape
    t = t * _vignette(h, w, vignette) + ctx.rng.normal(0, noise, t.shape).astype(np.float32)
    t = agc(t, *agc_pct)
    return t


def smear(t: np.ndarray, ctx: Ctx) -> np.ndarray:
    """Microbolometer lag: an exponential smear along the track (image up = forward)."""
    px = ctx.pose.speed * TAU_S / ctx.gsd
    n = int(min(math.ceil(3 * px), 80))
    if n < 1 or px < 0.2:
        return t
    k = np.exp(-np.arange(n + 1) / max(px, 1e-3)).astype(np.float32)
    ker = np.zeros((2 * n + 1, 1), np.float32)
    ker[n:, 0] = k / k.sum()           # past positions lie behind (below) the current one
    return cv2.filter2D(t, -1, ker)


# condition name → function(scene_temperature, ctx, bgr) → final [0, 1] image
def c_nominal(t, ctx, bgr):
    return finish(smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx), ctx)


def c_polarity(t, ctx, bgr):
    return 1.0 - c_nominal(t, ctx, bgr)


def c_low_contrast(t, ctx, bgr, k=0.12):
    # crossover: the scene's temperature differences shrink, the sensor noise does not
    t = 0.5 + (t - t.mean()) * k
    return finish(smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx), ctx)


def c_low_contrast_05(t, ctx, bgr):
    return c_low_contrast(t, ctx, bgr, k=0.05)


def c_noise_high(t, ctx, bgr):
    return finish(smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx), ctx, noise=0.08)


def c_fpn(t, ctx, bgr):
    """Fixed-pattern noise left by a stale NUC: column / row offsets, pixel gain spread."""
    h, w = t.shape
    rng = np.random.default_rng(7)                 # the same pattern on every frame
    col = rng.normal(0, 0.06, (1, w)).astype(np.float32)
    row = rng.normal(0, 0.02, (h, 1)).astype(np.float32)
    gain = rng.normal(1, 0.05, (h, w)).astype(np.float32)
    t = smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx)
    return finish(t * gain + col + row, ctx)


def c_vignette_strong(t, ctx, bgr):
    h, w = t.shape
    yy, xx = np.mgrid[0:h, 0:w]
    narcissus = 0.25 * np.exp(-((xx - w / 2) ** 2 + (yy - h / 2) ** 2) / (2 * (0.25 * w) ** 2))
    return finish(smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx) + narcissus.astype(np.float32),
                  ctx, vignette=0.6)


def c_agc_jump(t, ctx, bgr):
    # a gain / level jump between frames: part of the scene clips
    g = c_nominal(t, ctx, bgr)
    a = float(ctx.rng.choice([0.5, 1.8])); b = float(ctx.rng.uniform(-0.3, 0.3))
    return np.clip((g - 0.5) * a + 0.5 + b, 0, 1)


def _blur_at(speed):
    def f(t, ctx, bgr):
        ctx.pose.speed = speed
        return c_nominal(t, ctx, bgr)
    return f


def c_hotspots(t, ctx, bgr, minmax=False):
    """Vehicles (small, hot), chimneys / flares (large, saturated) — and the AGC's reaction."""
    h, w = t.shape
    t = t.copy()
    m = 0.06 * 0.96 / ctx.gsd                       # ~6 cm/px scale factor → vehicle ~4 m
    _blobs(ctx.rng, h, w, 60, (max(1.0, 2 * m), max(1.5, 3 * m)), 1.6, t)
    _blobs(ctx.rng, h, w, 4, (6, 14), 3.0, t)
    t = smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx)
    return finish(t, ctx, agc_pct=(0.0, 100.0) if minmax else (1.0, 99.0))


def c_hotspots_minmax(t, ctx, bgr):
    return c_hotspots(t, ctx, bgr, minmax=True)


def c_fog(t, ctx, bgr, trans=0.35):
    """Fog / haze / rain: scene contrast times the transmission, plus path radiance."""
    t = t * trans + (1 - trans) * 0.5
    return finish(smear(cv2.GaussianBlur(t, (0, 0), 1.6), ctx), ctx)


def c_fog_dense(t, ctx, bgr):
    return c_fog(t, ctx, bgr, trans=0.12)


def c_rain(t, ctx, bgr):
    h, w = t.shape
    g = c_fog(t, ctx, bgr, trans=0.3)
    streak = np.zeros((h, w), np.float32)
    for _ in range(400):
        x, y = int(ctx.rng.integers(0, w)), int(ctx.rng.integers(0, h))
        cv2.line(streak, (x, y), (x + 3, y + 18), 1.0, 1)
    return np.clip(g * (1 - 0.35 * streak) , 0, 1)


def _clouds(cover):
    def f(t, ctx, bgr):
        """Clouds below the aircraft: cold (dark in white-hot), soft-edged, `cover` of the frame."""
        h, w = t.shape
        n = _smooth_noise(ctx.rng, h, w, 64) + 0.5 * _smooth_noise(ctx.rng, h, w, 16)
        thr = np.quantile(n, 1 - cover)
        m = np.clip((n - thr) / 0.4, 0, 1).astype(np.float32)
        cloud = 0.05 + 0.03 * _smooth_noise(ctx.rng, h, w, 8)
        t = smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx)
        return finish(t * (1 - m) + cloud * m, ctx)
    return f


def c_birds_planes(t, ctx, bgr):
    h, w = t.shape
    t = smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx).copy()
    _blobs(ctx.rng, h, w, 25, (1, 3), 1.2, t)                         # birds
    x, y = int(ctx.rng.integers(80, w - 80)), int(ctx.rng.integers(80, h - 80))
    a = float(ctx.rng.uniform(0, 180))                                  # a light aircraft below
    box = cv2.boxPoints(((x, y), (90, 14), a)).astype(np.int32)
    cv2.fillPoly(t, [box], 1.3)
    box = cv2.boxPoints(((x, y), (14, 70), a)).astype(np.int32)
    cv2.fillPoly(t, [box], 1.3)
    return finish(t, ctx)


def c_occluded_corner(t, ctx, bgr, share=0.18):
    """A part of the aircraft (gear, pod) in a corner: warm, nearly uniform, ~share of the frame."""
    h, w = t.shape
    g = c_nominal(t, ctx, bgr)
    poly = np.array([[0, h], [0, int(h * (1 - 2 * share))], [int(w * 2 * share * h / w * 1.0), h]])
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [poly.astype(np.int32)], 1)
    g[m > 0] = 0.92 + 0.02 * ctx.rng.normal(0, 1, int(m.sum()))
    return np.clip(g, 0, 1)


def c_material_remap(t, ctx, bgr):
    return finish(smear(cv2.GaussianBlur(material_remap(bgr), (0, 0), 1.0), ctx), ctx)


def c_flat_water(t, ctx, bgr):
    """LWIR does not see through water: the seabed the satellite shows becomes one
    surface temperature (slightly warmer than the land at night)."""
    f = bgr.astype(np.float32)
    water = (f[..., 0] > f[..., 2] + 12) & (f.sum(axis=2) < 330)
    water = cv2.morphologyEx(water.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0
    t = t.copy()
    t[water] = float(np.median(t)) + 0.1
    return c_nominal(t, ctx, bgr)


def c_pure_noise(t, ctx, bgr):
    return agc(cv2.GaussianBlur(ctx.rng.normal(0.5, 0.2, t.shape).astype(np.float32), (0, 0), 1.0))


def c_uniform(t, ctx, bgr):
    return finish(np.full_like(t, 0.5), ctx)


# ── 2026-10-19 additions: sensor defects, AGC, weather, distractors, low-light visible ──

def c_dead_pixels(t, ctx, bgr):
    """Dead / stuck pixels after AGC: 0.5 % stuck black or white, 4 dead columns, one
    dead 3 px cluster per 50 000 px (a real core ships with a bad-pixel map; this is the
    case where it is stale)."""
    g = c_nominal(t, ctx, bgr).copy()
    h, w = g.shape
    rng = np.random.default_rng(11)                # the same defects on every frame
    n = int(0.005 * h * w)
    ys, xs = rng.integers(0, h, n), rng.integers(0, w, n)
    g[ys, xs] = rng.choice([0.0, 1.0], n)
    for x in rng.integers(0, w, 4):
        g[:, x] = float(rng.choice([0.02, 0.98]))
    for _ in range(max(1, h * w // 50_000)):
        x, y = int(rng.integers(0, w - 3)), int(rng.integers(0, h - 3))
        g[y:y + 3, x:x + 3] = 1.0
    return g


def c_nuc_drift(t, ctx, bgr):
    """NUC drift long after the last shutter calibration: a smooth offset bowl / gradient
    across the frame (housing warming) of 40 % of the scene range, plus column stripes."""
    h, w = t.shape
    rng = np.random.default_rng(13)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    bowl = ((xx - 0.3 * w) ** 2 + (yy - 0.6 * h) ** 2) / float(w * w)
    col = rng.normal(0, 0.08, (1, w)).astype(np.float32)
    t = smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx)
    rng_scene = float(np.percentile(t, 99) - np.percentile(t, 1))
    return finish(t + 0.4 * rng_scene * bowl / max(float(bowl.max()), 1e-6) + col * rng_scene, ctx)


def _plateau_eq(counts: np.ndarray, bins: int = 4096, plateau: float = 0.004) -> np.ndarray:
    """Plateau histogram equalisation (the usual 14-bit -> 8-bit thermal AGC): each
    histogram bin is clipped at `plateau` of the pixels before the cumulative mapping."""
    lo, hi = float(counts.min()), float(counts.max())
    idx = np.clip(((counts - lo) / max(hi - lo, 1e-6) * (bins - 1)).astype(np.int32), 0, bins - 1)
    hist = np.bincount(idx.ravel(), minlength=bins).astype(np.float64)
    hist = np.minimum(hist, plateau * counts.size)
    cdf = np.cumsum(hist)
    cdf /= max(cdf[-1], 1.0)
    return cdf[idx].astype(np.float32)


def c_agc_14bit_plateau(t, ctx, bgr):
    """14-bit counts (scene + hot vehicles + one fire), plateau-equalised to 8 bit: local
    contrast stretched where the histogram is dense, grey levels no longer linear."""
    h, w = t.shape
    t = t.copy()
    m = 0.06 * 0.96 / ctx.gsd
    _blobs(ctx.rng, h, w, 40, (max(1.0, 2 * m), max(1.5, 3 * m)), 1.6, t)
    _blobs(ctx.rng, h, w, 1, (8, 16), 6.0, t)
    t = smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx)
    t = t * _vignette(h, w, 0.15) + ctx.rng.normal(0, 0.02, t.shape).astype(np.float32)
    counts = np.round(np.clip(t / 6.0, 0, 1) * 16383.0)
    return _plateau_eq(counts)


def c_agc_linear_fire(t, ctx, bgr):
    """Linear min-max AGC 14 -> 8 bit with a fire in view: the fire takes the top of the
    range and the whole ground is squeezed into ~1/20 of the grey levels (quantised)."""
    h, w = t.shape
    t = t.copy()
    _blobs(ctx.rng, h, w, 2, (6, 14), 20.0, t)
    t = smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx)
    t = t * _vignette(h, w, 0.15) + ctx.rng.normal(0, 0.02, t.shape).astype(np.float32)
    counts = np.round(np.clip(t / 20.0, 0, 1) * 16383.0)
    g = agc(counts, 0.0, 100.0)
    return np.round(g * 255.0) / 255.0               # the 8-bit quantisation is the point


def c_fires(t, ctx, bgr):
    """1-3 fires (saturated, 15-40 m) with a warm smoke plume drifting downwind; percentile AGC."""
    h, w = t.shape
    t = t.copy()
    plume = np.zeros((h, w), np.float32)
    for _ in range(int(ctx.rng.integers(1, 4))):
        x, y = int(ctx.rng.integers(40, w - 40)), int(ctx.rng.integers(40, h - 40))
        r = max(3, int(round(float(ctx.rng.uniform(15, 40)) / 2 / ctx.gsd)))
        cv2.circle(plume, (x, y), r, 1.0, -1)
        cv2.circle(t, (x, y), r, 5.0, -1, lineType=cv2.LINE_AA)
    k = np.zeros((1, 81), np.float32)
    k[0, 40:] = np.exp(-np.arange(41) / 15.0)
    plume = cv2.filter2D(plume, -1, k / k.sum())
    t = t + 0.6 * cv2.GaussianBlur(plume, (0, 0), 6.0)
    return finish(smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx), ctx)


def c_city_hot(t, ctx, bgr):
    """A city at night: 400 hot points (vehicles, lit windows, AC units) and 10 chimneys."""
    h, w = t.shape
    t = t.copy()
    m = 0.06 * 0.96 / ctx.gsd
    _blobs(ctx.rng, h, w, 400, (max(1.0, 1.5 * m), max(1.5, 3 * m)), 1.5, t)
    _blobs(ctx.rng, h, w, 10, (3, 7), 3.0, t)
    return finish(smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx), ctx)


def c_lights_drones(t, ctx, bgr):
    """Hot points that do not belong to the ground: 3 drones (small hot crosses), aircraft
    navigation lights / landing light (bright points), 40 birds."""
    h, w = t.shape
    t = smear(cv2.GaussianBlur(t, (0, 0), 1.0), ctx).copy()
    for _ in range(3):
        x, y = int(ctx.rng.integers(20, w - 20)), int(ctx.rng.integers(20, h - 20))
        s = int(ctx.rng.integers(5, 12))
        cv2.line(t, (x - s, y - s), (x + s, y + s), 1.8, 2)
        cv2.line(t, (x - s, y + s), (x + s, y - s), 1.8, 2)
    _blobs(ctx.rng, h, w, 8, (1, 2), 4.0, t)
    _blobs(ctx.rng, h, w, 40, (1, 3), 1.2, t)
    return finish(t, ctx)


def c_haze_humid(t, ctx, bgr):
    """Humid haze: transmission 0.55 with a slow 20 % variation across the frame, path
    radiance, a slightly softer image."""
    h, w = t.shape
    tr = 0.55 * (1 + 0.2 * _smooth_noise(ctx.rng, h, w, 128))
    t = t * tr + (1 - tr) * 0.55
    return finish(smear(cv2.GaussianBlur(t, (0, 0), 2.0), ctx), ctx)


def _lowlight_visible(photons_white: float, lights: bool = True):
    def f(t, ctx, bgr):
        """A VISIBLE camera at night (the Insta360 class, not thermal): the scene's
        reflectance times a moonlight level, shot noise (Poisson, `photons_white`
        electrons for a white surface per exposure), read noise 2 e-, street / window
        lights on man-made surfaces (grey, bright in the day image), auto-exposure on the
        99th percentile, gamma 2.2, 8 bit. Grey output (the night chain takes a grey image)."""
        h, w = t.shape
        f32 = bgr.astype(np.float32) / 255.0
        luma = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
        sat = (f32.max(axis=2) - f32.min(axis=2)) / np.maximum(f32.max(axis=2), 1e-3)
        e = luma * photons_white
        if lights:
            built = ((sat < 0.18) & (luma > 0.45)).astype(np.float32)
            cand = np.flatnonzero(built.ravel())
            if cand.size:
                pick = ctx.rng.choice(cand, size=min(cand.size, int(0.002 * h * w)), replace=False)
                lamp = np.zeros(h * w, np.float32)
                lamp[pick] = 1.0
                lamp = cv2.GaussianBlur(lamp.reshape(h, w), (0, 0), 2.5)
                e = e + lamp / max(float(lamp.max()), 1e-6) * 60.0 * max(photons_white, 5.0)
        e = ctx.rng.poisson(np.clip(e, 0, None)).astype(np.float32) + ctx.rng.normal(0, 2.0, e.shape)
        e = smear(e, ctx)
        g = np.clip(e / max(float(np.percentile(e, 99)), 1e-3), 0, 1) ** (1 / 2.2)
        return np.round(g * 255.0) / 255.0
    return f


@dataclass
class Condition:
    name: str
    group: str
    look: Callable = c_nominal
    pose_kw: Dict = field(default_factory=dict)
    no_info: bool = False             # the frame carries no position: any accept is wrong
    note: str = ""


CONDITIONS: List[Condition] = [
    Condition("nominal", "baseline"),
    Condition("polarity_inverted", "thermal", c_polarity, note="black-hot vs white-hot"),
    Condition("low_contrast_x0.12", "thermal", c_low_contrast, note="crossover hours"),
    Condition("low_contrast_x0.05", "thermal", c_low_contrast_05),
    Condition("noise_high", "thermal", c_noise_high, note="NETD 4x"),
    Condition("fpn_stale_nuc", "thermal", c_fpn),
    Condition("vignette_narcissus", "thermal", c_vignette_strong),
    Condition("agc_jump", "thermal", c_agc_jump),
    Condition("material_remap", "thermal", c_material_remap, note="heuristic night emission"),
    Condition("speed_10mps", "blur", _blur_at(10)),
    Condition("speed_30mps", "blur", _blur_at(30)),
    Condition("speed_60mps", "blur", _blur_at(60)),
    Condition("speed_100mps", "blur", _blur_at(100)),
    Condition("speed_100mps_h150", "blur", _blur_at(100), dict(agl=150.0)),
    Condition("hotspots", "lights", c_hotspots),
    Condition("hotspots_minmax_agc", "lights", c_hotspots_minmax),
    Condition("fog_t0.35", "weather", c_fog),
    Condition("fog_t0.12", "weather", c_fog_dense),
    Condition("rain", "weather", c_rain),
    Condition("clouds_30pct", "weather", _clouds(0.30)),
    Condition("clouds_60pct", "weather", _clouds(0.60)),
    Condition("birds_plane", "objects", c_birds_planes),
    Condition("corner_occluded", "objects", c_occluded_corner),
    *[Condition(f"agl_{h:.0f}m", "geometry", pose_kw=dict(agl=h)) for h in (150, 250, 350, 600, 1000, 1500)],
    *[Condition(f"heading_err_{e}deg", "geometry", pose_kw=dict(heading_err_deg=e)) for e in (5, 10, 20, 30)],
    *[Condition(f"tilt_{t}deg", "geometry", pose_kw=dict(tilt_deg=t)) for t in (10, 20)],
    *[Condition(f"height_err_{e:+.0%}", "geometry", pose_kw=dict(alt_err=e)) for e in (-0.2, -0.1, 0.1, 0.2)],
    *[Condition(f"prior_{p:.0f}m", "geometry", pose_kw=dict(prior_m=p)) for p in (50, 500, 750, 1000)],
    *[Condition(f"terrain_{s}", "terrain", pose_kw=dict(site=s)) for s in ("urban", "farmland", "coast")],
    Condition("terrain_coast_flat_sea", "terrain", c_flat_water, dict(site="coast"),
              note="sea as one temperature (LWIR)"),
    Condition("terrain_sea", "false-accept", c_flat_water, dict(site="sea"), no_info=True),
    Condition("terrain_desert", "false-accept", pose_kw=dict(site="desert")),
    Condition("pure_noise", "false-accept", c_pure_noise, no_info=True),
    Condition("uniform_frame", "false-accept", c_uniform, no_info=True),
    # 2026-10-19 additions
    Condition("dead_pixels", "thermal", c_dead_pixels, note="stale bad-pixel map"),
    Condition("nuc_drift", "thermal", c_nuc_drift, note="offset bowl 40 % + stripes"),
    Condition("agc_14bit_plateau", "thermal", c_agc_14bit_plateau, note="plateau equalisation"),
    Condition("agc_linear_fire", "thermal", c_agc_linear_fire, note="min-max AGC, fire in view"),
    Condition("haze_humid", "weather", c_haze_humid),
    Condition("clouds_85pct", "weather", _clouds(0.85)),
    Condition("clouds_100pct", "weather", _clouds(1.0), no_info=True),
    Condition("fires", "objects", c_fires),
    Condition("lights_drones", "objects", c_lights_drones),
    Condition("city_hot", "terrain", c_city_hot, dict(site="urban"), note="400 hot points"),
    Condition("terrain_olives", "terrain", pose_kw=dict(site="olives"), note="repeated pattern"),
    Condition("heading_err_45deg", "geometry", pose_kw=dict(heading_err_deg=45)),
    Condition("tilt_0deg", "geometry", pose_kw=dict(tilt_deg=0)),
    Condition("tilt_15deg", "geometry", pose_kw=dict(tilt_deg=15)),
    *[Condition(f"height_err_{e:+.0%}", "geometry", pose_kw=dict(alt_err=e)) for e in (-0.4, 0.4)],
    *[Condition(f"hfov_err_{e:+.0%}", "geometry", pose_kw=dict(hfov_err=e)) for e in (-0.1, -0.05, 0.05, 0.1)],
    *[Condition(f"timing_{s}s_turn", "geometry", pose_kw=dict(timing_s=s)) for s in (0.2, 0.5, 1.5)],
    Condition("visible_fullmoon", "visible-night", _lowlight_visible(60.0), dict(site="urban")),
    Condition("visible_quartermoon", "visible-night", _lowlight_visible(8.0), dict(site="urban")),
    Condition("visible_starlight", "visible-night", _lowlight_visible(0.5), dict(site="urban")),
    Condition("visible_fullmoon_rural", "visible-night", _lowlight_visible(60.0), dict(site="farmland")),
]


# ── the run ─────────────────────────────────────────────────────────────────────

def sigma_stated(alt_m: float, conf: float, shift_px: Optional[float], alt_sigma: Optional[float]) -> float:
    """The night subscriber's stated sigma (simulator-calibrated), outside the 10 s after GPS loss."""
    sig = max(8.0, 0.025 * alt_m)
    if conf < 0.995 or (shift_px is not None and shift_px > 20.0):
        sig *= 2.5
    if alt_sigma is not None:
        sig = math.hypot(sig, 0.1 * alt_sigma)
    return sig


def run_condition(cond: Condition, loc, cam: _GeomCamera, fb: FrameBuilder, n: int,
                  save_dir: Optional[Path] = None) -> dict:
    rows = []
    for i in range(n):
        pose = make_pose(i, **cond.pose_kw)
        q_true = quat_rpy(pose.roll, pose.pitch, pose.heading)
        bgr, ok = cam.render(pose.lat, pose.lon, pose.agl, q_true)
        gsd = 2 * pose.agl * math.tan(math.radians(HFOV_DEG / 2)) / SIZE[0]
        ctx = Ctx(pose, gsd, np.random.default_rng(50_000 + i))
        g = cond.look(to_thermal(bgr), ctx, bgr)
        frame = cv2.cvtColor((np.clip(g, 0, 1) * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        e = pose.att_err
        q_meas = quat_rpy(pose.roll + e[0], pose.pitch + e[1], pose.heading + e[2])
        img, meta = fb.build(frame, i, int(time.time() * 1e9), q_meas, "imu",
                             altitude=(pose.alt_meas, pose.alt_sigma, "baro"))
        if save_dir is not None and i < 3:
            cv2.imwrite(str(save_dir / f"{cond.name}_{i}.jpg"), img)
        t0 = time.perf_counter()
        r = loc.localize(img, pose.prior[0], pose.prior[1], altitude_m=meta["altitude_m"],
                         hfov_deg=meta["camera_hfov_deg"] * pose.hfov_factor, heading_deg=meta["heading_deg"],
                         **({"heading_retry_deg": HEADING_RETRY} if HEADING_RETRY else {}),
                         **({"height_retry": HEIGHT_RETRY} if HEIGHT_RETRY else {}))
        dt = (time.perf_counter() - t0) * 1000
        acc = bool(r.get("success"))
        err = dist_m((r["lat"], r["lon"]), (pose.lat, pose.lon)) if acc else None
        sig = (r.get("sigma_m") or sigma_stated(pose.alt_meas, float(r.get("conf", 0.0)), r.get("rms_px"),
                                                pose.alt_sigma)) if acc else None
        rows.append(dict(cond=cond.name, i=i, site=pose.site, agl=pose.agl, accepted=acc, err_m=err, sigma_m=sig,
                         conf=r.get("conf"), shift_px=r.get("rms_px"), reason=r.get("reason", ""),
                         prior_err_m=dist_m(pose.prior, (pose.lat, pose.lon)), dt_ms=dt,
                         coverage=(r.get("query") or {}).get("coverage"),
                         recheck_m=r.get("recheck_m"), heading_fix=r.get("heading_correction_deg"),
                         **{f"v_{k}": v for k, v in (r.get("verify") or
                                                     dict(ncc=None)).items()},
                         wrong=acc and (cond.no_info or err > WRONG_M),
                         wrong3s=acc and (cond.no_info or err > WRONG_HARD_M or err > 3 * sig)))
    return summarize(cond, rows), rows


def summarize(cond: Condition, rows: List[dict]) -> dict:
    n = len(rows)
    acc = [r for r in rows if r["accepted"]]
    errs = sorted(r["err_m"] for r in acc)
    in3 = [r for r in acc if r["err_m"] <= 3 * r["sigma_m"]]
    refused = {}
    for r in rows:
        if not r["accepted"]:
            key = (r["reason"] or "rejected").split("(")[0].split(" — ")[0].strip()[:40]
            refused[key] = refused.get(key, 0) + 1
    return dict(
        condition=cond.name, group=cond.group, n=n, accepted=len(acc),
        match_rate=len(acc) / n if n else 0.0,
        median_m=statistics.median(errs) if errs else None,
        p90_m=float(np.percentile(errs, 90)) if errs else None,
        max_m=max(errs) if errs else None,
        wrong=sum(r["wrong"] for r in rows),
        wrong_rate=sum(r["wrong"] for r in rows) / n if n else 0.0,
        wrong3s=sum(r["wrong3s"] for r in rows),
        within_3sigma=len(in3) / len(acc) if acc else None,
        ms_median=statistics.median(r["dt_ms"] for r in rows),
        refused=refused)


def _fmt(v, f="{:.0f}"):
    return "-" if v is None else f.format(v)


def print_table(summaries: List[dict]):
    print(f"\n{'condition':24s} {'group':12s} {'match':>7s} {'med':>5s} {'p90':>5s} {'max':>6s} "
          f"{'wrong':>6s} {'w100|3σ':>7s} {'in3σ':>5s} {'ms':>5s}  refused")
    for s in summaries:
        print(f"{s['condition']:24s} {s['group']:12s} {s['accepted']:3d}/{s['n']:<3d} "
              f"{_fmt(s['median_m']):>5s} {_fmt(s['p90_m']):>5s} {_fmt(s['max_m']):>6s} "
              f"{s['wrong']:3d}/{s['n']:<2d} {s['wrong3s']:7d} {_fmt(s['within_3sigma'], '{:.0%}'):>5s} "
              f"{s['ms_median']:5.0f}  {'; '.join(f'{k}:{v}' for k, v in s['refused'].items())}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=24, help="frames per condition")
    ap.add_argument("--only", default="", help="comma-separated condition names or groups")
    ap.add_argument("--device", default=None, help="cuda | cpu (default: cuda if available)")
    ap.add_argument("--csv", default="", help="write every frame's result here")
    ap.add_argument("--save-frames", default="", help="save the first 3 frames of each condition here")
    ap.add_argument("--night-pkg", default="",
                    help="another night_pkg source tree to test (e.g. an older commit, for before/after)")
    ap.add_argument("--min-ncc", type=float, default=None, help="override the map-check correlation gate")
    ap.add_argument("--recheck-max", type=float, default=None,
                    help="override the second-centre re-check gate (m)")
    ap.add_argument("--heading-retry", default="",
                    help="heading offsets (deg, comma-separated) retried when the map check fails")
    ap.add_argument("--featureless-mask", action="store_true",
                    help="leave cloud / calm water out of the query (NightLocalizer mask_featureless, off by default)")
    ap.add_argument("--height-retry", default="",
                    help="relative height changes (e.g. 0.1,-0.1) retried after the heading offsets")
    a = ap.parse_args()
    global HEADING_RETRY, HEIGHT_RETRY
    HEADING_RETRY = tuple(float(x) for x in a.heading_retry.split(",") if x.strip())
    HEIGHT_RETRY = tuple(float(x) for x in a.height_retry.split(",") if x.strip())
    if a.night_pkg:
        sys.path.insert(0, str(Path(a.night_pkg).resolve()))
    mbtiles = os.environ.get("NAVERA_MBTILES", os.path.expanduser("~/navera_data_map.mbtiles"))
    sthn = os.environ.get("NAVERA_STHN_DIR", os.path.expanduser("~/navera_data/night_pkg/STHN"))
    weights = os.environ.get("NAVERA_STHN_WEIGHTS", os.path.join(sthn, "weights/one_stage/model.safetensors"))

    import torch
    from night_pkg.nodes.night_localizer import NightLocalizer
    conds = CONDITIONS
    if a.only:
        keys = set(a.only.split(","))
        conds = [c for c in CONDITIONS if c.name in keys or c.group in keys]
    lens = dict(model="pinhole", image_width=SIZE[0], image_height=SIZE[1], distortion=[],
                camera_matrix=CameraModel.ideal(HFOV_DEG, SIZE).K.ravel().tolist())
    tiles = Tiles(mbtiles)
    cam = _GeomCamera(lens, tiles.get)
    fb = FrameBuilder(CameraModel.ideal(HFOV_DEG, SIZE), camera_type="thermal")
    # omitted: the localizer's defaults; <= -1: that gate off (measure only)
    gates = {k: (v if v > -1 else None) for k, v in (("min_match_ncc", a.min_ncc),
                                                   ("recheck_max_m", a.recheck_max))
             if v is not None}
    loc = NightLocalizer(sthn, weights, mbtiles, device=a.device, mask_featureless=a.featureless_mask, **gates)
    save = Path(a.save_frames) if a.save_frames else None
    if save:
        save.mkdir(parents=True, exist_ok=True)
    summaries, all_rows = [], []
    try:
        for c in conds:
            s, rows = run_condition(c, loc, cam, fb, a.n, save)
            summaries.append(s)
            all_rows += rows
            print(f"{c.name}: {s['accepted']}/{s['n']} accepted, median {_fmt(s['median_m'])} m, "
                  f"max {_fmt(s['max_m'])} m, wrong {s['wrong']}", flush=True)
    finally:
        del loc
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    print_table(summaries)
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)


if __name__ == "__main__":
    main()
