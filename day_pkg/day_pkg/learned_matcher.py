"""Day localisation with learned features: DISK keypoints + LightGlue matching (kornia, GPU).

Same contract as local_matcher.LocalMatcher (it is one: locate(), locate_any_height(),
frame_m_per_px()), measured better on real aerial frames that differ from the map in
colour, shadows and date (navera_tools/bench/learned_matchers.py, 33 frames, 600 m search,
position carried along the velocity): 30/33 located, 0 wrong, 333 ms/frame on the Orin
Nano — SIFT (LocalMatcher): 22/33, 0 wrong, 720 ms.

DISK and LightGlue are not rotation invariant: the frame is turned north-up from its
heading before matching — heading_deg from the attitude, or, without an IMU, the
rotation the previous match measured (kept 10 s). With no heading at all, or when the
learned match fails, SIFT (rotation invariant) is tried: never worse than LocalMatcher.

The map's features are computed in 640 px chunks on a fixed grid of the map, once, kept in
memory (CPU) and saved next to the tiles (<images_dir>/../learned_features/), so a mission
area costs its computation only once (prepare_area.py can do it before the flight).
"""
import math
import os
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from day_pkg.local_matcher import LocalMatcher, map_m_per_px, tile_px_to_latlon, tile_xy


def north_up(img: np.ndarray, heading_deg: float) -> np.ndarray:
    """The frame turned so its top points north (its top was at heading_deg), on a canvas
    holding all of it; the frame centre stays the canvas centre."""
    h, w = img.shape[:2]
    R = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), -heading_deg, 1.0)
    c, s = abs(R[0, 0]), abs(R[0, 1])
    nw, nh = int(h * s + w * c), int(h * c + w * s)
    R[0, 2] += nw / 2.0 - w / 2.0
    R[1, 2] += nh / 2.0 - h / 2.0
    return cv2.warpAffine(img, R, (nw, nh))


