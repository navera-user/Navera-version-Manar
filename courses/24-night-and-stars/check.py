import math
import os
import random
import sys

from academy_check import Checker, load_student, need, sh

c = Checker()

G = 316.48                     # Greenwich sidereal time at 2026-10-07 20:00 UTC (degrees)
SOUSSE = (35.83, 10.64)
BSC = "/data/bsc5.dat"


def stars_mod():
    return load_student("stars.py")


def navera_local_to_radec():
    try:
        from cn_pkg.nodes.celestial_math import local_to_radec
    except ImportError:
        sys.path.insert(0, os.path.expanduser("~/navera/cn_pkg"))
        from cn_pkg.nodes.celestial_math import local_to_radec
    return local_to_radec


def altaz(ra, dec, lat=SOUSSE[0], lon=SOUSSE[1], g=G):
    (f,) = need(stars_mod(), "star_altaz")
    r = f(ra, dec, lat, lon, g)
    c.ok(isinstance(r, (tuple, list)) and len(r) == 2, f"star_altaz should return (alt, az), got {r!r}")
    return float(r[0]), float(r[1])


@c.test("star_altaz: a star exactly overhead has altitude 90°",
        hint="Overhead means dec = your latitude and hour angle H = 0 (RA = GAST + longitude). "
             "Did you turn degrees into radians before sin/cos, and asin's result back into degrees?")
def _():
    alt, _ = altaz(G + SOUSSE[1], SOUSSE[0])
    c.near(alt, 90.0, tol=0.05, what="the altitude")


@c.test("star_altaz: Vega seen from Sousse at 21:00 (Tunisian time) on 7 October 2026",
        hint="Check the sign of H = LST − RA, LST = GAST + longitude, and that the azimuth is in 0..360 (% 360).")
def _():
    alt, az = altaz(279.2346, 38.7837)
    c.near(alt, 52.23, tol=0.1, what="Vega's altitude")
    c.near(az, 289.24, tol=0.1, what="Vega's azimuth")


@c.test("star_altaz agrees with NAVERA's local_to_radec (cn_pkg) on 20 random stars",
        hint="NAVERA's function goes the other way (alt/az → RA/Dec). If the altitude is right but this fails, "
             "look at the azimuth: atan2(-cos(dec)·sin(H), sin(dec)·cos(lat) − cos(dec)·sin(lat)·cos(H)).")
def _():
    l2r = navera_local_to_radec()
    rnd = random.Random(24)
    for _ in range(20):
        ra, dec = rnd.uniform(0, 360), rnd.uniform(-60, 85)
        lat, lon = rnd.uniform(-50, 60), rnd.uniform(-170, 170)
        g = rnd.uniform(0, 360)
        alt, az = altaz(ra, dec, lat, lon, g)
        c.ok(0.0 <= az < 360.0, f"azimuth {az:.2f} is not in 0..360")
        if alt > 85:
            continue                      # azimuth is not well defined near the zenith
        ra2, dec2 = l2r(lat, lon, alt, az, g)
        dra = (ra2 - ra + 180) % 360 - 180
        c.ok(abs(dec2 - dec) < 0.01 and abs(dra) * math.cos(math.radians(dec)) < 0.01,
             f"for RA {ra:.1f}°, Dec {dec:.1f}° seen from ({lat:.1f}, {lon:.1f}) you give alt {alt:.2f}°, "
             f"az {az:.2f}° — NAVERA turns that back into RA {ra2:.2f}°, Dec {dec2:.2f}°")


@c.test("visible_stars: the bright stars above Sousse's horizon, brightest first",
        hint="Keep a star only when its altitude is > min_alt_deg; return dicts with name, mag, alt, az; "
             "sort with sorted(..., key=lambda v: v['mag']).")
def _():
    m = stars_mod()
    load, vis = need(m, "load_bright_stars", "visible_stars")
    stars = load(BSC, 2.5)
    v = vis(stars, SOUSSE[0], SOUSSE[1], G)
    c.ok(isinstance(v, list), f"visible_stars should return a list, got {type(v).__name__}")
    c.ok(len(v) > 0, "the list is empty")
    c.ok(all(isinstance(x, dict) and {"name", "mag", "alt", "az"} <= set(x) for x in v),
         "each item should be a dict with the keys name, mag, alt, az")
    c.ok(all(x["alt"] > 0 for x in v), "a star below the horizon (alt <= 0) is in the list")
    c.ok(abs(len(v) - 40) <= 1, f"{len(v)} stars above the horizon, expected 40 (of {len(stars)})")
    mags = [x["mag"] for x in v]
    c.ok(mags == sorted(mags), "the list is not sorted from the brightest (smallest mag) to the faintest")
    c.eq(v[0]["name"], "Vega", "the brightest star above the horizon")


@c.test("latitude_from_polaris gives your latitude within 1°",
        hint="The altitude of the celestial pole above your horizon equals your latitude, and Polaris is "
             "less than 1° from the pole.")
