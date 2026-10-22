"""NAV-FUN-17: an operator start position is a search area for day vision, never a published position."""
import math
from types import MethodType, SimpleNamespace

from navera_msgs.msg import PositionEstimate

from day_pkg.nodes.day_subscriber import DaySubscriber


def _node(gps_fresh=False):
    published = []
    n = SimpleNamespace(
        _gps_prior=SimpleNamespace(fresh=lambda: (35.8, 10.6) if gps_fresh else None),
        _anchor_lat=None, _anchor_lon=None, _anchor_time=None, _anchor_sigma=None, _last_measured_time=None,
        max_speed_mps=30.0, track=SimpleNamespace(reset=lambda: None),
        get_logger=lambda: SimpleNamespace(warn=lambda *a, **k: None, info=lambda *a, **k: None),
        pub_estimate=SimpleNamespace(publish=published.append),
        _publish_estimate=lambda *a, **k: published.append(a))
    n.on_operator_position = MethodType(DaySubscriber.on_operator_position, n)
    return n, published


def _op(lat=35.80, lon=10.60, acc=200.0):
    m = PositionEstimate()
    m.latitude, m.longitude = lat, lon
    m.position_covariance = [acc ** 2, 0.0, 0.0, 0.0, acc ** 2, 0.0, 0.0, 0.0, 1.0]
    return m


def test_without_gps_it_becomes_the_search_area_only():
    n, published = _node()
    n.on_operator_position(_op(acc=200.0))
    assert (n._anchor_lat, n._anchor_lon) == (35.80, 10.60) and math.isclose(n._anchor_sigma, 200.0)
    assert published == []                                     # never a published position


def test_the_search_circle_starts_as_wide_as_the_stated_accuracy():
    n, _ = _node()
    n.on_operator_position(_op(acc=300.0))
    assert math.isclose((n._anchor_time - n._last_measured_time) * n.max_speed_mps, 300.0, rel_tol=1e-6)


def test_ignored_while_gps_is_trusted():
    n, _ = _node(gps_fresh=True)
    n.on_operator_position(_op())
    assert n._anchor_lat is None


def test_a_bad_position_is_refused():
    for lat, lon in ((math.nan, 10.6), (95.0, 10.6), (35.8, math.inf)):
        n, _ = _node()
        n.on_operator_position(_op(lat=lat, lon=lon))
        assert n._anchor_lat is None
