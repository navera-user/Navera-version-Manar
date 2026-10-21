"""Ground elevation from terrarium DEM tiles (fetch_scene_data.py), bilinear, m above sea level."""
import glob
import math
import os
import re
from typing import Dict, Tuple

import numpy as np


class Dem:
    def __init__(self, dem_dir: str):
        self.tiles: Dict[Tuple[int, int], np.ndarray] = {}
        self.z = None
        import cv2
        for f in glob.glob(os.path.join(os.path.expanduser(dem_dir), "terrarium_*_*_*.png")):
            z, x, y = map(int, re.findall(r"terrarium_(\d+)_(\d+)_(\d+)\.png$", f)[0])
            t = cv2.imread(f, cv2.IMREAD_COLOR)[:, :, ::-1].astype(np.float64)     # RGB
            self.tiles[(x, y)] = t[..., 0] * 256 + t[..., 1] + t[..., 2] / 256 - 32768
            self.z = z
        if not self.tiles:
            raise FileNotFoundError(f"no terrarium tiles in {dem_dir}")
        xs, ys = [k[0] for k in self.tiles], [k[1] for k in self.tiles]
        self.px_box = (min(xs) * 256, (max(xs) + 1) * 256 - 1, min(ys) * 256, (max(ys) + 1) * 256 - 1)

    def _px(self, px: int, py: int) -> float:
        px = min(max(px, self.px_box[0]), self.px_box[1])              # the edge pixel past the last tile
        py = min(max(py, self.px_box[2]), self.px_box[3])
        t = self.tiles.get((px // 256, py // 256))
        if t is None:
            raise ValueError("outside the DEM tiles")
        return float(t[py % 256, px % 256])

    def height(self, lat: float, lon: float) -> float:
        n = 2 ** self.z
        fx = (lon + 180) / 360 * n * 256 - 0.5
        fy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * 256 - 0.5
        x0, y0 = int(math.floor(fx)), int(math.floor(fy))
        dx, dy = fx - x0, fy - y0
        v = self._px
        return ((v(x0, y0) * (1 - dx) + v(x0 + 1, y0) * dx) * (1 - dy)
                + (v(x0, y0 + 1) * (1 - dx) + v(x0 + 1, y0 + 1) * dx) * dy)
