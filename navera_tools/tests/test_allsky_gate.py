"""All-sky identification and its quality gate (allsky.identify / accept), on synthetic rays."""
import os

import numpy as np
import pytest

from navera_tools.field import allsky

BSC5 = os.path.expanduser("~/.navera_sim/bsc5.dat")
pytestmark = pytest.mark.skipif(not os.path.exists(BSC5), reason="Yale catalogue not installed")


@pytest.fixture(scope="module")
def cat():
    return allsky.Catalogue(limit_mag=4.0)


def _random_rotation(rng):
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def test_true_stars_are_identified_and_accepted(cat):
    rng = np.random.default_rng(3)
    R = _random_rotation(rng)                                   # IMU → ICRS
    zen = cat.vec[0]
    near = np.nonzero(cat.vec @ zen > np.cos(np.radians(70)))[0]
    bright = near[np.argsort(cat.mag[near])][:30]
    rays = cat.vec[bright] @ R                                  # R.T @ v: the stars in the IMU frame
    rays += rng.normal(0, np.radians(0.03), rays.shape)
    rays /= np.linalg.norm(rays, axis=1, keepdims=True)
    Rf, idx, kidx, rms, p = allsky.identify(rays, cat, with_p=True)
    ang = np.degrees(np.arccos(np.clip((np.trace(Rf.T @ R) - 1) / 2, -1, 1)))
    assert ang < 0.05 and len(idx) >= 25
    assert allsky.accept(len(idx), rms, p) is None
    assert len(allsky.identify(rays, cat)) == 4                 # the bench scripts unpack four values


@pytest.mark.parametrize("seed", range(4))
def test_random_points_are_refused(cat, seed):
    rng = np.random.default_rng(100 + seed)
    rays = rng.normal(size=(60, 3))
    rays[:, 2] = np.abs(rays[:, 2])                             # one hemisphere, like the sky above the camera
    rays /= np.linalg.norm(rays, axis=1, keepdims=True)
    r = allsky.identify(rays, cat, with_p=True)
    if r is not None:                                           # some chance alignment is always found ...
        assert allsky.accept(len(r[1]), r[3], r[4]) is not None  # ... and must never be accepted


def test_gate_thresholds():
    assert allsky.accept(10, 0.08, 1e-8) is None
    assert allsky.accept(7, 0.05, 9e-6) is None                 # few stars, all fitting tightly
    assert allsky.accept(10, 0.31, 1e-2) is not None            # real bench: wrong match among room features
    assert allsky.accept(13, 0.169, 1.3e-6) is not None         # real bench: right but not provable
    assert allsky.accept(30, 0.05, 1e-20, lens_disagree_deg=2.0) is not None
