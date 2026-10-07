import json
import math
import os
import random
import re
import sys

import numpy as np

from academy_check import Checker, load_student, need, sh

c = Checker()

SITE = (28.30, -16.51)         # Teide Observatory, Tenerife
GAST = 316.48003               # NAVERA gast_deg("2026-10-07 20:00:00") (astropy, offline)
GMST_ASTROPY = 316.477860      # astropy GMST at the same instant
VEGA_APP = (279.45960, 38.81067)          # Vega, true equator and equinox of date (TETE)
VEGA_ASTROPY_ALTAZ = (70.00612, 307.01331)  # astropy AltAz of Vega from Teide Observatory at that instant
THERMAL = "/data/navera_data/camera_pkg/camera_pkg/data/thermal"
DAY = "/data/navera_data/camera_pkg/camera_pkg/data/day"
# NAVERA normalize_query() coverage: (w, h, hfov, heading, altitude) -> coverage (lat 35.83)
NAVERA_COVERAGE = {(640, 480, 84.0, 0.0, 300.0): 0.816, (640, 480, 84.0, 45.0, 300.0): 0.769,
                   (640, 480, 84.0, 45.0, 350.0): 0.884, (640, 512, 84.0, 30.0, 350.0): 0.9245,
                   (640, 528, 56.7, 0.0, 480.0): 0.8613, (1536, 730, 84.0, 20.0, 400.0): 0.7283}


def S():
    return load_student("stars.py")


def T():
    return load_student("thermal.py")


def navera_cn():
    try:
        from cn_pkg.nodes import celestial_math as cm
    except ImportError:
        sys.path.insert(0, os.path.expanduser("~/navera/cn_pkg"))
        from cn_pkg.nodes import celestial_math as cm
    return cm


def results():
    c.file_exists("results.json")
    try:
        with open("results.json") as f:
            return json.load(f)
    except ValueError as e:
        c.ok(False, f"results.json is not valid JSON: {e}")


# ---------------- part A: the sky ----------------

@c.test("TODO 1 — julian_date(): J2000.0, Meeus' examples and our evening",
        hint="Follow Meeus step by step: January and February count as months 13 and 14 of the year before. "
             "Use math.floor, not int(), and add the hours as a fraction of a day.")
def _():
    (jd,) = need(S(), "julian_date")
    c.near(jd(2000, 1, 1, 12), 2451545.0, 1e-6, "julian_date(2000, 1, 1, 12)")
    c.near(jd(1987, 1, 27), 2446822.5, 1e-6, "julian_date(1987, 1, 27) (a January date)")
    c.near(jd(1957, 10, 4, 19, 26, 24), 2436116.31, 1e-5, "julian_date(1957, 10, 4, 19:26:24) (Sputnik 1)")
    c.near(jd(2026, 10, 7, 20, 0, 0.0), 2461321.333333, 1e-5, "julian_date(2026, 10, 7, 20:00)")


@c.test("TODO 2 — gmst_deg() agrees with Meeus and with astropy to better than 1 arcsecond",
        hint="d = JD - 2451545.0 and T = d / 36525; the big term is 360.98564736629 * d. "
             "Bring the result into 0..360 with % 360.")
def _():
    s = S()
    jd, g = need(s, "julian_date", "gmst_deg")
    c.near(g(jd(1987, 4, 10)), 197.693195, 1e-4, "gmst_deg on 1987-04-10 0h UT (Meeus example 12.a)")
    got = g(jd(2026, 10, 7, 20, 0, 0.0))
    c.ok(0.0 <= got < 360.0, f"gmst_deg should be in 0..360, got {got}")
    c.near(got, GMST_ASTROPY, 3e-4, "gmst_deg at 2026-10-07 20:00 UTC (astropy: 316.477860)")


@c.test("TODO 3 — radec_to_altaz(): a star at the zenith, and Vega from Teide Observatory like astropy",
        hint="H = gst + lon - RA. np.sin/np.cos need radians (np.radians), np.arcsin/np.arctan2 give radians "
             "(np.degrees). Azimuth: % 360.")
