"""Tests for the REAL product: navera_common/geo.py (teacher solution)."""
import math

import pytest

from navera_common.geo import dead_reckon, haversine_m, is_finite_latlon

M_PER_DEG = 2 * math.pi * 6_371_000.0 / 360.0


def test_muscat_is_a_position():
    assert is_finite_latlon(23.588, 58.3829) is True


@pytest.mark.parametrize("lat, lon", [(0.0, 0.0), (math.nan, 10.0), (None, 10.0), (95.0, 10.0)])
def test_not_a_position(lat, lon):
    assert is_finite_latlon(lat, lon) is False


def test_one_degree_of_latitude():
    assert haversine_m(23.0, 58.0, 24.0, 58.0) == pytest.approx(M_PER_DEG, rel=1e-6)


def test_dead_reckon_100_m_east():
    lat, lon = dead_reckon(23.588, 58.3829, 90.0, 10.0, 10.0)
    assert haversine_m(23.588, 58.3829, lat, lon) == pytest.approx(100.0, abs=0.01)
    assert lon > 58.3829


@pytest.mark.parametrize("speed, dt", [(-1.0, 10.0), (10.0, 0.0)])
def test_dead_reckon_refuses_unknown_motion(speed, dt):
    assert dead_reckon(23.588, 58.3829, 90.0, speed, dt) is None
