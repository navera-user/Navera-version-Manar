import csv
import math
import os

from academy_check import Checker, load_student, need, sh

c = Checker()

SOUSSE = (35.8277, 10.6388)        # Ribat of Sousse
MONASTIR = (35.7795, 10.8320)      # Monastir marina


def geo():
    return load_student("geo_lab.py")


def num(v, what):
    if v is None:
        c.ok(False, f"{what} returned None — the TODO is not done yet")
    return v


def pair(v, what):
    c.ok(v is not None, f"{what} returned None — the TODO is not done yet")
    c.ok(isinstance(v, (tuple, list)) and len(v) == 2, f"{what} should return two numbers, like (east, north); got {v!r}")
    return float(v[0]), float(v[1])


@c.test("distance() is 0 m between a point and itself",
        hint="When both points are the same, every difference is 0, so the haversine 'a' is 0.")
def _():
    (distance,) = need(geo(), "distance")
    c.near(num(distance(*SOUSSE, *SOUSSE), "distance()"), 0.0, tol=0.01, what="distance(Sousse, Sousse)")


@c.test("distance() gives about 111 195 m for 1° of latitude",
        hint="Use math.radians() on every angle before sin/cos, and multiply by 2 * EARTH_RADIUS_M at the end.")
def _():
    (distance,) = need(geo(), "distance")
    c.near(num(distance(35.0, 10.0, 36.0, 10.0), "distance()"), 111194.93, tol=1.0,
           what="distance(35, 10, 36, 10)")


@c.test("distance() from the Ribat of Sousse to Monastir marina is right (≈ 18.2 km)",
        hint="Longitude counts too: the haversine has a cos(lat1) * cos(lat2) * sin²(Δlon / 2) part.")
def _():
    (distance,) = need(geo(), "distance")
    d = num(distance(*SOUSSE, *MONASTIR), "distance()")
    c.near(d, 18228.89, tol=1.0, what="distance(Sousse, Monastir)")
    c.near(distance(*MONASTIR, *SOUSSE), d, tol=0.01, what="distance(Monastir, Sousse) (it should be the same both ways)")


@c.test("distance() agrees with NAVERA's haversine_m()",
        hint="NAVERA's version is in ~/navera/navera_common/navera_common/geo.py — compare it with yours.")
def _():
    (distance,) = need(geo(), "distance")
    try:
        from navera_common.geo import haversine_m
    except Exception:
        c.skip("NAVERA's navera_common is not importable here")
    for a, b in [((35.70, 10.40), (36.05, 10.85)), ((35.83, 10.60), (35.8301, 10.6002)),
                 ((-33.9, 18.4), (51.5, -0.12))]:
        c.near(num(distance(*a, *b), "distance()"), haversine_m(*a, *b), tol=0.05, what=f"distance{a + b}")


@c.test("bearing() gives 0 (north), 90 (east), 180 (south) and 270 (west)",
        hint="atan2(y, x) with y = sin(Δlon)·cos(lat2) — the EAST part first. Then % 360 to remove negative angles.")
def _():
    (bearing,) = need(geo(), "bearing")
    lat, lon = SOUSSE
    for (lat2, lon2), want, name in [((lat + 0.01, lon), 0.0, "north"), ((lat, lon + 0.01), 90.0, "east"),
                                     ((lat - 0.01, lon), 180.0, "south"), ((lat, lon - 0.01), 270.0, "west")]:
        b = num(bearing(lat, lon, lat2, lon2), "bearing()")
        if want == 0.0 and b > 359.9:
            b -= 360.0
        c.near(b, want, tol=0.1, what=f"bearing to a point due {name}")


@c.test("bearing() from Sousse to Monastir is ≈ 107°, and back is ≈ 287°, always between 0 and 360",
        hint="Use radians inside sin/cos, degrees for the answer (math.degrees), and `% 360` at the end.")
def _():
    (bearing,) = need(geo(), "bearing")
    there = num(bearing(*SOUSSE, *MONASTIR), "bearing()")
    back = num(bearing(*MONASTIR, *SOUSSE), "bearing()")
    c.near(there, 107.042, tol=0.05, what="bearing(Sousse → Monastir)")
    c.near(back, 287.155, tol=0.05, what="bearing(Monastir → Sousse)")
    c.ok(0.0 <= back < 360.0, f"bearing should be in 0..360, got {back}")


@c.test("to_local_xy(): home is (0, 0), 0.01° north is 1113.2 m north, 0.01° east is ≈ 902.6 m east",
        hint="north = Δlat × M_PER_DEG ; east = Δlon × M_PER_DEG × cos(home latitude in radians). Return (east, north).")
