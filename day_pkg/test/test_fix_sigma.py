"""day_pkg.fix_sigma: the stated sigma of a local match from its parts."""
import math

from day_pkg.fix_sigma import day_fix_sigma_m


def test_floor_and_matcher_sigma():
    assert day_fix_sigma_m(3.0, floor_m=5.0) == 5.0
    assert day_fix_sigma_m(12.0, floor_m=5.0) == 12.0
    assert day_fix_sigma_m(None, floor_m=5.0) == 5.0


def test_speed_and_attitude_terms_add_in_quadrature():
    s = day_fix_sigma_m(4.0, floor_m=5.0, speed_mps=60.0, delay_sigma_s=0.05,
                        height_m=1500.0, attitude_sigma_deg=0.5)
    att = 0.5 * 1500.0 * math.tan(math.radians(0.5))
    assert abs(s - math.sqrt(25.0 + 9.0 + att * att)) < 1e-9


def test_unknown_height_or_speed_adds_nothing():
    assert day_fix_sigma_m(8.0, height_m=float("nan")) == 8.0
    assert day_fix_sigma_m(8.0, speed_mps=None, height_m=None) == 8.0
