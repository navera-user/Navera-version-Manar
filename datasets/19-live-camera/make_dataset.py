#!/usr/bin/env python3
"""Build datasets/19-live-camera/ (run on the host, by the teacher).

Source (read only): frames saved by the Insta360 ONE R (USB webcam mode, MJPG 1920x1080)
during NAVERA's lens calibration session of 2026-10-06, and its calibration file.

    python3 datasets/19-live-camera/make_dataset.py

Writes:
  frames/frame_000.jpg ...  30 consecutive saved frames (f0280-f0309), 1920x1080.
                            PRIVACY: the bottom lens filmed people in the room, so the
                            bottom half (rows 540-1079) is pixelated into 48 px blocks.
  grab_times.csv            SIMULATED grab times: the calibration tool did not record
                            when each frame arrived. They are spaced at the 28.8 fps the
                            camera gives, with a little random jitter (seed 19).
  insta360_top.yaml         the top lens' calibration (fisheye, latency_s 0.138), copied
                            unchanged.
"""
import csv
import os
import random
import shutil

import cv2
import numpy as np

SRC = "/home/shadow-team/.navera_sim/bench_2026-10-06/calib"
OUT = os.path.dirname(os.path.abspath(__file__))
FIRST, N, BLOCK, FPS = 280, 30, 48, 28.8


README = """Lesson 19 dataset — recorded frames of the Insta360 ONE R (USB webcam mode, MJPG 1920x1080).

frames/frame_000..029.jpg  30 consecutive frames saved during NAVERA's lens calibration
                           (2026-10-06). Top half = top lens (the one NAVERA uses), bottom
                           half = bottom lens: it filmed people, so it is PIXELATED (privacy).
grab_times.csv             SIMULATED grab times: the calibration tool did not record when each
                           frame arrived. Spaced at 28.8 fps (what the camera gives) + jitter.
insta360_top.yaml          the real calibration of the top lens (fisheye, 1920x540,
                           latency_s 0.138 measured with navera_tools/bench/camera_latency.py).
Rebuilt by make_dataset.py.
"""


def pixelate(img, block):
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(1, w // block), max(1, h // block)), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)


def main():
    os.makedirs(os.path.join(OUT, "frames"), exist_ok=True)
    for i in range(N):
        img = cv2.imread(os.path.join(SRC, "frames", f"f{FIRST + i:04d}.jpg"))
        assert img is not None and img.shape == (1080, 1920, 3)
        img[540:] = pixelate(img[540:], BLOCK)
        cv2.imwrite(os.path.join(OUT, "frames", f"frame_{i:03d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    rng = random.Random(19)
    t = 1791360000.0                                   # an arbitrary start (seconds)
    with open(os.path.join(OUT, "grab_times.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "grab_time_s"])
        for i in range(N):
            w.writerow([f"frame_{i:03d}.jpg", f"{t + i / FPS + rng.gauss(0, 0.002):.4f}"])
    with open(os.path.join(OUT, "README.txt"), "w") as f:
        f.write(README)
    shutil.copyfile(os.path.join(SRC, "insta360_top.yaml"), os.path.join(OUT, "insta360_top.yaml"))
    print("done:", OUT)


if __name__ == "__main__":
    main()
