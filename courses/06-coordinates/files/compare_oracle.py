"""compare_oracle.py — checks YOUR geo.py against methods you did not write (Step 8).

    python3 compare_oracle.py

Part 1  your haversine_m (sphere) against Vincenty's formula on the WGS84 ellipsoid (geodesic_ref.py):
        100 km due north and due east of three places — how wrong is the sphere, and in which direction?
Part 2  your exact ENU frame against Vincenty: distance AND direction. For short distances the horizontal
        ENU distance and the distance along the ellipsoid agree to millimetres; farther away they drift
        apart (the ENU plane is flat, Vincenty follows the curved ground: lesson §7). The direction of
        the point in your ENU frame, atan2(e, n), must match Vincenty's azimuth: a mirrored or swapped
        frame fails here.
Part 3  pyproj, the geodesy library used by most GIS software, if it is installed here: its ECEF and its
        distances against yours. (Not installed? Part 3 is skipped; parts 1–2 are enough.)
"""
import math

import runner_kit as rk
from geodesic_ref import vincenty

# ---- you don't need to change anything in this file (but you can read it!) ----

g = rk.load_student("navera_lite.geo")
PLACES = [("Quito (equator)", -0.1807, -78.4678), ("Sousse (NAVERA's test area)", 35.8277, 10.6388),
          ("Reykjavik", 64.1466, -21.9426)]


def point_at(lat, lon, e_m, n_m):
    """The point e_m east and n_m north of (lat, lon), placed with YOUR exact enu_to_geodetic."""
    la, lo, _ = rk.need_ok(g, "enu_to_geodetic", e_m, n_m, 0.0, lat, lon, 0.0, n=3)
    return la, lo


def part1():
    print("Part 1 — the sphere against the ellipsoid, 100 km from each place")
    print("(each point is 100 km from home in the ENU plane; along the curved ground that is a few metres less)")
    print(f"{'place':30s} {'direction':>9s} {'ellipsoid (m)':>15s} {'sphere (m)':>13s} {'sphere error':>13s}")
    for name, lat, lon in PLACES:
        for dname, e, n in (("north", 0.0, 100_000.0), ("east", 100_000.0, 0.0)):
            la, lo = point_at(lat, lon, e, n)
            s_ell = vincenty(lat, lon, la, lo)[0]
            s_sph = rk.need_ok(g, "haversine_m", lat, lon, la, lo, kind=float)
            print(f"{name:30s} {dname:>9s} {s_ell:15.1f} {s_sph:13.1f} {100 * (s_sph - s_ell) / s_ell:+12.3f}%")


def part2():
    print("\nPart 2 — your exact ENU against Vincenty (horizontal distance and direction, ground points)")
    worst_dir = 0.0
    lat0, lon0 = 46.2044, 6.1432                          # Geneva
    for d in (100.0, 1_000.0, 10_000.0, 50_000.0):
        e, n = d * math.sin(math.radians(30)), d * math.cos(math.radians(30))
        la, lo = point_at(lat0, lon0, e, n)
        _, _, h = rk.need_ok(g, "enu_to_geodetic", e, n, 0.0, lat0, lon0, 0.0, n=3)
        ground = rk.need_ok(g, "geodetic_to_enu", la, lo, 0.0, lat0, lon0, 0.0, n=3)   # same point, on the ground
        enu_d = math.hypot(ground[0], ground[1])
        s_ell, az_ref, _ = vincenty(lat0, lon0, la, lo)
        az = math.degrees(math.atan2(ground[0], ground[1])) % 360.0
        worst_dir = max(worst_dir, abs((az - az_ref + 180.0) % 360.0 - 180.0))
        print(f"   {d / 1000:6.1f} km:  ENU {enu_d:12.4f} m  Vincenty {s_ell:12.4f} m  diff {1000 * (enu_d - s_ell):+9.3f} mm"
              f"  |  direction ENU {az:8.4f}°  Vincenty {az_ref:8.4f}°  |  plane {h:7.3f} m above ground")
    print("   " + ("✔ directions agree (better than 0.01°): your frame is not mirrored" if worst_dir < 0.01 else
                 f"✘ directions differ by up to {worst_dir:.2f}°: is your ENU frame mirrored (E and N rows swapped,"
                 " or a sign)? Check det(R) with python3 run_geo.py enu"))


def part3():
    print("\nPart 3 — pyproj")
    try:
        import pyproj
    except ImportError:
        print("   pyproj is not installed in this sandbox: skipped (parts 1 and 2 already used an independent method).")
        return
    to_ecef = pyproj.Transformer.from_crs("EPSG:4979", "EPSG:4978", always_xy=True)
    worst = 0.0
    for name, lat, lon in PLACES:
        mine = rk.need_ok(g, "geodetic_to_ecef", lat, lon, 500.0, n=3)
        theirs = to_ecef.transform(lon, lat, 500.0)
        worst = max(worst, math.dist(mine, theirs))
    print(f"   ECEF: largest difference with pyproj over {len(PLACES)} places: {worst * 1000:.3f} mm")
    geod = pyproj.Geod(ellps="WGS84")
    _, _, s = geod.inv(PLACES[0][2], PLACES[0][1], PLACES[2][2], PLACES[2][1])
    print(f"   Quito -> Reykjavik on the ellipsoid: pyproj {s:.3f} m, Vincenty {vincenty(*PLACES[0][1:], *PLACES[2][1:])[0]:.3f} m")


if __name__ == "__main__":
    part1()
    part2()
    part3()
