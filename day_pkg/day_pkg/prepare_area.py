#!/usr/bin/env python3
"""Prepare the day-vision dataset for a mission area, from the onboard MBTiles map.

Day vision matches the camera against satellite tiles near the vehicle's last
known position. Before a mission, the tiles covering the route (a corridor of
--buffer-m metres around it) are extracted from the MBTiles map and their DINOv2
descriptors computed, producing a dataset directory that day_subscriber loads
with DAY_DATASET_DIR:

    <out>/images/tile_<z>_<x>_<y>.jpg
    <out>/dataset.csv              filename, lat, lon (tile north-west corner)
    <out>/descriptors_cache.npz    dinov2_descriptors, coords (centres), valid_indices
    <out>/area.json                route, buffer, zoom, map, tile counts, missing tiles
    <out>/terrain/                 the corridor's DEM (--dem copernicus; navera_common.terrain):
                                   the height above ground under the vehicle over relief

    prepare_area.py --mbtiles map.mbtiles --out /data/areas/mission1 \\
        --route 35.8256,10.6385 35.8560,10.6010 [--buffer-m 1000] [--zoom 17]
    prepare_area.py ... --check          coverage report only, nothing written
    prepare_area.py ... --fetch-url 'https://…/{z}/{y}/{x}' --cache world.mbtiles
                                         tiles the map lacks are downloaded into the
                                         cache MBTiles (mission areas anywhere)
    prepare_area.py ... --source sentinel2_l2a --cache s2.mbtiles
                                         the same from a licence-labelled source
                                         (day_pkg.tile_sources.SOURCES); a base map
                                         labelled with another source is not used

Every downloaded cache is labelled with its source and licence (MBTiles metadata,
day_pkg.tile_sources); area.json "map_source" copies the label and its
"licence_warnings" say whether the map may ship on a sold device (Esri World
Imagery: development only).

Progress is printed as one JSON object per line ({"stage", "done", "total"}),
so a ground-station page can show it. The dataset is built in a temporary
directory and moved into place only when complete: a half-built area is never
loaded. Tiles missing from the map are reported (area.json "missing"); inside
them day vision has nothing to match and reports no position.
"""
import argparse
import json
import math
import os
import shutil
import sqlite3
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from day_pkg import tile_sources

M_PER_DEG = 111_320.0


def tile_xy(lat: float, lon: float, z: int):
    """Fractional XYZ tile coordinates of a point."""
    n = 2 ** z
    r = math.radians(lat)
    return ((lon + 180.0) / 360.0 * n,
            (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n)


def tile_nw(x: int, y: int, z: int):
    """(lat, lon) of a tile's north-west corner."""
    n = 2 ** z
    return (math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n)))), x / n * 360.0 - 180.0)


def tile_center(x: int, y: int, z: int):
    n = 2 ** z
    return (math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / n)))),
            (x + 0.5) / n * 360.0 - 180.0)


def _dist_to_route_m(lat, lon, route):
    """Distance (m) from a point to a polyline, in a local flat frame."""
    k = math.cos(math.radians(lat))
    px, py = lon * M_PER_DEG * k, lat * M_PER_DEG
    pts = [(b * M_PER_DEG * k, a * M_PER_DEG) for a, b in route]
    if len(pts) == 1:
        return math.hypot(px - pts[0][0], py - pts[0][1])
    best = float("inf")
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
        best = min(best, math.hypot(px - ax - t * dx, py - ay - t * dy))
    return best


def open_cache(path: str):
    """Open (create if needed) a writable MBTiles cache for downloaded tiles."""
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.execute("CREATE TABLE IF NOT EXISTS metadata (name TEXT, value TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS tiles (zoom_level INTEGER, tile_column INTEGER, "
                "tile_row INTEGER, tile_data BLOB)")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS tile_index ON tiles "
                "(zoom_level, tile_column, tile_row)")
    if not con.execute("SELECT 1 FROM metadata WHERE name='name'").fetchone():
        con.executemany("INSERT INTO metadata VALUES (?, ?)",
                        [("name", "NAVERA downloaded tiles"), ("format", "jpg"),
                         ("type", "baselayer")])
    con.commit()
    return con


