"""The day camera's lens, calibrated in flight against the map while the GPS is trusted.

No checkerboard: the satellite map is the calibration target. NAVERA always takes off with GPS
(the start rule); while it is trusted, every GPS-check match (day_subscriber._calibrate_altitude)
pairs points of the frame with points of the map — a few hundred ground control points per frame,
on a plane, seen from a known place (the GPS) with a known attitude (the IMU). That is a planar
camera calibration (Zhang) whose target is the ground:

    observation  the frame point, taken back through live_camera's straightening (the homography
                 of the frame's attitude) and its CURRENT lens model to the raw camera pixel;
    model        the map point (east, north, -height above ground, relative to the GPS position)
                 seen by the camera at (GPS + d_p) with attitude (IMU x shared mount x per-view d_r),
                 projected by the lens being fitted (focal f, radial k1, k2; the principal point
                 stays the image centre: its offset is a mount error, which mount_cal learns);
    nuisances    per view: position d_p (GPS error, the camera delay along the track, the map's own
                 shift — sigma pos_sigma_m + speed x delay_sigma_s), attitude d_r (IMU noise,
                 att_sigma_deg); shared: the mount (mount_sigma_deg). Gaussian priors on each, so
                 that what the views cannot separate stays near the measured value.
    unknowns     f, k1, k2, with weak priors around the current lens.

Solved by scipy least squares (soft-L1 loss, sparse Jacobian: each view's nuisances touch only
its points). The fit is offered (fit() returns it) only when it explains the points significantly better than
the current lens with the poses fitted: the drop of the squared pixel residuals (each clipped at
3 robust sigmas), in units of the residuals' own robust variance, at least min_chi2_gain — real map
matches are noisy (Isaac Sim 2026-10-26: ~6 px, the map's pixel is ~3 frame pixels at 280 m), so the
noise is measured, not assumed — the pixel RMS lower, the two lenses at least min_shift_px apart
somewhere in the image (else the change does not matter), with enough views (min_views) and points spread over the
image (min_radius_frac of the half-diagonal reached), and the focal is determined to focal_sigma_max.

What it separates only partly: the focal against a height error common to all views (a barometer
or GPS altitude bias). The tilted views (a copter's 10-15 deg, a plane's bank) show the perspective
that tells them apart: in the synthetic test a 5 % height bias moved the focal 1.2 % (tests/
test_lens_selfcal.py) — the rest goes to the per-view heights. Distortion (k1, k2) has no such
ambiguity: a plane seen through a distortion-free lens is a homography, and the bend is measured
directly.

Pure Python + numpy + scipy (no ROS): the day node, the bench and the tests use the same code.
"""
import math
import time
from collections import deque
from typing import Dict, List, Optional, Sequence

import numpy as np

EARTH_R = 6378137.0


def project(model: str, f: float, cx: float, cy: float, k1: float, k2: float, xc: np.ndarray) -> np.ndarray:
    """Pixels (N, 2) of camera-frame points xc (N, 3), z forward."""
    x, y = xc[:, 0] / xc[:, 2], xc[:, 1] / xc[:, 2]
    r2 = x * x + y * y
    if model == "fisheye":
        r = np.sqrt(r2)
        th = np.arctan(r)
        th2 = th * th
        s = np.where(r > 1e-12, th * (1.0 + k1 * th2 + k2 * th2 * th2) / np.maximum(r, 1e-12), 1.0)
    else:
        s = 1.0 + k1 * r2 + k2 * r2 * r2
    return np.stack([f * x * s + cx, f * y * s + cy], axis=1)


