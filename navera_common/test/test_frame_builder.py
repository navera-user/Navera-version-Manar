"""Frame builder: undistort, straighten, describe."""
import math

import cv2
import numpy as np
import pytest

from navera_common.camera_model import CameraModel, camera_rotation, nadir_homography
from navera_common.frame_builder import FrameBuilder

from test_camera_model import body_q

W, H_ = 640, 480


def nadir_scene(seed=0):
    rng = np.random.default_rng(seed)
    img = cv2.GaussianBlur((rng.random((H_, W)) * 255).astype(np.uint8), (0, 0), 3)
    cv2.circle(img, (W // 2, H_ // 2), 6, 255, -1)          # the point under the vehicle
    return img


@pytest.mark.parametrize("roll,up,hdg", [(0, 0, 0), (8, -6, 30), (-12, 10, 250)])
def test_a_tilted_frame_comes_out_as_the_straight_down_view(roll, up, hdg):
    cam = CameraModel.ideal(84.0, (W, H_))
    q = body_q(roll, up, hdg)
    Hn = nadir_homography(cam.K_out, camera_rotation(q))
    truth = nadir_scene()
    raw = cv2.warpPerspective(truth, np.linalg.inv(Hn), (W, H_))      # what the tilted camera sees
    out, meta = FrameBuilder(cam).build(raw, 7, 123_000_000_000, q, altitude=(150.0, 3.0, "GPS - ground"))
    inner = (slice(120, 360), slice(160, 480))
    assert np.corrcoef(out[inner].ravel(), truth[inner].ravel())[0, 1] > 0.95
    yy, xx = np.unravel_index(np.argmax(cv2.GaussianBlur(out, (0, 0), 2)[200:280, 280:360]), (80, 80))
    assert math.hypot(xx + 280 - W / 2, yy + 200 - H_ / 2) < 2.0      # the dot is back at the centre
    assert meta["straightened"] and meta["heading_deg"] == pytest.approx(hdg % 360, abs=0.01)
    assert meta["roll_deg"] == pytest.approx(roll, abs=0.01) and meta["pitch_deg"] == pytest.approx(up, abs=0.01)
    assert meta["altitude_m"] == 150.0 and meta["camera_hfov_deg"] == pytest.approx(84.0)
    assert meta["gps_valid"] is False and meta["image_stamp_ns"] == 123_000_000_000


def test_too_tilted_is_published_but_marked_unusable():
    cam = CameraModel.ideal(84.0, (W, H_))
    out, meta = FrameBuilder(cam).build(nadir_scene(), 1, 0, body_q(50, 0, 0))
    assert meta["usable"] is False and "tilted 50" in meta["reason"]


def test_without_attitude_a_fixed_camera_frame_is_unusable():
    cam = CameraModel.ideal(84.0, (W, H_))
    _, meta = FrameBuilder(cam).build(nadir_scene(), 1, 0, None)
    assert meta["usable"] is False and "no attitude" in meta["reason"]
    _, meta = FrameBuilder(cam, gimbal=True).build(nadir_scene(), 1, 0, None)
    assert meta["usable"] is True                       # a level camera is straight down anyway


def test_without_attitude_source_the_frame_is_left_as_is():
    cam = CameraModel.ideal(84.0, (W, H_))
    img = nadir_scene()
    out, meta = FrameBuilder(cam, require_attitude=False).build(img, 1, 0, None, gps=(35.8, 10.6))
    assert out is img and meta["attitude_source"] == "none" and meta["heading_deg"] is None
    assert meta["altitude_m"] is None and meta["gps_lat"] == 35.8 and meta["gps_valid"] is False


def test_mount_angles_are_applied():
    cam = CameraModel.ideal(84.0, (W, H_))
    _, meta = FrameBuilder(cam, mount_rpy_deg=(0, -15, 0)).build(nadir_scene(), 1, 0, body_q())
    assert meta["tilt_deg"] == pytest.approx(15.0, abs=0.01) and meta["straightened"]


def test_gimbal_keeps_the_camera_level():
    cam = CameraModel.ideal(84.0, (W, H_))
    img = nadir_scene()
    out, meta = FrameBuilder(cam, gimbal=True).build(img, 1, 0, body_q(15, -30, 120))
    assert meta["tilt_deg"] == pytest.approx(0.0, abs=1e-6) and meta["heading_deg"] == pytest.approx(120.0)
    assert np.array_equal(out, img)                   # nothing to straighten


def test_a_star_camera_frame_is_undistorted_only():
    cam = CameraModel.ideal(60.0, (W, H_))
    img = nadir_scene()
    out, meta = FrameBuilder(cam, camera_type="star").build(img, 1, 5, None, utc="2026-10-02T21:00:00")
    assert meta["usable"] is True and meta["straightened"] is False and meta["utc_time"]
    assert meta["camera_type"] == "star" and (out == img).all()


def test_a_fixed_camera_turning_fast_is_not_used_a_gimbal_is():
    cam = CameraModel.ideal(84.0, (W, H_))
    q = (0.0, 0.0, 0.0, 1.0)
    _, meta = FrameBuilder(cam).build(nadir_scene(), 1, 0, q, rate_dps=45.0)
    assert meta["usable"] is False and "turning 45 deg/s" in meta["reason"] and meta["rate_dps"] == 45.0
    _, meta = FrameBuilder(cam).build(nadir_scene(), 1, 0, q, rate_dps=10.0)
    assert meta["usable"] is True
    _, meta = FrameBuilder(cam, gimbal=True).build(nadir_scene(), 1, 0, q, rate_dps=45.0)
    assert meta["usable"] is True


def test_the_frame_says_which_lens_and_attitude_made_it():
    """camera_lens + R_world_cam: the in-flight lens calibration takes a published pixel back to the raw one
    (and the mount identity's readable "lens" key, added by live_camera, must not overwrite it)."""
    import math
    from navera_common.camera_model import CameraModel, mount_identity
    from navera_common.frame_builder import FrameBuilder
    fb = FrameBuilder(CameraModel.ideal(70.0, (640, 480)), (0, 0, 0), 45.0, "day", False, True, 30.0)
    q = (math.sin(math.radians(5) / 2), 0.0, 0.0, math.cos(math.radians(5) / 2))
    _, meta = fb.build(np.zeros((480, 640, 3), np.uint8), 1, 10 ** 18, q, "imu", (100.0, 1.0, "baro"))
    meta.update(mount_identity((0, 0, 0), "", 70.0, None))
    assert meta["camera_lens"]["model"] == "pinhole" and len(meta["camera_lens"]["K_out"]) == 9
    assert len(meta["R_world_cam"]) == 9 and meta["lens"] == "ideal 70.0 deg"
