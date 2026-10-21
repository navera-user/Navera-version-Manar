"""mission_bundle: route input, map levels, plan/estimate, build, and the offline check.

A synthetic textured map (no network, no GPU): the bundle is built from it, then checked with every
socket call refused (and, when `unshare -rn` works without root, in a network namespace)."""
import http.server
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading

import cv2
import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, TOOLS)
import mission_bundle as mb  # noqa: E402
from day_pkg.learned_matcher import LearnedMatcher  # noqa: E402

Z = 17
LAT, LON = 35.82, 10.60
ROUTE = [[35.8200, 10.5960], [35.8215, 10.6060]]        # ~0.9 km
BLOCK = 16                                              # map: BLOCK x BLOCK tiles around the route


def _iers_a_file():
    from astropy.utils import iers
    return iers.IERS_A_FILE


def _iers_date():
    """A date inside the IERS-A table astropy ships (its measured part)."""
    import datetime as dt
    end = dt.date.fromisoformat(mb.iers_coverage(_iers_a_file())["measured_until"])
    return (end - dt.timedelta(days=30)).isoformat()


def _texture(n_px, seed=1):
    rng = np.random.default_rng(seed)
    img = np.full((n_px, n_px, 3), 110, np.uint8)
    for _ in range(n_px * n_px // 900):
        c = tuple(int(v) for v in rng.integers(0, 255, 3))
        x, y = (int(v) for v in rng.integers(0, n_px, 2))
        if rng.random() < 0.5:
            w, h = (int(v) for v in rng.integers(6, 40, 2))
            cv2.rectangle(img, (x, y), (x + w, y + h), c, -1)
        else:
            cv2.circle(img, (x, y), int(rng.integers(4, 22)), c, -1)
    return cv2.GaussianBlur(img, (3, 3), 0)


def _origin():
    fx, fy = mb.corridor_tiles([ROUTE[0]], 0.0, Z)[0]
    return fx - BLOCK // 2 + 3, fy - BLOCK // 2


def _write_map(path, skip=(), meta=None):
    x0, y0 = _origin()
    tex = _texture(BLOCK * 256)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
    con.execute("CREATE TABLE tiles (zoom_level INT, tile_column INT, tile_row INT, tile_data BLOB)")
    con.execute("CREATE UNIQUE INDEX ti ON tiles (zoom_level, tile_column, tile_row)")
    meta = meta or {"source": "synthetic test map", "licence": "test licence"}
    con.executemany("INSERT INTO metadata VALUES (?, ?)", list(meta.items()))
    for j in range(BLOCK):
        for i in range(BLOCK):
            x, y = x0 + i, y0 + j
            if (x, y) in skip:
                continue
            tile = tex[j * 256:(j + 1) * 256, i * 256:(i + 1) * 256]
            ok, buf = cv2.imencode(".jpg", tile, [cv2.IMWRITE_JPEG_QUALITY, 90])
            con.execute("INSERT INTO tiles VALUES (?, ?, ?, ?)", (Z, x, 2 ** Z - 1 - y, buf.tobytes()))
    con.commit()
    con.close()
    return path


def _spec(**kw):
    d = dict(route=ROUTE, corridor_width_m=800.0, min_height_m=50.0, max_height_m=200.0, hfov_deg=60.0,
             frame_width_px=640, learned=False, dinov2=False)
    d.update(kw)
    return mb.MissionSpec(**d)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    d = tmp_path_factory.mktemp("world")
    return _write_map(str(d / "onboard.mbtiles"))


@pytest.fixture(scope="module")
def bundle(world, tmp_path_factory):
    out = str(tmp_path_factory.mktemp("b") / "bundle")
    spec = _spec(extras={"lens.yaml": __file__})
    mb.build_bundle(spec, [mb.MBTilesSource(world)], out, mb.Progress(), iers_file=_iers_a_file())
    return out


# ── route input ────────────────────────────────────────────────────────
def test_route_files_gpx_kml_json(tmp_path):
    gpx = tmp_path / "r.gpx"
    gpx.write_text('<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>'
                   '<trkpt lat="35.82" lon="10.596"/><trkpt lat="35.8215" lon="10.606"/></trkseg></trk></gpx>')
    kml = tmp_path / "r.kml"
    kml.write_text('<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><LineString><coordinates>'
                   '10.596,35.82,0 10.606,35.8215,0</coordinates></LineString></Placemark></kml>')
    js = tmp_path / "r.json"
    js.write_text(json.dumps({"route": [[35.82, 10.596], [35.8215, 10.606]]}))
    want = [[35.82, 10.596], [35.8215, 10.606]]
    for f in (gpx, kml, js):
        assert mb.load_route_file(str(f)) == want
    assert mb.route_from_args("35.82,10.596", "35.8215,10.606") == want
    assert mb.route_from_args("35.82,10.596", "35.8215,10.606", ["35.83,10.6"])[1] == [35.83, 10.6]
    with pytest.raises(ValueError):
        mb.parse_latlon("95,10")


# ── heights, footprint, map levels ─────────────────────────────────────
def test_levels_and_buffer_follow_the_height():
    # the bench camera: 1200 px over 100 deg; 1500 m -> 2.98 m/px, 3.1x the zoom-17 map: level 2
    assert mb.levels_for_heights(35.82, 1500, 1500, 100.0, 1200) == [2]
    assert mb.levels_for_heights(35.82, 100, 1500, 100.0, 1200) == [0, 1, 2]
    low, high = _spec(max_height_m=100.0), _spec(max_height_m=1500.0)
    assert low.buffer_m < high.buffer_m
    assert high.buffer_m == pytest.approx(400.0 + mb.footprint_half_diag_m(1500.0, 60.0, 0.75))
    assert mb.max_supported_height_m(35.82, 100.0, 1200) > 3000.0


def test_chunks_for_tiles_is_exact():
    rng = np.random.default_rng(0)
    tiles = {(int(x), int(y)) for x, y in rng.integers(1000, 1030, (40, 2))}
    step, C = LearnedMatcher.CHUNK - LearnedMatcher.OVERLAP, LearnedMatcher.CHUNK
    for lv in (0, 1, 2, 3):
        f = 2 ** lv
        brute = set()
        for gx in range(0, 1100 * 256 // f // step + 2):
            for gy in range(0, 1100 * 256 // f // step + 2):
                for x, y in tiles:          # chunk box [g*step, g*step+C) vs the tile's level pixels
                    if (gx * step < (x + 1) * 256 / f and gx * step + C > x * 256 / f
                            and gy * step < (y + 1) * 256 / f and gy * step + C > y * 256 / f):
                        brute.add((gx, gy))
                        break
        assert set(LearnedMatcher.chunks_for_tiles(tiles, lv)) == brute


# ── plan / estimate ────────────────────────────────────────────────────
def test_plan_counts_tiles_before_downloading(world, tmp_path):
    spec = _spec()
    p = mb.plan_bundle(spec, [mb.MBTilesSource(world)], str(tmp_path / "x"))
    assert p["tiles"] == len(mb.corridor_tiles(spec.legs, spec.buffer_m, Z)) > 10
    assert p["tiles_missing"] == 0 and p["download_tiles"] == 0
    assert 5 < p["avg_tile_kb"] < 100 and p["total_mb"] > 0 and p["free_mb"] > 0
    assert "tiles" in mb.format_estimate(p)
    # a map missing 5 corridor tiles + a download source: those 5 are to download
    need = mb.corridor_tiles(spec.legs, spec.buffer_m, Z)
    holed = _write_map(str(tmp_path / "holed.mbtiles"), skip=set(need[:5]))
    dl = mb.XYZSource("http://127.0.0.1:9/{z}/{x}/{y}", "test-xyz", "test licence", rate_tps=10.0)
    p2 = mb.plan_bundle(spec, [mb.MBTilesSource(holed), dl])
    assert p2["download_tiles"] == 5 and p2["tiles_missing"] == 0
    assert p2["time_s"]["download"] == pytest.approx(0.5, abs=1)
    p3 = mb.plan_bundle(spec, [mb.MBTilesSource(holed)])
    assert p3["tiles_missing"] == 5 and p3["warnings"]


# ── build ──────────────────────────────────────────────────────────────
def test_bundle_layout_and_manifest(bundle):
    m = json.load(open(os.path.join(bundle, "manifest.json")))
    assert m["format"] == mb.FORMAT and not os.path.exists(bundle + ".partial")
    for rel in (mb.MAP_FILE, "day/dataset.csv", "day/area.json", mb.IERS_NAME, mb.CATALOGUE_NAME, "bundle.env",
                "extra/lens.yaml"):
        assert rel in m["files"], rel
        assert m["files"][rel]["sha256"] == mb.sha256_file(os.path.join(bundle, rel))
    assert m["map"]["tiles"] == m["map"]["tiles_needed"] and m["map"]["missing"] == []
    assert m["map"]["sources"][0]["licence"] == "test licence"
    assert m["day"]["images"] == m["map"]["tiles"]
    assert m["valid_until"]["overall"] == mb.iers_coverage(_iers_a_file())["predicted_until"]
    assert m["celestial"]["catalogue"]["stars"] > 800
    assert {x["name"] for x in m["models"]} >= set(mb.MODEL_FILES)
    meta = mb._mbtiles_meta(os.path.join(bundle, mb.MAP_FILE))
    assert meta["minzoom"] == meta["maxzoom"] == "17" and meta["licence"] == "test licence"
    assert len(meta["bounds"].split(",")) == 4 and meta["downloaded"]
    # corridor only: no tile of the onboard map outside it
    con = sqlite3.connect(os.path.join(bundle, mb.MAP_FILE))
    assert con.execute("SELECT count(*) FROM tiles").fetchone()[0] == m["map"]["tiles_needed"] < BLOCK * BLOCK
    con.close()
    env = dict(line.split("=", 1) for line in mb.env_lines("/somewhere/b", m))
    assert env["DAY_DATASET_DIR"] == "/somewhere/b/day" and env["NAVERA_MBTILES"].endswith(mb.MAP_FILE)


def test_build_refuses_missing_tiles(tmp_path):
    spec = _spec()
    need = mb.corridor_tiles(spec.legs, spec.buffer_m, Z)
    holed = _write_map(str(tmp_path / "holed.mbtiles"), skip={need[0]})
    with pytest.raises(RuntimeError, match="could not be obtained"):
        mb.build_bundle(spec, [mb.MBTilesSource(holed)], str(tmp_path / "b"), mb.Progress(),
                        iers_file=_iers_a_file())
    assert not os.path.exists(tmp_path / "b")


class _Tiles(http.server.BaseHTTPRequestHandler):
    """XYZ server from a MBTiles file; the first request of every tile answers 429."""
    seen = set()
    path_map = None

    def do_GET(self):
        z, x, y = (int(v) for v in self.path.strip("/").split("/"))
        if (x, y) not in self.seen:
            self.seen.add((x, y))
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.end_headers()
            return
        con = sqlite3.connect(self.path_map)
        r = con.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                        (z, x, 2 ** z - 1 - y)).fetchone()
        con.close()
        if not r:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.end_headers()
        self.wfile.write(r[0])

    def log_message(self, *a):
        pass


def test_download_source_fills_the_holes_politely(world, tmp_path):
    spec = _spec()
    need = mb.corridor_tiles(spec.legs, spec.buffer_m, Z)
    holed = _write_map(str(tmp_path / "holed.mbtiles"), skip=set(need[:6]))
    _Tiles.path_map, _Tiles.seen = world, set()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Tiles)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        dl = mb.XYZSource(f"http://127.0.0.1:{srv.server_port}/{{z}}/{{x}}/{{y}}", "test-xyz", "xyz licence",
                          rate_tps=50.0)
        m = mb.build_bundle(spec, [mb.MBTilesSource(holed), dl], str(tmp_path / "b"), mb.Progress(),
                            iers_file=_iers_a_file())
    finally:
        srv.shutdown()
    by = {s["name"]: s["tiles"] for s in m["map"]["sources"]}
    assert by == {"onboard": len(need) - 6, "test-xyz": 6} and m["map"]["missing"] == []
    assert "xyz licence" in m["map"]["licence"] and "test licence" in m["map"]["licence"]


def test_bbox_function_source_copies_only_the_corridor(world, tmp_path):
    calls = []

    def fetch(bbox, source, zooms):
        calls.append((bbox, source, zooms))
        return world                                   # a catalogue returns a bbox map (here: bigger)
    spec = _spec()
    src = [mb.BBoxFunctionSource(fetch, "sentinel-test")]
    m = mb.build_bundle(spec, src, str(tmp_path / "b"), mb.Progress(), iers_file=_iers_a_file())
    assert calls and all(c[1] == "sentinel-test" and c[2] == [Z] for c in calls)
    w, s, e, n = calls[0][0]
    assert w < e and s < n
    assert m["map"]["tiles"] == m["map"]["tiles_needed"] and m["map"]["licence"] == "test licence"


# ── check: offline ─────────────────────────────────────────────────────
def test_check_passes_with_every_socket_refused(bundle, monkeypatch):
    def refuse(*a, **k):
        raise OSError("test: network is off")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    r = mb.check_bundle(bundle, mission_date=_iers_date())
    assert r["ok"], mb.format_report(r)
    c = r["checks"]
    assert c["files"]["ok"] and c["files"]["n_unlisted"] == 0
    assert c["map"]["missing"] == 0 and c["map"]["licence"] == "test licence"
    assert c["day_match"]["accepted"] >= 5 and c["day_match"]["err_max_m"] < 15
    assert c["celestial_time"]["status"] == "IERS-A measured"
    assert c["catalogue"]["stars_mag4"] > 400
    assert c["offline"]["attempts"] == []
    assert r["network"]["offline"]


def test_guard_refuses_and_records_network_use():
    with mb.NetworkGuard() as g:
        with pytest.raises(OSError):
            socket.create_connection(("example.com", 80), timeout=1)
        with pytest.raises(OSError):
            socket.getaddrinfo("example.com", 80)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with pytest.raises(OSError):
            s.connect(("127.0.0.1", 9))
        s.close()
    assert len(g.attempts) == 3
    socket.socket(socket.AF_INET, socket.SOCK_STREAM).close()     # restored


def test_check_finds_tampering_and_holes(bundle, tmp_path):
    b = str(tmp_path / "copy")
    shutil.copytree(bundle, b)
    img = os.path.join(b, "day", "images", sorted(os.listdir(os.path.join(b, "day", "images")))[0])
    with open(img, "ab") as f:
        f.write(b"x")
    con = sqlite3.connect(os.path.join(b, mb.MAP_FILE))
    con.execute("DELETE FROM tiles WHERE rowid IN (SELECT rowid FROM tiles LIMIT 3)")
    con.commit()
    con.close()
    r = mb.check_bundle(b, mission_date=_iers_date())
    assert not r["ok"]
    assert not r["checks"]["files"]["ok"] and img.split(b + "/")[1] in r["checks"]["files"]["sha256_mismatch"]
    assert r["checks"]["map"]["missing"] == 3 and not r["checks"]["map"]["ok"]
    os.remove(os.path.join(b, "manifest.json"))
    assert "incomplete" in mb.check_bundle(b)["error"]


@pytest.mark.skipif(not mb._netns_available(), reason="no unprivileged network namespace (unshare -rn)")
def test_cli_check_in_a_network_namespace(bundle):
    env = dict(os.environ)
    env.pop("NAVERA_BUNDLE_NETNS", None)
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "mission_bundle.py"), "check", bundle,
                        "--date", _iers_date(), "--json"], capture_output=True, text=True, env=env, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    rep = json.loads(r.stdout)
    assert rep["network"]["netns"] and rep["network"]["interfaces"] == ["lo"]
    assert rep["network"]["offline"] and rep["ok"]


def test_cli_plan_json(world):
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "mission_bundle.py"), "plan", "--start",
                        f"{ROUTE[0][0]},{ROUTE[0][1]}", "--dest", f"{ROUTE[1][0]},{ROUTE[1][1]}", "--corridor-m", "800",
                        "--max-height-m", "200", "--hfov", "60", "--frame-width", "640", "--mbtiles", world, "--json"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    p = json.loads(r.stdout)
    assert p["tiles"] > 10 and p["tiles_missing"] == 0 and p["learned_levels"] == [0]


def test_selftest_points_avoid_featureless_stretches():
    d = mb._textured_distances(22180.0, [[13.01, 22.18]], 6)          # Sousse corridor: sea after 13 km
    assert len(d) == 6 and max(d) < 13010.0 and d == sorted(d)
    assert mb._textured_distances(1000.0, [[0.0, 1.0]], 6) == []
    assert len(mb._textured_distances(1000.0, [], 4)) == 4
