"""The in-flight lens calibration (day_pkg.lens_selfcal) recovers a lens from GPS-check views.

Synthetic views made exactly as live_camera makes frames: a TRUE lens (distorted, wider than
assumed) photographs the ground; the frame is undistorted with the ASSUMED lens (an ideal one,
as navera-discover's guess) and straightened with the IMU attitude (noisy, the mount 1 deg off);
the map points come with a GPS that is metres off and a height a few percent off.
"""
import math

import numpy as np
import pytest

from day_pkg.lens_selfcal import LensSelfCal, enu_offsets, project, raw_pixels
from navera_common.camera_model import CameraModel, camera_rotation, nadir_homography

W, H = 1280, 720
LAT0, LON0 = 35.82, 10.63


def quat(roll, pitch, yaw):
    r, p, y = (math.radians(a) / 2 for a in (roll, pitch, yaw))
    return (math.sin(r) * math.cos(p) * math.cos(y) - math.cos(r) * math.sin(p) * math.sin(y),
            math.cos(r) * math.sin(p) * math.cos(y) + math.sin(r) * math.cos(p) * math.sin(y),
            math.cos(r) * math.cos(p) * math.sin(y) - math.sin(r) * math.sin(p) * math.cos(y),
            math.cos(r) * math.cos(p) * math.cos(y) + math.sin(r) * math.sin(p) * math.sin(y))


def make_views(true_model, true_f, k1, k2, assumed: CameraModel, n_views=16, seed=1, height_bias=0.0, reach=1.0):
    rng = np.random.default_rng(seed)
    views = []
    lens = dict(model=assumed.model, K=assumed.K.ravel().tolist(), D=assumed.D.tolist(), size=[W, H],
                K_out=assumed.K_out.ravel().tolist())
    for _ in range(n_views):
        h = rng.uniform(120, 300)
        att = (rng.uniform(-12, 12), rng.uniform(-12, 12), rng.uniform(0, 360))
        R_true = camera_rotation(quat(*att), (1.0, -0.5, 0.0))
        R_imu = camera_rotation(quat(*(a + rng.normal(0, 0.3) for a in att)), (0.0, 0.0, 0.0))
        mx, my = (1 - reach) * W / 2 + 5, (1 - reach) * H / 2 + 5      # matches only near the centre
        raw = np.c_[rng.uniform(mx, W - mx, 300), rng.uniform(my, H - my, 300)]
        # true rays: invert the true lens numerically (bisection on the radius)
        x = (raw[:, 0] - W / 2) / true_f
        y = (raw[:, 1] - H / 2) / true_f
        rd = np.hypot(x, y)
        r = rd.copy()
        for _ in range(60):
            g = project(true_model, true_f, 0, 0, k1, k2, np.c_[r, np.zeros_like(r), np.ones_like(r)])[:, 0] / true_f
            r = r - (g - rd) * 0.7
        ray = np.c_[x * r / np.maximum(rd, 1e-12), y * r / np.maximum(rd, 1e-12), np.ones(len(r))]
        d = ray @ R_true.T                                   # world directions
        keep = d[:, 2] < -0.05
        d, raw = d[keep], raw[keep]
        pts = d * (h / -d[:, 2])[:, None]                    # ground points, camera at the origin
        gps = (rng.normal(0, 2.0), rng.normal(0, 2.0))       # the GPS (and map) metres off
        k = math.pi / 180 * 6378137.0
        lat = LAT0 + pts[:, 1] / k
        lon = LON0 + pts[:, 0] / (k * math.cos(math.radians(LAT0)))
        glat, glon = LAT0 + gps[1] / k, LON0 + gps[0] / (k * math.cos(math.radians(LAT0)))
        # the published frame: assumed lens, straightened with the IMU attitude
        und = assumed.undistort_points(raw[:, None, :])
        Hs = nadir_homography(assumed.K_out, R_imu)
        q = np.c_[und, np.ones(len(und))] @ Hs.T
        fp = q[:, :2] / q[:, 2:3] + rng.normal(0, 0.7, (len(q), 2))
        views.append(dict(lens=lens, R=R_imu.ravel().tolist(), fp=fp, ml=np.c_[lat, lon], gps=(glat, glon),
                          h=h * (1 + height_bias) * (1 + rng.normal(0, 0.01))))
    return views


