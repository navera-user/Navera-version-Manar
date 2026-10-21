"""The gyro heading carry (day_pkg.gyro_heading) and its use by the day node's carry between fixes."""
import math
from types import MethodType, SimpleNamespace

import pytest

from day_pkg.gyro_heading import CourseReset, GyroHeading, heading_rate_dps
from day_pkg.nodes.day_subscriber import DaySubscriber
from navera_common.track import TrackVelocity

M_LAT = 1.0 / 111195.0
LAT0, LON0 = 35.8, 10.6


def _feed(g, t0, t1, rate_dps, hz=50.0):
    t = t0
    while t <= t1 + 1e-9:
        g.add_rate(t, rate_dps)
        t += 1.0 / hz


# ── GyroHeading ──────────────────────────────────────────────────────────────

def test_no_heading_before_a_vision_heading():
    g = GyroHeading()
    _feed(g, 0.0, 5.0, 2.0)
    assert g.at(3.0) is None


def test_integrates_the_rate_from_the_vision_heading_both_ways_in_time():
    g = GyroHeading()
    _feed(g, 0.0, 20.0, -3.0)                      # turning left 3 deg/s
    assert g.reset(10.0, 90.0)
    h, s = g.at(15.0)
    assert h == pytest.approx(75.0, abs=0.01)
    assert g.at(5.0)[0] == pytest.approx(105.0, abs=0.01)
    assert s > 2.0                                  # grown from the vision heading's 2 deg
    assert g.at(10.0)[1] == pytest.approx(2.0)


def test_wraps_through_north():
    g = GyroHeading()
    _feed(g, 0.0, 10.0, 5.0)
    g.reset(0.0, 350.0)
    assert g.at(4.0)[0] == pytest.approx(10.0, abs=0.01)


def test_the_carried_heading_ages_out():
    g = GyroHeading(bias_dps=0.1, noise_dps_rthz=0.02, reset_sigma_deg=2.0, max_sigma_deg=10.0)
    _feed(g, 0.0, 200.0, 0.0, hz=10.0)
    g.reset(0.0, 0.0)
    assert g.at(90.0) is not None                   # sqrt(4 + 81 + 0.036) = 9.2 deg
    assert g.at(110.0) is None                      # > 10 deg: no heading, the carry goes straight on


def test_outside_the_samples_or_across_a_gap_there_is_no_heading():
    g = GyroHeading(max_gap_s=0.5)
    _feed(g, 0.0, 10.0, 1.0)
    _feed(g, 12.0, 20.0, 1.0)                       # 2 s without samples
    g.reset(5.0, 0.0)
    assert g.at(9.0) is not None
    assert g.at(15.0) is None                       # the turn in the gap is unknown
    assert g.at(20.3) is None                       # the vision heading's interval holds the gap too
    g.reset(13.0, 0.0)
    assert g.at(20.3)[0] == pytest.approx(7.3, abs=0.05)   # a little past the last sample: extrapolated
    assert g.at(21.0) is None                       # too far past it


def test_a_vision_heading_far_from_a_valid_carried_one_is_not_taken():
    """A wrong-place match has a meaningless rotation: it must not restart the heading."""
    g = GyroHeading()
    _feed(g, 0.0, 10.0, 0.0)
    assert g.reset(0.0, 40.0)
    assert not g.reset(5.0, 120.0)                  # 80 deg off a heading known to ~2 deg
    assert g.at(5.0)[0] == pytest.approx(40.0)
    assert g.reset(5.0, 43.0)                       # within 3 sigma: taken
    assert g.at(5.0)[0] == pytest.approx(43.0)


def test_once_aged_out_any_vision_heading_is_taken():
    g = GyroHeading(max_sigma_deg=5.0)
    _feed(g, 0.0, 100.0, 0.0, hz=10.0)
    g.reset(0.0, 40.0)
    assert g.at(60.0) is None
    assert g.reset(60.0, 200.0)
    assert g.at(61.0)[0] == pytest.approx(200.0)


def test_clear_and_a_clock_stepping_back_forget_the_heading():
    g = GyroHeading()
    _feed(g, 100.0, 110.0, 0.0)
    g.reset(105.0, 10.0)
    g.clear()
    assert g.at(106.0) is None
    g.reset(105.0, 10.0)
    g.add_rate(50.0, 0.0)                           # clock stepped back
    assert g.at(105.0) is None


def test_heading_rate_from_an_imu_sample():
    # ENU, z up: +z rate turns left (counter-clockwise), the heading (clockwise) decreases
    assert heading_rate_dps((0.0, 0.0, math.radians(10.0))) == pytest.approx(-10.0)
    assert heading_rate_dps((0.0, 0.0, -math.radians(4.0)), (0.0, 0.0, 0.0, 1.0)) == pytest.approx(4.0)
    # rolled 90 deg about x: the body y axis is the vertical, a body y rate is the turn
    s = math.sqrt(0.5)
    q = (s, 0.0, 0.0, s)
    assert heading_rate_dps((0.0, math.radians(6.0), 0.0), q) == pytest.approx(-6.0, abs=1e-9)
    assert heading_rate_dps((0.0, 0.0, math.radians(6.0)), q) == pytest.approx(0.0, abs=1e-9)
    # the yaw (unreliable without a magnetometer) does not change it
    qy = (0.0, 0.0, math.sin(1.0), math.cos(1.0))
    assert heading_rate_dps((0.1, 0.2, 0.3), qy) == pytest.approx(-math.degrees(0.3))


