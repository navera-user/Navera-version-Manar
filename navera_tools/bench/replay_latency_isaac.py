#!/usr/bin/env python3
"""Replay Isaac Sim campaign runs through the online camera-delay estimator (navera_common.latency_cal).

    python3 navera_tools/bench/replay_latency_isaac.py [RUN_DIR ...] [--true-delay 1.3] [--rollback 20]
        [--prior D,SIGMA]

SIMULATION data (navera_tools/isaac campaign, ~/.navera_sim/isaac/campaign/<run>): every run logs
day.csv (each vision fix: its arrival stamp t, lat/lon, the truth exposure time) and position.csv
(NAVERA's output — the GPS while 'gps' is 'on' — and the truth). The GPS-check fixes of the GPS
phase are fed to the estimator against that GPS track exactly as day_subscriber does (arrival =
the camera's stamp + camera_latency_s 0), the estimator is frozen at the cut (with rollback),
and the vision fixes after the cut are re-dated by what it applied.

Printed per run: samples, estimate +- sigma at the cut (before / after the rollback), when a
delay was first applied and what was applied at the cut with its sigma, and the fix error after
the cut at the stated time (fix vs truth at arrival - applied) with the delay applied (and with
none, as the campaign ran: c3_base 12.8 / 20.7 m), and at the exposure (the floor).
"""
import argparse
import csv
import glob
import json
import math
import os

import numpy as np

from navera_common.latency_cal import LatencyCalibrator

M = 111320.0
DEFAULT_RUNS = os.path.expanduser("~/.navera_sim/isaac/campaign")


def load(run):
    pos = list(csv.DictReader(open(os.path.join(run, "position.csv"))))
    day = list(csv.DictReader(open(os.path.join(run, "day.csv"))))
    fr = [json.loads(x) for x in open(os.path.join(run, "frames.jsonl"))]
    summ = json.load(open(os.path.join(run, "summary.json")))
    cut = (summ.get("mission") or {}).get("cut_at")
    if cut is None:
        off = [float(r["t"]) for r in pos if r["gps"] != "on"]
        cut = off[0] if off else None
    gps = [(float(r["t"]), float(r["lat"]), float(r["lon"])) for r in pos
           if r["gps"] == "on" and r["source"] == "gps" and r["lat"] not in ("", "nan")]
    fixes = [(float(r["t"]), float(r["lat"]), float(r["lon"]), float(r["t_exposure"])) for r in day
             if r["mode"] == "measured" and r["valid"] == "1" and r["t_exposure"] not in ("", "nan")]
    truth = np.array([(f["t"], f["lat"], f["lon"], f.get("z", 0.0)) for f in fr])
    return gps, fixes, truth, cut


def truth_at(truth, t):
    return np.interp(t, truth[:, 0], truth[:, 1]), np.interp(t, truth[:, 0], truth[:, 2])


def dist(a, b):
    c = math.cos(math.radians(a[0]))
    return math.hypot((a[0] - b[0]) * M, (a[1] - b[1]) * M * c)


def replay(run, rollback, prior, kw):
    gps, fixes, truth, cut = load(run)
    if cut is None or not gps:
        return None
    cal = LatencyCalibrator(**kw)
    if prior is not None and hasattr(cal, "set_prior"):
        cal.set_prior(*prior)
    gi, first_applied = 0, None
    pre = [f for f in fixes if f[0] < cut]
    for ta, la, lo, te in pre:
        # the day node sees a check fix ~0.5 s after its arrival (matching), by then GPS up to that time
        while gi < len(gps) and gps[gi][0] <= ta + 0.5:
            cal.add_gps(*gps[gi])
            gi += 1
        cal.add_fix(ta, la, lo)
        if first_applied is None and cal.applied is not None:
            first_applied = (ta, cal.applied)
    while gi < len(gps) and gps[gi][0] < cut:
        cal.add_gps(*gps[gi])
        gi += 1
    before = (cal.samples, cal.estimate, cal.sigma)
    cal.freeze("GPS lost", rollback)
    a = cal.applied if cal.applied is not None else 0.0
    asig = getattr(cal, "applied_sigma", None)
    post = [f for f in fixes if f[0] >= cut]
    e0 = [dist((la, lo), truth_at(truth, ta)) for ta, la, lo, te in post]
    e1 = [dist((la, lo), truth_at(truth, ta - a)) for ta, la, lo, te in post]
    ex = [dist((la, lo), truth_at(truth, te)) for ta, la, lo, te in post]
    return dict(run=os.path.basename(run), cut=cut, before=before, after=(cal.samples, cal.estimate, cal.sigma),
                first=first_applied, applied=cal.applied, applied_sigma=asig, reason=cal.reason, cal=cal,
                n=len(post), e0=e0, e1=e1, ex=ex)


def fmt(x, k=2):
    return "-" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{k}f}"


def stats(e):
    return f"{np.median(e):5.1f}/{np.percentile(e, 90):5.1f}" if e else "  -  /  -  "


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*")
    ap.add_argument("--rollback", type=float, default=20.0)
    ap.add_argument("--true-delay", type=float, default=1.3)
    ap.add_argument("--prior", help="D,SIGMA: a stored delay to start from")
    a = ap.parse_args()
    runs = a.runs or sorted(d for d in glob.glob(os.path.join(DEFAULT_RUNS, "c*")) if os.path.isdir(d))
    prior = tuple(float(x) for x in a.prior.split(",")) if a.prior else None
    print(f"{'run':18s} {'n':>3s} {'est+-sig before cut':>20s} {'after rollback':>16s} {'first applied':>14s} "
          f"{'applied+-sig':>13s} {'stamp err none':>14s} {'stamp err appl':>14s} {'exposure':>11s}")
    for run in runs:
        try:
            r = replay(run, a.rollback, prior, {})
        except (OSError, KeyError, ValueError, IndexError) as exc:
            print(f"{os.path.basename(run):18s} skipped ({exc})")
            continue
        if r is None or not r["n"]:
            continue
        b, af = r["before"], r["after"]
        first = f"{r['first'][0] - r['cut']:+.0f}s {r['first'][1]:.2f}" if r["first"] else "-"
        print(f"{r['run']:18s} {b[0]:3d} {fmt(b[1]):>8s} +- {fmt(b[2]):<6s}   {af[0]:3d} {fmt(af[1]):>5s}+-{fmt(af[2]):<5s} "
              f"{first:>14s} {fmt(r['applied']):>6s}+-{fmt(r['applied_sigma']):<5s} {stats(r['e0']):>14s} "
              f"{stats(r['e1']):>14s} {stats(r['ex']):>11s}")


if __name__ == "__main__":
    main()
