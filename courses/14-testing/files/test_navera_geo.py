"""Tests for the REAL product: navera_common/geo.py in your NAVERA copy.

    python3 -m pytest -v test_navera_geo.py

NAVERA already has its own tests (navera_common/test/test_geo.py). Here you write YOURS, as the engineer
who must make sure nobody breaks these functions. Compute expected values INDEPENDENTLY.
"""
import math

import pytest

from navera_common.geo import dead_reckon, haversine_m, is_finite_latlon

M_PER_DEG = 2 * math.pi * 6_371_000.0 / 360.0


# TODO 6: at least 4 tests:
#   - is_finite_latlon accepts London and refuses (0, 0), NaN, None and a latitude of 95
#   - haversine_m gives M_PER_DEG for 1 degree of latitude
#   - dead_reckon(lat, lon, heading 90, speed 10, dt 10) ends 100 m from the start (use haversine_m)
#     and further EAST; dead_reckon refuses (returns None) a negative speed or dt = 0
