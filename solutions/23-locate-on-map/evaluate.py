# Lesson 23 — locate every photo with YOUR pipeline and with NAVERA's LocalMatcher, and measure both.
# Run:  python3 evaluate.py      → a table, results.csv, results.json and errors.png
import csv
import json
import math
import os
import sys
import time

import cv2

import navmap
from locate import DATA, locate, read_truth

WRONG_M = 50.0         # an accepted fix further than this from the truth is WRONG (as in VALIDATION_STATUS.md)


def error_m(res, lat_key, lon_key, row):
    """Distance in metres between the answer and the truth, or None when the photo was refused."""
    # TODO 9: None when res["accepted"] is not True; else navmap.haversine_m between
    #         (res[lat_key], res[lon_key]) and (row["true_lat"], row["true_lon"]) (text: float()).
    if not res.get("accepted"):
        return None
    return navmap.haversine_m(res[lat_key], res[lon_key], float(row["true_lat"]), float(row["true_lon"]))


def percentile(values, q):
    """The q-th percentile (0-100) of a list of numbers, with linear interpolation between the
    two closest ranks (numpy's default). None for an empty list."""
    # TODO 10: sort; position = (n - 1) * q / 100; interpolate between floor and ceil of it
    v = sorted(values)
    if not v:
        return None
    pos = (len(v) - 1) * q / 100.0
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def summarise(errors, wrong_m=WRONG_M):
    """errors: one entry per photo, the error in metres or None (refused).
    Returns a dict: n, accepted, availability (accepted / n), median_m, p90_m, worst_m (None when
    nothing was accepted) and wrong_accepted (accepted with an error > wrong_m)."""
    # TODO 11
    acc = [e for e in errors if e is not None]
    return dict(n=len(errors), accepted=len(acc), availability=len(acc) / len(errors) if errors else 0.0,
                median_m=percentile(acc, 50), p90_m=percentile(acc, 90), worst_m=max(acc) if acc else None,
                wrong_accepted=sum(1 for e in acc if e > wrong_m))


# ---- you don't need to change anything below this line ----
def navera_matcher():
    """NAVERA's own day-vision matcher, from your copy ~/navera (CPU: no GPU needed)."""
    sys.path.insert(0, os.path.expanduser("~/navera/day_pkg"))        # works even without ROS sourced
    from day_pkg.local_matcher import LocalMatcher
    return LocalMatcher(f"{DATA}/images", zoom=17, device="cpu"), LocalMatcher.frame_m_per_px


def run():
    try:
        nav, nav_mpp = navera_matcher()
    except Exception as e:  # noqa: BLE001 — still evaluate the student's pipeline
        print(f"(NAVERA's LocalMatcher could not be loaded: {e})")
        nav = None
    rows_out, mine, theirs = [], [], []
    print(f"{'photo':13s} {'source':7s} | {'YOUR PIPELINE':^33s} | {'NAVERA LocalMatcher':^27s}")
    for row in read_truth():
        photo = cv2.imread(f"{DATA}/{row['file']}")
        prior = (float(row["prior_lat"]), float(row["prior_lon"]))
        t0 = time.time()
        res = locate(photo, prior[0], prior[1], float(row["altitude_m"]), float(row["hfov_deg"]),
                     float(row["search_m"]))
        ms = (time.time() - t0) * 1000
        err = error_m(res, "lat", "lon", row)
        nerr, nres, nms = None, {}, None
        if nav is not None:
            t0 = time.time()
            nres = nav.locate(photo, prior, float(row["search_m"]),
                              nav_mpp(photo.shape[1], float(row["altitude_m"]), float(row["hfov_deg"])))
            nms = (time.time() - t0) * 1000
            nerr = error_m(nres, "predicted_lat", "predicted_lon", row)
        mine.append(err)
        theirs.append(nerr)
        name = row["file"].split("/")[-1][:-4]
        rows_out.append(dict(photo=name, source=row["source"], accepted=bool(res.get("accepted")),
                             inliers=res.get("inliers", 0), scale=res.get("scale"),
                             error_m=None if err is None else round(err, 2), time_ms=round(ms),
                             reason=res.get("reason", ""),
                             navera_accepted=bool(nres.get("accepted")), navera_inliers=nres.get("inliers", 0),
                             navera_error_m=None if nerr is None else round(nerr, 2),
                             navera_time_ms=None if nms is None else round(nms),
                             navera_reason=nres.get("reason", "") or nres.get("error", "")))
        r = rows_out[-1]
        e1 = "  no fix " if err is None else f"{err:6.1f} m "
        e2 = "  no fix " if nerr is None else f"{nerr:6.1f} m "
        print(f"{name:13s} {r['source']:7s} | {e1} {r['inliers']:4d} inl {ms:6.0f} ms | "
              f"{e2} {r['navera_inliers']:4d} inl {nms or 0:6.0f} ms")
    s1 = summarise(mine)
    s2 = summarise(theirs) if nav is not None else None
    for who, s in (("your pipeline", s1), ("NAVERA LocalMatcher", s2)):
        if s:
            f = (lambda x: "-" if x is None else f"{x:.2f} m")
            print(f"\n{who:20s}: accepted {s['accepted']}/{s['n']} ({s['availability']:.0%}), median "
                  f"{f(s['median_m'])}, p90 {f(s['p90_m'])}, worst {f(s['worst_m'])}, "
                  f"wrong accepted {s['wrong_accepted']}")
    with open("results.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0]))
        w.writeheader()
        w.writerows(rows_out)
    with open("results.json", "w") as fh:
        json.dump(dict(student=s1, navera=s2, per_photo=rows_out), fh, indent=1)
    plot(rows_out)
    print("\nwritten: results.csv, results.json and errors.png")


def plot(rows):
    import warnings
    warnings.filterwarnings("ignore", message="Unable to import Axes3D")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 4))
    x = list(range(len(rows)))
    for dx, key, col, lab in ((-0.2, "error_m", "#0b6e8a", "your pipeline"),
                              (0.2, "navera_error_m", "#f2a33a", "NAVERA LocalMatcher")):
        ax.bar([i + dx for i in x], [r[key] if r[key] is not None else 0 for r in rows], 0.4, color=col, label=lab)
        for i, r in enumerate(rows):
            if r[key] is None:
                ax.text(i + dx, 0.02, "no fix", ha="center", va="bottom", rotation=90, fontsize=8, color="#d64545")
    ax.set_xticks(x)
    ax.set_xticklabels([r["photo"] for r in rows], rotation=45, ha="right")
    ax.set_ylabel("error (m)")
    ax.set_title("Error per photo (p01-p08 cut from the map, p09-p11 older imagery, p12 sea, p13 lost)")
    ax.legend()
    fig.tight_layout()
    fig.savefig("errors.png", dpi=90)


if __name__ == "__main__":
    try:
        run()
    except NotImplementedError as e:
        print(f"Not written yet: {e} — fill in that TODO (in locate.py or evaluate.py) and run again.")
