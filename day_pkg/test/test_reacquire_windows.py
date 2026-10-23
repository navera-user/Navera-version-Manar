"""Re-acquiring after a gap (F32): the uncertainty circle covered with small windows, nearest first."""
import math
import random
from types import MethodType, SimpleNamespace

import numpy as np

from day_pkg.nodes.day_subscriber import DaySubscriber
from day_pkg.reacquire import WindowScan, cover_windows
from day_pkg.vision_nav import _en


def test_the_windows_cover_the_whole_disc():
    rng = random.Random(1)
    for radius, w in [(600.0, 150.0), (1500.0, 150.0), (300.0, 100.0)]:
        cover = cover_windows(radius, w)
        for _ in range(3000):
            a, r = rng.random() * 2 * math.pi, radius * math.sqrt(rng.random())
            p = (r * math.cos(a), r * math.sin(a))
            assert min(math.hypot(p[0] - x, p[1] - y) for x, y in cover) <= w + 1e-6


def test_the_carried_position_first_then_by_distance():
    cover = cover_windows(600.0, 150.0)
    d = [math.hypot(*c) for c in cover]
    assert cover[0] == (0.0, 0.0) and d == sorted(d) and len(cover) == 31


def test_a_circle_within_one_window_is_one_window():
    assert cover_windows(100.0, 150.0) == [(0.0, 0.0)]


def test_the_scan_goes_on_from_frame_to_frame_and_wraps():
    cover = [(0.0, 0.0)] + [(float(i), 0.0) for i in range(1, 7)]
    s = WindowScan()
    seen = []
    for _ in range(3):
        pick = s.pick(cover, 3)
        assert pick[0] == (0.0, 0.0) and len(pick) == 3
        seen += pick[1:]
    assert sorted(set(seen)) == cover[1:]          # 6 others in 3 frames of 2


def _node(accept_at=None, inliers=60, per_frame=4):
    """A node whose matcher accepts only a window holding accept_at (lat, lon)."""
    calls = []

    def locate(img, prior, r, mpp, **kw):
        calls.append((prior, r))
        ok = accept_at is not None and math.hypot(*_en(accept_at, prior)) <= r
        return {"accepted": ok, "inliers": inliers if ok else 3, "reason": None if ok else "3 matches"}
    n = SimpleNamespace(local=SimpleNamespace(locate=locate), local_min_radius_m=80.0, local_max_radius_m=600.0,
                        reacquire_windows=True, reacquire_window_frac=0.65, reacquire_per_frame=per_frame,
                        reacquire_max_radius_m=1500.0, reacquire_min_inliers=25, _scan=WindowScan(),
                        reacquire_budget_s=10.0, heading_search=False,
                        _scale_tol=lambda m: 0.15, _match_heading_kw=lambda m: {}, _hfov=lambda m: 77.0,
                        _expected_tilt=lambda m: 0.0, _heading_search_kw=lambda: {})
    for name in ("_locate_search", "_reacquire_window_m", "_window_gate", "_search_cap_m"):
        setattr(n, name, MethodType(getattr(DaySubscriber, name), n))
    return n, calls


IMG = np.zeros((760, 1344, 3), np.uint8)       # 0.3 m/px: half diagonal 232 m, window 150 m
C = (35.87, 10.53)


def test_a_narrow_circle_is_one_call_as_before():
    n, calls = _node(accept_at=C)
    assert n._locate_search(IMG, C, 120.0, 0.3, {})["accepted"] and calls == [(C, 120.0)]


def test_a_wide_circle_tries_the_carried_position_first():
    n, calls = _node(accept_at=C)
    res = n._locate_search(IMG, C, 1200.0, 0.3, {})
    assert res["accepted"] and len(calls) == 1 and calls[0][0] == C and abs(calls[0][1] - 150.8) < 1
    assert res["radius_m"] == 1200.0 and res["windows_tried"] == 1


