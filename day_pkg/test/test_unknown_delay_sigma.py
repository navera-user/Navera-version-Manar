"""A fix's stated accuracy includes speed x the camera delay's uncertainty while the delay is unknown."""
import math
from types import MethodType, SimpleNamespace

from day_pkg.fix_sigma import SigmaCalibration
from day_pkg.nodes.day_subscriber import DaySubscriber
from navera_common.latency_cal import LatencyCalibrator


def _node(nominal=0.0, applied=None):
    lc = LatencyCalibrator(nominal_s=nominal)
    lc.applied = applied
    n = SimpleNamespace(latency_cal=lc, unknown_delay_sigma_s=1.0, local_sigma_m=30.0,
                        sigma_cal=SigmaCalibration(5.0, 15),
                        track=SimpleNamespace(velocity=lambda t: (6.0, 8.0, 0.5)))       # 10 m/s
    n._model_sigma = lambda result, meta: 7.8
    n._unknown_delay_sigma_s = MethodType(DaySubscriber._unknown_delay_sigma_s, n)
    n._fix_sigma = MethodType(DaySubscriber._fix_sigma, n)
    return n


def test_unknown_delay_widens_the_stated_sigma():
    assert math.isclose(_node()._fix_sigma({"sigma_m": 7.8}, {}), math.hypot(7.8, 10.0), rel_tol=1e-6)


def test_a_known_or_estimated_delay_does_not():
    assert math.isclose(_node(nominal=1.0)._fix_sigma({"sigma_m": 7.8}, {}), 7.8)
    assert math.isclose(_node(applied=1.3)._fix_sigma({"sigma_m": 7.8}, {}), 7.8)
