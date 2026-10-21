#!/usr/bin/env python3
"""Download the public data the Isaac Sim scene is built from (development / evaluation only).

    python3 navera_tools/isaac/fetch_scene_data.py --lat 35.8685 --lon 10.5352 \
        --out ~/.navera_sim/isaac/kalaa [--zoom 18] [--tiles 32] [--release 10321]

Into --out:
  imagery/tile_<z>_<x>_<y>.jpg   Esri World Imagery Wayback release --release (default 10321
                                 = 2022-03-16, the "wb2022" imagery of the cross-date bench):
                                 the SCENE's ground, deliberately another date than the map
                                 NAVERA matches against (Sousse MBTiles, ~2025)
  dem/terrarium_<z>_<x>_<y>.png  AWS Terrain Tiles (terrarium encoding, SRTM-class ~30 m),
                                 as navera_tools/bench/uavvisloc_dem.py reads them
  osm_buildings.json             OpenStreetMap building footprints (Overpass API) in the box,
                                 with their height / building:levels tags when present
  ms_buildings.json              Microsoft Global ML Building Footprints (ODbL) in the box: OSM
                                 alone maps a few dozen buildings here, the ML footprints
                                 thousands (no heights in Tunisia: prepare_scene gives floors)
  fetch.json                     what was fetched, from where, when

Licences: Esri imagery (Wayback) and OSM data (ODbL) are for internal evaluation here; do not
redistribute the scene.
"""
import argparse
import json
import math
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

WAYBACK = ("https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/"
           "default028mm/MapServer/tile/{rid}/{z}/{y}/{x}")
TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter")
MS_LINKS = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
UA = {"User-Agent": "NAVERA-sim-scene/1.0 (internal evaluation)"}


def tile_xy(lat, lon, z):
    n = 2 ** z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def tile_lon(x, z):
    return x / 2 ** z * 360.0 - 180.0


def tile_lat(y, z):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))


def get(url, path, tries=4):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return True
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                data = r.read()
            with open(path + ".part", "wb") as f:
                f.write(data)
            os.replace(path + ".part", path)
            return True
        except Exception:                        # noqa: BLE001 — retried, then reported
            time.sleep(1.5 * (k + 1))
    return False


def quadkey(lat, lon, z=9):
    fx, fy = tile_xy(lat, lon, z)
    x, y, q = int(fx), int(fy), ""
    for i in range(z, 0, -1):
        m = 1 << (i - 1)
        q += str((1 if x & m else 0) + (2 if y & m else 0))
    return q


