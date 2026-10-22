"""F33/F35 in the day node: a local match placed before the gates — the camera mount error learned
from GPS checks removed, the pose guard's two candidates resolved by the carried position, a pose
far from the attitude refused, and the stated sigma widened by the mount's and the guard's doubt."""
import math
from types import MethodType, SimpleNamespace

import pytest

from day_pkg.mount_cal import MountCalibration, axes
from day_pkg.nodes.day_subscriber import DaySubscriber
from day_pkg.vision_nav import _en, _move
from navera_common.latency_cal import LatencyCalibrator
from navera_common.sensor_history import History

LAT0, LON0 = 35.8685, 10.5352
METHODS = ("_place_fix", "_pose_guard_refusal", "_mount_corrected", "_delay_known_sigma_s",
           "_unknown_delay_sigma_s", "_mount_check_fix", "_mount_sigma", "_mount_term_m", "_mount_sample_refused")


def _node(pred=None, mount=True):
    n = SimpleNamespace(latency_cal=LatencyCalibrator(nominal_s=1.3), unknown_delay_sigma_s=1.0,
                        frame_time_sigma_s=0.05, mount_sigma_deg=2.0, pose_guard_choose=True,
                        pose_guard_refuse_deg=15.0, _gps_hist=History(maxlen=100, max_gap_s=1.5),
                        mount_cal=MountCalibration(prior_deg=2.0, min_samples=12) if mount else None)
    for m in METHODS:
        setattr(n, m, MethodType(getattr(DaySubscriber, m), n))
    for m in ("_fix_kind", "_fix_heading", "_fix_height", "_expected_tilt"):
        setattr(n, m, getattr(DaySubscriber, m))
    n._predicted = lambda meta: pred
    return n


META = {"altitude_m": 250.0, "heading_deg": 0.0, "straightened": True, "attitude_source": "imu",
        "image_stamp_ns": int(100e9)}


def _off(p, q):
    return math.hypot(*_en(p, q))


def _teach(n, mf_deg=3.0, mr_deg=-2.5, h=250.0):
    """GPS checks around a circuit: the frame centre is h x tan(mount) off the truth."""
    for i in range(24):
        hd = i * 15.0
        top, right = axes(hd)
        a, b = h * math.tan(math.radians(mf_deg)), h * math.tan(math.radians(mr_deg))
        off = (a * top[0] + b * right[0], a * top[1] + b * right[1])
        truth = _move((LAT0, LON0), 40.0 * i, 0.0)
        vis = _move(truth, -off[0], -off[1])
        n.mount_cal.add("frame centre", _en(truth, vis), hd, h, t=float(i))


def test_mount_error_removed_from_a_fix():
    n = _node()
    _teach(n)
    truth = (LAT0, LON0)
    a, b = 250.0 * math.tan(math.radians(3.0)), 250.0 * math.tan(math.radians(-2.5))
    vis = _move(truth, -b, -a)                                 # heading 0: top = north, right = east
    res = {"predicted_lat": vis[0], "predicted_lon": vis[1], "position_from": "frame centre", "rotation_deg": 0.0}
    st = {}
    lat, lon, why = n._place_fix(res, META, st)
    assert why is None and _off((lat, lon), truth) < 1.5 < _off(vis, truth) - 15.0
    assert "mount_corr_m" in st and st["mount_cal"]["calibrated"]


def test_without_calibration_the_fix_is_unchanged():
    n = _node()
    res = {"predicted_lat": LAT0, "predicted_lon": LON0, "position_from": "camera pose"}
    lat, lon, why = n._place_fix(res, META, {})
    assert (lat, lon, why) == (LAT0, LON0, None)


def _guarded(tilt=8.0):
    centre = _move((LAT0, LON0), 0.0, 35.0)                    # the stale attitude: 35 m off
    return {"predicted_lat": centre[0], "predicted_lon": centre[1], "centre_lat": centre[0],
            "centre_lon": centre[1], "pose_lat": LAT0, "pose_lon": LON0, "position_from": "frame centre",
            "pose_tilt_deg": tilt, "pose_guard": "pose tilt ...: frame centre kept"}


