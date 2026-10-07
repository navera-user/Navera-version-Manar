"""Tests for geo_tools.py — run them with:   python3 -m pytest -v test_geo_tools.py

Each test is a function whose name starts with test_. Inside, `assert` what must be true.
Compare decimal numbers with pytest.approx(expected, abs=...) — never with == .
"""
import math

import pytest

from geo_tools import haversine_m, is_valid_position, meters_to_degrees, speed_mps


# ---------- an example, already written ----------

def test_distance_from_a_point_to_itself_is_zero():
    assert haversine_m(35.8256, 10.6084, 35.8256, 10.6084) == pytest.approx(0.0, abs=1e-6)


# ---------- TODO 1: haversine_m ----------
# Write at least 2 more tests. Ideas: one degree of latitude is about 111 195 m (on the same
# longitude); the distance A->B equals the distance B->A; a known distance from lesson 6.


# ---------- TODO 2: meters_to_degrees ----------
# Write at least 2 tests. Ideas: 111 195 m north is about 1 degree of latitude; at latitude 60°,
# 111 195 m east is about 2 degrees of longitude (cos 60° = 0.5); a move north does not change
# the longitude.


# ---------- TODO 3: is_valid_position ----------
# Write tests for: a normal position (True), (0, 0) (False), a latitude of 91 (False),
# a longitude of 181 (False), math.nan (False).


# ---------- TODO 4: speed_mps ----------
# Write tests for: 100 m in 20 s is 5 m/s; dt = 0 gives None (`assert speed_mps(...) is None`).
