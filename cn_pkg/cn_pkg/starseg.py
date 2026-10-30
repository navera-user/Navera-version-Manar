"""Star segmentation: a small U-Net that labels each pixel 'star' or 'not star'. A filter / detector only.

It never outputs an image, only a per-pixel probability; spots are its local maxima, placed at the centroid of the
frame's own residual light (so a position always comes from real pixels). The solver (allsky.locate) keeps every
gate (accept(), p_chance): the network can only change WHICH spots are handed to it.

Trained offline (navera_tools/field/starseg_train.py) on catalogue-like synthetic stars (Gaussian / Moffat PSF,
sigma 0.6-1.6 px, peak 0.3-4 DN, rounded to 8 bit) added to real night frames that hold no starlight (sessions
2026-10-29 1853/1902/1928: city glow, cloud, the room's reflections, H.264 noise): everything real in them is junk.
Validated on the held-out session 2300 (navera_tools/field/starseg_eval.py).

Input channels: the detector's residual (frame - Gaussian(12 px)) / 4 and its local SNR / 6 (allsky noise map).
Weights: not in git (rule: no .pth); NAVERA_STARSEG_WEIGHTS or ~/navera_models/starseg_v1.pth.
"""
import os
from typing import List, Optional, Tuple

import numpy as np

WEIGHTS = os.environ.get("NAVERA_STARSEG_WEIGHTS",
                         os.path.expanduser("~/navera_models/starseg_v1.pth"))
PROB_MIN = 0.5           # a spot: a local maximum of the probability above this
TILE = 1024              # px: inference tile (overlap TILE_PAD) bounds GPU memory
TILE_PAD = 16


