#!/usr/bin/env python3
"""A UAV-VisLoc area rebuilt from REAL Sentinel-2 L2A imagery (10 m), for uavvisloc_eval.py.

    python3 navera_tools/bench/sentinel2_area.py <area dir> <out area dir> --date 2023-10-19 [--max-cloud 5]

The tiles of <area dir>/images (tile_17_x_y.jpg) are fetched again from Sentinel-2 through the
product path (day_pkg.tile_sources.fetch_tiles, source "sentinel2_l2a": earth-search STAC +
AWS open-data COGs, no account) into <out>/map.mbtiles (licence-labelled), then written as
<out>/images/tile_17_x_y.jpg. Tiles Sentinel-2 cannot fill (no data) are left out.
"""
import argparse
import json
import os
import re
import sqlite3

from day_pkg.tile_sources import fetch_tiles, read_map_info

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("area")
ap.add_argument("out")
ap.add_argument("--date", required=True, help="YYYY-MM-DD or YYYY-MM-DD/YYYY-MM-DD")
ap.add_argument("--max-cloud", type=float, default=5.0)
ap.add_argument("--max-scenes", type=int, default=4)
a = ap.parse_args()
tiles = sorted((int(m.group(1)), int(m.group(2))) for f in os.listdir(os.path.join(a.area, "images"))
               if (m := re.fullmatch(r"tile_17_(\d+)_(\d+)\.jpg", f)))
os.makedirs(os.path.join(a.out, "images"), exist_ok=True)
mb = os.path.join(a.out, "map.mbtiles")
r = fetch_tiles(tiles, 17, "sentinel2_l2a", mb, date=a.date, max_cloud=a.max_cloud, max_scenes=a.max_scenes,
                progress=lambda s, d, t: print(json.dumps({"stage": s, "done": d, "total": t}), flush=True))
con = sqlite3.connect(mb)
n = 2 ** 17
for x, row, data in con.execute("SELECT tile_column, tile_row, tile_data FROM tiles WHERE zoom_level=17"):
    with open(os.path.join(a.out, "images", f"tile_17_{x}_{n - 1 - row}.jpg"), "wb") as f:
        f.write(data)
con.close()
print(json.dumps({k: v for k, v in r.items()}))
print(json.dumps(read_map_info(mb)))
