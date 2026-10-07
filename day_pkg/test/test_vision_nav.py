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
    assert not nav.update(6.0, _fix(*_move(p, 10, 0), inliers=20, spread=0.125), 500.0)


def test_map_bias_learned_with_gps_is_removed_after():
    nav = VisionNavigator()
    for t in range(10):                                        # vision 25 m west of GPS, two headings
        g = _move(P0, 10.0 * t, 0.0)
        nav.gps(t, *g)
        nav.bias_sample(_move(g, -25.0 + (t % 3) - 1, 0.0), g, heading_deg=90.0 * (t % 2))
    g = _move(P0, 100.0, 0.0)
    nav.update(10.0, _fix(*_move(g, -25.0, 0.0)), 500.0)
    assert math.hypot(*_en(nav.fix[:2], g)) < 1.5


def test_an_offset_that_turns_with_the_vehicle_is_not_a_map_bias():
    """A timing error puts vision behind along the track: on opposite headings the offsets
    cancel — learning it in east/north would help one heading and hurt the other."""
    nav = VisionNavigator()
    for t in range(12):
        hdg = 0.0 if t % 2 else 180.0
        g = _move(P0, 0.0, 10.0 * t)
        back = -5.0 if hdg == 0.0 else 5.0                    # 5 m behind, along the track
        nav.bias_sample(_move(g, 0.0, back + 0.3 * (t % 3)), g, heading_deg=hdg)
    assert max(abs(x) for x in nav.bias(P0)) < 1.0
    nav2 = VisionNavigator()                                  # one heading only: not learned either
    for t in range(12):
        g = _move(P0, 0.0, 10.0 * t)
        nav2.bias_sample(_move(g, -40.0, 0.0), g, heading_deg=0.0)
    assert nav2.bias(P0) == (0.0, 0.0)


def test_heights_are_retried_after_failures_and_height_follows_scale():
    nav = VisionNavigator()
    nav.set_height(0.0, 500.0, 10.0, "gps")
    assert nav.heights_to_try(0.0)[1] == []
    for t in range(3):
        nav.update(t, {"accepted": False}, 500.0)
    h, extra, tol = nav.heights_to_try(3.0)
    assert abs(h - 500.0) < 1 and [round(x) for x in extra] == [400, 625] and tol >= 0.2
    nav.update(20.0, _fix(*P0, scale=1.1), 500.0)            # GPS height old: vision takes over
    assert abs(nav.height[0] - 550.0) < 5.0 and nav.height[3] == "vision"


def test_height_follows_a_climb_after_gps_loss():
    """The filter must not freeze (2026-10-07: 445 -> 570 m true, the estimate stayed 466-475)."""
    nav = VisionNavigator()
    for t in range(10):
        nav.set_height(float(t), 450.0, 13.0, "gps")
    for t in range(10, 40):                                   # climbing 4 m/s, vision only
        true = 450.0 + 4.0 * (t - 10)
        used = nav.heights_to_try(float(t))[0]
        nav.update(float(t), _fix(*_move(P0, 0, 25.0 * t), scale=true / used), used)
    assert abs(nav.height_at(40.0)[0] - (450 + 4 * 30)) < 0.05 * 570


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


def test_frame_odometry_with_a_static_overlay_and_a_prediction():
    """Something fixed in the image (an overlay, lens dirt) pulled the old phase correlation
    toward zero motion (bench 2026-10-07: 4-5 m/s measured at 25 m/s)."""
    g = _texture()
    vo = FrameOdometry()
    a, b = _view(g, 0, 0, 30.0), _view(g, 25.0, 43.3, 30.0)       # 50 m along the heading
    for im in (a, b):
        im[20:140, 30:330] = 255                                   # a HUD box that does not move
        cv2.putText(im, "NAVERA", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 2, 0, 5)
    vo.step(a, 30.0, 1.0, 0.0)
    r = vo.step(b, 30.0, 1.0, 2.0, predicted_en=(20.0, 40.0))      # the velocity's guess, ~6 m off
    assert r is not None and abs(r[0] - 25.0) < 3.0 and abs(r[1] - 43.3) < 3.0, r


def test_odometry_disagreeing_with_the_fixes_is_not_used():
    nav = VisionNavigator()
    _fly(nav, 0, 10, 25.0, 0.0, gps=True)
    assert not nav.odometry(11.0, 9.0, 0.0, 2.0, 1.0)              # 4.5 m/s: the static-peak failure
    assert nav.vo_rejected == 1 and abs(nav.vel[0] - 25.0) < 1.0
    assert nav.odometry(12.0, 52.0, 2.0, 2.0, 1.0)                 # 26 m/s: agrees
    assert nav.vel_sigma >= 3.0


def test_two_agreeing_fixes_re_acquire_when_the_prediction_is_wrong():
    nav = VisionNavigator()
    _fly(nav, 0, 10, 25.0, 0.0)
    nav.vel = (5.0, 0.0)                                          # a wrong velocity (bad odometry)
    real = lambda t: _move(P0, 25.0 * t, 0.0)                     # noqa: E731
    assert not nav.update(20.0, _fix(*real(20), inliers=60, sigma=8.0), 500.0)
    assert nav.update(21.0, _fix(*real(21), inliers=60, sigma=8.0), 500.0)
    assert "re-acquired" in nav.last_reason
    assert math.hypot(*_en(nav.fix[:2], real(21))) < 1.0


def test_a_weak_fix_while_lost_needs_confirmation():
    nav = VisionNavigator()
    _fly(nav, 0, 10, 25.0, 0.0)
    t = 25.0                                                      # 15 s without fixes: sigma > 50 m
    assert nav.predict(t)[2] > 50
    p = nav.predict(t)
    assert not nav.update(t, _fix(p[0], p[1], inliers=25, sigma=20.0), 500.0)
    assert "weak fix" in nav.last_reason
