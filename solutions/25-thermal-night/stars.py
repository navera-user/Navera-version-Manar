"""Lab 25, part A — the sky above Tenerife, computed from first principles.

Run:  python3 stars.py
You implement the chain  calendar date -> Julian date -> sidereal time -> hour angle ->
altitude/azimuth, compare every step with astropy and with NAVERA's cn_pkg, then measure
what clock and attitude errors cost a celestial fix. Fill in the TODOs from top to bottom.
The program prints a report, draws sky.png and writes the "stars" part of results.json.
"""
import math

import numpy as np

TEIDE = (28.30, -16.51)                     # observing site: Teide Observatory, Tenerife (deg N, deg E; west < 0)
NEW_YORK = (40.71, -74.01)
WHEN = (2026, 10, 7, 20, 0, 0.0)            # UTC: 21:00 in Tenerife (UTC+1 in October)
EARTH_KM_PER_DEG = 111.195                  # 2*pi*6371 km / 360: one degree of a great circle
SIDEREAL_DEG_PER_S = 360.98564736629 / 86400.0   # how fast the sky turns (deg per second of UT)


# TODO 1 — Julian date (Meeus, "Astronomical Algorithms", ch. 7), Gregorian calendar.
#   if month <= 2: year -= 1; month += 12
#   A = floor(year / 100);  B = 2 - A + floor(A / 4)
#   JD = floor(365.25 (year + 4716)) + floor(30.6001 (month + 1)) + day + B - 1524.5
#   then add the time of day as a fraction of a day: (hour + minute/60 + second/3600) / 24
def julian_date(year, month, day, hour=0, minute=0, second=0.0):
    if month <= 2:
        year -= 1
        month += 12
    a = math.floor(year / 100)
    b = 2 - a + math.floor(a / 4)
    jd = math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + b - 1524.5
    return jd + (hour + minute / 60.0 + second / 3600.0) / 24.0


# TODO 2 — Greenwich MEAN sidereal time in degrees, 0 <= GMST < 360 (IAU 1982, Meeus 12.4):
#   T = (JD - 2451545.0) / 36525
#   GMST = 280.46061837 + 360.98564736629 (JD - 2451545.0) + 0.000387933 T^2 - T^3 / 38710000
def gmst_deg(jd):
    d = jd - 2451545.0
    t = d / 36525.0
    g = 280.46061837 + 360.98564736629 * d + 0.000387933 * t * t - t ** 3 / 38710000.0
    return g % 360.0


# TODO 3 — equatorial (RA, Dec) -> horizontal (altitude, azimuth), VECTORISED with numpy.
#   ra_deg, dec_deg may be numbers or numpy arrays; gst_deg is the Greenwich sidereal time.
#   LST = gst + lon,   H = LST - RA   (hour angle)
#   sin(alt) = sin(dec) sin(lat) + cos(dec) cos(lat) cos(H)
#   az = atan2(-cos(dec) sin(H),  sin(dec) cos(lat) - cos(dec) sin(lat) cos(H))   in 0..360
#   Return (alt, az) in degrees, as numpy arrays (or numpy floats for one star).
def radec_to_altaz(ra_deg, dec_deg, lat_deg, lon_deg, gst_deg):
    H = np.radians(gst_deg + lon_deg - np.asarray(ra_deg, float))
    d, p = np.radians(np.asarray(dec_deg, float)), math.radians(lat_deg)
    s = np.sin(d) * math.sin(p) + np.cos(d) * math.cos(p) * np.cos(H)
    alt = np.degrees(np.arcsin(np.clip(s, -1.0, 1.0)))
    az = np.degrees(np.arctan2(-np.cos(d) * np.sin(H), np.sin(d) * math.cos(p) - np.cos(d) * math.sin(p) * np.cos(H)))
    return alt, az % 360.0


# GIVEN 4 (already written for you: read it, nothing to change) — the stars above min_alt_deg, brightest (smallest magnitude) first.
#   stars: list of dicts {"name", "mag", "ra", "dec"}. Use ONE call of radec_to_altaz on arrays.
#   Return a list of dicts {"name", "mag", "alt", "az"} (plain Python floats).
def visible_stars(stars, lat_deg, lon_deg, gst_deg, min_alt_deg=0.0):
    ra = np.array([s["ra"] for s in stars])
    dec = np.array([s["dec"] for s in stars])
    alt, az = radec_to_altaz(ra, dec, lat_deg, lon_deg, gst_deg)
    out = [{"name": s["name"], "mag": s["mag"], "alt": float(a), "az": float(z)}
           for s, a, z in zip(stars, alt, az) if a > min_alt_deg]
    return sorted(out, key=lambda v: v["mag"])