def test_guard_takes_the_candidate_nearer_the_carried_position():
    n = _node(pred=(*_move((LAT0, LON0), 3.0, -4.0), 12.0))
    res, st = _guarded(), {}
    lat, lon, why = n._place_fix(res, META, st)
    assert why is None and _off((lat, lon), (LAT0, LON0)) < 0.1
    assert res["position_from"] == "camera pose" and st["pose_guard_choice"]["took"] == "camera pose"
    assert res["_guard_sigma_m"] == pytest.approx(12.0)          # min(35 / 2, carried sigma)
    n = _node(pred=(*_move((LAT0, LON0), 0.0, 33.0), 30.0))      # the prediction says the centre
    res = _guarded()
    lat, lon, _ = n._place_fix(res, META, {})
    assert res["position_from"] == "frame centre" and res["_guard_sigma_m"] == pytest.approx(17.5)


def test_guard_without_a_carried_position_keeps_the_centre_with_half_the_gap_as_sigma():
    n = _node(pred=None)
    res = _guarded()
    lat, lon, _ = n._place_fix(res, META, {})
    assert res["position_from"] == "frame centre" and res["_guard_sigma_m"] == pytest.approx(17.5, abs=0.1)


def test_pose_far_from_the_attitude_is_refused():
    n = _node(pred=(LAT0, LON0, 10.0))
    _, _, why = n._place_fix(_guarded(tilt=32.0), META, {})
    assert why and "rejected" in why
    n.pose_guard_refuse_deg = 0.0                                 # off
    assert n._place_fix(_guarded(tilt=32.0), META, {})[2] is None


def test_stated_sigma_has_the_mount_term_until_learned():
    n = _node()
    res = {"position_from": "frame centre"}
    before = n._mount_sigma(10.0, res, META)
    assert before == pytest.approx(math.hypot(10.0, 250.0 * math.tan(math.radians(2.0))))
    _teach(n)
    after = n._mount_sigma(10.0, res, META)
    assert 10.0 <= after < 10.5
    assert n._mount_sigma(10.0, {"position_from": "camera pose"}, META) == pytest.approx(before)  # not learned
    res["_guard_sigma_m"] = 20.0
    assert n._mount_sigma(10.0, res, META) == pytest.approx(math.hypot(after, 20.0))
    assert n._mount_sigma(10.0, {}, {}) == 10.0                   # no height: no term


def test_gps_check_teaches_both_kinds():
    n = _node()
    g = (LAT0, LON0)
    n._gps_hist.add(99.0, _move(g, 0.0, -10.0))
    n._gps_hist.add(100.0, g)
    res = {"predicted_lat": LAT0 + 1e-4, "predicted_lon": LON0, "centre_lat": LAT0 + 1e-4, "centre_lon": LON0,
           "pose_lat": LAT0, "pose_lon": LON0 + 1e-4, "position_from": "camera pose", "rotation_deg": 0.0}
    placed = n._mount_check_fix(res, META, g)
    assert placed is not None
    assert n.mount_cal.samples("frame centre") == 1 and n.mount_cal.samples("camera pose") == 1
    s = n.mount_cal._s["frame centre"][0]
    assert s[1] == pytest.approx(0.0, abs=0.01) and s[2] == pytest.approx(-11.13, abs=0.05)   # GPS - vision
    assert s[5] == pytest.approx(0.0, abs=0.01) and s[6] == pytest.approx(10.0, abs=0.05)     # 10 m/s north
    assert n._mount_check_fix(dict(res, pose_guard="x", pose_tilt_deg=40.0), META, g) is None  # refused


def test_without_mount_cal_the_prior_term_stays():
    n = _node(mount=False)
    assert n._mount_sigma(10.0, {}, META) == pytest.approx(math.hypot(10.0, 250.0 * math.tan(math.radians(2.0))))
    res = {"predicted_lat": LAT0, "predicted_lon": LON0}
    assert n._place_fix(res, META, {}) == (LAT0, LON0, None)


class _Log:
    def __init__(self):
        self.lines = []

    def info(self, m, **kw):
        self.lines.append(m)

    warn = error = info


