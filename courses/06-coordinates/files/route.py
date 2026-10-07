# Reads route.csv, prints every leg of the route and draws it in meters (route.png).
# It uses YOUR functions from geo_lab.py: finish the TODOs there first.
#     python3 route.py
import csv
import warnings

import matplotlib
matplotlib.use("Agg")              # no window: we save a picture instead
warnings.filterwarnings("ignore", message="Unable to import Axes3D")   # a harmless warning of this computer
import matplotlib.pyplot as plt

from geo_lab import bearing, distance, route_length, to_local_xy

names, points = [], []
with open("route.csv") as f:
    for row in csv.DictReader(f):
        names.append(row["name"])
        points.append((float(row["lat"]), float(row["lon"])))

home_lat, home_lon = points[0]
print(f"{len(points)} points, home = {names[0]} ({home_lat}, {home_lon})\n")
print(f"{'leg':<32}{'length (m)':>12}{'bearing':>9}")
for i in range(len(points) - 1):
    (a, b), (c, d) = points[i], points[i + 1]
    dist, brg = distance(a, b, c, d), bearing(a, b, c, d)
    if dist is None or brg is None:
        raise SystemExit("distance() or bearing() still returns None: finish TODO 1 and TODO 2 in geo_lab.py")
    print(f"{names[i] + ' -> ' + names[i + 1]:<32}{dist:12.1f}{brg:8.1f}°")

total = route_length(points)
if total is None:
    raise SystemExit("route_length() still returns None: finish TODO 5 in geo_lab.py")
print(f"\nTotal length: {total:.1f} m  ({total / 1000:.2f} km)")
print(f"At 20 m/s a drone flies it in {total / 20 / 60:.1f} minutes.")

xy = [to_local_xy(lat, lon, home_lat, home_lon) for lat, lon in points]
if None in xy:
    raise SystemExit("to_local_xy() still returns None: finish TODO 3 in geo_lab.py")
east = [p[0] for p in xy]
north = [p[1] for p in xy]
plt.figure(figsize=(6, 6))
plt.plot(east, north, "-o", color="#0b6e8a")
for name, e, n in zip(names, east, north):
    plt.annotate(name, (e, n), textcoords="offset points", xytext=(6, 6), fontsize=8)
plt.plot([0], [0], "r*", markersize=15, label="home (0, 0)")
plt.axis("equal")                  # 1 m east = 1 m north on the picture
plt.grid(True, alpha=0.3)
plt.xlabel("east (m)")
plt.ylabel("north (m)")
plt.title(f"The route in a local frame — {total / 1000:.2f} km")
plt.legend()
plt.savefig("route.png", dpi=90, bbox_inches="tight")
print("Saved route.png — click it in the file list to see it.")
