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
        gps_hz=5.0, t0=10.0, gps_noise=0.0):
    """GPS at gps_hz on `track`; a vision fix every `period` s, of the ground seen at the exposure,
    offset + noise, arriving `delay` s later.
    """
    rng, grng = np.random.default_rng(seed), np.random.default_rng(seed + 100)
    tg = t0 - 6.0
    t = t0
    while t < t0 + duration:
        arrival = t + delay
        while tg <= arrival + 1.0:
            ge, gn = track(tg)
            if gps_noise > 0:                          # its own generator: the vision noise stays the same
                ge, gn = ge + grng.normal(0, gps_noise), gn + grng.normal(0, gps_noise)
            cal.add_gps(tg, *ll(ge, gn))
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
    the stated sigma says so and the delay is not applied as stable (the bench at 20 m/s: 1.3 s
    for 1.7 s) — for a set delay; an unknown one gets the staged correction with that sigma.
    """
    cal = fly(LatencyCalibrator(nominal_s=0.5), circle(20.0, 300.0), 1.0, 90.0, noise=3.0)
    assert abs(cal.estimate - 1.0) < 0.15
    assert cal.sigma > 0.1 and cal.applied is None and "sigma" in cal.reason
    cal = fly(LatencyCalibrator(), circle(20.0, 300.0), 1.0, 90.0, noise=3.0)
    assert not cal.stable and "partial" in cal.reason
    assert cal.applied_sigma > 0.1 and abs(cal.applied - 1.0) < 2 * cal.applied_sigma


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
    cal = fly(LatencyCalibrator(min_samples=20, partial_min_samples=20), circle(60.0, 900.0), 1.0, 15.0)
    assert cal.samples < 20 and cal.applied is None and "samples" in cal.reason
    cal = fly(LatencyCalibrator(min_samples=20), circle(60.0, 900.0), 1.0, 8.0)
    assert cal.samples < 10 and cal.applied is None and cal.delay_sigma() is None


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


def test_a_noisy_gps_on_a_straight_leg_is_not_a_turn():
    """10 m/s, 0.3 m of GPS noise per fix: samples are taken (were all refused as "turning")."""
    cal = fly(LatencyCalibrator(), circle(10.0, None), 1.0, 60.0, gps_noise=0.3)
    assert cal.samples > 40 and cal.rejected.get("turning", 0) < 5


def test_a_sharp_turn_is_still_refused_with_a_noisy_gps():
    cal = fly(LatencyCalibrator(), circle(60.0, 150.0), 1.0, 30.0, gps_noise=0.3)
    assert cal.samples == 0 and cal.rejected.get("turning", 0) > 20


# ── staged apply, prior, stored delay (F31: Isaac Sim closed loop 2026-10-21) ─────────────────────
def leg_turn_leg(v=10.0, t_turn=40.0, turn_deg=135.0, turn_s=6.0):
    """A copter leg east at v, a turn of turn_deg over turn_s, a second leg: the campaign's circuit."""
    w = math.radians(turn_deg) / turn_s

    def track(t):
        if t <= t_turn:
            return v * t, 0.0
        e0, tt = v * t_turn, min(t - t_turn, turn_s)
        # constant-rate turn (left), then straight on the new heading
        r = v / w
        e, n = e0 + r * math.sin(w * tt), r * (1 - math.cos(w * tt))
        if t > t_turn + turn_s:
            h = math.radians(turn_deg)
            e, n = e + v * (t - t_turn - turn_s) * math.cos(h), n + v * (t - t_turn - turn_s) * math.sin(h)
        return e, n
    return track


def test_staged_apply_is_the_posterior_with_the_unknown_prior():
    """Sigma between max_sigma and partial_max_sigma: applied = the estimate shrunk towards 0.

    By 1 / (1 + sigma^2) (prior 0 +- 1 s), its sigma the posterior's.
    """
    cal = fly(LatencyCalibrator(), leg_turn_leg(), 1.3, 70.0, noise=4.0, offset=(5.0, 3.0))
    assert 0.1 < cal.sigma <= 0.5 and not cal.stable
    w = 1.0 / (1.0 + cal.sigma ** 2)
    hist = [(t, a, s) for t, a, s in cal._applied_at]
    assert hist and math.isclose(cal.applied, hist[-1][1])
    assert cal.applied < cal.estimate or cal.estimate <= 0          # shrunk towards the prior
    assert abs(cal.applied - 1.3) < 3 * cal.applied_sigma and cal.applied_sigma < cal.sigma
    assert math.isclose(cal.applied_sigma, math.sqrt(w) * cal.sigma, rel_tol=0.3)   # last update's sigma
    assert cal.delay_sigma() == cal.applied_sigma and cal.state()["applied_sigma_s"] is not None