def hfov_deg(model: str, f: float, k1: float, k2: float, width: int) -> float:
    """Horizontal field of view (deg) of a lens centred in an image width pixels wide."""
    rd = (width / 2.0) / f
    if model != "fisheye":
        r = rd
        for _ in range(50):                               # invert r (1 + k1 r^2 + k2 r^4) = rd
            g = r * (1.0 + k1 * r * r + k2 * r ** 4) - rd
            dg = 1.0 + 3.0 * k1 * r * r + 5.0 * k2 * r ** 4
            r = r - g / dg if abs(dg) > 1e-9 else r
        return math.degrees(2.0 * math.atan(r))
    th = rd
    for _ in range(50):                                   # invert th (1 + k1 th^2 + k2 th^4) = rd
        g = th * (1.0 + k1 * th * th + k2 * th ** 4) - rd
        dg = 1.0 + 3.0 * k1 * th * th + 5.0 * k2 * th ** 4
        th = th - g / dg if abs(dg) > 1e-9 else th
    return math.degrees(2.0 * th)


def lens_shift_px(lens: dict, model: str, f: float, cx: float, cy: float, k1: float, k2: float) -> float:
    """The largest distance (px) between where the current lens and a new one put the same ray, over a grid
    of the image."""
    w, h = int(lens["size"][0]), int(lens["size"][1])
    g = np.stack(np.meshgrid(np.linspace(0, w - 1, 9), np.linspace(0, h - 1, 7)), -1).reshape(-1, 2)
    old = CameraModelLite(lens)
    ray = old.rays(g)
    new = project(model, f, cx, cy, k1, k2, ray)
    return float(np.max(np.hypot(*(new - g).T)))


class CameraModelLite:
    """Raw pixel -> camera ray of a lens description (frame meta camera_lens)."""

    def __init__(self, lens: dict):
        self.K = np.asarray(lens["K"], float).reshape(3, 3)
        self.D = np.asarray(lens.get("D") or [], float)
        self.model = lens.get("model", "pinhole")

    def rays(self, px: np.ndarray) -> np.ndarray:
        import cv2
        pts = np.asarray(px, np.float64).reshape(-1, 1, 2)
        if self.model == "fisheye":
            d = np.zeros(4)
            d[:min(4, self.D.size)] = self.D[:4]
            und = cv2.fisheye.undistortPoints(pts, self.K, d)
        else:
            und = cv2.undistortPoints(pts, self.K, self.D if self.D.size else None)
        und = und.reshape(-1, 2)
        return np.c_[und, np.ones(len(und))]


def rodrigues(v: np.ndarray) -> np.ndarray:
    th = float(np.linalg.norm(v))
    if th < 1e-12:
        return np.eye(3)
    k = v / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * (K @ K)


def raw_pixels(frame_px: np.ndarray, lens: dict, R_world_cam: Optional[np.ndarray], frame_scale: float = 1.0):
    """The raw camera pixels of points of a published frame: undo the straightening (when the frame
    was straightened with R_world_cam) and re-apply the lens the frame was made with."""
    import cv2
    from navera_common.camera_model import nadir_homography
    K_out = np.asarray(lens["K_out"], float).reshape(3, 3)
    p = np.asarray(frame_px, float).reshape(-1, 2) * float(frame_scale)
    if R_world_cam is not None:                    # (a frame under 0.05 deg of tilt is not warped: ~identity)
        H = nadir_homography(K_out, np.asarray(R_world_cam, float).reshape(3, 3))
        q = np.c_[p, np.ones(len(p))] @ np.linalg.inv(H).T
        p = q[:, :2] / q[:, 2:3]
    ray = np.c_[p, np.ones(len(p))] @ np.linalg.inv(K_out).T                 # normalised, z = 1
    K = np.asarray(lens["K"], float).reshape(3, 3)
    D = np.asarray(lens.get("D") or [], float)
    if lens.get("model") == "fisheye":
        d = np.zeros(4)
        d[:min(4, D.size)] = D[:4]
        out = cv2.fisheye.distortPoints(ray[:, None, :2].astype(np.float64), K, d)
    else:
        out, _ = cv2.projectPoints(ray.astype(np.float64), np.zeros(3), np.zeros(3), K,
                                   D if D.size else None)
    return out.reshape(-1, 2)


