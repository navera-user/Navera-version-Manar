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


def test_missing_tiles_are_downloaded_into_the_cache(tmp_path, mbtiles):
    """A route partly outside the map: the missing tile comes from the tile server."""
    import http.server
    import threading
    from day_pkg.prepare_area import download_missing

    served = []

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            served.append(self.path)
            body = _jpeg()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        path, needed = mbtiles
        cache = str(tmp_path / "cache.mbtiles")
        plan = plan_tiles(path, ROUTE, 1000.0, 17, cache)
        assert plan["missing"] == [needed[0]] and plan["in_cache"] == 0
        url = f"http://127.0.0.1:{srv.server_port}/{{z}}/{{y}}/{{x}}"
        assert download_missing(plan, url, cache, path) == 0
        assert served == [f"/17/{needed[0][1]}/{needed[0][0]}"]      # only the missing tile
        after = plan_tiles(path, ROUTE, 1000.0, 17, cache)
        assert after["missing"] == [] and after["in_cache"] == 1
        # the cache alone now covers the whole corridor
        assert plan_tiles(cache, ROUTE, 1000.0, 17)["missing"] == []
    finally:
        srv.shutdown()


# ── long routes: legs along the great circle ──
from day_pkg.prepare_area import _dist_to_route_m, _haversine_m, densify_route, point_along  # noqa: E402

PARIS, TUNISIA = [48.8534951, 2.3483915], [33.8439408, 9.400138]


def test_short_routes_are_unchanged():
    r = [[35.81, 10.59], [35.825, 10.615]]
    assert densify_route(r) == r


def test_long_route_legs_are_short_and_on_the_great_circle():
    r = densify_route([PARIS, TUNISIA])
    assert r[0] == PARIS and r[-1] == TUNISIA
    legs = [_haversine_m(a, b) for a, b in zip(r, r[1:])]
    assert max(legs) <= 10_000.0 + 1e-6 and sum(legs) == pytest.approx(_haversine_m(PARIS, TUNISIA), rel=1e-6)
    # every leg is short: the straight line between two vertices (what the corridor
    # follows) stays within metres of the great circle a vehicle flies leg by leg
    mid_gap = max(_haversine_m(point_along([a, b], _haversine_m(a, b) / 2)[0],
                               [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]) for a, b in zip(r, r[1:]))
    assert mid_gap < 5.0


def test_the_two_point_line_was_far_from_the_flown_path():
    """Why: the old corridor line is ~35 km from the great circle at mid-route."""
    mid = point_along(densify_route([PARIS, TUNISIA]), _haversine_m(PARIS, TUNISIA) / 2)[0]
    assert _dist_to_route_m(mid[0], mid[1], [PARIS, TUNISIA]) > 20_000.0
    assert _dist_to_route_m(mid[0], mid[1], densify_route([PARIS, TUNISIA])) < 10.0


def test_point_along():
    r = densify_route([PARIS, TUNISIA])
    p, nxt = point_along(r, 0.0)
    assert p == pytest.approx(PARIS) and nxt == 1
    p, nxt = point_along(r, 1e9)
    assert p == pytest.approx(TUNISIA) and nxt == len(r) - 1
    p, nxt = point_along(r, 123_456.0)
    assert _haversine_m(PARIS, p) == pytest.approx(123_456.0, rel=1e-4) and 0 < nxt < len(r)


def test_prepare_without_descriptors_needs_no_model(tmp_path, mbtiles):
    """descriptors=False (mission bundle --no-dinov2): tiles, csv and area.json, no DINOv2 cache."""
    import json
    import os
    from day_pkg.prepare_area import prepare
    path, needed = mbtiles
    out = tmp_path / "area"
    info = prepare(path, str(out), ROUTE, 1000.0, 17, descriptors=False)
    assert info["descriptors"] is False and info["prepared"] == len(needed) - 1
    assert len(os.listdir(out / "images")) == len(needed) - 1
    assert not (out / "descriptors_cache.npz").exists()
    assert json.load(open(out / "area.json"))["missing"] == [list(needed[0])]


def test_downloaded_cache_is_licence_labelled(tmp_path, mbtiles):
    """The cache says where its tiles come from; another source is not mixed into it."""
    from day_pkg import tile_sources
    from day_pkg.prepare_area import download_missing, open_cache
    path, needed = mbtiles
    cache = str(tmp_path / "cache.mbtiles")
    con = open_cache(cache)
    tile_sources.label_mbtiles(con, tile_sources.SOURCES["esri_world_imagery"])
    con.close()
    info = tile_sources.read_map_info(cache)
    assert info["source"] == "esri_world_imagery" and tile_sources.licence_warnings(info)
    plan = plan_tiles(path, ROUTE, 1000.0, 17, cache)
    with pytest.raises(ValueError):                 # a Sentinel-2 download into an Esri cache
        download_missing(plan, "sentinel2_l2a", cache, path)
    with pytest.raises(ValueError):                 # or another XYZ service
        download_missing(plan, "http://127.0.0.1:9/{z}/{x}/{y}", cache, path)
