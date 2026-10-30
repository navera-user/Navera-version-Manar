"""Sun and Moon lines of position from the Insta360's full 360 frame and its own gravity.

A star fix needs a dark, clear sky; the Sun (and the Moon, also through thin cloud) is seen almost always. One
body measured against 'up' gives its altitude: the observer is on a circle of equal altitude around the body's
geographic position (thousands of km wide), i.e. near the prior a LINE of position perpendicular to the body's
azimuth (Marcq St Hilaire). One line is not a fix: fused with the prior it shrinks the position error across the
line only. The body's azimuth moves ~15 deg/h, so lines taken minutes to hours apart cross: a running fix.

    altitude  = 90 deg - angle(up, ray to the disc centre)       (up: camera IMU; ray: lens model)
    error     ~ up error (IMU tilt, mount) + lens model + centroid:  1 deg of altitude = 111 km across the line.

Detection: a compact saturated blob above the horizon, its centre from a circle fitted to its edge (the full edge
for the Sun; for the Moon only the edge on the sunward side, the bright limb: the terminator is not a circle, so
a centroid would be pulled towards the lit side). The candidate is kept only if its altitude agrees with the
ephemeris at the prior (and its azimuth, when a heading is given); two candidates in the gate = ambiguous, none
used. Lamps and windows also saturate: the altitude gate, uniqueness and, over several frames, the body's own
motion (a lamp keeps its altitude, the Sun does not) are what refuse them.

Ephemeris: astropy's built-in (offline) Sun/Moon, apparent places through celestial_math's offline IERS set-up;
the body's Earth-fixed position is computed once per time, so the topocentric altitude anywhere (with the Moon's
~1 deg parallax) is a vector operation.

Fusion: generalized least squares on (north, east) km around the prior with every altitude, the errors split into
a part common to all frames of one camera mounting (up/lens bias, sigma_bias) and a per-frame part (centroid,
IMU noise, sigma_rand). The residual chi-square tests that the frames agree with ONE position (a lamp at constant
altitude fails it once the body should have moved).
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

import numpy as np

from cn_pkg.sky360 import Lens, default_lenses

KM_PER_DEG = 111.2
EARTH_A_KM = 6378.137
EARTH_F = 1.0 / 298.257223563
SUN_RADIUS_KM = 696_000.0
MOON_RADIUS_KM = 1737.4
SATURATED = 245            # DN: a pixel at or above this is clipped (8-bit frames)
MIN_AREA = 3               # px: smaller saturated spots are stars, planets or hot pixels
MAX_RADIUS_DEG = 8.0       # a blob wider than this (sky through a window, white wall) is not a disc + bloom
MIN_FILL = 0.55            # blob area / area of its fitted circle: a disc with bloom fills it, a window bar does not
MIN_ALT_DEG = 12.0         # as the star solver (allsky.LOCATE_MIN_ALT): ground, lamps, roofs below; refraction
MOON_MIN_LIT = 0.3         # a thinner crescent: too small for its centre (synthetic: 1.8-4.9 deg off, or a lamp)
GATE_SIGMA = 3.0
# error budget (1 sigma). The errors of a sight are NOT one constant altitude bias (real Moon, 2026-10-30 night,
# Sousse: intercept +0.34 deg at 81 deg altitude / azimuth 156, -0.5 at 70 / 251, -1.0 at 60 / 263, camera still).
# They are modelled where they come from, each correlated across sights as the physics says:
# - 'up' tilted (IMU bias, mounting): error = tilt . (the body's horizontal direction in the camera frame), SIGMA_UP_DEG
#   per axis (the field server's attitude_sigma_deg);
# - focal-length scale of the lens (screen-calibrated to 87 deg; the star solver searches f_scale 0.96-1.04):
#   error = dalt/dscale x scale, SIGMA_FSCALE per lens;
# - the centre of a blooming disc (halo vs clipped edge, phase): SIGMA_CENTRE_DEG common to all sights;
# - what changes slowly (bloom as the sky brightens, thin cloud): SIGMA_DRIFT_DEG common within BIN_S;
# - frame to frame (H.264, IMU noise): SIGMA_FRAME_DEG (real Moon: 0.2 deg frame to frame).
# Centre 0.4 and drift 0.3 are the smallest that kept the whole real night (465 sights, 02:28-05:12 UTC, priors
# 30/150/500 km) within 3 sigma (max 2.92; with 0.3/0.2: 3.38). Sized on that one night: to re-check on more.
SIGMA_UP_DEG = 0.3
SIGMA_FSCALE = 0.015
SIGMA_CENTRE_DEG = 0.4
SIGMA_LENS_DEG = math.hypot(SIGMA_CENTRE_DEG, SIGMA_FSCALE * 40.0)   # a sight without its geometry: ~0.72 deg in all
SIGMA_FRAME_DEG = 0.15
SIGMA_DRIFT_DEG = 0.3
BIN_S = 600.0
BIAS_CHANGE_DEG = 0.3     # a bias learnt with GPS, later: the body has moved across the lens (measured 0.29)
CENTROID_FLOOR_PX = 0.7


# ── geometry ──────────────────────────────────────────────────────────────────


def _unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def geodetic_to_ecef(lat_deg: float, lon_deg: float, h_km: float = 0.0) -> np.ndarray:
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    e2 = EARTH_F * (2 - EARTH_F)
    n = EARTH_A_KM / math.sqrt(1 - e2 * math.sin(la) ** 2)
    return np.array([(n + h_km) * math.cos(la) * math.cos(lo), (n + h_km) * math.cos(la) * math.sin(lo),
                     (n * (1 - e2) + h_km) * math.sin(la)])


def enu_basis(lat_deg: float, lon_deg: float) -> np.ndarray:
    """Rows: east, north, up (geodetic) in ECEF."""
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    return np.array([[-math.sin(lo), math.cos(lo), 0.0],
                     [-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)],
                     [math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)]])


def offset_latlon(lat: float, lon: float, north_km: float, east_km: float) -> Tuple[float, float]:
    return lat + north_km / KM_PER_DEG, lon + east_km / (KM_PER_DEG * math.cos(math.radians(lat)))


def distance_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, a)))


def refraction_deg(alt_deg: float) -> float:
    """Bennett (apparent altitude → apparent minus true), standard atmosphere."""
    a = max(alt_deg, -0.5)
    return (1.0 / math.tan(math.radians(a + 7.31 / (a + 4.4)))) / 60.0


# ── ephemeris ─────────────────────────────────────────────────────────────────


@dataclass
class BodyPlace:
    """A body's (and the Sun's) Earth-fixed position at one time: topocentric altitude/azimuth anywhere."""
    body: str
    utc: str
    r_ecef_km: np.ndarray
    sun_ecef_km: np.ndarray

    def altaz(self, lat: float, lon: float, h_km: float = 0.0) -> Tuple[float, float, float]:
        """True (airless) topocentric altitude, azimuth (deg, from north through east) and distance (km)."""
        d = self.r_ecef_km - geodetic_to_ecef(lat, lon, h_km)
        dist = float(np.linalg.norm(d))
        e, n, u = enu_basis(lat, lon) @ (d / dist)
        return math.degrees(math.asin(max(-1.0, min(1.0, u)))), math.degrees(math.atan2(e, n)) % 360.0, dist

    def semidiameter_deg(self, lat: float, lon: float) -> float:
        r = SUN_RADIUS_KM if self.body == "sun" else MOON_RADIUS_KM
        return math.degrees(math.asin(r / self.altaz(lat, lon)[2]))

    def illuminated_fraction(self) -> float:
        """Moon: lit fraction of the disc (1 for the Sun), from the Sun-Earth-Moon angle (geocentric)."""
        if self.body == "sun":
            return 1.0
        m, s = self.r_ecef_km, self.sun_ecef_km - self.r_ecef_km
        cos_i = float(np.dot(-m, s) / (np.linalg.norm(m) * np.linalg.norm(s)))   # phase angle at the Moon
        return (1.0 + cos_i) / 2.0

    def bright_limb_angle(self, lat: float, lon: float) -> float:
        """Angle (deg) around the body's line of sight from the local 'up' direction to the Sun's direction,
        counted positive towards +east-ish (right-handed about the line of sight from the observer)."""
        o = geodetic_to_ecef(lat, lon)
        m = _unit(self.r_ecef_km - o)
        s = _unit(self.sun_ecef_km - self.r_ecef_km)          # from the Moon to the Sun
        up = enu_basis(lat, lon)[2]
        a = up - np.dot(up, m) * m
        b = s - np.dot(s, m) * m
        return math.degrees(math.atan2(float(np.dot(np.cross(a, b), m)), float(np.dot(a, b))))


_PLACE_CACHE: dict = {}


def body_place(body: str, utc: str) -> BodyPlace:
    """Sun or Moon (geocentric apparent, light time and aberration included) in ITRS at utc. Offline."""
    key = (body, utc)
    if key in _PLACE_CACHE:
        return _PLACE_CACHE[key]
    import astropy.units as u
    from astropy.coordinates import ITRS, get_body
    from cn_pkg.nodes.celestial_math import obs_time
    t = obs_time(utc)

    def itrs(name):
        c = get_body(name, t)                                   # GCRS, geocentric
        x = c.transform_to(ITRS(obstime=t)).cartesian.xyz.to(u.km).value
        return np.asarray(x, float)

    p = BodyPlace(body, utc, itrs(body), itrs("sun") if body != "sun" else itrs("sun"))
    if len(_PLACE_CACHE) > 4096:
        _PLACE_CACHE.clear()
    _PLACE_CACHE[key] = p
    return p


# ── detection ─────────────────────────────────────────────────────────────────


@dataclass
class Disc:
    lens: str
    x: float
    y: float
    radius_px: float
    area: int
    fill: float
    peak: float
    centroid_sigma_px: float
    ray: np.ndarray = field(repr=False)           # unit, IMU frame
    alt_app_deg: float = 0.0                       # apparent altitude above the IMU's horizon
    alt_deg: float = 0.0                           # refraction removed
    deg_per_px: float = 0.1
    method: str = "circle"


def _circle_fit(pts: np.ndarray) -> Optional[Tuple[float, float, float, float]]:
    """Algebraic (Kasa) circle fit, then 5 geometric Gauss-Newton steps: (cx, cy, r, rms residual)."""
    if len(pts) < 5:
        return None
    x, y = pts[:, 0], pts[:, 1]
    A = np.c_[2 * x, 2 * y, np.ones(len(x))]
    sol, *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    cx, cy = sol[0], sol[1]
    r = math.sqrt(max(sol[2] + cx * cx + cy * cy, 1e-9))
    for _ in range(5):
        dx, dy = x - cx, y - cy
        d = np.hypot(dx, dy) + 1e-9
        J = np.c_[-dx / d, -dy / d, -np.ones(len(x))]
        res = d - r
        step, *_ = np.linalg.lstsq(J, -res, rcond=None)
        cx, cy, r = cx + step[0], cy + step[1], r + step[2]
    res = np.hypot(x - cx, y - cy) - r
    return float(cx), float(cy), float(abs(r)), float(np.sqrt(np.mean(res ** 2)))


def _edge_points(mask: np.ndarray) -> np.ndarray:
    """Sub-pixel-ish edge of a binary blob: the boundary pixels' outer edges (pixel centres ± 0.5 towards out)."""
    import cv2
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return np.zeros((0, 2))
    c = max(cs, key=len)[:, 0, :].astype(float)
    ctr = c.mean(axis=0)
    out = c - ctr
    n = np.linalg.norm(out, axis=1, keepdims=True) + 1e-9
    return c + 0.5 * out / n                                   # half a pixel outwards: the blob's true edge


