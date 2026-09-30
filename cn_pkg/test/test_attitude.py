"""boresight_altaz: star-camera pointing from the IMU orientation (ENU, REP-103)."""
import math

import pytest

from cn_pkg.nodes.celestial_math import boresight_altaz


def q_axis(axis, deg):
    h = math.radians(deg) / 2
    x, y, z = axis
    return (x * math.sin(h), y * math.sin(h), z * math.sin(h), math.cos(h))


def q_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


I = (0.0, 0.0, 0.0, 1.0)          # body x = east, y = north, z = up


def test_zenith_camera_level_vehicle():
    alt, _ = boresight_altaz(I)
    assert alt == pytest.approx(90.0)


def test_forward_camera_follows_heading():
    assert boresight_altaz(I, 0, 0)[1] == pytest.approx(90.0)             # facing east
    yaw90 = q_axis((0, 0, 1), 90)                                          # nose to north
    assert boresight_altaz(yaw90, 0, 0)[1] == pytest.approx(0.0, abs=1e-9)
    assert boresight_altaz(yaw90, 0, 90)[1] == pytest.approx(90.0)        # mounted to the right
    assert boresight_altaz(yaw90, 0, 0, declination_deg=3.5)[1] == pytest.approx(3.5)


def test_zenith_camera_tilts_with_the_vehicle():
    # nose to north, then pitched 10 deg nose-up (about the body left axis, -10)
    q = q_mul(q_axis((0, 0, 1), 90), q_axis((0, 1, 0), -10))
    alt, az = boresight_altaz(q)
    assert alt == pytest.approx(80.0)
    assert az == pytest.approx(180.0)          # nose up → the up-camera leans backwards (south)


def test_invalid_quaternion():
    with pytest.raises(ValueError):
        boresight_altaz((0, 0, 0, 0))
