"""A mount calibration belongs to the camera settings it was learned with (live_camera mount_id: F33
open item 4), and the day node tells live_camera its camera-delay estimate (attitude at exposure, F35)."""
import json
import math
from types import MethodType, SimpleNamespace

from day_pkg.mount_cal import stale_reason
from day_pkg.nodes.day_subscriber import DaySubscriber
from navera_common import state_store
from navera_common.latency_cal import LatencyCalibrator, attitude_shift_s
from test_mount_place_fix import _persist_node, _teach


def _with_check(n):
    n._check_mount_id = MethodType(DaySubscriber._check_mount_id, n)
    return n


def test_stale_reason():
    assert stale_reason(None, "a") is None and stale_reason("a", None) is None and stale_reason("a", "a") is None
    assert "a" in stale_reason("a", "b") and "b" in stale_reason("a", "b")


def test_a_stored_calibration_of_the_same_mount_is_kept_and_carries_its_id(tmp_path, monkeypatch):
    n, _ = _persist_node(tmp_path, monkeypatch)
    _with_check(n)._check_mount_id({"mount_id": "mountA"})
    _teach(n)
    n._save_mount_cal()
    assert state_store.load("day_mount", float("inf"))["mount_id"] == "mountA"
    nxt, log = _persist_node(tmp_path, monkeypatch)
    nxt._load_mount_cal("", 0.5)
    _with_check(nxt)._check_mount_id({"mount_id": "mountA"})
    assert nxt.mount_cal.state()["frame centre"]["persisted"]
    assert not any("dropped" in m for m in log.lines)


def test_a_changed_mount_drops_the_stored_calibration(tmp_path, monkeypatch):
    """mount_pitch / lens file changed between flights: the old boresight error is not applied, the
    stored one is overwritten (not reloaded by the flight after), the stated sigma back to the prior."""
    n, _ = _persist_node(tmp_path, monkeypatch)
    _with_check(n)._check_mount_id({"mount_id": "mountA"})
    _teach(n)
    n._save_mount_cal()
    nxt, log = _persist_node(tmp_path, monkeypatch)
    nxt._load_mount_cal("", 0.5)
    assert nxt.mount_cal.state()["frame centre"]["persisted"]
    _with_check(nxt)._check_mount_id({"mount_id": "mountB"})
    st = nxt.mount_cal.state()["frame centre"]
    assert not st["persisted"] and not st["calibrated"] and st["sigma_deg"] == 2.0
    assert any("dropped" in m and "mountA" in m and "mountB" in m for m in log.lines)
    assert "frame centre" not in state_store.load("day_mount", float("inf"))
    third, _ = _persist_node(tmp_path, monkeypatch)
    third._load_mount_cal("", 0.5)
    assert not third.mount_cal.state()["frame centre"]["persisted"]


def test_a_mount_changed_in_flight_forgets_the_samples_and_the_old_kinds_are_not_carried(tmp_path, monkeypatch):
    n, log = _persist_node(tmp_path, monkeypatch)
    _with_check(n)._check_mount_id({"mount_id": "mountA"})
    _teach(n)
    n._save_mount_cal()
    n._check_mount_id({"mount_id": "mountB"})            # the camera restarted with another lens file
    assert n.mount_cal.samples("frame centre") == 0 and any("dropped" in m for m in log.lines)
    _teach(n, mf_deg=-1.0, mr_deg=1.0)
    n._save_mount_cal()
    d = state_store.load("day_mount", float("inf"))
    assert d["mount_id"] == "mountB" and abs(d["frame centre"]["top_deg"] + 1.0) < 0.3


def test_a_calibration_without_id_or_frames_without_one_is_kept(tmp_path, monkeypatch):
    f = tmp_path / "bench.json"
    f.write_text('{"frame centre": {"top_deg": 1.0, "right_deg": 0.5, "sigma_deg": 0.3}, "source": "bench"}')
    n, _ = _persist_node(tmp_path, monkeypatch)
    n._load_mount_cal(str(f), 0.5)
    _with_check(n)._check_mount_id({"mount_id": "mountB"})
    assert n.mount_cal.state()["frame centre"]["persisted"]
    f.write_text('{"frame centre": {"top_deg": 1.0, "right_deg": 0.5, "sigma_deg": 0.3}, "mount_id": "mountA"}')
    m, _ = _persist_node(tmp_path, monkeypatch)
    m._load_mount_cal(str(f), 0.5)
    _with_check(m)._check_mount_id({})                    # a replay / camera without mount_id
    assert m.mount_cal.state()["frame centre"]["persisted"]
    m._check_mount_id({"mount_id": "mountB"})
    assert not m.mount_cal.state()["frame centre"]["persisted"]


def test_the_delay_estimate_is_published_for_the_camera_when_it_changes():
    sent = []
    n = SimpleNamespace(pub_cam_delay=SimpleNamespace(publish=lambda m: sent.append(json.loads(m.data))),
                        latency_cal=LatencyCalibrator(), auto_latency=True, _cam_delay_sent=None)
    pub = MethodType(DaySubscriber._publish_camera_delay, n)
    pub()
    pub()
    assert len(sent) == 1 and sent[0]["correction_s"] == 0.0
    n.latency_cal.applied, n.latency_cal.applied_sigma = 1.3, 0.05
    pub()
    assert len(sent) == 2 and math.isclose(attitude_shift_s(sent[-1], 0.0), 1.3)
    n.auto_latency = False                                 # not applied to the stamps: not to the attitude
    pub()
    assert len(sent) == 3 and attitude_shift_s(sent[-1], 0.0) == 0.0
