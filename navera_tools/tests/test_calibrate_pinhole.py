"""calibrate_camera --model pinhole: float64 corner arrays used to crash cv2.calibrateCamera (B1)."""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from calibrate_camera import board_points, calibrate  # noqa: E402


def test_pinhole_calibration_recovers_the_focal_length():
    K = np.array([[800.0, 0, 320], [0, 800.0, 240], [0, 0, 1]])
    obj = board_points(9, 6, 0.04)
    rng = np.random.default_rng(1)
    views = []
    for _ in range(12):
        rvec = rng.normal(0, 0.3, 3)
        tvec = np.array([-0.16, -0.1, 0.6]) + rng.normal(0, 0.05, 3)
        img, _ = cv2.projectPoints(obj, rvec, tvec, K, np.zeros(5))
        views.append(img.astype(np.float64).reshape(-1, 1, 2))      # what find_corners returns
    calib, rms = calibrate(views, (640, 480), 9, 6, 0.04, "pinhole")
    assert rms < 0.01 and abs(calib["camera_matrix"][0] - 800.0) < 1.0
