"""The red test of the project "a held fix states a sigma that grows with its age" (mission 33).

A position measured at stamp_s and still used at now_s is (speed × age) metres behind a moving vehicle; the
judge must say so in the σ it states. New setting: age_speed_mps (the speed used for that growth, 15 m/s: the
drone's cruise speed); 0.0 gives the old behaviour back.
"""
import math
import os

import pytest

from navera_lite.estimate import COV_DIAGONAL_KNOWN, Estimate


def day_fix(stamp_s, sigma_m=15.0):
    s2 = sigma_m ** 2
    return Estimate("day", 35.80, 10.60, stamp_s, cov=(s2, 0, 0, 0, s2, 0, 0, 0, 4 * s2), cov_type=COV_DIAGONAL_KNOWN)


def judge(**over):
    from navera_lite.arbiter import Arbiter
    from navera_lite.settings import DEFAULTS
    return Arbiter(dict(DEFAULTS, **over))


def test_sigma_grows_with_the_age_of_the_fix():
    a = judge(age_speed_mps=10.0)
    a.receive(day_fix(100.0), 100.3)
    assert a.step(100.0).sigma_m == pytest.approx(15.0)               # age 0: the source's own σ
    assert a.step(102.0).sigma_m == pytest.approx(math.hypot(15.0, 20.0))   # 2 s × 10 m/s → 25 m


def test_an_old_fix_turns_degraded():
    a = judge(age_speed_mps=15.0)
    a.receive(day_fix(100.0), 100.3)
    d = a.step(101.5)                                                 # σ √(15² + 22.5²) = 27.0 m > 25 m
    assert d.state == "DEGRADED" and d.sigma_m == pytest.approx(27.04, abs=0.01)


def test_zero_speed_keeps_the_old_behaviour():
    a = judge(age_speed_mps=0.0)
    a.receive(day_fix(100.0), 100.3)
    assert a.step(104.0).sigma_m == pytest.approx(15.0)


def test_the_setting_exists_in_the_defaults_and_in_the_yaml():
    from navera_lite.settings import DEFAULTS, check_settings, load
    assert DEFAULTS["age_speed_mps"] == 15.0
    cfg = load(os.path.join(os.path.dirname(__file__), "..", "..", "navera_lite.yaml"))
    assert cfg["age_speed_mps"] == 15.0
    assert check_settings(cfg) == []
