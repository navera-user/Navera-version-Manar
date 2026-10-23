"""open3 h1200: a strong match refused only for its fitted scale is matched again at the height that scale
implies (Isaac Sim h1200: the 25 % higher retry found the place with 150-355 inliers at scale 0.81 — the
frame's own height, 1.25 x 0.81 = 1.01 — and was refused as a wrong place 9 frames in a row)."""
from types import SimpleNamespace

from day_pkg.nodes.day_subscriber import DaySubscriber


class _Local:
    def __init__(self, ok_at):
        self.calls, self.ok_at = [], ok_at

    def locate(self, img, center, R, mpp, **kw):
        self.calls.append((center, R, mpp))
        ok = abs(mpp - self.ok_at) < 0.03 * self.ok_at
        return {"accepted": ok, "inliers": 300 if ok else 5, "scale_residual": 1.0 if ok else 0.8,
                "predicted_lat": center[0], "predicted_lon": center[1], "reason": None if ok else "x"}


def _node(local):
    n = SimpleNamespace(local=local, strong_inliers=100, local_scale_tol_max=0.35, local_min_radius_m=60.0,
                        get_logger=lambda: SimpleNamespace(info=lambda *a, **k: None))
    n._scale_tol = lambda meta: 0.15
    n._match_heading_kw = lambda meta: {"heading_deg": 90.0, "heading_tol_deg": 20.0}
    n._hfov = lambda meta: 77.0
    n._expected_tilt = lambda meta: 0.0
    return n


def _refused(sc, inliers=300):
    return {"accepted": False, "inliers": inliers, "scale_residual": sc, "predicted_lat": 35.87,
            "predicted_lon": 10.54, "reason": f"fitted scale {sc:.2f} ≠ 1 expected from the altitude (±15%): wrong place"}


def test_a_strong_match_at_the_wrong_retry_height_is_matched_again_at_its_own():
    local = _Local(ok_at=1.34 * 1.25 * 0.81)
    n = _node(local)
    res, f = DaySubscriber._rescaled_match(n, None, _refused(0.81), (35.86, 10.53), 200.0, 1.34, 1.25, {})
    assert res["accepted"] and abs(f - 1.0125) < 1e-6 and res["rescaled_from"] == 0.81
    assert local.calls[0][0] == (35.87, 10.54) and local.calls[0][1] == 60.0     # around the place found


def test_weak_or_far_off_scale_or_other_refusals_are_left_alone():
    local = _Local(ok_at=1.0)
    n = _node(local)
    for r, f in ((_refused(0.81, inliers=60), 1.25), (_refused(0.5), 1.0),
                 (dict(_refused(0.81), reason="3 geometric inliers (min 8)"), 1.25)):
        res, f2 = DaySubscriber._rescaled_match(n, None, r, (35.86, 10.53), 200.0, 1.34, f, {})
        assert res is r and f2 == f
    assert local.calls == []
    # a match again that fails keeps the refusal
    local = _Local(ok_at=9.0)
    res, f = DaySubscriber._rescaled_match(_node(local), None, _refused(0.81), (35.86, 10.53), 200.0, 1.34, 1.25, {})
    assert not res["accepted"] and f == 1.25 and len(local.calls) == 1
