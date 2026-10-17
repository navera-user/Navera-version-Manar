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
"""
import math
import os
from typing import List, Optional, Sequence

import numpy as np

from cn_pkg.nodes.celestial_math import apparent_radec, gast_deg
from navera_tools.field.sky360 import Lens, default_lenses

KM_PER_DEG = 111.2


def _unit(v):
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def radec_to_vec(ra_deg, dec_deg):
    ra, dec = np.radians(ra_deg), np.radians(dec_deg)
    return np.stack([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)], axis=-1)


def vec_to_radec(v):
    v = v / np.linalg.norm(v)
    return math.degrees(math.atan2(v[1], v[0])) % 360.0, math.degrees(math.asin(max(-1.0, min(1.0, v[2]))))


class Catalogue:
    """Bright stars (Yale BSC5, ICRS) and their pair separations, sorted for range lookups."""

    def __init__(self, work_dir: str = os.path.expanduser("~/.navera_sim"), limit_mag: float = 4.0,
                 max_sep_deg: float = 60.0):
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sim"))
        from sky_view import load_bsc5
        ra, dec, mag = load_bsc5(work_dir)
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


def detect_spots(gray: np.ndarray, lens: Lens, k_sigma: float = 6.0, max_spots: int = 120):
    """Bright compact spots inside the lens circle: (x, y, flux) sorted brightest first."""
    import cv2
    x0, x1 = int(max(0, lens.cx - lens.radius)), int(min(gray.shape[1], lens.cx + lens.radius))
    sub = gray[:, x0:x1].astype(np.float32)
    bg = cv2.GaussianBlur(sub, (0, 0), 12)
    res = sub - bg
    noise = 1.4826 * float(np.median(np.abs(res - np.median(res)))) + 1e-3
    peak = (res == cv2.dilate(res, np.ones((7, 7), np.uint8))) & (res > k_sigma * noise)
    yy, xx = np.nonzero(peak)
    xx = xx + x0
    inside = np.hypot(xx - lens.cx, yy - lens.cy) < lens.radius - 8
    xx, yy = xx[inside], yy[inside]
    out = []
    for x, y in zip(xx, yy):
        lx = x - x0
        w = res[max(0, y - 2):y + 3, max(0, lx - 2):lx + 3].clip(0)
        if w.sum() <= 0:
            continue
        gy, gx = np.mgrid[max(0, y - 2):y + 3, max(0, lx - 2):lx + 3]
        out.append((float((w * (gx + x0)).sum() / w.sum()), float((w * gy).sum() / w.sum()), float(w.sum())))
    out.sort(key=lambda s: -s[2])
    return out[:max_spots]


def unproject(lens: Lens, x, y, f: Optional[float] = None):
    """Pixels → unit rays in the IMU frame (inverse of Lens.project, Newton on the k1 term)."""
    f = f or lens.f
    dx, dy = np.asarray(x) - lens.cx, np.asarray(y) - lens.cy
    r = np.hypot(dx, dy)
    theta = r / f
    for _ in range(5):
        theta = theta - (theta + lens.k1 * theta ** 3 - r / f) / (1 + 3 * lens.k1 * theta ** 2)
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


def identify(rays: np.ndarray, cat: Catalogue, n_seed: int = 10, tol_deg: float = 0.5,
             match_deg: float = 0.5, min_matches: int = 6):
    """(rotation IMU→ICRS, matched ray indices, catalogue indices, rms deg) or None."""
    from scipy.spatial import cKDTree
    tree = cKDTree(cat.vec)
    seed = rays[:n_seed]
    best = (0, None)
    cos_match = 2 * math.sin(math.radians(match_deg) / 2)            # chord length
    for i in range(len(seed)):
        for j in range(i + 1, len(seed)):
            sep = math.degrees(math.acos(max(-1.0, min(1.0, float(seed[i] @ seed[j])))))
            if sep < 3.0 or sep > 60.0:
                continue
            ci, cj = cat.pairs_near(sep, tol_deg)
            for a, b in zip(ci, cj):
                for p, q in ((a, b), (b, a)):
                    R = triad(seed[i], seed[j], cat.vec[p], cat.vec[q])
                    d, _ = tree.query(rays @ R.T, distance_upper_bound=cos_match)
                    n = int(np.isfinite(d).sum())
                    if n > best[0]:
                        best = (n, R)
    if best[0] < min_matches:
        return None
    R = best[1]
    for _ in range(3):                                                # refine on every match
        d, k = tree.query(rays @ R.T, distance_upper_bound=cos_match)
        ok = np.isfinite(d)
        if ok.sum() < 3:
            return None
        R = wahba(rays[ok], cat.vec[k[ok]])
    d, k = tree.query(rays @ R.T, distance_upper_bound=cos_match)
    ok = np.isfinite(d)
    rms = math.degrees(float(np.sqrt(np.mean((2 * np.arcsin(d[ok] / 2)) ** 2))))
    return R, np.nonzero(ok)[0], k[ok], rms


def locate(frame: np.ndarray, up_imu: np.ndarray, utc: str, cat: Catalogue,
           lenses: Optional[List[Lens]] = None, f_scales: Sequence[float] = (1.0,),
           min_alt: float = 12.0, max_spots: int = 60) -> dict:
    """Latitude, longitude from the whole sky above the camera. f_scales: focal lengths to try
    (× each lens's f); the best one is reported so the caller can keep it."""
    import cv2
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    lenses = lenses or default_lenses()
    up = up_imu / np.linalg.norm(up_imu)
    spots = [(lens, s) for lens in lenses for s in detect_spots(gray, lens)]
    out = {"solved": False, "spots": len(spots)}
    best = None
    for fs in f_scales:
        rays, flux = [], []
        for lens, (x, y, fl) in spots:
            rays.append(unproject(lens, x, y, lens.f * fs))
            flux.append(fl)
        if not rays:
            break
        rays, flux = np.array(rays), np.array(flux)
        alt = np.degrees(np.arcsin(np.clip(rays @ up, -1, 1)))
        keep = alt > min_alt
        rays, flux, alt = rays[keep], flux[keep], alt[keep]
        order = np.argsort(-flux)[:max_spots]
        rays, alt = rays[order], alt[order]
        # undo refraction: move each ray down towards the horizon by the refraction at its altitude
        drop = np.radians(refraction_deg(alt))
        tang = _unit(up - (rays @ up)[:, None] * rays)
        rays = _unit(rays * np.cos(drop)[:, None] - tang * np.sin(drop)[:, None])
        r = identify(rays, cat)
        if r is not None and (best is None or (len(r[1]), -r[3]) > (len(best[1][1]), -best[1][3])):
            best = (fs, r, len(rays))
    if best is None:
        out["why"] = f"no star pattern identified ({out['spots']} spots)"
        return out
    fs, (R, idx, kidx, rms), n_used = best
    ra, dec = vec_to_radec(R @ up)
    ra_a, dec_a = apparent_radec(ra, dec, utc)
    out.update(solved=True, lat=dec_a, lon=(ra_a - gast_deg(utc) + 540.0) % 360.0 - 180.0, f_scale=fs,
               matched=int(len(idx)), used=int(n_used), rms_deg=round(rms, 3),
               brightest_matched_mag=round(float(cat.mag[kidx].min()), 2), faintest_matched_mag=round(float(cat.mag[kidx].max()), 2))
    return out
