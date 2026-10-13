#!/usr/bin/env python3
"""Teacher only: rebuild the lesson's data figures of courses/19-calibration/assets/ from the course data.

    python3 solutions/19-calibration/make_assets.py
writes assets/coverage.png (every chessboard corner of the 36 views, with rings of constant angle from the
bench calibration) and assets/before_after_small.jpg (view f0216, fisheye and straightened 111°).
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ACADEMY, "solutions", "_navera_lite"))
import cv2  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from navera_lite import fisheye as fe  # noqa: E402
from navera_lite.camera import K_from_hfov  # noqa: E402

DS = os.path.join(ACADEMY, "datasets", "19-calibration")
ASSETS = os.path.join(ACADEMY, "courses", "19-calibration", "assets")
cal = fe.load_calibration(os.path.join(DS, "insta360_top.yaml"))
K, D = cal["K"], cal["D"]
z = np.load(os.path.join(ACADEMY, "courses", "19-calibration", "hidden", "corners.npz"))
pts = np.concatenate([c.reshape(-1, 2) for c in z["corners"]])

fig, ax = plt.subplots(figsize=(9.6, 3.6))
ax.add_patch(plt.Rectangle((0, 0), 1920, 540, fill=True, color="#f1f3f5", zorder=0))
ax.plot(pts[:, 0], pts[:, 1], ".", ms=2.2, color="#0b6e8a", label="the 1 944 corners of the 36 views")
az = np.linspace(0, 2 * np.pi, 400)
for deg, style, col, lab in ((20, ":", "#868e96", "20°"), (40, ":", "#868e96", "40°"), (50, ":", "#868e96", "50°"),
                             (55.5, "--", "#d64545", "55.5°: left and right edges of the 111° straight view"),
                             (67.4, "-", "#000000", "67.4°: the calibrated curve stops rising")):
    t = math.radians(deg)
    ring = np.stack([np.sin(t) * np.cos(az), np.sin(t) * np.sin(az), np.full_like(az, np.cos(t))], axis=1)
    p = fe.fisheye_project(ring, K, D)
    ax.plot(p[:, 0], p[:, 1], style, color=col, lw=1.6, label=lab if deg > 50 else None)
    if deg <= 50:
        ax.text(K[0, 2] + (p[:, 0].max() - K[0, 2]) + 6, K[1, 2] + 4, lab, color=col, fontsize=8)
ax.plot(K[0, 2], K[1, 2], "k+", ms=10, mew=2)
ax.set_xlim(0, 1920)
ax.set_ylim(540, 0)
ax.set_aspect("equal")
ax.set_title("Where the calibration views put corners (rings: angle from the optical axis, bench calibration)",
             fontsize=10)
ax.legend(loc="lower left", fontsize=7.5, framealpha=0.9)
ax.set_xticks([0, 480, 960, 1440, 1920])
ax.set_yticks([0, 270, 540])
fig.tight_layout()
fig.savefig(os.path.join(ASSETS, "coverage.png"), dpi=80)
print("wrote assets/coverage.png")

img = cv2.imread(os.path.join(DS, "views", "f0216.jpg"))
flat = fe.undistort(img, K, D, K_from_hfov(111.0, 1920, 540))
both = np.vstack([img, np.full((12, 1920, 3), 255, np.uint8), flat])
for y, text in ((48, "fisheye (top lens, 1920 x 540)"), (540 + 12 + 48, "straightened: ideal pinhole, 111 deg wide")):
    cv2.putText(both, text, (24, y), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 7)
    cv2.putText(both, text, (24, y), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 230, 255), 3)
small = cv2.resize(both, (960, both.shape[0] // 2), interpolation=cv2.INTER_AREA)
cv2.imwrite(os.path.join(ASSETS, "before_after_small.jpg"), small, [cv2.IMWRITE_JPEG_QUALITY, 82])
print("wrote assets/before_after_small.jpg")
