"""Star detection for the celestial camera: stars only, nothing else.

A night frame holds more than stars: hot pixels, aircraft and satellite trails, the Moon
and planets as blobs, street lights, clouds and haze, and the car itself (roof edge,
windshield reflections, dirt). Everything that is not a star must be named and left out,
and the frame must be rated before anyone drives on it.

Two stages:

* ``detect`` judges ONE frame by what a star looks like through a lens: a small, round,
  compact spot above the local sky level. It names every other spot with its reason.
* ``StarTracker`` judges a SEQUENCE: a star keeps its place in the star pattern from
  frame to frame (the pattern turns as one rigid piece), a hot pixel or a speck of dirt
  stays on the same pixel while the pattern turns, an aircraft or satellite does not
  follow the pattern. Only stars seen again under the pattern's own motion are confirmed.

The final proof is the plate solver: a confirmed star is only counted as a star for
navigation when the solver matches it to the catalogue.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# Reasons a spot is not a star. The operator and the report show these words.
HOT_PIXEL = "hot pixel"          # one pixel, sharper than any lens makes a star
STREAK = "trail (aircraft, satellite)"
BLOB = "bright blob (Moon, planet, lamp)"
GLARE = "light or glare"         # saturated and big: street lamp, headlight, reflection
NOT_SKY = "not sky (car, horizon, next to a bright object)"
FIXED = "fixed on the sensor (dirt, hot pixel)"
MOVER = "moves against the stars"
FAINT = "too faint"

# What the sky as a whole looks like.
SKY_CLEAR, SKY_HAZY, SKY_CLOUDY, SKY_BRIGHT, SKY_BLOCKED = "clear", "hazy", "cloudy", "too bright", "blocked"


@dataclass
class Star:
    x: float
    y: float
    flux: float
    peak: float
    fwhm: float
    snr: float


@dataclass
class Detection:
    stars: List[Star]
    rejected: Dict[str, List[Tuple[float, float]]]
    sky: str                        # one of SKY_*
    background: float               # median sky level (0-255)
    noise: float                    # sky noise (grey levels)
    sky_fraction: float             # share of the picture that is usable sky
    cloud_range: float              # spread of the sky level across the picture

    def counts(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self.rejected.items() if v}


def _background(gray: np.ndarray) -> np.ndarray:
    """Slowly varying sky level; stars are far too small to move this median."""
    h, w = gray.shape
    small = cv2.resize(gray, (max(w // 8, 8), max(h // 8, 8)), interpolation=cv2.INTER_AREA)
    small = cv2.medianBlur(np.clip(small, 0, 255).astype(np.uint8), 21)
    return cv2.resize(small.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)


def _mad_sigma(a: np.ndarray) -> float:
    med = np.median(a)
    return float(1.4826 * np.median(np.abs(a - med))) or 1e-3


def detect(gray: np.ndarray, snr_min: float = 6.0, max_star_px: int = 60,
           bg_limit: float = 120.0, stride_limit: float = 2.6,
           hot_sharpness: float = 0.7) -> Detection:
    """Find the stars in one frame and name everything else.

    gray: 2-D uint8 or float picture (the straightened camera view).
    snr_min: a spot must stand this many noise sigmas above the sky.
    max_star_px: largest area a star may cover (the lens' own blur sets the real size).
    bg_limit: sky level (0-255) above which a region is treated as not dark sky.
    stride_limit: major/minor axis ratio above which a spot is a trail.
    hot_sharpness: share of a spot's light in one pixel above which it is a hot pixel.
    """
    g = gray.astype(np.float32)
    if g.ndim == 3:
        g = g.mean(axis=2)
    bg = _background(g)
    resid = g - bg

    # Regions that cannot show stars: lit areas, the car, the horizon.
    lit = (bg > bg_limit).astype(np.uint8)
    lit = cv2.dilate(lit, np.ones((15, 15), np.uint8))
    sky_mask = lit == 0
    sky_fraction = float(sky_mask.mean())
    rejected: Dict[str, List[Tuple[float, float]]] = {}

    def reject(reason, x, y):
        rejected.setdefault(reason, []).append((round(float(x), 1), round(float(y), 1)))

    if sky_fraction < 0.2:
        verdict = SKY_BLOCKED if float(np.median(bg)) < bg_limit else SKY_BRIGHT
        return Detection([], rejected, verdict, float(np.median(bg)), _mad_sigma(resid), sky_fraction, 0.0)

    noise = _mad_sigma(resid[sky_mask])
    sky_bg = bg[sky_mask]
    cloud_range = float(np.percentile(sky_bg, 95) - np.percentile(sky_bg, 5))
    med_bg = float(np.median(sky_bg))

    smooth = cv2.GaussianBlur(resid, (0, 0), 1.0)
    sn = _mad_sigma(smooth[sky_mask])
    binary = (smooth > snr_min * sn).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)

    stars: List[Star] = []
    big = np.zeros(g.shape, np.uint8)         # bright objects: their halo hides faint stars
    for i in range(1, n):
        x0, y0, bw, bh, area = stats[i]
        pad = 3
        xa, ya = max(x0 - pad, 0), max(y0 - pad, 0)
        xb, yb = min(x0 + bw + pad, g.shape[1]), min(y0 + bh + pad, g.shape[0])
        member = labels[ya:yb, xa:xb] == i
        patch = np.clip(resid[ya:yb, xa:xb], 0, None) * member
        flux = float(patch.sum())
        if flux <= 0:
            continue
        ys, xs = np.mgrid[ya:yb, xa:xb]
        cx, cy = float((patch * xs).sum() / flux), float((patch * ys).sum() / flux)
        if not sky_mask[min(int(round(cy)), g.shape[0] - 1), min(int(round(cx)), g.shape[1] - 1)]:
            reject(NOT_SKY, cx, cy)
            continue
        peak = float(g[ya:yb, xa:xb][member].max())
        sharp = float(patch.max()) / flux          # share of the light in the brightest pixel
        cxx = float((patch * (xs - cx) ** 2).sum() / flux)
        cyy = float((patch * (ys - cy) ** 2).sum() / flux)
        cxy = float((patch * (xs - cx) * (ys - cy)).sum() / flux)
        tr, det = cxx + cyy, cxx * cyy - cxy * cxy
        disc = max(tr * tr / 4 - det, 0.0) ** 0.5
        major, minor = max(tr / 2 + disc, 1e-3) ** 0.5, max(tr / 2 - disc, 1e-3) ** 0.5
        fwhm = 2.355 * (major * minor) ** 0.5
        snr = flux / (noise * max(area, 1) ** 0.5)
        radius = max(bw, bh) / 2.0

        if peak >= 250 and area > 60:
            reject(GLARE, cx, cy)
            cv2.circle(big, (int(cx), int(cy)), int(max(15, 1.5 * radius)), 1, -1)
        elif major / minor > stride_limit and major > 3.0:
            reject(STREAK, cx, cy)
        elif area > max_star_px or fwhm > 9.0:
            reject(BLOB, cx, cy)
            cv2.circle(big, (int(cx), int(cy)), int(max(15, 1.5 * radius)), 1, -1)
        elif sharp > hot_sharpness:
            reject(HOT_PIXEL, cx, cy)
        else:
            stars.append(Star(cx, cy, flux, peak, fwhm, snr))

    kept = []
    for s_ in stars:
        if big[min(int(s_.y), g.shape[0] - 1), min(int(s_.x), g.shape[1] - 1)]:
            reject(NOT_SKY, s_.x, s_.y)
        else:
            kept.append(s_)
    stars = kept

    if med_bg > 90.0:
        verdict = SKY_BRIGHT
    elif cloud_range > 28.0 or (sky_fraction < 0.5):
        verdict = SKY_CLOUDY
    elif cloud_range > 14.0:
        verdict = SKY_HAZY
    else:
        verdict = SKY_CLEAR
    stars.sort(key=lambda s: -s.flux)
    return Detection(stars, rejected, verdict, med_bg, noise, sky_fraction, cloud_range)


@dataclass
class _Track:
    x: float
    y: float
    seen: int = 1
    last: int = 0


@dataclass
class TrackerResult:
    confirmed: List[Star]
    rejected: Dict[str, List[Tuple[float, float]]]
    pattern_shift_px: float         # how far the star pattern moved since the previous frame


@dataclass
class StarTracker:
    """Keeps the spots of the last frames and decides which of them are stars."""
    tol_px: float = 2.0
    ban_after: int = 3
    ban_radius_px: float = 1.5
    _prev: List[Star] = field(default_factory=list)
    _fixed: List[Tuple[float, float, int]] = field(default_factory=list)
    frame: int = 0

    def banned(self) -> List[Tuple[float, float]]:
        return [(x, y) for x, y, n in self._fixed if n >= self.ban_after]

    def update(self, det: Detection) -> TrackerResult:
        self.frame += 1
        cur = det.stars
        rej = {k: list(v) for k, v in det.rejected.items()}
        # Spots on a banned pixel are not stars, whatever they look like.
        keep = []
        for s in cur:
            if any((s.x - bx) ** 2 + (s.y - by) ** 2 < self.ban_radius_px ** 2 for bx, by in self.banned()):
                rej.setdefault(FIXED, []).append((round(s.x, 1), round(s.y, 1)))
            else:
                keep.append(s)
        cur = keep
        if not self._prev:
            self._prev = cur
            # A single frame proves nothing: no star is confirmed yet.
            return TrackerResult([], rej, 0.0)

        shift = _pattern_shift(self._prev, cur, self.tol_px * 4)
        dx, dy = shift if shift is not None else (0.0, 0.0)
        moved = (dx * dx + dy * dy) ** 0.5
        pattern_moved = shift is not None and moved > 3 * self.tol_px
        confirmed = []
        for s_ in cur:
            hit = _nearest(self._prev, s_.x - dx, s_.y - dy)
            if hit is not None and hit[0] <= self.tol_px:
                still = _nearest(self._prev, s_.x, s_.y)
                if pattern_moved and still is not None and still[0] < 1.0:
                    # on the same pixel as before although the pattern moved
                    self._note_fixed(s_.x, s_.y)
                    rej.setdefault(FIXED, []).append((round(s_.x, 1), round(s_.y, 1)))
                else:
                    confirmed.append(s_)
                continue
            still = _nearest(self._prev, s_.x, s_.y)
            if pattern_moved and still is not None and still[0] < 1.0:
                self._note_fixed(s_.x, s_.y)
                rej.setdefault(FIXED, []).append((round(s_.x, 1), round(s_.y, 1)))
            else:
                rej.setdefault(MOVER, []).append((round(s_.x, 1), round(s_.y, 1)))
        self._prev = cur
        return TrackerResult(confirmed, rej, moved)

    def _note_fixed(self, x, y):
        for i, (fx, fy, n) in enumerate(self._fixed):
            if (fx - x) ** 2 + (fy - y) ** 2 < self.ban_radius_px ** 2:
                self._fixed[i] = (fx, fy, n + 1)
                return
        self._fixed.append((x, y, 1))


def _nearest(stars: List[Star], x: float, y: float) -> Optional[Tuple[float, Star]]:
    best = None
    for s in stars:
        d = ((s.x - x) ** 2 + (s.y - y) ** 2) ** 0.5
        if best is None or d < best[0]:
            best = (d, s)
    return best


def _pattern_shift(prev: List[Star], cur: List[Star], tol: float, max_shift: float = 150.0):
    """Shift of the star pattern between two frames: the offset most pairs agree on."""
    if len(prev) < 3 or len(cur) < 3:
        return (0.0, 0.0) if prev and cur else None
    a = np.array([[s.x, s.y] for s in prev[:40]])
    b = np.array([[s.x, s.y] for s in cur[:40]])
    d = (b[:, None, :] - a[None, :, :]).reshape(-1, 2)
    d = d[(np.abs(d) <= max_shift).all(axis=1)]
    if len(d) == 0:
        return None
    best, best_n = None, 0
    for cand in np.vstack([d, [[0.0, 0.0]]]):
        n = int((np.hypot(*(d - cand).T) <= tol).sum())
        if n > best_n or (n == best_n and best is not None and np.hypot(*cand) < np.hypot(*best)):
            best, best_n = cand, n
    if best_n < 3:
        return None
    members = d[np.hypot(*(d - best).T) <= tol]
    return tuple(members.mean(axis=0))
