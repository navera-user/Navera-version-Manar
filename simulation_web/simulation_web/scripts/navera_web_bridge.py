#!/usr/bin/env python3
"""
navera_web_bridge.py — ROS 2 → web bridge for the NAVERA simulation (day mode).

This bridge serves TWO surfaces with deliberately different sources:

  "/"          navera.html — the pipeline DEBUG dashboard. Reads /day/day_status
               (score, match, total_ms, frame_id): per-frame algorithm detail
               that exists nowhere else as typed fields. Unchanged.
  "/operator"  operator.html — the NAVIGATION view. Reads the arbiter's decision
               ONLY (/navera/position + /navera/nav_status). It re-implements no
               hierarchy: navera_estimator decides, this bridge renders.

  ROS in:
    /day/day_status         std_msgs/String            (JSON from day_subscriber; "/" only)
    /day/position_estimate  sensor_msgs/NavSatFix      (fallback lat/lon for "/" only)
    /navera/position        navera_msgs/PositionEstimate  (the WINNING estimate; "/operator")
    /navera/nav_status      navera_msgs/NavStatus      (the decision + heartbeat; "/operator")

  HTTP out (single server, default port 8181):
    GET  /                       → navera.html
    GET  /navera.html            → navera.html
    GET  /tiles/{z}/{x}/{y}.png  → MBTiles tile (TMS flip-Y), served as image/jpeg
    GET  /gps_status.json        → latest position {status:"predicted", lat, lon, …}
    GET  /operator               → operator.html (fullscreen operator view)
    GET  /api/operator_position  → the arbiter's decision, rendered:
                                   {lat, lon, source, valid, state, mode, reason}
                                   or {valid:false, state, reason} — see operator_position()
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
import math
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import rclpy
from navera_common.lifecycle import die_with_parent
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from std_msgs.msg import String, Bool
from sensor_msgs.msg import NavSatFix

from navera_msgs.msg import NavStatus, PositionEstimate

try:
    from ament_index_python.packages import get_package_share_directory
except Exception:
    get_package_share_directory = None


# Default MBTiles candidates (first existing one wins) if no param given.
_MBTILES_CANDIDATES = [
    "/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles",
    "/home/navera/isaac_ros_common/sousse_satellite.mbtiles",
]

# ── Enum → display strings for /api/operator_position ──────────────────────
# Rendering only. These tables never gate a decision: the arbiter already made
# it, and re-deriving "is this usable?" here is what created the duplicate
# hierarchy this node just lost.
_STATE_NAME = {
    NavStatus.STATE_INITIALIZING: "INITIALIZING",
    NavStatus.STATE_NO_FIX: "NO_FIX",
    NavStatus.STATE_FIX: "FIX",
    NavStatus.STATE_DEGRADED: "DEGRADED",
}
_MODE_NAME = {
    NavStatus.MODE_MEASURED: "MEASURED",
    NavStatus.MODE_PROPAGATED: "PROPAGATED",
    NavStatus.MODE_HELD: "HELD",
    NavStatus.MODE_REPLAYED: "REPLAYED",
}
# The only two sources the arbiter can elect today: it subscribes to
# /navera/estimate/gps and /navera/estimate/day, and nothing else. The labels
# are the vocabulary operator.html already speaks — its SRC table maps "GPS"
# and "VISION" to a badge and renders every other string as NO FIX, so serving
# "DAY_VISION" would paint NO FIX over a perfectly valid position.
#
# Celestial, inertial and night are deliberately NOT pre-mapped. A source that
# cannot occur cannot be tested, and an entry for it would claim a coverage
# that does not exist. When one of them starts winning, _source_label() says so
# in the log and this table grows then — that warning IS the mechanism.
_SOURCE_LABEL = {
    NavStatus.SOURCE_GPS: "GPS",
    NavStatus.SOURCE_DAY_VISION: "VISION",
}


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

        # Arbiter outputs for /operator. Not launch arguments (unlike the
        # pipeline topics above): there is exactly ONE arbiter, so these never
        # vary per pipeline — the day/night/celestial split happens upstream.
        self.declare_parameter("position_topic", "/navera/position")
        self.declare_parameter("nav_status_topic", "/navera/nav_status")
        # nav_status is the heartbeat (published every estimator tick, ~5 Hz):
        # 2 s ≈ 10 missed ticks → the arbiter is gone, not merely fixless.
        self.declare_parameter("nav_status_timeout_s", 2.0)
        # A position accompanying a FIX/DEGRADED tick arrives with it. Older
        # than 1 s (~5 ticks) while the state claims a winner = messages lost.
        self.declare_parameter("position_timeout_s", 1.0)

        status_topic = self.get_parameter("status_topic").value
        fix_topic    = self.get_parameter("fix_topic").value
        self.web_host = self.get_parameter("web_host").value
        self.web_port = int(self.get_parameter("web_port").value)

        self._position_topic     = self.get_parameter("position_topic").value
        nav_status_topic         = self.get_parameter("nav_status_topic").value
        self._nav_status_timeout = float(self.get_parameter("nav_status_timeout_s").value)
        self._position_timeout   = float(self.get_parameter("position_timeout_s").value)

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
        # Arbiter snapshot for /operator. Receipt instants are time.monotonic(),
        # NOT header stamps: what we need to know is "is the estimator still
        # talking to us", which is a property of our own clock and immune to
        # cross-process skew.
        self._nav_status = None      # last NavStatus; None → never heard
        self._nav_status_rx = None
        self._position = None        # last winning PositionEstimate
        self._position_rx = None

        # ── Tile DB (lazy, thread-safe) ─────────────────────────
        self._db_conn = None
        self._db_lock = threading.Lock()

        # ── ROS subscriptions: pipeline detail, for the "/" dashboard ──
        self.create_subscription(String,    status_topic, self._on_status, 10)
        self.create_subscription(NavSatFix, fix_topic,    self._on_fix,    10)

        # ── ROS subscriptions: the arbiter's decision, for "/operator" ──
        # RELIABLE depth 10 — matches navera_estimator's publishers.
        self.create_subscription(
            PositionEstimate, self._position_topic, self._on_position, 10)
        self.create_subscription(
            NavStatus, nav_status_topic, self._on_nav_status, 10)

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
        self.get_logger().info(f"  status topic : {status_topic}   (dashboard /)")
        self.get_logger().info(f"  fix topic    : {fix_topic}   (dashboard /)")
        self.get_logger().info(f"  position     : {self._position_topic}   (/operator)")
        self.get_logger().info(f"  nav_status   : {nav_status_topic}   (/operator)")
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

    def _on_nav_status(self, msg: NavStatus):
        """Store the arbiter's decisional summary (every estimator tick, ~5 Hz).

        This is the heartbeat of /operator. Its ABSENCE is information — it is
        what separates "the arbiter says no source is usable" (NO_FIX, a
        first-class answer) from "the arbiter is dead" (no answer at all)."""
        with self._state_lock:
            self._nav_status = msg
            self._nav_status_rx = time.monotonic()

    def _on_position(self, msg: PositionEstimate):
        """Store the winning estimate.

        Published ONLY while a source contributes, and never as a HELD echo —
        so this cache must never be served on its own. operator_position() gates
        it on nav_status; see the note there."""
        with self._state_lock:
            self._position = msg
            self._position_rx = time.monotonic()

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

    def _source_label(self, source: int) -> str:
        """Enum → the string operator.html expects. Unknown → explicit "UNKNOWN".

        An unmapped source is never guessed at and never silently dropped: it is
        labelled UNKNOWN and logged, so a new source announces itself as a
        warning in the log instead of as a wrong badge in the operator's face.
        """
        label = _SOURCE_LABEL.get(source)
        if label is None:
            self.get_logger().warn(
                f"[bridge] nav_status.active_source={source} has no operator label — "
                f"serving 'UNKNOWN' (operator.html will render NO FIX). Add it to "
                f"_SOURCE_LABEL and to the front's SRC table.",
                throttle_duration_sec=10.0)
            return "UNKNOWN"
        return label

    def operator_position(self):
        """The arbiter's decision, rendered as JSON. This method decides NOTHING.

        navera_estimator owns the source hierarchy; it publishes the winner on
        /navera/position and the decision on /navera/nav_status. Here we only
        translate. Three rules, in order:

          1. No nav_status for > nav_status_timeout_s → the arbiter is not
             running. That is NOT NO_FIX, and conflating the two would report
             "no source is usable" when the truth is "nobody is answering".
             Reported as state OFFLINE.
          2. state INITIALIZING / NO_FIX → no usable position. The last
             /navera/position is DROPPED, not held. /navera/position is silent
             when no source wins — absence IS the information — and re-showing
             a stale point as live is exactly the lie this chain removes.
          3. state FIX / DEGRADED → serve the last /navera/position, provided it
             is fresh.

        The position cache is gated by nav_status, NEVER by its own age alone:
        a cache that can answer on its own is a cache that will eventually
        answer with a ghost.

        Returns {lat, lon, source, valid, state, mode, reason} when usable, else
        {valid: False, state, reason} with no lat/lon. state/mode/reason are
        additive: operator.html reads only valid/lat/lon/source and ignores them.
        """
        now = time.monotonic()
        with self._state_lock:
            status, status_rx = self._nav_status, self._nav_status_rx
            pos, pos_rx = self._position, self._position_rx

        # 1) Is the arbiter alive at all?
        if status is None or (now - status_rx) > self._nav_status_timeout:
            return {"valid": False, "state": "OFFLINE",
                    "reason": "no nav_status from navera_estimator"}

        state_name = _STATE_NAME.get(status.state, "UNKNOWN")

        # 2) The arbiter says no source is usable. A first-class answer.
        if status.state not in (NavStatus.STATE_FIX, NavStatus.STATE_DEGRADED):
            return {"valid": False, "state": state_name, "reason": status.reason}

        # 3) A winner exists → its position must be here, and fresh.
        if pos is None or (now - pos_rx) > self._position_timeout:
            return {"valid": False, "state": state_name,
                    "reason": f"{state_name} declared but no fresh position on "
                              f"{self._position_topic}"}

        lat, lon = float(pos.latitude), float(pos.longitude)
        if not (math.isfinite(lat) and math.isfinite(lon)):
            # Serialization guard, not a policy call: json.dumps emits a bare
            # NaN, which is invalid JSON and throws in the browser's parse.
            return {"valid": False, "state": state_name,
                    "reason": f"{state_name} declared but position is not finite"}

        return {
            "lat": lat, "lon": lon,
            "source": self._source_label(status.active_source),
            "valid": True,
            "state": state_name,
            "mode": _MODE_NAME.get(status.active_mode, "UNKNOWN"),
            "reason": status.reason,
        }

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
    """Entry point. Exits cleanly (code 0) on SIGINT and SIGTERM.

    rclpy installs handlers for both signals and shuts the context down itself,
    so spin() returns with the context already closed — an unconditional
    rclpy.shutdown() here would then raise RCLError. Hence the rclpy.ok() guard.
    """
    die_with_parent()  # orphan guard: die if our launcher/systemd unit is killed
    rclpy.init(args=args)
    node = NaveraWebBridge()
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
