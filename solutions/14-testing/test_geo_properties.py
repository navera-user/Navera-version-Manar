"""test_geo_properties.py — property tests of NAVERA Lite's geo.py with hypothesis (mission 14: TODO 5).

    python3 -m pytest -v test_geo_properties.py
    python3 -m pytest -q test_geo_properties.py --hypothesis-show-statistics

A property must hold for EVERY input of a domain; hypothesis generates the inputs (100 per test unless
you ask for more), and when one fails it shrinks it to a small "Falsifying example" (lesson §3).
The three rules of test_geo_examples.py apply here too.
"""
import math

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from navera_lite.geo import enu_flat, haversine_m, is_finite_latlon, offset

R_M = 6_371_000.0                                       # the sphere, written again (rule 2)

# strategies: how hypothesis draws numbers. With both limits given, NaN and infinity are never drawn.
LAT = st.floats(min_value=-90.0, max_value=90.0)        # every latitude
LON = st.floats(min_value=-180.0, max_value=180.0)      # every longitude
METRES = st.floats(min_value=-50_000.0, max_value=50_000.0)   # a move of up to 50 km, either way


# ---------- one property, already written (lesson §3) ----------

@settings(deadline=None)              # no time limit per example: the machine is shared
@given(LAT, LON, LAT, LON)
def test_a_distance_is_between_zero_and_half_the_earth(lat1, lon1, lat2, lon2):
    d = haversine_m(lat1, lon1, lat2, lon2)
    assert 0.0 <= d <= math.pi * R_M + 1e-6


# ======== TODO 5 — four more properties =================================================================
LAT_80 = st.floats(min_value=-80.0, max_value=80.0)     # the domain of the flat-Earth shortcut (lab Step 3)


@settings(deadline=None)
@given(LAT, LON, LAT, LON)
def test_distance_is_symmetric(lat1, lon1, lat2, lon2):
    assert haversine_m(lat1, lon1, lat2, lon2) == pytest.approx(haversine_m(lat2, lon2, lat1, lon1), abs=1e-6)


@settings(deadline=None)
@given(LAT, LON, LAT, LON, LAT, LON)
def test_triangle_inequality(lat1, lon1, lat2, lon2, lat3, lon3):
    straight = haversine_m(lat1, lon1, lat3, lon3)
    via_b = haversine_m(lat1, lon1, lat2, lon2) + haversine_m(lat2, lon2, lat3, lon3)
    assert straight <= via_b + 1e-6


@settings(deadline=None)
@given(LAT_80, LON, METRES, METRES)
def test_offset_then_enu_flat_gives_the_metres_back(lat0, lon0, e, n):
    assume(is_finite_latlon(lat0, lon0))
    assert enu_flat(lat0, lon0, *offset(lat0, lon0, e, n)) == pytest.approx((e, n), abs=1e-6)


# first version, on the whole Earth (LAT, max_examples=2000): Falsifying example
#     lat0=89.55257463757103, lon0=0.0, e=0.0, n=49751.430354205564   → latitude 90.0000…  past the pole
@settings(deadline=None)
@given(LAT_80, LON, METRES, METRES)
def test_a_move_from_a_valid_start_stays_valid(lat0, lon0, e, n):
    assume(is_finite_latlon(lat0, lon0))
    assert is_finite_latlon(*offset(lat0, lon0, e, n))
