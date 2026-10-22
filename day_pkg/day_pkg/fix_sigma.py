"""Stated accuracy (1 sigma, metres) of a day-vision local match, from its parts.

The matcher's own sigma (local_matcher.fix_sigma_m: inlier class x map pixel) covers the
matching error; a fix is also off by the vehicle's travel during the frame-time error and by
the attitude error the straightening leaves (about half of height x tan(attitude error)).
They are independent and add in quadrature; a floor keeps a strong match from claiming
better than the bench showed.

Measured on the real camera (screen bench 2026-10-19, 76 runs, 10 481 matched frames, 18
conditions, 20 and 60 m/s, 1500 m): radial errors within 1/2/3 sigma
  fixed 30 m (before):                         0.984 / 0.996 / 0.999  (median sigma 30 m)
  this function (floor 5 m, 0.05 s, 0.5 deg):  0.954 / 0.983 / 0.992  (median sigma 10.6 m)
(2-D Gaussian: 0.39 / 0.86 / 0.989); every inlier class >= 0.987 within 3 sigma.
"""
import math
from typing import Optional


def day_fix_sigma_m(match_sigma_m: Optional[float], floor_m: float = 5.0,
                    speed_mps: Optional[float] = None, delay_sigma_s: float = 0.05,
                    height_m: Optional[float] = None, attitude_sigma_deg: float = 0.5) -> float:
    """1-sigma horizontal error (m) of a local match: max(matcher sigma, floor), the travel during
    the frame-time error and the residual attitude error, in quadrature."""
    s = max(float(match_sigma_m or 0.0), float(floor_m))
    t = abs(float(speed_mps)) * float(delay_sigma_s) if speed_mps is not None else 0.0
    a = (0.5 * abs(float(height_m)) * math.tan(math.radians(float(attitude_sigma_deg)))
         if height_m is not None and math.isfinite(float(height_m)) else 0.0)
    return math.sqrt(s * s + t * t + a * a)


# For an honest 2-D Gaussian sigma, 95 % of radial errors lie within 2.448 sigma.
R95_2D = 2.4477


def _quantile(v, p):
    v = sorted(v)
    pos = p * (len(v) - 1)
    lo = int(math.floor(pos))
    return v[lo] + (v[min(lo + 1, len(v) - 1)] - v[lo]) * (pos - lo)


