#!/usr/bin/env python3
"""
NAVERA — day_node.py  (ROS2 Node + process manager)
====================================================
Lance le bon receiver selon le mode de mission choisi dans l'UI :
  - A→B connus  → receiver.py       (port 5000, pré-collecte + cache)
  - A-only       → receiver_aonly.py (port 5000, dataset temps réel)

Expose aussi un mini-HTTP sur le port 8181 pour :
  - /tiles/{z}/{x}/{y}.png  → proxy MBTiles SQLite
  - /navera.html            → interface NAVERA UI
  - /api/node?action=...    → start_receiver / start_receiver_aonly / start_vision / stop
  - /api/set_mission        → forward mission config to receiver

Architecture :
  T1  ros2 run day_pkg day_node      (ou python3 day_node.py)
  T2  Browser → http://localhost:8181/navera.html
  T3  Receiver lancé automatiquement par /api/node?action=start_receiver[_aonly]
"""

import os
import sys
import json
import math
import sqlite3
import subprocess
import threading
import signal
import io
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen, Request
from urllib.error import URLError

# ── Chemins ─────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).resolve().parent.parent.parent  # .../isaac_ros-dev
PKG_DIR       = Path(__file__).resolve().parent                # .../day_pkg/day_pkg
MBTILES_PATH  = BASE_DIR / "sousse_satellite.mbtiles"
NAVERA_HTML   = BASE_DIR / "simulation_web" / "navera.html"
GPS_STATUS    = BASE_DIR / "gps_status.json"

TILE_PORT     = 8181
RECEIVER_PORT = 5000

# ── State des processus ──────────────────────────────────────────────────────
_procs: dict[str, subprocess.Popen] = {}
_procs_lock = threading.Lock()


