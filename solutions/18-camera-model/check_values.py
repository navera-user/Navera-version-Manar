#!/usr/bin/env python3
"""Mission 18 (teacher only) — the expected values pasted into courses/18-camera-model/check.py, computed once
with the course reference (solutions/18-camera-model/navera_lite, built by tools/lite_build.py).

    python3 solutions/18-camera-model/check_values.py
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from navera_lite.camera import (K_from_hfov, backproject_ground, camera_rotation_hpr, focal_px, footprint, gsd,  # noqa
                                nadir_homography, project, tilt_position_error)

np.set_printoptions(precision=6, suppress=True)
r = lambda v: np.round(np.asarray(v, dtype=float), 6).tolist()   # noqa: E731
print("focal_px", focal_px(50, 2048), focal_px(120, 640))
print("K_from_hfov(75,1600,1200)", r(K_from_hfov(75, 1600, 1200)))
K1 = np.array([[700.0, 0, 500], [0, 700, 400], [0, 0, 1]])
R1, R2 = camera_rotation_hpr(0.0), camera_rotation_hpr(125.0, -18.0, 7.0)
print("R2", r(R2))
print("project R1", r(project(K1, R1, [10, -20, 180], [55, 40, 0])))
for X in ([-50, 120, 0], [-90, 60, 30], [-30, 15, 260], [400, 300, 0]):
    print("project R2", X, None if project(K1, R2, [-30, 15, 210], X) is None else r(project(K1, R2, [-30, 15, 210], X)))
for uv in ((500, 400), (120, 650), (900, 100)):
    print("backproject R2", uv, r(backproject_ground(K1, R2, [-30, 15, 210], *uv)))
print("sky", backproject_ground(K1, camera_rotation_hpr(0.0, 75.0, 0.0), [0, 0, 100], 500, 0))
print("gsd", gsd(240, 84, 1600), gsd(55, 120, 640))
print("footprint R2", r(footprint(K1, R2, [-30, 15, 210], 1000, 800)))
print("footprint sky", footprint(K1, camera_rotation_hpr(0.0, -65.0, 0.0), [0, 0, 100], 1000, 800))
print("tilt", tilt_position_error(320, 25, 1.5), tilt_position_error(80, 0, 3), tilt_position_error(200, 15, -2))
print("H R2->level heading 125", r(nadir_homography(K1, R2, camera_rotation_hpr(125.0))))
print("H R2->north-up", r(nadir_homography(K1, R2, camera_rotation_hpr(0.0))))

# ---- the values typical mistakes give on the same inputs (for the check's diagnoses) ----
print("\nMISTAKES")
C2 = np.array([-30.0, 15, 210])


def proj(K, R, C, X, transpose=True, minusC=True):
    Xc = (R.T if transpose else R) @ (np.asarray(X, float) - (C if minusC else 0))
    p = K @ Xc
    return r(p[:2] / p[2])


print("project R not transposed", proj(K1, R2, C2, [-50, 120, 0], transpose=False))
print("project C not subtracted", proj(K1, R2, C2, [-50, 120, 0], minusC=False))
print("project R1 not transposed", proj(K1, R1, np.array([10, -20, 180.0]), [55, 40, 0], transpose=False))


def bp(K, R, C, u, v, transpose=False, ignoreC=False):
    d = (R.T if transpose else R) @ np.linalg.solve(K, [u, v, 1.0])
    lam = -C[2] / d[2]
    X = (np.zeros(3) if ignoreC else C) + lam * d
    return r(X[:2])


print("backproject R transposed", bp(K1, R2, C2, 500, 400, transpose=True))
print("backproject C e,n ignored", bp(K1, R2, C2, 500, 400, ignoreC=True))
print("gsd degrees", 2 * 240 * math.tan(42) / 1600, "no /2", 2 * 240 * math.tan(math.radians(84)) / 1600)
print("focal degrees", 1024 / math.tan(25), "no half", 1024 / math.tan(math.radians(50)))
print("tilt linear", 320 * math.radians(1.5) / math.cos(math.radians(25)) ** 2, "nadir-linear", 320 * math.radians(1.5),
      "degrees", abs(320 * math.tan(26.5) - 320 * math.tan(25)), "signed (−2)", -7.416200261111911)
Rv = camera_rotation_hpr(125.0)
Hs = K1 @ Rv @ R2.T @ np.linalg.inv(K1)
print("H swapped (R_wv @ R_wc.T)", r(Hs / Hs[2, 2]))
Hn = K1 @ Rv.T @ R2 @ np.linalg.inv(K1)
print("H not normalised H[2,2]", Hn[2, 2])
Hk = np.linalg.inv(K1) @ Rv.T @ R2 @ K1
print("H with K and K⁻¹ swapped", r(Hk / Hk[2, 2]))


def att(h, t, linear=False):
    lo, hi = 0.0, 40.0
    for _ in range(100):
        m = (lo + hi) / 2
        e = h * math.radians(m) / math.cos(math.radians(t)) ** 2 if linear else h * (math.tan(math.radians(t + m)) - math.tan(math.radians(t)))
        lo, hi = (m, hi) if e < 30 else (lo, m)
    return lo


print("attack exact 8/35", att(250, 8), att(250, 35), "linear 8/35", att(250, 8, True), att(250, 35, True))
