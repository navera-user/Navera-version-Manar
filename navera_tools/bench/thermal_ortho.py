"""Real aerial thermal orthomosaics as a nadir thermal camera, for night_real_thermal.py.

Two public, openly licensed (Licence Ouverte / Etalab, commercial reuse allowed with
attribution) airborne thermography products are used:

* Bordeaux Metropole, "Thermographie aerienne hiver 2018": an aircraft infrared scanner
  flown at NIGHT (15-17 Nov 2017, 8-9 and 22-23 Feb 2018), 0.5 m, 542 tiles of 1.4 x 1 km
  in RGF93 / CC45 (EPSG:3945), delivered as a rainbow palette (blue = cold, red = warm),
  turned back into a scalar here (hue).
* CRAIG, "Thermographie 1 m - Clermont-Ferrand - ete 2024": FLIR SC660-class MWIR
  (3-5 um), 11 Aug 2024 16-18 h (DAY, heat wave), 1 m, float surface temperature in
  RGF93 / Lambert-93 (EPSG:2154).

A frame is rendered from the orthomosaic for a camera at a true position, height
and heading (flat ground, nadir pinhole): the radiometry is real, the geometry is
an orthophoto (no relief displacement, no building lean, no motion). Rendering is
supersampled then area-averaged to the sensor's pixels, blurred by a 0.5 px optics
PSF, given sensor noise and an automatic gain to 8 bits.

Also: an Esri World Imagery z17 MBTiles writer (the map provider of NAVERA's map).
"""
import math
import os
import sqlite3
import threading
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

A_GRS80 = 6378137.0
F_GRS80 = 1.0 / 298.257222101
E2 = 2 * F_GRS80 - F_GRS80 ** 2
E = math.sqrt(E2)


# ── projections ────────────────────────────────────────────────────────────────

class LambertConformal:
    """Lambert conformal conic, two standard parallels, GRS80 (Snyder 1987, 15-1..15-11)."""

    def __init__(self, lat0, lon0, lat1, lat2, x0, y0):
        def m(p):
            return math.cos(p) / math.sqrt(1 - E2 * math.sin(p) ** 2)

        def t(p):
            return math.tan(math.pi / 4 - p / 2) / ((1 - E * math.sin(p)) / (1 + E * math.sin(p))) ** (E / 2)
        p0, p1, p2 = (math.radians(v) for v in (lat0, lat1, lat2))
        self.lon0 = math.radians(lon0)
        self.n = (math.log(m(p1)) - math.log(m(p2))) / (math.log(t(p1)) - math.log(t(p2)))
        self.F = m(p1) / (self.n * t(p1) ** self.n)
        self.rho0 = A_GRS80 * self.F * t(p0) ** self.n
        self.x0, self.y0 = x0, y0

    def forward(self, lat, lon):
        """Degrees (arrays) -> projected metres (x east, y north)."""
        p = np.radians(np.asarray(lat, np.float64))
        lam = np.radians(np.asarray(lon, np.float64))
        es = E * np.sin(p)
        t = np.tan(np.pi / 4 - p / 2) / ((1 - es) / (1 + es)) ** (E / 2)
        rho = A_GRS80 * self.F * t ** self.n
        th = self.n * (lam - self.lon0)
        return self.x0 + rho * np.sin(th), self.y0 + self.rho0 - rho * np.cos(th)

    def inverse(self, x, y):
        """Projected metres -> degrees."""
        dx = np.asarray(x, np.float64) - self.x0
        dy = self.rho0 - (np.asarray(y, np.float64) - self.y0)
        rho = np.sign(self.n) * np.hypot(dx, dy)
        t = (rho / (A_GRS80 * self.F)) ** (1 / self.n)
        th = np.arctan2(dx, dy)
        lam = th / self.n + self.lon0
        p = np.pi / 2 - 2 * np.arctan(t)
        for _ in range(8):
            es = E * np.sin(p)
            p = np.pi / 2 - 2 * np.arctan(t * ((1 - es) / (1 + es)) ** (E / 2))
        return np.degrees(p), np.degrees(lam)


