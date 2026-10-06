"""VisionNavigator and FrameOdometry: the rules between map matches (no ROS, no GPU)."""
import math

import cv2
import numpy as np

from day_pkg.frame_odometry import FrameOdometry
from day_pkg.vision_nav import VisionNavigator, _en, _move

P0 = (35.869, 10.535)


def _fix(lat, lon, inliers=150, sigma=4.0, scale=1.0, spread=0.75):
    return {"accepted": True, "predicted_lat": lat, "predicted_lon": lon, "inliers": inliers,
            "sigma_m": sigma, "scale_residual": scale, "spread": spread}


def _fly(nav, t0, t1, ve, vn, start=P0, heading=None, gps=False):
    """Fixes every second along a straight line; returns the last position."""
    p = start
    for t in range(t0, t1 + 1):
        p = _move(start, ve * (t - t0), vn * (t - t0))
        if gps:
            nav.gps(t, *p, heading_deg=heading)
        else:
            nav.update(t, _fix(*p), 500.0, heading)
    return p


def test_straight_gap_is_carried_with_growing_sigma():
    nav = VisionNavigator()
    p = _fly(nav, 0, 10, 25.0, 0.0, gps=True)
    lat, lon, sig, mode = nav.output(23.0)
    e, n = _en((lat, lon), p)
    assert abs(e - 25.0 * 13) < 5 and abs(n) < 5            # carried, not frozen (was 326 m off)
    assert mode == "propagated" and sig > 40                  # and honest about it
    assert nav.output(10 + 121)[3] == "unavailable"           # past max_dr_s: no position


def test_turn_is_followed_with_the_heading():
    nav = VisionNavigator()
    _fly(nav, 0, 10, 0.0, 25.0, heading=0.0, gps=True)        # north at 25 m/s
    # 10 s of a constant-rate right turn to east (heading 0 -> 90): a quarter circle
    r = 25.0 * 10 / (math.pi / 2)
    true = _move(_move(P0, 0, 250.0), r, r)
    lat, lon, sig, _ = nav.output(20.0, heading_deg=90.0)
    straight = _move(P0, 0, 500.0)
    assert math.hypot(*_en((lat, lon), true)) < 15            # the turn followed
    assert math.hypot(*_en(straight, true)) > 150             # a straight carry would be far off


def test_search_window_follows_the_uncertainty():
    nav = VisionNavigator()
    _fly(nav, 0, 10, 25.0, 0.0, gps=True)
    _, r1 = nav.search(11.0)
    _, r2 = nav.search(40.0)
    assert r1 == nav.min_search_m and r2 > 3 * r1 and r2 <= nav.max_search_m


def test_weak_fix_far_from_the_prediction_is_rejected_strong_one_kept():
    nav = VisionNavigator()
    p = _fly(nav, 0, 10, 25.0, 0.0)
    far = _move(p, 25.0 + 300.0, 0.0)
    assert not nav.update(11.0, _fix(*far, inliers=40, sigma=15.0), 500.0)
    assert "prediction" in nav.last_reason
    assert nav.update(11.0, _fix(*far, inliers=300), 500.0)    # very strong: believed


def test_inliers_on_a_strip_are_rejected():
    nav = VisionNavigator()
    p = _fly(nav, 0, 5, 10.0, 0.0)
    assert not nav.update(6.0, _fix(*_move(p, 10, 0), inliers=30, spread=0.125), 500.0)


def test_map_bias_learned_with_gps_is_removed_after():
    nav = VisionNavigator()
    for t in range(10):                                        # vision 40 m west of GPS
        g = _move(P0, 10.0 * t, 0.0)
        nav.gps(t, *g)
        nav.bias_sample(_move(g, -40.0, 0.0), g)
    g = _move(P0, 100.0, 0.0)
    nav.update(10.0, _fix(*_move(g, -40.0, 0.0)), 500.0)
    assert math.hypot(*_en(nav.fix[:2], g)) < 1.0


def test_heights_are_retried_after_failures_and_height_follows_scale():
    nav = VisionNavigator()
    nav.set_height(0.0, 500.0, 10.0, "gps")
    assert nav.heights_to_try()[1] == []
    for t in range(3):
        nav.update(t, {"accepted": False}, 500.0)
    h, extra, tol = nav.heights_to_try()
    assert extra == [400.0, 625.0] and tol >= 0.2
    nav.update(20.0, _fix(*P0, scale=1.1), 500.0)            # GPS height old: vision takes over
    assert abs(nav.height[0] - 550.0) < 1e-6 and nav.height[3] == "vision"


def _texture(size=3000, seed=0):
    rng = np.random.default_rng(seed)
    img = cv2.GaussianBlur(rng.integers(0, 255, (size, size)).astype(np.uint8), (0, 0), 3)
    return cv2.equalizeHist(img)


def _view(ground, e, n, hdg, mpp_ground=1.0, mpp=1.0, w=1200, h=400):
    """The camera frame over ground (1 m/px, north up) at (e, n) m from its centre, heading up."""
    th = math.radians(hdg)
    c, s = math.cos(th), math.sin(th)
    k = mpp / mpp_ground
    A = np.array([[c * k, -s * k, 0.0], [s * k, c * k, 0.0]])
    cx, cy = ground.shape[1] / 2 + e / mpp_ground, ground.shape[0] / 2 - n / mpp_ground
    A[:, 2] = [cx, cy] - A[:, :2] @ [w / 2, h / 2]
    return cv2.warpAffine(ground, A, (w, h), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)


def test_frame_odometry_measures_the_displacement():
    g = _texture()
    vo = FrameOdometry()
    for hdg, (de, dn) in ((0.0, (0.0, 40.0)), (30.0, (20.0, 34.6)), (200.0, (-15.0, -40.0))):
        vo.reset()
        assert vo.step(_view(g, 0, 0, hdg), hdg, 1.0, 0.0) is None
        r = vo.step(_view(g, de, dn, hdg + 4.0), hdg + 4.0, 1.0, 2.0)  # turned 4 deg meanwhile
        assert r is not None, hdg
        assert abs(r[0] - de) < 2.0 and abs(r[1] - dn) < 2.0, (hdg, r)
        assert r[2] == 2.0 and r[3] > 0.3


def test_frame_odometry_gives_up_on_a_featureless_view():
    vo = FrameOdometry()
    flat = np.full((400, 1200), 90, np.uint8)
    vo.step(flat, 0.0, 1.0, 0.0)
    assert vo.step(flat, 0.0, 1.0, 2.0) is None
