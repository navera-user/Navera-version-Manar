import json
import math
import os
import re

from academy_check import Checker, load_student, need, sh

c = Checker()

A, B = 6378137.0, 6356752.314245
MUSCAT = (23.5839, 58.3875)
SALALAH = (17.0194, 54.0897)
NIZWA = (22.9333, 57.5300, 500.0)
SHAMS = (23.2375, 57.2636, 3000.0)


def geo():
    return load_student("geo_lab.py")


def nums(v, what, n):
    """v must be n numbers (a tuple, a list or a numpy array); returns them as floats."""
    c.ok(v is not None, f"{what} returned None — the TODO is not done yet")
    try:
        vals = [float(x) for x in v]
    except TypeError:
        c.ok(False, f"{what} should return {n} numbers, got {v!r}")
    c.ok(len(vals) == n, f"{what} should return {n} numbers, got {len(vals)}: {v!r}")
    return vals


def num(v, what):
    c.ok(v is not None, f"{what} returned None — the TODO is not done yet")
    try:
        return float(v)
    except (TypeError, ValueError):
        c.ok(False, f"{what} should return one number, got {v!r}")


@c.test("radii(): M and N at the equator, the pole and Muscat",
        hint="w = 1 − e²·sin²(lat), with lat in RADIANS. M = a(1 − e²) / w**1.5 and N = a / sqrt(w). "
             "Use the constants WGS84_A and WGS84_E2 of the file. Return the tuple (M, N).")
def _():
    (radii,) = need(geo(), "radii")
    for lat, want in [(0.0, (6335439.327, 6378137.0)), (90.0, (6399593.626, 6399593.626)),
                      (MUSCAT[0], (6345636.485, 6381557.126))]:
        m, n = nums(radii(lat), f"radii({lat})", 2)
        c.near(m, want[0], tol=0.01, what=f"M at latitude {lat}")
        c.near(n, want[1], tol=0.01, what=f"N at latitude {lat}")


@c.test("geodetic_to_ecef(): (0°, 0°) is (a, 0, 0), the pole is (0, 0, b), Jebel Shams is right",
        hint="X = (N + h) cos(lat) cos(lon), Y = (N + h) cos(lat) sin(lon), Z = (N (1 − e²) + h) sin(lat). "
             "Z uses N·(1 − e²), not N. Angles in radians.")
def _():
    (f,) = need(geo(), "geodetic_to_ecef")
    for args, want, what in [((0.0, 0.0, 0.0), (A, 0.0, 0.0), "(0°, 0°, 0 m)"),
                             ((90.0, 0.0, 0.0), (0.0, 0.0, B), "the North Pole"),
                             ((0.0, 90.0, 100.0), (0.0, A + 100.0, 0.0), "(0°, 90° E, 100 m)"),
                             (SHAMS, (3172476.072, 4934740.537, 2502092.799), "Jebel Shams (3000 m)")]:
        x = nums(f(*args), "geodetic_to_ecef()", 3)
        for k, axis in enumerate("XYZ"):
            c.near(x[k], want[k], tol=0.01, what=f"{axis} of {what}")


@c.test("ecef_to_geodetic() is the inverse of geodetic_to_ecef() (to 1 mm), also high, low and south-west",
        hint="lon = atan2(Y, X). Iterate on the latitude: N from radii(lat), h = p / cos(lat) − N, "
             "lat = atan2(Z, p (1 − e² N / (N + h))). Keep lat in DEGREES between the calls to radii().")
def _():
    to_ecef, to_geo = need(geo(), "geodetic_to_ecef", "ecef_to_geodetic")
    for p in [MUSCAT + (0.0,), SHAMS, (17.0194, 54.0897, -45.0), (-33.9, -70.6, 2500.0), (65.0, 25.0, 10000.0)]:
        x = nums(to_ecef(*p), "geodetic_to_ecef()", 3)
        lat, lon, h = nums(to_geo(*x), "ecef_to_geodetic()", 3)
        c.near(lat, p[0], tol=1e-8, what=f"latitude after a round trip of {p}")
        c.near(lon, p[1], tol=1e-8, what=f"longitude after a round trip of {p}")
        c.near(h, p[2], tol=1e-3, what=f"height after a round trip of {p}")