def fetch_tile(url_template: str, z: int, x: int, y: int, retries: int = 2):
    """Tile bytes from an XYZ URL template ({z}/{x}/{y}), or None."""
    url = url_template.format(z=z, x=x, y=y)
    req = urllib.request.Request(url, headers={"User-Agent": "NAVERA-mission-planner/0.5"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read()
                if r.status == 200 and len(data) > 100:
                    return data
                return None
        except Exception:                            # noqa: BLE001 — network: retry, then give up
            time.sleep(0.5 * (attempt + 1))
    return None


def _present(path, zoom, tiles):
    """Subset of tiles (x, y) present in an MBTiles file (missing file = none).

    One indexed range query per tile column (zoom, column, row BETWEEN): a
    single query with hundreds of OR terms could not use the index and took
    ~1 ms per tile (75 s for a long route).
    """
    if not path or not os.path.exists(path) or not tiles:
        return set()
    n = 2 ** zoom
    cols = {}
    for x, y in tiles:
        cols.setdefault(x, []).append(y)
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    present = set()
    try:
        for x, ys in cols.items():
            lo, hi = n - 1 - max(ys), n - 1 - min(ys)          # TMS rows
            want = set(ys)
            for (row,) in con.execute(
                    "SELECT tile_row FROM tiles WHERE zoom_level=? AND tile_column=? "
                    "AND tile_row BETWEEN ? AND ?", (zoom, x, lo, hi)):
                y = n - 1 - row
                if y in want:
                    present.add((x, y))
    finally:
        con.close()
    return present


LEG_M = 10_000.0   # long routes are flown and mapped as legs of at most this length


def _gc_point(a, b, f):
    """Point at fraction f of the great circle from a to b (lat, lon in degrees)."""
    p1, l1, p2, l2 = (math.radians(v) for v in (a[0], a[1], b[0], b[1]))
    d = 2 * math.asin(math.sqrt(min(1.0, math.sin((p2 - p1) / 2) ** 2
                                     + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2)))
    if d < 1e-12:
        return [float(a[0]), float(a[1])]
    ka, kb = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
    x = ka * math.cos(p1) * math.cos(l1) + kb * math.cos(p2) * math.cos(l2)
    y = ka * math.cos(p1) * math.sin(l1) + kb * math.cos(p2) * math.sin(l2)
    z = ka * math.sin(p1) + kb * math.sin(p2)
    return [math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))]


def densify_route(route, leg_m: float = LEG_M):
    """The route with great-circle points added so that no leg is longer than leg_m.

    A vehicle sent to a far waypoint does not follow the straight lat/lon line the
    corridor is built on (Paris-Tunisia: ~17 km apart, for a ±1 km corridor). Flown
    leg by leg along these points, path and corridor agree to metres. Routes whose
    legs are already short are returned unchanged (same area id)."""
    out = [[float(route[0][0]), float(route[0][1])]]
    for a, b in zip(route, route[1:]):
        n = max(1, int(math.ceil(_haversine_m(a, b) / leg_m)))
        out += [_gc_point(a, b, k / n) for k in range(1, n)] + [[float(b[0]), float(b[1])]]
    return out


def point_along(route, dist_m: float):
    """(point, index of the next vertex) at dist_m along the polyline (great circles)."""
    left = max(0.0, float(dist_m))
    for i, (a, b) in enumerate(zip(route, route[1:])):
        seg = _haversine_m(a, b)
        if left <= seg and seg > 0:
            return _gc_point(a, b, left / seg), i + 1
        left -= seg
    return [float(route[-1][0]), float(route[-1][1])], len(route) - 1


def _haversine_m(a, b) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, h)))


def route_length_m(route) -> float:
    return sum(_dist_to_route_m(a[0], a[1], [b]) for a, b in zip(route, route[1:]))


def _tile_m(route, zoom):
    lat_c = sum(p[0] for p in route) / len(route)
    return 40_075_016.7 * math.cos(math.radians(lat_c)) / 2 ** zoom


