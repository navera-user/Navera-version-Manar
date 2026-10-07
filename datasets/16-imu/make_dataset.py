#!/usr/bin/env python3
"""Make imu_log.csv + imu_log_meta.json for lesson 16 (run on the host: python3 make_dataset.py).

A SIMULATED 5-minute IMU log of a multirotor flying near Nizwa, at the foot of Jebel Akhdar
(Oman), sampled at 50 Hz (the rate of NAVERA's imu_node). The BNO085 of the NAVERA box is not
connected, so the lab works on this log. Being simulated, it also contains the TRUTH.

Columns of imu_log.csv
    t_s                      time (s)
    qx,qy,qz,qw              fused orientation as the BNO085 gives it (ROS order x, y, z, w):
                             body FLU (x forward, y left, z up) in a local ENU frame whose
                             north is MAGNETIC north; noise 0.2 deg
    gx,gy,gz                 gyroscope, body frame, rad/s: true rate + constant bias + white noise
    ax,ay,az                 accelerometer, body frame, m/s^2: specific force f = a - g_vec
                             (reads +9.81 on z when level and still) + vibration noise
    mx,my,mz                 magnetometer, body frame, microtesla (WMM field at the place) + noise
    true_roll_deg            truth, ROS convention (positive = right side down)
    true_pitch_deg           truth, ROS convention (positive = nose DOWN)
    true_heading_deg         truth, clockwise from TRUE north

Physics: the attitude is that of a multirotor (nose down 4 deg in cruise, banked into the
turns: roll = atan(v * turn_rate / g)), the acceleration is the derivative of the velocity
(speed up, turns, slow down), and the accelerometer reads R^T (a + g z_up). So, as on a real
drone, the accelerometer "sees" a level vehicle during a coordinated turn.

Numbers chosen for teaching (not measured on NAVERA hardware): gyro bias (0.01, -0.01, 0.03)
deg/s, gyro noise 0.005 rad/s (= imu_node angular_velocity_stddev), accelerometer noise
0.3 m/s^2 (vibration), magnetometer noise 0.4 uT.
"""
import csv
import json
import math
import os

import numpy as np
from pygeomag import GeoMag

RATE_HZ, DURATION_S = 50.0, 300.0
LAT, LON, YEAR = 22.930, 57.530, 2026.79          # near Nizwa, 15 October 2026 (synthetic)
G = 9.80665
GYRO_BIAS = np.radians([0.01, -0.01, 0.03])        # rad/s
GYRO_NOISE = 0.005                                  # rad/s
ACC_NOISE = 0.3                                     # m/s^2
MAG_NOISE = 0.4                                     # uT
Q_NOISE = math.radians(0.2)
# (time, true heading) keyframes: hold, then a smooth (cosine) turn to the next heading
KEYS = [(0, 30), (30, 30), (40, 120), (90, 120), (110, 300), (160, 300), (170, 210),
        (230, 210), (250, 390), (300, 390)]
# (time, speed m/s) keyframes
SPEED = [(0, 0.0), (10, 0.0), (20, 10.0), (280, 10.0), (290, 0.0), (300, 0.0)]


def smooth(keys, t):
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            s = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return v0 + (v1 - v0) * (1 - math.cos(math.pi * s)) / 2
    return keys[-1][1]


def rpy_to_R(r, p, y):
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def quat_from_rpy(r, p, y):       # (w, x, y, z)
    cr, sr, cp, sp, cy, sy = (math.cos(r / 2), math.sin(r / 2), math.cos(p / 2), math.sin(p / 2),
                              math.cos(y / 2), math.sin(y / 2))
    return np.array([cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy,
                     cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy])


def qmul(a, b):                   # (w, x, y, z)
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw])


