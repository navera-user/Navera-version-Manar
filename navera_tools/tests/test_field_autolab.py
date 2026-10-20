"""autolab: rounds at the right times, the strict apply / refuse / revert rule, the kill switch, crash safety."""
import json
import os

import pytest

from navera_tools.field import autolab as al
from navera_tools.field import server as sv


def _score(trusted, p50=2.0, p90=4.0, wrong=0, outside=0, corrected=True):
    blk = {"n": trusted, "err_km_p50_p90_max": [p50, p90, p90 + 1] if trusted else None, "wrong": wrong,
           "within_3sigma": max(0, trusted - outside)}
    empty = {"n": 0, "err_km_p50_p90_max": None, "wrong": 0, "within_3sigma": 0}
    return {"frames": 100, "solved": trusted, "trusted": trusted, "moving_fixes": 0,
            "raw": dict(blk, wrong=0) if corrected else blk, "corrected": blk if corrected else empty,
            "not_solved": {}, "solve_s_median": 2.0}


def test_rounds_come_at_10_25_40_min_one_at_a_time():
    t0 = 1000.0
    assert al.due_round(t0, t0 + 9 * 60, []) is None
    assert al.due_round(t0, t0 + 10 * 60, []) == 0
    assert al.due_round(t0, t0 + 26 * 60, [0]) == 1
    assert al.due_round(t0, t0 + 41 * 60, [0]) == 2              # a late round 2 is skipped for round 3
    assert al.due_round(t0, t0 + 50 * 60, [0, 1, 2]) is None
    assert [n for n, _ in al.round_variants(0)] == ["k5", "stars8"]
    assert "k5" not in [n for n, _ in al.round_variants(0, {"name": "k5"})]


def test_variants_are_accepted_live_and_never_touch_the_calibration():
    from navera_tools.field import live_lab, livectl
    for name, sets in al.VARIANTS + al.REPORT_ONLY:
        assert not any(k.startswith("server.CAL") for k in sets)
        _, bad = livectl.parse_sets([f"{k}={json.dumps(v)}" for k, v in sets.items()])
        assert not bad, (name, bad)
        _, parsed = live_lab.parse_variant(name + ":" + ",".join(f"{k}={json.dumps(v)}" for k, v in sets.items()))
        assert len(parsed) == len(sets)


def test_the_decision_rule():
    base = _score(6, 2.0, 4.0)
    assert al.decide({"baseline": base, "k5": _score(8, 2.3, 3.9)}, None)[:2] == ("apply", "k5")
    # more fixes but one > 50 km / worse median / worse p90 / more outside 3 sigma / not more fixes: refused
    for bad in (_score(9, wrong=1), _score(9, 2.6, 4.0), _score(9, 2.0, 4.5), _score(9, outside=1), _score(6)):
        assert al.decide({"baseline": base, "x": bad}, None)[0] == "keep"
    assert al.decide({"baseline": base, "x": None}, None)[0] == "keep"          # a failed replay
    assert al.decide({"baseline": None, "x": _score(9)}, None)[0] == "keep"
    # the best of two winners (most trusted fixes)
    assert al.decide({"baseline": base, "a": _score(7), "b": _score(9)}, None)[1] == "b"
    # a change in use that now scores worse than the defaults is reverted, and nothing else this round
    applied = {"name": "k5", "sets": {"allsky.DETECT_K_SIGMA": 5.0}}
    act = al.decide({"baseline": base, "current": _score(4), "stars8": _score(12)}, applied)
    assert act[:2] == ("revert", "k5")
    assert al.decide({"baseline": base, "current": _score(8)}, applied)[0] == "keep"
    # judged on the raw errors when nothing is tilt-corrected yet
    assert al.decide({"baseline": _score(3, corrected=False), "k5": _score(5, corrected=False)}, None)[0] == "apply"


def _test(root, started, mode="360", ended=None):
    f = root / "2026-10-25_2100"
    (f / "raw").mkdir(parents=True)
    json.dump({"id": f.name, "started": started, "ended": ended, "mode": mode}, open(f / "session.json", "w"))
    (f / "events.jsonl").write_text('{"t":1,"kind":"start"}\n')
    (f / "frames.jsonl").write_text("")
    return f