def _lens_scale(lens: Lens, x: float, y: float) -> float:
    """Degrees per pixel (radial) of the fisheye at (x, y)."""
    r = math.hypot(x - lens.cx, y - lens.cy)
    th = r / lens.f
    for _ in range(4):
        th -= (th + lens.k1 * th ** 3 - r / lens.f) / (1 + 3 * lens.k1 * th ** 2)
    return math.degrees(1.0 / (lens.f * (1 + 3 * lens.k1 * th ** 2)))


def _ray(lens: Lens, x: float, y: float) -> np.ndarray:
    from cn_pkg.allsky import unproject
    return _unit(unproject(lens, np.array([x]), np.array([y]))[0])


def detect_discs(gray: np.ndarray, up_imu: Sequence[float], lenses: Optional[List[Lens]] = None,
                 sat: int = SATURATED, min_alt_deg: float = MIN_ALT_DEG, max_theta_deg: float = 95.0,
                 ref_width: float = 3840.0) -> List[Disc]:
    """Every compact saturated blob above min_alt_deg in either fisheye circle, with its circle-fitted centre."""
    import cv2
    lenses = lenses or default_lenses()
    up = _unit(up_imu)
    g = gray if gray.ndim == 2 else cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    sx = w / ref_width                                         # frames other than the lens model's width: scale
    m = (g >= sat).astype(np.uint8)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for k in range(1, n):
        area = int(stats[k, cv2.CC_STAT_AREA])
        if area < MIN_AREA:
            continue
        cx0, cy0 = cents[k][0] / sx, cents[k][1] / sx
        lens = min(lenses, key=lambda L: math.hypot(cx0 - L.cx, cy0 - L.cy))
        if math.degrees(math.hypot(cx0 - lens.cx, cy0 - lens.cy) / lens.f) > max_theta_deg:
            continue
        dpp = _lens_scale(lens, cx0, cy0) / sx
        if math.sqrt(area / math.pi) * dpp > MAX_RADIUS_DEG:
            continue
        x0, y0, bw, bh = stats[k, :4]
        # a disc cut by the image's edge or the lens circle's edge: its centre cannot be measured (ESO MASCOT: a
        # Moon cut at the border was fitted 11.9 deg off)
        if x0 <= 1 or y0 <= 1 or x0 + bw >= w - 1 or y0 + bh >= h - 1:
            continue
        if (math.hypot(cx0 - lens.cx, cy0 - lens.cy) + math.hypot(bw, bh) / 2 / sx) > 0.98 * lens.radius:
            continue
        sub = lab[y0:y0 + bh, x0:x0 + bw] == k
        pts = _edge_points(np.pad(sub, 1)) + [x0 - 1, y0 - 1]
        fit = _circle_fit(pts) if len(pts) >= 8 else None
        if fit is None or fit[2] < 0.8:
            x, y, r, rms = cents[k][0], cents[k][1], math.sqrt(area / math.pi), 0.5
            method = "centroid"
        else:
            x, y, r, rms = fit
            method = "circle"
        fill = area / (math.pi * max(r, 0.5) ** 2)
        if fill < MIN_FILL or fill > 1.6:
            continue
        csig = max(CENTROID_FLOOR_PX, rms / math.sqrt(max(len(pts), 1) / 4.0) + 0.1 * r)
        ray = _ray(lens, x / sx, y / sx)
        alt_app = 90.0 - math.degrees(math.acos(float(np.clip(ray @ up, -1, 1))))
        if alt_app < min_alt_deg:
            continue
        out.append(Disc(lens.name, float(x), float(y), float(r), area, float(fill), float(g[lab == k].max()),
                        float(csig), ray, alt_app, alt_app - refraction_deg(alt_app), dpp, method))
    return out


