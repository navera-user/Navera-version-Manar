#!/usr/bin/env python3
"""Rebuild datasets/18-calibration/ from the bench recording of 2026-10-06 (read only).

    python3 make_dataset.py [--bench ~/.navera_sim/bench_2026-10-06/calib]

What it writes (next to this script):
  insta360_top.yaml   the REAL calibration of the Insta360 ONE R top lens (copied verbatim;
                      made on the bench from 38 views, RMS 0.525 px)
  views/fNNNN.jpg     36 REAL frames of the calibration session, TOP HALF ONLY (1920x540 =
                      the calibration's crop [0, 0, 1920, 540]).
  corners_ref.npz     the 9x6 inner corners found in each view (names, corners (N,54,1,2)
                      float64), with the same detector as calibrate_camera.py — used by
                      check.py so that grading does not need the 1-minute detection.
Privacy: the bottom lens filmed the people in the room: it is never copied. Every top half
was checked by eye: f0273 and f0274 show a person's face in the top half and are left out.
f0309 is left out too: OpenCV's fisheye initialisation asserts on it (see EXCLUDED).
Board on the screen: 9x6 inner corners, 32.94 mm squares.
"""
import argparse
import glob
import os
import shutil

import cv2
import numpy as np

EXCLUDED = {"f0273", "f0274",          # a face is visible in the top half
            "f0309"}                   # OpenCV's fisheye initialisation fails on it (InitExtrinsics
                                       # assertion) and calibrate_camera.py cannot drop such a view

ap = argparse.ArgumentParser()
ap.add_argument("--bench", default=os.path.expanduser("~/.navera_sim/bench_2026-10-06/calib"))
a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__))
shutil.copyfile(os.path.join(a.bench, "insta360_top.yaml"), os.path.join(here, "insta360_top.yaml"))
out = os.path.join(here, "views")
os.makedirs(out, exist_ok=True)
for old in glob.glob(os.path.join(out, "*.jpg")):
    os.remove(old)
names, corners = [], []
for path in sorted(glob.glob(os.path.join(a.bench, "sel", "f*.jpg"))):
    n = os.path.basename(path)[:-4]
    if n in EXCLUDED:
        continue
    img = cv2.imread(path)
    assert img is not None and img.shape[:2] == (1080, 1920), n
    top = img[:540]                                   # top lens only (privacy + the calibrated crop)
    cv2.imwrite(os.path.join(out, n + ".jpg"), top, [cv2.IMWRITE_JPEG_QUALITY, 90])
    saved = cv2.cvtColor(cv2.imread(os.path.join(out, n + ".jpg")), cv2.COLOR_BGR2GRAY)  # as calibrate_camera.py
    ok, c = cv2.findChessboardCornersSB(saved, (9, 6), flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
    if ok:
        names.append(n)
        corners.append(c.astype(np.float64).reshape(-1, 1, 2))
    print(n, "board found" if ok else "no board")
np.savez(os.path.join(here, "corners_ref.npz"), names=np.array(names), corners=np.array(corners))
print(f"wrote insta360_top.yaml, {len(names)} views with corners to {here}")
