"""operator_position(): the SIMULATION marker appears only with simulated data.

The bridge method is called on a stand-in object (no ROS graph, no HTTP).
"""
import json
import threading
import time

from navera_common.track import TrackVelocity
from simulation_web.scripts.navera_web_bridge import NaveraWebBridge

from navera_msgs.msg import NavStatus, PositionEstimate


class _Stub:
    operator_position = NaveraWebBridge.operator_position
    operator_decision = NaveraWebBridge.operator_decision
    _source_label = NaveraWebBridge._source_label
    _camera_warning = NaveraWebBridge._camera_warning
    _with_map = staticmethod(NaveraWebBridge._with_map)
    forwarding_state = NaveraWebBridge.forwarding_state

    def __init__(self, details=""):
        now = time.monotonic()
        self._state_lock = threading.Lock()
        self._nav_status_timeout = 2.0
        self._position_timeout = 60.0
        self._position_topic = "/navera/position"
        st = NavStatus()
        st.state = NavStatus.STATE_FIX
        st.active_source = NavStatus.SOURCE_GPS
        self._nav_status, self._nav_status_rx = st, now
        pos = PositionEstimate()
        pos.source = PositionEstimate.SOURCE_GPS
        pos.latitude, pos.longitude = 35.83, 10.63
        pos.details_json = details
        self._position, self._position_rx = pos, now
        self._sim_truth = None
        self._sim_truth_rx = None
        self._frames = []
        self._track = TrackVelocity()

    def get_logger(self):
        class _L:
            def warn(self, *a, **k):
                pass
            warning = error = info = warn
        return _L()


def test_live_data_has_no_simulation_marker():
    out = _Stub(json.dumps({"num_sats": 9})).operator_position()
    assert out["valid"] is True
    assert "simulated" not in out and "sim_truth" not in out


def test_truth_topic_marks_simulation():
    b = _Stub()
    b._sim_truth, b._sim_truth_rx = (35.831, 10.631), time.monotonic()
    out = b.operator_position()
    assert out["simulated"] is True
    assert out["sim_truth"] == [35.831, 10.631]


def test_stale_truth_is_dropped():
    b = _Stub()
    b._sim_truth, b._sim_truth_rx = (35.831, 10.631), time.monotonic() - 10.0
    out = b.operator_position()
    assert "sim_truth" not in out and "simulated" not in out


def test_simulated_position_is_marked_without_truth():
    out = _Stub(json.dumps({"simulated": True})).operator_position()
    assert out["simulated"] is True


def test_no_fix_still_carries_truth():
    b = _Stub()
    b._nav_status.state = NavStatus.STATE_NO_FIX
    b._sim_truth, b._sim_truth_rx = (35.831, 10.631), time.monotonic()
    out = b.operator_position()
    assert out["valid"] is False and out["simulated"] is True


def test_operator_sees_the_accuracy_the_source_and_camera_warnings():
    b = _Stub()
    b._position.position_covariance = [100.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0]
    b._position.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
    d = b.operator_decision()
    assert d["accuracy_m"] == 10 and d["source_name"] == "GPS"
    now = time.monotonic()
    b._frames = [(now, False, "camera tilted 52 deg from vertical (max 45)")] * 8 + [(now, True, "")] * 4
    assert "too tilted" in b.operator_decision()["camera_warning"]


def test_operator_is_told_when_the_vehicle_nears_or_leaves_the_map():
    b = _Stub()
    assert "map_warning" not in b.operator_decision()             # no map flag: nothing said
    b._nav_status.map_area, b._nav_status.map_edge_m = NavStatus.MAP_AREA_NEAR_EDGE, 320.0
    d = b.operator_decision()
    assert d["map_edge_m"] == 320 and "320 m from the edge" in d["map_warning"]
    b._nav_status.state = NavStatus.STATE_NO_FIX                    # no position: still told
    b._nav_status.map_area, b._nav_status.map_edge_m = NavStatus.MAP_AREA_OUTSIDE, -450.0
    d = b.operator_decision()
    assert d["valid"] is False and "450 m OUTSIDE the map" in d["map_warning"]


