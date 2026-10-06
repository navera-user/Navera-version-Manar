"""Day vision by local feature matching against the satellite map around a prior.

The camera frame is scaled to the map's resolution (altitude + camera field of view),
its SIFT features are matched to those of the map tiles within the search circle, and
a rotation + scale + translation is fitted with RANSAC. The frame centre, carried
through that fit, is the position.

A match is accepted only when the fit is geometrically right, not when a similarity
score is high:
  * enough RANSAC inliers (min_inliers), and
  * the fitted scale equals the one the altitude predicts (scale_tol): a wrong place
    almost never matches at the right scale.

Benchmark (2026-10-01, the 33 labelled frames DINOv2 retrieval scored 442 m median on,
search within 600 m of the previous true position): 32/33 accepted, all within 9 m
(median 4 m), no wrong position accepted, ~420 ms per frame on the Jetson CPU once the
map tiles' features are computed. Those frames are aerial images from another source
and date than the map — not frames from NAVERA's camera.

Map tiles come from a prepared area (images/tile_{z}_{x}_{y}.jpg, XYZ numbering, as
prepare_area.py writes them). Each tile's features are computed once, on the tile with
a border from its neighbours (no seams), and kept in an LRU cache.
"""
import math
import os
import threading
import time
from collections import OrderedDict
from typing import Optional, Tuple

import cv2
import numpy as np

EQUATOR_M = 40075016.7


def tile_xy(lat: float, lon: float, z: int) -> Tuple[float, float]:
    """Fractional XYZ tile coordinates of (lat, lon) at zoom z."""
    n = 2 ** z
    r = math.radians(lat)
    return (lon + 180.0) / 360.0 * n, (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n


def tile_px_to_latlon(px: float, py: float, z: int) -> Tuple[float, float]:
    """(lat, lon) of a global tile-pixel position (256 px per tile) at zoom z."""
    n = 2 ** z
    x, y = px / 256.0, py / 256.0
    return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n)))), x / n * 360.0 - 180.0


def map_m_per_px(lat: float, z: int) -> float:
    return EQUATOR_M * math.cos(math.radians(lat)) / 2 ** z / 256.0


def inlier_spread(pts: np.ndarray, shape) -> float:
    """How much of the frame the inliers cover: the share of a 4 x 2 grid of cells holding
    at least 3 of them. A fix whose inliers sit on one strip (a shoreline, a road) is poorly
    conditioned in scale and rotation."""
    h, w = shape[:2]
    if len(pts) == 0:
        return 0.0
    cx = np.clip((pts[:, 0] / max(w, 1) * 4).astype(int), 0, 3)
    cy = np.clip((pts[:, 1] / max(h, 1) * 2).astype(int), 0, 1)
    counts = np.bincount(cy * 4 + cx, minlength=8)
    return float((counts >= 3).sum()) / 8.0


def fix_sigma_m(inliers: int, map_mpp: float) -> float:
    """1-sigma error of a fix from its inlier count, in map pixels times their size —
    campaign 2026-10-06 (2-3 years between map and ground, ~0.97 m map pixels): >= 100
    inliers p95 7.6 m, 50-99 about 15 m, 20-49 p95 29-34 m, fewer p95 up to 47 m."""
    px = 4.0 if inliers >= 100 else 8.0 if inliers >= 50 else 15.0 if inliers >= 20 else 25.0
    return px * float(map_mpp)


