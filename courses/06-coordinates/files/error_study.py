"""error_study.py — how wrong is the flat shortcut, as a function of distance? (Step 9)

    python3 error_study.py          writes results.json and out/error_study.png

The question: your enu_flat() (session 1) turns (lat, lon) into metres on a sphere with one cos(latitude).
Your geodetic_to_enu() / enu_to_geodetic() (session 2) are exact on the WGS84 ellipsoid. Around a home
point, for distances from 10 m to 300 km, how far apart are the two answers?

YOUR PART: TODO A, the function worst_flat_error_m() below (write it after your PREDICT_STUDY).
The rest of the file (the loop over distances and homes, the picture, results.json) is given.
"""
import json
import math
import os
import sys

import numpy as np

import runner_kit as rk

g = rk.load_student("navera_lite.geo")


# TODO A ---------------------------------------------------------------------------------------
def worst_flat_error_m(lat0, lon0, d_m):
    """The flat shortcut's worst horizontal error, in metres, at distance d_m from home (lat0, lon0).

    Definition (use exactly this, so that everyone gets the same numbers), for each of the 8 bearings
    0°, 45°, 90°, … 315°:
      - the TRUE point is d_m metres from home on that bearing in home's exact ENU frame
        (session 2; up = 0, home at height 0);
      - the FLAT answer is what g.enu_flat says about that point's (lat, lon), seen from home;
      - the error is the horizontal distance (m) between the flat (east, north) and the true one.
    Return the LARGEST of the 8 errors, in metres.

    Example: worst_flat_error_m(0.0, 0.0, 1000.0) → about 5.613
             worst_flat_error_m(-41.2865, 174.7762, 20000.0) → about 58.957   (Wellington, 20 km)
    """
    return None   # TODO: replace this line with your code


# ---- you don't need to change anything below this line (but you can read it!) ----

HOMES = {"Quito (equator)": (-0.1807, -78.4678), "Sousse (NAVERA's test area)": (35.8277, 10.6388),
         "Reykjavik": (64.1466, -21.9426)}
DISTANCES = [float(d) for d in np.round(np.logspace(1, math.log10(300_000), 41), 1)]


def first_above(errors, limit):
    """The smallest distance of the grid where the error reaches `limit` metres (None if never)."""
    for d, err in zip(DISTANCES, errors):
        if err >= limit:
            return d
    return None


def slope(ds, errs):
    """The slope of log(error) against log(distance): 1 means error ∝ d, 2 means error ∝ d²."""
    return round(float(np.polyfit(np.log10(ds), np.log10(errs), 1)[0]), 2)


def main():
    v, err = rk.call(sys.modules[__name__], "worst_flat_error_m", 0.0, 0.0, 1000.0)
    if err:
        raise SystemExit(err)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise SystemExit(f"worst_flat_error_m() must return one number (metres), but it returned {v!r}")
    w, err = rk.call(sys.modules[__name__], "worst_flat_error_m", -41.2865, 174.7762, 20000.0)
    if err:
        raise SystemExit(err)
    print(f"self-test: worst_flat_error_m(0, 0, 1 km) = {v:.3f} m (docstring: about 5.613), "
          f"Wellington 20 km = {w:.3f} m (docstring: about 58.957)")
    if abs(w - 24.645) < 0.01:
        raise SystemExit("✘ Wellington gives 24.645: only the first bearing counts — is your `return` inside the loop?")
    if abs(w - 66.005) < 0.01:
        raise SystemExit("✘ Wellington gives 66.005: math.sin/math.cos got the bearing in DEGREES — use math.radians")
    if abs(v - 2005.613) < 0.01:
        raise SystemExit("✘ 2005.613 at (0, 0, 1 km): enu_flat sees home from the point — call "
                         "g.enu_flat(lat0, lon0, lat, lon), home first")
    if v > 1e6 or w > 1e6:
        raise SystemExit("✘ errors of thousands of km: for points WEST of home your enu_flat gives tens of thousands "
                         "of km EAST — check its Δλ wrap, (Δλ + 180) % 360 − 180 (lesson §1), even if run_geo.py test "
                         "looked green")
    if abs(v - 5.613) > 0.01 or abs(w - 58.957) > 0.01:
        raise SystemExit("✘ not the docstring's values: check TODO A against its definition (and your geo.py TODOs 1, 12)")
    results = {"distances_m": DISTANCES, "homes": {}}
    curves = {}
    for name, (lat0, lon0) in HOMES.items():
        errs = []
        for d in DISTANCES:
            e = worst_flat_error_m(lat0, lon0, d)
            errs.append(float(e))
        curves[name] = errs
        near = [i for i, d in enumerate(DISTANCES) if d <= 1000.0]
        far = [i for i, d in enumerate(DISTANCES) if d >= 100_000.0]
        results["homes"][name] = {
            "latlon": [lat0, lon0],
            "max_error_m": [round(x, 4) for x in errs],
            "d_1m_m": first_above(errs, 1.0),
            "d_10m_m": first_above(errs, 10.0),
            "error_at_1km_m": round(float(np.interp(3.0, np.log10(DISTANCES), errs)), 3),
            "error_at_100km_m": round(float(np.interp(5.0, np.log10(DISTANCES), errs)), 1),
            "slope_below_1km": slope([DISTANCES[i] for i in near], [errs[i] for i in near]),
            "slope_above_100km": slope([DISTANCES[i] for i in far], [errs[i] for i in far]),
        }
        r = results["homes"][name]
        print(f"{name:30s} error reaches 1 m at {r['d_1m_m']} m, 10 m at {r['d_10m_m']} m;"
              f" slope {r['slope_below_1km']} below 1 km, {r['slope_above_100km']} above 100 km")
    with open("results.json", "w") as f:
        json.dump(results, f, indent=1)
    print("\nresults.json written")
    plt = rk.plt_or_none()
    if plt is None:
        return
    os.makedirs("out", exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 5))
    for (name, errs), colour in zip(curves.items(), ("#0b6e8a", "#d17a00", "#7a3fb0")):
        ax.loglog(DISTANCES, errs, "-o", ms=3, color=colour, label=name)
    ax.loglog(DISTANCES, [d / 1000 for d in DISTANCES], ":", color="grey", label="slope 1 (1 m per km)")
    ax.loglog(DISTANCES, [d * d / 1e7 for d in DISTANCES], "--", color="grey", label="slope 2")
    ax.axhline(1.0, color="k", lw=0.6)
    ax.set_xlabel("distance from home (m)")
    ax.set_ylabel("worst error of enu_flat (m)")
    ax.set_title("Flat shortcut against the exact ENU frame (WGS84)")
    ax.grid(alpha=.3, which="both")
    ax.legend(fontsize=8)
    fig.savefig("out/error_study.png", dpi=90, bbox_inches="tight")
    plt.close(fig)
    rk.saved("out/error_study.png")


if __name__ == "__main__":
    main()
