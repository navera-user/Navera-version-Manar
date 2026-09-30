"""Geodesy helpers shared across NAVERA localizers.

Kept in one place so every pipeline propagates a position the same way — and
refuses to propagate one when the inputs are unknown, instead of inventing them.
"""
import math
from typing import Optional, Tuple

EARTH_RADIUS_M = 6_371_000.0


def is_finite_latlon(lat, lon) -> bool:
    """True for a real, in-range position. Rejects None, NaN/inf and (0, 0)."""
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    return not (lat == 0.0 and lon == 0.0)


def dead_reckon(lat: float, lon: float, heading_deg, speed_mps,
                dt_s: float) -> Optional[Tuple[float, float]]:
    """Propagate (lat, lon) along ``heading_deg`` at ``speed_mps`` for ``dt_s``.

    Great-circle destination on a spherical Earth; heading is clockwise from
    true north. Returns None when heading or speed is unknown/non-finite, the
    speed is negative or dt is not positive: a propagated position must come
    from measured motion, never from a default.
    """
    try:
        hdg = float(heading_deg)
        spd = float(speed_mps)
        dt = float(dt_s)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(hdg) and math.isfinite(spd) and math.isfinite(dt)):
        return None
    if spd < 0.0 or dt <= 0.0 or not is_finite_latlon(lat, lon):
        return None

    d = spd * dt / EARTH_RADIUS_M
    brng = math.radians(hdg)
    p1 = math.radians(lat)
    l1 = math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(brng))
    l2 = l1 + math.atan2(math.sin(brng) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * math.sin(p2))
    lon2 = (math.degrees(l2) + 540.0) % 360.0 - 180.0
    return math.degrees(p2), lon2


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (spherical Earth, R = 6 371 km)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, a)))
