#!/usr/bin/env python3
"""Make the lesson-26 dataset (SIMULATED, reproducible — not a measurement of NAVERA).

    python3 make_dataset.py      # writes static_fixes.csv, track.csv, heights.csv, truth.json here

static_fixes.csv  A receiver standing still for 400 s on a surveyed point in Sousse harbour.
                  Its error is CORRELATED (cranes and containers hide part of the sky, so the
                  satellite geometry is poor in one direction): 1-sigma 4.0 m along an axis
                  30 deg north of east, 1.5 m across it. Columns: t_s, east_m, north_m (error
                  from the surveyed point, metres).
track.csv         A drone flying 360 s along the coast, west-north-west from Monastir.
                  Truth follows the constant-velocity model with white-noise acceleration
                  (q_true = 0.3 m^2/s^3, exact discrete Q), dt = 1 s. Position measurements
                  every second with sigma 5 m per axis (independent), EXCEPT:
                    - t = 150..189 s : no measurement (GPS jammed)  -> z_e, z_n empty
                    - 6 outliers (wrong map matches, 80-200 m off) -> outlier = 1
heights.csv       Height above ground, irregular times, from three sources with their sigma:
                  "gps-ground" (3 m), "baro" (1.5 m), "vision" (3 % of the height).
                  The truth climbs from 80 m to 140 m between t = 20 s and t = 80 s.
"""
import csv
import json
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
Q_TRUE, SIGMA_Z, DT = 0.3, 5.0, 1.0
OUTLIERS = (37, 96, 121, 233, 271, 318)
GAP = (150, 189)


def static(rng):
    th = math.radians(30.0)
    Rm = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    P = Rm @ np.diag([4.0 ** 2, 1.5 ** 2]) @ Rm.T
    L = np.linalg.cholesky(P)
    pts = (L @ rng.standard_normal((2, 400))).T
    with open(os.path.join(HERE, "static_fixes.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "east_m", "north_m"])
        for k, (e, n) in enumerate(pts):
            w.writerow([f"{k:.1f}", f"{e:.3f}", f"{n:.3f}"])
    return P


def track(rng):
    F = np.kron(np.array([[1.0, DT], [0.0, 1.0]]), np.eye(2))
    Q = np.kron(Q_TRUE * np.array([[DT ** 4 / 4, DT ** 3 / 2], [DT ** 3 / 2, DT ** 2]]), np.eye(2))
    Lq = np.linalg.cholesky(Q)
    x = np.array([0.0, 0.0, -12.0, 2.0])          # west-north-west along the coast, ~12 m/s
    rows = []
    for k in range(361):
        if k > 0:
            x = F @ x + Lq @ rng.standard_normal(4)
        z = x[:2] + SIGMA_Z * rng.standard_normal(2)
        out = 0
        if k in OUTLIERS:
            ang = rng.uniform(0, 2 * math.pi)
            d = rng.uniform(80, 200)
            z = x[:2] + d * np.array([math.cos(ang), math.sin(ang)])
            out = 1
        gap = GAP[0] <= k <= GAP[1]
        rows.append([f"{k * DT:.1f}", f"{x[0]:.3f}", f"{x[1]:.3f}", f"{x[2]:.4f}", f"{x[3]:.4f}",
                     "" if gap else f"{z[0]:.3f}", "" if gap else f"{z[1]:.3f}", f"{SIGMA_Z:.1f}",
                     0 if gap else out])
    with open(os.path.join(HERE, "track.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "true_e", "true_n", "true_ve", "true_vn", "z_e", "z_n", "sigma_m", "outlier"])
        w.writerows(rows)


def heights(rng):
    def truth(t):
        if t < 20:
            return 80.0
        if t < 80:
            return 80.0 + 60.0 * (1 - math.cos(math.pi * (t - 20) / 60)) / 2
        return 140.0
    t, rows = 0.0, []
    while t < 150:
        t += float(rng.uniform(0.4, 2.5))
        src = ["gps-ground", "baro", "vision"][int(rng.integers(0, 3))]
        h = truth(t)
        s = {"gps-ground": 3.0, "baro": 1.5, "vision": 0.03 * h}[src]
        rows.append([f"{t:.3f}", f"{h + s * rng.standard_normal():.3f}", f"{s:.3f}", src, f"{h:.3f}"])
    with open(os.path.join(HERE, "heights.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "height_m", "sigma_m", "source", "true_height_m"])
        w.writerows(rows)


def main():
    rng = np.random.default_rng(2026)
    P = static(rng)
    track(rng)
    heights(rng)
    with open(os.path.join(HERE, "truth.json"), "w") as f:
        json.dump({"static_cov_m2": P.round(6).tolist(), "static_point": "surveyed point, Sousse harbour (simulated)",
                   "track_q_true": Q_TRUE, "track_sigma_z_m": SIGMA_Z, "track_outliers_t_s": list(OUTLIERS),
                   "track_gap_t_s": list(GAP), "note": "SIMULATED data for lesson 27"}, f, indent=1)


if __name__ == "__main__":
    main()
