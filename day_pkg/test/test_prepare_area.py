"""prepare_area: corridor tile selection and MBTiles coverage (no model needed)."""
import io
import math
import sqlite3

import pytest
from PIL import Image

from day_pkg.nodes.day_localizer import tile_center_latlon
from day_pkg.prepare_area import _dist_to_route_m, plan_tiles, tile_center, tile_nw, tile_xy

ROUTE = [(35.8256, 10.6385), (35.8560, 10.6010)]


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), (90, 120, 80)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def mbtiles(tmp_path):
    """A map holding every corridor tile except one."""
    path = tmp_path / "t.mbtiles"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE tiles (zoom_level INT, tile_column INT, tile_row INT, tile_data BLOB)")
    con.commit()
    con.close()
    needed = plan_tiles(str(path), ROUTE, 1000.0, 17)["needed"]
    con = sqlite3.connect(path)
    data = _jpeg()
    for x, y in needed[1:]:                        # the first one is missing
        con.execute("INSERT INTO tiles VALUES (17, ?, ?, ?)", (x, 2 ** 17 - 1 - y, data))
    con.commit()
    con.close()
    return str(path), needed


def test_corridor_covers_the_route_and_reports_missing(mbtiles):
    path, needed = mbtiles
    p = plan_tiles(path, ROUTE, 1000.0, 17)
    assert p["needed"] == needed and len(needed) > 100
    assert p["missing"] == [needed[0]] and len(p["present"]) == len(needed) - 1
    # every point of the route lies in a corridor tile
    for f in (0.0, 0.25, 0.5, 0.75, 1.0):
        lat = ROUTE[0][0] + f * (ROUTE[1][0] - ROUTE[0][0])
        lon = ROUTE[0][1] + f * (ROUTE[1][1] - ROUTE[0][1])
        x, y = tile_xy(lat, lon, 17)
        assert (int(x), int(y)) in needed
    # and no tile is far outside the corridor
    for x, y in needed:
        c = tile_center(x, y, 17)
        assert _dist_to_route_m(c[0], c[1], ROUTE) < 1000 + 250


def test_tile_geometry_matches_day_localizer():
    x, y = 69390, 51542
    assert tile_center(x, y, 17) == pytest.approx(tile_center_latlon(f"tile_17_{x}_{y}.jpg"))
    nw = tile_nw(x, y, 17)
    fx, fy = tile_xy(nw[0], nw[1], 17)
    assert (fx, fy) == (pytest.approx(x), pytest.approx(y))


def test_distance_to_route():
    assert _dist_to_route_m(*ROUTE[0], ROUTE) == pytest.approx(0.0, abs=0.01)
    lat, lon = ROUTE[0][0] + 1000 / 111320.0, ROUTE[0][1]      # 1 km north of the start
    assert 500 < _dist_to_route_m(lat, lon, ROUTE) <= 1000.5
    assert math.isfinite(_dist_to_route_m(35.0, 10.0, [ROUTE[0]]))
