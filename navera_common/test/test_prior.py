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


def test_gps_refused_by_the_arbiter_is_not_a_prior():
    p = GpsPrior(2.0)
    assert p.update(35.83, 10.64, True, now=0.0)                 # no arbiter yet: accepted
    p.arbiter(True, now=1.0)
    assert p.update(35.831, 10.641, True, now=1.1)
    p.arbiter(False, now=2.0)                                    # arbiter refuses GPS (spoof)
    assert not p.update(35.85, 10.66, True, now=2.1)
    assert p.last() == (35.831, 10.641)                          # last TRUSTED position kept
    assert p.fresh(now=2.2) is None                              # → vision runs at once
    assert p.update(35.85, 10.66, True, now=4.5)                 # arbiter silent > 2 s: accepted
    p.arbiter(False, now=5.0)
    p.arbiter(True, now=6.0)                                     # GPS back in use
    assert p.update(35.832, 10.642, True, now=6.1)