def _():
    (f,) = need(S(), "radec_to_altaz")
    r = f(GAST + SITE[1], SITE[0], SITE[0], SITE[1], GAST)
    c.ok(isinstance(r, (tuple, list)) and len(r) == 2, f"radec_to_altaz should return (alt, az), got {r!r}")
    c.near(float(r[0]), 90.0, 0.01, "altitude of a star at the zenith")
    alt, az = f(VEGA_APP[0], VEGA_APP[1], SITE[0], SITE[1], GAST)
    c.near(float(alt), VEGA_ASTROPY_ALTAZ[0], 0.01, "Vega's altitude (astropy 70.00612)")
    c.near(float(az), VEGA_ASTROPY_ALTAZ[1], 0.01, "Vega's azimuth (astropy 307.01331)")


@c.test("TODO 3 — radec_to_altaz() works on numpy arrays and NAVERA's local_to_radec turns it back",
        hint="Use np.sin / np.cos / np.arctan2 (math.* refuse arrays). NAVERA's function goes alt/az -> RA/Dec: "
             "if the altitude is right but this fails, look at the signs inside the azimuth's atan2.")
def _():
    (f,) = need(S(), "radec_to_altaz")
    l2r = navera_cn().local_to_radec
    rnd = random.Random(24)
    ra = np.array([rnd.uniform(0, 360) for _ in range(30)])
    dec = np.array([rnd.uniform(-60, 85) for _ in range(30)])
    lat, lon, g = -33.92, 18.42, 123.4                        # Cape Town
    alt, az = f(ra, dec, lat, lon, g)
    alt, az = np.asarray(alt, float), np.asarray(az, float)
    c.ok(alt.shape == (30,) and az.shape == (30,), f"for 30 stars expected 30 altitudes and azimuths, got "
                                                    f"shapes {alt.shape} and {az.shape}")
    c.ok(np.all((az >= 0) & (az < 360)), "an azimuth is outside 0..360")
    for i in range(30):
        if alt[i] > 85:
            continue
        ra2, dec2 = l2r(lat, lon, float(alt[i]), float(az[i]), g)
        dra = (ra2 - ra[i] + 180) % 360 - 180
        c.ok(abs(dec2 - dec[i]) < 0.01 and abs(dra) * math.cos(math.radians(dec[i])) < 0.01,
             f"RA {ra[i]:.1f}°, Dec {dec[i]:.1f}° from Cape Town: you give alt {alt[i]:.2f}°, az {az[i]:.2f}° — "
             f"NAVERA turns that back into RA {ra2:.2f}°, Dec {dec2:.2f}°")


@c.test("Given code 4 — visible_stars() (uses your TODO 3): 44 bright stars above Teide Observatory, brightest first",
        hint="One radec_to_altaz call on arrays of all RA and Dec; keep alt > min_alt_deg; dicts with name, mag, "
             "alt, az; sorted(..., key=lambda v: v['mag']).")
def _():
    load, vis = need(S(), "load_bright_stars", "visible_stars")
    v = vis(load(max_mag=2.5), SITE[0], SITE[1], GAST)
    c.ok(isinstance(v, list) and v, f"visible_stars should return a non-empty list, got {type(v).__name__}")
    c.ok(all(isinstance(x, dict) and {"name", "mag", "alt", "az"} <= set(x) for x in v),
         "each item should be a dict with the keys name, mag, alt, az")
    c.ok(all(float(x["alt"]) > 0 for x in v), "a star at or below the horizon is in the list")
    c.ok(abs(len(v) - 44) <= 1, f"{len(v)} stars above the horizon, expected 44")
    mags = [x["mag"] for x in v]
    c.ok(mags == sorted(mags), "the list is not sorted from the brightest (smallest mag) to the faintest")
    c.eq(v[0]["name"], "Arcturus", "the brightest star above the horizon")
    v20 = vis(load(max_mag=2.5), SITE[0], SITE[1], GAST, 20.0)
    c.ok(all(float(x["alt"]) > 20 for x in v20) and len(v20) < len(v), "min_alt_deg=20 is not respected")


@c.test("TODO 5 and 6 — polaris_latitude() with and without the correction; zenith_fix()",
        hint="Corrected: altitude - p·cos(H), cos needs radians. Zenith: lat = Dec, lon = RA - GST "
             "wrapped with (x + 540) % 360 - 180.")
