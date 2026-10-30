#!/usr/bin/env python3
"""Mission 18 (teacher only) — regenerate datasets/18-camera-model/: three synthetic drone photos of
Sousse (Tunisia), rendered from the course's OpenStreetMap map (datasets/_map/render_view.py,
"pseudo-satellite" style), with a 12 m × 12 m orange landing pad painted on the ground.

Every photo is what an ideal pinhole camera (960 × 540 px, HFOV 90°, f = 480 px, principal point
(480, 270)) sees over FLAT ground: each pixel's ray is traced to the plane z = 0 (the same model the
lesson teaches), the ground there is read from a north-up orthophoto, and the pad is painted
analytically (hard edges, axis-aligned with east/north). Pixel (u, v) = column u, row v, at integer
coordinates (pixel centres).

  photo_A.png   straight down, nose north, HEIGHT_A
  photo_B.png   straight down, nose north, HEIGHT_B
  photo_T.png   tilted: 170 m, heading 40°, pitch −14° (nose down), roll +5° — pad at PAD_T_EN

The truth (heights, pad positions) goes to solutions/18-camera-model/truth.json — NEVER into
datasets/ (students can read it). datasets/18-camera-model/ gets the PNGs and a neutral README.

    python3 solutions/18-camera-model/make_dataset.py         # ~1–2 min on the Jetson
"""
import json
import math
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ACADEMY = os.path.realpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ACADEMY, "datasets", "18-camera-model")
sys.path.insert(0, os.path.join(ACADEMY, "datasets", "_map"))
from render_view import render_view  # noqa: E402