# TODO 5 — latitude from the measured altitude of Polaris.
#   Without more information: latitude = altitude.
#   With Polaris' hour angle H (deg) and its polar distance p = 90 - dec (deg), the first-order
#   correction is   latitude = altitude - p cos(H).
def polaris_latitude(alt_deg, ha_deg=None, polar_dist_deg=None):
    if ha_deg is None or polar_dist_deg is None:
        return float(alt_deg)
    return float(alt_deg - polar_dist_deg * math.cos(math.radians(ha_deg)))


# TODO 6 — the zenith fix: a camera pointing EXACTLY straight up, plate-solved to (ra, dec).
#   The zenith has declination = latitude and right ascension = local sidereal time.
#   Return (lat, lon) with lon in [-180, 180).
def zenith_fix(ra_deg, dec_deg, gst_deg):
    return float(dec_deg), float((ra_deg - gst_deg + 540.0) % 360.0 - 180.0)


# TODO 7 — what errors cost, in km.
#   attitude_error_km: a pointing error of e degrees moves the fix by e degrees of great circle.
#   clock_error_km: a clock wrong by dt seconds turns the sky by SIDEREAL_DEG_PER_S * dt degrees
#   of LONGITUDE; one degree of longitude is EARTH_KM_PER_DEG * cos(latitude) km.
#   Both return a distance >= 0.
def attitude_error_km(error_deg):
    return abs(error_deg) * EARTH_KM_PER_DEG


def clock_error_km(dt_s, lat_deg):
    return abs(dt_s) * SIDEREAL_DEG_PER_S * EARTH_KM_PER_DEG * math.cos(math.radians(lat_deg))


# TODO 8 — Monte Carlo: NAVERA's own fix with a noisy IMU.
#   rng = np.random.default_rng(seed) (same seed -> same numbers). For i in range(n): draw a tilt error ~ N(0, sigma_tilt_deg) and a heading error
#   ~ N(0, sigma_heading_deg) with rng.normal; the IMU then reports the camera at
#   (cam_alt + tilt error, cam_az + heading error). Ask NAVERA (functions passed in `cn`)
#   for the observer: cands = cn.observer_candidates(alt, az, ra, dec, gst);
#   fix = cn.choose_candidate(cands, site[0], site[1]). If fix is None count it as
#   ambiguous, otherwise append haversine_km(site, fix).
#   (ra, dec) is what the camera REALLY sees: cn.local_to_radec(site lat, lon, cam_alt, cam_az, gst).
#   Return (numpy array of errors in km, number of ambiguous fixes).
def monte_carlo_fix(cn, site, gst, cam_alt, cam_az, sigma_tilt_deg, sigma_heading_deg, n=2000, seed=24):
    rng = np.random.default_rng(seed)
    ra, dec = cn.local_to_radec(site[0], site[1], cam_alt, cam_az, gst)
    errs, amb = [], 0
    for _ in range(n):
        a = cam_alt + rng.normal(0.0, sigma_tilt_deg)
        z = cam_az + rng.normal(0.0, sigma_heading_deg)
        fix = cn.choose_candidate(cn.observer_candidates(a, z, ra, dec, gst), site[0], site[1])
        if fix is None:
            amb += 1
        else:
            errs.append(haversine_km(site, fix))
    return np.array(errs), amb


# ---- you don't need to change anything below this line (but read it!) ----
import json  # noqa: E402
import os  # noqa: E402
import types  # noqa: E402

