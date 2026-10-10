#!/usr/bin/env python3
"""Builds the dataset of lesson 23 (run on the host, once):  python3 make_dataset.py

Synthetic "drone photos" with an exact ground truth:
  * most are cut from the satellite map itself (/data/map.mbtiles, zoom 18), turned by the
    drone's heading, scaled to the camera's ground resolution (lesson 18:
    m/px = 2 * altitude * tan(hfov / 2) / width), blurred, brighter or darker, noisy, JPEG;
  * some are cut from OLDER imagery of the same place (Esri Wayback 2017 and 2022 tiles saved by
    the bench campaign of 2026-10-06): the map and the photo then differ like a real flight;
  * one is over open sea: nothing to match, the right answer is "no position";
  * one has a prior 1.2 km away from the truth, outside the searched map: "no position" too.
Writes photos/*.jpg, truth.csv and images/tile_17_x_y.jpg (the map tiles around the photos,
the layout NAVERA's LocalMatcher reads), plus overview.jpg.
"""
import csv
import math
import os
import random
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "courses", "23-locate-on-map", "files"))
import navmap  # noqa: E402

BENCH = os.path.expanduser("~/.navera_sim/bench_2026-10-06")
W, H = 640, 480                       # photo size (px)

# name, lat, lon, altitude m, hfov deg, heading deg, source, prior offset (m east, m north)
PHOTOS = [
    ("p01_medina",   35.8256, 10.6370, 200, 75, 30,  "map",    (120, -80)),
    ("p02_port",     35.8300, 10.6430, 250, 80, 300, "map",    (-150, 60)),
    ("p03_khezama",  35.8460, 10.6000, 180, 70, 120, "map",    (90, 160)),
    ("p04_olives",   35.6930, 10.6348, 220, 75, 210, "map",    (-60, -200)),
    ("p05_farms",    35.9389, 10.4590, 260, 84, 75,  "map",    (200, 40)),
    ("p06_hills",    35.8000, 10.3711, 300, 84, 160, "map",    (-120, -120)),
    ("p07_msaken",   35.7330, 10.5800, 200, 75, 250, "map",    (50, 230)),
    ("p08_hammam",   35.8610, 10.5950, 150, 70, 0,   "map",    (-220, 30)),
    ("p09_kalaa22",  35.8700, 10.5360, 200, 75, 45,  "wb2022", (140, 120)),
    ("p10_kalaa22",  35.8640, 10.5300, 240, 80, 190, "wb2022", (-100, 150)),
    ("p11_kalaa17",  35.8720, 10.5300, 200, 75, 330, "wb2017", (160, -60)),
    ("p12_sea",      35.8300, 10.7000, 200, 75, 90,  "map",    (100, 100)),
    # the prior is 1.2 km off: the true place is OUTSIDE the searched map -> the answer must be "no fix"
    ("p13_lost",     35.8380, 10.6200, 200, 75, 140, "map",    (-850, 850)),
]
SEARCH_M = 300.0


def tile_reader(source):
    if source == "map":
        return lambda x, y: navmap.read_tile(18, x, y)
    d = os.path.join(BENCH, source)
    return lambda x, y: cv2.imread(os.path.join(d, f"tile_18_{x}_{y}.jpg"))


