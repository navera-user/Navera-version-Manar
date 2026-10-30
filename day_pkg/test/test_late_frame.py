"""The day node with a late frame at 60 m/s (frame meta late_s from live_camera, frame_lateness).

Unit level only: synthetic metas, no Isaac Sim, no ROS graph.
"""
import math
from types import MethodType, SimpleNamespace

from day_pkg.fix_sigma import SigmaCalibration
from day_pkg.nodes.day_subscriber import DaySubscriber
from navera_common.latency_cal import LatencyCalibrator


def _node():
    lc = LatencyCalibrator(nominal_s=0.2)
    lc.applied = None
    logs = []
    n = SimpleNamespace(latency_cal=lc, auto_latency=False, unknown_delay_sigma_s=1.0, local_sigma_m=30.0,
                        sigma_cal=SigmaCalibration(5.0, 15), late_frame_gate_m=60.0, logs=logs,
                        track=SimpleNamespace(velocity=lambda t: (60.0, 0.0, 0.0)),       # 60 m/s east
                        get_logger=lambda: SimpleNamespace(warn=lambda *a, **k: logs.append(a)))
    n._model_sigma = lambda result, meta: 7.8
    n._unknown_delay_sigma_s = MethodType(DaySubscriber._unknown_delay_sigma_s, n)
    return n


def test_on_time_frame_unchanged():
    n = _node()
    base = DaySubscriber._fix_sigma(n, {"sigma_m": 7.8}, {})
    meta = {"image_stamp_ns": 1}
    DaySubscriber._check_late_frame(n, meta)
    assert meta == {"image_stamp_ns": 1} and not n.logs
    assert DaySubscriber._fix_sigma(n, {"sigma_m": 7.8}, meta) == base


def test_undated_late_frame_widens_the_sigma_to_cover_it():
    n = _node()
    base = DaySubscriber._fix_sigma(n, {"sigma_m": 7.8}, {})
    meta = {"late_s": 0.6, "late_basis": "interval", "late_redated": False}
    DaySubscriber._check_late_frame(n, meta)
    assert meta.get("usable") is None                           # 36 m: within the 60 m gate
    sig = DaySubscriber._fix_sigma(n, {"sigma_m": 7.8}, meta)
    assert math.isclose(sig, math.hypot(base, 36.0))
    assert 36.0 + 2 * base <= 3.0 * sig                         # the along-track error is inside 3 sigma
    assert math.isclose(DaySubscriber._fix_sigma(n, {}, meta), math.hypot(30.0, 36.0))   # no model sigma


def test_undated_frame_beyond_the_gate_gives_no_fix():
    n = _node()
    meta = {"late_s": 2.2, "late_basis": "interval", "late_redated": False}
    DaySubscriber._check_late_frame(n, meta)
    assert meta["usable"] is False and "2.20 s late" in meta["reason"] and n.logs


def test_redated_frame_keeps_its_sigma():
    n = _node()
    base = DaySubscriber._fix_sigma(n, {"sigma_m": 7.8}, {})
    meta = {"late_s": 2.2, "late_basis": "camera_stamp", "late_redated": True}
    DaySubscriber._check_late_frame(n, meta)
    assert meta.get("usable") is None
    assert DaySubscriber._fix_sigma(n, {"sigma_m": 7.8}, meta) == base
