"""D18: the heading search runs when the heading is uncertain (none known, or a failing streak), and stops
at once on a uniform frame (rotating it adds no texture)."""
from types import SimpleNamespace

from day_pkg.learned_matcher import LearnedMatcher
from day_pkg.nodes.day_subscriber import DaySubscriber


def _node(heading=None, rejects=0, after=3, forced=False):
    n = DaySubscriber.__new__(DaySubscriber)
    n.local = SimpleNamespace(heading_search_deg=30.0)
    n.heading_search, n.heading_search_after, n._rejects_in_row = forced, after, rejects
    n._match_heading_kw = lambda meta: {"heading_deg": heading, "heading_tol_deg": 20.0}
    n._last_frame = (0.0, {})
    return n


def test_search_when_no_heading_or_after_a_failing_streak_only():
    assert _node(heading=None)._heading_search_kw({}) == {"heading_search": True}
    assert _node(heading=120.0)._heading_search_kw({}) == {}
    assert _node(heading=120.0, rejects=3)._heading_search_kw() == {"heading_search": True}
    assert _node(heading=None, after=0)._heading_search_kw({}) == {}               # automatic search off
    assert _node(heading=120.0, after=0, forced=True)._heading_search_kw({}) == {"heading_search": True}
    n = _node(heading=None)
    n.local = SimpleNamespace()                                                     # SIFT matcher: no search
    assert n._heading_search_kw({}) == {}


def test_a_uniform_frame_is_not_tried_at_every_heading():
    calls = []

    def locate_learned(*args):
        calls.append(args[6])
        return {"accepted": False, "reason": "too few features in the frame (uniform ground, blur, darkness)",
                "inliers": 0}
    m = SimpleNamespace(_heading=None, HEADING_MEMORY_S=10.0, heading_search_deg=30.0, HEADING_SEARCH_MIN_INLIERS=25,
                        _locate_learned=locate_learned)
    m.heading_search_order = lambda h: LearnedMatcher.heading_search_order(m, h)
    res = LearnedMatcher._locate_heading_search(m, None, (0.0, 0.0), 300.0, 1.0, None, None, 10.0, None)
    assert calls == [10.0] and not res["accepted"] and res["heading_tried"] == [10]
