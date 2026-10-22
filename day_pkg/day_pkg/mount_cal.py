"""Camera boresight (mount roll/pitch) error of the day camera, learned in flight against GPS.

A camera fitted a few degrees off (or an IMU-to-camera misalignment) puts every day fix
height x tan(error) away from the vehicle, in a direction fixed to the camera: Isaac Sim closed
loop 2026-10-21, mount error 3/-2.5 deg at 250 m: 14 m median at the exposure instead of 6-7 m,
and the default 1.5/-1.0 deg sim mount at 600 m: 13 m — while the stated sigma had no term for it
(16 outputs beyond 3 sigma at 600 m). The map bias (vision_nav.VisionNavigator.bias) removes on
purpose only offsets that do NOT turn with the heading; this is the other half.

While GPS is trusted every GPS-check match gives err = GPS(at the frame instant) - vision (east,
north m). One least-squares fit per position kind ("frame centre", "camera pose": the matcher's
two ways to place a frame are not affected alike) explains them as
    err = h * (m_f * top + m_r * right)  +  b  +  d * v
    h: height above ground, top/right: the image's top and right on the ground (frame heading),
    m_f, m_r: tan of the boresight error along them (what is learned and applied),
    b: a map shift (east, north; the map bias' job, a nuisance here), d: a residual camera delay
    (s) times the ground velocity v (the latency calibrator's job, a nuisance here),
with Gaussian priors on every unknown (m: prior_deg, b: bias_prior_m, d: the delay's
uncertainty), so that a flight on one heading at one speed splits what it cannot separate by
the priors and says so in the posterior sigma. Outliers beyond 3.5 robust sigmas are dropped.

GPS may be trusted only for the take-off and climb, then lost for hours: too few checks to learn
anything in flight. The main source is therefore a PERSISTED calibration (set_prior / load: an
earlier flight's fit, or a ground/bench measurement) used as the prior mean and sigma of the fit —
applied from the first frame, refined by whatever GPS checks the flight gives. Without one, the
prior is zero with prior_deg, and that sigma stays in the stated accuracy for the whole flight.
export() gives what to persist (only samples older than the spoof rollback window).

Pure Python + numpy (no ROS): the day node and the bench use the same code.
"""
import math
from collections import deque
from typing import Dict, Optional, Tuple

import numpy as np

KINDS = ("frame centre", "camera pose")


def axes(heading_deg: float) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """(top, right) unit vectors (east, north) of a frame whose top points to heading_deg."""
    a = math.radians(heading_deg)
    return (math.sin(a), math.cos(a)), (math.cos(a), -math.sin(a))