def radial_error_px(fit_lens, true_model, true_f, k1, k2):
    """Largest pixel difference over the image between the fitted lens and the true one."""
    r = np.linspace(0.0, 0.95 * math.hypot(W / 2, H / 2) / true_f, 50)
    pts = np.c_[r, np.zeros_like(r), np.ones_like(r)]
    true = project(true_model, true_f, 0, 0, k1, k2, pts)
    K = fit_lens["camera_matrix"]
    D = fit_lens["distortion"]
    got = project(fit_lens["model"], K[0], 0, 0, D[0], D[1], pts)
    return float(np.max(np.abs(true[:, 0] - got[:, 0])))


@pytest.mark.parametrize("hfov_true,k1,k2", [(84.0, -0.25, 0.06), (62.0, 0.0, 0.0), (95.0, -0.30, 0.09)])
def test_a_wrong_ideal_lens_is_recovered_from_gps_check_views(hfov_true, k1, k2):
    f_true = (W / 2) / math.tan(math.radians(hfov_true) / 2)
    assumed = CameraModel.ideal(70.0, (W, H))
    cal = LensSelfCal(min_views=12)
    for v in make_views("pinhole", f_true, k1, k2, assumed):
        assert cal.add_view(v["lens"], v["R"], v["fp"], v["ml"], v["gps"], v["h"]) is None
    out = cal.fit()
    assert out["accepted"], out
    assert out["chi2_gain"] >= 25 and out["rms_after_px"] <= out["rms_before_px"]
    # within a few pixels of the true lens everywhere (the focal to ~1 %: the heights are 1 % noisy)
    assert radial_error_px(out["lens"], "pinhole", f_true, k1, k2) < 0.015 * W
    assert abs(out["focal_px"] / f_true - 1) < 0.02


def test_a_fisheye_is_recognised_from_an_ideal_guess():
    """A 110-deg fisheye (an action camera), the ideal 70-deg guess: the fisheye model fits better."""
    f_true = (W / 2) / math.radians(55.0)                     # equidistant: r = f theta
    cal = LensSelfCal(min_views=12)
    for v in make_views("fisheye", f_true, 0.02, -0.01, CameraModel.ideal(70.0, (W, H)), seed=7):
        cal.add_view(v["lens"], v["R"], v["fp"], v["ml"], v["gps"], v["h"])
    out = cal.fit()
    assert out["accepted"] and out["model"] == "fisheye", out
    assert radial_error_px(out["lens"], "fisheye", f_true, 0.02, -0.01) < 0.015 * W
    assert abs(out["hfov_deg"] - 110.0) < 3.0


def test_a_wide_fisheye_seen_only_near_the_centre_is_still_a_fisheye():
    """Real matches rarely reach the corners (Isaac Sim: a 92 deg fisheye fitted as a pinhole bent 200+ px in
    the corners): when both models explain the points alike, the one with the smaller distortion terms."""
    f_true = (W / 2) / math.radians(46.0)                     # 92 deg equidistant fisheye
    cal = LensSelfCal(min_views=12, min_radius_frac=0.5)
    for v in make_views("fisheye", f_true, 0.0, 0.0, CameraModel.ideal(70.0, (W, H)), seed=9, reach=0.7):
        cal.add_view(v["lens"], v["R"], v["fp"], v["ml"], v["gps"], v["h"])
    out = cal.fit()
    assert out["accepted"] and out["model"] == "fisheye", out
    assert radial_error_px(out["lens"], "fisheye", f_true, 0.0, 0.0) < 0.015 * W      # right in the corners too


def test_the_right_lens_is_not_changed():
    """The assumed lens IS the true lens: no clear improvement, nothing offered."""
    f = (W / 2) / math.tan(math.radians(70.0) / 2)
    assumed = CameraModel.ideal(70.0, (W, H))
    cal = LensSelfCal(min_views=12)
    for v in make_views("pinhole", f, 0.0, 0.0, assumed, seed=3):
        cal.add_view(v["lens"], v["R"], v["fp"], v["ml"], v["gps"], v["h"])
    out = cal.fit()
    assert not out["accepted"] and "no clear improvement" in out["why"]


