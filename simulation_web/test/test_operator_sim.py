"""operator_position(): the SIMULATION marker appears only with simulated data.

The bridge method is called on a stand-in object (no ROS graph, no HTTP).
"""
import json
import threading
import time

from simulation_web.scripts.navera_web_bridge import NaveraWebBridge

from navera_msgs.msg import NavStatus, PositionEstimate


class _Stub:
    operator_position = NaveraWebBridge.operator_position
    operator_decision = NaveraWebBridge.operator_decision
    _source_label = NaveraWebBridge._source_label

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
