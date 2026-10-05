#!/usr/bin/env python3
"""Calibrate NAVERA's camera lens (once per camera) — writes the file live_camera reads.

    # live, from the camera itself (e.g. the Insta360 ONE R in webcam mode):
    python3 navera_tools/calibrate_camera.py --device /dev/v4l/by-id/usb-<camera>-video-index0 --size 1920x1080 \\
        --board 9x6 --square-mm 25 --out /var/lib/navera/camera.yaml
    # or from photos already taken with the camera at that resolution:
    python3 navera_tools/calibrate_camera.py --images ./calib_photos --board 9x6 --square-mm 25 --out camera.yaml

Print a checkerboard (--board = inner corners, columns x rows; --square-mm = printed
square side), stick it flat on a rigid board, and show it to the camera at 20-40
different positions: near the corners and edges of the image (where a wide lens
distorts most), tilted up to ~45 deg, at different distances. In live mode a view is
kept when the board is found and it is not too close to a view already kept.

Model: 'fisheye' (OpenCV k1..k4: wide lenses such as the Insta360 4K wide-angle) or
'pinhole' (k1,k2,p1,p2,k3). The result reports the RMS reprojection error (pixels;
below ~0.5 is good) and the field of view NAVERA will publish.
Same resolution as NAVERA_CAMERA_SIZE: a calibration is valid for one resolution.
"""
import argparse
import glob
import math
import os
import sys
import time

import cv2
import numpy as np
import yaml


