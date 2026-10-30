#!/usr/bin/env python3
"""make_dataset.py — teacher only. Builds datasets/07-map-tiles/sousse_small.mbtiles: a small extract of the
course's OpenStreetMap map of Sousse (~/academy-data/osm_sousse.mbtiles on the host, /data/map.mbtiles in the
sandbox), so mission 07's checks and NAVERA Lite's MAP_PATH fallback do not depend on the 1 GB file.

    python3 solutions/07-map-tiles/make_dataset.py [path/to/osm_sousse.mbtiles]

Same schema as the big file (metadata + tiles, TMS rows, JPEG). Deterministic: the tiles are copied byte for
byte in a fixed order, so the same source map gives the same tiles (check.py compares the student's bytes with
the ones it reads from this extract). Tiles kept:
  around the Ribat of Sousse (35.8277, 10.6388): 3x3 tiles at z13-z16 and z18-z19, 5x5 at z17
  around Port El Kantaoui marina (35.8930, 10.5965): 3x3 tiles at z17
The big map is opened read-only. Map data © OpenStreetMap contributors (ODbL): the attribution metadata is kept.
"""
import math
import os
import sqlite3
import sys
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/academy-data/osm_sousse.mbtiles")
DST = os.path.join(HERE, "..", "..", "datasets", "07-map-tiles", "sousse_small.mbtiles")

RIBAT = (35.8277, 10.6388)
KANTAOUI = (35.8930, 10.5965)
BLOCKS = [(RIBAT, z, 1) for z in (13, 14, 15, 16, 18, 19)] + [(RIBAT, 17, 2), (KANTAOUI, 17, 1)]
KEEP = ("type", "version", "format", "minzoom", "maxzoom", "altitude_min", "altitude_max", "altitude_zoom_map",
        "region", "attribution", "attribution_url", "attribution_html", "license", "source", "osm_data_date",
        "osm_pbf", "osm_pbf_sha256", "jpeg_quality", "scheme")


def tile_of(lat, lon, z):
    n = 2 ** z
    r = math.radians(lat)
    return int((lon + 180.0) / 360.0 * n), int((1.0 - math.asinh(math.tan(r)) / math.pi) / 2.0 * n)


def main():
    src = sqlite3.connect("file:" + quote(os.path.realpath(SRC)) + "?mode=ro", uri=True)
    meta = dict(src.execute("SELECT name, value FROM metadata"))
    dst_path = os.path.realpath(DST)
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    if os.path.exists(dst_path):
        os.remove(dst_path)
    dst = sqlite3.connect(dst_path)
    dst.execute("CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT)")
    dst.execute("CREATE TABLE tiles (zoom_level INTEGER NOT NULL, tile_column INTEGER NOT NULL, "
                "tile_row INTEGER NOT NULL, tile_data BLOB NOT NULL, "
                "PRIMARY KEY (zoom_level, tile_column, tile_row))")
    rows, wanted = [], set()
    for (lat, lon), z, r in BLOCKS:
        x0, y0 = tile_of(lat, lon, z)
        for y in range(y0 - r, y0 + r + 1):
            for x in range(x0 - r, x0 + r + 1):
                wanted.add((z, x, (2 ** z - 1) - y))            # XYZ y -> TMS row
    for z, x, row in sorted(wanted):
        got = src.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                          (z, x, row)).fetchone()
        if got:
            rows.append((z, x, row, bytes(got[0])))
    z17 = [(x, (2 ** 17 - 1) - row) for z, x, row, _ in rows if z == 17]
    west, east = (min(x for x, _ in z17) / 2 ** 17) * 360 - 180, ((max(x for x, _ in z17) + 1) / 2 ** 17) * 360 - 180
    lat_of = lambda y: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** 17))))
    north, south = lat_of(min(y for _, y in z17)), lat_of(max(y for _, y in z17) + 1)
    new = {"name": "Sousse - small extract of the course map (NAVERA Academy, mission 07)",
           "description": f"{len(rows)} tiles copied from the course's OpenStreetMap map of Sousse "
                         "(the Ribat of Sousse and Port El Kantaoui marina); bounds = the zoom-17 tiles",
           "bounds": f"{west:.4f},{south:.4f},{east:.4f},{north:.4f}", "center": "10.6388,35.8277,17"}
    for k in KEEP:
        if k in meta:
            new[k] = meta[k]
    for k, v in sorted(new.items()):
        assert "esri" not in v.lower(), k
        dst.execute("INSERT INTO metadata VALUES (?, ?)", (k, v))
    dst.executemany("INSERT INTO tiles VALUES (?, ?, ?, ?)", rows)
    dst.commit()
    dst.execute("VACUUM")
    dst.close()
    print(f"{len(rows)} of {len(wanted)} tiles -> {dst_path} ({os.path.getsize(dst_path) / 1e6:.2f} MB); "
          f"bounds (z17) {west:.4f},{south:.4f},{east:.4f},{north:.4f}")


if __name__ == "__main__":
    main()