def test_straight_leg_only_is_never_applied_even_staged():
    cal = fly(LatencyCalibrator(), circle(10.0, None), 1.3, 75.0, noise=4.0)
    assert cal.applied is None and cal.delay_sigma() is None


def test_hover_is_never_applied():
    cal = fly(LatencyCalibrator(), lambda t: (0.3 * math.sin(t), 0.2 * math.cos(t)), 1.3, 75.0)
    assert cal.samples == 0 and cal.applied is None


@pytest.mark.parametrize("seed", range(6))
def test_wrong_samples_are_not_applied_wrong(seed):
    """Vision fixes unrelated to the delay (40 m of white noise, 20 % gross outliers): whatever is
    applied stays within 3 of its own sigmas of the truth.
    """
    cal = fly(LatencyCalibrator(), leg_turn_leg(), 1.3, 75.0, noise=40.0, outliers=0.2, seed=seed)
    if cal.applied is not None:
        assert abs(cal.applied - 1.3) <= 3 * cal.applied_sigma


@pytest.mark.parametrize("delay", [0.1, 0.6, 1.3, 2.2])
@pytest.mark.parametrize("seed", range(4))
def test_staged_apply_reduces_the_delay_error(delay, seed):
    """Whatever the true delay, what is applied is closer to it than nothing (0), and within 3 sigma."""
    cal = fly(LatencyCalibrator(), leg_turn_leg(), delay, 75.0, noise=4.0, seed=seed)
    if cal.applied is not None:
        assert abs(cal.applied - delay) <= max(3 * cal.applied_sigma, 0.05)
        assert abs(cal.applied - delay) <= delay + 0.05


def test_a_set_delay_gets_no_staged_correction():
    cal = fly(LatencyCalibrator(nominal_s=0.4), leg_turn_leg(), 1.3, 70.0, noise=4.0)
    assert cal.prior is None and not cal.stable and cal.applied is None and cal.delay_sigma() == 0.1


def test_spoof_drift_in_the_rollback_window_is_undone():
    """A GPS dragged at 3 m/s over the last 20 s, then refused: the staged value of that time is
    dropped with its samples (rollback), back to what was applied before the drift.
    """
    track = leg_turn_leg(t_turn=30.0)
    cal = fly(LatencyCalibrator(), track, 1.3, 50.0, noise=4.0)
    t_end = 60.0

    def dragged(t):
        e, n = track(t)
        return e + 3.0 * max(0.0, t - t_end), n
    rng = np.random.default_rng(5)
    for k in range(int(t_end * 5) + 1, int((t_end + 20.0) * 5)):
        t = k / 5.0
        cal.add_gps(t, *ll(*dragged(t)))
        if k % 5 == 0 and t + 1.3 < t_end + 19.0:
            e, n = track(t - 1.3)
            cal.add_fix(t, *ll(e + 40.0 + rng.normal(0, 4.0), n - 25.0 + rng.normal(0, 4.0)))
    during, cut = (cal.applied, cal.applied_sigma), cal._t[-1] - 20.0
    before = [(x, sx) for t, x, sx in cal._applied_at if t <= cut]
    cal.freeze("GPS refused", rollback_s=20.0)
    assert cal._t[-1] <= t_end and before and (cal.applied, cal.applied_sigma) == before[-1] != during
    assert abs(cal.applied - 1.3) <= 3 * cal.applied_sigma


def test_stored_prior_starts_the_flight_and_is_refined():
    cal = LatencyCalibrator()
    assert cal.set_prior(1.25, 0.2, "stored")
    assert cal.applied == 1.25 and cal.delay_sigma() == 0.2 and math.isclose(cal.correction(), 1.25)
    fly(cal, leg_turn_leg(), 1.3, 70.0, noise=4.0)
    assert abs(cal.applied - 1.3) < 0.15 and cal.applied_sigma < 0.2 and "stored" in cal.prior_source


def test_a_contradicted_stored_prior_is_dropped():
    """Another camera / stream setting: the stored 0.3 s against a measured 1.3 s."""
    cal = LatencyCalibrator()
    cal.set_prior(0.3, 0.1, "stored")
    fly(cal, leg_turn_leg(), 1.3, 70.0, noise=4.0)
    assert "contradicted" in cal.reason or cal.prior_source == "unknown delay"
    assert abs(cal.applied - 1.3) < 3 * cal.applied_sigma


