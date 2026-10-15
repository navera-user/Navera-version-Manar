#!/usr/bin/env python3
"""Teacher only — writes courses/32-measuring/hidden/cases.json: the check's unseen inputs and the course
reference's answers (solutions/_navera_lite stats.py, solutions/32-measuring/baseline.py), plus the expected
numbers of the lab's flights and bag. check.py never runs the reference. Run from the academy root with ROS 2
sourced, after make_dataset.py:

    source /opt/ros/humble/setup.bash && python3 solutions/32-measuring/make_hidden.py
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite import stats as S                      # noqa: E402
from navera_lite.geo import offset                      # noqa: E402
from navera_lite.tools import evaluate_bag as EB        # noqa: E402
import baseline as BL                                   # noqa: E402

DATA = os.path.join(ACADEMY, "datasets", "32-measuring")
OUT = os.path.join(ACADEMY, "courses", "32-measuring", "hidden", "cases.json")
NAN = None                                              # JSON null = an empty cell


def table(d):
    """A JSON-friendly dict of columns → the DataFrame the check builds (null → NaN)."""
    return pd.DataFrame({k: [np.nan if v is None else v for v in col] for k, col in d.items()})


def r(x, k=6):
    return None if x is None else round(float(x), k)


def main():
    rng = np.random.default_rng(3299)
    cases = {}

    # TODO 1 — errors far north (cos(lat) matters), NaN rows of three kinds
    lat0, lon0 = 64.1466, -21.9426                     # Reykjavik
    rows = {"lat": [], "lon": [], "truth_lat": [], "truth_lon": []}
    for i, (de, dn, kind) in enumerate([(0, 0, ""), (40, 0, ""), (0, -25, ""), (0, 0, "nolat"), (-300, 120, ""),
                                        (5, 5, "nolon"), (12, -7, ""), (0, 0, "notruth"), (1500, 0, "")]):
        tl, tn = offset(lat0, lon0, 30.0 * i, 0.0)
        el, en = offset(tl, tn, de, dn)
        rows["truth_lat"].append(None if kind == "notruth" else round(tl, 7))
        rows["truth_lon"].append(round(tn, 7))
        rows["lat"].append(None if kind == "nolat" else round(el, 7))
        rows["lon"].append(None if kind == "nolon" else round(en, 7))
    cases["errors"] = {"table": rows, "want": [r(x, 4) for x in S.errors_m(table(rows))]}

    # TODO 2 — percentiles of unseen samples
    samples = [[42.5], [9.0, 3.0], [5, 1, 9, 3, 7, 2, 8, 4, 6, 11, 10], [2.0, 2.0, 2.0, 50.0],
               [round(float(x), 3) for x in rng.gamma(2.0, 7.0, 23)]]
    qs = [0, 10, 25, 50, 73, 90, 95, 100]
    cases["percentile"] = [{"v": v, "q": q, "want": r(S.percentile(v, q))} for v in samples for q in qs]

    # TODO 3 — summaries
    sm = [[3.5, 1.2, 4.8, 2.2, 77.0, 3.1, 2.9], [6.0]]
    cases["summary"] = [{"v": v, "want": {k: (r(x) if k != "n" else x) for k, x in S.summary(v).items()}} for v in sm]

    # TODO 4–5 — availability and gaps, 0.5 s rows, a gap at the start and one at the end
    st = ["STARTING", "FIX", "FIX", "DEGRADED", "NO_FIX", "NO_FIX", "DEGRADED", "FIX", "DEGRADED", "NO_FIX",
          "NO_FIX", "NO_FIX", "NO_FIX"]
    lat = [None, 35.8, 35.8, None, None, None, 35.8, 35.8, 35.8, None, None, None, None]
    av = {"t_s": [0.5 * i for i in range(len(st))], "state": st, "lat": lat,
          "lon": [None if x is None else 10.6 for x in lat]}
    d = table(av)
    cases["avail"] = {"table": av, "dt_s": 0.5, "availability": r(S.availability(d)),
                      "availability_fix_only": r(S.availability(d, ok=("FIX",))),
                      "gap": r(S.longest_gap_s(d, dt_s=0.5)), "gap_first5": r(S.longest_gap_s(d.iloc[:6], dt_s=0.5))}

    # TODO A — baseline: GPS output 30 m off the truth; a day row just before the jam; GPS after the jam
    la, lo = 51.5007, -0.1246                          # London
    bl = {k: [] for k in ("t_s", "gps", "state", "source", "lat", "lon", "truth_lat", "truth_lon")}
    plan = [("ok", "gps"), ("ok", "gps"), ("ok", "gps"), ("ok", "day"), ("jammed", "day"), ("jammed", ""),
            ("jammed", "day"), ("jammed", "day"), ("ok", "day"), ("ok", "gps")]
    for i, (g, src) in enumerate(plan):
        tl, tn = offset(la, lo, 0.0, 20.0 * i)
        if src == "gps":
            el, en = offset(tl, tn, 30.0, 0.0)
        elif src == "day":
            el, en = offset(tl, tn, -80.0, 15.0)
        else:
            el = en = None
        bl["t_s"].append(float(i))
        bl["gps"].append(g)
        bl["state"].append({"gps": "FIX", "day": "DEGRADED", "": "NO_FIX"}[src])
        bl["source"].append(src)
        bl["lat"].append(None if el is None else round(el, 7))
        bl["lon"].append(None if en is None else round(en, 7))
        bl["truth_lat"].append(round(tl, 7))
        bl["truth_lon"].append(round(tn, 7))
    cases["baseline"] = {"table": bl, "want": [r(x, 4) for x in BL.last_fix_baseline(table(bl))]}

    # TODO 8 — Wilson
    cases["wilson"] = [{"k": k, "n": n, "want": [r(x) for x in S.wilson(k, n)]}
                       for k, n in ((45, 50), (0, 12), (7, 7), (1, 3), (130, 400))]
    cases["wilson_z"] = {"k": 18, "n": 20, "z": 2.576, "want": [r(x) for x in S.wilson(18, 20, z=2.576)]}

    # TODO 9 — coverage with the check's own callables (same generator for both)
    cov = {}
    cov["minmax"] = S.coverage_experiment(lambda g: g.normal(0.0, 1.0, 3), lambda s, g: (s.min(), s.max()),
                                          0.0, trials=60, seed=7)
    cov["shared"] = S.coverage_experiment(lambda g: g.normal(0.0, 1.0, 4),
                                          lambda s, g: (s.mean() - g.uniform(0, 1), s.mean() + g.uniform(0, 1)),
                                          0.0, trials=50, seed=11)
    cases["coverage"] = cov

    # the lab's flights (measure_lab.py flights / ci, B 2000, seed 32, blocks of 10 s)
    fl, ci = {}, {}
    for name in ("target", "retrieval", "selective"):
        df = pd.read_csv(os.path.join(DATA, f"flight_{name}.csv"))
        jam = df[df["gps"] == "jammed"]
        base = BL.last_fix_baseline(df)
        e = S.errors_m(jam)
        fl[name] = {"all": S.summary(S.errors_m(df)), "jam": S.summary(e), "baseline": S.summary(base),
                    "availability": S.availability(df), "availability_jam": S.availability(jam),
                    "longest_gap_s": S.longest_gap_s(df), "longest_gap_jam_s": S.longest_gap_s(jam)}
        has = jam["lat"].notna().to_numpy()
        bm = base[has]
        c = {"jam_median_iid": S.bootstrap_ci(e, np.median, B=2000, seed=32),
             "diff_median_iid": S.paired_diff_ci(e, bm, np.median, B=2000, seed=32)}
        if name != "selective":
            c["jam_median_block10"] = S.bootstrap_ci(e, np.median, B=2000, seed=32, block=10)
            c["diff_median_block10"] = S.paired_diff_ci(e, bm, np.median, B=2000, seed=32, block=10)
        ci[name] = {k: [r(x, 2) for x in v] for k, v in c.items()}
    cases["flights"] = json.loads(json.dumps(fl, default=float))
    cases["ci"] = ci

    # the bag (evaluate_bag, linear rule)
    fixes = EB.read_bag(os.path.join(DATA, "shadow_bag"))
    gtruth = sorted((e.stamp_s, e.lat, e.lon) for s, e in fixes if s == "gps" and e.valid)
    a = EB.score(fixes, gtruth, S.percentile, 1.5, ("gps",))
    b = EB.score(fixes, EB.truth_from_csv(os.path.join(DATA, "shadow_truth.csv")), S.percentile, 1.5)
    cases["bag"] = {"day_honest_gps_truth": r(a["day"]["honest_sigma_m"], 2),
                    "day_honest_true": r(b["day"]["honest_sigma_m"], 2),
                    "day_within2_pct": r(b["day"]["within_2sigma_pct"], 2),
                    "gps_honest_true": r(b["gps"]["honest_sigma_m"], 2),
                    "day_no_position": a["day"]["no_position"]}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(cases, f, indent=1, default=float)
    print("written", OUT)
    print(json.dumps({k: cases[k] for k in ("coverage", "bag", "ci")}, indent=1))


if __name__ == "__main__":
    main()
