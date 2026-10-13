"""navera_lite/estimate.py — the position contract: one position from ONE source (an Estimate), and the
checks a judge makes before it trusts one (is it a covariance, what σ does it state, is it fresh).
Part of NAVERA Lite, the course's teaching stack (given in mission 09, completed in mission 12).
Written for the course; it is not NAVERA code.

Conventions (courses/_lib/CONVENTIONS.md §5): the covariance is 9 numbers, ENU, row-major, m², as in
sensor_msgs/NavSatFix; its horizontal block is a = σE² (index 0), b = cov(E, N) (indices 1 and 3),
c = σN² (index 4). Times are seconds; `stamp_s` is the instant the position was MEASURED.
"""
import math
from dataclasses import dataclass, field

from navera_lite.geo import is_finite_latlon

# @part 09
SOURCES = ("gps", "day", "night", "celestial")      # the witnesses, in priority order (GPS first)
# @part 09
TIMEOUT_KEY = {"gps": "gps_timeout_s", "day": "day_timeout_s", "night": "night_timeout_s",
               "celestial": "celestial_timeout_s"}   # the setting that says when each source is stale
# @part 09
COV_UNKNOWN, COV_APPROXIMATED, COV_DIAGONAL_KNOWN, COV_KNOWN = 0, 1, 2, 3   # NavSatFix covariance types
# @part 09
STATED_TYPES = (COV_APPROXIMATED, COV_DIAGONAL_KNOWN, COV_KNOWN)          # the types that state an accuracy


# @part 09
@dataclass
class Estimate:
    """One position from one source, as the judge receives it.

    source: "gps", "day", "night" or "celestial" · lat, lon: degrees · stamp_s: when it was measured (s)
    cov: 9 numbers, ENU, row-major, m² · cov_type: one of the COV_* types (COV_UNKNOWN: the numbers mean
    nothing) · alt_m: metres, nan if unknown · valid: False when the source is alive but has no position
    · reason: why not, in words · t_recv_s: when the judge received it (None before).
    Example: Estimate("gps", 35.8256, 10.6084, 100.0, cov=(9.0, 0, 0, 0, 9.0, 0, 0, 0, 36.0), cov_type=1)
    """
    source: str
    lat: float
    lon: float
    stamp_s: float
    cov: tuple = field(default=(0.0,) * 9)
    cov_type: int = COV_UNKNOWN
    alt_m: float = math.nan
    valid: bool = True
    reason: str = ""
    t_recv_s: float | None = None


# @part 09
def horizontal(cov9):
    """(a, b, c) — the horizontal block of a 9-number covariance (CONVENTIONS §5): σE², cov(E, N), σN².

    Example: horizontal([9.0, 1.0, 0, 1.0, 4.0, 0, 0, 0, 36.0]) → (9.0, 1.0, 4.0)
    """
    return float(cov9[0]), float(cov9[1]), float(cov9[4])


# @part 09
def classify(sigma_m, cfg):
    """The state a winning position gets from the σ it states (lesson 1's table):
    "FIX" if sigma_m is a number ≤ cfg["fix_max_sigma_m"], else "DEGRADED"; with a short reason.

    sigma_m: metres, or None when the source states no usable accuracy. Returns (state, reason).
    Example: classify(3.0, {"fix_max_sigma_m": 25.0}) → ("FIX", "σ 3.0 m");
             classify(None, {"fix_max_sigma_m": 25.0}) → ("DEGRADED", "σ unknown")
    """
    limit = float(cfg["fix_max_sigma_m"])
    if sigma_m is None or not math.isfinite(sigma_m):
        return "DEGRADED", "σ unknown"
    if sigma_m > limit:
        return "DEGRADED", f"σ {sigma_m:.1f} m > {limit:.1f} m"
    return "FIX", f"σ {sigma_m:.1f} m"


# @part 12
def age_s(est, now_s):
    """How old the measurement is at now_s, in seconds (negative: stamped in the future).

    Example: age_s(Estimate("gps", 35.8, 10.6, 100.0), 103.4) → 3.4 (to rounding)
    """
    return now_s - est.stamp_s


