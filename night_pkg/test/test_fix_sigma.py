"""Stated sigma of a confirmed STHN fix (D3): fix_sigma_m."""
import math

from night_pkg.nodes.night_localizer import fix_sigma_m


def test_floor_at_400_m_with_agreeing_centres():
    assert math.isclose(fix_sigma_m(400.0, 0.0), 8.0)
    assert math.isclose(fix_sigma_m(250.0, 0.0), 8.0)          # lower: not tighter
    assert math.isclose(fix_sigma_m(None, 0.0), 8.0)           # unknown height: the 400 m value


def test_grows_with_height_and_disagreement():
    assert math.isclose(fix_sigma_m(1400.0, 0.0), 18.0)
    assert math.isclose(fix_sigma_m(400.0, 20.0), math.hypot(8.0, 16.0))
    assert fix_sigma_m(400.0, 25.0) > fix_sigma_m(400.0, 5.0)
