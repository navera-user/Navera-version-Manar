#!/usr/bin/env python3
"""Make the dataset of mission 03 (deterministic: the same file every time).

harbour_track.csv — a SYNTHETIC survey flight of a small multirotor that inspects the breakwater of a
harbour on a rocky coast (a generic site). Local metres east (e_m) and north (n_m) of the take-off
point, one row per second: t_s,e_m,n_m. Flight: 1200 m north at about 12 m/s, 600 m east, then
straight home. GPS-like noise (σ 1.5 m per axis), and ONE wrong fix (40 m east) at t = 150 s.

    python3 solutions/03-python-basics/make_dataset.py   # writes datasets/03-python-basics/harbour_track.csv

Teacher only (course rule: generators live in solutions/<id>/, datasets/<id>/ holds outputs only).
"""
import math
import os
import random

WAYPOINTS = [(0.0, 0.0), (0.0, 1200.0), (600.0, 1200.0), (0.0, 0.0)]
SPEED_MPS = 12.0
GLITCH_T_S = 150.0
GLITCH_E_M = 40.0


def main(out):
    rnd = random.Random(303)
    t, rows = 0.0, [(0.0, 0.0, 0.0)]
    for (e0, n0), (e1, n1) in zip(WAYPOINTS, WAYPOINTS[1:]):
        length = math.hypot(e1 - e0, n1 - n0)
        done = 0.0
        while done < length - 1e-9:
            done = min(length, done + SPEED_MPS + rnd.uniform(-0.8, 0.8))
            f = done / length
            t += 1.0
            rows.append((t, e0 + f * (e1 - e0), n0 + f * (n1 - n0)))
    with open(out, "w") as fh:
        fh.write("t_s,e_m,n_m\n")
        for t, e, n in rows:
            e += rnd.gauss(0, 1.5)
            n += rnd.gauss(0, 1.5)
            if t == GLITCH_T_S:
                e += GLITCH_E_M          # a receiver glitch: one wrong fix
            fh.write(f"{t:.0f},{e:.2f},{n:.2f}\n")
    print(out, len(rows), "rows")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    main(os.path.join(here, "..", "..", "datasets", "03-python-basics", "harbour_track.csv"))
