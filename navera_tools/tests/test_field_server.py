"""The field server's session control: restart in the middle of a test, odd taps, the key, a failing finish."""
import json
import os
import time

from navera_tools.field import server as sv
from navera_tools.field.store import FieldSession, read_jsonl


class FakeCam:
    device, cal_path, hfov, error = "fake", "fake.yaml", 111.0, None

    def latest(self):
        return None, 0.0


def _field(root):
    sv.Field.interval_guard = None
    return sv.Field(str(root), FakeCam())


def test_a_restart_in_the_middle_of_a_test_carries_on_in_the_same_folder(tmp_path):
    f = _field(tmp_path)
    f.go(2), f.go(3), f.go(4)
    first = f.session.id
    f.session.log("frames", {"idx": 7, "solved": False})
    f.session.log("phone", {"lat": 35.8, "lon": 10.6})
    f2 = _field(tmp_path)                                         # the server was killed and started again
    assert f2.session is not None and f2.session.id == first and f2.step == 4 and f2.frame_idx == 7
    assert len([n for n in os.listdir(tmp_path) if n[:2] == "20"]) == 1
    assert f2.on_phone_batch([{"phone_t_ms": 1000, "lat": 1.0, "lon": 2.0}]) == 1


def test_an_old_unfinished_test_is_closed_with_a_report_not_resumed(tmp_path):
    s = FieldSession(str(tmp_path), now=time.time() - 3 * 86400)
    s.log("frames", {"idx": 1, "solved": False, "t": time.time() - 3 * 86400})
    f = _field(tmp_path)
    assert f.session is None and os.path.exists(os.path.join(s.dir, "report.md"))


def test_steps_only_go_in_the_page_order(tmp_path):
    f = _field(tmp_path)
    f.go("abc"), f.go(4), f.go(5)
    assert f.step == 1 and f.session is None                      # no jump to 4 or 5 from step 1
    f.go(2), f.go(3), f.go(4), f.go(4)                            # a double tap on Start
    assert len([n for n in os.listdir(tmp_path) if n[:2] == "20"]) == 1
    f.go(1)                                                       # a second phone cannot stop a running test
    assert f.step == 4 and f.session is not None
    f.go(5)
    assert f.step == 5 and f.session is None and f.last_done


def test_a_failing_report_does_not_trap_the_operator_in_step_4(tmp_path, monkeypatch):
    f = _field(tmp_path)
    f.go(2), f.go(3), f.go(4)
    monkeypatch.setattr(sv.report_mod, "write_report", lambda d: 1 / 0)
    f.go(5)
    assert f.step == 5 and f.session is None


def test_the_key_can_never_be_empty(tmp_path):
    (tmp_path / "access_key.txt").write_text("")
    k = sv.access_key(str(tmp_path))
    assert len(k) >= 8 and (tmp_path / "access_key.txt").read_text().strip() == k
    (tmp_path / "access_key.txt").write_text("abc")
    assert sv.access_key(str(tmp_path)) != "abc"


def test_a_disk_error_is_remembered_not_raised(tmp_path):
    s = FieldSession(str(tmp_path))
    s.dir = "/proc/does-not-exist"
    s.log("phone", {"lat": 1})                                   # must not raise
    assert s.io_error and s.save_frame(1, b"x") is None


class Fake360(FakeCam):
    hfov = None

    def __init__(self):
        self.still = False

    def gravity(self, at_frame=False):
        return None, None, None

    def stopped(self, at_frame=False):
        return {"stopped": self.still}


def test_360_solves_early_while_stopped_but_not_while_moving(tmp_path):
    f = sv.Field(str(tmp_path), Fake360())
    f.interval_s = 20.0
    f.last_solve_t = time.time() - (sv.STOPPED_SOLVE_GAP_S + 1)
    assert not f._due()                                           # moving: wait for the 20 s cadence
    f.camera.still = True
    assert f._due()                                               # stopped: a frame now
    f.last_solve_t = time.time() - 1.0
    assert not f._due()                                           # but not more often than every STOPPED_SOLVE_GAP_S
    f.last_solve_t = time.time() - 21.0
    f.camera.still = False
    assert f._due()


def test_phone_speed_is_matched_to_the_exposure(tmp_path):
    f = sv.Field(str(tmp_path), Fake360())
    now = time.time()
    f.speeds.extend([(now - 5, 12.0), (now - 2, 0.0)])
    assert f._phone_speed_at(now - 4.6) == 12.0 and f._phone_speed_at(now - 1.5) == 0.0
    assert f._phone_speed_at(now - 30) is None
