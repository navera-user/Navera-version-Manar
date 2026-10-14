"""run_stars.py — runs YOUR functions of navera_lite/stars.py on the sky and on star photos, and draws the results.

    python3 run_stars.py test                 check each function on its docstring example (and a few traps)
    python3 run_stars.py look                 the star catalogue                                       (Step 1)
    python3 run_stars.py clock                Julian date, sidereal time, Vega's transit, precession   (Step 2)
    python3 run_stars.py sky PLACE            the sky over a place: sousse, capetown, reykjavik, quito, sydney (Step 3)
    python3 run_stars.py polaris              latitude from Polaris at four places through a night     (Step 4)
    python3 run_stars.py detect [N]           find the stars in photo N (1–6, default 1)               (Step 5)
    python3 run_stars.py solve [N]            identify them: where does the camera point?              (Step 6)
    python3 run_stars.py fix [OPTION]         a position from each photo; OPTION: truth, magnetic, oneroot,
                                              truth refraction                             (Step 8)
    python3 run_stars.py budget [N]           attitude errors → position errors, 2 000 random draws    (Step 9)

Data: /data/academy/26-stars/ (read only). Pictures are saved in out/ — click them in the 📝 Code tab.
"""
import csv
import json
import math
import os
import sys

import numpy as np

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

DATA = os.environ.get("STARS_DATA", "/data/academy/26-stars")
st = rk.load_student("navera_lite.stars")
cam = rk.load_student("navera_lite.camera")
imu = rk.load_student("navera_lite.imu")
YEAR = 2026.80                                     # the date of the photos as a decimal year (for the declination)
PLACES = {                                         # name, lat, lon, UTC (y, mo, d, h, mi, s)
    "sousse": ("Sousse, Tunisia (NAVERA's test area)", 35.83, 10.64, (2026, 10, 20, 20, 30, 0)),
    "capetown": ("Cape Town, South Africa", -33.92, 18.42, (2026, 10, 20, 20, 0, 0)),
    "reykjavik": ("Reykjavik, Iceland", 64.15, -21.94, (2026, 10, 21, 0, 30, 0)),
    "quito": ("Quito, Ecuador (on the equator)", -0.18, -78.47, (2026, 10, 21, 3, 0, 0)),
    "sydney": ("Sydney, Australia", -33.87, 151.21, (2026, 10, 20, 12, 0, 0)),
}


def need_data(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"{path} is missing: the course data is not mounted here (tell your teacher)")
    return path


def catalogue(mag_max=6.5):
    return st.load_catalogue(need_data("bright_stars.csv"), mag_max=mag_max)


def stub(name):
    f = getattr(st, name, None)
    if f is None:
        sys.exit(f"{name}() does not exist in navera_lite/stars.py — did you rename it?")
    return rk.is_stub(f)


def needs(*names):
    for n in names:
        if stub(n):
            sys.exit(f"{n}() is not written yet: write its TODO in navera_lite/stars.py first "
                     "(python3 run_stars.py test shows which ones work)")


def num(v, fn):
    if isinstance(v, bool) or v is None:
        sys.exit(f"{fn}() must return a number, but it returned {v!r}")
    try:
        x = float(v)
    except (TypeError, ValueError):
        sys.exit(f"{fn}() must return one number, but it returned {v!r}")
    if not math.isfinite(x):
        sys.exit(f"{fn}() returned {x}: not a usable number")
    return x


def pair(v, fn, what="(alt_deg, az_deg)"):
    if not (isinstance(v, (tuple, list)) and len(v) == 2):
        sys.exit(f"{fn}() must return two values {what}, but it returned {v!r}")
    return v


def jd_of(utc):
    return num(rk.need_ok(st, "julian_date", *utc), "julian_date")


def gst_of(jd):
    return num(rk.need_ok(st, "gmst_deg", jd), "gmst_deg")


def plt_ready():
    plt = rk.plt_or_none()
    if plt is not None:
        os.makedirs("out", exist_ok=True)
    return plt


def photos():
    with open(need_data("photos.json")) as f:
        return json.load(f)


def wrap180(x):
    return (x + 180.0) % 360.0 - 180.0


# ------------------------------------------------------------------------------------------- test
def attempt(fn, name, none_ok=False):
    import contextlib
    import io
    import traceback
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            v = fn()
    except NotImplementedError:
        return None, "it is not written yet"
    except Exception as e:
        tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename.endswith(os.path.join("navera_lite", "stars.py"))]
        where = f" (navera_lite/stars.py line {tb[-1].lineno}, in {tb[-1].name}())" if tb else ""
        s = str(e)
        hint = rk._hint(e)
        if "only length-1 arrays" in s or "only size-1 arrays" in s:
            hint = " — math.sin/math.cos take single numbers: use np.sin, np.cos, np.arctan2 so arrays work too"
        elif "math domain error" in s:
            hint = " — asin got a value beyond ±1: when |sin δ| > R there is no root at all: return []"
        elif "truth value of an array" in s:
            hint = " — an `if` on a numpy array: work on whole arrays with np.where, or compare single numbers"
        return None, f"{name}() stopped with {type(e).__name__}: {e}{where}{hint}"
    if v is None and not none_ok:
        return None, f"{name}() returned None: every path must end with a `return`"
    return v, None


def near(a, b, tol):
    return abs(float(a) - float(b)) <= tol