LAMBERT93 = LambertConformal(46.5, 3.0, 49.0, 44.0, 700000.0, 6600000.0)     # EPSG:2154
CC45 = LambertConformal(45.0, 3.0, 44.25, 45.75, 1700000.0, 4200000.0)      # EPSG:3945


def enu_to_latlon(lat0, lon0, east_m, north_m):
    """Local east/north offsets (m, arrays) -> lat/lon on the GRS80 ellipsoid."""
    s = math.sin(math.radians(lat0))
    w = math.sqrt(1 - E2 * s * s)
    r_merid = A_GRS80 * (1 - E2) / w ** 3
    r_prime = A_GRS80 / w
    return (lat0 + np.degrees(np.asarray(north_m) / r_merid),
            lon0 + np.degrees(np.asarray(east_m) / (r_prime * math.cos(math.radians(lat0)))))


def dist_m(a, b) -> float:
    """Ellipsoidal local distance between two (lat, lon) close points (m)."""
    s = math.sin(math.radians(a[0]))
    w = math.sqrt(1 - E2 * s * s)
    dn = math.radians(b[0] - a[0]) * A_GRS80 * (1 - E2) / w ** 3
    de = math.radians(b[1] - a[1]) * A_GRS80 / w * math.cos(math.radians(a[0]))
    return math.hypot(dn, de)


# ── orthomosaic tiles ──────────────────────────────────────────────────────────

class _Tile:
    __slots__ = ("path", "x0", "y0", "dx", "dy", "w", "h")

    def __init__(self, path, x0, y0, dx, dy, w, h):
        # (x0, y0): projected coordinates of the CENTRE of pixel (0, 0)
        self.path, self.x0, self.y0, self.dx, self.dy, self.w, self.h = path, x0, y0, dx, dy, w, h

    def bounds(self):
        xa, xb = self.x0 - self.dx / 2, self.x0 + (self.w - 0.5) * self.dx
        yb, ya = self.y0 - self.dy / 2, self.y0 - (self.h - 0.5) * self.dy
        return xa, ya, xb, yb


