#!/usr/bin/env python3
"""Ground elevation under each UAV-VisLoc image (public DEM), so the eval can use height above ground.

UAV-VisLoc's "height" is above sea level (flight 05, Yunnan: 2313 m over ground at 1900-2125 m,
i.e. 190-400 m above ground). The matcher needs the height above ground; this writes
--out (filename, ground_m) from the AWS Terrain Tiles (terrarium, z12,
~30 m SRTM-class), cached in --cache.

    python3 navera_tools/bench/uavvisloc_dem.py <flight dir> --out ground.csv [--cache DIR]
"""
import argparse
import csv
import math
import os
import urllib.request

import numpy as np
from PIL import Image

Z = 12
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("flight")
ap.add_argument("--out", required=True)
ap.add_argument("--cache", default=os.path.expanduser("~/.navera_sim/uavvisloc/dem"))
a = ap.parse_args()
os.makedirs(a.cache, exist_ok=True)
_tiles = {}


def tile(x, y):
    if (x, y) not in _tiles:
        p = os.path.join(a.cache, f"{Z}_{x}_{y}.png")
        if not os.path.exists(p):
            urllib.request.urlretrieve(f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png", p)
        t = np.asarray(Image.open(p).convert("RGB")).astype(float)
        _tiles[(x, y)] = t[..., 0] * 256 + t[..., 1] + t[..., 2] / 256 - 32768
    return _tiles[(x, y)]


def ground_m(lat, lon):
    """Bilinear DEM height (m above sea level) at lat, lon."""
    n = 2 ** Z
    fx = (lon + 180) / 360 * n * 256 - 0.5
    fy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * 256 - 0.5
    x0, y0 = int(math.floor(fx)), int(math.floor(fy))
    v = lambda px, py: tile(px // 256, py // 256)[py % 256, px % 256]  # noqa: E731
    dx, dy = fx - x0, fy - y0
    return ((v(x0, y0) * (1 - dx) + v(x0 + 1, y0) * dx) * (1 - dy) + (v(x0, y0 + 1) * (1 - dx) + v(x0 + 1, y0 + 1) * dx) * dy)


rows = list(csv.DictReader(open(os.path.join(a.flight, os.path.basename(a.flight.rstrip("/")) + ".csv"))))
with open(a.out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["filename", "ground_m"])
    agl = []
    for r in rows:
        g = ground_m(float(r["lat"]), float(r["lon"]))
        agl.append(float(r["height"]) - g)
        w.writerow([r["filename"], round(g, 1)])
agl.sort()
print(f"{len(rows)} images, height above ground min {agl[0]:.0f} median {agl[len(agl) // 2]:.0f} max {agl[-1]:.0f} m")