def ms_buildings(lat, lon, box, out):
    """Footprints of the z9 quadkey holding (lat, lon), kept inside the box -> ms_buildings.json."""
    import csv
    import gzip
    import io
    qk = quadkey(lat, lon)
    with urllib.request.urlopen(urllib.request.Request(MS_LINKS, headers=UA), timeout=120) as r:
        rows = [row for row in csv.DictReader(io.StringIO(r.read().decode())) if row["QuadKey"] == qk]
    keep = []
    for row in rows:
        gz = os.path.join(out, f"ms_{qk}_{len(keep)}.csv.gz")
        if not get(row["Url"], gz):
            raise SystemExit(f"Microsoft footprints not fetched: {row['Url']}")
        for line in gzip.open(gz, "rt"):
            f = json.loads(line)
            if f["geometry"]["type"] != "Polygon":
                continue
            ring = f["geometry"]["coordinates"][0]
            clo, cla = sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
            if box["lon_w"] <= clo <= box["lon_e"] and box["lat_s"] <= cla <= box["lat_n"]:
                keep.append(dict(ring=ring, height=f["properties"].get("height", -1.0)))
    path = os.path.join(out, "ms_buildings.json")
    json.dump(keep, open(path, "w"))
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--zoom", type=int, default=18)
    ap.add_argument("--tiles", type=int, default=32, help="imagery tiles per side")
    ap.add_argument("--release", type=int, default=10321, help="Wayback release id (10321 = 2022-03-16)")
    ap.add_argument("--dem-zoom", type=int, default=14)
    a = ap.parse_args()
    out = os.path.expanduser(a.out)
    for d in ("imagery", "dem"):
        os.makedirs(os.path.join(out, d), exist_ok=True)

    fx, fy = tile_xy(a.lat, a.lon, a.zoom)
    x0, y0 = int(round(fx - a.tiles / 2)), int(round(fy - a.tiles / 2))
    jobs = [(x, y) for x in range(x0, x0 + a.tiles) for y in range(y0, y0 + a.tiles)]
    with ThreadPoolExecutor(8) as ex:
        ok = list(ex.map(lambda j: get(WAYBACK.format(rid=a.release, z=a.zoom, x=j[0], y=j[1]),
                                       os.path.join(out, "imagery", f"tile_{a.zoom}_{j[0]}_{j[1]}.jpg")), jobs))
    lat_n, lat_s = tile_lat(y0, a.zoom), tile_lat(y0 + a.tiles, a.zoom)
    lon_w, lon_e = tile_lon(x0, a.zoom), tile_lon(x0 + a.tiles, a.zoom)

    dz = a.dem_zoom
    dx0, dy0 = (int(v) for v in tile_xy(lat_n, lon_w, dz))
    dx1, dy1 = (int(v) for v in tile_xy(lat_s, lon_e, dz))
    dem_ok = [get(TERRARIUM.format(z=dz, x=x, y=y), os.path.join(out, "dem", f"terrarium_{dz}_{x}_{y}.png"))
              for x in range(dx0, dx1 + 1) for y in range(dy0, dy1 + 1)]

    q = (f"[out:json][timeout:120];(way[\"building\"]({lat_s},{lon_w},{lat_n},{lon_e}););"
         "out tags geom;")
    osm_path = os.path.join(out, "osm_buildings.json")
    n_bld = None
    if not os.path.exists(osm_path):
        osm, err = None, None
        for url in OVERPASS * 2:                 # public mirrors, often busy
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers=UA)
                with urllib.request.urlopen(req, timeout=180) as r:
                    osm = json.loads(r.read())
                break
            except Exception as e:               # noqa: BLE001
                err = e
                time.sleep(5)
        if osm is None:
            raise SystemExit(f"OSM buildings not fetched: {err}")
        json.dump(osm, open(osm_path, "w"))
    n_bld = len(json.load(open(osm_path)).get("elements", []))

    ms_path = os.path.join(out, "ms_buildings.json")
    if not os.path.exists(ms_path):
        ms_buildings(a.lat, a.lon, dict(lat_n=lat_n, lat_s=lat_s, lon_w=lon_w, lon_e=lon_e), out)
    n_ms = len(json.load(open(ms_path)))
    info = dict(lat=a.lat, lon=a.lon, imagery=dict(source="Esri World Imagery Wayback", release=a.release,
                                                   zoom=a.zoom, x0=x0, y0=y0, n=a.tiles,
                                                   ok=sum(ok), failed=len(ok) - sum(ok)),
                box=dict(lat_n=lat_n, lat_s=lat_s, lon_w=lon_w, lon_e=lon_e),
                dem=dict(source="AWS Terrain Tiles (terrarium)", zoom=dz, ok=sum(dem_ok), failed=len(dem_ok) - sum(dem_ok)),
                osm=dict(source="OpenStreetMap via Overpass (ODbL)", buildings=n_bld),
                ms_buildings=dict(source="Microsoft Global ML Building Footprints (ODbL)", buildings=n_ms),
                fetched=time.strftime("%Y-%m-%dT%H:%M:%S"))
    json.dump(info, open(os.path.join(out, "fetch.json"), "w"), indent=1)
    print(json.dumps(info))


if __name__ == "__main__":
    main()
