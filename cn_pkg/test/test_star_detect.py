"""Star detection: stars are kept, everything else is named and left out."""
import cv2
import numpy as np

from cn_pkg import star_detect as sd

W, H = 640, 360


def _sky(seed=1, level=20.0, noise=2.0):
    rng = np.random.default_rng(seed)
    return level + rng.normal(0, noise, (H, W)).astype(np.float32)


def _star(img, x, y, amp=80.0, sigma=1.2):
    ys, xs = np.mgrid[0:H, 0:W]
    img += amp * np.exp(-((xs - x) ** 2 + (ys - y) ** 2) / (2 * sigma ** 2))


def _field(n=25, seed=3):
    rng = np.random.default_rng(seed)
    return [(float(rng.uniform(30, W - 30)), float(rng.uniform(30, H - 30))) for _ in range(n)]


def _frame(stars, seed=1, shift=(0.0, 0.0)):
    img = _sky(seed)
    for x, y in stars:
        _star(img, x + shift[0], y + shift[1])
    return img


def test_clear_sky_finds_the_stars_and_nothing_else():
    stars = _field()
    det = sd.detect(_frame(stars))
    assert det.sky == sd.SKY_CLEAR
    assert len(det.stars) >= 0.9 * len(stars)
    found = np.array([[s.x, s.y] for s in det.stars])
    near = sum(np.hypot(*(found - [x, y]).T).min() < 1.0 for x, y in stars)
    assert near >= 0.9 * len(stars)
    assert len(det.stars) <= len(stars) + 1


def test_hot_pixel_is_not_a_star():
    img = _frame(_field())
    img[100, 200] += 150.0
    det = sd.detect(img)
    assert (200.0, 100.0) in det.rejected.get(sd.HOT_PIXEL, [])
    assert all(abs(s.x - 200) > 2 or abs(s.y - 100) > 2 for s in det.stars)


def test_aircraft_trail_is_not_a_star():
    img = _frame(_field())
    for t in range(40):
        _star(img, 100 + t * 2.0, 150 + t * 0.5, amp=70.0, sigma=1.2)
    det = sd.detect(img)
    assert det.rejected.get(sd.STREAK)
    assert all(not (95 < s.x < 190 and 145 < s.y < 175) for s in det.stars)


def test_moon_and_street_lamp_are_not_stars():
    img = _frame(_field())
    _star(img, 500, 80, amp=200.0, sigma=14.0)
    _star(img, 80, 300, amp=400.0, sigma=5.0)
    det = sd.detect(img)
    named = det.rejected.get(sd.BLOB, []) + det.rejected.get(sd.GLARE, []) + det.rejected.get(sd.NOT_SKY, [])
    assert named
    assert all(not (440 < s.x < 560 and 20 < s.y < 140) for s in det.stars)


def test_lit_region_is_masked():
    img = _frame(_field())
    img[:, :150] += 120.0
    det = sd.detect(img)
    assert all(s.x > 130 for s in det.stars)


def test_cloud_gradient_is_reported():
    img = _frame(_field())
    img += np.linspace(0, 45, W, dtype=np.float32)[None, :]
    det = sd.detect(img)
    assert det.sky in (sd.SKY_CLOUDY, sd.SKY_HAZY)


def test_covered_or_bright_sky_is_blocked():
    det = sd.detect(np.full((H, W), 200.0, np.float32))
    assert det.sky in (sd.SKY_BLOCKED, sd.SKY_BRIGHT)
    assert det.stars == []


def test_tracker_confirms_only_what_follows_the_pattern():
    stars = _field()
    tr = sd.StarTracker()
    first = tr.update(sd.detect(_frame(stars, seed=1)))
    assert first.confirmed == []                      # one frame proves nothing
    img = _frame(stars, seed=2, shift=(12.0, -7.0))   # the car turned: the whole pattern moved
    _star(img, 300, 200, amp=90.0)                    # an aircraft appears somewhere else
    res = tr.update(sd.detect(img))
    assert abs(res.pattern_shift_px - (12 ** 2 + 7 ** 2) ** 0.5) < 2.0
    assert len(res.confirmed) >= 0.8 * len(stars)
    assert any(abs(x - 300) < 2 and abs(y - 200) < 2 for x, y in res.rejected.get(sd.MOVER, []))


def test_tracker_bans_a_pixel_that_stays_while_the_pattern_turns():
    stars = _field()
    tr = sd.StarTracker()
    shifts = [(0, 0), (10, 4), (-6, 9), (14, -5), (3, 12), (-9, -9)]
    for i, sh in enumerate(shifts):
        img = _frame(stars, seed=i + 1, shift=sh)
        _star(img, 250, 120, amp=90.0, sigma=1.2)     # dirt on the lens: never moves
        res = tr.update(sd.detect(img))
    assert [(round(x), round(y)) for x, y in tr.banned()] == [(250, 120)]
    assert sd.FIXED in res.rejected
    assert len(res.confirmed) >= 0.8 * len(stars)


def _text_screen(rows=22, cols=90):
    """Dark screen with lines of small bright characters: looks like stars to a naive detector."""
    img = _sky(level=12.0)
    rng = np.random.default_rng(7)
    for r in range(rows):
        for c in range(cols):
            if rng.random() < 0.8:
                _star(img, 20 + c * 6.5, 15 + r * 15.0, amp=70.0, sigma=1.3)
                _star(img, 20 + c * 6.5 + 2.0, 15 + r * 15.0 + 3.0, amp=40.0, sigma=1.1)
    return img


def test_lines_of_text_are_not_a_sky():
    det = sd.detect(_text_screen())
    assert det.stars == []
    assert det.sky != sd.SKY_CLEAR


def test_a_textured_wall_is_not_a_sky():
    rng = np.random.default_rng(5)
    img = _sky(level=40.0, noise=2.0)
    blots = cv2.resize(rng.normal(0, 12, (H // 6, W // 6)).astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST)
    img += blots                                                                           # blotchy plaster
    det = sd.detect(img)
    assert det.stars == []


def test_roof_edge_on_one_side_keeps_the_stars_of_the_clear_side():
    stars = [(x, y) for x, y in _field(40, seed=11) if x > 200]
    img = _frame(stars)
    img[:, :150] = 8.0                 # the car roof: dark, then a bright edge line
    img[:, 148:152] = 150.0
    det = sd.detect(img)
    assert det.sky in (sd.SKY_CLEAR, sd.SKY_HAZY)
    assert len(det.stars) >= 0.8 * len(stars)
    assert all(s.x > 160 for s in det.stars)


def test_a_dense_real_sky_still_passes():
    import os
    path = "/media/shadow-team/ADATA SD620/nour/sky_localization_v0/sky_localization/ImageTest.jpeg"
    if not os.path.exists(path):
        return
    im = cv2.imread(path, 0)
    det = sd.detect(im)
    assert det.sky != sd.SKY_BLOCKED
    assert len(det.stars) > 300


def test_a_jpeg_flattened_dark_sky_still_gives_its_stars():
    """Video compression turns a dark background into constant blocks: the noise must not fall to zero."""
    stars = _field(30)
    img = np.clip(_frame(stars), 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 40])
    det = sd.detect(cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE).astype(np.float32))
    assert det.sky != sd.SKY_BLOCKED
    assert len(det.stars) >= 0.5 * len(stars)
    assert len(det.stars) <= len(stars) + 5