# @part 12 todo 1
def is_covariance(cov9, tol=1e-9):
    """Can these 9 numbers be a covariance (lesson §2)? Returns (ok, reason), with the first rule broken:
      not 9 numbers                     → (False, "not 9 numbers")
      one of them is nan or infinite    → (False, "not finite")
      cov9[1] != cov9[3] (beyond tol)   → (False, "not symmetric")
      a < 0, c < 0 or cov9[8] < 0       → (False, "negative variance")
      a·c − b² < −tol                   → (False, "not positive semi-definite")
      otherwise                         → (True, "ok")
    The vertical entries other than cov9[8] are not checked.
    Example: is_covariance([25.0, 30.0, 0, 30.0, 16.0, 0, 0, 0, 1.0]) → (False, "not positive semi-definite")
             (25 × 16 − 30² = −500: a correlation of 1.5, impossible)
    """
    try:
        values = [float(v) for v in cov9]
    except (TypeError, ValueError):
        return False, "not 9 numbers"
    if len(values) != 9:
        return False, "not 9 numbers"
    if not all(math.isfinite(v) for v in values):
        return False, "not finite"
    a, b, c = values[0], values[1], values[4]
    if abs(values[1] - values[3]) > tol:
        return False, "not symmetric"
    if a < 0 or c < 0 or values[8] < 0:
        return False, "negative variance"
    if a * c - b * b < -tol:
        return False, "not positive semi-definite"
    return True, "ok"


# @part 12 todo 2
def stated_sigma(est, cfg):
    """The one accuracy number the source states, in metres: √max(a, c) (CONVENTIONS §5) — or None when
    it states none: cov_type not in STATED_TYPES (COV_UNKNOWN or an undefined number), the 9 numbers are
    not a covariance (is_covariance), or σ is below cfg["min_stated_sigma_m"] (an all-zero covariance
    states nothing: nobody knows a position to the millimetre).
    Example: stated_sigma(Estimate("gps", 35.8, 10.6, 0.0, cov=(9.0, 0, 0, 0, 4.0, 0, 0, 0, 36.0),
             cov_type=COV_DIAGONAL_KNOWN), {"min_stated_sigma_m": 0.01}) → 3.0
    """
    if est.cov_type not in STATED_TYPES:
        return None
    ok, _ = is_covariance(est.cov)
    if not ok:
        return None
    a, _, c = horizontal(est.cov)
    sigma = math.sqrt(max(a, c))
    if sigma < float(cfg["min_stated_sigma_m"]):
        return None
    return sigma


# @part 12 todo 3
def staleness_m(speed_mps, age_s):
    """How far (m) a vehicle moving at speed_mps has gone since a position age_s seconds old was
    measured: the error of using that position NOW (lesson §3). Raises ValueError if speed_mps or age_s
    is negative.
    Example: staleness_m(40.0, 2.5) → 100.0   (a plane at 40 m/s, a vision fix 2.5 s old)
    """
    if speed_mps < 0:
        raise ValueError(f"speed_mps must be >= 0, got {speed_mps}")
    if age_s < 0:
        raise ValueError(f"age_s must be >= 0, got {age_s}")
    return float(speed_mps) * float(age_s)


# @part 12 todo 4
def eligible(est, now_s, cfg):
    """May the judge use this estimate at now_s? Returns (ok, reason), with the first rule broken:
      est.valid is False                              → (False, "no position")
      lat, lon exactly (0, 0)                         → (False, "null island")
      any other position is_finite_latlon refuses     → (False, "bad position")
      cov_type in STATED_TYPES but not a covariance   → (False, "not a covariance")
      stamped more than future_tolerance_s ahead      → (False, "from the future")
      source not in TIMEOUT_KEY                       → (False, "unknown source")
      age > the source's timeout                      → (False, "stale (3.4 s > 3.0 s)")   (one decimal)
      otherwise                                       → (True, "eligible")
    cfg: the settings (DEFAULTS keys). A position with an unknown accuracy is still eligible: classify()
    makes it DEGRADED.
    Example: eligible(Estimate("gps", 35.8, 10.6, 100.0), 103.4, DEFAULTS) → (False, "stale (3.4 s > 3.0 s)")
    """
    if not est.valid:
        return False, "no position"
    if est.lat == 0 and est.lon == 0:
        return False, "null island"
    if not is_finite_latlon(est.lat, est.lon):
        return False, "bad position"
    if est.cov_type in STATED_TYPES and not is_covariance(est.cov)[0]:
        return False, "not a covariance"
    age = age_s(est, now_s)
    if age < -float(cfg["future_tolerance_s"]):
        return False, "from the future"
    if est.source not in TIMEOUT_KEY:
        return False, "unknown source"
    timeout = float(cfg[TIMEOUT_KEY[est.source]])
    if age > timeout:
        return False, f"stale ({age:.1f} s > {timeout:.1f} s)"
    return True, "eligible"
