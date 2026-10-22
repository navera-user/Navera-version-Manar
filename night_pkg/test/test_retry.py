"""NightLocalizer.localize retries: heading offsets after a failed map check, then heights; a
footprint too small for the stated height is only retried higher.
"""
import types

from night_pkg.nodes.night_localizer import FIRST_MIN_CONF, NightLocalizer, RETRY_GATE_DEFAULTS, retry_evidence_ok


def _stub(good_heading=None, good_alt=None, small_below=None):
    calls = []

    def once(self, img, lat, lon, alt, hfov, heading, require_scale):
        calls.append((heading, round(alt, 1)))
        if small_below is not None and alt < small_below:
            return {"success": False, "reason": "camera footprint too small for night matching", "dt_ms": 1.0}
        ok = (good_heading is None or heading == good_heading) and (good_alt is None or abs(alt - good_alt) < 1e-6)
        return {"success": ok, "map_check_failed": not ok, "reason": "" if ok else "map check failed", "dt_ms": 1.0}
    ns = types.SimpleNamespace(_localize_once=types.MethodType(once, object()), recheck_offset_m=0,
                               retry_gate=None, first_min_conf=None)
    ns._attempt = types.MethodType(NightLocalizer._attempt, ns)
    return ns, calls


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


def _scripted(results, gate, first_min_conf=None):
    """A localizer whose hypotheses return `results` in order (dicts merged into a success)."""
    calls = []

    def attempt(self, img, lat, lon, alt, hfov, heading, require_scale):
        x = dict(results[len(calls)])
        calls.append((heading, round(alt, 1)))
        ok = x.pop("ok", True)
        base = {"success": ok, "lat": 1.0, "lon": 2.0, "dt_ms": 1.0, "conf": 0.999,
                "verify": {"ncc": 0.2}, "recheck_m": 5.0}
        if not ok:
            base.update(map_check_failed=True, reason="map check failed")
        base.update(x)
        return base
    ns = types.SimpleNamespace(retry_gate=gate, first_min_conf=first_min_conf)
    ns._attempt = types.MethodType(attempt, ns)
    return ns, calls


def test_a_retry_needs_more_evidence_than_a_first_try():
    gate = dict(RETRY_GATE_DEFAULTS)
    # first-try gate off: a weak-looking quad is still accepted (the retry gate is for retries)
    s, _ = _scripted([dict(conf=0.90)], gate)
    assert _run(s, heading_retry_deg=(-10, 10))["success"]
    # retried: the weak hypothesis is refused, the next, stronger one kept
    s, calls = _scripted([dict(ok=False), dict(conf=0.90, lat=9.0), dict(conf=0.999, lat=3.0)], gate)
    r = _run(s, heading_retry_deg=(-10, 10))
    assert r["success"] and r["lat"] == 3.0 and r["heading_correction_deg"] == 10
    assert len(calls) == 3 and "heading -10 deg refused" in r["retries_refused"][0]
    # none strong enough: no position, and the reason says why
    s, _ = _scripted([dict(ok=False), dict(conf=0.90), dict(conf=0.91)], gate)
    r = _run(s, heading_retry_deg=(-10, 10))
    assert not r["success"] and "weaker evidence than a retry needs" in r["reason"]
    # gate off: the first verified retry is kept, as before
    s, _ = _scripted([dict(ok=False), dict(conf=0.90, lat=9.0), dict(conf=0.999, lat=3.0)], None)
    assert _run(s, heading_retry_deg=(-10, 10))["lat"] == 9.0


def test_retry_evidence_rules():
    ok = {"conf": 0.99, "verify": {"ncc": 0.08}, "recheck_m": 12.0, "recheck": {"verify": {"ncc": 0.04}}}
    assert retry_evidence_ok(ok, 1, min_ncc=0.05, recheck_max_m=25.0, min_conf=0.96)
    assert not retry_evidence_ok(ok, 1, min_ncc=0.05, min_conf=0.995)
    assert not retry_evidence_ok(ok, 1, min_ncc=0.05, recheck_max_m=10.0)
    assert not retry_evidence_ok(ok, 1, min_ncc=0.05, both_centres=True)       # second centre 0.04
    # the more hypotheses tried, the higher the map correlation asked (ncc_per_try)
    assert retry_evidence_ok(ok, 2, min_ncc=0.05, ncc_per_try=0.01)
    assert not retry_evidence_ok(ok, 4, min_ncc=0.05, ncc_per_try=0.01)
    assert not retry_evidence_ok({"conf": 0.99, "verify": {}, "recheck_m": 1.0}, 1)


def test_node_parameters_build_the_retry_gate():
    from night_pkg.nodes.night_subscriber import _retry_gate_from
    g = _retry_gate_from(0.97, 0.05, 0.0, 25.0)
    assert g["min_conf"] == 0.97 and g["recheck_max_m"] == 25.0
    assert _retry_gate_from(-1.0, 0.05, 0.0, 25.0) == {}
    assert _retry_gate_from(0.97, 0.05, 0.0, -1.0)["recheck_max_m"] is None
    assert RETRY_GATE_DEFAULTS["min_conf"] == 0.97


def test_a_weak_first_try_is_refused_and_retried():
    """F12 / D20: the first hypothesis needs consistency >= first_min_conf (0.97, as a retry); a
    weak first match (often a frame turned by a wrong heading, half absorbed) goes to the retries.
    """
    gate = dict(RETRY_GATE_DEFAULTS)
    assert FIRST_MIN_CONF == RETRY_GATE_DEFAULTS["min_conf"] == 0.97
    s, calls = _scripted([dict(conf=0.9698, lat=9.0), dict(ok=False), dict(conf=0.995, lat=3.0)],
                         gate, first_min_conf=FIRST_MIN_CONF)
    r = _run(s, heading_retry_deg=(-10, 10))
    assert r["success"] and r["lat"] == 3.0 and r["heading_correction_deg"] == 10 and len(calls) == 3
    # nothing better: no position, the weak first match is not published
    s, _ = _scripted([dict(conf=0.95, lat=9.0), dict(ok=False), dict(ok=False)], gate,
                     first_min_conf=FIRST_MIN_CONF)
    r = _run(s, heading_retry_deg=(-10, 10))
    assert not r["success"] and r["lat"] == 0.0 and "weak match" in r["reason"] and "sigma_m" not in r
    # a strong first match is kept at once
    s, calls = _scripted([dict(conf=0.99, lat=9.0)], gate, first_min_conf=FIRST_MIN_CONF)
    assert _run(s, heading_retry_deg=(-10, 10))["lat"] == 9.0 and len(calls) == 1
