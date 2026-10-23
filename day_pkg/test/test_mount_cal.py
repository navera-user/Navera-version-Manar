"""F33: the camera boresight (mount) error learned in flight from GPS-check matches (day_pkg.mount_cal)."""
import math
import random

import pytest

from day_pkg.mount_cal import MountCalibration, axes


def _offset(heading, h, mf_deg, mr_deg):
    top, right = axes(heading)
    a, b = h * math.tan(math.radians(mf_deg)), h * math.tan(math.radians(mr_deg))
    return a * top[0] + b * right[0], a * top[1] + b * right[1]


def _fly(cal, mf=3.0, mr=-2.5, shift=(5.0, -3.0), headings=None, h=250.0, speed=10.0, delay=0.0,
         noise=4.0, n=60, t0=0.0, kind="frame centre", seed=1):
    rng = random.Random(seed)
    for i in range(n):
        hd = headings[i % len(headings)] if headings else (i * 360.0 / n * 2) % 360.0
        hh = h * (1.0 + 0.1 * math.sin(i))
        top, _ = axes(hd)
        v = (speed * top[0], speed * top[1])
        o = _offset(hd, hh, mf, mr)
        err = (o[0] + shift[0] + delay * v[0] + rng.gauss(0, noise),
               o[1] + shift[1] + delay * v[1] + rng.gauss(0, noise))
        cal.add(kind, err, hd, hh, t=t0 + i, vel_en=v)


def test_recovers_the_mount_error_over_a_circuit():
    cal = MountCalibration(prior_deg=2.0)
    _fly(cal)
    f = cal.fit("frame centre", delay_sigma_s=0.05)
    assert math.degrees(math.atan(f["m_f"])) == pytest.approx(3.0, abs=0.4)
    assert math.degrees(math.atan(f["m_r"])) == pytest.approx(-2.5, abs=0.4)
    assert f["b"][0] == pytest.approx(5.0, abs=2.5) and f["b"][1] == pytest.approx(-3.0, abs=2.5)
    assert cal.sigma_deg("frame centre", 0.05) < 0.5
    # the correction moves a vision position onto the truth (the map shift is the map bias' job)
    for hd in (0.0, 135.0, 260.0):
        c = cal.correction("frame centre", hd, 300.0, 0.05)
        o = _offset(hd, 300.0, 3.0, -2.5)
        assert math.hypot(c[0] - o[0], c[1] - o[1]) < 0.012 * 300.0


def test_not_learned_before_min_samples_nor_for_the_other_kind():
    cal = MountCalibration(prior_deg=2.0, min_samples=12)
    _fly(cal, n=11)
    assert cal.fit("frame centre") is None
    assert cal.correction("frame centre", 0.0, 250.0) == (0.0, 0.0)
    assert cal.sigma_deg("frame centre") == 2.0                  # the prior until learned
    _fly(cal, n=30, t0=100.0)
    assert cal.fit("frame centre") is not None and cal.fit("camera pose") is None
    assert cal.sigma_deg("camera pose") == 2.0


def test_one_heading_cannot_separate_a_map_shift_and_says_so():
    """Straight line, one heading: mount offset and map shift are the same vector; the posterior
    sigma stays near the prior on that axis instead of claiming a learned mount."""
    cal = MountCalibration(prior_deg=2.0)
    _fly(cal, headings=[90.0], n=80)
    assert cal.sigma_deg("frame centre", 0.05) > 1.0
    both = MountCalibration(prior_deg=2.0)
    _fly(both, n=80)
    assert both.sigma_deg("frame centre", 0.05) < 0.5 * cal.sigma_deg("frame centre", 0.05)


def test_a_residual_delay_is_not_learned_as_mount_when_the_speed_varies():
    cal = MountCalibration(prior_deg=3.0)
    rng = random.Random(4)
    for i in range(120):
        hd, h, sp = rng.uniform(0, 360), rng.uniform(150, 600), rng.uniform(2, 30)
        top, _ = axes(hd)
        v = (sp * top[0], sp * top[1])
        o = _offset(hd, h, 1.0, 0.5)
        cal.add("camera pose", (o[0] + 1.3 * v[0] + rng.gauss(0, 3), o[1] + 1.3 * v[1] + rng.gauss(0, 3)), hd, h,
                t=float(i), vel_en=v)
    f = cal.fit("camera pose", delay_sigma_s=1.0)
    assert f["d"] == pytest.approx(1.3, abs=0.15)
    assert math.degrees(math.atan(f["m_f"])) == pytest.approx(1.0, abs=0.3)


def test_outliers_do_not_move_it():
    cal = MountCalibration(prior_deg=2.0)
    _fly(cal, n=60)
    clean = cal.fit("frame centre", 0.05)
    for i in range(6):                                           # wrong matches 150-300 m off
        cal.add("frame centre", (150.0 + 30 * i, -200.0), 45.0 * i, 250.0, t=100.0 + i)
    f = cal.fit("frame centre", 0.05)
    assert abs(f["m_f"] - clean["m_f"]) < math.tan(math.radians(0.3))
    assert abs(f["m_r"] - clean["m_r"]) < math.tan(math.radians(0.3))


