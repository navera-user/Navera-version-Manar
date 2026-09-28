#!/usr/bin/env python3
"""
night_subscriber.py — NAVERA Night Localization ROS2 subscriber (Option A).

Calqué EXACTEMENT sur day_subscriber.py, mais la localisation GPS-denied passe
par STHN (night_localizer) au lieu de DINOv2 :

    /thermal/image_raw    sensor_msgs/Image   (bgr8, RELIABLE — back-pressure)
    /thermal/frame_meta   std_msgs/String     (JSON from camera_publisher.py)

et émet :

    /night/position_estimate  sensor_msgs/NavSatFix
    /night/night_status       std_msgs/String   (JSON diagnostics, lu par navera_web_bridge)
    /thermal/frame_done       std_msgs/Int32    (ack back-pressure → publisher)
    /night/localizer_ready    std_msgs/Bool     (latché : handshake modèle chargé)

Logique par frame (miroir du day) :
  1. GPS connu (lat/lon dans le CSV)  → publie cette position (src=gps), SANS STHN.
  2. NOGPS → prior = dernier point valide (anchor) → STHN.localize(img, anchor) :
       • succès & conf ≥ seuil → publie la position STHN (src=night_sthn).
       • échec / conf basse    → DEAD-RECKONING depuis l'anchor (src=dead_reckon).
  STHN raffine AUTOUR du prior (il fetch un patch satellite centré dessus) : le
  prior=anchor remplace le « cercle » du day.

Handshake + back-pressure + cadence identiques au day (la cadence est gérée par
le camera_publisher via min_frame_interval).
"""
import json
import logging
import math
import os
import threading
import time

import cv2
import numpy as np

import rclpy
from navera_common.geo import dead_reckon, is_finite_latlon
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from navera_common.pairing import FramePairer, exposure_stamp, stamp_ns
from navera_common.prior import GpsPrior
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from sensor_msgs.msg import Image, NavSatFix, NavSatStatus
from std_msgs.msg import String, Int32, Bool
from cv_bridge import CvBridge

# Import the existing STHN wrapper (UNMODIFIED user code).
# NightLocalizer.localize(query_bgr, prior_lat, prior_lon) -> dict
from night_pkg.nodes.night_localizer import NightLocalizer
from navera_msgs.msg import PositionEstimate

# Typed source contract (estimator step 6) — mode is the HONESTY axis:
# a replayed CSV point can NEVER pass itself off as a STHN measurement,
# and a dead-reckon bridge is PROPAGATED, not measured. Same rule as day_pkg.
_NIGHT_MODE_BY_SRC = {
    "gps":         PositionEstimate.MODE_REPLAYED,   # CSV ground truth, not a measurement
    "night_sthn":  PositionEstimate.MODE_MEASURED,   # real STHN inference
    "dead_reckon": PositionEstimate.MODE_PROPAGATED, # heading/speed bridge from anchor
}
_NIGHT_MODEL_BY_SRC = {
    "gps":         "csv_replay",
    "night_sthn":  "sthn_one_stage",
    "dead_reckon": "dead_reckon_v1",
}



def image_to_bgr8(bridge, msg: Image):
    """Image → 8-bit BGR. 16-bit thermal is contrast-stretched (2nd-98th
    percentile): a plain conversion saturates or blanks the scene."""
    if msg.encoding in ("mono16", "16UC1"):
        raw = bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough").astype(np.float32)
        lo, hi = np.percentile(raw, (2.0, 98.0))
        g = np.clip((raw - lo) / max(hi - lo, 1.0) * 255.0, 0, 255).astype(np.uint8)
        return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    return bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")