@c.test("enu_matrix() is a rotation (R·Rᵀ = I, det = +1) with the right east and up rows",
        hint="Rows: east = (−sin λ, cos λ, 0); north = (−sin φ cos λ, −sin φ sin λ, cos φ); "
             "up = (cos φ cos λ, cos φ sin λ, sin φ). Return np.array([...]) of shape (3, 3).")
def _():
    import numpy as np
    (f,) = need(geo(), "enu_matrix")
    r = f(*MUSCAT)
    c.ok(r is not None, "enu_matrix() returned None — the TODO is not done yet")
    r = np.asarray(r, float)
    c.eq(r.shape, (3, 3), what="the shape of enu_matrix()")
    c.ok(np.allclose(r @ r.T, np.eye(3), atol=1e-12), "R·Rᵀ is not the identity: the rows are not orthonormal")
    c.near(float(np.linalg.det(r)), 1.0, tol=1e-9, what="det(R) (−1 means two rows are swapped)")
    lam, phi = math.radians(MUSCAT[1]), math.radians(MUSCAT[0])
    c.ok(np.allclose(r[0], [-math.sin(lam), math.cos(lam), 0.0], atol=1e-12), f"the east row is {r[0].tolist()}")
    c.ok(np.allclose(r[2], [math.cos(phi) * math.cos(lam), math.cos(phi) * math.sin(lam), math.sin(phi)],
                     atol=1e-12), f"the up row is {r[2].tolist()}")


@c.test("geodetic_to_enu(): origin is (0, 0, 0), +100 m height is up = 100, Nizwa from Muscat is right",
        hint="d = ECEF(point) − ECEF(origin), then enu_matrix(lat0, lon0) @ d. Use numpy arrays: "
             "np.array(geodetic_to_ecef(...)) so that the subtraction works element by element.")
def _():
    (f,) = need(geo(), "geodetic_to_enu")
    e, n, u = nums(f(*MUSCAT, 0.0, *MUSCAT, 0.0), "geodetic_to_enu()", 3)
    c.near(math.hypot(e, n, u), 0.0, tol=1e-6, what="the ENU of the origin itself")
    e, n, u = nums(f(*MUSCAT, 100.0, *MUSCAT, 0.0), "geodetic_to_enu()", 3)
    c.near(u, 100.0, tol=1e-6, what="up of a point 100 m above the origin")
    e, n, u = nums(f(*NIZWA, *MUSCAT, 0.0), "geodetic_to_enu()", 3)
    for got, want, what in [(e, -87959.818, "east"), (n, -71793.198, "north"), (u, -512.350, "up")]:
        c.near(got, want, tol=0.01, what=f"{what} of Nizwa fort (500 m) seen from Muscat")


@c.test("enu_to_geodetic() is the inverse of geodetic_to_enu() (to 1 mm)",
        hint="R is orthonormal, so R⁻¹ = Rᵀ: X = X0 + enu_matrix(lat0, lon0).T @ [e, n, u], "
             "then ecef_to_geodetic(X[0], X[1], X[2]).")
def _():
    to_enu, to_geo = need(geo(), "geodetic_to_enu", "enu_to_geodetic")
    for enu in [(1000.0, 0.0, 0.0), (-2500.0, 400.0, 30.0), (-87959.818, -71793.198, -512.350), (0.0, 0.0, -20.0)]:
        lat, lon, h = nums(to_geo(*enu, *MUSCAT, 0.0), "enu_to_geodetic()", 3)
        back = nums(to_enu(lat, lon, h, *MUSCAT, 0.0), "geodetic_to_enu()", 3)
        c.ok(math.dist(back, enu) < 1e-3, f"{enu} -> geodetic -> ENU gives {[round(v, 4) for v in back]}")
    lat, lon, h = nums(to_geo(-87959.818, -71793.198, -512.350, *MUSCAT, 0.0), "enu_to_geodetic()", 3)
    c.near(lat, NIZWA[0], tol=1e-7, what="latitude of Nizwa found back from its ENU")


