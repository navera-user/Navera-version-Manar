#!/usr/bin/env python3
"""
day_subscriber.py — NAVERA day_pkg, visual-localization subscriber.

Consumes the DAY camera stream published by camera_pkg and runs the existing
DayLocalizer (DINOv2 retrieval) on each frame:

    /day/image_raw    sensor_msgs/Image   (bgr8, BEST_EFFORT)
    /day/frame_meta   std_msgs/String     (JSON from camera_publisher.py, RELIABLE)

and emits:

    /day/position_estimate  sensor_msgs/NavSatFix
    /day/day_status         std_msgs/String   (JSON diagnostics)

This node ONLY wires camera_pkg → DayLocalizer. The localization logic in
day_localizer.py is used as-is through its public API
(DayLocalizer().load_models() / load_or_build_cache() / predict()).

Examples:
  ros2 launch day_pkg day_subscriber.launch.py
  ros2 launch day_pkg day_subscriber.launch.py conf_threshold:=0.80
  ros2 launch day_pkg day_subscriber.launch.py image_topic:=/day/image_raw \
                                               meta_topic:=/day/frame_meta
"""
import json
import logging
import math
import threading
import time

import cv2

import rclpy
from navera_common import state_store
from navera_common.geo import is_finite_latlon
from navera_common.track import TrackVelocity
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from navera_common.pairing import FramePairer, exposure_stamp, stamp_ns
from navera_common.prior import GpsPrior
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from sensor_msgs.msg import Image, NavSatFix, NavSatStatus, Range
from std_msgs.msg import String, Int32, Bool
from cv_bridge import CvBridge
from navera_msgs.msg import NavStatus, PositionEstimate

# Existing localization logic (UNMODIFIED user code).
# DayLocalizer().predict(bgr_array, threshold=...) -> dict
from day_pkg.nodes.day_localizer import IMAGES_DIR, DayLocalizer, haversine_m
from day_pkg.fix_sigma import day_fix_sigma_m
from day_pkg.frame_odometry import FrameOdometry
from day_pkg.local_matcher import LocalMatcher
from day_pkg.vision_nav import VisionNavigator, _en, _move, kinematic_margin_m

# ── A priori spatial GPS-denied (fix matching cross-source) ─────────────────
# Sur une frame sans GPS, on restreint la recherche DINOv2 à un CERCLE autour du
# dernier point retenu (anchor), puis on prend le top-1 DINOv2 dans ce cercle.
# Rayon (cahier des charges) :
#     R = max(footprint_m × FOOTPRINT_MULT, altitude_m × ALTITUDE_MULT)
# où footprint_m = GSD_M_PER_PX × grand côté de la frame (≈1486 m pour 1536×730).
# R_MAX_M BORNE ce rayon théorique à la ZONE DE MATCHING FIABLE validée
# empiriquement au harnais (R≈400→600 m ⇒ médiane d'erreur ~564→611 m ; au-delà
# le cercle englobe trop de tuiles et l'erreur remonte vers ~3485 m).
GSD_M_PER_PX   = 0.967    # mesuré au diagnostic : tuile z17 = 248 m / 256 px
FOOTPRINT_MULT = 3.0
ALTITUDE_MULT  = 2.0
R_MIN_M        = 400.0    # plancher : ~1 pas inter-frame (frames à ~480 m)
ANCHOR_MEMORY_S = 300.0  # a saved position older than this is not reused after a restart
R_MAX_M        = 600.0    # PLAFOND décisif : garde R dans la bande validée

# ── source contract for navera_estimator (additive; see step 4) ──────────────
# Internal src label → honest provenance mode. This is the whole point of the
# mode field: a REPLAYED CSV point can NEVER pass itself off as a DINOv2
# MEASURED recognition, and a dead-reckon bridge is PROPAGATED, not measured.
_DAY_MODE_BY_SRC = {
    "gps":          PositionEstimate.MODE_REPLAYED,    # CSV ground truth, not a measurement
    "predicted":    PositionEstimate.MODE_MEASURED,    # real DINOv2 inference (global/gate)
    "visual_match": PositionEstimate.MODE_MEASURED,    # real DINOv2 inference (spatial a-priori)
    "dead_reckon":  PositionEstimate.MODE_PROPAGATED,  # heading/speed bridge from anchor
    "local_match":  PositionEstimate.MODE_MEASURED,    # local features vs the map (local_matcher)
}
_DAY_MODEL_BY_SRC = {
    "gps":          "csv_ground_truth",
    "predicted":    "dinov2_vits14+gem",
    "visual_match": "dinov2_vits14+gem",
    "dead_reckon":  "dead_reckon",
    "local_match":  "sift_local+ransac",
}


