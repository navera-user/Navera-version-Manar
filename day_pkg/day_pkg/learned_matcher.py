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
area costs its computation only once — the first pass over each place is slower (warm()
computes an area ahead; prepare_area.py does not call it yet).
"""
import math
import os
import threading
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from day_pkg.local_matcher import (LocalMatcher, fix_sigma_m, inlier_spread, map_m_per_px, refine_with_pose,
                                   tile_px_to_latlon, tile_xy)


def map_level(frame_scale: float, max_level: int = 3) -> int:
    """Map level (the map shrunk 2**level times) to match a frame whose pixels are frame_scale map
    pixels: 0 up to 1.3 (the frame is enlarged a little), else the level nearest its scale."""
    if not math.isfinite(frame_scale) or frame_scale < 1.3:
        return 0
    return int(min(max_level, max(0, round(math.log2(frame_scale)))))


def north_up_matrix(shape, heading_deg: float):
    """(2x3 affine frame -> north-up canvas, canvas (w, h)) for north_up."""
    h, w = shape[:2]
    R = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), -heading_deg, 1.0)
    c, s = abs(R[0, 0]), abs(R[0, 1])
    nw, nh = int(h * s + w * c), int(h * c + w * s)
    R[0, 2] += nw / 2.0 - w / 2.0
    R[1, 2] += nh / 2.0 - h / 2.0
    return R, (nw, nh)


def north_up(img: np.ndarray, heading_deg: float) -> np.ndarray:
    """The frame turned so its top points north (its top was at heading_deg), on a canvas
    holding all of it; the frame centre stays the canvas centre."""
    R, size = north_up_matrix(img.shape, heading_deg)
    return cv2.warpAffine(img, R, size)


class LearnedMatcher(LocalMatcher):
    """DISK + LightGlue against the map around a prior; SIFT (LocalMatcher) as the fallback."""

    CHUNK, OVERLAP = 640, 64
    MIN_INLIERS = 12                  # LightGlue gives hundreds of inliers on a right place
    # memory (campaign 3, 2026-10-07: a lost vehicle's 1-1.5 km search window grew the
    # process to 4.2-4.9 GB and the 8 GB Jetson killed it): chunks kept in memory (~0.4 MB
    # each at 768 keypoints), map keypoints matched at once, and no SIFT fallback over a
    # window wider than this (it doubled the time of every failed frame: 33-64 s)
    MAX_CHUNKS = 500
    MAX_LEVEL = 3                     # map levels: up to 8x coarser than the zoom (high frames)
    MAX_MAP_KEYPOINTS = 24000
    SIFT_FALLBACK_MAX_M = 300.0
    HEADING_MEMORY_S = 10.0           # a measured rotation stands in for the heading this long
    RESCALE_MIN_INLIERS = 60          # a match rejected for its scale is retried at that scale from this many
    # heading search (an IMU without magnetometer: its yaw drifts, or is unknown): the frame is
    # turned north-up at these steps around the given heading until a match; more tries = more
    # chances of an accidental match, so one found away from the first heading needs more inliers
    heading_search_deg = 30.0
    HEADING_SEARCH_MIN_INLIERS = 25

    def __init__(self, images_dir: str, zoom: int = 17, keypoints: int = 1536, cache_dir: Optional[str] = None,
                 per_chunk: int = 768, half: bool = True,
                 **kw):
        super().__init__(images_dir, zoom=zoom, **kw)
        import torch
        import kornia.feature as KF
        if not torch.cuda.is_available():
            raise RuntimeError("learned matcher: no GPU")
        self._t, self._KF = torch, KF
        self.dev = torch.device("cuda")
        self.disk = KF.DISK.from_pretrained("depth").to(self.dev).eval()
        # half: DISK and LightGlue in fp16 on the GPU's tensor cores (LightGlue's own
        # mixed precision, "mp"); per_chunk: map keypoints per 640 px chunk
        self.half, self.PER_CHUNK = bool(half), int(per_chunk)
        self.lg = KF.LightGlueMatcher("disk", params={"mp": self.half}).to(self.dev).eval()
        self.keypoints = int(keypoints)
        self.cache_dir = cache_dir or os.path.join(os.path.dirname(os.path.abspath(images_dir)), "learned_features")
        from collections import OrderedDict
        self._grid = OrderedDict()    # chunk -> features, least recently used dropped first
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
            if len(self._tiles) > 300:                # only needed while computing chunks
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
            with t.autocast("cuda", dtype=t.float16, enabled=self.half):
                f = self.disk(x, n, pad_if_not_divisible=True)[0]
        return f.keypoints.float(), f.descriptors.float()

    def _chunk(self, gx: int, gy: int, level: int = 0):
        """Features of grid chunk (gx, gy) of map level `level` (the map shrunk 2**level times):
        level pixels (N,2) and descriptors, on the CPU."""
        key = (gx, gy) if level == 0 else (level, gx, gy)
        if key in self._grid:
            self._grid.move_to_end(key)
            return self._grid[key]
        lv = f"_L{level}" if level else ""
        path = os.path.join(self.cache_dir, f"{self.z}_{gx}_{gy}{lv}_k{self.PER_CHUNK}{'h' if self.half else ''}.npz")
        out = None
        try:
            with np.load(path) as d:
                out = (self._t.from_numpy(d["k"]), self._t.from_numpy(d["d"]))
        except (OSError, KeyError, ValueError):
            step, f = self.CHUNK - self.OVERLAP, 2 ** level
            sub = self._pixels(gx * step * f, gy * step * f, self.CHUNK * f, self.CHUNK * f)
            if f > 1:
                sub = cv2.resize(sub, (self.CHUNK, self.CHUNK), interpolation=cv2.INTER_AREA)
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
        self._grid[key] = out
        while len(self._grid) > self.MAX_CHUNKS:      # a memory budget, not a wipe
            self._grid.popitem(last=False)
        return out

    def map_features(self, x0: int, y0: int, w: int, h: int, level: int = 0):
        """Map features in global pixels [x0, x0+w) x [y0, y0+h) of map level `level` (2**level
        times coarser than the zoom), relative to (x0, y0), on the GPU."""
        t = self._t
        step = self.CHUNK - self.OVERLAP
        ks, ds = [], []
        for gy in range(y0 // step, (y0 + h) // step + 1):
            for gx in range(x0 // step, (x0 + w) // step + 1):
                k, d = self._chunk(gx, gy, level)
                if len(k):
                    ks.append(k)
                    ds.append(d)
        if not ks:
            return t.zeros((0, 2), device=self.dev), t.zeros((0, 128), device=self.dev)
        k, d = t.cat(ks), t.cat(ds)
        inside = (k[:, 0] >= x0) & (k[:, 0] < x0 + w) & (k[:, 1] >= y0) & (k[:, 1] < y0 + h)
        k, d = k[inside], d[inside]
        if len(k) > self.MAX_MAP_KEYPOINTS:          # evenly thinned: memory of the matching
            keep = t.linspace(0, len(k) - 1, self.MAX_MAP_KEYPOINTS).long()
            k, d = k[keep], d[keep]
        k = k.to(self.dev) - t.tensor([x0, y0], device=self.dev, dtype=k.dtype)
        return k, d.to(self.dev)

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
               heading_deg: Optional[float] = None, heading_tol_deg: float = 20.0,
               hfov_deg: Optional[float] = None, heading_search: bool = False) -> dict:
        """As LocalMatcher.locate; res["features"] says which matcher gave the result.
        heading_search: the heading is not trusted (no magnetometer: unknown, or drifted by
        tens of degrees) — when no match is found at it, the frame is tried turned every
        heading_search_deg around it (the full circle; the previous match's rotation first),
        and the fitted rotation is not checked against heading_deg."""
        t0 = time.time()
        if heading_search:
            res = self._locate_heading_search(frame, prior, search_m, frame_m_per_px, margin_m, scale_tol,
                                              heading_deg, hfov_deg)
            res["total_ms"] = (time.time() - t0) * 1000.0
            if search_m > 300.0:
                self._t.cuda.empty_cache()
            return res
        hdg, hdg_src = heading_deg, "attitude"
        if hdg is None and self._heading and time.time() - self._heading[1] < self.HEADING_MEMORY_S:
            hdg, hdg_src = self._heading[0], "previous match"
        res = None
        if hdg is not None:
            try:
                res = self._locate_learned(frame, prior, search_m, frame_m_per_px, margin_m, scale_tol, hdg,
                                           hfov_deg)
            except RuntimeError as e:                        # GPU out of memory, CUDA error: SIFT this frame
                res = dict(accepted=False, reason=f"learned matcher failed: {str(e)[:120]}")
                self._t.cuda.empty_cache()
            res["heading_source"] = hdg_src
            if res["accepted"] and heading_deg is not None and \
                    abs((res["rotation_deg"] - heading_deg + 180) % 360 - 180) > heading_tol_deg:
                res.update(accepted=False, reason=f"fitted rotation {res['rotation_deg']:.0f} deg ≠ heading "
                                                  f"{heading_deg:.0f} deg (±{heading_tol_deg:.0f}): wrong place")
            sc = float(res.get("scale_residual") or 1.0)
            if not res["accepted"] and "fitted scale" in str(res.get("reason")) and \
                    int(res.get("inliers") or 0) >= self.RESCALE_MIN_INLIERS and 0.6 < sc < 1.6:
                # a strong match at another scale than the height predicts (height 20 % off:
                # 0/10 located, simulation): matched again at the scale it measured, kept only
                # if that second match confirms it (scale within tolerance, same heading check)
                again = self._locate_learned(frame, prior, search_m, frame_m_per_px * sc, margin_m, scale_tol,
                                             hdg, hfov_deg)
                if again["accepted"] and not (heading_deg is not None and abs(
                        (again["rotation_deg"] - heading_deg + 180) % 360 - 180) > heading_tol_deg):
                    res = dict(again, heading_source=hdg_src, rescaled_by=round(sc, 3))
        if (res is None or not res["accepted"]) and not (self._no_fallback and res is not None) \
                and (res is None or search_m <= self.SIFT_FALLBACK_MAX_M):
            learned = res
            res = super().locate(frame, prior, search_m, frame_m_per_px, margin_m=margin_m, scale_tol=scale_tol,
                                 heading_deg=heading_deg, heading_tol_deg=heading_tol_deg, hfov_deg=hfov_deg)
            res["features"] = "sift"
            if learned is not None:
                res["learned_reason"] = learned.get("reason")
        if res["accepted"] and res.get("rotation_deg") is not None:
            self._heading = (float(res["rotation_deg"]), time.time())
        res["total_ms"] = (time.time() - t0) * 1000.0
        if search_m > 300.0:
            # a wide window's tensors stay in PyTorch's cache, which on the Jetson is system
            # memory: a single 600 m frame raised the process by 1.7 GB (campaign 4)
            self._t.cuda.empty_cache()
        return res

    def heading_search_order(self, heading_deg: Optional[float]) -> list:
        """Headings tried by the heading search, in order: the previous match's rotation (kept
        HEADING_MEMORY_S), the given heading, then alternately right and left of it every
        heading_search_deg, the full circle once."""
        out = []
        if self._heading and time.time() - self._heading[1] < self.HEADING_MEMORY_S:
            out.append(self._heading[0])
        base = heading_deg if heading_deg is not None else (out[0] if out else 0.0)
        n = max(1, int(round(360.0 / self.heading_search_deg)))
        out.append(base)
        for k in range(1, n // 2 + 1):
            out += [base + k * self.heading_search_deg, base - k * self.heading_search_deg]
        uniq = []
        for h in out:
            h = (h + 180.0) % 360.0 - 180.0
            if not any(abs((h - x + 180.0) % 360.0 - 180.0) < 1.0 for x in uniq):
                uniq.append(h)
        return uniq

    def _locate_heading_search(self, frame, prior, search_m, frame_m_per_px, margin_m, scale_tol, heading_deg,
                               hfov_deg) -> dict:
        """The learned match at headings around the given one (locate(heading_search=True))."""
        res, tried = None, []
        for h in self.heading_search_order(heading_deg):
            tried.append(h)
            try:
                r = self._locate_learned(frame, prior, search_m, frame_m_per_px, margin_m, scale_tol, h, hfov_deg)
            except RuntimeError as e:                        # GPU out of memory, CUDA error
                self._t.cuda.empty_cache()
                r = dict(accepted=False, reason=f"learned matcher failed: {str(e)[:120]}", inliers=0)
            # the first heading is trusted as a normal match; any other is a search, which
            # needs more inliers
            if r["accepted"] and len(tried) > 1 and int(r.get("inliers") or 0) < self.HEADING_SEARCH_MIN_INLIERS:
                r = dict(r, accepted=False, reason=f"heading search: {r.get('inliers')} inliers at heading "
                                                   f"{h:.0f} (min {self.HEADING_SEARCH_MIN_INLIERS})")
            if res is None or r["accepted"] or (not res["accepted"] and
                                               int(r.get("inliers") or 0) > int(res.get("inliers") or 0)):
                res = r
            if r["accepted"]:
                break
        res = dict(res, heading_source="heading search", heading_tried=[round(x) for x in tried])
        if res["accepted"] and res.get("rotation_deg") is not None:
            self._heading = (float(res["rotation_deg"]), time.time())
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

    def _locate_learned(self, frame, prior, search_m, frame_m_per_px, margin_m, scale_tol, hdg,
                        hfov_deg=None) -> dict:
        tol = self.scale_tol if scale_tol is None else float(scale_tol)
        res = dict(spatial=True, spatial_empty=False, radius_m=float(search_m), matcher="local",
                   features="disk+lightglue", predicted_lat=None, predicted_lon=None, accepted=False, score=0.0,
                   fused_score=0.0, match=None, top5=[], n_candidates=0, inliers=0, scale_residual=None,
                   rotation_deg=None)
        img = frame if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        rot_m, rot_size = north_up_matrix(img.shape, hdg)
        img = cv2.warpAffine(img, rot_m, rot_size)
        mpp_map = map_m_per_px(prior[0], self.z)
        s0 = frame_m_per_px / mpp_map
        if not (math.isfinite(s0) and 0.02 < s0 < 50):
            res.update(reason=f"frame scale {s0:.3f} of the map resolution is not plausible")
            return res
        # a high frame is not enlarged to the map's scale (2-3x: 10-15 s and 4.5 GB a frame at
        # 1500 m): it is matched on a map level shrunk 2**level times, near its own scale
        level = map_level(s0, self.MAX_LEVEL)
        f = 2 ** level
        s = s0 / f
        q = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)
        if margin_m is None:
            margin_m = 0.5 * math.hypot(*frame.shape[:2]) * frame_m_per_px
        fx, fy = tile_xy(prior[0], prior[1], self.z)
        r = (search_m + margin_m) / (mpp_map * f)                 # in level pixels
        x0, y0 = int(fx * 256 / f - r), int(fy * 256 / f - r)
        k1, d1 = self.map_features(x0, y0, int(2 * r), int(2 * r), level)
        res["map_level"] = level
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
        px, py = (float(px) + x0) * f, (float(py) + y0) * f      # global pixels of the zoom
        lat, lon = tile_px_to_latlon(px, py, self.z)
        rot = (hdg + math.degrees(math.atan2(A[1, 0], A[0, 0])) + 180.0) % 360.0 - 180.0
        res.update(predicted_lat=lat, predicted_lon=lon, inliers=n_in, matches=good, scale_residual=round(scale, 3),
                   rotation_deg=round(rot, 1), score=float(n_in), fused_score=float(n_in),
                   match=f"{n_in} inliers / {good} matches (DISK+LightGlue)",
                   spread=inlier_spread(src[inl.ravel() > 0], q.shape), sigma_m=fix_sigma_m(n_in, mpp_map * f))
        # the pose from the matches near the similarity fit (loosely: a tilted frame's edges
        # depart from a similarity), its own RANSAC removing the rest
        m = np.hypot(*(src @ A[:, :2].T.astype(np.float32) + A[:, 2].astype(np.float32) - dst).T) < 16.0
        inv = cv2.invertAffineTransform(rot_m)       # north-up canvas -> frame pixels
        fp = (src / np.float32(s)) @ inv[:, :2].T.astype(np.float32) + inv[:, 2].astype(np.float32)
        mp = (dst + np.float32([x0, y0])) * np.float32(f)
        fi = inl.ravel() > 0
        not_straight = refine_with_pose(res, (fp[fi], mp[fi]), (fp[m], mp[m]), (frame.shape[1], frame.shape[0]),
                                        hfov_deg, frame_m_per_px, scale, mpp_map, self.z,
                                        (px, py))
        if n_in < need:
            res["reason"] = f"{n_in} geometric inliers (min {need})"
        elif not_straight:
            res["reason"] = not_straight
        elif abs(scale - 1.0) > tol:
            res["reason"] = f"fitted scale {scale:.2f} ≠ 1 expected from the altitude (±{tol:.0%}): wrong place"
        else:
            res["accepted"] = True
        return res