def test_rollback_forgets_recent_samples():
    cal = MountCalibration(min_samples=12)
    _fly(cal, n=20)
    _fly(cal, n=10, t0=50.0, kind="camera pose")
    assert cal.rollback(15.0) == 5 + 10
    assert cal.samples("frame centre") == 15 and cal.samples("camera pose") == 0


def test_bad_samples_are_ignored():
    cal = MountCalibration()
    assert not cal.add("frame centre", (1.0, 1.0), None, 250.0)
    assert not cal.add("frame centre", (1.0, 1.0), 10.0, None)
    assert not cal.add("frame centre", (float("nan"), 1.0), 10.0, 250.0)
    assert not cal.add("frame centre", (1.0, 1.0), 10.0, 2.0)          # on the ground
    assert not cal.add("somewhere", (1.0, 1.0), 10.0, 250.0)
    assert cal.samples("frame centre") == 0
    st = cal.state()
    assert st["frame centre"] == {"samples": 0, "calibrated": False, "persisted": False, "sigma_deg": 2.0}


def test_a_persisted_calibration_applies_from_the_first_frame():
    """GPS only for the take-off: no in-flight sample, the persisted calibration is the estimate."""
    cal = MountCalibration(prior_deg=2.0)
    assert cal.load({"frame centre": {"top_deg": 3.0, "right_deg": -2.5, "sigma_deg": 0.2},
                     "source": "flight 2026-10-21"}, min_sigma_deg=0.5) == 1
    assert cal.sigma_deg("frame centre") == pytest.approx(0.5)            # floored: the camera may have moved
    assert cal.sigma_deg("camera pose") == 2.0
    c = cal.correction("frame centre", 90.0, 250.0)
    o = _offset(90.0, 250.0, 3.0, -2.5)
    assert c == pytest.approx(o, abs=0.01)
    assert cal.state()["frame centre"]["persisted"] and cal.prior_source == "flight 2026-10-21"


def test_in_flight_samples_refine_a_stale_persisted_calibration():
    cal = MountCalibration(prior_deg=2.0)
    cal.set_prior("frame centre", 1.0, 0.0, 0.5)                          # camera re-fitted since
    _fly(cal, mf=3.0, mr=-2.5, n=80)
    f = cal.fit("frame centre", 0.05)
    assert math.degrees(math.atan(f["m_f"])) == pytest.approx(3.0, abs=0.5)
    assert math.degrees(math.atan(f["m_r"])) == pytest.approx(-2.5, abs=0.5)


def test_export_round_trip_and_rollback_window():
    cal = MountCalibration(min_samples=12)
    _fly(cal, n=40)
    assert cal.export(before_t=5.0) == {}                                  # too few samples before t
    ex = cal.export(delay_sigma_s=0.05)
    assert set(ex) == {"frame centre"} and ex["frame centre"]["samples"] >= 35
    new = MountCalibration()
    assert new.load(ex, min_sigma_deg=0.3) == 1
    assert new.correction("frame centre", 10.0, 300.0) == pytest.approx(
        cal.correction("frame centre", 10.0, 300.0, 0.05), abs=0.2)


def test_bad_persisted_values_are_ignored():
    cal = MountCalibration()
    assert cal.load(None) == 0 and cal.load({"frame centre": {"top_deg": "x"}}) == 0
    assert not cal.set_prior("frame centre", 30.0, 0.0, 1.0)               # beyond max_deg
    assert not cal.set_prior("frame centre", 1.0, 0.0, 0.0)


def test_heading_span():
    from day_pkg.mount_cal import heading_span_deg
    assert heading_span_deg([350.0, 10.0]) == pytest.approx(20.0)
    assert heading_span_deg([0.0, 90.0, 180.0]) == pytest.approx(180.0)
    assert heading_span_deg([10.0, 130.0, 250.0]) == pytest.approx(240.0)
    assert heading_span_deg([42.0]) == 0.0 and heading_span_deg([]) == 0.0


def test_a_climb_on_one_heading_is_not_learned_but_a_persisted_calibration_stays():
    """F41 (Isaac Sim h600, 2026-10-22): GPS checks during a climb on one heading (height 136-570 m) gave a
    1.2 deg 'mount' with a 0.33 deg sigma — a map shift — that put the fixes 16 m off instead of 10 m."""
    cal = MountCalibration(prior_deg=2.0, min_samples=12)
    for i in range(40):
        h = 136.0 + 11.0 * i
        cal.add("camera pose", (-7.0 + random.Random(i).gauss(0, 1.5), 8.0), 354.0, h, t=float(i), vel_en=(0.0, 0.3))
    assert cal.fit("camera pose") is None and cal.correction("camera pose", 89.0, 573.0) == (0.0, 0.0)
    assert cal.sigma_deg("camera pose") == 2.0 and cal.export() == {}
    assert cal.set_prior("camera pose", 0.5, -0.2, 0.6)
    assert cal.fit("camera pose")["n"] == 0                       # the persisted one alone
    _fly(cal, kind="camera pose", n=30, t0=100.0)                 # then a circuit: learned
    assert cal.fit("camera pose")["n"] > 12
