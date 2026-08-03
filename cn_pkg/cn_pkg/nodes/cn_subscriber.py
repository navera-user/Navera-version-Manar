#!/usr/bin/env python3
"""
cn_subscriber.py — NAVERA Celestial Navigation ROS2 subscriber.

Subscribes to camera_pkg celestial topics, runs the existing
astrometry-based solver (cn_pkg.nodes.solver.solve_image_b64),
and publishes a position fix.

Subscribes:
    /celestial/image_raw    sensor_msgs/Image
    /celestial/frame_meta   std_msgs/String  (JSON from camera_publisher.py)

Publishes:
    /cn/position_estimate   sensor_msgs/NavSatFix
    /cn/cn_status           std_msgs/String  (JSON)

Pairing strategy:
    The publisher emits image + meta in the same millisecond. We simply
    cache the latest image and the latest meta as they arrive; whenever
    BOTH are present we process the pair and clear the buffers. Robust
    against any timestamp format and works for celestial (slow) frames.

Parameters:
    conf_threshold (float, default 0.30) — minimum match_score below which
                   the fix is REJECTED.
    image_topic    (str,  default "/celestial/image_raw")
    meta_topic     (str,  default "/celestial/frame_meta")
    fix_topic      (str,  default "/cn/position_estimate")
    status_topic   (str,  default "/cn/cn_status")

Concurrency: skip-if-busy. If a new pair arrives while the solver is still
running, the new pair is DROPPED (logged) — never queued, never parallel.
"""
import json
import base64
import threading

import cv2
import numpy as np

import rclpy
from navera_common.lifecycle import die_with_parent
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from sensor_msgs.msg import Image, NavSatFix, NavSatStatus
from navera_msgs.msg import PositionEstimate
import math
from std_msgs.msg import String
from cv_bridge import CvBridge

from cn_pkg.nodes import solver as cn_solver


