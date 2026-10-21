"""The ground height under a position, from the DEM stored with the mission map (offline).

The barometer gives the vehicle's height above its take-off point; vision needs the height above
the ground under the frame. Over relief the two differ by the terrain (MARS-LVIG AMvalley03, a real
flight over a valley: 28-31 m off at the median, 97 m p90). A DEM of the corridor, downloaded with
the map before departure (day_pkg.dem_sources, prepare_area --dem), gives the terrain height under
the vehicle's position.

Layout (an area's or a bundle's `terrain/` directory):
    dem.json        {"format": "navera-dem", "version": 1, "source", "licence", "attribution",
                     "vertical_datum", "sigma_m", "resolution_m", "pieces": [{"file", "north", "west",
                     "dlat", "dlon", "rows", "cols", "resolution_m", "sigma_m"}]}
    dem_000.npy     float32 heights (m), row 0 = north; pixel (r, c) is the point
                    (north - r * dlat, west + c * dlon); NaN = no data

`Terrain.load(dir)` returns None when there is no DEM (callers keep their behaviour without one);
`height(lat, lon)` returns (height_m, sigma_m, slope) or None outside the pieces / on no data.
Pure numpy, no ROS.
"""
import json
import math
import os
from typing import List, Optional, Tuple

import numpy as np

DEM_FORMAT, DEM_VERSION = "navera-dem", 1
DEM_DIR, DEM_INDEX = "terrain", "dem.json"
M_PER_DEG = 111_320.0


class _Piece:
    def __init__(self, grid: np.ndarray, north: float, west: float, dlat: float, dlon: float,
                 sigma_m: float):
        self.grid = grid
        self.north, self.west, self.dlat, self.dlon = float(north), float(west), float(dlat), float(dlon)
        self.rows, self.cols = grid.shape
        self.sigma_m = float(sigma_m)

    def contains(self, lat: float, lon: float) -> bool:
        r = (self.north - lat) / self.dlat
        c = (lon - self.west) / self.dlon
        return 0.0 <= r <= self.rows - 1 and 0.0 <= c <= self.cols - 1

    def sample(self, lat: float, lon: float) -> Optional[Tuple[float, float]]:
        """(bilinear height, slope m/m) at the point, or None (outside or no data)."""
        r = (self.north - lat) / self.dlat
        c = (lon - self.west) / self.dlon
        r0 = int(min(max(math.floor(r), 0), self.rows - 2))
        c0 = int(min(max(math.floor(c), 0), self.cols - 2))
        fr, fc = r - r0, c - c0
        q = self.grid[r0:r0 + 2, c0:c0 + 2].astype(np.float64)
        if q.shape != (2, 2) or not np.all(np.isfinite(q)):
            return None
        top = q[0, 0] * (1 - fc) + q[0, 1] * fc
        bot = q[1, 0] * (1 - fc) + q[1, 1] * fc
        h = top * (1 - fr) + bot * fr
        # slope from the cell's gradient (east and north, metres per metre)
        dx_m = self.dlon * M_PER_DEG * math.cos(math.radians(lat))
        dy_m = self.dlat * M_PER_DEG
        gx = ((q[0, 1] - q[0, 0]) * (1 - fr) + (q[1, 1] - q[1, 0]) * fr) / dx_m
        gy = ((q[0, 0] - q[1, 0]) * (1 - fc) + (q[0, 1] - q[1, 1]) * fc) / dy_m
        return float(h), float(math.hypot(gx, gy))


