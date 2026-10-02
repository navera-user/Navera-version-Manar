"""Sensor histories read at a frame's exposure time."""
import math

import pytest

from navera_common.sensor_history import History, slerp


def yaw_q(deg):
    return (0.0, 0.0, math.sin(math.radians(deg) / 2), math.cos(math.radians(deg) / 2))


def yaw_of(q):
    return math.degrees(2 * math.atan2(q[2], q[3]))


def test_numbers_are_interpolated_at_the_exposure_time():
    h = History(max_gap_s=0.5)
    for t, alt in ((10.0, 100.0), (11.0, 110.0), (12.0, 130.0)):
        h.add(t, alt)
    assert h.at(10.5) == pytest.approx(105.0)
    assert h.at(11.75) == pytest.approx(125.0)
    assert h.at(12.3) == 130.0                      # just after the last sample: held
    assert h.at(13.0) is None                       # too far: unknown, not stale


def test_quaternions_are_slerped():
    h = History(max_gap_s=0.1, interp=slerp)
    h.add(0.0, yaw_q(10.0))
    h.add(0.02, yaw_q(20.0))
    assert yaw_of(h.at(0.005)) == pytest.approx(12.5, abs=1e-6)
    assert yaw_of(slerp(yaw_q(170.0), yaw_q(-170.0), 0.5)) == pytest.approx(180.0, abs=1e-6) or \
        yaw_of(slerp(yaw_q(170.0), yaw_q(-170.0), 0.5)) == pytest.approx(-180.0, abs=1e-6)


def test_a_gap_in_the_data_is_not_bridged():
    h = History(max_gap_s=0.1)
    h.add(0.0, 1.0)
    h.add(5.0, 2.0)                                  # the sensor was silent for 5 s
    assert h.at(2.5) is None
    assert h.at(0.05) == pytest.approx(1.01)         # close to a sample: still interpolated


def test_out_of_order_samples_are_dropped():
    h = History()
    h.add(1.0, 1.0)
    h.add(0.5, 99.0)
    h.add(1.0, 3.0)                                  # same stamp: replaces
    assert h.latest() == (1.0, 3.0)


def test_nearest_mode():
    h = History(max_gap_s=1.0, interp=None)
    h.add(0.0, "a")
    h.add(1.0, "b")
    assert h.at(0.4) == "a" and h.at(0.6) == "b"
