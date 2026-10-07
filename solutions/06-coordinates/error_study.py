# Error study: how wrong are the shortcuts, as a function of distance?
# Uses YOUR functions from geo_lab.py (finish TODO 1-9 first) and the ellipsoid reference
# of geodesic_ref.py. Writes results.json and error_study.png.
#     python3 error_study.py
#
# Method (home = Sousse, NAVERA's test area, height 0):
#   for each distance d (10 m ... 300 km, log-spaced) and each of 8 bearings:
#     1. the "true" point is (east, north, up) = (d sin θ, d cos θ, 0) in the EXACT ENU frame
#        -> enu_to_geodetic() gives its (lat, lon)
#     2. NAVERA's shortcut:       flat_en(lat, lon, home)            -> (e1, n1)
#        the same with WGS84 radii: (Δlon · N cos φ0, Δlat · M) in radians -> (e2, n2)
#        error = horizontal distance between the shortcut and the exact (east, north)
#     3. distance: spherical haversine() against the WGS84 ellipsoid distance (Vincenty)
#   We keep, for each d, the WORST of the 8 bearings.
import json
import math
import warnings

import numpy as np

from geo_lab import EARTH_RADIUS_M, M_PER_DEG, bearing, enu_to_geodetic, flat_en, haversine, radii
from geodesic_ref import vincenty

HOME = (35.8277, 10.6388)                         # Sousse (medina), NAVERA's test area
ROME = (41.8902, 12.4922)                         # Rome, the Colosseum
DISTANCES = [float(d) for d in np.round(np.logspace(1, math.log10(300_000), 41), 1)]
BEARINGS = range(0, 360, 45)

for name, fn in (("radii", radii), ("enu_to_geodetic", lambda: enu_to_geodetic(0.0, 0.0, 0.0, *HOME, 0.0)),
                 ("flat_en", lambda: flat_en(*HOME, *HOME)), ("haversine", lambda: haversine(*HOME, *HOME))):
    if (fn(0.0) if name == "radii" else fn()) is None:
        raise SystemExit(f"{name}() still returns None: finish its TODO in geo_lab.py first")

m0, n0 = radii(HOME[0])
flat_navera, flat_wgs84, hav_rel = [], [], []
for d in DISTANCES:
    worst_nav = worst_wgs = worst_hav = 0.0
    for b in BEARINGS:
        e, n = d * math.sin(math.radians(b)), d * math.cos(math.radians(b))
        lat, lon, _h = enu_to_geodetic(e, n, 0.0, HOME[0], HOME[1], 0.0)
        e1, n1 = flat_en(lat, lon, *HOME)
        e2 = math.radians(lon - HOME[1]) * n0 * math.cos(math.radians(HOME[0]))
        n2 = math.radians(lat - HOME[0]) * m0
        worst_nav = max(worst_nav, math.hypot(e1 - e, n1 - n))
        worst_wgs = max(worst_wgs, math.hypot(e2 - e, n2 - n))
        s_ell = vincenty(HOME[0], HOME[1], lat, lon)[0]
        worst_hav = max(worst_hav, abs(haversine(HOME[0], HOME[1], lat, lon) - s_ell) / s_ell * 100.0)
    flat_navera.append(worst_nav)
    flat_wgs84.append(worst_wgs)
    hav_rel.append(worst_hav)


def first_above(errors, limit):
    """The smallest distance of the grid where the error reaches `limit` meters (None if never)."""
    for d, err in zip(DISTANCES, errors):
        if err >= limit:
            return d
    return None


def at(errors, d):
    return errors[DISTANCES.index(d)] if d in DISTANCES else float(np.interp(math.log(d), np.log(DISTANCES), errors))


