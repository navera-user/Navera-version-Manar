"""Builds courses/01-welcome/files/flight.csv — a SIMULATED survey flight for lab 1 (not recorded data).

A drone flies east at 15 m/s, one fix per second, for 600 s: over land (0–199 s), over the sea (200–449 s,
day vision cannot match water) and over land again (450–599 s). Honest GPS has 3 m noise and two short
multipath spikes. At t = 250 s, over the sea, a spoofer starts dragging the GPS north at 2 m/s.
Day vision, when it matches, states sigma = 30 m and has 10 m noise.
"""
import csv
import math
import os
import random

random.seed(2017)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "courses", "01-welcome", "files", "flight.csv")
SPIKES = {60: 70.0, 121: 52.0}              # multipath: the GPS jumps north for one fix
rows = []
for t in range(600):
    x, y = 15.0 * t, 0.0
    gx, gy = x + random.gauss(0, 3), y + random.gauss(0, 3) + SPIKES.get(t, 0.0)
    if t >= 250:
        gy += 2.0 * (t - 250)               # the spoof: 2 m/s drag to the north
    land = t < 200 or t >= 450
    if land:
        vx, vy, vs = x + random.gauss(0, 10), y + random.gauss(0, 10), 30.0
    else:
        vx = vy = vs = ""
    rows.append([t, round(gx, 1), round(gy, 1), "" if vx == "" else round(vx, 1), "" if vy == "" else round(vy, 1), vs])
with open(OUT, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["t_s", "gps_x_m", "gps_y_m", "vision_x_m", "vision_y_m", "vision_sigma_m"])
    w.writerows(rows)
print("wrote", os.path.normpath(OUT), len(rows), "rows")