def test():
    cases = []          # (TODO, function, label, call, check(result) -> (ok, note))

    def number(want, tol, msgs=(), deg360=False):
        def chk(v):
            try:
                x = float(v)
            except (TypeError, ValueError):
                return False, f"expected one number, got {v!r}"
            if deg360 and not 0.0 <= x < 360.0:
                return False, f"{x:.4f} is outside [0, 360): use % 360.0"
            for bad, m in msgs:
                if near(x, bad, tol):
                    return False, m
            return near(x, want, tol), None
        return chk

    def two(want, tol, msgs=()):
        def chk(v):
            if not (isinstance(v, (tuple, list)) and len(v) == 2):
                return False, f"expected two values, got {v!r}"
            try:
                a, b = (np.asarray(x, dtype=float) for x in v)
            except (TypeError, ValueError):
                return False, f"expected two numbers or two arrays, got {v!r}"
            for (ba, bb), m in msgs:
                if np.allclose(a, ba, atol=tol) and np.allclose(b, bb, atol=tol):
                    return False, m
            return bool(np.allclose(a, want[0], atol=tol) and np.allclose(b, want[1], atol=tol)), None
        return chk

    def roots_chk(want, msgs=()):
        def chk(v):
            if not isinstance(v, (list, tuple)):
                return False, f"expected a list of (lat, lon) tuples, got {v!r}"
            try:
                got = [(float(r[0]), float(r[1])) for r in v]
            except (TypeError, ValueError, IndexError):
                return False, f"expected a list of (lat, lon) tuples, got {v!r}"
            if any(abs(g[0]) > 90.0 + 1e-9 for g in got):
                return False, (f"a root has latitude beyond ±90° {[(round(a, 2), round(b, 2)) for a, b in got]}: keep only "
                               "the valid roots, |φ| ≤ 90° (lesson §6)")
            for bad, m in msgs:
                if len(got) == len(bad) and all(near(g[0], b[0], 0.02) and near(g[1], b[1], 0.02) for g, b in zip(got, bad)):
                    return False, m
            if len(got) != len(want):
                return False, f"expected {len(want)} root(s), got {len(got)}: {[(round(a, 2), round(b, 2)) for a, b in got]}"
            return all(near(g[0], w[0], 0.02) and near(g[1], w[1], 0.02) for g, w in zip(got, want)), \
                f"got {[(round(a, 2), round(b, 2)) for a, b in got]}"
        return chk

    def choose_chk(want, why=None):
        def chk(v):
            if want is None:
                return v is None, (f"expected None (no position), got {v!r}" if v is not None else None)
            if v is None or not (isinstance(v, (tuple, list)) and len(v) == 2):
                return False, why or f"expected one (lat, lon) tuple, got {v!r}"
            return near(v[0], want[0], 1e-9) and near(v[1], want[1], 1e-9), None
        return chk

    def detect_chk(v):
        if not (isinstance(v, (tuple, list)) and len(v) == 2):
            return False, f"expected (pts, flux), got {v!r}"
        pts, flux = (np.asarray(x, dtype=float) for x in v)
        if pts.shape != (1, 2):
            return False, f"expected pts of shape (1, 2) for one star, got shape {pts.shape}"
        if near(pts[0, 0], 4.0, 1e-6) and near(pts[0, 1], 4.0909, 1e-3):
            return False, "u and v are swapped: u is the COLUMN (x), v the ROW (y)"
        if near(pts[0, 0], 4.0, 1e-6) and near(pts[0, 1], 4.0, 1e-6):
            return False, ("(4.0, 4.0) is the plain (unweighted) centre of the 3 × 3 block: weight each pixel by its "
                           "brightness above the background")
        return near(pts[0, 0], 4.0909, 1e-3) and near(pts[0, 1], 4.0, 1e-3) and near(flux[0], 220.0, 1e-6), \
            f"got pts {pts.round(4).tolist()}, flux {flux.round(2).tolist()}"

    def tiny():
        img = np.zeros((9, 9), dtype=np.uint8)
        img[3:6, 3:6] = [[10, 20, 10], [20, 80, 40], [10, 20, 10]]
        return img

    def hot():
        img = np.zeros((9, 9), dtype=np.uint8)
        img[3:6, 3:6] = [[10, 20, 10], [20, 80, 40], [10, 20, 10]]
        img[1, 7] = 200                                    # a hot pixel: one pixel only
        return img

    def grey():
        rng = np.random.default_rng(5)
        img = (20 + rng.integers(-2, 3, (40, 40))).astype(np.uint8)
        img[18:21, 18:21] += np.array([[10, 20, 10], [20, 80, 40], [10, 20, 10]], dtype=np.uint8)
        return img

    def grey_chk(v):
        if not (isinstance(v, (tuple, list)) and len(v) == 2):
            return False, f"expected (pts, flux), got {v!r}"
        pts = np.asarray(v[0], dtype=float).reshape(-1, 2)
        if len(pts) > 3:
            return False, (f"{len(pts)} 'stars' on a grey sky with ONE star: `gray - bg` on two uint8 arrays wraps around "
                           "below 0 (19 − 20 = 255): convert to float first, gray.astype(float) - bg")
        if len(pts) != 1:
            return False, f"expected 1 star, got {len(pts)}"
        return near(pts[0, 0], 19.09, 0.15) and near(pts[0, 1], 19.0, 0.15), \
            f"the centre {pts[0].round(3).tolist()} should be near (19.09, 19.00): subtract the background first"

    def hot_chk(v):
        if not (isinstance(v, (tuple, list)) and len(v) == 2):
            return False, f"expected (pts, flux), got {v!r}"
        pts = np.asarray(v[0], dtype=float).reshape(-1, 2)
        if len(pts) == 2:
            return False, "the hot pixel (one pixel, area 1) was kept as a star: keep groups of min_area to max_area pixels"
        return len(pts) == 1, f"expected 1 star, got {len(pts)}"

    cases += [
        (1, "julian_date", "julian_date(2000, 1, 1, 12) — J2000.0 (docstring)", lambda: st.julian_date(2000, 1, 1, 12),
         number(2451545.0, 1e-6, ((2451544.5, "0.5 day short: the hours are not added (h / 24)"),
                                  (2451544.0, "one day short: January and February count as months 13 and 14 of the "
                                              "PREVIOUS year")))),
        (1, "julian_date", "julian_date(2026, 10, 20, 20, 30) (docstring)", lambda: st.julian_date(2026, 10, 20, 20, 30),
         number(2461334.3541667, 1e-6, ((2461334.3458333, "the minutes count as hundredths of an hour: h + mi / 60"),
                                        (2461334.3333333, "30 minutes short: the minutes are not added — the time of "
                                                          "day is (h + mi / 60 + s / 3600) / 24"),
                                        (2461347.3541667, "13 days off: the Gregorian correction B = 2 − A + A // 4 is missing")))),
        (1, "julian_date", "julian_date(2026, 2, 14, 6) — January and February count as months 13 and 14",
         lambda: st.julian_date(2026, 2, 14, 6), number(2461085.75, 1e-6, ((2461082.75, "Jan/Feb: they count as months 13 "
                                                                              "and 14 of the PREVIOUS year"),))),
        (2, "gmst_deg", "gmst_deg(2451545.0) (docstring)", lambda: st.gmst_deg(2451545.0),
         number(280.46061837, 1e-6, deg360=True)),
        (2, "gmst_deg", "gmst_deg(2461334.3541667) (docstring)", lambda: st.gmst_deg(2461334.3541667),
         number(336.8118, 2e-4, ((22.4541, "these are HOURS (÷ 15): the function returns degrees"),), deg360=True)),
        (2, "gmst_deg", "gmst_deg on an array of two dates",
         lambda: st.gmst_deg(np.array([2451545.0, 2451546.0])),
         lambda v: (np.allclose(np.asarray(v, dtype=float), [280.46061837, 281.44626573], atol=1e-5),
                    "expected about [280.4606, 281.4463] — use numpy operations (and % 360.0) so arrays work")),
        (3, "altaz", "altaz: Vega from Sousse (docstring)", lambda: st.altaz(279.4596, 38.8078, 35.83, 10.64, 336.8118),
         two((37.13, 295.02), 0.01, (((37.13, -64.98), "the azimuth is negative: wrap it into [0, 360) with % 360.0"),
                                     ((37.13, 64.98), "the azimuth goes the wrong way round: it is clockwise from north "
                                                       "(atan2(−cos δ sin H, …), in that order)"),
                                     ((37.13, 115.02), "the azimuth is measured from SOUTH: north is 0°"),
                                     ((53.14, 289.00), "the longitude has the wrong sign: east is positive, LST = gst + lon")))),
        (3, "altaz", "altaz on arrays: Vega and Polaris at once",
         lambda: st.altaz(np.array([279.4596, 46.7679]), np.array([38.8078, 89.3747]), 35.83, 10.64, 336.8118),
         two(((37.13, 36.15), (295.02, 0.67)), 0.01)),
        (3, "altaz", "altaz: Canopus, below the horizon of Sousse (negative altitude)",
         lambda: st.altaz(96.1365, -52.7116, 35.83, 10.64, 336.8118), two((-38.54, 132.80), 0.01)),
        (4, "lat_from_polaris", "lat_from_polaris(50.0) — no hour angle (docstring)", lambda: st.lat_from_polaris(50.0),
         number(50.0, 1e-9)),
        (4, "lat_from_polaris", "lat_from_polaris(50.0, 60.0) (docstring)", lambda: st.lat_from_polaris(50.0, 60.0),
         number(49.68735, 1e-4, ((50.31265, "the correction has the wrong sign: Polaris is ABOVE the pole when H = 0, "
                                            "so φ = a − p·cos H"),
                                 (50.0 - 0.6253 * math.cos(60.0), "cos got DEGREES: math.cos(math.radians(ha_deg))")))),
        (5, "detect_stars", "detect_stars: one 3 × 3 star (docstring)", lambda: st.detect_stars(tiny()), detect_chk),
        (5, "detect_stars", "detect_stars: the same star and a hot pixel", lambda: st.detect_stars(hot()), hot_chk),
        (5, "detect_stars", "detect_stars: the same star on a grey, noisy sky (background about 20)",
         lambda: st.detect_stars(grey()), grey_chk),
        (6, "boresight_altaz", "boresight_altaz: level, nose north (docstring)",
         lambda: st.boresight_altaz((0.0, 0.0, 0.7071068, 0.7071068)),
         two((70.0, 0.0), 0.01, (((70.0, 90.0), "the azimuth is measured from EAST, counter-clockwise: azimuth = "
                                                "atan2(east, north)"),
                                 ((90.0, 0.0), "you rotated (0, 0, 1): rotate the camera's axis cam_axis_body")))),
        (6, "boresight_altaz", "boresight_altaz: level, nose east",
         lambda: st.boresight_altaz((0.0, 0.0, 0.0, 1.0)), two((70.0, 90.0), 0.01)),
        (7, "both_roots", "both_roots: Vega seen from Sousse (docstring)",
         lambda: st.both_roots(37.13, 295.02, 279.4596, 38.8078, 336.8118),
         roots_chk([(35.83, 10.64), (85.80, 54.66)], (([(35.83, 10.64)], "only one root: the altitude equation has TWO "
                                                                         "solutions, x and 180° − x (lesson §6)"),))),
        (7, "both_roots", "both_roots: a camera looking north, 55° high (the asin root is the wrong one)",
         lambda: st.both_roots(55.0, 0.0, 228.6, 75.35, 100.0),
         roots_chk([(40.35, 128.6), (69.65, -51.4)])),
        (7, "both_roots", "both_roots: one valid root only (the other latitude is beyond 90°), across the 180° meridian",
         lambda: st.both_roots(70.0, 95.0, 89.6092315, 7.6903777, 250.0),
         roots_chk([(10.0, 179.5)], (([(10.0, -180.5)], "the longitude is not wrapped into [−180, 180)"),))),
        (7, "both_roots", "both_roots: a direction that no latitude can give (|sin δ| > R)",
         lambda: st.both_roots(20.0, 90.0, 10.0, 80.0, 0.0), roots_chk([])),
        (8, "choose", "choose: max_sep_deg 1.0 (docstring)",
         lambda: st.choose([(35.8, 10.6), (37.5, 6.7)], 36.0, 10.0, max_sep_deg=1.0), choose_chk((35.8, 10.6))),
        (8, "choose", "choose: both roots near the prior (docstring)",
         lambda: st.choose([(35.8, 10.6), (37.5, 6.7)], 36.0, 10.0), choose_chk(None)),
        (8, "choose", "choose: 0.38° from the prior at 64° N (max_sep_deg 0.5)",
         lambda: st.choose([(64.17, -21.98)], 64.0, -21.2, max_sep_deg=0.5),
         choose_chk((64.17, -21.98), "measure with sep_deg (on the sphere): at 64° N one degree of longitude is only "
                                     "cos 64° = 0.44° of arc, so a latitude/longitude box is wrong")),
        (9, "error_km", "error_km(0.2, 1.0, 60.0) (docstring)", lambda: st.error_km(0.2, 1.0, 60.0),
         number(59.88, 0.01, ((77.84, "the two errors are ADDED: independent errors combine as √(a² + b²)"),
                              (113.40, "the heading error is not multiplied by cos(altitude)"),
                              (108.21, "cos got DEGREES: math.cos(math.radians(alt_deg))")))),
    ]
    done, said = 0, set()
    for k, name, label, fn, chk in cases:
        if getattr(st, name, None) is None:
            print(f"✘ TODO {k}  {name}() does not exist in navera_lite/stars.py — did you rename it?")
            continue
        if stub(name):
            if k not in said:
                print(f"· TODO {k}  {name}() is not written yet")
            said.add(k)
            continue
        got, err = attempt(fn, name, none_ok=(name == "choose"))
        if err:
            print(f"✘ TODO {k}  {label}: {err}")
            continue
        try:
            ok, note = chk(got)
        except Exception as e:                                   # a strange return value
            ok, note = False, f"could not read the result {got!r} ({type(e).__name__})"
        shown = got
        if isinstance(got, (float, int, np.floating)):
            shown = f"{float(got):.6f}"
        elif isinstance(got, tuple) and len(got) == 2 and all(hasattr(x, "shape") for x in got):
            shown = "(" + ", ".join(str(np.round(np.asarray(x, dtype=float), 4).tolist()) for x in got) + ")"
        print(f"{'✔' if ok else '✘'} TODO {k}  {label}  ->  {shown}" + ("" if ok else "\n          (" + (note or (
            "not the docstring result" if "docstring" in label else "not the expected result")) + ")"))
        done += bool(ok)
    print(f"\n{done} of {len(cases)} examples give the expected result.")