@c.test("haversine() uses EARTH_RADIUS_M and agrees with NAVERA's haversine_m() (Muscat → Salalah 856.4 km)",
        hint="The radius is called EARTH_RADIUS_M in geo_lab.py (not R). Every angle in radians; "
             "a = sin²(Δφ/2) + cos φ1 cos φ2 sin²(Δλ/2); d = 2 · EARTH_RADIUS_M · asin(sqrt(min(1.0, a))).")
def _():
    (f,) = need(geo(), "haversine")
    c.near(num(f(*MUSCAT, *MUSCAT), "haversine()"), 0.0, tol=1e-6, what="haversine of a point to itself")
    c.near(num(f(*MUSCAT, *SALALAH), "haversine()"), 856375.19, tol=0.5, what="haversine(Muscat, Salalah)")
    try:
        from navera_common.geo import haversine_m
    except Exception:
        c.skip("NAVERA's navera_common is not importable here")
    for a, b in [((23.58, 58.38), (23.5801, 58.3802)), ((24.347, 56.709), (22.9333, 57.53)), ((-33.9, 18.4), (51.5, -0.12))]:
        c.near(num(f(*a, *b), "haversine()"), haversine_m(*a, *b), tol=1e-3, what=f"haversine{a + b} vs NAVERA")


@c.test("bearing(): 0 / 90 / 180 / 270 for due N / E / S / W; Muscat → Salalah ≈ 212.3°, back ≈ 30.8°",
        hint="bearing() needs its OWN p1, p2, dl lines (variables of haversine() do not exist inside bearing()). "
             "y = sin Δλ cos φ2 (east part), x = cos φ1 sin φ2 − sin φ1 cos φ2 cos Δλ; degrees(atan2(y, x)) % 360.")
def _():
    (f,) = need(geo(), "bearing")
    lat, lon = MUSCAT
    for (lat2, lon2), want, name in [((lat + 0.01, lon), 0.0, "north"), ((lat, lon + 0.01), 90.0, "east"),
                                     ((lat - 0.01, lon), 180.0, "south"), ((lat, lon - 0.01), 270.0, "west")]:
        b = num(f(lat, lon, lat2, lon2), "bearing()")
        if want == 0.0 and b > 359.9:
            b -= 360.0
        c.near(b, want, tol=0.01, what=f"bearing to a point due {name}")
    c.near(num(f(*MUSCAT, *SALALAH), "bearing()"), 212.324, tol=0.01, what="bearing(Muscat → Salalah)")
    back = num(f(*SALALAH, *MUSCAT), "bearing()")
    c.near(back, 30.830, tol=0.01, what="bearing(Salalah → Muscat)")


@c.test("flat_en() and flat_move() give exactly NAVERA's _en() and _move()",
        hint="flat_en: east = Δlon · M_PER_DEG · cos(lat0), north = Δlat · M_PER_DEG. flat_move: lat + dn / M_PER_DEG, "
             "lon + de / (M_PER_DEG · cos(lat)) with the CURRENT latitude. Read ~/navera/day_pkg/day_pkg/vision_nav.py.")
def _():
    fe, fm = need(geo(), "flat_en", "flat_move")
    e, n = nums(fe(NIZWA[0], NIZWA[1], *MUSCAT), "flat_en()", 2)
    c.near(e, -87483.881, tol=0.001, what="east of Nizwa (flat)")
    c.near(n, -72424.792, tol=0.001, what="north of Nizwa (flat)")
    lat, lon = nums(fm(*MUSCAT, 500.0, -300.0), "flat_move()", 2)
    c.near(lat, 23.581205066, tol=1e-9, what="latitude after flat_move(500 m E, 300 m S)")
    c.near(lon, 58.392400903, tol=1e-9, what="longitude after flat_move(500 m E, 300 m S)")
    try:
        from day_pkg.vision_nav import _en, _move
    except Exception:
        c.skip("NAVERA's day_pkg is not importable here")
    for p in [(23.70, 58.20), (17.0194, 54.0897)]:
        c.ok(math.dist(nums(fe(*p, *MUSCAT), "flat_en()", 2), _en(p, MUSCAT)) < 1e-6, f"flat_en{p} differs from _en()")
    c.ok(math.dist(nums(fm(17.0, 54.0, -800.0, 1200.0), "flat_move()", 2), _move((17.0, 54.0), -800.0, 1200.0)) < 1e-12,
         "flat_move() differs from NAVERA's _move()")


