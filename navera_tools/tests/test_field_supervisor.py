"""The field supervisor: status screen and alerts from a test folder, never touching the test's files."""
import hashlib
import json
import os
import time

from navera_tools.field import supervisor as sv


def _session(root, now, frames, phone, ended=None):
    d = os.path.join(root, "2026-10-19_2100")
    os.makedirs(d)
    json.dump({"id": "2026-10-19_2100", "started": now - 900, "ended": ended}, open(os.path.join(d, "session.json"), "w"))
    for name, rows in (("frames", frames), ("phone", phone), ("events", [{"t": now - 900, "kind": "start"}])):
        with open(os.path.join(d, name + ".jsonl"), "w") as f:
            f.write("".join(json.dumps(r) + "\n" for r in rows))
    return d


def _digest(d):
    return {n: hashlib.md5(open(os.path.join(d, n), "rb").read()).hexdigest() for n in sorted(os.listdir(d))}


def test_a_healthy_drive_has_no_alert(tmp_path):
    now = time.time()
    frames = [{"t": now - 30 * k, "mode": "360", "solved": True, "stopped": True, "err_km_live": 8.0,
               "err_km_cal_live": 1.2, "sigma_km": 33.0, "solve_s": 2.0, "cal_sample": None} for k in range(20, 0, -1)]
    d = _session(str(tmp_path), now, frames, [{"t": now - 2, "lat": 35.8, "lon": 10.6, "acc": 5}])
    state = {"step": 4, "recording": "2026-10-19_2100", "mode": "360", "imu_age_s": 0.1, "frames": 20, "fixes": 20,
             "checks": [{"id": "camera", "status": "ok"}], "live": {"sky": "clear", "confirmed": 25},
             "raw": {"mb": 3400.0, "files": ["raw360_0000.bin"], "drops": 0, "drop_mb": 0.0, "queue_mb": 0.1, "error": None}}
    before = _digest(d)
    lines, alerts = sv.assess(state, d, now=now, root=str(tmp_path))
    assert alerts == {}, alerts
    text = "\n".join(lines)
    assert "raw recording: 3400 MB" in text
    lines, alerts = sv.assess(dict(state, raw=dict(state["raw"], drops=3, drop_mb=0.4)), d, now=now, root=str(tmp_path))
    assert "raw" in alerts
    lines, alerts = sv.assess(dict(state, raw=None), d, now=now, root=str(tmp_path))
    assert "raw_off" in alerts
    assert "RECORDING 2026-10-19_2100" in text and "USE" in text and "corrected 1.2 km" in text
    assert _digest(d) == before                                   # read only


def test_problems_are_named_with_what_to_do(tmp_path):
    now = time.time()
    frames = [{"t": now - 700, "mode": "360", "solved": True, "stopped": False, "solve_s": 9.0} for _ in range(6)]
    d = _session(str(tmp_path), now, frames, [{"t": now - 300, "lat": 35.8, "lon": 10.6, "acc": 5}])
    state = {"step": 4, "recording": "x", "mode": "360", "imu_age_s": 45.0, "checks": [], "live": {}}
    _, alerts = sv.assess(state, d, now=now)
    assert {"imu", "frames", "phone", "slow", "no_use"} <= set(alerts)
    assert all(fix for _, fix in alerts.values())
    _, alerts = sv.assess(None, None, now=now)
    assert "server" in alerts


def test_once_writes_status_and_alerts_and_finished_tests_are_scored_once(tmp_path, monkeypatch):
    now = time.time()
    d = _session(str(tmp_path), now, [{"t": now - 5, "mode": "360", "solved": False}], [], ended=now - 1)
    (tmp_path / "access_key.txt").write_text("abcdefgh123")
    calls = []
    monkeypatch.setattr(sv, "fetch_state", lambda url, key, timeout=5.0: None)
    monkeypatch.setattr(sv.subprocess, "run", lambda *a, **k: calls.append(a) or type("R", (), {"stdout": "{}", "stderr": "", "returncode": 0})())
    monkeypatch.setattr("sys.argv", ["supervisor", "--root", str(tmp_path), "--once"])
    before = _digest(d)
    assert sv.main() == 0 and sv.main() == 0
    assert "server: NOT ANSWERING" in (tmp_path / "STATUS.txt").read_text()
    log = (tmp_path / "ALERTS.log").read_text()
    assert log.count("ALERT server") == 1                         # logged when it appears, not every pass
    assert len(calls) == 1 and (tmp_path / "2026-10-19_2100_reprocess360.txt").exists()
    assert _digest(d) == before
