#!/usr/bin/env python3
"""Teacher only — makes datasets/27-uncertainty/ (students see it at /data/academy/27-uncertainty/).

    python3 solutions/27-uncertainty/make_dataset.py            # the public lab data
    python3 solutions/27-uncertainty/make_dataset.py --hidden   # also courses/27-uncertainty/hidden/drive.csv

Everything is synthetic, seeded and deterministic (seed 2727; the hidden drive uses seed 2799). This file lives in
solutions/ because a generator's numbers (true covariances, wrong-match epochs) would give answers away.

1. static_fixes.csv — 600 fixes of a receiver standing on a surveyed pillar on a harbour quay, one every 10 s
   (100 min, so consecutive errors are nearly independent). True error: Gaussian, zero mean, long axis 3.4 m at
   −55° from east (towards the south-east / north-west: multipath from a warehouse wall), short axis 1.5 m.
2. judge.json — the gate scenario of lab Steps 5–6: a drone flew 40 s on visual odometry while GPS was jammed;
   its prediction has σ 60 m along its track (bearing 120°) and 25 m across; GPS states σ 3 m. Six candidate
   fixes A–F (metres east, north from the prediction), each one a separate situation.
3. fusion.csv — a 400 s drive at 10 m/s: open sky (GPS σ 3 m round), then a street canyon at 40° from east
   (t 120–279 s, GPS long axis 18 → 34 → 18 m along the street, 6 m across), then open sky. Day vision states
   σ 15 m and is honest (Gaussian 15 m per axis) except 24 wrong matches (120–400 m off, random direction).
   GPS errors are drawn from the covariance GPS states (an honest GPS). `vis_wrong` marks the wrong matches: the
   runner uses it ONLY to score a gate.
"""
import argparse
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ACADEMY, "datasets", "27-uncertainty")
HIDDEN = os.path.join(ACADEMY, "courses", "27-uncertainty", "hidden")


def rot(deg):
    t = math.radians(deg)
    return np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])


def cov_from_axes(long_m, short_m, angle_deg):
    R = rot(angle_deg)
    return R @ np.diag([long_m ** 2, short_m ** 2]) @ R.T


def static_fixes(rng):
    P = cov_from_axes(3.4, 1.5, -55.0)
    L = np.linalg.cholesky(P)
    err = rng.standard_normal((600, 2)) @ L.T
    rows = ["t_s,e_m,n_m"]
    for i, (e, n) in enumerate(err):
        rows.append(f"{10 * i},{e:.3f},{n:.3f}")
    return "\n".join(rows) + "\n"


def judge():
    track_bearing = 120.0
    ang = 90.0 - track_bearing                    # ENU angle of the track (−30°)
    u = np.array([math.cos(math.radians(ang)), math.sin(math.radians(ang))])
    v = np.array([-u[1], u[0]])
    P = cov_from_axes(60.0, 25.0, ang)
    cands = {"A": 150 * u, "B": 150 * v, "C": -100 * u + 20 * v, "D": 400 * u, "E": 15 * u + 78 * v,
             "F": -90 * u - 45 * v}
    return {
        "story": "GPS jammed for 40 s; the drone flew on visual odometry. Prediction at (0, 0) m. Each candidate "
                 "is ONE fix in a separate situation, in metres east and north of the prediction.",
        "track_bearing_deg": track_bearing,
        "P_pred": [[round(float(P[0, 0]), 2), round(float(P[0, 1]), 2)],
                   [round(float(P[1, 0]), 2), round(float(P[1, 1]), 2)]],
        "P_pred_never_grown": [[25.0, 0.0], [0.0, 25.0]],
        "gps_sigma_m": 3.0,
        "circle_rule_m": 160.0,
        "candidates": {k: [round(float(x[0]), 1), round(float(x[1]), 1)] for k, x in cands.items()},
    }


def drive(rng, n=400, n_wrong=24, street_deg=40.0):
    t = np.arange(n, dtype=float)
    speed = 10.0
    heading = np.where((t >= 120) & (t < 280), street_deg, 0.0)          # ENU angle of travel
    steps = np.stack([speed * np.cos(np.radians(heading)), speed * np.sin(np.radians(heading))], axis=1)
    truth = np.vstack([[0.0, 0.0], np.cumsum(steps, axis=0)[:-1]])
    rows = ["t_s,true_e,true_n,gps_e,gps_n,gps_a,gps_b,gps_c,vis_e,vis_n,vis_sigma_m,vis_wrong"]
    wrong = set(rng.choice(n, size=n_wrong, replace=False).tolist())
    for i in range(n):
        if 120 <= t[i] < 280:
            long_m = 18.0 + 16.0 * math.sin(math.pi * (t[i] - 120.0) / 160.0)
            Pg = cov_from_axes(long_m, 6.0, street_deg)
        else:
            Pg = np.diag([9.0, 9.0])
        g = truth[i] + np.linalg.cholesky(Pg) @ rng.standard_normal(2)
        if i in wrong:
            d = rng.uniform(120.0, 400.0)
            a = rng.uniform(0.0, 2.0 * math.pi)
            vis = truth[i] + d * np.array([math.cos(a), math.sin(a)])
        else:
            vis = truth[i] + 15.0 * rng.standard_normal(2)
        rows.append(f"{t[i]:.0f},{truth[i, 0]:.2f},{truth[i, 1]:.2f},{g[0]:.2f},{g[1]:.2f},"
                    f"{Pg[0, 0]:.3f},{Pg[0, 1]:.3f},{Pg[1, 1]:.3f},{vis[0]:.2f},{vis[1]:.2f},15.0,{int(i in wrong)}")
    return "\n".join(rows) + "\n"


README = """# Mission 27 data

Synthetic data made for the course (no real flight). Positions and errors are in metres, east and north (ENU).

| File | What |
|---|---|
| `static_fixes.csv` | 600 fixes of a receiver standing still on a surveyed pillar on a harbour quay, one every 10 s: `t_s`, and the error `e_m`, `n_m` of each fix from the surveyed point |
| `judge.json` | lab Steps 5–6: a predicted position after a GPS outage, its covariance, the covariance GPS states, and six candidate fixes A–F |
| `fusion.csv` | lab Step 7: a 400 s drive, one row per second: the true position, the GPS fix and the covariance it states (`gps_a` = σE², `gps_b` = cov(E, N), `gps_c` = σN², m²), the day-vision fix and the σ it states, and `vis_wrong` (1 = a wrong map match; use it only to score a gate, never to decide) |
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hidden", action="store_true", help="also write courses/27-uncertainty/hidden/drive.csv")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    for f in os.listdir(OUT):                       # the old mission's files (heights, track…) live in 28 now
        os.remove(os.path.join(OUT, f))
    rng = np.random.default_rng(2727)
    with open(os.path.join(OUT, "static_fixes.csv"), "w") as f:
        f.write(static_fixes(rng))
    with open(os.path.join(OUT, "judge.json"), "w") as f:
        j = judge()
        f.write("{\n" + ",\n".join(f' "{k}": {json.dumps(v)}' for k, v in j.items()) + "\n}\n")
    with open(os.path.join(OUT, "fusion.csv"), "w") as f:
        f.write(drive(rng))
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write(README)
    print("wrote", sorted(os.listdir(OUT)))
    if args.hidden:
        os.makedirs(HIDDEN, exist_ok=True)
        with open(os.path.join(HIDDEN, "drive.csv"), "w") as f:
            f.write(drive(np.random.default_rng(2799), n=400, n_wrong=30, street_deg=-25.0))
        print("wrote", os.path.join(HIDDEN, "drive.csv"))


if __name__ == "__main__":
    main()
