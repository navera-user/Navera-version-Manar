#!/usr/bin/env python3
"""Make datasets/17-imu/ for mission 17 (teacher only — never copy this file into datasets/).

    python3 solutions/17-imu/make_dataset.py          (on the host, from the repository root; seed 1717)

Writes, deterministic:
    imu_log.csv         a SIMULATED 5-minute flight of a multirotor near Monastir (NAVERA's test area), 50 Hz
    imu_log_meta.json   place, date, rate, columns (NOT the sensor errors: the students measure them)
    imu_frozen.csv      20 s on the pad, 50 Hz: a 10-sample read hiccup at t = 5.00 s, then the data
                        freezes from t = 12.36 s on (the timestamps keep coming)
    README.md           neutral description

Columns of imu_log.csv
    t_s                                time (s)
    gx, gy, gz                         gyroscope, body FLU, rad/s = true rate + constant bias + white noise
    ax, ay, az                         accelerometer, body FLU, m/s² = specific force Rᵀ(a + g·up) + vibration noise
    mx, my, mz                         magnetometer, body FLU, µT = Rᵀ·(WMM field at the place) + noise
    chip_qx, chip_qy, chip_qz, chip_qw the IMU chip's own fused attitude, (x, y, z, w), ENU whose north is MAGNETIC
                                       north, 0.2° noise, w ≥ 0
    true_roll_deg, true_pitch_up_deg, true_heading_deg   the truth as a pilot reads it (pitch positive nose UP,
                                       heading clockwise from TRUE north)

The answers that depend on these numbers (bias, drift, best τ, RMS errors…) are in TEACHER.md; they are
recomputed by solutions/17-imu/make_expected.py and the runner. Sensor errors (chosen for teaching, not
measured on any real hardware): gyro bias (0.02, −0.03, 0.03) °/s, gyro noise 0.005 rad/s per sample,
accelerometer noise 0.3 m/s² (vibration), magnetometer noise 0.4 µT, chip attitude noise 0.2°.
"""
import csv
import json
import math
import os

import numpy as np
from pygeomag import GeoMag

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "..", "datasets", "17-imu")

RATE_HZ, DURATION_S = 50.0, 300.0
LAT, LON, YEAR = 35.760, 10.750, 2026.79          # near Monastir, 15 October 2026 (synthetic flight)
G = 9.80665
GYRO_BIAS_DEG_S = (0.05, -0.04, 0.10)
GYRO_NOISE = 0.003                                  # rad/s per sample
ACC_NOISE = 0.3                                     # m/s²
MAG_NOISE = 0.4                                     # µT
CHIP_NOISE_DEG = 0.2
# (time s, true heading deg): hold, then a smooth (cosine) turn to the next heading
KEYS = [(0, 30), (30, 30), (40, 120), (90, 120), (110, 300), (160, 300), (170, 210),
        (230, 210), (250, 390), (300, 390)]
SPEED = [(0, 0.0), (10, 0.0), (20, 10.0), (280, 10.0), (290, 0.0), (300, 0.0)]     # (time s, m/s)


def smooth(keys, t):
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            s = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return v0 + (v1 - v0) * (1 - math.cos(math.pi * s)) / 2
    return keys[-1][1]


def R_zyx(r, p, y):
    """Rz(y)·Ry(p)·Rx(r), ROS pitch (nose down positive)."""
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return np.array([[cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
                     [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
                     [-sp, cp * sr, cp * cr]])


def q_zyx(r, p, y):
    """(x, y, z, w) of the same attitude."""
    cr, sr, cp, sp, cy, sy = (math.cos(r / 2), math.sin(r / 2), math.cos(p / 2), math.sin(p / 2),
                              math.cos(y / 2), math.sin(y / 2))
    return np.array([sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
                     cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy])


def qmul(a, b):
    """Hamilton product, (x, y, z, w)."""
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz])


def body_rate(Ra, Rb, dt):
    """The constant body rate (rad/s) that turns Ra into Rb in dt: Raᵀ·Rb = exp([ω]× dt)."""
    dR = Ra.T @ Rb
    ang = math.acos(max(-1.0, min(1.0, (np.trace(dR) - 1) / 2)))
    vee = np.array([dR[2, 1] - dR[1, 2], dR[0, 2] - dR[2, 0], dR[1, 0] - dR[0, 1]])
    return vee / (2 * math.sin(ang)) * ang / dt if ang > 1e-12 else np.zeros(3)


def field():
    gm = GeoMag().calculate(glat=LAT, glon=LON, alt=0, time=YEAR)
    return gm.d, np.array([gm.y, gm.x, -gm.z]) / 1000.0          # nT → µT, (east, north, up), TRUE north


