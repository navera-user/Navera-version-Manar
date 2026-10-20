"""navera_common.gps_crosscheck: the GPS refusal rule shared by the arbiter and the bench."""
import math
import random

from navera_common.gps_crosscheck import STREAK_N, GpsCrossCheck, GpsDriftTrend


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


# ---------- the growth test (slow spoofing) ----------
# Independent fixes come at the day node's GPS-check cadence (gps_check_period_s 2 s): 0.5 Hz.
def _vision_noise(rnd, jitter):
    """A wrong fix (100-300 m) 2 % of the time, else Gaussian jitter."""
    if rnd.random() < 0.02:
        r, th = rnd.uniform(100.0, 300.0), rnd.uniform(0.0, 2.0 * math.pi)
        return r * math.cos(th), r * math.sin(th)
    return rnd.gauss(0.0, jitter), rnd.gauss(0.0, jitter)


def _drift_at_refusal(v_mps, sigma, jitter, seed=1, start=60.0, dur=400.0, rate_hz=0.5, trend=True):
    """Drift (m) of GPS when the cross-check (size, + growth if trend) refuses it, or None."""
    rnd = random.Random(seed)
    x = GpsCrossCheck(trend=GpsDriftTrend() if trend else None)
    t = 0.0
    while t < dur:
        drift = v_mps * max(0.0, t - start)
        ne, nn = _vision_noise(rnd, jitter)
        oe, on = drift + 12.0 - ne, -7.0 - nn            # GPS - vision, vision bias (-12, 7) m
        if x.update(t, math.hypot(oe, on), 5 * sigma + 50.0, 3 * sigma, t, "day vision",
                    sample=(t, oe, on, sigma)):
            return drift
        t += 1.0 / rate_hz
    return None


def test_a_3_mps_drift_is_refused_before_the_size_rules_when_vision_beats_its_sigma():
    """Vision jitter 5 m under the stated 30 m floor (before calibration): the size rules wait for
    3 sigma (90 m) at 5 fixes in a row (~105 m), the growth test for 1.5 sigma of steady growth."""
    for seed in range(5):
        at = _drift_at_refusal(3.0, 30.0, jitter=5.0, seed=seed)
        size_only = _drift_at_refusal(3.0, 30.0, jitter=5.0, seed=seed, trend=False)
        assert at is not None and 0.0 < at < 85.0, (seed, at)
        assert size_only is None or size_only > at + 20.0, (seed, at, size_only)


def test_slow_drifts_are_refused_and_the_reason_says_so():
    x = GpsCrossCheck(trend=GpsDriftTrend())
    reason = None
    for k in range(400):
        t = 2.0 * k
        oe = 1.0 * max(0.0, t - 40.0) + (1.5 if k % 2 else -1.5)
        reason = x.update(t, abs(oe), 200.0, 90.0, k, "day vision", sample=(t, oe, 0.0, 10.0))
        if reason:
            break
    assert reason and "offset grew" in reason and "slow spoofing" in reason
    assert oe < 70.0                                   # 1 m/s, 0.5 Hz: the 3 sigma rule is off here (90 m)


def test_a_good_gps_is_never_refused_for_growth_by_noisy_vision_with_wrong_fixes():
    """Two hours at 0.5 Hz: an AR(1) bias (0.3 sigma, tau 30 s), jitter, 2 % wrong fixes."""
    for sigma in (10.0, 30.0):
        rnd = random.Random(7)
        tr = GpsDriftTrend()
        a = math.exp(-2.0 / 30.0)
        sb, sj = 0.3 * sigma, math.sqrt(1.0 - 0.09) * sigma
        be = bn = 0.0
        for k in range(3600):
            be = a * be + math.sqrt(1 - a * a) * rnd.gauss(0.0, sb)
            bn = a * bn + math.sqrt(1 - a * a) * rnd.gauss(0.0, sb)
            ne, nn = _vision_noise(rnd, sj)
            assert tr.add(2.0 * k, -(be + ne), -(bn + nn), sigma, k) is None, (sigma, k, tr.last)


def test_a_run_of_wrong_fixes_is_a_step_not_a_growth():
    tr = GpsDriftTrend()
    for k in range(200):
        off = 200.0 if 100 <= k < 106 else 0.0                    # 6 wrong fixes in a row, 12 s
        assert tr.add(2.0 * k, off + (k % 3), 0.0, 10.0, k) is None


def test_a_growth_inside_the_stated_sigma_is_never_refused():
    tr = GpsDriftTrend()
    for k in range(400):
        t = 0.5 * k
        assert tr.add(t, min(0.5 * t, 50.0), 0.0, 30.0, k) is None    # 50 m < 2 x 30 m


def test_one_fix_counts_once():
    tr = GpsDriftTrend(confirm_n=1)
    for k in range(60):
        tr.add(0.5 * k, float(k % 4), 0.0, 10.0, "same" if k >= 30 else k)
    assert len(tr._hist) == 31                                    # 30 + the first "same"


def test_growth_marks_doubt_first_and_keeps_the_offset_before_it():
    x = GpsCrossCheck(trend=GpsDriftTrend(confirm_n=3))
    seen_doubt, r = False, None
    for k in range(300):
        t = 2.0 * k
        oe = 4.0 * max(0.0, t - 40.0) + 20.0
        r = x.update(t, oe, 1e9, 1e9, k, sample=(t, oe, 0.0, 10.0))
        seen_doubt = seen_doubt or x.in_doubt
        if r:
            break
    assert r and seen_doubt and not x.in_doubt                   # reset after the refusal
    e, n, growth = x.baseline
    assert abs(e - 20.0) < 15.0 and growth > 20.0
    assert not x.back_to_baseline((t, oe, 0.0, 10.0))           # still drifted: stays refused
    assert x.back_to_baseline((t, 22.0, 0.0, 10.0))             # the growth undone
