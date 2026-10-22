"""D8/D12: the standstill test with the gyro-propagated vertical (cn_pkg.standstill). Synthetic 500 Hz IMU.

A car on a glass-smooth road: the accelerometer barely shakes, so a gentle acceleration looks like a stop to the
exposure-window test. The long window sees the change of 'up' without any turn of the camera.
"""
import math

import numpy as np
import pytest

from cn_pkg import standstill as ss

HZ = 500


def _stream(phases, noise_g=0.0005, gyro_noise_dps=0.05, seed=0, pitch_events=()):
    """Synthetic IMU: phases [(seconds, horizontal acceleration g along camera +y)]; the camera stands: +x up.
    pitch_events [(t0, t1, deg)]: the camera is tilted by deg about +z between t0 and t1 (a person getting in),
    seen by the gyro and the accelerometer alike. Returns t_ms, acc (g), gyro (rad/s).
    """
    rng = np.random.default_rng(seed)
    a_h = np.concatenate([np.full(int(d * HZ), h) for d, h in phases])
    n = len(a_h)
    t = np.arange(n) / HZ
    ang = np.zeros(n)                               # rotation about camera +z (rad)
    for t0, t1, deg in pitch_events:
        k = (t >= t0) & (t <= t1)
        ang[k] = math.radians(deg) * (t[k] - t0) / (t1 - t0)
        ang[t > t1] += math.radians(deg)
    f_world = np.stack([np.ones(n), a_h, np.zeros(n)], 1)         # specific force in the level frame: up + accel
    c, s = np.cos(ang), np.sin(ang)
    acc = np.stack([c * f_world[:, 0] + s * f_world[:, 1], -s * f_world[:, 0] + c * f_world[:, 1],
                    f_world[:, 2]], 1)                            # R(ang)^T f
    acc += rng.normal(0, noise_g, acc.shape)
    gyro = np.zeros((n, 3))
    gyro[:, 2] = np.gradient(ang, 1.0 / HZ)
    gyro += rng.normal(0, math.radians(gyro_noise_dps), gyro.shape)
    return t * 1000.0, acc, gyro


def _at(t_ms, acc, gyro, te_s):
    return ss.judge(t_ms, acc, gyro, te_s * 1000.0)


def test_rest_is_stopped():
    t, a, g = _stream([(20, 0.0)])
    r = _at(t, a, g, 15.0)
    assert r["stopped"], r


@pytest.mark.parametrize("h", [0.02, 0.035, 0.05])
def test_gentle_acceleration_after_rest_or_cruise_is_not_stopped(h):
    """Cruising (a = 0) then a gentle acceleration: the exposure window alone calls it stopped."""
    t, a, g = _stream([(12, 0.0), (8, h)])
    for te in (14.5, 15.0, 17.0, 19.0):         # the exposure window (2 s before) after the onset
        r = _at(t, a, g, te)
        assert not r["stopped"], (te, r)
        assert "gentle" in r["why"]


def test_gentle_acceleration_longer_than_the_window_is_the_stated_limit():
    t, a, g = _stream([(5, 0.0), (20, 0.03)])
    assert _at(t, a, g, 22.0)["stopped"]          # no change of 'up' left in the window: cannot be seen (documented)


@pytest.mark.parametrize("brake", [0.1, 0.2, 0.3])
def test_stop_after_braking_is_stopped_at_once(brake):
    t, a, g = _stream([(10, 0.0), (5, -brake), (15, 0.0)])
    for te in (17.5, 19.0, 22.0, 29.0):           # 2.5 s after the stop (the exposure window) onwards
        r = _at(t, a, g, te)
        assert r["stopped"], (te, r)


def test_gentle_braking_to_a_stop_is_refused_then_accepted():
    """A very gentle roll to a stop cannot be told from a gentle acceleration: refused (safe) for LONG_S."""
    t, a, g = _stream([(10, 0.0), (8, -0.02), (20, 0.0)])
    assert not _at(t, a, g, 21.0)["stopped"]
    assert _at(t, a, g, 18.0 + ss.LONG_S + 0.5)["stopped"]


def test_coasting_on_after_braking_is_not_stopped():
    """Braking hard, then a gentle deceleration that goes on: the newest change is the gentle one."""
    t, a, g = _stream([(10, 0.0), (3, -0.15), (6, 0.0), (5, -0.03)])
    r = _at(t, a, g, 22.0)
    assert not r["stopped"], r


def test_camera_turned_at_rest_by_a_person_getting_in():
    """The car pitches 2 deg while parked (seen by the gyro): 'up' moves in the camera frame, but the propagated
    vertical does not; still stopped once the exposure window is quiet again.
    """
    t, a, g = _stream([(25, 0.0)], pitch_events=[(8.0, 9.0, 2.0)])
    r = _at(t, a, g, 15.0)
    assert r["stopped"], r
    assert r["up_change_deg"] < ss.DIR_TOL_DEG


def test_magnitude_refuses_steady_strong_acceleration():
    t, a, g = _stream([(5, 0.0), (15, 0.12)])
    r = _at(t, a, g, 18.0)
    assert not r["stopped"] and "accelerating" in r["why"]


def test_missing_imu_is_not_stopped():
    t, a, g = _stream([(20, 0.0)])
    keep = (t < 12000) | (t > 14000)
    r = _at(t[keep], a[keep], g[keep], 13.0)
    assert not r["stopped"] and "sensor data" in r["why"]


def test_short_history_uses_what_there_is():
    t, a, g = _stream([(4, 0.0)])
    r = _at(t, a, g, 3.0)
    assert r["stopped"] and r["long_window_s"] < 4.0


def test_ground_change_sees_lit_ground_moving_not_noise():
    rng = np.random.default_rng(1)
    H, W = 400, 800
    sky = rng.normal(10, 2, (H, W))
    ground = rng.uniform(0, 200, (H // 8, W // 8)).repeat(8, 0).repeat(8, 1)
    mask = np.zeros((H, W), bool)
    mask[H // 2:] = True
    f0 = np.where(mask, ground, sky)
    still = np.where(mask, ground, sky) + rng.normal(0, 2, (H, W))
    moved = np.where(mask, np.roll(ground, 24, axis=1), sky) + rng.normal(0, 2, (H, W))
    r_still = ss.ground_change(f0, still, mask)
    r_moved = ss.ground_change(f0, moved, mask)
    assert r_still is not None and r_moved is not None
    assert r_still < 3.0 < r_moved
    dark = np.where(mask, 5.0, sky)
    assert ss.ground_change(dark, dark + rng.normal(0, 2, (H, W)), mask) is None       # dark ground: says nothing