def flight(rng):
    n = int(DURATION_S * RATE_HZ) + 1
    dt = 1.0 / RATE_HZ
    t = np.arange(n) * dt
    hdg = np.radians([smooth(KEYS, x) for x in t])          # true heading, rad (unwrapped)
    spd = np.array([smooth(SPEED, x) for x in t])
    vel = np.stack([spd * np.sin(hdg), spd * np.cos(hdg), np.zeros(n)], 1)   # ENU
    acc = np.gradient(vel, dt, axis=0)
    hdot = np.gradient(hdg, dt)
    k = spd / 10.0                                          # 0 on the pad: no wobble while it sits still
    roll = np.arctan(spd * hdot / G) + np.radians(1.0) * k * np.sin(2 * np.pi * t / 7.0)
    # forward acceleration a needs a nose-down pitch atan(a/g) on a multirotor; cruise drag: 4° at 10 m/s
    along = np.einsum("ij,ij->i", acc, np.stack([np.sin(hdg), np.cos(hdg), np.zeros(n)], 1))
    pitch = np.radians(4.0) * k + np.arctan(along / G) + np.radians(0.8) * k * np.sin(2 * np.pi * t / 5.0)
    yaw = np.pi / 2 - hdg
    D, m_true = field()
    bias = np.radians(GYRO_BIAS_DEG_S)
    Rs = [R_zyx(roll[i], pitch[i], yaw[i]) for i in range(n)]
    qD = np.array([0.0, 0.0, math.sin(math.radians(D) / 2), math.cos(math.radians(D) / 2)])   # world turned +D
    rows = []
    for i in range(n):
        a, b = (Rs[i], Rs[i + 1]) if i + 1 < n else (Rs[i - 1], Rs[i])
        gyro = body_rate(a, b, dt) + bias + rng.normal(0, GYRO_NOISE, 3)
        f_b = Rs[i].T @ (acc[i] + np.array([0.0, 0.0, G])) + rng.normal(0, ACC_NOISE, 3)
        m_b = Rs[i].T @ m_true + rng.normal(0, MAG_NOISE, 3)
        qm = qmul(qD, q_zyx(roll[i], pitch[i], yaw[i]))          # magnetic-north world frame
        e = rng.normal(0, math.radians(CHIP_NOISE_DEG), 3)
        qm = qmul(qm, np.array([e[0] / 2, e[1] / 2, e[2] / 2, 1.0]))
        qm /= np.linalg.norm(qm)
        if qm[3] < 0:
            qm = -qm
        rows.append([f"{t[i]:.2f}"] + [f"{v:.6f}" for v in gyro] + [f"{v:.4f}" for v in f_b]
                    + [f"{v:.3f}" for v in m_b] + [f"{v:.6f}" for v in qm]
                    + [f"{math.degrees(roll[i]):.4f}", f"{-math.degrees(pitch[i]):.4f}",
                       f"{math.degrees(hdg[i]) % 360.0:.4f}"])
    return rows, D


def frozen(rng):
    """20 s on the pad, heading 75°, level; hiccup (10 repeats) at 5.00 s; frozen from 12.36 s on."""
    n = int(20.0 * RATE_HZ) + 1
    t = np.arange(n) / RATE_HZ
    _, m_true = field()
    R = R_zyx(0.0, 0.0, math.radians(90.0 - 75.0))
    bias = np.radians(GYRO_BIAS_DEG_S)
    rows, last = [], None
    for i in range(n):
        if 5.00 <= t[i] < 5.20 - 1e-9 or t[i] >= 12.36 - 1e-9:
            vals = last                                       # the library hands back its cached report
        else:
            gyro = bias + rng.normal(0, GYRO_NOISE, 3)
            f_b = R.T @ np.array([0.0, 0.0, G]) + rng.normal(0, ACC_NOISE, 3)
            m_b = R.T @ m_true + rng.normal(0, MAG_NOISE, 3)
            vals = [f"{v:.6f}" for v in gyro] + [f"{v:.4f}" for v in f_b] + [f"{v:.3f}" for v in m_b]
        last = vals
        rows.append([f"{t[i]:.2f}"] + vals)
    return rows


def main():
    rng = np.random.default_rng(1717)
    os.makedirs(OUT, exist_ok=True)
    rows, D = flight(rng)
    with open(os.path.join(OUT, "imu_log.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "gx", "gy", "gz", "ax", "ay", "az", "mx", "my", "mz",
                    "chip_qx", "chip_qy", "chip_qz", "chip_qw",
                    "true_roll_deg", "true_pitch_up_deg", "true_heading_deg"])
        w.writerows(rows)
    with open(os.path.join(OUT, "imu_frozen.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "gx", "gy", "gz", "ax", "ay", "az", "mx", "my", "mz"])
        w.writerows(frozen(rng))
    meta = {"place": "near Monastir, Tunisia (synthetic flight in NAVERA's test area)", "lat": LAT, "lon": LON,
            "alt_km": 0.0, "decimal_year": YEAR, "date": "2026-10-15", "rate_hz": RATE_HZ,
            "duration_s": DURATION_S, "simulated": True,
            "units": {"t_s": "s", "g": "rad/s, body FLU", "a": "m/s^2 specific force, body FLU",
                      "m": "microtesla, body FLU", "chip_q": "(x, y, z, w), ENU with MAGNETIC north",
                      "true_*": "degrees: roll right wing down +, pitch nose UP +, heading clockwise from TRUE north"},
            "pad": "the drone sits still on the pad for the first 10 s"}
    with open(os.path.join(OUT, "imu_log_meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    with open(os.path.join(OUT, "README.md"), "w") as f:
        f.write(README)
    print(f"wrote {len(rows)} rows (declination used {D:.3f}°) and imu_frozen.csv to {os.path.relpath(OUT)}")


README = """# Mission 17 data

- `imu_log.csv` — a simulated 5-minute flight of a multirotor near Monastir, 50 samples per second:
  gyroscope `gx, gy, gz` (rad/s), accelerometer `ax, ay, az` (m/s²) and magnetometer `mx, my, mz` (µT),
  all in the body frame (x forward, y left, z up); the IMU chip's own attitude `chip_qx … chip_qw`
  (x, y, z, w); and the true attitude `true_roll_deg, true_pitch_up_deg, true_heading_deg`.
- `imu_log_meta.json` — place, date, rate and units of the log.
- `imu_frozen.csv` — 20 s of IMU samples from a drone sitting on its pad (same columns, no attitude).

Simulated data, written for the course.
"""

if __name__ == "__main__":
    main()
