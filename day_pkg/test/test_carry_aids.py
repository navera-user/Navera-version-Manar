"""open3 (2026-10-23): the carry's aids — the autopilot's velocity with a bias fitted on NAVERA's fixes, and
the IMU attitude's yaw across a restart (day_pkg.carry_aids, carry_state.carry_snap_aided).

Isaac Sim closed loop: a day node killed on a corner went straight on (745 m off, fin_endur_2h); the velocity
carried into a 60 s cloud bank right after a corner was 6-8 m/s off (outage60) while the autopilot's own was
0.5 m/s off; at 1200 m the carry kept the hover's velocity while the copter accelerated (h1200)."""
import math

import pytest

from day_pkg.carry_aids import AttitudeYaw, VelocityRef, carry_autopilot, yaw_of_quaternion
from day_pkg.carry_state import DrSnap, carry_snap_aided
from navera_common.track import TrackVelocity

LAT0, LON0 = 35.8685, 10.5352
M = 111320.0
K = math.cos(math.radians(LAT0))


def _ll(e, n):
    return LAT0 + n / M, LON0 + e / (M * K)


def _en(lat, lon):
    return (lon - LON0) * M * K, (lat - LAT0) * M


def corner_then_speedup(t):
    """Truth (e, n, ve, vn): north at 8 m/s, a 90 deg turn east over 4 s at t = 10 s, then speeding up
    2 m/s^2 from t = 20 s to 12 m/s (a copter starting its leg)."""
    if t <= 10.0:
        return 0.0, 8.0 * t, 0.0, 8.0
    if t <= 14.0:
        a = math.pi / 2 * (t - 10.0) / 4.0
        r = 8.0 * 4.0 / (math.pi / 2)
        return r * (1 - math.cos(a)), 80.0 + r * math.sin(a), 8.0 * math.sin(a), 8.0 * math.cos(a)
    r = 8.0 * 4.0 / (math.pi / 2)
    e0, n0 = r, 80.0 + r
    if t <= 20.0:
        return e0 + 8.0 * (t - 14.0), n0, 8.0, 0.0
    tau = min(t - 20.0, 2.0)
    e = e0 + 48.0 + 8.0 * tau + tau * tau + 12.0 * max(0.0, t - 22.0)
    return e, n0, 8.0 + 2.0 * tau, 0.0


def _apv(bias=(1.5, -1.0), t_end=60.0):
    apv = VelocityRef()
    t = 0.0
    while t <= t_end:
        _, _, ve, vn = corner_then_speedup(t)
        apv.add(1000.0 + t, ve + bias[0], vn + bias[1])
        t += 0.1
    return apv


def _fixes(t0, t1, sigma=15.0, step=0.5):
    pts, t = [], t0
    while t <= t1 + 1e-9:
        e, n, _, _ = corner_then_speedup(t)
        pts.append((1000.0 + t, *_ll(e, n), sigma))
        t += step
    return pts


def test_the_bias_is_fitted_through_a_corner_and_the_carry_follows_the_speed_up():
    apv = _apv()
    pts = _fixes(0.0, 18.0)                 # the corner inside the window
    b = apv.fit_bias(pts, 1018.0)
    assert b is not None
    assert b[0] == pytest.approx(-1.5, abs=0.3) and b[1] == pytest.approx(1.0, abs=0.3)
    # carried 30 s from the last fix (t = 18 s): through the speed-up the track never saw
    lat, lon, ve, vn, gap, _ = carry_autopilot(*pts[-1][1:3], 1018.0, 1048.0, apv, b)
    e, n, tve, tvn = corner_then_speedup(48.0)
    pe, pn = _en(lat, lon)
    assert math.hypot(pe - e, pn - n) < 15.0 and gap == 0.0
    assert math.hypot(ve - tve, vn - tvn) < 0.5
    # the plain carry (the track's velocity fit) goes on at the fitted chord: far off
    tr = TrackVelocity()
    for p in pts:
        tr.add(*p)
    pl = tr.propagate(1048.0)
    assert math.hypot(_en(pl[0], pl[1])[0] - e, _en(pl[0], pl[1])[1] - n) > 100.0


