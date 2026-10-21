#!/usr/bin/env python3
"""NAVERA mission bundle: everything a mission needs to fly OFFLINE, in one directory.

Before departure the operator chooses the route and downloads its bundle; in flight NAVERA
needs no network at all. A bundle holds the satellite map of the route's corridor (MBTiles,
with source, licence and date), the day-vision area made from it (tiles, DINOv2 descriptors,
learned DISK features of every map level the flight heights need), the IERS Earth-orientation
table and the star catalogue of the celestial fix, optionally the model weights, and a
manifest (sha256 and size of every file, versions, valid-until dates).

    mission_bundle.py plan  --start 35.8256,10.6385 --dest 35.6781,10.0963 \\
        [--route-file r.gpx|r.kml|r.waypoints|r.plan|r.json] [--waypoint lat,lon ...] \\
        [--corridor-m 2000] [--min-height-m 100] [--max-height-m 600] [--hfov 100] \\
        [--frame-width 1200] [--source onboard [esri | xyz:URL | fn:module:function ...]] [--json]
    mission_bundle.py build OUT_DIR <same options> [--yes] [--no-learned] [--no-dinov2]
        [--include-models] [--fetch-iers] [--extra NAME=PATH ...] [--allow-missing] [--max-mb 10240]
        [--progress-json]
    mission_bundle.py check BUNDLE_DIR [--replay REC_DIR] [--deep] [--date YYYY-MM-DD] [--json]
    mission_bundle.py env BUNDLE_DIR      environment lines pointing NAVERA at the bundle

`plan` shows the tile count, size and download/compute time BEFORE anything is downloaded;
`build` shows the same estimate and asks (or needs --yes) before it downloads. `check` runs with
the network OFF (re-executed in its own network namespace with `unshare -rn` when possible,
and every socket call is refused in-process as well) and proves that the bundle is complete
(every file's sha256, every corridor tile), that day matching works from its map alone
(synthetic frames rendered from its tiles; --replay: recorded camera frames with truth), that
the celestial time (IERS) and the star catalogue load from it alone. Exit code 0 = pass.

Layout of a bundle (all paths relative; the directory can be copied to the vehicle):

    manifest.json                    written last: a bundle without it is incomplete
    bundle.env                       DAY_DATASET_DIR, NAVERA_MBTILES, NAVERA_IERS_FILE, ... (absolute,
                                     for where it was built; `env` prints them for where it is now)
    map/corridor.mbtiles             corridor tiles only (zoom 17), metadata: source, licence, date, bbox
    day/images/tile_17_x_y.jpg       the day-vision area (prepare_area.py layout, DAY_DATASET_DIR=day)
    day/dataset.csv, day/area.json, day/descriptors_cache.npz (DINOv2, unless --no-dinov2)
    day/learned_features/*.npz       DISK features of the corridor per map level (unless --no-learned)
    celestial/finals2000A.all        IERS-A table (NAVERA_IERS_FILE)
    celestial/bsc5_mag4.5.csv        star catalogue (cn_subscriber allsky_catalogue)
    models/hub/...                   torch hub weights (--include-models; TORCH_HOME=models)
    extra/<name>                     --extra files (lens / IMU calibrations ...)

Tile sources (--source, first that has a tile wins): `onboard` (the onboard MBTiles,
--mbtiles or NAVERA_MBTILES), `esri` (Esri World Imagery XYZ, rate limited), `xyz:URL`
(any XYZ template, --licence required), `fn:module:function` — a function
`fetch(bbox=(west, south, east, north), source=name, zooms=[17]) -> MBTiles path` (the
licence-labelled source catalogue), called per block of the corridor; only corridor tiles
are copied into the bundle.

Python API (the operator web view calls the CLI with --progress-json / --json, or these):
    spec = MissionSpec(route=[[lat, lon], ...], corridor_width_m=2000, max_height_m=600)
    plan = plan_bundle(spec, make_sources(["onboard"]))         -> dict (estimate)
    manifest = build_bundle(spec, sources, out_dir, progress)   -> dict
    report = check_bundle(bundle_dir)                           -> dict (report["ok"])
"""
import argparse
import contextlib
import datetime as dt
import hashlib
import importlib
import io
import json
import math
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (os.path.join(ROOT, "day_pkg"), os.path.join(ROOT, "cn_pkg"), os.path.join(ROOT, "navera_common"),
           os.path.join(ROOT, "simulation_web")):
    if os.path.isdir(_p):                 # this checkout's packages before any installed ones
        sys.path.insert(0, _p)

from day_pkg.prepare_area import (corridor_tiles, densify_route, route_length_m,  # noqa: E402
                                  tile_nw, _tile_m)

FORMAT, FORMAT_VERSION = "navera-mission-bundle", 1
ZOOM = 17
MAP_FILE, DAY_DIR = "map/corridor.mbtiles", "day"
IERS_NAME, CATALOGUE_NAME = "celestial/finals2000A.all", "celestial/bsc5_mag4.5.csv"
EQUATOR_M = 40075016.7
# estimates (measured on this Jetson, see navera_tools/README.md "Mission bundle")
TILE_KB_DEFAULT = 20.0          # a zoom-17 JPEG tile when no tile of the corridor is at hand
DESC_KB, DESC_TILES_S = 3.0, 45.0
CHUNK_KB = 370.0                # a learned-feature chunk (k768, fp16 DISK) over land: 320 MB / 871 (Sousse-Kairouan)
CHUNK_S = 0.17                  # GPU seconds per learned chunk (DISK at 640 px, Orin Nano): 155.9 s / 934
COPY_TILES_S = 130.0            # local tiles copied per second (MBTiles, then area images; USB disk)
DOWNLOAD_LIMIT_MB = 10240.0
ESRI_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_LICENCE = ("Esri World Imagery (Esri, Maxar, Earthstar Geographics, and the GIS User Community). "
                "Storing tiles for offline use requires an Esri licence: evaluation / development only.")
MODEL_FILES = {   # torch hub checkpoints NAVERA's day pipeline loads (file -> what needs it)
    "dinov2_vits14_pretrain.pth": "DINOv2 ViT-S/14 retrieval (day fallback, descriptors_cache.npz)",
    "depth-save.pth": "DISK keypoints (learned matcher, learned_features)",
    "disk_lightglue_v0-1_arxiv-pth": "LightGlue for DISK (learned matcher)",
}
DINOV2_REPO_DIR = "facebookresearch_dinov2_main"


