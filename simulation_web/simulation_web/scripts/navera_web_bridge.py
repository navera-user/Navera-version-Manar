#!/usr/bin/env python3
"""
navera_web_bridge.py — ROS 2 → web bridge for the NAVERA simulation (day mode).

Subscribes to the day localization output and exposes it over HTTP in the exact
shape navera.html already polls, so the browser marker moves in real time from
the ROS chain (camera_pkg → day_subscriber → /day/position_estimate):

  ROS in:
    /day/day_status         std_msgs/String   (JSON from day_subscriber)
    /day/position_estimate  sensor_msgs/NavSatFix  (fallback lat/lon)
    /navera/sensors/gps_fix sensor_msgs/NavSatFix  (real GPS; wins over vision when valid)

  HTTP out (single server, default port 8181):
    GET  /                       → navera.html
    GET  /navera.html            → navera.html
    GET  /tiles/{z}/{x}/{y}.png  → MBTiles tile (TMS flip-Y), served as image/jpeg
    GET  /gps_status.json        → latest position {status:"predicted", lat, lon, …}
    GET  /operator               → operator.html (fullscreen operator view)
    GET  /api/operator_position  → {lat, lon, source:"GPS"|"VISION", valid} (GPS→vision hierarchy)
    GET  /flight_log.csv         → minimal header (keeps navera.html pollCsv happy)
    GET/POST /api/set_mission    → store Point A (map centring)
    GET  /api/cache_status, /api/precollect_progress, POST /api/precollect → benign stubs
    GET  /health                 → {ok:true}
    (any other GET)              → static file from the resources/ dir

Run standalone (test the bridge alone, no camera/subscriber needed):
    ros2 run simulation_web navera_web_bridge.py
    curl http://localhost:8181/gps_status.json
    # → {"status": "idle"}   (then "predicted" once /day/day_status flows)
"""
import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from std_msgs.msg import String, Bool
from sensor_msgs.msg import NavSatFix

try:
    from ament_index_python.packages import get_package_share_directory
except Exception:
    get_package_share_directory = None


# Default MBTiles candidates (first existing one wins) if no param given.
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
    # Source layout: .../simulation_web/simulation_web/scripts/  → ../resources
    here = os.path.dirname(os.path.realpath(__file__))
    return os.path.normpath(os.path.join(here, "..", "resources"))


