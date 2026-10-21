#!/usr/bin/env python3
"""Licence-labelled satellite imagery sources for NAVERA's offline map (MBTiles).

NAVERA flies on a map downloaded before departure; every tile it carries must come from a
source whose licence allows storing it offline on a commercial device. This module knows
each source's licence and writes it into the MBTiles it fills, so a map can always say
where its pixels come from.

API (also used by the end-user "download offline bundle" tool)::

    from day_pkg.tile_sources import fetch_area, read_map_info, licence_warnings, SOURCES
    path = fetch_area((min_lon, min_lat, max_lon, max_lat), "sentinel2_l2a", "/data/maps/area.mbtiles")
    info = read_map_info(path)          # {"source", "licence", "attribution", "resolution_m", ...}
    licence_warnings(info)              # [] when the map may ship on a commercial device

    fetch_tiles([(x, y), ...], 17, source, out_path)   # the same for a tile list (prepare_area)

bbox order is GeoJSON/STAC: (min_lon, min_lat, max_lon, max_lat), WGS 84 degrees.
Tiles are always written at `zoom` (17 for the day matcher, ~1 m/px): a coarser source
(Sentinel-2, 10 m) is resampled (bicubic) to that grid and its true resolution is recorded
in the metadata (navera_resolution_m). One MBTiles holds ONE source: adding tiles of
another source to a labelled file raises ValueError (a map with mixed licences cannot be
labelled honestly).

Sources (SOURCES): see each entry's `licence` / `offline_commercial`:
- esri_world_imagery: DEVELOPMENT ONLY (Esri terms forbid offline storage / redistribution
  without a separate Esri licence).
- sentinel2_l2a: Copernicus Sentinel-2 L2A true colour (10 m), free, open, commercial use
  allowed with attribution; read without an account from the AWS open-data COGs
  (Element 84 earth-search STAC).
- openaerialmap: CC BY 4.0 drone/aerial imagery where volunteers uploaded some (sparse).
- geotiff: a GeoTIFF the customer or IRIS bought (Airbus, Maxar/Vantor, Planet, national
  agency); the licence text is supplied with it.
- custom: any XYZ URL; licence "unknown" unless given — flagged by licence_warnings().

Metadata keys written (MBTiles `metadata` table): name, format, type, bounds, minzoom, maxzoom,
attribution, description, and navera_source, navera_licence, navera_licence_url,
navera_offline_commercial (yes / no / per-contract / unknown), navera_dev_only, navera_resolution_m,
navera_imagery_date, navera_created, navera_scenes.
"""
import io
import json
import math
import os
import sqlite3
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

USER_AGENT = "NAVERA-map-preparation/0.6 (IRIS Systems)"
EARTH_SEARCH = "https://earth-search.aws.element84.com/v1/search"
OAM_API = "https://api.openaerialmap.org/meta"


@dataclass(frozen=True)
class TileSource:
    """One imagery source and the terms its tiles are stored under."""
    name: str
    title: str
    kind: str                    # xyz | sentinel2 | oam | geotiff
    url: str                     # XYZ template ({z} {x} {y}) or the API endpoint
    licence: str
    licence_url: str
    attribution: str
    resolution_m: float          # native ground resolution (0: varies)
    native_zoom: int             # finest zoom the source serves (xyz); tiles above are resampled
    offline_commercial: str      # yes | no | per-contract | unknown
    dev_only: bool = False
    note: str = ""


SOURCES: Dict[str, TileSource] = {s.name: s for s in (
    TileSource(
        "esri_world_imagery", "Esri World Imagery (DEVELOPMENT ONLY)", "xyz",
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "Esri Master Agreement / Terms of Use: no offline storage, caching or redistribution outside "
        "Esri products without a separate Esri licence", "https://www.esri.com/en-us/legal/terms/full-master-agreement",
        "Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community", 0.5, 19, "no", dev_only=True,
        note="bench and simulator only; a map from this source must not ship on a sold device"),
    TileSource(
        "sentinel2_l2a", "Copernicus Sentinel-2 L2A true colour (10 m)", "sentinel2", EARTH_SEARCH,
        "Copernicus Sentinel data terms (EU Regulation 1159/2013): free, full and open, commercial use "
        "and redistribution allowed with attribution",
        "https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice",
        "Contains modified Copernicus Sentinel data {year}", 10.0, 14, "yes",
        note="read without an account from the AWS open-data COGs (registry.opendata.aws/sentinel-2-l2a-cogs)"),
    TileSource(
        "openaerialmap", "OpenAerialMap (CC BY 4.0 aerial/drone imagery)", "oam", OAM_API,
        "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/",
        "© OpenAerialMap contributors: {provider}", 0.0, 21, "yes",
        note="sparse: almost nothing over Tunisia (2026-10-21: 3 coarse entries)"),
    TileSource(
        "geotiff", "Licensed GeoTIFF (bought imagery: Airbus, Vantor/Maxar, Planet, national agency)", "geotiff",
        "", "as supplied with the GeoTIFF (contract)", "", "{provider}", 0.0, 21, "per-contract",
        note="give licence= and attribution= from the purchase contract"),
    TileSource(
        "custom", "Custom XYZ service", "xyz", "", "unknown", "", "", 0.0, 19, "unknown"),
)}


