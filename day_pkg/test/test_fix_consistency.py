"""day_pkg.fix_consistency (F16 / D17): the doubt rule against the carried position and the confirmation
of a doubted fix by a second one; VisionNavigator with it."""
import math

from day_pkg.fix_consistency import FixConsistency
from day_pkg.vision_nav import VisionNavigator, _move

P0 = (35.82, 10.61)


def test_a_strong_fix_beyond_3_sigma_is_doubted():
    c = FixConsistency()                          # strong_gate_k 3 since 2026-10-22 (was 6)
    assert c.doubt(4.0 * math.hypot(10, 5), 10.0, 5.0, inliers=180) is not None
    assert c.doubt(2.5 * math.hypot(10, 5), 10.0, 5.0, inliers=180) is None
    old = FixConsistency(strong_gate_k=6.0)
    assert old.doubt(4.0 * math.hypot(10, 5), 10.0, 5.0, inliers=180) is None


def test_weak_fixes_while_lost_are_doubted_and_the_reacquisition_check_is_optional():
    c = FixConsistency(reacquire_check=False)
    assert "weak" in c.doubt(20.0, 120.0, 10.0, inliers=25)
    assert c.doubt(150.0, 120.0, 10.0, inliers=80) is None            # inside 3 sigma of a lost carry
    r = FixConsistency(reacquire_check=True)
    assert "re-acquisition" in r.doubt(150.0, 120.0, 10.0, inliers=80)
    assert r.doubt(40.0, 120.0, 10.0, inliers=80) is None             # close to the carry: believed


def test_a_doubted_fix_is_confirmed_by_a_second_agreeing_one_only():
    c = FixConsistency(confirm_n=2)                                    # the rule of 2026-10-22
    a = _move(P0, 300.0, 0.0)
    assert not c.confirm(10.0, *a, 5.0, (20.0, 0.0), lost=False)
    b = _move(a, 20.0 * 1.0, 3.0)                                      # 1 s later, carried 20 m east
    assert c.confirm(11.0, *b, 5.0, (20.0, 0.0), lost=False)
    assert c.pending is None and c.confirmed == 1
    # disagreeing second fix: not confirmed, it becomes the pending one
    assert not c.confirm(20.0, *a, 5.0, None, lost=False)
    assert not c.confirm(21.0, *_move(a, 200.0, 0.0), 5.0, None, lost=False)
    # too late (window 6 s; 20 s while lost)
    c.clear()
    assert not c.confirm(30.0, *a, 5.0, None, lost=False)
    assert not c.confirm(40.0, *a, 5.0, None, lost=False)
    assert c.confirm(55.0, *a, 5.0, None, lost=True)


def _res(p, inl=150, sig=4.0):
    return dict(accepted=True, predicted_lat=p[0], predicted_lon=p[1], inliers=inl, sigma_m=sig, spread=1.0)


def test_vision_nav_with_the_rules_refuses_a_confident_wrong_fix_then_confirms_a_real_jump():
    """A 180-inlier fix 4 sigma off: believed by the old rules, doubted by the new; two in a row agree."""
    for cons, believed in ((None, True), (FixConsistency(), False)):
        nav = VisionNavigator(max_speed_mps=40.0, consistency=cons)
        nav.gps(0.0, *P0, sigma_m=5.0, heading_deg=90.0)
        nav.gps(2.0, *_move(P0, 40.0, 0.0), sigma_m=5.0, heading_deg=90.0)
        pred = nav.predict(3.0, 90.0)
        off = 4.0 * math.hypot(pred[2], 4.0)
        wrong = _move(pred[:2], 0.0, off)
        assert nav.update(3.0, _res(wrong), None, 90.0) is believed
    # the next frame agrees with it (carried 4 m by the 20 m/s velocity): still doubted on a good
    # track (D17: two frames in a row are not independent); the third agreeing one is believed
    assert not nav.update(3.2, _res(_move(wrong, 4.0, 0.0)), None, 90.0)
    assert nav.update(3.4, _res(_move(wrong, 8.0, 0.0)), None, 90.0)
    assert "re-acquired" in nav.last_reason


def test_d17_two_wrong_in_a_row_at_the_same_place_are_not_believed_on_a_good_track():
    c = FixConsistency()
    a = _move(P0, 300.0, 0.0)
    assert not c.confirm(10.0, *a, 5.0, (20.0, 0.0), lost=False)
    assert not c.confirm(11.0, *_move(a, 20.0, 0.0), 5.0, (20.0, 0.0), lost=False)   # agrees: 2 in a row
    c.clear()                                                          # a right fix the gate believed
    assert not c.confirm(12.0, *_move(a, 40.0, 0.0), 5.0, (20.0, 0.0), lost=False)
    assert c.confirmed == 0
    # three in a row, each agreeing with the previous one carried: a real jump, believed
    assert not c.confirm(13.0, *_move(a, 60.0, 0.0), 5.0, (20.0, 0.0), lost=False)
    assert c.confirm(14.0, *_move(a, 80.0, 0.0), 5.0, (20.0, 0.0), lost=False)
    assert c.confirmed == 1 and c.pending is None
    # a disagreeing one in the middle restarts the run
    assert not c.confirm(20.0, *a, 5.0, None, lost=False)
    assert not c.confirm(21.0, *a, 5.0, None, lost=False)
    assert not c.confirm(22.0, *_move(a, 300.0, 0.0), 5.0, None, lost=False)
    assert not c.confirm(23.0, *_move(a, 300.0, 0.0), 5.0, None, lost=False)
    assert c.confirm(24.0, *_move(a, 300.0, 0.0), 5.0, None, lost=False)


def test_d17_reacquisition_after_a_gap_still_needs_two_only():
    c = FixConsistency()
    a = _move(P0, 300.0, 0.0)
    assert not c.confirm(100.0, *a, 8.0, None, lost=True)
    assert c.confirm(115.0, *a, 8.0, None, lost=False)                # the run began lost: 2 suffice
    c.clear()
    assert not c.confirm(200.0, *a, 8.0, None, lost=True)
    assert not c.confirm(230.0, *a, 8.0, None, lost=True)              # beyond confirm_lost_s (20 s)
    assert c.confirm(240.0, *a, 8.0, None, lost=True)
