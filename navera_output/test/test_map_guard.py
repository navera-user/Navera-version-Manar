"""navera_output.map_guard: the mission-area STATUSTEXT (when, what, how often)."""
from navera_output.map_guard import (INSIDE, NEAR_EDGE, OUTSIDE, SEVERITY_CRITICAL, SEVERITY_NOTICE,
                                     SEVERITY_WARNING, UNKNOWN, MapGuard)


def test_silent_inside_and_without_a_map():
    g = MapGuard()
    assert g.update(UNKNOWN, float("nan"), 0.0) is None
    assert g.update(INSIDE, 2000.0, 1.0) is None
    assert g.update(INSIDE, 1500.0, 100.0) is None


def test_near_edge_warns_at_once_then_every_repeat():
    g = MapGuard(repeat_s=30.0)
    g.update(INSIDE, 900.0, 0.0)
    sev, text = g.update(NEAR_EDGE, 420.4, 1.0)
    assert sev == SEVERITY_WARNING and "420 m" in text and len(text) <= 50
    assert g.update(NEAR_EDGE, 400.0, 10.0) is None
    assert g.update(NEAR_EDGE, 300.0, 31.5)[0] == SEVERITY_WARNING


def test_outside_is_critical_and_back_inside_is_said_once():
    g = MapGuard()
    g.update(NEAR_EDGE, 100.0, 0.0)
    sev, text = g.update(OUTSIDE, -250.0, 2.0)
    assert sev == SEVERITY_CRITICAL and "250 m OUTSIDE" in text and len(text) <= 50
    assert g.update(INSIDE, 800.0, 3.0) == (SEVERITY_NOTICE, "NAVERA: back inside the map")
    assert g.update(INSIDE, 900.0, 4.0) is None