def get_source(source) -> TileSource:
    """A TileSource from its name (or the object itself)."""
    if isinstance(source, TileSource):
        return source
    if source not in SOURCES:
        raise ValueError(f"unknown map source {source!r}; known: {', '.join(SOURCES)}")
    return SOURCES[source]


def source_for_url(url: str) -> TileSource:
    """The registered source an XYZ URL template belongs to (else 'custom' with that URL)."""
    for s in SOURCES.values():
        if s.kind == "xyz" and s.url and urllib.parse.urlsplit(s.url).netloc == urllib.parse.urlsplit(url).netloc:
            return s
    c = SOURCES["custom"]
    return TileSource(c.name, c.title, c.kind, url, c.licence, c.licence_url,
                      urllib.parse.urlsplit(url).netloc, c.resolution_m, c.native_zoom, c.offline_commercial)


# --------------------------------------------------------------------------- tile maths

def tile_xy(lat: float, lon: float, z: int) -> Tuple[float, float]:
    """Fractional XYZ (web-mercator) tile coordinates of a point."""
    n = 2 ** z
    r = math.radians(lat)
    return (lon + 180.0) / 360.0 * n, (1.0 - math.asinh(math.tan(r)) / math.pi) / 2.0 * n


def bbox_tiles(bbox: Sequence[float], zoom: int) -> List[Tuple[int, int]]:
    """Tiles (x, y) covering bbox = (min_lon, min_lat, max_lon, max_lat)."""
    w, s, e, n = bbox
    if not (w < e and s < n):
        raise ValueError(f"empty bbox {bbox} (order: min_lon, min_lat, max_lon, max_lat)")
    x0, y0 = tile_xy(n, w, zoom)
    x1, y1 = tile_xy(s, e, zoom)
    return [(x, y) for y in range(int(y0), int(y1) + 1) for x in range(int(x0), int(x1) + 1)]


def tiles_bbox(tiles: Iterable[Tuple[int, int]], zoom: int) -> Tuple[float, float, float, float]:
    """(min_lon, min_lat, max_lon, max_lat) of a set of tiles."""
    tiles = list(tiles)
    n = 2 ** zoom
    xs, ys = [t[0] for t in tiles], [t[1] for t in tiles]

    def lat(y):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return (min(xs) / n * 360 - 180, lat(max(ys) + 1), (max(xs) + 1) / n * 360 - 180, lat(min(ys)))


def tile_pixel_latlon(x: int, y: int, zoom: int, size: int = 256) -> Tuple[np.ndarray, np.ndarray]:
    """(lat, lon) grids of the pixel centres of a tile (size x size)."""
    n = 2 ** zoom
    f = (np.arange(size) + 0.5) / size
    lon = (x + f) / n * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + f) / n))))
    return np.repeat(lat[:, None], size, 1), np.repeat(lon[None, :], size, 0)


# --------------------------------------------------------------------------- projections

def utm_forward(lat, lon, zone: int, south: bool = False):
    """WGS 84 -> UTM (easting, northing) in metres, Krüger series (sub-millimetre in the zone)."""
    a, f, k0 = 6378137.0, 1 / 298.257223563, 0.9996
    n = f / (2 - f)
    A = a / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    al = (n / 2 - 2 / 3 * n ** 2 + 5 / 16 * n ** 3, 13 / 48 * n ** 2 - 3 / 5 * n ** 3, 61 / 240 * n ** 3)
    phi, dl = np.radians(lat), np.radians(np.asarray(lon) - (zone * 6 - 183))
    c = 2 * math.sqrt(n) / (1 + n)
    t = np.sinh(np.arctanh(np.sin(phi)) - c * np.arctanh(c * np.sin(phi)))
    xi, eta = np.arctan2(t, np.cos(dl)), np.arctanh(np.sin(dl) / np.sqrt(1 + t * t))
    E = eta + sum(al[j] * np.cos(2 * (j + 1) * xi) * np.sinh(2 * (j + 1) * eta) for j in range(3))
    N = xi + sum(al[j] * np.sin(2 * (j + 1) * xi) * np.cosh(2 * (j + 1) * eta) for j in range(3))
    return 500000.0 + k0 * A * E, (10_000_000.0 if south else 0.0) + k0 * A * N


