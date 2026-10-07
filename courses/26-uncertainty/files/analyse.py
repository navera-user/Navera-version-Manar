#!/usr/bin/env python3
"""analyse.py — error statistics, error circles and a weighted average on real-looking fixes.

    python3 analyse.py          # prints the numbers, writes error_circles.png and results.json

The data (/data/academy/26-uncertainty/, SIMULATED): a receiver standing still on a known point,
measured 300 times by a GPS (gps_fixes.csv) and by a vision source (vision_fixes.csv), and two
independent sources A and B side by side (two_sources.csv).
"""
import csv
import json
import math
import os
import warnings

warnings.filterwarnings("ignore", message="Unable to import Axes3D")   # harmless on this Jetson
import matplotlib                          # noqa: E402
matplotlib.use("Agg")                      # no window: we save a PNG
import matplotlib.pyplot as plt            # noqa: E402

from uncertainty import fuse, mean, median, share_within, std, to_local_m   # noqa: E402

DATA = "/data/academy/26-uncertainty"
SIGMA_A, SIGMA_B = 6.0, 9.0                # what sources A and B STATE (per axis, metres)


def load(name):
    with open(os.path.join(DATA, name)) as f:
        return list(csv.DictReader(f))


def errors_of(rows, truth, lat="lat", lon="lon"):
    """east, north offsets (m) and distances (m) of each fix from the truth."""
    east, north = [], []
    for r in rows:
        e, n = to_local_m(float(r[lat]), float(r[lon]), truth["lat"], truth["lon"])
        east.append(e)
        north.append(n)
    dist = [math.hypot(e, n) for e, n in zip(east, north)]
    return east, north, dist


def ready():
    """True once TODO 1 to 5 of uncertainty.py give numbers."""
    try:
        return all(isinstance(v, (int, float)) for v in (mean([1, 2]), median([1, 2]), std([1, 2]),
                                                          share_within([1, 2], 1.5), fuse(1, 1, 2, 1)[0]))
    except Exception:
        return False


def main():
    if not ready():
        print("uncertainty.py is not finished: complete TODO 1 to 5 first (python3 uncertainty.py to try them).")
        return
    with open(os.path.join(DATA, "truth.json")) as f:
        truth = json.load(f)
    res = {}

    # ---- 1. GPS: how far from the truth, and how spread out?
    east, north, dist = errors_of(load("gps_fixes.csv"), truth)
    s_e, s_n = std(east), std(north)
    sigma = math.sqrt((s_e ** 2 + s_n ** 2) / 2.0)          # one sigma per axis, averaged
    res["gps"] = dict(n=len(dist), mean_m=mean(dist), median_m=median(dist), max_m=max(dist),
                      sigma_east_m=s_e, sigma_north_m=s_n, sigma_m=sigma)
    # TODO 7: the share of GPS fixes inside the 1-, 2- and 3-sigma circles (0.0 .. 1.0)
    res["gps"]["within_1s"] = None
    res["gps"]["within_2s"] = None
    res["gps"]["within_3s"] = None

    # ---- 2. Vision: three wrong matches among 300 — look at mean vs median
    ve, vn, vdist = errors_of(load("vision_fixes.csv"), truth)
    res["vision"] = dict(n=len(vdist), mean_m=mean(vdist), median_m=median(vdist), max_m=max(vdist),
                         sigma_east_m=std(ve), sigma_north_m=std(vn))

    # ---- 3. Two sources, one better answer: the weighted average
    rows = load("two_sources.csv")
    ae, an, ad = errors_of(rows, truth, "a_lat", "a_lon")
    be, bn, bd = errors_of(rows, truth, "b_lat", "b_lon")
    fused = []
    # TODO 8: for each row, fuse A and B on the east axis, then on the north axis
    #         (fuse(a, SIGMA_A, b, SIGMA_B) gives (value, sigma)), and append the distance
    #         math.hypot(fused_east, fused_north) to the list `fused`.
    for e1, n1, e2, n2 in zip(ae, an, be, bn):
        pass                                   # <- replace this line
    res["fusion"] = dict(median_a_m=median(ad), median_b_m=median(bd),
                         median_fused_m=median(fused) if fused else None,
                         stated_fused_sigma_m=fuse(0.0, SIGMA_A, 0.0, SIGMA_B)[1])

    # ---- 4. The picture: the fixes and the 1-, 2-, 3-sigma circles
    fig, ax = plt.subplots(figsize=(6.5, 6.5))
    ax.scatter(east, north, s=8, color="#2563eb", alpha=0.6, label="GPS fixes (300)")
    ax.plot(0, 0, "r+", markersize=16, mew=2, label="truth")
    # TODO 9: draw the three circles, radius k * sigma for k = 1, 2, 3, centred on the truth.
    #         plt.Circle((0, 0), radius, fill=False, ...) then ax.add_patch(circle)
    for k, color in ((1, "#16a34a"), (2, "#d97706"), (3, "#dc2626")):
        share = res["gps"][f"within_{k}s"]
        label = f"{k} sigma = {k * sigma:.1f} m" + (f": {100 * share:.0f} % inside" if share is not None else "")
        pass                                   # <- replace this line (use color=color, label=label)
    lim = 3.4 * sigma
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_aspect("equal")
    ax.grid(alpha=0.3)
    ax.set_xlabel("east error (m)")
    ax.set_ylabel("north error (m)")
    ax.set_title("GPS standing still: where do the fixes fall? (simulated)")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig("error_circles.png", dpi=100)

    with open("results.json", "w") as f:
        json.dump(res, f, indent=1)
    g, v, fu = res["gps"], res["vision"], res["fusion"]
    print(f"GPS    : median {g['median_m']:.2f} m, mean {g['mean_m']:.2f} m, max {g['max_m']:.2f} m, "
          f"sigma east {g['sigma_east_m']:.2f} / north {g['sigma_north_m']:.2f} m")
    if g["within_1s"] is not None:
        print(f"         inside 1/2/3 sigma: {100 * g['within_1s']:.0f} % / {100 * g['within_2s']:.0f} % / "
              f"{100 * g['within_3s']:.0f} %   (a perfect 2-D Gaussian: 39 / 86 / 99 %)")
    print(f"vision : median {v['median_m']:.1f} m, mean {v['mean_m']:.1f} m, max {v['max_m']:.0f} m")
    if fu["median_fused_m"] is not None:
        print(f"fusion : A {fu['median_a_m']:.2f} m, B {fu['median_b_m']:.2f} m -> fused {fu['median_fused_m']:.2f} m "
              f"(stated sigma {fu['stated_fused_sigma_m']:.2f} m)")
    print("saved error_circles.png and results.json")


if __name__ == "__main__":
    main()
