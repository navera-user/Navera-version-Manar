#!/usr/bin/env python3
"""Stress test of the all-sky celestial solver (allsky.locate) under realistic night conditions.
SIMULATION ONLY: every number this prints comes from synthetic frames, never from the real camera.

    PYTHONPATH=.:cn_pkg:navera_common python3 -m navera_tools.sim.celestial360_conditions \
        [--seeds 6] [--only name,name] [--workers 5] [--json out.json]

The scene is the selftest360 sky (Yale catalogue, refraction, the standing Insta360's two
equidistant fisheye circles, mag-1 star = 900 counts on a 10 +- 3 background), drawn in layers so
that effects can be added one at a time and combined:

    frame = stars x transmission + background + noise   (then clip to 8 bits, optional JPEG)

Each condition is run on several seeds (time of night, heading, tilt, effect placement). A frame
counts as *solved* when the solver returns a fix, *wrong* when that fix is more than WRONG_KM from
the truth (a confident wrong answer, worse than no answer), and the junk frames (no catalogue stars
in them at all) count every fix as a false accept. The solver gets the true focal length (as after
the first night's calibration) except in the focal-length conditions, which use the server's
first-solve search.
"""
import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg"), HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from navera_tools.field import allsky, sky360  # noqa: E402

LAT, LON = 36.8, 10.2                     # Tunis area; the UTC hours below are night there in October
WRONG_KM = 50.0
F_SCALE_SEARCH = (0.90, 0.95, 1.0, 1.05, 1.10)   # the server's first-solve focal search (server.F_SCALE_SEARCH)
EXPOSURE_S = 1.0 / 30.0
ATTITUDE_SIGMA_360_DEG = 0.3                     # server.ATTITUDE_SIGMA_360_DEG (not imported: server pulls in cv2/http)