def project(epsg: int, lat, lon):
    """(X, Y) of WGS 84 points in a supported CRS: 4326, 3857, UTM WGS 84 (326xx / 327xx)."""
    if epsg == 4326:
        return np.asarray(lon, float), np.asarray(lat, float)
    if epsg == 3857:
        R = 6378137.0
        return R * np.radians(lon), R * np.arcsinh(np.tan(np.radians(lat)))
    if 32601 <= epsg <= 32660 or 32701 <= epsg <= 32760:
        return utm_forward(lat, lon, epsg % 100, epsg >= 32701)
    raise ValueError(f"EPSG:{epsg} not supported (4326, 3857, UTM WGS 84); reproject with "
                     "gdalwarp -t_srs EPSG:3857 first")


# --------------------------------------------------------------------------- GeoTIFF / COG reader

class HttpFile(io.RawIOBase):
    """A read-only, seekable file over HTTP range requests (small reads served from 64 KB blocks)."""
    BLOCK = 65536

    def __init__(self, url: str, timeout: float = 60.0):
        super().__init__()
        self.url, self.pos, self.timeout, self._blocks = url, 0, timeout, {}
        self.requests = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else self.pos + off if whence == 1 else self._size() + off
        return self.pos

    def tell(self):
        return self.pos

    def _size(self):
        if not hasattr(self, "_len"):
            req = urllib.request.Request(self.url, method="HEAD", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self._len = int(r.headers["Content-Length"])
        return self._len

    def _get(self, start, n):
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={start}-{start + n - 1}",
                                                        "User-Agent": USER_AGENT})
        for attempt in range(3):
            try:
                self.requests += 1
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return r.read()
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(1.0 + attempt)

    def read(self, n=-1):
        if n is None or n < 0:
            n = self._size() - self.pos
        if n <= 0:
            return b""
        if n > self.BLOCK:                       # large read (an image segment): direct
            data = self._get(self.pos, n)
        else:
            out, p, end = [], self.pos, self.pos + n
            while p < end:
                b = p // self.BLOCK
                if b not in self._blocks:
                    self._blocks[b] = self._get(b * self.BLOCK, self.BLOCK)
                blk = self._blocks[b]
                lo = p - b * self.BLOCK
                if lo >= len(blk):
                    break
                chunk = blk[lo:lo + end - p]
                out.append(chunk)
                p += len(chunk)
            data = b"".join(out)
        self.pos += len(data)
        return data


_TYPES = {1: "B", 2: "s", 3: "H", 4: "I", 5: "II", 6: "b", 7: "B", 8: "h", 9: "i", 11: "f", 12: "d", 16: "Q", 17: "q"}


