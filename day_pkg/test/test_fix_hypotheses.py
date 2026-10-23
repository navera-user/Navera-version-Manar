"""day_pkg.fix_hypotheses (D17): alternative tracks — two agreeing far-off fixes never move the track, the
third and later fixes decide, the published sigma covers the alternative meanwhile."""
import math

from day_pkg.fix_consistency import FixConsistency
from day_pkg.fix_hypotheses import FixHypotheses
from day_pkg.vision_nav import VisionNavigator, _en, _move

P0 = (35.82, 10.61)


def _hyp():
    return FixHypotheses(FixConsistency(reacquire_check=False))     # the node default (reacquire_confirm off)


def test_a_wrong_pair_on_an_uncertain_track_is_not_believed_and_the_third_fix_decides():
    h = _hyp()
    pred = P0 + (45.0,)                                    # carried, +-45 m: a 120 m fix passes the 3-sigma gate
    wrong = _move(P0, 120.0, 0.0)
    assert h.cons.doubt(120.0, 45.0, 5.0, 150) is None
    for t in (10.0, 11.0):                                 # the same wrong place twice (moves with the vehicle)
        ok, why, sw = h.judge(t, *wrong, 5.0, 150, pred, None)
        assert not ok and not sw and "ambiguous" in why
    assert len(h.alts) == 1 and h.alts[0]["n"] == 2
    assert h.cover_sigma(11.5, 45.0) >= (120.0 + 2 * 5.0) / 3.0        # 3 sigma reach the alternative
    for t in (12.0, 13.0, 14.0):                           # the right fixes, on the carried track
        ok, _why, sw = h.judge(t, *_move(P0, 3.0, 2.0), 5.0, 150, pred, None)
        assert ok and not sw
        h.accepted()
    assert h.alts == []                                    # pruned: 3 fixes on the track, it scores below
    assert h.cover_sigma(14.5, 10.0) == 10.0


def test_a_real_jump_needs_three_agreeing_fixes_and_moves_the_track_on_the_third():
    h = _hyp()
    pred = P0 + (60.0,)
    real = _move(P0, 150.0, -40.0)
    assert not h.judge(10.0, *real, 6.0, 120, pred, None)[0]
    assert not h.judge(11.0, *real, 6.0, 120, pred, None)[0]           # two agreeing: still not a position
    ok, why, sw = h.judge(12.0, *real, 6.0, 120, pred, None)
    assert ok and sw and "re-acquired" in why
    h.accepted()
    # the old track is an alternative now, at minus the jump from the new one
    old = [a for a in h.alts if a["n"] == 0]
    assert old and math.hypot(old[0]["o"][0] + 150.0, old[0]["o"][1] - 40.0) < 1.0


def test_offsets_follow_the_track_when_a_believed_fix_moves_it():
    h = _hyp()
    pred = P0 + (40.0,)
    h.judge(10.0, *_move(P0, 200.0, 0.0), 5.0, 150, pred, None)
    ok, _w, _s = h.judge(11.0, *_move(P0, 20.0, 0.0), 5.0, 150, pred, None)
    assert ok
    h.accepted()                                           # the track is now 20 m east: the alternative 180 m
    assert abs(h.alts[0]["o"][0] - 180.0) < 1e-6
    h.clear()
    assert h.alts == [] and not h.hist


def test_beyond_far_max_sigma_the_far_rule_is_off():
    h = _hyp()
    pred = P0 + (300.0,)                                   # lost beyond 250 m: an in-gate fix re-acquires as before
    ok, _w, _s = h.judge(10.0, *_move(P0, 400.0, 0.0), 5.0, 150, pred, None)
    assert ok


def _res(p, inl=150, sig=4.0):
    return dict(accepted=True, predicted_lat=p[0], predicted_lon=p[1], inliers=inl, sigma_m=sig, spread=1.0)


def test_vision_nav_keeps_its_track_through_a_wrong_pair_and_states_the_doubt():
    cons = FixConsistency(reacquire_check=False)
    nav = VisionNavigator(max_speed_mps=60.0, consistency=cons, hypotheses=FixHypotheses(cons))
    nav.gps(0.0, *P0, sigma_m=5.0, heading_deg=90.0)
    nav.gps(2.0, *_move(P0, 40.0, 0.0), sigma_m=5.0, heading_deg=90.0)
    t = 12.0                                               # 10 s of carry: sigma ~ 40 m
    pred = nav.predict(t, 90.0)
    assert 30.0 < pred[2] < 3.0 * 120.0
    for k in range(2):
        tk = t + k
        p = nav.predict(tk, 90.0)
        assert not nav.update(tk, _res(_move(p[:2], 0.0, 120.0)), None, 90.0)
    lat, lon, sig, _m = nav.output(t + 1.2, 90.0)
    off = math.hypot(*_en((lat, lon), nav.predict(t + 1.2, 90.0)[:2]))
    assert off < 1.0 and sig >= 120.0 / 3.0                # on the carried track, sigma covering the pair
    p = nav.predict(t + 2.0, 90.0)
    assert nav.update(t + 2.0, _res(p[:2]), None, 90.0)    # the third, right, fix: believed
