# Lab 6 — Latitude, longitude and meters
#
# Fill in the five functions marked TODO, save (Ctrl+S), then run:
#     python3 geo_lab.py
# Angles are in DEGREES everywhere in this file (like a GPS gives them).
# Python's math.sin / math.cos want RADIANS: convert with math.radians(angle).

import math

EARTH_RADIUS_M = 6_371_000.0   # mean radius of the Earth, in meters (the same value NAVERA uses)
M_PER_DEG = 111_320.0          # meters in one degree of latitude (NAVERA's value, day_pkg/vision_nav.py)


def distance(lat1, lon1, lat2, lon2):
    """Distance in meters between two points, along the Earth's surface (haversine formula)."""
    # TODO 1: the haversine formula (see the course, section "Long distances: the haversine formula")
    return None


def bearing(lat1, lon1, lat2, lon2):
    """Direction to go from point 1 to point 2, in degrees clockwise from north, between 0 and 360."""
    # TODO 2: the bearing formula with atan2, then bring the angle into 0..360 with % 360
    return None


def to_local_xy(lat, lon, home_lat, home_lon):
    """(east, north) in meters of the point (lat, lon), seen from the home point."""
    # TODO 3: north from the latitude difference, east from the longitude difference (do not forget the cos!)
    return None


def from_local_xy(east, north, home_lat, home_lon):
    """(lat, lon) of the point that is `east` meters east and `north` meters north of home."""
    # TODO 4: the exact opposite of to_local_xy
    return None


def route_length(points):
    """Total length in meters of a route given as a list of (lat, lon) points, in order."""
    # TODO 5: add up the distance() of every leg: point 0 -> 1, 1 -> 2, ...
    return None


# ---- you don't need to change anything below this line (but you can read it!) ----

PLACES = {
    "Ribat of Sousse": (35.8277, 10.6388),
    "Port El Kantaoui marina": (35.8942, 10.5979),
    "Monastir marina": (35.7795, 10.8320),
    "Monastir airport": (35.7581, 10.7547),
}
HOME = "Ribat of Sousse"


def _fmt(v, width=0, decimals=1):
    """A number with `decimals` decimals, right-aligned in `width` characters ("TODO" if None)."""
    text = "TODO" if v is None else f"{v:.{decimals}f}"
    return text.rjust(width)


if __name__ == "__main__":
    hlat, hlon = PLACES[HOME]
    print(f"Home: {HOME} ({hlat}, {hlon})\n")
    print(f"{'place':<25}{'distance (m)':>14}{'bearing (deg)':>15}{'east (m)':>11}{'north (m)':>11}")
    for name, (lat, lon) in PLACES.items():
        d = distance(hlat, hlon, lat, lon)
        b = "-".rjust(15) if name == HOME else _fmt(bearing(hlat, hlon, lat, lon), 15)
        xy = to_local_xy(lat, lon, hlat, hlon)
        e, n = xy if xy is not None else (None, None)
        print(f"{name:<25}{_fmt(d, 14)}{b}{_fmt(e, 11)}{_fmt(n, 11)}")
    back = from_local_xy(1000.0, 0.0, hlat, hlon)
    print("\n1 km east of home is", "TODO 4" if back is None else f"({back[0]:.6f}, {back[1]:.6f})")
    print("Length of the route Sousse -> Kantaoui -> Monastir marina -> airport:",
          _fmt(route_length(list(PLACES.values()))), "m")
