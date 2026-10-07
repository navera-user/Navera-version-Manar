# Lab 6 — Geodesy for navigation: WGS84, ECEF, ENU and the flat-Earth shortcut
#
# Fill in the ten functions marked TODO, save (Ctrl+S), then run:
#     python3 geo_lab.py
# Conventions used everywhere in this file:
#   * latitudes / longitudes / bearings are in DEGREES (like a GPS gives them);
#     math.sin / math.cos / math.atan2 work in RADIANS: convert with math.radians() / math.degrees();
#   * heights h are in meters above the WGS84 ellipsoid;
#   * a function that returns several numbers returns a tuple:  return east, north
#     and the caller unpacks it:                                e, n = flat_en(...)

import math

import numpy as np

# --- the WGS84 ellipsoid (the reference surface of GPS) -------------------------------------
WGS84_A = 6_378_137.0                    # semi-major axis a (equatorial radius), meters — exact by definition
WGS84_F = 1.0 / 298.257223563            # flattening f = (a - b) / a — exact by definition
WGS84_B = WGS84_A * (1.0 - WGS84_F)      # semi-minor axis b (polar radius) = 6 356 752.314 m
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)     # first eccentricity squared e² = (a² - b²) / a² = 0.00669438

# --- the two constants NAVERA uses -----------------------------------------------------------
EARTH_RADIUS_M = 6_371_000.0             # mean radius of a SPHERICAL Earth (navera_common/geo.py)
M_PER_DEG = 111_320.0                    # meters per degree, flat shortcut (day_pkg/vision_nav.py)


def radii(lat):
    """(M, N) in meters at geodetic latitude `lat` (degrees):
    M = meridian radius of curvature (north-south), N = prime-vertical radius (east-west)."""
    # TODO 1: w = 1 - e² sin²(lat);  M = a (1 - e²) / w^1.5 ;  N = a / sqrt(w)
    return None


def geodetic_to_ecef(lat, lon, h=0.0):
    """(X, Y, Z) in meters, Earth-centred Earth-fixed, of the point (lat, lon, h)."""
    # TODO 2: the three formulas of the course, with N from radii()
    return None


def ecef_to_geodetic(x, y, z):
    """(lat, lon, h) of an ECEF point — the inverse of geodetic_to_ecef (iterative, < 0.1 mm)."""
    # TODO 3: lon = atan2(Y, X); p = sqrt(X² + Y²); start with lat = atan2(Z, p (1 - e²));
    #         repeat 6 times: N from radii(), h = p / cos(lat) - N, lat = atan2(Z, p (1 - e² N / (N + h)))
    return None


def enu_matrix(lat0, lon0):
    """3 x 3 numpy rotation matrix R that turns an ECEF difference into (east, north, up) at (lat0, lon0)."""
    # TODO 4: the matrix of the course (rows = the unit vectors east, north, up written in ECEF)
    return None


def geodetic_to_enu(lat, lon, h, lat0, lon0, h0):
    """numpy array [east, north, up] in meters of (lat, lon, h) seen from the origin (lat0, lon0, h0)."""
    # TODO 5: ECEF of both points, difference, multiply by enu_matrix (R @ d)
    return None


def enu_to_geodetic(e, n, u, lat0, lon0, h0):
    """(lat, lon, h) of the point (e, n, u) meters from the origin — the inverse of geodetic_to_enu."""
    # TODO 6: R is orthonormal, so its inverse is its transpose: X = X0 + R.T @ [e, n, u]
    return None


def haversine(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters on a sphere of radius EARTH_RADIUS_M."""
    # TODO 7: the haversine formula (clip a to 1.0 before the square root, like NAVERA)
    return None


def bearing(lat1, lon1, lat2, lon2):
    """Initial great-circle bearing from point 1 to point 2, degrees clockwise from north, in [0, 360)."""
    # TODO 8: atan2(east part, north part), then % 360
    return None


def flat_en(lat, lon, lat0, lon0):
    """(east, north) in meters of (lat, lon) from (lat0, lon0) — NAVERA's flat shortcut (M_PER_DEG)."""
    # TODO 9: north = Δlat · M_PER_DEG ; east = Δlon · M_PER_DEG · cos(lat0)
    return None


def flat_move(lat, lon, de, dn):
    """(lat, lon) after moving `de` meters east and `dn` meters north — NAVERA's _move()."""
    # TODO 10: the inverse of flat_en, with the cosine of the CURRENT latitude (like NAVERA)
    return None


# ---- you don't need to change anything below this line (but you can read it!) ----

PLACES = {                                  # approximate coordinates (degrees), height above the ellipsoid (m)
    "Muscat (Grand Mosque)": (23.5839, 58.3875, 0.0),
    "Sohar": (24.3470, 56.7090, 0.0),
    "Nizwa (fort)": (22.9333, 57.5300, 500.0),
    "Jebel Shams (summit)": (23.2375, 57.2636, 3000.0),
    "Salalah": (17.0194, 54.0897, 0.0),
}
HOME = "Muscat (Grand Mosque)"


def _fmt(v, width=0, decimals=1):
    """A number with `decimals` decimals, right-aligned in `width` characters ("TODO" if None)."""
    text = "TODO" if v is None else f"{v:.{decimals}f}"
    return text.rjust(width)


def _first(v):
    return None if v is None else v[0]


if __name__ == "__main__":
    print("WGS84: a = %.3f m, b = %.3f m, e2 = %.10f" % (WGS84_A, WGS84_B, WGS84_E2))
    print(f"\n{'place':<24}{'M (km)':>9}{'N (km)':>9}{'km/deg lat':>11}{'km/deg lon':>11}")
    for name, (lat, lon, h) in PLACES.items():
        r = radii(lat)
        if r is None:
            print(f"{name:<24}{'TODO 1':>9}")
            continue
        m, n = r
        print(f"{name:<24}{m / 1000:9.1f}{n / 1000:9.1f}{m * math.pi / 180 / 1000:11.3f}"
              f"{n * math.cos(math.radians(lat)) * math.pi / 180 / 1000:11.3f}")

    hlat, hlon, hh = PLACES[HOME]
    print(f"\nFrom {HOME}:")
    print(f"{'place':<24}{'haversine (m)':>14}{'bearing':>9}{'ENU east':>11}{'north':>11}{'up':>9}")
    for name, (lat, lon, h) in PLACES.items():
        if name == HOME:
            continue
        enu = geodetic_to_enu(lat, lon, h, hlat, hlon, hh)
        e, n, u = (None, None, None) if enu is None else enu
        print(f"{name:<24}{_fmt(haversine(hlat, hlon, lat, lon), 14)}{_fmt(bearing(hlat, hlon, lat, lon), 9)}"
              f"{_fmt(e, 11)}{_fmt(n, 11)}{_fmt(u, 9)}")

    x = geodetic_to_ecef(*PLACES["Jebel Shams (summit)"])
    print("\nJebel Shams ECEF (m):", "TODO 2" if x is None else "(%.1f, %.1f, %.1f)" % tuple(x))
    if x is not None:
        back = ecef_to_geodetic(*x)
        print("  ... and back      :", "TODO 3" if back is None else "(%.7f, %.7f, %.3f)" % tuple(back))
    fe = flat_en(23.6, 58.4, hlat, hlon)
    print("\nflat_en of (23.6, 58.4) from home:", "TODO 9" if fe is None else "(%.1f, %.1f) m" % tuple(fe))
    fm = flat_move(hlat, hlon, 1000.0, 0.0)
    print("1 km east of home (flat_move)     :", "TODO 10" if fm is None else "(%.6f, %.6f)" % tuple(fm))
