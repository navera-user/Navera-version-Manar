# Compares YOUR tile functions with NAVERA's own (day_pkg/day_pkg/local_matcher.py and
# day_pkg/day_pkg/prepare_area.py), and YOUR read_tile() with the simulator's MBTilesReader.
#     python3 compare_navera.py
import logging

from day_pkg import local_matcher, prepare_area
from simulation_web.web_common import MBTilesReader

from tiles_lab import MAP, latlon_to_tile, meters_per_pixel, read_tile, tile_to_latlon, tile_xy

lat, lon = 35.8277, 10.6388
print("Ribat of Sousse, zoom 13 to 19")
print(f"{'z':>2}  {'your tile_xy':>26}  {'NAVERA tile_xy':>26}  {'your m/px':>9}  {'NAVERA':>9}")
for z in range(13, 20):
    mine, theirs = tile_xy(lat, lon, z), local_matcher.tile_xy(lat, lon, z)
    m = "TODO" if mine is None else f"({mine[0]:.3f}, {mine[1]:.3f})"
    mpp = meters_per_pixel(lat, z)
    t = f"({theirs[0]:.3f}, {theirs[1]:.3f})"
    print(f"{z:>2}  {m:>26}  {t:>26}  {'TODO' if mpp is None else f'{mpp:.4f}':>9}"
          f"  {local_matcher.map_m_per_px(lat, z):9.4f}")

t = latlon_to_tile(lat, lon, 17)
if t is not None:
    x, y = t
    print("\nNorth-west corner of tile", (17, x, y))
    print("  yours :", tile_to_latlon(x, y, 17))
    print("  NAVERA:", prepare_area.tile_nw(x, y, 17))
    print("  centre (NAVERA prepare_area.tile_center):", prepare_area.tile_center(x, y, 17))
    reader = MBTilesReader(MAP, logging.getLogger("demo"))
    a, b = read_tile(MAP, 17, x, y), reader.get(17, x, y)
    print("\nSame tile read by your read_tile() and by NAVERA's MBTilesReader:",
          "TODO" if a is None else ("identical bytes" if a == b else "DIFFERENT bytes!"), f"({len(b)} bytes)")
