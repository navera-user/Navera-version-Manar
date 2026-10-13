#!/usr/bin/env python3
"""Teacher only: rebuild datasets/19-calibration/ (and courses/19-calibration/hidden/corners.npz) from NAVERA's bench
recording of 2026-10-06 (DATA copied from NAVERA, never code; owner decision §7.2). Read only on the recording.

    python3 solutions/19-calibration/make_dataset.py [--bench ~/.navera_sim/bench_2026-10-06/calib]

Writes:
  datasets/19-calibration/insta360_top.yaml   the bench calibration of the Insta360 ONE R top lens, copied verbatim
                                               (fisheye, 38 views, RMS 0.525 px, created 2026-10-06)
  datasets/19-calibration/views/fNNNN.jpg     36 real frames of the calibration session, TOP HALF ONLY (1920 × 540,
                                               the calibration's crop), re-encoded JPEG quality 90
  datasets/19-calibration/README.md           a neutral description (students can read it: no answers)
  courses/19-calibration/hidden/corners.npz   the 9 × 6 inner corners of every view (names, corners (36, 54, 1, 2)),
                                               detected as the lab's runner does; check.py's test input

Left out of the bench session's 39 selected frames: f0273 and f0274 (a person's face is visible in the top half) and
f0309 (an older OpenCV asserted on it; with OpenCV 4.11 it calibrates, but it stays out so the course's numbers do
not move). The bottom lens filmed the room and its people: it is never copied.
Measured on the host (2026-10-13, OpenCV 4.11): all 39 original top halves → fx 660.48, RMS 0.5245, f0023 refused
(= the bench file); the course's 36 originals → fx 670.24; the course's 36 re-encoded → fx 670.28, RMS 0.5064, f0023
and f0208 refused. JPEG re-encoding moves the corners by 0.01 px (median), 0.17 px (max).
"""
import argparse
import glob
import os
import shutil
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
from navera_lite.fisheye import find_corners  # noqa: E402

EXCLUDED = {"f0273", "f0274", "f0309"}
README = """# 19-calibration — data

Real data from NAVERA's bench, 6 October 2026 (copied as data; no code).

- `insta360_top.yaml` — the bench calibration of the Insta360 ONE R top lens (fisheye model), as written on the bench.
- `views/fNNNN.jpg` — 36 frames of the calibration session: the top lens only (the top half of the camera's
  1920 × 1080 picture, so 1920 × 540). A chessboard of 9 × 6 inner corners, squares of 32.94 mm, is shown on a
  computer screen. The frames are 36 of the session's 39 selected frames, re-saved as JPEG.
"""

ap = argparse.ArgumentParser()
ap.add_argument("--bench", default=os.path.expanduser("~/.navera_sim/bench_2026-10-06/calib"))
a = ap.parse_args()
out = os.path.join(ACADEMY, "datasets", "19-calibration")
views = os.path.join(out, "views")
os.makedirs(views, exist_ok=True)
shutil.copyfile(os.path.join(a.bench, "insta360_top.yaml"), os.path.join(out, "insta360_top.yaml"))
for old in glob.glob(os.path.join(views, "*.jpg")):
    os.remove(old)
names, corners = [], []
for path in sorted(glob.glob(os.path.join(a.bench, "sel", "f*.jpg"))):
    n = os.path.basename(path)[:-4]
    if n in EXCLUDED:
        continue
    img = cv2.imread(path)
    assert img is not None and img.shape[:2] == (1080, 1920), n
    cv2.imwrite(os.path.join(views, n + ".jpg"), img[:540], [cv2.IMWRITE_JPEG_QUALITY, 90])
    c = find_corners(cv2.imread(os.path.join(views, n + ".jpg")))
    print(n, "board found" if c is not None else "no board", flush=True)
    if c is not None:
        names.append(n)
        corners.append(c)
with open(os.path.join(out, "README.md"), "w") as f:
    f.write(README)
hid = os.path.join(ACADEMY, "courses", "19-calibration", "hidden")
os.makedirs(hid, exist_ok=True)
np.savez(os.path.join(hid, "corners.npz"), names=np.array(names), corners=np.array(corners))
print(f"wrote {len(names)} views to {out} and hidden/corners.npz")
