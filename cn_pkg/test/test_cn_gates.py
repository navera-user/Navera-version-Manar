"""cn_subscriber gates that refuse to solve: a frame the camera marked unusable (frozen picture),
and a frame with no trusted time (hazard H-08), in both solver modes.
"""
import json
import time

import numpy as np
import pytest

rclpy = pytest.importorskip("rclpy")
from builtin_interfaces.msg import Time   # noqa: E402
from cn_pkg.nodes import cn_subscriber as cs   # noqa: E402
from navera_msgs.msg import NavStatus, SourceHealth   # noqa: E402
from sensor_msgs.msg import TimeReference   # noqa: E402
from std_msgs.msg import String   # noqa: E402


def _make(args=()):
    rclpy.init(args=["--ros-args", *args] if args else None)
    n = cs.CNSubscriber()
    n.sent = []
    n.pub_est.publish = n.sent.append
    n.clock._ntp_synced = lambda: False               # this machine's NTP state must not matter
    return n


@pytest.fixture
def node():
    n = _make()
    yield n
    n.destroy_node()
    rclpy.shutdown()


def _process(n, meta):
    assert n._busy_lock.acquire(blocking=False)        # _dispatch holds it; _process_frame releases it
    n._process_frame(meta["frame_id"], np.zeros((60, 80, 3), np.uint8), meta)
    return n.sent[-1]


def _live_meta(frame_id):
    """frame_meta as live_camera sends it: the exposure on the system clock, utc_time from it."""
    ns = time.time_ns()
    return {"frame_id": frame_id, "image_stamp_ns": ns, "utc_source": "system_clock",
            "utc_time": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ns / 1e9))}


def _stamp(t):
    return Time(sec=int(t), nanosec=int((t % 1) * 1e9))


def _rtc(n, offset_s=0.0, valid=True, lost_power=False):
    now = time.time()
    n._on_rtc_status(String(data=json.dumps({"valid": valid, "lost_power": lost_power})))
    m = TimeReference()
    m.header.stamp, m.time_ref = _stamp(now), _stamp(now + offset_s)
    n._on_rtc(m)


def test_a_frozen_star_picture_is_never_solved(node):
    """D24 / H-01b: a stale sky with a new time is a wrong position — declared invalid, not solved."""
    est = _process(node, {"frame_id": 7, "usable": False, "image_stamp_ns": 1,
                          "reason": "camera image frozen: picture identical to the previous one"})
    assert not est.valid and "camera image frozen" in est.reason
    assert "frozen" in json.loads(est.details_json)["error"]


def test_no_star_solve_without_a_trusted_time(node):
    """H-08 / F27: the camera's system-clock time alone (no RTC, GNSS time or NTP) is never used."""
    est = _process(node, _live_meta(8))
    assert not est.valid and "no trusted time" in est.reason
    d = json.loads(est.details_json)
    assert d["utc"] is None and "no trusted time" in d["utc_source"]


def test_an_rtc_that_lost_power_is_no_trusted_time(node):
    _rtc(node, valid=True, lost_power=True)
    assert "no trusted time" in _process(node, _live_meta(9)).reason


def test_a_valid_rtc_gives_the_exposure_its_time(node):
    """The RTC vouches: the frame goes on to the next gate (here: no attitude), on the RTC's time."""
    _rtc(node, offset_s=7200.0)                       # system clock 2 h behind the DS3231
    meta = _live_meta(10)
    est = _process(node, meta)
    d = json.loads(est.details_json)
    assert d["utc_source"] == "rtc" and "attitude" in est.reason
    rtc_utc = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(meta["image_stamp_ns"] / 1e9 + 7200.0))
    assert d["utc"][:19] == rtc_utc and d["utc_sigma_s"] == 1.0


def _nav_status(gps_contributing):
    st = NavStatus()
    h = SourceHealth(source=SourceHealth.SOURCE_GPS, alive=True, contributing=gps_contributing)
    st.sources = [h]
    return st


def _gnss(n, offset_s):
    m = TimeReference()
    now = time.time()
    m.header.stamp, m.time_ref = _stamp(now), _stamp(now + offset_s)
    n._on_gnss_time(m)


def test_gnss_time_anchors_only_while_the_estimator_elects_the_gps(node):
    _gnss(node, -0.3)                                 # no nav_status yet: GPS not trusted
    assert "no trusted time" in _process(node, _live_meta(11)).reason
    node._on_nav_status(_nav_status(False))           # GPS refused (suspected spoofing)
    _gnss(node, -0.3)
    assert "no trusted time" in _process(node, _live_meta(12)).reason
    node._on_nav_status(_nav_status(True))
    _gnss(node, -0.3)
    d = json.loads(_process(node, _live_meta(13)).details_json)
    assert d["utc_source"] == "gnss" and d["utc_sigma_s"] == 0.5


def test_the_gps_anchor_survives_a_clock_step_after_the_settle_time(node):
    node._on_nav_status(_nav_status(True))
    _gnss(node, 0.0)
    node.clock._wall_minus_mono -= 3600.0             # the wall clock just stepped +1 h (NTP after a boot)
    est = _process(node, _live_meta(14))
    assert not est.valid and "stepped" in est.reason
    node.clock._step_mono -= 61.0                     # 61 s later
    assert node.clock.offset()[1] == "gnss"


def test_autopilot_time_is_used_and_cross_checks_the_anchor(node):
    m = TimeReference()
    now = time.time()
    m.header.stamp, m.time_ref = _stamp(now), _stamp(now + 2.0)
    node._on_autopilot_time(m)
    assert json.loads(_process(node, _live_meta(15)).details_json)["utc_source"] == "autopilot"
    node._on_nav_status(_nav_status(True))
    _gnss(node, 4.0)                                  # 2 s from SYSTEM_TIME: one of them lies
    est = _process(node, _live_meta(16))
    assert not est.valid and "disagree" in est.reason
    sent = []
    node.pub_time_status.publish = sent.append
    node._time_tick()
    st = json.loads(sent[-1].data)
    assert st["trusted"] is False and st["anchor"]["minus_autopilot_s"] == 2.0


def test_a_stated_time_is_used_as_given(node):
    """Replays and the simulator state the exposure time; the utc_time parameter is the operator's."""
    meta = {"frame_id": 13, "utc_time": "2026-03-10 20:20:00", "image_stamp_ns": 1}
    d = json.loads(_process(node, meta).details_json)
    assert d["utc_source"] == "frame" and d["utc"] == "2026-03-10 20:20:00"


def test_allsky360_mode_has_the_same_time_gate():
    n = _make(["-p", "solver_mode:=allsky360"])
    try:
        meta = _live_meta(14)
        result = n._solve_allsky(np.zeros((64, 128), np.uint8), meta)
        assert result["success"] is False and "no trusted time" in result["error"]
        n._publish_result(14, meta, result)
        assert not n.sent[-1].valid and "no trusted time" in n.sent[-1].reason
    finally:
        n.destroy_node()
        rclpy.shutdown()
