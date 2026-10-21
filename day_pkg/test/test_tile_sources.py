"""tile_sources: licence-labelled map sources, GeoTIFF reader, MBTiles metadata (no network)."""
import http.server
import io
import sqlite3
import threading

import numpy as np
import pytest
from PIL import Image, TiffImagePlugin

from day_pkg import tile_sources as ts


def _jpeg(colour=(90, 120, 80)):
    buf = io.BytesIO()
    Image.new("RGB", (256, 256), colour).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def xyz_server():
    """A local XYZ tile server; yields (url template, list of served paths)."""
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
    yield f"http://127.0.0.1:{srv.server_port}/{{z}}/{{x}}/{{y}}", served
    srv.shutdown()


def _geotiff(path, epsg=32632, x0=640000.0, y0=3970000.0, px=10.0, w=400, h=300):
    """An 8-bit RGB GeoTIFF (deflate, predictor 2, stripped): left half red, right half blue."""
    a = np.zeros((h, w, 3), np.uint8)
    a[:, :w // 2] = (200, 30, 30)
    a[:, w // 2:] = (30, 30, 200)
    ifd = TiffImagePlugin.ImageFileDirectory_v2()
    for tag, typ, val in ((33550, 12, (px, px, 0.0)), (33922, 12, (0.0, 0.0, 0.0, x0, y0, 0.0)),
                          (34735, 3, (1, 1, 0, 2, 1024, 0, 1, 1, 3072 if epsg != 4326 else 2048, 0, 1, epsg)),
                          (317, 3, 2)):
        ifd[tag] = val
        ifd.tagtype[tag] = typ
    Image.fromarray(a).save(path, compression="tiff_adobe_deflate", tiffinfo=ifd)
    return path


def test_utm_matches_reference_values():
    # reference: pyproj EPSG:4326 -> EPSG:326xx/327xx
    for lat, lon, zone, south, e, n in ((35.8256, 10.6385, 32, False, 648004.976, 3965844.115),
                                        (38.83, 101.05, 47, False, 677945.289, 4299908.264),
                                        (-33.9, 18.4, 34, True, 259583.222, 6245888.045)):
        E, N = ts.utm_forward(lat, lon, zone, south)
        assert float(E) == pytest.approx(e, abs=0.01) and float(N) == pytest.approx(n, abs=0.01)


def test_bbox_tiles_round_trip():
    bbox = (10.60, 35.80, 10.65, 35.86)
    tiles = ts.bbox_tiles(bbox, 17)
    b = ts.tiles_bbox(tiles, 17)
    assert b[0] <= bbox[0] and b[1] <= bbox[1] and b[2] >= bbox[2] and b[3] >= bbox[3]
    assert b[2] - b[0] < bbox[2] - bbox[0] + 2 * 0.0028                  # at most a tile more each side
    with pytest.raises(ValueError):
        ts.bbox_tiles((10.65, 35.80, 10.60, 35.86), 17)                  # lat/lon swapped


def _lon_at_easting(lat, easting, zone=32):
    lo, hi = zone * 6 - 186.0, zone * 6 - 180.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if float(ts.utm_forward(lat, mid, zone)[0]) < easting else (lo, mid)
    return lo


def test_geotiff_reader_and_tile_rendering(tmp_path):
    g = ts.GeoTiff(open(_geotiff(str(tmp_path / "a.tif")), "rb"))
    assert (g.w, g.h, g.epsg, g.sx) == (400, 300, 32632, 10.0)
    assert (g.window(195, 10, 205, 11)[0, :5] == (200, 30, 30)).all()
    assert (g.window(195, 10, 205, 11)[0, 5:] == (30, 30, 200)).all()
    assert (g.window(-5, -5, 0, 0) == 0).all()                           # outside: no data
    # raster: easting 640000-644000 m (red < 642000 < blue), northing 3967000-3970000 m
    lat = 35.85                                                           # ~N 3968600 in zone 32
    assert 3967000 < float(ts.utm_forward(lat, 10.55, 32)[1]) < 3970000
    for easting, channel in ((641000, 0), (643000, 2)):
        lon = _lon_at_easting(lat, easting)
        fx, fy = ts.tile_xy(lat, lon, 17)
        t = g.render_tile(int(fx), int(fy), 17)
        px = t[int((fy % 1) * 256), int((fx % 1) * 256)]
        assert px[channel] > 150 and px[2 - channel] < 80
    # far away: no data
    assert not g.render_tile(*(int(v) for v in ts.tile_xy(36.5, 10.55, 17)), 17).any()


def test_fetch_custom_xyz_labels_the_map(tmp_path, xyz_server):
    url, served = xyz_server
    out = str(tmp_path / "m.mbtiles")
    bbox = (10.630, 35.820, 10.640, 35.826)
    assert ts.fetch_area(bbox, "custom", out, url=url) == out
    n = len(ts.bbox_tiles(bbox, 17))
    assert len(served) == n
    info = ts.read_map_info(out)
    assert info["labelled"] and info["source"] == "custom" and info["offline_commercial"] == "unknown"
    assert any("unknown" in w for w in ts.licence_warnings(info))
    assert info["bounds"]
    # again: nothing downloaded twice
    ts.fetch_area(bbox, "custom", out, url=url)
    assert len(served) == n
    # another source into the same file is refused
    with pytest.raises(ValueError):
        ts.fetch_tiles(ts.bbox_tiles(bbox, 17), 17, "openaerialmap", out)
    with pytest.raises(ValueError):
        ts.fetch_area(bbox, "custom", out, url=url.replace("127.0.0.1", "localhost"))


def test_overzoom_from_a_coarser_source(xyz_server):
    url, served = xyz_server
    fetch = ts._xyz_fetcher(url, 15, 17)
    a, b = fetch(4 * 1000 + 1, 4 * 2000 + 3), fetch(4 * 1000 + 2, 4 * 2000 + 3)
    assert served == ["/15/1000/2000"]                                    # one parent tile for both
    assert ts._decode(a).shape == (256, 256, 3) and ts._decode(b).shape == (256, 256, 3)


def test_geotiff_source_is_per_contract(tmp_path):
    tif = _geotiff(str(tmp_path / "bought.tif"), epsg=4326, x0=10.60, y0=35.83, px=0.0001)
    out = str(tmp_path / "g.mbtiles")
    r = ts.fetch_tiles(ts.bbox_tiles((10.61, 35.81, 10.62, 35.82), 17), 17, "geotiff", out, path=tif,
                       licence="Airbus EULA 2025, contract 123", provider="Airbus DS")
    assert r["written"] >= 4 and r["failed"] == 0
    info = ts.read_map_info(out)
    assert info["source"] == "geotiff" and info["resolution_m"] == pytest.approx(11.13, abs=0.01)
    assert info["licence"] == "Airbus EULA 2025, contract 123" and info["attribution"] == "Airbus DS"
    assert "contract" in ts.licence_warnings(info)[0]


def test_unlabelled_and_dev_only_maps_are_flagged(tmp_path):
    path = str(tmp_path / "old.mbtiles")
    con = ts.open_mbtiles(path)
    con.close()
    assert not ts.read_map_info(path)["labelled"]
    assert ts.licence_warnings(ts.read_map_info(path))
    con = ts.open_mbtiles(path)
    ts.label_mbtiles(con, ts.SOURCES["esri_world_imagery"])
    con.close()
    info = ts.read_map_info(path)
    assert info["dev_only"] and "development only" in ts.licence_warnings(info)[0]
    con = ts.open_mbtiles(path)
    with pytest.raises(ValueError):
        ts.label_mbtiles(con, ts.SOURCES["sentinel2_l2a"])
    con.close()


def test_open_sources_ship_without_warning(tmp_path):
    path = str(tmp_path / "s2.mbtiles")
    con = ts.open_mbtiles(path)
    meta = ts.label_mbtiles(con, ts.SOURCES["sentinel2_l2a"], imagery_date="2023-10-19")
    con.close()
    assert meta["attribution"] == "Contains modified Copernicus Sentinel data 2023"
    info = ts.read_map_info(path)
    assert info["resolution_m"] == 10.0 and ts.licence_warnings(info) == []


def test_esri_url_is_recognised_as_the_dev_source():
    s = ts.source_for_url(ts.SOURCES["esri_world_imagery"].url)
    assert s.name == "esri_world_imagery" and s.dev_only
    assert ts.source_for_url("https://example.com/{z}/{x}/{y}").name == "custom"
    with pytest.raises(ValueError):
        ts.get_source("google")


def test_mbtiles_schema_is_the_one_prepare_area_reads(tmp_path, xyz_server):
    from day_pkg.prepare_area import _present
    url, _ = xyz_server
    out = str(tmp_path / "m.mbtiles")
    bbox = (10.630, 35.820, 10.640, 35.826)
    ts.fetch_area(bbox, "custom", out, url=url)
    tiles = ts.bbox_tiles(bbox, 17)
    assert _present(out, 17, tiles) == set(tiles)
    assert sqlite3.connect(out).execute("SELECT value FROM metadata WHERE name='format'").fetchone()[0] == "jpg"