class TileFeatures:
    """SIFT features of the map tiles of an area, computed lazily and cached."""

    PAD = 48                          # border taken from the neighbours

    def __init__(self, images_dir: str, zoom: int = 17, per_tile: int = 300, cache_tiles: int = 3000):
        self.dir, self.z, self.cap = images_dir, zoom, cache_tiles
        self.sift = cv2.SIFT_create(nfeatures=per_tile, contrastThreshold=0.02)
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self._img = OrderedDict()
        self._feat = OrderedDict()
        self._lock = threading.RLock()            # the prefetch thread and the frames share the caches
        self._want = None                         # latest prefetch request (lat, lon, radius_m)
        self._wake = threading.Event()
        threading.Thread(target=self._prefetch_loop, daemon=True).start()

    def prefetch(self, lat: float, lon: float, radius_m: float) -> None:
        """Compute the features of the tiles around (lat, lon) in the background (latest
        request wins): frames never wait for tiles the vehicle is flying into."""
        self._want = (lat, lon, radius_m)
        self._wake.set()

    def _prefetch_loop(self):
        while True:
            self._wake.wait()
            self._wake.clear()
            want = self._want
            if want is None:
                continue
            cx, cy = tile_xy(want[0], want[1], self.z)
            r = want[2] / map_m_per_px(want[0], self.z) / 256.0
            for tx, ty in sorted(((tx, ty) for tx in range(int(cx - r), int(cx + r) + 1)
                                  for ty in range(int(cy - r), int(cy + r) + 1)),
                                 key=lambda t: (t[0] + 0.5 - cx) ** 2 + (t[1] + 0.5 - cy) ** 2):
                if self._wake.is_set():           # a newer request: serve it first
                    break
                self.get(tx, ty)

    def _tile(self, x: int, y: int) -> Optional[np.ndarray]:
        with self._lock:
            return self._tile_locked(x, y)

    def _tile_locked(self, x: int, y: int) -> Optional[np.ndarray]:
        k = (x, y)
        if k in self._img:
            self._img.move_to_end(k)
            return self._img[k]
        im = cv2.imread(os.path.join(self.dir, f"tile_{self.z}_{x}_{y}.jpg"), cv2.IMREAD_GRAYSCALE)
        if im is not None and im.shape != (256, 256):
            im = cv2.resize(im, (256, 256), interpolation=cv2.INTER_AREA)
        self._img[k] = im
        if len(self._img) > self.cap:
            self._img.popitem(last=False)
        return im

    def get(self, x: int, y: int):
        """(points (N,2) in global tile pixels, descriptors (N,128) float32) of tile (x, y)."""
        k = (x, y)
        with self._lock:
            if k in self._feat:
                self._feat.move_to_end(k)
                return self._feat[k]
        out = self._compute(x, y)
        with self._lock:
            self._feat[k] = out
            if len(self._feat) > self.cap:
                self._feat.popitem(last=False)
        return out

    def _compute(self, x: int, y: int):
        """Features of tile (x, y), on the tile with a border from its neighbours."""
        if self._tile(x, y) is None:
            out = (np.zeros((0, 2), np.float32), np.zeros((0, 128), np.float32))
        else:
            p = self.PAD
            big = np.zeros((256 + 2 * p, 256 + 2 * p), np.uint8)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    t = self._tile(x + dx, y + dy)
                    if t is None:
                        continue
                    # this neighbour's part that falls in the padded window
                    wx0, wy0 = 256 * dx + p, 256 * dy + p
                    sx0, sy0 = max(0, -wx0), max(0, -wy0)
                    ex, ey = min(256, big.shape[1] - wx0), min(256, big.shape[0] - wy0)
                    if ex > sx0 and ey > sy0:
                        big[wy0 + sy0:wy0 + ey, wx0 + sx0:wx0 + ex] = t[sy0:ey, sx0:ex]
            kp, d = self.sift.detectAndCompute(self.clahe.apply(big), None)
            pts, des = [], []
            for kpt, v in zip(kp or (), d if d is not None else ()):
                u, w = kpt.pt[0] - p, kpt.pt[1] - p
                if 0 <= u < 256 and 0 <= w < 256:
                    pts.append((x * 256 + u, y * 256 + w))
                    des.append(v)
            out = (np.float32(pts).reshape(-1, 2), np.float32(des).reshape(-1, 128))
        return out

    def around(self, lat: float, lon: float, radius_m: float):
        """All tile features within radius_m of (lat, lon)."""
        cx, cy = tile_xy(lat, lon, self.z)
        r = radius_m / map_m_per_px(lat, self.z) / 256.0
        P, D = [], []
        for tx in range(int(cx - r), int(cx + r) + 1):
            for ty in range(int(cy - r), int(cy + r) + 1):
                p, d = self.get(tx, ty)
                if len(p):
                    P.append(p)
                    D.append(d)
        if not P:
            return np.zeros((0, 2), np.float32), np.zeros((0, 128), np.float32)
        return np.concatenate(P), np.concatenate(D)