def test_a_height_bias_moves_the_focal_only_partly():
    """A height source 5 % high: the tilted views' perspective keeps the focal near the true one
    (measured 1.2 % long), the per-view heights take the rest."""
    f_true = (W / 2) / math.tan(math.radians(84.0) / 2)
    cal = LensSelfCal(min_views=12)
    for v in make_views("pinhole", f_true, -0.2, 0.05, CameraModel.ideal(70.0, (W, H)), seed=5, height_bias=0.05):
        cal.add_view(v["lens"], v["R"], v["fp"], v["ml"], v["gps"], v["h"])
    out = cal.fit()
    assert out["accepted"]
    assert -0.005 < out["focal_px"] / f_true - 1 < 0.03


def test_views_need_points_and_height_and_a_lens():
    cal = LensSelfCal()
    lens = dict(model="pinhole", K=[500, 0, 640, 0, 500, 360, 0, 0, 1], D=[], size=[W, H],
                K_out=[500, 0, 640, 0, 500, 360, 0, 0, 1])
    R = np.eye(3).ravel().tolist()
    assert "attitude" in cal.add_view(lens, None, np.zeros((50, 2)), np.zeros((50, 2)), (LAT0, LON0), 100.0)
    assert "point pairs" in cal.add_view(lens, R, np.zeros((5, 2)), np.zeros((5, 2)), (LAT0, LON0), 100.0)
    assert "height" in cal.add_view(lens, R, np.zeros((50, 2)), np.zeros((50, 2)), (LAT0, LON0), float("nan"))
    assert "lens" in cal.add_view(None, R, np.zeros((50, 2)), np.zeros((50, 2)), (LAT0, LON0), 100.0)
    assert cal.fit() is None                                  # not enough views


def test_views_are_kept_across_a_lens_change_and_the_newest_lens_is_the_current_one():
    """The points are raw camera pixels: a frame made with another lens gives the same views."""
    assumed = CameraModel.ideal(70.0, (W, H))
    f_true = (W / 2) / math.tan(math.radians(84.0) / 2)
    cal = LensSelfCal(min_views=3)
    vs = make_views("pinhole", f_true, -0.2, 0.05, assumed, n_views=4)
    for v in vs:
        cal.add_view(v["lens"], v["R"], v["fp"], v["ml"], v["gps"], v["h"])
    other = CameraModel.ideal(80.0, (W, H))
    w = make_views("pinhole", f_true, -0.2, 0.05, other, n_views=1, seed=4)[0]
    cal.add_view(w["lens"], w["R"], w["fp"], w["ml"], w["gps"], w["h"])
    assert len(cal.views) == 5 and cal.lens is w["lens"]
    assert np.allclose(cal.views[-1]["raw"], cal.views[-1]["raw"])       # (raw pixels, lens-independent)


def test_raw_pixels_undo_the_straightening_and_the_lens():
    cam = CameraModel([[600, 0, 640], [0, 600, 360], [0, 0, 1]], [-0.2, 0.05, 0, 0, 0], (W, H))
    R = camera_rotation(quat(8, -5, 30))
    raw = np.array([[100.0, 80.0], [640.0, 360.0], [1200.0, 650.0]])
    und = cam.undistort_points(raw[:, None, :])
    Hs = nadir_homography(cam.K_out, R)
    q = np.c_[und, np.ones(3)] @ Hs.T
    fp = q[:, :2] / q[:, 2:3]
    lens = dict(model="pinhole", K=cam.K.ravel().tolist(), D=cam.D.tolist(), size=[W, H],
                K_out=cam.K_out.ravel().tolist())
    assert np.allclose(raw_pixels(fp, lens, R), raw, atol=0.05)


def test_enu_offsets():
    k = math.pi / 180 * 6378137.0
    en = enu_offsets(np.array([LAT0 + 100 / k]), np.array([LON0 + 50 / (k * math.cos(math.radians(LAT0)))]),
                     LAT0, LON0)
    assert np.allclose(en, [[50.0, 100.0]], atol=1e-6)
