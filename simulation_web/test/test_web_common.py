"""Unit tests for simulation_web.web_common (the bridges' security layer).

A real threaded HTTP server is started with a minimal handler; no ROS needed.
"""
import http.client
import sqlite3

import pytest

from simulation_web.web_common import (MAX_BODY, BridgeHandler, MBTilesReader, parse_tile_path,
                                       start_server, valid_latlon)

TOKEN = "s3cret"


class _Log:
    def debug(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class _Bridge:
    def get_logger(self):
        return _Log()


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp("resources")
    (root / "page.html").write_text("<p>ok</p>")

    class Handler(BridgeHandler):
        def do_GET(self):
            return self.serve_static(str(root), self.path)

        def do_POST(self):
            d = self.read_control_json(self.server.token)
            if d is not None:
                self.send_json(200, {"got": d})

    Handler.bridge = _Bridge()
    httpd = start_server("127.0.0.1", 0, Handler)
    httpd.token = TOKEN
    yield httpd
    httpd.shutdown()


def _request(server, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read()
    return r.status, dict(r.getheaders()), data


J = {"Content-Type": "application/json", "X-Navera-Token": TOKEN}


@pytest.mark.parametrize("headers, body, status", [
    ({"Content-Type": "application/json"}, "{}", 401),                        # no token
    ({"Content-Type": "application/json", "X-Navera-Token": "x"}, "{}", 401),  # wrong token
    ({"Content-Type": "text/plain", "X-Navera-Token": TOKEN}, "{}", 415),      # CSRF-style
    (J, "not json", 400),
    (J, "[1, 2]", 400),                                                        # not an object
    (J, " " * (MAX_BODY + 1), 413),
    (J, '{"a": 1}', 200),
])
def test_control_requests(server, headers, body, status):
    code, _, _ = _request(server, "POST", "/api/x", body, headers)
    assert code == status


def test_control_disabled_without_token(server):
    server.token = ""
    try:
        code, _, _ = _request(server, "POST", "/api/x", "{}", J)
    finally:
        server.token = TOKEN
    assert code == 403


def test_no_cors_and_nosniff(server):
    code, headers, _ = _request(server, "GET", "/page.html")
    assert code == 200
    assert not any(h.lower().startswith("access-control") for h in headers)
    assert headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.parametrize("path", ["/../../etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/nope.html"])
def test_static_stays_inside_root(server, path):
    code, _, _ = _request(server, "GET", path)
    assert code == 404


@pytest.mark.parametrize("path, expected", [
    ("/tiles/17/69388/51536.jpg", (17, 69388, 51536)),
    ("/tiles/0/0/0.png", (0, 0, 0)),
    ("/tiles/40000000/0/0.jpg", None),          # the 2**z memory attack
    ("/tiles/23/0/0.jpg", None),
    ("/tiles/3/8/0.jpg", None),                  # x out of range at z=3
    ("/tiles/3/0/-1.jpg", None),
    ("/tiles/a/b/c.jpg", None),
    ("/tiles/17/1.jpg", None),
])
def test_parse_tile_path(path, expected):
    assert parse_tile_path(path) == expected


@pytest.mark.parametrize("lat, lon, ok", [
    (35.8, 10.6, True), ("35.8", "10.6", True), ("nan", 10, False),
    (91, 0, False), (0, -181, False), (None, 0, False), ({}, 0, False)])
def test_valid_latlon(lat, lon, ok):
    assert valid_latlon(lat, lon) is ok


def test_mbtiles_reader_flips_rows_and_is_read_only(tmp_path):
    path = tmp_path / "m.mbtiles"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE tiles (zoom_level INT, tile_column INT, tile_row INT, tile_data BLOB)")
    conn.execute("INSERT INTO tiles VALUES (2, 1, 3, ?)", (b"tile-bytes",))   # TMS row 3 = XYZ y 0
    conn.commit()
    conn.close()
    r = MBTilesReader(str(path), _Log())
    assert r.get(2, 1, 0) == b"tile-bytes"
    assert r.get(2, 1, 3) is None
    with pytest.raises(sqlite3.OperationalError):
        r._conn.execute("DELETE FROM tiles")                                  # opened read-only


def test_mbtiles_reader_missing_file(tmp_path):
    assert MBTilesReader(str(tmp_path / "none.mbtiles"), _Log()).get(0, 0, 0) is None


def test_https_when_a_certificate_is_configured(tmp_path):
    import shutil
    import ssl
    import subprocess
    if shutil.which("openssl") is None:
        pytest.skip("openssl not available")
    cert, key = tmp_path / "c.pem", tmp_path / "k.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=navera-test", "-keyout", str(key), "-out", str(cert)],
                   check=True, capture_output=True)
    (tmp_path / "p.html").write_text("ok")

    class Handler(BridgeHandler):
        def do_GET(self):
            return self.serve_static(str(tmp_path), self.path)

    Handler.bridge = _Bridge()
    httpd = start_server("127.0.0.1", 0, Handler, str(cert), str(key))
    port = httpd.server_address[1]
    try:
        ctx = ssl.create_default_context(cafile=str(cert))
        ctx.check_hostname = False
        c = http.client.HTTPSConnection("127.0.0.1", port, context=ctx, timeout=5)
        c.request("GET", "/p.html")
        r = c.getresponse()
        assert r.status == 200 and r.read() == b"ok"
        plain = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        with pytest.raises(Exception):                   # plain HTTP is not served
            plain.request("GET", "/p.html")
            plain.getresponse()
    finally:
        httpd.shutdown()


def test_the_code_guard_forgets_old_addresses(monkeypatch):
    """Wrong codes from many addresses over hours: ended lock-outs and old failures are dropped."""
    from simulation_web import web_common as wc
    now = [1000.0]
    monkeypatch.setattr(wc.time, "monotonic", lambda: now[0])
    g = wc._CodeGuard()
    for i in range(500):
        for _ in range(g.FAILS_ALLOWED):
            g.failed(f"10.0.{i // 250}.{i % 250}")
        now[0] += 1.0
    assert g.blocked_for("10.0.1.249") > 0                          # the newest is still locked out
    now[0] += g.LOCK_S + g.WINDOW_S + 1
    g.failed("10.9.9.9")
    assert set(g._until) == set() and set(g._fails) == {"10.9.9.9"}
    assert g.blocked_for("10.0.1.249") == 0