RES = {}


@c.test("python3 error_study.py runs and writes results.json and error_study.png",
        hint="Run `python3 error_study.py` in the terminal and read the error. It needs TODO 1–9.")
def _():
    code, out = sh("python3 error_study.py", timeout=90)
    c.ok(code == 0, "error_study.py stopped with an error:\n" + out[-700:])
    c.file_exists("results.json")
    c.file_exists("error_study.png")
    c.ok(os.path.getsize("error_study.png") > 10000, "error_study.png looks empty")
    RES.update(json.load(open("results.json")))


@c.test("results.json: the error distances and the Muscat → Salalah numbers are right",
        hint="If these are wrong while the function checks pass, re-run `python3 error_study.py` after your last edit.")
def _():
    if not RES:
        c.ok(os.path.exists("results.json"), "results.json is missing: run python3 error_study.py")
        RES.update(json.load(open("results.json")))
    c.eq(RES.get("navera_flat_d_1m_m"), 220.4, what="navera_flat_d_1m_m")
    c.eq(RES.get("navera_flat_d_10m_m"), 2241.2, what="navera_flat_d_10m_m")
    c.eq(RES.get("wgs84_flat_d_1m_m"), 6283.5, what="wgs84_flat_d_1m_m")
    ms = RES.get("muscat_salalah", {})
    c.near(float(ms.get("difference_m", 0)), 2358.6, tol=0.5, what="muscat_salalah.difference_m")
    c.near(float(ms.get("ellipsoid_km", 0)), 854.017, tol=0.002, what="muscat_salalah.ellipsoid_km")


@c.test("report.md: the three sections, at least 150 words, and the key numbers quoted",
        hint="Use the headings '## Method', '## Results', '## Discussion'. Quote in meters the distance where "
             "NAVERA's flat error reaches 1 m and 10 m, and the Muscat–Salalah difference (e.g. 2359 or 2358.6).")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8").read()
    for h in ("## Method", "## Results", "## Discussion"):
        c.ok(re.search(r"^" + re.escape(h) + r"\b", text, re.M | re.I) is not None, f"report.md has no '{h}' heading")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    words = re.findall(r"[A-Za-z]{2,}", body)
    c.ok(len(words) >= 150, f"report.md has only {len(words)} words of your own (at least 150 expected)")
    flat = re.sub(r"(?<=\d)[ ,  ](?=\d{3}\b)", "", body)     # "2 241" or "2,241" -> "2241"
    for value, name in [(220.4, "the 1 m distance (220.4 m)"), (2241.2, "the 10 m distance (2241.2 m)"),
                        (2358.6, "the Muscat–Salalah difference (2358.6 m)")]:
        c.ok(re.search(rf"\b({int(value)}|{round(value)})(\.\d+)?\b", flat) is not None,
             f"report.md does not quote {name}")


@c.test("quiz Q1: km in 1° of longitude at Muscat (WGS84)",
        hint="N · cos(lat) · π / 180 with N from radii(23.5839) — or read the table printed by python3 geo_lab.py.")
def _():
    (v,) = need(load_student("answers.py"), "Q1")
    try:
        v = float(v)
    except (TypeError, ValueError):
        c.ok(False, f"Q1 should be a number, got {v!r}")
    c.ok(v != 0, "Q1 has no answer yet")
    c.ok(101.8 <= v <= 102.4, f"Q1 = {v} km is not right (kilometers, not meters)")


QUIZ = {"Q2": ("a", "Read the 'Null Island' box of the course, and is_finite_latlon() in ~/navera/navera_common/navera_common/geo.py."),
        "Q3": ("b", "Compare EARTH_RADIUS_M with M and N at Muscat: which one is further from 6 371 000 m?")}

for q, (good, hint) in QUIZ.items():
    @c.test(f"quiz {q}", hint=hint)
    def _(q=q, good=good):
        (v,) = need(load_student("answers.py"), q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f"{q} = \"{v}\" is not the right answer")

c.run()
