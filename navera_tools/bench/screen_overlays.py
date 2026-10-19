"""Weather, traffic and camera disturbances drawn over the map on the bench screen.

Used by screen_flight.py --overlay (comma-separated kinds, --overlay-amount 0-1 the strength)
and testable offline (navera_tools/bench/render_overlays.py writes PNGs, no window).

Kinds:
  clouds, cloudshadow, haze, fog, dust, smoke, rain, heavyrain (rain + water drops on the lens),
  snow, glare, flare (low sun + lens flare), dusk, night, birds, planes, drones, insects (close
  to the lens), wind (camera shake: the whole image jitters at 2-10 Hz, 0.5-3 deg equivalent
  with --overlay-amount 0-1, gusts every few seconds, with the motion blur of the shake).

The bench camera cannot be shaken, so "wind" moves the scene: draw() returns the image shift
(dx, dy) in screen pixels, and the caller moves the truth with it (the screen centre then shows
the map point (px - dx, py - dy)). An attitude-compensated camera would not see this shift: what
the bench measures is the blur and the frame-to-frame jitter, not the IMU compensation.
"""
import math
from typing import Iterable, Tuple

import cv2
import numpy as np

KINDS = ("clouds", "cloudshadow", "haze", "fog", "dust", "smoke", "rain", "heavyrain", "snow", "glare", "flare",
         "dusk", "night", "birds", "planes", "drones", "insects", "wind")