class Terrain:
    """Ground heights of a DEM tile set (see the module doc)."""

    def __init__(self, pieces: List[_Piece], info: Optional[dict] = None):
        self.pieces = pieces
        self.info = dict(info or {})

    @classmethod
    def from_grid(cls, grid: np.ndarray, north: float, west: float, dlat: float, dlon: float,
                  sigma_m: float = 5.0, **info) -> "Terrain":
        """One in-memory piece (tests, tools)."""
        return cls([_Piece(np.asarray(grid, np.float32), north, west, dlat, dlon, sigma_m)], info)

    @classmethod
    def load(cls, directory: Optional[str]) -> Optional["Terrain"]:
        """The DEM of an area / bundle: `directory` is the terrain dir itself or the dir holding
        `terrain/`; None when there is none (or it does not read).
        """
        if not directory:
            return None
        for d in (directory, os.path.join(directory, DEM_DIR)):
            idx = os.path.join(d, DEM_INDEX)
            if os.path.isfile(idx):
                break
        else:
            return None
        try:
            with open(idx) as f:
                info = json.load(f)
            if info.get("format") != DEM_FORMAT:
                return None
            pieces = []
            for p in info.get("pieces", []):
                grid = np.load(os.path.join(d, p["file"]), mmap_mode="r")
                pieces.append(_Piece(grid, p["north"], p["west"], p["dlat"], p["dlon"],
                                     p.get("sigma_m", info.get("sigma_m", 5.0))))
        except (OSError, ValueError, KeyError):
            return None
        return cls(pieces, {k: v for k, v in info.items() if k != "pieces"}) if pieces else None

    def height(self, lat: float, lon: float) -> Optional[Tuple[float, float, float]]:
        """(ground height m, its 1-sigma m, slope m/m) under the point, or None."""
        if not (math.isfinite(lat) and math.isfinite(lon)):
            return None
        for p in self.pieces:
            if p.contains(lat, lon):
                s = p.sample(lat, lon)
                if s is not None:
                    return s[0], p.sigma_m, s[1]
        return None

    def height_stats(self, lat: float, lon: float, radius_m: float) -> Optional[Tuple[float, float]]:
        """(mean, standard deviation) of the ground height over a disc where the position may be:
        Gaussian weights of sigma radius_m / 2 on a 7 x 7 grid spanning the radius; None when fewer
        than half the samples have data.
        """
        if not radius_m > 0:
            h = self.height(lat, lon)
            return None if h is None else (h[0], 0.0)
        k = math.cos(math.radians(lat))
        vals, wts, n = [], [], 0
        for i in range(-3, 4):
            for j in range(-3, 4):
                r2 = (i * i + j * j) / 9.0
                if r2 > 1.0:
                    continue
                n += 1
                dn, de = i * radius_m / 3.0, j * radius_m / 3.0
                h = self.height(lat + dn / M_PER_DEG, lon + de / (M_PER_DEG * k))
                if h is not None:
                    vals.append(h[0])
                    wts.append(math.exp(-2.0 * r2))
        if len(vals) * 2 < n:
            return None
        w = np.asarray(wts)
        v = np.asarray(vals)
        mean = float((w * v).sum() / w.sum())
        return mean, float(math.sqrt((w * (v - mean) ** 2).sum() / w.sum()))

    def describe(self) -> str:
        i = self.info
        return (f"{i.get('source', 'DEM')} ({i.get('resolution_m', '?')} m, sigma {i.get('sigma_m', '?')} m, "
                f"{len(self.pieces)} piece(s))")


def save_dem(directory: str, pieces: List[dict], **info) -> str:
    """Write a DEM tile set: pieces = [{"grid": array, "north", "west", "dlat", "dlon", ...}];
    info: source, licence, attribution, vertical_datum, sigma_m, resolution_m. Returns the index path.
    """
    os.makedirs(directory, exist_ok=True)
    out = []
    for i, p in enumerate(pieces):
        name = f"dem_{i:03d}.npy"
        np.save(os.path.join(directory, name), np.asarray(p["grid"], np.float32))
        meta = {k: v for k, v in p.items() if k != "grid"}
        rows, cols = np.asarray(p["grid"]).shape
        out.append(dict(meta, file=name, rows=int(rows), cols=int(cols)))
    index = dict(format=DEM_FORMAT, version=DEM_VERSION, **info, pieces=out)
    path = os.path.join(directory, DEM_INDEX)
    with open(path, "w") as f:
        json.dump(index, f, indent=1)
    return path