def halo_fit(gray: np.ndarray, x0: float, y0: float, r_sat: float, sat: int = SATURATED
             ) -> Optional[Tuple[float, float, float]]:
    """Centre of a saturated body from its halo: I = background plane + H(|p - c|), H a free radial profile
    (piecewise linear in r), fitted on the unsaturated pixels around the core (robust loss). A sky brighter on
    one side (horizon glow, dawn, cloud) moves the edge of the clipped blob, not the centre of a symmetric halo.
    Returns (x, y, sigma_px) or None."""
    from scipy.optimize import least_squares
    R = int(max(5.0 * r_sat, 18.0))
    xi, yi = int(round(x0)), int(round(y0))
    h, w = gray.shape
    if xi - R < 0 or yi - R < 0 or xi + R >= w or yi + R >= h:
        return None
    win = gray[yi - R:yi + R + 1, xi - R:xi + R + 1].astype(float)
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1].astype(float)
    rr0 = np.hypot(xx - (x0 - xi), yy - (y0 - yi))
    use = (win < sat - 5) & (rr0 <= R) & (rr0 >= 0.8 * r_sat)
    if use.sum() < 60:
        return None
    X, Y, V = xx[use], yy[use], win[use]
    knots = np.r_[0.0, np.geomspace(max(r_sat, 1.0), R, 9)]

    def model(p):
        cx, cy, a, b, c = p[:5]
        r = np.hypot(X - cx, Y - cy)
        return a + b * X / R + c * Y / R + np.interp(r, knots, np.r_[p[5:], 0.0][:len(knots)])

    def resid(p):
        return model(p) - V

    p0 = np.r_[x0 - xi, y0 - yi, np.percentile(V, 10), 0.0, 0.0, np.linspace(200, 0, len(knots) - 1)]
    try:
        sol = least_squares(resid, p0, loss="soft_l1", f_scale=3.0, max_nfev=200)
    except Exception:
        return None
    cx, cy = sol.x[:2]
    if math.hypot(cx - (x0 - xi), cy - (y0 - yi)) > max(2.0 * r_sat, 3.0):
        return None
    try:
        J = sol.jac
        s2 = float(np.median(np.abs(sol.fun)) * 1.4826) ** 2
        cov = np.linalg.pinv(J.T @ J) * s2
        sig = float(math.sqrt(max(cov[0, 0] + cov[1, 1], 0.0) / 2.0))
    except Exception:
        sig = 1.0
    return float(cx + xi), float(cy + yi), sig


