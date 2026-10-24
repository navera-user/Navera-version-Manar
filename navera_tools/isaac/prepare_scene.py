#!/usr/bin/env python3
"""Prepare the Isaac Sim scene (ground, relief, buildings) and NAVERA's map for one place.

    python3 navera_tools/isaac/prepare_scene.py --lat0 35.8685 --lon0 10.5352 \
        --scene ~/.navera_sim/isaac/kalaa --scene-out ~/.navera_sim/isaac/kalaa_scene \
        --map-tiles ~/.navera_sim/dayv_conditions/kalaa_map/images --area-out ~/.navera_sim/isaac/kalaa_area

--scene      fetch_scene_data.py output: imagery/ (Wayback tiles), dem/, ms_buildings.json,
             osm_buildings.json
--scene-out  what isaac_flight.py loads:
               mosaic.jpg + mosaic.json  the scene imagery stitched, rows resampled from Web
                                         Mercator to even latitude steps (the flat lat/lon
                                         projection of flight_profile.GeoRef)
               terrain.npy               DEM heights - z_ref on a regular grid over the mosaic
               buildings.npz             extruded footprints: roofs (textured with the mosaic
                                         at their place) and walls, base on the DEM
             z_ref = the DEM height at (lat0, lon0) = scene Z 0.
--map-tiles  NAVERA's map (tile_<z>_<x>_<y>.jpg, the ~2025 MBTiles export): tiles within
--area-radius-m of the origin -> --area-out (DAY_DATASET_DIR: images/ + dataset.csv)

Wide scenes (e.g. kalaa_wide, 12 x 12 km at z17): --buildings-within-m keeps only the footprints
within that distance of the origin (the route; the far ground stays imagery on the relief),
--terrain-grid sets the DEM mesh (default 257), --mosaic-max-px downsizes the mosaic texture if
the renderer's GPU memory or texture limit needs it.

Building heights: the footprints carry none here (Microsoft ML footprints, Tunisia): a
deterministic draw of 1-4 floors x 3.2 m (40/40/15/5 %), OSM height / building:levels tags
override when a mapped OSM building lies on the footprint.
"""
import argparse
import csv
import glob
import json
import math
import os
import random
import re
import shutil
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from flight_profile import GeoRef  # noqa: E402
from scene_dem import Dem  # noqa: E402


def tile_lon(x: float, z: int) -> float:
    return x / 2 ** z * 360.0 - 180.0


def tile_lat(y: float, z: int) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))


