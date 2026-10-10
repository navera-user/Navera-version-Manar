"""Example-based tests for geo_tools.py — run them with:   python3 -m pytest -v test_geo_tools.py

A test is a function whose name starts with test_. Inside, `assert` what must be true.
Compare decimals with pytest.approx(expected, abs=... or rel=...), exact values with `is` / `==`.
"""
import math

import pytest

from geo_tools import (haversine_m, is_valid_position, latlon_to_offset, meters_to_degrees,
                       offset_to_latlon, speed_mps)

M_PER_DEG = 2 * math.pi * 6_371_000.0 / 360.0      # 111 195 m: an INDEPENDENT expected value


# ---------- a fixture: a value prepared for any test that asks for it by name ----------

@pytest.fixture
def london():
    """Near Big Ben, London."""
    return (51.5007, -0.1246)


# ---------- examples, already written ----------

def test_distance_from_a_point_to_itself_is_zero(london):
    assert haversine_m(*london, *london) == pytest.approx(0.0, abs=1e-6)


@pytest.mark.parametrize("dt", [0.0, -1.0])
def test_speed_without_time_is_none(dt):
    assert speed_mps(100.0, dt) is None


# ---------- TODO 1: haversine_m (at least 3 tests) ----------
# Ideas: one degree of latitude along a meridian is M_PER_DEG metres; one degree of longitude on
# the equator too, and at 60° about half (cos 60° = 0.5); a known distance from lesson 06.
# Tolerance at 60°: haversine_m gives the GREAT-CIRCLE distance (55 596.93 m), a little shorter than
# half of M_PER_DEG measured ALONG the 60° parallel (55 597.46 m): a 1e-5 relative gap. So use
# rel=1e-3 there (rel=1e-6 fails on correct code); it still catches the factor-2 bug (missing cos).


# ---------- TODO 2: meters_to_degrees and offset_to_latlon (at least 3 tests) ----------
# Ideas: M_PER_DEG metres north is 1 degree of latitude AND 0 of longitude; at latitude 60°,
# M_PER_DEG metres east is 2 degrees of longitude; a move north does not change the longitude.


# ---------- TODO 3: is_valid_position (one parametrized test with at least 6 cases) ----------
# Use @pytest.mark.parametrize("lat, lon, ok", [...]) with valid AND invalid positions:
# London (True), (0, 0), latitude 91 and -91, longitude 181, math.nan, math.inf (False).


# ---------- TODO 4: speed_mps (at least 2 more tests) ----------
# Ideas: 100 m in 20 s is 5 m/s; 0 m in 10 s is 0 m/s (and not None!).