def _():
    s = S()
    pl, zf = need(s, "polaris_latitude", "zenith_fix")
    c.near(pl(23.9), 23.9, 1e-9, "polaris_latitude(23.9)")
    c.near(pl(24.0, 0.0, 0.626), 23.374, 1e-6, "polaris_latitude(24.0, H=0, p=0.626)")
    c.near(pl(24.0, 90.0, 0.626), 24.0, 1e-6, "polaris_latitude(24.0, H=90, p=0.626)")
    c.near(pl(22.8, 180.0, 0.626), 23.426, 1e-6, "polaris_latitude(22.8, H=180, p=0.626)")
    lat, lon = zf(299.970, 28.30, 316.480)
    c.near(lat, 28.30, 1e-6, "zenith_fix latitude")
    c.near(lon, -16.51, 1e-6, "zenith_fix longitude")
    c.near(zf(300.0, -10.0, 10.0)[1], -70.0, 1e-6, "zenith_fix(300, -10, 10) longitude (must be in -180..180)")


@c.test("TODO 7 — attitude_error_km() and clock_error_km(): 1° ≈ 111 km, 4 s ≈ 1 nautical mile at the equator",
        hint="Attitude: |e| x EARTH_KM_PER_DEG. Clock: |dt| x SIDEREAL_DEG_PER_S degrees of longitude, each worth "
             "EARTH_KM_PER_DEG x cos(latitude) km.")
def _():
    a, k = need(S(), "attitude_error_km", "clock_error_km")
    c.near(a(1.0), 111.195, 0.01, "attitude_error_km(1.0)")
    c.near(a(-0.5), 55.598, 0.01, "attitude_error_km(-0.5)")
    c.near(k(4.0, 0.0), 1.8583, 0.002, "clock_error_km(4 s, equator)")
    c.near(k(-1.0, 60.0), 0.2323, 0.001, "clock_error_km(-1 s, 60° N)")


@c.test("TODO 8 — monte_carlo_fix(): perfect IMU gives 0 km; BNO085-class IMU gives tens of km",
        hint="Compute (ra, dec) ONCE from the true pointing, then for each draw solve with the NOISY pointing "
             "(observer_candidates + choose_candidate with the site as prior) and measure haversine_km(site, fix).")
def _():
    (mc,) = need(S(), "monte_carlo_fix")
    cn = navera_cn()
    r = mc(cn, SITE, GAST, 75.0, 45.0, 0.0, 0.0, n=20, seed=1)
    c.ok(isinstance(r, (tuple, list)) and len(r) == 2, f"monte_carlo_fix should return (errors, ambiguous), got {r!r}")
    e0 = np.asarray(r[0], float)
    c.ok(e0.size == 20 and np.all(e0 < 0.01), f"with a perfect IMU every error should be ~0 km, got {e0[:5]}")
    e, amb = mc(cn, SITE, GAST, 75.0, 45.0, 0.3, 1.5, n=600, seed=24)
    e = np.asarray(e, float)
    c.ok(e.size + int(amb) == 600, f"{e.size} errors + {amb} ambiguous ≠ 600 draws")
    med = float(np.median(e))
    c.ok(38.0 <= med <= 56.0, f"median error {med:.1f} km with 0.3° tilt / 1.5° heading at 75°, expected ~50 km")
    e2, _ = mc(cn, SITE, GAST, 75.0, 45.0, 0.3, 1.5, n=50, seed=7)
    e3, _ = mc(cn, SITE, GAST, 75.0, 45.0, 0.3, 1.5, n=50, seed=7)
    c.ok(np.allclose(np.asarray(e2, float), np.asarray(e3, float)), "the same seed must give the same errors "
                                                                      "(create the generator from `seed`)")


@c.test("python3 stars.py runs, draws sky.png and writes the 'stars' results",
        hint="Run `python3 stars.py` and read its last lines. It must reach 'Wrote the stars section of results.json'.")
def _():
    if os.path.exists("sky.png"):
        os.remove("sky.png")
    code, out = sh("python3 stars.py", timeout=120)
    c.ok(code == 0 and "Wrote the 'stars' section" in out, "stars.py did not finish:\n" + out[-700:])
    import cv2
    c.ok(cv2.imread("sky.png") is not None, "sky.png is missing or not a picture")
    r = results().get("stars", {})
    c.ok(abs(r.get("gmst_diff_arcsec", 99)) < 1.0, f"GMST differs from astropy by {r.get('gmst_diff_arcsec')} arcsec")
    c.ok(r.get("altaz_worst_diff_arcsec", 99) < 5.0, f"alt/az differ from astropy by {r.get('altaz_worst_diff_arcsec')} arcsec")
    c.ok(r.get("polaris_max_err_corrected_km", 99) < 1.0 < r.get("polaris_max_err_plain_km", 0),
         "the Polaris correction should bring the worst error from ~70 km to below 1 km")


