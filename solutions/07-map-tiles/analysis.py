# Lab 7 analysis: scales and zooms around the world, facts about NAVERA's map file, the corner bug.
# Uses YOUR functions of tiles_lab.py (finish TODO 1-10 first). Writes results.json.
#     python3 analysis.py                (about 20 s: it counts the tiles of the 10 GB map)
import json
import math
import os
import sqlite3

from tiles_lab import (MAP, TILE_PX, latlon_to_pixel, latlon_to_tile, meters_per_pixel, pixel_to_latlon,
                       tile_to_latlon, zoom_for_gsd)

PLACES = {"Quito": (-0.1807, -78.4678), "Singapore": (1.2834, 103.8607), "Mexico City": (19.4326, -99.1332),
          "Cape Town": (-33.9249, 18.4241), "Sydney": (-33.8568, 151.2153),
          "Sousse (NAVERA test map)": (35.8277, 10.6388), "London": (51.5007, -0.1246),
          "Reykjavik": (64.1417, -21.9266)}
CAMERA = {"altitude_m": 300.0, "hfov_deg": 84.0, "width_px": 1536}     # an example nadir camera
A, E2 = 6378137.0, 0.0066943799901414   # WGS84


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(min(1.0, a)))


def web_vs_ellipsoidal_km(lat):
    """Northing of EPSG:3857 (sphere formula on WGS84 latitudes) minus true ellipsoidal Mercator (EPSG:3395)."""
    e = math.sqrt(E2)
    return A * e * math.atanh(e * math.sin(math.radians(lat))) / 1000.0


for name, v in (("meters_per_pixel", meters_per_pixel(0.0, 0)), ("zoom_for_gsd", zoom_for_gsd(0.0, 1.0)),
                ("tile_to_latlon", tile_to_latlon(0, 0, 1)), ("latlon_to_pixel", latlon_to_pixel(0.0, 0.0, 1, 0, 0)),
                ("pixel_to_latlon", pixel_to_latlon(0.0, 0.0, 1, 0, 0)), ("latlon_to_tile", latlon_to_tile(0.0, 0.0, 1))):
    if v is None:
        raise SystemExit(f"{name}() still returns None: finish its TODO in tiles_lab.py first")

gsd = 2.0 * CAMERA["altitude_m"] * math.tan(math.radians(CAMERA["hfov_deg"]) / 2.0) / CAMERA["width_px"]
world = []
print(f"camera example: {CAMERA}, ground sample distance {gsd:.3f} m/px\n")
print(f"{'place':<26}{'lat':>8}{'m/px z17':>10}{'tile z17 (m)':>13}{'1/cos':>7}{'3857-3395 (km)':>15}{'zoom':>6}")
for name, (lat, lon) in PLACES.items():
    row = {"place": name, "lat": lat, "m_per_px_z17": round(meters_per_pixel(lat, 17), 4),
           "tile_width_z17_m": round(meters_per_pixel(lat, 17) * TILE_PX, 1),
           "scale_factor": round(1.0 / math.cos(math.radians(lat)), 4),
           "web_vs_ellipsoidal_mercator_km": round(web_vs_ellipsoidal_km(lat), 2),
           "zoom_for_camera": zoom_for_gsd(lat, gsd, 13, 19)}
    world.append(row)
    print(f"{name:<26}{lat:8.3f}{row['m_per_px_z17']:10.4f}{row['tile_width_z17_m']:13.1f}{row['scale_factor']:7.3f}"
          f"{row['web_vs_ellipsoidal_mercator_km']:15.2f}{row['zoom_for_camera']:6d}")

alt_zoom = {}
lat_m = PLACES["Singapore"][0]
for alt in (150, 200, 300, 500, 1000, 1500, 2000):
    g = 2.0 * alt * math.tan(math.radians(CAMERA["hfov_deg"]) / 2.0) / CAMERA["width_px"]
    alt_zoom[str(alt)] = zoom_for_gsd(lat_m, g, 13, 19)
print("\nSingapore, same camera: zoom_for_gsd() by flying height:", alt_zoom)

corner = {}
for name in ("Sousse (NAVERA test map)", "Singapore", "Reykjavik"):
    lat, lon = PLACES[name]
    x, y = latlon_to_tile(lat, lon, 17)
    nw, ce = tile_to_latlon(x, y, 17), tile_to_latlon(x + 0.5, y + 0.5, 17)
    corner[name] = round(haversine(*nw, *ce), 1)
print("\nNW corner -> centre of a zoom-17 tile (the size of the corner bug):", corner)

worst = 0.0
for k in range(200):                                               # pixel <-> lat/lon round trip
    lat, lon = -70.0 + 140.0 * ((k * 37) % 200) / 200.0, -170.0 + 340.0 * ((k * 91) % 200) / 200.0
    x, y = latlon_to_tile(lat, lon, 18)
    px, py = latlon_to_pixel(lat, lon, 18, x - 1, y - 1)
    la, lo = pixel_to_latlon(px, py, 18, x - 1, y - 1)
    worst = max(worst, abs(la - lat), abs(lo - lon))
print(f"pixel <-> lat/lon round trip over 200 points around the world: worst error {worst:.2e} degrees")

db = sqlite3.connect("file:" + MAP + "?mode=ro", uri=True)
meta = dict(db.execute("SELECT name, value FROM metadata"))
counts = {str(z): n for z, n in db.execute("SELECT zoom_level, COUNT(*) FROM tiles GROUP BY zoom_level")}
page_size = db.execute("PRAGMA page_size").fetchone()[0]
page_count = db.execute("PRAGMA page_count").fetchone()[0]
size = os.path.getsize(MAP)
mapinfo = {"file_bytes": size, "file_gb": round(size / 1e9, 2), "page_size": page_size, "page_count": page_count,
           "estimated_size_mb_in_metadata": int(meta.get("estimated_size_mb", 0)),
           "tiles_per_zoom": counts, "total_tiles": sum(counts.values()),
           "mean_bytes_per_tile": round(size / sum(counts.values()))}
print(f"\nmap file: {size} bytes = {mapinfo['file_gb']} GB ({page_count} pages x {page_size} B); "
      f"metadata says estimated_size_mb = {mapinfo['estimated_size_mb_in_metadata']}")
print("tiles per zoom:", counts, " total", mapinfo["total_tiles"])
print("the map's own altitude_zoom_map:", meta.get("altitude_zoom_map"))

results = {"camera": dict(CAMERA, gsd_m=round(gsd, 4)), "world": world, "corner_bug_m": corner,
           "pixel_round_trip_max_error_deg": worst, "singapore_zoom_by_altitude": alt_zoom, "map": mapinfo}
with open("results.json", "w") as f:
    json.dump(results, f, indent=1)
print("\nSaved results.json")
