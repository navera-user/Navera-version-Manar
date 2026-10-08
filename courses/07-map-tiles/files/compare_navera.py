# Compares YOUR tile functions with NAVERA's own code:
#   day_pkg/day_pkg/local_matcher.py   tile_xy(), tile_px_to_latlon(), map_m_per_px()
#   day_pkg/day_pkg/prepare_area.py    tile_nw(), tile_center()
#   day_pkg/day_pkg/nodes/day_localizer.py   tile_center_latlon()  (the fix of the corner bug)
#   simulation_web/simulation_web/web_common.py   MBTilesReader (reads the map for the simulator)
#     python3 compare_navera.py
import logging
import os

from day_pkg import local_matcher, prepare_area
from day_pkg.nodes.day_localizer import tile_center_latlon
from simulation_web.web_common import MBTilesReader

from tiles_lab import MAP, latlon_to_tile, meters_per_pixel, pixel_to_latlon, read_tile, tile_to_latlon, tile_xy


def show(v, fmt):
    return "TODO" if v is None else fmt % tuple(v) if isinstance(v, (tuple, list)) else fmt % v


lat, lon = 35.8277, 10.6388
print("1) Ribat of Sousse: tile_xy() and meters_per_pixel(), zoom 13 to 19")
print(f"{'z':>2}  {'yours tile_xy':>28}  {'NAVERA tile_xy':>28}  {'your m/px':>9}  {'NAVERA':>9}")
for z in range(13, 20):
    mine, theirs = tile_xy(lat, lon, z), local_matcher.tile_xy(lat, lon, z)
    print(f"{z:>2}  {show(mine, '(%.6f, %.6f)'):>28}  {show(theirs, '(%.6f, %.6f)'):>28}"
          f"  {show(meters_per_pixel(lat, z), '%.5f'):>9}  {local_matcher.map_m_per_px(lat, z):9.5f}")

t = latlon_to_tile(lat, lon, 17)
if t is None:
    raise SystemExit("\nlatlon_to_tile() returns None: finish TODO 1-4 to see the rest")
x, y = t
print(f"\n2) Tile 17/{x}/{y}: north-west corner and centre")
print("   yours  NW    ", show(tile_to_latlon(x, y, 17), "(%.10f, %.10f)"))
print("   NAVERA tile_nw", "(%.10f, %.10f)" % prepare_area.tile_nw(x, y, 17))
print("   yours  centre", show(tile_to_latlon(x + 0.5, y + 0.5, 17), "(%.10f, %.10f)"))
print("   NAVERA tile_center         ", "(%.10f, %.10f)" % prepare_area.tile_center(x, y, 17))
print("   NAVERA tile_center_latlon  ", "(%.10f, %.10f)" % tile_center_latlon(f"tile_17_{x}_{y}.jpg"))

print("\n3) A global pixel -> lat/lon: your pixel_to_latlon(px, py, z, 0, 0) and NAVERA's tile_px_to_latlon()")
px, py = x * 256 + 100.25, y * 256 + 37.5
print("   yours ", show(pixel_to_latlon(px, py, 17, 0, 0), "(%.10f, %.10f)"))
print("   NAVERA", "(%.10f, %.10f)" % local_matcher.tile_px_to_latlon(px, py, 17))

if not os.path.exists(MAP):
    raise SystemExit(f"\n4) skipped: map data not found ({MAP}) — ask the teacher to connect the data disk")
reader = MBTilesReader(MAP, logging.getLogger("demo"))
a, b = read_tile(MAP, 17, x, y), reader.get(17, x, y)
print("\n4) The same tile read by your read_tile() and by the simulator's MBTilesReader:",
      "TODO" if a is None else ("identical bytes" if a == b else "DIFFERENT bytes!"), f"({len(b)} bytes)")