def lit_centroid_offset(fraction: float) -> float:
    """Offset (in disc radii, towards the Sun) of the light centroid of a Moon lit to `fraction` (orthographic,
    uniform brightness): the halo is centred there, not on the disc's centre."""
    k = 2.0 * fraction - 1.0                                # terminator ellipse: x = k sqrt(1 - y^2)
    y = np.linspace(-1, 1, 801)
    half = np.sqrt(1 - y ** 2)
    x_lo = -k * half                                        # lit from x_lo to +half (Sun at +x)
    area = np.trapz(half - x_lo, y)
    mx = np.trapz((half ** 2 - x_lo ** 2) / 2.0, y)
    return float(mx / area) if area > 1e-9 else 0.0


def sunward_image_dir(ray, up, limb_angle_deg: float, lens: Lens) -> np.ndarray:
    """Unit image direction (lens pixels) from the body's centre towards the Sun: 'up' turned about the line of
    sight by BodyPlace.bright_limb_angle."""
    m = _unit(ray)
    a = _unit(up - np.dot(up, m) * m)
    th = math.radians(limb_angle_deg)
    sun_t = a * math.cos(th) + np.cross(m, a) * math.sin(th)
    p0 = np.array(lens.project((lens.R_lens_imu @ m)[None])[:2]).ravel()
    p1 = np.array(lens.project((lens.R_lens_imu @ _unit(m + 0.01 * sun_t))[None])[:2]).ravel()
    return _unit(p1 - p0)


def refine_centre(gray: np.ndarray, disc: Disc, up_imu, lens: Lens, body: str, fraction: float = 1.0,
                  limb_angle_deg: float = 0.0, semidiameter_deg: float = 0.26, ref_width: float = 3840.0) -> Disc:
    """The disc's centre from its halo (halo_fit); the Moon's halo centre moved back from its light centroid to
    the disc's centre. Without a usable halo: the bright-limb fit (Moon) or the clipped blob's circle (Sun)."""
    import cv2
    g = gray if gray.ndim == 2 else cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    sx = g.shape[1] / ref_width
    up = _unit(up_imu)
    hf = halo_fit(g, disc.x, disc.y, disc.radius_px)
    if hf is None:
        if body == "moon":
            return refine_moon_limb(gray, disc, up_imu, limb_angle_deg, lens, fraction, ref_width=ref_width)
        return disc
    x, y, sig = hf
    method = "halo"
    if body == "moon" and fraction < 0.999:
        sdir = sunward_image_dir(disc.ray, up, limb_angle_deg, lens)
        r_px = semidiameter_deg / disc.deg_per_px
        x, y = np.array([x, y]) - lit_centroid_offset(fraction) * r_px * sdir
        method = "halo, phase-corrected"
    ray = _ray(lens, x / sx, y / sx)
    alt_app = 90.0 - math.degrees(math.acos(float(np.clip(ray @ up, -1, 1))))
    return Disc(disc.lens, float(x), float(y), disc.radius_px, disc.area, disc.fill, disc.peak,
                max(CENTROID_FLOOR_PX, sig), ray, alt_app, alt_app - refraction_deg(alt_app), disc.deg_per_px, method)