def _start_process(name: str, cmd: list[str], cwd: str = None):
    """Lance un sous-processus (si pas déjà actif)."""
    with _procs_lock:
        existing = _procs.get(name)
        if existing and existing.poll() is None:
            print(f"[Node] {name} already running (pid={existing.pid})")
            return existing.pid
        env = os.environ.copy()
        env["HF_HOME"] = "/usr/local/share/hf_cache"
        p = subprocess.Popen(
            cmd,
            cwd=cwd or str(PKG_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        _procs[name] = p
        print(f"[Node] Started {name} pid={p.pid}  cmd={' '.join(cmd)}")
        # Tail stdout in background
        def _tail():
            for line in iter(p.stdout.readline, b""):
                sys.stdout.write(f"[{name}] {line.decode(errors='replace')}")
        threading.Thread(target=_tail, daemon=True).start()
        return p.pid


def _stop_process(name: str):
    with _procs_lock:
        p = _procs.pop(name, None)
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
        print(f"[Node] Stopped {name}")


# ── MBTiles helper ──────────────────────────────────────────────────────────
_db_conn: sqlite3.Connection | None = None
_db_lock = threading.Lock()


def _get_tile(z: int, x: int, y: int) -> bytes | None:
    global _db_conn
    if not MBTILES_PATH.exists():
        return None
    with _db_lock:
        if _db_conn is None:
            _db_conn = sqlite3.connect(str(MBTILES_PATH), check_same_thread=False)
            _db_conn.execute("PRAGMA cache_size=8000")
            _db_conn.execute("PRAGMA temp_store=MEMORY")
        y_tms = (2 ** z - 1) - y
        cur = _db_conn.cursor()
        cur.execute(
            "SELECT tile_data FROM tiles "
            "WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (z, x, y_tms),
        )
        row = cur.fetchone()
        return bytes(row[0]) if row else None


# ── HTTP Request Handler ─────────────────────────────────────────────────────
class NaveraHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Silence tile 404s to keep console clean
        if "404" not in fmt % args:
            super().log_message(fmt, *args)

    def _send(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj).encode()
        self._send(code, "application/json", body)

    # ── GET ─────────────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/")
        qs     = parse_qs(parsed.query)

        # ── Tiles  /tiles/{z}/{x}/{y}.png ───────────────────────────────
        if path.startswith("/tiles/"):
            parts = path.split("/")
            try:
                z, x, y = int(parts[2]), int(parts[3]), int(parts[4].replace(".png", ""))
            except (IndexError, ValueError):
                self._json(400, {"error": "bad tile path"})
                return
            data = _get_tile(z, x, y)
            if data:
                self._send(200, "image/png", data)
            else:
                self._json(404, {"error": "tile not found"})
            return

        # ── Static: navera.html ─────────────────────────────────────────
        if path in ("", "/", "/navera.html"):
            if NAVERA_HTML.exists():
                self._send(200, "text/html; charset=utf-8", NAVERA_HTML.read_bytes())
            else:
                self._json(404, {"error": "navera.html not found"})
            return

        # ── /api/node?action=... ────────────────────────────────────────
        if path == "/api/node":
            action = qs.get("action", [""])[0]
            self._handle_node_action(action)
            return

        # ── /api/set_mission (forwarded from browser) ───────────────────
        # Browser sends POST but let's also accept GET for health check
        if path == "/api/set_mission":
            self._json(200, {"ok": True, "note": "use POST"})
            return

        # ── Proxy: forward to receiver on port 5000 ─────────────────────
        if path in ("/gps_status.json", "/flight_log.csv",
                    "/api/cache_status", "/api/precollect_progress",
                    "/health"):
            self._proxy_to_receiver("GET", path, None)
            return

        self._json(404, {"error": f"unknown path: {path}"})

    # ── POST ────────────────────────────────────────────────────────────────
    def do_POST(self):
        parsed  = urlparse(self.path)
        path    = parsed.path.rstrip("/")
        length  = int(self.headers.get("Content-Length", 0))
        body    = self.rfile.read(length) if length else b""

        # Forward everything POST to receiver (api/set_mission, api/precollect, /frame …)
        self._proxy_to_receiver("POST", path, body)

    # ── OPTIONS (CORS preflight) ─────────────────────────────────────────────
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── Proxy helper ────────────────────────────────────────────────────────
    def _proxy_to_receiver(self, method: str, path: str, body: bytes | None):
        url = f"http://localhost:{RECEIVER_PORT}{path}"
        headers = {"Content-Type": "application/json"}
        try:
            req  = Request(url, data=body, headers=headers, method=method)
            resp = urlopen(req, timeout=15)
            data = resp.read()
            ct   = resp.getheader("Content-Type", "application/json")
            self._send(resp.status, ct, data)
        except URLError as e:
            self._json(503, {"error": f"receiver unavailable: {e}"})

    # ── Node action handler ──────────────────────────────────────────────────
    def _handle_node_action(self, action: str):
        if action == "start_receiver":
            pid = _start_process(
                "receiver",
                [sys.executable, str(PKG_DIR / "receiver.py")],
            )
            self._json(200, {"ok": True, "pid": pid, "mode": "ab"})

        elif action == "start_receiver_aonly":
            pid = _start_process(
                "receiver",
                [sys.executable, str(PKG_DIR / "receiver_aonly.py")],
            )
            self._json(200, {"ok": True, "pid": pid, "mode": "a-only"})

        elif action == "start_night_receiver":
            night_pkg = BASE_DIR / "night_pkg" / "night_pkg"
            pid = _start_process(
                "night_receiver",
                [sys.executable, str(night_pkg / "receiver.py")],
                cwd=str(night_pkg),
            )
            self._json(200, {"ok": True, "pid": pid, "mode": "night"})

        elif action == "start_stellar_receiver":
            stellar_pkg = BASE_DIR / "stellar_pkg" / "stellar_pkg"
            pid = _start_process(
                "stellar_receiver",
                [sys.executable, str(stellar_pkg / "receiver.py")],
                cwd=str(stellar_pkg),
            )
            self._json(200, {"ok": True, "pid": pid, "mode": "stellar"})

        elif action == "start_vision":
            # No-op in standalone mode — vision_node is ROS2.
            # In ROS2 mode, ros2 run day_pkg day_node starts this.
            self._json(200, {"ok": True, "note": "vision_node managed by ROS2"})

        elif action == "stop_receiver":
            _stop_process("receiver")
            self._json(200, {"ok": True})

        elif action == "status":
            with _procs_lock:
                status = {
                    name: (p.poll() is None)
                    for name, p in _procs.items()
                }
            self._json(200, {"ok": True, "processes": status})

        else:
            self._json(400, {"error": f"unknown action: {action}"})


# ── ROS2 Node wrapper (optional) ─────────────────────────────────────────────
def _maybe_run_ros2():
    """
    Si ROS2 est disponible, enregistre ce nœud dans le graph.
    Sinon, tourne en mode standalone (pas de ROS2 requis).
    """
    try:
        import rclpy
        from rclpy.node import Node

        class DayNodeRos(Node):
            def __init__(self):
                super().__init__("day_node")
                self.get_logger().info("DayNode ROS2 ready")

        rclpy.init()
        node = DayNodeRos()
        t = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
        t.start()
        print("[Node] ROS2 spin started")
    except Exception as e:
        print(f"[Node] ROS2 not available ({e}) — running standalone")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    # Init gps_status if missing
    if not GPS_STATUS.exists():
        GPS_STATUS.write_text(json.dumps({"status": "idle", "mission_started": False}))

    # Optional ROS2
    _maybe_run_ros2()

    # HTTP tile server + API
    httpd = HTTPServer(("0.0.0.0", TILE_PORT), NaveraHandler)
    print(f"[Node] NAVERA tile server on http://localhost:{TILE_PORT}")
    print(f"[Node] Open  http://localhost:{TILE_PORT}/navera.html")

    # Graceful shutdown
    def _shutdown(sig, frame):
        print("\n[Node] Shutting down...")
        for name in list(_procs.keys()):
            _stop_process(name)
        httpd.shutdown()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    httpd.serve_forever()


if __name__ == "__main__":
    main()
