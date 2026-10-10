#!/usr/bin/env python3
"""Builds the dataset of lesson 22-matching (run on the host, from anywhere):

    python3 datasets/22-matching/make_dataset.py

For each pair: patch_<name>.jpg is a piece of the satellite map (/data/map.mbtiles, zoom 18,
0.48 m per pixel), view_<name>.jpg a synthetic "drone photo" of a place inside it: cut from the
map (or from 2022 imagery for 'otherdate'), turned, rescaled, blurred, with another brightness,
noise and JPEG. truth.json holds, for each pair, the transformation view -> patch:
rotation_deg, scale (patch pixels per view pixel) and centre (patch pixel of the view centre).
points.csv: 2D points on a line + outliers for the RANSAC warm-up (truth in truth.json).
"""
import glob
import json
import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "courses", "22-matching", "files"))
import navmap  # noqa: E402

WB2022 = os.path.expanduser("~/.navera_sim/bench_2026-10-06/wb2022")
Z = 18
PATCH = 800                      # patch size in pixels (~390 m)
VIEW_W, VIEW_H = 480, 360

# name: (lat, lon of the view centre, rotation deg, scale, offset of the view centre from the
#        patch centre in patch px, source, blur, brightness gain, brightness offset)
PAIRS = {
    "city":      (35.8256, 10.6370,   30.0, 0.80, (60, -40), "map",   1.0, 1.15, 10),
    "olives":    (35.6930, 10.6348,  -60.0, 1.20, (-50, 70), "map",   1.5, 0.85, -10),
    "otherdate": (35.8690, 10.5350,  120.0, 1.50, (40, 30),  "wb2022", 1.0, 1.00, 0),
    "sea":       (35.8300, 10.7000,   45.0, 1.00, (0, 0),    "map",   1.0, 1.00, 0),
}


def wb2022_tile(z, x, y):
    return cv2.imread(os.path.join(WB2022, f"tile_{z}_{x}_{y}.jpg"))


def mosaic(cx, cy, size, reader):
    """size x size picture centred on global pixel (cx, cy) from a tile reader."""
    x0, y0 = int(round(cx - size / 2)), int(round(cy - size / 2))
    out = np.zeros((size, size, 3), np.uint8)
    for tx in range(x0 // 256, (x0 + size - 1) // 256 + 1):
        for ty in range(y0 // 256, (y0 + size - 1) // 256 + 1):
            t = reader(Z, tx, ty)
            if t is None:
                raise SystemExit(f"missing tile {Z}/{tx}/{ty}")
            ox, oy = tx * 256 - x0, ty * 256 - y0
            sx0, sy0 = max(0, -ox), max(0, -oy)
            ex, ey = min(256, size - ox), min(256, size - oy)
            out[oy + sy0:oy + ey, ox + sx0:ox + ex] = t[sy0:ey, sx0:ex]
    return out, (x0, y0)


def main():
    rng = np.random.default_rng(21)
    truth = {}
    for name, (lat, lon, rot, s, (dx, dy), src, blur, gain, off) in PAIRS.items():
        vx, vy = navmap.latlon_to_pixel(lat, lon, Z)          # global pixel of the view centre
        # the map patch, centred so that the view centre is at (PATCH/2 + dx, PATCH/2 + dy)
        patch, (px0, py0) = navmap.map_patch(*navmap.pixel_to_latlon(vx - dx, vy - dy, Z), Z, PATCH, PATCH)
        # the source picture of the view: a big square around the view centre
        big = 900
        reader = navmap.read_tile if src == "map" else wb2022_tile
        srcimg, (bx0, by0) = mosaic(vx, vy, big, reader)
        # view pixel (u, v) -> source pixel: turn by rot and scale by s around the centre.
        # H (view -> map) = rotation rot (image coordinates, y down) and scale s.
        a = math.radians(rot)
        A = np.array([[s * math.cos(a), -s * math.sin(a)], [s * math.sin(a), s * math.cos(a)]])
        c_src = np.array([vx - bx0, vy - by0])
        t = c_src - A @ np.array([VIEW_W / 2.0, VIEW_H / 2.0])
        M = np.hstack([A, t[:, None]])                         # view -> source
        view = cv2.warpAffine(srcimg, M, (VIEW_W, VIEW_H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
        if blur > 0:
            view = cv2.GaussianBlur(view, (0, 0), blur)
        view = np.clip(view.astype(np.float32) * gain + off + rng.normal(0, 4, view.shape), 0, 255).astype(np.uint8)
        cv2.imwrite(os.path.join(HERE, f"view_{name}.jpg"), view, [cv2.IMWRITE_JPEG_QUALITY, 85])
        cv2.imwrite(os.path.join(HERE, f"patch_{name}.jpg"), patch, [cv2.IMWRITE_JPEG_QUALITY, 90])
        centre = (vx - px0, vy - py0)
        truth[name] = {"rotation_deg": rot, "scale": s, "centre": [round(centre[0], 2), round(centre[1], 2)],
                       "lat": lat, "lon": lon, "zoom": Z, "patch_top_left_global_px": [px0, py0],
                       "view_source": "ESRI 2022 (Wayback)" if src == "wb2022" else "the map itself"}
    # points for the line-fitting warm-up: y = 0.6 x + 12 with noise, plus 30 % outliers
    n_in, n_out = 70, 30
    x = rng.uniform(0, 100, n_in)
    y = 0.6 * x + 12 + rng.normal(0, 1.0, n_in)
    xo = rng.uniform(0, 100, n_out)
    yo = rng.uniform(0, 100, n_out)
    pts = np.vstack([np.c_[x, y], np.c_[xo, yo]])
    pts = pts[rng.permutation(len(pts))]
    np.savetxt(os.path.join(HERE, "points.csv"), pts, delimiter=",", header="x,y", comments="", fmt="%.3f")
    truth["line"] = {"slope": 0.6, "intercept": 12.0, "inliers": n_in, "outliers": n_out}
    with open(os.path.join(HERE, "truth.json"), "w") as f:
        json.dump(truth, f, indent=1)
    print("written:", sorted(os.path.basename(p) for p in glob.glob(os.path.join(HERE, "*.*"))))


if __name__ == "__main__":
    main()
