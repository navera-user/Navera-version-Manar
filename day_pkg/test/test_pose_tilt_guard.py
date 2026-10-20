"""The pose-attitude guard of the day position (local_matcher.refine_with_pose, backlog VL-1):
the point under the camera from the matched pose is used only when the pose's tilt agrees with
the tilt the attitude gives the frame; otherwise the frame centre is kept (the match is not refused)."""
import math

import cv2
import numpy as np
import pytest

from day_pkg.local_matcher import refine_with_pose, tile_px_to_latlon, tile_xy
from day_pkg.nodes.day_subscriber import DaySubscriber

Z, MAP_MPP, H_M, HFOV = 17, 1.0, 300.0, 60.0
W, HGT = 640, 480
F = (W / 2.0) / math.tan(math.radians(HFOV) / 2.0)
FRAME_MPP = 2.0 * H_M * math.tan(math.radians(HFOV) / 2.0) / W
CAM_PX = tuple(256.0 * v for v in tile_xy(35.8, 10.6, Z))    # the camera above this map pixel


def _matches(tilt_deg, seed=3):
    """Frame/map points of a camera H_M above CAM_PX, its axis tilted tilt_deg (about the frame
    x axis), and the map pixel the frame centre sees."""
    rng = np.random.default_rng(seed)
    R = cv2.Rodrigues(np.array([math.radians(tilt_deg), 0.0, 0.0]))[0]
    C = np.array([0.0, 0.0, -H_M / MAP_MPP])                  # object frame: X east, Y south, Z down
    tv = -R @ C
    K = np.array([[F, 0, W / 2.0], [0, F, HGT / 2.0], [0, 0, 1.0]])
    obj = np.zeros((600, 3))
    obj[:, :2] = rng.uniform(-260.0, 260.0, (600, 2))
    img = cv2.projectPoints(obj, cv2.Rodrigues(R)[0], tv, K, None)[0].reshape(-1, 2)
    keep = (img[:, 0] > 5) & (img[:, 0] < W - 5) & (img[:, 1] > 5) & (img[:, 1] < HGT - 5)
    img = img[keep] + rng.normal(0.0, 0.3, (int(keep.sum()), 2))
    mp = obj[keep, :2] + np.array(CAM_PX)
    # the frame centre's ray: from the camera along the optical axis to the ground
    axis = R.T @ np.array([0.0, 0.0, 1.0])
    k = -C[2] / axis[2]
    centre = (CAM_PX[0] + k * axis[0], CAM_PX[1] + k * axis[1])
    return (img.astype(np.float32), mp.astype(np.float32)), centre


def _refine(tilt_deg, **kw):
    pts, centre = _matches(tilt_deg)
    lat, lon = tile_px_to_latlon(*centre, Z)
    res = dict(predicted_lat=lat, predicted_lon=lon)
    why = refine_with_pose(res, pts, pts, (W, HGT), HFOV, FRAME_MPP, 1.0, MAP_MPP, Z, centre, **kw)
    return res, why, (lat, lon)


def _off_m(res, latlon):
    return math.hypot((res["predicted_lat"] - latlon[0]) * 111320.0,
                      (res["predicted_lon"] - latlon[1]) * 111320.0 * math.cos(math.radians(latlon[0])))


def test_pose_tilt_far_from_the_attitude_keeps_the_frame_centre():
    res, why, centre = _refine(10.0, expected_tilt_deg=0.0, tilt_guard_deg=4.0)
    assert why is None                                         # not refused
    assert res["pose_tilt_deg"] == pytest.approx(10.0, abs=0.5)
    assert res["position_from"] == "frame centre"
    assert "frame centre kept" in res["pose_guard"]
    assert _off_m(res, centre) < 1e-3                          # the centre, untouched


def test_pose_tilt_agreeing_with_the_attitude_is_used():
    under = tile_px_to_latlon(*CAM_PX, Z)
    for tilt, expected in ((1.0, 0.0), (10.0, 9.0)):           # straightened frame; frame left tilted
        res, why, centre = _refine(tilt, expected_tilt_deg=expected, tilt_guard_deg=4.0)
        assert why is None and res["position_from"] == "camera pose" and "pose_guard" not in res
        assert _off_m(res, under) < 2.0
    assert _off_m(res, centre) > 45.0                          # 300 m x tan(10 deg) = 53 m from the centre


@pytest.mark.parametrize("guard", [0.0, -1.0])
def test_guard_off_uses_the_pose_as_before(guard):
    res, why, _ = _refine(10.0, expected_tilt_deg=0.0, tilt_guard_deg=guard)
    old, _, _ = _refine(10.0)                                  # the defaults: no guard
    assert why is None and res["position_from"] == old["position_from"] == "camera pose"
    assert (res["predicted_lat"], res["predicted_lon"]) == (old["predicted_lat"], old["predicted_lon"])
    assert "pose_guard" not in res


def test_expected_tilt_of_a_frame():
    assert DaySubscriber._expected_tilt(dict(straightened=True, attitude_source="imu", tilt_deg=12.0)) == 0.0
    assert DaySubscriber._expected_tilt(dict(straightened=False, attitude_source="none")) == 0.0
    assert DaySubscriber._expected_tilt(dict(straightened=False, attitude_source="imu", tilt_deg=7.5)) == 7.5
    assert DaySubscriber._expected_tilt({}) == 0.0
