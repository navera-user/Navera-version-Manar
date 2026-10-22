"""All-sky star identification for the Insta360's full 360 frame (lost-in-space, gravity-aided).

A short video exposure shows only bright stars, too few in any single window for astrometry.net
(simulated 50 degree windows: stars to magnitude 5 always solved, to 4 two times in six, to 3.5
never). Both fisheye circles together see the whole sky above the camera, ~20 times one window,
so even magnitude-3 stars give dozens of points. Like a satellite star tracker:

1. detect bright spots in both circles and turn them into unit rays in the IMU frame;
2. drop spots below `min_alt` (the accelerometer says where the horizon is) and undo refraction;
3. for pairs of bright spots, look up catalogue pairs with the same angular separation, take the
   rotation that maps the pair (TRIAD), count how many other spots land on catalogue stars;
4. the best rotation, refined on all matched stars (Wahba / SVD), maps 'up' (gravity) to the
   zenith among the stars → latitude = its declination, longitude = its RA - sidereal time.

The focal length of the lens is not measured yet: `locate` searches it (and keeps the best),
so the lens calibrates itself on the first frames that match.

Shared by the flight node (cn_pkg cn_subscriber, solver_mode allsky360) and the field tools
(navera_tools.field.allsky is this very module, so the field server's live knobs set here act on both).
Fully offline: the star catalogue is read from a local file, never downloaded.
"""
import math
import os
from typing import List, Optional, Sequence

import numpy as np

from cn_pkg.nodes.celestial_math import apparent_radec, gast_deg
from cn_pkg.sky360 import Lens, default_lenses

KM_PER_DEG = 111.2


def _unit(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def radec_to_vec(ra_deg, dec_deg):
    ra, dec = np.radians(ra_deg), np.radians(dec_deg)
    return np.stack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)], axis=-1)


def vec_to_radec(v):
    v = v / np.linalg.norm(v)
    return math.degrees(math.atan2(v[1], v[0])) % 360.0, math.degrees(math.asin(max(-1.0, min(1.0, v[2]))))


# the bright-star list shipped with the package (Yale BSC5 to mag 4.5, the same numbers as parsed from bsc5.dat)
BUNDLED_CATALOGUE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "bsc5_mag4.5.csv")


