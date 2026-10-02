"""Velocity from measured fixes, and dead-reckoning with an honest, growing uncertainty."""
import math

import pytest

from navera_common.geo import haversine_m
from navera_common.track import TrackVelocity

M_LAT = 1.0 / 111195.0


def fixes(tr, ve=10.0, vn=5.0, n=10, dt=1.0, noise=None):
    lon_m = M_LAT / math.cos(math.radians(35.8))
    for i in range(n):
        e = noise[i] if noise else (0.0, 0.0)
        tr.add(i * dt, 35.8 + (vn * i * dt + e[1]) * M_LAT, 10.6 + (ve * i * dt + e[0]) * lon_m, 3.0)


def test_velocity_of_a_straight_track():
    tr = TrackVelocity()
    fixes(tr)
    ve, vn, sig = tr.velocity(9.0)
    assert (ve, vn) == (pytest.approx(10.0, abs=0.05), pytest.approx(5.0, abs=0.05))
    assert 0.5 <= sig < 2.0


def test_dead_reckoning_follows_the_track_and_states_a_growing_error():
    tr = TrackVelocity()
    fixes(tr)
    lat, lon, sig = tr.propagate(39.0)                      # 30 s after the last fix
    truth = (35.8 + 5.0 * 39 * M_LAT, 10.6 + 10.0 * 39 * M_LAT / math.cos(math.radians(35.8)))
    assert haversine_m(lat, lon, *truth) < 3.0
    assert sig > tr.propagate(19.0)[2] > 3.0               # grows with time


def test_a_turn_measured_by_the_imu_turns_the_velocity():
    tr = TrackVelocity()
    fixes(tr, ve=0.0, vn=10.0)                              # flying north
    lat, lon, _ = tr.propagate(19.0, heading_change_deg=90.0)   # then turned to the east
    north = (lat - (35.8 + 90 * M_LAT)) / M_LAT
    east = (lon - 10.6) / (M_LAT / math.cos(math.radians(35.8)))
    assert north == pytest.approx(0.0, abs=1.0) and east == pytest.approx(100.0, abs=1.0)


def test_too_few_or_too_short_gives_nothing():
    tr = TrackVelocity()
    fixes(tr, n=2)
    assert tr.propagate(5.0) is None
    tr = TrackVelocity()
    fixes(tr, n=5, dt=0.5)                                  # 2 s span < 4 s
    assert tr.propagate(5.0) is None


def test_a_noisy_track_states_a_larger_speed_error():
    clean, noisy = TrackVelocity(), TrackVelocity()
    fixes(clean)
    fixes(noisy, noise=[(30.0 * (-1) ** i, -20.0 * (-1) ** i) for i in range(10)])
    assert noisy.velocity(9.0)[2] > 3 * clean.velocity(9.0)[2]
