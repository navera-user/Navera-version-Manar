"""navera_common.latency_cal: the camera delay estimated online against a trusted GPS (synthetic tracks)."""
import math

import numpy as np
import pytest

from navera_common.latency_cal import LatencyCalibrator, shift_meta

LAT0, LON0 = 35.82, 10.61
M = 111320.0


def ll(e, n):
    return LAT0 + n / M, LON0 + e / (M * math.cos(math.radians(LAT0)))


def circle(v, radius):
    """Position (e, n m) at t on a circle flown at v m/s (radius=None: a straight line east)."""
    if radius is None:
        return lambda t: (v * t, 0.0)
    w = v / radius
    return lambda t: (radius * math.sin(w * t), radius * (1 - math.cos(w * t)))


def fly(cal, track, delay, duration, period=1.0, noise=3.0, offset=(40.0, -25.0), outliers=0.0, seed=1,
        gps_hz=5.0, t0=10.0):
    """GPS at gps_hz on `track`; a vision fix every `period` s, of the ground seen at the exposure,
    offset + noise, arriving `delay` s later."""
    rng = np.random.default_rng(seed)
    tg = t0 - 6.0
    t = t0
    while t < t0 + duration:
        arrival = t + delay
        while tg <= arrival + 1.0:
            cal.add_gps(tg, *ll(*track(tg)))
            tg += 1.0 / gps_hz
        e, n = track(t)
        e, n = e + offset[0] + rng.normal(0, noise), n + offset[1] + rng.normal(0, noise)
        if rng.random() < outliers:
            e, n = e + rng.uniform(-300, 300), n + rng.uniform(-300, 300)
        cal.add_fix(arrival, *ll(e, n))
        t += period
    return cal


@pytest.mark.parametrize("delay", [0.2, 1.0, 1.7])
@pytest.mark.parametrize("v,radius,duration,noise,tol", [(60.0, 900.0, 60.0, 3.0, 0.05),
                                                         (20.0, 300.0, 90.0, 1.5, 0.1)])
def test_recovers_the_delay_on_a_turning_track(delay, v, radius, duration, noise, tol):
    cal = fly(LatencyCalibrator(), circle(v, radius), delay, duration, noise=noise)
    assert abs(cal.estimate - delay) < tol
    assert cal.sigma < 0.1 and cal.stable
    assert abs(cal.applied - delay) < tol and abs(cal.delay() - delay) < tol
    assert abs(cal.offset_m[0] - 40.0) < 5 and abs(cal.offset_m[1] + 25.0) < 5     # the offset is not a delay


def test_slow_and_noisy_is_estimated_but_not_trusted_enough_to_apply():
    """20 m/s with 3 m of vision noise: the residual spread over the velocity spread is 0.15 s,
    the stated sigma says so and the delay is not applied (the bench at 20 m/s: 1.3 s for 1.7 s)."""
    cal = fly(LatencyCalibrator(), circle(20.0, 300.0), 1.0, 90.0, noise=3.0)
    assert abs(cal.estimate - 1.0) < 0.15
    assert cal.sigma > 0.1 and cal.applied is None and "sigma" in cal.reason


def test_outliers_do_not_move_it():
    cal = fly(LatencyCalibrator(), circle(60.0, 900.0), 1.0, 60.0, outliers=0.1)
    assert abs(cal.estimate - 1.0) < 0.05 and cal.stable


def test_a_straight_line_at_one_speed_cannot_separate_a_delay_from_an_offset():
    cal = fly(LatencyCalibrator(), circle(60.0, None), 1.0, 90.0)
    assert cal.samples > 50
    assert not cal.stable and cal.applied is None and cal.delay() == 0.0
    assert "sigma" in cal.reason or "bound" in cal.reason


def test_standing_still_gives_no_sample():
    cal = fly(LatencyCalibrator(), lambda t: (0.0, 0.0), 1.0, 60.0)
    assert cal.samples == 0 and cal.estimate is None and cal.applied is None
    assert cal.rejected.get("too slow", 0) > 50


def test_slow_motion_below_min_speed_is_ignored():
    cal = fly(LatencyCalibrator(min_speed_mps=5.0), circle(3.0, 100.0), 1.0, 60.0)
    assert cal.samples == 0


