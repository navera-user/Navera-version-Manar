#!/usr/bin/env python3
"""Teacher only — makes datasets/16-rotations/ (the detective's attitude log). Deterministic (seed 16).

    python3 solutions/16-rotations/make_dataset.py

attitude_log.csv       t_s, qx, qy, qz, qw: a simulated 150 s drone flight, orientation as sensor_msgs/Imu
                       stores it (x, y, z, w), ENU world, FLU body, 10 Hz; the recorder keeps w >= 0
                       (so q changes sign once, when the rotation angle passes 180°).
colleague_attitude.csv t_s, roll_deg, pitch_up_deg, heading_deg: what the colleague's script printed — it
                       read the four numbers as (w, x, y, z).
The truth (for TEACHER.md) is printed, never written to datasets/.
"""
import csv
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite.rotations import q_from_euler_zyx, rpy_human  # noqa: E402

OUT = os.path.join(ACADEMY, "datasets", "16-rotations")
DT = 0.1
# (start_s, end_s, heading rate °/s, pitch_up °): the flight plan
PLAN = [(0, 10, 0.0, 0.0),        # on the pad, heading 030
        (10, 20, 0.0, -6.0),      # forward flight, nose 6° down
        (20, 35, 6.0, -6.0),      # right turn 030 → 120
        (35, 55, 0.0, -6.0),
        (55, 81, 5.0, -6.0),      # right turn 120 → 250
        (81, 106, 0.0, -6.0),     # west-south-west leg
        (106, 131, 3.6, -6.0),    # right turn 250 → 340 (passes west, heading 270)
        (131, 141, -3.0, -6.0),   # left turn 340 → 310
        (141, 150, 0.0, 0.0)]     # hover, heading 310
BANK_PER_RATE = 2.0               # roll (°, right wing down positive) per °/s of heading rate


def plan_at(t):
    for a, b, rate, pu in PLAN:
        if a <= t < b:
            return rate, pu
    return 0.0, 0.0


def smooth(x, n=10):
    k = np.ones(n) / n
    return np.convolve(np.pad(x, (n // 2, n - 1 - n // 2), mode="edge"), k, mode="valid")


def main():
    rng = np.random.default_rng(16)
    t = np.round(np.arange(0.0, 150.0 + 1e-9, DT), 1)
    rate = np.array([plan_at(x)[0] for x in t])
    pitch_up = smooth(np.array([plan_at(x)[1] for x in t]))
    roll = smooth(BANK_PER_RATE * rate)
    heading = 30.0 + np.concatenate([[0.0], np.cumsum(rate[:-1] * DT)])
    on_pad = t < 10.0
    noise = rng.normal(0.0, 0.05, size=(3, len(t)))
    noise[:, on_pad] *= 0.2
    roll, pitch_up, heading = roll + noise[0], pitch_up + noise[1], heading + noise[2]
    os.makedirs(OUT, exist_ok=True)
    rows, coll, flips, last = [], [], 0, None
    for k in range(len(t)):
        yaw = math.radians(90.0 - heading[k])
        q = q_from_euler_zyx(math.radians(roll[k]), math.radians(-pitch_up[k]), yaw)
        if q[3] < 0:
            q = -q
        if last is not None and float(q @ last) < 0:
            flips += 1
        last = q
        rows.append([f"{t[k]:.1f}"] + [f"{v:.7f}" for v in q])
        w, x, y, z = q                                   # the colleague's mistake: (w, x, y, z)
        r2, p2, h2 = rpy_human((x, y, z, w))
        coll.append([f"{t[k]:.1f}", f"{r2:.1f}", f"{p2:.1f}", f"{h2:.1f}"])
    with open(os.path.join(OUT, "attitude_log.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "qx", "qy", "qz", "qw"])
        w.writerows(rows)
    with open(os.path.join(OUT, "colleague_attitude.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "roll_deg", "pitch_up_deg", "heading_deg"])
        w.writerows(coll)
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write("# Mission 16 data\n\n"
                "- `attitude_log.csv` — `t_s, qx, qy, qz, qw`: the orientation of a simulated 150 s drone flight, "
                "10 samples per second, as a `sensor_msgs/Imu` message stores it (ENU world, FLU body).\n"
                "- `colleague_attitude.csv` — `t_s, roll_deg, pitch_up_deg, heading_deg`: the table a colleague's "
                "script printed from the same log.\n\nSimulated data, written for the course.\n")
    print(f"wrote {len(rows)} samples to {OUT}; sign flips in the log: {flips}")


if __name__ == "__main__":
    main()
