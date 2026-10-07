"""Property-based tests for geo_tools.py with hypothesis — run them with:

    python3 -m pytest -v test_properties.py

Instead of choosing examples, you state a PROPERTY that must hold for ALL inputs of a domain;
hypothesis generates many inputs (100 by default), and when one fails it SHRINKS it to a minimal
counterexample, printed as "Falsifying example: ...".
"""
import math

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from geo_tools import haversine_m, is_valid_position, latlon_to_offset, offset_to_latlon

LAT = st.floats(min_value=-90.0, max_value=90.0, allow_nan=False)
LON = st.floats(min_value=-180.0, max_value=180.0, allow_nan=False)
OFFSET = st.floats(min_value=-50_000.0, max_value=50_000.0, allow_nan=False)   # metres
HALF_CIRCUMFERENCE = math.pi * 6_371_000.0


# ---------- an example property, already written ----------

@settings(deadline=None)          # no time limit per example: the Jetson may be busy
@given(LAT, LON, LAT, LON)
def test_distance_is_never_negative_nor_longer_than_half_the_earth(lat1, lon1, lat2, lon2):
    d = haversine_m(lat1, lon1, lat2, lon2)
    assert 0.0 <= d <= HALF_CIRCUMFERENCE + 1e-6


# ---------- TODO 5: at least 4 more properties ----------
# a) SYMMETRY: the distance from A to B equals the distance from B to A (pytest.approx, abs=1e-6).
# b) TRIANGLE INEQUALITY: d(A, C) <= d(A, B) + d(B, C) + 1e-6.
# c) VALIDITY: from a valid start (use hypothesis.assume(is_valid_position(lat0, lon0))), a move of
#    OFFSET metres north and east gives a valid position (is_valid_position). Write it FIRST with
#    LAT and LON (the whole Earth) and @settings(deadline=None, max_examples=2000): read the
#    "Falsifying example" (lab, step 8). Then restrict lat0 to [-80, 80] and lon0 to [-170, 170].
# d) ROUND TRIP: latlon_to_offset(lat0, lon0, *offset_to_latlon(lat0, lon0, north, east)) gives back
#    (north, east) within 1e-6 m, on the restricted domain.