def load_bsc5(path: str):
    """(ra deg, dec deg, V mag) arrays (ICRS / J2000) from a local Yale BSC5 file: the catalogue's fixed-width
    text (bsc5.dat) or the bundled CSV (ra,dec,mag). Never downloads (NAVERA runs offline).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"star catalogue {path} not found (offline: install it before departure)")
    if path.endswith(".csv"):
        a = np.loadtxt(path, delimiter=",", comments="#", ndmin=2)
        return a[:, 0].copy(), a[:, 1].copy(), a[:, 2].copy()
    ra, dec, mag = [], [], []
    with open(path, "rb") as f:
        for raw in f:
            line = raw.decode("latin-1")
            try:
                rah, ram, ras = int(line[75:77]), int(line[77:79]), float(line[79:83])
                sign = -1.0 if line[83] == "-" else 1.0
                ded, dem, des = int(line[84:86]), int(line[86:88]), int(line[88:90])
                v = float(line[102:107])
            except ValueError:
                continue                       # a few entries have no position (novae...)
            ra.append(15.0 * (rah + ram / 60.0 + ras / 3600.0))
            dec.append(sign * (ded + dem / 60.0 + des / 3600.0))
            mag.append(v)
    return np.array(ra), np.array(dec), np.array(mag)


class Catalogue:
    """Bright stars (Yale BSC5, ICRS) and their pair separations, sorted for range lookups.
    path: a local catalogue file (bsc5.dat or the bundled CSV); default <work_dir>/bsc5.dat.
    """

    def __init__(self, work_dir: str = os.path.expanduser("~/.navera_sim"), limit_mag: float = 4.0,
                 max_sep_deg: float = 60.0, path: Optional[str] = None):
        ra, dec, mag = load_bsc5(path or os.path.join(work_dir, "bsc5.dat"))
        keep = mag <= limit_mag
        self.mag = mag[keep]
        self.vec = radec_to_vec(ra[keep], dec[keep])
        n = len(self.vec)
        i, j = np.triu_indices(n, 1)
        sep = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", self.vec[i], self.vec[j]), -1, 1)))
        k = sep <= max_sep_deg
        order = np.argsort(sep[k])
        self.pair_i, self.pair_j, self.pair_sep = i[k][order], j[k][order], sep[k][order]

    def pairs_near(self, sep_deg: float, tol_deg: float):
        lo, hi = np.searchsorted(self.pair_sep, [sep_deg - tol_deg, sep_deg + tol_deg])
        return self.pair_i[lo:hi], self.pair_j[lo:hi]


NOISE_BLOCK = 32          # px: the noise is measured per block (sky glow, moon and clouds make it vary over the frame)
NOISE_FLOOR = 1.0         # DN: an 8-bit, compressed dark sky can show zero spread; never threshold below this
SATURATED = 250           # DN
MAX_AREA = 150            # px above 3 sigma: a mag -2 star (simulated PSF) covers ~70; lamps, moon, glare far more
MAX_SATURATED = 45        # px at >= 250 DN: Jupiter in the simulation ~37; a street lamp of radius >= 4 px more
MAX_SHARPNESS = 0.6       # centre / 3x3 sum of the residual: hot pixel ~1, star (PSF sigma >= 0.5 px) <= 0.6
# defaults of detect_spots / locate, module-level so the field server can tune them live (live_params.json)
DETECT_K_SIGMA = 6.0      # a spot's peak above this many times the local noise
LOCATE_MAX_SPOTS = 60     # brightest spots above LOCATE_MIN_ALT given to the identification
LOCATE_MATCH_DEG = 0.5    # a spot and a catalogue star match within this angle
LOCATE_MIN_ALT = 12.0     # deg above the horizon (ground, lamps, roofs below)


def detect_spots(gray: np.ndarray, lens: Lens, k_sigma: Optional[float] = None, max_spots: int = 120,
                 up_imu: Optional[np.ndarray] = None, min_alt: Optional[float] = None,
                 stats: Optional[dict] = None):
    """Star-like spots inside the lens circle: (x, y, flux) sorted brightest first.

    Threshold k_sigma x the LOCAL noise (per NOISE_BLOCK block), one spot per connected blob, and blobs
    that cannot be a star are dropped: extended (lamps, moon, glare, meteors, lit clouds), saturated
    over a large area, or a single hot pixel. With up_imu and min_alt, spots below that altitude
    (ground, lamps, windows) are dropped before the max_spots cap so they cannot crowd out the sky.
    stats (optional dict) receives the number of blobs rejected per reason.
    """
    H = gray.shape[0]
    x0, x1 = int(max(0, lens.cx - lens.radius)), int(min(gray.shape[1], lens.cx + lens.radius))
    y0, y1 = int(max(0, lens.cy - lens.radius)), int(min(H, lens.cy + lens.radius))

    def inside(xx, yy):
        return np.hypot(xx + x0 - lens.cx, yy + y0 - lens.cy) < lens.radius - 8

    below = None
    if up_imu is not None and min_alt is not None:
        def below(xx, yy):
            up = up_imu / np.linalg.norm(up_imu)
            alt = np.degrees(np.arcsin(np.clip(unproject(lens, xx + x0, yy + y0) @ up, -1, 1)))
            return alt < min_alt
    return _detect_blobs(gray[y0:y1, x0:x1], x0, y0, inside, below, k_sigma, max_spots, stats)


def detect_spots_view(gray: np.ndarray, mask: Optional[np.ndarray] = None, k_sigma: Optional[float] = None,
                      max_spots: int = 60, stats: Optional[dict] = None, border: int = 8):
    """detect_spots for a rectangular (pinhole) view: the same local-noise threshold and the same star-shape blob
    filters (extended, saturated, hot pixel), over the pixels where mask is non-zero (all when None) and at least
    border px from the edges. Used by the screen bench (bench/celestial_screen.py) so that it judges the stars
    the way the field does (F18: its own peak finder took ~60 spurious spots in clouds and rain).
    """
    h, w = gray.shape[:2]

    def inside(xx, yy):
        ok = (xx >= border) & (yy >= border) & (xx < w - border) & (yy < h - border)
        if mask is not None:
            ok &= mask[yy, xx] > 0
        return ok
    return _detect_blobs(gray, 0, 0, inside, None, k_sigma, max_spots, stats)


def _detect_blobs(raw: np.ndarray, x0: int, y0: int, inside, below, k_sigma: Optional[float], max_spots: int,
                  stats: Optional[dict]):
    """The detector shared by detect_spots (one fisheye circle, cropped at x0, y0) and detect_spots_view.
    inside(xx, yy) / below(xx, yy): boolean masks over candidate peaks in raw's coordinates.
    """
    import cv2
    k_sigma = DETECT_K_SIGMA if k_sigma is None else k_sigma
    sub = raw.astype(np.float32)
    res = sub - cv2.GaussianBlur(sub, (0, 0), 12)
    h, w = res.shape
    B = NOISE_BLOCK
    hb, wb = max(1, h // B), max(1, w // B)
    blocks = np.abs(res[:hb * B, :wb * B]).reshape(hb, B, wb, B).transpose(0, 2, 1, 3).reshape(hb, wb, B * B)
    noise_b = np.maximum(1.4826 * np.median(blocks, axis=2), NOISE_FLOOR).astype(np.float32)
    noise = cv2.resize(noise_b, (w, h), interpolation=cv2.INTER_LINEAR)
    snr = res / noise
    peak = (res == cv2.dilate(res, np.ones((7, 7), np.uint8))) & (snr > k_sigma)
    n_lab, lab, st, _ = cv2.connectedComponentsWithStats((snr > 3.0).astype(np.uint8), connectivity=8)
    yy, xx = np.nonzero(peak)
    ok = inside(xx, yy)
    yy, xx = yy[ok], xx[ok]
    rej = {"extended": 0, "saturated": 0, "hot_pixel": 0, "below_horizon": 0}
    if len(xx) == 0:
        if stats is not None:
            stats.update(rej)
        return []
    # one spot per blob: its highest peak
    lb = lab[yy, xx]
    order = np.lexsort((-res[yy, xx], lb))
    first = np.ones(len(order), bool)
    first[1:] = lb[order][1:] != lb[order][:-1]
    sel = order[first]
    yy, xx, lb = yy[sel], xx[sel], lb[sel]
    sat = np.bincount(lab[raw >= SATURATED], minlength=n_lab)
    keep = np.ones(len(xx), bool)
    big = st[lb, cv2.CC_STAT_AREA] > MAX_AREA
    rej["extended"] = int(big.sum())
    keep &= ~big
    s_bad = keep & (sat[lb] > MAX_SATURATED)
    rej["saturated"] = int(s_bad.sum())
    keep &= ~s_bad
    pad = np.pad(res, 3)
    s3 = sum(pad[yy + 3 + dy, xx + 3 + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1))
    hot = keep & (res[yy, xx] > MAX_SHARPNESS * np.maximum(s3, 1e-6))
    rej["hot_pixel"] = int(hot.sum())
    keep &= ~hot
    yy, xx, lb = yy[keep], xx[keep], lb[keep]
    if below is not None and len(xx):
        low = below(xx, yy)
        rej["below_horizon"] = int(low.sum())
        yy, xx, lb = yy[~low], xx[~low], lb[~low]
    if stats is not None:
        stats.update(rej)
    # centroid and flux over the blob's own pixels in a 7x7 box (blurred streaks keep their middle)
    padl = np.pad(lab, 3, constant_values=-1)
    out = []
    gy, gx = np.mgrid[-3:4, -3:4]
    for x, y, L in zip(xx, yy, lb):
        win = pad[y:y + 7, x:x + 7].clip(0) * (padl[y:y + 7, x:x + 7] == L)
        s = float(win.sum())
        if s <= 0:
            continue
        out.append((float(x + x0 + (win * gx).sum() / s), float(y + y0 + (win * gy).sum() / s), s))
    out.sort(key=lambda t: -t[2])
    return out[:max_spots]


def unproject(lens: Lens, x, y, f: Optional[float] = None, k1: Optional[float] = None):
    """Pixels → unit rays in the IMU frame (inverse of Lens.project, Newton on the k1 term)."""
    f = f or lens.f
    k1 = lens.k1 if k1 is None else k1
    dx, dy = np.asarray(x) - lens.cx, np.asarray(y) - lens.cy
    r = np.hypot(dx, dy)
    theta = r / f
    for _ in range(5):
        theta = theta - (theta + k1 * theta ** 3 - r / f) / (1 + 3 * k1 * theta ** 2)
    with np.errstate(invalid="ignore", divide="ignore"):
        ux, uy = np.where(r > 0, dx / r, 0.0), np.where(r > 0, dy / r, 0.0)
    v_lens = np.stack([np.sin(theta) * ux, np.sin(theta) * uy, np.cos(theta)], axis=-1)
    return v_lens @ lens.R_lens_imu                                       # R.T @ v for each row


def refraction_deg(alt_deg):
    """Bennett: apparent − true altitude (standard atmosphere)."""
    a = np.maximum(alt_deg, 1.0)
    return (1.0 / np.tan(np.radians(a + 7.31 / (a + 4.4)))) / 60.0


def triad(a1, a2, b1, b2):
    """Rotation R with R @ a ≈ b for the two pairs (a1 exact)."""
    def frame(u, v):
        t1 = u
        t2 = np.cross(u, v)
        t2 = t2 / np.linalg.norm(t2)
        return np.stack([t1, t2, np.cross(t1, t2)], axis=1)
    return frame(b1, b2) @ frame(a1, a2).T


def wahba(a, b, w=None):
    """Best rotation R (R @ a_i ≈ b_i) by SVD."""
    w = np.ones(len(a)) if w is None else w
    B = (w[:, None] * b).T @ a
    U, _, Vt = np.linalg.svd(B)
    d = np.sign(np.linalg.det(U @ Vt))
    return U @ np.diag([1, 1, d]) @ Vt


def _frames(u, v):
    """Orthonormal frames (columns u, u x v, u x (u x v)) for stacked vector pairs (..., 3)."""
    t2 = np.cross(u, v)
    t2 = t2 / np.linalg.norm(t2, axis=-1, keepdims=True)
    return np.stack([u, t2, np.cross(u, t2)], axis=-1)


def match(rays: np.ndarray, R: np.ndarray, tree, chord: float):
    """Ray indices, catalogue indices and chord distances of the rays that land within `chord` of a
    catalogue star once rotated by R; each catalogue star keeps only its closest ray.
    """
    d, k = tree.query(rays @ R.T, distance_upper_bound=chord)
    ok = np.nonzero(np.isfinite(d))[0]
    if len(ok) == 0:
        return ok, ok, d[ok]
    o = ok[np.lexsort((d[ok], k[ok]))]
    first = np.ones(len(o), bool)
    first[1:] = k[o][1:] != k[o][:-1]
    o = o[first]
    return o, k[o], d[o]


def chance_probability(n_rays: int, n_matched: int, n_hyp: int, cat: Catalogue, match_deg: float) -> float:
    """Probability that SOME of the n_hyp rotations tried lines up n_matched of n_rays junk points with
    catalogue stars by chance (Bonferroni bound). The two rays that built a rotation match by
    construction and are not counted.
    """
    from scipy.stats import binom
    p = len(cat.vec) * (1.0 - math.cos(math.radians(match_deg))) / 2.0      # fraction of the sky near a star
    k, n = n_matched - 2, max(0, n_rays - 2)
    if k <= 0:
        return 1.0
    return float(min(1.0, n_hyp * binom.sf(k - 1, n, p)))


def identify(rays: np.ndarray, cat: Catalogue, n_seed: int = 16, tol_deg: float = 0.5,
             match_deg: float = 0.5, min_matches: int = 6, stop_p: float = 1e-15, with_p: bool = False):
    """(rotation IMU→ICRS, matched ray indices, catalogue indices, rms deg[, chance probability if with_p]) or None.
    No quality gate here: a caller that acts on the answer must apply accept() (locate does).

    Lost-in-space: every pair of the n_seed brightest rays is compared with the catalogue pairs of the
    same separation; each candidate rotation (TRIAD, vectorised over all candidates of a pair) is
    first scored on the seed rays only, the promising ones on all rays. The chance probability
    (chance_probability, conditioned on the number of rotations tried) says how likely the best
    match is to be junk lined up with stars; the search stops early once it is below stop_p.
    """
    from scipy.spatial import cKDTree
    tree = getattr(cat, "_tree", None)
    if tree is None:
        tree = cat._tree = cKDTree(cat.vec)
    chord = 2 * math.sin(math.radians(match_deg) / 2)
    seed = rays[:n_seed]
    ns = len(seed)
    best_n, best_R, n_hyp = 0, None, 0
    for i in range(ns):
        for j in range(i + 1, ns):
            sep = math.degrees(math.acos(max(-1.0, min(1.0, float(seed[i] @ seed[j])))))
            if sep < 3.0 or sep > 60.0:
                continue
            ci, cj = cat.pairs_near(sep, tol_deg)
            if len(ci) == 0:
                continue
            P, Q = np.concatenate([ci, cj]), np.concatenate([cj, ci])
            Rs = _frames(cat.vec[P], cat.vec[Q]) @ _frames(seed[i], seed[j]).T          # (M, 3, 3)
            n_hyp += len(Rs)
            d, _ = tree.query(np.einsum("mab,nb->mna", Rs, seed).reshape(-1, 3), distance_upper_bound=chord)
            cnt = np.isfinite(d).reshape(len(Rs), ns).sum(axis=1)
            good = np.nonzero(cnt >= 3)[0]                       # the pair + at least one other seed
            if len(good) > 64:
                good = good[np.argsort(-cnt[good])[:64]]
            if len(good) == 0:
                continue
            d, _ = tree.query(np.einsum("mab,nb->mna", Rs[good], rays).reshape(-1, 3), distance_upper_bound=chord)
            full = np.isfinite(d).reshape(len(good), len(rays)).sum(axis=1)
            b = int(np.argmax(full))
            if full[b] > best_n:
                best_n, best_R = int(full[b]), Rs[good[b]]
                if chance_probability(len(rays), best_n, n_hyp, cat, match_deg) < stop_p:
                    break
        else:
            continue
        break
    if best_n < min_matches:
        return None
    n_unique = len(match(rays, best_R, tree, chord)[0])         # matches of the rotation as found, before any fit
    p_chance = chance_probability(len(rays), n_unique, n_hyp, cat, match_deg)
    R = best_R
    for _ in range(3):                                                # refine on every match
        ok, k, _ = match(rays, R, tree, chord)
        if len(ok) < 3:
            return None
        R = wahba(rays[ok], cat.vec[k])
    ok, k, d = match(rays, R, tree, chord)
    rms = math.degrees(float(np.sqrt(np.mean((2 * np.arcsin(d / 2)) ** 2))))
    return (R, ok, k, rms, p_chance) if with_p else (R, ok, k, rms)


# 'up' is the accelerometer's mean: any vehicle acceleration tilts it (0.1 g = 5.7 degrees = 640 km). Its norm is
# sqrt(1 + a^2) g, so a tolerance on the norm only catches a > ~sqrt(2 tol): 0.01 → braking/accelerating > 0.14 g.
# Smaller accelerations (gentle speed changes) are NOT detectable from the accelerometer alone.
ACCEL_NORM_TOL = 0.01

# quality gate: a wrong fix is worse than no fix. Accepted when
#   matched >= MIN_MATCHED and rms <= MAX_RMS_DEG and
#   (p_chance <= MAX_P_CHANCE  or  (p_chance <= MAX_P_CHANCE_TIGHT and rms <= MAX_RMS_TIGHT_DEG)
#    or  (p_chance <= MAX_P_CHANCE_LOOSE and rms <= MAX_RMS_LOOSE_DEG))
# and the two lenses agree. p_chance (chance_probability): probability that junk spots line up with this many
# catalogue stars for one of the rotations tried; 60 spots, ~1e5 rotations: 11 matches 6e-4, 14 matches 5e-8.
# Calibrated on the real camera bench (2026-10-17, catalogue stars on a screen, identify() before this gate):
#  - lit room, 60 spots mostly room features: 16/16 frames matched 8-11, rms 0.23-0.34, ALL wrong (10-160 deg);
#  - dark room, 27 frames: 23 right (rms 0.036-0.169, p 1e-58..7e-2), 4 wrong (rms 0.212-0.345, p >= 1.1e-2).
#    This gate rejects the 4 wrong and accepts 20 of the 23 right (refuses noise mag 3: p 1.3e-6 rms 0.169,
#    noise mag 2.5 and clouds mag 3: p ~1e-2). rms alone separates them by a thin margin only (0.169 / 0.212).
MIN_MATCHED = 7
MAX_P_CHANCE = 1e-6
MAX_P_CHANCE_TIGHT = 1e-4       # allowed only with a residual typical of a true match
MAX_RMS_DEG = 0.2
MAX_RMS_TIGHT_DEG = 0.12
# third tier (real camera, screen campaign 2026-10-19, 162 cases): the 16 right identifications refused as
# "chance" had p <= 1.2e-2 and rms <= 0.09 deg (one 0.13); all 44 wrong ones had rms >= 0.16 deg and p >= 0.07
# (2026-10-17: wrong ones rms >= 0.212). A small residual is what a chance alignment of junk spots cannot fake.
MAX_P_CHANCE_LOOSE = 1e-2
MAX_RMS_LOOSE_DEG = 0.10
MAX_LENS_DISAGREE_DEG = 1.0     # zenith from each lens alone (when both have >= 4 stars)
K1_FIT_MIN_STARS = 20           # the radial term is refitted only with this many matched stars


def accept(matched: int, rms_deg: float, p_chance: float, lens_disagree_deg: float = 0.0) -> Optional[str]:
    """The quality gate: None when the identification may be used, else the reason it may not."""
    if matched < MIN_MATCHED:
        return f"only {matched} stars matched (< {MIN_MATCHED})"
    if p_chance > MAX_P_CHANCE_TIGHT and not (p_chance <= MAX_P_CHANCE_LOOSE and rms_deg <= MAX_RMS_LOOSE_DEG):
        return f"match could be chance (p = {p_chance:.2g})"
    if rms_deg > MAX_RMS_DEG:
        return f"star residual {rms_deg:.2f} deg (> {MAX_RMS_DEG})"
    if p_chance > MAX_P_CHANCE and rms_deg > MAX_RMS_TIGHT_DEG:
        return f"match could be chance (p = {p_chance:.2g}) and residual {rms_deg:.2f} deg (> {MAX_RMS_TIGHT_DEG})"
    if lens_disagree_deg > MAX_LENS_DISAGREE_DEG:
        return f"the two lenses disagree by {lens_disagree_deg:.2f} deg"
    return None


def locate(frame: np.ndarray, up_imu: np.ndarray, utc: str, cat: Catalogue,
           lenses: Optional[List[Lens]] = None, f_scales: Sequence[float] = (1.0,),
           min_alt: Optional[float] = None, max_spots: Optional[int] = None, match_deg: Optional[float] = None,
           retry_spots: int = 25) -> dict:
    """Latitude, longitude from the whole sky above the camera. f_scales: focal lengths to try
    (x each lens's f); the best one is reported so the caller can keep it.

    A fix is returned only if it passes the quality gate (MIN_MATCHED, MAX_P_CHANCE, MAX_RMS_DEG,
    MAX_LENS_DISAGREE_DEG); otherwise solved=False and 'why' says which test failed (after one retry on
    the retry_spots brightest spots, when junk may have crowded the first attempt). sigma_fit_deg
    is the zenith's uncertainty from the star fit alone (residuals, the two lenses' disagreement);
    the caller adds the accelerometer's and the clock's.
    """
    import cv2
    min_alt = LOCATE_MIN_ALT if min_alt is None else min_alt
    max_spots = LOCATE_MAX_SPOTS if max_spots is None else max_spots
    match_deg = LOCATE_MATCH_DEG if match_deg is None else match_deg
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    lenses = lenses or default_lenses()
    up = up_imu / np.linalg.norm(up_imu)
    # a focal search moves a pixel's altitude by up to ~10 degrees: cut the ground with margin here, exactly below
    margin = 2.0 + 100.0 * max(abs(fs - 1.0) for fs in f_scales)
    rej: dict = {}
    spots = []
    for lens in lenses:
        st: dict = {}
        spots += [(lens, s) for s in detect_spots(gray, lens, up_imu=up, min_alt=min_alt - margin, stats=st)]
        for k, v in st.items():
            rej[k] = rej.get(k, 0) + v
    out = {"solved": False, "spots": len(spots), "rejected_spots": rej}
    if not spots:
        out["why"] = "no star pattern identified (0 spots)"
        return out
    flux_all = np.array([s[2] for _, s in spots])
    lens_of = np.array([lenses.index(lens) for lens, _ in spots])
    spot_x = np.array([s[0] for _, s in spots])
    spot_y = np.array([s[1] for _, s in spots])

    dk1 = [0.0]                                               # radial-term correction found by the stars (below)

    def rays_for(fs, sel=None):
        """Refraction-corrected rays of the spots above min_alt, brightest first, and their spot indices."""
        rays = np.empty((len(spots), 3))
        for li, lens in enumerate(lenses):                    # one vectorised call per lens (was one per spot)
            m = lens_of == li
            if m.any():
                rays[m] = unproject(lens, spot_x[m], spot_y[m], lens.f * fs, lens.k1 + dk1[0])
        alt = np.degrees(np.arcsin(np.clip(rays @ up, -1, 1)))
        if sel is None:
            sel = np.nonzero(alt > min_alt)[0]
            sel = sel[np.argsort(-flux_all[sel])][:max_spots]
        rays, alt = rays[sel], alt[sel]
        # undo refraction: move each ray down towards the horizon by the refraction at its altitude
        drop = np.radians(refraction_deg(alt))
        tang = _unit(up - (rays @ up)[:, None] * rays)
        return _unit(rays * np.cos(drop)[:, None] - tang * np.sin(drop)[:, None]), sel

    best = None
    for fs in f_scales:
        rays, sel = rays_for(fs)
        if len(rays) < 3:
            continue
        r = identify(rays, cat, match_deg=match_deg, with_p=True)
        if r is not None and (best is None or (len(r[1]), -r[3]) > (len(best[1][1]), -best[1][3])):
            best = (fs, r, sel)
    if best is None:
        out["why"] = f"no star pattern identified ({out['spots']} spots)"
        return out
    fs, (R, idx, kidx, rms, p_chance), sel = best
    # p_chance is conditioned on all the rotations tried, over every focal length
    p_chance = min(1.0, p_chance * len(f_scales))
    n_used = len(sel)
    tree, chord = cat._tree, 2 * math.sin(math.radians(match_deg) / 2)

    def fit(f, spots_idx, cat_idx):
        rays, _ = rays_for(f, spots_idx)
        Rf = wahba(rays, cat.vec[cat_idx])
        res = np.degrees(np.arccos(np.clip(np.einsum("ij,ij->i", rays @ Rf.T, cat.vec[cat_idx]), -1, 1)))
        return float(np.sqrt(np.mean(res ** 2))), Rf

    def golden(lo, hi, spots_idx, cat_idx):
        for _ in range(30):                                           # golden-section on the rms
            a, b = lo + 0.382 * (hi - lo), lo + 0.618 * (hi - lo)
            if fit(a, spots_idx, cat_idx)[0] < fit(b, spots_idx, cat_idx)[0]:
                hi = b
            else:
                lo = a
        return (lo + hi) / 2

    # the matched stars measure the lens: the focal length that makes them fit best (a 1% error is tens of km);
    # then every spot is matched again at that focal length (the coarse search step loses the wide-angle stars)
    half = 0.06
    for _ in range(2):
        fs = golden(fs - half, fs + half, sel[idx], kidx)
        _, R = fit(fs, sel[idx], kidx)
        rays_n, sel_n = rays_for(fs)
        for _ in range(2):
            i2, k2, _ = match(rays_n, R, tree, chord)
            if len(i2) < 3:
                break
            idx, kidx, sel = i2, k2, sel_n
            R = wahba(rays_n[idx], cat.vec[kidx])
        half = 0.01
    rms, R = fit(fs, sel[idx], kidx)
    # with many stars across the field the radial term is measured too (focal and k1 together, then match again);
    # kept only if it lowers the residual
    if len(idx) >= K1_FIT_MIN_STARS:
        from scipy.optimize import minimize

        def cost(p):
            dk1[0] = p[1]
            return fit(p[0], sel[idx], kidx)[0]
        sol = minimize(cost, [fs, 0.0], method="Nelder-Mead",
                       options={"xatol": 1e-5, "fatol": 1e-5, "initial_simplex": [[fs, 0], [fs + 0.01, 0], [fs, 0.01]]})
        dk1[0] = float(sol.x[1])
        if abs(dk1[0]) <= 0.05 and sol.fun < rms:
            fs = float(sol.x[0])
            _, R = fit(fs, sel[idx], kidx)
            rays_n, sel_n = rays_for(fs)
            i2, k2, _ = match(rays_n, R, tree, chord)
            if len(i2) >= len(idx):
                idx, kidx, sel = i2, k2, sel_n
            rms, R = fit(fs, sel[idx], kidx)
        else:
            dk1[0] = 0.0
    m = len(idx)
    # each lens alone: the zenith it gives (an independent check, and the lenses' relative alignment)
    rays_m, _ = rays_for(fs, sel[idx])
    zen = [wahba(rays_m[lens_of[sel[idx]] == li], cat.vec[kidx[lens_of[sel[idx]] == li]]) @ up
           for li in range(len(lenses)) if (lens_of[sel[idx]] == li).sum() >= 4]
    disagree = 0.0
    if len(zen) == 2:
        disagree = math.degrees(math.acos(max(-1.0, min(1.0, float(zen[0] @ zen[1])))))
    sigma_fit = math.sqrt((rms / math.sqrt(max(m, 1))) ** 2 + (disagree / 2) ** 2)
    out.update(f_scale=round(fs, 5), k1_offset=round(dk1[0], 5), matched=int(m), used=int(n_used),
               rms_deg=round(rms, 3), p_chance=float(f"{p_chance:.3g}"), lens_disagree_deg=round(disagree, 3),
               sigma_fit_deg=round(sigma_fit, 4),
               matched_per_lens={lens.name: int((lens_of[sel[idx]] == li).sum()) for li, lens in enumerate(lenses)})
    why = accept(m, rms, p_chance, disagree)
    if why:
        out["why"] = "rejected: " + why
        if retry_spots and n_used > retry_spots:              # junk among the spots: try again on the brightest only
            r2 = locate(frame, up_imu, utc, cat, lenses, f_scales, min_alt, retry_spots, match_deg, retry_spots=0)
            if r2.get("solved"):
                r2["retried_with"] = retry_spots
                return r2
            out["why"] += f"; with the {retry_spots} brightest: {r2.get('why')}"
        return out
    ra, dec = vec_to_radec(R @ up)
    ra_a, dec_a = apparent_radec(ra, dec, utc)
    out.update(solved=True, lat=dec_a, lon=(ra_a - gast_deg(utc) + 540.0) % 360.0 - 180.0,
               brightest_matched_mag=round(float(cat.mag[kidx].min()), 2),
               faintest_matched_mag=round(float(cat.mag[kidx].max()), 2),
               R_icrs_imu=np.round(R, 8).tolist())                  # the camera's orientation among the stars (J2000)
    return out
