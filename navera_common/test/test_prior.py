"""Unit tests for navera_common.prior.GpsPrior."""
from navera_common.prior import GpsPrior


def test_only_valid_measured_finite_fixes_are_kept():
    p = GpsPrior(timeout_s=2.0)
    assert not p.update(35.8, 10.6, valid=False, now=0.0)
    assert not p.update(35.8, 10.6, valid=True, measured=False, now=0.0)
    assert not p.update(float("nan"), 10.6, valid=True, now=0.0)
    assert p.last() is None
    assert p.update(35.8, 10.6, valid=True, now=0.0)
    assert p.last() == (35.8, 10.6)


def test_freshness_window():
    p = GpsPrior(timeout_s=2.0)
    p.update(35.8, 10.6, valid=True, now=10.0)
    assert p.fresh(now=11.9) == (35.8, 10.6)
    assert p.fresh(now=12.1) is None           # GPS lost
    assert p.last() == (35.8, 10.6)            # but the last fix is still the prior


def test_invalid_update_does_not_refresh():
    p = GpsPrior(timeout_s=2.0)
    p.update(35.8, 10.6, valid=True, now=0.0)
    p.update(0.0, 0.0, valid=True, now=5.0)    # (0,0) is not a fix
    assert p.fresh(now=5.0) is None
    assert p.last() == (35.8, 10.6)