def refine_moon_limb(gray: np.ndarray, disc: Disc, up_imu, limb_angle_deg: float, lens: Lens,
                     fraction: float, sat: int = SATURATED, ref_width: float = 3840.0) -> Disc:
    """Moon: the centre from the bright limb only (edge points whose outward normal is within 80 deg of the
    sunward direction), with the circle's radius free. limb_angle_deg: BodyPlace.bright_limb_angle (from 'up'
    towards the Sun, about the line of sight). A nearly full Moon (> 0.9 lit) keeps the full-circle fit."""
    import cv2
    if fraction > 0.9:
        return disc
    g = gray if gray.ndim == 2 else cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    sx = g.shape[1] / ref_width
    up = _unit(up_imu)
    sdir = sunward_image_dir(disc.ray, up, limb_angle_deg, lens)
    r0 = int(max(6, disc.radius_px * 3))
    x0, y0 = int(round(disc.x)) - r0, int(round(disc.y)) - r0
    win = g[max(0, y0):y0 + 2 * r0 + 1, max(0, x0):x0 + 2 * r0 + 1]
    pts = _edge_points(np.pad(win >= sat, 1)) + [max(0, x0) - 1, max(0, y0) - 1]
    if len(pts) < 8:
        return disc
    c = pts.mean(axis=0)
    nrm = _unit(pts - c)
    keep = nrm @ sdir > math.cos(math.radians(80.0))
    fit = _circle_fit(pts[keep]) if keep.sum() >= 8 else None
    if fit is None or fit[2] > 3 * disc.radius_px + 2:
        return disc
    x, y, r, rms = fit
    ray = _ray(lens, x / sx, y / sx)
    alt_app = 90.0 - math.degrees(math.acos(float(np.clip(ray @ up, -1, 1))))
    return Disc(disc.lens, x, y, r, disc.area, disc.fill, disc.peak,
                max(CENTROID_FLOOR_PX, rms / math.sqrt(keep.sum() / 4.0) + 0.15 * r), ray, alt_app,
                alt_app - refraction_deg(alt_app), disc.deg_per_px, "bright limb")


# ── observation, gating, fix ──────────────────────────────────────────────────


@dataclass
class Sight:
    """One measured altitude of a body: what the fix needs."""
    body: str
    utc: str
    alt_deg: float                 # measured, refraction removed (centre of the disc)
    sigma_frame_deg: float         # per-frame part (centroid, IMU noise)
    azimuth_deg: Optional[float] = None
    sigma_az_deg: Optional[float] = None
    disc: Optional[Disc] = field(default=None, repr=False)
    horiz_imu: Optional[np.ndarray] = field(default=None, repr=False)   # the body's horizontal unit vector (IMU)
    lens: Optional[str] = None
    dalt_dfscale_deg: Optional[float] = None       # altitude change for a +1 (100 %) focal-length scale error


def sight_geometry(ray, up, lens: Lens, x: float, y: float, sx: float = 1.0) -> Tuple[np.ndarray, float]:
    """(horizontal unit vector of the ray in the IMU frame, d altitude / d focal scale in deg) of a disc at (x, y)."""
    import copy
    r, u = _unit(ray), _unit(up)
    a = _unit(r - np.dot(r, u) * u)
    L2 = copy.copy(lens)
    L2.f = lens.f * 1.001
    r2 = _ray(L2, x / sx, y / sx)
    h1 = math.degrees(math.asin(float(np.clip(r @ u, -1, 1))))
    h2 = math.degrees(math.asin(float(np.clip(r2 @ u, -1, 1))))
    return a, (h2 - h1) / 0.001


def azimuth_of(ray_imu: np.ndarray, up_imu, north_imu) -> float:
    """Azimuth of a ray (deg from north through east) given 'up' and a north direction in the IMU frame."""
    up = _unit(up_imu)
    n = _unit(np.asarray(north_imu, float) - np.dot(north_imu, up) * up)
    e = np.cross(n, up)
    return math.degrees(math.atan2(float(ray_imu @ e), float(ray_imu @ n))) % 360.0