# ---------------- part B: night ----------------

@c.test("Given code 9 — parse_thermal_name() reads lat, lon and alt — and None for a NOGPS frame",
        hint="os.path.basename, os.path.splitext, split('_'); a part starting with 'lat' gives float(part[3:]); "
             "for 'alt400m' remove the 'm'. Without lat or lon, return None.")
def _():
    (f,) = need(T(), "parse_thermal_name")
    r = f("frame_0002_lat35.83026_lon10.64111_alt400m.jpg")
    c.ok(isinstance(r, (tuple, list)) and len(r) == 3, f"expected (lat, lon, alt), got {r!r}")
    c.ok(abs(r[0] - 35.83026) < 1e-9 and abs(r[1] - 10.64111) < 1e-9 and abs(r[2] - 400) < 1e-9, f"got {r!r}")
    r = f("/data/x/frame_0031_lat-12.5_lon-3.25_alt250m.jpg")
    c.ok(r is not None and abs(r[0] + 12.5) < 1e-9 and abs(r[1] + 3.25) < 1e-9 and abs(r[2] - 250) < 1e-9,
         f"a full path with negative coordinates gave {r!r}")
    c.ok(f("frame_0004_NOGPS_alt400m.jpg") is None, "a NOGPS frame should give None")


@c.test("TODO 10 and 11 — scale_to_map() and query_coverage() agree with NAVERA's normalize_query()",
        hint="Coverage: sample the 512 x 512 square at pixel centres (meshgrid), rotate each sample into the frame's "
             "axes with the heading (radians!), test |x| <= W/2 and |y| <= H/2 with W, H in MAP pixels, take the mean.")
def _():
    m = T()
    sc, cov = need(m, "scale_to_map", "query_coverage")
    mpp = 40075016.7 * math.cos(math.radians(35.85)) / 2 ** 17 / 256.0
    want = 2 * 400 * math.tan(math.radians(42)) / 1536 / mpp
    c.near(sc(400.0, 84.0, 1536, 35.85), want, want * 0.002, "scale_to_map(400, 84, 1536, 35.85)")
    for (w, h, hfov, hdg, alt), ref in NAVERA_COVERAGE.items():
        got = cov(w, h, alt, hfov, hdg, 35.83)
        c.near(got, ref, 0.006, f"query_coverage({w}x{h}, {alt:.0f} m, {hfov}°, heading {hdg:.0f}°) (NAVERA {ref})")


@c.test("TODO 13 (and given code 12, min_altitude() by bisection) — NAVERA's motion gate",
        hint="Bisection: if coverage(mid) >= need then hi = mid else lo = mid, until hi - lo < tol. "
             "Gate: reach = max_speed x max(0, t - t_anchor) + margin; accepted when jump <= reach.")
def _():
    m = T()
    ma, gate = need(m, "min_altitude", "motion_gate")
    c.near(ma(640, 480, 84.0, 45.0, 35.83), 332.8, 2.0, "min_altitude(640x480, 84°, heading 45°)")
    c.near(ma(640, 528, 56.7, 0.0, 35.83), 473.2, 2.0, "min_altitude(640x528, 56.7°, heading 0°)")
    ok, jump, reach = gate((35.83, 10.64), 0.0, (35.8420, 10.66), 4.0)
    c.ok(not ok, f"a 2.2 km jump in 4 s was accepted (jump {jump:.0f} m, reach {reach:.0f} m)")
    c.near(reach, 150.0, 1e-6, "reach after 4 s (30 m/s x 4 s + 30 m)")
    c.near(jump, 2243.0, 5.0, "jump (m)")
    ok, jump, reach = gate((35.83, 10.64), 10.0, (35.8303, 10.6404), 12.0)
    c.ok(ok, f"a {jump:.0f} m move in 2 s should be accepted (reach {reach:.0f} m)")
    ok, _, reach = gate((35.83, 10.64), 10.0, (35.83, 10.64), 9.0)
    c.near(reach, 30.0, 1e-6, "reach when the clock goes backwards (elapsed must not be negative)")


@c.test("TODO 14 and 15 — ncc() and find_day_twin(): night frame 1 is a copy of day frame 9",
        hint="NCC: subtract the means, sum of products over sqrt(product of sums of squares); 0.0 for a uniform "
             "picture. Twin: grey, resize both to `size` with INTER_AREA, best and second-best scores.")
