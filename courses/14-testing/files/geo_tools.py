"""geo_tools.py — small position helpers, like the ones of lessons 06 and 10.

These functions are CORRECT. Your job in this lab is not to change them: it is to write tests that
would catch anyone who breaks them. The checker will try 12 wrong versions of this file.
"""
import math

EARTH_RADIUS_M = 6_371_000.0          # the same value as NAVERA's navera_common/geo.py


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres between two points given in degrees."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))


def meters_to_degrees(north_m, east_m, lat_deg):
    """A small move in metres (north, east) -> (dlat, dlon) in degrees, at latitude lat_deg."""
    m_per_deg_lat = 2 * math.pi * EARTH_RADIUS_M / 360.0
    m_per_deg_lon = m_per_deg_lat * math.cos(math.radians(lat_deg))
    return north_m / m_per_deg_lat, east_m / m_per_deg_lon


def offset_to_latlon(lat0, lon0, north_m, east_m):
    """Flat-Earth: the point (north_m, east_m) metres from (lat0, lon0) -> (lat, lon)."""
    dlat, dlon = meters_to_degrees(north_m, east_m, lat0)
    return lat0 + dlat, lon0 + dlon


def latlon_to_offset(lat0, lon0, lat, lon):
    """The inverse of offset_to_latlon: (north_m, east_m) of (lat, lon) seen from (lat0, lon0)."""
    m_per_deg_lat = 2 * math.pi * EARTH_RADIUS_M / 360.0
    north = (lat - lat0) * m_per_deg_lat
    east = (lon - lon0) * m_per_deg_lat * math.cos(math.radians(lat0))
    return north, east


def is_valid_position(lat, lon):
    """True for a real position: finite numbers, latitude in [-90, 90], longitude in [-180, 180],
    and not exactly (0, 0) — "Null Island", the classic value of a field nobody filled."""
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return False
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return False
    return not (lat == 0.0 and lon == 0.0)


def speed_mps(distance_m, dt_s):
    """Speed in m/s, or None when it cannot be computed (dt_s is 0 or negative)."""
    if dt_s <= 0:
        return None
    return distance_m / dt_s


if __name__ == "__main__":
    print("Muscat -> Nizwa:", round(haversine_m(23.5880, 58.3829, 22.9333, 57.5333)), "m")
    print("100 m north, 100 m east at Muscat:", meters_to_degrees(100, 100, 23.588))
    print("round trip:", latlon_to_offset(23.588, 58.3829, *offset_to_latlon(23.588, 58.3829, 250.0, -120.0)))
    print("(0, 0) valid?", is_valid_position(0.0, 0.0))
    print("speed for 100 m in 20 s:", speed_mps(100, 20), "m/s")
