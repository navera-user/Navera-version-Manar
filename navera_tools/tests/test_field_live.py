"""Live settings of the field server (live_params.json, livectl) and the live lab (snapshot of a running test,
replays with variants, scores against the phone)."""
import json
import os
import struct

import pytest

from navera_tools.field import allsky
from navera_tools.field import insta360_usb as iu
from navera_tools.field import live_lab, livectl
from navera_tools.field import server as sv


class FakeCam:
    device, cal_path, hfov, error = "fake", "fake.yaml", 111.0, None

    def latest(self):
        return None, 0.0


@pytest.fixture
def field(tmp_path):
    sv.Field.interval_guard = None
    f = sv.Field(str(tmp_path), FakeCam())
    yield f
    _write(tmp_path, {})                                        # back to the values at start
    f.live_params_tick(force=True)
    f._lp_check_t = 1e18                                        # the loop thread leaves the modules alone


def _write(tmp_path, d):
    livectl.write_file(str(tmp_path / sv.LIVE_PARAMS_FILE), d)      # as livectl: a new file renamed in


def test_valid_knobs_apply_and_go_back_when_removed(field, tmp_path):
    k0, gap0 = allsky.DETECT_K_SIGMA, sv.STOPPED_SOLVE_GAP_S
    field.start()
    _write(tmp_path, {"allsky.DETECT_K_SIGMA": 5, "server.STOPPED_SOLVE_GAP_S": 2.5, "field.interval_s": 10,
                      "server.F_SCALE_SEARCH": [0.98, 1.0, 1.02], "_by": "test"})
    field.live_params_tick(force=True)
    assert allsky.DETECT_K_SIGMA == 5.0 and sv.STOPPED_SOLVE_GAP_S == 2.5 and field.interval_s == 10.0
    assert sv.F_SCALE_SEARCH == (0.98, 1.0, 1.02)
    st = field.state()["live_params"]
    assert st["active"]["allsky.DETECT_K_SIGMA"] == 5.0 and st["refused"] == {}
    ev = [json.loads(x) for x in open(tmp_path / field.session.id / "events.jsonl")]
    lp = [e for e in ev if e.get("kind") == "live_param"]
    assert {e["key"] for e in lp} >= {"allsky.DETECT_K_SIGMA", "server.STOPPED_SOLVE_GAP_S"} and lp[0]["by"] == "test"
    _write(tmp_path, {"server.STOPPED_SOLVE_GAP_S": 2.5})
    field.live_params_tick(force=True)
    assert allsky.DETECT_K_SIGMA == k0 and sv.STOPPED_SOLVE_GAP_S == 2.5
    _write(tmp_path, {})
    field.live_params_tick(force=True)
    assert sv.STOPPED_SOLVE_GAP_S == gap0 and field.state()["live_params"]["active"] == {}


def test_unknown_out_of_range_and_wrong_type_are_refused(field, tmp_path):
    m0 = allsky.MIN_MATCHED
    _write(tmp_path, {"allsky.MIN_MATCHED": 2, "server.MIN_STARS": "many", "os.system": 1, "allsky.MAX_RMS_DEG": True,
                      "server.F_SCALE_SEARCH": [0.5]})
    field.live_params_tick(force=True)
    ref = field.state()["live_params"]["refused"]
    assert set(ref) == {"allsky.MIN_MATCHED", "server.MIN_STARS", "os.system", "allsky.MAX_RMS_DEG", "server.F_SCALE_SEARCH"}
    assert allsky.MIN_MATCHED == m0


def test_a_bad_file_changes_nothing_and_never_raises(field, tmp_path):
    _write(tmp_path, {"allsky.MIN_MATCHED": 9})
    field.live_params_tick(force=True)
    (tmp_path / sv.LIVE_PARAMS_FILE).write_text('{"allsky.MIN_MATCHED": 1, "server.MIN_STARS": 5')   # half written
    field.live_params_tick(force=True)
    assert allsky.MIN_MATCHED == 9 and field.state()["live_params"]["error"]
    (tmp_path / sv.LIVE_PARAMS_FILE).write_text("[1, 2]")
    field.live_params_tick(force=True)
    assert allsky.MIN_MATCHED == 9


def test_calibration_knobs_refused_once_frozen_and_focal_reset_acts_once(field, tmp_path):
    field.cal_samples = [None] * sv.CAL_SAMPLES
    _write(tmp_path, {"server.CAL_SAMPLES": 20})
    field.live_params_tick(force=True)
    assert "server.CAL_SAMPLES" in field.state()["live_params"]["refused"]
    field.f_scale = 1.03
    _write(tmp_path, {"field.f_scale_reset": 1.5})
    field.live_params_tick(force=True)
    assert field.f_scale is None
    field.f_scale = 1.01
    _write(tmp_path, {"field.f_scale_reset": 1.5})                                 # same value: not again
    field.live_params_tick(force=True)
    assert field.f_scale == 1.01