W, H, HFOV = 960, 540, 90.0
F = (W / 2.0) / math.tan(math.radians(HFOV) / 2.0)
K = np.array([[F, 0, W / 2.0], [0, F, H / 2.0], [0, 0, 1.0]])
PAD_M = 12.0
R_BODY_NADIR_CAM = np.array([[0.0, -1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])
HEIGHT_A, HEIGHT_B = 135.0, 260.0
PAD_T_EN = (-18.0, -66.0)

# name, lat, lon (point under the drone), height (m), heading, pitch (nose up +), roll (right wing down +),
# pad centre (E, N) m from the point under the drone
PHOTOS = [
    ("photo_A.png", 35.8262, 10.6395, HEIGHT_A, 0.0, 0.0, 0.0, (21.0, 13.0)),
    ("photo_B.png", 35.8190, 10.6310, HEIGHT_B, 0.0, 0.0, 0.0, (-41.0, 29.0)),
    ("photo_T.png", 35.8231, 10.6352, 170.0, 40.0, -14.0, 5.0, PAD_T_EN),
]


def camera_rotation_hpr(heading_deg, pitch_deg, roll_deg):
    """R_wc: Rz(90° − heading) · Ry(−pitch) · Rx(roll) · R_BODY_NADIR_CAM (human angles, pitch + nose up)."""
    y, p, r = math.radians(90.0 - heading_deg), math.radians(-pitch_deg), math.radians(roll_deg)
    Rz = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
    Ry = np.array([[math.cos(p), 0, math.sin(p)], [0, 1, 0], [-math.sin(p), 0, math.cos(p)]])
    Rx = np.array([[1, 0, 0], [0, math.cos(r), -math.sin(r)], [0, math.sin(r), math.cos(r)]])
    return Rz @ Ry @ Rx @ R_BODY_NADIR_CAM


def ground_of_pixels(R, h):
    """E, N (H × W arrays) of every pixel's ground point, for a camera at (0, 0, h)."""
    u, v = np.meshgrid(np.arange(W, dtype=float), np.arange(H, dtype=float))
    rays = np.stack([u.ravel(), v.ravel(), np.ones(u.size)])
    d = R @ np.linalg.inv(K) @ rays
    if np.any(d[2] >= -1e-6):
        raise SystemExit("some pixels see the sky: reduce the tilt")
    lam = -h / d[2]
    return (lam * d[0]).reshape(H, W), (lam * d[1]).reshape(H, W), (lam / F).reshape(H, W)


def offset_latlon(lat, lon, e, n):
    """Flat-Earth offset (fine over a few hundred metres)."""
    return lat + math.degrees(n / 6371000.0), lon + math.degrees(e / (6371000.0 * math.cos(math.radians(lat))))


def render(lat, lon, h, heading, pitch, roll, pad_en):
    R = camera_rotation_hpr(heading, pitch, roll)
    E, N, slant_gsd = ground_of_pixels(R, h)
    # north-up orthophoto covering the footprint, ~2.5× finer than the finest photo pixel
    e0, e1, n0, n1 = E.min() - 8, E.max() + 8, N.min() - 8, N.max() + 8
    side = max(e1 - e0, n1 - n0)
    res = max(min(slant_gsd.min() / 2.5, 0.12), side / 3600.0)
    npx = int(math.ceil(side / res))
    ec, nc = (e0 + e1) / 2.0, (n0 + n1) / 2.0
    clat, clon = offset_latlon(lat, lon, ec, nc)
    ortho = render_view(clat, clon, heading_deg=0.0, ground_size_m=npx * res, out_px=npx, seed=0, style="pseudo")
    ortho = cv2.GaussianBlur(ortho, (0, 0), max(0.5, 0.45 * float(np.median(slant_gsd)) / res))
    # ortho pixel of each ground point: x = (E − ec)/res + npx/2, y = (nc − N)/res + npx/2
    mx = ((E - ec) / res + npx / 2.0).astype(np.float32)
    my = ((nc - N) / res + npx / 2.0).astype(np.float32)
    img = cv2.remap(ortho, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    # the pad on the ground (axis-aligned with east/north) and its white H, painted per pixel
    a, b = E - pad_en[0], N - pad_en[1]
    half = PAD_M / 2.0
    inside = (np.abs(a) <= half) & (np.abs(b) <= half)
    t = PAD_M / 8.0
    bar_l = (np.abs(a + PAD_M / 4.0 - t / 2) <= t / 2) & (np.abs(b) <= PAD_M / 4.0)
    bar_r = (np.abs(a - PAD_M / 4.0 + t / 2) <= t / 2) & (np.abs(b) <= PAD_M / 4.0)
    bar_m = (np.abs(a) <= PAD_M / 4.0) & (np.abs(b) <= t / 2)
    img[inside] = (0, 140, 255)
    img[inside & (bar_l | bar_r | bar_m)] = (255, 255, 255)
    rng = np.random.default_rng(18)
    img = np.clip(img.astype(float) + rng.normal(0, 2.0, img.shape), 0, 255).astype(np.uint8)
    box = img[H - 24:, W - 276:].astype(float)                  # a light box keeps the credit readable
    img[H - 24:, W - 276:] = (0.35 * box + 0.65 * 255).astype(np.uint8)
    cv2.putText(img, "(c) OpenStreetMap contributors", (W - 268, H - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (40, 40, 40), 1, cv2.LINE_AA)
    cols = np.where(inside.any(axis=0))[0]
    rows, cc = np.nonzero(inside)
    return img, R, {"pad_cols": int(cols.max() - cols.min() + 1), "pad_centre_px": [float(cc.mean()), float(rows.mean())],
                    "ortho_res_m": res, "ortho_px": npx}


def orange_mask(img):
    b, g, r = (img[:, :, k].astype(int) for k in range(3))
    return (r > 200) & (g > 100) & (g < 180) & (b < 80)


def main():
    os.makedirs(OUT, exist_ok=True)
    for old in ("truth.json", "make_dataset.py"):          # the old generator and truth sat in datasets/
        p = os.path.join(OUT, old)
        if os.path.exists(p):
            os.remove(p)
    truth = {"camera": {"width_px": W, "height_px": H, "hfov_deg": HFOV, "f_px": F}, "pad_size_m": PAD_M,
             "map": "OpenStreetMap (render_view pseudo style), © OpenStreetMap contributors",
             "conventions": "ENU, origin on the ground under the drone; heading cw from north, pitch + nose up, "
                            "roll + right wing down", "photos": {}}
    for name, lat, lon, h, hd, p, r, pad in PHOTOS:
        img, R, info = render(lat, lon, h, hd, p, r, pad)
        m = orange_mask(img)
        ys, xs = np.nonzero(m)
        cv2.imwrite(os.path.join(OUT, name), img)
        truth["photos"][name] = {"lat": lat, "lon": lon, "height_m": h, "heading_deg": hd, "pitch_deg": p,
                                 "roll_deg": r, "pad_centre_en_m": list(pad), **info,
                                 "mask_cols": int(xs.max() - xs.min() + 1), "mask_centre_px": [float(xs.mean()), float(ys.mean())],
                                 "mask_pixels": int(m.sum())}
        print(name, truth["photos"][name])
    with open(os.path.join(HERE, "truth.json"), "w") as fh:
        json.dump(truth, fh, indent=1)
    with open(os.path.join(OUT, "README.md"), "w") as fh:
        fh.write(
            "# Mission 18 — three synthetic drone photos\n\n"
            "Rendered for the course from OpenStreetMap data of Sousse, Tunisia (NAVERA's test area). "
            "Map data © OpenStreetMap contributors (https://www.openstreetmap.org/copyright), ODbL.\n\n"
            "Ideal pinhole camera: 960 × 540 px, horizontal field of view 90°, principal point at the image centre, "
            "flat ground. Each photo shows a 12 m × 12 m orange landing pad lying on the ground.\n\n"
            "| File | Camera |\n|---|---|\n"
            "| photo_A.png | straight down, image top = north, height unknown |\n"
            "| photo_B.png | straight down, image top = north, height unknown |\n"
            "| photo_T.png | 170 m above the ground, heading 40°, pitch −14° (nose down), roll +5° (right wing down) |\n")
    print("wrote", OUT, "and", os.path.join(HERE, "truth.json"))


if __name__ == "__main__":
    main()
