# Builds a mosaic of tiles around a point, marks the point, the centre tile's NW corner and centre,
# and saves mosaic.png. Usage:
#     python3 mosaic.py LAT LON ZOOM [--radius 1]      e.g.  python3 mosaic.py 35.8277 10.6388 17
#     python3 mosaic.py LAT LON ZOOM --map /data/academy/07-map-tiles/sousse_small.mbtiles
#     python3 mosaic.py LAT LON ZOOM --out other.png   (write another file instead of mosaic.png)
import sys

import cv2

from tiles_lab import (MAP, TILE_PX, build_mosaic, latlon_to_pixel, latlon_to_tile, meters_per_pixel,
                       pixel_to_latlon, tile_to_latlon)

args = sys.argv[1:]
path, radius, out_png = MAP, 1, "mosaic.png"
for flag in ("--map", "--radius", "--out"):
    if flag in args:
        i = args.index(flag)
        if flag == "--map":
            path = args[i + 1]
        elif flag == "--out":
            out_png = args[i + 1]
        else:
            radius = int(args[i + 1])
        del args[i:i + 2]
if len(args) != 3:
    raise SystemExit("usage: python3 mosaic.py LAT LON ZOOM [--radius R] [--map FILE] [--out FILE.png]")
lat, lon, z = float(args[0]), float(args[1]), int(args[2])
for name, result in (("latlon_to_tile", latlon_to_tile(lat, lon, z)), ("meters_per_pixel", meters_per_pixel(lat, z)),
                     ("latlon_to_pixel", latlon_to_pixel(lat, lon, z, 0, 0)),
                     ("pixel_to_latlon", pixel_to_latlon(0.0, 0.0, z, 0, 0))):
    if result is None:
        raise SystemExit(f"{name}() returns None: finish its TODO first")

img, x0, y0 = build_mosaic(path, lat, lon, z, radius)
size = img.shape[1]
for k in range(1, 2 * radius + 1):                                  # thin white lines between tiles
    img[k * TILE_PX, :] = (255, 255, 255)
    img[:, k * TILE_PX] = (255, 255, 255)


def mark(la, lo, colour, r):
    px, py = latlon_to_pixel(la, lo, z, x0, y0)
    p = (int(round(px)), int(round(py)))
    cv2.circle(img, p, r, colour, 2)
    cv2.line(img, (p[0] - r - 8, p[1]), (p[0] + r + 8, p[1]), colour, 1)
    cv2.line(img, (p[0], p[1] - r - 8), (p[0], p[1] + r + 8), colour, 1)
    return px, py


tx, ty = latlon_to_tile(lat, lon, z)
mark(*tile_to_latlon(tx, ty, z), (0, 220, 255), 6)                 # yellow: NW corner of the centre tile
mark(*tile_to_latlon(tx + 0.5, ty + 0.5, z), (60, 200, 60), 6)     # green: centre of the centre tile
px, py = mark(lat, lon, (0, 0, 255), 12)                            # red: the point
back = pixel_to_latlon(px, py, z, x0, y0)
mpp = meters_per_pixel(lat, z)
length_m = next(L for L in (5000, 2000, 1000, 500, 200, 100, 50, 20, 10, 5) if L / mpp <= 0.4 * size)
bar = int(round(length_m / mpp))
cv2.rectangle(img, (14, size - 34), (30 + bar, size - 8), (255, 255, 255), -1)
cv2.line(img, (22, size - 20), (22 + bar, size - 20), (0, 0, 0), 3)
cv2.putText(img, f"{length_m} m", (24, size - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 1)
cv2.imwrite(out_png, img)
print(f"top-left tile ({x0}, {y0}), centre tile ({tx}, {ty}); the point is at pixel ({px:.1f}, {py:.1f})")
print(f"pixel -> lat/lon gives back ({back[0]:.8f}, {back[1]:.8f})")
print(f"the mosaic covers {size * mpp:.0f} m x {size * mpp:.0f} m ({mpp:.3f} m per pixel)")
print("red = the point, yellow = NW corner of its tile, green = centre of its tile")
print(f"saved {out_png} — click it in the file list to see it.")