def test_livectl_writes_atomically_and_checks_ranges(tmp_path, capsys):
    rc = livectl.main(["set", "allsky.DETECT_K_SIGMA=5", "server.F_SCALE_SEARCH=0.97,1,1.03", "--dir", str(tmp_path),
                       "--url", "http://127.0.0.1:9", "--wait", "0"])
    d = json.load(open(tmp_path / sv.LIVE_PARAMS_FILE))
    assert d["allsky.DETECT_K_SIGMA"] == 5 and d["server.F_SCALE_SEARCH"] == [0.97, 1.0, 1.03] and rc == 1
    assert not [n for n in os.listdir(tmp_path) if ".tmp" in n]
    assert livectl.main(["set", "allsky.DETECT_K_SIGMA=99", "--dir", str(tmp_path), "--wait", "0"]) == 2
    assert json.load(open(tmp_path / sv.LIVE_PARAMS_FILE))["allsky.DETECT_K_SIGMA"] == 5
    livectl.main(["reset", "allsky.DETECT_K_SIGMA", "--dir", str(tmp_path), "--url", "http://127.0.0.1:9", "--wait", "0"])
    assert "allsky.DETECT_K_SIGMA" not in json.load(open(tmp_path / sv.LIVE_PARAMS_FILE))


def _session(tmp_path):
    """A synthetic recorded test (test_field_raw's camera stream), its raw file still 'being written'."""
    from navera_tools.tests.test_field_raw import _live, _packets
    sess = tmp_path / "2026-10-19_2100"
    pk = _packets(6.0)
    _live(pk, str(sess / "raw"))
    t0 = pk[0][0]
    json.dump({"id": sess.name, "started": t0, "interval_s": 2.0, "clock_offset_s": 0.5, "latency_s": 1.71,
               "calibration": "none"}, open(sess / "session.json", "w"))
    with open(sess / "phone.jsonl", "w") as fh:
        for k in range(7):
            fh.write(json.dumps({"t": t0 + k, "lat": 36.8, "lon": 10.2, "acc": 5, "speed": 0}) + "\n")
        fh.write('{"t": 18000')                                                     # a line being written
    raw = sess / "raw" / "raw360_0000.bin"
    with open(raw, "ab") as fh:                                                     # a record being written
        fh.write(iu.RAW_RECORD.pack(t0 + 7, iu.KIND_IMU, 1, 5000) + b"\x00" * 100)
    return sess, len(pk)


def test_snapshot_of_a_test_being_written(tmp_path):
    pytest.importorskip("av")
    sess, n = _session(tmp_path)
    snap = live_lab.snapshot(str(sess), str(tmp_path / "snap"))
    assert len(list(iu.read_raw(os.path.join(snap, "raw")))) == n
    assert os.path.getsize(os.path.join(snap, "raw", "raw360_0000.bin")) == live_lab.complete_raw_length(
        str(sess / "raw" / "raw360_0000.bin"))
    assert open(os.path.join(snap, "phone.jsonl")).read().endswith("}\n")
    assert len(list(iu.read_raw(str(sess / "raw")))) == n                         # the live folder untouched


def test_lab_baseline_and_variant_table(tmp_path, capsys):
    pytest.importorskip("av")
    sess, _ = _session(tmp_path)
    out = tmp_path / "lab"
    assert live_lab.main([str(sess), "--variant", "k5:allsky.DETECT_K_SIGMA=5,server.F_SCALE_SEARCH=(0.98,1.02)",
                          "--out", str(out), "--jobs", "2"]) == 0
    lab = json.load(open(out / "lab.json"))
    assert [r["name"] for r in lab["runs"]] == ["baseline", "k5"]
    assert all(r["score"] and r["score"]["frames"] > 0 for r in lab["runs"]), lab
    assert "| baseline |" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        live_lab.parse_variant("bad:allsky.MIN_MATCHED=1")                        # out of the live range
    with pytest.raises(SystemExit):
        live_lab.parse_variant("x:os.path=1")


def test_score_against_the_phone(tmp_path):
    t0 = 1_800_000_000.0
    with open(tmp_path / "phone.jsonl", "w") as fh:
        for k in range(100):
            fh.write(json.dumps({"t": t0 + k, "lat": 36.8, "lon": 10.2}) + "\n")
    frames = [
        {"mode": "360", "solved": True, "stopped": True, "t_exp": t0 + 10, "lat": 36.9, "lon": 10.2, "sigma_km": 33.0,
         "lat_cal": 36.81, "lon_cal": 10.2, "sigma_km_cal": 5.6},
        {"mode": "360", "solved": True, "stopped": True, "t_exp": t0 + 20, "lat": 38.2, "lon": 10.2, "sigma_km": 33.0},
        {"mode": "360", "solved": True, "stopped": False, "t_exp": t0 + 30, "lat": 38.0, "lon": 10.2, "sigma_km": 600},
        {"mode": "360", "solved": False, "why": "too few stars (3)"},
    ]
    with open(tmp_path / "frames.jsonl", "w") as fh:
        fh.write("\n".join(json.dumps(f) for f in frames) + "\n")
    s = live_lab.score(str(tmp_path))
    assert s["trusted"] == 2 and s["moving_fixes"] == 1 and s["raw"]["wrong"] == 1 and s["raw"]["within_3sigma"] == 1
    assert s["corrected"]["n"] == 1 and s["corrected"]["err_km_p50_p90_max"][0] == pytest.approx(1.1, abs=0.1)
    assert s["not_solved"] == {"too few stars": 1}
