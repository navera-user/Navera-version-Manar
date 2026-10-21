"""dem_sources: Copernicus DEM corridor cut-out (float32 COG reading, GLO-30 -> GLO-90 fallback), offline."""
import math
import struct
import zlib

import numpy as np

from day_pkg import dem_sources as dm
from day_pkg.tile_sources import GeoTiff
from navera_common.terrain import Terrain


def _float_tiff(path, grid, lat_top, lon_left, step_deg, predictor=3):
    """A float32 GeoTIFF as Copernicus ships it: one band, deflate, floating-point predictor,
    EPSG:4326, PixelIsPoint (the tiepoint is the first pixel's centre)."""
    h, w = grid.shape
    if predictor == 3:
        b = grid.astype(">f4").view(np.uint8).reshape(h, w, 4).transpose(0, 2, 1).reshape(h, 4 * w)
        b = np.concatenate([b[:, :1], np.diff(b, axis=1)], axis=1).astype(np.uint8)
        raw = b.tobytes()
    else:
        raw = grid.astype("<f4").tobytes()
    data = zlib.compress(raw)
    entries = []                      # (tag, type, count, payload bytes)

    def add(tag, typ, vals):
        fmt = {3: "H", 4: "I", 12: "d"}[typ]
        entries.append((tag, typ, len(vals), struct.pack("<" + fmt * len(vals), *vals)))
    for tag, typ, vals in ((256, 4, [w]), (257, 4, [h]), (258, 3, [32]), (259, 3, [8]), (262, 3, [1]),
                           (273, 4, [0]), (277, 3, [1]), (278, 4, [h]), (279, 4, [len(data)]), (284, 3, [1]),
                           (317, 3, [predictor]), (339, 3, [3]), (33550, 12, [step_deg, step_deg, 0.0]),
                           (33922, 12, [0.0, 0.0, 0.0, lon_left, lat_top, 0.0]),
                           (34735, 3, [1, 1, 0, 3, 1024, 0, 1, 2, 1025, 0, 1, 2, 2048, 0, 1, 4326])):
        add(tag, typ, vals)
    entries.sort()
    n = len(entries)
    ifd_off = 8
    extra_off = ifd_off + 2 + 12 * n + 4
    extra, ifd = b"", struct.pack("<H", n)
    for tag, typ, cnt, payload in entries:
        if len(payload) <= 4:
            ifd += struct.pack("<HHI", tag, typ, cnt) + payload.ljust(4, b"\0")
        else:
            ifd += struct.pack("<HHII", tag, typ, cnt, extra_off + len(extra))
            extra += payload
    ifd += struct.pack("<I", 0)
    strip_off = extra_off + len(extra)
    ifd = ifd.replace(struct.pack("<HHII", 273, 4, 1, 0), struct.pack("<HHII", 273, 4, 1, strip_off))
    with open(path, "wb") as f:
        f.write(b"II*\0" + struct.pack("<I", ifd_off) + ifd + extra + data)
    return path


def _plane(n, lat0, lon0, step):
    """Heights 1000 + 100 m per 0.01 deg north + 50 m per 0.01 deg east, sampled at pixel centres."""
    r, c = np.mgrid[0:n, 0:n]
    lat, lon = lat0 - r * step, lon0 + c * step
    return (1000.0 + (lat - 39.0) * 1e4 + (lon - 44.0) * 5e3).astype(np.float32)


def test_float32_predictor3_tiff_reads_back(tmp_path):
    g = _plane(120, 40.0, 44.0, 1 / 120)
    for pred in (3, 1):
        t = GeoTiff(open(_float_tiff(str(tmp_path / f"p{pred}.tif"), g, 40.0, 44.0, 1 / 120, pred), "rb"))
        assert t.float32 and t.epsg == 4326 and (t.w, t.h) == (120, 120)
        v = t.values(-2, -2, 122, 122)
        assert np.isnan(v[0, 0]) and np.allclose(v[2:-2, 2:-2], g, atol=1e-3)
        assert math.isclose(t.x0, 44.0 - 0.5 / 120) and math.isclose(t.y0, 40.0 + 0.5 / 120)


def test_tile_url_names_the_cell():
    assert dm.tile_url("R", "10", 39, 44).endswith("Copernicus_DSM_COG_10_N39_00_E044_00_DEM.tif")
    assert "S01_00_W071_00" in dm.tile_url("R", "30", -1, -71)


def test_build_dem_falls_back_to_glo90_and_samples_bilinear(tmp_path):
    """No GLO-30 cell (withheld country): GLO-90 is used; heights at any point match the source."""
    step = 1 / 1200.0
    g = _plane(1200, 40.0, 44.0, step)
    path = _float_tiff(str(tmp_path / "glo90.tif"), g, 40.0, 44.0, step)
    asked = []

    def opener(url):
        asked.append(url)
        return open(path, "rb") if "dem-90m" in url and "N39_00_E044_00" in url else None
    legs = [[39.94, 44.89], [39.95, 44.90]]
    info = dm.build_dem(legs, 1000.0, str(tmp_path / "terrain"), opener=opener)
    assert info["source"] == "Copernicus DEM GLO-90" and info["sigma_m"] == 8.0 and info["missing_share"] == 0.0
    assert any("dem-30m" in u for u in asked)                    # GLO-30 tried first
    T = Terrain.load(str(tmp_path))                               # the area dir holding terrain/
    for lat, lon in ((39.94, 44.89), (39.9437, 44.9012), (39.951, 44.887)):
        h, s, slope = T.height(lat, lon)
        assert abs(h - (1000.0 + (lat - 39.0) * 1e4 + (lon - 44.0) * 5e3)) < 0.05
        assert s == 8.0
        assert math.isclose(slope, math.hypot(1e4 / 111320.0, 5e3 / (111320.0 * math.cos(math.radians(lat)))),
                            rel_tol=0.02)
    assert T.height(39.0, 44.0) is None                           # outside the corridor


def test_build_dem_without_any_source_writes_nothing(tmp_path):
    info = dm.build_dem([[10.0, 10.0]], 500.0, str(tmp_path / "terrain"), opener=lambda u: None)
    assert info["pieces"] == 0 and info["missing_share"] == 1.0
    assert Terrain.load(str(tmp_path)) is None