def _():
    m = T()
    ncc, twin = need(m, "ncc", "find_day_twin")
    a = np.arange(100, dtype=np.uint8).reshape(10, 10)
    c.near(ncc(a, a), 1.0, 1e-9, "ncc(a, a)")
    c.near(ncc(a, 255 - a), -1.0, 1e-9, "ncc(a, 255 - a) (uint8: did you convert to float?)")
    c.near(ncc(a, np.full((10, 10), 7)), 0.0, 1e-9, "ncc(a, uniform picture)")
    rnd = np.random.default_rng(3)
    x, y = rnd.normal(size=(20, 30)), rnd.normal(size=(20, 30))
    c.near(ncc(x, x + 0.5 * y), float(np.corrcoef(x.ravel(), (x + 0.5 * y).ravel())[0, 1]), 1e-9, "ncc vs np.corrcoef")
    days = sorted(os.path.join(DAY, f) for f in os.listdir(DAY) if f.startswith("frame_") and f.endswith(".jpeg"))
    r = twin(os.path.join(THERMAL, "frame_0001_lat35.82883_lon10.63605_alt400m.jpg"), days)
    c.ok(isinstance(r, (tuple, list)) and len(r) == 3, f"find_day_twin should return (name, best, second), got {r!r}")
    c.eq(os.path.basename(str(r[0])), "frame_0009.jpeg", "the twin of night frame 0001")
    c.ok(r[1] > 0.85 and r[2] < 0.4, f"best {r[1]:.2f} (expected ~0.90), second {r[2]:.2f} (expected ~0.05)")


@c.test("python3 thermal.py runs, draws thermal_vs_map.png and writes the 'thermal' results",
        hint="Run `python3 thermal.py` and read its last lines; it takes ~30 s (900 picture comparisons).")
def _():
    if os.path.exists("thermal_vs_map.png"):
        os.remove("thermal_vs_map.png")
    code, out = sh("python3 thermal.py", timeout=150)
    c.ok(code == 0 and "Wrote the 'thermal' section" in out, "thermal.py did not finish:\n" + out[-700:])
    import cv2
    im = cv2.imread("thermal_vs_map.png")
    c.ok(im is not None and im.shape[1] > 3 * im.shape[0], "thermal_vs_map.png is not 3 pictures side by side")
    r = results().get("thermal", {})
    c.eq(r.get("twin_offsets"), [8], "the twin offsets (day number - night number, mod 30) in results.json")
    c.eq(r.get("gate_decisions"), [True, False, True], "the motion gate decisions in results.json")


SECTIONS = ["Sidereal time", "Polaris", "Error budget", "Night geometry", "The night replay set"]


def numbers(text):
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))]


@c.test("report.md: five sections, with your own numbers",
        hint="Keep the five '## ' headings of the template. Each section needs at least 40 words of your own. "
             "Quote the Monte Carlo median (Error budget), the minimum height at 45° (Night geometry) and the "
             "frame-number offset you found (The night replay set), as printed by your programs.")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8").read()
    parts = re.split(r"^##\s+", text, flags=re.M)[1:]
    sec = {}
    for p in parts:
        title, _, body = p.partition("\n")
        for s in SECTIONS:
            if title.strip().lower().startswith(s.lower()):
                sec[s] = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    for s in SECTIONS:
        c.ok(s in sec, f"the section '## {s}' is missing")
        n = len(re.findall(r"[A-Za-z]{2,}", sec[s]))
        c.ok(n >= 40, f"the section '{s}' has {n} words, at least 40 expected")
    r = results()
    med = r.get("stars", {}).get("mc_median_km_75")
    h45 = r.get("thermal", {}).get("min_alt_45deg_m")
    c.ok(med is not None and h45 is not None, "results.json is incomplete: run stars.py and thermal.py first")
    c.ok(any(abs(x - med) <= 0.1 * med for x in numbers(sec["Error budget"])),
         f"'Error budget' should quote your Monte Carlo median (~{med:.0f} km)")
    c.ok(any(abs(x - h45) <= 10 for x in numbers(sec["Night geometry"])),
         f"'Night geometry' should quote your minimum height at heading 45° (~{h45:.0f} m)")
    c.ok(8 in [int(x) for x in numbers(sec["The night replay set"]) if x == int(x)],
         "'The night replay set' should give the frame-number offset you found")


c.run()