def merc_y(lat: float, z: int) -> float:
    r = math.radians(lat)
    return (1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * 2 ** z


def read_tiles(d):
    tiles = {}
    for f in glob.glob(os.path.join(os.path.expanduser(d), "tile_*_*_*.jpg")):
        z, x, y = map(int, re.findall(r"tile_(\d+)_(\d+)_(\d+)\.jpg$", f)[0])
        tiles[(x, y)] = (z, f)
    zs = {z for z, _ in tiles.values()}
    if len(zs) != 1:
        raise SystemExit(f"{d}: one zoom expected, found {sorted(zs)}")
    return zs.pop(), tiles


def mosaic(tile_dir, out, quality=92, max_px=0):
    z, tiles = read_tiles(tile_dir)
    xs, ys = sorted({k[0] for k in tiles}), sorted({k[1] for k in tiles})
    nx, ny = xs[-1] - xs[0] + 1, ys[-1] - ys[0] + 1
    ts = cv2.imread(next(iter(tiles.values()))[1]).shape[0]
    merc = np.zeros((ny * ts, nx * ts, 3), np.uint8)
    for (x, y), (_, f) in tiles.items():
        merc[(y - ys[0]) * ts:(y - ys[0] + 1) * ts, (x - xs[0]) * ts:(x - xs[0] + 1) * ts] = cv2.imread(f)
    lat_n, lat_s = tile_lat(ys[0], z), tile_lat(ys[-1] + 1, z)
    lon_w, lon_e = tile_lon(xs[0], z), tile_lon(xs[-1] + 1, z)
    rows = merc.shape[0]
    lats = lat_n + (np.arange(rows) + 0.5) / rows * (lat_s - lat_n)
    src_y = np.array([(merc_y(v, z) - ys[0]) * ts - 0.5 for v in lats], np.float32)
    map_y = np.repeat(src_y[:, None], merc.shape[1], axis=1)
    map_x = np.repeat(np.arange(merc.shape[1], dtype=np.float32)[None, :], rows, axis=0)
    flat = cv2.remap(merc, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    del merc, map_x, map_y
    if max_px and max(flat.shape[:2]) > max_px:
        f = max_px / max(flat.shape[:2])
        flat = cv2.resize(flat, (round(flat.shape[1] * f), round(flat.shape[0] * f)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(os.path.join(out, "mosaic.jpg"), flat, [cv2.IMWRITE_JPEG_QUALITY, quality])
    lat_c = (lat_n + lat_s) / 2
    return dict(zoom=z, tiles=len(tiles), missing=nx * ny - len(tiles), width=flat.shape[1], height=flat.shape[0],
                lat_n=lat_n, lat_s=lat_s, lon_w=lon_w, lon_e=lon_e,
                m_per_px=(lon_e - lon_w) * 111_320.0 * math.cos(math.radians(lat_c)) / flat.shape[1],
                source=os.path.abspath(os.path.expanduser(tile_dir)))


def _area2(p):
    return sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))


def triangulate(poly):
    """Ear clipping of a simple polygon [(x, y)...] (counter-clockwise) -> index triples."""
    idx = list(range(len(poly)))
    tris, guard = [], 0
    while len(idx) > 3 and guard < 10 * len(poly):
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 1e-9:
                continue                                  # reflex or flat
            inside = False
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                p = poly[j]
                d1 = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
                d2 = (c[0] - b[0]) * (p[1] - b[1]) - (c[1] - b[1]) * (p[0] - b[0])
                d3 = (a[0] - c[0]) * (p[1] - c[1]) - (a[1] - c[1]) * (p[0] - c[0])
                if d1 >= 0 and d2 >= 0 and d3 >= 0:
                    inside = True
                    break
            if inside:
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris if len(idx) <= 3 else [(0, i, i + 1) for i in range(1, len(poly) - 1)]


def osm_heights(osm_path):
    """[(e-n box, height m)] of OSM buildings that say how tall they are."""
    out = []
    if not os.path.exists(osm_path):
        return out
    for el in json.load(open(osm_path)).get("elements", []):
        tags, geom = el.get("tags", {}), el.get("geometry") or []
        h = None
        try:
            if "height" in tags:
                h = float(str(tags["height"]).split()[0])
            elif "building:levels" in tags:
                h = 3.2 * float(tags["building:levels"])
        except ValueError:
            h = None
        if h and geom:
            out.append(((min(p["lat"] for p in geom), max(p["lat"] for p in geom),
                         min(p["lon"] for p in geom), max(p["lon"] for p in geom)), h))
    return out


def buildings(scene, geo, dem, z_ref, mos, out, within_m=0.0):
    fp = json.load(open(os.path.join(scene, "ms_buildings.json")))
    tagged = osm_heights(os.path.join(scene, "osm_buildings.json"))
    xw, ys_ = geo.to_en(mos["lat_s"], mos["lon_w"])
    xe, yn = geo.to_en(mos["lat_n"], mos["lon_e"])
    rnd = random.Random(11)
    rp, ruv, rt, wp, wf = [], [], [], [], []
    heights = []
    for b in fp:
        ring = b["ring"][:-1] if b["ring"][0] == b["ring"][-1] else b["ring"]
        if len(ring) < 3:
            continue
        pts = [geo.to_en(la, lo) for lo, la in ring]
        if within_m and math.hypot(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) > within_m:
            continue
        if _area2(pts) < 0:
            pts, ring = pts[::-1], ring[::-1]
        if abs(_area2(pts)) / 2 < 12.0:                     # sheds, noise
            continue
        r = rnd.random()
        floors = 1 if r < 0.4 else 2 if r < 0.8 else 3 if r < 0.95 else 4
        h = floors * 3.2 + 0.4
        cla, clo = sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring)
        for (la0, la1, lo0, lo1), th in tagged:
            if la0 <= cla <= la1 and lo0 <= clo <= lo1:
                h = th
                break
        if b.get("height", -1) and b.get("height", -1) > 0:
            h = float(b["height"])
        try:
            base = min(dem.height(la, lo) for lo, la in ring) - z_ref - 0.3
        except ValueError:
            continue
        heights.append(h)
        top = base + h + 0.3
        k0 = len(rp)
        for (e, n) in pts:
            rp.append((e, n, top))
            ruv.append(((e - xw) / (xe - xw), (n - ys_) / (yn - ys_)))
        rt += [(k0 + i, k0 + j, k0 + k) for i, j, k in triangulate(pts)]
        for i in range(len(pts)):
            a, c = pts[i], pts[(i + 1) % len(pts)]
            k = len(wp)
            wp += [(a[0], a[1], base), (c[0], c[1], base), (c[0], c[1], top), (a[0], a[1], top)]
            wf.append((k, k + 1, k + 2, k + 3))
    np.savez_compressed(os.path.join(out, "buildings.npz"), roof_points=np.array(rp, np.float32),
                        roof_uv=np.array(ruv, np.float32), roof_tris=np.array(rt, np.int32),
                        wall_points=np.array(wp, np.float32), wall_quads=np.array(wf, np.int32))
    hs = sorted(heights)
    return dict(buildings=len(hs), height_median_m=hs[len(hs) // 2] if hs else None, within_m=within_m or None,
                osm_tagged=len(tagged), source="Microsoft Global ML Building Footprints + OSM tags")


def terrain(geo, dem, z_ref, mos, out, n=257):
    lat = np.linspace(mos["lat_s"], mos["lat_n"], n)
    lon = np.linspace(mos["lon_w"], mos["lon_e"], n)
    h = np.array([[dem.height(la, lo) - z_ref for lo in lon] for la in lat], np.float32)   # [row = south->north]
    np.save(os.path.join(out, "terrain.npy"), h)
    return dict(grid=n, min_m=float(h.min()), max_m=float(h.max()))


def area(map_tiles, lat0, lon0, radius_m, out):
    z, tiles = read_tiles(map_tiles)
    img_dir = os.path.join(out, "images")
    os.makedirs(img_dir, exist_ok=True)
    n = 0
    with open(os.path.join(out, "dataset.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["filename", "lat", "lon"])
        for (x, y), (_, f) in sorted(tiles.items()):
            cla, clo = tile_lat(y + 0.5, z), tile_lon(x + 0.5, z)
            dn = (cla - lat0) * 111_320.0
            de = (clo - lon0) * 111_320.0 * math.cos(math.radians(lat0))
            if max(abs(dn), abs(de)) > radius_m:
                continue
            name = os.path.basename(f)
            if not os.path.exists(os.path.join(img_dir, name)):
                shutil.copy2(f, img_dir)
            w.writerow([name, tile_lat(y, z), tile_lon(x, z)])
            n += 1
    return dict(tiles=n, zoom=z, radius_m=radius_m, source=os.path.abspath(os.path.expanduser(map_tiles)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lat0", type=float, required=True)
    ap.add_argument("--lon0", type=float, required=True)
    ap.add_argument("--scene", required=True)
    ap.add_argument("--scene-out", required=True)
    ap.add_argument("--map-tiles", default="")
    ap.add_argument("--area-out", default="")
    ap.add_argument("--area-radius-m", type=float, default=3000.0)
    ap.add_argument("--terrain-grid", type=int, default=257, help="DEM mesh points per side")
    ap.add_argument("--buildings-within-m", type=float, default=0.0,
                    help="only footprints within this distance of the origin (0 = all)")
    ap.add_argument("--mosaic-max-px", type=int, default=0, help="downsize the mosaic to at most this many px a side")
    a = ap.parse_args()
    scene, out = os.path.expanduser(a.scene), os.path.expanduser(a.scene_out)
    os.makedirs(out, exist_ok=True)
    geo = GeoRef(a.lat0, a.lon0)
    dem = Dem(os.path.join(scene, "dem"))
    z_ref = dem.height(a.lat0, a.lon0)
    mos = mosaic(os.path.join(scene, "imagery"), out, max_px=a.mosaic_max_px)
    info = dict(lat0=a.lat0, lon0=a.lon0, z_ref_m=z_ref, mosaic=mos,
                terrain=terrain(geo, dem, z_ref, mos, out, n=a.terrain_grid),
                buildings=buildings(scene, geo, dem, z_ref, mos, out, a.buildings_within_m))
    fetch = os.path.join(scene, "fetch.json")
    if os.path.exists(fetch):
        info["fetch"] = json.load(open(fetch))
    if a.map_tiles and a.area_out:
        info["navera_area"] = area(a.map_tiles, a.lat0, a.lon0, a.area_radius_m, os.path.expanduser(a.area_out))
    json.dump(mos, open(os.path.join(out, "mosaic.json"), "w"), indent=1)
    json.dump(info, open(os.path.join(out, "scene.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in info.items() if k != "fetch"}))


if __name__ == "__main__":
    main()
