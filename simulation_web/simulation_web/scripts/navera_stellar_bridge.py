#!/usr/bin/env python3
"""
navera_stellar_bridge.py — ROS 2 → web bridge for NAVERA stellar (celestial) mode.

Stellar counterpart of navera_web_bridge.py. It subscribes to the celestial
navigation output and re-publishes it over HTTP in the exact shape the stellar
view of navera.html polls (stlHandleGps), so the browser marker moves in real
time from the ROS chain (camera_pkg celestial → cn_subscriber → /cn/*):

  ROS in:
    /cn/cn_status          std_msgs/String        (JSON from cn_subscriber)
    /cn/position_estimate  sensor_msgs/NavSatFix  (fallback lat/lon)

  HTTP out (single server, default port 8181 — same as day, only one runs):
    GET  /                       → navera.html
    GET  /navera.html            → navera.html
    GET  /tiles/{z}/{x}/{y}.png  → MBTiles tile (TMS flip-Y)
    GET  /gps_status.json        → {status:"predicted", lat, lon, ra_deg, dec_deg, …}
    GET  /health                 → {ok:true}
    GET/POST /api/*, /frame       → benign stubs (the ROS chain feeds frames, not HTTP)
    (any other GET)              → static file from resources/

Run standalone (test the bridge alone, no camera/subscriber needed):
    ros2 run simulation_web navera_stellar_bridge.py
    curl http://localhost:8181/gps_status.json     # → {"status": "idle"}
"""
import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from std_msgs.msg import String, Bool
from sensor_msgs.msg import NavSatFix

try:
    from ament_index_python.packages import get_package_share_directory
except Exception:
    get_package_share_directory = None


_MBTILES_CANDIDATES = [
    "/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles",
    "/home/navera/isaac_ros_common/sousse_satellite.mbtiles",
]


def _resolve_resources_dir():
    """Locate the resources/ dir holding navera.html (installed share or source)."""
    if get_package_share_directory is not None:
        try:
            d = os.path.join(get_package_share_directory("simulation_web"), "resources")
            if os.path.isdir(d):
                return d
        except Exception:
            pass
    here = os.path.dirname(os.path.realpath(__file__))
    return os.path.normpath(os.path.join(here, "..", "resources"))


