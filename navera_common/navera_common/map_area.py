"""The mapped area: where NAVERA's day vision has a map to match against (mission-area guard).

Day vision only works over the satellite map loaded for the mission (DAY_DATASET_DIR/images,
the mission bundle's day/images: tiles tile_<z>_<x>_<y>.jpg). Past its edge there is nothing to
match, NAVERA dead-reckons and then stops giving positions (Isaac endurance run 2026-10-22: the
vehicle flew 1.3 km past the map's edge, its output stopped, the autopilot landed it 3 km from
home). MapArea tells how far a position is from that edge — positive inside, negative outside —
for the status flag (navera_estimator -> NavStatus.map_area / map_edge_m) and the geofence an
integrator may load into the autopilot before flight (navera_tools/map_geofence.py).

The coverage is the union of the tiles, rasterised on a local grid (cell_m, default 20 m);
distances come from a distance transform of that grid, so a query is a table lookup.
NAVERA reports; it never acts on the vehicle by itself.
"""
import math
import os
import re
from typing import List, Optional, Sequence, Tuple

import numpy as np

_TILE = re.compile(r"^tile_(\d+)_(\d+)_(\d+)\.(?:jpg|jpeg|png)$")
_M_PER_DEG = 111319.49


def tile_bounds(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
    """(south, west, north, east) degrees of an XYZ (web-mercator) tile."""
    n = 2 ** z

    def lat(yy):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))
    return lat(y + 1), x / n * 360.0 - 180.0, lat(y), (x + 1) / n * 360.0 - 180.0


class MapArea:
    """Coverage of a set of map tiles, on a local east/north grid around their centre."""

    def __init__(self, tiles: Sequence[Tuple[int, int, int]], cell_m: float = 20.0, pad_m: float = 3000.0):
        if not tiles:
            raise ValueError("no map tiles")
        import cv2
        self.tiles = sorted(set(tiles))
        self.cell = float(cell_m)
        b = [tile_bounds(*t) for t in self.tiles]
        self.south, self.west = min(x[0] for x in b), min(x[1] for x in b)
        self.north, self.east = max(x[2] for x in b), max(x[3] for x in b)
        self.lat0, self.lon0 = (self.south + self.north) / 2.0, (self.west + self.east) / 2.0
        self._kx = _M_PER_DEG * math.cos(math.radians(self.lat0))
        e0, n0 = self.to_en(self.south, self.west)
        e1, n1 = self.to_en(self.north, self.east)
        self.e_min, self.n_max = e0 - pad_m, n1 + pad_m
        self.w = int(math.ceil((e1 - e0 + 2 * pad_m) / self.cell)) + 1
        self.h = int(math.ceil((n1 - n0 + 2 * pad_m) / self.cell)) + 1
        mask = np.zeros((self.h, self.w), np.uint8)
        for s, w, nn, e in b:
            c0, r0 = self._cell(*self.to_en(nn, w))
            c1, r1 = self._cell(*self.to_en(s, e))
            mask[max(0, r0):min(self.h, r1 + 1), max(0, c0):min(self.w, c1 + 1)] = 1
        self.mask = mask
        # distance (in cells) to the nearest uncovered cell (inside) / covered cell (outside)
        self._d_in = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        self._d_out = cv2.distanceTransform(1 - mask, cv2.DIST_L2, 5)
        self.area_km2 = float(mask.sum()) * self.cell ** 2 / 1e6

    # ---------------------------------------------------------------- construction
    @classmethod
    def from_images_dir(cls, images_dir: str, cell_m: float = 20.0) -> Optional["MapArea"]:
        """The tiles of a prepared area's images/ (prepare_area.py, mission bundle day/images),
        or None when there are none. An area holding several zooms counts every tile."""
        try:
            names = os.listdir(images_dir)
        except OSError:
            return None
        tiles = []
        for name in names:
            m = _TILE.match(name)
            if m:
                tiles.append(tuple(int(v) for v in m.groups()))
        return cls(tiles, cell_m) if tiles else None

    # ---------------------------------------------------------------- geometry
    def to_en(self, lat: float, lon: float) -> Tuple[float, float]:
        return (lon - self.lon0) * self._kx, (lat - self.lat0) * _M_PER_DEG

    def to_latlon(self, e: float, n: float) -> Tuple[float, float]:
        return self.lat0 + n / _M_PER_DEG, self.lon0 + e / self._kx

    def _cell(self, e: float, n: float) -> Tuple[int, int]:
        return int(math.floor((e - self.e_min) / self.cell)), int(math.floor((self.n_max - n) / self.cell))

    def edge_distance_m(self, lat: float, lon: float) -> float:
        """Distance (m) from (lat, lon) to the edge of the mapped area: > 0 inside, < 0 outside
        (to the nearest mapped tile), NaN for a non-finite position. Resolution: one cell."""
        if not (math.isfinite(lat) and math.isfinite(lon)):
            return math.nan
        e, n = self.to_en(lat, lon)
        c, r = self._cell(e, n)
        if 0 <= c < self.w and 0 <= r < self.h:
            if self.mask[r, c]:
                return float(self._d_in[r, c]) * self.cell
            return -max(float(self._d_out[r, c]) * self.cell, self.cell)
        # beyond the grid's padding: at least as far as the bounding box
        de = max(self.to_en(lat, self.west)[0] - e, e - self.to_en(lat, self.east)[0], 0.0)
        dn = max(self.to_en(self.south, lon)[1] - n, n - self.to_en(self.north, lon)[1], 0.0)
        return -math.hypot(de, dn)

    def fence_polygon(self, margin_m: float, max_vertices: int = 60) -> List[Tuple[float, float]]:
        """An inclusion polygon [(lat, lon), ...] at least margin_m inside the mapped area (the
        largest piece if the area is in several), with at most max_vertices vertices; [] when
        nothing is left that far inside."""
        import cv2
        eps = self.cell
        while True:
            inner = (self._d_in * self.cell >= margin_m + eps).astype(np.uint8)
            cs, _ = cv2.findContours(inner, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not cs:
                return []
            c = max(cs, key=cv2.contourArea)
            # every vertex of the simplified outline lies on the contour, which lies margin + eps
            # inside; the outline strays at most eps from the contour: it stays >= margin inside
            poly = cv2.approxPolyDP(c, eps / self.cell, True).reshape(-1, 2)
            if len(poly) <= max_vertices or eps > 50 * self.cell:
                break
            eps *= 1.5
        out = []
        for col, row in poly:
            e = self.e_min + (col + 0.5) * self.cell
            n = self.n_max - (row + 0.5) * self.cell
            out.append(self.to_latlon(e, n))
        return out


# NavStatus.map_area values (navera_msgs/NavStatus.msg)
MAP_AREA_UNKNOWN, MAP_AREA_INSIDE, MAP_AREA_NEAR_EDGE, MAP_AREA_OUTSIDE = 0, 1, 2, 3


def classify(edge_m: float, warn_m: float) -> int:
    """NavStatus.map_area for a distance to the map's edge (edge_distance_m)."""
    if not math.isfinite(edge_m):
        return MAP_AREA_UNKNOWN
    if edge_m < 0.0:
        return MAP_AREA_OUTSIDE
    if edge_m < warn_m:
        return MAP_AREA_NEAR_EDGE
    return MAP_AREA_INSIDE
