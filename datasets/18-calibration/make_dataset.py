#!/usr/bin/env python3
"""Rebuild datasets/18-calibration/ from the bench recording of 2026-10-06 (read only).

    python3 make_dataset.py [--bench ~/.navera_sim/bench_2026-10-06/calib]

What it writes (next to this script):
  insta360_top.yaml   the REAL calibration of the Insta360 ONE R top lens (copied verbatim)
  views/fNNNN.jpg     14 REAL frames of the calibration session, TOP HALF ONLY (1920x540 =
                      the calibration's crop [0, 0, 1920, 540]). The bottom lens filmed the
                      people in the room: it is never copied. Each view was checked by eye:
                      no person visible (f0273/f0274 were left out for that reason).
Board on the screen: 9x6 inner corners, 32.94 mm squares.
"""
import argparse
import os
import shutil

import cv2

VIEWS = ["f0022", "f0023", "f0030", "f0044", "f0075", "f0091", "f0099", "f0111", "f0208",
         "f0230", "f0248", "f0287", "f0322", "f0323"]

ap = argparse.ArgumentParser()
ap.add_argument("--bench", default=os.path.expanduser("~/.navera_sim/bench_2026-10-06/calib"))
a = ap.parse_args()
here = os.path.dirname(os.path.abspath(__file__))
shutil.copyfile(os.path.join(a.bench, "insta360_top.yaml"), os.path.join(here, "insta360_top.yaml"))
os.makedirs(os.path.join(here, "views"), exist_ok=True)
for n in VIEWS:
    img = cv2.imread(os.path.join(a.bench, "sel", n + ".jpg"))
    assert img is not None and img.shape[:2] == (1080, 1920), n
    top = img[:540]                                   # top lens only (privacy + the calibrated crop)
    cv2.imwrite(os.path.join(here, "views", n + ".jpg"), top, [cv2.IMWRITE_JPEG_QUALITY, 90])
print(f"wrote insta360_top.yaml and {len(VIEWS)} views to {here}")
