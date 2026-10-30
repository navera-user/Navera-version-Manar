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


# ======== TODO 5 — four more properties (lab Step 3) ====================================================
# a) symmetry: the distance from A to B is the distance from B to A.
# b) triangle inequality: going from A to C through B is never shorter than going straight.
# c) round trip: enu_flat(lat0, lon0, *offset(lat0, lon0, e, n)) gives back (e, n), to 1e-6 m.
# d) validity: from a valid start, offset(...) is a valid position (is_finite_latlon).
#    Write d) FIRST on the whole Earth (LAT, LON) with @settings(deadline=None, max_examples=2000), run it,
#    and copy its Falsifying example into answers.py. Only THEN restrict the domain (lab Step 3).
# Every property gets @settings(deadline=None).
