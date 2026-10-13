"""Tests of the trip computer's pure parts (navera_lite/ros/trip_node.py, mission 11).
Written for the course; it is not NAVERA code.

Run from the lesson folder:  python3 -m pytest navera_lite/tests/test_trip.py -q
"""
import math

import pytest

from navera_lite.estimate import Estimate
from navera_lite.geo import offset
from navera_lite.ros.trip_node import TripComputer, Watchdog, speed_window

START = (35.8256, 10.6084)


def fix(e_m, t, **kw):
    lat, lon = offset(START[0], START[1], e_m, 0.0)
    return Estimate("gps", kw.pop("lat", lat), kw.pop("lon", lon), t, **kw)


def test_update_refuses_and_says_why():
    tc = TripComputer()
    assert tc.update(fix(0.0, 0.0)) == (True, "first fix")
    assert tc.update(fix(10.0, 1.0)) == (True, "ok")
    assert tc.update(fix(5000.0, 2.0)) == (False, "jump")
    assert tc.update(fix(20.0, 1.0)) == (False, "old fix")
    assert tc.update(fix(20.0, 3.0, valid=False)) == (False, "no position")
    assert tc.update(fix(20.0, 3.0, lat=math.nan)) == (False, "bad position")
    assert tc.update(fix(30.0, 3.0)) == (True, "ok")
    assert tc.refused == 4 and tc.last_refusal == "bad position"
    assert len(tc.fixes) == 3 and tc.distance_m == pytest.approx(30.0, rel=1e-3)


def test_speed_window():
    fixes = [(t, *offset(START[0], START[1], 10.0 * t, 0.0)) for t in range(11)]
    assert speed_window(fixes, 5.0) == pytest.approx(10.0, rel=1e-3)
    assert speed_window(fixes[:1], 5.0) is None
    assert speed_window([fixes[0], fixes[10]], 5.0) is None          # only one fix in the window
    assert speed_window([(0.0, 35.8256, 10.6084), (5.0, 35.8256, 10.60895), (10.0, 35.8256, 10.61005)],
                        6.0) == pytest.approx(19.83, abs=0.01)


def test_watchdog():
    w = Watchdog(3.0)
    assert w.silent(0.0) is True
    w.kick(10.0)
    assert w.silent(13.0) is False and w.silent(13.1) is True