BSC_PATH = "/data/bsc5.dat" if os.path.exists("/data/bsc5.dat") else os.path.expanduser("~/.navera_sim/bsc5.dat")
NAMES = {424: "Polaris", 7001: "Vega", 7557: "Altair", 7924: "Deneb", 5340: "Arcturus", 1708: "Capella",
         1457: "Aldebaran", 8728: "Fomalhaut", 2491: "Sirius", 2061: "Betelgeuse", 1713: "Rigel",
         6134: "Antares", 5056: "Spica", 2943: "Procyon", 2990: "Pollux", 3982: "Regulus", 472: "Achernar",
         2326: "Canopus", 1017: "Mirfak", 15: "Alpheratz", 4301: "Dubhe", 5191: "Alkaid", 168: "Schedar",
         617: "Hamal", 936: "Algol", 4905: "Alioth", 337: "Mirach", 603: "Almach", 8308: "Enif",
         8775: "Scheat", 8781: "Markab", 5563: "Kochab", 6556: "Rasalhague", 6705: "Eltanin", 7121: "Nunki",
         6879: "Kaus Australis", 188: "Diphda", 99: "Ankaa", 6527: "Shaula", 21: "Caph", 8162: "Alderamin",
         7796: "Sadr", 264: "Navi", 5054: "Mizar", 2088: "Menkalinan", 8425: "Alnair", 5793: "Alphecca",
         6217: "Atria", 4819: "Menkent", 39: "Algenib"}
# HR 264 is Gamma Cassiopeiae. It has no classical name; Apollo astronauts called it "Navi" (Ivan, the
# middle name of astronaut Gus Grissom, spelled backwards) and used it as a navigation star. A real
# nickname, not a bug and not our swallow.
SKIP = {5958}    # T CrB: a nova the catalogue lists at its 1946 outburst brightness


def load_bright_stars(path=BSC_PATH, max_mag=2.5):
    """Stars of the Yale Bright Star Catalogue brighter than max_mag (J2000 positions, degrees).
    Fixed columns: 1-4 HR number | 76-83 RA hhmmss.s | 84-90 Dec +-ddmmss | 103-107 V magnitude."""
    stars = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            if len(line) < 107 or not line[75:83].strip() or not line[102:107].strip():
                continue
            mag = float(line[102:107])
            hr = int(line[0:4])
            if mag > max_mag or hr in SKIP:
                continue
            ra = 15.0 * (int(line[75:77]) + int(line[77:79]) / 60.0 + float(line[79:83]) / 3600.0)
            sign = -1.0 if line[83] == "-" else 1.0
            dec = sign * (int(line[84:86]) + int(line[86:88]) / 60.0 + int(line[88:90]) / 3600.0)
            name = NAMES.get(hr) or (" ".join(line[7:14].split()) or f"HR {hr}")
            stars.append({"hr": hr, "name": name, "mag": mag, "ra": ra, "dec": dec})
    return stars


def haversine_km(p, q):
    """Great-circle distance between (lat, lon) points p and q, in km (lesson 6)."""
    p1, p2 = math.radians(p[0]), math.radians(q[0])
    dp, dl = p2 - p1, math.radians(q[1] - p[1])
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(min(1.0, a)))


def offline_astropy():
    """astropy, set up for a box WITHOUT internet (the sandbox, a drone in flight).
    astropy wants the IERS Earth-rotation tables (UT1-UTC, polar motion) and tries to download
    them. We forbid the download and accept the degraded accuracy: UT1-UTC is then taken as 0
    (it is always below 0.9 s, i.e. < 0.004 deg of sky rotation). Keep these lines."""
    import logging
    import warnings
    warnings.filterwarnings("ignore")
    from astropy import log
    log.setLevel(logging.ERROR)
    from astropy.utils import iers
    iers.conf.auto_download = False
    iers.conf.iers_degraded_accuracy = "ignore"
    import astropy.units as u
    from astropy.coordinates import TETE, AltAz, EarthLocation, SkyCoord
    from astropy.time import Time
    return types.SimpleNamespace(u=u, TETE=TETE, AltAz=AltAz, EarthLocation=EarthLocation,
                                 SkyCoord=SkyCoord, Time=Time)


def navera_cn():
    """NAVERA's celestial functions (cn_pkg/cn_pkg/nodes/celestial_math.py)."""
    try:
        from cn_pkg.nodes import celestial_math as cm
    except ImportError:
        import sys
        sys.path.insert(0, os.path.expanduser("~/navera/cn_pkg"))
        from cn_pkg.nodes import celestial_math as cm
    return cm


def utc_string(when):
    y, mo, d, h, mi, s = when
    return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:06.3f}"


