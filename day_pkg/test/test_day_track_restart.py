"""B23 / F32 / endurance: the day node's carried position does not depend on the matching thread.

- a day node restarted alone in flight restores its track (state "day_track"): dead reckoning resumes at
  once with the uncertainty grown by the time elapsed (never a fresh fix) and the search circle stays
  small (hil_resil4: a 600 m restart circle, no match within the output's 10 s bridge, EKF failsafe);
- a stalled match (5.7 s in endur2) no longer silences the carried position: a watchdog in its own
  thread publishes the last output's snapshot carried to now, without touching the matching state;
- F32 h1200: GPS points read while a 10 s match held the node came in bursts timed at their arrival:
  no track velocity at the GPS loss, no position for 13 s, EKF failsafe 8 s after the cut. They are
  now read in their own thread, timed by their stamps, and the GPS snapshot bridges the handover.

The node is built by its own __init__ (shipped defaults) without a matcher, on a virtual clock
(navera_tools/bench/replay_sigma_isaac.py's harness), with a real state directory (tmp)."""
import importlib.util
import math
import os

import numpy as np
import pytest

from day_pkg.carry_state import DrSnap, carry_snap, restore_track, track_state, watchdog_carry
from navera_common.track import TrackVelocity
from navera_msgs.msg import PositionEstimate

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LAT0, LON0, V = 35.8685, 10.5352, 10.0           # flying north at 10 m/s
M = 111320.0


