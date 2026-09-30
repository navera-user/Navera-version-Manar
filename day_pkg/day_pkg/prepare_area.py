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

    prepare_area.py --mbtiles map.mbtiles --out /data/areas/mission1 \\
        --route 35.8256,10.6385 35.8560,10.6010 [--buffer-m 1000] [--zoom 17]
    prepare_area.py ... --check          coverage report only, nothing written

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


def plan_tiles(mbtiles: str, route, buffer_m: float, zoom: int = 17):
    """Tiles of the corridor: {"needed": [(x, y)], "present": [...], "missing": [...]}.

    A tile belongs to the corridor when its centre is within buffer_m of the
    route plus half its diagonal (so the corridor edge is fully covered).
    """
    if not route:
        raise ValueError("empty route")
    lats = [p[0] for p in route]
    lons = [p[1] for p in route]
    pad_lat = buffer_m / M_PER_DEG
    pad_lon = buffer_m / (M_PER_DEG * math.cos(math.radians(sum(lats) / len(lats))))
    x0, y0 = tile_xy(max(lats) + pad_lat, min(lons) - pad_lon, zoom)
    x1, y1 = tile_xy(min(lats) - pad_lat, max(lons) + pad_lon, zoom)
    lat_c = sum(lats) / len(lats)
    tile_m = 40_075_016.7 * math.cos(math.radians(lat_c)) / 2 ** zoom
    reach = buffer_m + tile_m * math.sqrt(2) / 2
    needed = []
    for x in range(int(x0), int(x1) + 1):
        for y in range(int(y0), int(y1) + 1):
            c = tile_center(x, y, zoom)
            if _dist_to_route_m(c[0], c[1], route) <= reach:
                needed.append((x, y))
    con = sqlite3.connect(f"file:{mbtiles}?mode=ro", uri=True)
    try:
        n = 2 ** zoom
        present = set()
        for i in range(0, len(needed), 500):
            chunk = needed[i:i + 500]
            q = " OR ".join("(tile_column=? AND tile_row=?)" for _ in chunk)
            args = [v for x, y in chunk for v in (x, n - 1 - y)]
            for col, row in con.execute(
                    f"SELECT tile_column, tile_row FROM tiles WHERE zoom_level=? AND ({q})",
                    [zoom] + args):
                present.add((col, n - 1 - row))
    finally:
        con.close()
    return {"zoom": zoom, "tile_m": tile_m, "needed": needed,
            "present": [t for t in needed if t in present],
            "missing": [t for t in needed if t not in present]}


def _progress(stage, done, total, **extra):
    print(json.dumps(dict(stage=stage, done=done, total=total, **extra)), flush=True)


def prepare(mbtiles, out_dir, route, buffer_m, zoom=17):
    """Build the dataset in <out_dir>.partial, then move it to out_dir."""
    t0 = time.time()
    plan = plan_tiles(mbtiles, route, buffer_m, zoom)
    tmp = out_dir.rstrip("/") + ".partial"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, "images"))
    con = sqlite3.connect(f"file:{mbtiles}?mode=ro", uri=True)
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
    info = {"route": route, "buffer_m": buffer_m, "zoom": zoom, "mbtiles": os.path.abspath(mbtiles),
            "tiles": len(plan["needed"]), "prepared": len(valid),
            "missing": plan["missing"], "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "build_s": round(time.time() - t0, 1), "device": device}
    with open(os.path.join(tmp, "area.json"), "w") as f:
        json.dump(info, f)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.replace(tmp, out_dir)
    _progress("done", len(valid), len(plan["needed"]), missing=len(plan["missing"]),
              build_s=info["build_s"])
    return info


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mbtiles", required=True)
    ap.add_argument("--out")
    ap.add_argument("--route", nargs="+", required=True, help="lat,lon waypoints")
    ap.add_argument("--buffer-m", type=float, default=1000.0)
    ap.add_argument("--zoom", type=int, default=17)
    ap.add_argument("--check", action="store_true", help="coverage report only")
    a = ap.parse_args()
    route = [tuple(float(v) for v in p.split(",")) for p in a.route]
    if a.check:
        p = plan_tiles(a.mbtiles, route, a.buffer_m, a.zoom)
        print(json.dumps({"tiles": len(p["needed"]), "present": len(p["present"]),
                          "missing": len(p["missing"])}))
        return 0
    if not a.out:
        ap.error("--out is required unless --check")
    prepare(a.mbtiles, a.out, route, a.buffer_m, a.zoom)
    return 0


if __name__ == "__main__":
    sys.exit(main())