# ══ route ═════════════════════════════════════════════════════════════════
def parse_latlon(text: str) -> List[float]:
    """"lat,lon" -> [lat, lon], validated."""
    parts = [p.strip() for p in str(text).split(",")]
    if len(parts) < 2:
        raise ValueError(f"'{text}': expected lat,lon")
    lat, lon = float(parts[0]), float(parts[1])
    if not (-85.0 <= lat <= 85.0 and -180.0 <= lon <= 180.0):
        raise ValueError(f"'{text}': latitude must be within +-85 and longitude within +-180")
    return [lat, lon]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def load_route_file(path: str) -> List[List[float]]:
    """Waypoints of a GPX (track, else route, else waypoints), KML (first LineString, else the
    Points), JSON ([[lat, lon], ...] or {"route": ...}) or autopilot mission file (.waypoints QGC
    WPL 110 / .plan, via simulation_web.mission_prep)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path) as f:
            d = json.load(f)
        pts = d.get("route") if isinstance(d, dict) else d
        return [parse_latlon(f"{p[0]},{p[1]}") for p in pts]
    if ext in (".waypoints", ".plan", ".txt", ".mission"):
        from simulation_web.mission_prep import parse_mission
        with open(path) as f:
            return [[float(a), float(b)] for a, b in parse_mission(f.read())]
    root = ET.parse(path).getroot()
    if ext == ".gpx":
        for kind in ("trkpt", "rtept", "wpt"):
            pts = [[float(e.get("lat")), float(e.get("lon"))] for e in root.iter() if _local(e.tag) == kind]
            if pts:
                return [parse_latlon(f"{a},{b}") for a, b in pts]
        raise ValueError(f"{path}: no track, route or waypoint")
    if ext == ".kml":
        def coords(e):
            out = []
            for tok in (e.text or "").split():
                v = tok.split(",")
                out.append(parse_latlon(f"{v[1]},{v[0]}"))          # KML is lon,lat[,alt]
            return out
        for e in root.iter():
            if _local(e.tag) == "LineString":
                for c in e:
                    if _local(c.tag) == "coordinates":
                        return coords(c)
        pts = [p for e in root.iter() if _local(e.tag) == "Point" for c in e if _local(c.tag) == "coordinates"
               for p in coords(c)]
        if pts:
            return pts
        raise ValueError(f"{path}: no LineString or Point")
    raise ValueError(f"{path}: unknown route file type (gpx, kml, json, waypoints, plan)")


def route_from_args(start: Optional[str] = None, dest: Optional[str] = None, waypoints: Sequence[str] = (),
                    route_file: Optional[str] = None) -> List[List[float]]:
    """The route: a route file, or start + waypoints + destination."""
    if route_file:
        route = load_route_file(route_file)
    else:
        route = ([parse_latlon(start)] if start else []) + [parse_latlon(w) for w in waypoints] \
            + ([parse_latlon(dest)] if dest else [])
    if len(route) < 1:
        raise ValueError("no route: give --start and --dest, --waypoint ..., or --route-file")
    return route


# ══ heights, footprint, map levels ════════════════════════════════════════
def map_mpp(lat: float, zoom: int = ZOOM) -> float:
    """Map metres per pixel at this latitude."""
    return EQUATOR_M * math.cos(math.radians(lat)) / (2 ** zoom) / 256.0


def frame_mpp(height_m: float, hfov_deg: float, width_px: int) -> float:
    """Ground metres per pixel of a nadir frame."""
    return 2.0 * height_m * math.tan(math.radians(hfov_deg) / 2.0) / float(width_px)


def footprint_half_diag_m(height_m: float, hfov_deg: float, aspect: float) -> float:
    """Half the diagonal of a nadir frame's ground footprint (the map margin the matcher reads
    around the frame centre: LocalMatcher/LearnedMatcher margin_m)."""
    w = 2.0 * height_m * math.tan(math.radians(hfov_deg) / 2.0)
    return 0.5 * math.hypot(w, w * aspect)


def levels_for_heights(lat: float, min_h: float, max_h: float, hfov_deg: float, width_px: int,
                       zoom: int = ZOOM) -> List[int]:
    """Map levels (learned_matcher.map_level) the frames of this height band are matched on."""
    from day_pkg.learned_matcher import LearnedMatcher, map_level
    out = set()
    for h in [min_h + (max_h - min_h) * k / 40.0 for k in range(41)]:
        out.add(map_level(frame_mpp(h, hfov_deg, width_px) / map_mpp(lat, zoom), LearnedMatcher.MAX_LEVEL))
    return sorted(out)


def max_supported_height_m(lat: float, hfov_deg: float, width_px: int, zoom: int = ZOOM) -> float:
    """Highest flight the zoom-17 map serves: the coarsest map level (8x) matches frames up to
    ~1.5x its own scale (above, the frame is shrunk more than the map's detail allows)."""
    from day_pkg.learned_matcher import LearnedMatcher
    s_max = 1.5 * 2 ** LearnedMatcher.MAX_LEVEL
    return s_max * map_mpp(lat, zoom) * width_px / (2.0 * math.tan(math.radians(hfov_deg) / 2.0))


@dataclass
class MissionSpec:
    """What the operator chooses before departure."""
    route: List[List[float]]
    corridor_width_m: float = 2000.0       # full width the vehicle may stray in, centred on the route
    min_height_m: float = 100.0            # flight heights above ground
    max_height_m: float = 600.0
    hfov_deg: float = 100.0                # day camera: straightened view width (Insta360 crop as shipped)
    frame_width_px: int = 1200
    aspect: float = 0.75                   # frame height / width
    zoom: int = ZOOM
    learned: bool = True                   # precompute DISK features (GPU)
    dinov2: bool = True                    # precompute DINOv2 descriptors (GPU or CPU)
    include_models: bool = False
    extras: Dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.route:
            raise ValueError("empty route")
        if not (50.0 <= self.corridor_width_m <= 50_000.0):
            raise ValueError("corridor width must be 50 m .. 50 km")
        if not (5.0 <= self.min_height_m <= self.max_height_m <= 10_000.0):
            raise ValueError("heights: 5 m <= min <= max <= 10 km")
        if not (5.0 <= self.hfov_deg <= 170.0) or not (64 <= self.frame_width_px <= 10000):
            raise ValueError("hfov 5..170 deg, frame width 64..10000 px")

    @property
    def legs(self) -> List[List[float]]:
        """The route as flown: great-circle legs of at most 10 km (prepare_area.densify_route)."""
        return densify_route([[float(a), float(b)] for a, b in self.route])

    @property
    def lat_c(self) -> float:
        return sum(p[0] for p in self.route) / len(self.route)

    @property
    def buffer_m(self) -> float:
        """Map half-width around the route: the corridor plus the footprint of the highest frame."""
        return self.corridor_width_m / 2.0 + footprint_half_diag_m(self.max_height_m, self.hfov_deg, self.aspect)

    def bundle_id(self) -> str:
        key = json.dumps([[round(a, 6), round(b, 6)] for a, b in self.legs]
                         + [round(self.buffer_m, 1), self.zoom])
        return hashlib.sha1(key.encode()).hexdigest()[:12]


# ══ tile sources ══════════════════════════════════════════════════════════
Tile = Tuple[int, int]                    # XYZ (x, y) at the bundle's zoom
Put = Callable[[int, int, bytes], None]


class TileSource:
    """Where corridor tiles come from. has() is cheap and offline; fetch() may download."""
    name, licence, attribution, url, kind = "", "", "", "", ""
    rate_tps = 0.0                        # tiles/s it delivers (estimates); 0 = local copy
    imagery_date = "unknown"

    def has(self, zoom: int, tiles: Sequence[Tile]) -> set:
        """Subset of tiles available without downloading (local sources: all they hold)."""
        return set()

    def avg_tile_bytes(self, zoom: int, tiles: Sequence[Tile]) -> Optional[float]:
        return None

    def fetch(self, zoom: int, tiles: Sequence[Tile], put: Put,
              progress: Callable[[int, int, int], None]) -> List[Tile]:
        """Put every tile it can; returns the ones it could not provide."""
        raise NotImplementedError

    def describe(self) -> dict:
        return dict(name=self.name, kind=self.kind, licence=self.licence, attribution=self.attribution,
                    url=self.url, imagery_date=self.imagery_date)


def _mbtiles_meta(path: str) -> Dict[str, str]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return dict(con.execute("SELECT name, value FROM metadata").fetchall())
    except sqlite3.Error:
        return {}
    finally:
        con.close()


def _by_column(zoom: int, tiles: Iterable[Tile]):
    cols: Dict[int, List[int]] = {}
    for x, y in tiles:
        cols.setdefault(x, []).append(y)
    return cols


class MBTilesSource(TileSource):
    """Tiles of a local MBTiles map (the onboard map, or one a source catalogue downloaded)."""
    kind = "mbtiles"

    def __init__(self, path: str, name: Optional[str] = None, licence: Optional[str] = None):
        if not path or not os.path.exists(path):
            raise FileNotFoundError(f"MBTiles map {path!r} not found")
        self.path = path
        meta = _mbtiles_meta(path)
        self.meta = meta
        self.name = name or "onboard"
        self.attribution = meta.get("attribution") or meta.get("source") or meta.get("description", "")
        self.licence = licence or meta.get("licence") or meta.get("license") or (
            ESRI_LICENCE if "esri" in self.attribution.lower() else "not stated in the map's metadata")
        self.url = "file:" + os.path.basename(path)
        self.imagery_date = meta.get("imagery_date") or meta.get("date") or "unknown"

    def _rows(self, zoom, tiles, data: bool):
        n = 2 ** zoom
        con = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        col = "tile_data" if data else "length(tile_data)"
        try:
            for x, ys in _by_column(zoom, tiles).items():
                want = set(ys)
                lo, hi = n - 1 - max(ys), n - 1 - min(ys)
                for row, v in con.execute(f"SELECT tile_row, {col} FROM tiles WHERE zoom_level=? AND tile_column=? "
                                          "AND tile_row BETWEEN ? AND ?", (zoom, x, lo, hi)):
                    y = n - 1 - row
                    if y in want and v:
                        yield x, y, v
        finally:
            con.close()

    def has(self, zoom, tiles):
        return {(x, y) for x, y, _ in self._rows(zoom, tiles, False)}

    def avg_tile_bytes(self, zoom, tiles):
        sizes = [v for _, _, v in self._rows(zoom, tiles, False)]
        return sum(sizes) / len(sizes) if sizes else None

    def bytes_of(self, zoom, tiles) -> int:
        return int(sum(v for _, _, v in self._rows(zoom, tiles, False)))

    def fetch(self, zoom, tiles, put, progress):
        got = set()
        for i, (x, y, data) in enumerate(self._rows(zoom, tiles, True)):
            put(x, y, bytes(data))
            got.add((x, y))
            if i % 500 == 0:
                progress(len(got), len(tiles), 0)
        progress(len(got), len(tiles), len(tiles) - len(got))
        return [t for t in tiles if t not in got]


class _RateLimiter:
    def __init__(self, rate: float):
        self.dt, self.next, self.lock = 1.0 / rate, 0.0, threading.Lock()

    def wait(self, extra_s: float = 0.0):
        with self.lock:
            now = time.monotonic()
            self.next = max(self.next, now) + self.dt + extra_s
            delay = self.next - self.dt - now
        if delay > 0:
            time.sleep(delay)


class XYZSource(TileSource):
    """An XYZ tile server ({z} {x} {y} template), rate limited, polite to HTTP 429/503."""
    kind = "xyz"

    def __init__(self, url: str, name: str, licence: str, attribution: str = "", rate_tps: float = 8.0,
                 workers: int = 4, retries: int = 4, timeout_s: float = 20.0):
        if not licence:
            raise ValueError(f"tile source {name}: a licence statement is required")
        self.url, self.name, self.licence = url, name, licence
        self.attribution = attribution or name
        self.rate_tps, self.workers, self.retries, self.timeout_s = float(rate_tps), int(workers), retries, timeout_s
        self._limit = _RateLimiter(self.rate_tps)

    def _get(self, z, x, y) -> Optional[bytes]:
        req = urllib.request.Request(self.url.format(z=z, x=x, y=y),
                                     headers={"User-Agent": "NAVERA-mission-bundle/1.0"})
        for attempt in range(self.retries + 1):
            self._limit.wait()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                    data = r.read()
                    return data if r.status == 200 and len(data) > 100 else None
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code in (429, 503):                      # slow down: the provider asks for it
                    wait = float(e.headers.get("Retry-After") or 2 ** (attempt + 1))
                    self._limit.wait(min(wait, 60.0))
                    continue
                time.sleep(1.0 + attempt)
            except Exception:                                  # noqa: BLE001 — network: retry, then give up
                time.sleep(1.0 + attempt)
        return None

    def fetch(self, zoom, tiles, put, progress):
        failed, done = [], 0
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            for t, data in zip(tiles, ex.map(lambda t: self._get(zoom, *t), tiles)):
                done += 1
                if data:
                    put(t[0], t[1], data)
                else:
                    failed.append(t)
                if done % 50 == 0 or done == len(tiles):
                    progress(done, len(tiles), len(failed))
        return failed


class BBoxFunctionSource(TileSource):
    """A source catalogue function fetch(bbox, source, zooms) -> MBTiles path, called per block
    of BLOCK x BLOCK tiles of the corridor (a long diagonal route is not one huge bbox); the
    licence, attribution and date come from the returned MBTiles' metadata."""
    kind = "bbox-function"
    BLOCK = 16

    def __init__(self, fn: Callable, source_name: str, rate_tps: float = 8.0):
        self.fn, self.name, self.rate_tps = fn, source_name, rate_tps
        self.url = f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__name__', '?')}({source_name})"
        self.licence = "from the source catalogue (MBTiles metadata)"
        self.attribution = source_name

    @staticmethod
    def _bbox(zoom, xs, ys):
        n = 2 ** zoom
        north, west = tile_nw(min(xs), min(ys), zoom)
        south, east = tile_nw(max(xs) + 1, max(ys) + 1, zoom)
        # shrink by a hair so the neighbouring blocks' tiles are not requested too
        e = 1e-7 * 360.0 / n
        return (west + e, south + e, east - e, north - e)

    def fetch(self, zoom, tiles, put, progress):
        blocks: Dict[Tile, List[Tile]] = {}
        for x, y in tiles:
            blocks.setdefault((x // self.BLOCK, y // self.BLOCK), []).append((x, y))
        got, done = set(), 0
        for ts in blocks.values():
            path = self.fn(bbox=self._bbox(zoom, [t[0] for t in ts], [t[1] for t in ts]), source=self.name,
                           zooms=[zoom])
            src = MBTilesSource(path, self.name)
            self.licence, self.attribution, self.imagery_date = src.licence, src.attribution, src.imagery_date
            for t in src.fetch(zoom, ts, lambda x, y, d: (put(x, y, d), got.add((x, y))), lambda *a: None):
                pass
            done += len(ts)
            progress(done, len(tiles), done - len(got))
        return [t for t in tiles if t not in got]


def make_sources(names: Sequence[str], mbtiles: Optional[str] = None, licence: Optional[str] = None,
                 rate_tps: float = 8.0) -> List[TileSource]:
    """Tile sources from their CLI names (see the module doc), in priority order."""
    out: List[TileSource] = []
    for name in names:
        if name == "onboard":
            out.append(MBTilesSource(mbtiles or os.path.expanduser(os.environ.get("NAVERA_MBTILES", "")),
                                     "onboard", licence))
        elif name == "esri":
            out.append(XYZSource(ESRI_URL, "esri", ESRI_LICENCE, "Esri World Imagery", rate_tps=rate_tps))
        elif name.startswith("xyz:"):
            out.append(XYZSource(name[4:], "xyz", licence or "", rate_tps=rate_tps))
        elif name.startswith("mbtiles:"):
            out.append(MBTilesSource(name[8:], os.path.basename(name[8:]), licence))
        elif name.startswith("fn:"):
            mod, _, rest = name[3:].partition(":")
            func, _, src = rest.partition(":")
            out.append(BBoxFunctionSource(getattr(importlib.import_module(mod), func), src or func, rate_tps))
        else:
            raise ValueError(f"unknown tile source {name!r} (onboard, esri, xyz:URL, mbtiles:PATH, "
                             "fn:module:function[:source])")
    if not out:
        raise ValueError("no tile source")
    return out


# ══ plan (the estimate shown before anything is downloaded) ══════════════
def _models_dir() -> str:
    return os.path.join(os.path.expanduser(os.environ.get("TORCH_HOME", "~/.cache/torch")), "hub")


def plan_bundle(spec: MissionSpec, sources: Sequence[TileSource], out_dir: Optional[str] = None) -> dict:
    """Tiles, sizes and times of the bundle of this mission, nothing downloaded or written."""
    spec.validate()
    legs = spec.legs
    tiles = corridor_tiles(legs, spec.buffer_m, spec.zoom)
    left, per_source, avg = list(tiles), [], []
    local_bytes = 0
    for src in sources:
        have = src.has(spec.zoom, left) if left else set()
        if isinstance(src, MBTilesSource) and have:
            local_bytes += src.bytes_of(spec.zoom, list(have))
            a = src.avg_tile_bytes(spec.zoom, list(have))
            if a:
                avg.append(a)
        if src.rate_tps > 0:                     # a download source: it is asked for all that is left
            take = list(left)
        else:
            take = [t for t in left if t in have]
        per_source.append(dict(src.describe(), tiles=len(take), download=src.rate_tps > 0))
        taken = set(take)
        left = [t for t in left if t not in taken]
    n_dl = sum(p["tiles"] for p in per_source if p["download"])
    tile_b = (sum(avg) / len(avg)) if avg else TILE_KB_DEFAULT * 1024
    dl_bytes = n_dl * tile_b
    map_bytes = local_bytes + dl_bytes
    levels = levels_for_heights(spec.lat_c, spec.min_height_m, spec.max_height_m, spec.hfov_deg,
                                spec.frame_width_px, spec.zoom) if spec.learned else []
    from day_pkg.learned_matcher import LearnedMatcher
    chunks = {lv: len(LearnedMatcher.chunks_for_tiles(tiles, lv)) for lv in levels}
    n_chunks = sum(chunks.values())
    model_bytes = 0
    if spec.include_models:
        for f in MODEL_FILES:
            p = os.path.join(_models_dir(), "checkpoints", f)
            model_bytes += os.path.getsize(p) if os.path.exists(p) else 0
    iers_b, cat_b = 3.8e6, 3.0e4
    total = 2 * map_bytes + (len(tiles) * DESC_KB * 1024 if spec.dinov2 else 0) + n_chunks * CHUNK_KB * 1024 \
        + iers_b + cat_b + model_bytes
    rates = [s.rate_tps for s in sources if s.rate_tps > 0]
    t_dl = n_dl / min(rates) if n_dl and rates else 0.0
    t_copy = (len(tiles) - n_dl) / COPY_TILES_S + len(tiles) / COPY_TILES_S
    t_desc = len(tiles) / DESC_TILES_S if spec.dinov2 else 0.0
    t_learn = n_chunks * CHUNK_S
    free = None
    if out_dir:
        probe = os.path.dirname(os.path.abspath(out_dir.rstrip("/")))
        while probe and not os.path.exists(probe):
            probe = os.path.dirname(probe)
        free = shutil.disk_usage(probe).free
    ms = max_supported_height_m(spec.lat_c, spec.hfov_deg, spec.frame_width_px, spec.zoom)
    warnings = []
    if left:
        warnings.append(f"{len(left)} corridor tiles are in no source: day vision is blind there")
    if spec.max_height_m > ms:
        warnings.append(f"max height {spec.max_height_m:.0f} m is above what the zoom-{spec.zoom} map serves "
                        f"with this camera (~{ms:.0f} m)")
    if any(isinstance(s, XYZSource) and "esri" in s.url for s in sources):
        warnings.append("Esri World Imagery: offline storage needs an Esri licence (evaluation only)")
    return dict(
        id=spec.bundle_id(), route_points=len(spec.route), route_length_km=round(route_length_m(legs) / 1000, 2),
        corridor_width_m=spec.corridor_width_m, buffer_m=round(spec.buffer_m, 1), zoom=spec.zoom,
        tile_m=round(_tile_m(legs, spec.zoom), 1), tiles=len(tiles), tiles_missing=len(left),
        sources=per_source, download_tiles=n_dl, download_mb=round(dl_bytes / 2 ** 20, 1),
        map_mb=round(map_bytes / 2 ** 20, 1), avg_tile_kb=round(tile_b / 1024, 1),
        learned_levels=levels, learned_chunks=chunks, max_supported_height_m=round(ms),
        heights_m=[spec.min_height_m, spec.max_height_m], hfov_deg=spec.hfov_deg,
        total_mb=round(total / 2 ** 20, 1), free_mb=None if free is None else round(free / 2 ** 20),
        time_s=dict(download=round(t_dl), copy=round(t_copy), dinov2=round(t_desc), learned=round(t_learn),
                    total=round(t_dl + t_copy + t_desc + t_learn + 10)),
        warnings=warnings, _tiles=tiles)


def format_estimate(p: dict) -> str:
    """The estimate as the operator reads it."""
    t = p["time_s"]
    src = ", ".join(f"{s['name']} {s['tiles']}" + (" (download)" if s["download"] else "") for s in p["sources"])
    lines = [
        f"bundle {p['id']}: {p['route_length_km']} km route, corridor {p['corridor_width_m']:.0f} m wide "
        f"(map +-{p['buffer_m']:.0f} m: corridor + footprint at {p['heights_m'][1]:.0f} m), zoom {p['zoom']}",
        f"  tiles     {p['tiles']} ({src}); missing {p['tiles_missing']}",
        f"  download  {p['download_tiles']} tiles, {p['download_mb']} MB, ~{t['download'] / 60:.1f} min",
        f"  learned   levels {p['learned_levels']} -> {sum(p['learned_chunks'].values())} chunks, "
        f"~{t['learned'] / 60:.1f} min GPU",
        f"  size      ~{p['total_mb']:.0f} MB on disk" + (f" ({p['free_mb'] / 1024:.0f} GB free)"
                                                          if p['free_mb'] is not None else ""),
        f"  time      ~{t['total'] / 60:.1f} min in all",
    ]
    lines += [f"  WARNING   {w}" for w in p["warnings"]]
    return "\n".join(lines)


# ══ build ═════════════════════════════════════════════════════════════════
class Progress:
    """Progress as JSON lines on stdout ({"stage", "done", "total", ...}: the web view reads them)
    or as text on stderr."""

    def __init__(self, json_lines: bool = False):
        self.json, self._last = json_lines, {}

    def __call__(self, stage: str, done: int = 0, total: int = 0, **extra):
        if self.json:
            print(json.dumps(dict(stage=stage, done=done, total=total, **extra)), flush=True)
            return
        now = time.monotonic()
        if done != total and now - self._last.get(stage, 0.0) < 2.0:
            return
        self._last[stage] = now
        more = " ".join(f"{k}={v}" for k, v in extra.items() if not isinstance(v, (dict, list)))
        print(f"[{stage}] {done}/{total} {more}".rstrip(), file=sys.stderr, flush=True)


class _ProgressRelay(io.TextIOBase):
    """prepare_area prints its own JSON progress lines: relayed as day_<stage>."""

    def __init__(self, progress: Progress):
        self.p, self.buf = progress, ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            try:
                d = json.loads(line)
                self.p("day_" + str(d.pop("stage", "?")), d.pop("done", 0), d.pop("total", 0),
                       **{k: v for k, v in d.items() if k != "terrain"})
            except ValueError:
                if line.strip():
                    print(line, file=sys.stderr)
        return len(s)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _tree_sha256(path: str) -> str:
    """One hash of a directory's files (names and contents), for a model code directory."""
    h = hashlib.sha256()
    for d, dirs, files in sorted(os.walk(path)):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, path).encode() + b"\0" + sha256_file(p).encode())
    return h.hexdigest()


def _write_mbtiles(path: str, spec: MissionSpec, tiles: Sequence[Tile], sources: Sequence[TileSource],
                   progress: Progress) -> dict:
    """The corridor MBTiles: every corridor tile the sources have, then its metadata."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT)")
    con.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
    con.execute("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)")
    n = 2 ** spec.zoom
    lock = threading.Lock()
    counts: Dict[str, int] = {}
    left = list(tiles)
    used = []
    for src in sources:
        if not left:
            break
        name = src.name

        def put(x, y, data, _name=name):
            with lock:
                con.execute("INSERT OR IGNORE INTO tiles VALUES (?, ?, ?, ?)", (spec.zoom, x, n - 1 - y, data))
                counts[_name] = counts.get(_name, 0) + 1

        if src.rate_tps > 0:
            todo = left
        else:
            have = src.has(spec.zoom, left)
            todo = [t for t in left if t in have]
        if not todo:
            continue
        stage = "download" if src.rate_tps > 0 else "copy"
        t0 = time.time()
        failed = set(src.fetch(spec.zoom, todo, put,
                               lambda d, t, f, _s=stage, _n=name: progress(_s, d, t, source=_n, failed=f)))
        with lock:
            con.commit()
        done_set = set(todo)
        left = [t for t in left if t not in done_set or t in failed]
        used.append(dict(src.describe(), tiles=counts.get(name, 0), seconds=round(time.time() - t0, 1)))
    lats = [tile_nw(x, y, spec.zoom)[0] for x, y in tiles] + [tile_nw(x, y + 1, spec.zoom)[0] for x, y in tiles]
    lons = [tile_nw(x, y, spec.zoom)[1] for x, y in tiles] + [tile_nw(x + 1, y, spec.zoom)[1] for x, y in tiles]
    bbox = [min(lons), min(lats), max(lons), max(lats)]
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = {
        "name": f"NAVERA mission corridor {spec.bundle_id()}", "format": "jpg", "type": "baselayer",
        "version": "1", "minzoom": str(spec.zoom), "maxzoom": str(spec.zoom),
        "bounds": ",".join(f"{v:.6f}" for v in bbox),
        "center": f"{(bbox[0] + bbox[2]) / 2:.6f},{(bbox[1] + bbox[3]) / 2:.6f},{spec.zoom}",
        "source": "; ".join(f"{u['name']} ({u['tiles']} tiles)" for u in used),
        "attribution": "; ".join(sorted({u["attribution"] for u in used if u["attribution"]})),
        "licence": " | ".join(sorted({u["licence"] for u in used if u["licence"]})),
        "imagery_date": "; ".join(sorted({str(u["imagery_date"]) for u in used})),
        "downloaded": now,
        "navera_corridor": json.dumps(dict(route=spec.legs, buffer_m=round(spec.buffer_m, 1))),
    }
    con.executemany("INSERT INTO metadata VALUES (?, ?)", list(meta.items()))
    con.commit()
    con.close()
    return dict(file=MAP_FILE, zooms=[spec.zoom], tiles=sum(counts.values()), tiles_needed=len(tiles),
                missing=[list(t) for t in left], bbox=bbox, sources=used, downloaded=now,
                imagery_date=meta["imagery_date"], licence=meta["licence"])


def iers_coverage(path: str) -> dict:
    """Dates an IERS-A file covers: measured (final/rapid 'I') and predicted ('P') UT1-UTC."""
    from astropy.time import Time
    from astropy.utils import iers
    import numpy as np
    t = iers.IERS_A.open(path)
    flag, mjd = np.array(t["UT1Flag_A"]), np.array(t["MJD"].value if hasattr(t["MJD"], "value") else t["MJD"])
    meas = mjd[flag == "I"]
    pred = mjd[(flag == "I") | (flag == "P")]
    return dict(measured_from=Time(float(meas.min()), format="mjd").iso[:10],
                measured_until=Time(float(meas.max()), format="mjd").iso[:10],
                predicted_until=Time(float(pred.max()), format="mjd").iso[:10])


def _git_version() -> str:
    try:
        return subprocess.run(["git", "-C", ROOT, "describe", "--always", "--dirty", "--tags"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _versions() -> dict:
    out = {"navera": _git_version(), "python": sys.version.split()[0]}
    for mod in ("numpy", "cv2", "torch", "kornia", "astropy"):
        try:
            out[mod] = importlib.import_module(mod).__version__
        except Exception:                                    # noqa: BLE001 — not installed: not required here
            out[mod] = None
    return out


def _learned_features(spec: MissionSpec, day_dir: str, tiles, levels, progress: Progress) -> dict:
    from day_pkg.learned_matcher import LearnedMatcher
    m = LearnedMatcher(os.path.join(day_dir, "images"), zoom=spec.zoom)
    out = dict(dir="day/learned_features", levels=levels, per_chunk=m.PER_CHUNK, half=m.half,
               chunk_px=m.CHUNK, overlap_px=m.OVERLAP, chunks={})
    t0 = time.time()
    for lv in levels:
        out["chunks"][str(lv)] = m.warm_tiles(tiles, lv, lambda d, t, _lv=lv: progress("learned", d, t, level=_lv))
    out["seconds"] = round(time.time() - t0, 1)
    del m
    try:
        import torch
        torch.cuda.empty_cache()
    except Exception:                                        # noqa: BLE001
        pass
    return out


def required_models(spec: MissionSpec) -> List[dict]:
    """The weight files NAVERA's day pipeline loads for this bundle, with their sha256 on this machine."""
    out = []
    hub = _models_dir()
    for f, what in MODEL_FILES.items():
        p = os.path.join(hub, "checkpoints", f)
        ok = os.path.exists(p)
        out.append(dict(name=f, used_by=what, path=f"models/hub/checkpoints/{f}",
                        sha256=sha256_file(p) if ok else None, size=os.path.getsize(p) if ok else None,
                        included=bool(spec.include_models and ok)))
    repo = os.path.join(hub, DINOV2_REPO_DIR)
    if os.path.isdir(repo):
        out.append(dict(name=DINOV2_REPO_DIR, used_by="DINOv2 model code (torch.hub)",
                        path=f"models/hub/{DINOV2_REPO_DIR}",
                        tree_sha256=_tree_sha256(repo), included=spec.include_models))
    return out


def env_lines(bundle_dir: str, manifest: dict) -> List[str]:
    """Environment of a NAVERA unit flying this bundle (where the bundle is now)."""
    b = os.path.abspath(bundle_dir)
    lines = [f"DAY_DATASET_DIR={b}/{DAY_DIR}", f"NAVERA_MBTILES={b}/{MAP_FILE}", f"NAVERA_IERS_FILE={b}/{IERS_NAME}",
             f"NAVERA_STAR_CATALOGUE={b}/{CATALOGUE_NAME}", f"NAVERA_BUNDLE_DIR={b}"]
    if any(m.get("included") for m in manifest.get("models", [])):
        lines.append(f"TORCH_HOME={b}/models")
    return lines


def build_bundle(spec: MissionSpec, sources: Sequence[TileSource], out_dir: str,
                 progress: Optional[Progress] = None, allow_missing: bool = False, iers_file: Optional[str] = None,
                 fetch_iers: bool = False, catalogue: Optional[str] = None, force: bool = False,
                 plan: Optional[dict] = None) -> dict:
    """Build the bundle in <out_dir>.partial, then move it to out_dir (never half-built)."""
    progress = progress or Progress()
    t_start = time.time()
    plan = plan or plan_bundle(spec, sources, out_dir)
    out_dir = os.path.abspath(out_dir.rstrip("/"))
    if os.path.exists(out_dir) and not force:
        raise FileExistsError(f"{out_dir} exists (use --force to replace it)")
    tmp = out_dir + ".partial"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, "map"))
    tiles = plan["_tiles"]
    stages = {}

    # 1. the corridor map
    t0 = time.time()
    progress("map", 0, len(tiles))
    map_info = _write_mbtiles(os.path.join(tmp, MAP_FILE), spec, tiles, sources, progress)
    stages["map_s"] = round(time.time() - t0, 1)
    if map_info["missing"] and not allow_missing:
        raise RuntimeError(f"{len(map_info['missing'])} of {len(tiles)} corridor tiles could not be obtained "
                           f"(left in {tmp}); add a source or use --allow-missing")

    # 2. the day-vision area from that map alone
    t0 = time.time()
    from day_pkg import prepare_area
    with contextlib.redirect_stdout(_ProgressRelay(progress)):
        area = prepare_area.prepare(os.path.join(tmp, MAP_FILE), os.path.join(tmp, DAY_DIR), spec.legs,
                                    spec.buffer_m, spec.zoom, descriptors=spec.dinov2)
    area["mbtiles"] = "../" + MAP_FILE                     # relocatable
    with open(os.path.join(tmp, DAY_DIR, "area.json"), "w") as f:
        json.dump(area, f)
    stages["day_s"] = round(time.time() - t0, 1)
    learned = None
    if spec.learned and plan["learned_levels"]:
        t0 = time.time()
        present = [tuple(t) for t in tiles if list(t) not in map_info["missing"]]
        learned = _learned_features(spec, os.path.join(tmp, DAY_DIR), present, plan["learned_levels"], progress)
        stages["learned_s"] = round(time.time() - t0, 1)

    # 3. celestial: IERS table and star catalogue
    os.makedirs(os.path.join(tmp, "celestial"))
    iers_src = os.path.expanduser(iers_file or os.environ.get("NAVERA_IERS_FILE", "~/navera_data/iers/finals2000A.all"))
    if fetch_iers:
        progress("iers_fetch", 0, 1)
        r = subprocess.run([sys.executable, os.path.join(HERE, "fetch_iers.py"), "--out", iers_src],
                           capture_output=True, text=True, timeout=300)
        progress("iers_fetch", 1, 1, ok=r.returncode == 0, info=(r.stdout or r.stderr).strip()[-200:])
    if not os.path.exists(iers_src):
        raise FileNotFoundError(f"IERS table {iers_src} not found: run navera_tools/fetch_iers.py "
                                "(or --fetch-iers) before building")
    shutil.copy2(iers_src, os.path.join(tmp, IERS_NAME))
    cov = iers_coverage(os.path.join(tmp, IERS_NAME))
    if catalogue is None:
        from cn_pkg.allsky import BUNDLED_CATALOGUE
        catalogue = BUNDLED_CATALOGUE
    shutil.copy2(catalogue, os.path.join(tmp, CATALOGUE_NAME))
    from cn_pkg.allsky import load_bsc5
    _, _, mags = load_bsc5(os.path.join(tmp, CATALOGUE_NAME))

    # 4. models and extra files
    models = required_models(spec)
    if spec.include_models:
        for m in models:
            src = os.path.join(_models_dir(), os.path.relpath(m["path"], "models/hub"))
            dst = os.path.join(tmp, m["path"])
            if os.path.isdir(src):
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", ".git"))
            elif os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
        trusted = os.path.join(_models_dir(), "trusted_list")      # torch.hub writes it on load otherwise
        if os.path.exists(trusted):
            shutil.copy2(trusted, os.path.join(tmp, "models", "hub", "trusted_list"))
    extras = {}
    for name, path in spec.extras.items():
        dst = os.path.join(tmp, "extra", os.path.basename(name))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.expanduser(path), dst)
        extras[name] = os.path.relpath(dst, tmp)

    # 5. environment file, then the manifest (last): every file's sha256 and size
    with open(os.path.join(tmp, "bundle.env"), "w") as f:
        f.write("# NAVERA mission bundle environment (paths where it was built; "
                "`mission_bundle.py env DIR` prints them for where it is now)\n")
        f.write("\n".join(env_lines(out_dir, dict(models=models))) + "\n")
    progress("manifest", 0, 1)
    files = {}
    for d, dirs, fs in os.walk(tmp):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in fs:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, tmp)
            files[rel] = dict(size=os.path.getsize(p), sha256=sha256_file(p))
    total = sum(v["size"] for v in files.values())
    created = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = dict(
        format=FORMAT, format_version=FORMAT_VERSION, id=spec.bundle_id(), created=created,
        mission=dict(asdict(spec), legs=spec.legs, buffer_m=round(spec.buffer_m, 1),
                     route_length_km=plan["route_length_km"], learned_levels=plan["learned_levels"],
                     max_supported_height_m=plan["max_supported_height_m"]),
        map=map_info,
        day=dict(dataset_dir=DAY_DIR, images=len(os.listdir(os.path.join(tmp, DAY_DIR, "images"))),
                 dinov2_descriptors=spec.dinov2, terrain=area.get("terrain"), learned_features=learned),
        celestial=dict(iers=dict(file=IERS_NAME, source=iers_src, **cov),
                       catalogue=dict(file=CATALOGUE_NAME, stars=int(len(mags)), limit_mag=float(max(mags)),
                                      epoch="J2000 (ICRS), proper motion not applied", expires=None)),
        models=models, extras=extras, versions=_versions(),
        valid_until=dict(iers_predictions=cov["predicted_until"], overall=cov["predicted_until"],
                         note="after this date UT1-UTC is held at the table's last value (< 0.4 km on the "
                              "celestial fix); refresh with --fetch-iers"),
        estimate={k: v for k, v in plan.items() if not k.startswith("_")},
        build=dict(stages, total_s=round(time.time() - t_start, 1)),
        files=files, totals=dict(files=len(files), bytes=total, mb=round(total / 2 ** 20, 1)),
    )
    with open(os.path.join(tmp, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.replace(tmp, out_dir)
    progress("done", len(files), len(files), mb=manifest["totals"]["mb"], seconds=manifest["build"]["total_s"])
    return manifest


# ══ check (network OFF) ═══════════════════════════════════════════════════
class NetworkGuard:
    """Refuses every network call in this process (AF_UNIX sockets excepted) and records them."""

    def __init__(self):
        self.attempts: List[str] = []
        self._saved = {}

    def _deny(self, what):
        self.attempts.append(what)
        raise OSError(f"network blocked by mission bundle check ({what})")

    def __enter__(self):
        guard = self
        real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex
        self._saved = dict(connect=real_connect, connect_ex=real_connect_ex, gai=socket.getaddrinfo,
                           cc=socket.create_connection)

        def connect(sock, addr):
            if sock.family == getattr(socket, "AF_UNIX", None):
                return real_connect(sock, addr)
            guard._deny(f"connect {addr}")

        def connect_ex(sock, addr):
            if sock.family == getattr(socket, "AF_UNIX", None):
                return real_connect_ex(sock, addr)
            guard._deny(f"connect {addr}")

        socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
        socket.getaddrinfo = lambda host, *a, **k: guard._deny(f"resolve {host}")
        socket.create_connection = lambda addr, *a, **k: guard._deny(f"connect {addr}")
        return self

    def __exit__(self, *exc):
        socket.socket.connect, socket.socket.connect_ex = self._saved["connect"], self._saved["connect_ex"]
        socket.getaddrinfo, socket.create_connection = self._saved["gai"], self._saved["cc"]
        return False


def network_state() -> dict:
    """What the network looks like from here: interfaces, and whether an outside address answers."""
    try:
        ifaces = sorted(name for _, name in socket.if_nameindex())     # this process's network namespace
    except OSError:
        ifaces = []
    probe = None
    try:
        s = socket.create_connection(("1.1.1.1", 53), timeout=2)
        s.close()
        probe = "outbound connection SUCCEEDED"
    except OSError as e:
        probe = f"outbound connection failed: {e}"
    return dict(interfaces=ifaces, probe=probe, offline=not probe.startswith("outbound connection SUCCEEDED"),
                netns=os.environ.get("NAVERA_BUNDLE_NETNS") == "1")


def _render_frame(images_dir: str, lat: float, lon: float, zoom: int, size: Tuple[int, int], f_mpp: float,
                  heading_deg: float):
    """A nadir frame rendered from the map tiles: centre (lat, lon), top towards heading_deg."""
    import cv2
    import numpy as np
    from day_pkg.local_matcher import tile_xy
    w, h = size
    s = f_mpp / map_mpp(lat, zoom)
    fx, fy = tile_xy(lat, lon, zoom)
    cx, cy = fx * 256.0, fy * 256.0
    r = int(math.hypot(w, h) / 2 * s) + 4
    x0, y0 = int(cx) - r, int(cy) - r
    mosaic = np.zeros((2 * r, 2 * r, 3), np.uint8)
    for ty in range(y0 // 256, (y0 + 2 * r) // 256 + 1):
        for tx in range(x0 // 256, (x0 + 2 * r) // 256 + 1):
            t = cv2.imread(os.path.join(images_dir, f"tile_{zoom}_{tx}_{ty}.jpg"))
            if t is None:
                continue
            ox, oy = tx * 256 - x0, ty * 256 - y0
            sx, sy, dx, dy = max(0, -ox), max(0, -oy), max(0, ox), max(0, oy)
            cw, ch = min(256 - sx, 2 * r - dx), min(256 - sy, 2 * r - dy)
            if cw > 0 and ch > 0:
                mosaic[dy:dy + ch, dx:dx + cw] = t[sy:sy + ch, sx:sx + cw]
    c, sn = math.cos(math.radians(heading_deg)), math.sin(math.radians(heading_deg))
    # frame pixel (u, v) -> mosaic pixel: s * R(heading) (u - w/2, v - h/2) + centre
    A = np.float32([[s * c, -s * sn, 0], [s * sn, s * c, 0]])
    A[:, 2] = np.float32([cx - x0, cy - y0]) - A[:, :2] @ np.float32([w / 2.0, h / 2.0])
    return cv2.warpAffine(mosaic, A, (w, h), flags=cv2.INTER_AREA | cv2.WARP_INVERSE_MAP)


def _offset(p, dist_m, bearing_rad):
    return (p[0] + dist_m * math.cos(bearing_rad) / 111320.0,
            p[1] + dist_m * math.sin(bearing_rad) / (111320.0 * math.cos(math.radians(p[0]))))


def _err_m(a, b):
    from day_pkg.prepare_area import _haversine_m
    return _haversine_m(a, b)


def _summary(rows) -> dict:
    import numpy as np
    acc = [r for r in rows if r["accepted"]]
    errs = [r["err_m"] for r in acc]
    return dict(frames=len(rows), accepted=len(acc), wrong_over_50m=sum(e > 50 for e in errs),
                err_median_m=round(float(np.median(errs)), 1) if errs else None,
                err_max_m=round(float(max(errs)), 1) if errs else None,
                ms_per_frame=round(float(np.mean([r["ms"] for r in rows])), 0) if rows else None)


def _textured_distances(total_m: float, stretches, points: int) -> List[float]:
    """points distances along the route spread evenly over its textured parts (the area's terrain
    profile lists the featureless stretches, sea or uniform sand, in km: nothing to match there)."""
    cuts = sorted((max(0.0, a * 1000.0), min(total_m, b * 1000.0)) for a, b in stretches)
    parts, x = [], 0.0
    for a, b in cuts:
        if a > x:
            parts.append((x, a))
        x = max(x, b)
    if x < total_m:
        parts.append((x, total_m))
    length = sum(b - a for a, b in parts)
    if length <= 0:
        return []
    out = []
    for k in range(points):
        t = length * (k + 0.5) / points
        for a, b in parts:
            if t <= b - a:
                out.append(a + t)
                break
            t -= b - a
    return out


def day_selftest(bundle: str, manifest: dict, matcher=None, points: int = 6) -> dict:
    """Synthetic nadir frames rendered from the bundle's tiles along the textured parts of the route
    (various headings, a 150 m prior error), located with the day matcher reading ONLY the bundle's
    day/images."""
    import numpy as np
    from day_pkg.local_matcher import LocalMatcher
    from day_pkg.prepare_area import point_along
    m = manifest["mission"]
    images = os.path.join(bundle, DAY_DIR, "images")
    M = matcher or LocalMatcher(images, zoom=m["zoom"], device="cpu")
    legs, total = m["legs"], route_length_m(m["legs"])
    rng = np.random.default_rng(3)
    rows = []
    stretches = (manifest["day"].get("terrain") or {}).get("stretches") or []
    levels = m.get("learned_levels") or [0, 1]
    for k, d in enumerate(_textured_distances(total, stretches, points)):
        p, _ = point_along(legs, d)
        # the frame's scale cycles through the bundle's map levels (a level it does not carry would
        # make the learned matcher compute chunks: not what flies)
        f_mpp = map_mpp(p[0], m["zoom"]) * 2 ** levels[k % len(levels)]
        hdg = float(k * 97 % 360)
        img = _render_frame(images, p[0], p[1], m["zoom"], (640, 480), f_mpp, hdg)
        if img.std() < 12:                                  # sea / uniform ground: nothing to match
            rows.append(dict(point=[round(p[0], 6), round(p[1], 6)], skipped="featureless", accepted=False,
                             err_m=None, ms=0.0))
            continue
        prior = _offset(p, 150.0, rng.uniform(0, 2 * math.pi))
        t0 = time.time()
        r = M.locate(img, prior, 300.0, f_mpp, scale_tol=0.15, heading_deg=hdg, heading_tol_deg=15.0)
        ok = bool(r.get("accepted"))
        rows.append(dict(point=[round(p[0], 6), round(p[1], 6)], heading=hdg, accepted=ok,
                         err_m=round(_err_m((r["predicted_lat"], r["predicted_lon"]), p), 1) if ok else None,
                         inliers=r.get("inliers"), ms=round((time.time() - t0) * 1000), reason=r.get("reason")))
    tested = [r for r in rows if not r.get("skipped")]
    s = _summary(tested)
    s["skipped_featureless"] = len(rows) - len(tested)
    s["ok"] = bool(tested) and s["accepted"] >= max(1, math.ceil(0.8 * len(tested))) and s["wrong_over_50m"] == 0 \
        and (s["err_max_m"] or 0) < 15.0
    s["rows"] = rows
    return s


def day_replay(bundle: str, manifest: dict, rec_dir: str, limit: int = 30, gpu: bool = False) -> dict:
    """Recorded camera frames with truth (screen_flight.py --record: frames.jsonl), located with the
    day matcher reading ONLY the bundle (prior = truth moved 0-150 m, search 400 m, as
    bench/eval_recorded.py)."""
    import cv2
    import numpy as np
    from day_pkg.local_matcher import LocalMatcher
    M = LocalMatcher(os.path.join(bundle, DAY_DIR, "images"), zoom=manifest["mission"]["zoom"],
                     device="auto" if gpu else "cpu")
    meta = [json.loads(line) for line in open(os.path.join(rec_dir, "frames.jsonl"))]
    meta = [x for x in meta if x.get("mpp") and x.get("truth") and (x.get("truth_unc_m") or 0) <= 10.0]
    if limit and len(meta) > limit:
        meta = [meta[int(i)] for i in np.linspace(0, len(meta) - 1, limit)]
    rng = np.random.default_rng(7)
    rows = []
    for x in meta:
        img = cv2.imread(os.path.join(rec_dir, x["file"]))
        if img is None:
            continue
        truth = tuple(x["truth"])
        prior = _offset(truth, rng.uniform(0, 150.0), rng.uniform(0, 2 * math.pi))
        t0 = time.time()
        r = M.locate(img, prior, 400.0, x["mpp"], scale_tol=0.15, heading_deg=x.get("rot_deg") or 0.0,
                     heading_tol_deg=15.0)
        ok = bool(r.get("accepted"))
        rows.append(dict(file=x["file"], height_m=x.get("height_m"), accepted=ok, inliers=r.get("inliers"),
                         err_m=round(_err_m((r["predicted_lat"], r["predicted_lon"]), truth), 1) if ok else None,
                         ms=round((time.time() - t0) * 1000)))
    s = _summary(rows)
    s.update(rec_dir=rec_dir, rows=rows)
    return s


def _learned_check(bundle: str, manifest: dict, deep: bool) -> dict:
    """Every learned-feature chunk the corridor needs is in the bundle; deep: DISK + LightGlue load
    offline and locate the synthetic frames with no chunk computed."""
    import numpy as np
    lf = manifest["day"].get("learned_features")
    if not lf:
        return dict(ok=True, present=False)
    from day_pkg.learned_matcher import LearnedMatcher
    d = os.path.join(bundle, lf["dir"])
    z = manifest["mission"]["zoom"]
    tiles = [tuple(t) for t in corridor_tiles(manifest["mission"]["legs"], manifest["mission"]["buffer_m"], z)
             if list(t) not in manifest["map"]["missing"]]
    missing = []
    for lv in lf["levels"]:
        sfx = f"_L{lv}" if lv else ""
        for gx, gy in LearnedMatcher.chunks_for_tiles(tiles, lv):
            name = f"{z}_{gx}_{gy}{sfx}_k{lf['per_chunk']}{'h' if lf['half'] else ''}.npz"
            if not os.path.exists(os.path.join(d, name)):
                missing.append([lv, gx, gy])
    sample = sorted(os.listdir(d))[:: max(1, len(os.listdir(d)) // 20)]
    for f in sample:
        with np.load(os.path.join(d, f)) as a:
            if a["k"].shape[0] != a["d"].shape[0] or (a["d"].size and a["d"].shape[1] != 128):
                missing.append(["corrupt", f])
    out = dict(ok=not missing, present=True, levels=lf["levels"], chunks=lf["chunks"], missing=missing[:20],
               n_missing=len(missing))
    if deep:
        before = set(os.listdir(d))
        m = LearnedMatcher(os.path.join(bundle, DAY_DIR, "images"), zoom=z)
        st = day_selftest(bundle, manifest, matcher=m)
        st.pop("rows", None)
        new = set(os.listdir(d)) - before
        for f in new:                          # the check leaves the bundle as it found it
            os.remove(os.path.join(d, f))
        out.update(selftest=st, computed_in_check=len(new))
        out["ok"] = out["ok"] and st["ok"] and out["computed_in_check"] == 0
    return out


def _models_check(bundle: str, manifest: dict, deep: bool) -> dict:
    hub = os.path.join(bundle, "models", "hub") if any(m.get("included") for m in manifest["models"]) \
        else _models_dir()
    rows, ok = [], True
    for m in manifest["models"]:
        p = os.path.join(hub, os.path.relpath(m["path"], "models/hub"))
        if "sha256" in m:
            have = os.path.exists(p)
            match = have and m["sha256"] is not None and sha256_file(p) == m["sha256"]
            rows.append(dict(name=m["name"], found=have, sha256_match=match, where=hub))
            ok = ok and (match or not m.get("included"))
    out = dict(ok=ok, hub=hub, files=rows)
    if deep:
        os.environ["TORCH_HOME"] = os.path.dirname(hub)
        import torch
        import kornia.feature as KF
        torch.hub.set_dir(hub)
        sys.dont_write_bytecode = True         # no __pycache__ written into the bundle's model code
        loaded = []
        if manifest["day"].get("dinov2_descriptors"):
            from day_pkg.nodes.day_localizer import DINOV2_HUB_REPO
            torch.hub.load(DINOV2_HUB_REPO, "dinov2_vits14", pretrained=True)      # as day_localizer does
            loaded.append("dinov2_vits14")
        if manifest["day"].get("learned_features"):
            KF.DISK.from_pretrained("depth")
            KF.LightGlueMatcher("disk")
            loaded += ["DISK depth", "LightGlue disk"]
        out["loaded_offline"] = loaded
    return out


def check_bundle(bundle: str, replay: Optional[str] = None, deep: bool = False, allow_missing: bool = False,
                 mission_date: Optional[str] = None, replay_limit: int = 30, gpu: bool = False) -> dict:
    """Prove, with the network refused, that the bundle is complete and that day matching, the
    celestial time and the star catalogue work from it alone. report["ok"] is the verdict."""
    bundle = os.path.abspath(bundle)
    report = dict(bundle=bundle, network=network_state(), checks={})
    C = report["checks"]
    with NetworkGuard() as guard:
        # manifest and files
        mpath = os.path.join(bundle, "manifest.json")
        if not os.path.exists(mpath):
            report.update(ok=False, error="no manifest.json: the bundle is incomplete (build interrupted?)")
            return report
        manifest = json.load(open(mpath))
        if manifest.get("format") != FORMAT:
            report.update(ok=False, error=f"not a {FORMAT}")
            return report
        bad, missing_f = [], []
        for rel, v in manifest["files"].items():
            p = os.path.join(bundle, rel)
            if not os.path.exists(p):
                missing_f.append(rel)
            elif os.path.getsize(p) != v["size"] or sha256_file(p) != v["sha256"]:
                bad.append(rel)
        listed = set(manifest["files"]) | {"manifest.json"}
        extra = sorted(os.path.relpath(os.path.join(d, f), bundle) for d, _, fs in os.walk(bundle) for f in fs
                       if "__pycache__" not in d.split(os.sep)
                       if os.path.relpath(os.path.join(d, f), bundle) not in listed)
        C["files"] = dict(ok=not bad and not missing_f, listed=len(manifest["files"]), missing=missing_f[:20],
                          sha256_mismatch=bad[:20], unlisted=extra[:20], n_unlisted=len(extra))

        # map: corridor coverage, metadata, tiles decode
        import cv2
        import numpy as np
        m = manifest["mission"]
        z = m["zoom"]
        need = corridor_tiles(m["legs"], m["buffer_m"], z)
        mb = os.path.join(bundle, MAP_FILE)
        meta = _mbtiles_meta(mb)
        con = sqlite3.connect(f"file:{mb}?mode=ro", uri=True)
        have = {(x, 2 ** z - 1 - r)
                for x, r in con.execute("SELECT tile_column, tile_row FROM tiles WHERE zoom_level=?", (z,))}
        sample = con.execute("SELECT tile_data FROM tiles ORDER BY random() LIMIT 25").fetchall()
        con.close()
        decoded = sum(cv2.imdecode(np.frombuffer(s[0], np.uint8), cv2.IMREAD_COLOR) is not None for s in sample)
        lack = [t for t in need if t not in have]
        imgs = os.path.join(bundle, DAY_DIR, "images")
        lack_img = [t for t in need
                    if t in have and not os.path.exists(os.path.join(imgs, f"tile_{z}_{t[0]}_{t[1]}.jpg"))]
        meta_ok = all(meta.get(k) for k in ("source", "licence", "bounds", "minzoom", "downloaded"))
        C["map"] = dict(ok=(not lack or allow_missing) and not lack_img and decoded == len(sample) and meta_ok,
                        tiles=len(have), corridor_tiles=len(need), missing=len(lack), missing_images=len(lack_img),
                        decoded_sample=f"{decoded}/{len(sample)}", source=meta.get("source"),
                        licence=meta.get("licence"), imagery_date=meta.get("imagery_date"),
                        downloaded=meta.get("downloaded"), bounds=meta.get("bounds"))

        # day: DINOv2 cache, synthetic frames, learned features, replay
        if manifest["day"].get("dinov2_descriptors"):
            with np.load(os.path.join(bundle, DAY_DIR, "descriptors_cache.npz")) as a:
                n_rows = sum(1 for _ in open(os.path.join(bundle, DAY_DIR, "dataset.csv"))) - 1
                C["dinov2_cache"] = dict(ok=a["dinov2_descriptors"].shape[0] == len(a["valid_indices"]) > 0
                                         and len(a["valid_indices"]) == n_rows,
                                         descriptors=list(a["dinov2_descriptors"].shape), tiles=n_rows)
        C["day_match"] = day_selftest(bundle, manifest)
        C["learned_features"] = _learned_check(bundle, manifest, deep)
        C["models"] = _models_check(bundle, manifest, deep)
        if replay:
            C["day_replay"] = day_replay(bundle, manifest, replay, replay_limit, gpu)
            C["day_replay"]["ok"] = C["day_replay"]["accepted"] > 0 and C["day_replay"]["wrong_over_50m"] == 0

        # celestial time from the bundle's IERS table only
        from astropy.time import Time
        iers_path = os.path.join(bundle, IERS_NAME)
        os.environ["NAVERA_IERS_FILE"] = iers_path
        from cn_pkg.nodes import celestial_math
        src = celestial_math.configure_offline_iers(iers_path)
        date = mission_date or dt.date.today().isoformat()
        from astropy.utils import iers
        t = Time(f"{date}T12:00:00", scale="utc")
        dut1, status = iers.earth_orientation_table.get().ut1_utc(t, return_status=True)
        ra, dec = celestial_math.apparent_radec(279.2347, 38.7837, f"{date}T22:00:00")   # Vega, apparent
        names = {0: "IERS-B", 1: "IERS-A measured", 2: "IERS-A prediction", -1: "before the table",
                 -2: "beyond the table (edge value held)"}
        cov = manifest["celestial"]["iers"]
        C["celestial_time"] = dict(ok=src.startswith("IERS-A file") and int(status) in (1, 2), source=src,
                                   date=date, ut1_utc_s=round(float(dut1.to_value("s")), 4),
                                   status=names.get(int(status), str(status)),
                                   measured_until=cov["measured_until"], valid_until=cov["predicted_until"],
                                   vega_apparent=[round(ra, 4), round(dec, 4)])
        # star catalogue from the bundle only
        from cn_pkg.allsky import Catalogue
        cat = Catalogue(path=os.path.join(bundle, CATALOGUE_NAME))
        C["catalogue"] = dict(ok=400 < len(cat.vec) < 700, stars_mag4=int(len(cat.vec)), pairs=int(len(cat.pair_sep)))

        report["network_attempts"] = list(guard.attempts)
    C["offline"] = dict(ok=not guard.attempts, attempts=guard.attempts[:10],
                        network_off=report["network"]["offline"])
    report["valid_until"] = manifest.get("valid_until")
    report["id"] = manifest.get("id")
    report["ok"] = all(c.get("ok", True) for c in C.values())
    return report


def format_report(r: dict) -> str:
    if "error" in r:
        return f"FAIL {r['bundle']}: {r['error']}"
    net = r["network"]
    out = [f"bundle {r['id']} at {r['bundle']}",
           f"  network   {'namespace (unshare -rn) ' if net['netns'] else ''}interfaces {net['interfaces']}; "
           f"{net['probe']}"]
    for name, c in r["checks"].items():
        d = {k: v for k, v in c.items() if k not in ("ok", "rows", "selftest", "files") or k == "selftest"}
        out.append(f"  {'PASS' if c.get('ok', True) else 'FAIL'}  {name:16s} "
                   + "; ".join(f"{k}={v}" for k, v in d.items() if v not in (None, [], {})))
    out.append(f"  valid until {r['valid_until'].get('overall')} (IERS predictions)")
    out.append("PASS: the bundle is complete and works offline" if r["ok"] else "FAIL")
    return "\n".join(out)


def _netns_available() -> bool:
    if not shutil.which("unshare"):
        return False
    try:
        return subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ══ CLI ═══════════════════════════════════════════════════════════════════
def _spec_args(ap):
    ap.add_argument("--start", help="lat,lon")
    ap.add_argument("--dest", help="lat,lon")
    ap.add_argument("--waypoint", action="append", default=[], help="lat,lon (repeatable, between start and dest)")
    ap.add_argument("--route-file", help="GPX, KML, JSON, .waypoints or .plan")
    ap.add_argument("--corridor-m", type=float, default=2000.0, help="corridor full width (m)")
    ap.add_argument("--min-height-m", type=float, default=100.0)
    ap.add_argument("--max-height-m", type=float, default=600.0)
    ap.add_argument("--hfov", type=float, default=100.0,
                    help="day camera horizontal field of view (deg)")
    ap.add_argument("--frame-width", type=int, default=1200, help="day camera frame width (px)")
    ap.add_argument("--source", nargs="+", default=["onboard"],
                    help="tile sources in priority order: onboard esri xyz:URL mbtiles:PATH fn:module:function[:src]")
    ap.add_argument("--mbtiles", help="onboard map (default NAVERA_MBTILES)")
    ap.add_argument("--licence", help="licence statement of an xyz: source / an MBTiles without one")
    ap.add_argument("--rate", type=float, default=8.0, help="download rate limit, tiles/s")
    ap.add_argument("--no-learned", action="store_true", help="no learned (DISK) features")
    ap.add_argument("--no-dinov2", action="store_true", help="no DINOv2 descriptor cache")
    ap.add_argument("--include-models", action="store_true", help="copy the model weights into the bundle")
    ap.add_argument("--extra", action="append", default=[], help="NAME=PATH file to carry (calibrations)")
    ap.add_argument("--json", action="store_true")


def _spec(a) -> MissionSpec:
    extras = dict(e.split("=", 1) for e in a.extra)
    return MissionSpec(route=route_from_args(a.start, a.dest, a.waypoint, a.route_file),
                       corridor_width_m=a.corridor_m, min_height_m=a.min_height_m, max_height_m=a.max_height_m,
                       hfov_deg=a.hfov, frame_width_px=a.frame_width, learned=not a.no_learned,
                       dinov2=not a.no_dinov2, include_models=a.include_models, extras=extras)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan", help="tiles, size and time, nothing downloaded")
    _spec_args(p_plan)
    p_plan.add_argument("--out", help="where the bundle would go (free disk space)")
    p_build = sub.add_parser("build", help="download and build a bundle")
    p_build.add_argument("out")
    _spec_args(p_build)
    p_build.add_argument("--yes", action="store_true", help="no confirmation")
    p_build.add_argument("--force", action="store_true", help="replace an existing bundle")
    p_build.add_argument("--allow-missing", action="store_true")
    p_build.add_argument("--max-mb", type=float, default=DOWNLOAD_LIMIT_MB, help="refuse a bundle larger than this")
    p_build.add_argument("--iers-file", help="IERS-A table to carry (default NAVERA_IERS_FILE)")
    p_build.add_argument("--fetch-iers", action="store_true", help="refresh the IERS table first (network)")
    p_build.add_argument("--progress-json", action="store_true", help="progress as JSON lines on stdout")
    p_check = sub.add_parser("check", help="prove the bundle works offline (network off)")
    p_check.add_argument("bundle")
    p_check.add_argument("--replay", help="recorded frames dir (frames.jsonl with truth) to locate from the bundle")
    p_check.add_argument("--replay-max", type=int, default=30)
    p_check.add_argument("--gpu", action="store_true", help="replay matching on the GPU")
    p_check.add_argument("--deep", action="store_true", help="also load the models and run the learned matcher")
    p_check.add_argument("--date", help="mission date YYYY-MM-DD (IERS coverage; default today)")
    p_check.add_argument("--allow-missing", action="store_true")
    p_check.add_argument("--no-isolate", action="store_true", help="no network namespace (in-process guard only)")
    p_check.add_argument("--json", action="store_true")
    p_env = sub.add_parser("env", help="environment lines for a bundle where it is now")
    p_env.add_argument("bundle")
    a = ap.parse_args(argv)

    if a.cmd == "env":
        manifest = json.load(open(os.path.join(a.bundle, "manifest.json")))
        print("\n".join(env_lines(a.bundle, manifest)))
        return 0

    if a.cmd == "check":
        if not a.no_isolate and os.environ.get("NAVERA_BUNDLE_NETNS") != "1" and _netns_available():
            env = dict(os.environ, NAVERA_BUNDLE_NETNS="1")
            cmd = ["unshare", "-rn", sys.executable, os.path.abspath(__file__)] + list(argv or sys.argv[1:])
            return subprocess.run(cmd, env=env).returncode
        with contextlib.redirect_stdout(sys.stderr):         # libraries' prints must not break --json
            r = check_bundle(a.bundle, a.replay, a.deep, a.allow_missing, a.date, a.replay_max, a.gpu)
        print(json.dumps(r, indent=1, default=str) if a.json else format_report(r))
        return 0 if r.get("ok") else 1

    spec = _spec(a)
    sources = make_sources(a.source, a.mbtiles, a.licence, a.rate)
    plan = plan_bundle(spec, sources, getattr(a, "out", None))
    shown = {k: v for k, v in plan.items() if not k.startswith("_")}
    if a.cmd == "plan":
        print(json.dumps(shown, indent=1) if a.json else format_estimate(plan))
        return 0

    progress = Progress(a.progress_json)
    if a.progress_json:
        progress("estimate", 0, plan["tiles"], estimate=shown)
    else:
        print(format_estimate(plan), file=sys.stderr)
    if plan["total_mb"] > a.max_mb:
        print(f"refused: ~{plan['total_mb']:.0f} MB is over --max-mb {a.max_mb:.0f}", file=sys.stderr)
        return 2
    if plan["free_mb"] is not None and plan["total_mb"] * 1.1 + 1024 > plan["free_mb"]:
        print(f"refused: not enough disk space ({plan['free_mb']} MB free)", file=sys.stderr)
        return 2
    if not a.yes:
        if not sys.stdin.isatty():
            print("refused: confirm the estimate with --yes", file=sys.stderr)
            return 2
        if input("build this bundle? [y/N] ").strip().lower() not in ("y", "yes"):
            return 1
    manifest = build_bundle(spec, sources, a.out, progress, a.allow_missing, a.iers_file, a.fetch_iers,
                            force=a.force, plan=plan)
    summary = dict(out=os.path.abspath(a.out), id=manifest["id"], **manifest["totals"], build=manifest["build"],
                   tiles=manifest["map"]["tiles"], missing=len(manifest["map"]["missing"]),
                   valid_until=manifest["valid_until"]["overall"])
    print(json.dumps(summary) if a.progress_json or a.json else
          f"bundle {summary['id']} -> {summary['out']}: {summary['files']} files, {summary['mb']} MB, "
          f"{summary['tiles']} tiles ({summary['missing']} missing), built in {summary['build']['total_s']:.0f} s, "
          f"valid until {summary['valid_until']}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")     # tiles beyond the corridor are absent, not news
    sys.exit(main())