# ------------------------------------------------------------------------------------------- session 1
def look():
    cat = catalogue()
    m = cat["vmag"]
    print(f"bright_stars.csv: {len(m)} stars brighter than magnitude 6.5 (J2000 positions).\n")
    print("  magnitude    stars     (smaller magnitude = brighter; 5 magnitudes = 100 × fainter)")
    for lo, hi in ((-2, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 6.5)):
        print(f"  {lo:4.1f} – {hi:3.1f}   {int(np.sum((m >= lo) & (m < hi))):5d}")
    print("\n  The ten brightest:")
    for i in np.argsort(m)[:10]:
        print(f"    {cat['name'][i]:16s} V = {m[i]:+.2f}   ra {cat['ra_deg'][i]:8.3f}°   dec {cat['dec_deg'][i]:+8.3f}°")
    i = st.find_star(cat, "Polaris")
    print(f"\n  Polaris: V = {m[i]:.2f}, dec {cat['dec_deg'][i]:+.4f}° (J2000): {90 - cat['dec_deg'][i]:.4f}° from the pole")


def clock():
    needs("julian_date", "gmst_deg")
    cat = catalogue()
    print("The clock of the sky (your julian_date and gmst_deg).\n")
    for utc in ((2026, 10, 20, 0, 0, 0), (2026, 10, 20, 20, 30, 0), (2026, 10, 21, 0, 0, 0)):
        jd = jd_of(utc)
        g = gst_of(jd)
        print(f"  {utc[0]}-{utc[1]:02d}-{utc[2]:02d} {utc[3]:02d}:{utc[4]:02d} UTC   JD {jd:.6f}   GMST {g:9.4f}°  "
              f"= {int(g / 15):02d} h {int(g / 15 % 1 * 60):02d} min")
    i = st.find_star(cat, "Vega")
    lon = PLACES["sousse"][2]
    print(f"\nVega crosses the meridian of Sousse (lon {lon}° E; due south, highest in the sky):")
    times = []
    for day in (20, 21):
        jd0 = jd_of((2026, 10, day, 0, 0, 0))
        ra, _ = st.precess(cat["ra_deg"][i], cat["dec_deg"][i], jd0 + 0.5)

        def h_of(sec):
            return wrap180(gst_of(jd0 + sec / 86400.0) + lon - ra)
        grid = np.arange(0, 86400 + 1, 600)
        hs = [h_of(s) for s in grid]
        k = next((j for j in range(len(grid) - 1) if hs[j] < 0 <= hs[j + 1] and hs[j + 1] - hs[j] < 90), None)
        if k is None:
            sys.exit("could not find the transit: is gmst_deg right? (python3 run_stars.py test)")
        a, b = float(grid[k]), float(grid[k + 1])
        for _ in range(50):
            mid = (a + b) / 2
            a, b = (mid, b) if h_of(mid) < 0 else (a, mid)
        times.append((a + b) / 2)
        s = times[-1]
        print(f"  {day} October 2026: {int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{s % 60:05.2f} UTC")
    d = times[1] - times[0]
    print(f"  one day later the transit comes {abs(d):.1f} s {'earlier' if d < 0 else 'later'}")
    print("  (Sousse is UTC+1: these transits are in the afternoon, in daylight. The sky's clock does not care; at night")
    print("   Vega is still up, west of the meridian — you will see it 37° high at 20:30 UTC in Step 3's docstring.)")
    jd = jd_of((2026, 10, 20, 20, 30, 0))
    print("\nPrecession, J2000 → 20 October 2026 (the given precess()):")
    for name in ("Vega", "Polaris", "Sirius"):
        j = st.find_star(cat, name)
        ra, dec = st.precess(cat["ra_deg"][j], cat["dec_deg"][j], jd)
        moved = st.sep_deg(cat["dec_deg"][j], cat["ra_deg"][j], dec, ra) * 60.0
        print(f"  {name:8s} J2000 ra {cat['ra_deg'][j]:8.4f}° dec {cat['dec_deg'][j]:+8.4f}°  →  of date ra {ra:8.4f}° "
              f"dec {dec:+8.4f}°   moved {moved:5.2f}′ on the sky")


