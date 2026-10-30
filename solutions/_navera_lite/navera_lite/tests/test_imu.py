"""Tests of navera_lite/imu.py (mission 17). Written for the course; it is not NAVERA code.

Run from the lesson folder:  python3 -m pytest navera_lite/tests/test_imu.py -q
"""
import math

import numpy as np
import pytest

from navera_lite import imu
from navera_lite import rotations as r


def test_integrate_gyro_constant_yaw_rate():
    Q = imu.integrate_gyro((0, 0, 0, 1), [0.0, 0.5, 1.0], [[0, 0, 0.6]] * 3)
    assert Q.shape == (3, 4)
    assert r.q_angle_deg(Q[-1], r.q_from_axis_angle((0, 0, 1), 0.6)) == pytest.approx(0.0, abs=1e-9)


def test_integrate_gyro_turns_about_body_axes_and_skips_zero_rates():
    q0 = r.q_from_euler_zyx(0.0, 0.0, math.pi / 2)                 # nose north
    Q = imu.integrate_gyro(q0, [0.0, 0.5, 1.0, 1.5], [[0.5, 0, 0], [0.5, 0, 0], [0, 0, 0], [0, 0, 0]])
    roll, pitch_up, heading = r.rpy_human(Q[-1])
    assert roll == pytest.approx(math.degrees(0.5)) and pitch_up == pytest.approx(0.0, abs=1e-9)
    assert heading == pytest.approx(0.0, abs=1e-9)


def test_tilt_from_accel_signs_and_arrays():
    assert imu.tilt_from_accel(0.0, 0.0, 9.81) == (0.0, 0.0)
    roll, pitch = imu.tilt_from_accel(-1.6, 0.0, 9.68)
    assert pitch > 0                                                # ROS pitch: nose down
    rr, pp = imu.tilt_from_accel(np.array([-3.3552, 0.0]), np.array([7.9836, 0.0]), np.array([4.6094, 9.81]))
    assert np.degrees(rr) == pytest.approx([60.0, 0.0], abs=0.01) and np.degrees(pp) == pytest.approx([20.0, 0.0], abs=0.01)


def test_complementary_bias_error_is_b_tau():
    n = 1501
    t = np.arange(n) * 0.02
    Q = imu.complementary((0, 0, 0, 1), t, np.tile([math.radians(0.5), 0, 0], (n, 1)), np.tile([0, 0, 9.81], (n, 1)), 4.0)
    assert r.rpy_human(Q[-1])[0] == pytest.approx(2.0, abs=0.01)    # b·τ = 0.5 °/s × 4 s


def test_complementary_never_turns_the_heading_for_a_roll():
    q0 = r.q_from_euler_zyx(0.0, 0.0, math.radians(60))
    Q = imu.complementary(q0, [0.0, 0.5, 1.0], [[0, 0, 0]] * 3, [[0, 4.905, 8.496]] * 3, 1.5)
    assert r.rpy_human(Q[-1])[2] == pytest.approx(30.0, abs=1e-6)


def test_compass_tilt_compensation_and_true_north():
    H, Z = 28.25, 34.30
    R = r.euler_zyx_to_matrix(math.radians(10), 0.0, math.radians(90))      # nose north, 10° bank
    m = R.T @ np.array([0.0, H, -Z])
    assert imu.mag_heading(m, math.radians(10), 0.0) == pytest.approx(0.0, abs=1e-9) or \
        imu.mag_heading(m, math.radians(10), 0.0) == pytest.approx(360.0, abs=1e-9)
    assert imu.mag_heading(m, 0.0, 0.0) == pytest.approx(348.095, abs=0.01)
    assert imu.true_heading(350.0, 12.8) == pytest.approx(2.8)
    q = imu.q_true_north(r.q_from_euler_zyx(math.radians(30), 0.0, 0.0), 10.0)
    assert r.heading_deg_from_q(q) == pytest.approx(100.0)


def test_stale_detector_counts_whole_samples_and_recovers():
    d = imu.StaleDetector(max_repeat=2)
    assert [d.update(s) for s in [(1, 5), (1, 5), (1, 5), (1, 5), (1, 6), (1, 6)]] == \
        [False, False, True, True, False, False]
    with pytest.raises(ValueError):
        imu.StaleDetector(max_repeat=0)
