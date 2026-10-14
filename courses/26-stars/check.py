"""Check of mission 26 — navigating by the stars. Sealed: never shown to students.

Unseen inputs everywhere. Expected values of TODOs 1–4 and 6–9 come from the course reference on hidden inputs
(hidden/expected.json, made by solutions/26-stars/make_expected.py); TODO 5 is graded on a night image the check
renders itself, with exact truth. The lab's numbers (expected.json "lab") are what run_stars.py prints with the
reference; solutions/26-stars/TEACHER.md lists them. Numbers that depend on the student's own detector (Step 5)
are recomputed from the student's function.
"""
import contextlib
import csv
import io
import json
import math
import re

import numpy as np

from academy_check import CheckFailed, Checker, explained, hidden, is_stub, load_student, need, predicted, run

c = Checker()
E = json.loads(hidden("expected.json"))
LAB = E["lab"]
DATA = "/data/academy/26-stars"
KM = 2.0 * math.pi * 6371.0 / 360.0


def stars():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.stars", fresh=True)


def functions(*names):
    fns = need(stars(), *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/stars.py)")
    return fns


def answers(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        return need(load_student("answers.py", fresh=True), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")
    if not math.isfinite(x):
        raise CheckFailed(f"{name} is {x}: not a usable number")
    return x


def num(v, what):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    if isinstance(v, (tuple, list)) or (hasattr(v, "shape") and np.shape(v) != ()):
        raise CheckFailed(f"{what} should return one number, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return one number, got {v!r}")


def go(fn, *args, **kw):
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        if "only length-1 arrays" in msg or "only size-1 arrays" in msg:
            raise CheckFailed(msg + " — math.sin/math.cos take single numbers: use np.sin, np.cos, np.arctan2")
        if "math domain error" in msg:
            raise CheckFailed(msg + " — asin got a value beyond ±1: when |sin δ| > R there is no root (return [])")
        if "truth value of an array" in msg:
            raise CheckFailed(msg + " — an `if` on a numpy array: work on whole arrays, or compare single numbers")
        if "'NoneType'" in msg:
            raise CheckFailed(msg + " — a function it calls returned None: is an earlier TODO still a stub?")
        raise


def wrap180(x):
    return (x + 180.0) % 360.0 - 180.0


# ======================================================================== session 1 — Stargazer
def jd_variant(y, mo, d, h=0, mi=0, s=0.0, shift=True, B=True, mins=60.0, secs=True, half=1524.5, hours=True,
               minutes=True):
    if shift and mo <= 2:
        y, mo = y - 1, mo + 12
    a = math.floor(y / 100)
    b = 2 - a + math.floor(a / 4) if B else 0
    t = (h + (mi / mins if minutes else 0.0) + (s / 3600.0 if secs and minutes else 0.0)) / 24.0 if hours else 0.0
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (mo + 1)) + d + t + b - half


@c.test("TODO 1: julian_date() on unseen dates — January/February, a leap day, seconds, other centuries",
        hint="Lesson §1, the recipe: January and February are months 13 and 14 of the previous year; A = floor(year/100), "
             "B = 2 − A + floor(A/4); JD = floor(365.25(year + 4716)) + floor(30.6001(month + 1)) + day + hours/24 + B − 1524.5, "
             "hours = h + mi/60 + s/3600.")
def _():
    (f,) = functions("julian_date")
    for date, want in E["jd"]:
        got = num(go(f, *date), "julian_date")
        if abs(got - want) < 1e-6:
            continue
        for kw, msg in (({"shift": False}, "January and February must count as months 13 and 14 of the PREVIOUS year"),
                        ({"B": False}, "the Gregorian correction B = 2 − A + floor(A/4) is missing"),
                        ({"mins": 100.0}, "the minutes count as hundredths of an hour: hours = h + mi/60 + s/3600"),
                        ({"secs": False}, "the seconds are ignored: hours = h + mi/60 + s/3600"),
                        ({"minutes": False}, "the minutes (and seconds) are not added: hours = h + mi/60 + s/3600"),
                        ({"half": 1524.0}, "half a day off: the constant is − 1524.5 (a Julian day starts at noon)"),
                        ({"hours": False}, "the time of day is not added: + (h + mi/60 + s/3600) / 24")):
            if abs(got - jd_variant(*date, **kw)) < 1e-6:
                raise CheckFailed(f"julian_date{tuple(date)} = {got:.6f}: {msg}")
        raise CheckFailed(f"julian_date{tuple(date)} = {got:.6f} is {got - want:+.6f} days off")
    c.ok(True)


@c.test("TODO 2: gmst_deg() on unseen dates and on an array of dates",
        hint="Lesson §1: d = jd − 2451545.0, T = d/36525, GMST = 280.46061837 + 360.98564736629·d + 0.000387933·T² "
             "− T³/38710000, then % 360. Use numpy operations so that an array of dates works too.")
def _():
    (f,) = functions("gmst_deg")
    for jd, want in E["gmst"]:
        got = num(go(f, jd), "gmst_deg")
        if not 0.0 <= got < 360.0:
            raise CheckFailed(f"gmst_deg({jd}) = {got:.4f}: keep the angle in [0, 360) with % 360.0")
        if abs(got - want / 15.0) < 1e-4:
            raise CheckFailed("gmst_deg returns hours (÷ 15): the function returns DEGREES")
        if abs(got - math.radians(want)) < 1e-6:
            raise CheckFailed("gmst_deg returns radians: the function returns DEGREES")
        d = jd - 2451545.0
        if abs(got - (280.46061837 + 360.98564736629 * d) % 360) < 1e-7 and abs(got - want) > 1e-7:
            raise CheckFailed("the T² and T³ terms are missing: they are tiny (millionths of a degree here), but the "
                              "check wants the full IAU formula of lesson §1")
        if abs(got - (280.46061837 + 360.98564736629 * d / 36525.0) % 360) < 1e-4:
            raise CheckFailed("the 360.9856° per DAY term multiplies d (days since J2000), not T (centuries)")
        c.ok(abs(got - want) < 2e-6, f"gmst_deg({jd}) = {got:.6f}° is {got - want:+.6f}° off")
    jds = np.array([x[0] for x in E["gmst"]])
    got = go(f, jds)
    try:
        a = np.asarray(got, dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"gmst_deg on an array of {len(jds)} dates should return an array, got {got!r}")
    c.ok(a.shape == jds.shape, f"gmst_deg on an array of {len(jds)} dates should return {len(jds)} values (numpy "
                               f"operations, no math.*); got shape {a.shape}")
    c.ok(np.allclose(a, [x[1] for x in E["gmst"]], atol=2e-6), "gmst_deg on an array gives other values than one by one")


def altaz_ref(ra, dec, lat, lon, gst, sign_lon=1.0, h_sign=1.0):
    ra, dec, phi = np.radians(ra), np.radians(dec), math.radians(lat)
    H = h_sign * (np.radians(gst + sign_lon * lon) - ra)
    alt = np.degrees(np.arcsin(np.sin(dec) * math.sin(phi) + np.cos(dec) * math.cos(phi) * np.cos(H)))
    az = np.degrees(np.arctan2(-np.cos(dec) * np.sin(H), np.sin(dec) * math.cos(phi) - np.cos(dec) * math.sin(phi) * np.cos(H)))
    return alt, az % 360.0


@c.test("TODO 3: altaz() on unseen stars and observers — whole arrays, south and west, below the horizon",
        hint="Lesson §2: H = gst + lon − ra (east longitudes positive); sin a = sin δ sin φ + cos δ cos φ cos H; "
             "A = atan2(−cos δ sin H, sin δ cos φ − cos δ sin φ cos H) in degrees, % 360. numpy functions, so that "
             "arrays work.")
def _():
    (f,) = functions("altaz")
    for k in E["altaz"]:
        ra, dec = np.array(k["ra"]), np.array(k["dec"])
        got = go(f, ra, dec, k["lat"], k["lon"], k["gst"])
        if not (isinstance(got, (tuple, list)) and len(got) == 2):
            raise CheckFailed(f"altaz should return two values (alt, az), got {got!r}")
        try:
            a, z = (np.asarray(x, dtype=float).reshape(-1) for x in got)
        except (TypeError, ValueError):
            raise CheckFailed("altaz on arrays should return two numpy arrays")
        if a.shape != ra.shape or z.shape != ra.shape:
            raise CheckFailed(f"altaz on {len(ra)} stars should return {len(ra)} altitudes and azimuths (numpy "
                              f"operations); got sizes {a.size} and {z.size}")
        wa, wz = np.array(k["alt"]), np.array(k["az"])
        ok_a = np.allclose(a, wa, atol=1e-6)
        dz = np.abs(wrap180(z - wz))
        if ok_a and np.all(dz < 1e-6) and np.any(z < 0):
            raise CheckFailed("some azimuths are negative: keep them in [0, 360) with % 360.0")
        if ok_a and np.all(dz < 1e-6) and np.any(z >= 360.0):
            raise CheckFailed("some azimuths are ≥ 360: keep them in [0, 360) with % 360.0")
        if ok_a and np.all(np.abs(wrap180(z - (wz + 180.0))) < 1e-6):
            raise CheckFailed("the azimuth is measured from SOUTH: north is 0°, east 90° (atan2(−cos δ sin H, …))")
        if ok_a and np.all(np.abs(wrap180(z + wz)) < 1e-6):
            raise CheckFailed("the azimuth goes the wrong way round (counter-clockwise): it is clockwise from north; "
                              "check the minus sign in −cos δ sin H")
        ba, bz = altaz_ref(ra, dec, k["lat"], k["lon"], k["gst"], sign_lon=-1.0)
        if np.allclose(a, ba, atol=1e-6):
            raise CheckFailed(f"with lon = {k['lon']} the longitude has the wrong sign: LST = gst + lon (east positive)")
        ba, bz = altaz_ref(ra, dec, k["lat"], k["lon"], k["gst"], h_sign=-1.0)
        if np.allclose(a, ba, atol=1e-6) and np.allclose(np.abs(wrap180(z - bz)), 0, atol=1e-6):
            raise CheckFailed("the hour angle has the wrong sign: H = LST − ra = gst + lon − ra")
        c.ok(ok_a, f"altaz: altitudes off by up to {np.abs(a - wa).max():.4f}° (observer at lat {k['lat']}, lon {k['lon']})")
        c.ok(np.all(dz < 1e-6), f"altaz: azimuths off by up to {dz.max():.4f}° (observer at lat {k['lat']}, lon {k['lon']})")
    args, want = E["altaz_one"][0]
    got = go(f, *args)
    if not (isinstance(got, (tuple, list)) and len(got) == 2):
        raise CheckFailed(f"altaz on one star should return two numbers (alt, az), got {got!r}")
    a, z = num(got[0], "altaz (alt of one star)"), num(got[1], "altaz (az of one star)")
    c.ok(abs(a - want[0]) < 1e-6 and abs(z - want[1]) < 1e-6, f"altaz on one star (Sirius from Sydney) gives ({a:.4f}, {z:.4f})")


@c.test("TODO 4: lat_from_polaris() on unseen altitudes and hour angles",
        hint="Lesson §3: no hour angle → the altitude itself; else φ = a − p·cos H, with H in degrees turned into "
             "radians inside cos.")
def _():
    (f,) = functions("lat_from_polaris")
    (alt, want), = E["polaris_none"]
    got = num(go(f, alt), "lat_from_polaris")
    c.ok(abs(got - want) < 1e-9, f"lat_from_polaris({alt}) (no hour angle) gives {got}: it should be the altitude itself")
    for (a, h, p), want in E["polaris"]:
        got = num(go(f, a, h, p), "lat_from_polaris")
        if abs(got - (a + p * math.cos(math.radians(h)))) < 1e-9:
            raise CheckFailed("the correction has the wrong sign: at H = 0 Polaris is ABOVE the pole, φ = a − p·cos H")
        if abs(got - (a - p * math.cos(h))) < 1e-9:
            raise CheckFailed("cos got degrees: math.cos(math.radians(ha_deg))")
        if abs(got - (a - p * math.sin(math.radians(h)))) < 1e-9 or abs(got - (a + p * math.sin(math.radians(h)))) < 1e-9:
            raise CheckFailed("the correction uses sin H: Polaris stands p·cos H above the pole (H = 0: straight above), "
                              "φ = a − p·cos H")
        if abs(got - (a - 0.6253 * math.cos(math.radians(h)))) < 1e-9 and abs(p - 0.6253) > 1e-6:
            raise CheckFailed("p_deg is ignored: use the p_deg argument (its default is POLARIS_P_DEG)")
        c.ok(abs(got - want) < 1e-9, f"lat_from_polaris({a}, {h}, {p}) gives {got:.5f}")


@c.test("Steps 1–2: the catalogue, the sidereal day and precession — numbers and explanation",
        hint="N_VOTE_STARS: count cat['vmag'] <= 4.5. python3 run_stars.py clock: the transit shift (s, as a positive "
             "number) and Vega's precession (′); 1′ = 1.852 km. EXPLAIN_SIDEREAL: 361° per day, 3 min 56 s, and a "
             "clock error turns into a longitude error; Polaris: 1° of ra is cos δ degrees on the sky.")
def _():
    pred, n, sh, arc, km, why = answers("PREDICT_SIDEREAL", "N_VOTE_STARS", "TRANSIT_SHIFT_S", "VEGA_SHIFT_ARCMIN",
                                        "VEGA_SHIFT_KM", "EXPLAIN_SIDEREAL")
    predicted("PREDICT_SIDEREAL", pred)
    n = number(n, "N_VOTE_STARS")
    if n in (LAB["N_VOTE_STARS"] - 1, LAB["N_VOTE_STARS"] + 1) or n < 100:
        raise CheckFailed(f"N_VOTE_STARS = {n:g}: count the stars with vmag ≤ 4.5 (smaller magnitude = brighter; "
                          "≤, not <)")
    c.near(n, LAB["N_VOTE_STARS"], 0.5, "N_VOTE_STARS")
    sh = number(sh, "TRANSIT_SHIFT_S")
    if abs(sh + LAB["TRANSIT_SHIFT_S"]) < 0.5:
        raise CheckFailed("TRANSIT_SHIFT_S: write by how many seconds it comes EARLIER, as a positive number")
    c.near(sh, LAB["TRANSIT_SHIFT_S"], 0.3, "TRANSIT_SHIFT_S (seconds)")
    arc = number(arc, "VEGA_SHIFT_ARCMIN")
    c.near(arc, LAB["VEGA_SHIFT_ARCMIN"], 0.03, "VEGA_SHIFT_ARCMIN (′)")
    km = number(km, "VEGA_SHIFT_KM")
    if abs(km - arc * 111.195) < 1.0:
        raise CheckFailed("VEGA_SHIFT_KM: 111.2 km is ONE DEGREE; one arcminute is 1.852 km")
    c.near(km, arc * 1.852, 0.15, "VEGA_SHIFT_KM (your arcminutes × 1.852 km)")
    explained("EXPLAIN_SIDEREAL", why,
              ((r"361", r"orbit", r"around the sun", r"sun", r"365", r"23 ?h", r"sidereal day", r"one degree", r"1°",
                r"extra"), 'why the sky gains (e.g. "the Earth also moves on its orbit, so it turns 361° per day")'),
              ((r"clock", r"time", r"second", r"longitude", r"15", r"position", r"east", r"west", r"km"),
               'why it matters for a fix (e.g. "the time decides the longitude: a clock error moves the fix east or west")'),
              ((r"cos", r"pole", r"declination", r"δ", r"dec\b", r"89", r"converg", r"meridians", r"small circle"),
               'why Polaris\' right ascension moved 8.8° but Polaris only 9.1′ (e.g. "near the pole one degree of ra is '
               'only cos δ degrees on the sky")'))


@c.test("Steps 3–4: the sky over Cape Town and latitude from Polaris — numbers, prediction, explanation",
        hint="PREDICT_ACHERNAR by hand first; python3 run_stars.py sky capetown: Achernar's altitude and azimuth. "
             "python3 run_stars.py polaris: the largest error of each column. EXPLAIN_POLARIS: p ≈ 0.63°, "
             "the hour angle, and what is left (p² terms growing with tan φ).")
def _():
    pa, a, z, pred, nv, cr, why = answers("PREDICT_ACHERNAR", "ACHERNAR_ALT_DEG", "ACHERNAR_AZ_DEG", "PREDICT_POLARIS",
                                          "NAIVE_MAX_ERR_KM", "CORRECTED_MAX_ERR_KM", "EXPLAIN_POLARIS")
    predicted("PREDICT_ACHERNAR", pa)
    a, z = number(a, "ACHERNAR_ALT_DEG"), number(z, "ACHERNAR_AZ_DEG")
    if abs(a - LAB["ACHERNAR_AZ_DEG"]) < 0.05 and abs(z - LAB["ACHERNAR_ALT_DEG"]) < 0.05:
        raise CheckFailed("ACHERNAR_ALT_DEG and ACHERNAR_AZ_DEG are swapped")
    c.near(a, LAB["ACHERNAR_ALT_DEG"], 0.02, "ACHERNAR_ALT_DEG")
    c.near(z, LAB["ACHERNAR_AZ_DEG"], 0.02, "ACHERNAR_AZ_DEG")
    predicted("PREDICT_POLARIS", pred)
    nv, cr = number(nv, "NAIVE_MAX_ERR_KM"), number(cr, "CORRECTED_MAX_ERR_KM")
    if abs(nv - LAB["CORRECTED_MAX_ERR_KM"]) < 0.02 and abs(cr - LAB["NAIVE_MAX_ERR_KM"]) < 0.2:
        raise CheckFailed("NAIVE_MAX_ERR_KM and CORRECTED_MAX_ERR_KM are swapped")
    c.near(nv, LAB["NAIVE_MAX_ERR_KM"], 0.1, "NAIVE_MAX_ERR_KM (the largest of the naive column)")
    c.near(cr, LAB["CORRECTED_MAX_ERR_KM"], 0.005, "CORRECTED_MAX_ERR_KM (the largest of the corrected column)")
    explained("EXPLAIN_POLARIS", why,
              ((r"0\.6", r"polar distance", r"\bp\b", r"from the pole", r"not (exactly )?(at|on) the pole", r"circle",
                r"away from the pole", r"70"), 'why the naive error is about 70 km (e.g. "Polaris is 0.63° from the pole")'),
              ((r"hour angle", r"\bh\b", r"cos", r"where (polaris|it) is on", r"side of the pole", r"above or below",
                r"time"), 'what the correction removes (e.g. "p·cos H: where Polaris is on its circle")'),
              ((r"tan", r"high latitude", r"reykjavik", r"north", r"p²", r"p2", r"p\^2", r"squared", r"second.order",
                r"first.order", r"latitude"), 'why the rest is largest at Reykjavik (e.g. "the p² term grows with tan φ")'))


# ======================================================================== session 2 — Star navigator
def render_night(seed=2661):
    """A small unseen night image: stars, a glowing corner, hot pixels, an aircraft trail. Returns (img, stars, hots)."""
    import cv2
    rng = np.random.default_rng(seed)
    W, H = 360, 280
    p0, p1 = np.array([20.0, 252.0]), np.array([200.0, 200.0])          # the trail

    def dist_seg(p):
        t = np.clip(np.dot(p - p0, p1 - p0) / np.dot(p1 - p0, p1 - p0), 0, 1)
        return float(np.linalg.norm(p - (p0 + t * (p1 - p0))))
    stars_ = []
    while len(stars_) < 32:
        p = rng.uniform([10, 10], [W - 10, H - 10])
        if dist_seg(p) < 10 or any(np.hypot(*(p - q[:2])) < 14 for q in stars_):
            continue
        stars_.append(np.array([p[0], p[1], rng.uniform(220, 1400)]))
    stars_ = np.array(stars_)
    yy, xx = np.indices((H, W))
    img = 20.0 + 70.0 * np.exp(-((xx - 330.0) ** 2 + (yy - 40.0) ** 2) / (2 * 90.0 ** 2))
    erf = np.vectorize(math.erf)
    for u, v, F in stars_:
        xs, ys = np.arange(int(u) - 6, int(u) + 7), np.arange(int(v) - 6, int(v) + 7)
        gx = 0.5 * (erf((xs + 0.5 - u) / math.sqrt(2)) - erf((xs - 0.5 - u) / math.sqrt(2)))
        gy = 0.5 * (erf((ys + 0.5 - v) / math.sqrt(2)) - erf((ys - 0.5 - v) / math.sqrt(2)))
        okx, oky = (xs >= 0) & (xs < W), (ys >= 0) & (ys < H)
        img[np.ix_(ys[oky], xs[okx])] += (F * np.outer(gy, gx))[np.ix_(oky, okx)]
    trail = np.zeros((H, W), np.uint8)
    cv2.line(trail, tuple(int(x) for x in p0), tuple(int(x) for x in p1), 255, 2, lineType=cv2.LINE_AA)
    img += 70.0 * trail / 255.0
    img += rng.normal(0, 2.5, img.shape)
    out = np.clip(np.round(img), 0, 255).astype(np.uint8)
    hots = []
    while len(hots) < 12:
        p = rng.integers([3, 3], [W - 3, H - 3])
        if dist_seg(p.astype(float)) < 8 or np.min(np.hypot(stars_[:, 0] - p[0], stars_[:, 1] - p[1])) < 8:
            continue
        hots.append(p)
        out[p[1], p[0]] = int(rng.integers(150, 256))
    return out, stars_, np.array(hots), (p0, p1, dist_seg)


def det_arrays(got, what="detect_stars"):
    if not (isinstance(got, (tuple, list)) and len(got) == 2):
        raise CheckFailed(f"{what} should return (pts, flux), got {type(got).__name__}")
    try:
        pts, flux = np.asarray(got[0], dtype=float), np.asarray(got[1], dtype=float)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return two numpy arrays: pts (N × 2) and flux (N)")
    if pts.size == 0:
        pts = pts.reshape(0, 2)
    if pts.ndim != 2 or pts.shape[1] != 2 or flux.shape != (len(pts),):
        raise CheckFailed(f"{what} should return pts of shape (N, 2) and flux of shape (N,); got {pts.shape} and {flux.shape}")
    return pts, flux


@c.test("TODO 5: detect_stars() on an unseen night image — glow, hot pixels, a trail; centres to a tenth of a pixel",
        hint="Lesson §4: background = cv2.medianBlur(gray, 21); residual in float; σ = 1.4826 × MAD; mask = residual > "
             "k_sigma·σ; cv2.connectedComponentsWithStats; keep min_area ≤ area ≤ max_area; centre = brightness-weighted "
             "mean (residual as weights); flux = sum of the residual; brightest first.")
def _():
    (f,) = functions("detect_stars")
    tiny = np.zeros((11, 11), np.uint8)
    tiny[4:7, 3:6] = [[0, 10, 0], [10, 60, 30], [0, 10, 0]]
    pts, flux = det_arrays(go(f, tiny))
    if len(pts) == 0:
        raise CheckFailed("nothing found on a black image with one bright star: is your σ the ROBUST one (1.4826 × MAD)? "
                          "np.std is inflated by the star itself, and the threshold ends up above it")
    if len(pts) == 1 and abs(pts[0, 0] - 4.16667) > 1e-3 and abs(pts[0, 0] - 4.16667) < 0.02 and abs(pts[0, 1] - 5.0) < 0.02:
        raise CheckFailed(f"almost: the centre is {pts[0].round(4).tolist()} instead of about (4.167, 5.0). Is your background a "
                          "MEDIAN (cv2.medianBlur)? A mean or Gaussian blur is pulled up by the star's own light")
    if len(pts) == 1 and abs(pts[0, 0] - 5.0) < 1e-6 and abs(pts[0, 1] - 4.1667) < 1e-3:
        raise CheckFailed("u and v are swapped: u is the COLUMN (x), v the ROW (y)")
    if len(pts) == 1 and abs(pts[0, 0] - 4.0) < 1e-6 and abs(pts[0, 1] - 5.0) < 1e-6:
        raise CheckFailed("a lone star gives its PLAIN centre (4.0, 5.0): weight each pixel by its brightness above the "
                          "background (the weighted centre is (4.167, 5.0))")
    c.ok(len(pts) == 1 and abs(pts[0, 0] - 4.16667) < 1e-3 and abs(pts[0, 1] - 5.0) < 1e-3,
         f"on a black image with one 5-pixel star (values 10, 10, 60, 30, 10 around column 4, row 5) detect_stars returns "
         f"{np.round(pts, 4).tolist()}: expected one centre near (4.167, 5.0)")
    one_hot = tiny.copy()
    one_hot[1, 9] = 200
    pts1, _ = det_arrays(go(f, one_hot, min_area=1))
    pts3, _ = det_arrays(go(f, one_hot))
    if len(pts3) == 2:
        raise CheckFailed("a single hot pixel (1 pixel) is reported as a star: keep objects of min_area to max_area pixels")
    c.ok(len(pts1) == 2, "detect_stars(…, min_area=1) must also keep 1-pixel objects: use the min_area argument, do not "
                         "write the number 3 in the code")
    img, S_, hots, (p0, p1, dist_seg) = render_night()
    pts, flux = det_arrays(go(f, img, seconds=60))
    if len(flux) > 1 and np.any(np.diff(flux) > 1e-9):
        raise CheckFailed("the stars are not sorted brightest first: order them by flux, decreasing (np.argsort(-flux))")
    d_true = np.array([np.hypot(pts[:, 0] - u, pts[:, 1] - v).min() if len(pts) else 99.0 for u, v, _ in S_])
    d_swap = np.array([np.hypot(pts[:, 1] - u, pts[:, 0] - v).min() if len(pts) else 99.0 for u, v, _ in S_])
    if np.mean(d_swap < 1.0) > 0.8 and np.mean(d_true < 1.0) < 0.5:
        raise CheckFailed("u and v are swapped: pts[:, 0] is the column (x), pts[:, 1] the row (y)")
    far = [p for p in pts if np.hypot(S_[:, 0] - p[0], S_[:, 1] - p[1]).min() > 3.0]
    if len(far) > 60:
        raise CheckFailed(f"{len(pts)} detections on an image with {len(S_)} stars, {len(far)} of them noise: did you subtract "
                          "two uint8 arrays? On uint8, 19 − 20 = 255. Convert to float first: gray.astype(float) - bg")
    on_hot = [p for p in far if np.hypot(hots[:, 0] - p[0], hots[:, 1] - p[1]).min() < 1.5]
    on_trail = [p for p in far if dist_seg(np.asarray(p, dtype=float)) < 4.0]
    if on_hot:
        raise CheckFailed(f"{len(on_hot)} hot pixels (single bright pixels) are reported as stars: refuse objects smaller "
                          "than min_area pixels")
    if on_trail:
        raise CheckFailed("the aircraft trail is reported as a star: refuse objects larger than max_area pixels")
    if far:
        raise CheckFailed(f"{len(far)} detections are more than 3 px from every star — noise or glow kept as stars? "
                          "Subtract the LOCAL background (median filter) and use a robust σ (MAD)")
    missed = S_[d_true > 1.0]
    if len(missed):
        in_glow = [s for s in missed if math.hypot(s[0] - 330.0, s[1] - 40.0) < 160]
        if in_glow and len(in_glow) >= len(missed) / 2:
            raise CheckFailed(f"{len(missed)} of {len(S_)} stars are missed, most of them in the glowing corner: subtract "
                              "the LOCAL background (cv2.medianBlur over a large window), not one level for the whole image")
        raise CheckFailed(f"{len(missed)} of {len(S_)} stars (some faint) are missed: threshold at k_sigma × a ROBUST σ of the "
                          "background-subtracted image (σ = 1.4826 × MAD)")
    err = d_true
    rms = math.sqrt(float(np.mean(err ** 2)))
    if rms > 0.12:
        raise CheckFailed(f"the centres are {rms:.2f} px RMS from the true ones: weight each pixel by its brightness ABOVE "
                          "the background (the residual), not the plain centre and not the raw brightness")
    match = [int(np.argmin(np.hypot(S_[:, 0] - p[0], S_[:, 1] - p[1]))) for p in pts]
    r_got = np.argsort(np.argsort(-flux))
    r_true = np.argsort(np.argsort(-S_[match, 2]))
    c.ok(float(np.corrcoef(r_got, r_true)[0, 1]) > 0.95, "the flux does not follow the stars' brightness: the flux is the "
                                                         "SUM of the star's pixels above the background")


def quat_rotate(q, v):
    x, y, z, w = q
    u = np.array([x, y, z])
    v = np.asarray(v, dtype=float)
    return v + 2.0 * np.cross(u, np.cross(u, v) + w * v)


@c.test("TODO 6: boresight_altaz() on unseen attitudes and camera mounts",
        hint="Lesson §6: v = q_rotate(q_body, cam_axis_body) in ENU (east, north, up); alt = asin(up) in degrees; "
             "azimuth = atan2(east, north) in degrees, % 360 (a heading).")
def _():
    (f,) = functions("boresight_altaz")
    for k in E["boresight"]:
        got = go(f, k["q"], k["axis"])
        if not (isinstance(got, (tuple, list)) and len(got) == 2):
            raise CheckFailed(f"boresight_altaz should return (alt_deg, az_deg), got {got!r}")
        a, z = num(got[0], "boresight_altaz (alt)"), num(got[1], "boresight_altaz (az)")
        wa, wz = k["want"]
        if abs(a - wa) < 1e-6 and abs(wrap180(z - (90.0 - wz))) < 1e-6 and abs(wrap180(wz - 45.0)) > 1e-3:
            raise CheckFailed("the azimuth is measured from EAST counter-clockwise: azimuth = atan2(east, north)")
        q = np.array(k["q"])
        v0 = quat_rotate(q, (0.0, 0.0, 1.0))
        if abs(a - math.degrees(math.asin(max(-1, min(1, v0[2]))))) < 1e-6 and abs(a - wa) > 1e-3:
            raise CheckFailed("you rotated (0, 0, 1): rotate the camera's axis cam_axis_body (the argument)")
        vi = quat_rotate(q * np.array([-1, -1, -1, 1]), k["axis"])
        vi = vi / np.linalg.norm(vi)
        if abs(a - math.degrees(math.asin(max(-1, min(1, vi[2]))))) < 1e-6 and abs(a - wa) > 1e-3:
            raise CheckFailed("you rotated by the INVERSE attitude: q is body → world, so q_rotate(q_body, axis)")
        if not 0.0 <= z < 360.0:
            raise CheckFailed(f"the azimuth {z:.2f} is outside [0, 360): use % 360.0")
        c.ok(abs(a - wa) < 1e-6 and abs(wrap180(z - wz)) < 1e-6,
             f"boresight_altaz on an unseen attitude gives ({a:.3f}, {z:.3f})° instead of ({wa:.3f}, {wz:.3f})°")


@c.test("TODO 7: both_roots() on unseen directions — two roots, one root, no root, across the 180° meridian",
        hint="Lesson §6: p = sin a, q = cos a cos A, R = √(p² + q²), ψ = atan2(q, p); no root if |sin δ| > R; x = asin(sin δ/R); "
             "φ = x − ψ and 180° − x − ψ (keep |φ| ≤ 90°); H = atan2(−cos a sin A, sin a cos φ − cos a sin φ cos A); "
             "λ = α + H − gst wrapped to [−180, 180). The asin root first.")
def _():
    (f,) = functions("both_roots")
    for k in E["roots"]:
        got = go(f, *k["args"])
        if got is None:
            raise CheckFailed("both_roots returned None: return a list — [] when there is no root")
        if not isinstance(got, (list, tuple)):
            raise CheckFailed(f"both_roots should return a list of (lat, lon) tuples, got {got!r}")
        try:
            g = [(float(r[0]), float(r[1])) for r in got]
        except (TypeError, ValueError, IndexError):
            raise CheckFailed(f"both_roots should return a list of (lat, lon) tuples, got {got!r}")
        want = [tuple(w) for w in k["want"]]
        if any(abs(r[0]) > 90.0 + 1e-9 for r in g):
            raise CheckFailed("a root has |latitude| > 90°: keep only the valid roots (|φ| ≤ 90°) — if φ is still in "
                              "radians there, compare with math.pi / 2 or convert first")
        if any(not -180.0 <= r[1] < 180.0 for r in g):
            same = len(g) == len(want) and all(abs(r[0] - w[0]) < 1e-6 and abs(wrap180(r[1] - w[1])) < 1e-6
                                               for r, w in zip(g, want))
            raise CheckFailed("a longitude is outside [−180, 180)" + (": wrap it, (lon + 180) % 360 − 180" if same else ""))
        if len(want) == 2 and len(g) == 1 and abs(g[0][0] - want[0][0]) < 1e-6:
            a_, A_, _, d_, _ = k["args"]
            p_, q_ = math.sin(math.radians(a_)), math.cos(math.radians(a_)) * math.cos(math.radians(A_))
            raw2 = (180.0 - math.degrees(math.asin(math.sin(math.radians(d_)) / math.hypot(p_, q_)))
                    - math.degrees(math.atan2(q_, p_)))
            if abs(raw2) > 180.0:
                raise CheckFailed(f"the second root is {raw2:.1f}° before wrapping, i.e. {wrap180(raw2):.1f}°: wrap φ into "
                                  "[−180°, 180°) BEFORE the |φ| ≤ 90° test (lesson §6)")
            raise CheckFailed("only the asin root: the altitude equation has TWO solutions, x and 180° − x (lesson §6)")
        if len(want) == 2 and len(g) == 2 and all(abs(r[0] - w[0]) < 1e-6 for r, w in zip(g[::-1], want)):
            raise CheckFailed("the roots are in the other order: the asin root (x − ψ) first")
        if len(g) == len(want) and all(abs(r[0] - w[0]) < 1e-6 for r, w in zip(g, want)):
            if not all(abs(wrap180(r[1] - w[1])) < 1e-6 for r, w in zip(g, want)):
                raise CheckFailed("the latitudes are right but a longitude is not: λ = α + H − gst, with "
                                  "H = atan2(−cos a sin A, sin a cos φ − cos a sin φ cos A) for EACH root")
        c.ok(len(g) == len(want) and all(abs(r[0] - w[0]) < 1e-6 and abs(wrap180(r[1] - w[1])) < 1e-6
                                         for r, w in zip(g, want)),
             f"both_roots{tuple(round(x, 3) for x in k['args'])} returns {[(round(a, 3), round(b, 3)) for a, b in g]}: "
             f"expected {len(want)} root(s)")


@c.test("TODO 8: choose() on unseen roots and priors — ambiguous, too far, near the pole, across the 180° meridian",
        hint="Lesson §6: keep the roots within max_sep_deg of the prior, measured on the sphere with the given sep_deg; "
             "exactly one → that root, else None.")
def _():
    (f,) = functions("choose")
    msgs = {1: "both roots are within max_sep_deg of the prior: the prior cannot tell them apart → return None",
            3: "the root is 1.8° from the prior across the 180° meridian: measure with sep_deg (on the sphere), not with "
               "latitude/longitude differences",
            4: "the root is 4.5° from the prior across the North Pole: measure with sep_deg (on the sphere), not with "
               "latitude/longitude differences",
            5: "the only root is 10° from the prior: farther than max_sep_deg → return None, not the nearest one",
            2: "with max_sep_deg = 0.5 the root (64.17, −21.98) is 0.38° from the prior (64.0, −21.2) on the sphere: at "
               "64° N one degree of longitude is only cos 64° = 0.44° of arc — measure with sep_deg, not with "
               "latitude/longitude differences, and use the max_sep_deg argument"}
    for i, ((roots, plat, plon, ms), want) in enumerate(E["choose"]):
        got = go(f, [tuple(r) for r in roots], plat, plon, ms)
        if want is None:
            c.ok(got is None, msgs.get(i, f"choose({roots}, {plat}, {plon}, {ms}) should return None, got {got!r}"))
            continue
        if got is None or not (isinstance(got, (tuple, list)) and len(got) == 2):
            raise CheckFailed(msgs.get(i, f"choose({roots}, {plat}, {plon}, {ms}) should return the root {tuple(want)}, "
                                          f"got {got!r}"))
        c.ok(abs(float(got[0]) - want[0]) < 1e-9 and abs(float(got[1]) - want[1]) < 1e-9,
             f"choose({roots}, {plat}, {plon}, {ms}) returned {got!r} instead of {tuple(want)}")


@c.test("TODO 9: error_km() on unseen attitude errors and camera altitudes",
        hint="Lesson §7: KM_PER_DEG × √(tilt² + (heading × cos alt)²), alt turned into radians inside cos.")
def _():
    (f,) = functions("error_km")
    for (t, h, a), want in E["error_km"]:
        got = num(go(f, t, h, a), "error_km")
        if abs(got - KM * (t + h * math.cos(math.radians(a)))) < 1e-6 and t * h * math.cos(math.radians(a)) > 1e-9:
            raise CheckFailed("the two errors are ADDED: independent errors combine as √(tilt² + (heading·cos alt)²)")
        if abs(got - KM * math.hypot(t, h)) < 1e-6 and abs(math.cos(math.radians(a)) - 1.0) > 1e-6 and h > 0:
            raise CheckFailed("the heading error is not multiplied by cos(alt): a camera at the zenith does not see it")
        if abs(got - KM * math.hypot(t, h * math.cos(a))) < 1e-6 and h > 0:
            raise CheckFailed("cos got degrees: math.cos(math.radians(alt_deg))")
        if abs(got - KM * math.hypot(t, h * math.sin(math.radians(a)))) < 1e-6 and h > 0 and a != 45.0:
            raise CheckFailed("the heading term uses sin(alt): it is cos(alt) — a camera at the zenith (alt 90°) does not "
                              "see the heading at all")
        c.ok(abs(got - want) < 1e-6, f"error_km({t}, {h}, {a}) gives {got:.3f} km")


def student_detect_photo1():
    import cv2
    img = cv2.imread(f"{DATA}/photos/night_01.png", cv2.IMREAD_GRAYSCALE)
    if img is None:
        c.skip("the course data is not mounted here (tell your teacher)")
    (f,) = functions("detect_stars")
    pts, _ = det_arrays(go(f, img, seconds=60))
    rows = list(csv.DictReader(open(f"{DATA}/photo01_stars.csv")))
    errs = []
    for r in rows:
        if float(r["vmag"]) > 5.0 or not len(pts):
            continue
        d = np.hypot(pts[:, 0] - float(r["u_px"]), pts[:, 1] - float(r["v_px"])).min()
        if d <= 2.0:
            errs.append(d)
    return len(pts), (math.sqrt(float(np.mean(np.square(errs)))) if errs else float("nan"))


@c.test("Steps 5–6: your detector on photo 1, and what one pixel is worth — numbers and explanation",
        hint="python3 run_stars.py detect: how many stars, and the centre error RMS. python3 run_stars.py solve: the fit "
             "residual and one pixel in ′ (PREDICT_PIXEL before). EXPLAIN_CENTROID: brightness weighting (a fraction of a pixel), hot "
             "pixels and the trail (size limits), the glowing corner (local background).")
def _():
    pred, n, rms, why, pp, srms, parc = answers("PREDICT_DETECT", "N_STARS_01", "CENTROID_RMS_PX", "EXPLAIN_CENTROID",
                                                "PREDICT_PIXEL", "SOLVE_RMS_ARCSEC", "PIXEL_ARCMIN")
    predicted("PREDICT_PIXEL", pp)
    predicted("PREDICT_DETECT", pred)
    mine_n, mine_rms = student_detect_photo1()
    n = number(n, "N_STARS_01")
    c.ok(n == mine_n, f"N_STARS_01 = {n:g}, but your detect_stars finds {mine_n} stars in photo 1 now: run "
                      "python3 run_stars.py detect again and copy its number")
    c.ok(math.isfinite(mine_rms) and mine_rms < 0.3, "your detector's centres in photo 1 are far from the truth: check TODO 5")
    c.near(number(rms, "CENTROID_RMS_PX"), mine_rms, 0.002, "CENTROID_RMS_PX (what run_stars.py detect prints for YOUR detector)")
    explained("EXPLAIN_CENTROID", why,
              ((r"weight", r"bright", r"intensit", r"flux", r"sub.?pixel", r"fraction", r"pulls", r"more light"),
               'why weight the centre (e.g. "brighter pixels count more: the centre to a fraction of a pixel")'),
              ((r"hot", r"trail", r"aircraft", r"plane", r"single pixel", r"one pixel", r"size", r"area", r"too (small|large|big)"),
               'what the size limits refuse (e.g. "a hot pixel is 1 pixel, a trail hundreds")'),
              ((r"background", r"glow", r"corner", r"local", r"median", r"not flat", r"brighter (sky|part)"),
               'why the background must be local (e.g. "the glowing corner raises the background")'))
    srms = number(srms, "SOLVE_RMS_ARCSEC")
    c.ok(10.0 < srms < 60.0 and abs(srms - LAB["SOLVE_RMS_ARCSEC"]) < 8.0,
         f"SOLVE_RMS_ARCSEC = {srms:g}: copy the fit residual (″) of python3 run_stars.py solve")
    parc = number(parc, "PIXEL_ARCMIN")
    if abs(parc - 60.0 * 60.0 / 1280.0) < 0.01:
        raise CheckFailed("PIXEL_ARCMIN = 2.81′ is 60°/1280, the AVERAGE over the width: copy what `solve` prints for the "
                          "image centre (atan(1/f))")
    c.near(parc, LAB["PIXEL_ARCMIN"], 0.01, "PIXEL_ARCMIN (′)")


@c.test("Step 8: the fixes — median, no position, perfect attitude, magnetic north, one root — and why",
        hint="python3 run_stars.py fix (median error, the photo with no position), fix truth (largest error), fix magnetic "
             "(photo 1: the error to the truth AND how far the fix moved), fix oneroot (photo 3). TRACE_PSI_DEG = atan2(cos a cos A, sin a) with a = 37.13°, A = 295.02°.")
def _():
    tp, med, nofix, perf, pm, mag, one, w1, w2 = answers(
        "TRACE_PSI_DEG", "MEDIAN_FIX_KM", "NO_FIX_PHOTO", "PERFECT_MAX_KM", "PREDICT_MAGNETIC", "MAGNETIC_ERR_01_KM",
        "ONE_ROOT_ERR_03_KM", "EXPLAIN_ROOTS", "EXPLAIN_NORTH")
    tp = number(tp, "TRACE_PSI_DEG")
    if abs(tp - (90.0 - LAB["TRACE_PSI_DEG"])) < 0.05:
        raise CheckFailed("TRACE_PSI_DEG: ψ = atan2(q, p) with q = cos a·cos A FIRST and p = sin a second")
    c.near(tp, LAB["TRACE_PSI_DEG"], 0.03, "TRACE_PSI_DEG (degrees)")
    c.near(number(med, "MEDIAN_FIX_KM"), LAB["MEDIAN_FIX_KM"], 2.0, "MEDIAN_FIX_KM (fix: the median error, km)")
    nofix = number(nofix, "NO_FIX_PHOTO")
    c.ok(nofix in LAB["NO_FIX_PHOTO"], f"NO_FIX_PHOTO = {nofix:g}: which photo says 'no position' in python3 run_stars.py fix?")
    perf = number(perf, "PERFECT_MAX_KM")
    c.ok(0.0 < perf < 1.0, f"PERFECT_MAX_KM = {perf:g} km: copy the largest error of python3 run_stars.py fix truth")
    predicted("PREDICT_MAGNETIC", pm)
    mag = number(mag, "MAGNETIC_ERR_01_KM")
    mv = number(answers("MAGNETIC_MOVE_01_KM")[0], "MAGNETIC_MOVE_01_KM")
    if abs(mag - LAB["MAGNETIC_MOVE_01_KM"]) < 3.0 and abs(mv - LAB["MAGNETIC_ERR_01_KM"]) < 3.0:
        raise CheckFailed("MAGNETIC_ERR_01_KM and MAGNETIC_MOVE_01_KM are swapped")
    c.near(mag, LAB["MAGNETIC_ERR_01_KM"], 3.0, "MAGNETIC_ERR_01_KM (fix magnetic, photo 1: error to the truth, km)")
    c.near(mv, LAB["MAGNETIC_MOVE_01_KM"], 3.0, "MAGNETIC_MOVE_01_KM (fix magnetic, photo 1: moved from `fix`, km)")
    c.near(number(one, "ONE_ROOT_ERR_03_KM"), LAB["ONE_ROOT_ERR_03_KM"], 20.0, "ONE_ROOT_ERR_03_KM (fix oneroot, photo 3, km)")
    explained("EXPLAIN_ROOTS", w1,
              ((r"two", r"both", r"twice", r"180", r"sine", r"sin", r"mirror", r"same (alt|value|measure)"),
               'why one direction fits two places (e.g. "sin takes each value twice: x and 180° − x")'),
              ((r"asin", r"first root", r"one root", r"only", r"range", r"−90|-90", r"90", r"wrong root", r"other side"),
               'why the asin root is wrong for photo 3 (e.g. "asin only returns x in [−90°, 90°], the true one is 180° − x")'),
              ((r"prior", r"5 ?°", r"5 deg", r"close", r"near", r"cannot tell", r"can't tell", r"no root", r"ambigu", r"both"),
               'why photo 6 gives no position (e.g. "the roots are too close to the prior to tell apart")'))
    explained("EXPLAIN_NORTH", w2,
              ((r"declination", r"magnetic", r"3\.3", r"true north", r"heading"), 'what forgetting the declination does '
               '(e.g. "the heading is 3.34° off")'),
              ((r"cos", r"111", r"km", r"azimuth", r"direction", r"sideways", r"attitude", r"degree", r"adds", r"plus",
                r"move", r"stretch", r"same direction", r"imu"),
               'why that is so many km (e.g. "3.34° × cos(66°) × 111 km, added to the IMU\'s own error")'),
              ((r"prior", r"5 ?°", r"far", r"no position", r"refus", r"none", r"larger declination", r"−26|-26",
                r"cape town", r"−11|-11", r"−5|-5", r"bigger"),
               'why photos 3–5 give nothing (e.g. "their declinations are larger, the roots fall beyond 5° of the prior")'))


@c.test("Step 9: the error budget — formula, simulation, the mounting bias — and why they differ",
        hint="python3 run_stars.py budget: your formula, the RMS and the median. MOUNT_BIAS_MAX_DEG: 55 km / 111.2 km per "
             "degree. EXPLAIN_BUDGET: the heading term, the elongated spread, the sideways stretch.")
def _():
    pred, fk, rms, med, mount, why = answers("PREDICT_BUDGET", "FORMULA_KM", "MC_RMS_KM", "MC_MEDIAN_KM",
                                             "MOUNT_BIAS_MAX_DEG", "EXPLAIN_BUDGET")
    predicted("PREDICT_BUDGET", pred)
    c.near(number(fk, "FORMULA_KM"), LAB["FORMULA_KM"], 0.2, "FORMULA_KM (your error_km, km)")
    rms, med = number(rms, "MC_RMS_KM"), number(med, "MC_MEDIAN_KM")
    if abs(rms - LAB["MC_MEDIAN_KM"]) < 1.5 and abs(med - LAB["MC_RMS_KM"]) < 1.5:
        raise CheckFailed("MC_RMS_KM and MC_MEDIAN_KM are swapped")
    c.near(rms, LAB["MC_RMS_KM"], 1.5, "MC_RMS_KM (km)")
    c.near(med, LAB["MC_MEDIAN_KM"], 1.5, "MC_MEDIAN_KM (km)")
    mount = number(mount, "MOUNT_BIAS_MAX_DEG")
    c.near(mount, LAB["MOUNT_BIAS_MAX_DEG"], 0.005, "MOUNT_BIAS_MAX_DEG (degrees: 55 km at 111.2 km per degree)")
    explained("EXPLAIN_BUDGET", why,
              ((r"heading", r"1\.5", r"cos", r"azimuth", r"yaw"), 'which term dominates (e.g. "the 1.5° heading error, '
               'even × cos 66°")'),
              ((r"tail", r"outlier", r"large error", r"big error", r"square", r"skew", r"few", r"rare", r"extreme",
                r"elongat", r"ellips", r"one direction", r"spread", r"0\.83"),
               'why the median is below the RMS (e.g. "the error spreads mostly in one direction, and the RMS squares the '
               'big ones")'),
              ((r"pole", r"sideways", r"longitude", r"cos.*dec", r"stretch", r"approximat", r"rule of thumb", r"hour angle",
                r"cos ?h\b", r"1\.3", r"fold", r"0\.83", r"gaussian",
                r"not (exactly|linear)", r"geometry", r"assum", r"simplif"),
               'why formula and simulation differ (e.g. "the rule assumes 1:1, but sideways errors are stretched")'))


@c.test("Step 10: the star-fix memo in report.md",
        hint="Keep the three headings; 150–350 words in your own words; quote the median fix error with the IMU (km), the "
             "largest error with a perfect attitude (km), and the cost of one degree (km).")
def _():
    try:
        text = open("report.md", encoding="utf-8").read()
    except FileNotFoundError:
        raise CheckFailed("report.md is missing")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for h in ("## The sky's clock and a star's place", "## From a photo to a position", "## How good is it?"):
        c.ok(h in body, f"report.md must keep the heading '{h}'")
    words = re.findall(r"[A-Za-zÀ-ÿ0-9°'′.-]+", re.sub(r"^#.*$", "", body, flags=re.M))
    c.ok(len(words) >= 150, f"report.md has {len(words)} words: write at least 150")
    c.ok(len(words) <= 420, f"report.md has {len(words)} words: a memo is short — aim for 350 (the limit is 420)")
    low = body.lower()
    c.ok(re.search(r"\b1(1[0-9]|2[0-5])(\.\d+)?\s*km", low) is not None,
         "quote the median fix error with the IMU, in km (python3 run_stars.py fix)")
    c.ok(re.search(r"\b0\.\d+\s*km", low) is not None, "quote the largest error with a perfect attitude, in km (fix truth)")
    c.ok(re.search(r"\b111(\.\d+)?\s*km", low) is not None, "quote the cost of one degree of attitude, in km")


c.milestone("stargazer", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "Steps 1–2", "Steps 3–4", label="Stargazer")
c.milestone("navigator", "TODO", "Step", label="Star navigator")
c.run()
