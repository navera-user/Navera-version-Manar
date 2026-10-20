"""navera_common.gps_crosscheck: the GPS refusal rule shared by the arbiter and the bench."""
from navera_common.gps_crosscheck import STREAK_N, GpsCrossCheck


def test_two_noisy_fixes_never_refuse_a_good_gps():
    """The bench refused a good GPS on 2 frames of noisy vision (wind, heavy clouds, 2026-10-19)."""
    j = GpsCrossCheck()
    for k, d in enumerate((95.0, 120.0, 10.0, 99.0, 130.0, 20.0)):     # sigma 30: 3 sigma 90, wide 200
        assert j.update(float(k), d, 200.0, 90.0, k) is None


def test_a_slow_drift_is_refused_after_streak_n_fixes_beyond_3_sigma():
    j = GpsCrossCheck()
    out = [j.update(float(k), 100.0 + k, 200.0, 90.0, k) for k in range(STREAK_N)]
    assert out[:-1] == [None] * (STREAK_N - 1) and "in a row" in out[-1]
    assert j.in_doubt is False                       # reset after the refusal


def test_wide_disagreement_needs_two_measurements_over_persist_s():
    j = GpsCrossCheck(persist_s=3.0)
    assert j.update(0.0, 500.0, 200.0, 90.0, "a") is None
    assert j.update(3.5, 500.0, 200.0, 90.0, "a") is None        # the same measurement again
    assert "apart for" in j.update(3.6, 500.0, 200.0, 90.0, "b")


def test_doubt_after_two_in_a_row_and_an_agreeing_fix_clears_it():
    j = GpsCrossCheck()
    j.update(0.0, 100.0, 200.0, 90.0, 1)
    j.update(1.0, 100.0, 200.0, 90.0, 2)
    assert j.in_doubt
    j.update(2.0, 10.0, 200.0, 90.0, 3)
    assert not j.in_doubt


def test_disagreement_is_forgotten_without_a_reference():
    j = GpsCrossCheck(persist_s=3.0, forget_s=10.0)
    j.update(0.0, 500.0, 200.0, 90.0, "a")
    j.no_reference(14.0)
    assert j.update(14.5, 500.0, 200.0, 90.0, "b") is None       # a new disagreement starts