def test_samples_in_a_sharp_turn_are_dropped():
    # 60 m/s on a 150 m radius: 23 deg/s, beyond max_turn_dps 8
    cal = fly(LatencyCalibrator(), circle(60.0, 150.0), 1.0, 30.0)
    assert cal.samples == 0 and cal.rejected.get("turning", 0) > 20


def test_too_few_samples_never_applied():
    cal = fly(LatencyCalibrator(min_samples=20), circle(60.0, 900.0), 1.0, 15.0)
    assert cal.samples < 20 and cal.applied is None and "samples" in cal.reason


def test_a_set_delay_within_3_sigma_is_kept():
    """A well-measured hand value is not traded for a noisier estimate."""
    cal = fly(LatencyCalibrator(nominal_s=1.0), circle(60.0, 900.0), 1.02, 60.0)
    assert cal.stable and cal.applied is None and cal.delay() == 1.0 and cal.correction() == 0.0


def test_a_wrong_set_delay_is_corrected():
    cal = fly(LatencyCalibrator(nominal_s=0.4), circle(60.0, 900.0), 1.0, 60.0)
    assert abs(cal.delay() - 1.0) < 0.05 and abs(cal.correction() - 0.6) < 0.05


def test_frozen_when_gps_not_trusted_and_rollback_drops_the_last_samples():
    cal = fly(LatencyCalibrator(), circle(60.0, 900.0), 1.0, 60.0)
    n, applied = cal.samples, cal.applied
    cal.freeze("GPS lost")
    cal.add_fix(500.0, *ll(0.0, 0.0))                  # untrusted: ignored
    assert cal.samples == n and cal.applied == applied and cal.frozen and "frozen" in cal.state()["reason"]
    cal2 = fly(LatencyCalibrator(), circle(60.0, 900.0), 1.0, 60.0)
    cal2.freeze("GPS refused", rollback_s=20.0)
    assert cal2.samples < n - 15 and abs(cal2.applied - 1.0) < 0.05


def test_rollback_to_nothing_applied_when_nothing_was_stable_before():
    cal = fly(LatencyCalibrator(), circle(60.0, 900.0), 1.0, 30.0)
    cal.freeze("GPS refused", rollback_s=25.0)
    assert cal.applied is None and cal.delay() == 0.0


def test_a_fix_waits_for_the_gps_after_it():
    cal = LatencyCalibrator()
    tr = circle(60.0, 900.0)
    for k in range(60):
        cal.add_gps(k * 0.2, *ll(*tr(k * 0.2)))           # GPS up to 11.8 s
    cal.add_fix(11.8, *ll(*tr(10.8)))                  # needs GPS up to 12.3 s
    assert cal.samples == 0
    for k in range(60, 70):
        cal.add_gps(k * 0.2, *ll(*tr(k * 0.2)))
    assert cal.samples == 1


def test_gps_gap_drops_the_sample():
    cal = LatencyCalibrator()
    tr = circle(60.0, 900.0)
    for t in list(np.arange(0, 6, 0.2)) + list(np.arange(9, 14, 0.2)):   # 3 s hole
        cal.add_gps(t, *ll(*tr(t)))
    cal.add_fix(10.0, *ll(*tr(9.0)))
    assert cal.samples == 0 and cal.rejected.get("gps gap") == 1


def test_bounds_validated():
    with pytest.raises(ValueError):
        LatencyCalibrator(min_s=1.0, max_s=0.5)


def test_shift_meta_keeps_the_raw_stamp_and_is_idempotent():
    m = {"image_stamp_ns": 10_000_000_000}
    shift_meta(m, 0.6)
    assert m["image_stamp_raw_ns"] == 10_000_000_000 and m["image_stamp_ns"] == 9_400_000_000
    shift_meta(m, 0.5)                                 # from the raw stamp, not cumulative
    assert m["image_stamp_ns"] == 9_500_000_000
    assert shift_meta({"frame_id": 1}, 0.6) == {"frame_id": 1}


def test_state_is_json_ready():
    import json
    cal = fly(LatencyCalibrator(), circle(60.0, 900.0), 1.0, 30.0)
    st = json.loads(json.dumps(cal.state()))
    assert set(st) >= {"estimate_s", "sigma_s", "applied_s", "delay_s", "samples", "stable", "frozen", "reason"}
