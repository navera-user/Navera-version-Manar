#!/usr/bin/env python3
"""Make imu_log.csv for lesson 16 (run on the host:  python3 make_dataset.py).

A SIMULATED 5-minute IMU log of a multirotor, 50 Hz (the rate of NAVERA's imu_node):
    t_s                time (s)
    qx,qy,qz,qw        the fused orientation, as a BNO085 gives it: body (x forward, y left,
                       z up) in a local East-North-Up frame referenced to MAGNETIC north
    gx,gy,gz           the gyroscope (body frame, rad/s) with a constant bias + noise
    true_heading_deg   the true MAGNETIC heading (deg, clockwise from magnetic north): the
                       answer a perfect sensor would give
The drone holds 30 deg, turns to 120, 300, 210 and finally back to 30 deg.
Numbers chosen for teaching (not measured on hardware): gyro z bias 0.03 deg/s, gyro
noise 0.005 rad/s (= imu_node's angular_velocity_stddev), orientation noise 0.2 deg.
"""
import csv
import math
import os

import numpy as np

RATE_HZ, DURATION_S = 50.0, 300.0
GYRO_BIAS = np.radians([0.01, -0.01, 0.03])          # rad/s
GYRO_NOISE = 0.005                                    # rad/s
Q_NOISE = math.radians(0.2)
# (time, heading) keyframes: hold, then a smooth turn to the next heading
KEYS = [(0, 30), (20, 30), (30, 120), (90, 120), (110, 300), (170, 300), (180, 210),
        (240, 210), (250, 390), (300, 390)]


def heading_at(t):
    for (t0, h0), (t1, h1) in zip(KEYS, KEYS[1:]):
        if t0 <= t <= t1:
            if t1 == t0:
                return h0
            s = (t - t0) / (t1 - t0)
            return h0 + (h1 - h0) * (1 - math.cos(math.pi * s)) / 2
    return KEYS[-1][1]


def quat_from_rpy(r, p, y):
    cr, sr, cp, sp, cy, sy = (math.cos(r / 2), math.sin(r / 2), math.cos(p / 2), math.sin(p / 2),
                              math.cos(y / 2), math.sin(y / 2))
    return np.array([sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
                     cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy])


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])


def conj(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def main():
    rng = np.random.default_rng(16)
    n = int(DURATION_S * RATE_HZ) + 1
    t = np.arange(n) / RATE_HZ
    qs, heads = [], []
    for ti in t:
        hdg = heading_at(ti)
        flying = 20 <= ti <= 290
        roll = math.radians(1.5 * math.sin(2 * math.pi * ti / 7.0))
        # ROS pitch: positive = nose DOWN (a multirotor leans forward to fly)
        pitch = math.radians((4.0 if flying else 0.0) + 1.0 * math.sin(2 * math.pi * ti / 5.0))
        qs.append(quat_from_rpy(roll, pitch, math.radians(90.0 - hdg)))
        heads.append(hdg % 360.0)
    dt = 1.0 / RATE_HZ
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imu_log.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "qx", "qy", "qz", "qw", "gx", "gy", "gz", "true_heading_deg"])
        for i in range(n):
            # true body rate: rotation from this sample to the next (central for the last)
            a, b = (qs[i], qs[i + 1]) if i + 1 < n else (qs[i - 1], qs[i])
            d = qmul(conj(a), b)
            if d[3] < 0:
                d = -d
            ang = 2 * math.atan2(np.linalg.norm(d[:3]), d[3])
            axis = d[:3] / np.linalg.norm(d[:3]) if np.linalg.norm(d[:3]) > 1e-12 else np.zeros(3)
            omega = axis * ang / dt
            gyro = omega + GYRO_BIAS + rng.normal(0, GYRO_NOISE, 3)
            # small orientation noise: a tiny random rotation
            e = rng.normal(0, Q_NOISE, 3)
            qn = qmul(qs[i], np.array([e[0] / 2, e[1] / 2, e[2] / 2, 1.0]))
            qn /= np.linalg.norm(qn)
            if qn[3] < 0:
                qn = -qn
            w.writerow([f"{t[i]:.2f}"] + [f"{v:.6f}" for v in qn] + [f"{v:.6f}" for v in gyro]
                       + [f"{heads[i]:.3f}"])
    print("wrote", out, n, "rows")


if __name__ == "__main__":
    main()
