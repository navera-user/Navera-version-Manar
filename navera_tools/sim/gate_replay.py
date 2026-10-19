#!/usr/bin/env python3
"""Replay real bench runs' match results through NAVERA's track gates, offline.

The bench CSVs hold, per frame, whether day vision accepted a match, its inliers and its error
vector against the truth. Here the truth is rebuilt as a track (screen_flight: the circuit it
flew; screen_mission: integrated from the logged heading at --speed), each accepted match is
put at truth + its logged error, and the GPS-lost part is run through:

  raw      screen_flight's own rule until 2026-10-19: an accepted match IS the output
  before   day_pkg.vision_nav.VisionNavigator as it was: a fix with >= strong_inliers bypasses
           every gate, no kinematic limit
  after    VisionNavigator with the strong-fix gate (strong_gate_k sigma) and the kinematic
           gate (max_speed_mps from the last fix)

Only the gate's decisions are replayed: the matcher is not re-run, so a different search window
after a different decision is not modelled (the logged result is reused). Spread is taken from
the CSV when logged (screen_mission), else 1.0 (screen_flight does not log it).

    python3 navera_tools/sim/gate_replay.py --flight tilt2.csv --speed 20 --radius 900 --vmax 30
    python3 navera_tools/sim/gate_replay.py --mission camp5_city_long.csv --speed 25 --vmax 40
"""
import argparse
import csv
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (os.path.join(ROOT, "day_pkg"),):
    if p not in sys.path:
        sys.path.insert(0, p)

from day_pkg.local_matcher import fix_sigma_m  # noqa: E402
from day_pkg.vision_nav import VisionNavigator, _en, _move  # noqa: E402

P0 = (35.82227, 10.61691)
MAP_MPP = 0.97                                   # z17 at 35.8 deg


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load_flight(path, speed, radius):
    """screen_flight rows -> [(t, gps_ok, truth, fix or None, inliers, spread, heading)]."""
    rows = list(csv.DictReader(open(path)))
    g = [r for r in rows if r["phase"] == "gps" and r["matched"] == "1" and r["vis_de"]]
    axis = (float(np.median([float(r["vis_de"]) for r in g])), float(np.median([float(r["vis_dn"]) for r in g])))
    out = []
    w = speed / radius
    for r in rows:
        t = float(r["t"])
        ang = w * t
        truth = _move(P0, radius * math.sin(ang), radius * (1 - math.cos(ang)))
        hdg = math.degrees(math.atan2(math.cos(ang), math.sin(ang)))     # velocity (cos, sin) e, n
        fix = None
        if r["matched"] == "1" and r["vis_de"]:
            fix = _move(truth, float(r["vis_de"]) - axis[0], float(r["vis_dn"]) - axis[1])
        out.append((t, r["phase"] == "gps", truth, fix, int(f(r["inliers"]) or 0), 1.0, hdg % 360))
    return out


def load_mission(path, speed):
    rows = list(csv.DictReader(open(path)))
    out, p, tp = [], P0, None
    for r in rows:
        t, h = float(r["t"]), float(r["heading"])
        if tp is not None:
            p = _move(p, speed * (t - tp) * math.sin(math.radians(h)), speed * (t - tp) * math.cos(math.radians(h)))
        tp = t
        fix = None
        if r["matched"] == "1" and r["vision_e"] not in ("", None):     # the matcher's result
            fix = _move(p, float(r["vision_e"]), float(r["vision_n"]))
        out.append((t, r["gps"] == "1", p, fix, int(f(r["inliers"]) or 0), f(r["spread"]) or 1.0, h))
    return out


def run(track, mode, vmax, strong_k):
    """Per GPS-lost frame: (error of the output or None, sigma or None, measured?, vision error or None, used?)."""
    nav = None
    if mode != "raw":
        nav = VisionNavigator(strong_gate_k=strong_k if mode == "after" else float("inf"),
                              max_speed_mps=vmax if mode == "after" else None)
    res, last = [], None
    for t, gps_ok, truth, fix, inl, spread, hdg in track:
        if gps_ok:
            if nav:
                nav.gps(t, *truth, heading_deg=hdg)
            last = (truth, t)
            continue
        verr = math.hypot(*_en(fix, truth)) if fix else None
        if mode == "raw":
            if fix:
                last = (fix, t)
                res.append((verr, 10.0, True, verr, True))
            else:
                res.append((math.hypot(*_en(last[0], truth)) if last else None, None, False, None, False))
            continue
        used = False
        if fix:
            r = dict(accepted=True, predicted_lat=fix[0], predicted_lon=fix[1], inliers=inl, spread=spread,
                     sigma_m=fix_sigma_m(inl, MAP_MPP), scale_residual=1.0)
            used = nav.update(t, r, None, hdg, gps_valid=False)
        lat, lon, sig, m = nav.output(t, hdg)
        e = math.hypot(*_en((lat, lon), truth)) if lat is not None else None
        res.append((e, sig, m == "measured", verr, used))
    return res


def report(name, res):
    n = len(res)
    errs = [r[0] for r in res if r[0] is not None]
    meas = [r for r in res if r[2]]
    wrong_meas = sum(1 for r in meas if r[0] is not None and r[0] > 50)
    wrong_any = sum(1 for e in errs if e > 50)
    cov = [r for r in res if r[0] is not None and r[1] is not None]
    in3 = sum(1 for r in cov if r[0] <= 3 * r[1])
    right_rej = sum(1 for r in res if r[3] is not None and r[3] <= 20 and not r[4])
    wrong_vis = sum(1 for r in res if r[3] is not None and r[3] > 50)
    wrong_used = sum(1 for r in res if r[3] is not None and r[3] > 50 and r[4])
    e = np.array(errs) if errs else np.array([np.nan])
    return (f"| {name} | {n} | {len(errs)} | {len(meas)} | {wrong_vis} | {wrong_used} | {right_rej} | {wrong_meas} | "
            f"{wrong_any} | {np.median(e):.0f} | {np.percentile(e, 90):.0f} | {np.max(e):.0f} | "
            + (f"{in3}/{len(cov)} |" if cov else "- |"))


HEADER = ("| run / estimator | lost frames | with output | measured | vision >50 m | of them USED | right (<=20 m) "
          "rejected | measured output >50 m | any output >50 m | median m | p90 m | max m | within 3 sigma |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--flight", nargs="*", default=[], help="screen_flight CSVs")
    ap.add_argument("--mission", nargs="*", default=[], help="screen_mission CSVs")
    ap.add_argument("--speed", type=float, default=20.0)
    ap.add_argument("--radius", type=float, default=900.0)
    ap.add_argument("--vmax", type=float, default=30.0, help="the vehicle's top speed for the kinematic gate")
    ap.add_argument("--strong-k", type=float, default=6.0)
    a = ap.parse_args()
    print(HEADER)
    total = {}
    for kind, paths in (("flight", a.flight), ("mission", a.mission)):
        for p in paths:
            tr = load_flight(p, a.speed, a.radius) if kind == "flight" else load_mission(p, a.speed)
            for mode in (("raw", "before", "after") if kind == "flight" else ("before", "after")):
                res = run(tr, mode, a.vmax, a.strong_k)
                total.setdefault(mode, []).extend(res)
                print(report(f"{os.path.basename(p)} / {mode}", res))
    if len(a.flight) + len(a.mission) > 1:
        for mode, res in total.items():
            print(report(f"**all files / {mode}**", res))


if __name__ == "__main__":
    main()
