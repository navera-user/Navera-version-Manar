"""D11: the tilt of 'up' learned online must survive bad calibration samples.

The first stopped fixes with a reference position teach the tilt of 'up' (allsky_mount.TiltCalibration, the field
server's _tilt_corrected). A sample can be bad: a 'stopped' frame taken while the car accelerated gently ('up'
0.3-7 deg off, D12), a stale phone position, a wrong star identification. Synthetic samples (no catalogue needed):
a 1 deg tilt, 0.05 deg of noise per sample, bad samples 1.5-8 deg off.
"""
import math

import numpy as np
import pytest

from cn_pkg import allsky_mount as am

TRUE_TILT_DEG = 1.0


def _rand_rot(rng):
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    x, y, z, w = q
    return am.quat_to_matrix((x, y, z, w))


def _small_rot(rng, deg, perp_to=None):
    axis = rng.normal(size=3)
    if perp_to is not None:
        axis -= axis @ perp_to * perp_to
    axis /= np.linalg.norm(axis)
    return am.rotvec(math.radians(deg) * axis)


def _samples(n, bad=(), seed=0, noise_deg=0.05):
    """[(R_icrs_imu, up, z_true)]: up near the camera's +x (standing), z_true = R (Q0 up) + noise; samples whose
    index is in bad get z_true moved by 1.5-8 deg (what a 'stopped' frame taken while moving does).
    """
    rng = np.random.default_rng(seed)
    up0 = np.array([1.0, 0.0, 0.0])
    Q0 = am.rotvec(math.radians(TRUE_TILT_DEG) * np.array([0.0, 0.6, -0.8]))
    out = []
    for k in range(n):
        up = _small_rot(rng, rng.uniform(0, 3)) @ up0              # the parked car's own tilt varies a little
        R = _rand_rot(rng)
        z = R @ (Q0 @ up)
        z = _small_rot(rng, abs(rng.normal(0, noise_deg))) @ z
        if k in bad:
            z = _small_rot(rng, rng.uniform(1.5, 8.0), perp_to=z) @ z
        out.append((R, up, z))
    return out, Q0


def _tilt_error_deg(fit, Q0, samples):
    """How far the fitted correction leaves 'up' from the truth on a fresh, clean sample set (deg, worst)."""
    clean, _ = _samples(20, seed=99, noise_deg=0.0)
    errs = []
    for R, up, _ in clean:
        z_fit = R @ (fit["Q"] @ up)
        z_true = R @ (Q0 @ up)
        errs.append(math.degrees(math.acos(min(1.0, float(z_fit @ z_true)))))
    return max(errs)


def test_clean_samples_fit_as_before():
    s, Q0 = _samples(12)
    robust, plain = am.fit_tilt(s), am.fit_tilt(s, robust=False)
    assert robust["ok"] and robust["rejected"] == []
    assert _tilt_error_deg(robust, Q0, s) < 0.05
    assert _tilt_error_deg(robust, Q0, s) == pytest.approx(_tilt_error_deg(plain, Q0, s), abs=0.01)


@pytest.mark.parametrize("bad", [(0,), (0, 1), (1, 5, 9), (0, 2, 4, 6)])
def test_bad_samples_among_the_first_12_are_rejected(bad):
    s, Q0 = _samples(12, bad=bad, seed=len(bad))
    plain = am.fit_tilt(s, robust=False)
    fit = am.fit_tilt(s)
    assert fit["ok"], fit["why"]
    assert sorted(fit["rejected"]) == sorted(bad)
    assert fit["n"] == 12 - len(bad) and fit["n_total"] == 12
    assert _tilt_error_deg(fit, Q0, s) < 0.06
    assert _tilt_error_deg(plain, Q0, s) > 0.2            # what the bad samples did to the plain fit
    assert fit["sigma_deg"] < 0.15                        # the stated sigma is the good samples' residual


def test_no_majority_is_not_applied():
    s, _ = _samples(4, bad=(0, 1), seed=3)
    fit = am.fit_tilt(s)
    assert not fit["ok"] and ("majority" in fit["why"] or "agree" in fit["why"])


def test_implausible_tilt_is_not_applied():
    rng = np.random.default_rng(5)
    s = []
    Q = am.rotvec(math.radians(8.0) * np.array([0.0, 1.0, 0.0]))
    for _ in range(8):
        R, up = _rand_rot(rng), _small_rot(rng, 1.0) @ np.array([1.0, 0, 0])
        s.append((R, up, R @ (Q @ up)))
    fit = am.fit_tilt(s)
    assert not fit["ok"] and "not a mounting error" in fit["why"]


def test_calibration_keeps_learning_past_outliers_then_freezes():
    """The first 4 samples hold 2 bad ones: no fit is applied until a majority agrees; outliers do not count
    towards the 12, so the calibration freezes on 12 agreeing samples, and the correction is right.
    """
    s, Q0 = _samples(20, bad=(0, 1, 7), seed=11)
    cal = am.TiltCalibration(min_samples=4, max_samples=12)
    applied = []
    for k, (R, up, z) in enumerate(s):
        if cal.frozen:
            break
        cal.add(R, up, z)
        applied.append(cal.fit is not None)
    assert applied[3] is False                          # 4 samples, 2 bad: no clear majority yet
    assert cal.frozen and cal.fit["n"] == 12 and sorted(cal.fit["rejected"]) == [0, 1, 7]
    assert len(cal.samples) == 15
    assert _tilt_error_deg(cal.fit, Q0, s) < 0.06


def test_calibration_gives_up_after_twice_the_samples():
    rng = np.random.default_rng(2)
    cal = am.TiltCalibration(min_samples=4, max_samples=4)
    for _ in range(20):
        R, up = _rand_rot(rng), np.array([1.0, 0, 0])
        cal.add(R, up, _rand_rot(rng) @ np.array([0, 0, 1.0]))       # nothing agrees
    assert cal.frozen and len(cal.samples) == 8 and cal.fit is None