def test_an_autopilot_velocity_that_does_not_draw_the_fixes_is_refused():
    apv = VelocityRef()
    for i in range(300):                     # it says north 8 m/s, the fixes go east
        apv.add(1000.0 + 0.1 * i, 0.0, 8.0 if i < 150 else -8.0)
    pts = [(1000.0 + t, *_ll(8.0 * t, 0.0), 5.0) for t in range(0, 30)]
    assert apv.fit_bias(pts, 1029.0) is None


def test_no_samples_under_the_fixes_or_a_gap_gives_nothing():
    apv = VelocityRef()
    assert apv.fit_bias(_fixes(0.0, 18.0), 1018.0) is None
    for i in range(50):
        apv.add(1000.0 + 0.1 * i, 0.0, 8.0)
    for i in range(50):
        apv.add(1010.0 + 0.1 * i, 0.0, 8.0)  # 5 s without samples in between
    assert apv.disp(1001.0, 1012.0) is None and apv.disp(1001.0, 1004.0) is not None


def test_the_attitude_yaw_turn_across_a_restart_is_interpolated_with_its_gap():
    y = AttitudeYaw()
    assert y.seed(100.0, 350.0)
    for i in range(20):
        y.add(108.0 + 0.1 * i, (80.0 + i) % 360.0)          # 90 deg later after the gap, turning on
    turn, gap_s, gap_turn = y.turn(100.0, 109.9)
    assert turn == pytest.approx(109.0, abs=0.5)
    assert gap_s == pytest.approx(8.0, abs=0.01) and gap_turn == pytest.approx(90.0, abs=0.5)
    assert y.yaw(104.0) == pytest.approx(35.0, abs=0.5)      # interpolated across north


def test_yaw_of_a_quaternion_is_the_nose_azimuth():
    for hdg in (0.0, 45.0, 90.0, 200.0):
        psi = math.radians(90.0 - hdg)                         # ENU yaw of the nose
        q = (0.0, 0.0, math.sin(psi / 2), math.cos(psi / 2))
        assert yaw_of_quaternion(q) == pytest.approx(hdg % 360.0, abs=1e-6)
    assert yaw_of_quaternion((0.0, 0.0, 0.0, 0.0)) is None


def _restart_snap(yaw=0.0, be=None, bn=None, t=1010.0):
    e, n, ve, vn = corner_then_speedup(t - 1000.0)
    return DrSnap(*_ll(e, n), t, 12.0, ve, vn, 0.5, 1.0, t - 1.0, 0.0, yaw, be, bn)


def test_a_snapshot_on_a_corner_is_carried_round_it_by_the_attitude_yaw():
    """The kill at the corner (fin_endur_2h): 4 s without samples, the yaw then shows the turn."""
    snap = _restart_snap(yaw=0.0)                              # entering the corner, heading north
    y = AttitudeYaw()
    for i in range(160):                                       # samples from t = 14 s (the process up again)
        y.add(1014.0 + 0.1 * i, 90.0)
    tr = TrackVelocity(accel_mps2=0.25)
    c, how = carry_snap_aided(snap, 1028.0, tr, yaw=y)
    assert how == "attitude yaw"
    e, n, _, _ = corner_then_speedup(28.0)
    err = math.hypot(_en(c.lat, c.lon)[0] - e, _en(c.lat, c.lon)[1] - n)
    straight, _ = carry_snap_aided(snap, 1028.0, tr)
    err_straight = math.hypot(_en(straight.lat, straight.lon)[0] - e, _en(straight.lat, straight.lon)[1] - n)
    assert err < 30.0 and err < c.sigma and err_straight > 150.0
    assert c.ve == pytest.approx(8.0, abs=0.5) and abs(c.vn) < 0.5   # its velocity turned east


def test_a_snapshot_with_its_bias_follows_the_autopilot_velocity_across_a_restart_gap():
    apv = VelocityRef()
    for i in range(300):                                       # the restarted process hears from t = 15 s
        t = 15.0 + 0.1 * i
        _, _, ve, vn = corner_then_speedup(t)
        apv.add(1000.0 + t, ve + 1.5, vn - 1.0)
    snap = _restart_snap(be=-1.5, bn=1.0)
    c, how = carry_snap_aided(snap, 1040.0, TrackVelocity(accel_mps2=0.25), apv=apv)
    assert how == "autopilot velocity"
    e, n, _, _ = corner_then_speedup(40.0)
    err = math.hypot(_en(c.lat, c.lon)[0] - e, _en(c.lat, c.lon)[1] - n)
    assert err < 25.0 and err < c.sigma < 150.0
