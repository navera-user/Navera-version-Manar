#!/usr/bin/env python3
"""Build the synthetic flight of lesson 24 (visual odometry) from the satellite map.

A drone flies an arc of ~1.6 km over Sousse (town, olive groves, sand) at 114 m, its
camera looking straight down (70 deg field of view, 320 x 240 px -> 0.50 m per pixel).
Every 20 m it takes a photo. To be realistic:
  * the camera's "up" is turned 2 deg from north (an IMU heading bias) plus a small
    random wobble per frame (0.3 deg) — the student does not know it;
  * the barometer says 110.8 m instead of 114.25 m (3 % low) — the student's
    meters-per-pixel will be 3 % too small;
  * each photo gets its own brightness/contrast, a little blur, noise and JPEG.
Map fixes (as lesson 23 would give) every 10 frames: the truth + about 4 m of noise.

Run on the host (reads ~/navera_data_map.mbtiles):  python3 make_dataset.py
"""
import csv
import json
import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)            # navmap.py (the map helpers of lesson 7) sits next to this script
from navmap import map_patch, m_per_px, pixel_to_latlon, latlon_to_pixel  # noqa: E402

Z = 18
W, H = 320, 240
HFOV = 70.0
ALT_TRUE = 114.25                     # m above ground: 2*114.25*tan(35 deg)/320 = 0.500 m/px
ALT_BARO = 110.8                      # what the barometer says (3 % low)
MPP = 2 * ALT_TRUE * math.tan(math.radians(HFOV / 2)) / W
HEADING_BIAS = 2.0                    # deg, unknown to the student
HEADING_JITTER = 0.3                  # deg per frame
N_FRAMES = 80
STEP_M = 20.0
FIX_EVERY = 10
FIX_NOISE_M = 4.0
CENTRE = (35.815, 10.605)             # middle of the area
rng = np.random.default_rng(23)


def route():
    """Frame centres (east, north) in m from the first frame, and the direction of travel."""
    R = 650.0                                         # an arc of a circle of 650 m radius
    a0 = math.radians(220.0)                          # start south-west of the circle centre
    da = STEP_M / R
    pts = []
    for i in range(N_FRAMES):
        a = a0 - i * da                               # clockwise
        pts.append((R * math.cos(a), R * math.sin(a), a))
    e0, n0, _ = pts[0]
    out = []
    for e, n, a in pts:
        # direction of travel when going clockwise: tangent (sin a, -cos a)
        hdg = math.degrees(math.atan2(math.sin(a), -math.cos(a))) % 360.0
        out.append((e - e0, n - n0, hdg))
    return out


def main():
    os.makedirs(os.path.join(HERE, "frames"), exist_ok=True)
    pts = route()
    # the circle centre sits at CENTRE; the first frame is R*(cos a0, sin a0) from it
    R, a0 = 650.0, math.radians(220.0)
    mpp_map = m_per_px(CENTRE[0], Z)
    cx, cy = latlon_to_pixel(CENTRE[0], CENTRE[1], Z)
    sx, sy = cx + R * math.cos(a0) / mpp_map, cy - R * math.sin(a0) / mpp_map   # start, global px
    big, (x0, y0) = map_patch(CENTRE[0], CENTRE[1], Z, 3400, 3400)
    rows, fixes = [], []
    uu, vv = np.meshgrid(np.arange(W, dtype=np.float32) - (W - 1) / 2.0,
                         np.arange(H, dtype=np.float32) - (H - 1) / 2.0)
    for i, (e, n, hdg) in enumerate(pts):
        th = math.radians(HEADING_BIAS + rng.normal(0, HEADING_JITTER))
        up = (math.sin(th), math.cos(th))             # where the image top points (east, north)
        right = (math.cos(th), -math.sin(th))
        ge = (uu * right[0] - vv * up[0]) * MPP + e   # ground east/north of every frame pixel
        gn = (uu * right[1] - vv * up[1]) * MPP + n
        mapx = (sx + ge / mpp_map - x0).astype(np.float32)
        mapy = (sy - gn / mpp_map - y0).astype(np.float32)
        img = cv2.remap(big, mapx, mapy, cv2.INTER_LINEAR)
        img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.5, 1.1))
        img = img.astype(np.float32) * rng.uniform(0.85, 1.15) + rng.uniform(-12, 12)
        img += rng.normal(0, 4.0, img.shape)
        img = np.clip(img, 0, 255).astype(np.uint8)
        name = f"frame_{i:03d}.jpg"
        cv2.imwrite(os.path.join(HERE, "frames", name), img, [cv2.IMWRITE_JPEG_QUALITY, 88])
        lat, lon = pixel_to_latlon(sx + e / mpp_map, sy - n / mpp_map, Z)
        rows.append([i, name, round(e, 2), round(n, 2), round(lat, 7), round(lon, 7), round(hdg, 1)])
        if i > 0 and i % FIX_EVERY == 0:
            fixes.append([i, round(e + rng.normal(0, FIX_NOISE_M), 2), round(n + rng.normal(0, FIX_NOISE_M), 2)])
    with open(os.path.join(HERE, "truth.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "file", "east_m", "north_m", "lat", "lon", "heading_deg"])
        w.writerows(rows)
    with open(os.path.join(HERE, "map_fixes.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "east_m", "north_m"])
        w.writerows(fixes)
    info = {"frames": N_FRAMES, "width_px": W, "height_px": H, "camera_hfov_deg": HFOV,
            "altitude_m": ALT_BARO, "time_between_frames_s": 1.0,
            "start_lat": rows[0][4], "start_lon": rows[0][5],
            "note": "altitude_m is what the barometer says. Images are 'north-up' according to the IMU."}
    with open(os.path.join(HERE, "info.json"), "w") as f:
        json.dump(info, f, indent=1)
    print(f"{N_FRAMES} frames, {STEP_M * (N_FRAMES - 1):.0f} m flown, true {MPP:.4f} m/px, "
          f"{len(fixes)} map fixes")


if __name__ == "__main__":
    main()
