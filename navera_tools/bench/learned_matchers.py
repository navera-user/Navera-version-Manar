#!/usr/bin/env python3
"""Which matcher finds real aerial frames on the satellite map best? The 33 real frames
(another camera, another date: colours, shadows and seasons differ from the map) are matched
against the MBTiles map around the previous frame's position (600 m search), with:

  sift      — NAVERA's current local matcher (day_pkg.local_matcher, its tile features)
  disk_lg   — DISK features + LightGlue (learned, GPU, kornia)
  sp_lg     — SuperPoint + LightGlue... not in kornia 0.8: DISK and ALIKED are
  aliked_lg — ALIKED + LightGlue (learned, GPU)

Same geometry for all: similarity fit by RANSAC, accepted when the inliers reach the
minimum and the scale is within 15 % of the one expected. Prints, per method: located,
wrong (> 50 m), median / 90 % / max error, time per frame.

    python3 navera_tools/bench/learned_matchers.py [--methods sift,disk_lg] [--zoom 17]
"""
import argparse
import glob
import math
import os
import sqlite3
import time

import cv2
import numpy as np

from day_pkg.local_matcher import LocalMatcher, map_m_per_px, tile_px_to_latlon, tile_xy

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--methods", default="sift,disk_lg,aliked_lg")
ap.add_argument("--zoom", type=int, default=17)
ap.add_argument("--mbtiles", default=os.environ.get("NAVERA_MBTILES", ""))
ap.add_argument("--frames", default=os.path.expanduser("~/navera_data/vision_pkg/vision_pkg/dataset/frames_gps"))
ap.add_argument("--sift-area", default=os.path.expanduser("~/.navera_sim/dayv/bench_area/images"))
ap.add_argument("--search-m", type=float, default=600.0)
ap.add_argument("--min-inliers", type=int, default=12)
ap.add_argument("--keypoints", type=int, default=2048)
ap.add_argument("--prior", choices=["previous", "carried"], default="carried",
                help="where to search: the previous frame's position, or carried along the "
                     "velocity of the two previous frames (what NAVERA does in flight)")
ap.add_argument("--normalize", action="store_true",
                help="brightness: the frame's lightness stretched (1-99 %%) then CLAHE before matching")
ap.add_argument("--heading-noise", type=float, default=5.0,
                help="deg: the frames are turned north-up from their heading as the IMU gives it "
                     "(the true heading + this much random error); -1 = not turned")
a = ap.parse_args()

files = sorted(glob.glob(a.frames + "/*.jpg"))
truth = [(float(os.path.basename(f).split("_lat")[1].split("_")[0]),
          float(os.path.basename(f).split("_lon")[1].split("_")[0])) for f in files]
# each frame's heading (its rotation against the map, measured once by SIFT with the true
# position: frames_heading.json — it equals the track's bearing within 1 deg; the frames SIFT
# never located take the bearing from the previous frame, as a compass / IMU would give it)
_hd = __import__("json").load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "frames_heading.json")))


def _bearing(p, q):
    return math.degrees(math.atan2((q[1] - p[1]) * math.cos(math.radians(p[0])), q[0] - p[0]))


HEADING = [_hd.get(os.path.basename(f), _bearing(truth[i - 1], truth[i]) if i else _bearing(truth[0], truth[1]))
           for i, f in enumerate(files)]
_rng = np.random.default_rng(1)


_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))


