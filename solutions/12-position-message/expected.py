#!/usr/bin/env python3
"""TEACHER ONLY — the numbers of lab 12 Step 4 (the lag study), from datasets/12-position-message/day_vision_lag.csv.
Paste them into courses/12-position-message/check.py (LAB) and TEACHER.md when the data changes.

    python3 solutions/12-position-message/expected.py
"""
import csv
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "datasets", "12-position-message", "day_vision_lag.csv")
STATED_SIGMA_M = 30.0


def load(path=DATA):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    age = np.array([float(r["published_s"]) - float(r["exposure_s"]) for r in rows])
    err = np.array([float(r["match_err_m"]) for r in rows])
    return age, err


def within_pct(age, err, speed):
    return 100.0 * np.mean(speed * age + err <= STATED_SIGMA_M)


def speed_max(age, err, share=0.9):
    limits = np.sort((STATED_SIGMA_M - err) / age)[::-1]
    k = int(np.ceil(share * len(age))) - 1
    return float(limits[k])


if __name__ == "__main__":
    age, err = load()
    print(f"frames {len(age)}")
    print(f"LAG_MEDIAN_S         {np.percentile(age, 50):.3f}")
    print(f"p90 age              {np.percentile(age, 90):.3f}   max {age.max():.3f}  min {age.min():.3f}")
    print(f"LAG_PLANE_MEDIAN_M   {np.percentile(40.0 * age + err, 50):.2f}")
    print(f"LAG_PLANE_WITHIN_PCT {within_pct(age, err, 40.0):.2f}")
    print(f"LAG_DRONE_MEDIAN_M   {np.percentile(15.0 * age + err, 50):.2f}")
    print(f"LAG_DRONE_WITHIN_PCT {within_pct(age, err, 15.0):.2f}")
    print(f"LAG_OLD_WINDOW_REFUSED {int(np.sum(age > 3.0))}   (> 5 s: {int(np.sum(age > 5.0))})")
    v = speed_max(age, err)
    print(f"LAG_SPEED_MAX_MPS    {v:.3f}   check: {within_pct(age, err, v):.2f} % at v, "
          f"{within_pct(age, err, v + 0.05):.2f} % at v+0.05")