def test_the_place_off_the_carried_position_is_found_in_later_frames():
    from day_pkg.vision_nav import _move
    target = _move(C, 500.0, -300.0)
    n, calls = _node(accept_at=target)
    found = None
    for frame in range(20):
        res = n._locate_search(IMG, C, 1200.0, 0.3, {})
        if res["accepted"]:
            found = frame
            break
    assert found is not None and found > 0
    assert all(r < 160 for _, r in calls)          # never one wide window


def test_an_off_centre_window_needs_more_inliers():
    from day_pkg.vision_nav import _move
    n, _ = _node(accept_at=_move(C, 300.0, 0.0), inliers=20)
    for _ in range(15):
        res = n._locate_search(IMG, C, 1200.0, 0.3, {})
        assert not res["accepted"]
    assert "re-acquisition window" in res["reason"] or "windows of" in res["reason"]


def test_the_carried_position_window_keeps_the_usual_threshold():
    n, _ = _node(accept_at=C, inliers=14)
    assert n._locate_search(IMG, C, 1200.0, 0.3, {})["accepted"]


def test_height_retries_only_try_the_carried_position():
    n, calls = _node(accept_at=None)
    n._locate_search(IMG, C, 1200.0, 0.3, {}, windows=False)
    assert len(calls) == 1 and calls[0][0] == C


def test_off_is_the_former_single_window():
    n, calls = _node(accept_at=None)
    n.reacquire_windows = False
    n._locate_search(IMG, C, 600.0, 0.3, {})
    assert calls == [(C, 600.0)] and n._search_cap_m() == 600.0


def test_the_jump_gate_allows_a_dead_reckoned_anchor_its_own_uncertainty():
    n = SimpleNamespace(gate_k=3.0, gate_margin_m=250.0, _anchor_sigma=430.0, _fix_sigma=lambda r, m: 12.0)
    margin = MethodType(DaySubscriber._jump_margin_m, n)
    assert margin({}, {}) > 1200.0
    n._anchor_sigma = 15.0                          # a measured anchor: as before
    assert abs(margin({}, {}) - 3.0 * math.hypot(15.0, 12.0)) < 1e-9
    n._anchor_sigma = 120.0                         # gate_margin_m still caps a moderate one
    assert margin({}, {}) == 360.0
    n._anchor_sigma, n._fix_sigma = 90.0, (lambda r, m: 30.0)
    assert margin({}, {}) == 270.0


def test_the_heading_search_runs_in_the_carried_position_window_only():
    from day_pkg.vision_nav import _move
    seen = []
    n, _ = _node(accept_at=None)
    n._heading_search_kw = lambda meta=None: {"heading_search": True}
    n.local.locate = lambda img, prior, r, mpp, **kw: seen.append(kw.get("heading_search")) or \
        {"accepted": False, "inliers": 0, "reason": "none"}
    n._locate_search(IMG, C, 1200.0, 0.3, {})
    assert seen == [True, False, False, False]
    assert _move(C, 0.0, 0.0) == C


def test_no_heading_search_when_the_frame_states_its_heading():
    seen = []
    n, _ = _node(accept_at=None)
    n._heading_search_kw = lambda meta=None: {"heading_search": True}
    n._match_heading_kw = lambda m: {"heading_deg": 45.0, "heading_tol_deg": 20.0}
    n.local.locate = lambda img, prior, r, mpp, **kw: seen.append(kw.get("heading_search")) or \
        {"accepted": False, "inliers": 0, "reason": "none"}
    n._locate_search(IMG, C, 1200.0, 0.3, {})
    n._locate_search(IMG, C, 1200.0, 0.3, {}, windows=False)
    assert seen == [False] * 5
    seen.clear()
    n._locate_search(IMG, C, 100.0, 0.3, {})          # tracked (one window): the search as configured
    assert seen == [True]


def test_a_frame_stops_trying_windows_past_its_time_budget():
    import time
    n, calls = _node(accept_at=None)
    n.reacquire_budget_s = 0.05
    slow = n.local.locate
    n.local.locate = lambda *a, **k: time.sleep(0.06) or slow(*a, **k)
    n._locate_search(IMG, C, 1200.0, 0.3, {})
    assert len(calls) == 1