class SigmaCalibration:
    """In-flight check of the stated day sigma against a trusted GPS (no test flight needed).

    While GPS is trusted, every vision fix taken next to it (the GPS check frames, map bias
    removed) gives its error |vision - GPS| (the GPS's own error is not removed: stricter).
    Once min_samples are in, the published sigma is
        hypot(model x f, b),  f = max(1, q95(err / model) / 2.448),  b = q95(err) / 2.448
    f scales a model that is optimistic everywhere; b is this flight's own error level, which
    on real drone imagery does not shrink with the inlier count as the model assumes.
    Measured (bench/replay_sigma_cal.py, calibration on the GPS part, scored after the loss):
      UAV-VisLoc flight 03 (real drone images, 466 m, 687 fixes): model alone 0.48 within
        3 sigma (median 5.5 m); fixed 30 m 1.0 (30 m); this 0.999 (median 19 m);
      real camera screen campaign (72 runs): model 0.991 (10.5 m); this 0.999 (10.8 m).
    Never calibrated (GPS denied from take-off): at least floor_no_cal_m. The newest window
    samples count (terrain and light change along a flight).

    Kept across flights (F39, like the camera delay): a calibration measured with this camera
    is stored (export, sigma_store) and starts the next flight as a PRIOR (set_prior) — used
    only while this flight has fewer than min_samples of its own, inflated (terrain, light and
    height change between flights) and never below prior_floor_m; dropped as soon as this
    flight's own samples contradict it (2 of its first samples beyond 3 prior sigmas).
    Isaac endurance 2026-10-22: GPS lost 12 s after reaching altitude, no own calibration, the
    30 m floor stated for ~14 m real errors.
    """

    def __init__(self, floor_no_cal_m: float = 30.0, min_samples: int = 15, window: int = 200,
                 max_factor: float = 20.0):
        from collections import deque
        self.floor_no_cal_m = float(floor_no_cal_m)
        self.min_samples = int(min_samples)
        self.max_factor = float(max_factor)
        self._s = deque(maxlen=int(window))           # (error m, model sigma m)
        self._t = deque(maxlen=int(window))           # when each sample was taken (s)
        self.prior = None                             # (f, b, inflation, floor m, source) from an earlier flight
        self.prior_dropped = None                     # why a prior was dropped

    def set_prior(self, f: float, b: float, source: str = "stored", inflation: float = 1.3,
                  floor_m: float = 10.0) -> bool:
        """Start from an earlier flight's calibration (terms f, b): used while this flight has
        fewer than min_samples, scaled by inflation, at least floor_m. False if not plausible."""
        try:
            f, b = float(f), float(b)
        except (TypeError, ValueError):
            return False
        if not (math.isfinite(f) and math.isfinite(b) and 1.0 <= f <= self.max_factor and 0.0 <= b < 1000.0):
            return False
        self.prior = (f, b, max(1.0, float(inflation)), float(floor_m), source)
        self.prior_dropped = None
        return True

    def add(self, err_m: float, stated_sigma_m: float, t: Optional[float] = None) -> None:
        """One vision fix compared with the trusted GPS at the same instant (t: when)."""
        if stated_sigma_m and stated_sigma_m > 0 and math.isfinite(err_m):
            self._s.append((float(err_m), float(stated_sigma_m)))
            self._t.append(float("-inf") if t is None else float(t))
            self._check_prior()

    def _check_prior(self, k_sigma: float = 3.0, max_beyond: int = 2) -> None:
        """Drop the prior when this flight's own samples contradict it: max_beyond of them beyond
        k_sigma times the sigma the prior states (another camera setting, terrain or height)."""
        if self.prior is None or len(self._s) >= self.min_samples:
            return
        beyond = sum(1 for e, s in self._s if e > k_sigma * self._prior_sigma(s))
        if beyond >= max_beyond:
            self.prior_dropped = (f"{beyond} of {len(self._s)} samples beyond {k_sigma:g} sigma of the "
                                  f"{self.prior[4]} calibration")
            self.prior = None

    def _prior_sigma(self, stated_sigma_m: float) -> float:
        f, b, infl, floor, _ = self.prior
        return max(math.hypot(float(stated_sigma_m) * f, b) * infl, floor)

    def rollback(self, since_t: float) -> int:
        """Forget the samples taken at or after since_t; returns how many.

        A slowly spoofed GPS is still trusted for a while before it is refused: the
        samples of that time compare vision with a drifting GPS and would teach the
        calibration to accept the drift."""
        n = 0
        while self._t and self._t[-1] >= since_t:
            self._t.pop()
            self._s.pop()
            n += 1
        return n

    @property
    def samples(self) -> int:
        return len(self._s)

    def terms(self, until_t: Optional[float] = None) -> Optional[tuple]:
        """(f, b m) of this flight (from its samples taken at or before until_t), or None while
        there are fewer than min_samples."""
        s = list(self._s) if until_t is None else [x for x, t in zip(self._s, self._t) if t <= until_t]
        if len(s) < self.min_samples:
            return None
        f = _quantile([e / m for e, m in s], 0.95) / R95_2D
        b = _quantile([e for e, _ in s], 0.95) / R95_2D
        return min(max(1.0, f), self.max_factor), b

    def export(self, until_t: Optional[float] = None) -> Optional[dict]:
        """This flight's calibration to keep for the next flight (samples up to until_t: the ones a
        late spoof refusal could still roll back are left out), or None."""
        t = self.terms(until_t)
        if t is None:
            return None
        n = len(self._s) if until_t is None else sum(1 for x in self._t if x <= until_t)
        return {"f": round(t[0], 4), "b": round(t[1], 2), "samples": n}

    def apply(self, stated_sigma_m: float) -> float:
        """The sigma to publish for a fix whose model sigma is stated_sigma_m."""
        t = self.terms()
        if t is None:
            if self.prior is not None:
                return self._prior_sigma(stated_sigma_m)
            return max(float(stated_sigma_m), self.floor_no_cal_m)
        return math.hypot(float(stated_sigma_m) * t[0], t[1])

    def state(self) -> dict:
        t = self.terms()
        p = self.prior
        return {"samples": len(self._s), "calibrated": t is not None,
                "factor": None if t is None else round(t[0], 3), "flight_floor_m": None if t is None else round(t[1], 1),
                "floor_no_cal_m": self.floor_no_cal_m,
                "prior": None if p is None else {"f": round(p[0], 3), "b": round(p[1], 1), "inflation": p[2],
                                                 "floor_m": p[3], "source": p[4], "in_use": t is None},
                "prior_dropped": self.prior_dropped}


# ── kept across flights (F39): one calibration per camera, in the NAVERA state dir ──
def _store_name(key: str) -> str:
    import re
    return "sigma_cal_" + re.sub(r"[^A-Za-z0-9_.-]", "_", key)[:80]


def save_stored(key: str, terms: Optional[dict], directory: Optional[str] = None) -> bool:
    """Keep this camera's calibration ({f, b, samples}; None forgets it) for the next flight."""
    from navera_common import state_store
    return state_store.save(_store_name(key), {"key": key, "terms": terms}, directory)


def load_stored(key: str, max_age_s: float, directory: Optional[str] = None) -> Optional[dict]:
    """{f, b, samples, saved_at} kept for this camera if younger than max_age_s, else None."""
    from navera_common import state_store
    d = state_store.load(_store_name(key), max_age_s, directory)
    if d is None or d.get("key") != key or not isinstance(d.get("terms"), dict):
        return None
    try:
        out = {"f": float(d["terms"]["f"]), "b": float(d["terms"]["b"]),
               "samples": int(d["terms"].get("samples", 0)), "saved_at": float(d["saved_at"])}
    except (KeyError, TypeError, ValueError):
        return None
    return out if math.isfinite(out["f"]) and math.isfinite(out["b"]) else None
