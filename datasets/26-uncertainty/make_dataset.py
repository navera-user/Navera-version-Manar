#!/usr/bin/env python3
"""Make the lesson-26 dataset (synthetic, reproducible): a receiver standing still on a known
point, measured 300 times by a simulated GPS and by a simulated vision source.

    python3 make_dataset.py        # writes gps_fixes.csv, vision_fixes.csv, two_sources.csv, truth.json here

The point is the GPS test site of NAVERA's project report (M'saken, 35.734 N 10.576 E).
GPS: per-axis sigma 2.5 m with a slow wander (first-order Gauss-Markov, like the mission
simulator's receiver navera_tools/sim/nmea_gps.py) plus white noise.
Vision: per-axis sigma 8 m (east) / 6 m (north), errors independent from GPS, and 3 gross
mismatches (outliers ~150 m away) — what a wrong map match looks like.
two_sources.csv: two independent sources A (sigma 6 m per axis) and B (9 m), no outliers.
SIMULATED DATA — not a measurement of NAVERA.
"""
import csv
import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
LAT0, LON0 = 35.734, 10.576
R = 6_371_000.0
M_LAT = math.pi * R / 180.0
M_LON = M_LAT * math.cos(math.radians(LAT0))


def to_deg(e, n):
    return LAT0 + n / M_LAT, LON0 + e / M_LON


def main():
    rng = random.Random(2026)
    n = 300
    gps, vis = [], []
    we = wn = 0.0
    for k in range(n):
        t = float(k)
        # Gauss-Markov wander (tau 20 s) + white noise: total ~2.5 m per axis
        we += -we / 20.0 + rng.gauss(0, 0.45)
        wn += -wn / 20.0 + rng.gauss(0, 0.45)
        e, nn = we + rng.gauss(0, 1.2), wn + rng.gauss(0, 1.2)
        gps.append((t, *to_deg(e, nn)))
        ve, vn = rng.gauss(0, 8.0), rng.gauss(0, 6.0)
        if k in (41, 157, 233):                       # wrong matches
            ang = rng.uniform(0, 2 * math.pi)
            ve, vn = 150 * math.cos(ang), 150 * math.sin(ang)
        vis.append((t, *to_deg(ve, vn)))
    for name, rows in (("gps_fixes.csv", gps), ("vision_fixes.csv", vis)):
        with open(os.path.join(HERE, name), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["t_s", "lat", "lon"])
            for t, la, lo in rows:
                w.writerow([f"{t:.1f}", f"{la:.8f}", f"{lo:.8f}"])
    # two independent sources of similar quality, no outliers: for the weighted average
    rows = []
    for k in range(n):
        ae, an = rng.gauss(0, 6.0), rng.gauss(0, 6.0)
        be, bn = rng.gauss(0, 9.0), rng.gauss(0, 9.0)
        rows.append((float(k), *to_deg(ae, an), *to_deg(be, bn)))
    with open(os.path.join(HERE, "two_sources.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "a_lat", "a_lon", "b_lat", "b_lon"])
        for r in rows:
            w.writerow([f"{r[0]:.1f}"] + [f"{v:.8f}" for v in r[1:]])
    with open(os.path.join(HERE, "truth.json"), "w") as f:
        json.dump({"lat": LAT0, "lon": LON0, "note": "simulated receiver standing on this point"}, f)


if __name__ == "__main__":
    main()
