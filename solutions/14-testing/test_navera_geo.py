"""Tests for a function of the REAL product: navera_common/geo.py in your NAVERA copy."""
import math

import pytest

from navera_common.geo import haversine_m, is_finite_latlon


def test_sousse_is_a_position():
    assert is_finite_latlon(35.8256, 10.6084) is True


@pytest.mark.parametrize("lat, lon", [(0.0, 0.0), (math.nan, 10.0), (None, 10.0), (95.0, 10.0)])
def test_not_a_position(lat, lon):
    assert is_finite_latlon(lat, lon) is False


def test_one_degree_of_latitude():
    assert haversine_m(35.0, 10.0, 36.0, 10.0) == pytest.approx(111_195, rel=1e-3)
