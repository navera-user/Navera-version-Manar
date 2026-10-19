"""NightTracker: anchor, motion gate and dead reckoning of the night pipeline (no ROS)."""
from navera_common.geo import dead_reckon, haversine_m

from night_pkg.nodes.night_tracker import NightTracker

LAT, LON = 35.8280, 10.6320


def _east(m):
    return dead_reckon(LAT, LON, 90.0, 1.0, m)


def test_no_anchor_until_known():
    tr = NightTracker()
    assert not tr.has_anchor and tr.search_centre(None, None, None) is None
    assert tr.gate(LAT, LON, 0.0) is None       # nothing to gate against
    tr.set_known(LAT, LON, 0.0)
    assert tr.has_anchor and tr.search_centre(None, None, None) == (LAT, LON)


def test_gate_reach_grows_with_time():
    tr = NightTracker(max_speed_mps=30.0, gate_margin_m=30.0)
    tr.set_known(LAT, LON, 0.0)
    far = _east(200.0)
    assert tr.gate(*far, 1.0) is not None       # 200 m in 1 s: reach 60 m
    assert tr.gate(*far, 6.0) is None           # reach 210 m


def test_accepted_fix_becomes_anchor():
    tr = NightTracker()
    tr.set_known(LAT, LON, 0.0)
    p = _east(40.0)
    assert tr.offer(*p, 1.0) is None
    assert tr.anchor == p and tr.anchor_time == 1.0 and tr.last_measured_time == 1.0


def test_search_centre_carried_along_measured_motion():
    tr = NightTracker()
    tr.set_known(LAT, LON, 100.0)
    c = tr.search_centre(102.0, 90.0, 25.0)
    assert abs(haversine_m(LAT, LON, *c) - 50.0) < 0.5
    assert tr.search_centre(102.0, None, None) == (LAT, LON)   # no measured motion: the anchor


def test_coast_only_with_measured_motion_and_for_a_while():
    tr = NightTracker(max_dead_reckon_s=10.0)
    tr.set_known(LAT, LON, 0.0)
    assert tr.coast(1.0, None, None) is None
    p = tr.coast(2.0, 90.0, 20.0)
    assert p is not None and abs(haversine_m(LAT, LON, *p) - 40.0) < 0.5
    assert tr.coast(11.0, 90.0, 20.0) is None   # 11 s after the last measured position


def test_reset_forgets_the_track():
    tr = NightTracker()
    tr.set_known(LAT, LON, 0.0)
    tr.note_gps_lost(1.0)
    tr.reset()
    assert not tr.has_anchor and tr.seconds_since_gps_lost(5.0) == float("inf")
