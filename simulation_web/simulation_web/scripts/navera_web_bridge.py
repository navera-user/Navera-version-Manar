#!/usr/bin/env python3
"""navera_web_bridge.py — ROS 2 → web bridge for the NAVERA simulation (day mode).

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
    GET  /mission                → mission.html — mission preparation on the box:
                                   vehicle settings, route (autopilot mission file or
                                   drawn), satellite map generation and activation
    GET  /api/mission/state      → settings, map job, active map
    POST /api/mission/settings   → {changes:{KEY:value}} validated, written to the
                                   settings file (token)
    POST /api/mission/apply      → restart the running NAVERA units (token)
    POST /api/mission/plan       → {route:[[lat,lon],..]} or {mission_text:"..."} (token)
    POST /api/mission/generate | /cancel | /activate  → {id} (token)
    POST /api/mission/save_mission | /delete_mission → {name, route} (token): named routes
    (any other GET)              → static file from the resources/ dir

Run standalone (test the bridge alone, no camera/subscriber needed):
    ros2 run simulation_web navera_web_bridge.py
    curl http://localhost:8181/gps_status.json
    # → {"status": "idle"}   (then "predicted" once /day/day_status flows)
"""
import json
import math
import os
import threading
import time
from urllib.parse import urlparse

import rclpy
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy, HistoryPolicy

from std_msgs.msg import String, Bool
from sensor_msgs.msg import NavSatFix

from navera_msgs.msg import NavStatus, PositionEstimate

from simulation_web.web_common import (BridgeHandler, is_trusted, MBTilesReader, parse_tile_path,
                                       start_server, valid_latlon)
from navera_common.geo import dead_reckon
from navera_common.track import TrackVelocity
from simulation_web import mission_prep

MISSION_FILE_MAX = 512 * 1024       # bytes: an imported autopilot mission file
# NAVERA units restarted by "Apply settings" (try-restart: only those running)
NAVERA_UNITS = ["navera-estimator.service", "navera-imu.service", "navera-insta360.service",
                "navera-pipeline-day.service", "navera-pipeline-night.service", "navera-pipeline-cn.service",
                "navera-output.service"]   # the autopilot switch (NAVERA_FORWARD_DEGRADED)

try:
    from ament_index_python.packages import get_package_share_directory
except Exception:
    get_package_share_directory = None


# Default MBTiles candidates (first existing one wins) if no param given.
# $NAVERA_MBTILES, when set, is tried first.
_MBTILES_CANDIDATES = [p for p in (
    os.environ.get("NAVERA_MBTILES"),
    "/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles",
    "/home/navera/isaac_ros_common/sousse_satellite.mbtiles",
) if p]

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
# Every source navera_estimator can elect (GPS > day > night > celestial).
# The labels are the vocabulary operator.html speaks (its SRC table); an
# unmapped source is served as "UNKNOWN" and logged.
_SOURCE_LABEL = {
    NavStatus.SOURCE_GPS: "GPS",
    NavStatus.SOURCE_DAY_VISION: "VISION",
    NavStatus.SOURCE_NIGHT_VISION: "NIGHT",
    NavStatus.SOURCE_CELESTIAL: "CELESTIAL",
}
_SOURCE_NAME = {"GPS": "GPS", "VISION": "day vision", "NIGHT": "night vision", "CELESTIAL": "celestial"}


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


