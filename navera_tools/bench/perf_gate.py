#!/usr/bin/env python3
"""Accuracy gate of an optimisation: two perf_profile.py runs on the same inputs, compared frame for frame.

    python3 navera_tools/bench/perf_gate.py BASE.json NEW.json [--max-median-m 1.0] [--wrong-m 50]

Pass when: the same frames are accepted (identical acceptance), the accepted positions of the two
runs agree within --max-median-m metres at the median, and NEW has no wrong fix (> --wrong-m from the
truth) that BASE did not have. Prints the comparison and exits 1 when the gate fails.
Works for both modes (day rows: run/file/lat/lon/err; night rows: cond/i/lat/lon/err_m).
"""
import argparse
import json
import math
import statistics
import sys


def metres(p, q):
    dn = (p[0] - q[0]) * 111320.0
    de = (p[1] - q[1]) * 111320.0 * math.cos(math.radians(q[0]))
    return math.hypot(de, dn)


def key(r):
    return (r["run"], r["file"]) if "file" in r else (r["cond"], r["i"])


def err(r):
    return r.get("err") if "err" in r else r.get("err_m")


def wrong(r, wrong_m):
    if "wrong" in r:                       # night: the bench's own rule (no-information frames count)
        return bool(r["wrong"])
    return bool(r["accepted"]) and err(r) is not None and err(r) > wrong_m


def compare(base: dict, new: dict, max_median_m: float = 1.0, wrong_m: float = 50.0) -> dict:
    a = {key(r): r for r in base["rows"]}
    b = {key(r): r for r in new["rows"]}
    common = [k for k in a if k in b]
    flips = [k for k in common if bool(a[k]["accepted"]) != bool(b[k]["accepted"])]
    both = [k for k in common if a[k]["accepted"] and b[k]["accepted"] and a[k].get("lat") is not None
            and b[k].get("lat") is not None]
    d = sorted(metres((a[k]["lat"], a[k]["lon"]), (b[k]["lat"], b[k]["lon"])) for k in both)
    new_wrong = [k for k in common if wrong(b[k], wrong_m) and not wrong(a[k], wrong_m)]
    med = statistics.median(d) if d else 0.0
    out = {"frames": len(common), "missing": len(a) - len(common),
           "accepted_base": sum(bool(a[k]["accepted"]) for k in common),
           "accepted_new": sum(bool(b[k]["accepted"]) for k in common),
           "acceptance_flips": len(flips), "flips": [list(k) for k in flips][:20],
           "pos_diff_median_m": round(med, 3), "pos_diff_p90_m": round(d[int(0.9 * (len(d) - 1))], 3) if d else 0.0,
           "pos_diff_max_m": round(d[-1], 3) if d else 0.0,
           "new_wrong": len(new_wrong), "new_wrong_frames": [list(k) for k in new_wrong][:20]}
    out["pass"] = not flips and med <= max_median_m and not new_wrong and out["missing"] == 0
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("base")
    ap.add_argument("new")
    ap.add_argument("--max-median-m", type=float, default=1.0)
    ap.add_argument("--wrong-m", type=float, default=50.0)
    a = ap.parse_args()
    r = compare(json.load(open(a.base)), json.load(open(a.new)), a.max_median_m, a.wrong_m)
    print(json.dumps(r, indent=1))
    sys.exit(0 if r["pass"] else 1)


if __name__ == "__main__":
    main()
