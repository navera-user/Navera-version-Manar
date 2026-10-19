"""The 360 camera driver's stillness and gravity verdicts on synthetic 500 Hz IMU rows (no camera needed)."""
import collections
import math
import os
import sys
import threading

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from navera_tools.field import insta360_usb  # noqa: E402

HZ = 500


def driver(acc, gyro):
    """An Insta360Usb without a camera, holding the given rows (camera ms = sample index x 2)."""
    d = insta360_usb.Insta360Usb.__new__(insta360_usb.Insta360Usb)
    d._lock = threading.Lock()
    d._imu = collections.deque(maxlen=3500)
    d.acc_bias, d.acc_scale, d.gyro_bias = np.zeros(3), np.ones(3), np.zeros(3)
    d.max_rate = math.radians(3.0)
    for i, (a, w) in enumerate(zip(acc, gyro)):
        if a is not None:
            d._imu.append((0.0, i * 1000.0 / HZ, *a, *w))
    return d


def rows(n=3000, idle_g=0.0, idle_hz=26.7, jitter_deg=0.0, accel_g=0.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n) / HZ
    acc = np.tile([1.0, 0.0, 0.0], (n, 1)) + rng.normal(0, 0.002, (n, 3))
    acc[:, 0] += idle_g * np.sin(2 * math.pi * idle_hz * t)
    acc[:, 1] += accel_g
    gyro = rng.normal(0, math.radians(0.17), (n, 3))
    gyro[:, 2] += math.radians(jitter_deg) * 2 * math.pi * 20 * np.cos(2 * math.pi * 20 * t)
    return list(acc), list(gyro)


def test_parked_with_strong_idle_vibration_is_stopped():
    d = driver(*rows(idle_g=0.05))
    assert d.stopped(at_ms=4000)["stopped"]


def test_braking_onset_is_not_stopped():
    acc, gyro = rows()
    for i in range(1700, 3000):
        acc[i] = acc[i] + np.array([0.0, -0.1 * min(1.0, (i - 1700) / 100), 0.0])
    assert not driver(acc, gyro).stopped(at_ms=4000)["stopped"]


def test_imu_silence_inside_the_window_is_not_stopped():
    acc, gyro = rows()
    for i in range(1000, 1700):                    # 1.4 s of the 2.5 s window missing
        acc[i] = None
    st = driver(acc, gyro).stopped(at_ms=4000)
    assert not st["stopped"] and "cover" in st["why"]


def test_gravity_ignores_mount_jitter():
    d = driver(*rows(jitter_deg=0.02))             # 20 Hz, peaks ~2.5 deg/s per sample: not a turn
    up, g, _ = d.gravity(at_ms=4000)
    assert up is not None and abs(g - 1.0) < 0.01 and up[0] > 0.9999
