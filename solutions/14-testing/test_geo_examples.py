"""test_geo_examples.py — example tests of NAVERA Lite's geo.py and guard.py (mission 14: TODO 1–4, then 6b).

    python3 -m pytest -v test_geo_examples.py

Three rules (lesson §2; ✔ Check my work enforces them):
  1. Every test passes on the stack as given (navera_lite/ unchanged).
  2. Expected values are computed independently — from a docstring, by hand, or with R_M and M_PER_DEG
     below — never with the function under test.
  3. Test through inputs and outputs only: no reading of files or of source code.
"""
import math

import pytest

from navera_lite.estimate import Estimate
from navera_lite.geo import bearing_deg, enu_flat, great_circle_points, haversine_m, is_finite_latlon, offset
from navera_lite.guard import JumpGate, gate_ok
from navera_lite.settings import DEFAULTS

R_M = 6_371_000.0                      # the sphere of mission 06, written here AGAIN on purpose (rule 2)
M_PER_DEG = math.pi * R_M / 180.0      # 111 194.93 m: one degree of any great circle (a meridian, the equator)


# ---------- fixtures: values prepared for every test that names them as an argument ----------

@pytest.fixture
def quito():
    """A point 20 km south of the equator, in Ecuador (lat, lon in degrees)."""
    return (-0.1807, -78.4678)


@pytest.fixture
def gate():
    """A new jump gate with the stack's settings: max_speed_mps 100.0, gps_jump_margin_m 50.0."""
    return JumpGate(DEFAULTS)


def gps(e_m, t_s, start=(35.8256, 10.6084)):
    """A GPS Estimate e_m metres east of `start` (a helper, not a test), measured at t_s seconds."""
    lat, lon = offset(start[0], start[1], e_m, 0.0)
    return Estimate("gps", lat, lon, t_s)


# ---------- examples, already written (lesson §2) ----------

@pytest.mark.parametrize("dlat, dlon, expected", [
    (0.01, 0.0, 0.0),        # north
    (0.0, 0.01, 90.0),       # east
    (-0.01, 0.0, 180.0),     # south
    (0.0, -0.01, 270.0),     # west
])
def test_bearing_of_the_four_cardinal_directions(quito, dlat, dlon, expected):
    lat, lon = quito
    # 0.01 degree of tolerance: 100 times finer than a wrong quadrant or a swapped east/north
    assert bearing_deg(lat, lon, lat + dlat, lon + dlon) == pytest.approx(expected, abs=0.01)


def test_a_point_is_at_zero_metres_from_itself(quito):
    assert haversine_m(*quito, *quito) == 0.0


# ======== TODO 1 — haversine_m ===========================================================================
def test_one_degree_along_a_meridian():
    # along a meridian the arc IS a great circle: rounding only (1e-9 relative is far below any real bug)
    assert haversine_m(10.0, 20.0, 11.0, 20.0) == pytest.approx(M_PER_DEG, rel=1e-9)


def test_one_degree_of_longitude_at_60_degrees():
    # along the 60° parallel the arc is M_PER_DEG × cos 60° = 55 597.46 m; the great circle is 0.5 m shorter
    # (1e-5 relative), so rel=1e-3: it passes on correct code and still catches a missing cos (factor 2)
    assert haversine_m(60.0, 5.0, 60.0, 6.0) == pytest.approx(M_PER_DEG * 0.5, rel=1e-3)


def test_london_to_paris(london=(51.5074, -0.1278), paris=(48.8566, 2.3522)):
    # the docstring's value (343 556.1 m): a diagonal move, latitudes AND longitudes differ
    assert haversine_m(*london, *paris) == pytest.approx(343_556.1, abs=1.0)


def test_quarter_of_the_equator():
    assert haversine_m(0.0, 0.0, 0.0, 90.0) == pytest.approx(90 * M_PER_DEG, rel=1e-9)


# ======== TODO 2 — is_finite_latlon =====================================================================
@pytest.mark.parametrize("lat, lon, ok", [
    (-0.1807, -78.4678, True),     # Quito
    (90.0, 180.0, True),           # the limits are valid
    (-90.0, -180.0, True),
    (0.0, 0.0, False),             # Null Island
    (0.0, 1e-9, True),             # next to it: valid
    (90.1, 10.0, False),           # latitude too big
    (-90.1, 10.0, False),
    (10.0, 180.1, False),          # longitude too big
    (10.0, -180.1, False),
    (math.nan, 10.0, False),       # not finite
    (10.0, math.inf, False),
    (None, 10.0, False),           # not numbers at all
    ("35.8", 10.6, False),
])
def test_is_finite_latlon(lat, lon, ok):
    assert is_finite_latlon(lat, lon) is ok


