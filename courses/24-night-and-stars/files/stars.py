"""Lab 24 — where are the stars tonight, seen from Sousse?

Run:  python3 stars.py
It loads the bright stars of the Yale Bright Star Catalogue (/data/bsc5.dat), asks NAVERA's
own celestial code for the sidereal time, computes where each star is in the sky, prints a
table and draws sky.png. Fill in the four TODOs from top to bottom.
"""
import math

SOUSSE_LAT, SOUSSE_LON = 35.83, 10.64      # degrees (north, east)
WHEN_UTC = "2026-10-07 20:00:00"            # 21:00 in Tunisia (UTC+1)
EARTH_KM_PER_DEG = 111.195                  # 2 x pi x 6371 km / 360: one degree of the Earth's surface


# TODO 1: the altitude and azimuth of a star.
#   ra_deg, dec_deg : the star's right ascension and declination (degrees)
#   lat_deg, lon_deg: where you stand (degrees, east positive)
#   gast_deg        : the Greenwich sidereal time (degrees) — "the clock of the sky"
# Steps (all angles in degrees; math.sin/cos need radians: use math.radians / math.degrees):
#   1. local sidereal time  LST = gast_deg + lon_deg
#   2. hour angle           H = LST - ra_deg
#   3. sin(alt) = sin(dec)·sin(lat) + cos(dec)·cos(lat)·cos(H)          -> alt = asin(...)
#   4. az = atan2( -cos(dec)·sin(H),  sin(dec)·cos(lat) - cos(dec)·sin(lat)·cos(H) )
#      then bring it into 0..360 with  % 360
# Return (alt, az) in degrees.
def star_altaz(ra_deg, dec_deg, lat_deg, lon_deg, gast_deg):
    raise NotImplementedError("TODO 1")


# TODO 2: the stars above the horizon.
#   stars: a list of dicts {"name", "mag", "ra", "dec"} (from load_bright_stars below)
# For each star, compute (alt, az) with star_altaz. Keep the ones with alt > min_alt_deg.
# Return a list of dicts {"name", "mag", "alt", "az"}, sorted from the brightest
# (smallest magnitude) to the faintest.
def visible_stars(stars, lat_deg, lon_deg, gast_deg, min_alt_deg=0.0):
    raise NotImplementedError("TODO 2")


# TODO 3: your latitude from the altitude of Polaris (degrees).
# Polaris sits (almost) at the celestial north pole, and the pole's altitude above your
# horizon IS your latitude. Return the latitude in degrees.
def latitude_from_polaris(polaris_alt_deg):
    raise NotImplementedError("TODO 3")


# TODO 4: how far off a celestial position is when the camera's attitude is wrong.
# One degree of error in "where the camera points" moves the computed position by one degree
# of the Earth's surface: EARTH_KM_PER_DEG km. Return the error in km (always >= 0).
def position_error_km(attitude_error_deg):
    raise NotImplementedError("TODO 4")


# ---- you don't need to change anything below this line (but read it!) ----
import os  # noqa: E402

BSC_PATH = "/data/bsc5.dat" if os.path.exists("/data/bsc5.dat") else os.path.expanduser("~/.navera_sim/bsc5.dat")

# The catalogue numbers its stars (HR number) but gives no common names: here are some.
NAMES = {424: "Polaris", 7001: "Vega", 7557: "Altair", 7924: "Deneb", 5340: "Arcturus", 1708: "Capella",
         1457: "Aldebaran", 8728: "Fomalhaut", 2491: "Sirius", 2061: "Betelgeuse", 1713: "Rigel",
         6134: "Antares", 5056: "Spica", 2943: "Procyon", 2990: "Pollux", 3982: "Regulus", 472: "Achernar",
         2326: "Canopus", 1017: "Mirfak", 15: "Alpheratz", 4301: "Dubhe", 5191: "Alkaid", 168: "Schedar",
         617: "Hamal", 936: "Algol", 4905: "Alioth", 337: "Mirach", 603: "Almach", 8308: "Enif",
         8775: "Scheat", 8781: "Markab", 5563: "Kochab", 6556: "Rasalhague", 6705: "Eltanin", 7121: "Nunki",
         6879: "Kaus Australis", 188: "Diphda", 99: "Ankaa", 6527: "Shaula", 21: "Caph", 8162: "Alderamin",
         7796: "Sadr", 264: "Navi", 5054: "Mizar", 2088: "Menkalinan", 8425: "Alnair", 5793: "Alphecca",
         6217: "Atria", 4819: "Menkent", 39: "Algenib"}
SKIP = {5958}    # T CrB: a nova the catalogue lists at its 1946 outburst brightness — normally invisible


