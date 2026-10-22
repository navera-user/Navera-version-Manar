"""A fix's stated accuracy includes speed x the camera delay's uncertainty while the delay is unknown."""
import math
from types import MethodType, SimpleNamespace

from day_pkg.fix_sigma import SigmaCalibration
from day_pkg.nodes.day_subscriber import DaySubscriber
from navera_common.latency_cal import LatencyCalibrator


def _node(nominal=0.0, applied=None):
    lc = LatencyCalibrator(nominal_s=nominal)
    lc.applied = applied
    n = SimpleNamespace(latency_cal=lc, auto_latency=True, unknown_delay_sigma_s=1.0, local_sigma_m=30.0,
                        sigma_cal=SigmaCalibration(5.0, 15),
                        track=SimpleNamespace(velocity=lambda t: (6.0, 8.0, 0.5)))       # 10 m/s
    n._model_sigma = lambda result, meta: 7.8
    n._unknown_delay_sigma_s = MethodType(DaySubscriber._unknown_delay_sigma_s, n)
    n._fix_sigma = MethodType(DaySubscriber._fix_sigma, n)
    return n


def test_unknown_delay_widens_the_stated_sigma():
    assert math.isclose(_node()._fix_sigma({"sigma_m": 7.8}, {}), math.hypot(7.8, 10.0), rel_tol=1e-6)


def test_a_set_delay_adds_only_its_bench_sigma():
    """camera_latency_s (bench-measured) is good to camera_latency_sigma_s (0.1 s): 1 m at 10 m/s."""
    assert math.isclose(_node(nominal=1.0)._fix_sigma({"sigma_m": 7.8}, {}), math.hypot(7.8, 1.0))
    n = _node(nominal=1.0)
    n.auto_latency = False
    assert math.isclose(n._fix_sigma({"sigma_m": 7.8}, {}), math.hypot(7.8, 1.0))


def test_a_stable_estimate_adds_its_own_sigma():
    n = _node(applied=1.3)
    n.latency_cal.applied_sigma = 0.05
    assert math.isclose(n._fix_sigma({"sigma_m": 7.8}, {}), math.hypot(7.8, 0.5))


def test_the_camera_set_delay_becomes_the_nominal():
    """live_camera subtracted a bench-measured 1.3 s (capture_latency_s in the frame meta): the
    day node's delay is no longer unknown — speed x 0.1 s, not x 1 s, and no staged prior."""
    logs = []
    n = _node()
    n.get_logger = lambda: SimpleNamespace(info=logs.append, warn=logs.append)
    DaySubscriber._camera_set_delay(n, {"capture_latency_s": 1.3})
    assert n.latency_cal.nominal == 1.3 and n.latency_cal.prior is None and logs
    assert math.isclose(n._fix_sigma({"sigma_m": 7.8}, {}), math.hypot(7.8, 1.0))
    DaySubscriber._camera_set_delay(n, {})                       # no key (replay camera): unchanged
    assert n.latency_cal.nominal == 1.3


def test_a_staged_delay_states_its_own_sigma():
    """auto_latency applied a staged (partial) delay 1.2 +- 0.4 s: speed x 0.4 s, not x 1 s, not 0."""
    n = _node(applied=1.2)
    n.latency_cal.applied_sigma = 0.4
    n.auto_latency = True
    assert math.isclose(n._fix_sigma({"sigma_m": 7.8}, {}), math.hypot(7.8, 4.0), rel_tol=1e-6)


def test_an_estimate_not_applied_with_auto_latency_off_is_still_unknown():
    n = _node(applied=1.2)
    n.latency_cal.applied_sigma = 0.4
    n.auto_latency = False
    assert math.isclose(n._fix_sigma({"sigma_m": 7.8}, {}), math.hypot(7.8, 10.0), rel_tol=1e-6)