def corridor_tiles(route, buffer_m: float, zoom: int = 17):
    """Tiles (x, y) whose centre is within buffer_m (+ half a tile diagonal) of the route.

    Samples the route every half tile and tests only the tiles around it,
    vectorised: the cost grows with the route length (the former bounding-box
    scan grew with its square — minutes, and a stuck planner, for long routes).
    """
    import numpy as np
    tile_m = _tile_m(route, zoom)
    reach = buffer_m + tile_m * math.sqrt(2) / 2
    half = int(math.ceil(reach / tile_m)) + 1
    pts = np.asarray(route if len(route) > 1 else [route[0], route[0]], dtype=float)
    lat_s, lon_s = [], []
    for a, b in zip(pts, pts[1:]):
        seg = _dist_to_route_m(a[0], a[1], [tuple(b)])
        f = np.linspace(0.0, 1.0, max(1, int(math.ceil(seg / (tile_m / 2)))) + 1)
        lat_s.append(a[0] + f * (b[0] - a[0]))
        lon_s.append(a[1] + f * (b[1] - a[1]))
    lat_s, lon_s = np.concatenate(lat_s), np.concatenate(lon_s)
    n = 2 ** zoom
    tx = np.floor((lon_s + 180.0) / 360.0 * n).astype(np.int64)
    r = np.radians(lat_s)
    ty = np.floor((1.0 - np.log(np.tan(r) + 1.0 / np.cos(r)) / np.pi) / 2.0 * n).astype(np.int64)
    off = np.arange(-half, half + 1, dtype=np.int64)
    dx, dy = (g.ravel() for g in np.meshgrid(off, off))
    keys = np.unique(((tx[:, None] + dx) << 32) | (ty[:, None] + dy))
    x, y = keys >> 32, keys & 0xFFFFFFFF
    clon = (x + 0.5) / n * 360.0 - 180.0
    clat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + 0.5) / n))))
    # distance to the polyline, in a local flat frame (as _dist_to_route_m)
    k = np.cos(np.radians(clat))
    px, py = clon * M_PER_DEG * k, clat * M_PER_DEG
    best = np.full(len(keys), np.inf)
    for a, b in zip(pts, pts[1:]):
        ax, ay = a[1] * M_PER_DEG * k, a[0] * M_PER_DEG
        bx, by = b[1] * M_PER_DEG * k, b[0] * M_PER_DEG
        vx, vy = bx - ax, by - ay
        l2 = vx * vx + vy * vy
        with np.errstate(invalid="ignore", divide="ignore"):
            t = np.where(l2 > 0, ((px - ax) * vx + (py - ay) * vy) / np.where(l2 > 0, l2, 1), 0.0)
        t = np.clip(t, 0.0, 1.0)
        best = np.minimum(best, np.hypot(px - ax - t * vx, py - ay - t * vy))
    ok = best <= reach
    return sorted(zip(x[ok].tolist(), y[ok].tolist()))


def plan_tiles(mbtiles: str, route, buffer_m: float, zoom: int = 17, cache: str = None):
    """Tiles of the corridor: {"needed", "present", "missing", "in_base", "in_cache"}.

    A tile belongs to the corridor when its centre is within buffer_m of the
    route plus half its diagonal (so the corridor edge is fully covered).
    """
    if not route:
        raise ValueError("empty route")
    needed = corridor_tiles(route, buffer_m, zoom)
    tile_m = _tile_m(route, zoom)
    in_base = _present(mbtiles, zoom, needed)
    in_cache = _present(cache, zoom, [t for t in needed if t not in in_base])
    present = in_base | in_cache
    return {"zoom": zoom, "tile_m": tile_m, "needed": needed,
            "present": [t for t in needed if t in present],
            "missing": [t for t in needed if t not in present],
            "in_base": len(in_base), "in_cache": len(in_cache)}


# a map tile with fewer SIFT keypoints than this cannot be matched (measured: sea and
# uniform tiles 0, land 900-1600 at zoom 17)
FEATURELESS_KEYPOINTS = 50


