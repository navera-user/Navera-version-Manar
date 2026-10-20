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


class _FakeClock:
    """A clock the test moves by hand (the node reads time only through get_clock())."""

    def __init__(self, ns, clock_type):
        self.ns, self.clock_type = ns, clock_type

    def now(self):
        from rclpy.time import Time
        return Time(nanoseconds=self.ns, clock_type=self.clock_type)


def _fly(drift_mps, dur_s=150.0, seed=3, vision_sigma=10.0, spoof_end_s=None, until_end=False):
    """A vehicle at 20 m/s north; GPS at 1 Hz (truth + drift east from t=40 s), day vision every 2 s
    0.5 s late (truth + bias + jitter, 2 % wrong fixes 100-300 m) stating vision_sigma. Returns
    (drift m at refusal or None, reason, doubt seen)."""
    import random
    from rclpy.time import Time
    rnd = random.Random(seed)
    n = EstimatorNode()
    real = n.get_clock()
    clock = _FakeClock(real.now().nanoseconds, real.clock_type)
    n.get_clock = lambda: clock
    t0 = clock.ns
    doubt = False
    try:
        for k in range(int(dur_s * 2)):
            t = 0.5 * k
            clock.ns = t0 + int(t * 1e9)
            if k % 2 == 0:
                g = _msg(n, PositionEstimate.SOURCE_GPS, north_m=20.0 * t, sigma=2.0)
                if spoof_end_s is None or t < spoof_end_s:
                    g.longitude += drift_mps * max(0.0, t - 40.0) * M / math.cos(math.radians(LAT))
                n._on_gps(g)
            tp = t - 0.5
            if tp > 0 and k % 4 == 1:                  # the day node's GPS check: one fix per 2 s
                v = _msg(n, PositionEstimate.SOURCE_DAY_VISION, north_m=20.0 * tp + 6.0 + rnd.gauss(0, 4.0),
                         sigma=vision_sigma)
                v.longitude += (-9.0 + rnd.gauss(0, 4.0)) * M / math.cos(math.radians(LAT))
                if rnd.random() < 0.02:
                    v.latitude += rnd.uniform(100.0, 300.0) * M
                st = Time(nanoseconds=t0 + int(tp * 1e9)).to_msg()
                v.header.stamp, v.sensor_stamp = clock.now().to_msg(), st
                n._on_day(v)
            doubt = doubt or n._gps_doubt is not None
            if n._gps_suspect and not until_end:
                return drift_mps * max(0.0, t - 40.0), n._gps_suspect, doubt
            if until_end:
                doubt = doubt if isinstance(doubt, list) else []
                doubt.append((t, n._gps_suspect))
        return None, None, doubt
    finally:
        n.destroy_node()


def test_a_slow_gps_spoof_is_refused_by_the_growth_of_the_offset(node):
    """3 m/s drift, vision stating the 30 m floor: the size rules alone wait for 3 sigma (90 m)."""
    drift, why, doubt = _fly(3.0, vision_sigma=30.0)
    assert drift is not None and drift < 85.0, (drift, why)
    assert "slow spoofing" in why and doubt


def test_a_good_gps_is_not_refused_by_jittery_vision_with_wrong_fixes(node):
    drift, why, _ = _fly(0.0, dur_s=600.0, vision_sigma=15.0)
    assert why is None, why


def test_a_growth_refusal_holds_while_the_spoof_lasts_and_lifts_when_it_ends(node):
    """Refused well inside 3 sigma: agreeing within 3 sigma must not bring the spoofed GPS back."""
    _, _, log = _fly(3.0, dur_s=130.0, vision_sigma=30.0, spoof_end_s=100.0, until_end=True)
    first = next(t for t, why in log if why)
    assert first < 70.0
    assert all(why for t, why in log if first <= t < 100.0)         # the drift goes on: refused
    assert not log[-1][1]                                           # true GPS back after the spoof