class CNSubscriber(Node):
    def __init__(self):
        super().__init__("cn_subscriber")

        # ── Parameters ──────────────────────────────────────────
        self.declare_parameter("conf_threshold", 0.30)
        self.declare_parameter("image_topic", "/celestial/image_raw")
        self.declare_parameter("meta_topic", "/celestial/frame_meta")
        self.declare_parameter("fix_topic", "/cn/position_estimate")
        self.declare_parameter("status_topic", "/cn/cn_status")

        # Solver selection:
        #   "geoloc" → real ground fix via drone_sky_prep.py (needs tilt/azimuth/UTC)
        #   "wcs"    → rough placeholder (lat=Dec, lon=f(RA)) via solve_image_b64
        # tilt/azimuth/utc_time default to the bundled etoiles.jpeg sample; a
        # frame_meta carrying "tilt"/"azimuth"/"utc_time" overrides them per frame.
        self.declare_parameter("solver_mode", "geoloc")
        self.declare_parameter("tilt", 75.46)
        self.declare_parameter("azimuth", 283.18)
        self.declare_parameter("utc_time", "2026-03-10 20:20:00")

        self.conf_threshold = float(self.get_parameter("conf_threshold").value)
        image_topic   = self.get_parameter("image_topic").value
        meta_topic    = self.get_parameter("meta_topic").value
        fix_topic     = self.get_parameter("fix_topic").value
        status_topic  = self.get_parameter("status_topic").value
        self.solver_mode = str(self.get_parameter("solver_mode").value).lower()
        self.tilt        = float(self.get_parameter("tilt").value)
        self.azimuth     = float(self.get_parameter("azimuth").value)
        self.utc_time    = str(self.get_parameter("utc_time").value)

        # ── State ───────────────────────────────────────────────
        self.bridge        = CvBridge()
        self._busy_lock    = threading.Lock()
        self._state_lock   = threading.Lock()
        self._latest_img   = None   # cv2 numpy image (BGR)
        self._latest_meta  = None   # dict from JSON
        self._frame_count  = 0
        self._success_count = 0
        self._skip_count   = 0
        self._reject_count = 0

        # ── QoS per topic (must match camera_pkg publisher exactly) ─
        # RELIABLE — MUST match the camera_publisher image publisher (RELIABLE,
        # depth-1, ONE-SHOT for celestial). A BEST_EFFORT reader gets no
        # retransmission, so a single ~2 MB mono8 frame is silently dropped the
        # moment any UDP fragment is lost → never pairs, never solves. Mirrors
        # the working day_subscriber image QoS.
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
        # Typed source contract for navera_estimator (additive, estimator step 7).
        self.pub_est    = self.create_publisher(PositionEstimate, "/navera/estimate/cn", 10)

        # ── Subscribers ─────────────────────────────────────────
        self.sub_image = self.create_subscription(
            Image, image_topic, self.on_image, image_qos
        )
        self.sub_meta = self.create_subscription(
            String, meta_topic, self.on_meta, meta_qos
        )

        # ── Banner ──────────────────────────────────────────────
        self.get_logger().info("=" * 60)
        self.get_logger().info("  NAVERA cn_pkg — CELESTIAL NAVIGATION subscriber")
        self.get_logger().info(f"  image topic     : {image_topic}")
        self.get_logger().info(f"  meta  topic     : {meta_topic}")
        self.get_logger().info(f"  fix   topic     : {fix_topic}")
        self.get_logger().info(f"  status topic    : {status_topic}")
        self.get_logger().info(f"  conf_threshold  : {self.conf_threshold:.2f}")
        self.get_logger().info(f"  solver_mode     : {self.solver_mode}")
        if self.solver_mode == "geoloc":
            self.get_logger().info(
                f"  tilt/azimuth    : {self.tilt}° / {self.azimuth}°  utc={self.utc_time}"
            )
        self.get_logger().info("  policy          : skip-if-busy, latest-pair")
        self.get_logger().info("=" * 60)

    # ────────────────────────────────────────────────────────────
    # Callbacks
    # ────────────────────────────────────────────────────────────
    def on_image(self, msg: Image):
        try:
            img = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as e:
            self.get_logger().warn(f"cv_bridge decode failed: {e}")
            return
        with self._state_lock:
            self._latest_img = img
        self._try_dispatch("image")

    def on_meta(self, msg: String):
        try:
            meta = json.loads(msg.data)
        except Exception as e:
            self.get_logger().warn(f"meta JSON decode failed: {e}")
            return
        with self._state_lock:
            self._latest_meta = meta
        self._try_dispatch("meta")

    # ────────────────────────────────────────────────────────────
    # Pair + dispatch
    # ────────────────────────────────────────────────────────────
    def _try_dispatch(self, source):
        """If we have a latest image AND a latest meta, run the solver."""
        with self._state_lock:
            img  = self._latest_img
            meta = self._latest_meta
            if img is None or meta is None:
                return
            # Consume the pair — next pair must come from new arrivals.
            self._latest_img  = None
            self._latest_meta = None

        seq_id = meta.get("frame_id", "?")
        self._frame_count += 1
        self.get_logger().info(
            f"[cn] 🌟 paired (via {source}) frame={seq_id}  "
            f"shape={img.shape}  gps_valid={meta.get('gps_valid')}"
        )

        # Skip-if-busy: do not block, do not queue.
        if not self._busy_lock.acquire(blocking=False):
            self._skip_count += 1
            self.get_logger().warn(
                f"[cn] ⏭  skipping frame={seq_id} (solver still busy)"
            )
            return

        threading.Thread(
            target=self._process_frame, args=(seq_id, img, meta), daemon=True
        ).start()

    def _process_frame(self, seq_id, img, meta):
        try:
            ok, jpg = cv2.imencode(".jpg", img)
            if not ok:
                self.get_logger().error(f"[cn] cv2.imencode failed frame={seq_id}")
                return
            b64 = base64.b64encode(jpg.tobytes()).decode("ascii")

            self.get_logger().info(
                f"[cn] 🛰  solving frame={seq_id} (mode={self.solver_mode}, 10-60s)…"
            )
            if self.solver_mode == "geoloc":
                tilt    = float(meta.get("tilt", self.tilt))
                azimuth = float(meta.get("azimuth", self.azimuth))
                utc     = str(meta.get("utc_time", self.utc_time))
                result = cn_solver.solve_image_b64_geoloc(b64, tilt, azimuth, utc)
            else:
                result = cn_solver.solve_image_b64(b64)
            self._publish_result(seq_id, meta, result)
        except Exception as e:
            self.get_logger().error(f"[cn] solver error frame={seq_id}: {e}")
        finally:
            self._busy_lock.release()

    # ────────────────────────────────────────────────────────────
    # Publish result
    # ────────────────────────────────────────────────────────────
    def _publish_result(self, seq_id, meta, result):
        now = self.get_clock().now().to_msg()

        status = {
            "frame_id": seq_id,
            "success": bool(result.get("success", False)),
            "ra_deg":  result.get("ra_deg"),
            "dec_deg": result.get("dec_deg"),
            "lat":     result.get("predicted_lat"),
            "lon":     result.get("predicted_lon"),
            "match_score": result.get("match_score"),
            "source": result.get("source", "stellar"),
            "error":  result.get("error"),
        }

        score = float(result.get("match_score", 0.0) or 0.0)
        if result.get("success") and score < self.conf_threshold:
            self._reject_count += 1
            status["success"]   = False
            status["rejected"]  = True
            status["reason"]    = f"match_score {score:.2f} < threshold {self.conf_threshold:.2f}"
            self.get_logger().warn(
                f"[cn] ⚠  frame={seq_id} REJECTED (score={score:.2f} < {self.conf_threshold:.2f})"
            )

        self.pub_status.publish(String(data=json.dumps(status)))

        if not status["success"]:
            err = result.get("error")
            if err:
                self.get_logger().warn(
                    f"[cn] ✗  frame={seq_id} solver failed: {str(err)[:120]}"
                )
            # Contract: a failed/rejected solve is DECLARED, never swallowed.
            self._publish_estimate(now, seq_id, None, None, meta,
                                   valid=False,
                                   reason=str(status.get("reason") or result.get("error") or "solve failed"),
                                   details=status)
            return

        fix = NavSatFix()
        fix.header.stamp    = now
        fix.header.frame_id = "celestial_camera_link"
        fix.status.status   = NavSatStatus.STATUS_FIX
        fix.status.service  = NavSatStatus.SERVICE_GPS
        fix.latitude        = float(result["predicted_lat"])
        fix.longitude       = float(result["predicted_lon"])
        fix.altitude        = float(meta.get("altitude_m") or 0.0)
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.pub_fix.publish(fix)
        self._publish_estimate(now, seq_id, fix.latitude, fix.longitude, meta,
                               valid=True, reason="",
                               details={**status, "hardcoded_score_warning":
                                        "match_score is a CONSTANT (0.95), not a measured confidence"})

        self._success_count += 1
        self.get_logger().info(
            f"[cn] ✅ frame={seq_id}  lat={fix.latitude:+.5f}  lon={fix.longitude:+.5f}  "
            f"score={score:.2f}  "
            f"(total: ok={self._success_count} reject={self._reject_count} skip={self._skip_count})"
        )


    def _publish_estimate(self, now, seq_id, lat, lon, meta, valid, reason, details):
        """Additive: emit the typed source contract on /navera/estimate/cn."""
        est = PositionEstimate()
        est.header.stamp    = now
        est.header.frame_id = "celestial_camera_link"
        if valid and lat is not None and lon is not None:
            est.latitude, est.longitude = float(lat), float(lon)
        else:
            est.latitude = est.longitude = math.nan
            valid = False
        _alt = meta.get("altitude_m") if isinstance(meta, dict) else None
        est.altitude  = float(_alt) if _alt is not None else math.nan
        est.position_covariance      = [0.0] * 9
        est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        est.source     = PositionEstimate.SOURCE_CELESTIAL
        est.mode       = PositionEstimate.MODE_MEASURED
        est.valid      = bool(valid)
        est.confidence = 0.0        # hard-coded 0.95 is NOT a measurement — see module doc
        est.reason     = reason
        est.sensor_stamp = now
        est.producer   = "cn_subscriber"
        est.model_id   = "astrometry.net"
        try:
            est.frame_index = int(seq_id)
        except (TypeError, ValueError):
            est.frame_index = -1
        est.details_json = json.dumps(details, default=str)
        self.pub_est.publish(est)


CN_SUBSCRIBER_ESTIMATE_DOC = """Typed contract notes (estimator step 7):
Covariance UNKNOWN and confidence 0.0 by design: the celestial match_score is a
hard-coded constant (0.95), NOT a measured confidence (handoff warning). It is
relegated to details_json as diagnostic only. Also: the geodetic solution
depends on tilt/azimuth/UTC inputs that are still static test metadata — until
RTC UTC + IMU attitude are wired in, celestial fixes are MEASURED but unbounded.
"""


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
        # Unlike day/night, CNSubscriber.__init__ has NO heavy pre-load: cn is a
        # per-frame astrometry.net plate-solver, so subscriptions are created
        # immediately (no multi-second startup window to be interrupted). Hence no
        # rclpy.ok() guard inside __init__ — there is no window to protect. node=None
        # still matters: if __init__ raises for any other reason, the finally below
        # must not touch an undefined node.
        node = CNSubscriber()
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