def enu_offsets(lat: np.ndarray, lon: np.ndarray, lat0: float, lon0: float) -> np.ndarray:
    """(east, north) metres of points from (lat0, lon0) (local plane: a frame spans < 2 km)."""
    k = math.pi / 180.0 * EARTH_R
    return np.stack([(np.asarray(lon) - lon0) * k * math.cos(math.radians(lat0)), (np.asarray(lat) - lat0) * k],
                    axis=1)


class LensSelfCal:
    """Collect GPS-check views and fit the lens (see the module docstring)."""

    def __init__(self, min_views: int = 12, max_views: int = 40, points_per_view: int = 120,
                 min_points: int = 40, att_sigma_deg: float = 1.0, mount_sigma_deg: float = 5.0,
                 pos_sigma_m: float = 4.0, delay_sigma_s: float = 0.1, height_sigma_frac: float = 0.04,
                 pixel_sigma: float = 1.5, min_chi2_gain: float = 25.0, min_shift_px: float = 1.0,
                 focal_sigma_max: float = 0.05, model_tie: float = 0.03,
                 min_radius_frac: float = 0.6, max_tilt_deg: float = 30.0):
        self.min_views, self.points_per_view, self.min_points = min_views, points_per_view, min_points
        self.att_sigma, self.mount_sigma = math.radians(att_sigma_deg), math.radians(mount_sigma_deg)
        self.pos_sigma_m, self.delay_sigma_s, self.height_sigma_frac = pos_sigma_m, delay_sigma_s, height_sigma_frac
        self.pixel_sigma, self.focal_sigma_max = pixel_sigma, focal_sigma_max
        self.min_chi2_gain, self.min_shift_px, self.model_tie = min_chi2_gain, min_shift_px, model_tie
        self.min_radius_frac, self.max_tilt_deg = min_radius_frac, max_tilt_deg
        self.views = deque(maxlen=max_views)
        self.lens = None                     # the lens of the newest frame (the one in use)
        self.last = None                     # the last fit's summary
        self.rng = np.random.default_rng(0)

    # ── data ──────────────────────────────────────────────────────────────
    def add_view(self, lens: dict, R_world_cam: Optional[Sequence[float]], frame_px, map_latlon,
                 gps_latlon, height_m: float, speed_mps: float = 0.0, frame_scale: float = 1.0,
                 t: Optional[float] = None) -> Optional[str]:
        """One GPS-check match: frame points (published-frame pixels) and their map points (lat, lon).
        Returns why the view is not kept, None when kept."""
        if lens is None or not lens.get("K") or not lens.get("K_out") or not lens.get("size"):
            return "the frame carries no lens description"
        fp = np.asarray(frame_px, float).reshape(-1, 2)
        ml = np.asarray(map_latlon, float).reshape(-1, 2)
        if len(fp) < self.min_points or len(fp) != len(ml):
            return f"{len(fp)} point pairs (min {self.min_points})"
        if not (math.isfinite(height_m) and height_m > 5.0):
            return "no height above ground"
        if R_world_cam is None:
            return "no attitude at the exposure (the frame's heading and tilt are unknown)"
        R = np.asarray(R_world_cam, float).reshape(3, 3)
        tilt = math.degrees(math.acos(max(-1.0, min(1.0, -float((R @ np.array([0.0, 0.0, 1.0]))[2])))))
        if tilt > self.max_tilt_deg:
            return f"tilted {tilt:.0f} deg"
        # a view is kept across lens changes: its points are RAW camera pixels (taken back through the lens
        # the frame was made with), the same whichever lens is applied; the newest lens is the current one
        self.lens = lens
        if len(fp) > self.points_per_view:
            keep = self.rng.choice(len(fp), self.points_per_view, replace=False)
            fp, ml = fp[keep], ml[keep]
        raw = raw_pixels(fp, lens, R, frame_scale)
        en = enu_offsets(ml[:, 0], ml[:, 1], float(gps_latlon[0]), float(gps_latlon[1]))
        ground = np.c_[en, np.full(len(en), -float(height_m))]
        self.views.append(dict(raw=raw, ground=ground, R=R, height=float(height_m),
                               pos_sigma=self.pos_sigma_m + abs(float(speed_mps)) * self.delay_sigma_s,
                               t=time.time() if t is None else float(t)))
        return None

    def ready(self) -> bool:
        return len(self.views) >= self.min_views

    # ── fit ───────────────────────────────────────────────────────────────
    def _residuals(self, x, views, model, cx, cy, f0, k_prior, fit_lens):
        if fit_lens:
            f, k1, k2 = x[0] * f0, x[1], x[2]
            off = 3
        else:
            f, k1, k2 = f0, k_prior[0], k_prior[1]
            off = 0
        mount = x[off:off + 3]
        res = []
        Rm = rodrigues(mount)
        for i, v in enumerate(views):
            dr = x[off + 3 + 6 * i: off + 6 + 6 * i]
            dp = x[off + 6 + 6 * i: off + 9 + 6 * i]
            R = v["R"] @ Rm @ rodrigues(dr)
            C = dp * np.array([v["pos_sigma"], v["pos_sigma"], self.height_sigma_frac * v["height"]])
            xc = (v["ground"] - C) @ R                    # R_world_cam^T (X - C), row form
            ok = xc[:, 2] > 1e-3
            px = project(model, f, cx, cy, k1, k2, np.where(ok[:, None], xc, np.array([0.0, 0.0, 1.0])))
            r = (px - v["raw"]) / self.pixel_sigma
            r[~ok] = 50.0
            res.append(r.ravel())
            res.append(dr / self.att_sigma)
            res.append(dp)                                 # dp is already in sigmas
        res.append(mount / self.mount_sigma)
        if fit_lens:
            res.append(np.array([(x[0] - 1.0) / 0.3, (x[1] - k_prior[0]) / 0.5, (x[2] - k_prior[1]) / 0.5]))
        return np.concatenate(res)

    def _sparsity(self, views, fit_lens):
        from scipy.sparse import lil_matrix
        off = 3 if fit_lens else 0
        n_par = off + 3 + 6 * len(views)
        rows = sum(2 * len(v["raw"]) + 6 for v in views) + 3 + (3 if fit_lens else 0)
        A = lil_matrix((rows, n_par), dtype=int)
        r = 0
        for i, v in enumerate(views):
            m = 2 * len(v["raw"])
            A[r:r + m, :off + 3] = 1
            A[r:r + m, off + 3 + 6 * i: off + 9 + 6 * i] = 1
            A[r + m: r + m + 6, off + 3 + 6 * i: off + 9 + 6 * i] = 1
            r += m + 6
        A[r:r + 3, off:off + 3] = 1
        if fit_lens:
            A[r + 3:r + 6, 0:3] = 1
        return A

    def fit(self) -> Optional[dict]:
        """Fit the lens from the views kept. None: not enough views. Otherwise a summary dict with
        accepted (bool), why, and — accepted — the new lens {model, K, D, size}."""
        if not self.ready():
            return None
        from scipy.optimize import least_squares
        views, lens = list(self.views), self.lens
        model = "fisheye" if lens.get("model") == "fisheye" else "pinhole"
        K = np.asarray(lens["K"], float).reshape(3, 3)
        D = list(np.asarray(lens.get("D") or [], float)) + [0.0, 0.0]
        f0, cx, cy = float(K[0, 0]), float(K[0, 2]), float(K[1, 2])
        k0 = (float(D[0]), float(D[1]))
        w, h = (int(lens["size"][0]), int(lens["size"][1]))
        r_img = max(np.max(np.hypot(v["raw"][:, 0] - cx, v["raw"][:, 1] - cy)) for v in views)
        reach = r_img / math.hypot(w / 2.0, h / 2.0)
        n_pts = sum(len(v["raw"]) for v in views)
        out = dict(views=len(views), points=n_pts, reach=round(reach, 2), model=model, t=time.time())
        # 1) the current lens, the poses fitted
        x0 = np.zeros(3 + 6 * len(views))
        b = least_squares(self._residuals, x0, jac_sparsity=self._sparsity(views, False), loss="soft_l1",
                          f_scale=2.0, args=(views, model, cx, cy, f0, k0, False), max_nfev=60, x_scale="jac")
        # 2) the lens too — for a lens never calibrated (no distortion yet) both models, the better
        # kept: a 100-deg fisheye is not a pinhole with k1, k2, nor a 60-deg lens a fisheye
        # Two that explain the points alike (cost within model_tie): the one with the smaller distortion
        # terms — the matches rarely reach the corners, where a pinhole polynomial mimicking a fisheye
        # bends away (Isaac Sim 2026-10-26: a 92 deg fisheye fitted as a pinhole, 1-2 px off in the centre,
        # 200+ px in the corners; the fisheye model with k ~ 0 is right everywhere)
        candidates = [model] + ([("pinhole" if model == "fisheye" else "fisheye")] if not any(D[:2]) else [])
        fits = []
        for m in candidates:
            x1 = np.r_[1.0, k0[0], k0[1], b.x]
            r = least_squares(self._residuals, x1, jac_sparsity=self._sparsity(views, True), loss="soft_l1",
                              f_scale=2.0, args=(views, m, cx, cy, f0, k0, True), max_nfev=120, x_scale="jac")
            fits.append((r, m))
        best = min(r.cost for r, _ in fits)
        alike = [(r, m) for r, m in fits if r.cost <= best * (1.0 + self.model_tie)]
        a, model = min(alike, key=lambda rm: abs(rm[0].x[1]) + abs(rm[0].x[2]))
        out["model"] = model
        out["model_costs"] = {m: round(float(r.cost), 1) for r, m in fits}
        rms_b, rms_a = self._rms(b.fun, views), self._rms(a.fun, views)
        f, k1, k2 = float(a.x[0] * f0), float(a.x[1]), float(a.x[2])
        try:
            J = a.jac.toarray() if hasattr(a.jac, "toarray") else a.jac
            cov = np.linalg.pinv(J.T @ J)
            s_f = float(math.sqrt(max(cov[0, 0], 0.0)))
            s_k1 = float(math.sqrt(max(cov[1, 1], 0.0)))
        except (np.linalg.LinAlgError, ValueError, MemoryError):
            s_f, s_k1 = float("inf"), float("inf")
        hfov = hfov_deg(model, f, k1, k2, w)
        pb, pa = self._pixel_residuals(b.fun, views), self._pixel_residuals(a.fun, views)
        noise = max(1.4826 * float(np.median(np.abs(pa))), 0.3)          # px, robust, per coordinate
        clip = 3.0 * noise
        gain = float(np.sum(np.minimum(np.abs(pb), clip) ** 2 - np.minimum(np.abs(pa), clip) ** 2)) / noise ** 2
        s_f *= noise / self.pixel_sigma                                  # the covariance assumed pixel_sigma
        shift = lens_shift_px(lens, model, f, cx, cy, k1, k2)
        out.update(rms_before_px=round(rms_b, 2), rms_after_px=round(rms_a, 2), noise_px=round(noise, 2),
                   chi2_gain=round(gain, 1), shift_px=round(shift, 1), focal_px=round(f, 1),
                   focal_change=round(f / f0 - 1.0, 4), focal_sigma=round(s_f, 4), k1=round(k1, 5), k2=round(k2, 5),
                   k1_sigma=round(s_k1, 5), hfov_deg=round(hfov, 2),
                   mount_deg=[round(math.degrees(v), 2) for v in a.x[3:6]])
        why = None
        if not a.success and a.status <= 0:
            why = f"the fit did not converge ({a.message})"
        elif reach < self.min_radius_frac:
            why = f"points reach only {reach:.0%} of the image half-diagonal (min {self.min_radius_frac:.0%})"
        elif not (gain >= self.min_chi2_gain and rms_a < rms_b):
            why = (f"no clear improvement: {rms_a:.2f} px vs {rms_b:.2f} px with the current lens, gain {gain:.0f} "
                   f"(needs >= {self.min_chi2_gain:.0f}; noise {noise:.1f} px)")
        elif shift < self.min_shift_px:
            why = f"the new lens moves no pixel by more than {shift:.1f} px: not worth changing"
        elif s_f > self.focal_sigma_max:
            why = f"focal not determined (sigma {s_f:.1%} > {self.focal_sigma_max:.0%})"
        elif not (15.0 < hfov < 175.0) or (model == "pinhole" and not self._monotonic(k1, k2, w, h, f)):
            why = f"implausible lens (field of view {hfov:.0f} deg, k1 {k1:.3f}, k2 {k2:.3f})"
        out["accepted"], out["why"] = why is None, why or "fitted"
        if why is None:
            Kn = [[f, 0.0, cx], [0.0, f, cy], [0.0, 0.0, 1.0]]
            Dn = [k1, k2, 0.0, 0.0] + ([] if model == "fisheye" else [0.0])
            out["lens"] = dict(model=model, camera_matrix=[v for row in Kn for v in row], distortion=Dn,
                               image_width=w, image_height=h)
        self.last = out
        return out

    @staticmethod
    def _pixel_residuals(fun: np.ndarray, views) -> np.ndarray:
        r, i = [], 0
        for v in views:
            m = 2 * len(v["raw"])
            r.append(fun[i:i + m])
            i += m + 6
        return np.concatenate(r) * 1.0 if r else np.zeros(0)

    def _rms(self, fun: np.ndarray, views) -> float:
        n = sum(2 * len(v["raw"]) for v in views)
        r, i = [], 0
        for v in views:
            m = 2 * len(v["raw"])
            r.append(fun[i:i + m])
            i += m + 6
        r = np.concatenate(r) * self.pixel_sigma
        return float(np.sqrt(np.mean(r * r))) if n else float("nan")

    @staticmethod
    def _monotonic(k1: float, k2: float, w: int, h: int, f: float) -> bool:
        """A pinhole radial model must keep growing out to the image corner (else it folds)."""
        rmax = math.hypot(w / 2.0, h / 2.0) / f * 1.2
        r = np.linspace(0.0, rmax, 200)
        rd = r * (1.0 + k1 * r * r + k2 * r ** 4)
        return bool(np.all(np.diff(rd) > 0))

    def state(self) -> Dict:
        return dict(views=len(self.views), min_views=self.min_views, last=self.last)


