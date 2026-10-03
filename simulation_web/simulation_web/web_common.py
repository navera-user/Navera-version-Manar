"""Shared HTTP plumbing for the NAVERA web bridges.

Both bridges (navera_web_bridge, navera_stellar_bridge) serve the same kind of
API on the vehicle's network, so the security rules live here, once:

  * no CORS headers — pages are served by the bridge itself (same origin), and
    other web sites must not be able to script it;
  * control endpoints need the X-Navera-Token header (shared secret); with no
    token configured, control is disabled;
  * request bodies are JSON objects of at most MAX_BODY bytes;
  * map tile coordinates are bounded before any arithmetic on them;
  * static files are confined to the resources directory;
  * idle connections time out;
  * HTTPS when a certificate is configured (NAVERA_TLS_CERT / NAVERA_TLS_KEY).
"""
import hmac
import json
import time
import math
import os
import sqlite3
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Tuple
from urllib.parse import quote

MAX_BODY = 4096          # bytes accepted in a POST body
MAX_ZOOM = 22            # deepest zoom level any MBTiles map is expected to hold
CONNECTION_TIMEOUT_S = 10

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript",
    ".css": "text/css",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
}


def valid_latlon(lat, lon) -> bool:
    """True for finite numbers within [-90, 90] x [-180, 180]."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return (math.isfinite(lat) and math.isfinite(lon)
            and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0)


def parse_tile_path(path: str) -> Optional[Tuple[int, int, int]]:
    """(z, x, y) from "/tiles/z/x/y.ext", or None when malformed or out of range."""
    parts = path.split("/")
    if len(parts) != 5 or parts[1] != "tiles":
        return None
    try:
        z, x, y = int(parts[2]), int(parts[3]), int(parts[4].split(".")[0])
    except ValueError:
        return None
    # Bound z BEFORE computing 2**z: an unchecked client integer made the
    # server allocate gigabytes for 2**z.
    if not (0 <= z <= MAX_ZOOM and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        return None
    return z, x, y



class _CodeGuard:
    """Wrong control codes: after FAILS_ALLOWED in WINDOW_S from one address, that address
    is refused for LOCK_S (a code cannot be guessed by trying them all)."""
    FAILS_ALLOWED, WINDOW_S, LOCK_S = 5, 60.0, 60.0

    def __init__(self):
        self._lock = threading.Lock()
        self._fails = {}                      # address -> [times]
        self._until = {}                      # address -> locked until (monotonic)

    def blocked_for(self, addr):
        with self._lock:
            return max(0.0, self._until.get(addr, 0.0) - time.monotonic())

    def failed(self, addr):
        now = time.monotonic()
        with self._lock:
            ts = [t for t in self._fails.get(addr, []) if now - t < self.WINDOW_S] + [now]
            self._fails[addr] = ts
            if len(ts) >= self.FAILS_ALLOWED:
                self._until[addr], self._fails[addr] = now + self.LOCK_S, []

    def succeeded(self, addr):
        with self._lock:
            self._fails.pop(addr, None)


_GUARD = _CodeGuard()

class MBTilesReader:
    """Thread-safe, read-only access to an MBTiles file (TMS rows)."""

    def __init__(self, path: str, logger):
        self.path = path
        self._log = logger
        self._conn = None
        self._lock = threading.Lock()

    def exists(self) -> bool:
        return bool(self.path) and os.path.exists(self.path)

    def get(self, z: int, x: int, y: int) -> Optional[bytes]:
        """Tile bytes for XYZ coordinates (already bounds-checked), or None."""
        if not self.exists():
            return None
        with self._lock:
            try:
                if self._conn is None:
                    uri = "file:" + quote(self.path) + "?mode=ro"
                    self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
                    self._conn.execute("PRAGMA cache_size=8000")
                    self._conn.execute("PRAGMA temp_store=MEMORY")
                row = self._conn.execute(
                    "SELECT tile_data FROM tiles "
                    "WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                    (z, x, (2 ** z - 1) - y),
                ).fetchone()
            except sqlite3.Error as e:
                self._log.error(f"mbtiles read failed: {e}", throttle_duration_sec=10.0)
                return None
        return bytes(row[0]) if row else None


class BridgeHandler(BaseHTTPRequestHandler):
    """Base request handler. Subclasses set `bridge` (the ROS node)."""

    bridge = None
    timeout = CONNECTION_TIMEOUT_S

    def log_message(self, fmt, *args):
        self.bridge.get_logger().debug(fmt % args)

    # ── responses ──────────────────────────────────────────────────────
    def send_body(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, code: int, obj) -> None:
        # allow_nan=False: a NaN would be emitted as bare NaN, which is not JSON.
        self.send_body(code, "application/json", json.dumps(obj, allow_nan=False).encode())

    # ── control requests ───────────────────────────────────────────────
    def read_control_json(self, token: str, max_body: int = None):
        """Authorise and parse a control POST. Returns the JSON object, or
        None after having sent the error response."""
        if not token:
            self.send_json(403, {"error": "control disabled: set NAVERA_WEB_TOKEN"})
            return None
        client = self.client_address[0] if self.client_address else "?"
        wait = _GUARD.blocked_for(client)
        if wait > 0:
            self.send_json(429, {"error": f"too many wrong codes from this address: wait {wait:.0f} s"})
            return None
        given = self.headers.get("X-Navera-Token", "")
        if not hmac.compare_digest(given.encode(), token.encode()):
            _GUARD.failed(client)
            self.send_json(401, {"error": "missing or wrong X-Navera-Token"})
            return None
        _GUARD.succeeded(client)
        if "application/json" not in self.headers.get("Content-Type", ""):
            self.send_json(415, {"error": "Content-Type must be application/json"})
            return None
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self.send_json(400, {"error": "bad Content-Length"})
            return None
        if not 0 <= length <= (max_body or MAX_BODY):
            self.send_json(413, {"error": "body too large"})
            return None
        try:
            obj = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self.send_json(400, {"error": "invalid JSON"})
            return None
        if not isinstance(obj, dict):
            self.send_json(400, {"error": "JSON object expected"})
            return None
        return obj

    # ── files ──────────────────────────────────────────────────────────
    def send_file(self, full_path: str) -> None:
        ctype = _CONTENT_TYPES.get(os.path.splitext(full_path)[1].lower(),
                                   "application/octet-stream")
        with open(full_path, "rb") as f:
            self.send_body(200, ctype, f.read())

    def serve_static(self, root: str, path: str) -> None:
        """Serve root/path if it stays inside root (checked on the normalised
        path: a symlink install makes every resource a symlink into build/)."""
        rel = path.lstrip("/")
        root = os.path.normpath(root)
        full = os.path.normpath(os.path.join(root, rel))
        if os.path.commonpath([root, full]) == root and os.path.isfile(full):
            return self.send_file(full)
        return self.send_json(404, {"error": f"unknown path: /{rel}"})


def start_server(host: str, port: int, handler_cls, certfile: str = "", keyfile: str = ""):
    """Threaded HTTP(S) server running in a daemon thread. Returns the server.

    With a certificate and key, the server speaks HTTPS only (TLS >= 1.2):
    the control token and the positions are then encrypted on the network.
    """
    httpd = ThreadingHTTPServer((host, port), handler_cls)
    httpd.daemon_threads = True
    if certfile:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(certfile, keyfile or None)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
