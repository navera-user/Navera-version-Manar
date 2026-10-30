"""navera_lite/tools/evaluate_bag.py — score the position sources recorded in a ROS 2 bag against a truth, and
test whether the accuracy each source STATES is honest. Part of NAVERA Lite, the course's teaching stack
(mission 32). Written for the course; it is not NAVERA code. It uses YOUR percentile() (navera_lite/stats.py).

    python3 -m navera_lite.tools.evaluate_bag BAG                         # truth = the GPS fixes in the bag
    python3 -m navera_lite.tools.evaluate_bag BAG --truth truth.csv       # truth = a better reference
    python3 -m navera_lite.tools.evaluate_bag BAG --rule nearest          # the nearest-sample percentile rule
    python3 -m navera_lite.tools.evaluate_bag BAG --json scores.json      # also save the tables

The bag holds sensor_msgs/NavSatFix messages on /navera_lite/fix/<source> (shadow mode: the vision sources
keep working while GPS is good, so they can be scored against it). For every fix that has a position, the
truth is taken AT THE FIX'S STAMP (the instant it was measured), interpolated in time between the two
truth samples around it — or the fix is skipped when no truth sample lies within --max-gap seconds on
each side. The truth is either the valid GPS fixes of the bag, or a CSV file with the columns
stamp_s, truth_lat, truth_lon (seconds on the same clock as the bag's stamps).

Two tables: (1) per source: n, fixes without a position, median, p90, max, and the share within 25 / 50 /
100 m; (2) per source that states a σ: the share of errors within 1, 2 and 3 × the stated σ (an honest
round 2-D Gaussian gives about 39 / 86 / 99 %) and the "honest σ": the σ that would make the statement
true, p86 of the errors / 2 (86 % of an honest 2-D error lies within 2 σ).
"""
import argparse
import bisect
import csv
import json
import math
import os
import sys

from navera_lite.estimate import stated_sigma
from navera_lite.logbook import haversine_m

# @part 32
FIX_PREFIX = "/navera_lite/fix/"
# @part 32
WITHIN_M = (25.0, 50.0, 100.0)
# @part 32
SIGMA_CFG = {"min_stated_sigma_m": 0.01}


# @part 32
def read_bag(path):
    """Every NavSatFix of the bag's /navera_lite/fix/* topics, in bag order, as (source, Estimate) pairs.

    Example: read_bag("/data/academy/32-measuring/shadow_bag")[0][0] → "gps"
    """
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import NavSatFix

    from navera_lite.ros.convert import from_navsatfix

    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=path, storage_id="sqlite3"),
                rosbag2_py.ConverterOptions("cdr", "cdr"))
    out = []
    while reader.has_next():
        topic, data, _ = reader.read_next()
        if topic.startswith(FIX_PREFIX):
            src = topic[len(FIX_PREFIX):]
            out.append((src, from_navsatfix(deserialize_message(data, NavSatFix), source=src)))
    return out


# @part 32
def truth_from_csv(path):
    """The truth samples of a CSV file (stamp_s, truth_lat, truth_lon) as a time-sorted list of (t, lat, lon).

    Example: truth_from_csv("/data/academy/32-measuring/shadow_truth.csv")[0] → (1791000000.0, 35.8256…, 10.6084…)
    """
    with open(path, newline="") as f:
        rows = [(float(r["stamp_s"]), float(r["truth_lat"]), float(r["truth_lon"])) for r in csv.DictReader(f)]
    return sorted(rows)


# @part 32
def truth_at(truth, t, max_gap_s):
    """The truth at instant t, interpolated linearly in time between the samples before and after it, or None
    when t is outside the samples or a neighbour is more than max_gap_s away. truth: sorted (t, lat, lon).

    Example: truth_at([(0.0, 35.0, 10.0), (1.0, 35.001, 10.0)], 0.5, 1.5) → (35.0005, 10.0)
    """
    times = [s[0] for s in truth]
    i = bisect.bisect_left(times, t)
    if i < len(truth) and truth[i][0] == t:
        return truth[i][1], truth[i][2]
    if i == 0 or i == len(truth):
        return None
    (t0, la0, lo0), (t1, la1, lo1) = truth[i - 1], truth[i]
    if t - t0 > max_gap_s or t1 - t > max_gap_s:
        return None
    w = (t - t0) / (t1 - t0)
    return la0 + w * (la1 - la0), lo0 + w * (lo1 - lo0)


