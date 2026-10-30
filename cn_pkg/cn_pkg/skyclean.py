"""Sky cleaning before the star detector: it only REMOVES light, it never adds a point source.

The 360 detector (allsky._detect_blobs) already removes a smooth background (Gaussian, 12 px) and thresholds
against the local noise. What it cannot see is time: a lamp, a hot pixel, the window frame or a reflection in the
glass stays on the same pixel for hours, while a star crosses ~2.4 px per minute (556 px/rad lens, sidereal rate,
less near the pole). SkyCleaner keeps a few frames of the last minutes (one per RING_GAP_S) and

1. static scene: the per-pixel median of the ring, high-passed at the detector's scale, is the camera-fixed
   structure; where it stands above STATIC_K x its own noise it is subtracted from the frame. A star sits on a
   given pixel in at most one or two ring frames, so it never enters the median (stars within a few degrees of
   the celestial pole move too little and are removed too: a loss, never a gain).
   Only POSITIVE static structure is subtracted, so the cleaned frame is <= the input on every pixel: no new
   light is created anywhere.
2. moving texture (cloud lit by the city, drifting reflections): per CLOUD_BLOCK block, the frame-minus-median
   difference is smoothed over CLOUD_BOX px; noise averages out, cloud texture (several px wide) stays. Blocks
   where the smoothed difference's spread is above CLOUD_RATIO x the spread white noise would keep are cloud: the
   cleaned frame there is replaced by its own smooth background (no spot can be found there), and the fraction
   masked is reported. Fewer junk spots, so the chance probability of a real pattern is honestly lower; nothing
   is ever added.

Static removal needs RING_MIN_FRAMES frames spanning RING_MIN_SPAN_S with the camera still (the caller resets the
ring when the camera turns or moves). Before that, clean() returns the frame unchanged (info["static"] False).
Memory: RING_MAX_FRAMES uint8 frames (3840 x 1920: 7.4 MB each) + a few float32 frames while cleaning.
"""
import os
from collections import deque
from typing import Optional, Tuple

import numpy as np

HP_SIGMA = 12.0          # px: the detector's background scale (allsky._detect_blobs)
RING_MAX_FRAMES = 12
RING_GAP_S = 45.0        # s between ring frames: a star moves ~1.8 px (equator) in between
RING_MIN_FRAMES = 8
RING_MIN_SPAN_S = 360.0  # s: over the ring a star at declination <= 75 deg moves >= 3.7 px (> 2 FWHM)
RING_EXCLUDE_S = 60.0    # ring frames closer than this to the frame being cleaned are not used for it
STATIC_K = 3.0           # subtract the static structure where it is above this many times its own noise
STATIC_NOISE_FLOOR = 0.5  # DN: the median of 8-bit frames is quantised; its measured spread can be ~0
NOISE_BLOCK = 32
CLOUD_BLOCK = 64         # px
CLOUD_BOX = 7            # px: the smoothing that removes pixel noise but keeps cloud texture
CLOUD_RATIO = 2.0        # a block's texture ratio above this x the frame's noise-only ratio -> moving texture
CLOUD_REF_PCT = 25.0     # percentile of the block ratios taken as the noise-only ratio
CLOUD_MIN_SPREAD = 0.5   # DN: below this the smoothed difference is too faint to call anything cloud
STATIC_PCT = float(os.environ.get("NAVERA_SKYCLEAN_PCT", "50"))  # ring percentile taken as the static scene
STRIP = 240              # rows per strip for the ring median (bounds memory)


def _blur(img: np.ndarray, sigma: float) -> np.ndarray:
    import cv2
    return cv2.GaussianBlur(img, (0, 0), sigma)


