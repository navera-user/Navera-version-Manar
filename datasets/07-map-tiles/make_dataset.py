#!/usr/bin/env python3
"""Builds sousse_small.mbtiles: a few tiles of the real NAVERA map (/data/map.mbtiles in the
sandbox, ~/navera_data_map.mbtiles on the host), so lesson 07's checks do not depend on the 10 GB file.

    python3 make_dataset.py [path/to/map.mbtiles]

Same schema as the big file (metadata + tiles, TMS rows). Tiles kept:
  around the Ribat of Sousse (35.8277, 10.6388): 3x3 tiles at z13-z16 and z18-z19, 5x5 at z17
  around Monastir marina (35.7795, 10.8320): 3x3 tiles at z17
The big map is opened read-only.
"""
import math
import os
import sqlite3
import sys
from urllib.parse import quote

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/navera_data_map.mbtiles")
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sousse_small.mbtiles")

SOUSSE = (35.8277, 10.6388)
MONASTIR = (35.7795, 10.8320)
BLOCKS = [(SOUSSE, z, 1) for z in (13, 14, 15, 16, 18, 19)] + [(SOUSSE, 17, 2), (MONASTIR, 17, 1)]


def tile_xy(lat, lon, z):
    n = 2 ** z
    r = math.radians(lat)
    return int((lon + 180.0) / 360.0 * n), int((1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n)


src = sqlite3.connect("file:" + quote(os.path.realpath(SRC)) + "?mode=ro", uri=True)
if os.path.exists(DST):
    os.remove(DST)
dst = sqlite3.connect(DST)
dst.execute("CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT)")
dst.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB, "
            "PRIMARY KEY (zoom_level, tile_column, tile_row))")
for name, value in src.execute("SELECT name, value FROM metadata"):
    if name == "name":
        value = "Sousse - small extract for NAVERA Academy lesson 07"
    if name == "estimated_size_mb":
        continue
    dst.execute("INSERT INTO metadata VALUES (?, ?)", (name, value))
count = 0
for (lat, lon), z, r in BLOCKS:
    x0, y0 = tile_xy(lat, lon, z)
    for y in range(y0 - r, y0 + r + 1):
        for x in range(x0 - r, x0 + r + 1):
            row = (2 ** z - 1) - y                     # XYZ y -> TMS row
            got = src.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                              (z, x, row)).fetchone()
            if got:
                dst.execute("INSERT OR IGNORE INTO tiles VALUES (?, ?, ?, ?)", (z, x, row, got[0]))
                count += 1
dst.commit()
dst.execute("VACUUM")
dst.close()
print(f"{count} tiles -> {DST} ({os.path.getsize(DST) / 1e6:.1f} MB)")
