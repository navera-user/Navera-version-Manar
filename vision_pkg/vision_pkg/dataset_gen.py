#!/usr/bin/env python3
"""
dataset_gen.py  ──  NAVERA · Fast BBox Tile Collector
══════════════════════════════════════════════════════
Collecte les tuiles MBTiles BRUTES dans le bbox — pas de mosaïques,
pas d'overlap, structure plate unique.

Structure de sortie :
    precollected/
    ├── images/
    │   ├── z17_35.8274_10.6310.jpg   (256×256px, tuile brute)
    │   └── ...
    └── metadata.csv   → lat,lon,zoom,filename,tile_x,tile_y

Perf : ~736 tuiles pour un bbox 4km → < 2 secondes.
"""

import math, time, csv, sqlite3, threading, zlib, io, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional, Callable

try:
    from PIL import Image
    import numpy as np
except ImportError:
    raise ImportError("pip install Pillow numpy")


# ══════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════

N_WORKERS    = 16   # threads pour extraction MBTiles (I/O bound)
JPEG_QUALITY = 92
TILE_SIZE_PX = 256

ALTITUDE_ZOOM_MAP = [
    (100,  18), (200, 18), (400, 17), (600, 17),
    (900,  16), (1500, 15), (9999, 14),
]

def altitude_to_zoom(alt_m: int) -> int:
    for max_alt, zoom in ALTITUDE_ZOOM_MAP:
        if alt_m <= max_alt:
            return zoom
    return 14


# ══════════════════════════════════════════════════════════════════════
#  RESULT
# ══════════════════════════════════════════════════════════════════════

@dataclass
class DatasetResult:
    success:      bool
    output_dir:   Path
    images_dir:   Path
    csv_path:     Path
    total_images: int
    zoom:         int
    altitude_m:   int
    time_ms:      float
    error:        Optional[str] = None
    images:       list = field(default_factory=list)
    # Compat fields
    resolution_mpp:  float = 0.24
    search_radius_m: float = 800.0
    center_lat:      float = 0.0
    center_lon:      float = 0.0


# ══════════════════════════════════════════════════════════════════════
#  TILE MATH
# ══════════════════════════════════════════════════════════════════════

def latlon_to_tile(lat: float, lon: float, z: int):
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_r) + 1.0 / math.cos(lat_r)) / math.pi) / 2.0 * n)
    return x, y

def tile_center_latlon(x: int, y: int, z: int):
    n = 2 ** z
    lon = (x + 0.5) / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / n))))
    return lat, lon

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# ══════════════════════════════════════════════════════════════════════
#  MBTILES READER  (thread-safe)
# ══════════════════════════════════════════════════════════════════════

class MBTilesReader:
    def __init__(self, path: str):
        self.path = str(path)
        self._local = threading.local()

    def _conn(self):
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.execute("PRAGMA cache_size=4000")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("PRAGMA mmap_size=268435456")
            self._local.conn = conn
            self._local.cur  = conn.cursor()
        return self._local.cur

    def get_tile_bytes(self, x: int, y: int, z: int) -> Optional[bytes]:
        y_tms = (2 ** z - 1) - y
        try:
            cur = self._conn()
            cur.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (z, x, y_tms)
            )
            row = cur.fetchone()
            if not row:
                return None
            data = row[0]
            if isinstance(data, bytes) and len(data) >= 2 and data[:2] == b'\x1f\x8b':
                data = zlib.decompress(data, 15 + 32)
            return bytes(data) if not isinstance(data, bytes) else data
        except Exception:
            return None

    def get_bounds(self):
        try:
            cur = self._conn()
            cur.execute("SELECT value FROM metadata WHERE name='bounds'")
            row = cur.fetchone()
            if row:
                return tuple(float(v) for v in row[0].split(','))
        except Exception:
            pass
        return (10.3, 35.55, 10.9, 36.1)

    def get_zoom_range(self):
        try:
            cur = self._conn()
            cur.execute("SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles")
            row = cur.fetchone()
            if row:
                return int(row[0]), int(row[1])
        except Exception:
            pass
        return (13, 19)