def _harness():
    spec = importlib.util.spec_from_file_location(
        "replay_sigma_isaac", os.path.join(ROOT, "navera_tools", "bench", "replay_sigma_isaac.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def env(tmp_path, monkeypatch):
    import rclpy
    from navera_common import state_store
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    R = _harness()
    owned = not rclpy.ok()
    if owned:
        rclpy.init(args=["--ros-args", "--log-level", "error"])
    nodes = []
    try:
        with R._patched() as ds:
            ds.state_store = state_store                # the real store, in tmp_path
            R.VClock.now = 1.8e9

            def make():
                n = R.make_node(ds)
                n.est = []
                n.pub_est = R._Pub(n.est.append)
                nodes.append(n)
                return n
            yield R, make
    finally:
        for n in nodes:
            n.destroy_node()
        if owned:
            rclpy.shutdown()


def _truth(t, t0):
    return LAT0 + V * (t - t0) / M, LON0


def _fly_measured(R, n, t0, seconds=10, sigma=8.0):
    """Measured fixes 1 Hz along the track, then one dead-reckoned output (snapshot + persisted)."""
    for i in range(seconds):
        lat, lon = _truth(t0 + i, t0)
        n.track.add(t0 + i, lat, lon, sigma)
    n._anchor_lat, n._anchor_lon = _truth(t0 + seconds - 1, t0)
    n._anchor_time = n._last_measured_time = t0 + seconds - 1
    n._dr_sigma = n._anchor_sigma = sigma
    R.VClock.now = t0 + seconds + 1
    meta = {"frame_id": 1, "image_stamp_ns": int((t0 + seconds + 1) * 1e9)}
    assert n._dead_reckon(n.get_clock().now().to_msg(), 1, meta, {}, 0.0, "test")
    return n.est[-1]


def _sigma(est):
    return math.sqrt(est.position_covariance[0])


def test_a_restarted_day_node_resumes_its_track_not_a_fresh_fix(env):
    R, make = env
    t0 = R.VClock.now
    a = make()
    a.track_persist, a._track_saved_at = True, 0.0
    before = _fly_measured(R, a, t0)
    a.destroy_node()
    R.VClock.now = t0 + 11 + 6.0                        # killed, respawned and ready 6 s later
    b = make()
    assert b.track.last_time() == pytest.approx(t0 + 9)  # the measured points, at their own times
    lat, lon, sig = b._predicted({})
    # carried at once, its uncertainty grown by the time elapsed (never the fix's own)
    assert sig > _sigma(before) + 1.0
    assert sig < 60.0
    tl = _truth(R.VClock.now, t0)
    assert math.hypot((lat - tl[0]) * M, (lon - tl[1]) * M * math.cos(math.radians(LAT0))) < 3.0 * sig
    # the search stays around the carry (k sigma), not the 600 m restart circle
    _, r = b._spatial_window(np.zeros((480, 640, 3), np.uint8), {"altitude_m": 250.0})
    assert r < 200.0
    # and dead reckoning is published by the first frame without a match
    assert b._dead_reckon(b.get_clock().now().to_msg(), 2, {"image_stamp_ns": int(R.VClock.now * 1e9)},
                          {}, 0.0, "no match")
    assert b.est[-1].mode == PositionEstimate.MODE_PROPAGATED and b.est[-1].valid


def test_a_stale_or_rewound_track_is_not_restored(env):
    R, make = env
    t0 = R.VClock.now
    a = make()
    a.track_persist, a._track_saved_at = True, 0.0
    _fly_measured(R, a, t0)
    R.VClock.now = t0 + 11 + a.max_dead_reckon_s + 5   # past the dead-reckoning limit
    assert make().track.last_time() is None
    R.VClock.now = t0 + 12
    a.on_start_cmd(type("B", (), {"data": False})())    # mission rewind: forgotten
    assert make().track.last_time() is None


def test_the_watchdog_publishes_while_a_match_is_stalled(env):
    R, make = env
    t0 = R.VClock.now
    n = make()
    first = _fly_measured(R, n, t0)
    pts, anchor = list(n.track._pts), (n._anchor_lat, n._anchor_lon, n._anchor_time)
    n._busy_lock.acquire()                              # a frame is being matched ...
    try:
        n._last_frame = (R.VClock.now, {})
        R.VClock.now += 1.0
        n._watchdog()
        assert len(n.est) == 1                          # ... under dr_watchdog_s: nothing yet
        R.VClock.now += 4.7                             # 5.7 s stall (endur2)
        n._watchdog()
        assert len(n.est) == 2
        e = n.est[-1]
        assert e.valid and e.mode == PositionEstimate.MODE_PROPAGATED
        assert _sigma(e) > _sigma(first)
        tl = _truth(R.VClock.now, t0)
        assert abs(e.latitude - tl[0]) * M < 3.0 * _sigma(e)
        n._watchdog()                                   # once per dr_watchdog_s, not every tick
        assert len(n.est) == 2
        # the matching thread's state is not touched
        assert list(n.track._pts) == pts and (n._anchor_lat, n._anchor_lon, n._anchor_time) == anchor
    finally:
        n._busy_lock.release()


def _gps(lat, lon, t):
    m = PositionEstimate()
    m.source, m.valid, m.mode = PositionEstimate.SOURCE_GPS, True, PositionEstimate.MODE_MEASURED
    m.latitude, m.longitude = lat, lon
    m.header.stamp.sec, m.header.stamp.nanosec = int(t), int(round((t % 1) * 1e9))
    m.position_covariance = [4.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 0.0]
    return m


def test_gps_handover_during_a_long_match_h1200(env):
    """F32 h1200: GPS at 5 Hz while 10 s matches hold the node, then the GPS is cut."""
    R, make = env
    t0 = R.VClock.now
    n = make()
    n._busy_lock.acquire()                              # GPS checks taking 10 s each at 1200 m
    try:
        for k in range(100):                            # 20 s of GPS at 5 Hz, all during the match
            t = t0 + 0.2 * k
            R.VClock.now = t
            n.on_gps(_gps(*_truth(t, t0), t))
        assert n.track.last_time() is None              # the matching state waits for the frame thread
        assert n._dr_snap is not None                   # the GPS thread's snapshot is there
        R.VClock.now = t0 + 19.8 + 3.0                  # GPS cut: not trusted any more (2 s)
        n._last_frame = (R.VClock.now, {})
        n._watchdog()                                   # the handover: carried from the last GPS point
        e = n.est[-1]
        assert e.valid and e.mode == PositionEstimate.MODE_PROPAGATED and _sigma(e) < 30.0
        tl = _truth(R.VClock.now, t0)
        assert abs(e.latitude - tl[0]) * M < 3.0 * _sigma(e)
    finally:
        n._busy_lock.release()
    n._drain_gps()                                      # the next frame: the GPS points at their times
    v = n.track.velocity(R.VClock.now)
    assert v is not None and v[1] == pytest.approx(V, abs=0.5)
    meta = {"altitude_m": 1200.0, "image_stamp_ns": int(R.VClock.now * 1e9)}
    _, r = n._spatial_window(np.zeros((480, 640, 3), np.uint8), meta)
    assert r < 150.0                                    # was the 600 m circle around the anchor
    # the first fix after the cut: a frame exposed 2.5 s before the last GPS point (camera delay + a
    # 10 s match). It used to erase the GPS track (taken for a clock step back): 600 m search after it
    t_exp = t0 + 19.8 - 2.5
    lat, lon = _truth(t_exp, t0)
    n._gps_was_trusted = False
    n._publish_result(1, {"frame_id": 1, "image_stamp_ns": int(t_exp * 1e9), "altitude_m": 1200.0},
                      {"matcher": "local", "accepted": True, "predicted_lat": lat, "predicted_lon": lon,
                       "inliers": 300, "spread": 1.0, "score": 300.0, "sigma_m": 5.0, "spatial": True,
                       "radius_m": 80.0})
    assert n.est[-1].mode == PositionEstimate.MODE_MEASURED and n.est[-1].valid
    assert n.track.velocity(R.VClock.now) is not None
    R.VClock.now += 2.0
    meta = {"altitude_m": 1200.0, "image_stamp_ns": int(R.VClock.now * 1e9)}
    _, r = n._spatial_window(np.zeros((480, 640, 3), np.uint8), meta)
    assert r < 200.0


def test_carry_state_pure_rules():
    tr = TrackVelocity(accel_mps2=0.25)
    s = DrSnap(LAT0, LON0, 100.0, 10.0, 0.0, V, 0.5, 0.0, 99.0, 0.0)
    lat, lon, sig = carry_snap(s, 110.0, tr)
    assert (lat - LAT0) * M == pytest.approx(100.0, rel=1e-3) and lon == pytest.approx(LON0)
    assert sig == pytest.approx(10.0 + tr.sigma_growth(0.5, V, 10.0, 0.0))
    assert carry_snap(s, 120.0, tr)[2] > sig
    assert watchdog_carry(None, 110.0, tr, 120.0, 900.0)[0] is None
    assert watchdog_carry(s, 99.0 + 121.0, tr, 120.0, 900.0)[0] is None          # time limit
    assert watchdog_carry(s, 110.0, tr, 120.0, 12.0)[0] is None                  # sigma limit
    rec = track_state([(90.0 + i, LAT0, LON0, 8.0) for i in range(40)], None, None, 12.0,
                      [(95.0, 12.0)], (LAT0, LON0, 129.0, 9.0), 129.0, s)
    assert len(rec["pts"]) <= 26                                                   # the fit window only
    r = restore_track(rec, 135.0, 120.0)
    assert r is not None and r["snap"] == s and r["pts"][-1][0] == 129.0
    assert restore_track(rec, 129.0 + 121.0, 120.0) is None                      # too old
    assert restore_track(rec, 120.0, 120.0) is None                               # from the future
    assert restore_track({"pts": [[1, "x", 2, 3]]}, 2.0, 120.0) is None           # malformed
    assert restore_track({"pts": []}, 2.0, 120.0) is None


def test_the_watchdog_follows_the_turn_the_gyro_measures(env):
    """A copter at a waypoint corner: the watchdog's carry turns with the gyro (fin_base: carried straight
    at a 90 deg corner, 46-50 m off at +-17 m)."""
    R, make = env
    t0 = R.VClock.now
    n = make()
    _fly_measured(R, n, t0)
    snap = n._dr_snap
    for k in range(0, 201):                             # 0.02 s samples: 30 deg/s for 3 s, clockwise
        n.gyro.add_rate(snap.t - 1.0 + 0.02 * k, 0.0 if k < 50 else 30.0)
    R.VClock.now = snap.t + 3.0
    n._busy_lock.acquire()
    try:
        n._last_frame = (R.VClock.now, {})
        n._last_out_wall = R.VClock.now - 3.0
        assert n._watchdog_publish()
    finally:
        n._busy_lock.release()
    e = n.est[-1]
    de = (e.longitude - snap.lon) * M * math.cos(math.radians(LAT0))
    dn = (e.latitude - snap.lat) * M
    # 3 s turning north -> east along an arc: ~19 m east and north each (straight on: 30 m north, 0 east)
    assert de > 12.0 and dn < 25.0, (de, dn)


def test_the_no_frame_carry_is_dated_like_a_frame_and_adds_no_used_odometry(env):
    """Isaac Sim p2_plane60_turns (2026-10-30), camera delay 1.46 s applied at 63 m/s: the 'no camera
    frame' carry was dated now while the track runs on exposure times, and re-added the last frame's
    odometry step: 109-160 m ahead, then the right fixes refused as too far from it."""
    R, make = env
    t0 = R.VClock.now
    n = make()
    _fly_measured(R, n, t0)
    n.auto_latency = True
    n.latency_cal.applied, n.latency_cal.applied_sigma = 1.5, 0.1      # the camera delay, known
    n._vo_step = (0.0, 100.0, 1.0, 1.0)                                 # the last frame's step, already used
    n._last_frame = (R.VClock.now, {"frame_id": 7, "image_stamp_ns": int((R.VClock.now - 1.5) * 1e9)})
    R.VClock.now += 3.0                                                 # no camera frame for 3 s
    n._watchdog()
    e = n.est[-1]
    assert e.mode == PositionEstimate.MODE_PROPAGATED and n._vo_step is None
    t_dated = R.VClock.now - 1.5
    assert n._anchor_time == pytest.approx(t_dated, abs=0.05)
    assert abs(e.latitude - _truth(t_dated, t0)[0]) * M < 5.0              # where it was at that instant


def test_a_frame_refused_before_the_odometry_does_not_reuse_the_last_step(env):
    """Isaac Sim p3_plane60_turns (2026-10-30): a frame refused for a 120 deg/s roll-out re-added the last
    frame's odometry step (33 m in 0.5 s) to a carry of 2.3 s at 63 m/s: 160 m behind."""
    R, make = env
    t0 = R.VClock.now
    n = make()
    _fly_measured(R, n, t0)
    R.VClock.now += 2.0
    n._anchor_time = R.VClock.now - 0.6                                 # within the odometry's continuity
    n._vo_step = (0.0, -100.0, 0.5, 1.0)                                 # the last frame's step, wrong here
    meta = {"frame_id": 9, "usable": False, "reason": "vehicle turning 120 deg/s at the exposure",
            "image_stamp_ns": int(R.VClock.now * 1e9)}
    n._process_frame(9, np.zeros((480, 640, 3), np.uint8), meta)
    e = n.est[-1]
    assert e.mode == PositionEstimate.MODE_PROPAGATED
    assert abs(e.latitude - _truth(R.VClock.now, t0)[0]) * M < 3.0 * _sigma(e)