def test_a_round_applies_live_logs_and_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getloadavg", lambda: (0.5, 0.5, 0.5))
    t0 = 1_800_000_000.0
    f = _test(tmp_path, t0)
    seen = []

    def lab(folder, out, runs, last_min, jobs):
        seen.append(([n for n, _ in runs], last_min, jobs))
        return {"baseline": _score(5), "k5": _score(8), "stars8": _score(6, wrong=1)}
    assert al.step(str(tmp_path), now=t0 + 5 * 60, lab=lab) is None                 # too early
    rec = al.step(str(tmp_path), now=t0 + 11 * 60, lab=lab)
    assert rec["action"] == "apply" and rec["variant"] == "k5"
    assert seen == [(["baseline", "k5", "stars8"], al.LAST_MIN, 1)]
    live = json.load(open(tmp_path / sv.LIVE_PARAMS_FILE))
    assert live["allsky.DETECT_K_SIGMA"] == 5.0 and live["_by"] == "autolab"
    ev = [json.loads(x) for x in open(f / "events.jsonl")]
    assert ev[-1]["kind"] == "autolab" and ev[-1]["action"] == "apply"
    assert "| k5 |" in open(f / "autolab_round_1.md").read()
    assert "AUTOLAB" in open(tmp_path / "ALERTS.log").read() and "apply k5" in open(tmp_path / "AUTOLAB.txt").read()
    assert al.step(str(tmp_path), now=t0 + 12 * 60, lab=lab) is None                # round 1 done once
    # round 2: the change in use now scores worse than the defaults: reverted
    rec = al.step(str(tmp_path), now=t0 + 26 * 60,
                  lab=lambda *a: {"baseline": _score(7), "current": _score(5), "spots80": _score(9)})
    assert rec["action"] == "revert"
    assert "allsky.DETECT_K_SIGMA" not in json.load(open(tmp_path / sv.LIVE_PARAMS_FILE))


def test_end_removes_the_change_and_reports_only(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getloadavg", lambda: (0.5, 0.5, 0.5))
    t0 = 1_800_000_000.0
    f = _test(tmp_path, t0)
    al.step(str(tmp_path), now=t0 + 11 * 60, lab=lambda *a: {"baseline": _score(5), "k5": _score(8)})
    meta = json.load(open(f / "session.json"))
    meta["ended"] = t0 + 30 * 60
    json.dump(meta, open(f / "session.json", "w"))
    runs = []
    rec = al.step(str(tmp_path), now=t0 + 31 * 60,
                  lab=lambda folder, out, r, last_min, jobs: runs.append((len(r), last_min)) or {"baseline": _score(5)})
    assert rec["action"] == "report" and runs == [(len(al.VARIANTS) + len(al.REPORT_ONLY) + 1, None)]
    assert "allsky.DETECT_K_SIGMA" not in json.load(open(tmp_path / sv.LIVE_PARAMS_FILE))
    assert al.step(str(tmp_path), now=t0 + 32 * 60, lab=lambda *a: pytest.fail("END round twice")) is None


def test_waits_while_the_jetson_is_busy_and_skips_strip_tests(tmp_path, monkeypatch):
    t0 = 1_800_000_000.0
    f = _test(tmp_path, t0)
    monkeypatch.setattr(os, "getloadavg", lambda: (6.0, 6.0, 6.0))
    assert al.step(str(tmp_path), now=t0 + 11 * 60, lab=lambda *a: pytest.fail("ran while busy")) is None
    assert "waits: load" in open(tmp_path / "AUTOLAB.txt").read()
    monkeypatch.setattr(os, "getloadavg", lambda: (0.5, 0.5, 0.5))
    (f / "frames.jsonl").write_text("".join(json.dumps({"t": t0 + 600 + k, "solve_s": 7.0}) + "\n" for k in range(5)))
    assert al.step(str(tmp_path), now=t0 + 11 * 60, lab=lambda *a: pytest.fail("ran while slow")) is None
    g = tmp_path / "strip"
    _test(g, t0, mode="strip")
    assert al.step(str(g), now=t0 + 11 * 60, lab=lambda *a: pytest.fail("strip test")) is None


def test_kill_switch_and_crash_safety(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getloadavg", lambda: (0.5, 0.5, 0.5))
    t0 = 1_800_000_000.0
    _test(tmp_path, t0)
    assert not al.enabled(str(tmp_path), {"NAVERA_AUTOLAB": "0"})
    (tmp_path / "autolab_off").write_text("")
    assert al.step(str(tmp_path), now=t0 + 11 * 60, lab=lambda *a: pytest.fail("ran while off")) is None
    os.remove(tmp_path / "autolab_off")

    def boom(*a):
        raise RuntimeError("replay crashed")
    rec = al.step(str(tmp_path), now=t0 + 11 * 60, lab=boom)
    assert rec["action"] == "error" and "replay crashed" in open(tmp_path / "AUTOLAB.txt").read()
    (tmp_path / "2026-10-25_2100" / "session.json").write_text("{broken")
    assert al.step(str(tmp_path), now=t0 + 30 * 60)["action"] == "error"          # never raises


def test_a_real_round_on_a_recorded_test(tmp_path, monkeypatch):
    pytest.importorskip("av")
    from navera_tools.tests.test_field_live import _session
    sess, _ = _session(tmp_path)
    scores = al.run_lab(str(sess), str(tmp_path / "lab"), [("baseline", {}), al.VARIANTS[0]], None, 1)
    assert set(scores) == {"baseline", "k5"} and all(s and s["frames"] > 0 for s in scores.values())


def test_report_only_variants_are_never_applied_live():
    assert "stack4" in [n for n, _ in al.REPORT_ONLY]
    for k in range(6):
        assert all(n not in dict(al.REPORT_ONLY) for n, _ in al.round_variants(k))
