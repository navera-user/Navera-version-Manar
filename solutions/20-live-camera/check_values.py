#!/usr/bin/env python3
"""check_values.py — TEACHER ONLY. Recomputes (1) courses/20-live-camera/hidden/flight_table.json, the per-delay
table check.py compares with the student's MINE_MEDIAN_M and N_* (their camera.yaml's latency_s), and (2) prints the
lab's numbers (answer key) and the values of the check's unseen inputs, all from the course reference.

    python3 solutions/20-live-camera/check_values.py        (≈ 25 s; after make_dataset.py or a reference change)
"""
import bisect
import csv
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, ROOT + '/solutions/_navera_lite')
from navera_lite import timing as T
D = ROOT + '/datasets/20-live-camera/'
imu = list(csv.DictReader(open(D + 'flight/imu.csv')))
it = [float(r['t_s']) for r in imu]
iq = [tuple(float(r[k]) for k in ('qx', 'qy', 'qz', 'qw')) for r in imu]
fr = list(csv.DictReader(open(D + 'flight/frames.csv')))
def ang(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return math.degrees(2 * math.acos(min(1.0, abs(float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b))))))
rows = [(float(r['grab_s']), float(r['height_m']), tuple(float(r[k]) for k in ('true_qx', 'true_qy', 'true_qz', 'true_qw'))) for r in fr]
table = {}
for ms in range(0, 201):
    lat = ms / 1000.0
    errs = []
    c = {"ok": 0, "no attitude": 0, "rate unknown": 0, "turning": 0, "tilted": 0}
    for g, h, qt in rows:
        e = g - lat
        q = T.attitude_at(e, it, iq)
        if q is not None:
            errs.append(h * math.tan(math.radians(ang(q, qt))))
        ok, why = T.usable(q, T.rotation_rate_dps(e, it, iq), T.DEFAULTS)
        k = "ok" if ok else {"no": "no attitude", "rotation": "rate unknown"}.get(why.split(" ")[0], why.split(" ")[0])
        c[k] += 1
    table[f"{lat:.3f}"] = {"median_m": round(float(np.median(errs)), 4), **c}
grab = []
for g, h, qt in rows:
    i = bisect.bisect_right(it, g) - 1
    grab.append(h * math.tan(math.radians(ang(iq[i], qt))))
meta = {"grab_median_m": round(float(np.median(grab)), 4), "grab_max_m": round(float(max(grab)), 4)}
scan = {f"{l:.3f}": table[f"{l:.3f}"]["median_m"] for l in np.round(np.arange(0.060, 0.2001, 0.002), 3)}
meta["best_scan_s"] = min(scan, key=scan.get)
json.dump({"meta": meta, "by_latency": table}, open(ROOT + '/courses/20-live-camera/hidden/flight_table.json', 'w'))
print(meta)
for k in ("0.000", "0.118", "0.119", "0.120", "0.121", "0.136", "0.138", "0.141", "0.156"):
    print(k, table[k])

# ---- the lab's numbers (answer key)
lab = {}
g = [float(r["grab_s"]) for r in csv.DictReader(open(D + "grab_log.csv"))]
lab["stats_60s"] = T.frame_stats(g)
lab["stats_40s"] = T.frame_stats([x for x in g if x < g[0] + 40.0])
fl = [float(r["t_white_s"]) for r in csv.DictReader(open(D + "flashes.csv"))]
bf = list(csv.DictReader(open(D + "bench_frames.csv")))
d = T.delay_from_flashes(fl, [float(r["grab_s"]) for r in bf], [float(r["brightness"]) for r in bf])
v = np.array([x for x in d if x is not None])
Tp = 1.0 / 28.8
lab["delays_ms"] = {"median": 1000 * float(np.median(v)), "min": 1000 * float(v.min()), "mean": 1000 * float(v.mean()),
                    "max": 1000 * float(v.max()), "unseen": [k for k, x in enumerate(d) if x is None],
                    "setting_s": float(np.median(v)) - Tp / 2 - 0.020, "min_minus_s": float(v.min()) - 0.020}
lab["budget_300_m"] = T.time_error_m(300.0, 30.0, Tp)
lab["dt_for_30m_s"] = math.degrees(math.atan(30.0 / 150.0)) / 25.0
lab["lesson_worked_m"] = T.time_error_m(150.0, 25.0, 0.14)
lab["step0_m"] = T.time_error_m(120.0, 40.0, 0.10)
for k, x in lab.items():
    print(k, x)
