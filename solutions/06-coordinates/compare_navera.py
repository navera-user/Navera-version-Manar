# Compares YOUR functions (geo_lab.py) with the ones inside NAVERA.
#     python3 compare_navera.py
import math

from geo_lab import PLACES, bearing, flat_en, flat_move, geodetic_to_enu, haversine
from navera_common.geo import dead_reckon, haversine_m    # ~/navera/navera_common/navera_common/geo.py
from day_pkg.vision_nav import _en, _move                  # ~/navera/day_pkg/day_pkg/vision_nav.py


def show(v, fmt):
    return "TODO" if v is None else fmt % tuple(v) if isinstance(v, (tuple, list)) else fmt % v


home = PLACES["Sousse (medina)"][:2]
print("1) Distances from Sousse: your haversine() against NAVERA's haversine_m()")
print(f"{'place':<24}{'yours (m)':>14}{'NAVERA (m)':>14}{'difference':>12}")
for name, (lat, lon, _h) in PLACES.items():
    mine, theirs = haversine(*home, lat, lon), haversine_m(*home, lat, lon)
    diff = "TODO" if mine is None else f"{abs(mine - theirs):.6f}"
    print(f"{name:<24}{show(mine, '%.3f'):>14}{theirs:14.3f}{diff:>12}")

print("\n2) Flat shortcut: your flat_en() against NAVERA's _en()   (points are (lat, lon) pairs)")
for name, (lat, lon, _h) in PLACES.items():
    mine, theirs = flat_en(lat, lon, *home), _en((lat, lon), home)
    print(f"{name:<24} yours {show(mine, '(%11.3f, %11.3f)')}   NAVERA ({theirs[0]:11.3f}, {theirs[1]:11.3f})")

print("\n3) Moving 500 m east and 300 m south: your flat_move() against NAVERA's _move()")
mine, theirs = flat_move(home[0], home[1], 500.0, -300.0), _move(home, 500.0, -300.0)
print("   yours ", show(mine, "(%.9f, %.9f)"))
print("   NAVERA (%.9f, %.9f)" % theirs)

print("\n4) NAVERA's dead_reckon(): fly 20 m/s for 600 s on bearing 12.8 deg (towards Rome)")
end = dead_reckon(home[0], home[1], 12.8, 20.0, 600.0)
print("   NAVERA lands at (%.6f, %.6f)" % end)
d, b = haversine(*home, *end), bearing(*home, *end)
print("   your haversine() says", show(d, "%.1f m"), " and your bearing() says", show(b, "%.2f deg"))
enu = geodetic_to_enu(end[0], end[1], 0.0, home[0], home[1], 0.0)
if enu is not None:
    print("   exact WGS84 ENU of that point: east %.1f m, north %.1f m (horizontal %.1f m)"
          % (enu[0], enu[1], math.hypot(enu[0], enu[1])))
    flown = math.hypot(enu[0], enu[1])
    print("   -> on the ellipsoid the spherical dead_reckon() covered %.1f m instead of 12 000 m (%+.2f %%)"
          % (flown, (flown - 12000.0) / 120.0))