# ══════════════════════════════════════════════════════════════════════
#  MAIN : generate_dataset
# ══════════════════════════════════════════════════════════════════════

def generate_dataset(
    lat:             float,
    lon:             float,
    altitude_m:      int,
    mbtiles_path:    str,
    output_dir:      Optional[str]  = None,
    search_radius_m: Optional[float] = None,
    bbox:            Optional[dict]  = None,
    min_coverage_pct: float          = 0.0,
    verbose:         bool            = True,
    progress_cb:     Optional[Callable[[int, int], None]] = None,
) -> DatasetResult:
    """
    Collecte les tuiles MBTiles brutes dans le bbox.
    
    bbox format: {minLat, maxLat, minLng, maxLng}
    Si bbox absent → cercle autour de (lat, lon) avec search_radius_m.
    """
    t_start = time.time()
    zoom    = altitude_to_zoom(altitude_m)

    # ── Output dirs ────────────────────────────────────────────────────
    if output_dir is None:
        output_dir = f"dataset_z{zoom}"
    out_path   = Path(output_dir)
    images_dir = out_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_path / "metadata.csv"

    reader = MBTilesReader(mbtiles_path)
    z_min, z_max = reader.get_zoom_range()
    zoom = max(z_min, min(z_max, zoom))

    # ── Déterminer le bbox ─────────────────────────────────────────────
    if bbox:
        lat_min = bbox['minLat'];  lat_max = bbox['maxLat']
        lon_min = bbox['minLng'];  lon_max = bbox['maxLng']
    else:
        if search_radius_m is None:
            footprint = altitude_m * 0.24 * 640 / 1000
            search_radius_m = max(footprint * 3, altitude_m * 2)
        R = search_radius_m
        dlat = R / 111_000
        dlon = R / (111_000 * math.cos(math.radians(lat)))
        lat_min = lat - dlat;  lat_max = lat + dlat
        lon_min = lon - dlon;  lon_max = lon + dlon

    center_lat = (lat_min + lat_max) / 2
    center_lon = (lon_min + lon_max) / 2

    # ── Grille de tuiles (N→S, W→E) ────────────────────────────────────
    x_min, y_min = latlon_to_tile(lat_max, lon_min, zoom)   # NW
    x_max, y_max = latlon_to_tile(lat_min, lon_max, zoom)   # SE
    x_min = max(0, x_min - 1);  y_min = max(0, y_min - 1)
    x_max = x_max + 1;          y_max = y_max + 1

    tasks = []
    for y in range(y_min, y_max + 1):
        for x in range(x_min, x_max + 1):
            clat, clon = tile_center_latlon(x, y, zoom)
            tasks.append((x, y, clat, clon))

    total = len(tasks)
    if verbose:
        print(f"\n{'═'*60}")
        print(f"  NAVERA Dataset Gen — Raw MBTiles Tiles")
        print(f"{'═'*60}")
        print(f"  BBox : lat[{lat_min:.4f}→{lat_max:.4f}] lon[{lon_min:.4f}→{lon_max:.4f}]")
        print(f"  Zoom : {zoom}  |  Tuiles : {x_max-x_min+1} × {y_max-y_min+1} = {total}")
        print(f"  Threads : {N_WORKERS}")
        print(f"{'─'*60}")

    # ── Extraction parallèle ────────────────────────────────────────────
    rows     = []
    rows_lock = threading.Lock()
    saved    = [0]

    def process_tile(args):
        x, y, clat, clon = args
        fname = f"z{zoom}_{clat:.6f}_{clon:.6f}.jpg"
        fpath = images_dir / fname

        # Skip si déjà présent
        if fpath.exists():
            with rows_lock:
                rows.append((clat, clon, zoom, fname, x, y))
                saved[0] += 1
                if progress_cb: progress_cb(saved[0], total)
            return fname

        data = reader.get_tile_bytes(x, y, zoom)
        if data is None:
            return None

        # Écrire directement les bytes JPEG (format natif MBTiles)
        try:
            # Vérifier que c'est une image valide et la re-sauvegarder en JPEG propre
            img = Image.open(io.BytesIO(data))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(str(fpath), "JPEG", quality=JPEG_QUALITY, optimize=True)
            img.close()
        except Exception:
            # Si PIL échoue, écrire les bytes bruts directement
            fpath.write_bytes(data)

        with rows_lock:
            rows.append((clat, clon, zoom, fname, x, y))
            saved[0] += 1
            if progress_cb: progress_cb(saved[0], total)
            if verbose and saved[0] % 100 == 0:
                elapsed = time.time() - t_start
                rate = saved[0] / elapsed
                eta  = (total - saved[0]) / max(rate, 1)
                print(f"  [{saved[0]:>5}/{total}]  {rate:.0f} tiles/s  ETA: {eta:.0f}s")
        return fname

    with ThreadPoolExecutor(max_workers=N_WORKERS) as pool:
        list(pool.map(process_tile, tasks))

    # ── Trier N→S, W→E ────────────────────────────────────────────────
    rows.sort(key=lambda r: (-r[0], r[1]))

    # ── Écrire metadata.csv ────────────────────────────────────────────
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["lat", "lon", "zoom", "filename",
                         "tile_x", "tile_y",
                         # Colonnes compat avec gps_localizer ancien format
                         "center_lat", "center_lon"])
        for r in rows:
            writer.writerow([f"{r[0]:.8f}", f"{r[1]:.8f}", r[2], r[3],
                              r[4], r[5], f"{r[0]:.8f}", f"{r[1]:.8f}"])

    elapsed = (time.time() - t_start) * 1000
    n_ok = len(rows)

    if verbose:
        print(f"{'═'*60}")
        print(f"  ✅ {n_ok} tuiles extraites en {elapsed:.0f}ms ({elapsed/1000:.1f}s)")
        print(f"  📁 {out_path}")
        print(f"{'═'*60}\n")

    return DatasetResult(
        success=True, output_dir=out_path, images_dir=images_dir,
        csv_path=csv_path, total_images=n_ok, zoom=zoom,
        altitude_m=altitude_m, time_ms=elapsed,
        images=[{"filename": r[3], "lat": r[0], "lon": r[1]} for r in rows],
        center_lat=center_lat, center_lon=center_lon,
        search_radius_m=search_radius_m or 800,
    )