def _():
    (f,) = need(stars_mod(), "latitude_from_polaris")
    c.near(f(36.07), SOUSSE[0], tol=1.0, what="latitude_from_polaris(36.07) (Polaris from Sousse)")
    c.near(f(48.3), 48.85, tol=1.0, what="latitude_from_polaris(48.3) (Polaris from Paris)")


@c.test("position_error_km: 1° of attitude error ≈ 111 km",
        hint="Multiply the error in degrees by EARTH_KM_PER_DEG, and use abs() so a negative error "
             "gives a positive distance.")
def _():
    (f,) = need(stars_mod(), "position_error_km")
    c.near(f(1.0), 111.2, tol=0.5, what="position_error_km(1.0)")
    c.near(f(0.5), 55.6, tol=0.3, what="position_error_km(0.5)")
    c.near(f(-2.0), 222.4, tol=1.0, what="position_error_km(-2.0)")


@c.test("python3 stars.py runs and draws sky.png",
        hint="Run `python3 stars.py` in the terminal and read the last lines of the error, if any.")
def _():
    if os.path.exists("sky.png"):
        os.remove("sky.png")
    code, out = sh("python3 stars.py", timeout=90)
    c.ok(code == 0, "stars.py stopped with an error:\n" + out[-600:])
    c.file_exists("sky.png")
    import cv2
    c.ok(cv2.imread("sky.png") is not None, "sky.png is not a readable picture")


def thermal_mod():
    return load_student("thermal.py")


@c.test("parse_thermal_name reads lat, lon and alt — and None for a NOGPS frame",
        hint="Split the name without '.jpg' on '_'; a part starting with 'lat' gives float(part[3:]); "
             "for 'alt400m' remove the 'm'. If there is no lat/lon, return None.")
def _():
    (f,) = need(thermal_mod(), "parse_thermal_name")
    r = f("frame_0002_lat35.83026_lon10.64111_alt400m.jpg")
    c.ok(isinstance(r, (tuple, list)) and len(r) == 3, f"expected (lat, lon, alt), got {r!r}")
    c.near(r[0], 35.83026, 1e-6, "lat")
    c.near(r[1], 10.64111, 1e-6, "lon")
    c.near(r[2], 400.0, 1e-6, "alt")
    r = f("/data/navera_data/x/frame_0031_lat-12.5_lon-3.25_alt250m.jpg")
    c.ok(r is not None and abs(r[0] + 12.5) < 1e-9 and abs(r[1] + 3.25) < 1e-9 and abs(r[2] - 250) < 1e-9,
         f"a full path with negative coordinates gave {r!r}")
    c.ok(f("frame_0004_NOGPS_alt400m.jpg") is None, "a NOGPS frame should give None")


@c.test("scale_to_map: the frame resized to the map's resolution, like NAVERA's night localizer",
        hint="footprint = 2·alt·tan(hfov/2) (radians!), gsd_cam = footprint / width, scale = gsd_cam / m_per_px(lat, zoom).")
def _():
    (f,) = need(thermal_mod(), "scale_to_map")
    for alt, hfov, w, lat in ((400.0, 84.0, 1536, 35.85), (250.0, 60.0, 640, 35.70)):
        mpp_map = 40075016.7 * math.cos(math.radians(lat)) / 2 ** 17 / 256.0
        want = 2 * alt * math.tan(math.radians(hfov) / 2) / w / mpp_map
        c.near(f(alt, hfov, w, lat), want, tol=want * 0.002, what=f"scale_to_map({alt}, {hfov}, {w}, {lat})")


@c.test("python3 thermal.py runs and draws thermal_vs_map.png",
        hint="Run `python3 thermal.py` in the terminal once TODO 5 and 6 work, and read the error, if any.")
def _():
    if os.path.exists("thermal_vs_map.png"):
        os.remove("thermal_vs_map.png")
    code, out = sh("python3 thermal.py", timeout=60)
    c.ok(code == 0, "thermal.py stopped with an error:\n" + out[-600:])
    c.file_exists("thermal_vs_map.png")
    import cv2
    im = cv2.imread("thermal_vs_map.png")
    c.ok(im is not None and im.shape[1] > 3 * im.shape[0], "thermal_vs_map.png does not look like 3 pictures side by side")


ANSWERS = {"Q1": ("a", "Read 'Seeing heat' in the course again: what does a thermal camera measure?"),
           "Q2": ("b", "Look at the picture really: same streets? same houses? Then read the warning box of lab step 6."),
           "Q3": ("b", "Read 'Two answers, one prior' in the course."),
           "Q4": ("b", "The table 'What NAVERA measured' in the course gives it.")}

for q, (good, hint) in ANSWERS.items():
    @c.test(f"quiz {q}", hint=hint)
    def _(q=q, good=good):
        (v,) = need(load_student("answers.py"), q)
        v = str(v).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f"{q} = \"{v}\" is not the right answer")

c.run()
