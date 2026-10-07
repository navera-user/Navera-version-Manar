#!/usr/bin/env python3
"""race_navera.py — your 1-D Kalman filter against NAVERA's real height filter.

    python3 race_navera.py        # prints the comparison, writes race.json

NAVERA's day-vision navigator (~/navera/day_pkg/day_pkg/vision_nav.py, class VisionNavigator)
keeps the height above ground in a Kalman filter on [height, climb rate]: process noise
climb_accel = 0.5 m/s^2 (so q = 0.25), first state [first height, 0] with covariance
diag(sigma^2, 4), and an update with R = sigma^2 for each independent height
(GPS minus ground, barometer, vision). Both filters read the same heights.csv.
"""
import csv
import json
import math

import numpy as np

from kalman import cv_model, kf_predict, kf_update

DATA = "/data/academy/26-uncertainty/heights.csv"
Q_HEIGHT = 0.5 ** 2          # NAVERA: climb_accel ** 2


def load_rows():
    with open(DATA) as f:
        return [(float(r["t_s"]), float(r["height_m"]), float(r["sigma_m"]), r["source"], float(r["true_height_m"]))
                for r in csv.DictReader(f)]


def student_heights(rows):
    """Your filter on the same heights: one (height, sigma) per row, AFTER that row's update.
    TODO 13: - first row: x = [h, 0.0], P = diag(sigma^2, 4.0)
             - every next row: F, Q = cv_model(dt, Q_HEIGHT, dims=1); predict; then
               kf_update with z = [h], H = [[1, 0]], R = [[sigma^2]]
             - append (x[0], sqrt(P[0][0])) after each row."""
    out = []
    x = P = None
    t_prev = None
    for t, h, s, _, _ in rows:
        if x is None:
            x, P = np.array([h, 0.0]), np.diag([s * s, 4.0])
        else:
            F, Q = cv_model(t - t_prev, Q_HEIGHT, dims=1)
            x, P = kf_predict(x, P, F, Q)
            x, P, _, _ = kf_update(x, P, np.array([h]), np.array([[1.0, 0.0]]), np.array([[s * s]]))
        t_prev = t
        out.append((float(x[0]), math.sqrt(P[0][0])))
    return out


# ---- you don't need to change anything below this line ----

def navera_heights(rows):
    from day_pkg.vision_nav import VisionNavigator      # NAVERA's real code, from ~/navera
    nav = VisionNavigator()
    out = []
    for t, h, s, src, _ in rows:
        nav.set_height(t, h, s, src)
        out.append((nav.height[0], nav.height[1]))
    return out


def main():
    rows = load_rows()
    if cv_model(1.0, 1.0, dims=1)[0] is None or kf_predict(np.zeros(2), np.eye(2), np.eye(2), np.eye(2))[0] is None:
        print("kalman.py is not finished: complete TODO 8 to 10 first (python3 kalman.py to try them).")
        return
    mine = student_heights(rows)
    if not mine or mine[0] is None or mine[0][0] is None:
        print("student_heights() returns nothing yet: complete TODO 13 (and kalman.py TODO 8-10 first).")
        return
    real = navera_heights(rows)
    truth = [r[4] for r in rows]
    diff_h = max(abs(a[0] - b[0]) for a, b in zip(mine, real))
    diff_s = max(abs(a[1] - b[1]) for a, b in zip(mine, real))
    rmse = lambda est: math.sqrt(sum((e - t) ** 2 for e, t in zip(est, truth)) / len(truth))   # noqa: E731
    res = {"n": len(rows), "max_diff_height_m": diff_h, "max_diff_sigma_m": diff_s,
           "rmse_raw_m": rmse([r[1] for r in rows]), "rmse_student_m": rmse([m[0] for m in mine]),
           "rmse_navera_m": rmse([r[0] for r in real])}
    print(f"{len(rows)} heights.   t (s)   raw (m)   yours (m) +- sigma   NAVERA (m) +- sigma")
    for i in range(0, len(rows), max(1, len(rows) // 12)):
        print(f"            {rows[i][0]:6.1f}   {rows[i][1]:7.2f}   {mine[i][0]:8.2f} +- {mine[i][1]:4.2f}"
              f"     {real[i][0]:8.2f} +- {real[i][1]:4.2f}")
    print(f"\nlargest difference with NAVERA: height {diff_h:.2e} m, sigma {diff_s:.2e} m")
    print(f"RMSE vs truth: raw heights {res['rmse_raw_m']:.2f} m, your filter {res['rmse_student_m']:.2f} m, "
          f"NAVERA {res['rmse_navera_m']:.2f} m")
    print("SAME FILTER" if diff_h < 1e-6 and diff_s < 1e-6 else "the two filters differ: check your model and your start values")
    with open("race.json", "w") as f:
        json.dump(res, f, indent=1)
    print("saved race.json")


if __name__ == "__main__":
    main()
