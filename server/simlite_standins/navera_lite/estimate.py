"""Sim Lite stand-in: the position contract as mission 09 gives it (no checks of mission 12). Written for the course.

Sent to the browser instead of the course's finished estimate.py while mission 12 is not passed."""
import math
from dataclasses import dataclass, field

SOURCES = ("gps", "day", "night", "celestial")
TIMEOUT_KEY = {"gps": "gps_timeout_s", "day": "day_timeout_s", "night": "night_timeout_s",
               "celestial": "celestial_timeout_s"}
COV_UNKNOWN, COV_APPROXIMATED, COV_DIAGONAL_KNOWN, COV_KNOWN = 0, 1, 2, 3
STATED_TYPES = (COV_APPROXIMATED, COV_DIAGONAL_KNOWN, COV_KNOWN)


@dataclass
class Estimate:
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


def horizontal(cov9):
    return float(cov9[0]), float(cov9[1]), float(cov9[4])


def classify(sigma_m, cfg):
    limit = float(cfg["fix_max_sigma_m"])
    if sigma_m is None or not math.isfinite(sigma_m):
        return "DEGRADED", "σ unknown"
    if sigma_m > limit:
        return "DEGRADED", f"σ {sigma_m:.1f} m > {limit:.1f} m"
    return "FIX", f"σ {sigma_m:.1f} m"