# ── the day node's carry ─────────────────────────────────────────────────────

R_M, V = 900.0, 60.0                                # the screen bench's circuit: 900 m, 60 m/s


def _circle(t):
    """(lat, lon, heading_deg) on a left-hand circle started heading east at t = 0."""
    a = V / R_M * t
    e, n = R_M * math.sin(a), R_M * (1.0 - math.cos(a))
    return (LAT0 + n * M_LAT, LON0 + e * M_LAT / math.cos(math.radians(LAT0)),
            (90.0 - math.degrees(a)) % 360.0)


def _err(p, q):
    return math.hypot((p[0] - q[0]) / M_LAT, (p[1] - q[1]) / M_LAT * math.cos(math.radians(LAT0)))


def _node(gyro: bool):
    """A DaySubscriber with what the carry needs: 20 s of fixes on the circle every 0.5 s, the
    frames without attitude, and (gyro) the vision heading of the last fix carried by the gyro."""
    tr = TrackVelocity(accel_mps2=0.25)
    for k in range(41):
        t = 0.5 * k
        lat, lon, _ = _circle(t)
        tr.add(t, lat, lon, 5.0)
    n = SimpleNamespace(track=tr, _carry=None, _track_heading=None, _vel_epoch=None, gyro=None,
                        gyro_min_inliers=20)
    if gyro:
        n.gyro = GyroHeading()
        _feed(n.gyro, -1.0, 60.0, -math.degrees(V / R_M))
        n.gyro.reset(20.0, _circle(20.0)[2])
    n._heading_for_match = lambda meta: None
    n._frame_time = DaySubscriber._frame_time
    for f in ("_predicted", "_set_carry", "_keep_carry_velocity", "_carry_heading", "_velocity_heading",
              "_gyro_carry", "_gyro_reset"):
        setattr(n, f, MethodType(getattr(DaySubscriber, f), n))
    n.GYRO_STEP_S = DaySubscriber.GYRO_STEP_S
    return n


def _meta(t):
    return {"image_stamp_ns": int(t * 1e9)}


@pytest.mark.parametrize("gap", [2.0, 5.0, 10.0])
def test_a_gap_on_a_turn_is_carried_along_the_turn(gap):
    """60 m/s on a 900 m circle (3.8 deg/s): straight on along the fitted velocity (a 20 s chord,
    38 deg behind the heading) the carry is tens to hundreds of metres off; along the gyro heading,
    under 5 % of the distance flown (what is left: the chord's speed, ~7 % short on a 76 deg
    window) — and within the stated 3 sigma."""
    t = 20.0 + gap
    truth = _circle(t)
    off = _node(False)._predicted(_meta(t))
    on = _node(True)._predicted(_meta(t))
    assert _err(on, truth) < 0.25 * _err(off, truth)
    assert _err(on, truth) < 0.05 * V * gap
    assert _err(on, truth) < 3.0 * on[2]


def test_carried_frame_by_frame_like_at_once():
    n, once = _node(True), _node(True)._predicted(_meta(30.0))
    for k in range(1, 21):                          # a frame every 0.5 s, none matched
        t = 20.0 + 0.5 * k
        p = n._predicted(_meta(t))
        n._set_carry(p[0], p[1], t, _meta(t), p[2])
    assert _err(p, once) < 5.0
    assert _err(p, _circle(30.0)) < 0.05 * V * 10.0


def test_without_a_gyro_heading_the_carry_is_unchanged():
    n = _node(True)
    n.gyro.clear()                                  # no vision heading: as without the gyro
    assert n._predicted(_meta(25.0)) == _node(False)._predicted(_meta(25.0))


def test_the_aged_gyro_heading_falls_back_to_straight_on():
    n = _node(True)
    n.gyro.max_sigma = 2.5                           # ages out after ~15 s
    assert n._carry_heading(_meta(25.0))[1] > 0.0
    assert n._carry_heading(_meta(40.0)) == (None, 0.0)
    assert n._predicted(_meta(40.0)) == _node(False)._predicted(_meta(40.0))


def test_the_frame_attitude_has_priority_over_the_gyro():
    n = _node(True)
    n._heading_for_match = lambda meta: 123.0
    assert n._carry_heading(_meta(25.0)) == (123.0, 0.0)


