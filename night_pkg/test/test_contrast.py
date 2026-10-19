"""stretch_contrast: the query's ground fills the 8 bits whatever the camera's AGC did."""
import numpy as np

from night_pkg.nodes.night_localizer import stretch_contrast


def _scene(rng, lo, hi, shape=(64, 64)):
    return rng.integers(lo, hi + 1, shape).astype(np.uint8)


def test_squeezed_ground_is_stretched():
    rng = np.random.default_rng(0)
    g = _scene(rng, 10, 22)                      # a linear AGC left the ground in 13 levels
    g[5, 5] = 255                                # the fire that took the range
    out = stretch_contrast(np.dstack([g] * 3))
    assert out.shape == (64, 64, 3)
    p1, p99 = np.percentile(out[..., 0], (1, 99))
    assert p1 <= 5 and p99 >= 250
    # order preserved (monotonic): polarity untouched
    order = np.argsort(g.ravel(), kind="stable")
    assert np.all(np.diff(out[..., 0].ravel()[order].astype(int)) >= 0)


def test_already_stretched_frame_nearly_unchanged():
    rng = np.random.default_rng(1)
    g = _scene(rng, 0, 255)
    out = stretch_contrast(np.dstack([g] * 3))[..., 0].astype(int)
    assert np.abs(out - g.astype(int)).mean() < 4.0


def test_empty_border_ignored_and_flat_frame_left_alone():
    rng = np.random.default_rng(2)
    g = _scene(rng, 100, 120)
    mask = np.full(g.shape, 255, np.uint8)
    mask[:, :16] = 0
    g[:, :16] = 0                                # empty wedge of a straightened frame
    out = stretch_contrast(np.dstack([g] * 3), mask)[..., 0]
    assert np.percentile(out[mask > 0], 99) >= 250 and np.percentile(out[mask > 0], 1) <= 5
    assert len(np.unique(out[mask == 0])) == 1   # the wedge is one value (no structure)
    flat = np.full((32, 32, 3), 77, np.uint8)
    assert np.array_equal(stretch_contrast(flat), flat)
