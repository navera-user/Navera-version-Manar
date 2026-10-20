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
    """

    def __init__(self, floor_no_cal_m: float = 30.0, min_samples: int = 15, window: int = 200,
                 max_factor: float = 20.0):
        from collections import deque
        self.floor_no_cal_m = float(floor_no_cal_m)
        self.min_samples = int(min_samples)
        self.max_factor = float(max_factor)
        self._s = deque(maxlen=int(window))           # (error m, model sigma m)

    def add(self, err_m: float, stated_sigma_m: float) -> None:
        """One vision fix compared with the trusted GPS at the same instant."""
        if stated_sigma_m and stated_sigma_m > 0 and math.isfinite(err_m):
            self._s.append((float(err_m), float(stated_sigma_m)))

    @property
    def samples(self) -> int:
        return len(self._s)

    def terms(self) -> Optional[tuple]:
        """(f, b m) of this flight, or None while not calibrated."""
        if len(self._s) < self.min_samples:
            return None
        f = _quantile([e / s for e, s in self._s], 0.95) / R95_2D
        b = _quantile([e for e, _ in self._s], 0.95) / R95_2D
        return min(max(1.0, f), self.max_factor), b

    def apply(self, stated_sigma_m: float) -> float:
        """The sigma to publish for a fix whose model sigma is stated_sigma_m."""
        t = self.terms()
        if t is None:
            return max(float(stated_sigma_m), self.floor_no_cal_m)
        return math.hypot(float(stated_sigma_m) * t[0], t[1])

    def state(self) -> dict:
        t = self.terms()
        return {"samples": len(self._s), "calibrated": t is not None,
                "factor": None if t is None else round(t[0], 3), "flight_floor_m": None if t is None else round(t[1], 1),
                "floor_no_cal_m": self.floor_no_cal_m}
