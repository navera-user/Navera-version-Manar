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