def block_mad(img: np.ndarray, block: int, floor: float = 1e-3) -> np.ndarray:
    """1.4826 x median |img| per block x block tile (the robust spread of a zero-mean image), (hb, wb)."""
    h, w = img.shape
    hb, wb = max(1, h // block), max(1, w // block)
    t = np.abs(img[:hb * block, :wb * block]).reshape(hb, block, wb, block).transpose(0, 2, 1, 3)
    return np.maximum(1.4826 * np.median(t.reshape(hb, wb, -1), axis=2), floor).astype(np.float32)


def _up(blocks: np.ndarray, shape, block: int) -> np.ndarray:
    """Block values back to pixels (nearest: a block's decision covers its own pixels; the ragged edge repeats)."""
    out = np.repeat(np.repeat(blocks, block, axis=0), block, axis=1)
    h, w = shape
    out = np.pad(out, ((0, max(0, h - out.shape[0])), (0, max(0, w - out.shape[1]))), mode="edge")
    return out[:h, :w]


def ring_median(frames, pct: float = None) -> np.ndarray:
    """Per-pixel STATIC_PCT percentile (50: median) of equal-shape uint8 frames (float32), in strips so that memory
    stays ~2x one frame. Above 50, junk that flickers (present in a part of the frames only) is caught too; a star
    is on a pixel in at most 1-2 of the ring frames, so a percentile <= 100 x (1 - 2 / ring) never holds it."""
    pct = STATIC_PCT if pct is None else pct
    h, w = frames[0].shape
    out = np.empty((h, w), np.float32)
    for y in range(0, h, STRIP):
        out[y:y + STRIP] = np.percentile(np.stack([f[y:y + STRIP] for f in frames]), pct, axis=0)
    return out


def static_structure(med: np.ndarray) -> np.ndarray:
    """What to subtract: the positive part of the ring median's high-pass, where it is above STATIC_K x its noise."""
    hp = med - _blur(med, HP_SIGMA)
    noise = _up(block_mad(hp, NOISE_BLOCK, STATIC_NOISE_FLOOR), hp.shape, NOISE_BLOCK)
    return np.where(hp > STATIC_K * noise, hp, 0.0).astype(np.float32)


def cloud_blocks(diff: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """(boolean (hb, wb) moving-texture blocks, ratio per block) of a frame-minus-median difference (high-passed).

    ratio = spread of the CLOUD_BOX-smoothed difference / spread of what the smoothing removed. Codec noise is
    correlated (H.264 blocks), so the noise-only ratio is not 1/CLOUD_BOX: it is measured on the frame itself, as
    the CLOUD_REF_PCT percentile of the blocks (the dark border outside the lens circles and the static room are
    noise only). A block is moving texture when its ratio is CLOUD_RATIO x that and its smoothed spread is above
    CLOUD_MIN_SPREAD DN."""
    import cv2
    sm = cv2.blur(diff, (CLOUD_BOX, CLOUD_BOX))
    pix = block_mad(diff - sm, CLOUD_BLOCK, floor=0.05)
    spread = block_mad(sm, CLOUD_BLOCK)
    ratio = spread / pix
    ref = float(np.percentile(ratio, CLOUD_REF_PCT))
    return (ratio > CLOUD_RATIO * ref) & (spread > CLOUD_MIN_SPREAD), ratio


def gain_of(g_hp: np.ndarray, m_hp: np.ndarray, sel: np.ndarray) -> float:
    """Least-squares scale of the median's high-pass in the frame's (exposure / gain changes), clipped 0.5-2, over
    the significant static structure only (sel; elsewhere the median's own noise would dilute the fit)."""
    if sel.sum() < 50:
        return 1.0
    m, g = m_hp[sel], g_hp[sel]
    den = float((m * m).sum())
    return 1.0 if den <= 0 else float(np.clip((g * m).sum() / den, 0.5, 2.0))


class SkyCleaner:
    """Rolling static-scene model of a still camera; clean() returns a frame with less junk and never more light."""

    def __init__(self, max_frames: int = RING_MAX_FRAMES, gap_s: float = RING_GAP_S, cloud: bool = True,
                 static: bool = True):
        self.ring = deque(maxlen=max_frames)
        self.gap_s = gap_s
        self.cloud = cloud
        self.static = static
        self._model = None                                   # (ring key, median, structure, median high-pass)
        self.cloud_map = None                                # last clean(): moving-texture blocks (CLOUD_BLOCK px)

    def reset(self):
        """The camera moved or turned: the static scene is no longer the same pixels."""
        self.ring.clear()
        self._model = None

    def add(self, gray: np.ndarray, t: float) -> bool:
        """Offer a frame (uint8 grey) taken at t (s); kept if RING_GAP_S after the last one kept."""
        if gray.ndim != 2:
            raise ValueError("grey frame expected")
        if self.ring and (t - self.ring[-1][0] < self.gap_s or gray.shape != self.ring[-1][1].shape):
            if gray.shape != self.ring[-1][1].shape:
                self.reset()
            else:
                return False
        self.ring.append((float(t), np.ascontiguousarray(gray, dtype=np.uint8)))
        return True

    def _usable(self, t: float):
        use = [(tt, f) for tt, f in self.ring if abs(tt - t) >= RING_EXCLUDE_S]
        if len(use) < RING_MIN_FRAMES or use[-1][0] - use[0][0] < RING_MIN_SPAN_S:
            return None
        return use

    def clean(self, gray: np.ndarray, t: float) -> Tuple[np.ndarray, dict]:
        """(cleaned float32 frame, info). The cleaned frame is <= gray on every pixel, except in cloud blocks,
        which are replaced by the frame's own smooth background (no point source survives there)."""
        g = gray.astype(np.float32)
        info = {"static": False, "ring": len(self.ring), "cloud_frac": 0.0}
        use = self._usable(t) if (self.static or self.cloud) else None
        if use is None:
            return g, info
        key = tuple(tt for tt, _ in use)
        if self._model is None or self._model[0] != key:
            med = ring_median([f for _, f in use])
            self._model = (key, med, static_structure(med), med - _blur(med, HP_SIGMA))
        _, med, struct, m_hp = self._model
        g_hp = g - _blur(g, HP_SIGMA)
        gain = gain_of(g_hp, m_hp, struct > 0)
        out = g - gain * struct if self.static else g.copy()
        info.update(static=True, ring_used=len(use), ring_span_s=round(use[-1][0] - use[0][0], 1),
                    static_px=int((struct > 0).sum()), gain=round(gain, 3))
        if self.cloud:
            cb, _ = cloud_blocks(g_hp - gain * m_hp)
            self.cloud_map = cb
            if cb.any():
                m = _up(cb, g.shape, CLOUD_BLOCK)
                bg = _blur(out, HP_SIGMA)
                out = np.where(m, np.minimum(bg, out), out)
                info["cloud_frac"] = round(float(cb.mean()), 4)
        sat = gray >= 250                                      # keep saturation visible to the detector's filter
        if sat.any():
            out[sat] = g[sat]
        return out, info


# ---- clear-sky gate: is there enough usable sky to try a fix at all? ----
MIN_USABLE_SKY = 0.10     # fraction of the in-lens sky above min_alt that must be usable
USABLE_NOISE_DN = 4.0     # detector noise above this (glow, lit cloud texture): a faint star cannot be seen there
BRIGHT_DN = 120.0         # smooth level above this: glare, a lit room, a lamp's halo
GATE_BLOCK = 32


def sky_usable(gray: np.ndarray, lenses, up_imu: np.ndarray, min_alt: float = 12.0,
               cloud_map: Optional[np.ndarray] = None) -> dict:
    """How much of the sky above min_alt (in both lens circles) a star could be found in, per GATE_BLOCK block:
    not moving texture (cloud_map from SkyCleaner, CLOUD_BLOCK blocks), detector noise <= USABLE_NOISE_DN,
    smooth level < BRIGHT_DN. A dark, still obstruction (a ceiling at night) cannot be told from a starless dark
    sky in one frame: the gate catches cloud, glare and glow, not every roof."""
    from cn_pkg.allsky import unproject
    g = gray.astype(np.float32)
    hp = g - _blur(g, HP_SIGMA)
    noise = block_mad(hp, GATE_BLOCK)
    level = _blur(g, 2 * HP_SIGMA)
    hb, wb = noise.shape
    yc, xc = (np.mgrid[0:hb, 0:wb] + 0.5) * GATE_BLOCK
    up = np.asarray(up_imu, float) / np.linalg.norm(up_imu)
    sky = np.zeros((hb, wb), bool)
    for L in lenses:
        inside = np.hypot(xc - L.cx, yc - L.cy) < L.radius - 8
        if inside.any():
            rays = unproject(L, xc[inside], yc[inside])
            alt = np.degrees(np.arcsin(np.clip(rays @ up, -1, 1)))
            s = np.zeros_like(inside)
            s[inside] = alt >= min_alt
            sky |= s
    n = int(sky.sum())
    if n == 0:
        return {"sky_blocks": 0, "usable_frac": 0.0}
    yi = np.clip(yc.astype(int), 0, g.shape[0] - 1)
    xi = np.clip(xc.astype(int), 0, g.shape[1] - 1)
    bright = level[yi, xi] >= BRIGHT_DN
    noisy = noise > USABLE_NOISE_DN
    cloud = np.zeros_like(sky)
    if cloud_map is not None:
        cy = np.clip(yi // CLOUD_BLOCK, 0, cloud_map.shape[0] - 1)
        cx = np.clip(xi // CLOUD_BLOCK, 0, cloud_map.shape[1] - 1)
        cloud = cloud_map[cy, cx]
    usable = sky & ~bright & ~noisy & ~cloud
    f = lambda m: round(float((m & sky).sum()) / n, 3)  # noqa: E731
    return {"sky_blocks": n, "usable_frac": f(usable), "cloud_frac": f(cloud), "bright_frac": f(bright),
            "noisy_frac": f(noisy)}


def gate_reason(rep: dict, min_usable: float = MIN_USABLE_SKY) -> Optional[str]:
    """None when there is enough usable sky; otherwise the 'why' for the frame record (no solve is tried)."""
    if rep.get("usable_frac", 0.0) >= min_usable:
        return None
    return (f"too cloudy / blocked: {100 * rep.get('usable_frac', 0.0):.0f} % of the sky usable "
            f"(< {100 * min_usable:.0f} %; moving cloud {100 * rep.get('cloud_frac', 0.0):.0f} %, "
            f"glare {100 * rep.get('bright_frac', 0.0):.0f} %, glow/noise {100 * rep.get('noisy_frac', 0.0):.0f} %)")
