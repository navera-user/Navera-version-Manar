"""Example-based tests for geo_tools.py (teacher solution)."""
import math

import pytest

from geo_tools import (haversine_m, is_valid_position, latlon_to_offset, meters_to_degrees,
                       offset_to_latlon, speed_mps)

M_PER_DEG = 2 * math.pi * 6_371_000.0 / 360.0


@pytest.fixture
def london():
    """Near Big Ben, London."""
    return (51.5007, -0.1246)


def test_distance_from_a_point_to_itself_is_zero(london):
    assert haversine_m(*london, *london) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("dt", [0.0, -1.0])
def test_speed_without_time_is_none(dt):
    assert speed_mps(100.0, dt) is None


# ---------- haversine_m ----------

def test_one_degree_of_latitude():
    assert haversine_m(35.0, 10.0, 36.0, 10.0) == pytest.approx(M_PER_DEG, rel=1e-6)


def test_one_degree_of_longitude_on_the_equator_and_at_60():
    assert haversine_m(0.0, 10.0, 0.0, 11.0) == pytest.approx(M_PER_DEG, rel=1e-6)
    assert haversine_m(60.0, 10.0, 60.0, 11.0) == pytest.approx(M_PER_DEG / 2, rel=1e-3)


def test_london_to_paris_is_about_341_km(london):
    # Big Ben -> Eiffel Tower, computed independently: 340 539 m
    assert haversine_m(*london, 48.8584, 2.2945) == pytest.approx(340_539, abs=50)


# ---------- meters_to_degrees / offset_to_latlon ----------

def test_north_move_in_degrees():
    dlat, dlon = meters_to_degrees(M_PER_DEG, 0.0, 35.0)
    assert dlat == pytest.approx(1.0, rel=1e-9)
    assert dlon == pytest.approx(0.0, abs=1e-12)


def test_east_move_at_60_degrees_is_twice_as_many_degrees():
    dlat, dlon = meters_to_degrees(0.0, M_PER_DEG, 60.0)
    assert dlat == pytest.approx(0.0, abs=1e-12)
    assert dlon == pytest.approx(2.0, rel=1e-9)


def test_offset_to_latlon_moves_north_only(london):
    lat, lon = offset_to_latlon(*london, 1000.0, 0.0)
    assert lat > london[0]
    assert lon == pytest.approx(london[1], abs=1e-12)


def test_round_trip_example(london):
    n, e = latlon_to_offset(*london, *offset_to_latlon(*london, 2500.0, -1200.0))
    assert (n, e) == (pytest.approx(2500.0, abs=1e-6), pytest.approx(-1200.0, abs=1e-6))


# ---------- is_valid_position ----------

@pytest.mark.parametrize("lat, lon, ok", [
    (51.5007, -0.1246, True), (-89.9, 179.9, True), (0.0, 0.0, False), (91.0, 10.0, False),
    (-91.0, 10.0, False), (35.0, 181.0, False), (math.nan, 10.0, False), (35.0, math.inf, False)])
def test_is_valid_position(lat, lon, ok):
    assert is_valid_position(lat, lon) is ok


# ---------- speed_mps ----------

def test_speed():
    assert speed_mps(100.0, 20.0) == pytest.approx(5.0)


def test_standing_still_is_zero_not_none():
    assert speed_mps(0.0, 10.0) == 0.0
