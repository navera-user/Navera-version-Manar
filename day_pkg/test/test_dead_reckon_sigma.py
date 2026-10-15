"""The stated uncertainty of the day pipeline's dead-reckoned position (carried once a second)."""
import math
from types import MethodType, SimpleNamespace

import pytest

from day_pkg.nodes.day_subscriber import DaySubscriber
from navera_common.track import TrackVelocity

M_LAT = 1.0 / 111195.0


def _node():
    """A DaySubscriber with only what the carry needs (no ROS node, no models)."""
    tr = TrackVelocity(accel_mps2=0.5)
    lon_m = M_LAT / math.cos(math.radians(35.8))
    for i in range(10):                                    # measured fixes, 10 m/s east, t = 1000..1009
        tr.add(1000.0 + i, 35.8, 10.6 + 10.0 * i * lon_m, 30.0)
    n = SimpleNamespace(track=tr, _carry=None, _track_heading=None, _vel_epoch=None)
    n._heading_for_match = lambda meta: None
    n._frame_time = DaySubscriber._frame_time
    n._predicted = MethodType(DaySubscriber._predicted, n)
    n._set_carry = MethodType(DaySubscriber._set_carry, n)
    n._keep_carry_velocity = MethodType(DaySubscriber._keep_carry_velocity, n)
    return n


def _carry_for(n, seconds):
    """Carry once a second from the last fix (t = 1009) for `seconds`; the last (lat, lon, sigma)."""
    p = None
    for k in range(1, seconds + 1):
        t = 1009.0 + k
        meta = {"image_stamp_ns": int(t * 1e9)}
        p = n._predicted(meta)
        n._set_carry(p[0], p[1], t, meta, p[2])
    return p


@pytest.mark.parametrize("seconds", [10, 40, 99])
def test_carried_once_a_second_states_the_same_as_carried_at_once(seconds):
    stepped = _carry_for(_node(), seconds)
    n = _node()
    once = n.track.propagate(1009.0 + seconds)
    assert stepped[2] == pytest.approx(once[2], rel=0.02)


def test_the_stated_error_covers_a_vehicle_that_keeps_accelerating_unseen():
    """Simulator 2026-10-15: after 99 s the carried position was 1205 m off, stated +-244 m.
    A vehicle gaining 0.5 m/s2 unseen is 1/2 a t^2 = 2450 m off after 99 s: stated, not hidden."""
    assert _carry_for(_node(), 99)[2] > 0.5 * 0.5 * 99 ** 2
    assert _carry_for(_node(), 40)[2] > 0.5 * 0.5 * 40 ** 2


def test_odometry_displacements_are_as_uncertain_as_the_frame_height():
    rel = DaySubscriber._odometry_rel_error
    assert rel({}) == 0.1
    assert rel({"altitude_m": 100.0, "altitude_sigma_m": 5.0}) == 0.1        # better than 10 %: 10 %
    assert rel({"altitude_m": 100.0, "altitude_sigma_m": 35.0}) == pytest.approx(0.35)
    assert rel({"altitude_m": 0.0, "altitude_sigma_m": 5.0}) == 0.1
    assert rel({"altitude_m": 100.0, "altitude_sigma_m": math.nan}) == 0.1


def test_odometry_is_not_added_to_a_position_older_than_the_previous_frame():
    cont = DaySubscriber._odometry_continues
    vo = (12.0, 0.0, 1.0, 1.0)                      # 12 m east in 1 s
    assert cont(vo, 99.0, 100.0)                    # anchor = the previous frame: continues
    assert cont(vo, 101.5, 100.0)                   # a match published after the frame's instant
    assert not cont(vo, 97.0, 100.0)                # two frames in between published nothing
    assert not cont(vo, None, 100.0)


def _dr_node(emitted):
    """A node with what _dead_reckon needs; _emit_fix records (lat, lon, sigma, why)."""
    n = _node()
    n.max_dead_reckon_s, n.dr_max_sigma_m = 120.0, 500.0
    n._anchor_lat, n._anchor_lon, n._anchor_time = 35.8, 10.6 + 90.0 * M_LAT / math.cos(math.radians(35.8)), 1009.0
    n._dr_sigma, n._vo_step, n._dr_why = 30.0, None, ""
    n._odometry_continues = DaySubscriber._odometry_continues
    n._odometry_rel_error = DaySubscriber._odometry_rel_error
    n._emit_fix = lambda now, seq, lat, lon, meta, status, src, score, jump, reason=None: emitted.append(
        (lat, lon, n._dr_sigma, reason))
    n._dead_reckon = MethodType(DaySubscriber._dead_reckon, n)
    return n


