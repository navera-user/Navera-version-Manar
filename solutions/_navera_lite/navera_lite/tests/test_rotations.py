"""Tests of navera_lite/rotations.py (mission 16). Written for the course; it is not NAVERA code.

Run from the lesson folder:  python3 -m pytest navera_lite/tests/test_rotations.py -q
"""
import math

import numpy as np
import pytest

from navera_lite import rotations as r


def test_elementary_rotations_are_proper():
    for f in (r.rot_x, r.rot_y, r.rot_z):
        m = f(0.7)
        assert np.allclose(m @ m.T, np.eye(3)) and np.linalg.det(m) == pytest.approx(1.0)


def test_positive_ros_pitch_is_nose_down():
    nose = r.euler_zyx_to_matrix(0.0, math.radians(10), 0.0)[:, 0]
    assert nose[2] < 0
    roll, pitch_up, heading = r.rpy_human(r.q_from_euler_zyx(0.0, math.radians(10), 0.0))
    assert pitch_up == pytest.approx(-10.0) and heading == pytest.approx(90.0)


def test_euler_round_trip_and_gimbal_lock():
    assert r.matrix_to_euler_zyx(r.euler_zyx_to_matrix(-0.4, 0.9, -2.0))[:3] == pytest.approx((-0.4, 0.9, -2.0))
    roll, pitch, yaw, locked = r.matrix_to_euler_zyx(r.euler_zyx_to_matrix(0.2, -math.pi / 2, 0.3))
    assert locked and roll == 0.0 and yaw == pytest.approx(0.5)


def test_quaternion_matches_matrix():
    q = r.q_mul(r.q_from_axis_angle((0, 0, 1), 0.8), r.q_from_axis_angle((1, -1, 0.5), -1.1))
    m = r.euler_zyx_to_matrix(0.3, -0.5, 1.2)
    assert np.allclose(r.q_to_matrix(r.q_from_euler_zyx(0.3, -0.5, 1.2)), m)
    v = np.array([0.3, -2.0, 1.0])
    assert np.allclose(r.q_rotate(q, v), r.q_to_matrix(q) @ v)
    assert np.allclose(r.q_mul(q, r.q_conj(q)), r.IDENTITY_Q)


def test_slerp_constant_rate_and_shortest_path():
    q0 = r.q_from_euler_zyx(0.0, 0.0, 0.0)
    q1 = r.q_from_euler_zyx(0.0, 0.0, math.radians(120))
    for t in (0.25, 0.5, 0.75):
        assert r.q_angle_deg(q0, r.slerp(q0, q1, t)) == pytest.approx(120 * t)
    assert r.q_angle_deg(q0, r.slerp(q0, -q1, 0.5)) == pytest.approx(60.0)


def test_headings():
    assert r.heading_deg_from_q(r.IDENTITY_Q) == pytest.approx(90.0)
    assert r.heading_deg_from_q(r.q_from_euler_zyx(0.0, 0.0, math.radians(-90))) == pytest.approx(180.0)
    assert math.isnan(r.heading_deg_from_q(r.q_from_euler_zyx(0.0, math.pi / 2, 0.0)))
