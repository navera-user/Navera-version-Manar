#!/usr/bin/env python3
"""check_values.py — the expected values of check.py's unseen tests, computed ONCE from the reference (teacher only).
Run: python3 solutions/23-locate-on-map/check_values.py   (prints the constants pasted into check.py)."""
import os
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "_navera_lite"))
from navera_lite import locate as L, retrieval as R  # noqa: E402

# TODO 1 — preprocess: a random colour picture 300 × 260 (H × W), and size 112
img = np.random.default_rng(2323).integers(0, 256, (2, 300, 260, 3)).astype(np.uint8)
t = R.preprocess(img).numpy()
PIX = [(0, 0, 0, 0), (0, 1, 50, 60), (1, 2, 223, 223), (1, 0, 100, 7), (0, 2, 13, 200)]
print("PRE224", [round(float(t[p]), 5) for p in PIX], t.shape)
t2 = R.preprocess(img[:1], size=112).numpy()
print("PRE112", [round(float(t2[0, c, 40, 70]), 5) for c in range(3)], t2.shape)
# mutants: BGR kept, no /255, linear resize
import cv2  # noqa: E402
def mut(bgr=False, scale=True, interp=cv2.INTER_AREA):
    out = []
    for im in img:
        x = cv2.resize(im, (224, 224), interpolation=interp).astype(np.float32)
        x = x if bgr else x[:, :, ::-1]
        x = x / 255.0 if scale else x
        out.append(((x - np.array(R.IMAGENET_MEAN)) / np.array(R.IMAGENET_STD)).transpose(2, 0, 1))
    o = np.stack(out)
    return [round(float(o[p]), 5) for p in PIX]
print("PRE_BGR", mut(bgr=True))
print("PRE_LINEAR", mut(interp=cv2.INTER_LINEAR))

# TODO 2 — rank
q = [0.3, -1.2, 2.0, 0.5]
E = np.array([[1.0, 0.0, 0.0, 0.0], [0.6, -2.4, 4.0, 1.0], [-0.3, 1.2, -2.0, -0.5], [0.0, 0.0, 3.0, 0.0],
              [2.0, 1.0, 0.5, -1.0], [0.0, 0.0, 3.0, 0.0]])
o, s = R.rank(q, E)
print("RANK", o.tolist(), [round(float(v), 6) for v in s])

# TODO 3 — evaluate
for errs in ([12.0, 3.5, None, 410.0, 7.25, None, 64.0, 1.0], [None, None], [250.0], [300.0, 301.0, 55.0, 50.0]):
    print("EVAL", errs, L.evaluate(errs))
print("EVAL wrong_m=10", L.evaluate([12.0, 3.5, None, 410.0, 7.25, None, 64.0, 1.0], wrong_m=10.0))

# TODO 5 — info_nce
g = torch.Generator().manual_seed(5)
za = torch.nn.functional.normalize(torch.randn(6, 4, generator=g), dim=1)
zp = torch.nn.functional.normalize(za + 0.8 * torch.randn(6, 4, generator=g), dim=1)
print("ZA", [[round(float(v), 6) for v in r] for r in za])
print("ZP", [[round(float(v), 6) for v in r] for r in zp])
za = torch.tensor([[round(float(v), 6) for v in r] for r in za])
zp = torch.tensor([[round(float(v), 6) for v in r] for r in zp])
for tau in (0.1, 0.5, 1.0):
    print("NCE", tau, round(float(R.info_nce(za, zp, tau)), 6))
lg = za @ zp.T / 0.1
F = torch.nn.functional
print("NCE_SUM", round(float(F.cross_entropy(lg, torch.arange(6), reduction="sum")), 6))
print("NCE_COLS", round(float(F.cross_entropy(lg.T, torch.arange(6))), 6))
print("NCE_NOTAU", round(float(F.cross_entropy(za @ zp.T, torch.arange(6))), 6))
print("NCE_SYM", round(float((F.cross_entropy(lg, torch.arange(6)) + F.cross_entropy(lg.T, torch.arange(6))) / 2), 6))

# TODO 6 — search_radius
for a in ((37.5,), (37.5, 2.0), (7.0, 3.0, 50.0), (700.0, 3.0, 80.0, 1000.0), (0.0,)):
    print("SR", a, L.search_radius(*a))

# TODO 7 — place
A = np.array([[0.97, -0.21, 412.3], [0.21, 0.97, 377.9]])
print("PLACE", L.place(A, 23, (447, 447), 69391.2421875, 51553.71875))
print("PLACE3", L.place(A, 23, (447, 447, 3), 69391.2421875, 51553.71875, z=17))
print("PLACE_nohalf", __import__("navera_lite.tiles", fromlist=["x"]).pixel_to_latlon(
    *(A @ np.array([223.0, 223.0, 1.0])), 17, 69391.2421875, 51553.71875))
print("PLACE z18", L.place(A, 23, (447, 447), 2 * 69391.2421875, 2 * 51553.71875, z=18))
print("PLACE scale", L.place(np.array([[1.2, 0.0, 10.0], [0.0, 1.2, 10.0]]), 40, (101, 101), 69391.0, 51553.0))
print("PLACE tol", L.place(np.array([[1.2, 0.0, 10.0], [0.0, 1.2, 10.0]]), 40, (101, 101), 69391.0, 51553.0,
                           scale_tol=0.25))
print("PLACE inl", L.place(A, 5, (447, 447), 69391.0, 51553.0), L.place(A, 5, (447, 447), 69391.0, 51553.0, min_inliers=4))

# TODO 9 — budget
print("BUDGET", L.budget({"a": 1.5, "b": 2.0, "c": 6.0}), L.budget([0.3, 0.4]), L.budget({}))
