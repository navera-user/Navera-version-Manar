"""The terrain (DEM) of a mission corridor, downloaded before departure and stored with the map.

Vision needs the height above the ground; the barometer gives the height above take-off. Over
relief they differ by the terrain under the vehicle (navera_common.terrain). This module cuts the
corridor's terrain out of a free, licence-clean global DEM and writes it as an offline tile set
(`<area>/terrain/`: dem.json + dem_NNN.npy, one piece per route leg), read in flight by
navera_common.terrain.Terrain.

Source: Copernicus DEM (ESA / Airbus, a surface model: roofs and tree tops included), as
Cloud-Optimized GeoTIFFs on AWS Open Data (no account): GLO-30 (1 arc-second, ~30 m) where it is
published, else GLO-90 (3 arc-seconds, ~90 m; GLO-30 is withheld for a few countries, e.g.
Armenia and Azerbaijan). Licence: free of charge for any use, commercial included, with the
attribution below (Copernicus DEM licence, ESA 2022). Vertical datum EGM2008 (geoid): NAVERA only
uses height DIFFERENCES of it (navera_common.altitude), so the datum does not matter. Only the
image segments the corridor needs are fetched (HTTP range requests).

    from day_pkg.dem_sources import build_dem
    info = build_dem(legs, buffer_m, "<area>/terrain")
"""
import math
import urllib.error
from typing import Callable, Optional, Sequence, Tuple

import numpy as np

from day_pkg.tile_sources import GeoTiff, HttpFile

M_PER_DEG = 111_320.0
LICENCE = ("Copernicus DEM licence: free of charge, any use including commercial, attribution required "
           "(registry.opendata.aws/copernicus-dem)")
ATTRIBUTION = ("Copernicus DEM: produced using Copernicus WorldDEM-30 (c) DLR e.V. 2010-2014 and (c) Airbus "
               "Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; "
               "all rights reserved")
# (name, resolution m, URL root, file code, arc-seconds per pixel in latitude, 1-sigma height m).
# Sigma: GLO-30's specification is < 4 m absolute (90 % linear error, ~2.4 m 1-sigma) over the
# globe and worse on steep slopes; GLO-90 is the same surface averaged over 3x3 pixels, which on
# relief costs a few metres more. Taken cautiously; the position's slope term is added in use.
COPERNICUS = (
    ("Copernicus DEM GLO-30", 30, "https://copernicus-dem-30m.s3.amazonaws.com", "10", 1.0, 4.0),
    ("Copernicus DEM GLO-90", 90, "https://copernicus-dem-90m.s3.amazonaws.com", "30", 3.0, 8.0),
)


def tile_url(root: str, code: str, lat_floor: int, lon_floor: int) -> str:
    """URL of the Copernicus DEM COG of the 1-degree cell whose south-west corner is given."""
    ns = f"{'N' if lat_floor >= 0 else 'S'}{abs(lat_floor):02d}_00"
    ew = f"{'E' if lon_floor >= 0 else 'W'}{abs(lon_floor):03d}_00"
    name = f"Copernicus_DSM_COG_{code}_{ns}_{ew}_DEM"
    return f"{root}/{name}/{name}.tif"


def http_opener(url: str):
    """A seekable remote file, or None when the tile does not exist (404: sea, or withheld)."""
    f = HttpFile(url)
    try:
        f._size()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        raise
    return f


def _bbox(leg: Sequence[Sequence[float]], buffer_m: float) -> Tuple[float, float, float, float]:
    """(south, west, north, east) of a leg widened by buffer_m (and a 200 m margin)."""
    lats = [p[0] for p in leg]
    lons = [p[1] for p in leg]
    m = buffer_m + 200.0
    dlat = m / M_PER_DEG
    dlon = m / (M_PER_DEG * max(0.05, math.cos(math.radians(max(abs(min(lats)), abs(max(lats)))))))
    return min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon


class _Cells:
    """The 1-degree source cells (GLO-30 first, else GLO-90), opened on demand."""

    def __init__(self, opener: Callable):
        self.opener, self._open = opener, {}

    def get(self, lat_floor: int, lon_floor: int):
        key = (lat_floor, lon_floor)
        if key not in self._open:
            self._open[key] = None
            for name, res, root, code, arcsec, sigma in COPERNICUS:
                f = self.opener(tile_url(root, code, lat_floor, lon_floor))
                if f is not None:
                    self._open[key] = (GeoTiff(f, cache_segments=8), name, res, arcsec, sigma)
                    break
        return self._open[key]


