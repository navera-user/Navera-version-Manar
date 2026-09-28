#!/usr/bin/env python3
"""
day_subscriber.py — NAVERA day_pkg, visual-localization subscriber.

Consumes the DAY camera stream published by camera_pkg and runs the existing
DayLocalizer (NetVLAD + DINOv2 retrieval) on each frame:

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
import math
import threading
import time

import cv2

import rclpy
from navera_common.geo import dead_reckon, is_finite_latlon
from navera_common.lifecycle import die_with_parent
from navera_common.pairing import FramePairer, exposure_stamp, stamp_ns
from navera_common.prior import GpsPrior
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from sensor_msgs.msg import Image, NavSatFix, NavSatStatus
from std_msgs.msg import String, Int32, Bool
from cv_bridge import CvBridge
from navera_msgs.msg import PositionEstimate

# Existing localization logic (UNMODIFIED user code).
# DayLocalizer().predict(bgr_array, threshold=...) -> dict
from day_pkg.nodes.day_localizer import DayLocalizer, haversine_m

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
}
_DAY_MODEL_BY_SRC = {
    "gps":          "csv_ground_truth",
    "predicted":    "dinov2_vits14+gem",
    "visual_match": "dinov2_vits14+gem",
    "dead_reckon":  "dead_reckon",
}


class DaySubscriber(Node):
    def __init__(self):
        super().__init__("day_subscriber")

        # ── Parameters ──────────────────────────────────────────
        self.declare_parameter("conf_threshold", 0.75)
        self.declare_parameter("image_topic", "/day/image_raw")
        self.declare_parameter("meta_topic", "/day/frame_meta")
        self.declare_parameter("fix_topic", "/day/position_estimate")
        self.declare_parameter("status_topic", "/day/day_status")
        self.declare_parameter("estimate_topic", "/navera/estimate/day")  # typed source contract
        # Live GPS, used as the search prior: while it is valid the anchor follows
        # it and inference is skipped; when it drops, vision starts from its last fix.
        self.declare_parameter("gps_topic", "/navera/estimate/gps")
        self.declare_parameter("gps_prior_timeout_s", 2.0)
        self.declare_parameter("done_topic", "/day/frame_done")   # back-pressure ack (Int32 frame_id)
        self.declare_parameter("ready_topic", "/day/localizer_ready")  # handshake: modèle chargé
        # ── track filter (anchor, spatial prior, dead-reckoning) ──
        self.declare_parameter("antijump_enabled", True)      # false = raw per-frame output, no anchor
        # After this many consecutive frames without an accepted match, the anchor
        # is dropped and the next frame searches globally: a wrong anchor must not
        # confine the search forever.
        self.declare_parameter("max_consecutive_rejects", 3)
        # Dead-reckoning from the last accepted fix is only published for this long.
        self.declare_parameter("max_dead_reckon_s", 30.0)
        # Whole-map search (no prior). Measured on labelled frames: 12 % within
        # 300 m, and the similarity score does not separate good matches from
        # bad ones (docs/VALIDATION_STATUS.md). Off: without a prior (GPS fix or
        # tracked match) day vision reports no position instead of a guess.
        self.declare_parameter("allow_global_search", False)

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
        self.allow_global_search = bool(self.get_parameter("allow_global_search").value)

        # ── State ───────────────────────────────────────────────
        self.bridge        = CvBridge()
        self._busy_lock    = threading.Lock()
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
        self.get_logger().info("⏳ Loading DayLocalizer (NetVLAD + DINOv2)…")
        self.localizer = DayLocalizer()
        self.localizer.load_models()
        self.localizer.load_or_build_cache()
        self.get_logger().info("✅ DayLocalizer ready, awaiting frames…")

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
        self.sub_gps = self.create_subscription(
            PositionEstimate, self.get_parameter("gps_topic").value, self.on_gps, 10)

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

    def on_gps(self, msg: PositionEstimate):
        """Valid measured GPS → it becomes the anchor (the prior for GPS loss)."""
        if self._gps_prior.update(msg.latitude, msg.longitude, msg.valid,
                                  msg.mode == PositionEstimate.MODE_MEASURED):
            self._anchor_lat, self._anchor_lon = msg.latitude, msg.longitude
            self._anchor_time = time.time()
            self._last_measured_time = self._anchor_time
            self._rejects_in_row = 0

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
            # Live GPS healthy → it is the position source; no inference needed.
            if self._gps_prior.fresh() is not None:
                self.pub_status.publish(String(data=json.dumps({
                    "frame_id": seq_id, "success": False, "source": "gps_active",
                    "reason": "GPS valid — vision idle, tracking GPS as prior"})))
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
            result = self.localizer.predict(img, threshold=self.conf_threshold,
                                            center=center, radius_m=R)
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
                f"dino={c['dino']:.3f} nv={c['netvlad']:.3f} "
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
        return (self._anchor_lat, self._anchor_lon), R

    def _emit_fix(self, now, seq_id, lat, lon, meta, status, src, score, jump_m, reason=None):
        status["source"], status["lat"], status["lon"] = src, lat, lon
        status["jump_m"], status["reason"] = jump_m, reason
        status["success"] = True
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
        # Additive contract: same fix on the typed channel; mode derived from src.
        self._publish_estimate(now, seq_id, src, lat, lon, meta, score=score,
                               details={"src": src, "score": score, "jump_m": jump_m,
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
        valid = is_finite_latlon(lat, lon)
        est.latitude  = float(lat) if valid else math.nan
        est.longitude = float(lon) if valid else math.nan
        # altitude NaN-if-unknown (contract): 0.0 is sea level, a REAL altitude —
        # same trap as null-island. Absent altitude_m must be NaN, never 0.0.
        _alt = meta.get("altitude_m")
        est.altitude  = float(_alt) if _alt is not None else math.nan
        est.position_covariance      = [0.0] * 9
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        est.source     = PositionEstimate.SOURCE_DAY_VISION
        est.mode       = _DAY_MODE_BY_SRC.get(src, PositionEstimate.MODE_MEASURED)
        est.valid      = valid
        est.confidence = 0.0
        est.reason     = "" if valid else "non-finite position"
        est.sensor_stamp = exposure_stamp(meta, now)
        est.producer   = "day_subscriber"
        est.model_id   = _DAY_MODEL_BY_SRC.get(src, "")
        est.frame_index = self._as_frame_index(seq_id)
        est.details_json = json.dumps(details)
        self.pub_est.publish(est)

    # ────────────────────────────────────────────────────────────
    # Publish result
    # ────────────────────────────────────────────────────────────
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

        if measured:
            # Accepted match: in spatial mode it lies within R of the anchor by
            # construction; in global mode (no anchor) it passed conf_threshold.
            out_lat, out_lon = float(raw_lat), float(raw_lon)
            jump_m = (haversine_m(self._anchor_lat, self._anchor_lon, out_lat, out_lon)
                      if self._anchor_lat is not None else None)
            src = "visual_match" if result.get("spatial") else "predicted"
            reason = (f"in-circle R={float(result.get('radius_m') or 0.0):.0f}m "
                      f"n={result.get('n_candidates')}") if result.get("spatial") else None
            self._anchor_lat, self._anchor_lon, self._anchor_time = out_lat, out_lon, t_now
            self._last_measured_time = t_now
            self._rejects_in_row = 0
            self._emit_fix(now, seq_id, out_lat, out_lon, meta, status, src, score, jump_m, reason)
            return

        # ── No usable match this frame ──
        self._rejects_in_row += 1
        if err:
            why = str(err)
        elif spatial_empty:
            why = f"no tile within R={float(result.get('radius_m') or 0.0):.0f}m"
        else:
            why = f"score {score:.2f} < {self.conf_threshold:.2f}"

        propagated = None
        if (self._anchor_lat is not None and self._last_measured_time is not None
                and t_now - self._last_measured_time <= self.max_dead_reckon_s):
            propagated = dead_reckon(self._anchor_lat, self._anchor_lon,
                                     meta.get("heading_deg"), meta.get("speed_mps"),
                                     t_now - self._anchor_time)
        if propagated is not None:
            self._anchor_lat, self._anchor_lon = propagated
            self._anchor_time = t_now
            self._emit_fix(now, seq_id, propagated[0], propagated[1], meta, status,
                           "dead_reckon", score, None, reason=why)
        else:
            if self._anchor_lat is None:
                why += "; no previous fix"
            elif t_now - (self._last_measured_time or t_now) > self.max_dead_reckon_s:
                why += f"; dead-reckoning limit {self.max_dead_reckon_s:.0f}s reached"
            else:
                why += "; heading/speed unknown, cannot dead-reckon"
            self._publish_no_fix(now, seq_id, meta, status, score, why)

        if self._anchor_lat is not None and self._rejects_in_row >= self.max_consecutive_rejects:
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