# ══════════════════════════════════════════════════════════════════════
#  RADIUS FILTER (utilisé par gps_localizer)
# ══════════════════════════════════════════════════════════════════════

def get_images_in_radius(metadata_csv, center_lat, center_lon, radius_m):
    delta_lat = radius_m / 111_000
    delta_lon = radius_m / (111_000 * math.cos(math.radians(center_lat)))
    lat_min = center_lat - delta_lat;  lat_max = center_lat + delta_lat
    lon_min = center_lon - delta_lon;  lon_max = center_lon + delta_lon

    candidates = []
    with open(metadata_csv, 'r', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            lat = float(row.get('lat', row.get('center_lat', 0)))
            lon = float(row.get('lon', row.get('center_lon', 0)))
            if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
                continue
            if haversine_m(center_lat, center_lon, lat, lon) <= radius_m:
                candidates.append({
                    "lat": lat, "lon": lon,
                    "filename": row['filename'],
                })
    return candidates


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mbtiles", required=True)
    parser.add_argument("--output",  required=True)
    parser.add_argument("--altitude",type=int, default=400)
    parser.add_argument("--bbox",    default=None, help="minLat,maxLat,minLng,maxLng")
    parser.add_argument("--lat",     type=float, default=35.83)
    parser.add_argument("--lon",     type=float, default=10.63)
    args = parser.parse_args()

    bbox = None
    if args.bbox:
        minLat, maxLat, minLng, maxLng = map(float, args.bbox.split(','))
        bbox = {'minLat': minLat, 'maxLat': maxLat, 'minLng': minLng, 'maxLng': maxLng}

    result = generate_dataset(
        lat=args.lat, lon=args.lon, altitude_m=args.altitude,
        mbtiles_path=args.mbtiles, output_dir=args.output,
        bbox=bbox, verbose=True,
    )
    print(f"\n✅ {result.total_images} tiles → {result.output_dir}")
