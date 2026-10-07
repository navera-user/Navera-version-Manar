# Reads ONE tile with YOUR functions and saves it as a PNG picture. Usage:
#     python3 get_tile.py LAT LON ZOOM            e.g.  python3 get_tile.py 35.8277 10.6388 19
#     python3 get_tile.py LAT LON ZOOM --map /data/academy/07-map-tiles/sousse_small.mbtiles
import sys

import cv2

from tiles_lab import MAP, decode, latlon_to_tile, meters_per_pixel, read_tile, tile_to_latlon

args = sys.argv[1:]
path = MAP
if "--map" in args:
    i = args.index("--map")
    path = args[i + 1]
    del args[i:i + 2]
if len(args) != 3:
    raise SystemExit("usage: python3 get_tile.py LAT LON ZOOM")
lat, lon, z = float(args[0]), float(args[1]), int(args[2])

t = latlon_to_tile(lat, lon, z)
if t is None:
    raise SystemExit("latlon_to_tile() returns None: finish TODO 1 and TODO 2")
x, y = t
print(f"({lat}, {lon}) is in tile z={z} x={x} y={y}   (TMS row in the file: {2 ** z - 1 - y})")
nw = tile_to_latlon(x, y, z)
if nw is not None:
    print(f"tile north-west corner: ({nw[0]:.6f}, {nw[1]:.6f})")
mpp = meters_per_pixel(lat, z)
if mpp is not None:
    print(f"one pixel = {mpp:.3f} m, the tile is {256 * mpp:.0f} m wide")
data = read_tile(path, z, x, y)
if data is None:
    raise SystemExit("read_tile() returned None: TODO 5 not done, or this tile is not in the map")
print(f"read {len(data)} bytes, starting with {data[:3]!r} (a JPEG picture always starts with b'\\xff\\xd8\\xff')")
out = f"tile_{z}_{x}_{y}.png"
cv2.imwrite(out, decode(data))
print(f"saved {out} — click it in the file list to see it.")