class NaveraWebBridge(Node):
    def __init__(self):
        super().__init__("navera_web_bridge")

        # ── Parameters ──────────────────────────────────────────
        self.declare_parameter("status_topic", "/day/day_status")
        self.declare_parameter("fix_topic", "/day/position_estimate")
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
        self._gps_fix = None   # latest VALID real GPS fix {lat, lon}; None → fall back to vision

        # ── Tile DB (lazy, thread-safe) ─────────────────────────
        self._db_conn = None
        self._db_lock = threading.Lock()

        # ── ROS subscriptions ───────────────────────────────────
        self.create_subscription(String,    status_topic, self._on_status, 10)
        self.create_subscription(NavSatFix, fix_topic,    self._on_fix,    10)

        # ── Real GPS fix (source hierarchy: GPS wins over vision) ──
        self.declare_parameter("gps_fix_topic", "/navera/sensors/gps_fix")
        gps_fix_topic = self.get_parameter("gps_fix_topic").value
        self.create_subscription(NavSatFix, gps_fix_topic, self._on_gps_fix, 10)

        # ── camera start/pause trigger (Option A) ──
        self.declare_parameter("start_topic", "/day/camera/start")
        start_topic = self.get_parameter("start_topic").value
        cmd_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             history=HistoryPolicy.KEEP_LAST, depth=1)
        self._start_pub = self.create_publisher(Bool, start_topic, cmd_qos)

        # ── Banner ──────────────────────────────────────────────
        self.get_logger().info("=" * 60)
        self.get_logger().info("  NAVERA web bridge — ROS → web (day mode)")
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
    # ROS callbacks → update shared gps_status
    # ────────────────────────────────────────────────────────────
    def _on_status(self, msg: String):
        try:
            d = json.loads(msg.data)
        except Exception as e:
            self.get_logger().warn(f"day_status JSON decode failed: {e}")
            return

        frame_id = d.get("frame_id")
        lat, lon = d.get("lat"), d.get("lon")

        if d.get("error"):
            new = {"status": "error", "error": str(d.get("error")), "frame_id": frame_id}
        elif d.get("success") and lat is not None and lon is not None:
            new = {
                "status": "predicted",
                "lat": float(lat), "lon": float(lon),
                "score": d.get("score"), "match": d.get("match"),
                "frame_id": frame_id, "total_ms": d.get("total_ms"),
                "source": d.get("source", "day_visual"),
                "mission_started": True,
                "timestamp": time.time(),
            }
        else:
            # Rejected / low-confidence: report searching but keep last good fix visible.
            new = {"status": "searching", "frame_id": frame_id,
                   "reason": d.get("reason"), "mission_started": True,
                   "timestamp": time.time()}
            with self._state_lock:
                prev = self._gps_status
            if prev.get("lat") is not None:
                new["lat"], new["lon"] = prev["lat"], prev["lon"]

        with self._state_lock:
            self._gps_status = new
        self.get_logger().info(
            f"[bridge] {new['status']:9s} frame={frame_id} "
            f"{('lat=%.5f lon=%.5f' % (new['lat'], new['lon'])) if new.get('lat') is not None else ''}"
        )

    def _on_fix(self, msg: NavSatFix):
        # Fallback: keep lat/lon fresh even if day_status is unavailable.
        if msg.latitude != msg.latitude or msg.longitude != msg.longitude:  # NaN guard
            return
        with self._state_lock:
            if self._gps_status.get("status") in (None, "idle"):
                self._gps_status = {
                    "status": "predicted",
                    "lat": float(msg.latitude), "lon": float(msg.longitude),
                    "mission_started": True, "timestamp": time.time(),
                }

    def _on_gps_fix(self, msg: NavSatFix):
        """Store the latest VALID real GPS fix in self._gps_fix, else clear it to None.

        Valid = the receiver reports a fix (status.status >= 0, i.e. not
        STATUS_NO_FIX = -1) AND lat/lon are finite and not the (0, 0) null island.
        When the fix is invalid, self._gps_fix is reset to None so that
        operator_position() falls back to the vision source."""
        lat, lon = msg.latitude, msg.longitude
        has_fix = msg.status.status >= 0                 # -1 == NavSatStatus.STATUS_NO_FIX
        finite  = (lat == lat) and (lon == lon)          # NaN guard
        nonzero = not (lat == 0.0 and lon == 0.0)        # reject (0, 0) placeholder
        with self._state_lock:
            if has_fix and finite and nonzero:
                self._gps_fix = {"lat": float(lat), "lon": float(lon)}
            else:
                self._gps_fix = None

    def set_point_a(self, pa):
        """Anchor the trajectory at the user-entered Point A.

        Makes A the FIRST position published over /gps_status.json, so the web
        trace starts exactly at A instead of at the first CSV row. Real
        /day/day_status frames replace this anchor as soon as they arrive
        (and _on_fix won't clobber it: status is no longer 'idle')."""
        try:
            lat = float(pa["lat"])
            lon = float(pa["lon"])
        except (KeyError, TypeError, ValueError):
            self.get_logger().warn(f"[bridge] set_mission: bad point_a payload: {pa!r}")
            return
        self._point_a = {"lat": lat, "lon": lon}
        with self._state_lock:
            self._gps_status = {
                "status": "predicted",
                "lat": lat, "lon": lon,
                "source": "point_a",     # frontend treats this as the start anchor, not a match
                "match": "POINT_A", "score": 1.0,
                "frame_id": "A",
                "mission_started": True,
                "timestamp": time.time(),
            }
        self.get_logger().info(
            f"[bridge] Point A anchored at ({lat:.6f}, {lon:.6f}) — first published position")

    def trigger_camera_start(self):
        # stop/reset (false → pause+rewind) then go (true) — guarantees a frame-1 restart
        self._start_pub.publish(Bool(data=False))
        threading.Timer(0.4, lambda: self._start_pub.publish(Bool(data=True))).start()
        self.get_logger().info("[bridge] /api/set_mission → camera (rewind then go)")

    # ────────────────────────────────────────────────────────────
    # Tiles (MBTiles, TMS flip-Y) — same logic as day_node.py
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

    def operator_position(self):
        """Position for the operator view, with source hierarchy GPS → VISION → none.

        Returns a dict {lat, lon, source, valid}:
          1. GPS   — if a valid GPS fix is available (source="GPS").
          2. VISION— else the current day-localization fix (source="VISION").
          3. none  — else {"valid": False}.

        self._gps_fix holds the latest VALID real GPS fix (from the
        /navera/sensors/gps_fix subscription, via _on_gps_fix); it is None when
        no valid fix is available, so the hierarchy falls back to vision.
        """
        # 1) GPS — latest valid real fix (None → fall through to vision).
        gps = getattr(self, "_gps_fix", None)
        if gps and gps.get("lat") is not None and gps.get("lon") is not None:
            return {"lat": float(gps["lat"]), "lon": float(gps["lon"]),
                    "source": "GPS", "valid": True}
        # 2) VISION — current day-localization fix (predicted or searching keeps last good).
        with self._state_lock:
            st = dict(self._gps_status)
        if st.get("status") in ("predicted", "searching") \
                and st.get("lat") is not None and st.get("lon") is not None:
            return {"lat": float(st["lat"]), "lon": float(st["lon"]),
                    "source": "VISION", "valid": True}
        # 3) No fix.
        return {"valid": False}

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

                if path == "/flight_log.csv":
                    hdr = ("frame_id,timestamp,image_file,lat,lon,alt_m,heading_deg,"
                           "speed_mps,gps_valid,predicted_lat,predicted_lon,match_score\n")
                    return self._send(200, "text/csv", hdr.encode())

                if path in ("/api/cache_status", "/api/precollect_progress"):
                    return self._json(200, {"ok": True, "ready": True, "pct": 100})

                if path == "/health":
                    return self._json(200, {"ok": True})

                if path == "/operator":
                    op_html = os.path.join(bridge.resources_dir, "operator.html")
                    if os.path.exists(op_html):
                        with open(op_html, "rb") as f:
                            return self._send(200, "text/html; charset=utf-8", f.read())
                    return self._json(404, {"error": "operator.html not found"})

                if path == "/api/operator_position":
                    return self._json(200, bridge.operator_position())

                # Static fallback from resources/ (leaflet assets, etc.)
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
                    return self._json(200, {"ok": True})

                if path in ("/api/precollect", "/frame"):
                    return self._json(200, {"ok": True, "note": "handled by ROS chain"})

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
    rclpy.init(args=args)
    node = NaveraWebBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
