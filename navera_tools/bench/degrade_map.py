#!/usr/bin/env python3
"""A z17 tile map degraded to a coarser ground resolution (what a 2 / 3 / 5 / 10 m satellite gives).

    python3 navera_tools/bench/degrade_map.py <area dir> <out area dir> --gsd-m 10 [--mtf-sigma 0.5]

The tiles of <area dir>/images (tile_17_x_y.jpg, ~1 m/px) are assembled into one mosaic, reduced to
--gsd-m metres per pixel by pixel averaging (INTER_AREA: each coarse pixel is the mean of the ground
it covers, as a sensor pixel integrates it), optionally blurred by a Gaussian of --mtf-sigma coarse
pixels (a real sensor's optics: Sentinel-2's MTF at Nyquist is ~0.15-0.3, i.e. softer than a box),
then enlarged back to the z17 grid (bicubic) and cut into the same tiles. The day matcher is
unchanged: the map simply holds no detail finer than --gsd-m — as a coarse source over-zoomed to
z17 by the map preparation (day_pkg.tile_sources) would. The whole mosaic is processed at once so
tile edges add no artefact.
"""
import argparse
import math
import os
import re

import cv2
import numpy as np

Z = 17


def mpp_z17(lat_deg: float) -> float:
    """Ground metres per pixel of a z17 web-mercator tile at a latitude."""
    return 156543.03392 * math.cos(math.radians(lat_deg)) / 2 ** Z


def tile_lat(y: float) -> float:
    n = 2 ** Z
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def degrade(mosaic: np.ndarray, factor: float, mtf_sigma: float = 0.0) -> np.ndarray:
    """The mosaic with no detail finer than `factor` pixels (same size)."""
    h, w = mosaic.shape[:2]
    small = cv2.resize(mosaic, (max(1, round(w / factor)), max(1, round(h / factor))), interpolation=cv2.INTER_AREA)
    if mtf_sigma > 0:
        small = cv2.GaussianBlur(small, (0, 0), mtf_sigma)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("area")
    ap.add_argument("out")
    ap.add_argument("--gsd-m", type=float, required=True, help="ground resolution to simulate (m/px)")
    ap.add_argument("--mtf-sigma", type=float, default=0.0, help="Gaussian blur, in coarse pixels (0: none)")
    ap.add_argument("--quality", type=int, default=95)
    a = ap.parse_args()
    src = os.path.join(a.area, "images")
    tiles = {}
    for f in os.listdir(src):
        m = re.fullmatch(rf"tile_{Z}_(\d+)_(\d+)\.jpg", f)
        if m:
            tiles[(int(m.group(1)), int(m.group(2)))] = f
    xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]
    x0, y0 = min(xs), min(ys)
    W, H = (max(xs) - x0 + 1) * 256, (max(ys) - y0 + 1) * 256
    mosaic = np.zeros((H, W, 3), np.uint8)
    for (x, y), f in tiles.items():
        mosaic[(y - y0) * 256:(y - y0 + 1) * 256, (x - x0) * 256:(x - x0 + 1) * 256] = cv2.imread(os.path.join(src, f))
    native = mpp_z17(tile_lat((y0 + max(ys) + 1) / 2))
    factor = a.gsd_m / native
    out = degrade(mosaic, factor, a.mtf_sigma)
    dst = os.path.join(a.out, "images")
    os.makedirs(dst, exist_ok=True)
    for (x, y), f in tiles.items():
        cv2.imwrite(os.path.join(dst, f), out[(y - y0) * 256:(y - y0 + 1) * 256, (x - x0) * 256:(x - x0 + 1) * 256],
                    [cv2.IMWRITE_JPEG_QUALITY, a.quality])
    print(f"{len(tiles)} tiles, native {native:.2f} m/px -> {a.gsd_m} m/px (factor {factor:.2f}, "
          f"mtf sigma {a.mtf_sigma} px)", flush=True)


if __name__ == "__main__":
    main()
