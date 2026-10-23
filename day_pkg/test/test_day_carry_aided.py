"""open3 (2026-10-23), the day node's carry with the IMU attitude's yaw and the autopilot's velocity
(day_pkg.carry_aids; Isaac Sim closed loop, docs/VALIDATION_STATUS.md):

1. fin_endur_2h: day_subscriber killed on a diamond corner; the restored carry went straight on, 745 m off
   at +-384 m. The restarted node now turns with the yaw persisted with the snapshot vs the IMU's now;
2. outage60: the velocity carried into a 60 s cloud bank right after a corner was 6-8 m/s off. Along the
   autopilot's velocity (bias fitted on the fixes through the corner) it is not;
3. h1200: the GPS lost as the copter accelerates out of its hover; the carry kept the hover's velocity.

The node is built by its own __init__ without a matcher, on a virtual clock (replay_sigma_isaac's harness)."""
import importlib.util
import math
import os
import time

import pytest
from geometry_msgs.msg import TwistStamped
from sensor_msgs.msg import Imu

from day_pkg.carry_state import TRACK_STATE, DrSnap, track_state
from navera_msgs.msg import PositionEstimate

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LAT0, LON0 = 35.8685, 10.5352
M = 111320.0
K = math.cos(math.radians(LAT0))


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
            ds.state_store = state_store
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


def _ll(e, n):
    return LAT0 + n / M, LON0 + e / (M * K)


def _en(lat, lon):
    return (lon - LON0) * M * K, (lat - LAT0) * M


def corner(s):
    """(e, n, heading deg): north at 10 m/s, a 90 deg turn east between s = 10 and 13 s, then east."""
    r = 10.0 * 3.0 / (math.pi / 2)
    if s <= 10.0:
        return 0.0, 10.0 * s, 0.0
    if s <= 13.0:
        a = math.pi / 2 * (s - 10.0) / 3.0
        return r * (1 - math.cos(a)), 100.0 + r * math.sin(a), math.degrees(a)
    return r + 10.0 * (s - 13.0), 100.0 + r, 90.0


def _imu(t, heading_deg):
    m = Imu()
    m.header.stamp.sec, m.header.stamp.nanosec = int(t), int(round((t % 1) * 1e9))
    psi = math.radians(90.0 - heading_deg)
    m.orientation.z, m.orientation.w = math.sin(psi / 2), math.cos(psi / 2)
    m.orientation_covariance[0] = 1e-4
    m.linear_acceleration.z = 9.81
    return m


def _vel(t, ve, vn):
    m = TwistStamped()
    m.header.stamp.sec, m.header.stamp.nanosec = int(t), int(round((t % 1) * 1e9))
    m.twist.linear.x, m.twist.linear.y = ve, vn
    return m


def _err(est, e, n):
    pe, pn = _en(est.latitude, est.longitude)
    return math.hypot(pe - e, pn - n)


def _sigma(est):
    return math.sqrt(est.position_covariance[0])


def test_a_day_node_killed_on_a_corner_turns_its_restored_carry_with_the_imu_yaw(env):
    R, make = env
    t0 = R.VClock.now
    a = make()
    a.track_persist, a._track_saved_at = True, 0.0
    for k in range(0, 1000):                                    # IMU at 100 Hz up to the kill (s = 10)
        a.on_imu(_imu(t0 + 0.01 * k, 0.0))
    for i in range(10):
        e, n, _ = corner(i)
        a.track.add(t0 + i, *_ll(e, n), 8.0)
    a._anchor_lat, a._anchor_lon = _ll(*corner(9)[:2])
    a._anchor_time = a._last_measured_time = t0 + 9
    a._dr_sigma = a._anchor_sigma = 8.0
    R.VClock.now = t0 + 10.0
    assert a._dead_reckon(a.get_clock().now().to_msg(), 1, {"image_stamp_ns": int(R.VClock.now * 1e9)},
                          {}, 0.0, "test")
    assert a._dr_snap.yaw == pytest.approx(0.0, abs=0.5)        # persisted with the snapshot
    a.destroy_node()
    R.VClock.now = t0 + 16.0                                    # killed at the corner, respawned 6 s later
    b = make()
    for k in range(0, 600):                                     # its IMU: heading east now
        b.on_imu(_imu(t0 + 16.0 + 0.01 * k, 90.0))
    R.VClock.now = t0 + 22.0
    assert b._dead_reckon(b.get_clock().now().to_msg(), 2, {"image_stamp_ns": int(R.VClock.now * 1e9)},
                          {}, 0.0, "no match")
    est = b.est[-1]
    assert est.mode == PositionEstimate.MODE_PROPAGATED and est.valid
    e, n, _ = corner(22.0)
    err = _err(est, e, n)
    assert err < 3.0 * _sigma(est) and err < 60.0, (err, _sigma(est))
    # straight on (what the restored node did before) would be ~130 m off
    assert math.hypot(e - 0.0, n - 220.0) > 120.0