# ======== TODO 3 — offset, enu_flat, great_circle_points =================================================
def test_a_move_north_changes_only_the_latitude(quito):
    lat, lon = offset(*quito, 0.0, M_PER_DEG)
    assert lat == pytest.approx(quito[0] + 1.0, abs=1e-9)
    assert lon == pytest.approx(quito[1], abs=1e-12)


def test_a_move_east_at_60_degrees_is_two_degrees():
    # cos 60° = 0.5: M_PER_DEG metres east are 2 degrees of longitude there (the mean latitude stays 60°)
    lat, lon = offset(60.0, 10.0, M_PER_DEG, 0.0)
    assert lat == pytest.approx(60.0, abs=1e-12)
    assert lon == pytest.approx(12.0, abs=1e-9)


def test_enu_flat_of_a_point_placed_by_hand():
    # 0.01° north and 0.02° east of (45, 7): north 0.01 × M_PER_DEG, east 0.02 × M_PER_DEG × cos(45.005°)
    e, n = enu_flat(45.0, 7.0, 45.01, 7.02)
    assert n == pytest.approx(0.01 * M_PER_DEG, abs=1e-6)
    assert e == pytest.approx(0.02 * M_PER_DEG * math.cos(math.radians(45.005)), abs=1e-6)


def test_enu_flat_takes_the_short_way_across_the_date_line():
    e, n = enu_flat(-17.0, 179.95, -17.0, -179.95)          # 0.1° east, not 359.9° west
    assert e == pytest.approx(0.1 * M_PER_DEG * math.cos(math.radians(17.0)), rel=1e-6)


def test_offset_crosses_the_date_line():
    lat, lon = offset(-17.0, 179.99, 5000.0, 0.0)          # Fiji: 5 km east of 179.99°
    assert -180.0 <= lon < -179.9


def test_opposite_points_have_no_unique_path():
    with pytest.raises(ValueError):                           # the docstring: no unique shortest path
        great_circle_points((10.0, 20.0), (-10.0, -160.0), 3)


# ======== TODO 4 — the jump gate ========================================================================
@pytest.mark.parametrize("dist_m, elapsed_s, ok", [
    (150.0, 1.0, True),         # exactly the limit 100 × 1 + 50: accepted (≤)
    (150.1, 1.0, False),
    (250.0, 2.0, True),         # the gate grows with time
    (250.1, 2.0, False),
    (50.0, 0.0, True),          # no time: the margin alone
    (50.0, -3.0, True),         # a negative time counts as 0
    (60.0, -3.0, False),
])
def test_gate_ok_is_mission_01s_rule(dist_m, elapsed_s, ok):
    assert gate_ok((0.0, 0.0), (dist_m, 0.0), elapsed_s, 100.0, 50.0) is ok


def test_the_gate_measures_a_diagonal_jump_in_a_straight_line():
    # 100 m east AND 100 m north = 141.4 m (not 200 m): within 150 m after 1 s
    assert gate_ok((0.0, 0.0), (100.0, 100.0), 1.0, 100.0, 50.0) is True


def test_a_refused_fix_never_becomes_trusted(gate):
    assert gate.check(gps(0.0, 0.0))[0] is True
    assert gate.check(gps(500.0, 1.0))[0] is False           # 500 m > 150 m
    assert gate.check(gps(500.0, 2.0))[0] is False           # still judged from 0 m: 500 > 250
    assert gate.check(gps(500.0, 5.0))[0] is True            # 500 ≤ 550: accepted (lesson 1 table)
    assert gate.check(gps(900.0, 6.0))[0] is False           # 400 m from the new trusted fix > 150 m


# ======== TODO 6b — tests that kill my three mutants ====================================================
@pytest.mark.parametrize("lon", [180.5, -181.0, 359.0])
def test_longitudes_beyond_180_are_refused(lon):
    assert is_finite_latlon(10.0, lon) is False


def test_offset_brings_the_longitude_back():
    lat, lon = offset(10.0, 179.0, 300_000.0, 0.0)            # ~2.7° east of 179°
    assert -180.0 <= lon < 180.0
