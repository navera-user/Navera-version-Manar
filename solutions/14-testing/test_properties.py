"""Property-based tests for geo_tools.py with hypothesis (teacher solution)."""
import math

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from geo_tools import haversine_m, is_valid_position, latlon_to_offset, offset_to_latlon

LAT = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False)
LON = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False)
OFFSET = st.floats(min_value=-50_000.0, max_value=50_000.0, allow_nan=False)
HALF_CIRCUMFERENCE = math.pi * 6_371_000.0
# The flat-Earth helper does not wrap the longitude: near a pole or the antimeridian a 50 km move
# leaves [-180, 180] (hypothesis found lat0=86.6, lon0=173.2, east=44488.5); very close to a pole a
# move north can also give a latitude above 90 (e.g. lat0=89.6, north=49751). Its documented domain:
LAT_FLAT = st.floats(min_value=-80.0, max_value=80.0, allow_nan=False)
LON_FLAT = st.floats(min_value=-170.0, max_value=170.0, allow_nan=False)


@settings(deadline=None)
@given(LAT, LON, LAT, LON)
def test_distance_is_never_negative_nor_longer_than_half_the_earth(lat1, lon1, lat2, lon2):
    d = haversine_m(lat1, lon1, lat2, lon2)
    assert 0.0 <= d <= HALF_CIRCUMFERENCE + 1e-6


@settings(deadline=None)
@given(LAT, LON, LAT, LON)
def test_distance_is_symmetric(lat1, lon1, lat2, lon2):
    assert haversine_m(lat1, lon1, lat2, lon2) == pytest.approx(haversine_m(lat2, lon2, lat1, lon1), abs=1e-6)


@settings(deadline=None)
@given(LAT, LON, LAT, LON, LAT, LON)
def test_triangle_inequality(la, oa, lb, ob, lc, oc):
    assert haversine_m(la, oa, lc, oc) <= haversine_m(la, oa, lb, ob) + haversine_m(lb, ob, lc, oc) + 1e-6


@settings(deadline=None)
@given(LAT_FLAT, LON, OFFSET, OFFSET)
def test_flat_round_trip(lat0, lon0, north, east):
    n, e = latlon_to_offset(lat0, lon0, *offset_to_latlon(lat0, lon0, north, east))
    assert n == pytest.approx(north, abs=1e-6)
    assert e == pytest.approx(east, abs=1e-6)


@settings(deadline=None)
@given(LAT_FLAT, LON_FLAT, OFFSET, OFFSET)
def test_a_small_move_stays_valid(lat0, lon0, north, east):
    assume(is_valid_position(lat0, lon0))
    lat, lon = offset_to_latlon(lat0, lon0, north, east)
    assume(not (lat == 0.0 and lon == 0.0))          # landing exactly on Null Island: not this test's subject
    assert is_valid_position(lat, lon)
