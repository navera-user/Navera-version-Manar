#!/usr/bin/env python3
"""Replay day campaign CSVs (screen_flight) through the product's GPS refusal rule, the size rules
alone (navera_common.GpsCrossCheck) and with the growth test (GpsDriftTrend), as the arbiter sees
them: one independent vision fix per gps_check_period_s (2 s), GPS of that fix's instant.

    python3 navera_tools/bench/replay_spoof_trend.py [--sigma floor30|selfcal] [--cadence 2] DIR [...]

Per run: the recorded drift (false refusal = refused below 10 m, as replay_spoof_rule.py), the
whole run with a good GPS (any refusal is false), and drifts injected from the start of the
recorded drift phase at 0.5 / 1 / 3 / 5 m/s in three directions (drift at refusal, median / p90).
--sigma floor30: max(matcher sigma, 30 m) as replay_spoof_rule.py (the F22 baseline); selfcal: the
day node's published sigma (day_fix_sigma_m, then SigmaCalibration fed causally with |GPS - fix|,
the drift included: a spoof inflates it).
"""
import argparse
import csv
import glob
import math
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "day_pkg")]
from day_pkg.fix_sigma import SigmaCalibration, day_fix_sigma_m  # noqa: E402
from day_pkg.local_matcher import fix_sigma_m  # noqa: E402
from navera_common.gps_crosscheck import GpsCrossCheck, GpsDriftTrend  # noqa: E402

MPP = 156543.03392 * math.cos(math.radians(35.82227)) / 2 ** 17
GPS_SIGMA_M = 2.5


def load(path, cadence, sigma_mode):
    """[(t, err east, err north, model sigma)] vision error at the check cadence, phases, drift start."""
    rows = list(csv.DictReader(open(path)))
    ok = [r for r in rows if r["vis_de"] not in ("", "None")]
    g = [r for r in ok if r["phase"] == "gps"]
    if len(g) < 5:
        return None
    ax = (st.median(float(r["vis_de"]) for r in g), st.median(float(r["vis_dn"]) for r in g))
    fixes, rec = [], []
    for r in sorted(ok, key=lambda r: float(r["t"])):
        t = float(r["t"])
        rec.append((t, r["phase"], float(r["gps_drift_m"])))
        if fixes and t < fixes[-1][0] + cadence - 0.25:
            continue
        ms = fix_sigma_m(int(float(r["inliers"] or 0)), MPP)
        if sigma_mode == "selfcal":
            ms = day_fix_sigma_m(ms, speed_mps=60.0 if "_v60" in path else 20.0,
                                 height_m=float(r["height_m"] or 0) or None)
        fixes.append((t, float(r["vis_de"]) - ax[0], float(r["vis_dn"]) - ax[1], ms))
    t_drift = next((t for t, ph, _ in rec if ph != "gps"), None)
    t_lost = next((t for t, ph, _ in rec if ph == "lost"), math.inf)
    return fixes, rec, t_drift, t_lost


def refused_at(fixes, drift, trend, sigma_mode):
    """(t, drift m, reason) of the first refusal, or None. drift(t) -> (east, north) of GPS."""
    x = GpsCrossCheck(trend=GpsDriftTrend() if trend else None)
    cal = SigmaCalibration() if sigma_mode == "selfcal" else None
    for t, ee, en, ms in fixes:
        de, dn = drift(t)
        oe, on = de - ee, dn - en                           # GPS - vision
        d = math.hypot(oe, on)
        sig = max(ms, 30.0) if cal is None else cal.apply(ms)
        if cal is not None:
            cal.add(d, ms)
        why = x.update(t, d, 5.0 * sig + 50.0, 3.0 * sig, t, "day vision",
                       sample=(t, oe, on, math.hypot(sig, GPS_SIGMA_M)))
        if why:
            return t, math.hypot(de, dn), why
    return None


def summary(hits, v):
    got = sorted(h[1] for h in hits if h is not None and h[1] >= 0.5)
    early = sum(1 for h in hits if h is not None and h[1] < 0.5)
    if not got:
        return f"0/{len(hits)}"
    return (f"{len(got)}/{len(hits)} at {st.median(got):.0f} m (p90 {got[int(0.9 * (len(got) - 1))]:.0f} m, "
            f"{st.median(got) / v:.0f} s){f', {early} before the drift' if early else ''}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--sigma", choices=("floor30", "selfcal"), default="floor30")
    ap.add_argument("--cadence", type=float, default=2.0, help="s between independent fixes (gps_check_period_s)")
    a = ap.parse_args()
    runs = []
    for d in a.dirs:
        for p in sorted(glob.glob(os.path.join(d, "*.csv"))):
            r = load(p, a.cadence, a.sigma)
            if r:
                runs.append((os.path.basename(p)[:-4],) + r)
    print(f"{len(runs)} runs, sigma {a.sigma}, one fix per {a.cadence:g} s")
    for trend in (False, True):
        label = "size rules + growth" if trend else "size rules alone   "
        false_rec, false_h0 = [], []
        for name, fixes, rec, _, t_lost in runs:
            def recorded(t, rec=rec):
                return (max([dd for tt, ph, dd in rec if tt <= t and ph != "lost"] or [0.0]), 0.0)
            r = refused_at([f for f in fixes if f[0] < t_lost], recorded, trend, a.sigma)
            if r and r[1] < 10.0:
                false_rec.append(name)
            r0 = refused_at(fixes, lambda t: (0.0, 0.0), trend, a.sigma)
            if r0:
                false_h0.append((name, round(r0[0], 1), r0[2]))
        print(f"{label}: false refusals, recorded drift (< 10 m) {len(false_rec)} {false_rec or ''}; "
              f"good GPS whole run {len(false_h0)} {false_h0 or ''}")
        for v in (0.5, 1.0, 3.0, 5.0):
            hits = []
            for _, fixes, _, td, _ in runs:
                if td is None:
                    continue
                for ang in (0.0, 90.0, 225.0):
                    ce, cn = math.cos(math.radians(ang)), math.sin(math.radians(ang))

                    def drift(t, td=td, ce=ce, cn=cn):
                        return v * max(0.0, t - td) * ce, v * max(0.0, t - td) * cn
                    hits.append(refused_at(fixes, drift, trend, a.sigma))
            print(f"    {v:g} m/s: refused {summary(hits, v)}")


if __name__ == "__main__":
    main()
