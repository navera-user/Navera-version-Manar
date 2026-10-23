"""B23: a restarted day process carries the persisted position before its heavy imports and its matcher
(fin_endur_2h: 21 s without a day position after a kill, the output's 10 s bridge ended, EKF failsafe)."""
import math
import time

import pytest

from day_pkg.carry_state import TRACK_STATE, DrSnap, track_state
from navera_common import state_store
from navera_msgs.msg import PositionEstimate


@pytest.fixture
def ros(tmp_path, monkeypatch):
    import rclpy
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    owned = not rclpy.ok()
    if owned:
        rclpy.init(args=["--ros-args", "--log-level", "error"])
    yield
    if owned:
        rclpy.shutdown()


def _persist(age_s):
    now = time.time()
    t = now - age_s
    snap = DrSnap(35.8685, 10.5352, t, 12.0, 0.0, 10.0, 0.5, 0.0, t - 1.0, 0.0)
    state_store.save(TRACK_STATE, track_state([(t - 1.0 - i, 35.8685, 10.5352, 10.0) for i in range(5, -1, -1)],
                                              None, None, None, [], (35.8685, 10.5352, t, 12.0), t - 1.0, snap))


def test_the_early_bridge_publishes_the_persisted_carry_at_once(ros):
    from day_pkg.nodes.day_entry import EarlyBridge
    _persist(5.0)
    got = []
    n = EarlyBridge()
    try:
        n.pub = type("P", (), {"publish": staticmethod(got.append)})()
        assert n.tick()
        e = got[-1]
        assert e.valid and e.mode == PositionEstimate.MODE_PROPAGATED and e.source == PositionEstimate.SOURCE_DAY_VISION
        sigma = math.sqrt(e.position_covariance[0])
        assert 12.0 < sigma < 60.0                                     # grown since the snapshot
        assert (e.latitude - 35.8685) * 111320.0 == pytest.approx(50.0, abs=5.0)   # 10 m/s north for ~5 s
    finally:
        n.destroy_node()


def test_nothing_persisted_or_too_old_publishes_nothing(ros):
    from day_pkg.nodes.day_entry import EarlyBridge
    n = EarlyBridge()
    try:
        assert n.snap is None and not n.tick()
    finally:
        n.destroy_node()
    _persist(200.0)
    n = EarlyBridge()
    try:
        assert n.snap is None and not n.tick()
    finally:
        n.destroy_node()
