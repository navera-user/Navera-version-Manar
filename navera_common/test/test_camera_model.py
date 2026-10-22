"""Camera geometry: lens, attitude, tilt straightening, altitude from scale."""
import math

import numpy as np
import pytest

from navera_common.camera_model import (CameraModel, altitude_from_scale, body_rpy_enu,
                                        camera_rotation, ground_m_per_px, heading_of_image_up_deg,
                                        nadir_homography, rpy_to_matrix, tilt_deg)


def quat_from_rpy(roll, pitch, yaw):
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return (sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


def body_q(roll_deg=0.0, nose_up_deg=0.0, heading_deg=0.0):
    """Body ENU quaternion from aviation angles (roll right-down +, nose up +, heading cw from N)."""
    return quat_from_rpy(math.radians(roll_deg), -math.radians(nose_up_deg), math.radians(90.0 - heading_deg))


def project(K, R_world_cam, C, X):
    """World point X (ENU, m) seen by a camera at C."""
    v = R_world_cam.T @ (np.asarray(X, float) - np.asarray(C, float))
    assert v[2] > 0, "point behind the camera"
    p = K @ (v / v[2])
    return p[:2]


def apply_h(H, p):
    q = H @ np.array([p[0], p[1], 1.0])
    return q[:2] / q[2]


K = np.array([[800.0, 0, 640.0], [0, 800.0, 360.0], [0, 0, 1]])


@pytest.mark.parametrize("roll,up,hdg", [(0, 0, 0), (12, -5, 37), (-20, 15, 210), (5, 25, 300)])
def test_body_angles_round_trip(roll, up, hdg):
    r, p, h = body_rpy_enu(body_q(roll, up, hdg))
    assert (r, p, h) == pytest.approx((roll, up, hdg % 360.0), abs=1e-9)


def test_level_camera_looks_down_with_image_top_forward():
    R = camera_rotation(body_q(heading_deg=90.0))           # flying east
    assert tilt_deg(R) == pytest.approx(0.0, abs=1e-9)
    assert heading_of_image_up_deg(R) == pytest.approx(90.0)
    assert np.allclose(nadir_homography(K, R), np.eye(3), atol=1e-9)


@pytest.mark.parametrize("roll,up,hdg", [(0, 10, 0), (15, 0, 45), (-8, -12, 200), (20, 15, 333)])
def test_straightened_frame_centre_is_the_point_under_the_vehicle(roll, up, hdg):
    h = 150.0
    C = (0.0, 0.0, h)
    R = camera_rotation(body_q(roll, up, hdg))
    H = nadir_homography(K, R)
    # the point straight below lands at the centre of the straightened image
    assert apply_h(H, project(K, R, C, (0, 0, 0))) == pytest.approx((640.0, 360.0), abs=1e-6)
    # and the straightened image is a true nadir view: ground offsets scale as f/h, rotated by heading
    for de, dn in ((30.0, 0.0), (0.0, -40.0), (25.0, 25.0)):
        q = apply_h(H, project(K, R, C, (de, dn, 0)))
        a = math.radians(hdg)                                    # image up = heading
        right = de * math.cos(a) - dn * math.sin(a)              # ground offset along image right
        fwd = de * math.sin(a) + dn * math.cos(a)                # ... along image up
        assert q == pytest.approx((640.0 + 800.0 * right / h, 360.0 - 800.0 * fwd / h), abs=1e-6)


def test_why_it_matters_tilt_moves_the_image_centre():
    """Without straightening, 10 deg nose-up at 150 m: the image centre is 26 m ahead
    (the belly, and the camera, swing forward).
    """
    R = camera_rotation(body_q(0, 10, 0))
    centre_ground = np.array([0, 0, 150.0]) + R @ np.array([0, 0, 1.0]) * (150.0 / -(R @ [0, 0, 1.0])[2])
    assert math.hypot(*centre_ground[:2]) == pytest.approx(150.0 * math.tan(math.radians(10)), rel=1e-9)
    assert centre_ground[1] > 0                                  # ahead (north) when flying north


def test_camera_mounted_tilted_forward():
    R = camera_rotation(body_q(0, 0, 0), mount_rpy_deg=(0.0, -30.0, 0.0))
    assert tilt_deg(R) == pytest.approx(30.0)
    z = R @ np.array([0, 0, 1.0])
    assert z[1] > 0                                              # looks ahead (north)


def test_ideal_lens():
    cam = CameraModel.ideal(84.0, (1920, 1080))
    assert cam.out_hfov_deg == pytest.approx(84.0)
    img = np.zeros((1080, 1920, 3), np.uint8)
    assert cam.undistort(img) is img


@pytest.mark.parametrize("model", ["fisheye", "pinhole"])
def test_lens_distortion_is_removed(model):
    import cv2
    w, h = 1920, 1080
    Kd = np.array([[900.0, 0, 960.0], [0, 900.0, 540.0], [0, 0, 1]])
    D = np.array([-0.05, 0.01, -0.004, 0.0005]) if model == "fisheye" else np.array([-0.28, 0.09, 0.0, 0.0, -0.01])
    cam = CameraModel(Kd, D, (w, h), model)
    assert 70.0 < cam.out_hfov_deg < 140.0
    # rays → distorted pixels with the lens → undistorted pixels must be the pinhole projection
    rays = np.array([[x, y] for x in np.linspace(-0.6, 0.6, 7) for y in np.linspace(-0.35, 0.35, 5)])
    if model == "fisheye":
        dist = cv2.fisheye.distortPoints(rays.reshape(-1, 1, 2), Kd, D)
    else:
        pts3 = np.c_[rays, np.ones(len(rays))]
        dist, _ = cv2.projectPoints(pts3, np.zeros(3), np.zeros(3), Kd, D)
    und = cam.undistort_points(dist)
    expect = (cam.K_out @ np.c_[rays, np.ones(len(rays))].T).T[:, :2]
    assert und == pytest.approx(expect, abs=0.05)
    assert cam.undistort(np.zeros((h, w), np.uint8)).shape == (h, w)
    with pytest.raises(ValueError):
        cam.undistort(np.zeros((480, 640), np.uint8))


def test_calibration_dict():
    cam = CameraModel.from_calibration({"model": "fisheye", "image_width": 1920, "image_height": 1080,
                                        "camera_matrix": [900, 0, 960, 0, 900, 540, 0, 0, 1],
                                        "distortion": [-0.05, 0.01, -0.004, 0.0005]})
    assert cam.model == "fisheye" and cam.size == (1920, 1080)
    with pytest.raises(ValueError, match="camera_matrix"):
        CameraModel.from_calibration({"image_width": 10, "image_height": 10})


def test_a_distorted_lens_needs_its_model():
    d = {"image_width": 1920, "image_height": 1080, "camera_matrix": [900, 0, 960, 0, 900, 540, 0, 0, 1],
         "distortion": [-0.05, 0.01, -0.004, 0.0005]}
    with pytest.raises(ValueError, match="model"):
        CameraModel.from_calibration(d)
    assert CameraModel.from_calibration({**d, "distortion": []}).model == "pinhole"


def test_altitude_from_scale():
    hfov, w = 84.0, 1920
    for true_h, guess_h in ((150.0, 100.0), (400.0, 450.0)):
        s = ground_m_per_px(true_h, hfov, w) / ground_m_per_px(guess_h, hfov, w)
        assert altitude_from_scale(guess_h, s) == pytest.approx(true_h)


def test_rpy_matrix_is_a_rotation():
    R = rpy_to_matrix(0.3, -0.2, 1.1)
    assert np.allclose(R @ R.T, np.eye(3)) and np.linalg.det(R) == pytest.approx(1.0)


def test_crop_one_lens_of_a_360_camera():
    from navera_common.camera_model import parse_crop
    assert parse_crop("", 1920, 1080) is None
    assert parse_crop("bottom", 1920, 1080) == (0, 540, 1920, 540)
    assert parse_crop("top", 1920, 1080) == (0, 0, 1920, 540)
    assert parse_crop("100,50,800,600", 1920, 1080) == (100, 50, 800, 600)
    for bad in ("middle", "0,0,3000,100", "0,0,10,10"):
        with pytest.raises(ValueError):
            parse_crop(bad, 1920, 1080)


def test_wide_fisheye_keeps_its_centre_resolution():
    """The Insta360 One R top lens (calibrated 2026-10-06): 1920x540, fx 660. A straight view
    169 deg wide would give the centre 7x fewer pixels per degree than the lens: capped at
    2 atan(960 / 660) = 111 deg, even when an old calibration file asks for more.
    """
    K = [660.48, 0, 937.06, 0, 721.40, 317.66, 0, 0, 1]
    D = [0.2319, -0.4170, 0.5338, -0.2386]
    for asked in (None, 169.2):
        cam = CameraModel(K, D, (1920, 540), "fisheye", asked)
        assert abs(cam.out_hfov_deg - 111.0) < 0.5
        assert cam.K_out[0, 0] >= 660.0 - 1e-6          # centre: at least the lens' pixels per radian
    narrow = CameraModel(K, D, (1920, 540), "fisheye", 90.0)
    assert narrow.out_hfov_deg == 90.0                     # a narrower request is kept


def test_fisheye_native_fov_stays_inside_the_model_b2():
    """The Insta360 strip calibration (2026-10-06): its edge pixels lie past the angle where the
    fisheye model stops growing; OpenCV returned -1e6 there and the native FOV read 180 deg.
    """
    K = [660.4827, 0, 937.0585, 0, 721.3969, 317.6612, 0, 0, 1]
    D = [0.23188, -0.41701, 0.53385, -0.23863]
    m = CameraModel(K, D, (1920, 540), "fisheye", out_hfov_deg=111.0)
    half = math.degrees(m.fisheye_valid_theta())
    assert 60.0 < half < 75.0
    assert abs(m._native_hfov_deg() - 2 * half) < 0.5 and m._native_hfov_deg() < 179.0
