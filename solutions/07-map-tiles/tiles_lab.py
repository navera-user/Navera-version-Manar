# Lab 7 — How the world is cut into map tiles
#
# Fill in the six functions marked TODO, save (Ctrl+S), then run:
#     python3 tiles_lab.py
# Tile numbers follow the "XYZ" (slippy map) convention: x grows to the EAST, y grows to the SOUTH.

import math
import sqlite3

MAP = "/data/map.mbtiles"            # NAVERA's satellite map of the Sousse region (10 GB, read only!)
TILE_PX = 256                        # every tile is a square picture of 256 x 256 pixels
EQUATOR_M = 40_075_016.7             # length of the equator in meters (NAVERA's value, day_pkg/local_matcher.py)


def tile_xy(lat, lon, z):
    """Fractional tile coordinates (x, y) of a point at zoom z, e.g. (69409.47, 51547.56)."""
    # TODO 1: x from the longitude (a simple rule of three), y from the latitude (the Mercator formula)
    n = 2 ** z
    r = math.radians(lat)
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    return x, y


def latlon_to_tile(lat, lon, z):
    """Integer (x, y) of the tile that contains the point at zoom z."""
    # TODO 2: use tile_xy() and keep only the whole part of each number
    x, y = tile_xy(lat, lon, z)
    return int(math.floor(x)), int(math.floor(y))


def tile_to_latlon(x, y, z):
    """(lat, lon) of the NORTH-WEST corner (top-left) of tile x, y at zoom z."""
    # TODO 3: the opposite of tile_xy (lon: rule of three backwards; lat: atan(sinh(...)))
    n = 2 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lat, lon


def meters_per_pixel(lat, z):
    """Size on the ground of one map pixel, in meters, at latitude lat and zoom z."""
    # TODO 4: the equator is cut into 2**z tiles of 256 pixels; multiply by cos(latitude)
    return EQUATOR_M * math.cos(math.radians(lat)) / (2 ** z) / TILE_PX


def read_tile(db_path, z, x, y):
    """The bytes (a JPEG picture) of tile z/x/y (XYZ numbering) from an MBTiles file, or None."""
    # TODO 5: open the file READ-ONLY, SELECT tile_data with the TMS row, return bytes or None
    conn = sqlite3.connect("file:" + db_path + "?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                           (z, x, (2 ** z - 1) - y)).fetchone()
    finally:
        conn.close()
    return bytes(row[0]) if row else None


def pixel_in_mosaic(lat, lon, z):
    """(px, py): where the point falls in the 3 x 3 mosaic (768 x 768 pixels) built around its tile.

    The mosaic's top-left tile is (x - 1, y - 1), where (x, y) = latlon_to_tile(lat, lon, z).
    """
    # TODO 6: fractional tile position minus the top-left tile, times 256
    fx, fy = tile_xy(lat, lon, z)
    x, y = latlon_to_tile(lat, lon, z)
    return (fx - (x - 1)) * TILE_PX, (fy - (y - 1)) * TILE_PX


# ---- you don't need to change anything below this line (but you can read it!) ----

def decode(jpeg_bytes):
    """JPEG bytes -> picture (a numpy array, height x width x 3, in OpenCV's BGR colour order)."""
    import cv2
    import numpy as np
    return cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)


def build_mosaic(db_path, lat, lon, z):
    """3 x 3 tiles around the point, glued together (768 x 768), with the point marked in red."""
    import cv2
    import numpy as np
    x, y = latlon_to_tile(lat, lon, z)
    mosaic = np.full((3 * TILE_PX, 3 * TILE_PX, 3), 40, np.uint8)       # dark grey = missing tile
    for row in range(3):
        for col in range(3):
            data = read_tile(db_path, z, x - 1 + col, y - 1 + row)
            if data is not None:
                mosaic[row * TILE_PX:(row + 1) * TILE_PX, col * TILE_PX:(col + 1) * TILE_PX] = decode(data)
    for k in (1, 2):                                                    # thin lines between the tiles
        mosaic[k * TILE_PX, :] = (255, 255, 255)
        mosaic[:, k * TILE_PX] = (255, 255, 255)
    px, py = pixel_in_mosaic(lat, lon, z)
    p = (int(round(px)), int(round(py)))
    cv2.circle(mosaic, p, 12, (0, 0, 255), 2)
    cv2.line(mosaic, (p[0] - 20, p[1]), (p[0] + 20, p[1]), (0, 0, 255), 1)
    cv2.line(mosaic, (p[0], p[1] - 20), (p[0], p[1] + 20), (0, 0, 255), 1)
    mpp = meters_per_pixel(lat, z)                                      # scale bar of a round length
    length_m = next(L for L in (5000, 2000, 1000, 500, 200, 100, 50, 20, 10, 5) if L / mpp <= 300)
    bar = int(round(length_m / mpp))
    cv2.rectangle(mosaic, (14, 734), (30 + bar, 760), (255, 255, 255), -1)
    cv2.line(mosaic, (22, 748), (22 + bar, 748), (0, 0, 0), 3)
    cv2.putText(mosaic, f"{length_m} m", (24, 743), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)
    return mosaic


if __name__ == "__main__":
    lat, lon = 35.8277, 10.6388                                         # the Ribat of Sousse
    print(f"The Ribat of Sousse ({lat}, {lon}) on the map:\n")
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
        print("\nNorth-west corner of its zoom-17 tile:", tile_to_latlon(*t, 17))