def _():
    (to_local_xy,) = need(geo(), "to_local_xy")
    e, n = pair(to_local_xy(*SOUSSE, *SOUSSE), "to_local_xy()")
    c.near(math.hypot(e, n), 0.0, tol=0.001, what="distance of home from itself")
    e, n = pair(to_local_xy(SOUSSE[0] + 0.01, SOUSSE[1], *SOUSSE), "to_local_xy()")
    c.near(e, 0.0, tol=0.01, what="east of a point due north")
    c.near(n, 1113.2, tol=0.05, what="north of a point 0.01° north")
    e, n = pair(to_local_xy(SOUSSE[0], SOUSSE[1] + 0.01, *SOUSSE), "to_local_xy()")
    c.near(e, 902.561, tol=0.05, what="east of a point 0.01° east (did you forget the cos?)")
    c.near(n, 0.0, tol=0.01, what="north of a point due east")


@c.test("from_local_xy() is the exact opposite of to_local_xy()",
        hint="Solve the two formulas of to_local_xy for lat and lon: lat = home_lat + north / M_PER_DEG …")
def _():
    to_local_xy, from_local_xy = need(geo(), "to_local_xy", "from_local_xy")
    lat, lon = pair(from_local_xy(1000.0, 0.0, *SOUSSE), "from_local_xy()")
    c.near(lat, SOUSSE[0], tol=1e-7, what="latitude 1 km east of home")
    c.near(lon, 10.6498796, tol=1e-6, what="longitude 1 km east of home")
    for e0, n0 in [(-2500.0, 400.0), (17437.5, -5365.6), (0.0, -2000.0)]:
        lat, lon = pair(from_local_xy(e0, n0, *SOUSSE), "from_local_xy()")
        e, n = pair(to_local_xy(lat, lon, *SOUSSE), "to_local_xy()")
        c.near(e, e0, tol=0.001, what=f"east after a round trip of ({e0}, {n0})")
        c.near(n, n0, tol=0.001, what=f"north after a round trip of ({e0}, {n0})")


@c.test("route_length() of the route in route.csv is ≈ 14 198.7 m",
        hint="Loop over the legs i = 0 … len(points) - 2 and add distance(points[i], points[i + 1]).")
def _():
    (route_length,) = need(geo(), "route_length")
    with open("/academy/courses/06-coordinates/files/route.csv") as f:
        pts = [(float(r["lat"]), float(r["lon"])) for r in csv.DictReader(f)]
    c.near(num(route_length(pts), "route_length()"), 14198.68, tol=1.0, what="route_length(route.csv)")
    c.near(num(route_length(pts[:2]), "route_length()"), 2297.41, tol=1.0, what="route_length of the first leg only")


@c.test("route_length() is 0 for a route of one point or no point",
        hint="With 0 or 1 point there is no leg at all: the loop must not run, and the total stays 0.")
def _():
    (route_length,) = need(geo(), "route_length")
    c.near(num(route_length([SOUSSE]), "route_length()"), 0.0, tol=1e-9, what="route_length([one point])")
    c.near(num(route_length([]), "route_length()"), 0.0, tol=1e-9, what="route_length([])")


@c.test("python3 route.py runs and draws route.png",
        hint="Run `python3 route.py` in the terminal and read the last lines it prints.")
def _():
    code, out = sh("python3 route.py", timeout=60)
    c.ok(code == 0, "route.py stopped with an error:\n" + out[-600:])
    c.file_exists("route.png")
    c.ok(os.path.getsize("route.png") > 5000, "route.png looks empty")


QUIZ = {"Q2": ("c", "Bearings turn clockwise from north: 0 north, 90 east, 180 south…"),
        "Q3": ("a", "Open geo.py and read the docstring of is_finite_latlon(); then think about what (0, 0) is.")}


@c.test("quiz Q1: km in 1° of longitude at Sousse",
        hint="111.32 km × cos(35.8°). Write only the number, in kilometers.")
def _():
    (v,) = need(load_student("answers.py"), "Q1")
    try:
        v = float(v)
    except (TypeError, ValueError):
        c.ok(False, f"Q1 should be a number, got {v!r}")
    c.ok(v != 0, "Q1 has no answer yet")
    c.ok(85 <= v <= 95, f"Q1 = {v} km is not right")


for q, (good, hint) in QUIZ.items():
    @c.test(f"quiz {q}", hint=hint)
    def _(q=q, good=good):
        (v,) = need(load_student("answers.py"), q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f"{q} = \"{v}\" is not the right answer")

c.run()