def sky(args):
    if not args or args[0].lower() not in PLACES:
        sys.exit("name a place: python3 run_stars.py sky sousse   (sousse, capetown, reykjavik, quito, sydney)")
    needs("julian_date", "gmst_deg", "altaz")
    key = args[0].lower()
    label, lat, lon, utc = PLACES[key]
    cat = catalogue(5.0)
    jd = jd_of(utc)
    g = gst_of(jd)
    ra, dec = st.precess(cat["ra_deg"], cat["dec_deg"], jd)
    v = rk.need_ok(st, "altaz", ra, dec, lat, lon, g)
    alt, az = (np.asarray(x, dtype=float) for x in pair(v, "altaz"))
    if alt.shape != ra.shape:
        sys.exit(f"altaz() got {len(ra)} stars at once and must return {len(ra)} altitudes (arrays): use np.sin, "
                 f"np.arctan2…; it returned shape {alt.shape}")
    print(f"The sky over {label}, lat {lat}, lon {lon}, {utc[0]}-{utc[1]:02d}-{utc[2]:02d} {utc[3]:02d}:{utc[4]:02d} UTC "
          f"(GMST {g:.3f}°)\n")
    with open(need_data("bright_stars.csv"), newline="", encoding="utf-8") as f:
        common = {r["common"] for r in csv.DictReader(f) if r["common"]}
    named = [i for i in range(len(ra)) if cat["name"][i] in common]
    print("  named stars above the horizon     alt (°)   az (°)")
    for i in sorted([i for i in named if alt[i] > 0], key=lambda i: -alt[i]):
        print(f"    {cat['name'][i]:28s}  {alt[i]:6.2f}   {az[i]:6.2f}")
    p = st.find_star(cat, "Polaris")
    print(f"\n  Polaris: alt {alt[p]:+.2f}°, az {az[p]:.2f}°" + ("   (below the horizon)" if alt[p] < 0 else ""))
    print(f"  {int(np.sum(alt > 0))} of the {len(ra)} stars brighter than 5.0 are above the horizon.")
    plt = plt_ready()
    if plt is None:
        return
    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    up = alt > 0
    ax.scatter(np.radians(az[up]), 90 - alt[up], s=np.clip(14 - 2.6 * cat["vmag"][up], 1, 30), c="#1d2733")
    for i in named:
        if alt[i] > 0:
            ax.annotate(cat["name"][i], (math.radians(az[i]), 90 - alt[i]), fontsize=7, color="#0b6e8a",
                        xytext=(3, 3), textcoords="offset points")
    ax.set_rlim(0, 90)
    ax.set_yticks([30, 60, 90])
    ax.set_yticklabels(["60°", "30°", "horizon"], fontsize=7)
    ax.set_xticks(np.radians([0, 90, 180, 270]))
    ax.set_xticklabels(["N", "E", "S", "W"])
    ax.set_title(f"{label}\n{utc[0]}-{utc[1]:02d}-{utc[2]:02d} {utc[3]:02d}:{utc[4]:02d} UTC — centre = zenith",
                 fontsize=9)
    fig.tight_layout()
    name = f"out/sky_{key}.png"
    fig.savefig(name, dpi=90)
    rk.saved(name)


