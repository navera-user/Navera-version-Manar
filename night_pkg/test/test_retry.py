"""NightLocalizer.localize retries: heading offsets after a failed map check, then heights; a
footprint too small for the stated height is only retried higher."""
import types

from night_pkg.nodes.night_localizer import NightLocalizer


def _stub(good_heading=None, good_alt=None, small_below=None):
    calls = []

    def once(self, img, lat, lon, alt, hfov, heading, require_scale):
        calls.append((heading, round(alt, 1)))
        if small_below is not None and alt < small_below:
            return {"success": False, "reason": "camera footprint too small for night matching", "dt_ms": 1.0}
        ok = (good_heading is None or heading == good_heading) and (good_alt is None or abs(alt - good_alt) < 1e-6)
        return {"success": ok, "map_check_failed": not ok, "reason": "" if ok else "map check failed", "dt_ms": 1.0}
    return types.SimpleNamespace(_localize_once=types.MethodType(once, object()), recheck_offset_m=0), calls


def _run(stub, **kw):
    return NightLocalizer.localize(stub, None, 0.0, 0.0, altitude_m=500.0, hfov_deg=60.0, heading_deg=100.0, **kw)


def test_heading_then_height_retries_find_the_fix():
    s, calls = _stub(good_heading=100.0, good_alt=600.0)
    r = _run(s, heading_retry_deg=(-10, 10), height_retry=(0.1, 0.2))
    assert r["success"] and r["height_correction"] == 0.2 and calls[-1] == (100.0, 600.0)
    assert [c[0] for c in calls[1:3]] == [90.0, 110.0]


def test_footprint_too_small_is_only_tried_higher():
    s, calls = _stub(small_below=520.0, good_alt=550.0)
    r = _run(s, heading_retry_deg=(-10, 10), height_retry=(0.1, -0.1, 0.2))
    assert r["success"] and [c[1] for c in calls] == [500.0, 550.0]


def test_no_retry_lists_no_retry():
    s, calls = _stub(good_alt=600.0)
    r = _run(s)
    assert not r["success"] and len(calls) == 1