def patch18(read, lat, lon, size):
    """size x size z18 picture centred on (lat, lon) from a tile reader."""
    cx, cy = navmap.latlon_to_pixel(lat, lon, 18)
    x0, y0 = int(round(cx - size / 2)), int(round(cy - size / 2))
    out = np.zeros((size, size, 3), np.uint8)
    for tx in range(x0 // 256, (x0 + size - 1) // 256 + 1):
        for ty in range(y0 // 256, (y0 + size - 1) // 256 + 1):
            t = read(tx, ty)
            if t is None:
                raise SystemExit(f"missing tile 18/{tx}/{ty}")
            ox, oy = tx * 256 - x0, ty * 256 - y0
            sx0, sy0 = max(0, -ox), max(0, -oy)
            ex, ey = min(256, size - ox), min(256, size - oy)
            out[oy + sy0:oy + ey, ox + sx0:ox + ex] = t[sy0:ey, sx0:ex]
    return out, (cx - x0, cy - y0)


def render(name, lat, lon, alt, hfov, heading, source, rng):
    mpp = 2 * alt * math.tan(math.radians(hfov) / 2) / W          # lesson 18
    s = mpp / navmap.m_per_px(lat, 18)                             # photo px -> z18 px
    size = int(math.hypot(W, H) * s) + 16
    src, (pcx, pcy) = patch18(tile_reader(source), lat, lon, size)
    th = math.radians(heading)
    # photo pixel (u, v) -> source pixel: centre + s * R(heading) * (u - W/2, v - H/2)
    c, si = math.cos(th) * s, math.sin(th) * s
    M = np.float32([[c, -si, pcx - c * W / 2 + si * H / 2],
                    [si, c, pcy - si * W / 2 - c * H / 2]])
    img = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP)
    # a camera is not a satellite: blur, exposure, noise, JPEG
    img = cv2.GaussianBlur(img, (0, 0), rng.uniform(0.6, 1.4))
    img = np.clip(img.astype(np.float32) * rng.uniform(0.75, 1.25) + rng.uniform(-25, 25), 0, 255)
    img = np.clip(img + rng.normal(0, 4, img.shape), 0, 255).astype(np.uint8)
    cv2.imwrite(os.path.join(HERE, "photos", name + ".jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return mpp


def offset(lat, lon, de, dn):
    return lat + dn / 111320.0, lon + de / (111320.0 * math.cos(math.radians(lat)))


def main():
    rng = np.random.default_rng(22)
    os.makedirs(os.path.join(HERE, "photos"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "images"), exist_ok=True)
    rows, tiles = [], set()
    for name, lat, lon, alt, hfov, hdg, source, (de, dn) in PHOTOS:
        mpp = render(name, lat, lon, alt, hfov, hdg, source, rng)
        plat, plon = offset(lat, lon, de, dn)
        rows.append(dict(file=f"photos/{name}.jpg", true_lat=f"{lat:.6f}", true_lon=f"{lon:.6f}",
                         altitude_m=alt, hfov_deg=hfov, heading_deg=hdg, source=source,
                         prior_lat=f"{plat:.6f}", prior_lon=f"{plon:.6f}", search_m=SEARCH_M))
        # z17 tiles NAVERA's LocalMatcher would load around the prior (search + margin + border)
        cx, cy = navmap.latlon_to_pixel(plat, plon, 17)
        r = (SEARCH_M + 0.5 * math.hypot(W, H) * mpp + 150) / navmap.m_per_px(plat, 17)
        for tx in range(int((cx - r) // 256) - 1, int((cx + r) // 256) + 2):      # +1: NAVERA pads each tile with its neighbours
            for ty in range(int((cy - r) // 256) - 1, int((cy + r) // 256) + 2):
                tiles.add((tx, ty))
        print(f"{name}: {mpp:.3f} m/px, footprint {W * mpp:.0f} x {H * mpp:.0f} m, source {source}")
    for tx, ty in sorted(tiles):
        t = navmap.read_tile(17, tx, ty)
        if t is not None:
            cv2.imwrite(os.path.join(HERE, "images", f"tile_17_{tx}_{ty}.jpg"), t, [cv2.IMWRITE_JPEG_QUALITY, 90])
    with open(os.path.join(HERE, "truth.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    thumbs = [cv2.resize(cv2.imread(os.path.join(HERE, r["file"])), (320, 240)) for r in rows]
    thumbs += [np.zeros_like(thumbs[0])] * (-len(thumbs) % 4)
    grid = np.vstack([np.hstack(thumbs[i:i + 4]) for i in range(0, len(thumbs), 4)])
    cv2.imwrite(os.path.join(HERE, "overview.jpg"), grid, [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(f"{len(rows)} photos, {len(tiles)} map tiles")


if __name__ == "__main__":
    main()