def polaris():
    needs("julian_date", "gmst_deg", "altaz", "lat_from_polaris")
    cat = catalogue()
    p = st.find_star(cat, "Polaris")
    places = (("Reykjavik", 64.15, -21.94), ("London", 51.50, -0.12), ("Sousse", 35.83, 10.64), ("Singapore", 1.29, 103.85))
    print("Polaris through the night of 20–21 October 2026 (every 30 min, 18:00 → 06:00 UTC). Its altitude is computed")
    print("with your altaz (a perfect measurement, no refraction); the latitude with your lat_from_polaris.\n")
    print("   place        true lat   naive: lat = altitude     with the hour angle")
    print("                            max error (km)          max error (km)")
    km = st.KM_PER_DEG
    for name, lat, lon in places:
        e1, e2 = [], []
        for half in range(25):
            jd = jd_of((2026, 10, 20, 18, 0, 0)) + half / 48.0
            g = gst_of(jd)
            ra, dec = st.precess(cat["ra_deg"][p], cat["dec_deg"][p], jd)
            a, _ = pair(rk.need_ok(st, "altaz", ra, dec, lat, lon, g), "altaz")
            a = num(a, "altaz")
            H = (g + lon - ra) % 360.0
            e1.append(abs(num(rk.need_ok(st, "lat_from_polaris", a), "lat_from_polaris") - lat) * km)
            e2.append(abs(num(rk.need_ok(st, "lat_from_polaris", a, H), "lat_from_polaris") - lat) * km)
        print(f"   {name:10s} {lat:7.2f}        {max(e1):8.2f}                  {max(e2):8.3f}")


# ------------------------------------------------------------------------------------------- session 2
def load_photo(n):
    import cv2
    meta = photos()
    if not 1 <= n <= len(meta["photos"]):
        sys.exit(f"there are {len(meta['photos'])} photos: give a number from 1 to {len(meta['photos'])}")
    p = meta["photos"][n - 1]
    img = cv2.imread(need_data(p["file"]), cv2.IMREAD_GRAYSCALE)
    if img is None:
        sys.exit(f"could not read {p['file']}")
    return meta, p, img