def normalize(img):
    """A dark or flat frame (auto-exposure, haze) brought to a full lightness range: the
    lightness stretched between its 1 and 99 % values, then local contrast (CLAHE); the
    colours kept. The black canvas around a turned frame is left out of the percentiles."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L = lab[:, :, 0]
    valid = img.max(axis=2) > 0
    if valid.sum() < 100:
        return img
    lo, hi = np.percentile(L[valid], (1, 99))
    L2 = np.clip((L.astype(np.float32) - lo) * 255.0 / max(hi - lo, 1.0), 0, 255).astype(np.uint8)
    lab[:, :, 0] = np.where(valid, _clahe.apply(L2), 0)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def north_up(img, rot_deg):
    """The frame turned by -rot_deg (its top to the north), on a canvas holding all of it."""
    h, w = img.shape[:2]
    R = cv2.getRotationMatrix2D((w / 2, h / 2), -rot_deg, 1.0)
    c, s_ = abs(R[0, 0]), abs(R[0, 1])
    nw, nh = int(h * s_ + w * c), int(h * c + w * s_)
    R[0, 2] += nw / 2 - w / 2
    R[1, 2] += nh / 2 - h / 2
    return cv2.warpAffine(img, R, (nw, nh))


FRAME_MPP = 0.62 * 0.9683 * 768 / 1536                 # the frames' ground resolution (benchmark)
Z = a.zoom


def hav(p, q):
    return 2 * 6371000 * math.asin(math.sqrt(math.sin(math.radians(q[0] - p[0]) / 2) ** 2 + math.cos(math.radians(p[0]))
                                             * math.cos(math.radians(q[0])) * math.sin(math.radians(q[1] - p[1]) / 2) ** 2))


con = sqlite3.connect(f"file:{a.mbtiles}?mode=ro", uri=True)
_tiles = {}


def tile(x, y, z=None):
    z = z or Z
    k = (x, y, z)
    if k not in _tiles:
        n = 2 ** z
        r = con.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                        (z, x, n - 1 - y)).fetchone()
        t = cv2.imdecode(np.frombuffer(r[0], np.uint8), cv2.IMREAD_COLOR) if r else None
        _tiles[k] = None if t is None else cv2.resize(t, (256, 256))
    return _tiles[k]


def map_crop(lat, lon, radius_m, z=None, ry_m=None):
    """The map around (lat, lon), +-radius_m (+-ry_m north-south); (image, global px of its
    top-left corner) at zoom z."""
    z = z or Z
    fx, fy = tile_xy(lat, lon, z)
    r = radius_m / map_m_per_px(lat, z)
    ry = (ry_m if ry_m is not None else radius_m) / map_m_per_px(lat, z)
    return pixels(int(fx * 256 - r), int(fy * 256 - ry), int(2 * r), int(2 * ry), z), (int(fx * 256 - r), int(fy * 256 - ry))


def pixels(x0, y0, size, size_y, z):
    """The map's global pixels [x0, x0+size) x [y0, y0+size_y) at zoom z."""
    out = np.zeros((size_y, size, 3), np.uint8)
    for ty in range(y0 // 256, (y0 + size_y) // 256 + 1):
        for tx in range(x0 // 256, (x0 + size) // 256 + 1):
            t = tile(tx, ty, z)
            if t is None:
                continue
            ox, oy = tx * 256 - x0, ty * 256 - y0
            sx, sy = max(0, -ox), max(0, -oy)
            dx, dy = max(0, ox), max(0, oy)
            w, h = min(256 - sx, size - dx), min(256 - sy, size_y - dy)
            if w > 0 and h > 0:
                out[dy:dy + h, dx:dx + w] = t[sy:sy + h, sx:sx + w]
    return out


class Learned:
    """kornia local features + LightGlue."""

    def __init__(self, kind):
        import torch
        import kornia.feature as KF
        self.torch, self.KF, self.kind = torch, KF, kind
        self.dev = torch.device("cuda")
        if kind == "disk":
            self.feat = KF.DISK.from_pretrained("depth").to(self.dev).eval()
        else:
            self.feat = KF.ALIKED.from_pretrained("aliked-n16").to(self.dev).eval()
        self.lg = KF.LightGlueMatcher(kind).to(self.dev).eval()

    def features_tiled(self, img, chunk=640, overlap=64, per_chunk=1024):
        """Features of a large image chunk by chunk (the GPU has 8 GB shared with the CPU)."""
        t = self.torch
        H, W = img.shape[:2]
        kps, descs = [], []
        step = chunk - overlap
        for y in range(0, max(H - overlap, 1), step):
            for x in range(0, max(W - overlap, 1), step):
                sub = img[y:y + chunk, x:x + chunk]
                if sub.shape[0] < 32 or sub.shape[1] < 32 or sub.std() < 3:
                    continue
                k, d, _ = self.features(sub, per_chunk)
                kps.append(k + t.tensor([x, y], device=self.dev, dtype=k.dtype)); descs.append(d)
        return t.cat(kps), t.cat(descs), (H, W)

    def features(self, img, n=None):
        t = self.torch
        x = t.from_numpy(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float().div(255)[None].to(self.dev)
        h, w = x.shape[2:]
        x = x[:, :, :h // 16 * 16, :w // 16 * 16]
        with t.inference_mode():
            if self.kind == "disk":
                f = self.feat(x, n or a.keypoints, pad_if_not_divisible=True)[0]
                kp, desc = f.keypoints, f.descriptors
            else:
                f = self.feat(x)                                   # ALIKED returns a dict-like
                kp, desc = f["keypoints"][0], f["descriptors"][0]
                kp = (kp + 1) / 2 * t.tensor([x.shape[3] - 1, x.shape[2] - 1], device=self.dev)
        return kp, desc, (h, w)

    _grid = {}

    def map_features(self, x0, y0, w, h, z, chunk=640, overlap=64, per_chunk=1024):
        """Map features in global pixels [x0, x0+w) x [y0, y0+h) at zoom z, from chunks on a
        fixed global grid, each computed once (a mission's area: before the flight)."""
        t = self.torch
        step = chunk - overlap
        kps, descs = [], []
        for gy in range(y0 // step, (y0 + h) // step + 1):
            for gx in range(x0 // step, (x0 + w) // step + 1):
                key = (z, gx, gy)
                if key not in self._grid:
                    sub = pixels(gx * step, gy * step, chunk, chunk, z)
                    if sub.std() < 3:
                        self._grid[key] = None
                    else:
                        k, d, _ = self.features(sub, per_chunk)
                        # kept in CPU memory (the GPU's 8 GB are shared): to the GPU when matched
                        self._grid[key] = ((k + t.tensor([gx * step, gy * step], device=self.dev, dtype=k.dtype)).cpu(),
                                           d.cpu())
                if self._grid[key] is not None:
                    kps.append(self._grid[key][0]); descs.append(self._grid[key][1])
        k, d = t.cat(kps), t.cat(descs)
        inside = (k[:, 0] >= x0) & (k[:, 0] < x0 + w) & (k[:, 1] >= y0) & (k[:, 1] < y0 + h)
        k, d = k[inside].to(self.dev), d[inside].to(self.dev)
        return k - t.tensor([x0, y0], device=self.dev, dtype=k.dtype), d, (h, w)

    def match(self, frame, mapimg=None, region=None):
        """Frame vs the map image, or vs the cached map features of region (x0, y0, w, h, z)."""
        t = self.torch
        k0, d0, s0 = self.features(frame)
        k1, d1, s1 = self.map_features(*region) if region else self.features_tiled(mapimg)
        with t.inference_mode():
            lafs0 = self.KF.laf_from_center_scale_ori(k0[None], t.ones(1, len(k0), 1, 1, device=self.dev))
            lafs1 = self.KF.laf_from_center_scale_ori(k1[None], t.ones(1, len(k1), 1, 1, device=self.dev))
            _, idx = self.lg(d0, d1, lafs0, lafs1, hw1=t.tensor(s0, device=self.dev), hw2=t.tensor(s1, device=self.dev))
        idx = idx.cpu().numpy()
        return k0.cpu().numpy()[idx[:, 0]], k1.cpu().numpy()[idx[:, 1]]


def locate_two_stage(m, frame, prior):
    """Coarse: zoom Z over the search circle (cached map features); fine: zoom Z+1 within
    +-60 m of the coarse fix (twice the detail)."""
    p, n = locate_learned(m, frame, prior, cached=True)
    if p is None:
        return None, n
    p2, n2 = locate_learned(m, frame, p, cached=True, z=Z + 1, search_m=60.0)
    return (p2, n2) if p2 is not None else (p, n)


def locate_learned(m, frame, prior, cached=False, z=None, search_m=None):
    z = z or Z
    search_m = a.search_m if search_m is None else search_m
    s = FRAME_MPP / map_m_per_px(prior[0], z)
    q = cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    if cached:
        fx, fy = tile_xy(prior[0], prior[1], z)
        mpp = map_m_per_px(prior[0], z)
        rx = (search_m + 0.5 * frame.shape[1] * FRAME_MPP) / mpp
        ry = (search_m + 0.5 * frame.shape[0] * FRAME_MPP) / mpp
        x0, y0 = int(fx * 256 - rx), int(fy * 256 - ry)
        src, dst = m.match(q, region=(x0, y0, int(2 * rx), int(2 * ry), z))
        return fit(q, src, dst, x0, y0, z)
    return locate_learned_full(m, frame, prior)


def fit(q, src, dst, x0, y0, z):
    if len(src) < a.min_inliers:
        return None, len(src)
    A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0,
                                         maxIters=5000, confidence=0.999)
    if A is None or int(inl.sum()) < a.min_inliers or abs(math.hypot(A[0, 0], A[1, 0]) - 1) > 0.15:
        return None, 0 if A is None else int(inl.sum())
    px, py = A @ np.array([q.shape[1] / 2.0, q.shape[0] / 2.0, 1.0])
    return tile_px_to_latlon(float(px) + x0, float(py) + y0, z), int(inl.sum())


def locate_learned_full(m, frame, prior):
    s = FRAME_MPP / map_m_per_px(prior[0], Z)
    q = cv2.resize(frame, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
    margin = 0.5 * math.hypot(*frame.shape[:2]) * FRAME_MPP
    mp, (x0, y0) = map_crop(prior[0], prior[1], a.search_m + margin)
    src, dst = m.match(q, mp)
    if len(src) < a.min_inliers:
        return None, len(src)
    A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=6.0,
                                         maxIters=5000, confidence=0.999)
    if A is None or int(inl.sum()) < a.min_inliers or abs(math.hypot(A[0, 0], A[1, 0]) - 1) > 0.15:
        return None, 0 if A is None else int(inl.sum())
    px, py = A @ np.array([q.shape[1] / 2.0, q.shape[0] / 2.0, 1.0])
    return tile_px_to_latlon(float(px) + x0, float(py) + y0, Z), int(inl.sum())


for meth in a.methods.split(","):
    if meth == "sift":
        M = LocalMatcher(a.sift_area, zoom=Z)
        M.min_inliers = a.min_inliers
        run = lambda img, prior: (lambda r: ((r["predicted_lat"], r["predicted_lon"]) if r["accepted"] else None,
                                            r["inliers"]))(M.locate(img, prior, a.search_m, FRAME_MPP))
    else:
        L = Learned("disk" if meth.startswith("disk") else "aliked")
        if meth == "disk2":
            run = lambda img, prior, L=L: locate_two_stage(L, img, prior)
        elif meth == "disk_c":
            run = lambda img, prior, L=L: locate_learned(L, img, prior, cached=True)
        else:
            run = lambda img, prior, L=L: locate_learned(L, img, prior)
        for i in range(len(files)):                           # the mission's map features, before the flight
            for z in (Z, Z + 1) if meth == "disk2" else (Z,):
                fx, fy = tile_xy(truth[i][0], truth[i][1], z)
                r = int((a.search_m + 300) / map_m_per_px(truth[i][0], z)) if z == Z else int(400 / map_m_per_px(truth[i][0], z))
                L.map_features(int(fx * 256 - r), int(fy * 256 - r), 2 * r, 2 * r, z)
    run(cv2.imread(files[0]), truth[0])                         # warm-up (models, caches)
    errs, times, wrong, inl = [], [], 0, []
    for i, f in enumerate(files):
        img = cv2.imread(f)
        if a.heading_noise >= 0:
            img = north_up(img, HEADING[i] + _rng.normal(0, a.heading_noise))
        if a.normalize:
            img = normalize(img)
        prior = truth[i - 1] if i else truth[0]
        if a.prior == "carried" and i >= 2:
            prior = (2 * truth[i - 1][0] - truth[i - 2][0], 2 * truth[i - 1][1] - truth[i - 2][1])
        t0 = time.time()
        p, n = run(img, prior)
        times.append(time.time() - t0)
        if p is not None:
            e = hav(p, truth[i]); errs.append(e); wrong += e > 50; inl.append(n)
    good = [e for e in errs if e <= 50]
    print(f"{meth:10s} zoom {Z}: located {len(errs):2d}/{len(files)}, wrong {wrong}, "
          + (f"error median {np.median(good):.1f} m, 90% {np.percentile(good, 90):.1f} m, max {max(good):.1f} m, "
             f"inliers median {int(np.median(inl))}, " if good else "")
          + f"{1000 * np.median(times):.0f} ms/frame", flush=True)
