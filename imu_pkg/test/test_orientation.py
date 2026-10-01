"""Unit tests for the IMU orientation corrections (true north, mounting)."""
import math

import pytest

from imu_pkg.orientation import (Declination, OrientationCorrector, heading_deg, quat_from_rpy,
                                 rotate)


def enu_from_heading(heading, roll=0.0, pitch=0.0):
    """Body orientation (ENU) for a heading in deg clockwise from north."""
    return quat_from_rpy(math.radians(roll), math.radians(pitch), math.radians(90.0 - heading))


@pytest.mark.parametrize("mag_heading,decl", [(0.0, 3.3), (90.0, -12.0), (350.0, 15.0), (180.0, 0.0)])
def test_declination_turns_magnetic_into_true_heading(mag_heading, decl):
    q, _, _ = OrientationCorrector().apply(enu_from_heading(mag_heading), (0, 0, 0), (0, 0, 0), decl)
    assert heading_deg(q) == pytest.approx((mag_heading + decl) % 360.0, abs=1e-9)


def test_unknown_declination_leaves_magnetic_north():
    q0 = enu_from_heading(42.0)
    q, _, _ = OrientationCorrector().apply(q0, (0, 0, 0), (0, 0, 0), None)
    assert heading_deg(q) == pytest.approx(42.0)


def test_declination_keeps_roll_and_pitch():
    """Turning the world about 'up' must not change the tilt (celestial needs it)."""
    q, _, _ = OrientationCorrector().apply(enu_from_heading(30.0, roll=5.0, pitch=-8.0), (0, 0, 0), (0, 0, 0), 10.0)
    up_body = rotate(q, (0.0, 0.0, 1.0))
    up_ref = rotate(enu_from_heading(40.0, roll=5.0, pitch=-8.0), (0.0, 0.0, 1.0))
    assert up_body == pytest.approx(up_ref, abs=1e-9)


def test_mounting_yaw_gives_the_vehicle_heading():
    """IMU turned 90° left on the vehicle: the sensor reads heading-90, the body heading is right."""
    corr = OrientationCorrector((0.0, 0.0, 90.0))
    vehicle_heading = 120.0
    sensor_q = enu_from_heading(vehicle_heading - 90.0)
    q, _, _ = corr.apply(sensor_q, (0, 0, 0), (0, 0, 0), 0.0)
    assert heading_deg(q) == pytest.approx(vehicle_heading)


def test_mounting_rotates_rates_and_accelerations_into_the_body_frame():
    corr = OrientationCorrector((0.0, 0.0, 90.0))       # sensor x = body y (left)
    _, gyro, acc = corr.apply(enu_from_heading(0.0), (0.0, 0.0, 0.5), (1.0, 0.0, 0.0), None)
    assert gyro == pytest.approx((0.0, 0.0, 0.5))        # yaw rate unchanged by a yaw mount
    assert acc == pytest.approx((0.0, 1.0, 0.0), abs=1e-12)   # sensor-forward is body-left


def test_upside_down_mount():
    corr = OrientationCorrector((180.0, 0.0, 0.0))       # IMU mounted upside down
    sensor_q = quat_from_rpy(math.pi, 0.0, math.radians(90.0 - 75.0))
    q, _, acc = corr.apply(sensor_q, (0, 0, 0), (0.0, 0.0, -9.81), None)
    assert heading_deg(q) == pytest.approx(75.0)
    assert rotate(q, (0.0, 0.0, 1.0)) == pytest.approx((0.0, 0.0, 1.0), abs=1e-9)   # body level
    assert acc == pytest.approx((0.0, 0.0, 9.81), abs=1e-9)


def test_world_magnetic_model_values():
    d = Declination()
    if not d.available:
        pytest.skip(d.error)
    assert d.update(35.83, 10.64, 2026.75) == pytest.approx(3.33, abs=0.05)      # Sousse
    assert d.update(35.84, 10.65, 2026.75) is None                               # moved 1 km
    assert d.update(48.85, 2.35, 2026.75) == pytest.approx(2.08, abs=0.05)       # Paris


def test_world_magnetic_model_far_from_home_matters():
    """Declination is small around Tunisia but large elsewhere (why it is applied)."""
    d = Declination()
    if not d.available:
        pytest.skip(d.error)
    assert abs(d.update(64.1, -21.9, 2026.75)) > 8.0           # Reykjavik
