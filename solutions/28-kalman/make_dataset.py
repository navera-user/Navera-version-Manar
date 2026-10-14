#!/usr/bin/env python3
"""Teacher only — makes datasets/28-kalman/ (SIMULATED, reproducible; not a measurement of NAVERA).

    python3 solutions/28-kalman/make_dataset.py

Writes, in datasets/28-kalman/ (students read it at /data/academy/28-kalman/):
  heights.csv            height above ground from three sources (irregular times), and the true height
  reference_heights.csv  what the COURSE'S reference Height1D (climb_accel 0.5 m/s²) says after each row of
                         heights.csv: the race target of lab Step 4
  track.csv              a 2-D flight, one position fix per second (σ 5 m), with a 40 s jam and wrong fixes
  README.md              a neutral description (no model parameters, no answers)

What the README does NOT say (answers of the lab, teacher only):
  - track truth: constant-velocity model with random accelerations of variance Q_TRUE = 0.3 m²/s⁴ per step (the
    exact discrete model of cv_model), dt = 1 s, start velocity (−12, +2) m/s;
  - fixes: truth + N(0, 5²) per axis; no fix for t = 150…189 s (GAP); 6 wrong fixes (OUTLIERS) 80–200 m off;
  - heights: truth = 80 m, climb to 140 m (20–60 s), hold, descend to 100 m (100–125 s), hold; sources baro
    (σ 1.5 m), gps-ground (σ 3 m), vision (σ = 3 % of the height); two gps-ground rows read 0.0 ("no reading");
    one baro and one gps-ground row share a time stamp.
"""
import csv
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite.kalman import Height1D, cv_model   # noqa: E402

OUT = os.path.join(ACADEMY, "datasets", "28-kalman")
SEED_TRACK, SEED_HEIGHTS = 2834, 2829
Q_TRUE, SIGMA_Z, N_STEPS = 0.3, 5.0, 361
GAP = (150, 189)
OUTLIERS = (37, 96, 121, 233, 271, 318)


def true_height(t):
    if t < 20.0:
        return 80.0
    if t < 60.0:
        return 80.0 + 60.0 * (1.0 - math.cos(math.pi * (t - 20.0) / 40.0)) / 2.0
    if t < 100.0:
        return 140.0
    if t < 125.0:
        return 140.0 - 40.0 * (1.0 - math.cos(math.pi * (t - 100.0) / 25.0)) / 2.0
    return 100.0


def make_heights(rng):
    rows, t = [], 0.0
    while True:
        t += float(rng.uniform(0.3, 2.0))
        if t > 150.0:
            break
        src = ("baro", "gps-ground", "vision")[int(rng.integers(0, 3))]
        h = true_height(t)
        s = {"baro": 1.5, "gps-ground": 3.0, "vision": 0.03 * h}[src]
        rows.append([round(t, 3), round(h + s * float(rng.standard_normal()), 3), round(s, 3), src, round(h, 3)])
    # two "no reading" rows (the receiver had no height) and one shared time stamp
    for k in (23, 61):
        rows[k][1], rows[k][3], rows[k][2] = 0.0, "gps-ground", 3.0
    k = 40
    t2 = rows[k][0]
    h = true_height(t2)
    rows.insert(k + 1, [t2, round(h + 3.0 * float(rng.standard_normal()), 3), 3.0, "gps-ground", round(h, 3)])
    rows[k][3], rows[k][2] = "baro", 1.5
    rows[k][1] = round(h + 1.5 * float(rng.standard_normal()), 3)
    return rows


def make_track(rng):
    F, _ = cv_model(1.0, Q_TRUE, dims=2)
    # one random acceleration per axis and step (variance Q_TRUE): exactly the model's Q = q·g·gᵀ
    x = np.array([0.0, 0.0, -12.0, 2.0])
    rows = []
    for k in range(N_STEPS):
        if k > 0:
            a = math.sqrt(Q_TRUE) * rng.standard_normal(2)
            x = F @ x + np.concatenate([0.5 * a, a])
        z = x[:2] + SIGMA_Z * rng.standard_normal(2)
        if k in OUTLIERS:
            ang = rng.uniform(0.0, 2.0 * math.pi)
            d = rng.uniform(80.0, 200.0)
            z = x[:2] + d * np.array([math.cos(ang), math.sin(ang)])
        gap = GAP[0] <= k <= GAP[1]
        rows.append([f"{float(k):.1f}", f"{x[0]:.3f}", f"{x[1]:.3f}", f"{x[2]:.4f}", f"{x[3]:.4f}",
                     "" if gap else f"{z[0]:.3f}", "" if gap else f"{z[1]:.3f}", f"{SIGMA_Z:.1f}"])
    return rows


def write_csv(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


README = """# Mission 28 — Kalman filter data

SIMULATED data, made for the course (not a recording, not NAVERA's output). Local metres; times in seconds.

| File | What |
|---|---|
| `heights.csv` | t_s, height_m, sigma_m, source, true_height_m: heights above the ground from three sources (`baro`, `gps-ground`, `vision`) at irregular times, each with the σ its source states. A height of 0.0 means "no reading". `true_height_m` is the truth: use it to grade a filter, never inside one |
| `reference_heights.csv` | t_s, height_m, sigma_m: the course's reference height filter (NAVERA Lite `Height1D`, default settings) after each row of `heights.csv` |
| `track.csv` | t_s, true_e, true_n, true_ve, true_vn, z_e, z_n, sigma_m: a drone flying along a coast, one second per row. `true_*` is the truth (m, m/s); `z_e`, `z_n` are the position fixes it received (empty: no fix at that second); `sigma_m` the σ per axis the fixes state |
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    for old in ("static_fixes.csv", "truth.json", "make_dataset.py"):
        p = os.path.join(OUT, old)
        if os.path.exists(p):
            os.remove(p)
    hrows = make_heights(np.random.default_rng(SEED_HEIGHTS))
    write_csv("heights.csv", ["t_s", "height_m", "sigma_m", "source", "true_height_m"],
              [[f"{r[0]:.3f}", f"{r[1]:.3f}", f"{r[2]:.3f}", r[3], f"{r[4]:.3f}"] for r in hrows])
    f, ref, last = Height1D(), [], None
    for t, h, s, _, _ in hrows:
        out = f.update(float(f"{t:.3f}"), float(f"{h:.3f}"), float(f"{s:.3f}"))
        last = out if out is not None else last
        ref.append([f"{t:.3f}", f"{last[0]:.9f}", f"{last[1]:.9f}"])
    write_csv("reference_heights.csv", ["t_s", "height_m", "sigma_m"], ref)
    write_csv("track.csv", ["t_s", "true_e", "true_n", "true_ve", "true_vn", "z_e", "z_n", "sigma_m"],
              make_track(np.random.default_rng(SEED_TRACK)))
    with open(os.path.join(OUT, "README.md"), "w") as fh:
        fh.write(README)
    print("wrote", OUT, sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