def residual_noise(gray: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """(residual, local noise) float32 maps, exactly as allsky._detect_blobs computes them."""
    import cv2
    from cn_pkg import allsky
    sub = gray.astype(np.float32)
    res = sub - cv2.GaussianBlur(sub, (0, 0), 12)
    h, w = res.shape
    B = allsky.NOISE_BLOCK
    hb, wb = max(1, h // B), max(1, w // B)
    blocks = np.abs(res[:hb * B, :wb * B]).reshape(hb, B, wb, B).transpose(0, 2, 1, 3).reshape(hb, wb, B * B)
    noise_b = np.maximum(1.4826 * np.median(blocks, axis=2), allsky.NOISE_FLOOR).astype(np.float32)
    return res, cv2.resize(noise_b, (w, h), interpolation=cv2.INTER_LINEAR)


def features(gray: np.ndarray) -> np.ndarray:
    """(2, H, W) float32: residual / 4 and residual / local noise / 6, clipped (the network's input)."""
    res, noise = residual_noise(gray)
    return np.stack([np.clip(res / 4.0, -8, 16), np.clip(res / noise / 6.0, -4, 8)]).astype(np.float32)


def build(width: int = 16):
    """The U-Net: 2 down / 2 up levels, width-2w-4w channels (~45k parameters at width 16)."""
    import torch
    from torch import nn

    def block(i, o):
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                             nn.Conv2d(o, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True))

    class UNet(nn.Module):
        def __init__(self):
            super().__init__()
            w = width
            self.e1, self.e2, self.e3 = block(2, w), block(w, 2 * w), block(2 * w, 4 * w)
            self.u2, self.d2 = nn.ConvTranspose2d(4 * w, 2 * w, 2, stride=2), block(4 * w, 2 * w)
            self.u1, self.d1 = nn.ConvTranspose2d(2 * w, w, 2, stride=2), block(2 * w, w)
            self.out = nn.Conv2d(w, 1, 1)
            self.pool = nn.MaxPool2d(2)

        def forward(self, x):
            a = self.e1(x)
            b = self.e2(self.pool(a))
            c = self.e3(self.pool(b))
            b = self.d2(torch.cat([self.u2(c), b], 1))
            a = self.d1(torch.cat([self.u1(b), a], 1))
            return self.out(a)                                  # logits

    return UNet()


class StarSeg:
    """Loaded model; prob(gray) -> (H, W) star probability; spots(...) -> detect_spots-like list."""

    def __init__(self, weights: str = WEIGHTS, device: Optional[str] = None):
        import torch
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        state = torch.load(weights, map_location="cpu")
        self.net = build(state.get("width", 16))
        self.net.load_state_dict(state["model"])
        self.net.eval().to(self.device)
        self.half = self.device == "cuda"
        if self.half:
            self.net.half()

    def prob(self, gray: np.ndarray, box: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
        """Star probability over gray (or over box = x0, y0, x1, y1 only; zero elsewhere), tiled."""
        torch = self.torch
        H, W = gray.shape
        x0, y0, x1, y1 = box or (0, 0, W, H)
        feat = features(gray[y0:y1, x0:x1])
        h, w = feat.shape[1:]
        out = np.zeros((H, W), np.float32)
        with torch.no_grad():
            for ty in range(0, h, TILE):
                for tx in range(0, w, TILE):
                    a, b = max(0, ty - TILE_PAD), max(0, tx - TILE_PAD)
                    c, d = min(h, ty + TILE + TILE_PAD), min(w, tx + TILE + TILE_PAD)
                    ph, pw = (-(c - a)) % 4, (-(d - b)) % 4               # two poolings: multiple of 4
                    x = np.pad(feat[:, a:c, b:d], ((0, 0), (0, ph), (0, pw)), mode="reflect")
                    t = torch.from_numpy(x)[None].to(self.device)
                    t = t.half() if self.half else t
                    p = torch.sigmoid(self.net(t).float())[0, 0].cpu().numpy()[:c - a, :d - b]
                    yy, xx = ty - a, tx - b
                    out[y0 + ty:y0 + min(h, ty + TILE), x0 + tx:x0 + min(w, tx + TILE)] = \
                        p[yy:yy + min(TILE, h - ty), xx:xx + min(TILE, w - tx)]
        return out

    def spots(self, gray: np.ndarray, lens, up_imu=None, min_alt=None, max_spots: int = 120,
              prob_min: float = PROB_MIN, stats: Optional[dict] = None,
              prob: Optional[np.ndarray] = None) -> List[tuple]:
        """Like allsky.detect_spots for one lens circle: (x, y, flux) brightest first. Peaks of the probability
        (7x7 local maxima above prob_min); centroid and flux from the frame's residual light in a 5x5 box."""
        import cv2
        from cn_pkg.allsky import unproject
        H, W = gray.shape
        x0, x1 = int(max(0, lens.cx - lens.radius)), int(min(W, lens.cx + lens.radius))
        y0, y1 = int(max(0, lens.cy - lens.radius)), int(min(H, lens.cy + lens.radius))
        p = (self.prob(gray, (x0, y0, x1, y1)) if prob is None else prob)[y0:y1, x0:x1]
        sub = gray[y0:y1, x0:x1].astype(np.float32)
        res = sub - cv2.GaussianBlur(sub, (0, 0), 12)
        pk = (p == cv2.dilate(p, np.ones((7, 7), np.uint8))) & (p > prob_min)
        yy, xx = np.nonzero(pk)
        ok = np.hypot(xx + x0 - lens.cx, yy + y0 - lens.cy) < lens.radius - 8
        yy, xx = yy[ok], xx[ok]
        n_low = 0
        if up_imu is not None and min_alt is not None and len(xx):
            up = np.asarray(up_imu, float) / np.linalg.norm(up_imu)
            alt = np.degrees(np.arcsin(np.clip(unproject(lens, xx + x0, yy + y0) @ up, -1, 1)))
            n_low = int((alt < min_alt).sum())
            yy, xx = yy[alt >= min_alt], xx[alt >= min_alt]
        if stats is not None:
            stats.update({"below_horizon": n_low})
        pad = np.pad(res, 2)
        gy, gx = np.mgrid[-2:3, -2:3]
        out = []
        for x, y in zip(xx, yy):
            win = pad[y:y + 5, x:x + 5].clip(0)
            s = float(win.sum())
            if s <= 0:
                continue
            out.append((float(x + x0 + (win * gx).sum() / s), float(y + y0 + (win * gy).sum() / s), s))
        out.sort(key=lambda t: -t[2])
        return out[:max_spots]


def lens_box(lens, shape) -> Tuple[int, int, int, int]:
    H, W = shape
    return (int(max(0, lens.cx - lens.radius)), int(max(0, lens.cy - lens.radius)),
            int(min(W, lens.cx + lens.radius)), int(min(H, lens.cy + lens.radius)))


def finder(model: "StarSeg", mode: str = "detect", prob_min: float = PROB_MIN, k_sigma: Optional[float] = None):
    """A spot_finder for allsky.locate. mode 'detect': the network's peaks are the spots. mode 'filter': the
    production detector's spots (k_sigma), dropped where the network's probability (max within 2 px) is below
    prob_min - it can only remove spots. The probability map is computed once per frame and lens."""
    cache: dict = {}

    def prob_of(gray, lens):
        if cache.get("gray") is not gray:
            cache.clear()
            cache["gray"] = gray
        if lens.name not in cache:
            cache[lens.name] = model.prob(gray, lens_box(lens, gray.shape))
        return cache[lens.name]

    def find(gray, lens, up_imu=None, min_alt=None, stats=None, max_spots: int = 120, k_sigma_=None):
        from cn_pkg import allsky
        if mode == "detect":
            return model.spots(gray, lens, up_imu=up_imu, min_alt=min_alt, max_spots=max_spots,
                               prob_min=prob_min, stats=stats, prob=prob_of(gray, lens))
        sp = allsky.detect_spots(gray, lens, k_sigma=k_sigma, max_spots=max(300, max_spots), up_imu=up_imu,
                                 min_alt=min_alt, stats=stats)
        p = prob_of(gray, lens)
        H, W = p.shape
        keep = []
        for x, y, f in sp:
            xi, yi = int(round(x)), int(round(y))
            win = p[max(0, yi - 2):min(H, yi + 3), max(0, xi - 2):min(W, xi + 3)]
            if win.size and float(win.max()) >= prob_min:
                keep.append((x, y, f))
        if stats is not None:
            stats["network_dropped"] = len(sp) - len(keep)
        return keep[:max_spots]
    return find
