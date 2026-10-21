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
    sum made 1/2 a dt per second — +-244 m stated, 1205 m real, after 99 s).
    """
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


def test_fit_time_is_the_fixes_weighted_mean_time_and_last_fix_the_latest():
    tr = TrackVelocity()
    assert tr.fit_time() is None and tr.last_fix() is None
    for i in range(11):                                   # 0..10 s, the last 5 twice as precise
        tr.add(100.0 + i, 35.8 + i * 1e-4, 10.6, 10.0 if i < 6 else 5.0)
    w = [1 / 100.0] * 6 + [1 / 25.0] * 5
    assert tr.fit_time() == pytest.approx(sum(wi * (100.0 + i) for i, wi in enumerate(w)) / sum(w))
    assert tr.last_fix() == (110.0, 35.8 + 10e-4, 10.6, 5.0)
    tr.add(120.0, 35.81, 10.6, 5.0)                       # after a 10 s gap: alone, no fit
    assert tr.fit_time() is None and tr.velocity(120.0) is None


def test_the_autopilot_velocity_needs_five_fixes_on_a_straight_line():
    tr = TrackVelocity()
    fixes(tr, n=4, dt=1.5)
    assert tr.autopilot_velocity(4.5) is None                      # too few (velocity() has one)
    assert tr.velocity(4.5) is not None
    tr = TrackVelocity()
    fixes(tr, n=8)
    ve, vn, sig = tr.autopilot_velocity(7.0)
    assert (ve, vn) == (pytest.approx(10.0, abs=0.05), pytest.approx(5.0, abs=0.05))
    # the fit's error (floored at 0.5 m/s) + unseen accel 0.5 x 3.5 s from the fit's mean time
    assert sig == pytest.approx(0.5 + 0.5 * 3.5, abs=0.01)
    assert tr.autopilot_velocity(9.0)[2] == pytest.approx(sig + 1.0)   # older: less sure


def test_a_turn_or_fixes_worse_than_stated_give_no_autopilot_velocity():
    tr = TrackVelocity()
    for i in range(10):                                           # 20 m/s on a 100 m circle
        a = 0.2 * i
        tr.add(float(i), 35.8 + 100.0 * math.sin(a) * M_LAT,
               10.6 + 100.0 * (1 - math.cos(a)) * M_LAT / math.cos(math.radians(35.8)), 3.0)
    assert tr.autopilot_velocity(9.0) is None and tr.velocity(9.0) is not None
    tr = TrackVelocity()
    fixes(tr, noise=[(30.0 * (-1) ** i, 0.0) for i in range(10)])  # +-30 m, stated 3 m
    assert tr.autopilot_velocity(9.0) is None


def test_the_autopilot_velocity_accuracy_is_honest_for_30_m_fixes():
    """1 Hz fixes stated and truly +-30 m: the 2D error is within 2.45 sigma (95 %) at least 95 %."""
    import random
    rng = random.Random(3)
    inside, n = 0, 400
    lon_m = M_LAT / math.cos(math.radians(35.8))
    for _ in range(n):
        tr = TrackVelocity()
        for i in range(8):
            tr.add(float(i), 35.8 + (5.0 * i + rng.gauss(0, 30.0)) * M_LAT,
                   10.6 + (-20.0 * i + rng.gauss(0, 30.0)) * lon_m, 30.0)
        v = tr.autopilot_velocity(7.0)
        if v is None:                                             # chi-square refusal: fine
            inside += 1
            continue
        inside += math.hypot(v[0] + 20.0, v[1] - 5.0) <= 2.45 * v[2]
    assert inside / n >= 0.95


def test_a_turn_the_chi_square_lets_through_widens_the_autopilot_velocity_sigma():
    """A plane at 22 m/s on a 300 m circle with +-30 m fixes: the line fit still passes, but the
    velocity now is far from the window's chord — the stated sigma must cover it."""
    def track(radius):
        tr = TrackVelocity()
        for i in range(10):
            a = 22.0 * i / radius if radius else 0.0
            n, e = (radius * math.sin(a), radius * (1 - math.cos(a))) if radius else (22.0 * i, 0.0)
            tr.add(float(i), 35.8 + n * M_LAT, 10.6 + e * M_LAT / math.cos(math.radians(35.8)), 30.0)
        return tr
    straight = track(0.0).autopilot_velocity(9.6)
    ve, vn, sig = track(300.0).autopilot_velocity(9.6)
    a = 22.0 * 9.6 / 300.0                                           # true heading now
    err = math.hypot(ve - 22.0 * math.sin(a), vn - 22.0 * math.cos(a))
    assert err > 5.0 and err <= 2.45 * sig and sig > straight[2] + 3.0
