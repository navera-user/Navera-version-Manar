#!/usr/bin/env python3
"""Mission 21 raster assets (teacher only): assets/terrains.jpg from datasets/21-features (run make_dataset.py first)."""
import os
import cv2
import numpy as np

REPO = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
D = os.path.join(REPO, "datasets", "21-features")
names = ["city", "olives", "fields", "saltpans", "coast", "sea"]
tiles = []
for n in names:
    im = cv2.resize(cv2.imread(os.path.join(D, f"terrain_{n}.png")), (220, 220), interpolation=cv2.INTER_AREA)
    cv2.putText(im, n, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(im, n, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1, cv2.LINE_AA)
    tiles.append(im)
gap = np.full((220, 6, 3), 255, np.uint8)
row = lambda t: np.hstack([t[0], gap, t[1], gap, t[2]])          # noqa: E731
img = np.vstack([row(tiles[:3]), np.full((6, 672, 3), 255, np.uint8), row(tiles[3:])])
text = "(c) OpenStreetMap contributors"
cv2.rectangle(img, (img.shape[1] - 200, img.shape[0] - 18), (img.shape[1], img.shape[0]), (255, 255, 255), -1)
cv2.putText(img, text, (img.shape[1] - 196, img.shape[0] - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (60, 60, 60), 1, cv2.LINE_AA)
cv2.imwrite(os.path.join(REPO, "courses", "21-features", "assets", "terrains.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
