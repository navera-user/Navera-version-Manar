"""Stated sigma of a confirmed STHN fix (D3 / D22): fix_sigma_m (refitted on real thermal 2026-10-22)."""
import math

from night_pkg.nodes.night_localizer import fix_sigma_m


def test_floor_at_400_m_with_agreeing_centres():
    assert math.isclose(fix_sigma_m(400.0, 0.0), 10.0)
    assert math.isclose(fix_sigma_m(250.0, 0.0), 10.0)         # lower: not tighter
    assert math.isclose(fix_sigma_m(None, 0.0), 10.0)          # unknown height: the 400 m value


def test_grows_with_height_and_disagreement():
    assert math.isclose(fix_sigma_m(1400.0, 0.0), 20.0)
    assert math.isclose(fix_sigma_m(400.0, 20.0), math.hypot(10.0, 20.0))
    assert fix_sigma_m(400.0, 25.0) > fix_sigma_m(400.0, 5.0)


def test_covers_the_real_thermal_worst_cases():
    """2026-10-22 real thermal: the largest error / sigma among accepted fixes was 2.98 (a 15 deg
    heading error): Bordeaux night examples (height, two-centre gap, true error) stay inside 3 sigma.
    """
    for h, gap, err in ((500.0, 3.0, 26.0), (700.0, 10.0, 30.0), (1000.0, 2.0, 31.0)):
        assert err <= 3.0 * fix_sigma_m(h, gap)