def _profile(route, zoom, step, classify):
    """Featureless stretches along the route's centre line; classify(x, y) -> True
    (featureless), False (textured) or None (tile missing)."""
    total = route_length_m(route)
    memo, flags = {}, []
    d = 0.0
    while d <= total:
        p, _ = point_along(route, d)
        x, y = (int(v) for v in tile_xy(p[0], p[1], zoom))
        if (x, y) not in memo:
            memo[(x, y)] = classify(x, y)
        flags.append((d, memo[(x, y)]))
        d += step
    stretches, unknown, start = [], 0.0, None
    for i, (d, f) in enumerate(flags):
        if f is None:
            unknown += step
        if f and start is None:
            start = d
        if (not f or i == len(flags) - 1) and start is not None:
            end = d if not f else min(d + step, total)
            if end - start >= 200.0:
                stretches.append([round(start / 1000, 2), round(end / 1000, 2)])
            start = None
    lengths = [b - a for a, b in stretches]
    return {"featureless_km": round(sum(lengths), 2), "longest_km": round(max(lengths, default=0.0), 2),
            "stretches": stretches[:50], "unknown_km": round(min(unknown, total) / 1000, 2)}


def texture_profile(images_dir: str, route, zoom: int = 17, step_m: float = None):
    """Where along the route the map has nothing to match (sea, lakes, uniform sand):
    vision gives no position there and the vehicle flies on NAVERA's dead-reckoning (up to
    2 min), then on its own navigation. Returns {"featureless_km", "longest_km",
    "stretches": [[from_km, to_km], ...], "unknown_km"} — sampled on the route's centre
    line, one tile at a time (SIFT keypoints of the prepared tiles)."""
    import cv2
    sift = cv2.SIFT_create(contrastThreshold=0.02)

    def classify(x, y):
        g = cv2.imread(os.path.join(images_dir, f"tile_{zoom}_{x}_{y}.jpg"), cv2.IMREAD_GRAYSCALE)
        if g is None:
            return None                                     # tile missing from the map
        if g.std() > 25.0:                                  # textured: no need to count
            return False
        return len(sift.detect(g, None)) < FEATURELESS_KEYPOINTS
    return _profile(route, zoom, step_m or _tile_m(route, zoom) / 2.0, classify)


def quick_texture_profile(sources, route, zoom: int = 17, max_samples: int = 600):
    """The same, BEFORE generation, from the map files themselves (onboard map, download
    cache): a tile of nearly uniform grey levels (sea, lakes: std < 6) is featureless —
    fast (no feature extraction), coarser; tiles not yet downloaded are "unknown"."""
    import sqlite3
    import cv2
    import numpy as np
    cons = []
    for src in sources:
        if src and os.path.exists(src):
            try:
                cons.append(sqlite3.connect(f"file:{src}?mode=ro", uri=True))
            except sqlite3.Error:
                pass
    n = 2 ** zoom

    def classify(x, y):
        for c in cons:
            r = c.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                          (zoom, x, n - 1 - y)).fetchone()
            if r:
                g = cv2.imdecode(np.frombuffer(r[0], np.uint8), cv2.IMREAD_GRAYSCALE)
                return None if g is None else bool(g.std() < 6.0)
        return None
    total = route_length_m(route)
    step = max(_tile_m(route, zoom) / 2.0, total / max_samples)
    try:
        return _profile(route, zoom, step, classify)
    finally:
        for c in cons:
            c.close()


def _progress(stage, done, total, **extra):
    print(json.dumps(dict(stage=stage, done=done, total=total, **extra)), flush=True)


def download_missing(plan, fetch_url, cache, mbtiles, workers=8):
    """Download the plan's missing tiles into the cache, and copy the base map's
    corridor tiles there too, so the cache alone covers the whole corridor (the
    night localizer reads one map). Returns the number of tiles still missing.

    fetch_url: an XYZ URL template, or the name of a tile_sources source. The cache
    is labelled with the source's licence; a cache labelled with another source
    raises ValueError (one map, one licence)."""
    zoom, n = plan["zoom"], 2 ** plan["zoom"]
    registered = fetch_url in tile_sources.SOURCES
    src = tile_sources.get_source(fetch_url) if registered else tile_sources.source_for_url(fetch_url)
    con = open_cache(cache)
    try:
        tile_sources.label_mbtiles(con, src, zoom=zoom)
        if plan["in_base"] and mbtiles and os.path.exists(mbtiles):
            base = sqlite3.connect(f"file:{mbtiles}?mode=ro", uri=True)
            for x, y in plan["present"]:
                r = base.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? "
                                 "AND tile_row=?", (zoom, x, n - 1 - y)).fetchone()
                if r:
                    con.execute("INSERT OR IGNORE INTO tiles VALUES (?, ?, ?, ?)",
                                (zoom, x, n - 1 - y, r[0]))
            base.close()
            con.commit()
        if registered:
            con.close()
            r = tile_sources.fetch_tiles(plan["missing"], zoom, fetch_url, cache, workers=workers,
                                         progress=lambda s, d, t: _progress(s, d, t))
            return r["failed"]
        todo = list(plan["missing"])
        failed, done = 0, 0
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for (x, y), data in zip(todo, ex.map(lambda t: fetch_tile(fetch_url, zoom, *t), todo)):
                done += 1
                if data:
                    con.execute("INSERT OR REPLACE INTO tiles VALUES (?, ?, ?, ?)",
                                (zoom, x, n - 1 - y, data))
                else:
                    failed += 1
                if done % 25 == 0 or done == len(todo):
                    con.commit()
                    _progress("download", done, len(todo), failed=failed)
        con.commit()
        return failed
    finally:
        con.close()


