# Lab 7 — Web Mercator, the tile pyramid and MBTiles
#
# Fill in the ten functions marked TODO, save (Ctrl+S), then run:
#     python3 tiles_lab.py
# Conventions:
#   * latitudes / longitudes in DEGREES at the interface; math.tan / math.cos / math.log use RADIANS;
#   * tile numbers follow the XYZ ("slippy map") convention: x grows to the EAST, y to the SOUTH,
#     tile (0, 0) is the north-west corner of the world;
#   * a "global pixel" is tile coordinate x 256 (TILE_PX): pixel (0, 0) is the world's NW corner.

import math
import sqlite3

MAP = "/data/map.mbtiles"            # NAVERA's satellite map of the Sousse region (read only!)
TILE_PX = 256                        # every tile is a square picture of 256 x 256 pixels
EQUATOR_M = 40_075_016.7             # 2·π·a, length of the equator in metres (NAVERA's value, local_matcher.py)
MAX_LAT = 85.0511287798              # Web Mercator stops here: mercator_y(MAX_LAT) = π


def mercator_y(lat):
    """Mercator ordinate of latitude `lat` (degrees) on the unit sphere: ln(tan(π/4 + φ/2))."""
    # TODO 1: φ in radians; return math.log(math.tan(...))
    return None


def inverse_mercator_y(y):
    """Latitude in degrees whose mercator_y() is y:  φ = 2·atan(e^y) − π/2  (= atan(sinh y))."""
    # TODO 2: the inverse formula, result in DEGREES
    return None


def tile_xy(lat, lon, z):
    """Fractional tile coordinates (x, y) of a point at zoom z, e.g. (69409.47, 51547.56)."""
    # TODO 3: n = 2**z;  x = (lon + 180) / 360 · n  (a direct proportion);  y = (1 − mercator_y(lat) / π) / 2 · n
    return None


def latlon_to_tile(lat, lon, z):
    """Integer (x, y) of the tile that contains the point at zoom z."""
    # TODO 4: the whole parts of tile_xy(): int(math.floor(...))
    return None


def tile_to_latlon(x, y, z):
    """(lat, lon) of the point at tile coordinates (x, y): for whole numbers, the tile's NORTH-WEST
    corner; tile_to_latlon(x + 0.5, y + 0.5, z) is the tile's centre."""
    # TODO 5: invert tile_xy(): lon from x, then the Mercator ordinate from y and inverse_mercator_y()
    return None


def meters_per_pixel(lat, z):
    """Ground size of one map pixel (metres) at latitude lat and zoom z: EQUATOR_M · cos φ / (2**z · 256)."""
    # TODO 6
    return None


def zoom_for_gsd(lat, gsd_m, zmin=0, zmax=19):
    """The highest zoom whose map pixel is still at least gsd_m metres (the map must not be finer
    than the camera image), limited to [zmin, zmax]."""
    # TODO 7: z = floor(log2(meters_per_pixel(lat, 0) / gsd_m)), then clamp
    return None


def read_tile(db_path, z, x, y):
    """The bytes (a JPEG picture) of tile z/x/y (XYZ numbering) from an MBTiles file, or None."""
    # TODO 8: open READ-ONLY (uri "file:...?mode=ro"), SELECT tile_data with the TMS row, close, bytes or None
    return None


def latlon_to_pixel(lat, lon, z, x0, y0):
    """(px, py) of the point in a mosaic whose top-left tile is (x0, y0), at zoom z."""
    # TODO 9: (fractional tile coordinate − top-left tile) × TILE_PX, for x and for y
    return None


def pixel_to_latlon(px, py, z, x0, y0):
    """(lat, lon) of pixel (px, py) of a mosaic whose top-left tile is (x0, y0) — inverse of TODO 9."""
    # TODO 10: back to fractional tile coordinates, then tile_to_latlon()
    return None


# ---- you don't need to change anything below this line (but you can read it!) ----

def decode(jpeg_bytes):
    """JPEG bytes -> picture (a numpy array, height x width x 3, uint8, OpenCV's BGR colour order)."""
    import cv2
    import numpy as np
    return cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)


def build_mosaic(db_path, lat, lon, z, radius=1):
    """(2·radius + 1)² tiles around the point's tile, glued together. Returns (picture, x0, y0),
    where (x0, y0) is the top-left tile. Missing tiles stay dark grey."""
    import numpy as np
    x, y = latlon_to_tile(lat, lon, z)
    x0, y0, k = x - radius, y - radius, 2 * radius + 1
    mosaic = np.full((k * TILE_PX, k * TILE_PX, 3), 40, np.uint8)
    for row in range(k):
        for col in range(k):
            data = read_tile(db_path, z, x0 + col, y0 + row)
            if data is not None:
                mosaic[row * TILE_PX:(row + 1) * TILE_PX, col * TILE_PX:(col + 1) * TILE_PX] = decode(data)
    return mosaic, x0, y0


if __name__ == "__main__":
    print("Mercator ordinate y = ln(tan(pi/4 + lat/2)):")
    for lat in (0.0, 1.2834, 35.8277, 51.5007, 64.1417, MAX_LAT):
        y = mercator_y(lat)
        y = None if y is None else round(y, 12) + 0.0
        back = None if y is None else inverse_mercator_y(y)
        print(f"  lat {lat:9.4f}  ->  y = {'TODO 1' if y is None else f'{y:.6f}':>10}"
              f"   and back {'TODO 2' if back is None else f'{back:.10f}'}")
    lat, lon = 35.8277, 10.6388                                         # the Ribat of Sousse
    print(f"\nThe Ribat of Sousse ({lat}, {lon}) in NAVERA's map, zoom 13 to 19:")
    print(f"{'zoom':>4}  {'tile x':>8} {'tile y':>8}   {'m / pixel':>9}  {'tile width (m)':>14}")
    for z in range(13, 20):
        t = latlon_to_tile(lat, lon, z)
        mpp = meters_per_pixel(lat, z)
        tx, ty = t if t is not None else ("TODO", "TODO")
        m = "TODO" if mpp is None else f"{mpp:9.3f}"
        w = "TODO" if mpp is None else f"{mpp * TILE_PX:14.1f}"
        print(f"{z:>4}  {tx:>8} {ty:>8}   {m:>9}  {w:>14}")
    t = latlon_to_tile(lat, lon, 17)
    if t is not None and tile_to_latlon(*t, 17) is not None:
        print("\nzoom-17 tile", t, "NW corner:", tile_to_latlon(*t, 17),
              " centre:", tile_to_latlon(t[0] + 0.5, t[1] + 0.5, 17))