class GeoTiff:
    """A minimal reader of 8-bit RGB GeoTIFFs (tiled or stripped; none / deflate; predictor 1 or 2;
    classic or BigTIFF) — enough for Sentinel-2 COGs and GeoTIFF deliveries re-saved with
    `gdal_translate -ot Byte -co TILED=YES -co COMPRESS=DEFLATE`. Reads only the segments a
    window needs (local file or HttpFile)."""

    def __init__(self, f, cache_segments: int = 48):
        self.f, self._lock, self._cache, self._order = f, threading.Lock(), {}, []
        self.cache_segments = cache_segments
        f.seek(0)
        hdr = f.read(16)
        self.e = {b"II": "<", b"MM": ">"}[hdr[:2]]
        magic = struct.unpack(self.e + "H", hdr[2:4])[0]
        self.big = magic == 43
        off = struct.unpack(self.e + ("Q" if self.big else "I"), hdr[8:16] if self.big else hdr[4:8])[0]
        t = self._ifd(off)
        self.w, self.h = int(t[256][0]), int(t[257][0])
        self.spp = int(t.get(277, [1])[0])
        bps = t.get(258, [8])
        comp = int(t.get(259, [1])[0])
        if any(int(b) != 8 for b in bps):
            raise ValueError("only 8-bit imagery (gdal_translate -ot Byte -scale ...)")
        if comp not in (1, 8, 32946):
            raise ValueError(f"TIFF compression {comp} not supported (gdal_translate -co COMPRESS=DEFLATE)")
        if int(t.get(284, [1])[0]) != 1:
            raise ValueError("planar TIFF not supported (gdal_translate -co INTERLEAVE=PIXEL)")
        self.comp, self.pred = comp, int(t.get(317, [1])[0])
        if 322 in t:
            self.tw, self.tl = int(t[322][0]), int(t[323][0])
            self.offsets, self.counts = t[324], t[325]
        else:
            self.tw, self.tl = self.w, int(t.get(278, [self.h])[0])
            self.offsets, self.counts = t[273], t[279]
        self.across = (self.w + self.tw - 1) // self.tw
        if 34264 in t and 33922 not in t:
            raise ValueError("GeoTIFF with a ModelTransformation (rotated) not supported")
        sx, sy = t[33550][:2]
        tp = t[33922]
        keys = t.get(34735, [])
        geo = {int(keys[i]): int(keys[i + 3]) for i in range(4, len(keys), 4)} if keys else {}
        self.epsg = geo.get(3072) or geo.get(2048) or 0
        if not self.epsg:
            raise ValueError("GeoTIFF without an EPSG code (ProjectedCSType / GeographicType)")
        point = geo.get(1025) == 2                    # PixelIsPoint: tiepoint at the pixel centre
        self.sx, self.sy = float(sx), float(sy)
        self.x0 = float(tp[3]) - float(tp[0]) * self.sx - (0.5 * self.sx if point else 0.0)
        self.y0 = float(tp[4]) + float(tp[1]) * self.sy + (0.5 * self.sy if point else 0.0)

    def _ifd(self, off):
        e, f = self.e, self.f
        f.seek(off)
        n = struct.unpack(e + ("Q" if self.big else "H"), f.read(8 if self.big else 2))[0]
        esz = 20 if self.big else 12
        raw = f.read(n * esz)
        tags = {}
        for i in range(n):
            ent = raw[i * esz:(i + 1) * esz]
            tag, typ = struct.unpack(e + "HH", ent[:4])
            cnt = struct.unpack(e + ("Q" if self.big else "I"), ent[4:12] if self.big else ent[4:8])[0]
            fmt = _TYPES.get(typ)
            if fmt is None:
                continue
            size = struct.calcsize(e + fmt) * cnt if fmt != "s" else cnt
            inline = ent[12:20] if self.big else ent[8:12]
            if size <= len(inline):
                data = inline[:size]
            else:
                f.seek(struct.unpack(e + ("Q" if self.big else "I"), inline)[0])
                data = f.read(size)
            if fmt == "s":
                tags[tag] = [data.rstrip(b"\0").decode("latin-1")]
            elif fmt == "II":
                v = struct.unpack(e + "I" * (2 * cnt), data)
                tags[tag] = [v[i] / v[i + 1] if v[i + 1] else 0.0 for i in range(0, len(v), 2)]
            else:
                tags[tag] = list(struct.unpack(e + fmt * cnt, data))
        return tags

    def _segment(self, i: int) -> np.ndarray:
        with self._lock:
            if i in self._cache:
                return self._cache[i]
            self.f.seek(int(self.offsets[i]))
            raw = self.f.read(int(self.counts[i]))
        if self.comp != 1:
            raw = zlib.decompress(raw)
        a = np.frombuffer(raw, np.uint8)
        rows = len(a) // (self.tw * self.spp)
        a = a[:rows * self.tw * self.spp].reshape(rows, self.tw, self.spp)
        if self.pred == 2:
            a = np.cumsum(a, axis=1, dtype=np.uint8)
        with self._lock:
            self._cache[i] = a
            self._order.append(i)
            if len(self._order) > self.cache_segments:
                self._cache.pop(self._order.pop(0), None)
        return a

    def window(self, c0: int, r0: int, c1: int, r1: int) -> np.ndarray:
        """Pixels [r0:r1, c0:c1] (clipped to the image, zeros outside), RGB uint8."""
        out = np.zeros((r1 - r0, c1 - c0, 3), np.uint8)
        cc0, rr0, cc1, rr1 = max(c0, 0), max(r0, 0), min(c1, self.w), min(r1, self.h)
        if cc0 >= cc1 or rr0 >= rr1:
            return out
        for ty in range(rr0 // self.tl, (rr1 - 1) // self.tl + 1):
            for tx in range(cc0 // self.tw, (cc1 - 1) // self.tw + 1):
                seg = self._segment(ty * self.across + tx)
                sy0, sx0 = ty * self.tl, tx * self.tw
                a0, a1 = max(rr0, sy0), min(rr1, sy0 + seg.shape[0])
                b0, b1 = max(cc0, sx0), min(cc1, sx0 + seg.shape[1])
                if a0 >= a1 or b0 >= b1:
                    continue
                px = seg[a0 - sy0:a1 - sy0, b0 - sx0:b1 - sx0]
                px = np.repeat(px[..., :1], 3, 2) if self.spp < 3 else px[..., :3]
                out[a0 - r0:a1 - r0, b0 - c0:b1 - c0] = px
        return out

    def render_tile(self, x: int, y: int, zoom: int, size: int = 256) -> np.ndarray:
        """The (x, y, zoom) web-mercator tile resampled from this raster (bicubic); zeros = no data."""
        import cv2
        lat, lon = tile_pixel_latlon(x, y, zoom, size)
        X, Y = project(self.epsg, lat, lon)
        col = (X - self.x0) / self.sx - 0.5
        row = (self.y0 - Y) / self.sy - 0.5
        c0, r0 = int(math.floor(col.min())) - 2, int(math.floor(row.min())) - 2
        c1, r1 = int(math.ceil(col.max())) + 3, int(math.ceil(row.max())) + 3
        if c1 <= 0 or r1 <= 0 or c0 >= self.w or r0 >= self.h:
            return np.zeros((size, size, 3), np.uint8)
        win = self.window(c0, r0, c1, r1)
        mx, my = (col - c0).astype(np.float32), (row - r0).astype(np.float32)
        out = cv2.remap(win, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        # no data stays no data: a pixel whose neighbourhood touches a zero pixel is cleared
        valid = (win.max(axis=2) > 0).astype(np.uint8)
        vmask = cv2.remap(cv2.erode(valid, np.ones((3, 3), np.uint8)), mx, my, cv2.INTER_NEAREST,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        out[vmask == 0] = 0
        return out


# --------------------------------------------------------------------------- MBTiles

def open_mbtiles(path: str) -> sqlite3.Connection:
    """Open (create if needed) a writable MBTiles file (same schema as prepare_area.open_cache)."""
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.execute("CREATE TABLE IF NOT EXISTS metadata (name TEXT, value TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS tiles (zoom_level INTEGER, tile_column INTEGER, "
                "tile_row INTEGER, tile_data BLOB)")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS tile_index ON tiles (zoom_level, tile_column, tile_row)")
    con.commit()
    return con


def _meta(con) -> Dict[str, str]:
    return {k: v for k, v in con.execute("SELECT name, value FROM metadata")}


def _set_meta(con, values: Dict[str, str]):
    for k, v in values.items():
        con.execute("DELETE FROM metadata WHERE name=?", (k,))
        con.execute("INSERT INTO metadata VALUES (?, ?)", (k, str(v)))


def label_mbtiles(con, src: TileSource, *, zoom: int = 17, licence: Optional[str] = None,
                  attribution: Optional[str] = None, resolution_m: Optional[float] = None,
                  imagery_date: str = "", scenes: Sequence[str] = ()) -> Dict[str, str]:
    """Write the source's licence metadata into an MBTiles connection.

    Raises ValueError if the file is already labelled with ANOTHER source (one map, one licence).
    An unlabelled file that already holds tiles (made before labelling existed) is adopted.
    """
    old = _meta(con)
    if old.get("navera_source") and old["navera_source"] != src.name:
        raise ValueError(f"map already holds {old['navera_source']} tiles; {src.name} tiles go in another file")
    if old.get("navera_source") == "custom" and old.get("navera_url") and src.url and old["navera_url"] != src.url:
        raise ValueError(f"map already holds tiles of {old['navera_url']}; use another file for {src.url}")
    dates = sorted({d for d in (old.get("navera_imagery_date", "").split("/") + imagery_date.split("/")) if d})
    all_scenes = sorted(set(filter(None, old.get("navera_scenes", "").split(","))) | set(scenes))
    years = sorted({d[:4] for d in dates}) or [time.strftime("%Y")]
    attr = (attribution or src.attribution or "").replace("{year}", "-".join(dict.fromkeys([years[0], years[-1]])))
    values = {
        "name": old.get("name") or f"NAVERA map ({src.title})", "format": old.get("format") or "jpg",
        "type": "baselayer", "minzoom": str(min(zoom, int(old.get("minzoom", zoom)))),
        "maxzoom": str(max(zoom, int(old.get("maxzoom", zoom)))),
        "attribution": attr, "description": src.title,
        "navera_source": src.name, "navera_licence": licence or src.licence,
        "navera_licence_url": src.licence_url, "navera_offline_commercial": src.offline_commercial,
        "navera_dev_only": "true" if src.dev_only else "false",
        "navera_resolution_m": str(resolution_m if resolution_m is not None else src.resolution_m),
        "navera_imagery_date": "/".join([dates[0], dates[-1]] if len(dates) > 1 else dates),
        "navera_scenes": ",".join(all_scenes), "navera_created": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if src.name == "custom":
        values["navera_url"] = src.url
    _set_meta(con, values)
    con.commit()
    return values


def _update_bounds(con, zoom: int):
    n = 2 ** zoom
    r = con.execute("SELECT MIN(tile_column), MAX(tile_column), MIN(tile_row), MAX(tile_row) FROM tiles "
                    "WHERE zoom_level=?", (zoom,)).fetchone()
    if r and r[0] is not None:
        b = tiles_bbox([(r[0], n - 1 - r[3]), (r[1], n - 1 - r[2])], zoom)
        _set_meta(con, {"bounds": ",".join(f"{v:.6f}" for v in b)})
        con.commit()


def read_map_info(path: str) -> dict:
    """Source / licence metadata of an MBTiles map: {"labelled", "source", "licence", "attribution",
    "offline_commercial", "dev_only", "resolution_m", "imagery_date", "bounds", ...}."""
    if not path or not os.path.exists(path):
        return {"labelled": False, "source": None, "error": "no map file"}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        m = _meta(con)
    except sqlite3.Error as e:
        return {"labelled": False, "source": None, "error": str(e)}
    finally:
        con.close()
    info = {k[len("navera_"):]: v for k, v in m.items() if k.startswith("navera_")}
    info.update(labelled="source" in info, source=info.get("source"),
                attribution=m.get("attribution", ""), bounds=m.get("bounds", ""))
    if "dev_only" in info:
        info["dev_only"] = info["dev_only"] == "true"
    if "resolution_m" in info:
        info["resolution_m"] = float(info["resolution_m"])
    return info


def licence_warnings(info: dict) -> List[str]:
    """Why a map (read_map_info) may NOT ship on a sold device; [] when its licence allows it."""
    if not info.get("labelled"):
        return ["map has no source/licence label (made before labelling, or another tool): "
                "treat as Esri World Imagery — development only"]
    w = []
    if info.get("dev_only"):
        w.append(f"{info['source']}: development only — {info.get('licence', '')}")
    oc = info.get("offline_commercial")
    if oc == "no" and not info.get("dev_only"):
        w.append(f"{info['source']}: licence does not allow offline storage on a commercial device")
    if oc == "unknown":
        w.append(f"{info['source']}: licence unknown — check the provider's terms before shipping")
    if oc == "per-contract":
        w.append(f"{info['source']}: allowed only within the purchase contract ({info.get('licence', '')})")
    return w


# --------------------------------------------------------------------------- fetchers

def _http(url: str, data: Optional[bytes] = None, timeout: float = 30.0, retries: int = 2) -> Optional[bytes]:
    hdr = {"User-Agent": USER_AGENT}
    if data is not None:
        hdr["Content-Type"] = "application/json"
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=hdr), timeout=timeout) as r:
                return r.read() if r.status == 200 else None
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403, 404):
                return None
            time.sleep(0.5 * (attempt + 1))
        except OSError:
            time.sleep(0.5 * (attempt + 1))
    return None


def _encode(img: np.ndarray, quality: int = 90) -> bytes:
    import cv2
    ok, buf = cv2.imencode(".jpg", img[..., ::-1].copy(), [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


def _decode(data: bytes) -> Optional[np.ndarray]:
    import cv2
    im = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    return None if im is None else im[..., ::-1]


def _xyz_fetcher(url: str, native_zoom: int, zoom: int):
    """fn(x, y) -> tile bytes; above native_zoom the parent tile is cropped and enlarged (bicubic)."""
    import cv2
    parents, lock = {}, threading.Lock()

    def fetch(x, y):
        if zoom <= native_zoom:
            return _http(url.format(z=zoom, x=x, y=y), timeout=15)
        d = zoom - native_zoom
        px, py = x >> d, y >> d
        with lock:
            have = (px, py) in parents
        if not have:
            data = _http(url.format(z=native_zoom, x=px, y=py), timeout=15)
            with lock:
                parents[(px, py)] = None if data is None else _decode(data)
        p = parents[(px, py)]
        if p is None:
            return None
        k = p.shape[0] >> d
        sub = p[(y - (py << d)) * k:(y - (py << d) + 1) * k, (x - (px << d)) * k:(x - (px << d) + 1) * k]
        return _encode(cv2.resize(sub, (256, 256), interpolation=cv2.INTER_CUBIC))
    return fetch


def sentinel2_scenes(bbox: Sequence[float], date: Optional[str] = None, max_cloud: float = 5.0,
                     limit: int = 100) -> List[dict]:
    """Sentinel-2 L2A scenes over bbox (earth-search STAC, no account), best first: least cloud,
    then least no-data. date: 'YYYY-MM-DD', 'YYYY-MM-DD/YYYY-MM-DD' (default: the last 12 months)."""
    if not date:
        end = time.time()
        day = "%Y-%m-%d"
        date = f"{time.strftime(day, time.gmtime(end - 365 * 86400))}/{time.strftime(day, time.gmtime(end))}"
    a, b = (date.split("/") + [date])[:2]
    body = {"collections": ["sentinel-2-l2a"], "bbox": list(bbox), "limit": limit,
            "datetime": f"{a}T00:00:00Z/{b}T23:59:59Z", "query": {"eo:cloud_cover": {"lt": max_cloud}}}
    raw = _http(EARTH_SEARCH, json.dumps(body).encode(), timeout=60)
    if raw is None:
        raise RuntimeError("Sentinel-2 catalogue (earth-search) not reachable")
    feats = json.loads(raw).get("features", [])
    out = []
    for f in feats:
        p = f["properties"]
        if "visual" not in f.get("assets", {}):
            continue
        out.append(dict(id=f["id"], date=p["datetime"][:10], cloud=float(p.get("eo:cloud_cover", 100)),
                        nodata=float(p.get("s2:nodata_pixel_percentage", 0)), href=f["assets"]["visual"]["href"]))
    out.sort(key=lambda s: (round(s["cloud"]), s["nodata"], s["date"][::-1]))
    return out


def _raster_writer(rasters: List[Tuple[str, "GeoTiff"]], zoom: int, min_valid: float = 0.5):
    """fn(x, y) -> (jpeg bytes, [names used]); the rasters are mosaicked in order (first wins)."""
    def fetch(x, y):
        out, used = None, []
        for name, r in rasters:
            t = r.render_tile(x, y, zoom)
            m = t.max(axis=2) > 0
            if not m.any():
                continue
            if out is None:
                out, have = t, m
            else:
                fill = m & ~have
                out[fill] = t[fill]
                have = have | m
            used.append(name)
            if have.all():
                break
        if out is None or have.mean() < min_valid:
            return None, used
        return _encode(out), used
    return fetch


def fetch_tiles(tiles: Sequence[Tuple[int, int]], zoom: int, source, out_path: str, *,
                url: Optional[str] = None, path: Optional[str] = None, date: Optional[str] = None,
                max_cloud: float = 5.0, max_scenes: int = 4, licence: Optional[str] = None,
                attribution: Optional[str] = None, provider: str = "", resolution_m: Optional[float] = None,
                workers: int = 8, overwrite: bool = False,
                progress: Optional[Callable[[str, int, int], None]] = None) -> dict:
    """Fill out_path (MBTiles, created if needed, labelled with the source) with the given tiles.

    Tiles already in the file are kept unless overwrite. Returns {"written", "failed", "skipped",
    "path", "scenes"}. Raises ValueError if out_path is labelled with another source."""
    src = get_source(source)
    if src.kind == "xyz" and src.name == "custom":
        if not url:
            raise ValueError("source 'custom' needs url= (an XYZ template)")
        src = source_for_url(url)
        if src.name != "custom":                      # a registered service's URL
            url = None
    n = 2 ** zoom
    scenes: List[str] = []
    dates: List[str] = []
    res_m = resolution_m
    con = open_mbtiles(out_path)
    try:
        have = set()
        if not overwrite:
            have = {(c, n - 1 - r) for c, r in con.execute(
                "SELECT tile_column, tile_row FROM tiles WHERE zoom_level=?", (zoom,))}
        todo = [t for t in tiles if t not in have]
        if src.kind == "xyz":
            fetch1 = _xyz_fetcher(url or src.url, src.native_zoom, zoom)

            def fetch(x, y):
                return fetch1(x, y), []
        elif src.kind == "oam":
            img = _oam_pick(tiles_bbox(todo or tiles, zoom))
            if img is None:
                raise RuntimeError("no OpenAerialMap image over this area")
            fetch1 = _xyz_fetcher(img["tms"], 21, zoom)
            provider = provider or img["provider"]
            res_m = res_m or img["gsd"]
            dates.append(img["date"])
            scenes.append(img["id"])

            def fetch(x, y):
                return fetch1(x, y), []
        elif src.kind == "sentinel2":
            bb = tiles_bbox(todo or tiles, zoom)
            found = sentinel2_scenes(bb, date, max_cloud)
            if not found:
                raise RuntimeError(f"no Sentinel-2 scene with < {max_cloud}% cloud over {bb} "
                                   f"in {date or 'the last year'}")
            rasters = [(s["id"], GeoTiff(HttpFile(s["href"]))) for s in found[:max_scenes]]
            meta = {s["id"]: s["date"] for s in found}
            fetch = _raster_writer(rasters, zoom)
        elif src.kind == "geotiff":
            if not path:
                raise ValueError("source 'geotiff' needs path= (a GeoTIFF file)")
            g = GeoTiff(open(path, "rb"))
            res_m = res_m or round(abs(g.sx) * (111_320.0 if g.epsg == 4326 else 1.0), 2)
            fetch = _raster_writer([(os.path.basename(path), g)], zoom)
            scenes.append(os.path.basename(path))
        else:
            raise ValueError(f"source kind {src.kind!r} not supported")
        if src.kind in ("oam", "geotiff") and provider:
            attribution = attribution or src.attribution.replace("{provider}", provider)
        label_mbtiles(con, src, zoom=zoom, licence=licence, attribution=attribution, resolution_m=res_m,
                      imagery_date="/".join(sorted(dates)[:1] + sorted(dates)[-1:]) if dates else "",
                      scenes=scenes)
        written = failed = 0
        used_all = set()
        with ThreadPoolExecutor(max_workers=max(1, workers if src.kind in ("xyz", "oam") else min(workers, 4))) as ex:
            for i, ((x, y), (data, used)) in enumerate(zip(todo, ex.map(lambda t: fetch(*t), todo))):
                if data:
                    con.execute("INSERT OR REPLACE INTO tiles VALUES (?, ?, ?, ?)", (zoom, x, n - 1 - y, data))
                    written += 1
                    used_all.update(used)
                else:
                    failed += 1
                if (i + 1) % 25 == 0 or i + 1 == len(todo):
                    con.commit()
                    if progress:
                        progress("download", i + 1, len(todo))
        if src.kind == "sentinel2" and used_all:
            ds = sorted(meta[s] for s in used_all)
            label_mbtiles(con, src, zoom=zoom, licence=licence, attribution=attribution, resolution_m=res_m,
                          imagery_date="/".join([ds[0], ds[-1]]), scenes=sorted(used_all))
        con.commit()
        _update_bounds(con, zoom)
        return {"written": written, "failed": failed, "skipped": len(tiles) - len(todo), "path": out_path,
                "scenes": sorted(used_all) or scenes}
    finally:
        con.close()


def _oam_pick(bbox) -> Optional[dict]:
    """The finest OpenAerialMap image covering the bbox centre (CC BY 4.0), or None."""
    q = urllib.parse.urlencode({"bbox": ",".join(f"{v:.6f}" for v in bbox), "limit": 100})
    raw = _http(f"{OAM_API}?{q}")
    if raw is None:
        return None
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    best = None
    for r in json.loads(raw).get("results", []):
        b, tms, gsd = r.get("bbox"), r.get("properties", {}).get("tms"), r.get("gsd")
        if not (b and tms and gsd) or not (b[0] <= cx <= b[2] and b[1] <= cy <= b[3]):
            continue
        if best is None or gsd < best["gsd"]:
            best = dict(id=r.get("_id", ""), tms=tms, gsd=round(float(gsd), 2),
                        date=str(r.get("acquisition_end", ""))[:10], provider=r.get("provider", "unknown"))
    return best


def fetch_area(bbox: Sequence[float], source, out_path: str, zoom: int = 17, **kw) -> str:
    """Download the imagery of bbox = (min_lon, min_lat, max_lon, max_lat) from `source` (a SOURCES
    name) into the MBTiles out_path, labelled with its licence; returns out_path.

    Keyword options as fetch_tiles (url= for 'custom', path= for 'geotiff', date= / max_cloud= for
    'sentinel2_l2a', licence= / attribution= / provider= for bought imagery, progress=)."""
    r = fetch_tiles(bbox_tiles(bbox, zoom), zoom, source, out_path, **kw)
    if r["written"] == 0 and r["skipped"] == 0:
        raise RuntimeError(f"no tile of {bbox} could be fetched from {get_source(source).name}")
    return out_path