def test_rollback_without_earlier_value_returns_to_the_stored_start():
    cal = LatencyCalibrator()
    cal.set_prior(1.2, 0.3, "stored")
    fly(cal, leg_turn_leg(t_turn=5.0), 1.3, 25.0, noise=4.0)
    cal.freeze("GPS refused", rollback_s=60.0)
    assert (cal.applied, cal.applied_sigma) == (1.2, 0.3)


def test_set_prior_refused_for_a_set_delay_or_out_of_range():
    assert not LatencyCalibrator(nominal_s=0.4).set_prior(1.0, 0.1)
    assert not LatencyCalibrator().set_prior(5.0, 0.1)
    assert not LatencyCalibrator().set_prior(1.0, 0.0)


def test_persist_keeps_the_measured_delay_for_the_next_flight(tmp_path, monkeypatch):
    from navera_common import latency_cal
    monkeypatch.setenv("NAVERA_STATE_DIR", str(tmp_path))
    cal = LatencyCalibrator()
    cal.store_key = "hik_visible_lens.yaml"
    assert not cal.persist()                           # nothing measured yet: nothing written
    fly(cal, leg_turn_leg(), 1.3, 70.0, noise=4.0)
    assert cal.persist() and not cal.persist()         # written once
    kept = latency_cal.load_stored("hik_visible_lens.yaml", 3600.0)
    assert kept == (pytest.approx(cal.applied), pytest.approx(cal.applied_sigma))
    assert latency_cal.load_stored("other_lens.yaml", 3600.0) is None
    cal.freeze("GPS refused", rollback_s=1e6)          # everything undone: back to what we started from
    assert cal.applied is None and cal.persist()
    assert latency_cal.load_stored("hik_visible_lens.yaml", 3600.0) is None


def test_store_key_from_the_calibration_file(monkeypatch):
    from navera_common.latency_cal import store_key
    monkeypatch.setenv("NAVERA_CAMERA_CALIBRATION", "/etc/navera/hik_visible_lens_2026-10-20.yaml")
    assert store_key("") == "hik_visible_lens_2026-10-20.yaml" and store_key(" cam2 ") == "cam2"
    monkeypatch.delenv("NAVERA_CAMERA_CALIBRATION")
    assert store_key("") == "camera"


def test_set_nominal_from_the_camera_replaces_the_unknown_prior_and_a_stored_start():
    cal = LatencyCalibrator()
    cal.store_key = "lens.yaml"
    cal.set_prior(1.1, 0.2, "stored")
    assert cal.set_nominal(1.3, "camera")
    assert cal.nominal == 1.3 and cal.applied is None and cal.prior is None and cal.store_key is None
    assert cal.delay() == 1.3 and cal.correction() == 0.0 and cal.delay_sigma() == 0.1
    assert not cal.set_nominal(1.3) and not cal.set_nominal(9.0)


def test_set_nominal_refused_once_samples_exist():
    cal = fly(LatencyCalibrator(), leg_turn_leg(), 1.3, 30.0, noise=4.0)
    assert cal.samples and not cal.set_nominal(1.3) and cal.nominal == 0.0


def test_the_staged_delay_is_not_applied_when_speed_times_its_sigma_is_too_large():
    """A plane at 30 m/s whose staged estimate is 1.11 +- 0.38 s (11 m along the track) keeps the
    unknown delay (Isaac Sim m1_plane30: 0.58 +- 0.44 s staged for 1.3 s, 6 wrong fixes); without the
    cap the same samples are applied. A copter at 10 m/s with a like sigma (3 m) applies it."""
    capped = fly(LatencyCalibrator(partial_min_z=0.0), circle(30.0, 600.0), 1.3, 30.0, noise=8.0)
    assert not capped.stable and capped.applied is None and "not applied: 30 m/s" in capped.reason
    assert capped.delay_sigma() is None                # still unknown: the stated sigma keeps the prior
    free = fly(LatencyCalibrator(partial_max_error_m=0.0), circle(30.0, 600.0), 1.3, 30.0, noise=8.0)
    assert free.applied is not None and free.applied_sigma > 10.0 / 30.0
    copter = fly(LatencyCalibrator(), circle(10.0, 200.0), 1.3, 40.0, noise=3.0)
    assert not copter.stable and copter.applied is not None and 10.0 * copter.applied_sigma <= 10.0
    assert abs(copter.applied - 1.3) < 2 * copter.applied_sigma