def calibration_dict(lens: dict, summary: dict, camera: str = "") -> dict:
    """The calibration file content (navera_tools/calibrate_camera.py's format) of a fitted lens."""
    return dict(lens, source="in-flight self-calibration (map + GPS)", camera=camera,
                rms_px=summary.get("rms_after_px"), views=summary.get("views"), points=summary.get("points"),
                focal_sigma=summary.get("focal_sigma"), date=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


def lens_of_meta(meta: dict) -> Optional[dict]:
    """The lens description live_camera puts in each frame's meta (None for older frames)."""
    lens = meta.get("camera_lens")
    return lens if isinstance(lens, dict) and lens.get("K") and lens.get("K_out") else None


def list_pairs(res: dict) -> Optional[List[np.ndarray]]:
    """(frame points, map points (lat, lon)) of a match result (local / learned matcher), or None."""
    pairs = res.get("_lens_pairs")
    if not pairs:
        return None
    fp, mp, z = np.asarray(pairs[0], float), np.asarray(pairs[1], float), int(pairs[2])
    n = 2.0 ** z                                          # global tile pixels (256 a tile) at zoom z
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * (mp[:, 1] / 256.0) / n))))
    lon = (mp[:, 0] / 256.0) / n * 360.0 - 180.0
    return [fp, np.stack([lat, lon], axis=1)]