class MountCalibration:
    """Boresight error of the camera, per position kind, from GPS-check matches."""

    def __init__(self, prior_deg: float = 2.0, min_samples: int = 12, window: int = 200,
                 bias_prior_m: float = 15.0, floor_deg: float = 0.25, max_deg: float = 10.0):
        self.prior = math.tan(math.radians(float(prior_deg)))
        self.prior_deg = float(prior_deg)
        self.min_samples = int(min_samples)
        self.bias_prior_m = float(bias_prior_m)
        self.floor_deg = float(floor_deg)
        self.max = math.tan(math.radians(float(max_deg)))
        self._s: Dict[str, deque] = {k: deque(maxlen=int(window)) for k in KINDS}
        self._prior: Dict[str, Tuple[float, float, float]] = {}   # kind: (m_f, m_r, sigma) tan, persisted
        self.prior_source = None
        self._cache = {}

    # ── a persisted calibration ──────────────────────────────────────────
    def set_prior(self, kind: str, top_deg: float, right_deg: float, sigma_deg: float) -> bool:
        """A calibration known before this flight (earlier flight, ground or bench): the mean and
        1-sigma of the boresight error along the frame's top and right (deg)."""
        try:
            v = [float(top_deg), float(right_deg), float(sigma_deg)]
        except (TypeError, ValueError):
            return False
        if kind not in self._s or not all(math.isfinite(x) for x in v) or v[2] <= 0 or \
                max(abs(v[0]), abs(v[1])) > math.degrees(math.atan(self.max)):
            return False
        t = lambda d: math.tan(math.radians(d))                       # noqa: E731
        self._prior[kind] = (t(v[0]), t(v[1]), t(min(v[2], self.prior_deg)))
        self._cache.clear()
        return True

    def load(self, data: Optional[dict], min_sigma_deg: float = 0.5) -> int:
        """Priors from a persisted dict ({kind: {top_deg, right_deg, sigma_deg}}, as export() gives);
        each sigma at least min_sigma_deg (the camera may have moved since). Returns how many."""
        n = 0
        for k in KINDS:
            d = (data or {}).get(k)
            if isinstance(d, dict) and self.set_prior(k, d.get("top_deg"), d.get("right_deg"),
                                                      max(float(d.get("sigma_deg") or 0.0), float(min_sigma_deg))):
                n += 1
        if n and data:
            self.prior_source = data.get("source")
        return n

    def export(self, before_t: Optional[float] = None, delay_sigma_s: float = 1.0) -> dict:
        """What to persist: per kind with at least min_samples (taken before before_t), the fit
        (persisted prior included) as {top_deg, right_deg, sigma_deg, samples}."""
        out = {}
        for k in KINDS:
            s = [x for x in self._s[k] if before_t is None or x[0] < before_t]
            if len(s) < self.min_samples:
                continue
            f = self._solve(np.array(s, float), max(float(delay_sigma_s), 1e-3), k)
            out[k] = {"top_deg": round(math.degrees(math.atan(f["m_f"])), 3),
                      "right_deg": round(math.degrees(math.atan(f["m_r"])), 3),
                      "sigma_deg": round(math.degrees(math.atan(f["sigma"])), 3), "samples": f["n"]}
        return out

    # ── samples ──────────────────────────────────────────────────────────
    def add(self, kind: str, err_en: Tuple[float, float], heading_deg: Optional[float], height_m: Optional[float],
            t: Optional[float] = None, vel_en: Optional[Tuple[float, float]] = None) -> bool:
        """One GPS-check match: err_en = GPS at the frame's instant minus the vision position (m),
        the frame heading (its top), the height above ground, when (s), the ground velocity."""
        if kind not in self._s or heading_deg is None or height_m is None:
            return False
        try:
            e, n, h, hd = float(err_en[0]), float(err_en[1]), float(height_m), float(heading_deg)
        except (TypeError, ValueError):
            return False
        if not (all(math.isfinite(x) for x in (e, n, h, hd)) and h > 5.0):
            return False
        v = (0.0, 0.0)
        if vel_en is not None and all(math.isfinite(float(x)) for x in vel_en):
            v = (float(vel_en[0]), float(vel_en[1]))
        self._s[kind].append((float("-inf") if t is None else float(t), e, n, hd, h, v[0], v[1]))
        self._cache.clear()
        return True

    def rollback(self, since_t: float) -> int:
        """Forget the samples taken at or after since_t (a slowly spoofed GPS trusted then)."""
        n = 0
        for d in self._s.values():
            while d and d[-1][0] >= since_t:
                d.pop()
                n += 1
        if n:
            self._cache.clear()
        return n

    def samples(self, kind: str) -> int:
        return len(self._s.get(kind, ()))

    # ── the fit ──────────────────────────────────────────────────────────
    def fit(self, kind: str, delay_sigma_s: float = 1.0) -> Optional[dict]:
        """{m_f, m_r (tan), sigma (tan, the larger axis), b (m), d (s), noise_m, n} or None while
        fewer than min_samples."""
        key = (kind, round(float(delay_sigma_s), 3))
        if key in self._cache:
            return self._cache[key]
        s = list(self._s.get(kind, ()))
        out = None
        if len(s) >= self.min_samples:
            out = self._solve(np.array(s, float), max(float(delay_sigma_s), 1e-3), kind)
        elif kind in self._prior:                             # the persisted calibration alone
            m0f, m0r, sig = self._prior[kind]
            out = dict(m_f=m0f, m_r=m0r, sigma=sig, b=(0.0, 0.0), d=0.0, noise_m=None, n=0)
        self._cache[key] = out
        return out

    def _solve(self, s: np.ndarray, delay_sigma_s: float, kind: str) -> dict:
        hd = np.radians(s[:, 3])
        h, ve, vn = s[:, 4], s[:, 5], s[:, 6]
        te, tn, re, rn = np.sin(hd), np.cos(hd), np.cos(hd), -np.sin(hd)
        n = len(s)
        A = np.zeros((2 * n, 5))
        A[0::2, 0], A[1::2, 0] = h * te, h * tn               # m_f
        A[0::2, 1], A[1::2, 1] = h * re, h * rn               # m_r
        A[0::2, 2], A[1::2, 3] = 1.0, 1.0                     # b east, b north
        A[0::2, 4], A[1::2, 4] = ve, vn                       # residual delay
        y = np.empty(2 * n)
        y[0::2], y[1::2] = s[:, 1], s[:, 2]
        m0f, m0r, msig = self._prior.get(kind, (0.0, 0.0, self.prior))
        x0 = np.array([m0f, m0r, 0.0, 0.0, 0.0])
        prior_inv = np.diag([1.0 / msig ** 2] * 2 + [1.0 / self.bias_prior_m ** 2] * 2
                            + [1.0 / delay_sigma_s ** 2])
        ok = np.ones(n, bool)                                 # samples kept (both axes together)
        noise = 5.0                                           # per-axis noise (m), from the residuals
        for _ in range(3):
            keep = np.repeat(ok, 2)
            P = np.linalg.inv(A[keep].T @ A[keep] / noise ** 2 + prior_inv)
            x = P @ (A[keep].T @ y[keep] / noise ** 2 + prior_inv @ x0)
            r = y - A @ x
            rs = np.hypot(r[0::2], r[1::2])
            noise = max(1.0, float(np.median(rs[ok])) / 1.1774)   # median radius of a 2-D Gaussian
            new = rs <= 3.5 * noise
            if new.sum() < self.min_samples:
                break
            ok = new
        keep = np.repeat(ok, 2)
        P = np.linalg.inv(A[keep].T @ A[keep] / noise ** 2 + prior_inv)
        x = P @ (A[keep].T @ y[keep] / noise ** 2 + prior_inv @ x0)
        mf, mr = (float(np.clip(v, -self.max, self.max)) for v in x[:2])
        sig = math.sqrt(max(float(np.max(np.linalg.eigvalsh(P[:2, :2]))), 0.0))
        return dict(m_f=mf, m_r=mr, sigma=max(sig, math.tan(math.radians(self.floor_deg))),
                    b=(float(x[2]), float(x[3])), d=float(x[4]), noise_m=noise, n=int(keep.sum() // 2))

    # ── use ──────────────────────────────────────────────────────────────
    def correction(self, kind: str, heading_deg: Optional[float], height_m: Optional[float],
                   delay_sigma_s: float = 1.0) -> Tuple[float, float]:
        """(east, north) metres to ADD to a vision position of this kind (0, 0 when not known)."""
        f = self.fit(kind, delay_sigma_s)
        if f is None or heading_deg is None or height_m is None or not math.isfinite(float(height_m)):
            return 0.0, 0.0
        top, right = axes(float(heading_deg))
        h = float(height_m)
        return (h * (f["m_f"] * top[0] + f["m_r"] * right[0]), h * (f["m_f"] * top[1] + f["m_r"] * right[1]))

    def sigma_deg(self, kind: str, delay_sigma_s: float = 1.0) -> float:
        """1-sigma of the boresight error left (deg): prior_deg while nothing is known."""
        f = self.fit(kind, delay_sigma_s)
        if f is None:
            return self.prior_deg
        return min(self.prior_deg, math.degrees(math.atan(f["sigma"])))

    def state(self, delay_sigma_s: float = 1.0) -> dict:
        out = {}
        for k in KINDS:
            f = self.fit(k, delay_sigma_s)
            out[k] = {"samples": self.samples(k), "calibrated": f is not None,
                      "persisted": k in self._prior, "sigma_deg": round(self.sigma_deg(k, delay_sigma_s), 2)}
            if f is not None:
                out[k].update(top_deg=round(math.degrees(math.atan(f["m_f"])), 2),
                              right_deg=round(math.degrees(math.atan(f["m_r"])), 2),
                              map_shift_m=[round(v, 1) for v in f["b"]], delay_s=round(f["d"], 2),
                              noise_m=None if f["noise_m"] is None else round(f["noise_m"], 1))
        return out