def test_odometry_after_a_gap_does_not_leave_the_next_frame_without_a_position():
    """Simulator 2026-10-15: the carried position had no track point for > 5 s; the odometry point that
    came next was alone on the track (no velocity across a gap), the next frame without odometry had
    no velocity: no position for 19 s, then the autopilot's LAND. The carry keeps its velocity."""
    out = []
    n = _dr_node(out)
    for k in range(1, 9):                                  # 8 s carried, no odometry: no track point
        t = 1009.0 + k
        assert n._dead_reckon(None, k, {"image_stamp_ns": int(t * 1e9)}, {}, 0.0, "no match")
    assert n._carry is not None
    t = 1018.0                                             # odometry at last: 10 m east in 1 s
    n._vo_step = (10.0, 0.0, 1.0, 1.0)
    assert n._dead_reckon(None, 9, {"image_stamp_ns": int(t * 1e9)}, {}, 0.0, "no match")
    assert "odometry" in out[-1][3]
    assert n.track.velocity(t) is None                     # the track alone has none across the gap
    t = 1019.0                                             # the next frame: no odometry, no match
    assert n._dead_reckon(None, 10, {"image_stamp_ns": int(t * 1e9)}, {}, 0.0, "no match"), n._dr_why
    sig = [o[2] for o in out]
    assert sig == sorted(sig)                              # never a more precise position than before


def test_odometry_does_not_hide_frames_that_published_nothing():
    out = []
    n = _dr_node(out)
    n._anchor_time = 1005.0                                # the last published position: 4 s before
    n._vo_step = (10.0, 0.0, 1.0, 1.0)
    assert n._dead_reckon(None, 1, {"image_stamp_ns": int(1010.0 * 1e9)}, {}, 0.0, "no match")
    assert "odometry" not in out[-1][3] and "carried" in out[-1][3]


def test_a_match_after_a_gap_keeps_the_carry_velocity_and_the_accuracy_keeps_growing_from_its_age():
    """The same gap, ended by a map match instead of odometry: the match is alone on the track, the
    carry must keep going, and its accuracy must grow from when the velocity was measured (1009),
    not from the match: 1/2 a t^2 of 20 s, not of 0 s."""
    n = _node()
    for k in range(1, 11):                                 # 10 s carried
        t = 1009.0 + k
        p = n._predicted({"image_stamp_ns": int(t * 1e9)})
        n._set_carry(p[0], p[1], t, {}, p[2])
    t_vel, t_fix = n.track.last_time(), 1019.0
    n.track.add(t_fix, p[0], p[1], 30.0)                   # the match, 10 s after the last track point
    assert n.track.velocity(t_fix) is None
    n._keep_carry_velocity(p[0], p[1], t_fix, {}, 30.0, t_vel)
    assert n._carry is not None and n._vel_epoch == t_vel
    q = n._predicted({"image_stamp_ns": int(1029.0 * 1e9)})     # 10 s after the match
    assert q is not None
    # velocity measured at 1009: 20 s old at 1029 -> 1/2 a (20^2 - 10^2) = 75 m of the 1/2 a t^2 term
    assert q[2] > 30.0 + 0.5 * 0.5 * (20.0 ** 2 - 10.0 ** 2)


def test_a_match_on_a_track_that_gives_a_velocity_resets_the_carry():
    n = _node()
    p = n._predicted({"image_stamp_ns": int(1012.0 * 1e9)})
    n._set_carry(p[0], p[1], 1012.0, {}, p[2])
    assert n._carry is not None
    n.track.add(1013.0, p[0], p[1], 30.0)                  # 4 s after the last point: the track still has its velocity
    n._keep_carry_velocity(p[0], p[1], 1013.0, {}, 30.0, 1009.0)
    assert n._carry is None and n._vel_epoch is None