def _descriptors(tmp, rows):
    """DINOv2 descriptors of the area's tiles -> <tmp>/descriptors_cache.npz; (valid indices, device)."""
    import numpy as np
    import torch
    from day_pkg.nodes.day_localizer import DINOv2GeM, load_image_tensor, tile_center_latlon
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = DINOv2GeM().to(device).eval()
    descs, valid, coords = [], [], []
    batch = []

    def flush():
        with torch.no_grad():
            out = model(torch.stack([b[1] for b in batch]).to(device)).cpu().numpy()
        for (idx, _), d in zip(batch, out):
            descs.append(d)
            valid.append(idx)
            coords.append(tile_center_latlon(rows[idx][0]))
        batch.clear()

    for i, (name, _, _) in enumerate(rows):
        try:
            batch.append((i, load_image_tensor(os.path.join(tmp, "images", name))))
        except Exception as e:                       # corrupt tile in the map
            print(json.dumps({"stage": "warning", "tile": name, "error": str(e)}), flush=True)
        if len(batch) == 32 or (i == len(rows) - 1 and batch):
            flush()
            _progress("descriptors", i + 1, len(rows))
    np.savez(os.path.join(tmp, "descriptors_cache.npz"),
             dinov2_descriptors=np.array(descs, dtype=np.float32),
             coords=np.array(coords, dtype=float), valid_indices=np.array(valid))
    return valid, device


def _build_dem(kind, legs, buffer_m, out_dir, opener=None):
    """The corridor's DEM (area.json "dem"); {"error": ...} when it cannot be obtained."""
    if kind != "copernicus":
        return {"error": f"unknown DEM source {kind!r} (copernicus)"}
    from day_pkg import dem_sources
    try:
        return dem_sources.build_dem(legs, buffer_m, out_dir, opener=opener,
                                     progress=lambda s, d, t: _progress(s, d, t))
    except Exception as e:                       # noqa: BLE001 — network / source: no DEM, reported
        return {"error": f"DEM not obtained: {e}"}


