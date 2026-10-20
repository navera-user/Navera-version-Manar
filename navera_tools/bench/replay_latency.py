#!/usr/bin/env python3
"""Replay screen_flight logs through the online camera-delay estimator (navera_common.latency_cal).

    python3 navera_tools/bench/replay_latency.py run.csv:LATENCY:SPEED [...] [--radius 900] [--every 0]

Each CSV is a screen_flight output (columns t, phase, vis_de, vis_dn: the vision fix minus the
screen centre at the frame's stamped time t = arrival - LATENCY). The screen showed the route
(a circle of --radius at SPEED m/s), so the GPS track is that route and each frame arrived at
t + LATENCY. Every frame while the bench still trusted the GPS (source 'gps': the good phase
and the drift phase until the cross-check refused it) feeds the estimator, against a GPS that
drifts as the bench's did (a slow spoof); at the refusal it is frozen with --rollback.

Printed per run: the estimate and its sigma from the GPS phase alone, whether it would be
applied, and the vision error after GPS loss ('drift' + 'lost' phases) at the hand-set delay,
at the estimate, and at the applied value (the hand value while nothing is applied). That
error is the vision fix vs the screen truth at its stamp, minus the constant offset measured
during the GPS phase at the same delay (the bench's camera-axis calibration, the map bias in
flight): what remains is speed x delay error along a track whose heading changed.
"""
import argparse
import csv
import json
import math

import numpy as np

from navera_common.latency_cal import LatencyCalibrator

LAT0, LON0 = 35.82227, 10.61691
M = 111320.0


def route(t, v, radius):
    """Screen-centre ground point (east, north m) at t, as screen_flight.route draws it."""
    w = v / radius
    t = np.asarray(t, float)
    return np.stack([radius * np.sin(w * t), radius * (1 - np.cos(w * t))], -1)


def latlon(en):
    return LAT0 + en[1] / M, LON0 + en[0] / (M * math.cos(math.radians(LAT0)))


def after_loss_error(arr, vis, phase, latency, v, radius):
    """Median/p90 vision error after GPS loss when frames are dated arrival - latency."""
    err = vis - route(arr - latency, v, radius)
    off = np.median(err[phase == "gps"], 0)
    e = np.linalg.norm(err[phase != "gps"] - off, axis=1)
    return float(np.median(e)), float(np.percentile(e, 90))


def replay(path, latency, v, radius, every, rollback, kw, nominal=None):
    allrows = list(csv.DictReader(open(path)))
    # the GPS drift (east, m) the bench added: a line through its drift-phase rows
    dr = [(float(r["t"]), float(r["gps_drift_m"])) for r in allrows if r["phase"] == "drift"]
    k = np.polyfit(*zip(*dr), 1) if len(dr) > 2 else (0.0, 0.0)
    t_drift = -k[1] / k[0] if k[0] > 0 else 1e9
    t_refused = max(float(r["t"]) for r in allrows if r["source"] == "gps")
    rows = [r for r in allrows if r["vis_de"] not in ("", None)]
    t = np.array([float(r["t"]) for r in rows])
    phase = np.array([r["phase"] for r in rows])
    vis = route(t, v, radius) + np.array([[float(r["vis_de"]), float(r["vis_dn"])] for r in rows])
    arr = t + latency                                  # arrival times

    def gps(tt):                                       # tt: arrival-clock time; the screen at tt - latency
        en = route(tt, v, radius)
        return latlon(en + np.array([k[0] * max(0.0, tt - latency - t_drift), 0.0]))

    cal = LatencyCalibrator(nominal_s=latency if nominal is None else nominal, **kw)
    tg, last_check = -5.0, -1e9
    trace = []
    for i in np.argsort(arr):
        if t[i] > t_refused:
            break
        while tg <= arr[i] + 1.0:                      # the GPS (10 Hz) up to just after the arrival
            cal.add_gps(tg, *gps(tg))
            tg += 0.1
        if arr[i] - last_check < every:               # the node checks every gps_check_period_s
            continue
        last_check = arr[i]
        cal.add_fix(float(arr[i]), *latlon(vis[i]))
        trace.append((round(float(arr[i]), 1), cal.state()["estimate_s"], cal.state()["sigma_s"], cal.stable))
    while tg <= t_refused + latency + 2.0:
        cal.add_gps(tg, *gps(tg))
        tg += 0.1
    cal.freeze("GPS refused", rollback_s=rollback)
    # error after the GPS loss: stamp = arrival - delay; t in the CSV is arrival - latency
    errs = {}
    for name, d in (("hand", latency if nominal is None else nominal), ("estimate", cal.estimate),
                    ("applied", cal.delay())):
        errs[name] = None if d is None else after_loss_error(arr, vis, phase, d, v, radius)
    return cal, errs, trace


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", help="CSV:LATENCY:SPEED")
    ap.add_argument("--radius", type=float, default=900.0)
    ap.add_argument("--every", type=float, default=0.0, help="s between samples (the node: gps_check_period_s)")
    ap.add_argument("--min-samples", type=int, default=20)
    ap.add_argument("--max-sigma", type=float, default=0.1)
    ap.add_argument("--rollback", type=float, default=20.0, help="s of samples dropped at the GPS refusal")
    ap.add_argument("--nominal", type=float, default=None,
                    help="s, the set delay the estimate must beat (default: each run's LATENCY; 0 = no delay set)")
    ap.add_argument("--json", help="write the results here")
    a = ap.parse_args()
    out = []
    kw = dict(min_samples=a.min_samples, max_sigma_s=a.max_sigma)
    for spec in a.runs:
        path, lat, spd = spec.rsplit(":", 2)
        cal, errs, trace = replay(path, float(lat), float(spd), a.radius, a.every, a.rollback, kw, a.nominal)
        st = cal.state()
        f = (lambda e: "   -   " if e is None else f"{e[0]:5.1f}/{e[1]:5.1f}")
        print(f"{path.split('/')[-1]:24s} set {st['nominal_s']:4.2f} s {float(spd):3.0f} m/s | n={st['samples']:3d} "
              f"est {st['estimate_s']} +- {st['sigma_s']} s applied {st['applied_s']} ({st['reason'][:40]}) | "
              f"after loss median/p90 m: hand {f(errs['hand'])} est {f(errs['estimate'])} applied {f(errs['applied'])}")
        out.append(dict(run=path, hand_s=float(lat), speed=float(spd), state=st, errors=errs, trace=trace))
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
