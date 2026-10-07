#!/usr/bin/env python3
"""Builds the lesson 08 dataset from NAVERA's map (opened read-only):

  map_patch.png    512 x 512, north-up, zoom 17 (~0.968 m/px), centred on Port El Kantaoui marina
  drone_photo.jpg  640 x 480 synthetic "drone photo" of the same centre, made from zoom 18 tiles:
                   0.6 m per pixel, image top pointing to heading 35° (clockwise from north),
                   darker, less contrast, a warmer colour, slightly blurred, with sensor noise
  info.json        the exact parameters (the "ground truth")

    python3 make_dataset.py [path/to/map.mbtiles]
"""
import json
import math
import os
import sqlite3
import sys
from urllib.parse import quote

import cv2
import numpy as np

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/navera_data_map.mbtiles")
OUT = os.path.dirname(os.path.abspath(__file__))
LAT, LON = 35.8942, 10.5979              # Port El Kantaoui marina
HEADING_DEG = 35.0
PHOTO_MPP = 0.6
PHOTO_W, PHOTO_H = 640, 480
EQUATOR_M = 40075016.7

db = sqlite3.connect("file:" + quote(os.path.realpath(SRC)) + "?mode=ro", uri=True)


def tile_xy(lat, lon, z):
    n = 2 ** z
    r = math.radians(lat)
    return (lon + 180.0) / 360.0 * n, (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n


def mosaic(z, radius):
    """(2 radius + 1)^2 tiles around the point; returns (picture, px, py of the point)."""
    fx, fy = tile_xy(LAT, LON, z)
    x0, y0 = int(fx) - radius, int(fy) - radius
    k = 2 * radius + 1
    img = np.zeros((256 * k, 256 * k, 3), np.uint8)
    for j in range(k):
        for i in range(k):
            row = db.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                             (z, x0 + i, 2 ** z - 1 - (y0 + j))).fetchone()
            if row is None:
                raise SystemExit(f"missing tile {z}/{x0 + i}/{y0 + j}")
            img[256 * j:256 * (j + 1), 256 * i:256 * (i + 1)] = cv2.imdecode(np.frombuffer(row[0], np.uint8), 1)
    return img, (fx - x0) * 256.0, (fy - y0) * 256.0


# --- the map patch: zoom 17, 512 x 512 around the point
m17, px, py = mosaic(17, 2)
M = np.float32([[1, 0, 256 - px], [0, 1, 256 - py]])               # sub-pixel shift: point at (256, 256)
patch = cv2.warpAffine(m17, M, (512, 512), flags=cv2.INTER_LINEAR)
map_mpp = EQUATOR_M * math.cos(math.radians(LAT)) / 2 ** 17 / 256
cv2.imwrite(os.path.join(OUT, "map_patch.png"), patch)

# --- the drone photo: sample zoom 18 with the camera's geometry
m18, cx18, cy18 = mosaic(18, 3)
mpp18 = map_mpp / 2
h = math.radians(HEADING_DEG)
u, v = np.meshgrid(np.arange(PHOTO_W, dtype=np.float32), np.arange(PHOTO_H, dtype=np.float32))
right = (u - (PHOTO_W - 1) / 2.0) * PHOTO_MPP                     # meters to the right of the image centre
fwd = ((PHOTO_H - 1) / 2.0 - v) * PHOTO_MPP                       # meters towards the image top
east = fwd * math.sin(h) + right * math.cos(h)
north = fwd * math.cos(h) - right * math.sin(h)
map_x = (cx18 + east / mpp18).astype(np.float32)
map_y = (cy18 - north / mpp18).astype(np.float32)
photo = cv2.remap(m18, map_x, map_y, cv2.INTER_LINEAR).astype(np.float32)
photo = cv2.GaussianBlur(photo, (0, 0), 1.0)                      # a slightly soft lens
photo = photo * 0.55 + 18.0                                       # darker, less contrast
photo *= np.array([0.85, 1.0, 1.12], np.float32)                  # warmer light (B, G, R)
rng = np.random.default_rng(8)
photo += rng.normal(0.0, 4.0, photo.shape).astype(np.float32)     # sensor noise
photo = np.clip(photo, 0, 255).astype(np.uint8)
cv2.imwrite(os.path.join(OUT, "drone_photo.jpg"), photo, [cv2.IMWRITE_JPEG_QUALITY, 92])

info = {"place": "Port El Kantaoui marina", "lat": LAT, "lon": LON,
        "photo": {"file": "drone_photo.jpg", "width": PHOTO_W, "height": PHOTO_H, "heading_deg": HEADING_DEG,
                  "m_per_px": PHOTO_MPP, "centre": "the photo centre is exactly (lat, lon)"},
        "map": {"file": "map_patch.png", "zoom": 17, "size": 512, "m_per_px": round(map_mpp, 6),
                "centre": "pixel (256, 256) is exactly (lat, lon); north is up"},
        "made_by": "make_dataset.py (synthetic photo from zoom-18 tiles of /data/map.mbtiles)"}
with open(os.path.join(OUT, "info.json"), "w") as f:
    json.dump(info, f, indent=1)
print("done:", {n: os.path.getsize(os.path.join(OUT, n)) for n in ("map_patch.png", "drone_photo.jpg", "info.json")})