def _sample_cell(tif: GeoTiff, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Bilinear heights of a source cell at the points (all inside it)."""
    col = (lon - tif.x0) / tif.sx - 0.5
    row = (tif.y0 - lat) / tif.sy - 0.5
    c0, r0 = int(max(0, math.floor(col.min()))), int(max(0, math.floor(row.min())))
    c1, r1 = int(min(tif.w, math.floor(col.max()) + 2)), int(min(tif.h, math.floor(row.max()) + 2))
    win = tif.values(c0, r0, c1, r1).astype(np.float64)
    win[win < -1000.0] = np.nan                              # no-data values
    cc = np.clip(col - c0, 0.0, win.shape[1] - 1.000001)
    rr = np.clip(row - r0, 0.0, win.shape[0] - 1.000001)
    ci, ri = np.floor(cc).astype(int), np.floor(rr).astype(int)
    ci1, ri1 = np.minimum(ci + 1, win.shape[1] - 1), np.minimum(ri + 1, win.shape[0] - 1)
    fc, fr = cc - ci, rr - ri
    top = win[ri, ci] * (1 - fc) + win[ri, ci1] * fc
    bot = win[ri1, ci] * (1 - fc) + win[ri1, ci1] * fc
    return top * (1 - fr) + bot * fr


def build_dem(legs: Sequence[Sequence[float]], buffer_m: float, out_dir: str,
              opener: Optional[Callable] = None, progress: Optional[Callable] = None) -> dict:
    """Cut the corridor's terrain (one piece per route leg, each its leg's box + buffer_m) out of the
    Copernicus DEM into out_dir (navera_common.terrain layout). Returns the dem.json content
    (without the pieces) plus "pieces" (count), "cells" (source cells used), "missing_share"
    (share of corridor pixels without data: sea, or no source cell)."""
    from navera_common.terrain import save_dem
    opener = opener or http_opener
    cells = _Cells(opener)
    route = [list(map(float, p)) for p in legs]
    pairs = list(zip(route, route[1:])) or [(route[0], route[0])]
    pieces, used, total, missing = [], {}, 0, 0
    for k, leg in enumerate(pairs):
        south, west, north, east = _bbox(leg, buffer_m)
        # the finest source over this piece sets its spacing
        lat_cells = range(int(math.floor(south)), int(math.floor(north)) + 1)
        lon_cells = range(int(math.floor(west)), int(math.floor(east)) + 1)
        found = [cells.get(a, b) for a in lat_cells for b in lon_cells]
        arcsec = min([c[3] for c in found if c is not None] or [3.0])
        dlat = arcsec / 3600.0
        dlon = dlat / max(0.05, math.cos(math.radians((south + north) / 2.0)))
        rows = int(math.ceil((north - south) / dlat)) + 1
        cols = int(math.ceil((east - west) / dlon)) + 1
        lat = north - np.arange(rows) * dlat
        lon = west + np.arange(cols) * dlon
        grid = np.full((rows, cols), np.nan, np.float32)
        sigmas, res = [], []
        for a in lat_cells:
            for b in lon_cells:
                c = cells.get(a, b)
                ri = np.nonzero((lat >= a) & (lat < a + 1))[0]
                ci = np.nonzero((lon >= b) & (lon < b + 1))[0]
                if c is None or not len(ri) or not len(ci):
                    continue
                LA, LO = np.meshgrid(lat[ri], lon[ci], indexing="ij")
                grid[ri[0]:ri[-1] + 1, ci[0]:ci[-1] + 1] = _sample_cell(c[0], LA, LO)
                used[f"{a},{b}"] = c[1]
                sigmas.append(c[4])
                res.append(c[2])
        total += grid.size
        missing += int(np.isnan(grid).sum())
        pieces.append(dict(grid=grid, north=float(north), west=float(west), dlat=dlat, dlon=dlon,
                           resolution_m=max(res) if res else None, sigma_m=max(sigmas) if sigmas else None))
        if progress:
            progress("dem", k + 1, len(pairs))
    pieces = [p for p in pieces if p["sigma_m"] is not None]
    names = sorted(set(used.values()))
    info = dict(source=" + ".join(names) if names else "none", licence=LICENCE, attribution=ATTRIBUTION,
                vertical_datum="EGM2008", surface="DSM (roofs, tree tops)",
                sigma_m=max([p["sigma_m"] for p in pieces] or [0.0]) or None,
                resolution_m=max([p["resolution_m"] for p in pieces] or [0]) or None,
                buffer_m=round(float(buffer_m), 1))
    if pieces:
        save_dem(out_dir, pieces, **info)
    return dict(info, pieces=len(pieces), cells=used,
                missing_share=round(missing / total, 4) if total else 1.0)
