#!/usr/bin/env python3
"""Regenerates the data of mission 12 (the position contract). TEACHER ONLY: never copy it into datasets/
(students can read everything there).

    python3 solutions/12-position-message/make_dataset.py

Writes datasets/12-position-message/day_vision_lag.csv — a SYNTHETIC bench log of a day-vision matcher:
one row per photo, `frame,exposure_s,published_s,match_err_m`:
  exposure_s   when the photo was taken (bench clock, s)
  published_s  when the matcher published its position (s): latency = published_s − exposure_s
  match_err_m  how far the matched position is from where the camera really was AT THE EXPOSURE (m)
It imitates what NAVERA's validation report (2026-10-03, simulator) describes in words: vision fixes 1–2.5 s
old, match error 0–1 m. 160 photos, one every ≈2 s; latency from a lognormal around 1.6 s, clipped to
[0.95, 2.6] s, plus 6 frames taken while the computer was busy (3.2–4.6 s).
Deterministic (seed 1203). check.py of mission 12 recomputes its numbers from this file: if you change
it, rerun solutions/12-position-message/expected.py and paste the new numbers into check.py and TEACHER.md.
"""
import csv
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "datasets", "12-position-message", "day_vision_lag.csv")


def main():
    rnd = random.Random(1203)
    busy = set(rnd.sample(range(20, 160), 6))
    rows, t = [], 1000.0
    for k in range(160):
        t += rnd.uniform(1.6, 2.4)
        if k in busy:
            lat = rnd.uniform(3.2, 4.6)
        else:
            lat = min(2.6, max(0.95, math.exp(rnd.gauss(math.log(1.6), 0.22))))
        rows.append((k, round(t, 3), round(t + lat, 3), round(rnd.uniform(0.0, 1.0), 2)))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "exposure_s", "published_s", "match_err_m"])
        w.writerows(rows)
    print("wrote", os.path.normpath(OUT), len(rows), "rows")


if __name__ == "__main__":
    main()
