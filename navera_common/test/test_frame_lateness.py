"""Late camera frames at 60 m/s (Isaac plane60 2026-10-30: 100-160 m spikes): no fix beyond 3 sigma.

Unit level only (synthetic frames, no Isaac Sim): a camera at 10 Hz, a usual delay of 0.2 s, and
pipeline stalls of 0.5-2.2 s. A frame is dated arrival - the usual delay (- the re-dating
shift); its fix is the true position at its exposure (+ 5 m matcher noise), so it is
60 m/s x (dated - exposure) off where the estimator puts it. The matcher noise is clipped at
2 sigma so that only the dating decides the 3-sigma check.
"""
import math
import random

import pytest

from navera_common.frame_lateness import FrameLateness, lateness_sigma, meta_fields

SPEED, DELAY, PERIOD, SIGMA = 60.0, 0.2, 0.1, 5.0


def frames(stalls, n=600, keep_queued=True, seed=1):
    """(exposure, arrival) per delivered frame. A stall (start, length): frames exposed in it wait
    and arrive in a burst at its end (keep_queued) or are dropped but the last one."""
    rnd = random.Random(seed)
    out = []
    for k in range(n):
        e = k * PERIOD
        a = e + DELAY + rnd.uniform(0.0, 0.01)          # 10 ms ordinary jitter
        for s0, length in stalls:
            if s0 <= a < s0 + length:
                if not keep_queued and a + PERIOD < s0 + length:
                    a = None                             # dropped: a fresher frame follows in the stall
                else:
                    a = s0 + length                      # the queue drains in order, 1 ms apart
                break
        if a is not None:
            if out:
                a = max(a, out[-1][1] + 0.001)         # first in, first out: never before an older frame
            out.append((e, a))
    return out


def run(stalls, with_source, keep_queued=True, gate_m=60.0, seed=1):
    rnd = random.Random(seed + 7)
    fl = FrameLateness()
    errs, base_errs, dropped = [], [], 0
    for e, a in frames(stalls, keep_queued=keep_queued, seed=seed):
        late = fl.observe(a, e + 1000.0 if with_source else None)   # the source clock: another origin
        meta = meta_fields(*late)
        dated = a - DELAY - late[0]
        noise = max(-2.0 * SIGMA, min(2.0 * SIGMA, rnd.gauss(0.0, SIGMA)))   # the matcher: within 2 sigma
        base_errs.append(abs(SPEED * (a - DELAY - e) + noise))
        sigma, why = lateness_sigma(meta, SPEED, SIGMA, gate_m)
        if why:
            dropped += 1
            continue
        errs.append((abs(SPEED * (dated - e) + noise), sigma))
    return errs, base_errs, dropped


STALLS = [(5.0, 0.5), (12.0, 1.1), (20.0, 2.2), (31.0, 0.8), (44.0, 1.7)]


def test_without_the_check_late_frames_spike_100_m():
    _, base, _ = run(STALLS, with_source=False)
    assert max(base) > 100.0                        # the plane60 spikes this reproduces


@pytest.mark.parametrize("seed", range(10))
def test_camera_stamp_redates_late_frames(seed):
    errs, _, dropped = run(STALLS, with_source=True, seed=seed)
    assert dropped == 0                             # re-dated: nothing uncertain left
    assert all(err <= 3.0 * sig for err, sig in errs)
    assert max(err for err, _ in errs) < 3.0 * SIGMA


@pytest.mark.parametrize("seed", range(10))
def test_interval_only_widens_or_drops_queued_late_frames(seed):
    errs, _, dropped = run(STALLS, with_source=False, seed=seed)
    assert dropped > 0                              # 60 m/s x > 1 s: beyond the 60 m gate
    bad = [(err, sig) for err, sig in errs if err > 3.0 * sig]
    assert not bad, bad[:5]


@pytest.mark.parametrize("seed", range(10))
def test_interval_only_stale_frames_dropped_by_the_camera(seed):
    errs, _, _ = run(STALLS, with_source=False, keep_queued=False, seed=seed)
    assert all(err <= 3.0 * sig for err, sig in errs)


def test_on_time_frames_unchanged():
    fl = FrameLateness()
    for with_source in (True, False):
        fl = FrameLateness()
        for e, a in frames([], n=3000):
            late = fl.observe(a, e if with_source else None)
            assert late == (0.0, 0.0, "") and meta_fields(*late) == {}
    assert lateness_sigma({}, SPEED, SIGMA) == (SIGMA, None)
    assert lateness_sigma({"late_s": 0.0}, SPEED, SIGMA) == (SIGMA, None)


def test_burst_tail_stays_flagged_until_release():
    """Hysteresis: after a frame beyond late_s, 0.05-0.3 s late frames (a burst's tail) stay late."""
    fl = FrameLateness()
    for k in range(20):
        assert fl.observe(k * 0.1 + 0.2, k * 0.1) == (0.0, 0.0, "")
    assert fl.observe(2.0 + 0.2 + 1.0, 2.0)[2] == "camera_stamp"
    assert math.isclose(fl.observe(2.1 + 0.2 + 0.2, 2.1)[0], 0.2, abs_tol=1e-6)   # below 0.3 s: still re-dated
    assert fl.observe(2.2 + 0.2 + 0.01, 2.2) == (0.0, 0.0, "")                     # released
    assert fl.observe(2.3 + 0.2 + 0.2, 2.3) == (0.0, 0.0, "")                      # 0.2 s alone: on time


def test_lateness_sigma_rules():
    m = {"late_s": 0.5, "late_basis": "interval", "late_redated": False}
    assert math.isclose(lateness_sigma(m, SPEED, SIGMA)[0], math.hypot(SIGMA, 30.0))
    assert lateness_sigma(dict(m, late_s=1.5), SPEED, SIGMA)[1]              # 90 m > 60 m gate
    assert lateness_sigma(dict(m, late_redated=True, late_s=2.0), SPEED, SIGMA) == (SIGMA, None)
    assert lateness_sigma(dict(m, late_s="x"), SPEED, SIGMA) == (SIGMA, None)
    assert lateness_sigma(dict(m, late_s=1.5), 0.0, SIGMA) == (SIGMA, None)   # hovering: no along-track error