class NightSubscriber(Node):
    def __init__(self):
        super().__init__("night_subscriber")

        # ── Parameters ──────────────────────────────────────────
        self.declare_parameter("sthn_dir",
            os.environ.get("NAVERA_STHN_DIR", "/home/navera/isaac_ros_common/night_pkg/STHN"))
        self.declare_parameter("weights",
            os.environ.get("NAVERA_STHN_WEIGHTS", "/home/navera/isaac_ros_common/night_pkg/STHN/weights/one_stage/model.safetensors"))
        self.declare_parameter("mbtiles",
            os.environ.get("NAVERA_MBTILES", "/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles"))
        self.declare_parameter("zoom",            17)
        declare_float(self, "conf_threshold",  0.30)
        self.declare_parameter("image_topic",     "/thermal/image_raw")
        self.declare_parameter("meta_topic",      "/thermal/frame_meta")
        self.declare_parameter("fix_topic",       "/night/position_estimate")
        self.declare_parameter("status_topic",    "/night/night_status")
        self.declare_parameter("done_topic",      "/thermal/frame_done")     # ack back-pressure
        self.declare_parameter("ready_topic",     "/night/localizer_ready")  # handshake
        # Live GPS, used as the prior (see day_subscriber).
        # Map calibration offset (deg), measured for the map in use; none by default.
        declare_float(self, "map_offset_lat_deg", 0.0)
        declare_float(self, "map_offset_lon_deg", 0.0)
        self.declare_parameter("gps_topic",       "/navera/estimate/gps")
        declare_float(self, "gps_prior_timeout_s", 2.0)
        # Mission start/stop gate of the camera: a stop (rewind) resets tracking.
        self.declare_parameter("start_topic", "/thermal/camera/start")
        # Dead-reckoning from the last accepted fix is only published for this long.
        declare_float(self, "max_dead_reckon_s", 30.0)
        # fp16 au forward STHN (string pour un toggle 'false' fiable) — défaut activé.
        self.declare_parameter("mixed_precision", "true")

        sthn_dir   = self.get_parameter("sthn_dir").value
        weights    = self.get_parameter("weights").value
        mbtiles    = self.get_parameter("mbtiles").value
        zoom       = int(self.get_parameter("zoom").value)
        self.conf_threshold = float(self.get_parameter("conf_threshold").value)
        # parse robuste string→bool (bool('false') serait True : on évite ce piège)
        self.mixed_precision = str(self.get_parameter("mixed_precision").value).strip().lower() \
            in ("1", "true", "yes", "on")
        image_topic   = self.get_parameter("image_topic").value
        meta_topic    = self.get_parameter("meta_topic").value
        fix_topic     = self.get_parameter("fix_topic").value
        status_topic  = self.get_parameter("status_topic").value
        done_topic    = self.get_parameter("done_topic").value
        ready_topic   = self.get_parameter("ready_topic").value
        self.max_dead_reckon_s = float(self.get_parameter("max_dead_reckon_s").value)
        self._last_measured_time = None   # wall-clock of the last STHN / known fix

        # ── State ───────────────────────────────────────────────
        self.bridge        = CvBridge()
        self._busy_lock    = threading.Lock()
        self._pairer       = FramePairer()   # image/meta matched on the image stamp
        self._frame_count    = 0
        self._success_count  = 0
        self._reject_count   = 0
        # anchor = dernier point RETENU (GPS vérité OU sortie STHN/DR). dt source.
        self._anchor_lat  = None
        self._anchor_lon  = None
        self._anchor_time = None

        # ── Banner (PRE-load) ──────────────────────────────────
        self.get_logger().info("=" * 60)
        self.get_logger().info("  NAVERA night_pkg — STHN Localization subscriber")
        self.get_logger().info(f"  image topic     : {image_topic}")
        self.get_logger().info(f"  meta  topic     : {meta_topic}")
        self.get_logger().info(f"  fix   topic     : {fix_topic}")
        self.get_logger().info(f"  status topic    : {status_topic}")
        self.get_logger().info(f"  conf_threshold  : {self.conf_threshold:.2f}")
        self.get_logger().info(f"  max_dead_reckon : {self.max_dead_reckon_s:.0f} s")
        self.get_logger().info(f"  mixed_precision : {self.mixed_precision} (fp16 forward)")
        self.get_logger().info("  policy          : strictly-serial, back-pressure (acks frame_done)")
        self.get_logger().info("=" * 60)

        # ── Load STHN model (blocking, ~20-60s) ────────────────
        # Si ce chargement échoue (ex. dépendance manquante : kornia/kornia_rs/
        # safetensors), le handshake ci-dessous n'est JAMAIS atteint → le
        # camera_publisher (wait_for_ready) reste figé → 0 frame → bloqué au
        # Point A. On rend donc l'échec EXPLICITE avant de ré-émettre.
        self.get_logger().info("⏳ Loading STHN model — this can take 20-60s…")
        try:
            self.localizer = NightLocalizer(
                sthn_dir=sthn_dir, weights=weights, mbtiles=mbtiles,
                zoom=zoom, conf_threshold=self.conf_threshold,
                mixed_precision=self.mixed_precision,
                map_offset_deg=(float(self.get_parameter("map_offset_lat_deg").value),
                                float(self.get_parameter("map_offset_lon_deg").value)),
            )
        except Exception as e:
            self.get_logger().fatal("=" * 60)
            self.get_logger().fatal("❌ STHN n'a PAS pu charger — handshake non publié,")
            self.get_logger().fatal("   le camera_publisher restera FIGÉ au Point A.")
            self.get_logger().fatal(f"   Cause: {type(e).__name__}: {e}")
            self.get_logger().fatal("   → Vérifie les dépendances dans le container :")
            self.get_logger().fatal("       pip install --no-deps kornia kornia_rs safetensors")
            self.get_logger().fatal("=" * 60)
            raise
        self.get_logger().info("✅ STHN model ready, awaiting frames…")

        # A signal (SIGINT/SIGTERM) during the multi-second STHN load makes rclpy
        # close the context; the create_publisher/create_subscription calls below
        # would then raise "rcl node's context is invalid" (RCLError, exit 1). Abort
        # construction cleanly — main() maps ExternalShutdownException to exit 0.
        # (Lands outside the load try/except above, so STHN failure handling is intact.)
        if not rclpy.ok():
            raise ExternalShutdownException()

        # ── QoS (RELIABLE — match camera_publisher ack mode) ───
        image_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                               history=HistoryPolicy.KEEP_LAST, depth=10)
        meta_qos  = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                               history=HistoryPolicy.KEEP_LAST, depth=10)

        # ── Publishers ──────────────────────────────────────────
        self.pub_fix    = self.create_publisher(NavSatFix, fix_topic,    10)
        self.pub_status = self.create_publisher(String,    status_topic, 10)
        done_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                              history=HistoryPolicy.KEEP_LAST, depth=1)
        self.pub_done   = self.create_publisher(Int32, done_topic, done_qos)
        # Typed source contract for navera_estimator (additive, estimator step 6).
        self.pub_est    = self.create_publisher(PositionEstimate, "/navera/estimate/night", 10)

        # ── Subscribers ─────────────────────────────────────────
        self.sub_image = self.create_subscription(Image, image_topic, self.on_image, image_qos)
        self.sub_meta  = self.create_subscription(String, meta_topic, self.on_meta, meta_qos)
        self._gps_prior = GpsPrior(float(self.get_parameter("gps_prior_timeout_s").value))
        self.sub_gps   = self.create_subscription(
            PositionEstimate, self.get_parameter("gps_topic").value, self.on_gps, 10)
        # Same latched QoS as the camera's gate (TRANSIENT_LOCAL, depth 1).
        start_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                               durability=DurabilityPolicy.TRANSIENT_LOCAL,
                               history=HistoryPolicy.KEEP_LAST, depth=1)
        self.sub_start = self.create_subscription(
            Bool, self.get_parameter("start_topic").value, self.on_start_cmd, start_qos)

        # ── Handshake "ready" (latché) ─────────────────────────
        ready_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                               durability=DurabilityPolicy.TRANSIENT_LOCAL,
                               history=HistoryPolicy.KEEP_LAST, depth=1)
        self.pub_ready = self.create_publisher(Bool, ready_topic, ready_qos)
        self.pub_ready.publish(Bool(data=True))
        self.get_logger().info(f"📣 localizer_ready=True publié sur {ready_topic} (latché)")

    # ────────────────────────────────────────────────────────────
    # Callbacks
    # ────────────────────────────────────────────────────────────
    def on_image(self, msg: Image):
        try:
            img = image_to_bgr8(self.bridge, msg)
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

    def on_start_cmd(self, msg: Bool):
        """Mission stop/rewind → forget the previous run's track (the next run
        starts from GPS, or reports no position until it has a prior)."""
        if msg.data or self._gps_prior.fresh() is not None:
            return
        self._anchor_lat = self._anchor_lon = self._anchor_time = None
        self._last_measured_time = None
        self.get_logger().info("[thermal] mission rewind — tracking state reset")

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
    # Pair + dispatch (strictly-serial, back-pressure garantit 1 frame en vol)
    # ────────────────────────────────────────────────────────────
    def _dispatch(self, img, meta):
        """Handle one image/meta pair (matched on the image stamp)."""
        seq_id = meta.get("frame_id", "?")
        if img is None:
            self.get_logger().error(
                f"[night] frame={seq_id}: image missing or undecodable — acked, not localized")
            self._publish_done(seq_id)
            return
        self._frame_count += 1
        self.get_logger().info(
            f"[night] 🌙 paired frame={seq_id}  "
            f"shape={img.shape}  gps_valid={meta.get('gps_valid')}"
        )
        with self._busy_lock:
            self._process_frame(seq_id, img, meta)

    def _process_frame(self, seq_id, img, meta):
        try:
            gps_valid = meta.get("gps_valid")
            lat = meta.get("lat"); lon = meta.get("lon")

            # 1) GPS connu → naviguer directement vers ce point, sans STHN.
            if gps_valid and lat is not None and lon is not None:
                self._publish_known(seq_id, meta)
                return

            # Live GPS healthy → it is the position source; no inference needed.
            if self._gps_prior.fresh() is not None:
                self.pub_status.publish(String(data=json.dumps({
                    "frame_id": seq_id, "success": False, "source": "gps_active",
                    "reason": "GPS valid — STHN idle, tracking GPS as prior"})))
                return

            # 2) NOGPS → prior = anchor (dernier point valide)
            if self._anchor_lat is None:
                # aucun anchor encore (cas limite : 1res frames NOGPS) → hold
                self.get_logger().warn(
                    f"[night] ⚠ frame={seq_id} no prior: GPS never had a fix")
                self._publish_status_only(seq_id, reason="no anchor yet", meta=meta)
                return

            t_now = time.time()

            self.get_logger().info(
                f"[night] 🛰 STHN frame={seq_id} prior=anchor"
                f"({self._anchor_lat:+.5f},{self._anchor_lon:+.5f})…")
            result = self.localizer.localize(img, self._anchor_lat, self._anchor_lon)
            conf   = float(result.get("conf", 0.0) or 0.0)

            self.get_logger().info(
                f"[night] 🔬 RAW frame={seq_id} success={result.get('success')} "
                f"conf={conf:.3f} shift_px={result.get('rms_px')} dt_ms={result.get('dt_ms')} "
                f"raw_lat={result.get('raw_lat')} raw_lon={result.get('raw_lon')}"
            )

            if (result.get("success") and conf >= self.conf_threshold
                    and is_finite_latlon(result.get("lat"), result.get("lon"))):
                out_lat = float(result["lat"]); out_lon = float(result["lon"])
                self._anchor_lat, self._anchor_lon, self._anchor_time = out_lat, out_lon, t_now
                self._last_measured_time = t_now
                self._publish_fix(seq_id, out_lat, out_lon, meta, "night_sthn",
                                  score=conf, conf=conf,
                                  dt_ms=result.get("dt_ms"), rms_px=result.get("rms_px"))
                return

            # Rejected / failed: dead-reckon only from measured motion, and only for a while.
            reason = f"STHN rejected (consistency {conf:.2f}, min {self.conf_threshold:.2f})"
            propagated = None
            if (self._last_measured_time is not None
                    and t_now - self._last_measured_time <= self.max_dead_reckon_s):
                propagated = dead_reckon(self._anchor_lat, self._anchor_lon,
                                         meta.get("heading_deg"), meta.get("speed_mps"),
                                         t_now - self._anchor_time)
            if propagated is not None:
                self._anchor_lat, self._anchor_lon = propagated
                self._anchor_time = t_now
                self._publish_fix(seq_id, propagated[0], propagated[1], meta, "dead_reckon",
                                  score=0.0, conf=conf, reason=reason)
            else:
                self._publish_status_only(
                    seq_id, reason=reason + "; no measured motion or dead-reckoning limit reached", meta=meta)
        except Exception as e:
            self.get_logger().error(f"[night] STHN error frame={seq_id}: {e}")
        finally:
            # ALWAYS ack (known / sthn / dead_reckon / error) — le publisher ne hang jamais.
            self._publish_done(seq_id)

    # ────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────
    def _publish_known(self, seq_id, meta):
        """GPS connu (vérité terrain) : publie la position du CSV, sans STHN."""
        lat = float(meta["lat"]); lon = float(meta["lon"])
        self._anchor_lat, self._anchor_lon, self._anchor_time = lat, lon, time.time()
        self._last_measured_time = self._anchor_time
        self._publish_fix(seq_id, lat, lon, meta, "gps", score=1.0, conf=1.0)

    def _publish_fix(self, seq_id, lat, lon, meta, src, score, conf,
                     dt_ms=None, rms_px=None, reason=None):
        now = self.get_clock().now().to_msg()
        status = {
            "frame_id": seq_id, "success": True,
            "lat": lat, "lon": lon,
            "score": score, "conf": conf,        # 'score' lu par navera_web_bridge
            "source": src, "reason": reason,
            "dt_ms": dt_ms, "rms_px": rms_px,
        }
        self.pub_status.publish(String(data=json.dumps(status)))

        fix = NavSatFix()
        fix.header.stamp    = now
        fix.header.frame_id = "thermal_camera_link"
        # Legacy/diagnostic topic; the authoritative output is /navera/position.
        # service 0 = not a GNSS position unless replayed GPS; dead-reckoning is not a fix.
        fix.status.status   = (NavSatStatus.STATUS_NO_FIX if src == "dead_reckon"
                               else NavSatStatus.STATUS_FIX)
        fix.status.service  = NavSatStatus.SERVICE_GPS if src == "gps" else 0
        fix.latitude        = lat
        fix.longitude       = lon
        _alt = meta.get("altitude_m")
        fix.altitude        = float(_alt) if _alt is not None else math.nan
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.pub_fix.publish(fix)
        self._publish_estimate(now, seq_id, src, lat, lon, meta,
                               details={"src": src, "score": score, "conf": conf,
                                        "dt_ms": dt_ms, "rms_px": rms_px, "reason": reason})

        if src == "dead_reckon":
            self._reject_count += 1
        else:
            self._success_count += 1
        icon = {"gps": "🛰 KNOWN", "night_sthn": "✅ STHN", "dead_reckon": "🧭 DR"}.get(src, "✅")
        self.get_logger().info(
            f"[night] {icon} frame={seq_id} src={src} lat={lat:+.5f} lon={lon:+.5f} "
            f"conf={conf:.2f}" + (f" ({reason})" if reason else "")
        )

    def _publish_status_only(self, seq_id, reason, meta=None):
        """Statut sans fix (ex. NOGPS sans anchor) — le bridge garde le dernier point."""
        self.pub_status.publish(String(data=json.dumps({
            "frame_id": seq_id, "success": False, "reason": reason, "source": "none",
        })))
        # Contract: an unusable frame is DECLARED, never swallowed (valid=False).
        now = self.get_clock().now().to_msg()
        est = PositionEstimate()
        est.header.stamp = now
        est.header.frame_id = "thermal_camera_link"
        est.latitude = math.nan
        est.longitude = math.nan
        est.altitude = math.nan
        est.position_covariance = [0.0] * 9
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        est.source = PositionEstimate.SOURCE_NIGHT_VISION
        est.mode = PositionEstimate.MODE_MEASURED
        est.valid = False
        est.confidence = 0.0
        est.reason = str(reason or "no usable night frame")
        est.sensor_stamp = exposure_stamp(meta, now)
        est.producer = "night_subscriber"
        est.model_id = ""
        est.frame_index = -1
        est.details_json = json.dumps({"reason": reason})
        self.pub_est.publish(est)

    def _publish_estimate(self, now, seq_id, src, lat, lon, meta, details):
        """Additive: emit the typed source contract on /navera/estimate/night.

        Covariance is UNKNOWN and confidence 0.0: STHN has no validated sigma on
        real thermal imagery yet (same honesty stance as day_pkg — never emit a
        number that looks measured but is not). Raw score/conf live in
        details_json, diagnostic only.
        """
        est = PositionEstimate()
        est.header.stamp    = now
        est.header.frame_id = "thermal_camera_link"
        mode = _NIGHT_MODE_BY_SRC.get(src)
        valid = is_finite_latlon(lat, lon) and mode not in (None, PositionEstimate.MODE_REPLAYED)
        est.latitude  = float(lat) if valid else math.nan
        est.longitude = float(lon) if valid else math.nan
        _alt = meta.get("altitude_m")
        est.altitude  = float(_alt) if _alt is not None else math.nan
        est.position_covariance      = [0.0] * 9
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        est.source     = PositionEstimate.SOURCE_NIGHT_VISION
        est.mode       = PositionEstimate.MODE_MEASURED if mode is None else mode
        est.valid      = valid
        est.confidence = 0.0
        est.reason     = ("" if valid else
                          "replayed ground truth (test data), never a measurement"
                          if mode == PositionEstimate.MODE_REPLAYED else
                          f"unknown source '{src}'" if mode is None else "non-finite position")
        est.sensor_stamp = exposure_stamp(meta, now)
        est.producer   = "night_subscriber"
        est.model_id   = _NIGHT_MODEL_BY_SRC.get(src, "")
        try:
            est.frame_index = int(seq_id)
        except (TypeError, ValueError):
            est.frame_index = -1
        est.details_json = json.dumps(details)
        self.pub_est.publish(est)

    def _publish_done(self, seq_id):
        try:
            fid = int(seq_id)
        except (TypeError, ValueError):
            fid = -1
        self.pub_done.publish(Int32(data=fid))
        self.get_logger().info(f"[night] ✓ done frame={seq_id} → ack ({self.pub_done.topic_name})")


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
        node = NightSubscriber()   # may abort if a signal lands during model load
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
