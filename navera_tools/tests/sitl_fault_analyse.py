#!/usr/bin/env python3
"""Error of what NAVERA forwarded vs the sigma it stated, for runs of sitl_fault_campaign.py.

    python3 navera_tools/tests/sitl_fault_analyse.py DIR S2_gps_cut_forward_degraded [--bucket 20]

Reads DIR/<name>.csv (truth, 1 Hz) and DIR/<S-id>_ros.jsonl (sitl_ros_logger.py: /navera/fix is
what vehicle_output decided to send; its stamp is the instant the position describes). For every
forwarded position (status FIX, i.e. sent as a position) after the first fault: error = distance to
the truth at that instant, sigma = the stated accuracy, ratio = error / sigma. Also the intervals
in which nothing was forwarded ("withdrawn") and the outcome from DIR/<name>_summary.json.
SIMULATED data only.
"""
import argparse
import bisect
import csv
import json
import math
import os
import statistics


def load(d, name):
    rows = list(csv.DictReader(open(os.path.join(d, name + ".csv"))))
    ev = [json.loads(line) for line in open(os.path.join(d, name.split("_")[0] + "_ros.jsonl"))]
    return rows, ev


def hav(la1, lo1, la2, lo2):
    return math.hypot((la1 - la2) * 111195.0, (lo1 - lo2) * 111195.0 * math.cos(math.radians(la2)))


def analyse(d, name, bucket=20.0):
    rows, ev = load(d, name)
    summary = json.load(open(os.path.join(d, name + "_summary.json")))
    t0 = float(rows[0]["wall"]) - float(rows[0]["t_s"])
    tw = [float(r["wall"]) for r in rows]
    tla = [float(r["truth_lat"]) for r in rows]
    tlo = [float(r["truth_lon"]) for r in rows]

    def truth(w):
        i = min(max(bisect.bisect_left(tw, w), 1), len(tw) - 1)
        f = (w - tw[i - 1]) / max(1e-6, tw[i] - tw[i - 1])
        f = min(max(f, 0.0), 1.0)
        return tla[i - 1] + f * (tla[i] - tla[i - 1]), tlo[i - 1] + f * (tlo[i] - tlo[i - 1])

    t_cut = summary["faults"][0][0]
    t_stop = float(rows[-1]["t_s"])                       # the driver restores the GPS when it stops
    samples, withdrawn = [], []
    last_pos_t, gap_start = None, None
    for e in ev:
        if e["t"] != "fix":
            continue
        t = e["wall"] - t0
        if t < t_cut or t > t_stop:
            continue
        if e["lat"] is not None and e["status"] == 0:                       # STATUS_FIX: sent as a position
            if gap_start is not None and t - gap_start > 2.0:
                withdrawn.append((round(gap_start, 1), round(t, 1)))
            gap_start = None
            la, lo = truth(e["stamp"] if e["stamp"] > 1e9 else e["wall"])
            err = hav(e["lat"], e["lon"], la, lo)
            sig = e["sigma"]
            samples.append((t, err, sig, err / sig if sig else None))
            last_pos_t = t
        elif gap_start is None:
            gap_start = last_pos_t if last_pos_t is not None else t
    if gap_start is not None:
        withdrawn.append((round(gap_start, 1), None))
    # the pipeline's own stated accuracy (/navera/position covariance), without the integrator's
    # declared floor (degraded_sigma_m): what the vision source claims about itself
    stated = []
    for e in ev:
        if e["t"] != "position" or e["src"] != 2 or not e["valid"] or e["lat"] is None or not e["sigma"]:
            continue
        t = e["wall"] - t0
        if t_cut <= t <= t_stop:
            la, lo = truth(e["stamp"] if e["stamp"] > 1e9 else e["wall"])
            stated.append((t, hav(e["lat"], e["lon"], la, lo), e["sigma"]))
    out = dict(name=name, n_forwarded=len(samples), withdrawn_intervals=withdrawn,
               first_fault_s=t_cut, end_reason=summary.get("end_reason"), final=summary.get("final"),
               mode_changes=summary.get("mode_changes"))
    sr = [e / sg for _, e, sg in stated]
    out["stated"] = dict(n=len(stated), max_err_over_sigma=round(max(sr), 2) if sr else None,
                         n_over_3=sum(1 for x in sr if x > 3.0), max_sigma=round(max((x[2] for x in stated), default=0), 1))
    r = [s[3] for s in samples if s[3] is not None]
    out["max_err_over_sigma"] = round(max(r), 2) if r else None
    out["n_err_over_3sigma"] = sum(1 for x in r if x > 3.0)
    out["max_err_m"] = round(max(s[1] for s in samples), 1) if samples else None
    series = []
    if samples:
        t_end = samples[-1][0]
        b0 = t_cut
        while b0 <= t_end:
            b = [s for s in samples if b0 <= s[0] < b0 + bucket]
            if b:
                rr = [s[3] for s in b if s[3] is not None]
                series.append(dict(t=b0, n=len(b), err_median=round(statistics.median(s[1] for s in b), 1),
                                   err_max=round(max(s[1] for s in b), 1),
                                   sigma_median=round(statistics.median(s[2] for s in b if s[2]), 1),
                                   ratio_max=round(max(rr), 2) if rr else None))
            b0 += bucket
    out["series"] = series
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    ap.add_argument("names", nargs="+")
    ap.add_argument("--bucket", type=float, default=20.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    for n in a.names:
        r = analyse(a.dir, n, a.bucket)
        if a.json:
            print(json.dumps(r, indent=1, default=str))
            continue
        print(f"== {n}: {r['end_reason']}, forwarded {r['n_forwarded']} positions after the first fault "
              f"(t={r['first_fault_s']} s); max error {r['max_err_m']} m; max error/sigma {r['max_err_over_sigma']}; "
              f"{r['n_err_over_3sigma']} positions with error > 3 sigma")
        print(f"   the source's own stated sigma (no floor): {r['stated']}")
        print(f"   withdrawn (nothing forwarded > 2 s): {r['withdrawn_intervals']}")
        print(f"   autopilot modes: {r['mode_changes']}  final: {r['final']}")
        print("   t_s   n   err_median  err_max  sigma_median  max(err/sigma)")
        for s in r["series"]:
            print(f"  {s['t']:5.0f} {s['n']:3d} {s['err_median']:10.1f} {s['err_max']:8.1f} {s['sigma_median']:12.1f} "
                  f"{s['ratio_max']!s:>12}")


if __name__ == "__main__":
    main()
