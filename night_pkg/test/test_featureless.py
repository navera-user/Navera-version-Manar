"""featureless_mask: cloud / calm water left out of the night query, textured ground kept."""
import numpy as np

from night_pkg.nodes.night_localizer import featureless_mask


def _ground(seed=1, n=512):
    rng = np.random.default_rng(seed)
    g = rng.normal(128, 30, (n, n)).clip(0, 255).astype(np.uint8)
    return np.dstack([g, g, g])


def test_textured_ground_is_kept():
    m, share = featureless_mask(_ground())
    assert share > 0.97 and m.mean() > 245


def test_a_cloud_patch_is_masked_and_its_share_counted():
    q = _ground()
    q[:, :256] = 20                                   # a cold flat cloud over half the frame
    m, share = featureless_mask(q)
    assert 0.40 < share < 0.52
    assert (m[:, :240] == 0).all() and (m[:, 280:] > 0).mean() > 0.97


def test_small_flat_roofs_stay():
    q = _ground()
    for y in range(40, 480, 80):
        q[y:y + 12, y:y + 12] = 200                    # 12 px flat roofs: < FEATURELESS_MIN_AREA
    m, share = featureless_mask(q)
    assert share > 0.97


def test_existing_empty_border_stays_empty():
    q = _ground()
    valid = np.full(q.shape[:2], 255, np.uint8)
    valid[:, :50] = 0
    m, _ = featureless_mask(q, valid)
    assert (m[:, :50] == 0).all()
