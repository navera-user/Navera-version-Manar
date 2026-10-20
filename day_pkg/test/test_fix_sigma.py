"""day_pkg.fix_sigma: the stated sigma of a local match from its parts."""
import math

from day_pkg.fix_sigma import day_fix_sigma_m


def test_floor_and_matcher_sigma():
    assert day_fix_sigma_m(3.0, floor_m=5.0) == 5.0
    assert day_fix_sigma_m(12.0, floor_m=5.0) == 12.0
    assert day_fix_sigma_m(None, floor_m=5.0) == 5.0


def test_speed_and_attitude_terms_add_in_quadrature():
    s = day_fix_sigma_m(4.0, floor_m=5.0, speed_mps=60.0, delay_sigma_s=0.05,
                        height_m=1500.0, attitude_sigma_deg=0.5)
    att = 0.5 * 1500.0 * math.tan(math.radians(0.5))
    assert abs(s - math.sqrt(25.0 + 9.0 + att * att)) < 1e-9


def test_unknown_height_or_speed_adds_nothing():
    assert day_fix_sigma_m(8.0, height_m=float("nan")) == 8.0
    assert day_fix_sigma_m(8.0, speed_mps=None, height_m=None) == 8.0


def test_calibration_covers_this_flights_errors_honest_or_optimistic_model():
    import random
    from day_pkg.fix_sigma import SigmaCalibration
    rng = random.Random(1)
    for true_sigma in (10.0, 25.0):                   # model says 10 m: honest, then 2.5x optimistic
        cal = SigmaCalibration(floor_no_cal_m=30.0)
        draw = lambda: math.hypot(rng.gauss(0, true_sigma), rng.gauss(0, true_sigma))  # noqa: E731
        for _ in range(200):
            cal.add(draw(), 10.0)
        pub = cal.apply(10.0)
        assert pub >= 10.0
        inside = sum(draw() <= 3 * pub for _ in range(2000)) / 2000
        assert inside >= 0.99, (true_sigma, pub, inside)
        assert pub < 3 * true_sigma                   # and not absurdly wide


def test_never_calibrated_uses_the_floor_and_needs_min_samples():
    from day_pkg.fix_sigma import SigmaCalibration
    cal = SigmaCalibration(floor_no_cal_m=25.0, min_samples=15)
    assert cal.apply(8.0) == 25.0 and cal.apply(40.0) == 40.0
    for _ in range(14):
        cal.add(1.0, 10.0)
    assert cal.terms() is None
    cal.add(1.0, 10.0)
    f, b = cal.terms()
    assert f == 1.0 and abs(b - 1.0 / 2.4477) < 1e-9 and cal.apply(8.0) >= 8.0
    assert cal.state()["calibrated"] is True
