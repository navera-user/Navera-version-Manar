# Builds a 3 x 3 mosaic of tiles around a point, marks the point, saves mosaic.png. Usage:
#     python3 mosaic.py LAT LON ZOOM            e.g.  python3 mosaic.py 35.8277 10.6388 17
#     python3 mosaic.py LAT LON ZOOM --map /data/academy/07-map-tiles/sousse_small.mbtiles
import sys

import cv2

from tiles_lab import MAP, build_mosaic, latlon_to_tile, meters_per_pixel, pixel_in_mosaic

args = sys.argv[1:]
path = MAP
if "--map" in args:
    i = args.index("--map")
    path = args[i + 1]
    del args[i:i + 2]
if len(args) != 3:
    raise SystemExit("usage: python3 mosaic.py LAT LON ZOOM")
lat, lon, z = float(args[0]), float(args[1]), int(args[2])
for name, result in (("latlon_to_tile", latlon_to_tile(lat, lon, z)), ("meters_per_pixel", meters_per_pixel(lat, z)),
                     ("pixel_in_mosaic", pixel_in_mosaic(lat, lon, z))):
    if result is None:
        raise SystemExit(f"{name}() returns None: finish its TODO first")
img = build_mosaic(path, lat, lon, z)
px, py = pixel_in_mosaic(lat, lon, z)
mpp = meters_per_pixel(lat, z)
print(f"centre tile: {latlon_to_tile(lat, lon, z)}, the point is at pixel ({px:.1f}, {py:.1f}) of the mosaic")
print(f"the mosaic covers {768 * mpp:.0f} m x {768 * mpp:.0f} m ({mpp:.3f} m per pixel)")
cv2.imwrite("mosaic.png", img)
print("saved mosaic.png — click it in the file list to see it.")
