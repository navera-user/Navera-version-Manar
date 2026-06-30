import sqlite3, os, math
from PIL import Image
import io, csv

MBTILES  = "/workspaces/isaac_ros-dev/sousse_satellite.mbtiles"
OUT_DIR  = "/workspaces/isaac_ros-dev/day_pkg/day_pkg/dataset/images"
CSV_PATH = "/workspaces/isaac_ros-dev/day_pkg/day_pkg/dataset/dataset.csv"

def tile_to_latlon(x, y, z):
    n = 2 ** z
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    return math.degrees(lat_rad), lon

def latlon_to_tile(lat, lon, z):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y

def extract(zoom=17, bbox=None, progress_cb=None):
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = sqlite3.connect(MBTILES)
    cur  = conn.cursor()
    if bbox:
        min_lat, max_lat, min_lon, max_lon = bbox
        x_min, y_max = latlon_to_tile(min_lat, min_lon, zoom)
        x_max, y_min = latlon_to_tile(max_lat, max_lon, zoom)
        cur.execute("""SELECT tile_column, tile_row, tile_data FROM tiles
            WHERE zoom_level=? AND tile_column BETWEEN ? AND ?
            AND tile_row BETWEEN ? AND ?""",
            (zoom, x_min, x_max, y_min, y_max))
    else:
        cur.execute("SELECT tile_column, tile_row, tile_data FROM tiles WHERE zoom_level=?", (zoom,))
    rows = cur.fetchall()
    conn.close()
    print(f"Found {len(rows)} tiles")
    records = []
    for i, (x, y, data) in enumerate(rows):
        y_tms = (2**zoom - 1) - y
        lat, lon = tile_to_latlon(x, y_tms, zoom)
        fname = f"tile_{zoom}_{x}_{y}.jpg"
        fpath = os.path.join(OUT_DIR, fname)
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.save(fpath, "JPEG", quality=85)
        records.append({"filename": fname, "lat": lat, "lon": lon})
        if progress_cb: progress_cb(i+1, len(rows))
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["filename","lat","lon"])
        w.writeheader()
        w.writerows(records)
    print(f"Extracted {len(records)} tiles to {OUT_DIR}")
    print(f"CSV saved to {CSV_PATH}")
    return len(records)

if __name__ == "__main__":
    extract(zoom=17)
