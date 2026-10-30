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


# ======== TODO 1 — haversine_m: at least 3 tests ========================================================
# Done when: haversine_m is compared with distances you computed independently (M_PER_DEG, lesson §2), in
# METRES, with a tolerance you justify in a comment; at least one move along a meridian (north–south) and
# one along a parallel (east–west) away from the equator.


# ======== TODO 2 — is_finite_latlon: ONE parametrized test, at least 8 cases ============================
# Done when: each rule of its docstring is broken ALONE in at least one case (→ False); good positions,
# the limits themselves included, give True; inputs that are not numbers at all give False instead of a
# crash. Compare with `is True` / `is False`.


# ======== TODO 3 — offset, enu_flat, great_circle_points: at least 4 tests ==============================
# Done when: a move north changes only the latitude, by the right amount; a move east far from the equator
# has the right size in degrees; enu_flat gives back the metres of a point you placed by hand; the ±180°
# meridian behaves as offset's docstring says; and great_circle_points refuses what its docstring says it
# refuses (pytest.raises, lesson §2).


# ======== TODO 4 — the jump gate: at least 3 tests ======================================================
# Done when: gate_ok and JumpGate do what their docstrings and mission 01 say. Their docstrings are your
# specification.


# ======== TODO 6b (lab Step 5) — tests that kill YOUR three mutants of my_mutants.py ====================
