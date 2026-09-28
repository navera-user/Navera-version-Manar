"""Unit tests for the night (STHN) geometry: patch stitching and output reading.

No model is loaded. A synthetic MBTiles file is built in which every pixel
encodes its own tile and pixel coordinates, so the stitched patch can be
checked pixel-exactly.
"""
import math
import sqlite3

import cv2
import numpy as np
import pytest

from night_pkg.nodes import night_localizer as nl

Z = 17


def _encoded_tile(x, y):
    """B = column in tile, G = row in tile, R = tile id (x%16 + 16*(y%16))."""
    u, v = np.meshgrid(np.arange(256), np.arange(256))
    img = np.zeros((256, 256, 3), np.uint8)
    img[..., 0] = u
    img[..., 1] = v
    img[..., 2] = (x % 16) + 16 * (y % 16)
    return img


@pytest.fixture(scope="module")
def mbtiles(tmp_path_factory):
    path = tmp_path_factory.mktemp("tiles") / "synthetic.mbtiles"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE tiles (zoom_level INT, tile_column INT, tile_row INT, tile_data BLOB)")
    x0, y0 = nl._latlon_to_tile_frac(35.83, 10.64, Z)
    cx, cy = int(x0), int(y0)
    for x in range(cx - 5, cx + 6):
        for y in range(cy - 5, cy + 6):
            ok, png = cv2.imencode(".png", _encoded_tile(x, y))
            conn.execute("INSERT INTO tiles VALUES (?,?,?,?)", (Z, x, (2 ** Z - 1) - y, png.tobytes()))
    conn.commit()
    return conn


@pytest.mark.parametrize("lat, lon", [(35.83, 10.64), (35.8312, 10.6433), (35.8277, 10.6371)])
@pytest.mark.parametrize("size", [256, 1536])
def test_patch_is_centred_on_the_prior(mbtiles, lat, lon, size):
    """Regression: the patch used to be centred on the tile, up to ~110 m from the prior."""
    patch, ox, oy, missing = nl._stitch_satellite_patch(mbtiles, lat, lon, Z, size)
    assert patch.shape == (size, size, 3) and missing == 0
    b, g, r = (int(c) for c in patch[size // 2, size // 2])
    # Decode the global position of the centre pixel from its colour.
    xf, yf = nl._latlon_to_tile_frac(lat, lon, Z)
    tx, ty = int(xf), int(yf)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if (tx + dx) % 16 + 16 * ((ty + dy) % 16) == r:
                cx_px = (tx + dx - xf) * 256 + b + 0.5
                cy_px = (ty + dy - yf) * 256 + g + 0.5
                assert abs(cx_px) <= 1.0 and abs(cy_px) <= 1.0
                break
        else:
            continue
        break
    else:
        pytest.fail("centre pixel not in a tile next to the prior")
    # The returned origin maps the patch centre back onto the prior.
    lat_c, lon_c = nl._tile_frac_to_latlon(ox + (size / 2) / 256, oy + (size / 2) / 256, Z)
    assert abs(lat_c - lat) * 111320 < 1.0 and abs(lon_c - lon) * 111320 * math.cos(math.radians(lat)) < 1.0


def test_missing_tiles_are_counted(mbtiles):
    _, _, _, missing = nl._stitch_satellite_patch(mbtiles, 35.95, 10.64, Z, 256)
    assert missing > 0


def test_tile_frac_round_trip():
    for lat, lon in [(35.83, 10.64), (-33.9, 151.2), (60.0, -30.0)]:
        x, y = nl._latlon_to_tile_frac(lat, lon, Z)
        assert nl._tile_frac_to_latlon(x, y, Z) == pytest.approx((lat, lon), abs=1e-9)


def _corners(dx, dy, rw=256):
    fp = np.zeros((1, 2, 2, 2))
    fp[0, 0] += dx
    fp[0, 1] += dy
    return nl.NightLocalizer._predicted_corners(fp, rw)


def test_output_axes_are_not_mixed():
    """Regression: four_pred [1,2,2,2] was read as (4,2), mixing x and y."""
    assert _corners(0, 0).mean(axis=0) == pytest.approx((127.5, 127.5))
    assert _corners(10, 0).mean(axis=0) == pytest.approx((137.5, 127.5))   # east only
    assert _corners(0, -10).mean(axis=0) == pytest.approx((127.5, 117.5))  # north only


def test_quad_consistency():
    q = nl.NightLocalizer._quad_consistency
    assert q(_corners(0, 0)) == pytest.approx(1.0)
    assert q(_corners(30, -20)) == pytest.approx(1.0)       # pure shift keeps a square
    bad = np.zeros((1, 2, 2, 2))
    bad[0, 0, 0, 1] = -300.0                                  # TR crosses TL: self-intersecting
    assert q(nl.NightLocalizer._predicted_corners(bad, 256)) == 0.0
