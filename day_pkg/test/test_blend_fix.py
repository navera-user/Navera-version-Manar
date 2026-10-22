"""day_subscriber._blend_fix (F20 / F23 / D17): a local fix averaged with the carried position by their
sigmas, only when the carry turns with a heading and the fix is not a re-acquisition; and
_check_local_fix through day_pkg.fix_consistency."""
import math
from types import SimpleNamespace

from day_pkg.fix_consistency import FixConsistency
from day_pkg.nodes.day_subscriber import DaySubscriber
from day_pkg.vision_nav import _en, _move

P0 = (35.82, 10.61)


def _node(heading=90.0, pred_sigma=10.0, fix_sigma=10.0, common=0.0):
    n = DaySubscriber.__new__(DaySubscriber)
    n.blend_fixes = True
    n._carry_heading = lambda meta: (heading, 1.0)
    n._predicted = lambda meta: (P0[0], P0[1], pred_sigma)
    n._fix_sigma = lambda result, meta: fix_sigma
    n._fix_sigma_common = lambda result, meta: common
    return n


def test_equal_sigmas_meet_half_way_with_a_smaller_sigma():
    n = _node()
    fix = _move(P0, 40.0, 0.0)
    st = {}
    lat, lon, sig = n._blend_fix(*fix, {}, {}, st)
    de, dn = _en((lat, lon), P0)
    assert math.isclose(de, 20.0, abs_tol=0.1) and abs(dn) < 0.1
    assert math.isclose(sig, 10.0 / math.sqrt(2), rel_tol=1e-6) and st["blend"]["weight"] == 0.5


def test_the_error_common_to_fix_and_carry_is_not_averaged_down():
    """F38: the unknown delay's and the mount's error is in every fix, so in the carry made of them —
    it sets neither the weight nor shrinks: sigma = hypot(sqrt(k) x the fix's own part, the common part)."""
    fix = _move(P0, 40.0, 0.0)
    st = {}
    lat, lon, sig = _node(pred_sigma=10.0, fix_sigma=10.0, common=8.0)._blend_fix(*fix, {}, {}, st)
    assert st["blend"]["weight"] == 0.5 and st["blend"]["common_sigma_m"] == 8.0
    assert math.isclose(sig, math.hypot(math.sqrt(0.5) * 6.0, 8.0), rel_tol=1e-6) and sig > 8.0
    # a fix whose own error is small against a carry that is mostly the common error: the fix wins
    lat, lon, sig = _node(pred_sigma=12.0, fix_sigma=8.5, common=8.0)._blend_fix(*fix, {}, {}, {})
    assert _en((lat, lon), P0)[0] > 0.85 * 40.0 and sig >= 8.0
    # repeated blending never states less than the common part (it shrank to 5-9 m for 13-20 m errors)
    s = 10.0
    for _ in range(50):
        s = _node(pred_sigma=s + 1.0, fix_sigma=10.0, common=8.0)._blend_fix(*fix, {}, {}, {})[2]
    assert s >= 8.0


def test_no_blend_without_heading_on_reacquisition_or_when_off():
    fix = _move(P0, 40.0, 0.0)
    assert _node(heading=None)._blend_fix(*fix, {}, {}, {}) is None
    assert _node()._blend_fix(*fix, {}, {}, {"reacquired": "x"}) is None
    n = _node()
    n.blend_fixes = False
    assert n._blend_fix(*fix, {}, {}, {}) is None


def test_check_local_fix_uses_the_consistency_rules(monkeypatch):
    n = DaySubscriber.__new__(DaySubscriber)
    n.map_bias = SimpleNamespace(bias=lambda p: (0.0, 0.0))
    n.min_spread = 0.25
    n.consistency = FixConsistency()
    n._predicted = lambda meta: (P0[0], P0[1], 10.0)
    n._fix_sigma = lambda result, meta: 4.0
    n.track = SimpleNamespace(velocity=lambda t: None)
    res = {"inliers": 180, "spread": 1.0}
    far = _move(P0, 0.0, 4.0 * math.hypot(10.0, 4.0))      # 4 sigma: was believed with strong_gate_k 6
    _, _, why = n._check_local_fix(res, {}, *far, {})
    assert why is not None and "rejected" in why
    st = {}
    _, _, why = n._check_local_fix(res, {}, *_move(far, 3.0, 0.0), st)   # the next one agrees
    assert why is None and "reacquired" in st
    _, _, why = n._check_local_fix(res, {}, *_move(P0, 5.0, 0.0), {})
    assert why is None and n.consistency.pending is None
