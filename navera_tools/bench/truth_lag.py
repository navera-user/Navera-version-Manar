#!/usr/bin/env python3
"""Is the dataset's GNSS label late or early against its frames? Fit a time offset to accepted fixes.

A public dataset's position label can be taken at another instant than the frame (UAV-VisLoc
flight 06: ~360 m along the track). Errors that point along the track, with the sign following
the flight direction, are that, not the matcher. For an eval JSON (aerialvl_eval.py /
uavvisloc_eval.py layout: frames with t (s or ISO), lat, lon, accepted, east_m, north_m), this
finds the offset tau (s) and the constant east/north shift that best explain the accepted fixes
(fix ~ truth(t + tau) + shift), and prints the errors before and after. The corrected numbers
describe the matcher; the raw ones are what the dataset's labels give.

    python3 navera_tools/bench/truth_lag.py f.json [--max-err 150] [--json]
"""
import argparse
import json
import math
import statistics as st
from datetime import datetime


def _t(v):
    return float(v) if not isinstance(v, str) else datetime.fromisoformat(v).timestamp()


def analyse(frames, max_err=150.0, taus=None):
    fr = sorted(frames, key=lambda f: _t(f["t"]))
    ts = [_t(f["t"]) for f in fr]
    lat0 = fr[0]["lat"]
    kx = 111320.0 * math.cos(math.radians(lat0))
    xy = [((f["lon"] - fr[0]["lon"]) * kx, (f["lat"] - lat0) * 111320.0) for f in fr]

    def at(t):
        if t <= ts[0] or t >= ts[-1]:
            return None
        lo, hi = 0, len(ts) - 1
        while hi - lo > 1:
            m = (lo + hi) // 2
            lo, hi = (m, hi) if ts[m] <= t else (lo, m)
        if ts[hi] - ts[lo] > 20:
            return None
        u = (t - ts[lo]) / (ts[hi] - ts[lo])
        return (xy[lo][0] + u * (xy[hi][0] - xy[lo][0]), xy[lo][1] + u * (xy[hi][1] - xy[lo][1]))

    fixes = [(ts[i], xy[i][0] + f["east_m"], xy[i][1] + f["north_m"]) for i, f in enumerate(fr)
             if f.get("accepted") and f.get("err_m") is not None and f["err_m"] <= max_err]

    def score(tau, shift=(0.0, 0.0)):
        e = []
        for t, x, y in fixes:
            p = at(t + tau)
            if p is not None:
                e.append(math.hypot(x - shift[0] - p[0], y - shift[1] - p[1]))
        return e

    best = None
    for tau in taus or [k * 0.25 for k in range(-40, 41)]:
        # the constant shift for this tau: median of the residuals
        res = [(x - p[0], y - p[1]) for t, x, y in fixes for p in [at(t + tau)] if p is not None]
        if len(res) < 10:
            continue
        sh = (st.median(r[0] for r in res), st.median(r[1] for r in res))
        e = score(tau, sh)
        m = st.median(e)
        if best is None or m < best[0]:
            best = (m, tau, sh, e)
    raw = [f["err_m"] for f in fr if f.get("accepted") and f.get("err_m") is not None]
    q = lambda v, p: sorted(v)[min(len(v) - 1, int(p * (len(v) - 1)))]  # noqa: E731
    lag0 = score(0.0)
    return dict(fixes=len(raw), raw_median=round(st.median(raw), 1), raw_p90=round(q(raw, 0.9), 1),
                tau_s=best[1], shift_e_m=round(best[2][0], 1), shift_n_m=round(best[2][1], 1),
                corrected_median=round(best[0], 1), corrected_p90=round(q(best[3], 0.9), 1),
                corrected_max=round(max(best[3]), 1), corrected_over_50m=sum(e > 50 for e in best[3]),
                lag_only_median=round(st.median(score(best[1])), 1), no_lag_median=round(st.median(lag0), 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("eval_json", nargs="+")
    ap.add_argument("--max-err", type=float, default=150.0, help="fixes further than this are not used to fit")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    for p in a.eval_json:
        r = analyse(json.load(open(p))["frames"], a.max_err)
        print(json.dumps(dict(file=p, **r)) if a.json else
              f"{p}: {r['fixes']} fixes, raw median/p90 {r['raw_median']}/{r['raw_p90']} m; label offset "
              f"{r['tau_s']:+.2f} s + shift ({r['shift_e_m']}, {r['shift_n_m']}) m -> median/p90/max "
              f"{r['corrected_median']}/{r['corrected_p90']}/{r['corrected_max']} m, > 50 m {r['corrected_over_50m']} "
              f"(offset only {r['lag_only_median']} m)")


if __name__ == "__main__":
    main()
