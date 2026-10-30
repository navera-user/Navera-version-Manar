#!/usr/bin/env python3
"""Teacher tool: recompute the expected values pasted into courses/24-visual-odometry/check.py from the reference.

    python3 solutions/24-visual-odometry/check_values.py

check.py never imports the reference; when the dataset, the reference or a check input changes, run this and paste.
"""
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "solutions", "_navera_lite"))
from navera_lite import vo  # noqa: E402

HID = os.path.join(REPO, "courses", "24-visual-odometry", "hidden")


def smooth(seed, h, w):
    g = np.random.default_rng(seed).random((h, w))
    import cv2
    return cv2.GaussianBlur(g, (0, 0), 1.2)


def fourier_shift(img, dx, dy):
    h, w = img.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    return np.real(np.fft.ifft2(np.fft.fft2(img) * np.exp(-2j * np.pi * (fx * dx + fy * dy))))


def main():
    g = np.random.default_rng(2424).random((48, 64))
    for s in ((3, -7), (-11, 20), (0, 31), (17, 0)):
        print("roll", s, np.round(vo.phase_shift(g, np.roll(g, s, axis=(0, 1))), 4))
    n = np.random.default_rng(99)
    print("noise", np.round(vo.phase_shift(n.random((48, 64)), n.random((48, 64))), 4))
    sm = smooth(7, 60, 72)
    for dx, dy in ((0.4, -0.3), (-2.25, 1.7), (5.5, 0.0)):
        print("subpixel", (dx, dy), np.round(vo.phase_shift(sm, fourier_shift(sm, dx, dy)), 4))
    d = np.load(os.path.join(HID, "test_pairs.npz"))
    for a, b, t in zip(d["a"], d["b"], d["shift"]):
        dx, dy, r = vo.phase_shift(a, b)
        print("hidden pair", np.round(t, 3), "got", round(dx, 3), round(dy, 3), "resp", round(r, 3),
              "err", round(math.hypot(dx - t[0], dy - t[1]), 3))
    f = np.load(os.path.join(HID, "test_flight.npz"))
    import cv2
    steps = []
    for i in range(1, len(f["frames"])):
        turn = (f["heading"][i] - f["heading"][i - 1] + 180) % 360 - 180
        a = f["frames"][i - 1].astype(np.float32)
        R = cv2.getRotationMatrix2D(((a.shape[1] - 1) / 2, (a.shape[0] - 1) / 2), float(turn), 1.0)
        a = cv2.warpAffine(a, R, (a.shape[1], a.shape[0]), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        dx, dy, _ = vo.phase_shift(a, f["frames"][i])
        steps.append(vo.px_to_en(dx, dy, float(f["m_per_px"]), float(f["heading"][i])))
    tr = vo.integrate(steps)
    print("hidden flight: final", np.round(tr[-1], 2), "truth", np.round(f["truth"][-1], 2),
          "max err", round(float(np.max(np.hypot(*(tr - f["truth"]).T))), 3))
    for args in ((12.0, -30.0, 0.4, 0.0), (12.0, -30.0, 0.4, 37.5), (-8.5, 4.0, 0.6, 200.0), (3.0, 25.0, 0.25, 315.0)):
        print("px_to_en", args, np.round(vo.px_to_en(*args), 5))
    print("median", vo.median_shift([(0, 0), (10, 10), (20, 5), (40, 40), (5, 30), (60, 2), (33, 3), (8, 8),
                                     (90, 50)],
                                    [(4.0, -2.0), (14.5, 8.0), (24.0, 3.2), (0, 0), (9.0, 28.0), (70, 70), (37.4, 1.0),
                                     (11.9, 6.1), (10, 10)], 1.0))
    print("median tol 2.5", vo.median_shift([(0, 0), (10, 10), (20, 5), (40, 40), (5, 30), (60, 2), (33, 3), (8, 8),
                                             (90, 50)],
                                            [(4.0, -2.0), (14.5, 8.0), (24.0, 3.2), (0, 0), (9.0, 28.0), (70, 70),
                                             (37.4, 1.0), (11.9, 6.1), (10, 10)], 2.5))
    print("median even", vo.median_shift([(0, 0), (1, 1), (2, 2), (3, 3)], [(1, 2), (3, 3), (5, 4), (4, 5)], 0.5))
    print("drift", vo.drift_sigma(16, 0.5, 0.25), vo.drift_sigma(np.array([0, 1, 4, 9]), 0.3, 0.1))
    print("blend", vo.blend(-4.0, 25.0, 6.0, 100.0), vo.blend(np.array([1.0, 50.0]), np.array([4.0, 4.0]),
                                                             np.array([3.0, 44.0]), np.array([12.0, 1.0])))


if __name__ == "__main__":
    main()
