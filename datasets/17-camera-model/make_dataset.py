#!/usr/bin/env python3
"""Regenerate the lesson 17 dataset: two synthetic "drone photos" cut from the satellite map.

Each photo is what an ideal, distortion-free camera looking straight down would see:
960 px wide x 540 px high, horizontal field of view 90 deg, at a known height above the
ground. A 12 m x 12 m orange landing pad (synthetic, painted on the picture) gives the
students an object of known size to measure. Truth is in truth.json.

    python3 datasets/17-camera-model/make_dataset.py [--mbtiles ~/navera_data_map.mbtiles]
"""
import argparse
import io
import json
import math
import os
import sqlite3

import cv2
import numpy as np

EQUATOR_M = 40075016.7
W, H, HFOV = 960, 540, 90.0
PAD_M = 12.0
ZOOM = 19
PHOTOS = [  # name, lat, lon (centre of the photo), height above ground (m)
    ("photo_A.png", 35.8262, 10.6395, 120.0),
    ("photo_B.png", 35.8190, 10.6310, 210.0),
]


def tile_px(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(r)) / math.pi) / 2.0 * n
    return x * 256.0, y * 256.0


def map_mpp(lat, z):
    return EQUATOR_M * math.cos(math.radians(lat)) / 2 ** z / 256.0


def mosaic(db, z, x0, y0, x1, y1):
    """Global-pixel rectangle [x0,x1) x [y0,y1) of zoom z, stitched from the tiles."""
    tx0, ty0, tx1, ty1 = int(x0 // 256), int(y0 // 256), int(x1 // 256), int(y1 // 256)
    big = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 3), np.uint8)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            row = db.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                             (z, tx, (2 ** z - 1) - ty)).fetchone()
            if row is None:
                raise SystemExit(f"tile {z}/{tx}/{ty} missing")
            t = cv2.imdecode(np.frombuffer(row[0], np.uint8), cv2.IMREAD_COLOR)
            big[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = t
    ox, oy = int(x0 - tx0 * 256), int(y0 - ty0 * 256)
    return big[oy:oy + int(y1 - y0), ox:ox + int(x1 - x0)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mbtiles", default=os.path.expanduser("~/navera_data_map.mbtiles"))
    a = ap.parse_args()
    out_dir = os.path.dirname(os.path.abspath(__file__))
    db = sqlite3.connect("file:" + os.path.realpath(a.mbtiles) + "?mode=ro", uri=True)
    truth = {"camera": {"width_px": W, "height_px": H, "hfov_deg": HFOV}, "pad_size_m": PAD_M, "photos": {}}
    for name, lat, lon, h in PHOTOS:
        foot_w = 2.0 * h * math.tan(math.radians(HFOV) / 2.0)     # ground width (m)
        mpp = foot_w / W                                          # photo metres per pixel
        k = mpp / map_mpp(lat, ZOOM)                              # map pixels per photo pixel
        cx, cy = tile_px(lat, lon, ZOOM)
        mw, mh = W * k, H * k
        crop = mosaic(db, ZOOM, cx - mw / 2, cy - mh / 2, cx + mw / 2, cy + mh / 2)
        img = cv2.resize(crop, (W, H), interpolation=cv2.INTER_AREA if k > 1 else cv2.INTER_LINEAR)
        pad_px = PAD_M / mpp
        # the pad sits a little off-centre, on the ground
        px, py = W * 0.62, H * 0.40
        x0, y0 = int(round(px - pad_px / 2)), int(round(py - pad_px / 2))
        s = int(round(pad_px))
        cv2.rectangle(img, (x0, y0), (x0 + s - 1, y0 + s - 1), (0, 140, 255), -1)
        t = max(1, s // 8)                                        # a white "H" in the middle
        cv2.rectangle(img, (x0 + s // 4, y0 + s // 4), (x0 + s // 4 + t, y0 + 3 * s // 4), (255, 255, 255), -1)
        cv2.rectangle(img, (x0 + 3 * s // 4 - t, y0 + s // 4), (x0 + 3 * s // 4, y0 + 3 * s // 4), (255, 255, 255), -1)
        cv2.rectangle(img, (x0 + s // 4, y0 + s // 2 - t // 2), (x0 + 3 * s // 4, y0 + s // 2 + t // 2), (255, 255, 255), -1)
        cv2.imwrite(os.path.join(out_dir, name), img)
        truth["photos"][name] = {"lat": lat, "lon": lon, "height_m": h, "m_per_px": round(mpp, 5),
                                 "pad_px": s}
        print(f"{name}: height {h} m, {mpp:.3f} m/px, pad {s} px")
    with open(os.path.join(out_dir, "truth.json"), "w") as f:
        json.dump(truth, f, indent=1)


if __name__ == "__main__":
    main()
