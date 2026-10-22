"""F18: the screen bench detects stars with the product's detector (allsky.detect_spots_view), so it judges the
stars as the field does; the fisheye detector (detect_spots) and the view one share one implementation.
"""
import numpy as np

from cn_pkg import allsky


def _scene(seed=0):
    rng = np.random.default_rng(seed)
    img = rng.normal(12, 1.5, (600, 900)).astype(np.float32)
    stars = [(100 + 70 * k, 120 + 37 * (k % 5)) for k in range(10)]
    yy, xx = np.mgrid[0:600, 0:900]
    for x, y in stars:
        img += 120 * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.2 ** 2))
    img += 90 * np.exp(-((xx - 450) ** 2 + (yy - 450) ** 2) / (2 * 15.0 ** 2))     # a lit cloud / lamp: extended
    img[500, 100] = 255                                                             # a hot pixel
    return np.clip(img, 0, 255).astype(np.uint8), stars


def test_view_detector_keeps_stars_and_drops_blobs_and_hot_pixels():
    img, stars = _scene()
    st = {}
    sp = allsky.detect_spots_view(img, stats=st)
    found = [(x, y) for x, y, _ in sp]
    for sx, sy in stars:
        assert min(np.hypot(sx - x, sy - y) for x, y in found) < 0.5
    assert len(sp) == len(stars)
    assert st["extended"] >= 1 and st["hot_pixel"] >= 1


def test_view_detector_honours_the_mask():
    img, stars = _scene()
    mask = np.zeros(img.shape, np.uint8)
    mask[:, :450] = 1
    sp = allsky.detect_spots_view(img, mask=mask)
    assert len(sp) == sum(1 for x, _ in stars if x < 450 - 8)