def detections(img, n):
    v = rk.need_ok(st, "detect_stars", img)
    if not (isinstance(v, (tuple, list)) and len(v) == 2):
        sys.exit(f"detect_stars() must return (pts, flux), but it returned {type(v).__name__}")
    try:
        pts, flux = np.asarray(v[0], dtype=float), np.asarray(v[1], dtype=float)
    except (TypeError, ValueError):
        sys.exit("detect_stars() must return two numpy arrays (pts N × 2, flux N)")
    if pts.ndim != 2 or pts.shape[1:] != (2,) or flux.shape != (len(pts),):
        sys.exit(f"detect_stars() must return pts of shape (N, 2) and flux of shape (N,); got {pts.shape} and {flux.shape}")
    if len(flux) > 1 and np.any(np.diff(flux) > 1e-9):
        sys.exit("detect_stars() must sort the stars BRIGHTEST FIRST (flux decreasing): np.argsort(-flux)")
    return pts, flux


def detect(args):
    needs("detect_stars")
    n = int(args[0]) if args and args[0].isdigit() else 1
    meta, p, img = load_photo(n)
    pts, flux = detections(img, n)
    print(f"photo {n} ({p['file']}): {img.shape[1]} × {img.shape[0]} pixels, background median "
          f"{float(np.median(img)):.0f}; your detect_stars found {len(pts)} stars.")
    if len(pts):
        print("  the five brightest:   u (px)    v (px)     flux")
        for (u, v), f in list(zip(pts, flux))[:5]:
            print(f"                     {u:8.2f}  {v:8.2f}  {f:9.0f}")
    if n in (1, 2):
        truth = f"photo{n:02d}_stars.csv"
        rows = list(csv.DictReader(open(need_data(truth))))
        tu = np.array([[float(r["u_px"]), float(r["v_px"])] for r in rows])
        tm = np.array([float(r["vmag"]) for r in rows])
        bright = tm <= 5.0
        corner = (tu[:, 0] > 900) & (tu[:, 1] > 600)
        errs, found, found_corner = [], 0, 0
        for (u, v), m, cn in zip(tu, tm, corner):
            if len(pts) == 0:
                break
            d = np.hypot(pts[:, 0] - u, pts[:, 1] - v)
            if d.min() <= 2.0 and m <= 5.0:
                found += 1
                found_corner += int(cn)
                errs.append(d.min())
        far = sum(1 for u, v in pts if np.hypot(tu[:, 0] - u, tu[:, 1] - v).min() > 3.0)
        print(f"\n  Against the truth ({truth}):")
        print(f"    stars brighter than 5.0 found: {found} of {int(bright.sum())}")
        if n == 2:
            print(f"    … in the glowing corner (u > 900, v > 600): {found_corner} of {int((bright & corner).sum())}")
        if errs:
            print(f"    their centre error: RMS {math.sqrt(float(np.mean(np.square(errs)))):.3f} px, worst {max(errs):.3f} px")
        print(f"    detections more than 3 px from every catalogue star (not stars: hot pixels, trail, noise): {far}")
        if len(pts) > 300 and far > len(pts) / 2:
            print("\n  ⚠ Most of your detections are noise. Did you subtract two uint8 arrays? On uint8, 19 − 20 = 255:"
                  "\n    convert to float first, gray.astype(float) - bg (lesson §4, 🧰 box).")
    plt = plt_ready()
    if plt is None:
        return
    fig, axs = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [2, 1]})
    axs[0].imshow(np.clip(img.astype(float) * 3, 0, 255), cmap="gray", vmin=0, vmax=255)
    axs[0].scatter(pts[:, 0], pts[:, 1], s=60, facecolors="none", edgecolors="#e0a020", linewidths=0.8)
    for k, (u, v) in enumerate(pts[:10]):
        axs[0].annotate(str(k + 1), (u, v), color="#e0a020", fontsize=7, xytext=(5, -5), textcoords="offset points")
    axs[0].set_title(f"photo {n}: your {len(pts)} stars (circles; 1 = brightest), image ×3 brighter", fontsize=9)
    if len(pts):
        u0, v0 = int(round(pts[0, 0])), int(round(pts[0, 1]))
        y0, x0 = max(0, v0 - 8), max(0, u0 - 8)
        crop = img[y0:v0 + 9, x0:u0 + 9]
        axs[1].imshow(crop, cmap="gray", extent=(x0 - 0.5, x0 + crop.shape[1] - 0.5, y0 + crop.shape[0] - 0.5, y0 - 0.5))
        axs[1].plot(pts[0, 0], pts[0, 1], "+", color="#d64545", ms=14)
        axs[1].set_title("the brightest star, zoomed: + = your centre", fontsize=9)
    fig.tight_layout()
    name = f"out/detect_{n:02d}.png"
    fig.savefig(name, dpi=90)
    rk.saved(name)


def solve_photo(n, quiet=False):
    meta, p, img = load_photo(n)
    pts, flux = detections(img, n)
    cat = catalogue()
    jd = jd_of(tuple(p["utc_parts"]))
    ra, dec = st.precess(cat["ra_deg"], cat["dec_deg"], jd)
    K = np.array(meta["camera"]["K"])
    sol = st.plate_solve(pts, K, ra, dec, cat["vmag"])
    return meta, p, img, pts, cat, jd, sol, K