def rot(axis, deg):
    """Rotation matrix about an axis (Rodrigues)."""
    a = np.asarray(axis, float) / np.linalg.norm(axis)
    t = math.radians(deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * K @ K


def enu(alt_deg, az_deg):
    a, A = np.radians(alt_deg), np.radians(az_deg)
    return np.stack([np.cos(a) * np.sin(A), np.cos(a) * np.cos(A), np.sin(a)], axis=-1)


@dataclass
class Condition:
    """One row of the table: scene parameters + effects (name -> parameter)."""
    name: str
    limit_mag: float = 3.0
    tilt_deg: Optional[float] = None          # None: N(0, 3) per axis like selftest360
    f_true: float = 1.0                       # true focal / model guess
    k1_true: float = 0.0
    centre_off_px: float = 0.0                # true circle centres moved by this much (random direction per lens)
    right_misalign_deg: float = 0.0           # right lens rotated against the left (about a random axis)
    search_focal: bool = False                # solver searches the focal length (server's first solve)
    up_err_deg: float = 0.0                   # accelerometer noise/bias: 'up' given to the solver off by this
    accel_g: float = 0.0                      # horizontal vehicle acceleration seen by the accelerometer (g)
    yaw_rate_dps: float = 0.0                 # the vehicle's turn rate meanwhile (the camera's gyro gate)
    clock_err_s: float = 0.0
    junk: bool = False                        # no catalogue star in the frame: any fix is a false accept
    lat: float = LAT                          # where the car is
    lon: float = LON
    mount_deg: float = 0.0                    # both lenses rotated against the IMU (lens-to-IMU mounting error)
    right_f_true: float = 1.0                 # right lens only: true focal / model (its f is a first guess)
    right_k1_true: float = 0.0
    right_centre_off_px: float = 0.0
    effects: Dict[str, float] = field(default_factory=dict)


class Scene:
    """A synthetic frame of the standing camera with its true geometry (for effects and truth)."""

    def __init__(self, cond: Condition, seed: int):
        import astropy.units as u
        from astropy.coordinates import AltAz, EarthLocation, SkyCoord
        from astropy.time import Time
        from sky_view import load_bsc5
        self.c, self.rng = cond, np.random.default_rng(1000 + seed)
        rng = self.rng
        hour = [20, 22, 0, 2, 21, 23, 1, 3][seed % 8]
        day = 17 if hour >= 12 else 18
        self.utc = f"2026-10-{day} {hour:02d}:{int(rng.integers(0, 60)):02d}:00"
        ra, dec, mag = load_bsc5(os.path.expanduser("~/.navera_sim"))
        keep = mag <= cond.limit_mag
        aa = SkyCoord(ra=ra[keep] * u.deg, dec=dec[keep] * u.deg).transform_to(
            AltAz(obstime=Time(self.utc), location=EarthLocation(lat=cond.lat * u.deg, lon=cond.lon * u.deg)))
        alt = aa.alt.deg + allsky.refraction_deg(aa.alt.deg)
        self.star_alt, self.star_v, self.star_mag = alt, enu(alt, aa.az.deg), mag[keep]
        heading = rng.uniform(0, 360)
        if cond.tilt_deg is None:
            tilt = rng.normal(0, 3, 2)
        else:
            d = rng.uniform(0, 2 * math.pi)
            tilt = cond.tilt_deg * np.array([math.cos(d), math.sin(d)])
        up, hd = np.array([0, 0, 1.0]), np.array([math.sin(math.radians(heading)), math.cos(math.radians(heading)), 0])
        self.R_world_imu = rot([1, 0, 0], tilt[0]) @ rot([0, 1, 0], tilt[1]) @ np.stack([up, hd, np.cross(up, hd)], axis=1)
        self.up_imu = self.R_world_imu.T @ up
        self.lenses = sky360.default_lenses()                  # the TRUE lenses (the solver keeps the defaults)
        for L in self.lenses:
            L.f *= cond.f_true
            L.k1 += cond.k1_true                          # error added to the lens model's own radial term
            if cond.centre_off_px:
                a = rng.uniform(0, 2 * math.pi)
                L.cx += cond.centre_off_px * math.cos(a)
                L.cy += cond.centre_off_px * math.sin(a)
        R = self.lenses[1]
        R.f *= cond.right_f_true
        R.k1 += cond.right_k1_true
        if cond.right_centre_off_px:
            a = rng.uniform(0, 2 * math.pi)
            R.cx += cond.right_centre_off_px * math.cos(a)
            R.cy += cond.right_centre_off_px * math.sin(a)
        if cond.mount_deg:
            ax = np.cross([1.0, 0, 0], rng.normal(size=3))          # a tilt of the lenses against the accelerometer
            for L in self.lenses:
                L.R_lens_imu = L.R_lens_imu @ rot(ax, cond.mount_deg)
        if cond.right_misalign_deg:
            ax = rng.normal(size=3)
            self.lenses[1].R_lens_imu = self.lenses[1].R_lens_imu @ rot(ax, cond.right_misalign_deg)
        self.H, self.W = 1920, 3840
        self._maps()

    # ── geometry ──────────────────────────────────────────────────────
    def _maps(self):
        """Altitude/azimuth (deg) of every pixel (computed every 4 px, then upsampled); NaN outside the circles."""
        import cv2
        s = 4
        yy, xx = np.mgrid[0:self.H:s, 0:self.W:s].astype(float)
        alt = np.full(xx.shape, np.nan)
        az = np.full(xx.shape, np.nan)
        for L in self.lenses:
            inside = np.hypot(xx - L.cx, yy - L.cy) < L.radius
            v_imu = allsky.unproject(L, xx[inside], yy[inside])
            w = v_imu @ self.R_world_imu.T
            alt[inside] = np.degrees(np.arcsin(np.clip(w[:, 2], -1, 1)))
            az[inside] = np.degrees(np.arctan2(w[:, 0], w[:, 1])) % 360
        self.inside = cv2.resize((~np.isnan(alt)).astype(np.uint8), (self.W, self.H), interpolation=cv2.INTER_NEAREST) > 0
        self.alt = cv2.resize(np.nan_to_num(alt, nan=-90).astype(np.float32), (self.W, self.H), interpolation=cv2.INTER_LINEAR)
        azc = np.nan_to_num(az, nan=0)
        cs = cv2.resize(np.cos(np.radians(azc)).astype(np.float32), (self.W, self.H))
        sn = cv2.resize(np.sin(np.radians(azc)).astype(np.float32), (self.W, self.H))
        self.az = np.degrees(np.arctan2(sn, cs)) % 360

    def to_px(self, v_world, R_world_imu=None):
        """World (ENU) unit vectors (N,3) → pixel x, y (NaN when not seen by either lens)."""
        R = self.R_world_imu if R_world_imu is None else R_world_imu
        v_imu = np.atleast_2d(v_world) @ R
        X = np.full(len(v_imu), np.nan)
        Y = np.full(len(v_imu), np.nan)
        best = np.full(len(v_imu), np.inf)
        for L in self.lenses:
            x, y, th = L.project(v_imu @ L.R_lens_imu.T)
            ok = (th < best) & (np.hypot(x - L.cx, y - L.cy) < L.radius - 2) & (x > 5) & (x < self.W - 6) & (y > 5) & (y < self.H - 6)
            X, Y, best = np.where(ok, x, X), np.where(ok, y, Y), np.where(ok, th, best)
        return X, Y

    def dist_deg(self, alt0, az0):
        """Angular distance (deg) of every pixel from the direction (alt0, az0)."""
        a, a0 = np.radians(self.alt), math.radians(alt0)
        c = np.sin(a) * math.sin(a0) + np.cos(a) * math.cos(a0) * np.cos(np.radians(self.az - az0))
        return np.degrees(np.arccos(np.clip(c, -1, 1)))

    def rand_dir(self, alt_lo, alt_hi, n):
        """n random sky directions (uniform in solid angle) between two altitudes."""
        s = self.rng.uniform(math.sin(math.radians(alt_lo)), math.sin(math.radians(alt_hi)), n)
        return np.degrees(np.arcsin(s)), self.rng.uniform(0, 360, n)


PSF_R = 4


def add_psf(img, x, y, amp, sigma=1.2):
    """Add a Gaussian spot (sub-pixel position) of peak amp."""
    cx, cy = int(round(x)), int(round(y))
    if cx - PSF_R < 0 or cy - PSF_R < 0 or cx + PSF_R >= img.shape[1] or cy + PSF_R >= img.shape[0]:
        return
    ys, xs = np.mgrid[-PSF_R:PSF_R + 1, -PSF_R:PSF_R + 1]
    img[cy - PSF_R:cy + PSF_R + 1, cx - PSF_R:cx + PSF_R + 1] += amp * np.exp(
        -((xs + cx - x) ** 2 + (ys + cy - y) ** 2) / (2 * sigma ** 2))


def add_disc(img, x, y, r, val, halo=0.0, halo_r=0.0):
    import cv2
    if halo:
        H, W = img.shape
        x0, x1 = int(max(0, x - 4 * halo_r)), int(min(W, x + 4 * halo_r))
        y0, y1 = int(max(0, y - 4 * halo_r)), int(min(H, y + 4 * halo_r))
        if x1 > x0 and y1 > y0:
            gy, gx = np.mgrid[y0:y1, x0:x1]
            img[y0:y1, x0:x1] += halo * np.exp(-np.hypot(gx - x, gy - y) / halo_r)
    cv2.circle(img, (int(round(x)), int(round(y))), int(max(1, r)), float(val), -1, lineType=cv2.LINE_AA)


def star_amp(mag):
    return 900.0 * 10 ** (-0.4 * (mag - 1.0))


def render(sc: Scene):
    """(uint8 frame) of the scene with all its effects."""
    import cv2
    c, rng, e = sc.c, sc.rng, sc.c.effects
    H, W = sc.H, sc.W
    stars = np.zeros((H, W), np.float32)
    trans = np.ones((H, W), np.float32)
    bg = np.full((H, W), 10.0, np.float32)
    extra_var = np.zeros((H, W), np.float32)          # photon noise of added light (variance = 0.3 x counts)
    sky = sc.inside & (sc.alt > 0)

    # ── stars (optionally smeared by the vehicle's rotation during the exposure / vibration) ──
    if not c.junk:
        vis = sc.star_alt > 0.5
        v, m = sc.star_v[vis], sc.star_mag[vis]
        rate = e.get("rotation_dps", 0.0)
        vib = e.get("vibration_px", 0.0)
        K = 9 if (rate or vib) else 1
        axis = rng.normal(size=3) * np.array([0.3, 0.3, 1.0])      # mostly yaw
        for k in range(K):
            frac = (k / (K - 1) - 0.5) if K > 1 else 0.0
            R = rot(axis, rate * EXPOSURE_S * frac) @ sc.R_world_imu
            x, y = sc.to_px(v, R)
            if vib:
                x = x + rng.normal(0, vib, len(x))
                y = y + rng.normal(0, vib, len(y))
            for xi, yi, mi in zip(x, y, m):
                if np.isfinite(xi):
                    add_psf(stars, xi, yi, star_amp(mi) / K)

    # ── fake point sources not in the catalogue ──
    if "random_points" in e:                           # star-like points at random places (false-ID test)
        n = int(e["random_points"])
        alt, az = sc.rand_dir(5, 90, n)
        x, y = sc.to_px(enu(alt, az))
        for xi, yi, mi in zip(x, y, rng.uniform(0.0, 3.5, n)):
            if np.isfinite(xi):
                add_psf(stars, xi, yi, star_amp(mi))
    if "satellites" in e:
        n = int(e["satellites"])
        alt, az = sc.rand_dir(15, 90, n)
        x, y = sc.to_px(enu(alt, az))
        for xi, yi, mi in zip(x, y, rng.uniform(1.5, 4.0, n)):
            if np.isfinite(xi):
                d = rng.uniform(0, 2 * math.pi)
                for t in np.linspace(-1, 1, 3):          # ~2 px of motion in 1/30 s
                    add_psf(stars, xi + t * math.cos(d), yi + t * math.sin(d), star_amp(mi) / 3)
    if "planes" in e:
        n = int(e["planes"])
        alt, az = sc.rand_dir(8, 70, n)
        x, y = sc.to_px(enu(alt, az))
        for xi, yi in zip(x, y):
            if not np.isfinite(xi):
                continue
            d = rng.uniform(0, 2 * math.pi)
            for dx, dy, mag in ((0, 0, rng.uniform(-1, 1)), (6 * math.cos(d + 1.6), 6 * math.sin(d + 1.6), 1.5),
                                (-6 * math.cos(d + 1.6), -6 * math.sin(d + 1.6), 1.5)):
                if rng.random() < 0.8:                   # blinking: each light on in 80% of frames
                    for t in np.linspace(-1, 1, 5):      # ~8 px streak in 1/30 s
                        add_psf(stars, xi + dx + 4 * t * math.cos(d), yi + dy + 4 * t * math.sin(d), star_amp(mag) / 5)
    if "meteor" in e:
        for _ in range(int(e["meteor"])):
            alt, az = sc.rand_dir(20, 80, 1)
            x, y = sc.to_px(enu(alt, az))
            if np.isfinite(x[0]):
                d, ln = rng.uniform(0, 2 * math.pi), rng.uniform(80, 300)
                p0 = (int(x[0]), int(y[0]))
                p1 = (int(x[0] + ln * math.cos(d)), int(y[0] + ln * math.sin(d)))
                cv2.line(stars, p0, p1, float(rng.uniform(120, 400)), 3, lineType=cv2.LINE_AA)

    # ── sky light ──
    if "skyglow" in e:                                 # city dome: brighter towards the horizon, towards the city
        az_city = rng.uniform(0, 360)
        g = e["skyglow"] * np.exp(-np.clip(sc.alt, 0, 90) / 18.0) * (0.55 + 0.45 * np.cos(np.radians(sc.az - az_city)))
        g = g + 0.15 * e["skyglow"]
        bg += np.where(sc.inside, g, 0)
        extra_var += np.where(sc.inside, 0.3 * g, 0)
    if "twilight" in e:
        az_sun = rng.uniform(0, 360)
        g = e["twilight"] * (np.exp(-np.clip(sc.alt, 0, 90) / 25.0) * (0.6 + 0.4 * np.cos(np.radians(sc.az - az_sun))) + 0.3)
        bg += np.where(sc.inside, g, 0)
        extra_var += np.where(sc.inside, 0.3 * g, 0)
        trans *= 0.7                                  # fainter stars lost in the brighter sky (contrast)
    if "moon" in e:                                   # moon: e = glow at the moon (full ~40, quarter ~12, crescent ~4)
        alt, az = sc.rand_dir(e.get("moon_alt_lo", 25), e.get("moon_alt_hi", 65), 1)
        dist = sc.dist_deg(alt[0], az[0])
        g = e["moon"] * (np.exp(-dist / 12.0) + 0.25) * (1.0 if alt[0] > 0 else 0.3)   # below the horizon: twilight-like glow only
        bg += np.where(sc.inside, g, 0)
        extra_var += np.where(sc.inside, 0.3 * g, 0)
        x, y = sc.to_px(enu(alt, az))
        if np.isfinite(x[0]) and alt[0] > 0:
            add_disc(bg, x[0], y[0], 14, 400, halo=200, halo_r=25)
            sc.moon_px = (x[0], y[0])

    # ── clouds and haze ──
    if "clouds" in e:                                  # fraction of the sky covered (thick clouds lit by the city)
        lo = rng.normal(size=(H // 64 + 1, W // 64 + 1)).astype(np.float32)
        fld = cv2.GaussianBlur(cv2.resize(lo, (W, H), interpolation=cv2.INTER_CUBIC), (0, 0), 30)
        thr = np.quantile(fld[sky], 1.0 - e["clouds"]) if e["clouds"] < 1 else -np.inf
        edge = np.clip((fld - thr) / 0.15 + 0.5, 0, 1)                   # soft cloud edges
        edge = np.where(sky, edge, 0)
        trans *= (1 - 0.98 * edge)
        tex = cv2.GaussianBlur(rng.normal(size=(H, W)).astype(np.float32), (0, 0), 6) * 25
        lit = edge * (12 + tex.clip(-8, 30))
        bg += lit
        extra_var += 0.3 * np.abs(lit)
    if "haze_mag" in e:
        trans *= 10 ** (-0.4 * e["haze_mag"])
        bg += np.where(sc.inside, 4.0, 0)

    # ── ground clutter, obstruction, lights ──
    if "obstruction" in e:                            # buildings/trees up to e[...] degrees, lit windows, roof rack
        top = e["obstruction"]
        prof = np.zeros(360)
        a = 0
        while a < 360:                               # skyline: buildings (flat tops) and trees (round)
            w = int(rng.uniform(8, 40))
            h = rng.uniform(0, top) if rng.random() < 0.7 else 0
            prof[a:a + w] = h
            a += w
        skyline = prof[np.clip(sc.az.astype(int), 0, 359)]
        occ = sc.inside & (sc.alt < skyline)
        trans[occ] = 0
        bg[occ] = 8 + 6 * rng.random()
        ys, xs = np.nonzero(occ[::7, ::7])
        pick = rng.choice(len(ys), size=min(len(ys), 150), replace=False) if len(ys) else []
        for i in pick:                                 # lit windows: small bright rectangles
            y, x = ys[i] * 7, xs[i] * 7
            bg[y:y + 3, x:x + 2] += rng.uniform(60, 245)
        rack = sc.inside & (np.abs(sc.alt - 2) < 1.5)
        bg[rack] = 30
    if "lamps" in e:                                  # street lamps: saturated discs with a glow, mostly low
        n = int(e["lamps"])
        alt, az = sc.rand_dir(-8, 40, n)
        x, y = sc.to_px(enu(alt, az))
        for xi, yi, a in zip(x, y, alt):
            if np.isfinite(xi):
                r = rng.uniform(3, 14) * (1.5 if a > 15 else 1.0)
                add_disc(bg, xi, yi, r, 300, halo=rng.uniform(40, 120), halo_r=rng.uniform(8, 30))
    if "headlights" in e:                             # oncoming cars: big glare near the horizon + a streak
        for _ in range(int(e["headlights"])):
            alt, az = sc.rand_dir(-3, 6, 1)
            x, y = sc.to_px(enu(alt, az))
            if np.isfinite(x[0]):
                add_disc(bg, x[0], y[0], 25, 400, halo=250, halo_r=60)
                add_disc(bg, x[0] + 30, y[0], 20, 400)
                d = rng.uniform(0, 2 * math.pi)
                cv2.line(bg, (int(x[0]), int(y[0])), (int(x[0] + 500 * math.cos(d)), int(y[0] + 500 * math.sin(d))),
                         120.0, 4, lineType=cv2.LINE_AA)
    if "flare" in e:                                  # ghosts of a bright source mirrored through the lens centre
        srcs = [getattr(sc, "moon_px", None)]
        if srcs[0] is None:
            alt, az = sc.rand_dir(5, 30, 1)
            x, y = sc.to_px(enu(alt, az))
            if np.isfinite(x[0]):
                add_disc(bg, x[0], y[0], 10, 400, halo=150, halo_r=20)
                srcs = [(x[0], y[0])]
        for s in srcs:
            if s is None:
                continue
            L = min(sc.lenses, key=lambda L: math.hypot(s[0] - L.cx, s[1] - L.cy))
            for k in np.linspace(-1.2, 0.6, int(e["flare"])):
                gx, gy = L.cx + k * (s[0] - L.cx), L.cy + k * (s[1] - L.cy)
                if rng.random() < 0.5:
                    add_disc(bg, gx, gy, rng.uniform(8, 50), rng.uniform(20, 70))
                else:
                    add_psf(bg, gx, gy, rng.uniform(80, 250), sigma=rng.uniform(1.0, 2.5))
    if "birds" in e:                                  # dark silhouettes and blobs lit by street lamps
        n = int(e["birds"])
        alt, az = sc.rand_dir(10, 80, n)
        x, y = sc.to_px(enu(alt, az))
        for i, (xi, yi) in enumerate(zip(x, y)):
            if not np.isfinite(xi):
                continue
            r = rng.uniform(4, 25)
            if i % 2:
                cv2.ellipse(trans, (int(xi), int(yi)), (int(r), int(r / 2)), rng.uniform(0, 180), 0, 360, 0.0, -1)
            else:
                add_psf(bg, xi, yi, rng.uniform(40, 200), sigma=rng.uniform(1.5, max(2.0, r / 3)))
    if "ground" in e:                                 # below the horizon: textured ground lit by the town
        gnd = sc.inside & (sc.alt < 0)
        tex = cv2.GaussianBlur(rng.normal(size=(H, W)).astype(np.float32), (0, 0), 3) * 40 + 30
        bg[gnd] += tex[gnd].clip(0, 200)

    if "cirrus" in e:                                 # thin cirrus: patchy 0..e magnitudes of extinction, faintly lit
        lo = rng.normal(size=(H // 128 + 1, W // 128 + 1)).astype(np.float32)
        fld = cv2.GaussianBlur(cv2.resize(lo, (W, H), interpolation=cv2.INTER_CUBIC), (0, 0), 40)
        fld = (fld - fld.min()) / (np.ptp(fld) + 1e-6)
        trans *= 10 ** (-0.4 * e["cirrus"] * fld)
        bg += np.where(sky, 4.0 * e["cirrus"] * fld, 0)
    if "drones" in e:                                 # drone LEDs: steady point lights not in the catalogue, some pairs
        n = int(e["drones"])
        alt, az = sc.rand_dir(10, 60, n)
        x, y = sc.to_px(enu(alt, az))
        for xi, yi in zip(x, y):
            if np.isfinite(xi):
                add_psf(stars, xi, yi, star_amp(rng.uniform(0.0, 3.0)))
                if rng.random() < 0.5:
                    add_psf(stars, xi + rng.uniform(2, 5), yi, star_amp(rng.uniform(1.0, 3.0)))
    if "insects" in e:                                # insects near the lens, lit by lamps: big soft blobs and streaks
        for _ in range(int(e["insects"])):
            alt, az = sc.rand_dir(10, 85, 1)
            x, y = sc.to_px(enu(alt, az))
            if not np.isfinite(x[0]):
                continue
            if rng.random() < 0.5:
                add_psf(bg, x[0], y[0], rng.uniform(30, 200), sigma=rng.uniform(2.5, 8.0))
            else:
                d, ln = rng.uniform(0, 2 * math.pi), rng.uniform(15, 60)
                cv2.line(bg, (int(x[0]), int(y[0])), (int(x[0] + ln * math.cos(d)), int(y[0] + ln * math.sin(d))),
                         float(rng.uniform(30, 150)), int(rng.uniform(2, 6)), lineType=cv2.LINE_AA)
    if "inside" in e:                                 # camera inside the car: roof hides alt < e deg, glass, reflections
        roof = sc.inside & (sc.alt < e["inside"])
        trans[roof] = 0
        bg[roof] = 6 + 4 * rng.random()
        trans *= 10 ** (-0.4 * 0.5)                  # windscreen/sunroof glass ~0.5 mag
        if not c.junk:                               # second-surface ghosts of the bright stars, 8 px away, 8%
            vis = sc.star_alt > e["inside"]
            gx, gy = sc.to_px(sc.star_v[vis])
            off = rng.uniform(5, 10, 2)
            for xi, yi, mi in zip(gx, gy, sc.star_mag[vis]):
                if np.isfinite(xi) and mi < 2.0:
                    add_psf(stars, xi + off[0], yi + off[1], 0.08 * star_amp(mi))
        alt, az = sc.rand_dir(e["inside"], 89, 15)    # dashboard LEDs / phone screen reflected in the glass
        x, y = sc.to_px(enu(alt, az))
        for xi, yi in zip(x, y):
            if np.isfinite(xi):
                add_psf(bg, xi, yi, rng.uniform(40, 400), sigma=rng.uniform(0.9, 1.6))

    frame = stars * trans + bg
    noise_sd = math.sqrt(9.0 + e.get("read_noise", 0.0) ** 2)
    frame += rng.normal(0, 1, (H, W)).astype(np.float32) * np.sqrt(noise_sd ** 2 + extra_var + 0.3 * stars * trans)
    if "hot_pixels" in e:
        n = int(e["hot_pixels"])
        hy, hx = rng.integers(0, H, n), rng.integers(0, W, n)
        frame[hy, hx] = rng.uniform(80, 255, n)
    if "pure_noise" in e:
        frame = rng.normal(10 + e["pure_noise"], 3 + e["pure_noise"] / 4, (H, W)).astype(np.float32)
    out = np.clip(frame, 0, 255).astype(np.uint8)
    if "jpeg" in e:
        ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, int(e["jpeg"])])
        out = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    if "h264_qp" in e:
        out, sc.h264_bytes = h264_keyframe(out, int(e["h264_qp"]))
    return out


def h264_keyframe(gray, qp):
    """(the frame after an H.264 intra (key) frame round trip at quantiser qp, its size in bytes): libx264 as a
    stand-in for the camera's hardware encoder (40 Mbps, 3840x1920, key frames decoded only)."""
    import av
    enc = av.CodecContext.create("libx264", "w")
    enc.width, enc.height, enc.pix_fmt = gray.shape[1], gray.shape[0], "yuv420p"
    enc.time_base = __import__("fractions").Fraction(1, 30)
    enc.options = {"qp": str(qp), "preset": "veryfast", "keyint": "1", "bframes": "0"}
    yuv = np.full((gray.shape[0] * 3 // 2, gray.shape[1]), 128, np.uint8)
    yuv[:gray.shape[0]] = gray
    fr = av.VideoFrame.from_ndarray(yuv, format="yuv420p")
    pkts = list(enc.encode(fr)) + list(enc.encode(None))
    nbytes = sum(p.size for p in pkts)
    dec = av.CodecContext.create("h264", "r")
    imgs = []
    for p in pkts:
        imgs += [f.to_ndarray(format="yuv420p")[:gray.shape[0]] for f in dec.decode(p)]       # the Y plane as coded
    imgs += [f.to_ndarray(format="yuv420p")[:gray.shape[0]] for f in dec.decode(None)]
    return imgs[0], nbytes


def solver_up(sc: Scene):
    """'up' as the camera's accelerometer reports it, or None when a gravity gate refuses it:
    the camera's own (insta360_usb.gravity: |a| outside 0.95-1.05 g or turning > 3 deg/s) and, when the
    solver module has one, its tighter |a| tolerance (allsky.ACCEL_NORM_TOL, applied by the server)."""
    c, up = sc.c, sc.up_imu.copy()
    if c.up_err_deg:
        ax = np.cross(up, sc.rng.normal(size=3))
        up = rot(ax, c.up_err_deg) @ up
    if c.accel_g:
        h = np.cross(up, sc.rng.normal(size=3))
        a = up + c.accel_g * h / np.linalg.norm(h)          # specific force: gravity + horizontal acceleration
        g = float(np.linalg.norm(a))
        tol = getattr(_SOLVER, "ACCEL_NORM_TOL", None)
        if not 0.95 < g < 1.05:
            return None, f"camera gate |a| = {g:.3f} g"
        if c.yaw_rate_dps > 3.0:
            return None, f"camera gate turning {c.yaw_rate_dps:.1f} deg/s"
        if tol is not None and abs(g - 1.0) > tol:
            return None, f"server gate |a| = {g:.3f} g"
        return a / g, None
    return up, None


_CAT = None
_SOLVER = allsky                  # --solver FILE swaps in another allsky.py (e.g. an older commit's) for before/after


def run_one(args):
    """(condition name, seed) → result dict (a harness error is reported in the row, never raised)."""
    try:
        return _run_one(args)
    except Exception as ex:
        cond, seed = args
        return {"cond": cond.name, "seed": seed, "junk": cond.junk, "solved": False, "t": 0.0,
                "why": f"HARNESS ERROR {ex!r}"}


def _run_one(args):
    cond, seed = args
    global _CAT
    if _CAT is None:
        _CAT = _SOLVER.Catalogue(limit_mag=4.0)
    from datetime import datetime, timedelta
    sc = Scene(cond, seed)
    frame = render(sc)
    up, gate = solver_up(sc)
    res = {"cond": cond.name, "seed": seed, "junk": cond.junk}
    if up is None:
        res.update(solved=False, why=gate, t=0.0)
        return res
    utc = sc.utc
    if cond.clock_err_s:
        t = datetime.strptime(utc, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=cond.clock_err_s)
        utc = t.strftime("%Y-%m-%d %H:%M:%S")
    fs = F_SCALE_SEARCH if cond.search_focal else (cond.f_true,)
    t0 = time.time()
    try:
        r = _SOLVER.locate(frame, up, utc, _CAT, f_scales=fs)
    except Exception as ex:                               # a crash is a finding, not a harness failure
        r = {"solved": False, "why": f"exception {ex!r}"}
    res["t"] = time.time() - t0
    res.update(solved=bool(r.get("solved")), why=r.get("why"), spots=r.get("spots"), matched=r.get("matched"),
               rms=r.get("rms_deg"), sigma_fit_deg=r.get("sigma_fit_deg"), p_chance=r.get("p_chance"),
               lens_disagree_deg=r.get("lens_disagree_deg"), f_scale=r.get("f_scale"))
    if r.get("solved"):
        from navera_tools.field.reprocess360 import haversine_km
        res["err_km"] = haversine_km(r["lat"], r["lon"], cond.lat, cond.lon)
        # the sigma the server states for a stopped fix (server._solve360): accelerometer + star fit
        att = math.hypot(ATTITUDE_SIGMA_360_DEG, r.get("sigma_fit_deg") or 0.0)
        res["sigma_km"] = att * 111.2
    return res


def conditions() -> List[Condition]:
    C = Condition
    urban = {"skyglow": 40, "lamps": 12, "ground": 1, "obstruction": 20}
    return [
        C("baseline mag<=3"),
        C("exposure mag<=2.0", limit_mag=2.0),
        C("exposure mag<=2.5", limit_mag=2.5),
        C("exposure mag<=3.5", limit_mag=3.5),
        C("skyglow 20", effects={"skyglow": 20}),
        C("skyglow 60", effects={"skyglow": 60}),
        C("street lamps 15", effects={"lamps": 15}),
        C("headlights+flare", effects={"headlights": 2, "flare": 6}),
        C("moon", effects={"moon": 40}),
        C("moon + flare", effects={"moon": 40, "flare": 6}),
        C("twilight", effects={"twilight": 50}),
        C("clouds 20%", effects={"clouds": 0.2}),
        C("clouds 50%", effects={"clouds": 0.5}),
        C("clouds 80%", effects={"clouds": 0.8}),
        C("haze 1 mag", effects={"haze_mag": 1.0}),
        C("planes 4", effects={"planes": 4}),
        C("satellites 8", effects={"satellites": 8}),
        C("meteors 2", effects={"meteor": 2}),
        C("birds/insects 12", effects={"birds": 12}),
        C("obstruction 30 deg", effects={"obstruction": 30, "ground": 1}),
        C("hot pixels 400", effects={"hot_pixels": 400}),
        C("read noise 8", effects={"read_noise": 8}),
        C("jpeg q50", effects={"jpeg": 50}),
        C("rotation 20 deg/s", effects={"rotation_dps": 20}),
        C("vibration 1.5 px", effects={"vibration_px": 1.5}),
        C("tilt 8 deg", tilt_deg=8),
        C("tilt 15 deg", tilt_deg=15),
        C("focal -10% (search)", f_true=0.90, search_focal=True),
        C("focal +4% (search)", f_true=1.04, search_focal=True),
        C("focal +7% (search)", f_true=1.07, search_focal=True),
        C("k1 0.01", k1_true=0.01),
        C("k1 -0.02", k1_true=-0.02),
        C("centre off 5 px", centre_off_px=5),
        C("centre off 10 px", centre_off_px=10),
        C("lenses misaligned 0.3", right_misalign_deg=0.3),
        C("lenses misaligned 1.0", right_misalign_deg=1.0),
        C("accel noise 0.1 deg", up_err_deg=0.1),
        C("accel bias 0.5 deg", up_err_deg=0.5),
        C("braking 0.3 g", accel_g=0.3),
        C("braking 0.1 g", accel_g=0.1),
        C("turn 0.15 g at 15 m/s", accel_g=0.15, yaw_rate_dps=5.7),
        C("highway curve 0.1 g at 30 m/s", accel_g=0.1, yaw_rate_dps=1.9),
        C("clock +2 s", clock_err_s=2.0),
        C("urban", effects=urban),
        C("urban+moon+clouds50+planes", effects={**urban, "moon": 40, "clouds": 0.5, "planes": 3, "satellites": 5}),
        C("worst: mag2.5 urban jpeg tilt10 blur", limit_mag=2.5, tilt_deg=10,
          effects={**urban, "jpeg": 60, "rotation_dps": 10, "hot_pixels": 200, "planes": 2}),
        C("few stars (mag<=1.5) + 50 junk points", limit_mag=1.5, effects={"random_points": 50}),
        C("few stars (mag<=1.5) + lamps/windows/junk", limit_mag=1.5,
          effects={**urban, "lamps": 30, "random_points": 30, "hot_pixels": 300}),
        C("JUNK pure noise", junk=True, effects={"pure_noise": 0}),
        C("JUNK overcast lit", junk=True, effects={"clouds": 1.0, "skyglow": 40}),
        C("JUNK lamps+windows+planes", junk=True, effects={**urban, "lamps": 40, "planes": 5, "hot_pixels": 400}),
        C("JUNK 60 random points", junk=True, effects={"random_points": 60}),
        C("JUNK 120 random points", junk=True, effects={"random_points": 120}),
        C("JUNK clutter: 60 points + lamps/windows/trees", junk=True,
          effects={**urban, "obstruction": 35, "lamps": 25, "random_points": 60, "birds": 10}),
    ]


def car_matrix() -> List[Condition]:
    """The car field-test matrix (2026-10-19): the standing camera on a car roof at a stop. Every real-sky cell
    has the accelerometer's measured residual (0.07 deg, the stopped case) so the stated sigma is tested too."""
    def C(name, **kw):
        if not kw.get("junk"):
            kw.setdefault("up_err_deg", 0.07)
        return Condition(name, **kw)
    urban = {"skyglow": 40, "lamps": 12, "ground": 1, "obstruction": 20}
    return [
        C("base mag<=3"),
        C("stars mag<=2.0", limit_mag=2.0), C("stars mag<=2.5", limit_mag=2.5), C("stars mag<=3.5", limit_mag=3.5),
        C("stars mag<=4.0", limit_mag=4.0), C("stars mag<=5.0", limit_mag=5.0),
        C("h264 key frame qp24 (~640 kB) mag<=3", effects={"h264_qp": 24}),
        C("h264 qp24 mag<=3.5", limit_mag=3.5, effects={"h264_qp": 24}),
        C("h264 qp28 (~150 kB) mag<=3", effects={"h264_qp": 28}),
        C("h264 qp32 (~12 kB) mag<=3", effects={"h264_qp": 32}),
        C("h264 qp28 mag<=2.5", limit_mag=2.5, effects={"h264_qp": 28}),
        C("gain: read noise 8", effects={"read_noise": 8}),
        C("exposure -1 mag", effects={"haze_mag": 1.0}),
        C("moon full high", effects={"moon": 40}),
        C("moon full low (5-20 deg)", effects={"moon": 40, "moon_alt_lo": 5, "moon_alt_hi": 20}),
        C("moon quarter", effects={"moon": 12}),
        C("moon crescent", effects={"moon": 4}),
        C("moon full below horizon", effects={"moon": 40, "moon_alt_lo": -15, "moon_alt_hi": -3}),
        C("moon full + flare", effects={"moon": 40, "flare": 6}),
        C("city glow 20", effects={"skyglow": 20}), C("city glow 60", effects={"skyglow": 60}),
        C("clouds 20%", effects={"clouds": 0.2}), C("clouds 50%", effects={"clouds": 0.5}),
        C("clouds 80%", effects={"clouds": 0.8}),
        C("cirrus 1 mag", effects={"cirrus": 1.0}), C("cirrus 2 mag", effects={"cirrus": 2.0}),
        C("twilight", effects={"twilight": 50}),
        C("obstruction 10 deg", effects={"obstruction": 10, "ground": 1}),
        C("obstruction 25 deg", effects={"obstruction": 25, "ground": 1}),
        C("obstruction 40 deg", effects={"obstruction": 40, "ground": 1}),
        C("camera inside car (roof below 45 deg)", effects={"inside": 45}),
        C("planes 4 (blinking)", effects={"planes": 4}), C("satellites 8", effects={"satellites": 8}),
        C("drones 4", effects={"drones": 4}), C("birds 12", effects={"birds": 12}),
        C("insects 15 near the lens", effects={"insects": 15}), C("hot pixels 400", effects={"hot_pixels": 400}),
        C("street lamps 15", effects={"lamps": 15}),
        C("urban + moon + clouds 50% + planes", effects={**urban, "moon": 40, "clouds": 0.5, "planes": 3}),
        C("tilt 15 deg", tilt_deg=15), C("tilt 25 deg", tilt_deg=25), C("tilt 35 deg", tilt_deg=35),
        C("tilt 45 deg", tilt_deg=45),
        C("right lens f -5.5% (left's measured)", right_f_true=0.945),
        C("right lens f -3%", right_f_true=0.97), C("right lens f +3%", right_f_true=1.03),
        C("right lens k1 +0.02", right_k1_true=0.02), C("right lens centre 10 px", right_centre_off_px=10),
        C("right lens f -5.5% + centre 10 px", right_f_true=0.945, right_centre_off_px=10),
        C("mount 0.5 deg", mount_deg=0.5), C("mount 1 deg", mount_deg=1.0), C("mount 2 deg", mount_deg=2.0),
        C("clock +10 s", clock_err_s=10), C("clock +30 s", clock_err_s=30), C("clock +60 s", clock_err_s=60),
        C("latitude 0", lat=0.0), C("latitude 20", lat=20.0), C("latitude 50", lat=50.0), C("latitude 65", lat=65.0),
        C("latitude -35", lat=-35.0),
        C("JUNK pure noise", junk=True, effects={"pure_noise": 0}),
        C("JUNK overcast lit", junk=True, effects={"clouds": 1.0, "skyglow": 40}),
        C("JUNK 60 random points", junk=True, effects={"random_points": 60}),
        C("JUNK 120 random points", junk=True, effects={"random_points": 120}),
        C("JUNK clutter + insects + drones", junk=True,
          effects={**urban, "obstruction": 35, "lamps": 25, "random_points": 40, "insects": 15, "drones": 6}),
        C("JUNK inside car, LEDs", junk=True, effects={"inside": 45, "random_points": 30}),
        C("JUNK h264 qp28 + 60 points", junk=True, effects={"random_points": 60, "h264_qp": 28}),
    ]


def summarise(rows):
    out = []
    by = {}
    for r in rows:
        by.setdefault(r["cond"], []).append(r)
    for name, rs in by.items():
        n = len(rs)
        solved = [r for r in rs if r["solved"]]
        if rs[0]["junk"]:
            wrong = solved
        else:
            wrong = [r for r in solved if r.get("err_km", 1e9) > WRONG_KM]
        good = [r["err_km"] for r in solved if r not in wrong]
        cov = [r for r in solved if r.get("sigma_km") is not None and not rs[0]["junk"]]
        out.append({"cond": name, "n": n, "solved": len(solved), "wrong": len(wrong),
                    "median_km": round(float(np.median(good)), 1) if good else None,
                    "p90_km": round(float(np.percentile([r["err_km"] for r in solved], 90)), 1) if solved and not rs[0]["junk"] else None,
                    "within_3sigma": f"{sum(r['err_km'] <= 3 * r['sigma_km'] for r in cov)}/{len(cov)}" if cov else "-",
                    "max_good_km": round(float(np.max(good)), 1) if good else None,
                    "matched": round(float(np.median([r["matched"] for r in solved])), 0) if solved else None,
                    "t_s": round(float(np.mean([r["t"] for r in rs])), 1),
                    "whys": sorted({str(r.get("why"))[:40] for r in rs if not r["solved"]})[:2]})
    return out


def table(summary) -> str:
    lines = ["| condition | solved | WRONG (>50 km / junk fix) | median km | p90 km (all fixes) | within 3 sigma | max km (ok) | matched | solve s | why not |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        lines.append(f"| {s['cond']} | {s['solved']}/{s['n']} | {s['wrong']} | {s['median_km'] if s['median_km'] is not None else '-'} | "
                     f"{s.get('p90_km') if s.get('p90_km') is not None else '-'} | {s.get('within_3sigma', '-')} | "
                     f"{s['max_good_km'] if s['max_good_km'] is not None else '-'} | {s['matched'] if s['matched'] is not None else '-'} | "
                     f"{s['t_s']} | {'; '.join(s['whys'])} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--only", default="", help="comma-separated substrings of condition names")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--json", default="")
    ap.add_argument("--set", choices=("stress", "car"), default="stress",
                    help="stress: the 2026-10-17 conditions table; car: the car field-test matrix (2026-10-19)")
    ap.add_argument("--solver", default="", help="path of another allsky.py to test instead of the current one")
    ap.add_argument("--lens", choices=("measured", "nominal"), default="measured",
                    help="lens model (truth and solver): sky360.default_lenses() as measured, or the first guess")
    a = ap.parse_args()
    if a.lens == "nominal":
        sky360.LENS_FILE = "/nonexistent"                         # default_lenses() falls back to the first guess
    if a.solver:
        import importlib.util
        global _SOLVER
        spec = importlib.util.spec_from_file_location("allsky_under_test", a.solver)
        _SOLVER = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_SOLVER)
    conds = car_matrix() if a.set == "car" else conditions()
    if a.only:
        keys = [k.strip() for k in a.only.split(",") if k.strip()]
        conds = [c for c in conds if any(k in c.name for k in keys)]
    jobs = [(c, s) for c in conds for s in range(a.seeds)]
    t0 = time.time()
    rows = []
    log = open(a.json + "l", "w") if a.json else None          # one row per frame as it finishes (survives a kill)

    def keep(r):
        rows.append(r)
        if log:
            log.write(json.dumps(r, default=float) + "\n")
            log.flush()
    if a.workers > 1:
        import multiprocessing as mp
        with mp.get_context("fork").Pool(a.workers, maxtasksperchild=8) as pool:
            for r in pool.imap_unordered(run_one, jobs, chunksize=1):
                keep(r)
    else:
        for j in jobs:
            keep(run_one(j))
    order = {c.name: i for i, c in enumerate(conds)}
    rows.sort(key=lambda r: (order[r["cond"]], r["seed"]))
    summ = summarise(rows)
    print("SIMULATION ONLY - synthetic frames\n")
    print(table(summ))
    real = [r for r in rows if not r["junk"]]
    junk = [r for r in rows if r["junk"]]
    wrong_real = sum(1 for r in real if r["solved"] and r.get("err_km", 1e9) > WRONG_KM)
    print(f"\nreal-sky frames: {sum(r['solved'] for r in real)}/{len(real)} solved, {wrong_real} wrong (>{WRONG_KM:.0f} km); "
          f"junk frames: {sum(r['solved'] for r in junk)}/{len(junk)} false accepts; wall {time.time() - t0:.0f} s")
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"rows": rows, "summary": summ}, f, indent=1, default=float)


if __name__ == "__main__":
    main()