def sky_plot(visible, path="sky.png", title=""):
    """The sky as a round map: centre = zenith, edge = horizon; north at the top, east on the LEFT
    (you lie on your back, head to the north)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(1)
    ax.set_facecolor("#0b1d33")
    ax.set_ylim(0, 90)
    ax.set_yticks([30, 60, 90])
    ax.set_yticklabels(["60°", "30°", "0°"], color="#9fb3c8")
    ax.set_xticks([math.radians(a) for a in (0, 90, 180, 270)])
    ax.set_xticklabels(["N", "E", "S", "W"])
    for v in visible:
        size = max(4.0, 60.0 * 10 ** (-0.25 * (v["mag"] + 1.5)))
        ax.scatter(math.radians(v["az"]), 90 - v["alt"], s=size, color="white" if v["name"] != "Polaris" else "#f2a33a")
        if v["mag"] < 1.6 or v["name"] == "Polaris":
            ax.annotate(v["name"], (math.radians(v["az"]), 90 - v["alt"]), color="#f2d39a", fontsize=8,
                        xytext=(4, 4), textcoords="offset points")
    ax.set_title(title, fontsize=10)
    fig.savefig(path, dpi=90, bbox_inches="tight")
    plt.close(fig)


def save_results(section, values, path="results.json"):
    """Merge {section: values} into results.json (thermal.py writes its own section)."""
    data = {}
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
    data[section] = values
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


class Todo(Exception):
    pass


def _do(fn, *a, **k):
    try:
        return fn(*a, **k)
    except NotImplementedError as e:
        print(f"  ({e} is not done yet)")
        raise Todo()


def main():
    res = {}
    when_s = utc_string(WHEN)
    print(f"Time: {when_s} UTC (21:00 in Tenerife). Site: Teide Observatory {TEIDE}.\n")
    ap = offline_astropy()
    t = ap.Time(when_s, scale="utc")
    cn = navera_cn()

    # 1-2. the sky's clock
    jd = _do(julian_date, *WHEN)
    print(f"Julian date        yours {jd:.6f}   astropy {t.jd:.6f}")
    res["jd"] = jd
    g = _do(gmst_deg, jd)
    g_ap = float(t.sidereal_time("mean", "greenwich").deg)
    gast = float(cn.gast_deg(when_s))
    print(f"GMST (deg)         yours {g:.5f}   astropy {g_ap:.5f}   diff {(g - g_ap) * 3600:+.2f} arcsec")
    print(f"GAST (deg)         NAVERA gast_deg {gast:.5f}  -> equation of the equinoxes "
          f"{(gast - g_ap) * 240:+.3f} s of time")
    res.update(gmst_deg=g, gmst_astropy_deg=g_ap, gmst_diff_arcsec=(g - g_ap) * 3600.0, gast_navera_deg=gast,
               equation_of_equinoxes_s=(gast - g_ap) * 240.0)

    # 3. alt/az vs astropy for the 10 brightest stars
    stars = load_bright_stars(max_mag=2.5)
    for s in stars:                                  # catalogue J2000 -> true equator of date (NAVERA)
        s["ra"], s["dec"] = cn.apparent_radec(s["ra"], s["dec"], when_s)
    top = sorted(stars, key=lambda s: s["mag"])[:10]
    alt, az = _do(radec_to_altaz, np.array([s["ra"] for s in top]), np.array([s["dec"] for s in top]),
                  TEIDE[0], TEIDE[1], gast)
    loc = ap.EarthLocation(lat=TEIDE[0] * ap.u.deg, lon=TEIDE[1] * ap.u.deg, height=0 * ap.u.m)
    cat = ap.SkyCoord(ra=[s["ra"] for s in top] * ap.u.deg, dec=[s["dec"] for s in top] * ap.u.deg,
                      frame=ap.TETE(obstime=t))
    ref = cat.transform_to(ap.AltAz(obstime=t, location=loc))
    dalt = np.abs(alt - ref.alt.deg)
    daz = np.abs((az - ref.az.deg + 180) % 360 - 180) * np.cos(np.radians(alt))
    worst = float(np.max(np.hypot(dalt, daz)))
    print(f"\nAlt/az of the 10 brightest stars vs astropy AltAz: worst difference {worst * 3600:.1f} arcsec")
    res["altaz_worst_diff_arcsec"] = worst * 3600.0

    # 4. what is up tonight
    vis = _do(visible_stars, stars, TEIDE[0], TEIDE[1], gast)
    print(f"\n{len(vis)} of {len(stars)} stars brighter than 2.5 are above the horizon of Teide Observatory:")
    for v in vis[:10]:
        print(f"  {v['name']:16s} mag {v['mag']:5.2f}  alt {v['alt']:5.1f}°  az {v['az']:5.1f}°")
    sky_plot(vis, "sky.png", f"Teide Observatory, {when_s[:16]} UTC — {len(vis)} stars brighter than 2.5")
    print("Saved sky.png")
    res["n_visible"] = len(vis)
    res["brightest_visible"] = vis[0]["name"] if vis else None

    # 5. Polaris from New York, over a whole sidereal day
    pol = next(s for s in stars if s["name"] == "Polaris")
    p = 90.0 - pol["dec"]
    gs = (gast + np.arange(0, 360, 3.75))            # the sky every ~15 min of a sidereal day
    a_pol, _ = radec_to_altaz(np.full(gs.size, pol["ra"]), np.full(gs.size, pol["dec"]), NEW_YORK[0], NEW_YORK[1], gs)
    ha = gs + NEW_YORK[1] - pol["ra"]
    plain = np.array([_do(polaris_latitude, a) for a in a_pol]) - NEW_YORK[0]
    corr = np.array([_do(polaris_latitude, a, h, p) for a, h in zip(a_pol, ha)]) - NEW_YORK[0]
    print(f"\nPolaris from New York: polar distance p = {p:.3f}°")
    print(f"  latitude = altitude           worst error {np.abs(plain).max():.3f}° = "
          f"{np.abs(plain).max() * EARTH_KM_PER_DEG:.0f} km")
    print(f"  latitude = altitude - p cos H worst error {np.abs(corr).max():.4f}° = "
          f"{np.abs(corr).max() * EARTH_KM_PER_DEG:.2f} km")
    res.update(polaris_polar_distance_deg=p, polaris_max_err_plain_km=float(np.abs(plain).max() * EARTH_KM_PER_DEG),
               polaris_max_err_corrected_km=float(np.abs(corr).max() * EARTH_KM_PER_DEG))

    # 6. the zenith fix: what the solver would say for a perfectly levelled camera at Teide Observatory
    ra_z, dec_z = cn.local_to_radec(TEIDE[0], TEIDE[1], 90.0, 0.0, gast)
    zf = _do(zenith_fix, ra_z, dec_z, gast)
    print(f"\nZenith fix from the plate-solved centre RA {ra_z:.3f}°, Dec {dec_z:.3f}°: "
          f"({zf[0]:.3f}, {zf[1]:.3f}) — {haversine_km(TEIDE, zf):.3f} km from the truth")

    # 7. error budget
    print("\nError budget:")
    for e in (0.1, 0.3, 0.5, 1.0):
        print(f"  attitude {e:3.1f}°  -> {_do(attitude_error_km, e):6.1f} km")
    for dt in (1.0, 4.0, 60.0):
        print(f"  clock {dt:4.0f} s   -> {_do(clock_error_km, dt, NEW_YORK[0]):6.2f} km (at New York's latitude)")
    res["attitude_km_per_deg"] = attitude_error_km(1.0)
    res["clock_km_per_s_new_york"] = clock_error_km(1.0, NEW_YORK[0])

    # 8. Monte Carlo with a BNO085-class IMU (0.3° tilt, 1.5° heading), camera 75° up towards the north-east
    errs, amb = _do(monte_carlo_fix, cn, TEIDE, gast, 75.0, 45.0, 0.3, 1.5)
    errs0, _ = monte_carlo_fix(cn, TEIDE, gast, 90.0, 0.0, 0.3, 1.5)
    print(f"\nMonte Carlo, 2000 fixes, IMU 0.3° tilt / 1.5° heading:")
    print(f"  camera 75° up : median {np.median(errs):.1f} km, p90 {np.percentile(errs, 90):.1f} km, "
          f"ambiguous {amb}")
    print(f"  camera 90° up : median {np.median(errs0):.1f} km, p90 {np.percentile(errs0, 90):.1f} km")
    res.update(mc_median_km_75=float(np.median(errs)), mc_p90_km_75=float(np.percentile(errs, 90)),
               mc_ambiguous_75=int(amb), mc_median_km_90=float(np.median(errs0)))
    save_results("stars", res)
    print("\nWrote the 'stars' section of results.json")


if __name__ == "__main__":
    try:
        main()
    except Todo:
        print("\nStopped at the first TODO that is not done yet.")
