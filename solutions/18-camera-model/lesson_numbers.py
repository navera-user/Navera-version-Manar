#!/usr/bin/env python3
"""Mission 18 (teacher only) — recompute every number of lesson.md with the course reference (camera.py).

    python3 solutions/18-camera-model/lesson_numbers.py
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "navera_lite", ".."))
from navera_lite.camera import (K_from_hfov, backproject_ground, camera_rotation_hpr, focal_px, footprint, gsd,  # noqa
                                nadir_homography, project, tilt_position_error, warp_point)

np.set_printoptions(suppress=True, precision=4)
f = 800.0
W, H = 1280, 720
hfov = 2 * math.degrees(math.atan(W / 2 / f))
print(f"lesson camera 1280x720 f=800: HFOV {hfov:.2f}, VFOV {2 * math.degrees(math.atan(H / 2 / f)):.2f}")
K = K_from_hfov(hfov, W, H)
print("K", K)
for name, w, h, fov in (("Insta360 straightened", 1920, 540, 111.0), ("narrow", 1920, 1080, 30.0), ("lab", 960, 540, 90.0)):
    ff = focal_px(fov, w)
    print(f"{name}: f {ff:.1f}, VFOV {2 * math.degrees(math.atan(h / 2 / ff)):.2f}")
ff = focal_px(70, 1600)
print(f"check: HFOV 70 on 1600 px: f {ff:.1f}, VFOV(900) {2 * math.degrees(math.atan(450 / ff)):.2f}")
R0 = camera_rotation_hpr(0.0)
print("worked 1: (30, 45, 0) from 150 m:", project(K, R0, [0, 0, 150], [30, 45, 0]))
print("check: X_c (-20, 10, 200) f=800:", 800 * -20 / 200 + 640, 800 * 10 / 200 + 360)
R20 = camera_rotation_hpr(0.0, -20.0, 0.0)
print("worked 2: centre at 120 m, nose down 20:", backproject_ground(K, R20, [0, 0, 120], 640, 360),
      "slant", 120 / math.cos(math.radians(20)))
vf2 = math.degrees(math.atan(H / 2 / f))
print(f"edges at 120 m, 20 deg: near {120 * math.tan(math.radians(20 - vf2)):.1f}, far {120 * math.tan(math.radians(20 + vf2)):.1f}")
print("nadir footprint at 120 m:", footprint(K, R0, [0, 0, 120], W, H)[1] * 2)


def shoelace(p):
    x, y = np.asarray(p).T
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


for p in (0, -15, -30):
    R = camera_rotation_hpr(0.0, p, 0.0)
    fp = footprint(K, R, [0, 0, 120], W, H)
    c = backproject_ground(K, R, [0, 0, 120], 640, 360)
    print(f"pitch {p}: area {shoelace(fp):.0f}, centre {c[1]:.1f}, near/far {fp[2:, 1].mean():.1f}/{fp[:2, 1].mean():.1f},"
          f" near width {fp[2, 0] - fp[3, 0]:.1f}, far width {fp[1, 0] - fp[0, 0]:.1f}")
print("check ray: C (0,0,120) d (0.2,0.1,-0.8):", 120 / 0.8 * 0.2, 120 / 0.8 * 0.1)
print(f"GSD Insta360 150 m: {gsd(150, 111, 1920):.4f}; lesson camera 120 m: {120 / f:.3f}")
print(f"Insta at 300 m: {gsd(300, 111, 1920):.4f}")
for lat in (35.83,):
    for z in (17, 18):
        print(f"map Sousse z{z}: {40075016.686 * math.cos(math.radians(lat)) / 256 / 2 ** z:.4f}")
print("scale photo->map at 150 m, z18:", gsd(150, 111, 1920) / (40075016.686 * math.cos(math.radians(35.83)) / 256 / 2 ** 18))
print("mountain: predicted 1800, true 300 -> scale", 300 / 1800)
print("tilt 150 m, 10 deg, 1 deg exact", tilt_position_error(150, 10, 1), "linear",
      150 * math.radians(1) / math.cos(math.radians(10)) ** 2, "nadir h*dtheta", 150 * math.radians(1))
print("tilt 300 m 0 deg 1 deg", tilt_position_error(300, 0, 1))
print("28 m at h = 185 m: tilt", math.degrees(math.atan(28 / 185)))
R10 = camera_rotation_hpr(0.0, -10.0, 0.0)
Hm = nadir_homography(K, R10, R0)
print("H (pitch -10, lesson camera)", Hm)
print("centre ->", warp_point(Hm, 640, 360))
under = project(K, R10, [0, 0, 100], [0, 0, 0])
print("under drone in tilted image", under, "->", warp_point(Hm, *under))
print("800 tan 10", 800 * math.tan(math.radians(10)))
Rr = camera_rotation_hpr(0.0, 0.0, 8.0)
Hr = nadir_homography(K, Rr, R0)
print("check roll 8: centre ->", warp_point(Hr, 640, 360), 800 * math.tan(math.radians(8)))
