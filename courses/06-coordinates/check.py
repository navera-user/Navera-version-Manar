import contextlib
import io
import json
import math
import os
import re

from academy_check import CheckFailed, Checker, explained, is_stub, load_student, need, predicted, run, sh

c = Checker()
WELLINGTON_20KM = 58.957          # worst_flat_error_m(-41.2865, 174.7762, 20000.0), from the course reference


def geo():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.geo", fresh=True)


def functions(*names):
    mod = geo()
    fns = need(mod, *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/geo.py)")
    return fns


def answers(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        return need(load_student("answers.py", fresh=True), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def nums(v, n, what):
    """v must be n numbers (tuple, list or numpy array); returns floats."""
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    try:
        vals = [float(x) for x in v]
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return {n} numbers, got {v!r}")
    if len(vals) != n:
        raise CheckFailed(f"{what} should return {n} numbers, got {len(vals)}: {v!r}")
    return vals


def num(v, what):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    if isinstance(v, (tuple, list)):
        raise CheckFailed(f"{what} should return one number, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return one number, got {v!r}")


TIPS = [("unsupported operand type(s) for -: 'tuple'",
         " — tuples do not subtract: make numpy arrays first, np.array(geodetic_to_ecef(…)) (lab 🧰 Step 7)"),
        ("only length-1 arrays", " — a function that should take arrays uses math.…: your haversine_m must use "
                                 "np.sin, np.cos, np.arcsin, np.sqrt, np.minimum (TODO 3)"),
        ("only size-1 arrays", " — a function that should take arrays uses math.…: your haversine_m must use "
                               "np.sin, np.cos, np.arcsin, np.sqrt, np.minimum (TODO 3)"),
        ("could not be broadcast", " — numpy shapes do not fit: (101, 1) against (1, 1001) gives a (101, 1001) "
                                   "table (lab Step 4, 🧰 broadcasting)"),
        ("concatenate tuple", " — radii() returns two numbers (M, N): keep only N with `_, n = radii(lat)`"),
        ("math domain error", " — asin/acos/sqrt got a value just outside its range: clamp it (min(1.0, a)) or "
                              "check degrees vs radians")]


def go(fn, *args, **kw):
    """run() with one more sentence for the errors students meet most in this mission."""
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        for key, tip in TIPS:
            if key in msg:
                raise CheckFailed(msg + tip)
        raise


# ======================================================================== session 1 — the sphere
@c.test("TODO 1: enu_flat() gives metres east/north on unseen points, with the mean latitude and across ±180°",
        hint="Lesson §2: north = R·Δφ, east = R·cos(φ_mean)·Δλ, angles in RADIANS inside cos, R = EARTH_RADIUS_M. "
             "Bring Δλ into [−180, 180) before converting (lesson §1, the date line).")
def _():
    (f,) = functions("enu_flat")
    e, n = nums(go(f, -22.9068, -43.1729, -22.95, -43.10), 2, "enu_flat(Rio, …)")
    c.ok(abs(n - -4803.621) < 0.05, f"north of a point near Rio is {n:.3f} m — "
         + ("Δφ was not converted to radians" if abs(n) > 1e5 else "check R·Δφ with Δφ in radians"))
    c.ok(abs(e - -4798.861) > 1.0, "east has the wrong sign or size: math.cos() takes RADIANS — "
                                   "math.cos(-22.9) is not cos(22.9°)")
    e, n = nums(go(f, 40.4168, -3.7038, 55.7558, 37.6173), 2, "enu_flat(Madrid, Moscow)")
    if abs(e - 3498164.2) < 5:
        c.ok(False, "Madrid → Moscow: east uses cos of the START latitude — the docstring asks for the MEAN latitude")
    if abs(e - 2585533.5) < 5:
        c.ok(False, "Madrid → Moscow: east uses cos of the END latitude — the docstring asks for the MEAN latitude")
    c.near(e, 3069305.67, 0.5, "east of Moscow seen from Madrid (m)")
    c.near(n, 1705618.98, 0.5, "north of Moscow seen from Madrid (m)")
    e, n = nums(go(f, -17.70, 179.95, -17.69, -179.97), 2, "enu_flat across the date line")
    c.ok(abs(e) < 1e5, f"across the ±180° meridian (Fiji) east is {e:,.0f} m: Δλ = −359.92° must become +0.08° "
                       "(lesson §1, the date line)")
    c.near(e, 8474.73, 0.05, "east across the date line (m)")


@c.test("TODO 2: offset() is the exact inverse of enu_flat() on unseen moves",
        hint="Lesson §2: invert both formulas. The new latitude first; then use the MEAN of the old and new "
             "latitudes for cos, as enu_flat does. Keep the longitude in [−180, 180].")
def _():
    off, flat = functions("offset", "enu_flat")
    lat, lon = nums(go(off, 64.1466, -21.9426, -3000.0, 1500.0), 2, "offset(Reykjavik, −3 km E, 1.5 km N)")
    if abs(lat - 64.1466) < 0.001:
        raise CheckFailed(f"1.5 km north moves the latitude only to {lat:.6f}: n_m / R is in radians — convert it "
                          "with math.degrees before adding it to a latitude in degrees")
    lat2, lon2 = nums(go(off, -41.2865, 174.7762, 25000.0, -12000.0), 2, "offset(Wellington, 25 km E, 12 km S)")
    back = nums(go(flat, -41.2865, 174.7762, lat2, lon2), 2, "enu_flat(offset(…))")
    c.ok(math.dist(back, (25000.0, -12000.0)) < 1e-4,
         f"enu_flat(offset(…)) gives {tuple(round(v, 3) for v in back)} instead of (25000, −12000): "
         "offset must use the same cos(MEAN of old and new latitudes) as enu_flat")
    c.near(lat, 64.16008982, 1e-7, "latitude after the move")
    c.near(lon, -22.00448503, 1e-7, "longitude after the move")
    lat, lon = nums(go(off, -17.70, 179.95, 10000.0, 0.0), 2, "offset across the date line")
    c.ok(-180.0 <= lon <= 180.0, f"offset gives longitude {lon:.4f}: bring it back into [−180, 180]")
    c.near(lon, -179.95559904, 1e-7, "longitude after crossing the date line")


@c.test("TODO 3: haversine_m() on unseen pairs, and on numpy arrays (1-D and 2-D broadcasting)",
        hint="Lesson §3: a = sin²(Δφ/2) + cos φ1·cos φ2·sin²(Δλ/2), d = 2R·asin(√a), clamp a to at most 1. "
             "Use np.sin, np.cos, np.arcsin, np.sqrt, np.minimum (not math.… and min) so arrays work.")
def _():
    import numpy as np
    (f,) = functions("haversine_m")
    c.near(num(go(f, -1.2921, 36.8219, -1.2921, 36.8219), "haversine_m"), 0.0, 1e-6, "distance of a point to itself")
    v = num(go(f, -33.8688, 151.2093, -33.4489, -70.6693), "haversine_m")
    if abs(2 * v - 11346715.12) < 1:
        raise CheckFailed("Sydney → Santiago is exactly half the right distance: d = 2 R asin(√a) — the 2 is missing")
    c.near(v, 11346715.12, 0.5, "Sydney → Santiago (m)")
    c.near(num(go(f, 35.6762, 139.6503, 37.7749, -122.4194), "haversine_m"), 8274614.98, 0.5, "Tokyo → San Francisco (m)")
    try:
        got = f(np.array([10.0, -20.0, 60.0]), 5.0, np.array([11.0, -19.0, 61.0]), 5.0)
    except TypeError as e:
        raise CheckFailed(f"haversine_m() does not accept numpy arrays ({e}): use np.sin, np.cos, np.arcsin, np.sqrt "
                          "and np.minimum instead of math.… and min()")
    got = np.asarray(got, dtype=float)
    c.ok(got.shape == (3,), f"with 3 points in arrays it should return 3 distances, got shape {got.shape}")
    c.ok(np.allclose(got, 111194.927, atol=0.01), f"1° of latitude anywhere should be 111 194.9 m, got {got.round(1)}")
    grid = np.asarray(f(np.array([[0.0], [45.0]]), 0.0, 0.0, np.array([[10.0, 20.0, 30.0]])), dtype=float)
    c.ok(grid.shape == (2, 3), f"a (2, 1) array against a (1, 3) array should broadcast to (2, 3), got {grid.shape}")
    c.ok(np.allclose(grid, [[1111949.27, 2223898.53, 3335847.80], [5099840.84, 5377259.53, 5808684.65]], atol=0.05),
         "the 2 × 3 table of distances is not right")


@c.test("TODO 4: bearing_deg() — directions on unseen routes, always in [0, 360)",
        hint="Lesson §3: east ∝ sin Δλ·cos φ2, north ∝ cos φ1·sin φ2 − sin φ1·cos φ2·cos Δλ; "
             "atan2(EAST, NORTH) (east first!), then degrees, then % 360.")
def _():
    (f,) = functions("bearing_deg")
    w = num(go(f, -12.0, -77.0, -12.0, -77.01), "bearing_deg")
    if (0 <= w <= 2 * math.pi + 1e-9 and abs(w - 270) > 1) or abs(w - (-math.pi / 2) % 360) < 0.01:
        raise CheckFailed(f"due west you return {w:.3f}: still radians — convert with math.degrees, then % 360")
    c.ok(w >= 0, f"due west you return {w:.3f}°: a bearing is in [0, 360) — use % 360")
    sw = num(go(f, -12.0, -77.0, -12.01, -77.01), "bearing_deg")
    if abs(sw - 225.6) < 1.0 or abs(w - 180.0) < 1 or abs(w) < 1:
        c.ok(False, f"due west gives {w:.2f}° and south-west {sw:.2f}°: atan2 takes (east, north), east FIRST")
    c.near(w, 269.99896, 0.001, "bearing due west near Lima")
    c.near(sw, 224.36551, 0.001, "bearing to the south-west near Lima")
    c.near(num(go(f, -33.8688, 151.2093, -33.4489, -70.6693), "bearing_deg"), 145.28267, 0.001, "Sydney → Santiago")
    c.near(num(go(f, -33.4489, -70.6693, -33.8688, 151.2093), "bearing_deg"), 214.52429, 0.001, "Santiago → Sydney")
    c.near(num(go(f, 35.6762, 139.6503, 37.7749, -122.4194), "bearing_deg"), 54.36500, 0.001, "Tokyo → San Francisco")


@c.test("TODO 5: great_circle_points() — ends, equal steps, and the right path on unseen routes",
        hint="Lesson §4: turn both points into unit vectors (unit_vector is given), d = the angle between them "
             "(acos of the dot product), then v(f) = (sin((1−f)d)·a + sin(f·d)·b) / sin d for f = k/(n−1), "
             "and back to (lat, lon) with atan2. Raise ValueError when n < 2.")
def _():
    (f,) = functions("great_circle_points")
    pts = go(f, (40.4168, -3.7038), (55.7558, 37.6173), 5)
    c.ok(isinstance(pts, list) and len(pts) == 5, f"with n = 5 it should return a list of 5 (lat, lon), got {pts!r}")
    pts = [nums(p, 2, "each point") for p in pts]
    c.ok(math.dist(pts[0], (40.4168, -3.7038)) < 1e-9 and math.dist(pts[-1], (55.7558, 37.6173)) < 1e-9,
         "the first point must be p1 and the last p2")
    if abs(pts[2][0] - 48.0863) < 0.01 and abs(pts[2][1] - 16.9568) < 0.01:
        c.ok(False, "the middle point is the middle of the straight lat/lon line — that is not the great circle (lesson §4)")
    want = [(45.501640, 4.273089), (49.926407, 13.719150), (53.440709, 24.853721)]
    for k, (p, q) in enumerate(zip(pts[1:4], want), 1):
        c.ok(abs(p[0] - q[0]) < 1e-5 and abs(p[1] - q[1]) < 1e-5,
             f"point {k} Madrid → Moscow is ({p[0]:.5f}, {p[1]:.5f}), not on the great circle")
    mid = nums(go(f, (35.6762, 139.6503), (37.7749, -122.4194), 3)[1], 2, "the middle point Tokyo → San Francisco")
    c.ok(abs(mid[0] - 48.649780) < 1e-5 and abs(mid[1] - -172.284082) < 1e-5,
         f"Tokyo → San Francisco: the middle point is ({mid[0]:.4f}, {mid[1]:.4f}) — across the date line, "
         "convert back with atan2, which returns longitudes in [−180, 180]")
    try:
        f((10.0, 20.0), (-5.0, 40.0), 1)
    except ValueError:
        pass
    except Exception as e:
        raise CheckFailed(f"with n = 1 it should raise ValueError, it raised {type(e).__name__}: {e}")
    else:
        raise CheckFailed("with n = 1 it should raise ValueError (the docstring says n ≥ 2)")


@c.test("TODO 6: max_offset_km() — how far the great circle gets from the straight lat/lon line, on unseen routes",
        hint="Follow the docstring's definition exactly: 101 great-circle points, 1001 line points, for each "
             "great-circle point the distance to the NEAREST line point, the largest of these, in km. 🧰 Step 4 "
             "shows 2-D broadcasting with your haversine_m.")
def _():
    (f,) = functions("max_offset_km")
    v = num(go(f, (40.4168, -3.7038), (55.7558, 37.6173)), "max_offset_km")
    if abs(v - 295.756) < 0.01:
        raise CheckFailed("Madrid → Moscow gives 295.756: you took the nearest GREAT-CIRCLE point for each line point "
                          "(min over axis 0); the definition wants, for each great-circle point, the nearest LINE point")
    if abs(v - 312.41) < 0.05:
        c.ok(False, "Madrid → Moscow: you compare points at the SAME fraction of the route — the docstring asks for the "
                    "distance to the NEAREST point of the line")
    c.ok(not 1000 < v < 1e7, f"you return {v:.1f}: kilometres, not metres")
    c.ok(v > 1.0, f"Madrid → Moscow gives {v:.3g} km: almost 0 — are your great-circle points really on the great "
                  "circle (TODO 5), and is the line the straight lat/lon line?")
    c.near(v, 295.335, 0.01, "max offset Madrid → Moscow (km)")
    c.near(num(go(f, (30.0444, 31.2357), (-33.9249, 18.4241)), "max_offset_km"), 39.486, 0.01,
           "max offset Cairo → Cape Town (km)")
    c.near(num(go(f, (10.0, 5.0), (40.0, 5.0)), "max_offset_km"), 0.0, 1e-6, "along a meridian (km)")


@c.test("Step 2: how much a great-circle flight turns (Paris → Tunisia) — number and explanation",
        hint="Departure heading = bearing_deg(Paris → Tunisia). Arrival heading = the bearing from Tunisia back to "
             "Paris, turned around by 180° (then % 360). TURN_DEG = arrival − departure. EXPLAIN_BEARING: what makes "
             "the heading change along a great circle.")
def _():
    turn, why = answers("TURN_DEG", "EXPLAIN_BEARING")
    t = number(turn, "TURN_DEG")
    if abs(abs(t) - 184.70) < 0.05:
        raise CheckFailed("TURN_DEG is about 184.7: the bearing Tunisia → Paris points backwards — turn it by 180° "
                          "to get the arrival heading")
    if abs(t + 4.70) < 0.05:
        raise CheckFailed("TURN_DEG has the wrong sign: arrival − departure")
    c.near(t, 4.70, 0.02, "TURN_DEG (degrees)")
    explained("EXPLAIN_BEARING", why,
              ((r"great.?circle", r"curv", r"sphere", r"meridian", r"north"), "the path or the meridians"),
              ((r"chang", r"not constant", r"turn", r"differ", r"rotat", r"vary", r"converg"),
               "that the direction changes along the way"))


@c.test("Step 3: the route-length audit (NAVERA R-6) — numbers and explanation",
        hint="Run python3 run_geo.py cos; write the start-latitude and great-circle Paris → Tunisia lengths in km. "
             "EXPLAIN_COS: which column comes closest to the server's 1750 km, and why the mean latitude does better.")
def _():
    pred, a, gc, why = answers("PREDICT_COS", "ROUTE_FLAT_START_KM", "ROUTE_GC_KM", "EXPLAIN_COS")
    predicted("PREDICT_COS", pred)
    c.near(number(a, "ROUTE_FLAT_START_KM"), 1746.9, 0.2, "ROUTE_FLAT_START_KM")
    c.near(number(gc, "ROUTE_GC_KM"), 1767.8, 0.2, "ROUTE_GC_KM")
    explained("EXPLAIN_COS", why, ((r"start", r"first", r"paris", r"north"), "which latitude the server's number used"),
              ((r"mean", r"middle", r"average", r"half"), "why the mean latitude is better"),
              ((r"cos", r"parallel", r"shrink", r"longitude", r"east"), "what cos(latitude) scales"))


@c.test("Step 4: the corridor audit (NAVERA R-2) — prediction, numbers and explanation",
        hint="Run python3 run_geo.py route. OFFSET_KM in km, LEG_OFFSET_M in metres. EXPLAIN_ROUTE: on which side "
             "the great circle passes (look at out/route.png), and why short legs fix the corridor.")
def _():
    p0, off, leg, why = answers("PREDICT_ROUTE", "OFFSET_KM", "LEG_OFFSET_M", "EXPLAIN_ROUTE")
    predicted("PREDICT_ROUTE", p0)
    c.near(number(off, "OFFSET_KM"), 34.2, 0.1, "OFFSET_KM")
    c.near(number(leg, "LEG_OFFSET_M"), 1.09, 0.02, "LEG_OFFSET_M (metres!)")
    explained("EXPLAIN_ROUTE", why, ((r"north", r"pole", r"\beast", r"right", r"above"), "on which side the great circle passes"),
              ((r"leg", r"short", r"10 ?km", r"segment", r"small"), "why short legs fix it"),
              ((r"corridor", r"tile", r"1 ?km", r"map"), "what it meant for the map corridor"))


# ======================================================================== session 2 — the ellipsoid
@c.test("TODO 7: radii() — M and N at unseen latitudes",
        hint="Lesson §5: w = 1 − e²·sin²φ (φ in RADIANS), M = a(1 − e²)/w^1.5, N = a/√w. "
             "Use WGS84_A and WGS84_E2; return (M, N) in that order.")
def _():
    (f,) = functions("radii")
    for lat, want in [(-41.2865, (6363237.747, 6387451.978)), (78.2232, (6396899.590, 6398695.488)),
                      (19.4326, (6342487.564, 6380501.370))]:
        m, n = nums(go(f, lat), 2, f"radii({lat})")
        if lat == -41.2865 and abs(m - 6347285.09) < 0.1:
            raise CheckFailed("M at −41.2865° is 6 347 285 m: math.sin() got the latitude in DEGREES — convert to radians")
        if abs(m - want[1]) < 0.01 and abs(n - want[0]) < 0.01:
            raise CheckFailed("M and N are swapped: return (M, N) — M (meridian) is the smaller one away from the poles")
        c.near(m, want[0], 0.01, f"M at latitude {lat}")
        c.near(n, want[1], 0.01, f"N at latitude {lat}")


@c.test("TODO 8: geodetic_to_ecef() at unseen places and heights",
        hint="Lesson §6: X = (N + h)cos φ cos λ, Y = (N + h)cos φ sin λ, Z = (N(1 − e²) + h) sin φ, N from radii(lat) "
             "(lat in DEGREES there), radians inside sin/cos.")
def _():
    (f,) = functions("geodetic_to_ecef")
    for p, want, what in [((-41.2865, 174.7762, 25.0), (-4779740.875, 436992.464, -4186400.558), "Wellington"),
                          ((78.2232, 15.6267, 10.0), (1257701.197, 351788.348, 6222079.835), "Longyearbyen"),
                          ((19.4326, -99.1332, 2240.0), (-955419.121, -5942828.351, 2109313.009), "Mexico City")]:
        x = nums(go(f, *p), 3, f"geodetic_to_ecef{p}")
        if abs(x[2] - want[2]) > 1 and abs(x[0] - want[0]) < 0.01:
            raise CheckFailed(f"{what}: X and Y are right but Z is not — Z uses N·(1 − e²) + h, not N + h")
        for k, axis in enumerate("XYZ"):
            c.near(x[k], want[k], 0.01, f"{axis} of {what} (m)")


@c.test("TODO 9: ecef_to_geodetic() inverts geodetic_to_ecef() to 1 mm — high, low, south and west",
        hint="Lesson §6: lon = atan2(Y, X); iterate on the latitude (keep it in DEGREES between calls to radii): "
             "h = p/cos φ − N, φ = atan2(Z, p(1 − e²·N/(N + h))). 5–10 iterations; recompute h at the end.")
def _():
    to_ecef, to_geo = functions("geodetic_to_ecef", "ecef_to_geodetic")
    for p in [(-41.2865, 174.7762, 25.0), (31.5590, 35.4732, -400.0), (-54.8019, -68.3030, 30.0),
              (64.8378, -147.7164, 11000.0), (27.9881, 86.9250, 8800.0), (-0.0001, -0.0001, 0.0)]:
        x = nums(go(to_ecef, *p), 3, "geodetic_to_ecef")
        lat, lon, h = nums(go(to_geo, *x), 3, f"ecef_to_geodetic of {p}")
        if abs(h - p[2]) > 1000:
            raise CheckFailed(f"{p}: the height comes back {h:,.0f} m — degrees and radians are mixed up somewhere "
                              "(radii() takes degrees; sin/cos take radians)")
        if abs(lat - p[0]) < 1e-4:
            tip = "more iterations? recompute h after the last latitude?"
        else:
            tip = "radii() takes DEGREES: keep lat in degrees between iterations, radians only inside sin/cos/atan2"
        c.ok(abs(lat - p[0]) < 1e-8 and abs(lon - p[1]) < 1e-8 and abs(h - p[2]) < 1e-3,
             f"round trip of {p} gives ({lat:.9f}, {lon:.9f}, {h:.4f}) — {tip}")


@c.test("TODO 10: enu_matrix() is a rotation with the East, North and Up rows of an unseen place",
        hint="Lesson §7: E = (−sin λ, cos λ, 0), N = (−sin φ cos λ, −sin φ sin λ, cos φ), "
             "U = (cos φ cos λ, cos φ sin λ, sin φ), as the ROWS of np.array([...]). det = −1 → two rows swapped "
             "or one sign wrong.")
def _():
    import numpy as np
    (f,) = functions("enu_matrix")
    r = go(f, -41.2865, 174.7762)
    try:
        r = np.asarray(r, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"enu_matrix should return a 3 × 3 numpy array, got {r!r}")
    c.ok(r.shape == (3, 3), f"enu_matrix should return shape (3, 3), got {r.shape}")
    c.ok(np.allclose(r @ r.T, np.eye(3), atol=1e-12), "R @ R.T is not the identity: the rows are not unit vectors at "
                                                       "right angles (radians? a sign?)")
    c.near(float(np.linalg.det(r)), 1.0, 1e-9, "det(R) (−1 = a mirror: two rows swapped or one sign wrong)")
    want = [[-0.0910462512, -0.9958466650, 0.0], [-0.6570841644, 0.0600745596, 0.7514196219],
            [-0.7482987244, 0.0684139396, -0.6598246372]]
    for k, name in enumerate(("East (row 0)", "North (row 1)", "Up (row 2)")):
        c.ok(np.allclose(r[k], want[k], atol=1e-9), f"the {name} at Wellington is {r[k].round(6).tolist()}")


@c.test("TODOs 11–12: geodetic_to_enu() and enu_to_geodetic() on unseen points, and back again",
        hint="Lesson §7: d = ECEF(point) − ECEF(origin) as numpy arrays, then enu_matrix(lat0, lon0) @ d. Back: "
             "X = X0 + R.T @ [e, n, u] (R.T, not R), then your ecef_to_geodetic.")
def _():
    to_enu, to_geo = functions("geodetic_to_enu", "enu_to_geodetic")
    e, n, u = nums(go(to_enu, -41.10, 174.95, 300.0, -41.2865, 174.7762, 25.0), 3, "geodetic_to_enu")
    for got, want, what in [(e, 14601.236, "east"), (n, 20698.579, "north"), (u, 224.648, "up")]:
        c.near(got, want, 0.005, f"{what} of a point near Wellington (m)")
    e, n, u = nums(go(to_enu, 19.40, -99.00, 2300.0, 19.4326, -99.1332, 2240.0), 3, "geodetic_to_enu")
    c.near(u, 43.631, 0.005, "up of a point near Mexico City (m)")
    lat, lon, h = nums(go(to_geo, -5000.0, 12000.0, 150.0, 78.2232, 15.6267, 10.0), 3, "enu_to_geodetic")
    if abs(lat - 78.3306) > 0.01 and abs(h - 173.2) > 1:
        c.ok(False, f"enu_to_geodetic gives ({lat:.4f}, {lon:.4f}, {h:.1f}): use R.T (the inverse of a rotation), not R")
    c.ok(abs(lat - 78.33059372) < 1e-7 and abs(lon - 15.40535487) < 1e-7 and abs(h - 173.2086) < 1e-3,
         f"enu_to_geodetic near Longyearbyen gives ({lat:.7f}, {lon:.7f}, {h:.4f})")
    for enu in [(300.0, -1200.0, 15.0), (-40000.0, 25000.0, -100.0)]:
        lat, lon, h = nums(go(to_geo, *enu, 19.4326, -99.1332, 2240.0), 3, "enu_to_geodetic")
        back = nums(go(to_enu, lat, lon, h, 19.4326, -99.1332, 2240.0), 3, "geodetic_to_enu")
        c.ok(math.dist(back, enu) < 1e-3, f"ENU {enu} → geodetic → ENU gives {[round(v, 4) for v in back]}")


@c.test("Steps 5–7: degree lengths, the 111 320 m shortcut, geocentric latitude, the drop, heights",
        hint="Step 5: N·cos φ·π/180 at Anchorage (61.2181°), φ in radians inside cos; search the latitude where "
             "M·π/180 = 111 320 m (a loop or bisection with your radii). Step 6: atan2(Z, √(X² + Y²)) of surface "
             "points, at 30° and over all latitudes. Step 7: `up` of Tallinn in run_geo.py enu; ellipsoidal "
             "height = sea-level height + geoid separation.")
def _():
    km, zero, gdiff, gmax, pred, drop, h = answers("KM_PER_DEG_LON_ANCHORAGE", "SCALE_NORTH_ZERO_LAT_DEG",
                                                   "GEOCENTRIC_DIFF_DEG", "GEOCENTRIC_MAX_AT_DEG", "PREDICT_DROP",
                                                   "DROP_M", "H_ELLIPSOID_M")
    km = number(km, "KM_PER_DEG_LON_ANCHORAGE")
    c.ok(not 50000 < km < 60000, "KM_PER_DEG_LON_ANCHORAGE is in metres: write kilometres")
    c.ok(km > 0, "KM_PER_DEG_LON_ANCHORAGE is negative: math.cos got the latitude in degrees")
    c.near(km, 53.736, 0.01, "KM_PER_DEG_LON_ANCHORAGE (km)")
    zero = number(zero, "SCALE_NORTH_ZERO_LAT_DEG")
    c.ok(not abs(zero - 0.0) < 0.5, "SCALE_NORTH_ZERO_LAT_DEG = 0: 111 320 m is a degree of the EQUATOR (east–west), "
                                    "not of a meridian — search where M·π/180 equals it")
    c.near(zero, 54.81, 0.02, "SCALE_NORTH_ZERO_LAT_DEG (degrees)")
    c.near(number(gdiff, "GEOCENTRIC_DIFF_DEG"), 0.1664, 0.001, "GEOCENTRIC_DIFF_DEG (geodetic − geocentric, at 30°)")
    c.near(number(gmax, "GEOCENTRIC_MAX_AT_DEG"), 45.0, 0.5, "GEOCENTRIC_MAX_AT_DEG (degrees)")
    predicted("PREDICT_DROP", pred)
    drop = number(drop, "DROP_M")
    c.ok(drop < 0, "DROP_M: Tallinn is BELOW Helsinki's horizontal plane — the up value is negative")
    c.near(drop, -530.6, 0.2, "DROP_M (m)")
    c.near(number(h, "H_ELLIPSOID_M"), 283.8, 0.05, "H_ELLIPSOID_M (m)")


@c.test("Step 8: the oracle — how wrong is the sphere at the equator, and why",
        hint="Run python3 compare_oracle.py and copy the two Quito percentages (with their sign). EXPLAIN_SPHERE: "
             "compare EARTH_RADIUS_M with M and N at the equator (lesson §5).")
def _():
    n, e, why = answers("SPHERE_ERR_NORTH_PCT_QUITO", "SPHERE_ERR_EAST_PCT_QUITO", "EXPLAIN_SPHERE")
    c.near(number(n, "SPHERE_ERR_NORTH_PCT_QUITO"), 0.561, 0.005, "SPHERE_ERR_NORTH_PCT_QUITO (%)")
    c.near(number(e, "SPHERE_ERR_EAST_PCT_QUITO"), -0.112, 0.005, "SPHERE_ERR_EAST_PCT_QUITO (%)")
    explained("EXPLAIN_SPHERE", why, ((r"\bm\b", r"meridian", r"north.?south", r"radius", r"radii", r"curvature"),
                                      "which radius of curvature applies"),
              ((r"6 ?371", r"sphere", r"mean radius", r"larger", r"bigger", r"smaller", r"flatten", r"ellipsoid"),
               "how the sphere's radius compares"))


RES = {}


@c.test("TODO A + Step 9: error_study.py — your worst_flat_error_m(), results.json, prediction and explanation",
        hint="Write TODO A in error_study.py (its docstring defines the error exactly), run python3 error_study.py, "
             "read out/error_study.png. EXPLAIN_STUDY: what dominates near home (look at the slope) and far away.")
def _():
    with contextlib.redirect_stdout(io.StringIO()):
        mod = load_student("error_study.py", fresh=True)
    (f,) = need(mod, "worst_flat_error_m")
    if is_stub(f):
        raise CheckFailed("worst_flat_error_m() is not written yet (TODO A in error_study.py)")
    v = num(go(f, -41.2865, 174.7762, 20000.0, seconds=60), "worst_flat_error_m")
    if abs(v - 24.645) < 0.01:
        raise CheckFailed("worst_flat_error_m looks at the first bearing only: is the `return` inside the loop?")
    if abs(v - 66.005) < 0.01:
        raise CheckFailed("worst_flat_error_m: math.sin/math.cos got the bearing in DEGREES — convert with math.radians")
    c.ok(abs(v - WELLINGTON_20KM) <= 0.01, f"worst_flat_error_m at Wellington, 20 km, gives {v:.3f} m — not the right "
         "value (if a geo.py check above fails, fix it first: this function uses enu_flat and enu_to_geodetic)")
    code, out = sh("python3 error_study.py", timeout=100)
    c.ok(code == 0, "error_study.py stopped with an error:\n" + out[-600:])
    c.file_exists("results.json")
    RES.update(json.load(open("results.json")))
    homes = RES.get("homes", {})
    for name, d1, s in [("Quito (equator)", 220.4, 1.0), ("Sousse (NAVERA's test area)", 477.4, 1.0),
                        ("Reykjavik", 285.1, 1.0)]:
        r = homes.get(name, {})
        c.ok(r.get("d_1m_m") == d1, f"results.json: {name} reaches 1 m at {r.get('d_1m_m')} m — rerun error_study.py "
                                    "after your last edit; if it stays wrong, check worst_flat_error_m")
        c.near(float(r.get("slope_below_1km", 0)), s, 0.02, f"slope below 1 km at {name}")
    pred, d1m, why = answers("PREDICT_STUDY", "D_1M_SOUSSE_M", "EXPLAIN_STUDY")
    predicted("PREDICT_STUDY", pred)
    c.near(number(d1m, "D_1M_SOUSSE_M"), 477.4, 0.5, "D_1M_SOUSSE_M (m)")
    explained("EXPLAIN_STUDY", why, ((r"scale", r"radius", r"radii", r"sphere", r"6 ?371", r"slope 1", r"proportional"),
                                     "what makes the error grow like the distance near home"),
              ((r"curv", r"slope 2", r"square", r"d²", r"d\^2", r"far", r"large", r"flat"), "what takes over far away"))


@c.test("report.md: the audit memo — three sections, ≥ 150 words, the key numbers",
        hint="Keep the headings '## Route length (R-6)', '## Corridor (R-2)', '## Which model, where'. Quote "
             "your numbers: the two Paris → Tunisia lengths of Step 3 (flat with cos(start) and great circle), "
             "the offset of Step 4, and where your flat shortcut reaches 1 m at Sousse (Step 9).")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8").read()
    for h in ("## Route length", "## Corridor", "## Which model"):
        c.ok(re.search(r"^" + re.escape(h), text, re.M | re.I) is not None, f"report.md has no '{h}…' heading")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    words = re.findall(r"[A-Za-zÀ-ÿ']{2,}", body)
    c.ok(len(words) >= 150, f"report.md has {len(words)} words of your own (at least 150 expected)")
    flat = re.sub(r"(?<=\d)[ ,  ](?=\d{3}\b)", "", body)
    for pat, what in [(r"\b174[67](\.\d+)?\b", "the flat route length with cos(start latitude) (Step 3)"),
                      (r"\b176[78](\.\d+)?\b", "the great-circle length (Step 3)"),
                      (r"\b34(\.\d+)?\b", "the corridor offset in km (Step 4)"),
                      (r"\b47[78](\.\d+)?\b", "where your flat shortcut reaches 1 m at Sousse (Step 9)")]:
        c.ok(re.search(pat, flat) is not None, f"report.md does not quote {what}")


c.milestone("navigator", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "TODO 5:", "TODO 6:", "Step 2:", "Step 3:", "Step 4:",
            label="Session 1 complete: Navigator badge earned (the ✘ lines left, if any, are session 2)")
c.milestone("surveyor", "TODO", "Step", "report",
            label="Mission complete: Navigator and Surveyor badges earned")

c.run()