class _ActionStub(_Stub):
    mission_action = NaveraWebBridge.mission_action
    _in_flight_refusal = NaveraWebBridge._in_flight_refusal

    def __init__(self):
        super().__init__()
        self._armed, self._armed_rx = None, None    # no MAVLink vehicle link

    def _mission_jobs(self):
        return None


def test_forwarding_settings_refused_with_serial_gps_and_no_link(monkeypatch):
    import pytest
    from simulation_web import mission_prep
    monkeypatch.setenv("NAVERA_NMEA_PORT", "/dev/ttyTHS1")
    writes = []
    monkeypatch.setattr(mission_prep, "write_settings", lambda v: writes.append(v) or v)
    monkeypatch.setattr(mission_prep, "read_settings", lambda *a: {})
    b = _ActionStub()
    with pytest.raises(ValueError, match="armed state unknown"):
        b.mission_action("settings", {"changes": {"NAVERA_FORWARD_DEGRADED": "on", "NAVERA_DEGRADED_SIGMA_M": "30"}})
    with pytest.raises(ValueError, match="armed state unknown"):
        b.mission_action("apply", {})
    assert writes == []
    b.mission_action("settings", {"changes": {"NAVERA_DECLINATION_DEG": "3"}})   # not locked
    assert writes == [{"NAVERA_DECLINATION_DEG": "3"}]
    b._armed, b._armed_rx = False, time.monotonic()                               # the link says disarmed
    b.mission_action("settings", {"changes": {"NAVERA_FORWARD_DEGRADED": "off"}})
    assert writes[-1] == {"NAVERA_FORWARD_DEGRADED": "false"}


def _fwd(monkeypatch, saved, running):
    from simulation_web import mission_prep
    monkeypatch.delenv("NAVERA_FORWARD_DEGRADED", raising=False)
    monkeypatch.delenv("NAVERA_DEGRADED_SIGMA_M", raising=False)
    monkeypatch.setattr(mission_prep, "read_settings", lambda *a: saved)
    b = _Stub()
    if running is not None:
        msg = type("M", (), {"data": json.dumps(running)})()
        NaveraWebBridge._on_output_config(b, msg)
    return b.forwarding_state()


def test_the_chip_shows_the_running_output_setting_not_the_saved_one(monkeypatch):
    run = {"forward_degraded": True, "degraded_sigma_m": 50.0}
    same = _fwd(monkeypatch, {"NAVERA_FORWARD_DEGRADED": "true", "NAVERA_DEGRADED_SIGMA_M": "50"}, run)
    assert same == {"on": True, "sigma_m": "50", "running_known": True}
    off_saved = _fwd(monkeypatch, {"NAVERA_FORWARD_DEGRADED": "false"}, run)
    assert off_saved["on"] is True and off_saved["sigma_m"] == "50"           # what the autopilot gets NOW
    assert off_saved["pending_restart"] is True and off_saved["saved"] == {"on": False, "sigma_m": ""}
    sig = _fwd(monkeypatch, {"NAVERA_FORWARD_DEGRADED": "on", "NAVERA_DEGRADED_SIGMA_M": "30"}, run)
    assert sig["sigma_m"] == "50" and sig["saved"]["sigma_m"] == "30" and sig["pending_restart"]
    on_saved = _fwd(monkeypatch, {"NAVERA_FORWARD_DEGRADED": "on", "NAVERA_DEGRADED_SIGMA_M": "30"},
                    {"forward_degraded": False, "degraded_sigma_m": None})
    assert on_saved["on"] is False and on_saved["pending_restart"] and on_saved["saved"]["on"] is True


def test_without_the_running_output_the_chip_falls_back_to_the_saved_setting(monkeypatch):
    got = _fwd(monkeypatch, {"NAVERA_FORWARD_DEGRADED": "true", "NAVERA_DEGRADED_SIGMA_M": "40"}, None)
    assert got == {"on": True, "sigma_m": "40", "running_known": False}
    bad = _Stub()
    NaveraWebBridge._on_output_config(bad, type("M", (), {"data": "not json"})())
    assert getattr(bad, "_output_config", None) is None