class NaveraStellarBridge(Node):
    def __init__(self):
        super().__init__("navera_stellar_bridge")

        # ── Parameters ──────────────────────────────────────────
        self.declare_parameter("status_topic", "/cn/cn_status")
        self.declare_parameter("fix_topic", "/cn/position_estimate")
        self.declare_parameter("mbtiles_path", "")
        self.declare_parameter("web_host", "0.0.0.0")
        self.declare_parameter("web_port", 8181)

        status_topic = self.get_parameter("status_topic").value
        fix_topic    = self.get_parameter("fix_topic").value
        self.web_host = self.get_parameter("web_host").value
        self.web_port = int(self.get_parameter("web_port").value)

        mb = self.get_parameter("mbtiles_path").value
        if not mb:
            mb = next((p for p in _MBTILES_CANDIDATES if os.path.exists(p)), _MBTILES_CANDIDATES[0])
        self.mbtiles_path = mb

        self.resources_dir = _resolve_resources_dir()
        self.navera_html   = os.path.join(self.resources_dir, "navera.html")

        # ── Shared state ────────────────────────────────────────
        self._state_lock = threading.Lock()
        self._gps_status = {"status": "idle"}
        self._point_a = None

        # ── Tile DB (lazy, thread-safe) ─────────────────────────
        self._db_conn = None
        self._db_lock = threading.Lock()

        # ── ROS subscriptions ───────────────────────────────────
        self.create_subscription(String,    status_topic, self._on_status, 10)
        self.create_subscription(NavSatFix, fix_topic,    self._on_fix,    10)

        # ── camera start/pause trigger (mirrors navera_web_bridge) ──
        self.declare_parameter("start_topic", "/celestial/camera/start")
        start_topic = self.get_parameter("start_topic").value
        cmd_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             history=HistoryPolicy.KEEP_LAST, depth=1)
        self._start_pub = self.create_publisher(Bool, start_topic, cmd_qos)

        # ── Banner ──────────────────────────────────────────────
        self.get_logger().info("=" * 60)
        self.get_logger().info("  NAVERA stellar bridge — ROS → web (celestial mode)")
        self.get_logger().info(f"  status topic : {status_topic}")
        self.get_logger().info(f"  fix topic    : {fix_topic}")
        self.get_logger().info(f"  mbtiles      : {self.mbtiles_path}"
                               f" {'(OK)' if os.path.exists(self.mbtiles_path) else '(MISSING!)'}")
        self.get_logger().info(f"  navera.html  : {self.navera_html}"
                               f" {'(OK)' if os.path.exists(self.navera_html) else '(MISSING!)'}")
        self.get_logger().info(f"  http         : http://{self.web_host}:{self.web_port}/")
        self.get_logger().info("=" * 60)

        self._start_http_server()

    # ────────────────────────────────────────────────────────────
    # ROS callbacks → update shared gps_status (stellar shape)
    # ────────────────────────────────────────────────────────────
    def _on_status(self, msg: String):
        try:
            d = json.loads(msg.data)
        except Exception as e:
            self.get_logger().warn(f"cn_status JSON decode failed: {e}")
            return

        frame_id = d.get("frame_id")
        lat, lon = d.get("lat"), d.get("lon")

        if d.get("success") and lat is not None and lon is not None:
            new = {
                "status": "predicted",
                "lat": float(lat), "lon": float(lon),
                "ra_deg": d.get("ra_deg"), "dec_deg": d.get("dec_deg"),
                "image": frame_id, "source": d.get("source", "stellar"),
                "match_score": d.get("match_score"),
                "timestamp": time.time(),
            }
        else:
            new = {
                "status": "error",
                "error": d.get("error") or d.get("reason") or "solve failed",
                "image": frame_id,
                "timestamp": time.time(),
            }

        with self._state_lock:
            self._gps_status = new
        self.get_logger().info(
            f"[stellar-bridge] {new['status']:9s} frame={frame_id} "
            f"{('lat=%.5f lon=%.5f' % (new['lat'], new['lon'])) if new.get('lat') is not None else new.get('error', '')}"
        )

    def _on_fix(self, msg: NavSatFix):
        # Fallback: keep lat/lon fresh even if cn_status is unavailable.
        if msg.latitude != msg.latitude or msg.longitude != msg.longitude:  # NaN guard
            return
        with self._state_lock:
            if self._gps_status.get("status") in (None, "idle"):
                self._gps_status = {
                    "status": "predicted",
                    "lat": float(msg.latitude), "lon": float(msg.longitude),
                    "source": "stellar", "timestamp": time.time(),
                }

    # ────────────────────────────────────────────────────────────
    # Mission trigger (mirrors navera_web_bridge.set_point_a / trigger_camera_start)
    # ────────────────────────────────────────────────────────────
    def set_point_a(self, pa):
        """Anchor the trajectory at the user-entered Point A.

        Makes A the FIRST position published over /gps_status.json, so the
        stellar view starts at A instead of nothing. The first real /cn/cn_status
        solve replaces this anchor (and _on_fix won't clobber it: not 'idle')."""
        try:
            lat = float(pa["lat"])
            lon = float(pa["lon"])
        except (KeyError, TypeError, ValueError):
            self.get_logger().warn(f"[stellar-bridge] set_mission: bad point_a payload: {pa!r}")
            return
        self._point_a = {"lat": lat, "lon": lon}
        with self._state_lock:
            self._gps_status = {
                "status": "predicted",
                "lat": lat, "lon": lon,
                "source": "point_a", "image": "A",
                "mission_started": True, "timestamp": time.time(),
            }
        self.get_logger().info(
            f"[stellar-bridge] Point A anchored at ({lat:.6f}, {lon:.6f}) — first published position")

    def trigger_camera_start(self):
        # stop/reset (false → pause+rewind) then go (true) — guarantees a frame-1 restart
        self._start_pub.publish(Bool(data=False))
        threading.Timer(0.4, lambda: self._start_pub.publish(Bool(data=True))).start()
        self.get_logger().info("[stellar-bridge] /api/set_mission → camera (rewind then go)")

    # ────────────────────────────────────────────────────────────
    # Tiles (MBTiles, TMS flip-Y)
    # ────────────────────────────────────────────────────────────
    def _get_tile(self, z, x, y):
        if not os.path.exists(self.mbtiles_path):
            return None
        with self._db_lock:
            if self._db_conn is None:
                self._db_conn = sqlite3.connect(self.mbtiles_path, check_same_thread=False)
                self._db_conn.execute("PRAGMA cache_size=8000")
                self._db_conn.execute("PRAGMA temp_store=MEMORY")
            y_tms = (2 ** z - 1) - y
            cur = self._db_conn.cursor()
            cur.execute(
                "SELECT tile_data FROM tiles "
                "WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (z, x, y_tms),
            )
            row = cur.fetchone()
            return bytes(row[0]) if row else None

    def gps_status_json(self):
        with self._state_lock:
            return json.dumps(self._gps_status).encode()

    # ────────────────────────────────────────────────────────────
    # HTTP server
    # ────────────────────────────────────────────────────────────
    def _start_http_server(self):
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                if "404" not in (fmt % args):
                    bridge.get_logger().info(fmt % args)

            def _send(self, code, ctype, body):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code, obj):
                self._send(code, "application/json", json.dumps(obj).encode())

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self):
                parsed = urlparse(self.path)
                path   = parsed.path.rstrip("/")

                if path.startswith("/tiles/"):
                    parts = path.split("/")
                    try:
                        z, x, y = int(parts[2]), int(parts[3]), int(parts[4].split(".")[0])
                    except (IndexError, ValueError):
                        return self._json(400, {"error": "bad tile path"})
                    data = bridge._get_tile(z, x, y)
                    return self._send(200, "image/jpeg", data) if data \
                        else self._json(404, {"error": "tile not found"})

                if path in ("", "/", "/navera.html"):
                    if os.path.exists(bridge.navera_html):
                        with open(bridge.navera_html, "rb") as f:
                            return self._send(200, "text/html; charset=utf-8", f.read())
                    return self._json(404, {"error": "navera.html not found"})

                if path == "/gps_status.json":
                    return self._send(200, "application/json", bridge.gps_status_json())

                if path in ("/api/cache_status", "/api/precollect_progress", "/api/node"):
                    return self._json(200, {"ok": True, "ready": True, "source": "stellar"})

                if path == "/health":
                    return self._json(200, {"ok": True})

                return self._serve_static(path)

            def do_POST(self):
                parsed = urlparse(self.path)
                path   = parsed.path.rstrip("/")
                length = int(self.headers.get("Content-Length", 0))
                body   = self.rfile.read(length) if length else b""

                if path == "/api/set_mission":
                    try:
                        d = json.loads(body or b"{}")
                        if "point_a" in d:
                            bridge.set_point_a(d["point_a"])   # anchor trace at A (publish A first)
                    except Exception:
                        pass
                    bridge.trigger_camera_start()
                    return self._json(200, {"ok": True, "source": "stellar"})

                if path in ("/api/precollect", "/frame", "/api/stellar_gps"):
                    return self._json(200, {"ok": True, "source": "stellar",
                                            "note": "handled by ROS chain"})

                return self._json(404, {"error": f"unknown path: {path}"})

            def _serve_static(self, path):
                rel = path.lstrip("/")
                full = os.path.normpath(os.path.join(bridge.resources_dir, rel))
                if full.startswith(bridge.resources_dir) and os.path.isfile(full):
                    ctype = "text/html" if full.endswith(".html") else \
                            "application/javascript" if full.endswith(".js") else \
                            "text/css" if full.endswith(".css") else \
                            "application/octet-stream"
                    with open(full, "rb") as f:
                        return self._send(200, ctype, f.read())
                return self._json(404, {"error": f"unknown path: /{rel}"})

        try:
            self._httpd = HTTPServer((self.web_host, self.web_port), Handler)
        except Exception as e:
            self.get_logger().error(f"❌ cannot bind {self.web_host}:{self.web_port} — {e}")
            raise
        self._http_thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._http_thread.start()
        self.get_logger().info(f"✅ HTTP server up — open http://localhost:{self.web_port}/")

    def destroy_node(self):
        try:
            if getattr(self, "_httpd", None):
                self._httpd.shutdown()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    """Entry point. Exits cleanly (code 0) on SIGINT and SIGTERM.

    rclpy installs handlers for both signals and shuts the context down itself,
    so spin() returns with the context already closed — an unconditional
    rclpy.shutdown() here would then raise RCLError. Hence the rclpy.ok() guard.
    """
    rclpy.init(args=args)
    node = NaveraStellarBridge()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
