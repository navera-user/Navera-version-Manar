#!/usr/bin/env python3
"""Regenerate the lesson 18 dataset: three synthetic "drone photos" cut from NAVERA's
satellite map of Sousse, Tunisia (the only map NAVERA has; the lab says so).

Every photo is what an ideal, distortion-free pinhole camera would see over FLAT ground:
960 px wide x 540 px high, horizontal field of view 90 deg (f = 480 px, principal point at
the image centre). A 12 m x 12 m orange landing pad with a white "H" is painted ON THE
GROUND (so it is foreshortened correctly in the tilted photo). Ground truth: truth.json.

  photo_A.png  straight down, 120 m
  photo_B.png  straight down, 210 m
  photo_T.png  tilted: 150 m, heading 30 deg, pitch -12 deg (nose down), roll +4 deg

Conventions (the same as the lab's camera_math.py and NAVERA's camera_model.py):
world ENU (x east, y north, z up), origin on the ground under the drone; camera OpenCV
(x right, y down, z optical axis); R_wc maps camera vectors to world vectors.

    python3 datasets/18-camera-model/make_dataset.py [--mbtiles ~/navera_data_map.mbtiles]
"""
import argparse
import json
import math
import os
import sqlite3

import cv2
import numpy as np

EQUATOR_M = 40075016.7
W, H, HFOV = 960, 540, 90.0
F = (W / 2.0) / math.tan(math.radians(HFOV) / 2.0)
K = np.array([[F, 0, W / 2.0], [0, F, H / 2.0], [0, 0, 1.0]])
PAD_M = 12.0
ZOOM = 19
R_BODY_NADIR_CAM = np.array([[0.0, -1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])

# name, lat, lon (point under the drone), height (m), heading, pitch, roll (deg), pad centre (E, N) m
PHOTOS = [
    ("photo_A.png", 35.8262, 10.6395, 120.0, 0.0, 0.0, 0.0, None),
    ("photo_B.png", 35.8190, 10.6310, 210.0, 0.0, 0.0, 0.0, None),
    ("photo_T.png", 35.8231, 10.6352, 150.0, 30.0, -12.0, 4.0, (38.0, -92.0)),
]


def camera_rotation(heading_deg, pitch_deg, roll_deg):
    """R_wc of a camera fixed under the body, looking down: heading clockwise from north,
    pitch positive nose UP, roll positive right wing DOWN (NAVERA's body_rpy_enu)."""
    y, p, r = math.radians(90.0 - heading_deg), math.radians(-pitch_deg), math.radians(roll_deg)
    Rz = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
    Ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    return Rz @ Ry @ Rx @ R_BODY_NADIR_CAM


def tile_px(lat, lon, z):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
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
    return big, tx0 * 256, ty0 * 256


def render(db, lat, lon, h, heading, pitch, roll, pad_en):
    """Ray-trace every pixel to the flat ground, read the map there (bilinear)."""
    R = camera_rotation(heading, pitch, roll)
    C = np.array([0.0, 0.0, h])
    u, v = np.meshgrid(np.arange(W) + 0.0, np.arange(H) + 0.0)
    rays = np.stack([u.ravel(), v.ravel(), np.ones(u.size)])
    d = R @ np.linalg.inv(K) @ rays                       # world directions, 3 x N
    if np.any(d[2] >= -1e-6):
        raise SystemExit("some pixels see the sky: reduce the tilt")
    lam = -C[2] / d[2]
    E, N = C[0] + lam * d[0], C[1] + lam * d[1]
    mpp = map_mpp(lat, ZOOM)
    cx, cy = tile_px(lat, lon, ZOOM)
    mx, my = cx + E / mpp, cy - N / mpp                   # Web Mercator is conformal: locally E->x, N->-y
    big, ox, oy = mosaic(db, ZOOM, mx.min() - 2, my.min() - 2, mx.max() + 2, my.max() + 2)
    img = cv2.remap(big, (mx - ox).reshape(H, W).astype(np.float32), (my - oy).reshape(H, W).astype(np.float32),
                    cv2.INTER_AREA if h > 200 else cv2.INTER_LINEAR)
    # supersampled map for the high photo (map pixel 0.24 m < photo pixel 0.44 m): blur a little
    if lam.mean() * 1.0 / F > 1.5 * mpp:
        img = cv2.GaussianBlur(img, (0, 0), 0.6)
    if pad_en is None:                                    # nadir photos: pad a little off-centre
        pad_en = tuple(np.array([E.reshape(H, W)[int(H * 0.40), int(W * 0.62)],
                                 N.reshape(H, W)[int(H * 0.40), int(W * 0.62)]]).round(2))
    # the pad, on the ground (axis-aligned with east/north), with a white H
    a, b = (E - pad_en[0]).reshape(H, W), (N - pad_en[1]).reshape(H, W)
    half = PAD_M / 2.0
    inside = (np.abs(a) <= half) & (np.abs(b) <= half)
    t = PAD_M / 8.0
    bar_l = (np.abs(a + PAD_M / 4.0 - t / 2) <= t / 2) & (np.abs(b) <= PAD_M / 4.0)
    bar_r = (np.abs(a - PAD_M / 4.0 + t / 2) <= t / 2) & (np.abs(b) <= PAD_M / 4.0)
    bar_m = (np.abs(a) <= PAD_M / 4.0) & (np.abs(b) <= t / 2)
    img[inside] = (0, 140, 255)
    img[inside & (bar_l | bar_r | bar_m)] = (255, 255, 255)
    return img, pad_en, R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mbtiles", default=os.path.expanduser("~/navera_data_map.mbtiles"))
    a = ap.parse_args()
    out_dir = os.path.dirname(os.path.abspath(__file__))
    db = sqlite3.connect("file:" + os.path.realpath(a.mbtiles) + "?mode=ro", uri=True)
    truth = {"camera": {"width_px": W, "height_px": H, "hfov_deg": HFOV, "f_px": F},
             "pad_size_m": PAD_M, "map": "NAVERA satellite map, Sousse (Tunisia), zoom 19",
             "conventions": "ENU world, origin on the ground under the drone; heading cw from north, "
                            "pitch + nose up, roll + right wing down", "photos": {}}
    for name, lat, lon, h, hd, p, r, pad in PHOTOS:
        img, pad_en, R = render(db, lat, lon, h, hd, p, r, pad)
        cv2.imwrite(os.path.join(out_dir, name), img)
        x = R.T @ (np.array([pad_en[0], pad_en[1], 0.0]) - np.array([0, 0, h]))
        uv = (K @ x)[:2] / (K @ x)[2]
        truth["photos"][name] = {"lat": lat, "lon": lon, "height_m": h, "heading_deg": hd, "pitch_deg": p,
                                 "roll_deg": r, "pad_centre_en_m": [float(pad_en[0]), float(pad_en[1])],
                                 "pad_centre_px": [round(float(uv[0]), 1), round(float(uv[1]), 1)],
                                 "nadir_m_per_px": round(h / F, 5)}
        print(f"{name}: h {h} m, pad at E {pad_en[0]:.1f} N {pad_en[1]:.1f} m, pixel ({uv[0]:.0f}, {uv[1]:.0f})")
    with open(os.path.join(out_dir, "truth.json"), "w") as f:
        json.dump(truth, f, indent=1)


if __name__ == "__main__":
    main()
