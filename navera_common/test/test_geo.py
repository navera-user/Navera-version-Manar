"""Unit tests for navera_common.geo (dead-reckoning, position validity)."""
import math

import pytest

from navera_common.geo import dead_reckon, is_finite_latlon

R = 6_371_000.0


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


@pytest.mark.parametrize("heading, dlat_sign, dlon_sign", [
    (0.0, 1, 0), (90.0, 0, 1), (180.0, -1, 0), (270.0, 0, -1)])
def test_dead_reckon_direction_and_distance(heading, dlat_sign, dlon_sign):
    lat, lon = 35.83, 10.64
    out = dead_reckon(lat, lon, heading, 10.0, 10.0)          # 100 m
    assert out is not None
    assert haversine_m(lat, lon, *out) == pytest.approx(100.0, abs=0.01)
    if dlat_sign:
        assert math.copysign(1, out[0] - lat) == dlat_sign
    else:
        assert abs(out[0] - lat) < 1e-6
    if dlon_sign:
        assert math.copysign(1, out[1] - lon) == dlon_sign


def test_stationary_vehicle_does_not_move():
    # The old code floored every step at 120 m.
    out = dead_reckon(35.83, 10.64, 45.0, 0.0, 30.0)
    assert haversine_m(35.83, 10.64, *out) < 1e-6


@pytest.mark.parametrize("heading, speed, dt", [
    (None, 5.0, 1.0), (90.0, None, 1.0), (float("nan"), 5.0, 1.0),
    (90.0, float("inf"), 1.0), (90.0, -1.0, 1.0), (90.0, 5.0, 0.0), ("east", 5.0, 1.0)])
def test_unknown_motion_is_refused(heading, speed, dt):
    assert dead_reckon(35.83, 10.64, heading, speed, dt) is None


def test_invalid_start_is_refused():
    assert dead_reckon(float("nan"), 10.0, 0.0, 1.0, 1.0) is None
    assert dead_reckon(0.0, 0.0, 0.0, 1.0, 1.0) is None


def test_longitude_wraps_at_antimeridian():
    lat, lon = dead_reckon(0.5, 179.9999, 90.0, 100.0, 10.0)
    assert -180.0 <= lon < 180.0
    assert lon < 0.0


@pytest.mark.parametrize("lat, lon, ok", [
    (35.8, 10.6, True), (-89.9, -179.9, True), (0.0, 0.0, False),
    (float("nan"), 1.0, False), (91.0, 0.0, False), (0.0, 181.0, False),
    (None, 1.0, False), ("x", 1.0, False)])
def test_is_finite_latlon(lat, lon, ok):
    assert is_finite_latlon(lat, lon) is ok


def test_haversine():
    from navera_common.geo import haversine_m
    assert haversine_m(35.83, 10.64, 35.83, 10.64) == 0.0
    assert haversine_m(0.0, 0.0, 1.0, 0.0) == pytest.approx(111_195, rel=1e-4)