# @part 32
def score(fixes, truth, pct, max_gap_s=1.5, skip=()):
    """The two tables (see the top of this file) as a dict source → numbers. pct(values, q) is the percentile
    rule to use (stats.percentile or stats.pct_nearest).

    Example: score(read_bag(bag), truth, stats.percentile)["day"]["median_m"] → a number of metres
    """
    per = {}
    for src, est in fixes:
        if src in skip:
            continue
        d = per.setdefault(src, {"n_fixes": 0, "no_position": 0, "no_truth": 0, "errs": [], "pairs": []})
        d["n_fixes"] += 1
        if not est.valid or not (math.isfinite(est.lat) and math.isfinite(est.lon)):
            d["no_position"] += 1
            continue
        tr = truth_at(truth, est.stamp_s, max_gap_s)
        if tr is None:
            d["no_truth"] += 1
            continue
        e = float(haversine_m(tr[0], tr[1], est.lat, est.lon))
        d["errs"].append(e)
        s = stated_sigma(est, SIGMA_CFG)
        if s is not None:
            d["pairs"].append((e, s))
    out = {}
    for src, d in sorted(per.items()):
        errs = d["errs"]
        r = {"n_fixes": d["n_fixes"], "no_position": d["no_position"], "no_truth": d["no_truth"], "n": len(errs)}
        if errs:
            r.update(median_m=_num(pct(errs, 50)), p90_m=_num(pct(errs, 90)), max_m=max(errs))
            for lim in WITHIN_M:
                r[f"within_{lim:g}m_pct"] = 100.0 * sum(e <= lim for e in errs) / len(errs)
        if d["pairs"]:
            es = d["pairs"]
            r["stated_sigma_m"] = _num(pct([s for _, s in es], 50))
            for k in (1, 2, 3):
                r[f"within_{k}sigma_pct"] = 100.0 * sum(e <= k * s for e, s in es) / len(es)
            r["honest_sigma_m"] = _num(pct([e for e, _ in es], 86)) / 2.0
        out[src] = r
    return out


# @part 32
def _num(v):
    """A percentile's result as a float, or a plain message when the student's function is not ready."""
    if v is None:
        sys.exit("navera_lite/stats.py: percentile() returned None — write TODO 2 first (python3 measure_lab.py test)")
    try:
        return float(v)
    except (TypeError, ValueError):
        sys.exit(f"navera_lite/stats.py: percentile() must return a number, it returned {v!r}")


# @part 32
def print_tables(res, truth_name, rule):
    """Print the two tables of score() for humans.

    Example: print_tables(score(...), "GPS fixes of the bag", "linear") → two small tables on the screen
    """
    print(f"truth: {truth_name}; percentile rule: {rule}\n")
    print(f"{'source':10s}{'fixes':>7s}{'no pos':>8s}{'scored':>8s}{'median':>9s}{'p90':>8s}{'max':>8s}"
          + "".join(f"{'≤' + format(m, 'g') + ' m':>8s}" for m in WITHIN_M))
    for src, r in res.items():
        if not r["n"]:
            print(f"{src:10s}{r['n_fixes']:7d}{r['no_position']:8d}{0:8d}   (no fix with a position and a truth)")
            continue
        print(f"{src:10s}{r['n_fixes']:7d}{r['no_position']:8d}{r['n']:8d}{r['median_m']:8.1f}m{r['p90_m']:7.1f}m"
              f"{r['max_m']:7.1f}m" + "".join(f"{r[f'within_{m:g}m_pct']:7.0f}%" for m in WITHIN_M))
    stated = {s: r for s, r in res.items() if "honest_sigma_m" in r}
    if stated:
        print("\nstated accuracy vs truth (an honest 2-D σ: about 39 / 86 / 99 % within 1 / 2 / 3 σ)")
        print(f"{'source':10s}{'stated σ':>10s}{'≤1σ':>7s}{'≤2σ':>7s}{'≤3σ':>7s}{'honest σ':>11s}")
        for src, r in stated.items():
            flag = "   <- stated σ too optimistic" if r["within_2sigma_pct"] < 80 else ""
            print(f"{src:10s}{r['stated_sigma_m']:9.1f}m{r['within_1sigma_pct']:6.0f}%{r['within_2sigma_pct']:6.0f}%"
                  f"{r['within_3sigma_pct']:6.0f}%{r['honest_sigma_m']:10.1f}m{flag}")


# @part 32
def main(argv=None):
    """The command line (see the top of this file).

    Example: main(["/data/academy/32-measuring/shadow_bag"]) → prints the two tables
    """
    ap = argparse.ArgumentParser(description="Score the /navera_lite/fix/* sources of a ROS 2 bag against a truth.")
    ap.add_argument("bag")
    ap.add_argument("--truth", help="CSV with stamp_s, truth_lat, truth_lon (default: the bag's valid GPS fixes)")
    ap.add_argument("--rule", choices=("linear", "nearest"), default="linear")
    ap.add_argument("--max-gap", type=float, default=1.5, help="largest time to a truth sample (s)")
    ap.add_argument("--json", help="also write the tables to this JSON file")
    a = ap.parse_args(argv)
    if not os.path.isdir(a.bag):
        sys.exit(f"{a.bag}: no such bag folder")
    from navera_lite import stats
    pct = stats.percentile if a.rule == "linear" else stats.pct_nearest
    fixes = read_bag(a.bag)
    print(f"bag {a.bag}: {len(fixes)} fixes on {len({s for s, _ in fixes})} source topics")
    if a.truth:
        truth, name, skip = truth_from_csv(a.truth), f"{a.truth} ({os.path.basename(a.truth)})", ()
    else:
        truth = sorted((e.stamp_s, e.lat, e.lon) for s, e in fixes
                       if s == "gps" and e.valid and math.isfinite(e.lat) and math.isfinite(e.lon))
        name, skip = f"the {len(truth)} valid GPS fixes of the bag", ("gps",)
    if len(truth) < 2:
        sys.exit("not enough truth samples to interpolate (need at least 2)")
    res = score(fixes, truth, pct, a.max_gap, skip)
    print_tables(res, name, a.rule)
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"truth": name, "rule": a.rule, "sources": res}, f, indent=1)
        print(f"\nsaved {a.json}")


if __name__ == "__main__":
    main()
