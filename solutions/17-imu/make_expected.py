#!/usr/bin/env python3
"""Teacher only — the unseen test inputs of check.py for complementary(), and the reference's answers.

    python3 solutions/17-imu/make_expected.py      → courses/17-imu/hidden/expected.json (sealed: only check.py reads it)

The expected outputs come from the course reference (solutions/_navera_lite/navera_lite/imu.py); check.py
never imports the reference. Deterministic (seed 1771).
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite import imu, rotations as rot  # noqa: E402

OUT = os.path.join(ACADEMY, "courses", "17-imu", "hidden", "expected.json")
G = 9.80665


def specific_force(q, extra_world=(0.0, 0.0, 0.0)):
    """Rᵀ(a + g·up) for attitude q (x, y, z, w)."""
    R = rot.q_to_matrix(q)
    return R.T @ (np.array(extra_world) + np.array([0.0, 0.0, G]))


def main():
    rng = np.random.default_rng(1771)
    cases = {}
    # A: a bumpy flight — random rates, uneven dt, a wrong start, accelerations; τ = 0.4 s
    n = 60
    dt = rng.uniform(0.015, 0.06, n - 1)
    t = np.concatenate([[3.0], 3.0 + np.cumsum(dt)])
    w = rng.normal(0.0, 0.5, (n, 3))
    w[10] = 0.0
    truth = rot.q_from_euler_zyx(0.3, -0.2, 1.1)
    acc = []
    q = truth
    for k in range(n):
        acc.append(specific_force(q, rng.normal(0.0, 1.0, 3)))
        if k + 1 < n:
            ang = float(np.linalg.norm(w[k])) * dt[k]
            if ang > 0:
                q = rot.q_mul(q, rot.q_from_axis_angle(w[k], ang))
    q0 = rot.q_from_euler_zyx(0.0, 0.0, 1.1)              # starts level: the filter must pull the tilt in
    cases["bumpy"] = {"q0": q0.tolist(), "t": t.tolist(), "gyro": w.tolist(), "acc": np.array(acc).tolist(), "tau": 0.4}
    # B: still, heading 330°, gravity says roll 20°, ROS pitch −10°; τ = 2 s, 4 s at 50 Hz
    n = 201
    tb = np.arange(n) * 0.02
    qb = rot.q_from_euler_zyx(math.radians(20), math.radians(-10), math.radians(90 - 330))
    fb = np.tile(specific_force(qb), (n, 1))
    cases["still"] = {"q0": rot.q_from_euler_zyx(0.0, 0.0, math.radians(90 - 330)).tolist(), "t": tb.tolist(),
                      "gyro": np.zeros((n, 3)).tolist(), "acc": fb.tolist(), "tau": 2.0}
    # C: a level hover with a constant gyro bias on x (0.5 °/s), 30 s at 50 Hz, τ = 4 s → steady roll error ≈ b·τ
    n = 1501
    tc = np.arange(n) * 0.02
    cases["bias"] = {"q0": [0.0, 0.0, 0.0, 1.0], "t": tc.tolist(),
                     "gyro": np.tile([math.radians(0.5), 0.0, 0.0], (n, 1)).tolist(),
                     "acc": np.tile([0.0, 0.0, G], (n, 1)).tolist(), "tau": 4.0}
    out = {}
    for name, c in cases.items():
        Q = imu.complementary(c["q0"], c["t"], c["gyro"], c["acc"], c["tau"])
        c["expected"] = np.round(Q, 12).tolist()
        out[name] = c
        r = rot.rpy_human(Q[-1])
        print(f"{name:6s}: last attitude roll {r[0]:+.3f}°, pitch_up {r[1]:+.3f}°, heading {r[2]:.3f}°")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f)
    print("wrote", os.path.relpath(OUT, ACADEMY), os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
