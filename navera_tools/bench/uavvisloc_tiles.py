#!/usr/bin/env python3
"""UAV-VisLoc satellite map -> NAVERA map tiles (z17 web-mercator JPEG, tile_17_x_y.jpg).

    python3 navera_tools/bench/uavvisloc_tiles.py <flight dir, e.g. .../data/03> <out images dir>

The map's lat/lon corners come from satellite_coordinates_range.csv (one level above the
flight dir); the .tif is treated as linear in lat/lon (a few km: < 0.1 % off web-mercator).
"""
import csv
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
Z = 17
flight, out = sys.argv[1].rstrip("/"), sys.argv[2]
idx = os.path.basename(flight)
rng = next(r for r in csv.DictReader(open(os.path.join(os.path.dirname(flight), "satellite_ coordinates_range.csv")))
           if r["mapname"] == f"{idx}.tif")
lat0, lon0, lat1, lon1 = (float(rng[k]) for k in ("LT_lat_map", "LT_lon_map", "RB_lat_map", "RB_lon_map"))
im = Image.open(os.path.join(flight, f"satellite{idx}.tif")).convert("RGB")
W, H = im.size
print("tif", W, H, "corners", lat0, lon0, lat1, lon1, flush=True)
sc = 0.25
small = np.asarray(im.resize((int(W * sc), int(H * sc)), Image.LANCZOS))     # 0.25 -> ~1 m/px
del im
h, w = small.shape[:2]


def tile_xy(lat, lon):
    n = 2 ** Z
    return (lon + 180.0) / 360.0 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n


def tile_latlon(fx, fy):
    n = 2 ** Z
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * fy / n)))), fx / n * 360.0 - 180.0


x0, y0 = tile_xy(lat0, lon0)
x1, y1 = tile_xy(lat1, lon1)
os.makedirs(out, exist_ok=True)
n = 0
for ty in range(int(y0) + 1, int(y1)):
    for tx in range(int(x0) + 1, int(x1)):
        gy, gx = np.mgrid[0:256, 0:256]
        lat = np.empty((256, 256))
        lon = np.empty((256, 256))
        for r in range(256):
            la, _ = tile_latlon(tx, ty + (r + 0.5) / 256)
            lat[r, :] = la
        for c in range(256):
            _, lo = tile_latlon(tx + (c + 0.5) / 256, ty)
            lon[:, c] = lo
        mx = ((lon - lon0) / (lon1 - lon0) * w).astype(np.float32)
        my = ((lat0 - lat) / (lat0 - lat1) * h).astype(np.float32)
        t = cv2.remap(small, mx, my, cv2.INTER_AREA)
        cv2.imwrite(os.path.join(out, f"tile_{Z}_{tx}_{ty}.jpg"), cv2.cvtColor(t, cv2.COLOR_RGB2BGR))
        n += 1
print("tiles", n, "x", int(x0) + 1, "-", int(x1) - 1, "y", int(y0) + 1, "-", int(y1) - 1)