def sight_from_frame(gray: np.ndarray, up_imu, utc: str, prior: Tuple[float, float, float], body: str = "auto",
                     north_imu=None, sigma_heading_deg: float = 5.0, lenses: Optional[List[Lens]] = None,
                     sigma_bias_deg: Optional[float] = None, ref_width: float = 3840.0,
                     pressure_hpa: float = 1010.0, temp_c: float = 10.0) -> Tuple[Optional[Sight], dict]:
    """The Sun or Moon in one frame, gated by the ephemeris at the prior (lat, lon, sigma_km). Returns (sight or
    None, report). body 'auto': the Sun when it is above the horizon at the prior, else the Moon."""
    lenses = lenses or default_lenses()
    lat, lon, sig_km = prior
    rep: dict = {"utc": utc}
    if body == "auto":
        body = "sun" if body_place("sun", utc).altaz(lat, lon)[0] > -1.0 else "moon"
    place = body_place(body, utc)
    h_c, az_c, _ = place.altaz(lat, lon)
    rep.update(body=body, alt_pred=round(h_c, 3), az_pred=round(az_c, 2))
    sb = math.hypot(SIGMA_UP_DEG, SIGMA_LENS_DEG) if sigma_bias_deg is None else sigma_bias_deg   # gate only
    gate0 = GATE_SIGMA * math.hypot(math.hypot(sb, SIGMA_FRAME_DEG, SIGMA_DRIFT_DEG), sig_km / KM_PER_DEG)
    if h_c - gate0 < MIN_ALT_DEG:
        # the body may be under the detection floor: a lamp or a lit window in the gate would be taken for it
        # (synthetic: the Moon at 10.3 deg, a light at 15.3 deg accepted, 4.9 deg off)
        rep["why"] = f"{body} at {h_c:.1f} deg: may be below the {MIN_ALT_DEG:g} deg floor within the gate"
        return None, rep
    if body == "moon" and place.illuminated_fraction() < MOON_MIN_LIT:
        rep["why"] = f"Moon only {place.illuminated_fraction():.0%} lit (< {MOON_MIN_LIT:.0%})"
        return None, rep
    discs = detect_discs(gray, up_imu, lenses, ref_width=ref_width)
    pf = (pressure_hpa / 1010.0) * (283.0 / (273.0 + temp_c))   # refraction scales with the air's density
    for d in discs:
        d.alt_deg = d.alt_app_deg - refraction_deg(d.alt_app_deg) * pf
    rep["candidates"] = len(discs)
    ok = []
    for d in discs:
        sig = math.hypot(math.hypot(sb, SIGMA_FRAME_DEG, SIGMA_DRIFT_DEG), d.centroid_sigma_px * d.deg_per_px)
        gate_alt = GATE_SIGMA * math.hypot(sig, sig_km / KM_PER_DEG) + place.semidiameter_deg(lat, lon) * 0.0
        if abs(d.alt_deg - h_c) > gate_alt:
            continue
        az = None
        if north_imu is not None:
            az = azimuth_of(d.ray, up_imu, north_imu)
            daz = (az - az_c + 180.0) % 360.0 - 180.0
            # the prior's position error moves the azimuth by ~ sig_km / (distance to the GP) (rad), small
            if abs(daz) > GATE_SIGMA * math.hypot(sigma_heading_deg, 1.0):
                continue
        ok.append((d, az))
    rep["in_gate"] = len(ok)
    if not ok:
        rep["why"] = f"no {body} candidate within the altitude gate"
        return None, rep
    if len(ok) > 1:
        rep["why"] = f"{len(ok)} candidates in the gate: ambiguous"
        return None, rep
    d, az = ok[0]
    # the Sun and the Moon outshine every lamp, planet and star: a bigger clipped blob elsewhere means the one in
    # the gate is not the body (ESO MASCOT: a light at 12 deg taken while the Moon was hidden, 3.9 deg off)
    if any(o.area > d.area for o in discs):
        rep["why"] = "a bigger saturated blob outside the gate: the one in the gate is not the body"
        return None, rep
    lens = next(L for L in lenses if L.name == d.lens)
    frac = place.illuminated_fraction()
    limb = place.bright_limb_angle(lat, lon) if body == "moon" else 0.0
    d = refine_centre(gray, d, up_imu, lens, body, frac, limb, place.semidiameter_deg(lat, lon), ref_width)
    d.alt_deg = d.alt_app_deg - refraction_deg(d.alt_app_deg) * pf
    if body == "moon":
        rep["moon_lit"] = round(frac, 3)
    a_h, g = sight_geometry(d.ray, up_imu, lens, d.x, d.y, gray.shape[1] / ref_width)
    s = Sight(body, utc, d.alt_deg, math.hypot(SIGMA_FRAME_DEG, d.centroid_sigma_px * d.deg_per_px), az,
              sigma_heading_deg if az is not None else None, d, a_h, d.lens, g)
    rep.update(alt_meas=round(d.alt_deg, 3), intercept_deg=round(d.alt_deg - h_c, 3), method=d.method,
               radius_px=round(d.radius_px, 2), centroid_sigma_px=round(d.centroid_sigma_px, 2),
               dalt_dfscale_deg=round(g, 2), lens=d.lens, horiz_imu=[round(float(v), 5) for v in a_h])
    return s, rep


