# Reads ONE tile with YOUR functions and saves it as a PNG picture. Usage:
#     python3 get_tile.py LAT LON ZOOM            e.g.  python3 get_tile.py 35.8277 10.6388 19
#     python3 get_tile.py LAT LON ZOOM --map /data/academy/07-map-tiles/sousse_small.mbtiles
import os
import sys

import cv2

from tiles_lab import MAP, TILE_PX, decode, latlon_to_tile, meters_per_pixel, read_tile, tile_to_latlon

args = sys.argv[1:]
path = MAP
if "--map" in args:
    i = args.index("--map")
    path = args[i + 1]
    del args[i:i + 2]
if len(args) != 3:
    raise SystemExit("usage: python3 get_tile.py LAT LON ZOOM")
lat, lon, z = float(args[0]), float(args[1]), int(args[2])
if not os.path.exists(path):
    raise SystemExit(f"map data not found ({path}) — ask the teacher to connect the data disk "
                     "(or try the small map: --map /data/academy/07-map-tiles/sousse_small.mbtiles)")

t = latlon_to_tile(lat, lon, z)
if t is None:
    raise SystemExit("latlon_to_tile() returns None: finish TODO 1-4 first")
x, y = t
print(f"({lat}, {lon}) is in tile z={z} x={x} y={y}   (TMS row in the file: {2 ** z - 1 - y})")
nw, ce = tile_to_latlon(x, y, z), tile_to_latlon(x + 0.5, y + 0.5, z)
if nw is not None:
    print(f"tile north-west corner: ({nw[0]:.7f}, {nw[1]:.7f})   centre: ({ce[0]:.7f}, {ce[1]:.7f})")
mpp = meters_per_pixel(lat, z)
if mpp is not None:
    print(f"one pixel = {mpp:.3f} m, the tile is {TILE_PX * mpp:.0f} m wide")
data = read_tile(path, z, x, y)
if data is None:
    raise SystemExit("read_tile() returned None: TODO 8 not done, or this tile is not in the map "
                     "(NAVERA's map covers zoom 13-19, longitudes 10.3-10.9 E, latitudes 35.55-36.1 N)")
print(f"read {len(data)} bytes, starting with {data[:3]!r} (a JPEG file always starts with b'\\xff\\xd8\\xff')")
out = f"tile_{z}_{x}_{y}.png"
cv2.imwrite(out, decode(data))
print(f"saved {out} — click it in the file list to see it.")
