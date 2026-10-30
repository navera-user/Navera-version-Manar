#!/usr/bin/env python3
"""Mission 08: the data figures of lesson.md (teacher only).

    PYTHONPATH= python3 solutions/08-images/make_figures.py

Writes courses/08-images/assets/: cold_open.jpg, like_map_steps.jpg, thermal_wrap.jpg, and prints the numbers of
the lesson's §7 worked example. Uses the course reference (solutions/_navera_lite) and render_view.
"""
import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.realpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "datasets", "_map"))
sys.path.insert(0, os.path.join(REPO, "solutions", "_navera_lite"))
from render_view import render_view  # noqa: E402
from navera_lite.image import affine_matrix, like_map, normalise, to_gray  # noqa: E402

A = os.path.join(REPO, "courses", "08-images", "assets")
D = os.path.join(REPO, "datasets", "08-images")
OSM = "Map data (c) OpenStreetMap contributors"
FONT = cv2.FONT_HERSHEY_SIMPLEX


def caption(img, text, h=26, scale=0.5):
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    strip = np.full((h, img.shape[1], 3), 255, np.uint8)
    cv2.putText(strip, text, (6, h - 9), FONT, scale, (40, 40, 40), 1, cv2.LINE_AA)
    return np.vstack([img, strip])


def row(*imgs, gap=10):
    hmax = max(i.shape[0] for i in imgs)
    out = []
    for i in imgs:
        out += [np.vstack([i, np.full((hmax - i.shape[0], i.shape[1], 3), 255, np.uint8)]),
                np.full((hmax, gap, 3), 255, np.uint8)]
    return np.hstack(out[:-1])


def north_arrow(img, angle_deg, at=(30, 50), length=34, colour=(40, 40, 220), thick=3):
    """Draw an arrow pointing to north, which is angle_deg COUNTER-clockwise from the image top."""
    t = math.radians(angle_deg)
    x0, y0 = at
    x1, y1 = x0 - length * math.sin(t), y0 - length * math.cos(t)
    cv2.arrowedLine(img, (int(x0), int(y0)), (int(round(x1)), int(round(y1))), colour, thick, cv2.LINE_AA, tipLength=0.3)
    lx, ly = x0 - (length + 22) * math.sin(t), y0 - (length + 22) * math.cos(t)
    scale = 0.6 * thick / 3
    cv2.putText(img, "N", (int(round(lx)) - int(8 * scale / 0.6), int(round(ly)) + int(8 * scale / 0.6)), FONT, scale,
                colour, thick, cv2.LINE_AA)


def main():
    os.makedirs(A, exist_ok=True)
    # 1. cold open: the lab's map patch and raw drone photo, side by side
    mp = cv2.imread(os.path.join(D, "map_patch.png"))
    ph = cv2.imread(os.path.join(D, "drone_photo.jpg"))
    left = caption(cv2.resize(mp, (360, 360), interpolation=cv2.INTER_AREA), "the map: north up, 0.97 m per pixel")
    right = caption(cv2.resize(ph, (480, 360), interpolation=cv2.INTER_AREA), "simulated drone photo: 0.60 m per pixel")
    cv2.imwrite(os.path.join(A, "cold_open.jpg"), caption(row(left, right), OSM, scale=0.45),
                [cv2.IMWRITE_JPEG_QUALITY, 85])

    # 2. the §7 worked example: a photo of the Sousse medina, heading 120°, 0.45 m/px
    lat, lon, hd, gsd, gmap = 35.8277, 10.6388, 120.0, 0.45, 0.968
    photo = render_view(lat, lon, hd, ground_size_m=640 * gsd, out_px=(640, 480), style="pseudo", seed=4,
                        effects={"blur": 1.0, "noise": 4.0, "gamma": 1.3, "brightness": 0.75, "vignette": 0.25})
    ref = render_view(lat, lon, 0.0, ground_size_m=420 * gmap, out_px=420, style="pseudo", seed=0)
    g = normalise(to_gray(photo))
    ready = like_map(photo, hd, gsd, gmap)
    s = gsd / gmap
    side = int(round(math.hypot(640, 480) * s))
    M = affine_matrix(-hd, s, (319.5, 239.5))
    print(f"§7 worked example: s = {s:.4f}, side = {side}, M (before the shift) =\n{np.round(M, 4)}")
    M[0, 2] += (side - 1) / 2 - 319.5
    M[1, 2] += (side - 1) / 2 - 239.5
    print(f"after the shift:\n{np.round(M, 4)}\n centre check: {M @ np.array([319.5, 239.5, 1.0])}")
    p1 = photo.copy()
    north_arrow(p1, hd, at=(170, 150), length=80, thick=5)
    p1 = caption(cv2.resize(p1, (320, 240), interpolation=cv2.INTER_AREA), "1. the photo, top = heading 120")
    p2 = caption(cv2.resize(g, (320, 240), interpolation=cv2.INTER_AREA), "2. grey + normalise")
    r3 = cv2.cvtColor(cv2.resize(ready, (240, 240), interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
    north_arrow(r3, 0.0, at=(28, 85))
    p3 = caption(r3, "3. one warp: north up")
    off = (420 - side) // 2
    crop = normalise(to_gray(ref))[off:off + side, off:off + side]
    p4 = caption(cv2.resize(crop, (240, 240), interpolation=cv2.INTER_AREA), "4. the map, same place")
    cv2.imwrite(os.path.join(A, "like_map_steps.jpg"), caption(row(p1, p2, p3, p4), OSM, scale=0.45),
                [cv2.IMWRITE_JPEG_QUALITY, 85])

    # 3. the thermal frame: naive cast vs normalise (shown after lab Step 2)
    t = cv2.imread(os.path.join(D, "thermal16.png"), cv2.IMREAD_UNCHANGED)
    a = caption(cv2.resize(t.astype(np.uint8), (384, 307), interpolation=cv2.INTER_NEAREST), "t.astype(np.uint8)")
    b = caption(cv2.resize(normalise(t), (384, 307), interpolation=cv2.INTER_AREA), "normalise(t)")
    cv2.imwrite(os.path.join(A, "thermal_wrap.jpg"), caption(row(a, b), "synthetic thermal-like frame; " + OSM,
                                                             scale=0.45), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print("written", sorted(os.listdir(A)))


if __name__ == "__main__":
    main()