def test_only_a_good_fix_restarts_the_gyro_heading():
    n = _node(True)
    h0 = n.gyro.at(21.0)[0]
    n._gyro_reset(21.0, {"rotation_deg": h0 + 1.0, "inliers": 12})        # weak: not taken
    assert n.gyro.at(21.0)[0] == pytest.approx(h0)
    n._gyro_reset(21.0, {"rotation_deg": h0 + 1.0, "inliers": 40})
    assert n.gyro.at(21.0)[0] == pytest.approx(h0 + 1.0)
    n._gyro_reset(21.0, {"rotation_deg": None, "inliers": 40})            # no rotation: nothing
    assert n.gyro.at(21.0)[0] == pytest.approx(h0 + 1.0)


# ── the GPS course reset (CourseReset) ───────────────────────────────────────

def _track(course_deg, speed, t0=0.0, t1=10.0, hz=5.0):
    """A History of GPS (lat, lon) on a straight line at this course and speed."""
    from navera_common.sensor_history import History
    h = History(maxlen=600, max_gap_s=1.5)
    k = 0
    while t0 + k / hz <= t1 + 1e-9:
        t = t0 + k / hz
        d = speed * t
        h.add(t, (LAT0 + d * math.cos(math.radians(course_deg)) * M_LAT,
                  LON0 + d * math.sin(math.radians(course_deg)) * M_LAT / math.cos(math.radians(LAT0))))
        k += 1
    return h


def test_course_resets_the_heading_from_the_mount_on_a_steady_fast_course():
    """12 m/s at 298 deg, camera mounted at yaw -92 (MARS-LVIG): the frame top is at 30 deg."""
    g = GyroHeading()
    _feed(g, 0.0, 10.0, 0.0)
    c = CourseReset()
    h, sig = c.maybe_reset(g, _track(298.0, 12.0), 10.0, -92.0)
    chord = math.degrees(math.atan2(math.sqrt(2.0) * 0.5, 24.0))         # 0.5 m GPS noise over 24 m
    assert h == pytest.approx(30.0, abs=0.01) and sig == pytest.approx(math.hypot(5.0, chord), abs=0.01)
    assert g.at(10.0)[0] == pytest.approx(30.0, abs=0.01)
    assert c.maybe_reset(g, _track(298.0, 12.0), 10.5, -92.0) is None      # once a second at most


@pytest.mark.parametrize("why", ["slow", "turning", "no mount", "no gyro"])
def test_no_course_reset_when_the_course_says_nothing(why):
    g = GyroHeading()
    _feed(g, 0.0, 10.0, 5.0 if why == "turning" else 0.0)
    track = _track(298.0, 3.0 if why == "slow" else 12.0)
    assert CourseReset().maybe_reset(None if why == "no gyro" else g, track, 10.0,
                                     None if why == "no mount" else -92.0) is None
    assert g.at(10.0) is None


def test_the_offset_is_learned_from_vision_and_replaces_the_mount():
    c = CourseReset()
    for off in (88.0, 90.0, 92.0):                     # vision: frame top - course
        c.add_offset_sample(100.0 + off, 100.0)
    mean, sig = c.offset(-50.0)                        # the mount (wrong here) is not used any more
    assert mean == pytest.approx(90.0, abs=0.01) and sig == pytest.approx(2.0)
    assert CourseReset().offset(-92.0) == (92.0, 5.0) and CourseReset().offset(None) is None


def test_a_fresher_vision_heading_is_not_replaced_by_the_course():
    g = GyroHeading()
    _feed(g, 0.0, 10.0, 0.0)
    g.reset(9.5, 31.0, 2.0)                            # vision, 2 deg
    assert CourseReset().maybe_reset(g, _track(298.0, 12.0), 10.0, -92.0) is None
    assert g.at(10.0)[0] == pytest.approx(31.0)


def test_match_heading_is_the_attitude_else_the_gyro_with_its_tolerance():
    n = SimpleNamespace(local_heading_tol_deg=20.0, gyro=GyroHeading(max_sigma_deg=30.0))
    n._frame_time = DaySubscriber._frame_time
    n._heading_for_match = lambda meta: None
    kw = MethodType(DaySubscriber._match_heading_kw, n)
    assert kw(_meta(5.0)) == {"heading_deg": None, "heading_tol_deg": 20.0}      # nothing known
    _feed(n.gyro, 0.0, 10.0, 0.0)
    n.gyro.reset(5.0, 30.0, 9.0)
    assert kw(_meta(5.0)) == {"heading_deg": pytest.approx(30.0), "heading_tol_deg": pytest.approx(27.0)}
    n._heading_for_match = lambda meta: 123.0
    assert kw(_meta(5.0)) == {"heading_deg": 123.0, "heading_tol_deg": 20.0}     # the attitude first


def test_a_gps_check_fix_teaches_the_course_offset():
    n = _node(True)
    n.course = CourseReset()
    n._gps_hist = _track(90.0, 12.0, 0.0, 30.0)
    n._gps_prior = SimpleNamespace(fresh=lambda: (LAT0, LON0))
    g = GyroHeading()
    _feed(g, 0.0, 30.0, 0.0)
    n.gyro = g
    for t in (10.0, 12.0, 14.0):
        n._gyro_reset(t, {"rotation_deg": 182.0, "inliers": 40})
    assert n.course.offset(None) == (pytest.approx(92.0, abs=0.01), 2.0)
