"""Tests of navera_lite/guard.py, the jump gate (given in 09). Written for the course; it is not NAVERA code.

Run from the lesson folder:  python3 -m pytest navera_lite/tests/test_guard.py -q
"""
from navera_lite.estimate import Estimate
from navera_lite.geo import offset
from navera_lite.guard import JumpGate, gate_ok
from navera_lite.settings import DEFAULTS

START = (35.8256, 10.6084)


def fix(e_m, t_s):
    lat, lon = offset(START[0], START[1], e_m, 0.0)
    return Estimate("gps", lat, lon, t_s)


def test_gate_ok_is_mission_01s_rule():
    assert gate_ok((0, 0), (120, 0), 1.0, 100.0, 50.0) is True
    assert gate_ok((0, 0), (500, 0), 1.0, 100.0, 50.0) is False
    assert gate_ok((0, 0), (150, 0), 1.0, 100.0, 50.0) is True               # exactly on the limit
    assert gate_ok((0, 0), (60, 0), -1.0, 100.0, 50.0) is False              # negative time counts as 0


def test_lesson_1_table_five_refused():
    g = JumpGate(DEFAULTS)
    verdicts = [g.check(fix(e, t))[0] for t, e in enumerate([0, 500, 500, 500, 500, 500, 500, 900])]
    assert verdicts == [True, False, False, False, False, True, True, False]
    assert verdicts.count(False) == 5                                         # count_refused of mission 01


def test_a_refused_fix_never_becomes_trusted():
    g = JumpGate(DEFAULTS)
    assert g.check(fix(0.0, 0.0)) == (True, "first fix")
    ok, why = g.check(fix(5000.0, 1.0))
    assert not ok and why == "jump 5000 m > 150 m in 1.0 s"
    assert g.check(fix(120.0, 2.0)) == (True, "within the gate")             # judged from the fix at 0 m
    g.reset()
    assert g.check(fix(5000.0, 3.0)) == (True, "first fix")