def prepare(mbtiles, out_dir, route, buffer_m, zoom=17, fetch_url=None, cache=None, descriptors=True,
            dem=None, dem_opener=None):
    """Build the dataset in <out_dir>.partial, then move it to out_dir. descriptors=False: no DINOv2
    descriptor cache (no torch needed; day_subscriber then builds it at start-up from the tiles).
    dem="copernicus": also store the corridor's terrain (day_pkg.dem_sources; needs the network,
    dem_opener for tests); a DEM that cannot be obtained is reported in area.json "dem", not fatal
    (the height above ground then falls back to the barometer and the image)."""
    t0 = time.time()
    plan = plan_tiles(mbtiles, route, buffer_m, zoom, cache)
    source = mbtiles
    if fetch_url and cache and (plan["missing"] or plan["in_cache"]):
        download_missing(plan, fetch_url, cache, mbtiles)
        plan = plan_tiles(mbtiles, route, buffer_m, zoom, cache)
        source = cache                         # complete for the corridor
    elif plan["in_cache"]:
        source = cache
    tmp = out_dir.rstrip("/") + ".partial"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, "images"))
    con = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    rows = []
    n = 2 ** zoom
    total = len(plan["present"])
    try:
        for i, (x, y) in enumerate(plan["present"]):
            r = con.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? "
                            "AND tile_row=?", (zoom, x, n - 1 - y)).fetchone()
            name = f"tile_{zoom}_{x}_{y}.jpg"
            with open(os.path.join(tmp, "images", name), "wb") as f:
                f.write(r[0])
            lat, lon = tile_nw(x, y, zoom)
            rows.append((name, lat, lon))
            if i % 50 == 0 or i == total - 1:
                _progress("tiles", i + 1, total)
    finally:
        con.close()
    with open(os.path.join(tmp, "dataset.csv"), "w") as f:
        f.write("filename,lat,lon\n")
        for name, lat, lon in rows:
            f.write(f"{name},{lat},{lon}\n")

    valid, device = (_descriptors(tmp, rows) if descriptors else ([], None))
    dem_info = None
    if dem:
        _progress("dem", 0, 1)
        dem_info = _build_dem(dem, densify_route(route), buffer_m, os.path.join(tmp, "terrain"), dem_opener)
    _progress("terrain", 0, 1)
    terrain = texture_profile(os.path.join(tmp, "images"), densify_route(route), zoom)
    info = {"route": route, "buffer_m": buffer_m, "zoom": zoom, "mbtiles": os.path.abspath(source),
            "terrain": terrain,
            "tiles": len(plan["needed"]), "prepared": len(valid) if descriptors else len(rows),
            "descriptors": bool(descriptors),
            "missing": plan["missing"], "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "build_s": round(time.time() - t0, 1), "device": device}
    if dem_info is not None:
        info["dem"] = dem_info
    info["map_source"] = tile_sources.read_map_info(source)
    info["licence_warnings"] = tile_sources.licence_warnings(info["map_source"])
    with open(os.path.join(tmp, "area.json"), "w") as f:
        json.dump(info, f)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.replace(tmp, out_dir)
    _progress("done", info["prepared"], len(plan["needed"]), missing=len(plan["missing"]),
              build_s=info["build_s"], terrain=terrain)
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mbtiles", required=True)
    ap.add_argument("--out")
    ap.add_argument("--route", nargs="+", required=True, help="lat,lon waypoints")
    ap.add_argument("--buffer-m", type=float, default=1000.0)
    ap.add_argument("--zoom", type=int, default=17)
    ap.add_argument("--check", action="store_true", help="coverage report only")
    ap.add_argument("--fetch-url", help="XYZ tile URL template ({z} {x} {y}) for missing tiles")
    ap.add_argument("--cache", help="MBTiles file receiving downloaded tiles")
    ap.add_argument("--no-descriptors", action="store_true",
                    help="no DINOv2 descriptor cache (day_subscriber builds it at start-up)")
    ap.add_argument("--dem", choices=["copernicus", "none"], default="none",
                    help="also store the corridor's terrain (Copernicus DEM GLO-30 / GLO-90, free licence): "
                         "the height above ground over relief")
    ap.add_argument("--source", choices=sorted(n for n, s in tile_sources.SOURCES.items() if s.kind != "geotiff"),
                    help="licence-labelled source for missing tiles (instead of --fetch-url)")
    a = ap.parse_args()
    route = [tuple(float(v) for v in p.split(",")) for p in a.route]
    if a.source:
        if a.fetch_url:
            ap.error("--source or --fetch-url, not both")
        if not a.cache:
            ap.error("--source needs --cache")
        if tile_sources.read_map_info(a.mbtiles).get("source") != a.source:
            a.mbtiles = ""                        # the base map is another source: not mixed in
        a.fetch_url = a.source
    if a.check:
        p = plan_tiles(a.mbtiles, route, a.buffer_m, a.zoom, a.cache)
        print(json.dumps({"tiles": len(p["needed"]), "present": len(p["present"]),
                          "missing": len(p["missing"])}))
        return 0
    if not a.out:
        ap.error("--out is required unless --check")
    prepare(a.mbtiles, a.out, route, a.buffer_m, a.zoom, a.fetch_url, a.cache, descriptors=not a.no_descriptors,
            dem=None if a.dem == "none" else a.dem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