class LocalMatcher:
    """Locates a nadir camera frame on the map around a prior position."""

    GPU_BLOCK = 20000                 # map descriptors per GPU distance block (~120 MB)

    def __init__(self, images_dir: str, zoom: int = 17, min_inliers: int = 8, scale_tol: float = 0.15,
                 query_features: int = 1500, ratio: float = 0.8, ransac_px: float = 6.0, device: str = "auto"):
        self.tiles = TileFeatures(images_dir, zoom)
        self.z, self.min_inliers, self.scale_tol = zoom, min_inliers, scale_tol
        self.ratio, self.ransac_px = ratio, ransac_px
        self.sift = cv2.SIFT_create(nfeatures=query_features, contrastThreshold=0.02)
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)
        self.torch = None
        if device != "cpu":
            try:
                import torch
                if torch.cuda.is_available():
                    self.torch = torch                 # nearest-neighbour search on the GPU
            except Exception:                          # noqa: BLE001 — CPU matching instead
                self.torch = None

    def _knn2(self, dq: np.ndarray, dm: np.ndarray):
        """For each frame descriptor: (index, distance) of its two nearest map descriptors."""
        if self.torch is not None:
            t = self.torch
            with t.no_grad():
                q = t.from_numpy(dq).cuda()
                best_v = best_i = None
                for start in range(0, len(dm), self.GPU_BLOCK):     # bounded GPU memory
                    blk = t.from_numpy(dm[start:start + self.GPU_BLOCK]).cuda()
                    v, i = t.topk(t.cdist(q, blk), k=min(2, len(blk)), dim=1, largest=False)
                    i = i + start
                    if best_v is None:
                        best_v, best_i = v, i
                    else:
                        cv, ci = t.cat([best_v, v], 1), t.cat([best_i, i], 1)
                        best_v, o = t.topk(cv, k=2, dim=1, largest=False)
                        best_i = t.gather(ci, 1, o)
            return best_i.cpu().numpy(), best_v.cpu().numpy()
        # (with k=2 and more map than frame descriptors every frame descriptor gets two)
        pairs = self.matcher.knnMatch(dq, dm, k=2)
        idx = np.array([[p[0].trainIdx, p[1].trainIdx] for p in pairs])
        val = np.array([[p[0].distance, p[1].distance] for p in pairs])
        return idx.reshape(-1, 2), val.reshape(-1, 2)

    @staticmethod
    def frame_m_per_px(width_px: int, altitude_m: float, hfov_deg: float) -> float:
        """Ground resolution of a nadir frame: its footprint width over its pixel width."""
        return 2.0 * altitude_m * math.tan(math.radians(hfov_deg) / 2.0) / width_px

    def locate_any_height(self, frame, prior: Tuple[float, float], search_m: float, hfov_deg: float,
                          min_alt_m: float = 30.0, max_alt_m: float = 1500.0, step: float = 1.5,
                          min_inliers: int = 15, heading_deg: Optional[float] = None,
                          heading_tol_deg: float = 20.0, max_margin_m: float = 1000.0,
                          start_alt_m: Optional[float] = None, enough_inliers: int = 80) -> dict:
        """The frame's position AND the camera's height above the ground, with no height
        known (no GPS, no barometer): heights from min_alt_m to max_alt_m, each step x the
        previous, are tried with a +-30 % scale window around each (the windows overlap), and
        the strongest match wins. The fitted scale then measures the height:
        h = h_tried x scale (the ground width seen grows with the height).
        start_alt_m (the likeliest height: the last known one, the planned one): the ladder
        is tried from it outward, and stops at the first match with enough_inliers — a
        right place gives hundreds with the learned matcher, a wrong one a few dozen at most
        (campaign 2026-10-06: every fix wrong by > 20 m had <= 81 inliers).
        More scales tried = more chances of a match by accident at a wrong place: this needs
        min_inliers (15) instead of the usual 8. Adds "altitude_m" and "heights_tried"."""
        width = frame.shape[1]
        best, tried = None, []
        ladder, h = [], float(min_alt_m)
        while h <= max_alt_m * 1.0001:
            ladder.append(h)
            h *= step
        if start_alt_m and math.isfinite(start_alt_m) and start_alt_m > 0:
            ladder.sort(key=lambda x: abs(math.log(x / start_alt_m)))
        for h in ladder:
            mpp = 2.0 * h * math.tan(math.radians(hfov_deg) / 2.0) / width
            # the map loaded: the search circle + at most max_margin_m (half a high frame's
            # footprint would load several km of map per height tried)
            margin = min(0.5 * math.hypot(*frame.shape[:2]) * mpp, max_margin_m)
            r = self.locate(frame, prior, search_m, mpp, margin_m=margin, scale_tol=0.3,
                            heading_deg=heading_deg, heading_tol_deg=heading_tol_deg)
            tried.append(round(h))
            if r.get("accepted") and int(r.get("inliers") or 0) >= min_inliers and \
                    (best is None or r["inliers"] > best["inliers"]):
                best = dict(r, altitude_m=h * float(r["scale_residual"]), height_tried_m=h)
                if start_alt_m and best["inliers"] >= enough_inliers:
                    break
        if best is None:
            return {"accepted": False, "predicted_lat": None, "predicted_lon": None, "heights_tried": tried,
                    "reason": f"no match at any height {tried[0]}-{tried[-1]} m (min {min_inliers} inliers)"}
        best["heights_tried"] = tried
        return best

    def locate(self, frame, prior: Tuple[float, float], search_m: float, frame_m_per_px: float,
               margin_m: Optional[float] = None, scale_tol: Optional[float] = None,
               heading_deg: Optional[float] = None, heading_tol_deg: float = 20.0) -> dict:
        """Position of the frame centre near prior, as a result dict (see keys below).
        scale_tol: accepted |fitted scale - 1| for this frame (default self.scale_tol) —
        wider when the frame's altitude is uncertain.
        heading_deg: azimuth of the frame's top from the attitude (live camera): the fitted
        rotation must agree within heading_tol_deg — a wrong place rarely fits with both
        the right scale and the right rotation."""
        tol = self.scale_tol if scale_tol is None else float(scale_tol)
        t0 = time.time()
        res = dict(spatial=True, spatial_empty=False, radius_m=float(search_m), matcher="local",
                   predicted_lat=None, predicted_lon=None, accepted=False, score=0.0, fused_score=0.0,
                   match=None, top5=[], n_candidates=0, inliers=0, scale_residual=None, rotation_deg=None)
        grey = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mpp_map = map_m_per_px(prior[0], self.z)
        s = frame_m_per_px / mpp_map                     # frame pixels → map pixels
        if not (math.isfinite(s) and 0.02 < s < 50):
            res.update(error=f"frame scale {s:.3f} of the map resolution is not plausible")
            return res
        q = self.clahe.apply(cv2.resize(grey, None, fx=s, fy=s,
                                        interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR))
        if margin_m is None:                              # half the frame's diagonal on the ground
            margin_m = 0.5 * math.hypot(*grey.shape[:2]) * frame_m_per_px
        pm, dm = self.tiles.around(prior[0], prior[1], search_m + margin_m)
        res["n_candidates"] = int(len(dm))
        if len(dm) < 10:
            res.update(spatial_empty=True, reason="no map tiles (or no texture) in the search circle")
            return res
        kq, dq = self.sift.detectAndCompute(q, None)
        if dq is None or len(kq) < 10:
            res.update(reason="too few features in the frame (uniform ground, blur, darkness)")
            return res
        idx, val = self._knn2(dq, dm)
        ok = val[:, 0] < self.ratio * val[:, 1]
        qi = np.nonzero(ok)[0]
        good = len(qi)
        if good < self.min_inliers:
            res.update(reason=f"{good} feature matches (min {self.min_inliers})")
            return res
        src = np.float32([kq[i].pt for i in qi])
        dst = pm[idx[qi, 0]].astype(np.float32)
        A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=self.ransac_px,
                                             maxIters=5000, confidence=0.999)
        if A is None:
            res.update(reason="no consistent geometry")
            return res
        n_in = int(inl.sum())
        scale = math.hypot(A[0, 0], A[1, 0])              # 1.0 when the altitude/FOV prediction is right
        px, py = A @ np.array([q.shape[1] / 2.0, q.shape[0] / 2.0, 1.0])
        lat, lon = tile_px_to_latlon(float(px), float(py), self.z)
        res.update(predicted_lat=lat, predicted_lon=lon, inliers=n_in, matches=good,
                   scale_residual=round(scale, 3), rotation_deg=round(math.degrees(math.atan2(A[1, 0], A[0, 0])), 1),
                   score=float(n_in), fused_score=float(n_in), match=f"{n_in} inliers / {good} matches",
                   spread=inlier_spread(src[inl.ravel() > 0], q.shape), sigma_m=fix_sigma_m(n_in, mpp_map))
        if n_in < self.min_inliers:
            res["reason"] = f"{n_in} geometric inliers (min {self.min_inliers})"
        elif heading_deg is not None and abs((res["rotation_deg"] - heading_deg + 180) % 360 - 180) > heading_tol_deg:
            res["reason"] = (f"fitted rotation {res['rotation_deg']:.0f} deg ≠ heading {heading_deg:.0f} deg "
                             f"(±{heading_tol_deg:.0f}): wrong place")
        elif abs(scale - 1.0) > tol:
            res["reason"] = (f"fitted scale {scale:.2f} ≠ 1 expected from the altitude (±{tol:.0%}): "
                             "wrong place")
        else:
            res["accepted"] = True
        res["total_ms"] = (time.time() - t0) * 1000.0
        return res
