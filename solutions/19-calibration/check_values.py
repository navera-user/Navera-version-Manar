#!/usr/bin/env python3
"""Teacher only: every constant of courses/19-calibration/check.py, recomputed from the course reference
(solutions/_navera_lite) on the check's unseen inputs, plus the values of the typical mistakes.

    python3 solutions/19-calibration/check_values.py
"""
import io
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
import cv2  # noqa: E402
import numpy as np  # noqa: E402
from navera_lite import fisheye as fe  # noqa: E402

np.set_printoptions(precision=6, suppress=True)
z = np.load(os.path.join(ACADEMY, "courses", "19-calibration", "hidden", "corners.npz"))
names, views = [str(n) for n in z["names"]], list(z["corners"])
obj = fe.board_points(9, 6, fe.SQUARE_M)

print("== TODO 2: theta_from_theta_d with D3")
D3 = [0.12, -0.35, 0.30, -0.10]
g = np.linspace(0, math.pi / 2, 400001)
v = fe.theta_d_of(g, D3)
i = int(np.argmax(v))
print("peak theta", g[i], "theta_d max", v[i])
for td in (0.3, 0.8, 1.0, v[i] - 1e-4, v[i] + 0.02):
    print(" ", td, fe.theta_from_theta_d(td, D3))

print("== TODO 3: stretch_at with K3, D3")
K3 = np.array([[500.0, 0, 600], [0, 520, 300], [0, 0, 1]])
for args in ((25.0, 450.0), (50.0, 380.0), (0.0, 610.0), (70.0, 450.0), (89.0, 450.0)):
    print(" ", args, fe.stretch_at(*args, K3, D3))
t = math.radians(50.0)
print("  mistakes (50, 380): no slope", 380 / math.cos(t) ** 2 / 500, "avg", 380 / math.cos(t) ** 2 / (500 * fe.theta_d_of(t, D3) / t),
      "inverted", 1 / fe.stretch_at(50.0, 380.0, K3, D3))

print("== TODO 6: calibrate_fisheye on 12 real views")
SUB = ["f0022", "f0030", "f0044", "f0080", "f0090", "f0111", "f0216", "f0230", "f0252", "f0286", "f0322", "f0323"]
vs = [views[names.index(n)] for n in SUB]
rms, K, D, rv, tv = fe.calibrate_fisheye(obj, vs, (1920, 540))
print("  rms", rms, "K", K.ravel(), "D", D.ravel())
try:
    fe.calibrate_fisheye(obj, views, (1920, 540))
    print("  all 36: NO error")
except cv2.error as e:
    print("  all 36 raises:", str(e).strip().splitlines()[-1][:120])
# without CHECK_COND (a typical mistake): what fx?
r2, K2_, D2_, _, _ = cv2.fisheye.calibrate([obj] * len(views), views, (1920, 540), np.eye(3), np.zeros((4, 1)),
                                            flags=cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_FIX_SKEW,
                                            criteria=fe.CRITERIA)
print("  mistake no CHECK_COND on 36:", r2, K2_[0, 0])
r3, K3_, *_ = cv2.fisheye.calibrate([obj] * len(vs), vs, (1920, 540), np.eye(3), np.zeros((4, 1)),
                                    flags=cv2.fisheye.CALIB_CHECK_COND | cv2.fisheye.CALIB_FIX_SKEW, criteria=fe.CRITERIA)
print("  mistake no RECOMPUTE_EXTRINSIC on 12:", r3, K3_[0, 0])
r4, K4_, *_ = cv2.fisheye.calibrate([obj] * len(vs), vs, (1920, 540), np.eye(3), np.zeros((4, 1)),
                                    flags=cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_CHECK_COND, criteria=fe.CRITERIA)
print("  mistake no FIX_SKEW on 12:", r4, K4_.ravel()[:3])

print("== TODO 7: reprojection_rms of that 12-view calibration (per view)")
tot, per = fe.reprojection_rms(obj, vs, rv, tv, K, D)
print("  total", tot, "per", np.round(per, 6))
print("  mistake mean of per-view", np.mean(per))

print("== TODO 8: holdout_rms — train on 16 views, test on 6 unseen")
TRAIN = ["f0030", "f0044", "f0075", "f0085", "f0087", "f0099", "f0114", "f0130", "f0214", "f0215", "f0239",
         "f0248", "f0257", "f0285", "f0292", "f0321"]
TEST = ["f0022", "f0090", "f0216", "f0252", "f0287", "f0323"]
(r, Kt, Dt, *_), kept, dropped = fe.calibrate_robust(obj, [views[names.index(n)] for n in TRAIN], (1920, 540), TRAIN)
print("  train", r, kept.__len__(), dropped, "K", repr(Kt), "D", repr(Dt.ravel()))
te, per = fe.holdout_rms(obj, [views[names.index(n)] for n in TEST], Kt, Dt)
print("  test", te, np.round(per, 6))
# mistake: pinhole solvePnP on raw pixels with K and no distortion
sq = []
for n in TEST:
    vv = views[names.index(n)]
    ok, rvv, tvv = cv2.solvePnP(obj, vv, Kt, None)
    R, _ = cv2.Rodrigues(rvv)
    p = fe.fisheye_project(obj.reshape(-1, 3) @ R.T + tvv.reshape(1, 3), Kt, Dt)
    sq.append(((p - vv.reshape(-1, 2)) ** 2).sum(1))
print("  mistake pinhole pose:", math.sqrt(np.concatenate(sq).mean()))