@dataclass
class Fix:
    lat: float
    lon: float
    cov_km2: np.ndarray            # (north, east)
    chi2: float
    dof: int
    n_alt: int
    n_az: int
    accepted: bool
    why: str = ""

    @property
    def sigma_major_km(self) -> float:
        return float(math.sqrt(max(np.linalg.eigvalsh(self.cov_km2)))) if self.cov_km2 is not None else float("inf")

    @property
    def sigma_minor_km(self) -> float:
        return float(math.sqrt(max(min(np.linalg.eigvalsh(self.cov_km2)), 0.0)))

    def mahalanobis(self, lat: float, lon: float) -> float:
        dn = (lat - self.lat) * KM_PER_DEG
        de = (lon - self.lon) * KM_PER_DEG * math.cos(math.radians(self.lat))
        v = np.array([dn, de])
        return float(math.sqrt(v @ np.linalg.solve(self.cov_km2, v)))


def thin(sights: List[Sight], bin_s: float = BIN_S) -> List[Sight]:
    """One sight (the middle one in time) per body and BIN_S window. Frames seconds apart share almost all their
    error (bloom, cloud, the body's place in the lens); fed one by one they made the real night's fix 3.6 sigma
    off (467 sights), one per 10 min kept it within 2.6 sigma. For a still camera a tilt of 'up' is exactly a
    position shift (both move the altitudes as the cosine of the azimuth): crossing lines cannot beat it."""
    if not sights:
        return []
    t = np.array([_utc_seconds(s.utc) for s in sights])
    key = [(s.body, int((ti - t.min()) // bin_s)) for s, ti in zip(sights, t)]
    out = []
    for k in sorted(set(key), key=lambda kk: (kk[1], kk[0])):
        idx = [i for i, kk in enumerate(key) if kk == k]
        idx.sort(key=lambda i: t[i])
        out.append(sights[idx[len(idx) // 2]])
    return out


def altitude_covariance(alts: List[Sight], sigma_common_deg: float, sigma_drift_deg: float, same_bin: np.ndarray,
                        sigma_up_deg: float = SIGMA_UP_DEG, sigma_fscale: float = SIGMA_FSCALE) -> np.ndarray:
    """Covariance (deg^2) of the altitude errors of sights: frame + common centre bias + drift per window + tilt of
    'up' (tilt . horizontal directions, in the camera frame) + focal scale per lens (dalt/dscale products). A sight
    without its geometry gets the tilt and focal parts as common (conservative)."""
    n = len(alts)
    R = np.diag([s.sigma_frame_deg ** 2 for s in alts]) + sigma_common_deg ** 2 * np.ones((n, n))
    R += sigma_drift_deg ** 2 * (same_bin[:, None] == same_bin[None, :])
    geo = [s.horiz_imu is not None and s.dalt_dfscale_deg is not None for s in alts]
    if all(geo):
        A = np.array([s.horiz_imu for s in alts], float)
        R += sigma_up_deg ** 2 * (A @ A.T)
        g = np.array([s.dalt_dfscale_deg for s in alts], float)
        same_lens = np.array([[a.lens == b.lens for b in alts] for a in alts])
        R += sigma_fscale ** 2 * np.outer(g, g) * same_lens
    else:
        R += (sigma_up_deg ** 2 + (sigma_fscale * 40.0) ** 2) * np.ones((n, n))
    return R


def fuse(sights: List[Sight], prior: Tuple[float, float, float], sigma_bias_deg: Optional[float] = None,
         iters: int = 6, p_min: float = 1e-3, sigma_drift_deg: float = SIGMA_DRIFT_DEG,
         sigma_up_deg: float = SIGMA_UP_DEG, sigma_fscale: float = SIGMA_FSCALE) -> Fix:
    """Position from altitude (and azimuth) sights + the prior (lat, lon, 1-sigma km), generalized least squares.
    The altitude errors: sigma_bias_deg common to all sights (mounting / 'up' bias), sigma_drift_deg common to the
    sights of one BIN_S window, and each sight's own part: many frames of one window count about as one sight."""
    from scipy.stats import chi2 as chi2_dist
    lat0, lon0, sp = prior
    sb = SIGMA_CENTRE_DEG if sigma_bias_deg is None else sigma_bias_deg
    sights = thin(sights)
    alts = [s for s in sights if s.alt_deg is not None]
    azs = [s for s in sights if s.azimuth_deg is not None]
    if not alts:
        return Fix(lat0, lon0, np.eye(2) * sp ** 2, 0.0, 0, 0, 0, False, "no sight")
    na = len(alts)
    t = np.array([_utc_seconds(s.utc) for s in alts])
    same_bin = np.floor((t - t.min()) / BIN_S)
    R = altitude_covariance(alts, sb, sigma_drift_deg, same_bin, sigma_up_deg, sigma_fscale)
    Raz = np.diag([s.sigma_az_deg ** 2 for s in azs]) if azs else np.zeros((0, 0))
    W = np.linalg.inv(np.block([[R, np.zeros((na, len(azs)))], [np.zeros((len(azs), na)), Raz]]))
    x = np.zeros(2)                                        # (north, east) km from the prior
    P0 = np.eye(2) / sp ** 2

    def model(xk):
        la, lo = offset_latlon(lat0, lon0, xk[0], xk[1])
        out = []
        for s in alts:
            out.append(body_place(s.body, s.utc).altaz(la, lo)[0])
        for s in azs:
            out.append(body_place(s.body, s.utc).altaz(la, lo)[1])
        return np.array(out)

    z = np.array([s.alt_deg for s in alts] + [s.azimuth_deg for s in azs])
    for _ in range(iters):
        f0 = model(x)
        J = np.zeros((len(z), 2))
        for j, dk in enumerate(np.eye(2) * 1.0):
            J[:, j] = (model(x + dk) - f0)
        r = z - f0
        r[na:] = (r[na:] + 180.0) % 360.0 - 180.0
        H = J.T @ W @ J + P0
        g = J.T @ W @ r - P0 @ x
        dx = np.linalg.solve(H, g)
        x = x + dx
        if np.linalg.norm(dx) < 0.01:
            break
    f0 = model(x)
    r = z - f0
    r[na:] = (r[na:] + 180.0) % 360.0 - 180.0
    cov = np.linalg.inv(J.T @ W @ J + P0)
    chi2 = float(r @ W @ r + x @ P0 @ x)
    dof = len(z)
    la, lo = offset_latlon(lat0, lon0, x[0], x[1])
    p = float(chi2_dist.sf(chi2, dof)) if dof > 0 else 1.0
    ok = p >= p_min
    return Fix(la, lo, cov, chi2, dof, na, len(azs), ok, "" if ok else f"sights disagree with one position "
               f"(chi2 {chi2:.1f} / {dof}, p {p:.1g})")


def _utc_seconds(utc: str) -> float:
    from datetime import datetime, timezone
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in utc else "%Y-%m-%d %H:%M:%S"
    return datetime.strptime(utc, fmt).replace(tzinfo=timezone.utc).timestamp()


def fit_errors(sights: List[Sight], lat: float, lon: float) -> dict:
    """While GPS is valid: the sights' systematic errors against the ephemeris at the GPS place, by generalized least
    squares with the error model's priors: common centre bias (deg), tilt of 'up' (IMU-frame vector, deg) and the
    focal scale of each lens. Returns {"bias", "tilt", "fscale": {lens: s}, "n"}; correct() applies it."""
    alts = [s for s in sights if s.horiz_imu is not None and s.dalt_dfscale_deg is not None]
    lenses = sorted({s.lens for s in alts})
    if not alts:
        return {"bias": 0.0, "tilt": [0.0, 0.0, 0.0], "fscale": {}, "n": 0}
    n, k = len(alts), 4 + len(lenses)
    J = np.zeros((n, k))
    r = np.zeros(n)
    for i, s in enumerate(alts):
        J[i, 0] = 1.0
        J[i, 1:4] = np.asarray(s.horiz_imu, float)          # alt error (deg) = tilt (deg) . horizontal unit
        J[i, 4 + lenses.index(s.lens)] = s.dalt_dfscale_deg
        r[i] = s.alt_deg - body_place(s.body, s.utc).altaz(lat, lon)[0]
    t = np.array([_utc_seconds(s.utc) for s in alts])
    Rn = np.diag([s.sigma_frame_deg ** 2 for s in alts]) + SIGMA_DRIFT_DEG ** 2 * (
        np.floor((t - t.min()) / BIN_S)[:, None] == np.floor((t - t.min()) / BIN_S)[None, :])
    P = np.diag([1 / SIGMA_CENTRE_DEG ** 2] + [1 / SIGMA_UP_DEG ** 2] * 3 + [1 / SIGMA_FSCALE ** 2] * len(lenses))
    W = np.linalg.inv(Rn)
    x = np.linalg.solve(J.T @ W @ J + P, J.T @ W @ r)
    return {"bias": float(x[0]), "tilt": [float(v) for v in x[1:4]],
            "fscale": {L: float(x[4 + j]) for j, L in enumerate(lenses)}, "n": n}


def correct(sights: List[Sight], err: dict) -> List[Sight]:
    """Sights with fit_errors' systematic errors removed (fuse them with the smaller *_AFTER_FIT sigmas)."""
    out = []
    for s in sights:
        c = err["bias"]
        if s.horiz_imu is not None:
            c += float(np.dot(err["tilt"], s.horiz_imu))
        if s.dalt_dfscale_deg is not None and s.lens in err["fscale"]:
            c += err["fscale"][s.lens] * s.dalt_dfscale_deg
        out.append(Sight(s.body, s.utc, s.alt_deg - c, s.sigma_frame_deg, s.azimuth_deg, s.sigma_az_deg, s.disc,
                         s.horiz_imu, s.lens, s.dalt_dfscale_deg))
    return out


def expected_sigma_km(sigma_up_deg: float = SIGMA_UP_DEG, sigma_lens_deg: float = SIGMA_LENS_DEG,
                      centroid_px: float = 1.0, deg_per_px: float = 0.1) -> float:
    """Across-the-line 1-sigma of one sight without the prior (km)."""
    return KM_PER_DEG * math.sqrt(sigma_up_deg ** 2 + sigma_lens_deg ** 2 + SIGMA_FRAME_DEG ** 2
                                  + SIGMA_DRIFT_DEG ** 2 + (centroid_px * deg_per_px) ** 2)