def _persist_node(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    n = _node()
    n.mount_cal_persist, n.calib_rollback_s = True, 60.0
    n.MOUNT_STATE = DaySubscriber.MOUNT_STATE
    log = _Log()
    n.get_logger = lambda: log
    for m in ("_load_mount_cal", "_save_mount_cal"):
        setattr(n, m, MethodType(getattr(DaySubscriber, m), n))
    return n, log


def test_learned_mount_is_persisted_and_used_by_the_next_flight(tmp_path, monkeypatch):
    n, _ = _persist_node(tmp_path, monkeypatch)
    _teach(n)
    n._save_mount_cal()
    assert (tmp_path / "day_mount.json").exists()
    nxt, log = _persist_node(tmp_path, monkeypatch)              # next flight: GPS only for the take-off
    nxt._load_mount_cal("", 0.5)
    assert nxt.mount_cal.state()["frame centre"]["persisted"]
    a, b = 250.0 * math.tan(math.radians(3.0)), 250.0 * math.tan(math.radians(-2.5))
    vis = _move((LAT0, LON0), -b, -a)
    res = {"predicted_lat": vis[0], "predicted_lon": vis[1], "position_from": "frame centre", "rotation_deg": 0.0}
    lat, lon, _ = nxt._place_fix(res, META, {})
    assert _off((lat, lon), (LAT0, LON0)) < 1.5
    # its stated sigma: the persisted sigma (>= 0.5 deg), not the 2 deg prior
    s = nxt._mount_sigma(10.0, res, META)
    assert s == pytest.approx(math.hypot(10.0, 250.0 * math.tan(math.radians(0.5))), rel=1e-3)


def test_a_bench_calibration_file_and_none_at_all(tmp_path, monkeypatch):
    f = tmp_path / "bench.json"
    f.write_text('{"frame centre": {"top_deg": 1.0, "right_deg": 0.5, "sigma_deg": 0.3}, "source": "bench"}')
    n, _ = _persist_node(tmp_path, monkeypatch)
    n._load_mount_cal(str(f), 0.5)
    assert n.mount_cal.prior_source == "bench"
    none, log = _persist_node(tmp_path / "empty", monkeypatch)
    none._load_mount_cal("", 0.5)
    assert any("no camera mount calibration" in m for m in log.lines)
    assert none._mount_sigma(10.0, {}, META) == pytest.approx(math.hypot(10.0, 250.0 * math.tan(math.radians(2.0))))
    bad, log = _persist_node(tmp_path, monkeypatch)
    bad._load_mount_cal(str(tmp_path / "missing.json"), 0.5)
    assert any("unreadable" in m for m in log.lines) and not bad.mount_cal.state()["frame centre"]["persisted"]


def _check(n, speed):
    g = (LAT0, LON0)
    n._gps_hist.add(99.0, _move(g, 0.0, -speed))
    n._gps_hist.add(100.0, g)
    res = {"predicted_lat": LAT0 + 1e-4, "predicted_lon": LON0, "centre_lat": LAT0 + 1e-4, "centre_lon": LON0,
           "position_from": "frame centre", "rotation_deg": 0.0}
    return n._mount_check_fix(res, META, g)


def test_no_mount_sample_while_the_frame_time_is_unknown():
    """F38: a copter flies nose first — the unknown delay's offset (speed x delay) lies along the frame top
    like a pitch error (Isaac Sim 2026-10-22: 1.5 deg 'learned' for the point under the camera)."""
    n = _node()
    n.latency_cal = LatencyCalibrator()                           # no delay set, nothing applied
    assert _check(n, 10.0) is not None and n.mount_cal.samples("frame centre") == 0
    assert n._mount_sample_refused((10.0, 0.0)) == "camera delay unknown"
    n = _node()                                                   # set 1.3 +- 0.1 s
    assert _check(n, 10.0) is not None and n.mount_cal.samples("frame centre") == 1     # 1 m: a sample
    n = _node()
    assert _check(n, 30.0) is not None and n.mount_cal.samples("frame centre") == 0     # 3 m: none
    assert "dating error 3.0 m" in n._mount_sample_refused((30.0, 0.0))
