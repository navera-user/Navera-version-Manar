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
    # turned at a constant rate over the 10 s: a quarter circle of 100 m, radius 63.7 m
    r = 100.0 / (math.pi / 2)
    assert north == pytest.approx(r, abs=1.0) and east == pytest.approx(r, abs=1.0)


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


def test_unseen_acceleration_is_in_the_stated_accuracy():
    tr = TrackVelocity(accel_mps2=0.5)
    fixes(tr)
    sig_10 = tr.propagate(19.0)[2]
    sig_37 = tr.propagate(46.0)[2]
    # the simulator's camera-failure run: true error 15 m at 10 s, 153 m at 37 s
    assert sig_10 > 15.0 and sig_37 > 153.0


def test_no_velocity_across_a_gap_and_the_turn_widens_the_sigma():
    tr = TrackVelocity()
    fixes(tr, ve=0.0, vn=10.0)                              # flying north, fixes 0..9 s
    lat, lon = 35.8 + 300 * M_LAT, 10.6                     # 20 s later, one fix further north
    tr.add(29.0, lat, lon, 5.0)
    assert tr.velocity(29.0) is None                        # one fix after the gap: no velocity yet
    tr2 = TrackVelocity()
    fixes(tr2, ve=0.0, vn=10.0)
    s0 = tr2.propagate(19.0)[2]
    assert tr2.propagate(19.0, heading_change_deg=90.0)[2] > s0 + 70.0


def test_a_position_carried_step_by_step_grows_like_one_carried_at_once():
    """day_subscriber carries the position once a second: the stated accuracy must grow with the
    time since the last MEASURED fix, not as a sum of per-step terms (simulator 2026-10-15: the
    sum made 1/2 a dt per second — +-244 m stated, 1205 m real, after 99 s)."""
    tr = TrackVelocity(accel_mps2=0.5)
    once = tr.sigma_growth(2.0, 15.0, 99.0, 0.0, 0.0)
    stepped, t = 0.0, 0.0
    for _ in range(99):
        stepped += tr.sigma_growth(2.0, 15.0, 1.0, t, 0.0)
        t += 1.0
    assert stepped == pytest.approx(once, rel=1e-9)
    assert once > 0.5 * 0.5 * 99.0 ** 2                   # the unseen-acceleration term alone: 2450 m


def test_propagate_is_the_one_shot_growth():
    tr = TrackVelocity()
    fixes(tr)
    s0 = tr._pts[-1][3]
    _, _, sig = tr.propagate(9.0 + 30.0)
    ve, vn, sig_v = tr.velocity(39.0)
    assert sig == pytest.approx(s0 + tr.sigma_growth(sig_v, math.hypot(ve, vn), 30.0), rel=1e-9)
