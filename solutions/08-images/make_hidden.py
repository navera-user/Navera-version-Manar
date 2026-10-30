#!/usr/bin/env python3
"""Mission 08: the check's unseen test pictures (teacher only).

    PYTHONPATH= python3 solutions/08-images/make_hidden.py

Writes courses/08-images/hidden/ (sealed: only check.py reads it, from memory):
  photo_b.png   320 x 240 BGR "drone photo" of an olive orchard near Monastir (not the lab's place), true heading
                250°, 0.45 m/px, with camera effects — the student never sees it
  like_b.png    like_map(photo_b, 250.0, 0.45, 0.97) by the course reference (uint8, 186 x 186)
"""
import os
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "datasets", "_map"))
sys.path.insert(0, os.path.join(REPO, "solutions", "_navera_lite"))
from render_view import render_view  # noqa: E402
from navera_lite.image import like_map  # noqa: E402

OUT = os.path.join(REPO, "courses", "08-images", "hidden")
PLACE = (35.7660, 10.8260)            # Monastir, near the ribat
HEADING, GSD, GSD_MAP = 250.0, 0.45, 0.97


def main():
    os.makedirs(OUT, exist_ok=True)
    fx = {"blur": 0.8, "noise": 3.0, "gamma": 0.85, "brightness": 1.1, "vignette": 0.2, "jpeg": 90}
    photo = render_view(*PLACE, HEADING, ground_size_m=320 * GSD, out_px=(320, 240), style="pseudo", seed=21,
                        effects=fx)
    cv2.imwrite(os.path.join(OUT, "photo_b.png"), photo)
    ready = like_map(photo, HEADING, GSD, GSD_MAP)
    cv2.imwrite(os.path.join(OUT, "like_b.png"), ready)
    print("written", OUT, photo.shape, ready.shape, ready.dtype)


if __name__ == "__main__":
    main()
