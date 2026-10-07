"""Tests for a function of the REAL product: navera_common/geo.py in your NAVERA copy.

    python3 -m pytest -v test_navera_geo.py

NAVERA already has its own tests (navera_common/test/test_geo.py). Here you write YOURS, as if you
were the engineer who has to make sure nobody breaks these two functions.
"""
import math

import pytest

from navera_common.geo import haversine_m, is_finite_latlon


# TODO 5: write at least 3 tests:
#   - is_finite_latlon accepts a normal position (Sousse) and refuses (0, 0)
#   - is_finite_latlon refuses NaN and None (yes: None — read the function!)
#   - haversine_m gives about 111 195 m for 1 degree of latitude
