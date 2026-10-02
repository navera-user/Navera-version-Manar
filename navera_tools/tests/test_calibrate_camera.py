#!/usr/bin/env python3
"""The calibration tool recovers a known lens from checkerboard photos.

A 9x6 checkerboard is drawn at 24 poses through a known fisheye lens (the
simulator's Insta360-class lens): calibrate_camera.py --images must find the
focal length within 1 %, and the field of view NAVERA would publish within 1 deg,
with a sub-pixel reprojection error. Exit code 0 = pass.
"""
import math
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
from physical_camera import SIM_LENS  # noqa: E402

from navera_common.camera_model import CameraModel  # noqa: E402

COLS, ROWS, SQ_M = 9, 6, 0.04


def board_image(px=80):
    """The printed board, with a white margin: 10x7 squares."""
    img = np.full(((ROWS + 3) * px, (COLS + 3) * px), 255, np.uint8)
    for r in range(ROWS + 1):
        for c in range(COLS + 1):
            if (r + c) % 2 == 0:
                img[(r + 1) * px:(r + 2) * px, (c + 1) * px:(c + 2) * px] = 0
    return img, px


def render_view(board, px, rvec, tvec):
    """What the true lens sees of the board at this pose (inverse mapping)."""
    w, h = SIM_LENS["image_width"], SIM_LENS["image_height"]
    K = np.array(SIM_LENS["camera_matrix"]).reshape(3, 3)
    D = np.array(SIM_LENS["distortion"])
    u, v = np.meshgrid(np.arange(w, dtype=np.float64), np.arange(h, dtype=np.float64))
    n = cv2.fisheye.undistortPoints(np.stack([u.ravel(), v.ravel()], 1).reshape(-1, 1, 2), K, D).reshape(-1, 2)
    R, _ = cv2.Rodrigues(rvec)
    # ray (n, 1) meets the board plane z_board = 0: board point = s*ray in camera = R*X + t
    ray = np.c_[n, np.ones(len(n))]
    nrm = R[:, 2]
    s = (nrm @ tvec.ravel()) / (ray @ nrm)
    X = (ray * s[:, None] - tvec.ravel()) @ R          # board coordinates (m)
    # the inner-corner grid origin is one square inside the drawn margin + one square
    bx = X[:, 0] / SQ_M * px + 2 * px
    by = X[:, 1] / SQ_M * px + 2 * px
    bad = s <= 0
    bx[bad] = by[bad] = -1
    img = cv2.remap(board, bx.reshape(h, w).astype(np.float32), by.reshape(h, w).astype(np.float32),
                    cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=180)
    return img


def main():
    board, px = board_image()
    rng = np.random.default_rng(3)
    out_dir = tempfile.mkdtemp(prefix="navera_calib_")
    n = 0
    for i in range(24):
        rvec = np.array([rng.uniform(-0.5, 0.5), rng.uniform(-0.5, 0.5), rng.uniform(-0.3, 0.3)])
        # board centred somewhere in the field, 0.35-0.7 m away
        z = rng.uniform(0.35, 0.7)
        tvec = np.array([[rng.uniform(-0.45, 0.25) * z], [rng.uniform(-0.3, 0.15) * z], [z]])
        img = render_view(board, px, rvec, tvec)
        cv2.imwrite(os.path.join(out_dir, f"view_{i:02d}.png"), img)
        n += 1
    out = os.path.join(out_dir, "camera.yaml")
    r = subprocess.run([sys.executable, os.path.join(HERE, "..", "calibrate_camera.py"), "--images", out_dir,
                        "--board", f"{COLS}x{ROWS}", "--square-mm", str(SQ_M * 1000), "--model", "fisheye",
                        "--out", out], capture_output=True, text=True)
    failures = []
    if not os.path.exists(out):
        print(r.stdout[-800:], r.stderr[-800:])
        print("FAIL no calibration written")
        return 1
    c = yaml.safe_load(open(out))
    fx_true, fx = SIM_LENS["camera_matrix"][0], c["camera_matrix"][0]
    hfov_true = CameraModel.from_calibration(SIM_LENS).out_hfov_deg
    hfov = CameraModel.from_calibration(c).out_hfov_deg
    print(f"{c['views']} views used, RMS {c['rms_px']} px; focal {fx:.1f} px (true {fx_true:.1f}), "
          f"field of view {hfov:.2f} deg (true lens: {hfov_true:.2f})")
    if abs(fx - fx_true) / fx_true > 0.01:
        failures.append(f"focal length {fx:.1f} px, true {fx_true:.1f}")
    if abs(hfov - hfov_true) > 1.0:
        failures.append(f"field of view {hfov:.2f} deg, true {hfov_true:.2f}")
    if c["rms_px"] > 0.5:
        failures.append(f"reprojection error {c['rms_px']} px")
    if c["views"] < 12:
        failures.append(f"only {c['views']} views found the board")
    for f in failures:
        print("FAIL", f)
    print("calibrate_camera:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