def main():
    rng = np.random.default_rng(1616)
    n = int(DURATION_S * RATE_HZ) + 1
    dt = 1.0 / RATE_HZ
    t = np.arange(n) * dt
    hdg = np.radians([smooth(KEYS, x) for x in t])          # true heading, rad (unwrapped)
    spd = np.array([smooth(SPEED, x) for x in t])
    vel = np.stack([spd * np.sin(hdg), spd * np.cos(hdg), np.zeros(n)], 1)   # ENU
    acc = np.gradient(vel, dt, axis=0)
    hdot = np.gradient(hdg, dt)
    roll = np.arctan(spd * hdot / G) + np.radians(1.0) * np.sin(2 * np.pi * t / 7.0)
    pitch = np.radians(4.0) * spd / 10.0 + np.radians(0.8) * np.sin(2 * np.pi * t / 5.0)
    yaw = np.pi / 2 - hdg                                   # ENU yaw, true north

    gm = GeoMag().calculate(glat=LAT, glon=LON, alt=0, time=YEAR)
    D = gm.d
    m_enu = np.array([gm.y, gm.x, -gm.z]) / 1000.0         # nT -> uT, (east, north, up)

    Rs = [rpy_to_R(roll[i], pitch[i], yaw[i]) for i in range(n)]
    qs = [quat_from_rpy(roll[i], pitch[i], yaw[i]) for i in range(n)]
    qD = np.array([math.cos(math.radians(D) / 2), 0.0, 0.0, math.sin(math.radians(D) / 2)])

    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "imu_log.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "qx", "qy", "qz", "qw", "gx", "gy", "gz", "ax", "ay", "az",
                    "mx", "my", "mz", "true_roll_deg", "true_pitch_deg", "true_heading_deg"])
        for i in range(n):
            # true body rate from consecutive orientations: R_i^T R_{i+1} = exp([w] dt)
            a, b = (Rs[i], Rs[i + 1]) if i + 1 < n else (Rs[i - 1], Rs[i])
            dR = a.T @ b
            ang = math.acos(max(-1.0, min(1.0, (np.trace(dR) - 1) / 2)))
            vee = np.array([dR[2, 1] - dR[1, 2], dR[0, 2] - dR[2, 0], dR[1, 0] - dR[0, 1]])
            omega = vee / (2 * math.sin(ang)) * ang / dt if ang > 1e-12 else np.zeros(3)
            gyro = omega + GYRO_BIAS + rng.normal(0, GYRO_NOISE, 3)
            f_b = Rs[i].T @ (acc[i] + np.array([0.0, 0.0, G])) + rng.normal(0, ACC_NOISE, 3)
            m_b = Rs[i].T @ m_enu + rng.normal(0, MAG_NOISE, 3)
            # BNO085 output: magnetic-north ENU = rotate the world by +D about up, plus noise
            qm = qmul(qD, qs[i])
            e = rng.normal(0, Q_NOISE, 3)
            qm = qmul(qm, np.array([1.0, e[0] / 2, e[1] / 2, e[2] / 2]))
            qm /= np.linalg.norm(qm)
            if qm[0] < 0:
                qm = -qm
            w.writerow([f"{t[i]:.2f}"] + [f"{v:.6f}" for v in (qm[1], qm[2], qm[3], qm[0])]
                       + [f"{v:.6f}" for v in gyro] + [f"{v:.4f}" for v in f_b]
                       + [f"{v:.3f}" for v in m_b]
                       + [f"{math.degrees(roll[i]):.4f}", f"{math.degrees(pitch[i]):.4f}",
                          f"{math.degrees(hdg[i]) % 360.0:.4f}"])
    meta = {"place": "near Nizwa, Oman (synthetic flight)", "lat": LAT, "lon": LON,
            "decimal_year": YEAR, "date": "2026-10-15", "rate_hz": RATE_HZ, "duration_s": DURATION_S,
            "simulated": True,
            "note": "simulated log; the BNO085 of the NAVERA box is not connected",
            "sensor_model": {"gyro_bias_deg_s": [0.01, -0.01, 0.03], "gyro_noise_rad_s": GYRO_NOISE,
                             "accel_noise_m_s2": ACC_NOISE, "mag_noise_uT": MAG_NOISE,
                             "quat_noise_deg": 0.2}}
    with open(os.path.join(base, "imu_log_meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("wrote imu_log.csv", n, "rows; declination used", round(D, 3))


if __name__ == "__main__":
    main()
