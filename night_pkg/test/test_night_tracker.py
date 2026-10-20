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
    tr = NightTracker(max_speed_mps=30.0, gate_margin_m=30.0, max_single_jump_m=None)
    tr.set_known(LAT, LON, 0.0)
    far = _east(200.0)
    assert tr.gate(*far, 1.0) is not None       # 200 m in 1 s: reach 60 m
    assert tr.gate(*far, 6.0) is None           # reach 210 m
    tr = NightTracker(max_speed_mps=30.0, gate_margin_m=30.0)
    tr.set_known(LAT, LON, 0.0)
    assert "agreeing fixes" in tr.gate(*far, 6.0)   # > max_single_jump_m (150 m): not alone


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


def _fly(tr, t0, t1, wrong_at=(), wrong_m=300.0, start=(LAT, LON), lost_until=None):
    """Fly east at 25 m/s from `start` at t0; a correct fix (exact) each second from t0 to
    t1, a wrong one (wrong_m north) at the seconds in wrong_at; no fix before lost_until.
    Returns the published errors (None: no position)."""
    errs = []
    for t in range(t0, t1):
        truth = dead_reckon(start[0], start[1], 90.0, 25.0, t - t0) if t > t0 else start
        pub = None
        if lost_until is None or t >= lost_until:
            fix = dead_reckon(truth[0], truth[1], 0.0, 1.0, wrong_m) if t in wrong_at else truth
            if tr.offer(fix[0], fix[1], float(t), 90.0, 25.0) is None:
                pub = tr.anchor
        if pub is None:
            pub = tr.coast(float(t), 90.0, 25.0)
        errs.append(None if pub is None else haversine_m(pub[0], pub[1], *truth))
    return errs


def test_b16_one_wrong_fix_after_a_long_gap_does_not_lock_the_track():
    """B16: after a gap (dead reckoning expired) the reach is wide; a wrong fix used to
    become the anchor and dead reckoning from it kept the reach tight, refusing every
    correct fix for 30+ s. Now a jump > max_single_jump_m needs agreeing fixes."""
    tr = NightTracker(max_dead_reckon_s=30.0)
    tr.set_known(LAT, LON, 0.0)
    errs = _fly(tr, 0, 120, wrong_at={60}, lost_until=60)
    after = errs[60:]
    assert all(e is None or e < 50.0 for e in after)          # the wrong fix never published
    assert sum(e is None for e in after) <= 5                  # re-acquired within 5 frames
    assert all(e is not None and e < 1.0 for e in after[6:])


def test_b16_wrong_anchor_is_left_after_agreeing_fixes():
    """A wrong anchor (here forced) is replaced once reacquire_n correct fixes agree."""
    tr = NightTracker(max_single_jump_m=None)
    tr.set_known(LAT, LON, 0.0)
    errs = _fly(tr, 0, 80, wrong_at={60}, lost_until=60)       # wrong fix let in (no jump limit)
    assert errs[60] > 250.0
    assert all(e is not None and e < 1.0 for e in errs[60 + 4:])
    assert tr.reacquired_from is None                          # later frames: normal tracking


def test_confirmed_track_needs_more_agreeing_contrary_fixes():
    """While tracking (each fix agrees with the last), 3 agreeing wrong fixes do not move
    the anchor; 5 would (reacquire_confirmed_n)."""
    tr = NightTracker()
    tr.set_known(LAT, LON, 0.0)
    errs = _fly(tr, 0, 40, wrong_at={20, 21, 22})
    assert max(e for e in errs if e is not None) < 1.0
    tr = NightTracker()
    tr.set_known(LAT, LON, 0.0)
    errs = _fly(tr, 0, 40, wrong_at=set(range(20, 25)))
    assert max(e for e in errs if e is not None) < 1.0         # D22: 5 do not outnumber 15 agreeing
    tr = NightTracker()
    tr.set_known(LAT, LON, 0.0)
    errs = _fly(tr, 0, 50, wrong_at=set(range(20, 30)))
    assert errs[29] > 250.0                                    # documented limit: a long burst moves it
    assert all(e < 1.0 for e in errs[38:])


def test_a_wrong_burst_on_a_fresh_track_is_outnumbered_but_a_gap_resets_it():
    """D22: a consensus that starts right after the last measured fix must outnumber the
    track's own recent support; after a gap (dead reckoning) the plain counts apply (B16)."""
    tr = NightTracker(support_cap=15)
    tr.set_known(LAT, LON, 0.0)
    errs = _fly(tr, 0, 30, wrong_at=set(range(20, 26)))        # 6 wrong, fresh, support 15
    assert max(e for e in errs if e is not None) < 1.0
    tr = NightTracker(max_single_jump_m=None)
    tr.set_known(LAT, LON, 0.0)
    errs = _fly(tr, 0, 80, wrong_at={60}, lost_until=60)       # B16 path unchanged
    assert all(e is not None and e < 1.0 for e in errs[64:])


def test_reset_forgets_the_track():
    tr = NightTracker()
    tr.set_known(LAT, LON, 0.0)
    tr.note_gps_lost(1.0)
    tr.reset()
    assert not tr.has_anchor and tr.seconds_since_gps_lost(5.0) == float("inf")