def test_the_early_bridge_turns_with_the_imu_yaw_and_hands_its_carry_to_the_node(env, tmp_path):
    from day_pkg.nodes.day_entry import EarlyBridge
    from navera_common import state_store
    now = time.time()
    ts = now - 5.0                                              # the snapshot: entering the corner (s = 10)
    snap = DrSnap(*_ll(*corner(10.0)[:2]), ts, 12.0, 0.0, 10.0, 0.5, 1.0, ts - 1.0, 0.0, 0.0)
    pts = [(ts - 10.0 + i, *_ll(*corner(i)[:2]), 8.0) for i in range(10)]
    state_store.save(TRACK_STATE, track_state(pts, None, None, 0.0, [], None, ts - 1.0, snap))
    got = []
    n = EarlyBridge()
    try:
        n.pub = type("P", (), {"publish": staticmethod(got.append)})()
        for k in range(200):                                    # samples from 3 s after the snapshot: east
            n.on_imu(_imu(ts + 3.0 + 0.01 * k, 90.0))
        assert n.tick() and n.how == "attitude yaw"
        e, n_, _ = corner(10.0 + time.time() - ts)
        err = _err(got[-1], e, n_)
        assert err < 25.0 and err < 3.0 * _sigma(got[-1]), err
        stored = state_store.load(TRACK_STATE, 60.0)
        assert stored["snap"][2] > ts + 4.0                     # the carried snapshot is persisted
    finally:
        n.destroy_node()


def test_carried_along_the_autopilot_velocity_through_a_corner_and_a_speed_up(env):
    """outage60 / h1200: fixes through a corner, then nothing for 30 s while the copter speeds up; the
    autopilot's velocity has a 2 m/s offset (its EKF without GPS)."""
    R, make = env
    t0 = R.VClock.now

    def truth(s):
        e, n, h = corner(s)
        if s <= 13.0:
            return e, n, 10.0 * math.sin(math.radians(h)), 10.0 * math.cos(math.radians(h))
        tau = min(s - 13.0, 5.0)                                # 10 -> 20 m/s over 5 s, east
        return e + tau * tau + 10.0 * max(0.0, s - 18.0), n, 10.0 + 2.0 * tau, 0.0

    from navera_common import state_store
    for aided in ("bias applied", "fed by NAVERA", None):
        state_store.save(TRACK_STATE, {"pts": []})              # not the previous variant's track
        n = make()
        if aided is None:
            n.apv = None
        n.ap_apply_bias = aided == "bias applied"   # an autopilot NAVERA does not feed: its offset removed
        for k in range(0, 460):                                 # 10 Hz up to s = 46
            s = 0.1 * k
            _, _, ve, vn = truth(s)
            if n.apv is not None:
                n.on_ap_velocity(_vel(t0 + s, ve + 2.0, vn - 1.0))
        for i in range(31):                                     # vision fixes 2 Hz up to s = 15 (corner inside)
            s = 0.5 * i
            e, nn, _, _ = truth(s)
            n.track.add(t0 + s, *_ll(e, nn), 20.0)
        n._anchor_lat, n._anchor_lon = _ll(*truth(15.0)[:2])
        n._anchor_time = n._last_measured_time = t0 + 15.0
        n._dr_sigma = n._anchor_sigma = 20.0
        for s in range(16, 46):                                  # 30 s carried, frame by frame
            R.VClock.now = t0 + s
            assert n._dead_reckon(n.get_clock().now().to_msg(), s, {"image_stamp_ns": int((t0 + s) * 1e9)},
                                  {}, 0.0, "cloud")
        e, nn, _, _ = truth(45.0)
        err = _err(n.est[-1], e, nn)
        if aided == "bias applied":
            assert err < 40.0 and err < 3.0 * _sigma(n.est[-1]), (err, _sigma(n.est[-1]))
            assert _sigma(n.est[-1]) < 250.0
        elif aided:
            # fed by NAVERA the offset is not removed (its EKF would absorb it: outage60 ran away) — it
            # widens the stated accuracy: 2.2 m/s x 30 s off, within it
            assert err < 100.0 and err < 2.0 * _sigma(n.est[-1]), (err, _sigma(n.est[-1]))
        else:
            assert err > 150.0, err                             # the plain carry: hover / chord velocity


