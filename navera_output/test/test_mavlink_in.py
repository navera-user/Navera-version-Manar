"""MAVLink (autopilot) attitude and heights in NAVERA's frames."""
import math

import pytest

from navera_common.camera_model import body_rpy_enu
from navera_output.mavlink_in import (attitude_euler, attitude_quaternion, downward_range_agl,
                                      rates_frd_to_flu)


@pytest.mark.parametrize("roll,pitch,hdg", [(0, 0, 0), (10, 5, 90), (-15, -8, 225), (5, 20, 359)])
def test_autopilot_attitude_becomes_the_same_aviation_angles(roll, pitch, hdg):
    q = attitude_euler(math.radians(roll), math.radians(pitch), math.radians(hdg))
    r, p, h = body_rpy_enu(q)                         # roll right-down +, nose up +, heading cw from N
    assert (r, p) == pytest.approx((roll, pitch), abs=1e-6)
    assert (h - hdg + 180) % 360 - 180 == pytest.approx(0, abs=1e-6)


def test_quaternion_and_euler_forms_agree():
    roll, pitch, yaw = math.radians(12), math.radians(-7), math.radians(130)
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    w = cr * cp * cy + sr * sp * sy
    x = sr * cp * cy - cr * sp * sy
    y = cr * sp * cy + sr * cp * sy
    z = cr * cp * sy - sr * sp * cy
    a, b = attitude_quaternion(w, x, y, z), attitude_euler(roll, pitch, yaw)
    assert a == pytest.approx(b, abs=1e-9) or a == pytest.approx(tuple(-c for c in b), abs=1e-9)


def test_rates():
    assert rates_frd_to_flu(0.1, 0.2, 0.3) == (0.1, -0.2, -0.3)


def test_downward_rangefinder():
    assert downward_range_agl(15000, 20, 40000, 25) == 150.0
    assert downward_range_agl(15000, 20, 40000, 0) is None          # pointing forward
    assert downward_range_agl(50000, 20, 40000, 25) is None         # out of range
    assert downward_range_agl(40000, 20, 40000, 25) is None         # at max: no echo
    assert downward_range_agl(20, 20, 40000, 25) is None            # at min: too close / no echo
    tilted = attitude_euler(math.radians(20), 0.0, 0.0)
    assert downward_range_agl(15000, 20, 40000, 25, tilted) == pytest.approx(150.0 * math.cos(math.radians(20)))
