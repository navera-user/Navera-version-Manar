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
    c = FixConsistency()
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
    # the next frame agrees with it (carried 4 m by the 20 m/s velocity): believed, re-acquired
    assert nav.update(3.2, _res(_move(wrong, 4.0, 0.0)), None, 90.0)
    assert "re-acquired" in nav.last_reason