def load_bright_stars(path=BSC_PATH, max_mag=2.5):
    """Stars of the Yale Bright Star Catalogue brighter than max_mag (smaller = brighter).
    The file has one star per line, in fixed columns (J2000 positions):
      cols 1-4 HR number | 5-14 name | 76-83 RA hhmmss.s | 84-90 Dec ±ddmmss | 103-107 V magnitude"""
    stars = []
    with open(path, encoding="latin-1") as f:
        for line in f:
            if len(line) < 107 or not line[75:83].strip() or not line[102:107].strip():
                continue                                   # a few entries have no position
            mag = float(line[102:107])
            if mag > max_mag:
                continue
            hr = int(line[0:4])
            if hr in SKIP:
                continue
            ra = 15.0 * (int(line[75:77]) + int(line[77:79]) / 60.0 + float(line[79:83]) / 3600.0)
            sign = -1.0 if line[83] == "-" else 1.0
            dec = sign * (int(line[84:86]) + int(line[86:88]) / 60.0 + int(line[88:90]) / 3600.0)
            name = NAMES.get(hr) or (" ".join(line[7:14].split()) or f"HR {hr}")   # "Bet Aur" = beta of Auriga
            stars.append({"hr": hr, "name": name, "mag": mag, "ra": ra, "dec": dec})
    return stars


def navera_sky_clock(when_utc):
    """NAVERA's celestial_math: Greenwich sidereal time, and a function that moves catalogue
    (J2000) positions to the date (precession: ~0.36 deg in 26 years)."""
    import logging
    import warnings
    warnings.filterwarnings("ignore")
    from astropy import log
    log.setLevel(logging.ERROR)                        # (no warnings about the missing internet tables)
    from astropy.utils import iers
    iers.conf.auto_download = False                    # no internet on the box: use the built-in tables
    iers.conf.iers_degraded_accuracy = "ignore"        # (UT1 within ~1 s: 0.004 deg — fine here)
    from cn_pkg.nodes.celestial_math import apparent_radec, gast_deg
    return gast_deg(when_utc), lambda ra, dec: apparent_radec(ra, dec, when_utc)


def sky_plot(visible, path="sky.png", title=""):
    """The sky as a round map: centre = straight up (zenith), edge = horizon.
    Like lying on your back with your head to the north: east is on the LEFT."""
    import warnings
    warnings.filterwarnings("ignore")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(7, 7))
    ax = fig.add_subplot(projection="polar")
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(1)                          # N at the top, E on the left
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


def _todo(fn, *a):
    """Calls fn; None when its TODO is not done yet."""
    try:
        return fn(*a)
    except NotImplementedError as e:
        print(f"  ({e} is not done yet)")
        return None


if __name__ == "__main__":
    stars = load_bright_stars(max_mag=2.5)
    print(f"{len(stars)} stars brighter than magnitude 2.5 in the catalogue")
    gast, to_date = navera_sky_clock(WHEN_UTC)
    print(f"Greenwich sidereal time at {WHEN_UTC} UTC (NAVERA's gast_deg): {gast:.3f} deg")
    for s in stars:                                    # catalogue (J2000) -> positions of the date
        s["ra"], s["dec"] = to_date(s["ra"], s["dec"])

    vis = _todo(visible_stars, stars, SOUSSE_LAT, SOUSSE_LON, gast)
    if vis is not None:
        print(f"\n{len(vis)} of them are above the horizon of Sousse:\n")
        print(f"  {'star':16s} {'mag':>5s} {'altitude':>9s} {'azimuth':>8s}")
        for v in vis[:15]:
            print(f"  {v['name']:16s} {v['mag']:5.2f} {v['alt']:8.1f}° {v['az']:7.1f}°")
        if len(vis) > 15:
            print(f"  … and {len(vis) - 15} more")
        sky_plot(vis, "sky.png", f"Sousse, {WHEN_UTC} UTC — {len(vis)} stars brighter than 2.5")
        print("\nSaved sky.png — open it in the editor.")

    polaris = next(s for s in stars if s["name"] == "Polaris")
    pa = _todo(star_altaz, polaris["ra"], polaris["dec"], SOUSSE_LAT, SOUSSE_LON, gast)
    if pa is not None:
        lat = _todo(latitude_from_polaris, pa[0])
        print(f"\nPolaris: altitude {pa[0]:.2f}°, azimuth {pa[1]:.2f}°")
        if lat is not None:
            print(f"Latitude from Polaris: {lat:.2f}°  (true: {SOUSSE_LAT}°, off by {abs(lat - SOUSSE_LAT):.2f}° "
                  f"= {abs(lat - SOUSSE_LAT) * EARTH_KM_PER_DEG:.0f} km)")
        # NAVERA's inverse function must give the star back from its altitude/azimuth
        from cn_pkg.nodes.celestial_math import local_to_radec
        ra, dec = local_to_radec(SOUSSE_LAT, SOUSSE_LON, pa[0], pa[1], gast)
        print(f"Round trip through NAVERA's local_to_radec: RA {ra:.3f}° (star {polaris['ra']:.3f}°), "
              f"Dec {dec:.3f}° (star {polaris['dec']:.3f}°)")

    print("\nAttitude error -> position error:")
    for e in (0.1, 0.5, 1.0, 2.0):
        km = _todo(position_error_km, e)
        if km is None:
            break
        print(f"  {e:4.1f}°  ->  {km:6.1f} km")
