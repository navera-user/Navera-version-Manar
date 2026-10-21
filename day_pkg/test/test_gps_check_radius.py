"""day_subscriber's GPS-check match: near the GPS first, the wide radius only as a fallback."""
from types import MethodType, SimpleNamespace

from day_pkg.nodes.day_subscriber import DaySubscriber


def _node(accept_up_to_m, near=150.0, wide=600.0):
    radii = []

    def locate(img, prior, r, mpp, **kw):
        radii.append(r)
        return {"accepted": r <= accept_up_to_m}
    n = SimpleNamespace(local=SimpleNamespace(locate=locate), calib_radius_m=wide, calib_near_radius_m=near,
                        local_heading_tol_deg=20.0, _scale_tol=lambda m: 0.15, _heading_for_match=lambda m: None,
                        _hfov=lambda m: 77.0, _expected_tilt=lambda m: 0.0,
                        _match_heading_kw=lambda m: {})
    n._gps_check_locate = MethodType(DaySubscriber._gps_check_locate, n)
    return n, radii


def test_a_near_match_is_tried_first_and_kept():
    n, radii = _node(accept_up_to_m=200.0)
    assert n._gps_check_locate(None, (35.8, 10.6), 0.3, {})["accepted"] and radii == [150.0]


def test_the_wide_radius_is_the_fallback():
    n, radii = _node(accept_up_to_m=1000.0)
    n.local.locate = (lambda img, prior, r, mpp, **kw: radii.append(r) or {"accepted": r > 500})
    assert n._gps_check_locate(None, (35.8, 10.6), 0.3, {})["accepted"] and radii == [150.0, 600.0]


def test_near_radius_zero_is_the_former_behaviour():
    n, radii = _node(accept_up_to_m=1000.0, near=0.0)
    n._gps_check_locate(None, (35.8, 10.6), 0.3, {})
    assert radii == [600.0]


def test_checks_are_faster_until_the_delay_is_stable():
    from navera_common.latency_cal import LatencyCalibrator
    n = SimpleNamespace(calib_period_s=2.0, calib_period_delay_s=1.0, auto_latency=True,
                        latency_cal=LatencyCalibrator())
    period = MethodType(DaySubscriber._gps_check_period, n)
    assert period() == 1.0
    n.latency_cal.stable = True
    assert period() == 2.0
    n.latency_cal.stable, n.auto_latency = False, False
    assert period() == 2.0