def test_a_stable_delay_is_applied_whatever_the_speed():
    cal = fly(LatencyCalibrator(partial_max_error_m=1.0), circle(60.0, 900.0), 1.0, 60.0)
    assert cal.stable and abs(cal.applied - 1.0) < 0.05


def test_a_contradicted_stored_delay_is_not_kept_when_the_staged_one_is_capped():
    cal = LatencyCalibrator(partial_min_z=0.0)
    assert cal.set_prior(0.2, 0.15, "stored")
    fly(cal, circle(30.0, 600.0), 1.3, 30.0, noise=8.0)
    assert cal.prior_source == "unknown delay" and "not applied" in cal.reason     # the stored 0.2 s dropped
    assert cal.applied is None and cal.delay() == 0.0


def _staged(speed, d, sig, **kw):
    """The staged-apply decision alone: an estimate d +- sig at ground speed `speed`."""
    cal = LatencyCalibrator(**kw)
    cal.speed_mps = speed
    cal._t.append(0.0)
    cal._apply_posterior(d, sig, True, staged=True)
    return cal


def test_a_staged_delay_surely_not_zero_is_applied_above_the_speed_cap():
    """Isaac Sim p1_plane60_turns (2026-10-29): 1.25 +- 0.24 s for a true 1.3 s at 65 m/s was capped
    (65 x 0.23 = 15 m > 10 m) and every fix stayed ~80 m behind; the posterior is 4.9 of its sigmas
    from 0, so keeping 0 costs 5 x more than applying it. m1_plane30's 0.58 +- 0.44 s (1.2 sigma from
    0 once shrunk) stays capped."""
    cal = _staged(65.0, 1.25, 0.24)
    w = 1.0 / (1.0 + 0.24 ** 2)
    assert math.isclose(cal.applied, w * 1.25) and math.isclose(cal.applied_sigma, math.sqrt(w) * 0.24)
    assert "applied although 65 m/s" in cal.reason and cal.delay_sigma() == cal.applied_sigma
    assert _staged(30.0, 0.58, 0.44).applied is None
    assert _staged(65.0, 1.25, 0.24, partial_min_z=0.0).applied is None      # the exception off: capped
    assert _staged(65.0, 0.6, 0.45).applied is None                          # 1.2 sigma from 0: capped


@pytest.mark.parametrize("seed", range(3))
def test_a_fast_plane_on_a_wide_turn_gets_the_staged_delay_only_when_sure(seed):
    """A jet at 60 m/s on a 3 km circle (~1.1 deg/s, the delay barely observable): whatever is applied
    is the posterior within 3 sigma of the truth and closer to it than 0."""
    cal = fly(LatencyCalibrator(), circle(60.0, 3000.0), 1.3, 40.0, noise=8.0, seed=seed)
    if cal.applied is not None:
        assert abs(cal.applied - 1.3) <= 3 * cal.applied_sigma and abs(cal.applied - 1.3) < 1.3
        assert cal.applied >= 3.0 * cal.applied_sigma


def test_the_camera_takes_the_attitude_at_the_day_nodes_dating():
    from navera_common.latency_cal import attitude_shift_s, delay_message
    cal = fly(LatencyCalibrator(), circle(60.0, 900.0), 1.0, 60.0)
    msg = delay_message(cal, True)
    assert msg["auto"] and abs(msg["correction_s"] - 1.0) < 0.05 and msg["stable"]
    assert attitude_shift_s(msg, 0.0) == msg["correction_s"]
    assert delay_message(cal, False)["correction_s"] == 0.0 and attitude_shift_s(delay_message(cal, False), 0.0) == 0.0
    # the camera already subtracted 0.4 s: the day node's correction is relative to it (no double subtraction)
    cal2 = LatencyCalibrator()
    assert cal2.set_nominal(0.4)
    fly(cal2, circle(60.0, 900.0), 1.0, 60.0)
    assert abs(delay_message(cal2, True)["correction_s"] - 0.6) < 0.05
    # never an exposure after the arrival, never beyond the bound, nothing from garbage
    assert attitude_shift_s({"auto": True, "correction_s": -1.0}, 0.4) == -0.4
    assert attitude_shift_s({"auto": True, "correction_s": 9.0}, 0.0, 3.0) == 3.0
    assert attitude_shift_s({"auto": True, "correction_s": "x"}, 0.0) == 0.0
    assert attitude_shift_s({"auto": True, "correction_s": float("nan")}, 0.0) == 0.0
    assert attitude_shift_s(None, 0.0) == 0.0
