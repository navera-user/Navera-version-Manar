#!/usr/bin/env python3
"""Make the synthetic survey track of lesson 03 (deterministic: same file every time).

A multirotor inspects the breakwater of a small harbour on a desert coast
(synthetic numbers, local east/north metres from the take-off point). One row per second:
t_s, east_m, north_m. Flight: 1200 m north at ~12 m/s, 600 m east, then straight home.
Position noise 1.5 m (GPS-like), plus one 40 m glitch at t = 150 s.

    python3 make_track.py ../../courses/03-python-basics/files/harbour_track.csv
"""
import math
import random
import sys

WAYPOINTS = [(0.0, 0.0), (0.0, 1200.0), (600.0, 1200.0), (0.0, 0.0)]
SPEED = 12.0


def main(out):
    rnd = random.Random(303)
    t, rows = 0.0, []
    e, n = WAYPOINTS[0]
    rows.append((t, e, n))
    for (e0, n0), (e1, n1) in zip(WAYPOINTS, WAYPOINTS[1:]):
        length = math.hypot(e1 - e0, n1 - n0)
        done = 0.0
        while done < length - 1e-9:
            done = min(length, done + SPEED + rnd.uniform(-0.8, 0.8))
            f = done / length
            t += 1.0
            rows.append((t, e0 + f * (e1 - e0), n0 + f * (n1 - n0)))
    with open(out, "w") as fh:
        fh.write("t_s,east_m,north_m\n")
        for t, e, n in rows:
            e += rnd.gauss(0, 1.5)
            n += rnd.gauss(0, 1.5)
            if t == 150.0:
                e += 40.0          # a receiver glitch: one wrong fix
            fh.write(f"{t:.0f},{e:.2f},{n:.2f}\n")
    print(out, len(rows), "rows")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "harbour_track.csv")
