"""navera_common.gps_motion_check: GPS displacement vs visual odometry against slow spoofing."""
import cmath
import math
import random

from navera_common.gps_motion_check import GpsMotionCheck


def _fly(m, seconds, speed=20.0, turn_dps=0.0, vo_gain=1.0, vo_noise=0.7, fix_noise=15.0, gps_noise=0.3,
         drift=None, t_drift=0.0, seed=1, fix_period=2.0, start=0.0, lock_every=0):
    """Fly m through `seconds` of 1 s odometry steps and a map fix every fix_period. vo_gain: what the
    odometry measures per metre of ground (complex: scale and rotation). drift: GPS pulled at this
    (east, north) m/s from t_drift on. Returns (t, reason) of the first refusal, or None.
    """
    rng = random.Random(seed)
    p, hdg = 0j, 0.3
    gps_prev, t = None, start
    next_fix = start
    for k in range(int(seconds)):
        t0, t1 = t, t + 1.0
        hdg += math.radians(turn_dps)
        step = speed * cmath.exp(1j * (math.pi / 2 - hdg))       # east + i north
        p1 = p + step
        d = drift if drift is not None else (0.0, 0.0)
        g = [p + complex(d[0], d[1]) * max(0.0, t0 - t_drift), p1 + complex(d[0], d[1]) * max(0.0, t1 - t_drift)]
        g = [x + complex(rng.gauss(0, gps_noise), rng.gauss(0, gps_noise)) for x in g]
        if gps_prev is not None:
            g[0] = gps_prev
        gps_prev = g[1]
        vo = step * vo_gain + complex(rng.gauss(0, vo_noise), rng.gauss(0, vo_noise))
        if lock_every and k % lock_every == lock_every - 1:
            vo = 0j                                             # a lock on what does not move
        why = m.add_step(t0, t1, vo.real, vo.imag, (g[1] - g[0]).real, (g[1] - g[0]).imag)
        if why:
            return t1, why, abs(complex(*d)) * max(0.0, t1 - t_drift)
        while next_fix <= t1:
            f = p + step * (next_fix - t0) + complex(rng.gauss(0, fix_noise), rng.gauss(0, fix_noise))
            gps_at = p + step * (next_fix - t0) + complex(*d) * max(0.0, next_fix - t_drift)
            m.add_fix(next_fix, f.real, f.imag, ((gps_at - f).real, (gps_at - f).imag))
            next_fix += fix_period
        p, t = p1, t1
    return None


def test_a_good_gps_is_never_refused():
    for seed in range(5):
        for turn in (0.0, 3.0):
            m = GpsMotionCheck()
            assert _fly(m, 1200, turn_dps=turn, seed=seed) is None


def test_the_odometry_scale_and_heading_are_learned_from_the_map_fixes_alone():
    m = GpsMotionCheck()
    gain = 0.9 * cmath.exp(1j * math.radians(4.0))          # VO 10 % short, turned 4 deg
    assert _fly(m, 300, vo_gain=gain, turn_dps=2.0) is None
    c, eps, n = m.gain
    assert n > 20 and abs(c * gain - 1.0) < 0.02 and eps < 0.06
    # GPS plays no part: the same flight with GPS pulled away learns the same c
    m2 = GpsMotionCheck(h=1e9)
    _fly(m2, 300, vo_gain=gain, turn_dps=2.0, drift=(3.0, 0.0), t_drift=60.0)
    assert abs(m2.gain[0] - c) < 1e-9


def test_without_calibration_there_is_no_test():
    m = GpsMotionCheck()
    assert _fly(m, 300, fix_period=1e9, drift=(5.0, 0.0), t_drift=20.0) is None
    assert m.gain[2] == 0


def test_a_slow_spoof_is_refused_well_before_the_fixes_could_see_it():
    # the size and growth rules need ~2 x the fixes' 30 m sigma; the scale allowance is ~3-5 % of the
    # speed (map fixes 15 m) plus bias_mps 0.5: 3 m/s at 20 m/s, 2 m/s at 8 m/s
    for v, speed, limit in ((3.0, 20.0, 30.0), (2.0, 8.0, 50.0)):
        m = GpsMotionCheck()
        r = _fly(m, 600, speed=speed, drift=(0.0, v), t_drift=240.0, turn_dps=1.0)
        assert r is not None and r[0] > 240.0
        assert r[2] < limit, r
        assert "more than visual odometry" in r[1]


def test_the_baseline_to_come_back_to_is_the_offset_before_the_drift():
    m = GpsMotionCheck()
    r = _fly(m, 600, drift=(3.0, 0.0), t_drift=240.0, fix_noise=2.0)
    assert r is not None
    e, n, growth = m.refused_baseline
    assert math.hypot(e, n) < 5.0 and growth >= m.min_growth


def test_a_lock_on_what_does_not_move_is_left_out():
    m = GpsMotionCheck()
    assert _fly(m, 1200, lock_every=7) is None
    assert m.skipped >= 1200 // 7 - 5


def test_noisier_odometry_widens_the_test_by_itself():
    m = GpsMotionCheck()
    assert _fly(m, 1200, vo_noise=4.0) is None
    assert m.sigma > 3.0


def test_in_doubt_before_the_refusal():
    m = GpsMotionCheck(min_growth_m=1e9)
    _fly(m, 250, drift=(0.0, 3.0), t_drift=240.0)
    assert m.in_doubt
