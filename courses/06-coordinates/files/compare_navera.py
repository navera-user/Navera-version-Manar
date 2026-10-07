# Compares YOUR functions (geo_lab.py) with the ones inside NAVERA.
#     python3 compare_navera.py
from geo_lab import PLACES, distance, from_local_xy, to_local_xy
from navera_common.geo import haversine_m        # ~/navera/navera_common/navera_common/geo.py
from day_pkg.vision_nav import _en, _move          # ~/navera/day_pkg/day_pkg/vision_nav.py

home = PLACES["Ribat of Sousse"]
print("Distances from the Ribat of Sousse")
print(f"{'place':<25}{'yours (m)':>12}{'NAVERA (m)':>12}{'difference':>12}")
for name, (lat, lon) in PLACES.items():
    mine = distance(home[0], home[1], lat, lon)
    theirs = haversine_m(home[0], home[1], lat, lon)
    diff = "TODO" if mine is None else f"{abs(mine - theirs):.3f}"
    print(f"{name:<25}{'TODO' if mine is None else f'{mine:.1f}':>12}{theirs:12.1f}{diff:>12}")

print("\nLocal frame (east, north) in meters")
for name, (lat, lon) in PLACES.items():
    mine = to_local_xy(lat, lon, home[0], home[1])
    theirs = _en((lat, lon), home)
    m = "TODO" if mine is None else f"({mine[0]:9.1f}, {mine[1]:9.1f})"
    print(f"{name:<25} yours {m}   NAVERA ({theirs[0]:9.1f}, {theirs[1]:9.1f})")

mine = from_local_xy(500.0, -300.0, home[0], home[1])
theirs = _move(home, 500.0, -300.0)
print("\n500 m east and 300 m south of home:")
print("  yours ", "TODO" if mine is None else f"({mine[0]:.7f}, {mine[1]:.7f})")
print(f"  NAVERA ({theirs[0]:.7f}, {theirs[1]:.7f})")
