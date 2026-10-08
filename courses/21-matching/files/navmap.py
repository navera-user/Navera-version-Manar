"""Small helpers to read the satellite map /data/map.mbtiles (you met them in lesson 7)."""
import math
import os
import sqlite3

import cv2
import numpy as np

MAP_PATH = "/data/map.mbtiles" if os.path.exists("/data/map.mbtiles") else os.path.expanduser("~/navera_data_map.mbtiles")
EQUATOR_M = 40075016.7
_conn = None


def _db():
    global _conn
    if _conn is None:
        if not os.path.exists(MAP_PATH):
            raise FileNotFoundError(f"map data not found ({MAP_PATH}) — ask the teacher to connect the data disk")
        _conn = sqlite3.connect("file:" + MAP_PATH + "?mode=ro", uri=True)
    return _conn


def read_tile(z, x, y):
    """One 256x256 tile (BGR) with XYZ numbering, or None if the map has no such tile."""
    row = _db().execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                        (z, x, (2 ** z - 1) - y)).fetchone()          # MBTiles rows are TMS: flipped
    if row is None:
        return None
    return cv2.imdecode(np.frombuffer(row[0], np.uint8), cv2.IMREAD_COLOR)


def latlon_to_pixel(lat, lon, z):
    """Global pixel (px, py) of (lat, lon) at zoom z (256 px per tile, Web Mercator)."""
    n = 2 ** z
    r = math.radians(lat)
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    return x * 256.0, y * 256.0


def pixel_to_latlon(px, py, z):
    """(lat, lon) of a global pixel at zoom z — the inverse of latlon_to_pixel."""
    n = 2 ** z
    x, y = px / 256.0, py / 256.0
    return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n)))), x / n * 360.0 - 180.0


def m_per_px(lat, z):
    """Ground size of one map pixel at this latitude and zoom, in meters."""
    return EQUATOR_M * math.cos(math.radians(lat)) / 2 ** z / 256.0


def map_patch(lat, lon, z, width, height):
    """A width x height BGR picture of the map centred on (lat, lon) at zoom z.
    Returns (image, (x0, y0)): (x0, y0) is the global pixel of the image's top-left corner,
    so image pixel (u, v) is global pixel (x0 + u, y0 + v)."""
    cx, cy = latlon_to_pixel(lat, lon, z)
    x0, y0 = int(round(cx - width / 2.0)), int(round(cy - height / 2.0))
    out = np.zeros((height, width, 3), np.uint8)
    for tx in range(x0 // 256, (x0 + width - 1) // 256 + 1):
        for ty in range(y0 // 256, (y0 + height - 1) // 256 + 1):
            t = read_tile(z, tx, ty)
            if t is None:
                continue
            # where this tile lands in the output
            ox, oy = tx * 256 - x0, ty * 256 - y0
            sx0, sy0 = max(0, -ox), max(0, -oy)
            ex, ey = min(256, width - ox), min(256, height - oy)
            out[oy + sy0:oy + ey, ox + sx0:ox + ex] = t[sy0:ey, sx0:ex]
    return out, (x0, y0)


def haversine_m(lat1, lon1, lat2, lon2):
    """Distance in meters between two points (lesson 6)."""
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
