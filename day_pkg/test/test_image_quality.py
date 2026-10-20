"""image_quality: blur score, gyro smear and the lens mask."""
import cv2
import numpy as np

from day_pkg import image_quality as iq


def _ground(seed=1, h=480, w=640):
    rng = np.random.default_rng(seed)
    g = cv2.resize((rng.random((h // 8, w // 8)) * 255).astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
    for _ in range(40):                                           # buildings and roads: edges at several scales
        x, y = rng.integers(0, w - 60), rng.integers(0, h - 60)
        cv2.rectangle(g, (int(x), int(y)), (int(x + rng.integers(10, 60)), int(y + rng.integers(10, 60))),
                      int(rng.integers(0, 255)), -1)
    return g


def test_sharpness_drops_with_blur_but_not_with_haze():
    g = _ground()
    s0 = iq.sharpness(g)
    blurred = cv2.blur(g, (15, 1))
    hazy = (g.astype(np.float32) * 0.4 + 150).astype(np.uint8)
    assert iq.sharpness(blurred) < 0.7 * s0
    assert abs(iq.sharpness(hazy) - s0) < 0.2 * s0


def test_gyro_blur_px():
    # 30 deg/s for 1/120 s through a 600 px lens: 2.6 px of smear
    assert abs(iq.gyro_blur_px(30.0, 1 / 120, 600.0) - 2.618) < 0.01
    assert iq.gyro_blur_px(-30.0, 1 / 120, 600.0) == iq.gyro_blur_px(30.0, 1 / 120, 600.0)


def test_lens_mask_finds_a_fixed_drop_while_the_ground_moves():
    big = _ground(seed=3, h=960, w=1280)
    m = iq.LensMask()
    for k in range(6):
        f = big[k * 40:k * 40 + 480, k * 50:k * 50 + 640].copy()     # the ground scrolls
        cv2.circle(f, (500, 120), 60, 128, -1)                       # a drop stays put
        m.update(f)
    mask = m.mask(f.shape)
    assert mask is not None and mask[120, 500] == 0                   # the drop is masked
    assert (mask == 255).mean() > 0.8                                 # most of the frame is kept


def test_lens_mask_is_off_while_hovering_and_masks_saturated_glow():
    g = _ground(seed=4)
    m = iq.LensMask()
    for _ in range(5):
        m.update(g)                                                   # nothing moves: no lens mask
    assert m.mask(g.shape) is None
    sun = g.copy()
    cv2.circle(sun, (600, 40), 50, 255, -1)
    m.update(sun)
    mask = m.mask(sun.shape)
    assert mask is not None and mask[40, 600] == 0 and mask[400, 100] == 255