def bordeaux_palette_to_scalar(rgb: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Rainbow palette (blue cold .. red warm) -> uint8 scalar 0..255, and the valid mask.

    The scale is the hue: 240 deg (blue) -> 0, 0 deg (red) -> 255. Pure black / white
    (outside the survey) are not data."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL)          # H in 0..255 for 0..360 deg
    hue = hsv[..., 0].astype(np.float32) * (360.0 / 256.0)
    hue = np.where(hue > 300.0, 0.0, hue)                    # magenta wrap: treat as red
    val = np.clip((240.0 - hue) / 240.0, 0, 1) * 255.0
    s = rgb.astype(np.int16).sum(axis=2)
    valid = (s > 0) & (s < 765) & (hsv[..., 1] > 40)
    return val.astype(np.uint8), valid


class ThermalOrtho:
    """A set of georeferenced thermal tiles in one projection, sampled lazily."""

    def __init__(self, name: str, proj: LambertConformal, tiles: List[_Tile], kind: str,
                 gsd_m: float, cache_tiles: int = 48, exclude=()):
        self.name, self.proj, self.tiles, self.kind, self.gsd_m = name, proj, tiles, kind, gsd_m
        # projected boxes (xa, ya, xb, yb) that are not data: areas the producer masked
        # (filled by interpolation streaks), seen on the overview
        self.exclude = list(exclude)
        self._cache: "OrderedDict[str, tuple]" = OrderedDict()
        self._cache_n = cache_tiles
        self._lock = threading.Lock()
        b = np.array([t.bounds() for t in tiles])
        self._b = b

    # loading
    @classmethod
    def bordeaux(cls, root: str) -> "ThermalOrtho":
        tiles = []
        for d in sorted(os.listdir(root)):
            tif = os.path.join(root, d, f"{d}.tif")
            tfw = os.path.join(root, d, f"{d}.tfw")
            if not (os.path.isfile(tif) and os.path.isfile(tfw)):
                continue
            v = [float(x) for x in open(tfw).read().split()]
            with Image.open(tif) as im:
                w, h = im.size
            tiles.append(_Tile(tif, v[4], v[5], v[0], -v[3], w, h))
        return cls("bordeaux_night", CC45, tiles, "palette", 0.5)

    @classmethod
    def geotiff_float(cls, root: str, name: str, proj: LambertConformal, gsd_m: float,
                      exclude=()) -> "ThermalOrtho":
        tiles = []
        for f in sorted(os.listdir(root)):
            if not f.lower().endswith(".tif"):
                continue
            p = os.path.join(root, f)
            with Image.open(p) as im:
                w, h = im.size
                sc = im.tag_v2.get(33550)
                tp = im.tag_v2.get(33922)
            # GeoTIFF default raster type PixelIsArea: the tie point is the pixel corner
            tiles.append(_Tile(p, tp[3] + sc[0] / 2, tp[4] - sc[1] / 2, sc[0], sc[1], w, h))
        return cls(name, proj, tiles, "float", gsd_m, exclude=exclude)

    def _load(self, t: _Tile):
        with self._lock:
            if t.path in self._cache:
                self._cache.move_to_end(t.path)
                return self._cache[t.path]
        if self.kind == "palette":
            rgb = np.asarray(Image.open(t.path).convert("RGB"))
            val, ok = bordeaux_palette_to_scalar(rgb)
            arr = val.astype(np.float32)
        else:
            arr = np.asarray(Image.open(t.path), dtype=np.float32).copy()
            ok = np.isfinite(arr) & (arr > -1000)
            arr[~ok] = 0
        entry = (arr, ok.astype(np.uint8))
        with self._lock:
            self._cache[t.path] = entry
            while len(self._cache) > self._cache_n:
                self._cache.popitem(last=False)
        return entry

    def sample(self, x: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Bilinear values at projected (x, y) arrays; returns (values float32, valid bool)."""
        out = np.zeros(x.shape, np.float32)
        ok = np.zeros(x.shape, bool)
        xa, xb, ya, yb = x.min(), x.max(), y.min(), y.max()
        hit = np.nonzero((self._b[:, 0] <= xb) & (self._b[:, 2] >= xa) &
                         (self._b[:, 1] <= yb) & (self._b[:, 3] >= ya))[0]
        for i in hit:
            t = self.tiles[i]
            u = ((x - t.x0) / t.dx).astype(np.float32)
            v = ((t.y0 - y) / t.dy).astype(np.float32)
            inside = (u >= -0.5) & (u <= t.w - 0.5) & (v >= -0.5) & (v <= t.h - 0.5) & ~ok
            if not inside.any():
                continue
            arr, valid = self._load(t)
            val = cv2.remap(arr, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
            vm = cv2.remap(valid, u, v, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            take = inside & (vm > 0)
            out[take] = val[take]
            ok |= take
        for xa_, ya_, xb_, yb_ in self.exclude:
            ok &= ~((x >= xa_) & (x <= xb_) & (y >= ya_) & (y <= yb_))
        return out, ok

    def covers(self, lat: float, lon: float, radius_m: float, n: int = 9) -> bool:
        """Is the disc (n x n samples) entirely inside valid data?"""
        g = np.linspace(-radius_m, radius_m, n)
        e, nn = np.meshgrid(g, g)
        la, lo = enu_to_latlon(lat, lon, e, nn)
        x, y = self.proj.forward(la, lo)
        _, ok = self.sample(x, y)
        return bool(ok.all())

    def bbox_latlon(self):
        xa, ya = self._b[:, 0].min(), self._b[:, 1].min()
        xb, yb = self._b[:, 2].max(), self._b[:, 3].max()
        la, lo = self.proj.inverse(np.array([xa, xb, xa, xb]), np.array([ya, ya, yb, yb]))
        return float(la.min()), float(lo.min()), float(la.max()), float(lo.max())

    def random_point(self, rng) -> Tuple[float, float]:
        t = self.tiles[int(rng.integers(0, len(self.tiles)))]
        xa, ya, xb, yb = t.bounds()
        x, y = rng.uniform(xa, xb), rng.uniform(ya, yb)
        la, lo = self.proj.inverse(np.array([x]), np.array([y]))
        return float(la[0]), float(lo[0])


# ── camera ─────────────────────────────────────────────────────────────────────

class Sensor:
    """A nadir thermal camera: pixels, horizontal field of view, noise, gain."""

    def __init__(self, name, width, height, hfov_deg, noise=0.01, psf_px=0.5):
        self.name, self.width, self.height, self.hfov_deg = name, width, height, hfov_deg
        self.noise, self.psf_px = noise, psf_px

    def gsd(self, agl):
        return 2 * agl * math.tan(math.radians(self.hfov_deg) / 2) / self.width


def render(ortho: ThermalOrtho, sensor: Sensor, lat: float, lon: float, agl: float,
           heading_deg: float, rng, polarity: int = 1):
    """The frame a nadir camera at (lat, lon, agl, heading) sees, 8-bit BGR; None if the
    footprint leaves the data (> 0.5 % of it)."""
    ss = max(1, int(math.ceil(sensor.gsd(agl) / ortho.gsd_m)))
    ss = min(ss, 6)
    W, H = sensor.width * ss, sensor.height * ss
    f = (W / 2.0) / math.tan(math.radians(sensor.hfov_deg) / 2)
    u, v = np.meshgrid(np.arange(W, dtype=np.float64) + 0.5 - W / 2,
                       np.arange(H, dtype=np.float64) + 0.5 - H / 2)
    right, fwd = u * agl / f, -v * agl / f
    h = math.radians(heading_deg)
    east = fwd * math.sin(h) + right * math.cos(h)
    north = fwd * math.cos(h) - right * math.sin(h)
    la, lo = enu_to_latlon(lat, lon, east, north)
    x, y = ortho.proj.forward(la, lo)
    val, ok = ortho.sample(x, y)
    if ok.mean() < 0.995:
        return None
    val[~ok] = float(np.median(val[ok]))
    img = cv2.resize(val, (sensor.width, sensor.height), interpolation=cv2.INTER_AREA) if ss > 1 else val
    if sensor.psf_px > 0:
        img = cv2.GaussianBlur(img, (0, 0), sensor.psf_px)
    lo_, hi_ = np.percentile(img, (1, 99))
    img = (img - lo_) / max(hi_ - lo_, 1e-6)
    img = img + rng.normal(0, sensor.noise, img.shape).astype(np.float32)
    lo_, hi_ = np.percentile(img, (1, 99))                  # camera AGC (percentile)
    img = np.clip((img - lo_) / max(hi_ - lo_, 1e-6), 0, 1)
    if polarity < 0:
        img = 1.0 - img
    g = (img * 255).astype(np.uint8)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)


# ── Esri World Imagery z17 MBTiles ─────────────────────────────────────────────

TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def tile_xy(lat, lon, z):
    n = 2 ** z
    r = math.radians(lat)
    return (lon + 180.0) / 360.0 * n, (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n


def tiles_around(lat, lon, radius_m, z=17):
    """XYZ tiles covering a square of +-radius_m around (lat, lon)."""
    la0, lo0 = enu_to_latlon(lat, lon, -radius_m, radius_m)
    la1, lo1 = enu_to_latlon(lat, lon, radius_m, -radius_m)
    x0, y0 = tile_xy(la0, lo0, z)
    x1, y1 = tile_xy(la1, lo1, z)
    return {(z, x, y) for x in range(int(x0), int(x1) + 1) for y in range(int(y0), int(y1) + 1)}


class MapTiles:
    """An MBTiles file of Esri World Imagery tiles, filled on demand."""

    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("CREATE TABLE IF NOT EXISTS metadata (name text, value text)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS tiles (zoom_level integer, tile_column integer, "
                          "tile_row integer, tile_data blob)")
        self.conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS tile_index on tiles "
                          "(zoom_level, tile_column, tile_row)")
        if not self.conn.execute("SELECT 1 FROM metadata WHERE name='format'").fetchone():
            self.conn.executemany("INSERT INTO metadata VALUES (?, ?)", [
                ("name", "Esri World Imagery (evaluation only)"), ("format", "jpg"),
                ("attribution", "Esri, Maxar, Earthstar Geographics, and the GIS User Community")])
        self.conn.commit()

    def have(self, z, x, y) -> bool:
        return self.conn.execute("SELECT 1 FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                                 (z, x, (2 ** z - 1) - y)).fetchone() is not None

    def fetch(self, keys, workers: int = 4) -> Tuple[int, int]:
        """Download the missing tiles among keys; returns (fetched, failed)."""
        todo = [k for k in keys if not self.have(*k)]

        def get(k):
            z, x, y = k
            req = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y),
                                         headers={"User-Agent": "NAVERA-bench/1.0"})
            for _ in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=30) as r:
                        return k, r.read()
                except Exception:
                    continue
            return k, None
        n = 0
        with ThreadPoolExecutor(workers) as ex:
            for (z, x, y), data in ex.map(get, todo):
                if data:
                    self.conn.execute("INSERT OR REPLACE INTO tiles VALUES (?, ?, ?, ?)",
                                      (z, x, (2 ** z - 1) - y, data))
                    n += 1
        self.conn.commit()
        return n, len(todo) - n


class _WebMercatorPx:
    """lat/lon -> global pixel coordinates of 256 px tiles at zoom z (x right, y down)."""

    def __init__(self, z):
        self.z = z

    def forward(self, lat, lon):
        n = 256.0 * 2 ** self.z
        r = np.radians(np.asarray(lat, np.float64))
        x = (np.asarray(lon, np.float64) + 180.0) / 360.0 * n
        y = (1.0 - np.log(np.tan(r) + 1.0 / np.cos(r)) / np.pi) / 2.0 * n
        return x, y


class MapOrtho:
    """The satellite map itself as a frame source (grey): the control that separates the
    pipeline's own error from the thermal-to-map registration. Same interface as ThermalOrtho."""

    def __init__(self, maps: "MapTiles", z: int = 17):
        self.proj, self.maps, self.z, self.gsd_m, self.name = _WebMercatorPx(z), maps, z, 0.85, "map_grey"
        self._cache: "OrderedDict[tuple, np.ndarray]" = OrderedDict()

    def _tile(self, x, y):
        k = (x, y)
        if k not in self._cache:
            row = self.maps.conn.execute(
                "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (self.z, x, (2 ** self.z - 1) - y)).fetchone()
            img = None if row is None else cv2.imdecode(np.frombuffer(row[0], np.uint8), cv2.IMREAD_GRAYSCALE)
            self._cache[k] = img
            while len(self._cache) > 400:
                self._cache.popitem(last=False)
        return self._cache[k]

    def sample(self, x, y):
        # y grows downwards here (pixel rows), unlike the projected metres of ThermalOrtho
        tx0, tx1 = int(np.floor(x.min() / 256)), int(np.floor(x.max() / 256))
        ty0, ty1 = int(np.floor(y.min() / 256)), int(np.floor(y.max() / 256))
        mos = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), np.float32)
        ok_t = np.zeros_like(mos, np.uint8)
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                t = self._tile(tx, ty)
                if t is not None:
                    mos[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = t
                    ok_t[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = 1
        u = (x - tx0 * 256 - 0.5).astype(np.float32)
        v = (y - ty0 * 256 - 0.5).astype(np.float32)
        val = cv2.remap(mos, u, v, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        ok = cv2.remap(ok_t, u, v, cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0) > 0
        return val, ok