def _sigma_text(v) -> str:
    """A sigma as the page shows it ("50" for 50.0, "" when unknown), so saved and running compare."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(f):
        return ""
    return f"{f:g}"


class NaveraWebBridge(Node):
    def __init__(self):
        super().__init__("navera_web_bridge")

        # ── Parameters ──────────────────────────────────────────
        self.declare_parameter("status_topic", "/day/day_status")
        self.declare_parameter("fix_topic", "/day/position_estimate")
        self.declare_parameter("mbtiles_path", "")
        self.declare_parameter("web_host", "0.0.0.0")
        self.declare_parameter("web_port", 8181)
        # Shared secret for POST control endpoints; defaults to $NAVERA_WEB_TOKEN.
        # Empty = control disabled (read-only dashboard).
        self.declare_parameter("control_token", os.environ.get("NAVERA_WEB_TOKEN", ""))
        # HTTPS: certificate + key (PEM). Empty = plain HTTP.
        self.declare_parameter("tls_cert", os.environ.get("NAVERA_TLS_CERT", ""))
        self.declare_parameter("tls_key", os.environ.get("NAVERA_TLS_KEY", ""))

        # Arbiter outputs for /operator. Not launch arguments (unlike the
        # pipeline topics above): there is exactly ONE arbiter, so these never
        # vary per pipeline — the day/night/celestial split happens upstream.
        # Dashboard (/) freshness and readiness: a status older than this is
        # served as "stale"; readiness is the localizer's latched handshake.
        declare_float(self, "status_stale_s", 10.0)
        self.declare_parameter("ready_topic", "/day/localizer_ready")
        self.declare_parameter("position_topic", "/navera/position")
        self.declare_parameter("nav_status_topic", "/navera/nav_status")
        # nav_status is the heartbeat (published every estimator tick, ~5 Hz):
        # 2 s ≈ 10 missed ticks → the arbiter is gone, not merely fixless.
        declare_float(self, "nav_status_timeout_s", 2.0)
        # The arbiter publishes each winning measurement ONCE and judges its
        # freshness itself (per-source timeouts, up to 45 s for celestial), so
        # the position is gated by nav_status. This is only a sanity bound
        # against a lost /navera/position message.
        declare_float(self, "position_timeout_s", 60.0)

        status_topic = self.get_parameter("status_topic").value
        fix_topic = self.get_parameter("fix_topic").value
        self.web_host = self.get_parameter("web_host").value
        self.web_port = int(self.get_parameter("web_port").value)
        self._control_token = str(self.get_parameter("control_token").value)
        self._status_stale_s = float(self.get_parameter("status_stale_s").value)
        self._localizer_ready = False

        self._position_topic = self.get_parameter("position_topic").value
        nav_status_topic = self.get_parameter("nav_status_topic").value
        self._nav_status_timeout = float(self.get_parameter("nav_status_timeout_s").value)
        self._position_timeout = float(self.get_parameter("position_timeout_s").value)

        mb = self.get_parameter("mbtiles_path").value
        if not mb:
            mb = next((p for p in _MBTILES_CANDIDATES if os.path.exists(p)), _MBTILES_CANDIDATES[0])
        self.mbtiles_path = mb

        self.resources_dir = _resolve_resources_dir()
        self.navera_html = os.path.join(self.resources_dir, "navera.html")

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
        self._armed, self._armed_rx = None, None   # from vehicle_link (/navera/vehicle/status)
        self._track = TrackVelocity(window_s=10.0, min_span_s=3.0)   # NAVERA's own recent track

        # ── Tile DB (lazy, read-only, thread-safe) ──────────────
        self._tiles = MBTilesReader(self.mbtiles_path, self.get_logger())

        # ── ROS subscriptions: pipeline detail, for the "/" dashboard ──
        self.create_subscription(String,    status_topic, self._on_status, 10)
        # the live cameras' frame verdicts: why frames are not used (too tilted, turning)
        self._frames = []                       # (monotonic, usable, reason) of the last minute
        for ns in ("day", "thermal"):
            self.create_subscription(String, f"/{ns}/frame_meta", self._on_frame_meta, 10)
        ready_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                               durability=DurabilityPolicy.TRANSIENT_LOCAL,
                               history=HistoryPolicy.KEEP_LAST, depth=1)
        self.create_subscription(Bool, self.get_parameter("ready_topic").value,
                                 self._on_ready, ready_qos)
        self.create_subscription(NavSatFix, fix_topic,    self._on_fix,    10)
        self.create_subscription(String, "/navera/vehicle/status", self._on_vehicle_status, 10)
        # the settings navera-output RUNS with (latched by vehicle_output_node), for forwarding_state
        self._output_config = None
        self.create_subscription(String, "/navera/output/config", self._on_output_config, QoSProfile(
            depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        # the operator's start position (page /mission), latched for vision restarted later
        self._pub_start = self.create_publisher(
            PositionEstimate, "/navera/operator/start_position",
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL))

        # ── ROS subscriptions: the arbiter's decision, for "/operator" ──
        # RELIABLE depth 10 — matches navera_estimator's publishers.
        self.create_subscription(
            PositionEstimate, self._position_topic, self._on_position, 10)
        self.create_subscription(
            NavStatus, nav_status_topic, self._on_nav_status, 10)

        # ── Simulation marker: navera_tools/demo_mission.py publishes the true
        # position of its simulated vehicle here. Never published on a live box;
        # while it flows, /operator shows a SIMULATION banner and the truth. ──
        self._sim_truth = None
        self._sim_truth_rx = None
        self.create_subscription(NavSatFix, "/navera/sim/truth", self._on_sim_truth, 10)

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
    def _on_ready(self, msg: Bool):
        self._localizer_ready = bool(msg.data)

    def _on_status(self, msg: String):
        try:
            d = json.loads(msg.data)
        except Exception as e:
            self.get_logger().warn(f"day_status JSON decode failed: {e}")
            return

        frame_id = d.get("frame_id")
        lat, lon = d.get("lat"), d.get("lon")

        if d.get("error"):
            new = {"status": "error", "error": str(d.get("error")), "frame_id": frame_id,
                   "timestamp": time.time()}
        elif d.get("source") == "gps_active":
            # Live GPS is healthy; vision is idle on purpose. Not "GPS lost".
            new = {"status": "gps_active", "frame_id": frame_id, "reason": d.get("reason"),
                   "mission_started": True, "timestamp": time.time()}
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
        first-class answer) from "the arbiter is dead" (no answer at all).
        """
        with self._state_lock:
            self._nav_status = msg
            self._nav_status_rx = time.monotonic()

    def _on_position(self, msg: PositionEstimate):
        """Store the winning estimate.

        Published ONLY while a source contributes, and never as a HELD echo —
        so this cache must never be served on its own. operator_position() gates
        it on nav_status; see the note there.
        """
        with self._state_lock:
            self._position = msg
            self._position_rx = time.monotonic()
            # NAVERA's own track: the in-flight lock knows the vehicle moves even without
            # an autopilot link telling it is armed
            if msg.valid and msg.latitude == msg.latitude:
                self._track.add(time.time(), msg.latitude, msg.longitude, 10.0)

    def set_point_a(self, pa):
        """Anchor the trajectory at the user-entered Point A.

        Makes A the FIRST position published over /gps_status.json, so the web
        trace starts exactly at A instead of at the first CSV row. Real
        /day/day_status frames replace this anchor as soon as they arrive
        (and _on_fix won't clobber it: status is no longer 'idle').
        """
        if not isinstance(pa, dict) or not valid_latlon(pa.get("lat"), pa.get("lon")):
            self.get_logger().warn(f"[bridge] set_mission: bad point_a payload: {pa!r}")
            return False
        lat, lon = float(pa["lat"]), float(pa["lon"])
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
        return True

    def trigger_camera_start(self):
        # stop/reset (false → pause+rewind) then go (true) — guarantees a frame-1 restart
        self._start_pub.publish(Bool(data=False))
        threading.Timer(0.4, lambda: self._start_pub.publish(Bool(data=True))).start()
        self.get_logger().info("[bridge] /api/set_mission → camera (rewind then go)")

    def gps_status_json(self):
        """Dashboard status; served as "stale" (with its age) once it stops
        being updated, so a stalled pipeline never looks live.
        """
        with self._state_lock:
            st = dict(self._gps_status)
        ts = st.get("timestamp")
        if st.get("status") not in (None, "idle") and ts is not None:
            age = time.time() - ts
            st["age_s"] = round(age, 1)
            if age > self._status_stale_s:
                st["last_status"] = st.get("status")
                st["status"] = "stale"
        return json.dumps(st, allow_nan=False).encode()

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

    def _on_sim_truth(self, msg: NavSatFix):
        with self._state_lock:
            self._sim_truth = (float(msg.latitude), float(msg.longitude))
            self._sim_truth_rx = time.monotonic()

    def operator_position(self):
        """operator_decision(), plus the simulation marker when one is running.

        {"simulated": true, "sim_truth": [lat, lon]} is added only while
        /navera/sim/truth flows (a demo_mission run), or when the served
        position itself is labelled simulated. Live data never carries it.
        """
        out = self.operator_decision()
        now = time.monotonic()
        with self._state_lock:
            truth, truth_rx, pos = self._sim_truth, self._sim_truth_rx, self._position
        simulated = False
        if truth is not None and now - truth_rx < 3.0 and valid_latlon(*truth):
            out["sim_truth"] = [truth[0], truth[1]]
            simulated = True
        if out.get("valid") and pos is not None:
            try:
                simulated |= bool(json.loads(pos.details_json or "{}").get("simulated"))
            except (ValueError, AttributeError):
                pass
        if simulated:
            out["simulated"] = True
        out["autopilot_forwarding"] = self.forwarding_state()
        return out

    def _on_output_config(self, msg):
        try:
            d = json.loads(msg.data)
        except (ValueError, AttributeError):
            return
        if isinstance(d, dict):
            self._output_config = d

    def forwarding_state(self):
        """Whether the autopilot gets NAVERA's vision / celestial positions.

        The RUNNING value: what navera-output publishes on /navera/output/config (latched). The saved
        setting (page first, then the environment) is shown only when the output is not heard, or
        beside the running one with pending_restart when it differs (applies at the next restart).
        """
        cur, env = mission_prep.read_settings(), os.environ
        val = cur.get("NAVERA_FORWARD_DEGRADED", env.get("NAVERA_FORWARD_DEGRADED", "false"))
        sigma = cur.get("NAVERA_DEGRADED_SIGMA_M", env.get("NAVERA_DEGRADED_SIGMA_M", ""))
        saved_on = str(val).strip().lower() in ("1", "true", "yes", "on")
        saved = {"on": saved_on, "sigma_m": _sigma_text(sigma) if saved_on else ""}
        run = getattr(self, "_output_config", None)
        if not isinstance(run, dict) or "forward_degraded" not in run:
            return dict(saved, running_known=False)
        run_on = bool(run.get("forward_degraded"))
        out = {"on": run_on, "sigma_m": _sigma_text(run.get("degraded_sigma_m")) if run_on else "",
               "running_known": True}
        if (saved["on"], saved["sigma_m"]) != (out["on"], out["sigma_m"]):
            out["pending_restart"] = True
            out["saved"] = saved
        return out

    def operator_decision(self):
        """The arbiter's decision, rendered as JSON. This method decides NOTHING.

        navera_estimator owns the source hierarchy; it publishes the winner on
        /navera/position and the decision on /navera/nav_status. Here we only
        translate. Three rules, in order:

          1. No nav_status for > nav_status_timeout_s → the arbiter is not
             running. That is NOT NO_FIX, and conflating the two would report
             "no source is usable" when the truth is "nobody is answering".
             Reported as state OFFLINE.
             Measured on the Jetson: after `systemctl restart navera-estimator`
             this clears in ~5-10 s, not in nav_status_timeout_s. The timeout
             only bounds how fast we NOTICE the silence; the rest is ros2 launch
             + rclpy init + DDS discovery. OFFLINE lingering ~10 s after a
             restart is the system working, not a stuck bridge.
          2. state INITIALIZING / NO_FIX → no usable position. The last
             /navera/position is DROPPED, not held. /navera/position is silent
             when no source wins — absence IS the information — and re-showing
             a stale point as live is exactly the lie this chain removes.
          3. state FIX / DEGRADED → serve the last /navera/position, provided it
             comes from the source nav_status declares active.

        The position cache is gated by nav_status, NEVER by its own age alone:
        a cache that can answer on its own is a cache that will eventually
        answer with a ghost.

        Returns {lat, lon, source, valid, state, mode, reason, age_s} when
        usable, else {valid: False, state, reason} with no lat/lon.
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
            return self._with_map({"valid": False, "state": state_name, "reason": status.reason}, status)

        # 3) A winner exists → its latest position must be here. The arbiter
        #    publishes each measurement once and owns freshness; we only check
        #    the position belongs to the source it declares active.
        if (pos is None or pos.source != status.active_source
                or (now - pos_rx) > self._position_timeout):
            return {"valid": False, "state": state_name,
                    "reason": f"{state_name} declared but no matching position on "
                              f"{self._position_topic} yet"}

        lat, lon = float(pos.latitude), float(pos.longitude)
        if not (math.isfinite(lat) and math.isfinite(lon)):
            # Serialization guard, not a policy call: json.dumps emits a bare
            # NaN, which is invalid JSON and throws in the browser's parse.
            return {"valid": False, "state": state_name,
                    "reason": f"{state_name} declared but position is not finite"}

        label = self._source_label(pos.source)
        out = {
            "lat": lat, "lon": lon,
            "source": label,
            "source_name": _SOURCE_NAME.get(label, label.lower()),
            "valid": True,
            "state": state_name,
            "mode": _MODE_NAME.get(pos.mode, "UNKNOWN"),
            "reason": status.reason,
            "age_s": round(now - pos_rx, 1),     # since this measurement was published
        }
        # the stated accuracy, and a vision position carried from its photo's instant to
        # now (as navera_output does for the autopilot): the operator sees where the
        # vehicle is, not where it was 1-2.5 s ago
        cov = list(pos.position_covariance)
        sigma = math.sqrt(max(cov[0], cov[4])) if pos.position_covariance_type and cov[0] > 0 else None
        s = pos.sensor_stamp if (pos.sensor_stamp.sec or pos.sensor_stamp.nanosec) else pos.header.stamp
        measured_age = max(0.0, time.time() - (s.sec + s.nanosec * 1e-9))
        out["measured_age_s"] = round(measured_age, 1)
        if pos.source != PositionEstimate.SOURCE_GPS and 0.0 < measured_age < 30.0:
            v = self._track.velocity(time.time()) if self._track.last_time() else None
            if v is not None and math.hypot(v[0], v[1]) > 0.05:
                carried = dead_reckon(lat, lon, math.degrees(math.atan2(v[0], v[1])) % 360.0,
                                      math.hypot(v[0], v[1]), measured_age)
                if carried:
                    out["measured_lat"], out["measured_lon"] = lat, lon
                    out["lat"], out["lon"] = carried
                    out["carried_s"] = round(measured_age, 1)
                if sigma is not None:
                    sigma += v[2] * measured_age
        if sigma is not None:
            out["accuracy_m"] = round(sigma)
        warn = self._camera_warning()
        if warn:
            out["camera_warning"] = warn
        return self._with_map(out, status)

    @staticmethod
    def _with_map(out, status):
        """The mission-area guard (NavStatus.map_area / map_edge_m): the operator is told when
        the vehicle nears or leaves the edge of the mission's map (day vision has nothing to
        match past it). A translation, like the rest: the estimator decided."""
        flag = getattr(status, "map_area", 0)
        edge = float(getattr(status, "map_edge_m", math.nan))
        if flag and math.isfinite(edge):
            out["map_edge_m"] = round(edge)
            if flag == NavStatus.MAP_AREA_NEAR_EDGE:
                out["map_warning"] = f"{edge:.0f} m from the edge of the map: day vision stops past it"
            elif flag == NavStatus.MAP_AREA_OUTSIDE:
                out["map_warning"] = f"{-edge:.0f} m OUTSIDE the map: no day-vision fix possible"
        return out

    def _on_frame_meta(self, msg):
        try:
            m = json.loads(msg.data)
        except ValueError:
            return
        now = time.monotonic()
        with self._state_lock:
            self._frames = [f for f in self._frames if now - f[0] < 60.0] + \
                [(now, m.get("usable", True) is not False, str(m.get("reason") or ""))]

    def _camera_warning(self):
        """A plain sentence when many of the last minute's frames could not be used."""
        with self._state_lock:
            frames = list(self._frames)
        if len(frames) < 10:
            return None
        bad = [r for _, ok, r in frames if not ok]
        if len(bad) < 0.3 * len(frames):
            return None
        kinds = {"tilted": "the camera is too tilted (fit a gimbal or fly smoother)",
                 "turning": "the vehicle turns too fast for a fixed camera",
                 "attitude": "no attitude (IMU / vehicle link)"}
        why = next((v for k, v in kinds.items() if any(k in r for r in bad)), bad[-1][:80])
        return f"{100 * len(bad) // len(frames)} % of the last minute's frames unusable: {why}"

    # ────────────────────────────────────────────────────────────
    # Mission preparation (page /mission)
    # ────────────────────────────────────────────────────────────
    def _mission_jobs(self):
        if getattr(self, "_jobs", None) is None:
            areas = os.environ.get("NAVERA_AREAS_DIR", "/data/navera/areas")
            self._jobs = mission_prep.AreaJobs(
                areas, self.mbtiles_path, tile_url=os.environ.get("NAVERA_TILE_URL", ""),
                cache=os.environ.get("NAVERA_TILE_CACHE", os.path.join(areas, "downloaded_tiles.mbtiles")),
                log=lambda level, text: (self.get_logger().warn if level in ("warn", "error")
                                         else self.get_logger().info)(text))
        return self._jobs

    def mission_state(self):
        jobs = self._mission_jobs()
        cur = mission_prep.read_settings()
        return dict(settings=cur, keys={k: v[1] for k, v in mission_prep.SETTINGS.items()},
                    site={k: os.environ.get(k, "") for k in mission_prep.SETTINGS},
                    control=bool(self._control_token), **jobs.state())

    def _on_vehicle_status(self, msg):
        try:
            armed = json.loads(msg.data).get("armed")
        except (ValueError, AttributeError):
            return
        self._armed, self._armed_rx = armed, time.monotonic()

    def _in_flight_refusal(self, action="apply"):
        now = time.monotonic()
        armed = self._armed if self._armed_rx is not None and now - self._armed_rx < 5.0 else None
        st = self._nav_status
        state = (st.state if st is not None and self._nav_status_rx is not None
                 and now - self._nav_status_rx < self._nav_status_timeout else None)
        moving = None
        last = self._track.last_time()
        if last is not None and time.time() - last < 10.0:
            v = self._track.velocity(time.time())
            if v is not None:
                moving = math.hypot(v[0], v[1])
        serial = bool((os.environ.get("NAVERA_NMEA_PORT") or "").strip())
        return mission_prep.in_flight_refusal(armed, state, moving, action, serial_gps_output=serial)

    def mission_action(self, action, d):
        jobs = self._mission_jobs()
        if action in ("apply", "activate", "generate"):
            why = self._in_flight_refusal(action)
            if why:
                raise ValueError(f"refused: {why}")
        if action == "settings":
            changes = d.get("changes")
            if not isinstance(changes, dict):
                raise ValueError("changes: object expected")
            valid = mission_prep.validate_settings(changes)
            if any(k in valid for k in mission_prep.IN_FLIGHT_LOCKED):
                why = self._in_flight_refusal("apply")    # what the autopilot is told: never in flight
                if why:
                    raise ValueError(f"refused: {why}")
            merged = {k: v for k, v in mission_prep.read_settings().items()}
            for k, v in valid.items():
                if v is None:
                    merged.pop(k, None)
                else:
                    merged[k] = v
            for k in ("NAVERA_FORWARD_DEGRADED", "NAVERA_DEGRADED_SIGMA_M"):
                if k not in merged and os.environ.get(k):
                    merged[k] = os.environ[k]
            mission_prep.check_forwarding(merged)
            cur = mission_prep.write_settings(valid)
            return {"ok": True, "settings": cur, "restart_needed": True}
        if action == "apply":
            import subprocess
            # allowed by deploy/sudoers/navera-web (exact command)
            r = subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "try-restart"] + NAVERA_UNITS,
                               capture_output=True, text=True, timeout=90)
            if r.returncode != 0:
                raise RuntimeError(f"restart refused: {(r.stderr or r.stdout).strip()[:200]}")
            return {"ok": True}
        if action == "plan":
            if "mission_text" in d:
                route = mission_prep.parse_mission(str(d["mission_text"]))
            else:
                route = d.get("route")
                if not (isinstance(route, list) and len(route) >= 2 and all(
                        isinstance(p, list) and len(p) == 2 and valid_latlon(*p) for p in route)):
                    raise ValueError("route: at least two [lat, lon] points expected")
            plan = jobs.plan(route)
            return {"ok": True, "plan": plan, "points": route}
        if action in ("generate", "activate"):
            aid = str(d.get("id", ""))
            (jobs.start if action == "generate" else jobs.activate)(aid)
            return {"ok": True}
        if action == "cancel":
            return {"ok": True, "cancelled": jobs.cancel()}
        if action == "start_position":
            lat, lon = float(d.get("lat", "nan")), float(d.get("lon", "nan"))
            acc = float(d.get("accuracy_m", "nan"))
            if not valid_latlon(lat, lon):
                raise ValueError("start position: valid latitude and longitude expected")
            if not (math.isfinite(acc) and 5.0 <= acc <= 20000.0):
                raise ValueError("start position accuracy: 5 to 20000 m")
            m = PositionEstimate()
            m.header.stamp = m.sensor_stamp = self.get_clock().now().to_msg()
            m.header.frame_id = "operator"
            m.latitude, m.longitude, m.altitude = lat, lon, math.nan
            m.position_covariance = [acc * acc, 0.0, 0.0, 0.0, acc * acc, 0.0, 0.0, 0.0, 0.0]
            m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
            m.source, m.mode, m.valid = PositionEstimate.SOURCE_EXTERNAL, PositionEstimate.MODE_MEASURED, True
            m.producer, m.reason = "operator", "start position entered on /mission (a search centre, not a fix)"
            self._pub_start.publish(m)
            self.get_logger().warn(f"operator start position {lat:.5f}, {lon:.5f} ±{acc:.0f} m sent to vision")
            return {"ok": True}
        if action == "save_mission":
            return {"ok": True, "missions": jobs.save_mission(d.get("name"), d.get("route"))}
        if action == "delete_mission":
            return {"ok": True, "missions": jobs.delete_mission(d.get("name"))}
        raise ValueError(f"unknown action: {action}")

    # ────────────────────────────────────────────────────────────
    # HTTP server
    # ────────────────────────────────────────────────────────────
    def _start_http_server(self):
        bridge = self

        class Handler(BridgeHandler):
            def do_GET(self):
                path = urlparse(self.path).path.rstrip("/")

                if path.startswith("/tiles/"):
                    zxy = parse_tile_path(path)
                    data = bridge._tiles.get(*zxy) if zxy else None
                    return self.send_body(200, "image/jpeg", data) if data \
                        else self.send_json(404, {"error": "tile not found"})

                if path in ("", "/") and os.environ.get("NAVERA_PRODUCT_MODE") == "1":
                    # the delivered box: the operator view first (the engineering page stays
                    # at /navera.html)
                    self.send_response(302)
                    self.send_header("Location", "/operator")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                if path in ("", "/", "/navera.html"):
                    if os.path.exists(bridge.navera_html):
                        return self.send_file(bridge.navera_html)
                    return self.send_json(404, {"error": "navera.html not found"})

                if path == "/operator":
                    op_html = os.path.join(bridge.resources_dir, "operator.html")
                    if os.path.exists(op_html):
                        return self.send_file(op_html)
                    return self.send_json(404, {"error": "operator.html not found"})

                if path == "/gps_status.json":
                    return self.send_body(200, "application/json", bridge.gps_status_json())

                if path == "/api/operator_position":
                    return self.send_json(200, bridge.operator_position())

                if path == "/flight_log.csv":
                    hdr = ("frame_id,timestamp,image_file,lat,lon,alt_m,heading_deg,"
                           "speed_mps,gps_valid,predicted_lat,predicted_lon,match_score\n")
                    return self.send_body(200, "text/csv", hdr.encode())

                if path in ("/api/cache_status", "/api/precollect_progress"):
                    ready = bridge._localizer_ready
                    return self.send_json(200, {"ok": True, "ready": ready, "pct": 100 if ready else 0})

                if path == "/health":
                    return self.send_json(200, {"ok": True})

                if path == "/mission":
                    return self.send_file(os.path.join(bridge.resources_dir, "mission.html"))

                if path == "/api/mission/state":
                    client = self.client_address[0] if self.client_address else ""
                    state = dict(bridge.mission_state(), trusted=is_trusted(client))
                    return self.send_json(200, state)

                return self.serve_static(bridge.resources_dir, path)

            def do_POST(self):
                path = urlparse(self.path).path.rstrip("/")
                if path.startswith("/api/mission/"):
                    big = path == "/api/mission/plan"
                    d = self.read_control_json(bridge._control_token,
                                               max_body=MISSION_FILE_MAX if big else None)
                    if d is None:
                        return None
                    try:
                        return self.send_json(200, bridge.mission_action(path.rsplit("/", 1)[1], d))
                    except ValueError as e:
                        return self.send_json(400, {"error": str(e)})
                    except RuntimeError as e:
                        return self.send_json(500, {"error": str(e)})
                if path == "/api/set_mission":
                    d = self.read_control_json(bridge._control_token)
                    if d is None:
                        return None
                    if "point_a" in d and not bridge.set_point_a(d["point_a"]):
                        return self.send_json(400, {"error": "point_a must be finite lat/lon in range"})
                    bridge.trigger_camera_start()
                    return self.send_json(200, {"ok": True})
                return self.send_json(404, {"error": f"unknown path: {path}"})

        Handler.bridge = bridge
        try:
            self._httpd = start_server(self.web_host, self.web_port, Handler,
                                       str(self.get_parameter("tls_cert").value),
                                       str(self.get_parameter("tls_key").value))
        except OSError as e:
            self.get_logger().error(f"❌ cannot bind {self.web_host}:{self.web_port} — {e}")
            raise
        self.get_logger().info(f"✅ HTTP{'S' if self.get_parameter('tls_cert').value else ''} "
                               f"server up on port {self.web_port}")

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