def board_points(cols, rows, square_m):
    obj = np.zeros((rows * cols, 1, 3), np.float64)
    obj[:, 0, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_m
    return obj


def find(img, cols, rows):
    grey = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ok, corners = cv2.findChessboardCornersSB(grey, (cols, rows), cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
    return corners.astype(np.float64).reshape(-1, 1, 2) if ok else None


def calibrate(views, size, cols, rows, square_m, model):
    """views: list of corner arrays. Returns (calibration dict, rms px)."""
    obj = [board_points(cols, rows, square_m)] * len(views)
    w, h = size
    if model == "fisheye":
        K, D = np.eye(3), np.zeros((4, 1))
        flags = (cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_CHECK_COND |
                 cv2.fisheye.CALIB_FIX_SKEW)
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-9)
        # CALIB_CHECK_COND refuses ill-conditioned views: drop them one by one
        while True:
            try:
                rms, K, D, _, _ = cv2.fisheye.calibrate(obj, views, (w, h), K, D, flags=flags, criteria=crit)
                break
            except cv2.error as e:
                msg = str(e)
                import re
                m = re.search(r"input array (\d+)", msg)
                if not m or len(views) <= 8:
                    raise
                bad = int(m.group(1))
                views = views[:bad] + views[bad + 1:]
                obj = obj[:len(views)]
        dist = [float(v) for v in D.ravel()]
    else:
        rms, K, D, _, _ = cv2.calibrateCamera(obj, views, (w, h), None, None)
        dist = [float(v) for v in D.ravel()[:5]]
    calib = dict(model=model, image_width=w, image_height=h,
                 camera_matrix=[float(v) for v in K.ravel()], distortion=dist,
                 rms_px=round(float(rms), 3), views=len(views),
                 created=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return calib, float(rms)


def far_from(corners, kept, min_px):
    c = corners.reshape(-1, 2).mean(axis=0)
    return all(np.linalg.norm(c - k.reshape(-1, 2).mean(axis=0)) > min_px for k in kept)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--device", help="camera device, e.g. /dev/video0")
    src.add_argument("--images", help="folder of photos taken with the camera")
    ap.add_argument("--size", default="1920x1080", help="WIDTHxHEIGHT (live mode)")
    ap.add_argument("--crop", default="", help="the part of the picture NAVERA uses: top, bottom, left, "
                                                "right or x,y,w,h (as NAVERA_CAMERA_CROP; a 360 camera's "
                                                "downward lens)")
    ap.add_argument("--preview", action="store_true", help="live mode: show the camera and the board found")
    ap.add_argument("--board", default="9x6", help="inner corners, columns x rows")
    ap.add_argument("--square-mm", type=float, required=True)
    ap.add_argument("--model", choices=["fisheye", "pinhole"], default="fisheye")
    ap.add_argument("--views", type=int, default=30, help="views to collect in live mode")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cols, rows = (int(v) for v in a.board.lower().split("x"))
    views, size, crop = [], None, None
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "navera_common"))
    from navera_common.camera_model import parse_crop

    def cut(img):
        nonlocal crop
        if a.crop and crop is None:
            crop = parse_crop(a.crop, img.shape[1], img.shape[0])
        if crop:
            x, y, w_, h_ = crop
            return img[y:y + h_, x:x + w_]
        return img
    if a.images:
        files = sorted(f for f in glob.glob(os.path.join(a.images, "*")) if f.lower().endswith((".jpg", ".jpeg", ".png")))
        for f in files:
            img = cv2.imread(f)
            if img is None:
                continue
            img = cut(img)
            if size is None:
                size = (img.shape[1], img.shape[0])
            elif (img.shape[1], img.shape[0]) != size:
                print(f"skip {f}: {img.shape[1]}x{img.shape[0]}, not {size[0]}x{size[1]}")
                continue
            c = find(img, cols, rows)
            print(f"{os.path.basename(f)}: {'board found' if c is not None else 'no board'}")
            if c is not None:
                views.append(c)
    else:
        w, h = (int(v) for v in a.size.lower().split("x"))
        cap = cv2.VideoCapture(a.device, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        if not cap.isOpened():
            sys.exit(f"cannot open {a.device}")
        size = None
        print(f"show the board to the camera — {a.views} views to collect (Ctrl-C to stop early)")
        try:
            while len(views) < a.views:
                ok, img = cap.read()
                if not ok:
                    continue
                if (img.shape[1], img.shape[0]) != (w, h):
                    sys.exit(f"the camera gives {img.shape[1]}x{img.shape[0]}, not {w}x{h}: check --size")
                img = cut(img)
                size = (img.shape[1], img.shape[0])
                c = find(img, cols, rows)
                kept = c is not None and far_from(c, views, 0.08 * size[0])
                if kept:
                    views.append(c)
                    print(f"view {len(views)}/{a.views} kept")
                if a.preview:
                    show = img.copy()
                    if c is not None:
                        cv2.drawChessboardCorners(show, (cols, rows), c.astype(np.float32), True)
                    for k in views:                                  # where views were kept
                        cv2.circle(show, tuple(int(v) for v in k.reshape(-1, 2).mean(axis=0)), 12, (0, 200, 0), 3)
                    cv2.putText(show, f"{len(views)}/{a.views}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.5,
                                (0, 0, 255), 3)
                    scale = min(1.0, 1280.0 / show.shape[1])
                    cv2.imshow("NAVERA calibration", cv2.resize(show, None, fx=scale, fy=scale))
                    if cv2.waitKey(1) == 27:
                        break
        except KeyboardInterrupt:
            pass
        cap.release()
    if len(views) < 8:
        sys.exit(f"only {len(views)} views with the board: at least 8 needed (20-40 recommended)")
    calib, rms = calibrate(views, size, cols, rows, a.square_mm / 1000.0, a.model)
    from navera_common.camera_model import CameraModel
    cam = CameraModel.from_calibration(calib)
    calib["out_hfov_deg"] = round(cam.out_hfov_deg, 2)
    if crop:
        calib["crop"] = list(crop)                    # live_camera checks it uses the same part
    if a.device:
        from navera_common.vehicle import camera_identity
        calib["camera_id"] = camera_identity(a.device)       # live_camera checks it is this camera
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w") as f:
        f.write("# NAVERA camera calibration (navera_tools/calibrate_camera.py) — NAVERA_CAMERA_CALIBRATION\n")
        yaml.safe_dump(calib, f, sort_keys=False)
    verdict = "good" if rms < 0.5 else "usable" if rms < 1.0 else "POOR — redo with more, sharper views"
    print(f"\n{a.model} calibration from {calib['views']} views: RMS {rms:.3f} px ({verdict}); "
          f"NAVERA will publish a {cam.out_hfov_deg:.1f} deg wide undistorted image -> {a.out}")
    return 0 if rms < 1.0 else 2


if __name__ == "__main__":
    sys.exit(main())