class DaySubscriber(Node):
    def __init__(self):
        super().__init__("day_subscriber")

        # ── Parameters ──────────────────────────────────────────
        declare_float(self, "conf_threshold", 0.75)
        self.declare_parameter("image_topic", "/day/image_raw")
        self.declare_parameter("meta_topic", "/day/frame_meta")
        self.declare_parameter("fix_topic", "/day/position_estimate")
        self.declare_parameter("status_topic", "/day/day_status")
        self.declare_parameter("estimate_topic", "/navera/estimate/day")  # typed source contract
        # Live GPS, used as the search prior: while it is valid the anchor follows
        # it and inference is skipped; when it drops, vision starts from its last fix.
        self.declare_parameter("gps_topic", "/navera/position")
        declare_float(self, "gps_prior_timeout_s", 2.0)
        # Mission start/stop gate of the camera: a stop (rewind) resets tracking.
        # Test flights only: run vision even while GPS is valid, to measure it
        # against GPS. GPS only seeds the track once (a prior re-centred on the
        # truth every frame would make the measured error meaningless).
        self.declare_parameter("shadow_mode", False)
        self.declare_parameter("start_topic", "/day/camera/start")
        self.declare_parameter("done_topic", "/day/frame_done")   # back-pressure ack (Int32 frame_id)
        self.declare_parameter("ready_topic", "/day/localizer_ready")  # handshake: modèle chargé
        # ── track filter (anchor, spatial prior, dead-reckoning) ──
        self.declare_parameter("antijump_enabled", True)      # false = raw per-frame output, no anchor
        # After this many consecutive frames without an accepted match, the anchor
        # is dropped and the next frame searches globally: a wrong anchor must not
        # confine the search forever.
        self.declare_parameter("max_consecutive_rejects", 3)
        # Dead-reckoning from the last accepted fix is only published for this long.
        # without a match, the last measured position is carried along the velocity of the
        # last measured fixes (turned by the IMU heading change) this long, while its stated
        # uncertainty stays under dead_reckon_max_sigma_m
        declare_float(self, "max_dead_reckon_s", 120.0)
        declare_float(self, "dead_reckon_max_sigma_m", 500.0)
        # unseen acceleration allowed for in the stated accuracy (1/2 a t^2). 0.25: outages
        # replayed on the real camera campaign's fixes (2026-10-19, 1606 per gap length, true
        # heading change given): still 100 % within 3 sigma at 5-60 s on a constant 900 m turn
        # and on a straight track; the 60 s sigma on a straight track 1078 -> 628 m (error 15 m
        # median, 55 m p95: the heading and velocity terms, not this one, keep it wide)
        declare_float(self, "dead_reckon_accel_mps2", 0.25)
        # Whole-map search (no prior). Measured on labelled frames: 12 % within
        # 300 m, and the similarity score does not separate good matches from
        # bad ones (docs/VALIDATION_STATUS.md). Off: without a prior (GPS fix or
        # tracked match) day vision reports no position instead of a guess.
        self.declare_parameter("allow_global_search", False)
        # Motion gate: a match farther from the last retained position than the
        # vehicle can travel (max_speed_mps x elapsed + gate_margin_m) is rejected.
        # The margin covers the tile quantisation (a match is a tile centre, tiles
        # ~250 m). Without it the track jumped 554 m in 1 s and stayed on wrong
        # tiles (0.4-1.1 km) in the mission simulator.
        declare_float(self, "max_speed_mps", 30.0)
        declare_float(self, "gate_margin_m", 250.0)
        # Matching method. "local": local features vs the satellite map around the prior
        # (local_matcher, SIFT; needs the frame altitude and camera_hfov_deg to know the
        # frame's scale — without them, falls back to "retrieval"); "learned": the same with
        # DISK + LightGlue (learned_matcher, GPU; SIFT as its fallback) — 28-29/33 real aerial
        # frames vs SIFT's 23-24/33 with the shipped 8 inliers, 0 wrong (docs/VALIDATION_STATUS.md,
        # re-measured 2026-10-20); "auto": "learned" when its models
        # load (GPU, kornia, weights), else "local"; "retrieval": DINOv2 tile retrieval
        # (the former method, ~440 m median).
        self.declare_parameter("matcher", "auto")
        # Between map matches (bench campaign 2026-10-06, day_pkg/vision_nav.py): the search
        # circle is k sigma of the carried position, never under local_min_radius_m; a fix
        # far from the prediction (gate_k sigma) is rejected — one with strong_inliers only beyond
        # strong_gate_k_sigma (it was believed at any distance: 2026-10-19 bench, 100-150 inlier
        # matches 270-650 m off were forwarded) — unless the next fix agrees with it,
        # one whose inliers cover < min_inlier_spread of the frame (with < 30 inliers) or at most
        # 1/8 of it (with < 50) too;
        # after height_retry_after failures in a row, the frame is also tried 20 % lower
        # and 25 % higher (a stale height makes every match fail).
        declare_float(self, "local_min_radius_m", 80.0)
        declare_float(self, "search_k_sigma", 3.0)
        declare_float(self, "gate_k_sigma", 3.0)
        self.declare_parameter("strong_inliers", 100)
        declare_float(self, "strong_gate_k_sigma", 6.0)
        declare_float(self, "min_inlier_spread", 0.25)
        self.declare_parameter("height_retry_after", 3)
        declare_float(self, "camera_hfov_deg", float("nan"))   # day camera horizontal field of view
        # wrong places measured at <= 5 inliers on real aerial frames; correct ones 3-73
        self.declare_parameter("local_min_inliers", 8)
        declare_float(self, "local_scale_tol", 0.15)
        # widest scale window when the frame altitude is uncertain (frame_meta altitude_sigma_m)
        declare_float(self, "local_scale_tol_max", 0.35)
        declare_float(self, "local_heading_tol_deg", 20.0)
        # an IMU without magnetometer (its yaw drifts tens of degrees, or is unknown): the learned
        # matcher searches the heading (every 30 deg) when the IMU's fails — simulation
        # 2026-10-19, 300 m: heading 45 deg wrong 0/30 -> 30/30 located, 0 wrong
        self.declare_parameter("local_heading_search", False)
        # a height measured by a match is trusted only from a strong match confirmed by
        # the next one (a wrong match must not set the altitude the next frames are judged by)
        self.declare_parameter("altitude_min_inliers", 20)
        # heights above ground measured by local matches (the camera uses them)
        self.declare_parameter("vision_altitude_topic", "/navera/vision/altitude_agl")
        # while GPS is trusted, match a frame this often around the GPS position: an
        # INDEPENDENT position for the estimator's GPS cross-check (a slow spoof drifts
        # GPS away from it), and the height above ground known when GPS is lost. 0 = off.
        declare_float(self, "gps_check_period_s", 2.0)
        declare_float(self, "gps_check_radius_m", 600.0)   # covers a GPS drifted this far
        # Stated accuracy (1 sigma, m) of a local match: day_pkg.fix_sigma.day_fix_sigma_m (the
        # matcher's inlier-class sigma, a floor, the frame-time and attitude terms), measured on
        # NAVERA's camera on the screen bench (2026-10-19: 99.2 % within 3 sigma, median 10.6 m).
        # local_sigma_m is only the fallback for a result without its own sigma.
        declare_float(self, "local_sigma_m", 30.0)
        declare_float(self, "local_sigma_floor_m", 5.0)
        declare_float(self, "frame_time_sigma_s", 0.05)
        declare_float(self, "attitude_sigma_deg", 0.5)
        # Local matching keeps its last position when frames fail (uniform ground, blur) and
        # widens the search by max_speed_mps x the time since its last match, up to this
        # radius, instead of dropping it after max_consecutive_rejects (a retrieval-era rule).
        declare_float(self, "local_max_radius_m", 600.0)   # wider: memory and 30-60 s frames (campaign 3)

        self.conf_threshold = float(self.get_parameter("conf_threshold").value)
        image_topic   = self.get_parameter("image_topic").value
        meta_topic    = self.get_parameter("meta_topic").value
        fix_topic     = self.get_parameter("fix_topic").value
        status_topic  = self.get_parameter("status_topic").value
        done_topic    = self.get_parameter("done_topic").value
        ready_topic   = self.get_parameter("ready_topic").value
        self.antijump_enabled    = bool(self.get_parameter("antijump_enabled").value)
        self.max_consecutive_rejects = int(self.get_parameter("max_consecutive_rejects").value)
        self.max_dead_reckon_s   = float(self.get_parameter("max_dead_reckon_s").value)
        self.dr_max_sigma_m      = float(self.get_parameter("dead_reckon_max_sigma_m").value)
        self.track = TrackVelocity(accel_mps2=float(self.get_parameter("dead_reckon_accel_mps2").value))
        self._track_heading = None             # frame heading (IMU) at the last measured fix
        self._dr_sigma = None
        self._anchor_sigma = None               # 1-sigma (m) of the anchor position, None: unknown
        p_ = lambda n: self.get_parameter(n).value               # noqa: E731
        self.local_min_radius_m, self.search_k = float(p_("local_min_radius_m")), float(p_("search_k_sigma"))
        self.gate_k, self.strong_inliers = float(p_("gate_k_sigma")), int(p_("strong_inliers"))
        self.strong_gate_k = float(p_("strong_gate_k_sigma"))
        self.min_spread, self.height_retry_after = float(p_("min_inlier_spread")), int(p_("height_retry_after"))
        # the map's offset from the ground (registration, camera boresight), learned from the
        # GPS-check matches while GPS is good and removed from the fixes after its loss
        self.map_bias = VisionNavigator()
        # frame-to-frame visual odometry: the displacement through gaps in map matching
        self.vo = FrameOdometry()
        self._vo_step = None
        self._doubted = None                    # (t, lat, lon, sigma): a fix a gate doubted
        # the position carried frame by frame since the last fix (lat, lon, t, heading,
        # ve, vn, sigma): one turn from the fix's heading to the present folded a 180 deg
        # turn or a lap into a small one (bench campaign 4: 3-3.8 km off on the coast)
        self._carry = None
        # the trusted GPS by its measurement time: a bias sample compares a frame's fix with
        # the GPS at that frame's instant (the latest GPS is v x delay off along the track)
        from navera_common.sensor_history import History
        self._gps_hist = History(maxlen=600, max_gap_s=1.5)
        self.allow_global_search = bool(self.get_parameter("allow_global_search").value)
        self.max_speed_mps = float(self.get_parameter("max_speed_mps").value)
        self.gate_margin_m = float(self.get_parameter("gate_margin_m").value)

        # ── State ───────────────────────────────────────────────
        self.bridge        = CvBridge()
        self._busy_lock    = threading.Lock()
        # without frames at all (camera failed, unplugged), the measured track is still
        # carried on (1 Hz) — the case dead-reckoning matters most for
        self._last_frame = (time.time(), {})
        self.create_timer(1.0, self._dead_reckon_without_frames)
        self._pairer       = FramePairer()   # image/meta matched on the image stamp
        self._frame_count   = 0
        self._success_count = 0
        self._skip_count    = 0
        self._reject_count  = 0
        # anchor = last RETAINED position (GPS truth OR filtered output). dt source.
        self._anchor_lat  = None
        self._anchor_lon  = None
        self._anchor_time = None   # wall-clock (time.time()) of last retained frame
        self._last_measured_time = None   # wall-clock of the last MEASURED/known fix
        self._rejects_in_row     = 0
        self._anchor_saved_at    = 0.0
        # restarted (in flight): start from the last position this node was sure of, if
        # recent — the search circle grows with its age like after any gap
        saved = state_store.load("day_anchor", ANCHOR_MEMORY_S)
        if saved is not None and is_finite_latlon(saved.get("lat"), saved.get("lon")):
            self._anchor_lat, self._anchor_lon = float(saved["lat"]), float(saved["lon"])
            self._anchor_time = self._last_measured_time = float(saved["saved_at"])
            self.get_logger().warn(f"[day] restart: last known position {time.time() - saved['saved_at']:.0f} s "
                                   f"ago reused as the search centre")

        # ── Banner (PRE-load) ──────────────────────────────────
        self.get_logger().info("=" * 60)
        self.get_logger().info("  NAVERA day_pkg — DAY visual-localization subscriber")
        self.get_logger().info(f"  image topic     : {image_topic}")
        self.get_logger().info(f"  meta  topic     : {meta_topic}")
        self.get_logger().info(f"  fix   topic     : {fix_topic}")
        self.get_logger().info(f"  status topic    : {status_topic}")
        self.get_logger().info(f"  conf_threshold  : {self.conf_threshold:.2f}")
        self.get_logger().info("  policy          : strictly-serial, back-pressure (acks frame_done)")
        self.get_logger().info("=" * 60)

        # ── Load DayLocalizer model + descriptor cache (blocking) ─
        self.get_logger().info("⏳ Loading DayLocalizer (DINOv2)…")
        self.localizer = DayLocalizer()
        self.localizer.load_models()
        self.localizer.load_or_build_cache()
        self.localizer.warm_up()
        self.get_logger().info("✅ DayLocalizer ready, awaiting frames…")
        self.matcher_mode = str(self.get_parameter("matcher").value)
        self.camera_hfov_deg = float(self.get_parameter("camera_hfov_deg").value)
        self.local_sigma_m = float(self.get_parameter("local_sigma_m").value)
        self.local_sigma_floor_m = float(self.get_parameter("local_sigma_floor_m").value)
        self.frame_time_sigma_s = float(self.get_parameter("frame_time_sigma_s").value)
        self.attitude_sigma_deg = float(self.get_parameter("attitude_sigma_deg").value)
        self._last_fix_sigma = self.local_sigma_m
        self.local_max_radius_m = float(self.get_parameter("local_max_radius_m").value)
        self.local_scale_tol_max = float(self.get_parameter("local_scale_tol_max").value)
        self.local_heading_tol_deg = float(self.get_parameter("local_heading_tol_deg").value)
        self.heading_search = bool(self.get_parameter("local_heading_search").value)
        self.alt_min_inliers = int(self.get_parameter("altitude_min_inliers").value)
        self._alt_candidate = None             # (height, time) of the last strong match
        self._check_fix = None                 # (lat, lon, time) of the last GPS-check match
        self._gps_was_trusted = False
        self.calib_period_s = float(self.get_parameter("gps_check_period_s").value)
        self.calib_radius_m = float(self.get_parameter("gps_check_radius_m").value)
        self._last_calib = 0.0
        self.local = None
        kw = dict(min_inliers=int(self.get_parameter("local_min_inliers").value),
                  scale_tol=float(self.get_parameter("local_scale_tol").value))
        if self.matcher_mode in ("learned", "auto"):
            try:
                from day_pkg.learned_matcher import LearnedMatcher
                self.local = LearnedMatcher(IMAGES_DIR, **kw)
                self.get_logger().info(f"matcher: DISK + LightGlue vs the map (GPU), SIFT as fallback, "
                                       f"camera_hfov_deg={self.camera_hfov_deg}")
            except Exception as e:                     # noqa: BLE001 — no GPU / kornia / weights
                if self.matcher_mode == "learned":
                    raise
                self.get_logger().warn(f"learned matcher unavailable ({e}): SIFT local matching instead")
            self.matcher_mode = "local"
        if self.matcher_mode == "local" and self.local is None:
            self.local = LocalMatcher(IMAGES_DIR, **kw)
            self.get_logger().info(
                f"matcher: local features vs the map ({'GPU' if self.local.torch else 'CPU'} matching), "
                f"camera_hfov_deg={self.camera_hfov_deg}"
                + ("" if math.isfinite(self.camera_hfov_deg) else
                   " — UNKNOWN: the frame scale cannot be computed, retrieval is used instead"))

        # A signal (SIGINT/SIGTERM) during the multi-second DINOv2 load makes rclpy
        # close the context; the create_publisher/create_subscription calls below
        # would then raise "rcl node's context is invalid" (RCLError, exit 1). Abort
        # construction cleanly — main() maps ExternalShutdownException to exit 0.
        if not rclpy.ok():
            raise ExternalShutdownException()

        # ── QoS per topic (must match camera_pkg publisher) ────
        # RELIABLE — MUST match the camera_publisher image publisher (also RELIABLE).
        # A RELIABLE subscriber + BEST_EFFORT publisher would NOT connect.
        image_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )
        meta_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        # ── Publishers ──────────────────────────────────────────
        self.pub_fix    = self.create_publisher(NavSatFix, fix_topic,    10)
        self.pub_status = self.create_publisher(String,    status_topic, 10)
        self.pub_vision_alt = self.create_publisher(Range, self.get_parameter("vision_altitude_topic").value, 10)
        # Additive: typed per-source estimate for navera_estimator. Same RELIABLE
        # depth-10 class as the fix/status topics. /day/* topics are UNTOUCHED.
        estimate_topic = self.get_parameter("estimate_topic").value
        self.pub_est   = self.create_publisher(PositionEstimate, estimate_topic, 10)
        # back-pressure ack: published once per frame (RELIABLE, matches camera ack sub)
        done_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST, depth=1,
        )
        self.pub_done   = self.create_publisher(Int32, done_topic, done_qos)

        # ── Subscribers ─────────────────────────────────────────
        self.sub_image = self.create_subscription(
            Image, image_topic, self.on_image, image_qos
        )
        self.sub_meta = self.create_subscription(
            String, meta_topic, self.on_meta, meta_qos
        )
        self._gps_prior = GpsPrior(float(self.get_parameter("gps_prior_timeout_s").value))
        # The arbiter's decision: GPS is the prior only while it is the source in use.
        self.create_subscription(NavStatus, "/navera/nav_status", self.on_nav_status, 10)
        self.shadow_mode = bool(self.get_parameter("shadow_mode").value)
        if self.shadow_mode:
            self.get_logger().warn("SHADOW MODE: vision runs while GPS is valid (test flights)")
        self.sub_gps = self.create_subscription(
            PositionEstimate, self.get_parameter("gps_topic").value, self.on_gps, 10)
        # a start position entered by the operator (page /mission) when there is no GPS:
        # where to search first — never published as a position (latched: heard on restart)
        self.create_subscription(
            PositionEstimate, "/navera/operator/start_position", self.on_operator_position,
            QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        # Same latched QoS as the camera's gate (TRANSIENT_LOCAL, depth 1).
        start_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                               durability=DurabilityPolicy.TRANSIENT_LOCAL,
                               history=HistoryPolicy.KEEP_LAST, depth=1)
        self.sub_start = self.create_subscription(
            Bool, self.get_parameter("start_topic").value, self.on_start_cmd, start_qos)

        # ── Handshake "ready" ───────────────────────────────────
        # Le modèle est chargé ET les subscriptions sont en place → on signale au
        # camera_publisher qu'il peut envoyer la frame 1. Latché (TRANSIENT_LOCAL)
        # pour que le publisher reçoive le signal même s'il s'abonne après nous.
        ready_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST, depth=1,
        )
        self.pub_ready = self.create_publisher(Bool, ready_topic, ready_qos)
        self.pub_ready.publish(Bool(data=True))
        self.get_logger().info(f"📣 localizer_ready=True publié sur {ready_topic} (latché)")

    # ────────────────────────────────────────────────────────────
    # Callbacks
    # ────────────────────────────────────────────────────────────
    def on_image(self, msg: Image):
        try:
            img = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as e:
            self.get_logger().warn(f"cv_bridge decode failed: {e}")
            img = None                      # still paired, so the frame is acked
        pair = self._pairer.add_image(stamp_ns(msg.header.stamp), img)
        if pair is not None:
            self._dispatch(*pair)

    def on_nav_status(self, msg: NavStatus):
        self._gps_prior.arbiter(msg.active_source == NavStatus.SOURCE_GPS
                                and msg.state in (NavStatus.STATE_FIX, NavStatus.STATE_DEGRADED))

    def on_gps(self, msg: PositionEstimate):
        """GPS position vetted by the arbiter → it becomes the anchor (the prior for GPS loss).

        Read from the arbiter's output (/navera/position, GPS source only): a GPS
        message the arbiter refuses (spoofed, implausible) never reaches it. Taken
        from the raw GPS, the first spoofed fix of an attack became the search
        centre, 2 km off (mission simulator). Any other source is ignored.
        In shadow mode it only seeds a missing anchor."""
        if msg.source != PositionEstimate.SOURCE_GPS:
            return
        if self._gps_prior.update(msg.latitude, msg.longitude, msg.valid,
                                  msg.mode == PositionEstimate.MODE_MEASURED):
            st = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
            if st > 0:
                self._gps_hist.add(st, (float(msg.latitude), float(msg.longitude)))
            if self.shadow_mode and self._anchor_lat is not None:
                return
            self._anchor_lat, self._anchor_lon = msg.latitude, msg.longitude
            self._anchor_time = time.time()
            self._last_measured_time = self._anchor_time
            self._rejects_in_row = 0
            self._remember_anchor()
            cov = list(msg.position_covariance)
            self._anchor_sigma = math.sqrt(max(cov[0], cov[4])) if cov[0] > 0 else 5.0
            self.track.add(self._anchor_time, msg.latitude, msg.longitude, self._anchor_sigma)

    def on_operator_position(self, msg: PositionEstimate):
        """The operator's start position: the search centre while no GPS is trusted, the
        search circle as wide as its stated accuracy (the circle grows with time since)."""
        if self._gps_prior.fresh() is not None or not is_finite_latlon(msg.latitude, msg.longitude):
            return
        acc = math.sqrt(max(msg.position_covariance[0], msg.position_covariance[4], 1.0))
        now = time.time()
        self._anchor_lat, self._anchor_lon, self._anchor_time = msg.latitude, msg.longitude, now
        self._anchor_sigma = acc
        # the search circle grows by max_speed x the time since the last measurement:
        # start it as wide as the operator's accuracy
        self._last_measured_time = now - acc / max(self.max_speed_mps, 1.0)
        self.track.reset()
        self.get_logger().warn(f"[day] operator start position {msg.latitude:.5f}, {msg.longitude:.5f} "
                               f"(±{acc:.0f} m): searching there (no GPS)")

    def on_start_cmd(self, msg: Bool):
        """Mission stop/rewind → forget the previous run's track (the next run
        starts from GPS, or reports no position until it has a prior)."""
        if msg.data or self._gps_prior.fresh() is not None:
            return
        self._anchor_lat = self._anchor_lon = self._anchor_time = None
        self._last_measured_time = None
        self.track.reset()
        state_store.save("day_anchor", {"lat": None, "lon": None})   # forgotten too
        self._rejects_in_row = 0
        self.get_logger().info("[day] mission rewind — tracking state reset")

    def on_meta(self, msg: String):
        try:
            meta = json.loads(msg.data)
        except ValueError as e:
            self.get_logger().warn(f"meta JSON decode failed: {e}")
            return
        if not isinstance(meta, dict):
            self.get_logger().warn(f"meta is not a JSON object: {msg.data[:80]!r}")
            return
        pair = self._pairer.add_meta(meta)
        if pair is not None:
            self._dispatch(*pair)

    # ────────────────────────────────────────────────────────────
    # Pair + dispatch
    # ────────────────────────────────────────────────────────────
    def _dispatch(self, img, meta):
        """Handle one image/meta pair (matched on the image stamp)."""
        seq_id = meta.get("frame_id", "?")
        if img is None:
            self.get_logger().error(
                f"[day] frame={seq_id}: image missing or undecodable — acked, not localized")
            self._publish_done(seq_id)
            return
        self._frame_count += 1
        self._last_frame = (time.time(), meta)
        self.get_logger().info(
            f"[day] 📷 paired frame={seq_id}  "
            f"shape={img.shape}  gps_valid={meta.get('gps_valid')}"
        )

        # Strictly serial — back-pressure (camera waits for our ack) guarantees a single
        # frame is ever in flight, so we process inline and NEVER skip/drop a frame.
        # The busy_lock stays as a defensive guard against a future multi-threaded executor.
        with self._busy_lock:
            self._process_frame(seq_id, img, meta)

    def _process_frame(self, seq_id, img, meta):
        try:
            # GPS connu (CSV lat/lon réelles) → naviguer vers CE point, SANS prédire.
            # (la paire img/meta est déjà consommée dans _dispatch ; le finally
            #  ci-dessous release _busy_lock → la frame suivante est traitée normalement)
            if meta.get("gps_valid") and meta.get("lat") is not None and meta.get("lon") is not None:
                self._publish_known(seq_id, meta)
                return
            # A live frame the camera could not use (e.g. too tilted): say why, no inference.
            if meta.get("usable") is False:
                why = meta.get("reason") or "frame marked unusable by the camera"
                if self._gps_prior.fresh() is None and \
                        self._dead_reckon(self.get_clock().now().to_msg(), seq_id, meta, {}, 0.0, why):
                    return
                self.pub_status.publish(String(data=json.dumps({
                    "frame_id": seq_id, "success": False, "source": "unusable", "reason": why})))
                return
            # GPS just stopped being trusted: if our own last independent fix disagrees with
            # the last GPS position (a spoofed GPS dragged the anchor away), start from ours
            trusted = self._gps_prior.fresh() is not None
            if self._gps_was_trusted and not trusted:
                self._handover_from_gps()
            self._gps_was_trusted = trusted
            # Live GPS healthy → it is the position source; no inference needed.
            if trusted and not self.shadow_mode:
                self.pub_status.publish(String(data=json.dumps({
                    "frame_id": seq_id, "success": False, "source": "gps_active",
                    "anchor": [self._anchor_lat, self._anchor_lon]
                    if self._anchor_lat is not None else None,
                    "reason": "GPS valid — vision idle, tracking GPS as prior"})))
                self._prewarm(img, meta)
                self._calibrate_altitude(seq_id, img, meta)
                return
            center, R = self._spatial_window(img, meta)
            if center is not None:
                self.get_logger().info(f"[day] 🔎 localizing frame={seq_id}… (cercle R={R:.0f}m autour de l'anchor)")
            elif not self.allow_global_search:
                self._publish_no_fix(self.get_clock().now().to_msg(), seq_id, meta,
                                     {"frame_id": seq_id}, 0.0,
                                     "no position prior (waiting for a GPS fix); "
                                     "whole-map search disabled — not reliable")
                return
            else:
                self.get_logger().info(f"[day] 🔎 localizing frame={seq_id}… (pas d'anchor → recherche globale)")
            mpp, why_not = self._frame_m_per_px(img, meta)
            self._vo_step = None
            if mpp is not None:
                ns = meta.get("image_stamp_ns")
                t_img = int(ns) / 1e9 if ns else time.time()
                v = self.track.velocity(time.time())
                pred = None
                if v is not None and self.vo._prev is not None:
                    dt = t_img - self.vo._prev[3]
                    pred = (v[0] * dt, v[1] * dt)
                self._vo_step = self.vo.step(img, self._heading_for_match(meta), mpp, t_img, pred)
                if self._vo_step is not None and v is not None:
                    # odometry that disagrees with the velocity the map fixes measured is not
                    # used (phase correlation can lock on what does not move in the image)
                    de, dn, dt, _ = self._vo_step
                    dv = math.hypot(de / dt - v[0], dn / dt - v[1])
                    if dv > max(3.0 * v[2], 0.3 * math.hypot(v[0], v[1]), 3.0):
                        self._vo_step = None
            if self.local is not None and center is not None and mpp is not None:
                # after height_retry_after failures, 20 % lower and 25 % higher too
                factors = [1.0] + ([0.8, 1.25] if self._rejects_in_row + 1 >= self.height_retry_after else [])
                for f in factors:
                    result = self.local.locate(img, center, R, mpp * f, scale_tol=self._scale_tol(meta),
                                               heading_deg=self._heading_for_match(meta),
                                               heading_tol_deg=self.local_heading_tol_deg, hfov_deg=self._hfov(meta),
                                               **self._heading_search_kw())
                    if result.get("accepted"):
                        break
                sc = float(result.get("scale_residual") or 1.0)
                if result.get("accepted") and abs(sc - 1.0) > 0.05:
                    # the fitted scale answers only ~half of a height error (campaign 2: slope
                    # 0.45-0.6): match again at the corrected height, keep it if it holds
                    again = self.local.locate(img, center, R, mpp * f * sc, scale_tol=self._scale_tol(meta),
                                              heading_deg=self._heading_for_match(meta),
                                              heading_tol_deg=self.local_heading_tol_deg, hfov_deg=self._hfov(meta),
                                              **self._heading_search_kw())
                    if again.get("accepted") and int(again.get("inliers") or 0) >= int(result.get("inliers") or 0) // 2:
                        result, f = again, f * sc
                result["_frame_shape"], result["_frame_mpp"] = img.shape, mpp * f
                result["_height_factor"] = f
            elif self.local is not None:
                # retrieval (~440 m median on real frames) is no substitute for a local match
                # that cannot run: published, its positions were 1.1 km off (sim, near the ground)
                self._publish_no_fix(self.get_clock().now().to_msg(), seq_id, meta, {"frame_id": seq_id}, 0.0,
                                     why_not or "no prior: local matching needs a search centre")
                return
            else:
                result = self.localizer.predict(img, threshold=self.conf_threshold,
                                                center=center, radius_m=R)
            result["search_center"] = list(center) if center is not None else None
            self._log_top5(seq_id, result)
            self._publish_result(seq_id, meta, result)
        except Exception as e:
            self.get_logger().error(f"[day] localizer error frame={seq_id}: {e}")
        finally:
            # ALWAYS ack — known / accepted / rejected / error — so the camera never
            # hangs waiting for a frame whose outcome was "rejected" or "error".
            self._publish_done(seq_id)

    def _log_top5(self, seq_id, result):
        """Diagnostic correctif #1 : top-5 des matches (DINOv2) pour les frames sans GPS."""
        top5 = result.get("top5")
        if not top5:
            return
        self.get_logger().info(f"[day] 🔝 TOP-5 frame={seq_id} (retrieval=DINOv2)")
        for c in top5:
            self.get_logger().info(
                f"        #{c['rank']} idx={c['index']:4d} {c['image']:<28} "
                f"dino={c['dino']:.3f} "
                f"lat={c['lat']:+.5f} lon={c['lon']:+.5f}"
            )

    def _publish_done(self, seq_id):
        try:
            fid = int(seq_id)
        except (TypeError, ValueError):
            fid = -1
        self.pub_done.publish(Int32(data=fid))
        self.get_logger().info(f"[day] ✓ done frame={seq_id} → ack ({self.pub_done.topic_name})")

    def _publish_known(self, seq_id, meta):
        """GPS connu (vérité terrain) : publie la position du CSV, sans prédiction."""
        now = self.get_clock().now().to_msg()
        lat = float(meta["lat"]); lon = float(meta["lon"])
        status = {
            "frame_id": seq_id, "success": True,
            "lat": lat, "lon": lon,
            "score": 1.0, "match": None, "total_ms": 0.0,
            "source": "gps", "error": None,
        }
        self.pub_status.publish(String(data=json.dumps(status)))
        fix = NavSatFix()
        fix.header.stamp    = now
        fix.header.frame_id = "day_camera_link"
        fix.status.status   = NavSatStatus.STATUS_FIX
        fix.status.service  = NavSatStatus.SERVICE_GPS
        fix.latitude        = lat
        fix.longitude       = lon
        _alt = meta.get("altitude_m")
        fix.altitude        = float(_alt) if _alt is not None else math.nan
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.pub_fix.publish(fix)
        self._success_count += 1
        # frame 11 (1ère prédiction) prendra CE point GPS (frame 10) comme référence
        self._anchor_lat, self._anchor_lon, self._anchor_time = lat, lon, time.time()
        self._anchor_sigma = None
        self._last_measured_time = self._anchor_time
        self._rejects_in_row = 0
        # Additive contract: CSV truth → MODE_REPLAYED (never a DINOv2 measurement).
        self._publish_estimate(now, seq_id, "gps", lat, lon, meta, score=1.0,
                               details={"src": "gps", "score": 1.0, "note": "CSV ground truth"})
        self.get_logger().info(
            f"[day] 🛰 KNOWN frame={seq_id}  lat={lat:+.5f}  lon={lon:+.5f}  (GPS truth)"
        )

    # ────────────────────────────────────────────────────────────
    # Anti-jump helpers
    # ────────────────────────────────────────────────────────────
    PREFETCH_AHEAD_S = 8.0          # how far ahead (in time) the map features are prepared

    def _prefetch_ahead(self, lat, lon, t_now, img_shape=None, mpp=None):
        """From the last two matches, prepare the map features where the vehicle will be."""
        prev = (self._anchor_lat, self._anchor_lon, self._anchor_time)
        alat, alon = lat, lon
        if None not in prev and t_now > prev[2]:
            dt = t_now - prev[2]
            k = self.PREFETCH_AHEAD_S / dt
            alat, alon = lat + (lat - prev[0]) * k, lon + (lon - prev[1]) * k
        margin = 0.5 * math.hypot(*img_shape[:2]) * mpp if img_shape and mpp else 300.0
        self.local.tiles.prefetch(alat, alon, R_MAX_M + margin)

    def _handover_from_gps(self):
        """At GPS loss or refusal: the anchor is the last trusted GPS position, unless a
        recent independent vision fix disagrees with it by more than 100 m (the GPS was
        drifting: spoofing) — then the search starts from where vision last saw us."""
        c = self._check_fix
        if c is None or self._anchor_lat is None or time.time() - c[2] > 10.0:
            return
        d = haversine_m(self._anchor_lat, self._anchor_lon, c[0], c[1])
        if d > 100.0:
            self.get_logger().warn(f"[day] GPS lost/refused: starting from the last vision fix, "
                                   f"{d:.0f} m from the last GPS position (GPS was drifting)")
            self._anchor_lat, self._anchor_lon, self._anchor_time = c[0], c[1], c[2]
            self._anchor_sigma = self.local_sigma_m
            self._last_measured_time = c[2]
            self.track.reset()                      # its GPS points were the spoofed ones
            self.track.add(c[2], c[0], c[1], self.local_sigma_m)

    def _calibrate_altitude(self, seq_id, img, meta):
        """GPS trusted: every gps_check_period_s, match this frame within gps_check_radius_m
        of the GPS position. A match is published as an independent day-vision estimate
        (the estimator never prefers it to a trusted GPS, but cross-checks GPS with it:
        a slowly spoofed GPS drifts away and is refused) and gives the height above
        ground. The tracking state (anchor) is not touched: GPS stays the prior."""
        if self.local is None or self.calib_period_s <= 0 or time.time() - self._last_calib < self.calib_period_s:
            return
        prior = self._gps_prior.fresh()
        mpp, _ = self._frame_m_per_px(img, meta)
        if prior is None or mpp is None:
            return
        self._last_calib = time.time()
        res = self.local.locate(img, prior, self.calib_radius_m, mpp, scale_tol=self._scale_tol(meta),
                                heading_deg=self._heading_for_match(meta),
                                heading_tol_deg=self.local_heading_tol_deg, hfov_deg=self._hfov(meta))
        self.get_logger().info(
            f"[day] GPS check frame={seq_id}: " + (f"vision {haversine_m(prior[0], prior[1], res['predicted_lat'], res['predicted_lon']):.0f} m from GPS "
                                                  f"({res.get('inliers')} inliers)" if res.get("accepted") else f"no match ({res.get('reason')})"))
        if res.get("accepted"):
            self._check_fix = (float(res["predicted_lat"]), float(res["predicted_lon"]), time.time())
            ns = meta.get("image_stamp_ns")
            g = self._gps_hist.at(int(ns) / 1e9) if ns else None
            if g is not None:                       # no GPS at the frame's instant: no sample
                self.map_bias.bias_sample(self._check_fix[:2], g, self._heading_for_match(meta))
            st = {}
            self._publish_vision_altitude(meta, res, st)
            self._publish_estimate(exposure_stamp(meta, self.get_clock().now().to_msg()), seq_id, "local_match",
                                   float(res["predicted_lat"]), float(res["predicted_lon"]), meta,
                                   score=float(res.get("score") or 0.0),
                                   details={"src": "local_match", "gps_check": True,
                                            "inliers": res.get("inliers"), "sigma_m": self._fix_sigma(res, meta)})
            self.get_logger().info(f"[day] height above ground calibrated while GPS is good: "
                                   f"{st.get('altitude_measured_m')} m (frame said {meta.get('altitude_m')} m, "
                                   f"{res.get('inliers')} inliers)", throttle_duration_sec=30.0)

    def _prewarm(self, img, meta):
        """While GPS is trusted, vision is idle: compute the map features around the current
        position now, so that the first frames after a GPS loss find them ready (computed
        on demand, the tiles of a whole search circle take seconds — stale positions).
        Only the tiles not yet cached cost anything; a frame's time budget is respected."""
        if self.local is None or self._anchor_lat is None:
            return
        mpp, _ = self._frame_m_per_px(img, meta)
        if mpp is None:
            return
        _, R = self._spatial_window(img, meta)
        margin = 0.5 * math.hypot(*img.shape[:2]) * mpp
        self.local.tiles.prefetch(self._anchor_lat, self._anchor_lon, R + margin)

    def _heading_search_kw(self) -> dict:
        """locate() keywords: the heading search when enabled and the matcher has it."""
        if self.heading_search and hasattr(self.local, "heading_search_deg"):
            return {"heading_search": True}
        return {}

    def _hfov(self, meta):
        """Field of view of this frame: the live camera states it (undistorted image),
        else the camera_hfov_deg parameter."""
        try:
            v = float(meta.get("camera_hfov_deg"))
            if 1.0 < v < 179.0:
                return v
        except (TypeError, ValueError):
            pass
        return self.camera_hfov_deg

    def _scale_tol(self, meta):
        """Accepted scale error: the configured one, widened to twice the frame's relative
        altitude uncertainty (e.g. GPS altitude over unknown terrain), capped."""
        tol = self.local.scale_tol
        try:
            rel = 2.0 * float(meta.get("altitude_sigma_m")) / float(meta.get("altitude_m"))
            if math.isfinite(rel):
                tol = min(max(tol, rel), self.local_scale_tol_max)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
        return tol

    def _frame_m_per_px(self, img, meta):
        """(metres per frame pixel, None) from the frame altitude and the camera's field of
        view, or (None, why) when the scale of this frame cannot be known."""
        hfov = self._hfov(meta)
        if not math.isfinite(hfov) or not 1.0 < hfov < 179.0:
            return None, "camera_hfov_deg unknown"
        try:
            alt = float(meta.get("altitude_m"))
        except (TypeError, ValueError):
            return None, "frame altitude unknown"
        if not (math.isfinite(alt) and alt > 5.0):
            return None, "frame altitude unknown or on the ground"
        return LocalMatcher.frame_m_per_px(img.shape[1], alt, hfov), None

    def _spatial_window(self, img, meta):
        """Cercle de recherche pour une frame GPS-denied.
        Centre = dernier point retenu (anchor). Retourne (None, None) si aucun anchor.

        Formule (cahier des charges, gardée EXPLICITE) :
            footprint_m = GSD_M_PER_PX × max(largeur, hauteur) de la frame   (≈1486 m)
            R_theorique = max(footprint_m × FOOTPRINT_MULT, altitude_m × ALTITUDE_MULT)
            R           = clamp(R_theorique, R_MIN_M, R_MAX_M)

        R_MAX_M borne le rayon théorique à la zone de matching fiable validée au
        harnais (cf. constantes en tête de fichier) : sans ce plafond, R≈4458 m
        engloberait presque tout le dataset et l'erreur remonterait vers ~3485 m.
        """
        if self._anchor_lat is None or self._anchor_lon is None:
            return None, None
        h, w        = img.shape[:2]
        footprint_m = GSD_M_PER_PX * max(w, h)
        altitude_m  = float(meta.get("altitude_m") or 0.0)
        R_theorique = max(footprint_m * FOOTPRINT_MULT, altitude_m * ALTITUDE_MULT)
        R           = min(max(R_theorique, R_MIN_M), R_MAX_M)
        if self.local is not None:
            pred = self._predicted(meta)
            if pred is not None:
                # the carried position and k sigma of it: the window follows the uncertainty
                # (a lost vehicle is searched for wider, a tracked one cheaply)
                return (pred[0], pred[1]), min(max(self.search_k * pred[2], self.local_min_radius_m),
                                               self.local_max_radius_m)
            if self._last_measured_time is not None:
                # the vehicle may have gone this far since the last match: search that far
                grown = R + self.max_speed_mps * max(0.0, time.time() - self._last_measured_time)
                R = min(max(R, grown), max(R, self.local_max_radius_m))
        return (self._anchor_lat, self._anchor_lon), R

    def _predicted(self, meta):
        """(lat, lon, sigma_m) of the last measured fix carried to now along the track
        (turned with the IMU heading), or None."""
        t_last = self.track.last_time()
        if t_last is None:
            return None
        h = self._heading_for_match(meta)
        t = self._frame_time(meta)
        c = self._carry
        if c is not None and c[2] >= t_last:
            lat, lon, tc, hc, ve, vn, sig = c
            dt = max(0.0, t - tc)
            turn = (h - hc + 180.0) % 360.0 - 180.0 if h is not None and hc is not None else 0.0
            steps = max(1, int(abs(turn) / 5.0))
            de = dn = 0.0
            for i in range(steps):
                a = math.radians(turn * (i + 0.5) / steps)
                de += (ve * math.cos(a) + vn * math.sin(a)) * dt / steps
                dn += (-ve * math.sin(a) + vn * math.cos(a)) * dt / steps
            v = self.track.velocity(t_last + 1e-3)
            sig_v = v[2] if v is not None else 3.0
            speed = math.hypot(ve, vn)
            p = _move((lat, lon), de, dn)
            return (p[0], p[1], sig + sig_v * dt + math.radians(5.0) * speed * dt + 0.25 * dt * dt
                    + 0.5 * abs(math.radians(turn)) * speed * dt)
        turn = 0.0
        if h is not None and self._track_heading is not None:
            turn = (h - self._track_heading + 180.0) % 360.0 - 180.0
        return self.track.propagate(t, turn)

    def _set_carry(self, lat, lon, t, meta, sigma):
        """Remember the carried position and its velocity turned to this frame's heading."""
        v = self.track.velocity(t)
        if v is None:
            self._carry = None
            return
        h = self._heading_for_match(meta)
        hc = self._carry[3] if self._carry is not None else self._track_heading
        ve, vn = (self._carry[4], self._carry[5]) if self._carry is not None else (v[0], v[1])
        if h is not None and hc is not None:
            a = math.radians((h - hc + 180.0) % 360.0 - 180.0)
            ve, vn = ve * math.cos(a) + vn * math.sin(a), -ve * math.sin(a) + vn * math.cos(a)
        self._carry = (lat, lon, t, h, ve, vn, sigma)

    @staticmethod
    def _frame_time(meta) -> float:
        """The frame's exposure instant (its stamp), else now: a position carried to the
        processing instant but stamped at the exposure lands v x delay ahead (simulator
        plane, 2026-10-07: dead-reckoned frames 31-48 m ahead at 42 m/s)."""
        ns = meta.get("image_stamp_ns")
        return int(ns) / 1e9 if ns else time.time()

    def _dead_reckon_without_frames(self):
        t_frame, meta = self._last_frame
        if time.time() - t_frame < 2.5 or self._gps_prior.fresh() is not None:
            return
        if not self._busy_lock.acquire(blocking=False):
            return                                          # a frame is being processed
        try:
            m = dict(meta)
            m.pop("image_stamp_ns", None)                   # this is no frame: stamped now
            self._dead_reckon(self.get_clock().now().to_msg(), m.get("frame_id", -1), m, {}, 0.0,
                              f"no camera frame for {time.time() - t_frame:.0f} s")
        finally:
            self._busy_lock.release()

    def _dead_reckon(self, now, seq_id, meta, status, score, why) -> bool:
        """No measurement this frame: publish the last measured position carried along the
        measured track (PROPAGATED, with its growing stated uncertainty). False, with
        self._dr_why set, when it cannot be done honestly."""
        t_now = self._frame_time(meta)
        t_last = self.track.last_time()
        if t_last is None:
            self._dr_why = "no measured track to continue"
            return False
        if t_now - t_last > self.max_dead_reckon_s:
            self._dr_why = f"dead-reckoning limit {self.max_dead_reckon_s:.0f}s reached"
            return False
        vo, self._vo_step = self._vo_step, None
        if vo is not None and self._anchor_lat is not None and self._dr_sigma is not None:
            # visual odometry measured this frame's displacement: carry the last position by it
            # (and add it to the track: the velocity follows the turns)
            de, dn, dt, q = vo
            lat, lon = _move((self._anchor_lat, self._anchor_lon), de, dn)
            sigma = self._dr_sigma + 0.1 * math.hypot(de, dn) + 1.0
            if sigma <= self.dr_max_sigma_m:
                self.track.add(t_now, lat, lon, sigma)
                self._carry = None                  # the odometry point is on the track itself
                self._anchor_lat, self._anchor_lon, self._anchor_time = lat, lon, t_now
                self._dr_sigma = self._anchor_sigma = sigma
                self._emit_fix(now, seq_id, lat, lon, meta, status, "dead_reckon", score, None,
                               reason=f"{why}; visual odometry {math.hypot(de, dn):.0f} m in {dt:.1f} s, "
                                      f"±{sigma:.0f} m")
                return True
        p = self._predicted(meta)
        if p is None:
            self._dr_why = "velocity unknown (too few measured fixes), cannot dead-reckon"
            return False
        lat, lon, sigma = p
        if sigma > self.dr_max_sigma_m:
            self._dr_why = f"dead-reckoning uncertainty {sigma:.0f} m > {self.dr_max_sigma_m:.0f} m"
            return False
        self._set_carry(lat, lon, t_now, meta, sigma)
        self._anchor_lat, self._anchor_lon, self._anchor_time = lat, lon, t_now
        self._dr_sigma = self._anchor_sigma = sigma
        self._emit_fix(now, seq_id, lat, lon, meta, status, "dead_reckon", score, None,
                       reason=f"{why}; carried {t_now - t_last:.0f} s, ±{sigma:.0f} m")
        return True

    def _remember_anchor(self):
        """Persist the anchor (at most once a second) for a restart in flight."""
        if time.time() - self._anchor_saved_at >= 1.0 and self._anchor_lat is not None:
            self._anchor_saved_at = time.time()
            state_store.save("day_anchor", {"lat": self._anchor_lat, "lon": self._anchor_lon})

    def _heading_for_match(self, meta):
        """The frame top's azimuth when the live camera measured it (straightened frames),
        else None (no rotation check)."""
        if meta.get("attitude_source") in (None, "none") or meta.get("heading_deg") is None:
            return None
        try:
            return float(meta["heading_deg"])
        except (TypeError, ValueError):
            return None

    def _publish_vision_altitude(self, meta, result, status):
        """The height above ground this match measured: the frame was scaled for
        meta altitude_m, the fitted scale says how much more ground it saw. Published only
        from a strong match (altitude_min_inliers) agreeing within 5 % with the previous
        strong match of the last 10 s: one wrong match cannot set the altitude."""
        try:
            alt = float(meta.get("altitude_m")) * float(result.get("_height_factor", 1.0)) * \
                float(result.get("scale_residual"))
        except (TypeError, ValueError):
            return
        if not (math.isfinite(alt) and alt > 5.0) or int(result.get("inliers") or 0) < self.alt_min_inliers:
            return
        prev, self._alt_candidate = self._alt_candidate, (alt, time.time())
        if prev is None or time.time() - prev[1] > 10.0 or abs(alt - prev[0]) > 0.05 * prev[0]:
            return                                          # not confirmed yet
        r = Range()
        r.header.stamp = exposure_stamp(meta, self.get_clock().now().to_msg())
        r.header.frame_id = "day_camera_link"
        r.radiation_type = Range.INFRARED                     # (no "optical" type in the message)
        r.min_range, r.max_range, r.range = 5.0, 20000.0, float(alt)
        r.field_of_view = float(max(1.0, 0.03 * alt))         # 1-sigma of the measured height (m)
        self.pub_vision_alt.publish(r)
        status["altitude_measured_m"] = round(alt, 1)

    def _emit_fix(self, now, seq_id, lat, lon, meta, status, src, score, jump_m, reason=None):
        status["source"], status["lat"], status["lon"] = src, lat, lon
        status["jump_m"], status["reason"] = jump_m, reason
        status["success"] = True
        self.pub_status.publish(String(data=json.dumps(status)))
        fix = NavSatFix()
        fix.header.stamp    = now
        fix.header.frame_id = "day_camera_link"
        # Legacy/diagnostic topic; the authoritative output is /navera/position.
        # service 0 = not a GNSS position; dead-reckoning is not a fix.
        fix.status.status   = (NavSatStatus.STATUS_NO_FIX if src == "dead_reckon"
                               else NavSatStatus.STATUS_FIX)
        fix.status.service  = 0
        fix.latitude        = lat
        fix.longitude       = lon
        _alt = meta.get("altitude_m")
        fix.altitude        = float(_alt) if _alt is not None else math.nan
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.pub_fix.publish(fix)
        # Additive contract: same fix on the typed channel; mode derived from src.
        self._publish_estimate(now, seq_id, src, lat, lon, meta, score=score,
                               details={"src": src, "score": score, "jump_m": jump_m,
                                        "sigma_m": self._last_fix_sigma if src == "local_match" else None,
                                        "reason": reason,
                                        "fused_score": status.get("fused_score"),
                                        "match": status.get("match")})
        if src == "dead_reckon":
            self._reject_count += 1
        else:
            self._success_count += 1
        icon  = "🧭 DR" if src == "dead_reckon" else "✅"
        extra = f" jump={jump_m:.0f}m" if jump_m is not None else ""
        self.get_logger().info(
            f"[day] {icon} frame={seq_id} src={src} lat={lat:+.5f} lon={lon:+.5f} "
            f"score={score:.2f}{extra}" + (f" ({reason})" if reason else "")
        )

    # ────────────────────────────────────────────────────────────
    # Typed source contract (additive) → /navera/estimate/day
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def _as_frame_index(seq_id):
        try:
            return int(seq_id)
        except (TypeError, ValueError):
            return -1

    def _publish_estimate(self, now, seq_id, src, lat, lon, meta, score, details):
        """Additive: emit the typed source contract on /navera/estimate/day.

        One PositionEstimate per NavSatFix, same lat/lon. `mode` is the honesty
        axis (REPLAYED/MEASURED/PROPAGATED via _DAY_MODE_BY_SRC). Covariance is
        UNKNOWN and confidence 0.0: the day pipeline has no measured sigma — the
        harness median error is sim-only and not a validated Gaussian (step-4
        note). Raw score lives in details_json, diagnostic only.
        """
        est = PositionEstimate()
        est.header.stamp    = now
        est.header.frame_id = "day_camera_link"
        # A NaN / out-of-range / (0,0) position is never published as valid.
        mode = _DAY_MODE_BY_SRC.get(src)
        valid = is_finite_latlon(lat, lon) and mode not in (None, PositionEstimate.MODE_REPLAYED)
        est.latitude  = float(lat) if valid else math.nan
        est.longitude = float(lon) if valid else math.nan
        # altitude NaN-if-unknown (contract): 0.0 is sea level, a REAL altitude —
        # same trap as null-island. Absent altitude_m must be NaN, never 0.0.
        _alt = meta.get("altitude_m")
        est.altitude  = float(_alt) if _alt is not None else math.nan
        if src in ("local_match", "dead_reckon") and valid:
            # local match: its stated sigma (details["sigma_m"], see _fix_sigma; local_sigma_m
            # without one); dead-reckoning: the anchor's plus the growth along the track
            sig = (details.get("sigma_m") if src == "local_match" else None) or \
                (self.local_sigma_m if src == "local_match" else self._dr_sigma)
            var = float(sig) ** 2
            est.position_covariance = [var, 0.0, 0.0, 0.0, var, 0.0, 0.0, 0.0, 0.0]
            est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
        else:
            est.position_covariance      = [0.0] * 9
            est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        est.source     = PositionEstimate.SOURCE_DAY_VISION
        est.mode       = PositionEstimate.MODE_MEASURED if mode is None else mode
        est.valid      = valid
        est.confidence = 0.0
        est.reason     = ("" if valid else
                          "replayed ground truth (test data), never a measurement"
                          if mode == PositionEstimate.MODE_REPLAYED else
                          f"unknown source '{src}'" if mode is None else "non-finite position")
        est.sensor_stamp = exposure_stamp(meta, now)
        est.producer   = "day_subscriber"
        est.model_id   = _DAY_MODEL_BY_SRC.get(src, "")
        est.frame_index = self._as_frame_index(seq_id)
        est.details_json = json.dumps(details)
        self.pub_est.publish(est)

    # ────────────────────────────────────────────────────────────
    # Publish result
    # ────────────────────────────────────────────────────────────
    def _fix_sigma(self, result, meta) -> float:
        """Stated 1-sigma (m) of a local match (day_pkg.fix_sigma), or local_sigma_m without one."""
        if not result.get("sigma_m"):
            return self.local_sigma_m
        v = self.track.velocity(time.time())
        alt = meta.get("altitude_m")
        return day_fix_sigma_m(result.get("sigma_m"), self.local_sigma_floor_m,
                               math.hypot(v[0], v[1]) if v else None, self.frame_time_sigma_s,
                               float(alt) if alt is not None else None, self.attitude_sigma_deg)

    def _check_local_fix(self, result, meta, lat, lon, status):
        """A local match before it is believed: the map bias removed, then the quality gates.
        (lat, lon, None) when it passes, (lat, lon, why) when rejected."""
        de, dn = self.map_bias.bias((lat, lon))
        if de or dn:
            lat, lon = _move((lat, lon), de, dn)
            status["map_bias_m"] = [round(de, 1), round(dn, 1)]
            status["lat"], status["lon"] = lat, lon
        inl = int(result.get("inliers") or 0)
        spread = float(result.get("spread", 1.0))
        if (inl < 30 and spread < self.min_spread) or (inl < 50 and spread <= 0.125):
            return lat, lon, (f"inliers cover {float(result.get('spread', 0)):.0%} of the frame ({inl}): "
                              "poorly conditioned — match rejected")
        pred = self._predicted(meta)
        sig = self._fix_sigma(result, meta)
        doubt = None
        if pred is not None and inl >= self.strong_inliers:
            d = math.hypot(*_en((lat, lon), pred[:2]))
            lim = self.strong_gate_k * math.hypot(pred[2], sig)
            if d > lim:
                doubt = f"strong fix ({inl} inliers) {d:.0f} m from the carried position (> {lim:.0f} m)"
        elif pred is not None:
            d = math.hypot(*_en((lat, lon), pred[:2]))
            lim = self.gate_k * math.hypot(pred[2], sig)
            if d > lim:
                doubt = f"{d:.0f} m from the carried position (> {lim:.0f} m, {inl} inliers)"
            elif pred[2] > 50.0 and inl < 40:
                doubt = f"weak fix ({inl} inliers) while the position is uncertain (±{pred[2]:.0f} m)"
        if doubt is None:
            self._doubted = None
            return lat, lon, None
        # two doubted fixes in a row agreeing with each other: the prediction is what is wrong
        now, prev, self._doubted = time.time(), self._doubted, (time.time(), lat, lon, sig)
        if prev is not None and 0 < now - prev[0] <= 6.0:
            v = self.track.velocity(now)
            ve, vn = (v[0], v[1]) if v is not None else (0.0, 0.0)
            carried = _move(prev[1:3], ve * (now - prev[0]), vn * (now - prev[0]))
            gap = math.hypot(*_en((lat, lon), carried))
            if gap <= max(3.0 * math.hypot(sig, prev[3]), 15.0) + 0.3 * math.hypot(ve, vn) * (now - prev[0]):
                self._doubted = None
                status["reacquired"] = doubt
                return lat, lon, None
        return lat, lon, doubt + " — match rejected (a second agreeing fix would confirm it)"

    def _publish_result(self, seq_id, meta, result):
        now      = self.get_clock().now().to_msg()
        score    = float(result.get("score") or 0.0)
        accepted = bool(result.get("accepted", False))
        err      = result.get("error")
        raw_lat  = result.get("predicted_lat")
        raw_lon  = result.get("predicted_lon")

        status = {
            "frame_id":    seq_id,
            "success":     accepted,
            "lat":         raw_lat, "lon": raw_lon,
            "raw_lat":     raw_lat, "raw_lon": raw_lon,
            "score":       result.get("score"),
            "fused_score": result.get("fused_score"),
            "match":       result.get("match"),
            "total_ms":    result.get("total_ms"),
            "source":      "predicted",
            "error":       err,
            # The search, for display: circle (centre = last retained position),
            # how many tiles it held, and the best candidates.
            "search_center":   result.get("search_center"),
            "search_radius_m": result.get("radius_m"),
            "n_candidates":    result.get("n_candidates"),
            "threshold":       self.conf_threshold,
            "top5": [{"lat": c["lat"], "lon": c["lon"], "score": c["dino"], "image": c["image"]}
                     for c in (result.get("top5") or [])],
            "matcher": result.get("matcher", "retrieval"),
            "inliers": result.get("inliers"),
            "scale_residual": result.get("scale_residual"),
            "rotation_deg": result.get("rotation_deg"),
            "matcher_note": result.get("matcher_note"),
        }

        # ───── filtre OFF → comportement BRUT historique (inchangé, pour comparaison) ─────
        if not self.antijump_enabled:
            if err:
                status["success"] = False
                self.pub_status.publish(String(data=json.dumps(status)))
                self.get_logger().warn(f"[day] ✗  frame={seq_id} localizer error: {err}")
                return
            if not accepted:
                self._reject_count += 1
                status["rejected"] = True
                status["reason"]   = f"score {score:.2f} < threshold {self.conf_threshold:.2f}"
                self.pub_status.publish(String(data=json.dumps(status)))
                self.get_logger().warn(
                    f"[day] ⚠  frame={seq_id} REJECTED (score={score:.2f} < {self.conf_threshold:.2f})")
                return
            self._emit_fix(now, seq_id, float(raw_lat), float(raw_lon), meta, status,
                           "predicted", score, jump_m=None)
            return

        # ───── filtre ON ─────
        t_now = time.time()
        spatial_empty = bool(result.get("spatial_empty"))
        measured = (not err) and accepted and not spatial_empty and is_finite_latlon(raw_lat, raw_lon)
        gated = None
        if measured and result.get("matcher") == "local":
            raw_lat, raw_lon, gated = self._check_local_fix(result, meta, float(raw_lat), float(raw_lon), status)
            measured = gated is None
        if measured and self._anchor_lat is not None and self._anchor_time is not None:
            jump = haversine_m(self._anchor_lat, self._anchor_lon, float(raw_lat), float(raw_lon))
            margin = self.gate_margin_m
            if result.get("matcher") == "local" and self._anchor_sigma is not None:
                # a local match is a position (not a ~250 m tile): the margin is the two
                # positions' uncertainty, never more than gate_margin_m
                margin = kinematic_margin_m(self.gate_k, self._anchor_sigma,
                                            self._fix_sigma(result, meta), self.gate_margin_m)
            reach = self.max_speed_mps * max(0.0, t_now - self._anchor_time) + margin
            if jump > reach:
                measured = False
                gated = (f"implausible jump {jump:.0f} m in {t_now - self._anchor_time:.1f} s "
                         f"(max {reach:.0f} m) — match rejected")

        if measured:
            # Accepted match: in spatial mode it lies within R of the anchor by
            # construction; in global mode (no anchor) it passed conf_threshold.
            out_lat, out_lon = float(raw_lat), float(raw_lon)
            jump_m = (haversine_m(self._anchor_lat, self._anchor_lon, out_lat, out_lon)
                      if self._anchor_lat is not None else None)
            src = ("local_match" if result.get("matcher") == "local" else
                   "visual_match" if result.get("spatial") else "predicted")
            reason = (f"in-circle R={float(result.get('radius_m') or 0.0):.0f}m "
                      f"n={result.get('n_candidates')}") if result.get("spatial") else None
            if self.local is not None and src == "local_match":
                self._prefetch_ahead(out_lat, out_lon, t_now, img_shape=result.get("_frame_shape"),
                                     mpp=result.get("_frame_mpp"))
            self._anchor_lat, self._anchor_lon, self._anchor_time = out_lat, out_lon, t_now
            self._last_measured_time = t_now
            fix_sigma = self._fix_sigma(result, meta) if src == "local_match" else self.local_sigma_m
            self._dr_sigma = self._anchor_sigma = fix_sigma
            self._last_fix_sigma = fix_sigma
            self._carry = None
            self._rejects_in_row = 0
            self._remember_anchor()
            if src == "local_match":
                ns = meta.get("image_stamp_ns")         # the photo's instant, not the processing's
                self.track.add(int(ns) / 1e9 if ns else t_now, out_lat, out_lon, fix_sigma)
                self._track_heading = self._heading_for_match(meta)
            if src == "local_match":
                self._publish_vision_altitude(meta, result, status)
            self._emit_fix(now, seq_id, out_lat, out_lon, meta, status, src, score, jump_m, reason)
            return

        # ── No usable match this frame ──
        # A motion-gate rejection keeps the (trusted) anchor: it does not count
        # towards dropping it.
        if not gated:
            self._rejects_in_row += 1
        if gated:
            why = gated
        elif err:
            why = str(err)
        elif spatial_empty:
            why = f"no tile within R={float(result.get('radius_m') or 0.0):.0f}m"
        else:
            why = (result.get("reason") if result.get("matcher") == "local" and result.get("reason")
                   else f"score {score:.2f} < {self.conf_threshold:.2f}")

        if not self._dead_reckon(now, seq_id, meta, status, score, why):
            self._publish_no_fix(now, seq_id, meta, status, score, why + "; " + self._dr_why)

        if (self._anchor_lat is not None and self._rejects_in_row >= self.max_consecutive_rejects
                and self.local is None):           # local matching widens its search instead
            self.get_logger().warn(
                f"[day] {self._rejects_in_row} frames without a match — dropping the anchor, "
                "next frame searches the whole map")
            self._anchor_lat = self._anchor_lon = self._anchor_time = None
            self._rejects_in_row = 0

    def _publish_no_fix(self, now, seq_id, meta, status, score, reason):
        """Declare a frame that produced no position (valid=False, NaN) — never a guess."""
        self._reject_count += 1
        status.update({"success": False, "rejected": True, "reason": reason,
                       "lat": None, "lon": None, "source": "none"})
        self.pub_status.publish(String(data=json.dumps(status)))
        est = PositionEstimate()
        est.header.stamp    = now
        est.header.frame_id = "day_camera_link"
        est.latitude = est.longitude = est.altitude = math.nan
        est.position_covariance      = [0.0] * 9
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        est.source     = PositionEstimate.SOURCE_DAY_VISION
        est.mode       = PositionEstimate.MODE_MEASURED
        est.valid      = False
        est.confidence = 0.0
        est.reason     = reason
        est.sensor_stamp = exposure_stamp(meta, now)
        est.producer   = "day_subscriber"
        est.model_id   = _DAY_MODEL_BY_SRC["predicted"]
        est.frame_index = self._as_frame_index(seq_id)
        est.details_json = json.dumps({"score": score, "reason": reason,
                                       "match": status.get("match")})
        self.pub_est.publish(est)
        self.get_logger().warn(f"[day] ✗ frame={seq_id} no position: {reason}")


def main(args=None):
    """Entry point. Exits cleanly (code 0) on SIGINT and SIGTERM.

    rclpy installs handlers for both signals and shuts the context down itself,
    so spin() returns with the context already closed — an unconditional
    rclpy.shutdown() here would then raise RCLError. Hence the rclpy.ok() guard.
    """
    # The localizer libraries log through the standard logging module.
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] [%(name)s]: %(message)s")
    die_with_parent()  # orphan guard: die if our launcher/systemd unit is killed
    rclpy.init(args=args)
    node = None
    try:
        node = DaySubscriber()   # may abort if a signal lands during model load
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
