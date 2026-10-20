"""learned_matcher.map_level: a high frame is matched on a coarser map level, not enlarged (D14)."""
import math

from day_pkg.learned_matcher import map_level


def test_low_frames_stay_on_the_zoom():
    assert map_level(0.4) == 0 and map_level(1.0) == 0 and map_level(1.29) == 0


def test_high_frames_use_the_nearest_level():
    assert map_level(1.64) == 1          # ~800 m with the bench camera
    assert map_level(3.07) == 2          # ~1500 m
    assert map_level(40.0) == 3          # capped
    assert map_level(float("nan")) == 0
    for s in (1.4, 2.0, 3.0, 5.0):
        assert 0.6 <= s / 2 ** map_level(s) <= 1.42   # the frame is never enlarged more than ~1.4x