s_ell, az1, _ = vincenty(*HOME, *ROME)
s_hav = haversine(*HOME, *ROME)
results = {
    "home": "Sousse (medina)",
    "home_latlon": list(HOME),
    "constants": {"EARTH_RADIUS_M": EARTH_RADIUS_M, "M_PER_DEG": M_PER_DEG,
                  "M_home_m": round(m0, 1), "N_home_m": round(n0, 1)},
    "distances_m": DISTANCES,
    "flat_navera_max_error_m": [round(v, 4) for v in flat_navera],
    "flat_wgs84_max_error_m": [round(v, 6) for v in flat_wgs84],
    "haversine_max_error_percent": [round(v, 5) for v in hav_rel],
    "navera_flat_d_1m_m": first_above(flat_navera, 1.0),
    "navera_flat_d_10m_m": first_above(flat_navera, 10.0),
    "wgs84_flat_d_1m_m": first_above(flat_wgs84, 1.0),
    "navera_flat_error_at_1km_m": round(at(flat_navera, 1000.0), 3),
    "navera_flat_error_at_10km_m": round(at(flat_navera, 10000.0), 3),
    "wgs84_flat_error_at_10km_m": round(at(flat_wgs84, 10000.0), 4),
    "sousse_rome": {"haversine_km": round(s_hav / 1000.0, 3), "ellipsoid_km": round(s_ell / 1000.0, 3),
                    "difference_m": round(s_hav - s_ell, 1),
                    "difference_percent": round((s_hav - s_ell) / s_ell * 100.0, 3),
                    "bearing_sphere_deg": round(bearing(*HOME, *ROME), 2),
                    "bearing_ellipsoid_deg": round(az1, 2)},
}
with open("results.json", "w") as f:
    json.dump(results, f, indent=1)

print(f"home: {results['home']} {HOME}   M = {m0:.1f} m, N = {n0:.1f} m")
print(f"\n{'distance':>11}  {'NAVERA flat':>12}  {'WGS84 flat':>12}  {'haversine':>10}")
print(f"{'(m)':>11}  {'error (m)':>12}  {'error (m)':>12}  {'error (%)':>10}")
for i in range(0, len(DISTANCES), 4):
    print(f"{DISTANCES[i]:11.1f}  {flat_navera[i]:12.3f}  {flat_wgs84[i]:12.4f}  {hav_rel[i]:10.3f}")
print("\nNAVERA flat error reaches 1 m at", results["navera_flat_d_1m_m"], "m and 10 m at",
      results["navera_flat_d_10m_m"], "m")
print("WGS84-radii flat error reaches 1 m at", results["wgs84_flat_d_1m_m"], "m")
ms = results["sousse_rome"]
print(f"Sousse -> Rome: haversine {ms['haversine_km']} km, ellipsoid {ms['ellipsoid_km']} km, "
      f"difference {ms['difference_m']} m ({ms['difference_percent']} %)")

import matplotlib                                   # noqa: E402  (plotting comes last)
matplotlib.use("Agg")
warnings.filterwarnings("ignore", message="Unable to import Axes3D")
import matplotlib.pyplot as plt                     # noqa: E402

fig, ax = plt.subplots(figsize=(7.5, 5))
ax.loglog(DISTANCES, flat_navera, "o-", ms=3, label="NAVERA flat (M_PER_DEG = 111 320)")
ax.loglog(DISTANCES, np.maximum(flat_wgs84, 1e-6), "s-", ms=3, label="flat with WGS84 radii M, N")
ax.loglog(DISTANCES, np.array(hav_rel) / 100.0 * np.array(DISTANCES), "^-", ms=3,
          label="haversine vs ellipsoid distance")
for y in (1.0, 10.0):
    ax.axhline(y, color="grey", lw=0.8, ls="--")
ax.set_xlabel("distance from home (m)")
ax.set_ylabel("worst horizontal error over 8 bearings (m)")
ax.set_title("Sousse: error of the shortcuts against exact WGS84 geometry")
ax.grid(True, which="both", alpha=0.25)
ax.legend(fontsize=8)
fig.savefig("error_study.png", dpi=90, bbox_inches="tight")
print("\nSaved results.json and error_study.png — click the picture in the file list.")