def solve(args):
    needs("detect_stars", "julian_date")
    n = int(args[0]) if args and args[0].isdigit() else 1
    meta, p, img, pts, cat, jd, sol, K = solve_photo(n)
    if sol is None:
        sys.exit(f"photo {n}: the plate solver could not identify the stars from your {len(pts)} detections "
                 "(too few? hot pixels kept? not sorted brightest first?)")
    one_px = math.degrees(math.atan(1.0 / K[0, 0]))
    print(f"photo {n}: {len(pts)} detections, {sol['n_matched']} identified as catalogue stars.")
    print(f"  the image centre points at  ra {sol['ra_deg']:.4f}°, dec {sol['dec_deg']:+.4f}°  (of date)")
    print(f"  fit residual: {sol['rms_arcsec']:.1f}″ RMS over the {sol['n_matched']} stars")
    print(f"  one pixel at the image centre = {one_px * 60:.2f}′ on the sky")
    names = [(cat["vmag"][c], cat["name"][c], d) for d, c in sol["matches"]]
    print("  the brightest identified:", ", ".join(f"{nm} (V {m:.1f})" for m, nm, _ in sorted(names)[:8]))
    plt = plt_ready()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(10, 7.5))
    ax.imshow(np.clip(img.astype(float) * 3, 0, 255), cmap="gray", vmin=0, vmax=255)
    for m, nm, d in sorted(names)[:25]:
        u, v = pts[d]
        ax.plot(u, v, "o", mfc="none", mec="#2e9e4f", ms=9)
        if not nm[:1].isdigit() and not nm.startswith("HR"):
            ax.annotate(nm, (u, v), color="#7fd99a", fontsize=7, xytext=(6, -6), textcoords="offset points")
    ax.plot(K[0, 2], K[1, 2], "+", color="#d64545", ms=18)
    ax.set_title(f"photo {n}: identified stars; + = image centre → ra {sol['ra_deg']:.2f}°, dec {sol['dec_deg']:+.2f}°",
                 fontsize=9)
    fig.tight_layout()
    name = f"out/solve_{n:02d}.png"
    fig.savefig(name, dpi=90)
    rk.saved(name)


def attitude_for(p, mode):
    if mode == "truth":
        return np.array(p["truth"]["q"], dtype=float)
    if mode == "magnetic":
        return np.array(p["chip_q"], dtype=float)
    d = imu.declination_deg(p["prior_lat"], p["prior_lon"], YEAR)
    return np.asarray(imu.q_true_north(p["chip_q"], d), dtype=float)


def roots_of(v):
    if not isinstance(v, (list, tuple)):
        sys.exit(f"both_roots() must return a list of (lat, lon) tuples, but it returned {v!r}")
    try:
        roots = [(float(r[0]), float(r[1])) for r in v]
    except (TypeError, ValueError, IndexError):
        sys.exit(f"both_roots() must return a list of (lat, lon) tuples, but it returned {v!r}")
    if any(abs(r[0]) > 90.0 + 1e-9 for r in roots):
        sys.exit(f"both_roots() returned a root with |latitude| > 90°: {roots} — keep only the valid roots (lesson §6)")
    return roots


def bennett_deg(alt_deg):
    """Atmospheric refraction (degrees) at an apparent altitude, Bennett's rule (standard air)."""
    return 1.0 / 60.0 / math.tan(math.radians(alt_deg + 7.31 / (alt_deg + 4.4)))


def one_fix(p, sol, g, mode, oneroot=False, refraction=False):
    """(alt, az, roots, chosen) for one photo, with the attitude of `mode` (truth, magnetic or imu)."""
    alt, az = pair(rk.need_ok(st, "boresight_altaz", attitude_for(p, mode)), "boresight_altaz")
    alt, az = num(alt, "boresight_altaz"), num(az, "boresight_altaz")
    if refraction:              # a real sky: the stars at the image centre truly stand R lower than the IMU says
        alt = alt + bennett_deg(alt)
    v, err = rk.call(st, "both_roots", alt, az, sol["ra_deg"], sol["dec_deg"], g)
    if err and "returned None" not in err:
        sys.exit(err)
    if err:
        sys.exit("both_roots() returned None: return a list — [] when there is no root")
    roots = roots_of(v)
    if oneroot:                                 # the old way: one root, taken as it is, no prior check
        roots = roots[:1]
        return alt, az, roots, (roots[0] if roots else None)
    v, err = rk.call(st, "choose", roots, p["prior_lat"], p["prior_lon"])
    if err and "returned None" not in err:
        sys.exit(err)
    return alt, az, roots, v


def fix(args):
    needs("julian_date", "gmst_deg", "detect_stars", "boresight_altaz", "both_roots", "choose")
    mode = args[0].lower() if args else "imu"
    refraction = len(args) > 1 and args[1].lower() == "refraction"
    if mode not in ("imu", "truth", "magnetic", "oneroot") or (len(args) > 1 and not (refraction and mode == "truth")):
        sys.exit("options: python3 run_stars.py fix  |  fix truth  |  fix magnetic  |  fix oneroot  |  fix truth refraction")
    title = {"imu": "the IMU chip's attitude turned to TRUE north (q_true_north with the WMM declination)",
             "truth": "the TRUE attitude (a perfect IMU)",
             "magnetic": "the IMU chip's attitude as delivered (MAGNETIC north, declination forgotten)",
             "oneroot": "the chip's attitude, true north, and only the FIRST root (the asin root), no prior check"}[mode]
    print(f"A position from each photo, with {title}" + (", and a refracted sky ignored by the solver (Bennett)"
                                                          if refraction else "") + ".\n")
    extra = "   moved from `fix`" if mode == "magnetic" else ""
    print("  photo  boresight alt/az   roots  →  chosen (lat, lon)      error to the truth" + extra + "   the other root")
    meta = photos()
    errs, rows = [], []
    for n in range(1, len(meta["photos"]) + 1):
        _, p, _, pts, _, jd, sol, _ = solve_photo(n, quiet=True)
        tr = p["truth"]
        if sol is None:
            print(f"   {n}     the plate solver failed on your detections")
            continue
        g = gst_of(jd)
        alt, az, roots, v = one_fix(p, sol, g, "imu" if mode == "oneroot" else mode, oneroot=(mode == "oneroot"),
                                    refraction=refraction)
        moved = ""
        if mode == "magnetic":
            ref = one_fix(p, sol, g, "imu")[3]
            moved = (f"   {st.sep_deg(float(v[0]), float(v[1]), float(ref[0]), float(ref[1])) * st.KM_PER_DEG:8.1f} km"
                     if v is not None and ref is not None else "         —   ")
        other = ""
        if len(roots) == 2:
            o = roots[1] if v is not None and abs(roots[0][0] - v[0]) < 1e-9 and abs(roots[0][1] - v[1]) < 1e-9 else roots[0]
            other = f"({o[0]:6.2f}, {o[1]:7.2f}), {st.sep_deg(o[0], o[1], tr['lat'], tr['lon']) * st.KM_PER_DEG:6.0f} km off"
        if v is None:
            print(f"   {n}     {alt:5.2f}° {az:6.2f}°      {len(roots)}   →  no position                    {moved}          {other}")
            rows.append((n, None, None, None))
            continue
        lat, lon = float(v[0]), float(v[1])
        e = st.sep_deg(lat, lon, tr["lat"], tr["lon"]) * st.KM_PER_DEG
        errs.append(e)
        rows.append((n, lat, lon, e))
        print(f"   {n}     {alt:5.2f}° {az:6.2f}°      {len(roots)}   →  ({lat:6.2f}, {lon:7.2f})   {e:10.1f} km{moved}          {other}")
    print("\n  (roots = the VALID roots: when it says 1, the other latitude is beyond ±90°; 0 = no latitude fits)")
    if errs:
        print(f"\n  {len(errs)} positions; error median {float(np.median(errs)):.1f} km, largest {max(errs):.1f} km")
    plt = plt_ready()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    for n, lat, lon, e in rows:
        tr = meta["photos"][n - 1]["truth"]
        ax.plot(tr["lon"], tr["lat"], "o", color="#1d2733", ms=5)
        ax.annotate(str(n), (tr["lon"], tr["lat"]), fontsize=8, xytext=(4, 4), textcoords="offset points")
        if lat is not None:
            ax.plot([tr["lon"], lon], [tr["lat"], lat], "-", color="#d64545", lw=1)
            ax.plot(lon, lat, "x", color="#d64545", ms=7)
    ax.set_xlim(-180, 180)
    ax.set_ylim(-90, 90)
    ax.set_xlabel("longitude (°)")
    ax.set_ylabel("latitude (°)")
    ax.grid(alpha=0.3)
    ax.set_title(f"truth (dots) and your fixes (x): {mode}", fontsize=9)
    fig.tight_layout()
    name = f"out/fix_{mode}{'_refraction' if refraction else ''}.png"
    fig.savefig(name, dpi=90)
    rk.saved(name)


