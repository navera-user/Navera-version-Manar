"""EstimatorNode rules on crafted messages (an rclpy node, no other process)."""
import math

import pytest
import rclpy
from rclpy.duration import Duration
from navera_msgs.msg import PositionEstimate

from navera_estimator.nodes.estimator_node import EstimatorNode

LAT, LON = 35.85, 10.57
M = 1.0 / 111195.0


@pytest.fixture(scope="module")
def node():
    rclpy.init()
    n = EstimatorNode()
    yield n
    n.destroy_node()
    rclpy.shutdown()


def _msg(n, src, dt_s=0.0, north_m=0.0, sigma=None):
    m = PositionEstimate()
    t = (n.get_clock().now() + Duration(seconds=dt_s)).to_msg()
    m.header.stamp = t
    m.sensor_stamp = t
    m.source, m.mode, m.valid = src, PositionEstimate.MODE_MEASURED, True
    m.latitude, m.longitude = LAT + north_m * M, LON
    if sigma is not None:
        m.position_covariance = [sigma ** 2, 0.0, 0.0, 0.0, sigma ** 2, 0.0, 0.0, 0.0, 0.0]
        m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
    return m


def test_a_fix_that_arrived_from_the_future_never_comes_back_to_life(node):
    m = _msg(node, PositionEstimate.SOURCE_DAY_VISION, dt_s=10.0, sigma=30.0)
    node._on_day(m)
    now = node.get_clock().now()
    assert node._eval_source(now, m, 3.0)[:2] == (False, False)
    later = now + Duration(seconds=11.0)              # the clock caught up: the stamp looks fresh
    assert node._eval_source(later, m, 3.0)[:2] == (False, False)
    fresh = _msg(node, PositionEstimate.SOURCE_DAY_VISION, sigma=30.0)
    node._on_day(fresh)
    assert node._eval_source(node.get_clock().now(), fresh, 3.0)[1] is True


def test_a_steady_drag_beyond_max_speed_is_refused_over_the_window(node):
    """D2: 100 m/s max + 50 m margin per 1 s fix let 150 m/s through; over the window it cannot."""
    node._gps_trusted, node._gps_suspect, node._day_last = None, None, None   # GPS judged alone
    node._trusted_hist.clear()
    t0 = node.get_clock().now()
    refused_at = None
    for k in range(25):
        m = _msg(node, PositionEstimate.SOURCE_GPS, north_m=145.0 * k, sigma=2.0)
        m.header.stamp = (t0 + Duration(seconds=float(k))).to_msg()
        node._check_gps_plausibility(m)
        if node._gps_suspect and refused_at is None:
            refused_at, why = k, node._gps_suspect
    assert refused_at is not None and refused_at <= 3 and "drift" in why


def test_a_vehicle_at_max_speed_is_never_refused(node):
    node._gps_trusted, node._gps_suspect, node._day_last = None, None, None   # GPS judged alone
    node._trusted_hist.clear()
    t0 = node.get_clock().now()
    for k in range(30):
        m = _msg(node, PositionEstimate.SOURCE_GPS, north_m=99.0 * k + (3.0 if k % 2 else -3.0), sigma=2.0)
        m.header.stamp = (t0 + Duration(seconds=float(k))).to_msg()
        node._check_gps_plausibility(m)
        assert node._gps_suspect is None


def test_stated_sigma_is_the_long_axis_and_sanity_ignores_the_up_variance(node):
    m = _msg(node, PositionEstimate.SOURCE_DAY_VISION, sigma=1.0)
    m.position_covariance = [200.0, 200.0, 0.0, 200.0, 200.0, 0.0, 0.0, 0.0, 1e12]
    assert math.isclose(node._stated_sigma(m), 20.0)
    assert node._sane(m)
    m.position_covariance = [1.0, 1.5, 0.0, 1.5, 1.0, 0.0, 0.0, 0.0, 1e12]
    assert not node._sane(m)
