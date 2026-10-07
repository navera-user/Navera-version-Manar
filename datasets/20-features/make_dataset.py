#!/usr/bin/env python3
"""Builds the dataset of lesson 20-features (run on the host, from anywhere):

    python3 datasets/20-features/make_dataset.py

- six 512x512 map patches at zoom 17 (~0.97 m/px, the zoom NAVERA's day vision matches against),
  one per kind of ground, read from the satellite map (MBTiles);
- two synthetic "drone views" of the city: a clear one and a blurry, dark one;
- one real aerial frame (a picture only: its flight_log GPS labels are WRONG);
- pairs.json + pair_*.jpg: synthetic drone views with the EXACT 3x3 transform H that maps a
  pixel (u, v) of the map patch terrain_<name>.jpg to the drone view (for repeatability).
"""
import json
import csv
import math
import os
import shutil
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "courses", "20-features", "files"))
import navmap  # noqa: E402

TERRAINS = [  # name, lat, lon, what it is
    ("city", 35.8256, 10.6370, "Sousse medina: roofs, narrow streets"),
    ("olives", 35.6930, 10.6348, "olive groves: rows of trees on bare soil"),
    ("farms", 35.9389, 10.4590, "farm fields with roads and hedges"),
    ("hills", 35.8000, 10.3711, "dry hills with ravines"),
    ("coast_water", 35.8552, 10.6269, "shallow sea with seagrass patches"),
    ("sea", 35.8300, 10.7000, "open sea"),
]
Z, SIZE = 17, 512
REAL = os.path.expanduser("~/navera_data/camera_pkg/camera_pkg/data/day/frame_0010.jpeg")


def drone_view(lat, lon, heading_deg, m_per_px, w=640, h=480, blur=0.0, gain=1.0, offset=0.0, seed=0,
               with_h=False, z=18):
    """A synthetic nadir photo: the zoom-z map around (lat, lon), turned by heading_deg, at m_per_px.
    with_h: also return H (3x3) mapping a pixel of the z17 512x512 patch centred on (lat, lon)
    (terrain_*.jpg) to a pixel of this photo."""
    mpp_map = navmap.m_per_px(lat, z)
    s = m_per_px / mpp_map                         # map pixels per photo pixel
    big = int(math.hypot(w, h) * s) + 8
    patch, (x18, y18) = navmap.map_patch(lat, lon, z, big, big)   # x18, y18: patch corner at zoom z
    c = (big / 2.0, big / 2.0)
    R = cv2.getRotationMatrix2D(c, heading_deg, 1.0 / s)
    R[0, 2] += w / 2.0 - c[0]
    R[1, 2] += h / 2.0 - c[1]
    img = cv2.warpAffine(patch, R, (w, h), flags=cv2.INTER_AREA)
    if blur > 0:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    rng = np.random.default_rng(seed)
    img = img.astype(np.float32) * gain + offset + rng.normal(0, 3, img.shape)
    img = np.clip(img, 0, 255).astype(np.uint8)
    if not with_h:
        return img
    _, (x17, y17) = navmap.map_patch(lat, lon, Z, SIZE, SIZE)
    # z17 patch pixel u -> global z17 (u + x17) -> global z pixel f(u + x17 + 0.5) - 0.5 -> z patch
    f = 2.0 ** (z - Z)
    T = np.array([[f, 0, f * (x17 + 0.5) - 0.5 - x18], [0, f, f * (y17 + 0.5) - 0.5 - y18], [0, 0, 1]])
    H = np.vstack([R, [0, 0, 1]]) @ T
    return img, H


PAIRS = [  # name, terrain patch, heading deg, m/px of the photo, source zoom, what changes
    # (zoom 19 = 0.24 m/px: real finer detail for the close-up photos; the map has no z19 imagery
    #  over the hills, so z18 there)
    ("city_rot35", "city", 35.0, 0.97, 19, "rotation 35 deg, same scale"),
    ("city_zoom2", "city", 0.0, 0.485, 19, "same orientation, 2x closer (scale change x2)"),
    ("city_zoom4", "city", 0.0, 0.25, 19, "same orientation, 4x closer (scale change x4)"),
    ("city_rot35_zoom", "city", 35.0, 0.6, 19, "rotation 35 deg and scale x1.6 (like drone_city.jpg)"),
    ("olives_rot35_zoom", "olives", 35.0, 0.6, 19, "olive groves, rotation 35 deg and scale x1.6"),
    ("hills_rot35_zoom", "hills", 35.0, 0.6, 18, "dry hills, rotation 35 deg and scale x1.6"),
]


def make_pairs():
    out = []
    terr = {t[0]: t for t in TERRAINS}
    for i, (name, t, hdg, mpp, zsrc, what) in enumerate(PAIRS):
        _, lat, lon, _ = terr[t]
        img, H = drone_view(lat, lon, hdg, mpp, blur=0.8, gain=1.1, offset=5, seed=10 + i, with_h=True, z=zsrc)
        fn = f"pair_{name}.jpg"
        cv2.imwrite(os.path.join(HERE, fn), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        out.append(dict(name=name, map=f"terrain_{t}.jpg", photo=fn, heading_deg=hdg,
                        scale=round(navmap.m_per_px(lat, Z) / mpp, 4), what=what,
                        H=[[round(v, 6) for v in row] for row in H.tolist()]))
    with open(os.path.join(HERE, "pairs.json"), "w") as f:
        json.dump(out, f, indent=1)


def main():
    rows = []
    for name, lat, lon, what in TERRAINS:
        img, _ = navmap.map_patch(lat, lon, Z, SIZE, SIZE)
        fn = f"terrain_{name}.jpg"
        cv2.imwrite(os.path.join(HERE, fn), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        rows.append(dict(file=fn, terrain=name, lat=lat, lon=lon, zoom=Z,
                         m_per_px=round(navmap.m_per_px(lat, Z), 3), description=what))
    with open(os.path.join(HERE, "terrain.csv"), "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    lat, lon = TERRAINS[0][1], TERRAINS[0][2]
    cv2.imwrite(os.path.join(HERE, "drone_city.jpg"),
                drone_view(lat, lon, 35.0, 0.6, blur=0.8, gain=1.1, offset=5, seed=1), [cv2.IMWRITE_JPEG_QUALITY, 88])
    cv2.imwrite(os.path.join(HERE, "drone_city_blurry_dark.jpg"),
                drone_view(lat, lon, 35.0, 0.6, blur=6.0, gain=0.25, offset=0, seed=2), [cv2.IMWRITE_JPEG_QUALITY, 88])
    make_pairs()
    if os.path.exists(REAL):
        shutil.copy(REAL, os.path.join(HERE, "real_aerial_frame.jpeg"))
    print("done:", sorted(os.listdir(HERE)))


if __name__ == "__main__":
    main()
