"""Slow-spoof safety: what the sigma calibration and the map bias learned from a GPS that was then
refused is forgotten (calib_rollback_s)."""
from day_pkg.fix_sigma import SigmaCalibration
from day_pkg.vision_nav import VisionNavigator


def test_sigma_calibration_forgets_the_samples_after_since():
    c = SigmaCalibration(30.0, 15)
    for i in range(20):
        c.add(10.0, 10.0, t=float(i))                 # honest flight: calibrated
    assert c.terms() is not None
    for i in range(20, 40):
        c.add(10.0 + 3.0 * (i - 20), 10.0, t=float(i))  # GPS drifting away 3 m/s: errors grow
    inflated = c.apply(10.0)
    assert c.rollback(20.0) == 20
    assert c.samples == 20 and c.apply(10.0) < inflated


def test_sigma_calibration_samples_without_time_are_never_rolled_back():
    c = SigmaCalibration(30.0, 2)
    c.add(5.0, 10.0)
    assert c.rollback(0.0) == 0 and c.samples == 1


def test_map_bias_forgets_the_samples_after_since():
    nav = VisionNavigator()
    for i in range(10):
        nav.bias_sample((36.0, 10.0), (36.0, 10.0), 0.0, t=float(i))
    for i in range(10, 16):
        nav.bias_sample((36.0, 10.0), (36.0005, 10.0), 90.0, t=float(i))
    assert nav.rollback_bias(10.0) == 6
    assert nav.rollback_bias(10.0) == 0
