"""Tests for geo_tools.py — run them with:   python3 -m pytest -v test_geo_tools.py"""
import math

import pytest

from geo_tools import haversine_m, is_valid_position, meters_to_degrees, speed_mps


def test_distance_from_a_point_to_itself_is_zero():
    assert haversine_m(35.8256, 10.6084, 35.8256, 10.6084) == pytest.approx(0.0, abs=1e-6)


# ---------- haversine_m ----------

def test_one_degree_of_latitude():
    assert haversine_m(35.0, 10.0, 36.0, 10.0) == pytest.approx(111_195, rel=1e-3)


def test_distance_is_symmetric():
    a = haversine_m(35.8256, 10.6084, 35.7643, 10.8113)
    b = haversine_m(35.7643, 10.8113, 35.8256, 10.6084)
    assert a == pytest.approx(b)


def test_one_degree_of_longitude_at_60_degrees_is_half():
    assert haversine_m(60.0, 10.0, 60.0, 11.0) == pytest.approx(111_195 / 2, rel=1e-3)


# ---------- meters_to_degrees ----------

def test_north_move_in_degrees():
    dlat, dlon = meters_to_degrees(111_195, 0, 35.0)
    assert dlat == pytest.approx(1.0, abs=1e-3)
    assert dlon == pytest.approx(0.0, abs=1e-9)


def test_east_move_at_60_degrees_is_twice_as_many_degrees():
    dlat, dlon = meters_to_degrees(0, 111_195, 60.0)
    assert dlat == pytest.approx(0.0, abs=1e-9)
    assert dlon == pytest.approx(2.0, abs=2e-3)


# ---------- is_valid_position ----------

def test_sousse_is_valid():
    assert is_valid_position(35.8256, 10.6084) is True


@pytest.mark.parametrize("lat, lon", [(0.0, 0.0), (91.0, 10.0), (-91.0, 10.0), (35.0, 181.0),
                                      (math.nan, 10.0), (35.0, math.inf)])
def test_invalid_positions(lat, lon):
    assert is_valid_position(lat, lon) is False


# ---------- speed_mps ----------

def test_speed():
    assert speed_mps(100, 20) == pytest.approx(5.0)


@pytest.mark.parametrize("dt", [0, -1.0])
def test_speed_without_time_is_none(dt):
    assert speed_mps(100, dt) is None
