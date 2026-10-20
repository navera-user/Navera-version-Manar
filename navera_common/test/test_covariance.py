"""navera_common.covariance: worst-axis sigma and the sanity check of a 3x3 position covariance."""
import math

from navera_common.covariance import covariance_sane, horizontal_sigma


def _cov(a, b, c, up=1.0):
    return [a, b, 0.0, b, c, 0.0, 0.0, 0.0, up]


def test_horizontal_sigma_is_the_long_axis_of_a_tilted_ellipse():
    assert math.isclose(horizontal_sigma(_cov(100.0, 0.0, 25.0)), 10.0)
    # 45 deg ellipse, axes 20 m and ~0: per-axis variances 200, worst axis 400
    assert math.isclose(horizontal_sigma(_cov(200.0, 200.0, 200.0)), 20.0)
    assert horizontal_sigma(_cov(200.0, 200.0, 200.0)) > math.sqrt(200.0) * 1.4


def test_a_huge_up_variance_does_not_switch_the_horizontal_check_off():
    bad = _cov(1.0, 1.5, 1.0, up=1e12)            # correlation 1.5: impossible
    assert not covariance_sane(bad)
    assert not covariance_sane(_cov(1.0, 3.7, 1.0, up=1e6))


def test_valid_km_scale_covariances_with_correlation_one_pass():
    for s in (1e3, 3.3e3, 7.7e4):
        a = s * s
        assert covariance_sane(_cov(a, a, a, up=1e6))
        assert covariance_sane(_cov(a, -a * (1 - 1e-15), a))


def test_non_finite_negative_or_asymmetric_are_refused():
    assert not covariance_sane(_cov(math.nan, 0.0, 1.0))
    assert not covariance_sane(_cov(-1.0, 0.0, 1.0))
    c = _cov(4.0, 1.0, 4.0)
    c[3] = 1.1
    assert not covariance_sane(c)
    assert covariance_sane([0.0] * 9)