def _field(rng, h: int, w: int, scale: float) -> np.ndarray:
    """Smooth random field in [0, 1], (h, w)."""
    sh, sw = max(2, int(h / scale)), max(2, int(w / scale))
    f = cv2.resize(rng.random((sh, sw)).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    f = cv2.GaussianBlur(f, (0, 0), scale / 3.0)
    f -= f.min()
    return f / max(float(f.max()), 1e-6)


class Overlays:
    """Stateful (fields, particles, lens drops) so that the conditions move smoothly in time."""

    def __init__(self, w: int = 1920, h: int = 1080, seed: int = 7, px_per_deg: float = 26.0):
        # px_per_deg: screen pixels per degree of camera rotation (camera ~41 cm from a 527 mm
        # wide 1920 px screen: 1 deg = 7.2 mm = 26 px)
        self.w, self.h, self.ppd = w, h, px_per_deg
        self.rng = np.random.default_rng(seed)
        r = self.rng
        self.cloud = _field(r, h * 2, w * 2, 120.0)
        self.fog = _field(r, h, w, 300.0)
        self.smoke = _field(r, h * 2, w * 2, 90.0)
        self.rain = r.random((2500, 3))           # x, y, length factor
        self.snow = r.random((2500, 3))
        self.dust = r.random((1500, 2))
        self.drops = [(r.uniform(0, w), r.uniform(0, h), r.uniform(15, 70)) for _ in range(40)]
        self.insects = r.random((4, 4))
        self.fog = np.pad(self.fog, ((0, h), (0, w)), mode="reflect")
        self.noise = [r.normal(0, 1, (h, w, 3)).astype(np.float32) for _ in range(4)]   # cycled
        yy, xx = np.mgrid[-h:h, -w:w].astype(np.float32)
        self.spot = {s: np.exp(-(xx ** 2 + yy ** 2) / (2 * s ** 2)) for s in (140.0,)}
        self.q = 4                                       # masks are computed at 1/q resolution

    # ── helpers ──────────────────────────────────────────────────────────
    def _scroll(self, f: np.ndarray, t: float, vx: float, vy: float) -> np.ndarray:
        fh, fw = f.shape
        ox, oy = int(t * vx) % (fw - self.w), int(t * vy) % (fh - self.h)
        return f[oy:oy + self.h:self.q, ox:ox + self.w:self.q]

    def _up(self, m: np.ndarray) -> np.ndarray:
        """A 1/q mask to full size, with a channel axis."""
        return cv2.resize(m.astype(np.float32), (self.w, self.h), interpolation=cv2.INTER_LINEAR)[..., None]

    def _spot(self, x: float, y: float, sigma: float) -> np.ndarray:
        """A Gaussian spot centred at (x, y), full size (cut from a precomputed one when it can)."""
        if sigma in self.spot:
            ox, oy = int(round(self.w - x)), int(round(self.h - y))
            if 0 <= ox <= self.w and 0 <= oy <= self.h:
                return self.spot[sigma][oy:oy + self.h, ox:ox + self.w]
        q = self.q
        yy, xx = np.mgrid[0:self.h:q, 0:self.w:q].astype(np.float32)
        return self._up(np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma ** 2)))[..., 0]

    def _shake(self, t: float, amount: float) -> Tuple[float, float, float, float]:
        """(dx, dy, vx, vy) screen px and px/s: a sum of 2-10 Hz sines, gusts every ~8 s."""
        amp = (0.5 + 2.5 * amount) * self.ppd / 2.0
        gust = 1.0 + 1.5 * max(0.0, math.sin(2 * math.pi * t / 8.0)) ** 8
        dx = dy = vx = vy = 0.0
        for k, (f, ph) in enumerate(((2.1, 0.3), (3.7, 1.1), (6.3, 2.0), (9.6, 0.7))):
            a = amp * gust / (1 + 0.5 * k)
            dx += a * math.sin(2 * math.pi * f * t + ph)
            dy += a * math.cos(2 * math.pi * f * 0.87 * t + 1.7 * ph)
            vx += a * 2 * math.pi * f * math.cos(2 * math.pi * f * t + ph)
            vy -= a * 2 * math.pi * f * 0.87 * math.sin(2 * math.pi * f * 0.87 * t + 1.7 * ph)
        return dx, dy, vx, vy

    # ── the frame ────────────────────────────────────────────────────────
    def draw(self, img: np.ndarray, t: float, kinds: Iterable[str], amount: float = 0.3):
        """(image with the conditions, (dx, dy) scene shift in px: non-zero only with wind)."""
        kinds = set(kinds) - {"none", ""}
        unknown = kinds - set(KINDS)
        if unknown:
            raise ValueError(f"unknown overlay(s) {sorted(unknown)}; known: {', '.join(KINDS)}")
        a = float(np.clip(amount, 0.0, 1.0))
        h, w = img.shape[:2]
        shift = (0.0, 0.0)
        out = img.astype(np.float32)
        if "wind" in kinds:                                # first: the scene itself moves
            dx, dy, vx, vy = self._shake(t, a)
            # the shift, blurred over ~1/60 s of exposure along the shake's velocity (5 samples)
            L = min(math.hypot(vx, vy) / 60.0, 80.0)
            ux, uy = (vx, vy) if L >= 1.0 else (0.0, 0.0)
            nv = math.hypot(ux, uy) or 1.0
            acc = np.zeros((h, w, 3), np.uint16)
            steps = np.linspace(-L / 2, L / 2, 4) if L >= 1.0 else [0.0]
            for st in steps:
                M = np.float32([[1, 0, dx + st * ux / nv], [0, 1, dy + st * uy / nv]])
                acc += cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_REFLECT)
            out = acc.astype(np.float32) * (1.0 / len(steps))
            shift = (dx, dy)
        if "cloudshadow" in kinds or "clouds" in kinds:
            fld = self._scroll(self.cloud, t, 15.0, 6.0)
            thr = float(np.quantile(fld[::4, ::4], 1 - max(a, 0.05)))
            alpha = np.clip((fld - thr) / 0.08, 0, 1)
            shadow = np.roll(np.roll(alpha, 60 // self.q, 0), 90 // self.q, 1) * 0.45
            out *= 1 - self._up(shadow)
            if "clouds" in kinds:
                al = self._up(alpha * 0.95)
                out = out * (1 - al) + 245 * al
        if "haze" in kinds:
            out = out * (1 - 0.6 * a) + 210 * 0.6 * a
        if "fog" in kinds:                                  # patchy: denser in places, drifting
            d = self._up(np.clip(a * (0.5 + 0.8 * self._scroll(self.fog, t, 4.0, 1.0)), 0, 0.97))
            out = out * (1 - d) + 200 * d
        if "dust" in kinds:                                 # brown haze + fast particles
            out = out * (1 - 0.55 * a) + np.float32([70, 120, 165]) * 0.55 * a
            n = int(1500 * a)
            p = self.dust[:n]
            xs = ((p[:, 0] * w + t * 700) % w).astype(int)
            ys = ((p[:, 1] * h + 40 * np.sin(t * 3 + p[:, 0] * 20)) % h).astype(int)
            for x, y in zip(xs, ys):
                cv2.circle(out, (int(x), int(y)), 2, (60, 100, 140), -1)
        if "smoke" in kinds:
            fld = self._scroll(self.smoke, t, 25.0, -8.0)
            thr = float(np.quantile(fld[::2, ::2], 1 - (0.08 + 0.3 * a)))      # plumes cover 8-38 %
            plume = self._up(np.clip((fld - thr) / 0.12, 0, 1) * 0.85)
            out = out * (1 - plume) + 70 * plume
        if "rain" in kinds or "heavyrain" in kinds:
            heavy = "heavyrain" in kinds
            n = int((1500 + 1000 * heavy) * max(a, 0.1))
            ang = math.radians(15 + 25 * a * math.sin(t / 5.0))      # the wind turns the streaks
            layer = np.zeros((h, w), np.float32)
            p = self.rain[:n]
            for x0, y0, lf in p:
                L = (25 + 35 * lf) * (1.5 if heavy else 1.0)
                y = (y0 * (h + 200) + t * 1400) % (h + 200) - 100
                x = (x0 * w + y * math.tan(ang)) % w
                cv2.line(layer, (int(x), int(y)), (int(x - L * math.sin(ang)), int(y - L * math.cos(ang))),
                         1.0, 2)
            layer = cv2.blur(layer, (3, 3)) * (0.9 if heavy else 0.75)
            out = out * (1 - 0.15 * a * heavy) + 230 * layer[..., None]
            if heavy:                                     # water drops on the lens: fixed blobs
                q = self.q
                small = cv2.resize(out, (w // q, h // q), interpolation=cv2.INTER_AREA)
                blur = cv2.resize(cv2.GaussianBlur(small, (0, 0), 9 / q), (w, h))
                mask = np.zeros((h // q, w // q), np.float32)
                for x, y, r in self.drops[:int(10 + 30 * a)]:
                    cv2.circle(mask, (int(x / q), int(y / q)), int(r / q), 1.0, -1)
                mask = cv2.GaussianBlur(self._up(mask)[..., 0], (0, 0), 5)[..., None]
                tint = blur * 1.15 + 12
                out = out * (1 - mask) + tint * mask
        if "snow" in kinds:
            n = int(2500 * max(a, 0.1))
            for x0, y0, s in self.snow[:n]:
                y = (y0 * h + t * (60 + 80 * s)) % h
                x = (x0 * w + 30 * math.sin(t * (0.5 + s) + 10 * x0)) % w
                cv2.circle(out, (int(x), int(y)), int(2 + 4 * s), (245, 245, 250), -1)
            out = out * (1 - 0.15 * a) + 230 * 0.15 * a
        if "glare" in kinds:
            gx, gy = w * (0.3 + 0.4 * math.sin(t / 9)), h * (0.4 + 0.2 * math.cos(t / 7))
            out += 255 * self._spot(gx, gy, 140.0)[..., None]
        if "flare" in kinds:                                # low sun just outside the frame + ghosts
            sx, sy = w * (0.95 + 0.04 * math.sin(t / 11)), h * (0.1 + 0.05 * math.cos(t / 13))
            out += (255 * (0.5 + a)) * self._spot(sx, sy, 260.0 + 200 * a)[..., None] * \
                np.float32([0.8, 0.95, 1.0])
            ghost = np.zeros((h, w, 3), np.float32)
            for k, (f, rad, col) in enumerate(((0.3, 40, (80, 160, 255)), (0.6, 70, (255, 160, 80)),
                                               (1.1, 30, (120, 255, 120)), (1.5, 110, (200, 120, 255)))):
                cx, cy = sx + (w / 2 - sx) * f * 2, sy + (h / 2 - sy) * f * 2
                pts = cv2.ellipse2Poly((int(cx), int(cy)), (rad, rad), int(t * 3) % 60, 0, 360, 60)
                cv2.fillConvexPoly(ghost, pts, col)
            out += ghost * (0.25 + 0.35 * a)
        if "dusk" in kinds:
            out = out * (1 - 0.8 * a) + 6 * self.noise[int(t * 30) % 4]
        if "night" in kinds:                                # night-ish: very little light, noisy, warm
            out = out * (0.12 - 0.08 * a) * np.float32([0.8, 0.95, 1.2]) + 4 * self.noise[int(t * 30) % 4]
        if "birds" in kinds:
            for k in range(int(3 + 9 * a)):
                x = (t * (260 + 40 * k) + k * 333) % (w + 200) - 100
                y = (k * 173 + 40 * math.sin(t * 2 + k)) % h
                pts = np.array([[x - 14, y - 6], [x, y], [x + 14, y - 6]], np.int32)
                cv2.polylines(out, [pts], False, (25, 25, 25), 4)
        if "drones" in kinds:
            for k in range(int(2 + 4 * a)):
                size = (12, 18, 26, 40, 60, 80)[k % 6]
                x = w * (0.5 + 0.42 * math.sin(t * (0.31 + 0.07 * k) + k)) + 25 * math.sin(t * 3.1 + k)
                y = h * (0.5 + 0.40 * math.cos(t * (0.23 + 0.05 * k) + 2 * k)) + 20 * math.cos(t * 2.7 + k)
                col = (40, 40, 40) if k % 2 else (200, 200, 205)
                for ddx, ddy in ((1, 1), (1, -1)):
                    cv2.line(out, (int(x - ddx * size), int(y - ddy * size)), (int(x + ddx * size), int(y + ddy * size)),
                             col, max(2, size // 6))
                for ddx, ddy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
                    cv2.circle(out, (int(x + ddx * size), int(y + ddy * size)), max(3, size // 2), col, max(1, size // 10))
                cv2.circle(out, (int(x), int(y)), max(3, size // 3), col, -1)
        if "planes" in kinds:
            for k in range(1 + int(2 * a)):
                x = (t * (120 + 60 * k) + k * 700) % (w + 400) - 200
                y = h * (0.25 + 0.3 * k)
                cv2.line(out, (int(x - 60), int(y)), (int(x + 60), int(y)), (235, 235, 235), 12)
                cv2.line(out, (int(x), int(y - 70)), (int(x + 10), int(y + 70)), (235, 235, 235), 10)
        if "insects" in kinds:                              # out of focus, close: big soft dark blobs
            layer = np.zeros((h // self.q, w // self.q), np.float32)
            for k, (p, q, r, s) in enumerate(self.insects[:1 + int(3 * a)]):
                x = w * (0.5 + 0.45 * math.sin(t * (1.3 + p) + 7 * q)) + 60 * math.sin(t * 9 + k)
                y = h * (0.5 + 0.45 * math.cos(t * (1.1 + r) + 5 * s)) + 60 * math.cos(t * 11 + k)
                cv2.ellipse(layer, (int(x / self.q), int(y / self.q)), (int((40 + 80 * s) / self.q),
                            int((20 + 40 * s) / self.q)), (t * 200 + 90 * k) % 180, 0, 360, 1.0, -1)
            layer = self._up(cv2.GaussianBlur(layer, (0, 0), 14 / self.q)) * 0.85
            out = out * (1 - layer) + 20 * layer
        return np.clip(out, 0, 255).astype(np.uint8), shift
