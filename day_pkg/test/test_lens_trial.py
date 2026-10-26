"""A lens fitted in flight is on trial: kept for the camera only if the next GPS checks are no worse,
put back when they are worse or when the GPS is lost first (day_subscriber._lens_check / _lens_trial_end)."""
import json
from collections import deque
from types import MethodType, SimpleNamespace

from day_pkg.nodes.day_subscriber import DaySubscriber
from navera_common import state_store

OLD_K = [700.0, 0, 640, 0, 700.0, 360, 0, 0, 1]
NEW_K = [760.0, 0, 640, 0, 760.0, 360, 0, 0, 1]


class _Log:
    def __init__(self):
        self.lines = []

    def warn(self, m):
        self.lines.append(m)

    error = info = warn


def node():
    n = SimpleNamespace(_check_errs=deque([10.0, 11.0, 9.0, 12.0, 10.0], maxlen=12), lens_trial_checks=8, _lens_fx=OLD_K[0],
                        lens_trial_margin=1.1, sent=[], log=_Log())
    n.pub_lens = SimpleNamespace(publish=lambda m: n.sent.append(json.loads(m.data)))
    n.get_logger = lambda: n.log
    n._lens_check = MethodType(DaySubscriber._lens_check, n)
    n._lens_trial_end = MethodType(DaySubscriber._lens_trial_end, n)
    n._lens_trial = dict(doc={"lens_key": "cam1", "lens": {"camera_matrix": NEW_K}}, before=[],
                         after=[], K=NEW_K, previous={"lens_key": "cam1", "revert": True, "lens": {"camera_matrix": OLD_K}})
    return n


def meta(K):
    return {"camera_lens": {"K": K, "K_out": K, "D": [], "model": "pinhole", "size": [1280, 720]}}


def test_a_better_lens_is_kept_for_the_camera(tmp_path, monkeypatch):
    """The camera alternates the two lenses: both are judged on the same stretch of flight."""
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    n = node()
    for _ in range(8):
        n._lens_check(6.0, meta(NEW_K))
        assert n._lens_trial is not None                 # not decided before both have their checks
    for _ in range(8):
        n._lens_check(10.0, meta(OLD_K))
    assert n._lens_trial is None and n.sent[-1]["keep"]
    assert state_store.load("lens_auto_cam1", 1e9)["verified"]["after_m"] == 6.0
    assert list(n._check_errs) == [6.0] * 8


def test_a_worse_lens_is_put_back_and_not_kept(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    n = node()
    for _ in range(8):
        n._lens_check(15.0, meta(NEW_K))
        n._lens_check(10.0, meta(OLD_K))
    assert n._lens_trial is None and n.sent == [n.sent[0]] and n.sent[0]["revert"]
    assert state_store.load("lens_auto_cam1", 1e9) is None
    n._lens_check(40.0, meta(NEW_K))                    # a late frame of the refused lens: not the old lens' record
    n._lens_check(9.0, meta(OLD_K))
    assert list(n._check_errs)[-1] == 9.0 and 40.0 not in n._check_errs


def test_a_phase_change_during_the_trial_does_not_decide_it(tmp_path, monkeypatch):
    """The cruise doubles every error (the camera delay x the speed): both lenses see it alike."""
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    n = node()
    for e in (5.0, 5.0, 5.0, 5.0, 20.0, 20.0, 20.0, 20.0):     # hover, then cruise
        n._lens_check(e * 0.8, meta(NEW_K))
        n._lens_check(e, meta(OLD_K))
    assert n.sent[-1].get("keep")


def test_the_gps_lost_during_the_trial_puts_the_old_lens_back(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    n = node()
    n._lens_check(6.0, meta(NEW_K))
    n._lens_trial_end("GPS lost")
    assert n._lens_trial is None and n.sent[0]["revert"] and state_store.load("lens_auto_cam1", 1e9) is None
