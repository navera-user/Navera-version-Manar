"""night_localizer tile cache: a tile is read and decoded once, the cache stays bounded, patches unchanged."""
import sqlite3

import cv2
import numpy as np
import pytest

pytest.importorskip("torch")
from night_pkg.nodes import night_localizer as nl  # noqa: E402


def _mbtiles(z=17, x0=100, y0=200, n=8):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE tiles (zoom_level INT, tile_column INT, tile_row INT, tile_data BLOB)")
    rng = np.random.default_rng(0)
    for x in range(x0, x0 + n):
        for y in range(y0, y0 + n):
            img = rng.integers(0, 255, (256, 256, 3), dtype=np.uint8)
            ok, buf = cv2.imencode(".png", img)
            conn.execute("INSERT INTO tiles VALUES (?,?,?,?)", (z, x, (2 ** z - 1) - y, buf.tobytes()))
    return conn


class _Counting:
    def __init__(self, conn):
        self.conn, self.n = conn, 0

    def execute(self, *a):
        self.n += 1
        return self.conn.execute(*a)


def test_tile_read_once(monkeypatch):
    monkeypatch.setattr(nl, "_tile_cache", nl.OrderedDict())
    monkeypatch.setattr(nl, "_tile_buf", None)
    c = _Counting(_mbtiles())
    a = nl._read_tile(c, 17, 101, 201).copy()
    b = nl._read_tile(c, 17, 101, 201)
    assert c.n == 1 and np.array_equal(a, b) and b.shape == (256, 256, 3)
    assert np.array_equal(b, nl._read_tile_uncached(c.conn, 17, 101, 201))


def test_cache_is_bounded(monkeypatch):
    monkeypatch.setattr(nl, "_tile_cache", nl.OrderedDict())
    monkeypatch.setattr(nl, "_tile_buf", None)
    monkeypatch.setattr(nl, "TILE_CACHE_MAX", 5)
    c = _Counting(_mbtiles())
    for x in range(100, 108):
        t = nl._read_tile(c, 17, x, 200)
        assert np.array_equal(t, nl._read_tile_uncached(c.conn, 17, x, 200))
    assert len(nl._tile_cache) == 5 and nl._tile_buf.shape[0] == 5
    assert nl._read_tile(c, 17, 999, 999) is None                  # absent tile
    assert nl._read_tile(c, 17, 107, 200) is not None and c.n == 9


def test_patch_identical_with_cache(monkeypatch):
    conn = _mbtiles()
    lat, lon = nl._tile_frac_to_latlon(104.3, 204.6, 17)
    monkeypatch.setattr(nl, "_read_tile", nl._read_tile_uncached)
    ref = nl._stitch_satellite_patch(conn, lat, lon, 17, 512)
    monkeypatch.undo()
    monkeypatch.setattr(nl, "_tile_cache", nl.OrderedDict())
    monkeypatch.setattr(nl, "_tile_buf", None)
    first = nl._stitch_satellite_patch(conn, lat, lon, 17, 512)
    again = nl._stitch_satellite_patch(conn, lat, lon, 17, 512)
    for p in (first, again):
        assert np.array_equal(p[0], ref[0]) and p[1:] == ref[1:]
