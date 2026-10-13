"""navera_lite/geo.py — positions on the Earth: sphere, WGS84, east/north.

Part of NAVERA Lite, the course's teaching stack (mission 06). Written for the course;
it is not NAVERA code.

SKELETON: this file only names what the part will hold. You write it in mission 06.
"""


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance, m."""
    ...


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing, degrees from north."""
    ...


def enu_flat(lat0, lon0, lat, lon):
    """Metres east and north of a reference."""
    ...


def offset(lat, lon, e_m, n_m):
    """Move a position by metres east and north."""
    ...
