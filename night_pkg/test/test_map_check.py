"""Night frame checks without the network: empty borders and the map check (verify_match)."""
import numpy as np

from night_pkg.nodes.night_localizer import (STHN_QUERY_PX, image_valid_mask, normalize_query,
                                             verify_match)

LAT = 35.83


def textured(h, w, seed=0):
    """A map-like picture: blocks and lines at several scales."""
    rng = np.random.default_rng(seed)
    import cv2
    img = np.zeros((h, w), np.float32)
    for s in (64, 24, 8):
        n = rng.uniform(0, 1, (h // s + 1, w // s + 1)).astype(np.float32)
        img += cv2.resize(n, (w, h), interpolation=cv2.INTER_NEAREST)[:h, :w]
    img = (255 * (img - img.min()) / (img.max() - img.min())).astype(np.uint8)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def test_empty_wedge_at_the_edge_is_masked_but_clipped_pixels_are_not():
    img = textured(480, 640)
    img[img == 0] = 1
    img[:, :120] = 0                                   # straightened frame: black wedge
    rng = np.random.default_rng(1)
    ys, xs = rng.integers(0, 480, 300), rng.integers(200, 640, 300)
    img[ys, xs] = 0                                    # AGC-clipped pixels inside
    img[200:240, 300:340] = 0                          # a cold object inside the frame
    m = image_valid_mask(img)
    assert (m[:, :110] == 0).all()
    assert (m[:, 130:] == 255).all()


def test_tilted_frame_wedges_reduce_coverage_and_say_why():
    img = textured(512, 640)
    img[img == 0] = 1
    q, info = normalize_query(img, LAT, 17, 420.0, 75.0)
    assert q is not None
    img[:, :120] = 0                                   # a small wedge: filled, still used
    q, info = normalize_query(img, LAT, 17, 420.0, 75.0)
    assert q is not None and info["ground_coverage"] < info["coverage"]
    img[:, :330] = 0                                   # half the frame empty: refused
    q, info = normalize_query(img, LAT, 17, 420.0, 75.0)
    assert q is None and "empty" in info["reason"] and info["empty_share"] > 0.4


def _corners_for(x0, y0, side, k):
    """STHN-style corners (TL, TR, BR, BL at resize-width scale) of a square crop."""
    c = np.array([[x0, y0], [x0 + side, y0], [x0 + side, y0 + side], [x0, y0 + side]], float)
    return (c + 0.5) / k - 0.5


def test_map_check_confirms_the_right_place_and_refuses_noise():
    sat = textured(1536, 1536, seed=3)
    x0, y0, side = 600, 500, 512
    k = 1536 / 256.0
    query = sat[y0:y0 + side, x0:x0 + side].copy()
    good = verify_match(query, None, sat, _corners_for(x0, y0, side - 1, k))
    assert good["ncc"] > 0.6
    inverted = verify_match(255 - query, None, sat, _corners_for(x0, y0, side - 1, k))
    assert inverted["ncc"] > 0.5                       # black-hot / white-hot alike
    off = verify_match(query, None, sat, _corners_for(x0 + 300, y0 - 200, side - 1, k))
    assert off["ncc"] < 0.3
    noise = np.random.default_rng(5).integers(0, 255, (side, side, 3), dtype=np.uint8)
    bad = verify_match(noise, None, sat, _corners_for(x0, y0, side - 1, k))
    assert bad["ncc"] < 0.2
    flat = verify_match(np.full((side, side, 3), 120, np.uint8), None, sat,
                        _corners_for(x0, y0, side - 1, k))
    assert flat["ncc"] < 0.2
    assert STHN_QUERY_PX == side


def test_shifted_map_control_peaks_at_the_right_place_only():
    sat = textured(1536, 1536, seed=3)
    x0, y0, side = 600, 500, 512
    k = 1536 / 256.0
    query = sat[y0:y0 + side, x0:x0 + side].copy()
    good = verify_match(query, None, sat, _corners_for(x0, y0, side - 1, k), shifts_px=(24.0, 64.0))
    assert good["ncc"] > 0.6 and good["ncc_ctrl"] < good["ncc"] - 0.3
    assert abs(good["ncc_margin"] - (good["ncc"] - good["ncc_ctrl"])) < 1e-9
    # 24 px off the truth: the control that lands on the truth beats the claimed place
    off = verify_match(query, None, sat, _corners_for(x0 + 24, y0, side - 1, k), shifts_px=(24.0, 64.0))
    assert off["ncc_margin"] < -0.2
    assert "ncc_ctrl" not in verify_match(query, None, sat, _corners_for(x0, y0, side - 1, k))