class LearnedMatcher(LocalMatcher):
    """DISK + LightGlue against the map around a prior; SIFT (LocalMatcher) as the fallback."""

    CHUNK, OVERLAP, PER_CHUNK = 640, 64, 1024
    MIN_INLIERS = 12                  # LightGlue gives hundreds of inliers on a right place
    HEADING_MEMORY_S = 10.0           # a measured rotation stands in for the heading this long

    def __init__(self, images_dir: str, zoom: int = 17, keypoints: int = 2048, cache_dir: Optional[str] = None,
                 **kw):
        super().__init__(images_dir, zoom=zoom, **kw)
        import torch
        import kornia.feature as KF
        if not torch.cuda.is_available():
            raise RuntimeError("learned matcher: no GPU")
        self._t, self._KF = torch, KF
        self.dev = torch.device("cuda")
        self.disk = KF.DISK.from_pretrained("depth").to(self.dev).eval()
        self.lg = KF.LightGlueMatcher("disk").to(self.dev).eval()
        self.keypoints = int(keypoints)
        self.cache_dir = cache_dir or os.path.join(os.path.dirname(os.path.abspath(images_dir)), "learned_features")
        self._grid = {}
        self._gpu = threading.Lock()
        self._tiles = {}
        self._heading = None          # (rotation deg, time) of the last learned match
        self._no_fallback = False     # inside locate_any_height: no SIFT per height tried
        # the day node asks the SIFT tiles to prefetch around where the vehicle goes: the
        # learned map chunks are computed there too, in the background
        self._want, self._wake = None, threading.Event()
        sift_prefetch = self.tiles.prefetch

        def prefetch(lat, lon, radius_m):
            sift_prefetch(lat, lon, radius_m)
            self._want = (lat, lon, radius_m)
            self._wake.set()
        self.tiles.prefetch = prefetch
        threading.Thread(target=self._prefetch_loop, daemon=True).start()

    def _prefetch_loop(self):
        while True:
            self._wake.wait()
            self._wake.clear()
            if self._want is not None:
                try:
                    self.warm(*self._want)
                except Exception:                            # noqa: BLE001 — the frames compute it themselves
                    pass

    # ── map ──────────────────────────────────────────────────────────────
    def _tile_rgb(self, x: int, y: int) -> Optional[np.ndarray]:
        k = (x, y)
        if k not in self._tiles:
            im = cv2.imread(os.path.join(self.tiles.dir, f"tile_{self.z}_{x}_{y}.jpg"), cv2.IMREAD_COLOR)
            if im is not None and im.shape[:2] != (256, 256):
                im = cv2.resize(im, (256, 256), interpolation=cv2.INTER_AREA)
            if len(self._tiles) > 2000:
                self._tiles.clear()
            self._tiles[k] = im
        return self._tiles[k]

    def _pixels(self, x0: int, y0: int, w: int, h: int) -> np.ndarray:
        out = np.zeros((h, w, 3), np.uint8)
        for ty in range(y0 // 256, (y0 + h) // 256 + 1):
            for tx in range(x0 // 256, (x0 + w) // 256 + 1):
                t = self._tile_rgb(tx, ty)
                if t is None:
                    continue
                ox, oy = tx * 256 - x0, ty * 256 - y0
                sx, sy = max(0, -ox), max(0, -oy)
                dx, dy = max(0, ox), max(0, oy)
                cw, ch = min(256 - sx, w - dx), min(256 - sy, h - dy)
                if cw > 0 and ch > 0:
                    out[dy:dy + ch, dx:dx + cw] = t[sy:sy + ch, sx:sx + cw]
        return out

    def _frame_features(self, img: np.ndarray):
        """The frame's features; a frame larger than one chunk is done chunk by chunk (a high
        frame enlarged to the map's scale: one DISK pass would not fit in the GPU)."""
        h, w = img.shape[:2]
        if h <= self.CHUNK * 1.6 and w <= self.CHUNK * 1.6:
            return self._features(img, self.keypoints)
        t = self._t
        step = self.CHUNK - self.OVERLAP
        cells = [(x, y) for y in range(0, max(h - self.OVERLAP, 1), step) for x in range(0, max(w - self.OVERLAP, 1), step)]
        ks, ds = [], []
        for x, y in cells:
            sub = img[y:y + self.CHUNK, x:x + self.CHUNK]
            if sub.shape[0] < 32 or sub.shape[1] < 32 or sub.std() < 3:
                continue
            k, d = self._features(sub, max(256, self.keypoints // len(cells) * 2))
            ks.append(k + t.tensor([x, y], device=self.dev, dtype=k.dtype))
            ds.append(d)
        if not ks:
            return t.zeros((0, 2), device=self.dev), t.zeros((0, 128), device=self.dev)
        return t.cat(ks), t.cat(ds)

    def _features(self, img: np.ndarray, n: int):
        t = self._t
        x = t.from_numpy(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).permute(2, 0, 1).float().div(255)[None].to(self.dev)
        with self._gpu, t.inference_mode():
            f = self.disk(x, n, pad_if_not_divisible=True)[0]
        return f.keypoints, f.descriptors

    def _chunk(self, gx: int, gy: int):
        """Features of grid chunk (gx, gy): global map pixels (N,2) and descriptors, on the CPU."""
        key = (gx, gy)
        if key in self._grid:
            return self._grid[key]
        path = os.path.join(self.cache_dir, f"{self.z}_{gx}_{gy}.npz")
        out = None
        try:
            with np.load(path) as d:
                out = (self._t.from_numpy(d["k"]), self._t.from_numpy(d["d"]))
        except (OSError, KeyError, ValueError):
            step = self.CHUNK - self.OVERLAP
            sub = self._pixels(gx * step, gy * step, self.CHUNK, self.CHUNK)
            if sub.std() >= 3:                               # not a missing / blank area
                k, d = self._features(sub, self.PER_CHUNK)
                k = (k + self._t.tensor([gx * step, gy * step], device=self.dev, dtype=k.dtype)).cpu()
                out = (k, d.cpu())
            else:
                out = (self._t.zeros((0, 2)), self._t.zeros((0, 128)))
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
                np.savez(path + ".tmp.npz", k=out[0].numpy(), d=out[1].numpy())
                os.replace(path + ".tmp.npz", path)
            except OSError:
                pass                                         # read-only area: memory only
        if len(self._grid) > 4000:
            self._grid.clear()
        self._grid[key] = out
        return out

    def map_features(self, x0: int, y0: int, w: int, h: int):
        """Map features in global pixels [x0, x0+w) x [y0, y0+h), relative to (x0, y0), on the GPU."""
        t = self._t
        step = self.CHUNK - self.OVERLAP
        ks, ds = [], []
        for gy in range(y0 // step, (y0 + h) // step + 1):
            for gx in range(x0 // step, (x0 + w) // step + 1):
                k, d = self._chunk(gx, gy)
                if len(k):
                    ks.append(k)
                    ds.append(d)
        if not ks:
            return t.zeros((0, 2), device=self.dev), t.zeros((0, 128), device=self.dev)
        k, d = t.cat(ks), t.cat(ds)
        inside = (k[:, 0] >= x0) & (k[:, 0] < x0 + w) & (k[:, 1] >= y0) & (k[:, 1] < y0 + h)
        k = k[inside].to(self.dev) - t.tensor([x0, y0], device=self.dev, dtype=k.dtype)
        return k, d[inside].to(self.dev)

    def warm(self, lat: float, lon: float, radius_m: float) -> int:
        """Compute (and save) the map features within radius_m of (lat, lon): before a flight."""
        fx, fy = tile_xy(lat, lon, self.z)
        r = radius_m / map_m_per_px(lat, self.z)
        step = self.CHUNK - self.OVERLAP
        n = 0
        for gy in range(int(fy * 256 - r) // step, int(fy * 256 + r) // step + 1):
            for gx in range(int(fx * 256 - r) // step, int(fx * 256 + r) // step + 1):
                self._chunk(gx, gy)
                n += 1
        return n

    # ── localisation ─────────────────────────────────────────────────────
    def locate(self, frame, prior: Tuple[float, float], search_m: float, frame_m_per_px: float,
               margin_m: Optional[float] = None, scale_tol: Optional[float] = None,
               heading_deg: Optional[float] = None, heading_tol_deg: float = 20.0) -> dict:
        """As LocalMatcher.locate; res["features"] says which matcher gave the result."""
        t0 = time.time()
        hdg, hdg_src = heading_deg, "attitude"
        if hdg is None and self._heading and time.time() - self._heading[1] < self.HEADING_MEMORY_S:
            hdg, hdg_src = self._heading[0], "previous match"
        res = None
        if hdg is not None:
            try:
                res = self._locate_learned(frame, prior, search_m, frame_m_per_px, margin_m, scale_tol, hdg)
            except RuntimeError as e:                        # GPU out of memory, CUDA error: SIFT this frame
                res = dict(accepted=False, reason=f"learned matcher failed: {str(e)[:120]}")
                self._t.cuda.empty_cache()
            res["heading_source"] = hdg_src
            if res["accepted"] and heading_deg is not None and \
                    abs((res["rotation_deg"] - heading_deg + 180) % 360 - 180) > heading_tol_deg:
                res.update(accepted=False, reason=f"fitted rotation {res['rotation_deg']:.0f} deg ≠ heading "
                                                  f"{heading_deg:.0f} deg (±{heading_tol_deg:.0f}): wrong place")
        if (res is None or not res["accepted"]) and not (self._no_fallback and res is not None):
            learned = res
            res = super().locate(frame, prior, search_m, frame_m_per_px, margin_m=margin_m, scale_tol=scale_tol,
                                 heading_deg=heading_deg, heading_tol_deg=heading_tol_deg)
            res["features"] = "sift"
            if learned is not None:
                res["learned_reason"] = learned.get("reason")
        if res["accepted"] and res.get("rotation_deg") is not None:
            self._heading = (float(res["rotation_deg"]), time.time())
        res["total_ms"] = (time.time() - t0) * 1000.0
        return res

    def locate_any_height(self, frame, prior, search_m, hfov_deg, *args, heading_deg=None, **kw) -> dict:
        """As LocalMatcher.locate_any_height. With a heading, only the learned matcher runs
        at each height tried (SIFT at each of them doubled the time: 27 s for a first fix);
        without one, SIFT does the search (rotation invariant)."""
        if heading_deg is None and not (self._heading and time.time() - self._heading[1] < self.HEADING_MEMORY_S):
            return super().locate_any_height(frame, prior, search_m, hfov_deg, *args, heading_deg=heading_deg, **kw)
        self._no_fallback = True
        try:
            return super().locate_any_height(frame, prior, search_m, hfov_deg, *args, heading_deg=heading_deg, **kw)
        finally:
            self._no_fallback = False

    def _locate_learned(self, frame, prior, search_m, frame_m_per_px, margin_m, scale_tol, hdg) -> dict:
        tol = self.scale_tol if scale_tol is None else float(scale_tol)
        res = dict(spatial=True, spatial_empty=False, radius_m=float(search_m), matcher="local",
                   features="disk+lightglue", predicted_lat=None, predicted_lon=None, accepted=False, score=0.0,
                   fused_score=0.0, match=None, top5=[], n_candidates=0, inliers=0, scale_residual=None,
                   rotation_deg=None)
        img = frame if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        img = north_up(img, hdg)
        mpp_map = map_m_per_px(prior[0], self.z)
        s = frame_m_per_px / mpp_map
        if not (math.isfinite(s) and 0.02 < s < 50):
            res.update(reason=f"frame scale {s:.3f} of the map resolution is not plausible")
            return res
        q = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        if margin_m is None:
            margin_m = 0.5 * math.hypot(*frame.shape[:2]) * frame_m_per_px
        fx, fy = tile_xy(prior[0], prior[1], self.z)
        r = (search_m + margin_m) / mpp_map
        x0, y0 = int(fx * 256 - r), int(fy * 256 - r)
        k1, d1 = self.map_features(x0, y0, int(2 * r), int(2 * r))
        res["n_candidates"] = int(len(k1))
        if len(k1) < 10:
            res.update(spatial_empty=True, reason="no map tiles (or no texture) in the search circle")
            return res
        t = self._t
        k0, d0 = self._frame_features(q)
        if len(k0) < 10:
            res.update(reason="too few features in the frame (uniform ground, blur, darkness)")
            return res
        with self._gpu, t.inference_mode():
            ones0 = t.ones(1, len(k0), 1, 1, device=self.dev)
            ones1 = t.ones(1, len(k1), 1, 1, device=self.dev)
            _, idx = self.lg(d0, d1, self._KF.laf_from_center_scale_ori(k0[None], ones0),
                             self._KF.laf_from_center_scale_ori(k1[None], ones1),
                             hw1=t.tensor(q.shape[:2], device=self.dev), hw2=t.tensor((int(2 * r),) * 2, device=self.dev))
        idx = idx.cpu().numpy()
        good = len(idx)
        need = max(self.min_inliers, self.MIN_INLIERS)
        if good < need:
            res.update(reason=f"{good} feature matches (min {need})")
            return res
        src = k0.cpu().numpy()[idx[:, 0]].astype(np.float32)
        dst = k1.cpu().numpy()[idx[:, 1]].astype(np.float32)
        A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0,
                                             maxIters=5000, confidence=0.999)
        if A is None:
            res.update(reason="no consistent geometry")
            return res
        n_in = int(inl.sum())
        scale = math.hypot(A[0, 0], A[1, 0])
        px, py = A @ np.array([q.shape[1] / 2.0, q.shape[0] / 2.0, 1.0])
        lat, lon = tile_px_to_latlon(float(px) + x0, float(py) + y0, self.z)
        rot = (hdg + math.degrees(math.atan2(A[1, 0], A[0, 0])) + 180.0) % 360.0 - 180.0
        res.update(predicted_lat=lat, predicted_lon=lon, inliers=n_in, matches=good, scale_residual=round(scale, 3),
                   rotation_deg=round(rot, 1), score=float(n_in), fused_score=float(n_in),
                   match=f"{n_in} inliers / {good} matches (DISK+LightGlue)")
        if n_in < need:
            res["reason"] = f"{n_in} geometric inliers (min {need})"
        elif abs(scale - 1.0) > tol:
            res["reason"] = f"fitted scale {scale:.2f} ≠ 1 expected from the altitude (±{tol:.0%}): wrong place"
        else:
            res["accepted"] = True
        return res
