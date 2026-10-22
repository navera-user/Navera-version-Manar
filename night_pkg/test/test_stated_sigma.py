"""night_subscriber states the two-centre fix sigma as covariance by default (D3 / D22)."""
from types import SimpleNamespace

from builtin_interfaces.msg import Time
from navera_msgs.msg import PositionEstimate

from night_pkg.nodes.night_subscriber import NightSubscriber


def _published(state_fix, state_sim, fitted, src="night_sthn", sigma=12.0):
    out = []
    node = SimpleNamespace(state_fix_sigma=state_fix, state_sim_sigma=state_sim, _fix_sigma=sigma,
                           _fix_sigma_fitted=fitted, pub_est=SimpleNamespace(publish=out.append))
    NightSubscriber._publish_estimate(node, Time(sec=100), 7, src, 44.86, -0.58,
                                      {"altitude_m": 700.0, "image_stamp_ns": 100 * 10**9}, {})
    return out[0]


def test_fitted_sigma_stated_by_default():
    est = _published(True, False, fitted=True)
    assert est.position_covariance_type == PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
    assert est.position_covariance[0] == 144.0 and est.position_covariance[4] == 144.0


def test_fallback_sigma_needs_the_explicit_sim_choice():
    est = _published(True, False, fitted=False)
    assert est.position_covariance_type == PositionEstimate.COVARIANCE_TYPE_UNKNOWN
    est = _published(True, True, fitted=False)
    assert est.position_covariance_type == PositionEstimate.COVARIANCE_TYPE_APPROXIMATED


def test_off_and_dead_reckoning_state_none():
    assert _published(False, False, fitted=True).position_covariance_type == \
        PositionEstimate.COVARIANCE_TYPE_UNKNOWN
    assert _published(True, True, fitted=True, src="dead_reckon").position_covariance_type == \
        PositionEstimate.COVARIANCE_TYPE_UNKNOWN