def budget(args=()):
    needs("julian_date", "gmst_deg", "detect_stars", "boresight_altaz", "both_roots", "choose", "error_km")
    rot = rk.load_student("navera_lite.rotations")
    n = int(args[0]) if args and args[0].isdigit() else 1
    _, p, _, pts, _, jd, sol, _ = solve_photo(n, quiet=True)
    if sol is None:
        sys.exit(f"photo {n}: the plate solver failed on your detections (python3 run_stars.py solve {n})")
    g = gst_of(jd)
    tr = p["truth"]
    q = np.array(tr["q"], dtype=float)
    alt0, _ = pair(rk.need_ok(st, "boresight_altaz", q), "boresight_altaz")
    sr, sp, sh = 0.3, 0.3, 1.5
    rng = np.random.default_rng(26)
    errs, lost = [], 0
    N = 2000
    for _ in range(N):
        dr, dp, dh = rng.normal(0.0, sr), rng.normal(0.0, sp), rng.normal(0.0, sh)
        qq = rot.q_mul(q, rot.q_from_axis_angle((1.0, 0.0, 0.0), math.radians(dr)))
        qq = rot.q_mul(qq, rot.q_from_axis_angle((0.0, 1.0, 0.0), math.radians(dp)))
        qq = rot.q_mul(rot.q_from_axis_angle((0.0, 0.0, 1.0), math.radians(dh)), qq)
        alt, az = st.boresight_altaz(qq)
        v = st.choose(st.both_roots(alt, az, sol["ra_deg"], sol["dec_deg"], g), p["prior_lat"], p["prior_lon"])
        if v is None:
            lost += 1
            continue
        errs.append(st.sep_deg(v[0], v[1], tr["lat"], tr["lon"]) * st.KM_PER_DEG)
    e = np.array(errs)
    if len(e) == 0:
        sys.exit(f"photo {n}: no position in any of the {N} draws")
    tilt = math.hypot(sr, sp)
    f = num(rk.need_ok(st, "error_km", tilt, sh, float(alt0)), "error_km")
    print(f"Photo {n}, the true attitude disturbed {N} times by random IMU errors: σ {sr}° on roll, {sp}° on pitch "
          f"(tilt σ √({sr}² + {sp}²) = {tilt:.3f}°), {sh}° on heading. Camera {float(alt0):.2f}° above the horizon.\n")
    print(f"  your error_km({tilt:.3f}, {sh}, {float(alt0):.2f})  = {f:7.1f} km   (the formula)")
    print(f"  measured: RMS {math.sqrt(float(np.mean(e ** 2))):7.1f} km,  median {float(np.median(e)):7.1f} km,  "
          f"90 % below {float(np.percentile(e, 90)):7.1f} km,  largest {e.max():7.1f} km")
    print(f"  no position in {lost} of {N} draws")
    plt = plt_ready()
    if plt is None:
        return
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(e, bins=50, color="#8a96a3")
    for x, col, lab in ((float(np.median(e)), "#2e9e4f", "median"), (math.sqrt(float(np.mean(e ** 2))), "#d64545", "RMS"),
                        (f, "#0b6e8a", "your error_km")):
        ax.axvline(x, color=col, lw=1.5, label=f"{lab} {x:.0f} km")
    ax.set_xlabel("position error (km)")
    ax.set_ylabel("draws")
    ax.legend(fontsize=8)
    ax.set_title(f"Star fix error from IMU attitude errors (photo {n})", fontsize=9)
    fig.tight_layout()
    name = "out/budget.png" if n == 1 else f"out/budget_{n:02d}.png"
    fig.savefig(name, dpi=90)
    rk.saved(name)


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(1)
    m, rest = a[0], a[1:]
    table = {"test": lambda: test(), "look": lambda: look(), "clock": lambda: clock(), "sky": lambda: sky(rest),
             "polaris": lambda: polaris(), "detect": lambda: detect(rest), "solve": lambda: solve(rest),
             "fix": lambda: fix(rest), "budget": lambda: budget(rest)}
    if m not in table:
        print(__doc__)
        sys.exit(1)
    table[m]()