def test_the_gps_snapshot_carries_the_autopilot_bias_for_the_handover(env):
    """h1200: GPS while hovering, the autopilot's velocity (offset) known; the watchdog's handover follows
    the acceleration that starts at the cut."""
    R, make = env
    t0 = R.VClock.now
    n = make()

    def truth(s):                                               # hover until s = 20, then 2 m/s^2 north
        tau = max(0.0, s - 20.0)
        return 0.0, tau * tau, 0.0, 2.0 * tau

    for k in range(0, 300):
        s = 0.1 * k
        _, _, ve, vn = truth(s)
        n.on_ap_velocity(_vel(t0 + s, ve + 1.0, vn + 0.5))
    m = PositionEstimate()
    m.source, m.valid, m.mode = PositionEstimate.SOURCE_GPS, True, PositionEstimate.MODE_MEASURED
    m.position_covariance = [4.0, 0.0, 0.0, 0.0, 4.0, 0.0, 0.0, 0.0, 0.0]
    for k in range(100):                                        # GPS 5 Hz, s = 0 .. 19.8
        s = 0.2 * k
        R.VClock.now = t0 + s
        m.latitude, m.longitude = _ll(*truth(s)[:2])
        m.header.stamp.sec, m.header.stamp.nanosec = int(t0 + s), int(round(((t0 + s) % 1) * 1e9))
        n.on_gps(m)
    # fed by NAVERA: the offset is not applied (0) but in the velocity's sigma
    assert n._dr_snap.be == 0.0 and n._dr_snap.bn == 0.0 and n._dr_snap.sig_v > 1.0
    n.ap_apply_bias, n._gps_ap_fit = True, (-math.inf, None)
    n.on_gps(m)
    assert n._dr_snap.be == pytest.approx(-1.0, abs=0.3) and n._dr_snap.bn == pytest.approx(-0.5, abs=0.3)
    R.VClock.now = t0 + 27.0
    n._last_frame = (R.VClock.now, {})
    n._last_out_wall = R.VClock.now - 3.0
    n._busy_lock.acquire()
    try:
        assert n._watchdog_publish()
    finally:
        n._busy_lock.release()
    _, nn, _, _ = truth(27.0)
    err = _err(n.est[-1], 0.0, nn)
    assert err < 3.0 * _sigma(n.est[-1]) and err < 15.0, (err, nn)


def test_the_first_fix_after_a_gap_keeps_the_autopilot_fit(env):
    """h1200 (o3_h12a): after the GPS loss the first vision fix stood alone after a > 5 s gap, too few
    points to fit again, and the carry fell back to the hover velocity; the last fit now holds."""
    R, make = env
    t0 = R.VClock.now
    n = make()
    for k in range(400):
        n.on_ap_velocity(_vel(t0 + 0.1 * k, 0.0, 5.0))
    for i in range(10):                                         # 10 s of points, then a gap of 12 s
        n.track.add(t0 + i, *_ll(0.0, 5.0 * i), 3.0)
    b = n._ap_bias()
    assert b is not None
    n.track.add(t0 + 21.0, *_ll(0.0, 105.0), 20.0)              # one fix after the gap
    assert n._ap_bias() == b
    n.track.add(t0 + 22.0, *_ll(400.0, 110.0), 20.0)            # far off its path: refused, not held
    n.track.add(t0 + 23.0, *_ll(-400.0, 115.0), 20.0)
    n.track.add(t0 + 24.0, *_ll(400.0, 120.0), 20.0)
    n.track.add(t0 + 25.5, *_ll(-400.0, 127.5), 20.0)
    assert n._ap_bias() is None
