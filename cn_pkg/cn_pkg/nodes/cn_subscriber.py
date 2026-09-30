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
    min_log_odds   (float, default 20.7) — minimum astrometry.net log-odds of
                   the star match (20.7 ~ odds of 1e9, astrometry's own default).
    camera_fov_deg (float, default NaN) — star camera horizontal field of view;
                   unknown = slower wide search.
    image_topic    (str,  default "/celestial/image_raw")
    meta_topic     (str,  default "/celestial/frame_meta")
    fix_topic      (str,  default "/cn/position_estimate")
    status_topic   (str,  default "/cn/cn_status")

Concurrency: skip-if-busy. If a new pair arrives while the solver is still
running, the new pair is DROPPED (logged) — never queued, never parallel.
"""
import json
import base64
from collections import deque
import threading
import time
from datetime import datetime, timezone

import cv2
import numpy as np

import rclpy
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from navera_common.pairing import FramePairer, exposure_stamp, stamp_ns
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from sensor_msgs.msg import Image, Imu, NavSatFix, NavSatStatus, TimeReference
from navera_msgs.msg import PositionEstimate
import math
from std_msgs.msg import String
from cv_bridge import CvBridge

from cn_pkg.nodes import solver as cn_solver
from cn_pkg.nodes.celestial_math import boresight_altaz


class CNSubscriber(Node):
    def __init__(self):
        super().__init__("cn_subscriber")

        # ── Parameters ──────────────────────────────────────────
        declare_float(self, "min_log_odds", 20.7)
        declare_float(self, "camera_fov_deg", float("nan"))
        self.declare_parameter("image_topic", "/celestial/image_raw")
        self.declare_parameter("meta_topic", "/celestial/frame_meta")
        self.declare_parameter("fix_topic", "/cn/position_estimate")
        self.declare_parameter("status_topic", "/cn/cn_status")

        # Solver selection:
        #   "geoloc" → real ground fix via drone_sky_prep.py (needs tilt/azimuth/UTC)
        #   "wcs"    → rough placeholder (lat=Dec, lon=f(RA)) via solve_image_b64
        # A frame_meta carrying "tilt"/"azimuth"/"utc_time" overrides the
        # parameters per frame. Defaults are UNKNOWN: without a measured camera
        # attitude (IMU) no position is published, and an empty utc_time means
        # "the system clock at processing time" (RTC-backed on the vehicle).
        # Replay launch files set the values of their sample image explicitly.
        self.declare_parameter("solver_mode", "geoloc")
        declare_float(self, "tilt", float("nan"))
        declare_float(self, "azimuth", float("nan"))
        self.declare_parameter("utc_time", "")
        # Approximate position of the operating area: one sky direction matches
        # two positions in general, and this prior picks the right one.
        declare_float(self, "prior_lat", float("nan"))
        # Time source when frame_meta and utc_time do not give one: the DS3231
        # RTC (survives an offline boot), else the system clock.
        self.declare_parameter("rtc_topic", "/navera/sensors/rtc_time")
        declare_float(self, "prior_lon", float("nan"))
        # Camera attitude from the IMU (used when frame_meta has no tilt/azimuth):
        # how the star camera is mounted on the vehicle, and the local magnetic
        # declination (the IMU heading is magnetic). 90 / 0 = pointing up.
        declare_float(self, "camera_mount_elevation_deg", 90.0)
        declare_float(self, "camera_mount_azimuth_deg", 0.0)
        declare_float(self, "magnetic_declination_deg", 0.0)
        self.declare_parameter("imu_topic", "/navera/sensors/imu")
        declare_float(self, "imu_timeout_s", 1.0)
        # 1-sigma attitude accuracy of the IMU (deg). Each degree of attitude
        # error moves the fix by ~111 km, so it sets the stated accuracy; NaN =
        # unknown (the fix is then published with an unknown covariance).
        declare_float(self, "attitude_sigma_deg", float("nan"))
        # Without prior_lat/lon, the last valid GPS fix is the prior.
        self.declare_parameter("gps_topic", "/navera/estimate/gps")

        self.min_log_odds   = float(self.get_parameter("min_log_odds").value)
        self.camera_fov_deg = float(self.get_parameter("camera_fov_deg").value)
        image_topic   = self.get_parameter("image_topic").value
        meta_topic    = self.get_parameter("meta_topic").value
        fix_topic     = self.get_parameter("fix_topic").value
        status_topic  = self.get_parameter("status_topic").value
        self.solver_mode = str(self.get_parameter("solver_mode").value).lower()
        self.tilt        = float(self.get_parameter("tilt").value)
        self.azimuth     = float(self.get_parameter("azimuth").value)
        self.utc_time    = str(self.get_parameter("utc_time").value)
        self.prior_lat   = float(self.get_parameter("prior_lat").value)
        self.prior_lon   = float(self.get_parameter("prior_lon").value)
        self.mount_el    = float(self.get_parameter("camera_mount_elevation_deg").value)
        self.mount_az    = float(self.get_parameter("camera_mount_azimuth_deg").value)
        self.declination = float(self.get_parameter("magnetic_declination_deg").value)
        self.imu_timeout = float(self.get_parameter("imu_timeout_s").value)
        self.attitude_sigma_deg = float(self.get_parameter("attitude_sigma_deg").value)
        # IMU history (stamp ns, quaternion): the attitude used is the one at the
        # frame's EXPOSURE, not at processing time — on a moving vehicle the
        # difference is degrees, i.e. hundreds of km (found in the simulator).
        self._imu_hist = deque(maxlen=400)
        self._gps_prior = None    # last valid GPS fix (lat, lon)
        self.create_subscription(Imu, self.get_parameter("imu_topic").value, self._on_imu, 10)
        self.create_subscription(PositionEstimate, self.get_parameter("gps_topic").value,
                                 self._on_gps, 10)
        self._rtc_sample = None   # (rtc_epoch, system_epoch_at_read)
        self.create_subscription(TimeReference, self.get_parameter("rtc_topic").value,
                                 self._on_rtc, 10)

        # ── State ───────────────────────────────────────────────
        self.bridge        = CvBridge()
        self._busy_lock    = threading.Lock()
        self._pairer       = FramePairer()   # image/meta matched on the image stamp
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
        self.get_logger().info(f"  min_log_odds    : {self.min_log_odds:.1f}   camera_fov_deg: {self.camera_fov_deg}")
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
            img = None                      # still paired, so the frame is acked
        pair = self._pairer.add_image(stamp_ns(msg.header.stamp), img)
        if pair is not None:
            self._dispatch(*pair)

    def _on_rtc(self, msg: TimeReference):
        """rtc_node publishes rtc_time only when the DS3231 time is valid (UTC)."""
        sys_epoch = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        self._rtc_sample = (msg.time_ref.sec + msg.time_ref.nanosec * 1e-9, sys_epoch)

    def _on_imu(self, msg: Imu):
        q = msg.orientation
        if (q.x, q.y, q.z, q.w) != (0.0, 0.0, 0.0, 0.0):
            self._imu_hist.append((stamp_ns(msg.header.stamp), (q.x, q.y, q.z, q.w)))

    def _imu_at(self, t_ns):
        """IMU orientation nearest to t_ns, if within imu_timeout_s of it."""
        if not self._imu_hist:
            return None
        ts, q = min(list(self._imu_hist), key=lambda s: abs(s[0] - t_ns))
        return q if abs(ts - t_ns) <= self.imu_timeout * 1e9 else None

    def _on_gps(self, msg: PositionEstimate):
        if msg.valid and msg.mode == PositionEstimate.MODE_MEASURED and \
                math.isfinite(msg.latitude) and math.isfinite(msg.longitude):
            self._gps_prior = (msg.latitude, msg.longitude)

    def _attitude(self, meta):
        """(tilt, azimuth, source): frame_meta, else a fresh IMU, else parameters."""
        if meta.get("tilt") is not None and meta.get("azimuth") is not None:
            return float(meta["tilt"]), float(meta["azimuth"]), "frame"
        exp = meta.get("image_stamp_ns")
        q = self._imu_at(int(exp) if exp is not None else self.get_clock().now().nanoseconds)
        if q is not None:
            alt, az = boresight_altaz(q, self.mount_el, self.mount_az, self.declination)
            return alt, az, "imu (at exposure)" if exp is not None else "imu (latest)"
        return self.tilt, self.azimuth, "parameter"

    def _prior(self):
        if math.isfinite(self.prior_lat):
            return self.prior_lat, self.prior_lon, "parameter"
        if self._gps_prior:
            return self._gps_prior[0], self._gps_prior[1], "last GPS fix"
        return float("nan"), float("nan"), "none"

    def _utc_now(self):
        """(UTC "YYYY-MM-DD HH:MM:SS", source) — RTC-based when a recent valid
        reading exists, else the system clock."""
        now = time.time()
        if self._rtc_sample is not None and 0.0 <= now - self._rtc_sample[1] <= 5.0:
            rtc_epoch, sys_epoch = self._rtc_sample
            t = datetime.fromtimestamp(rtc_epoch + (now - sys_epoch), tz=timezone.utc)
            return t.strftime("%Y-%m-%d %H:%M:%S"), "rtc"
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "system_clock"

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
                f"[cn] frame={seq_id}: image missing or undecodable — acked, not localized")
            return
        self._frame_count += 1
        self.get_logger().info(
            f"[cn] 🌟 paired frame={seq_id}  "
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
                tilt, azimuth, att_src = self._attitude(meta)
                prior_lat, prior_lon, prior_src = self._prior()
                meta.update(attitude_source=att_src, tilt_used=tilt, azimuth_used=azimuth,
                            prior=[prior_lat, prior_lon], prior_source=prior_src)
                utc = meta.get("utc_time") or self.utc_time
                utc_src = "frame" if meta.get("utc_time") else "parameter"
                if not utc:
                    utc, utc_src = self._utc_now()
                meta["utc_source"] = utc_src
                meta["utc_used"] = utc
                if not (math.isfinite(tilt) and math.isfinite(azimuth)):
                    result = {"success": False,
                              "error": "camera attitude (tilt/azimuth) unknown — needs the IMU"}
                else:
                    t0 = time.monotonic()
                    result = cn_solver.solve_image_b64_geoloc(
                        b64, tilt, azimuth, utc, prior_lat, prior_lon,
                        self.camera_fov_deg)
                    result["solve_s"] = round(time.monotonic() - t0, 1)
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
            "log_odds": result.get("log_odds"),
            "source": result.get("source", "stellar"),
            "error":  result.get("error"),
            "solve_s": result.get("solve_s"),
            "tilt":   meta.get("tilt_used"), "azimuth": meta.get("azimuth_used"),
            "attitude_source": meta.get("attitude_source"),
            "prior": meta.get("prior"), "prior_source": meta.get("prior_source"),
            "utc": meta.get("utc_used"), "utc_source": meta.get("utc_source"),
            "sigma_m": self._sigma_m(),
            "min_log_odds": self.min_log_odds,
        }

        log_odds = result.get("log_odds")
        if result.get("success") and (log_odds is None or log_odds < self.min_log_odds):
            self._reject_count += 1
            status["success"]   = False
            status["rejected"]  = True
            status["reason"]    = f"star match log-odds {log_odds} < {self.min_log_odds:.1f}"
            self.get_logger().warn(f"[cn] ⚠  frame={seq_id} REJECTED ({status['reason']})")

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
        # Legacy/diagnostic topic; the authoritative output is /navera/position.
        # service 0 = not a GNSS position; dead-reckoning is not a fix.
        fix.status.status   = NavSatStatus.STATUS_FIX
        fix.status.service  = 0
        fix.latitude        = float(result["predicted_lat"])
        fix.longitude       = float(result["predicted_lon"])
        _alt = meta.get("altitude_m")
        fix.altitude        = float(_alt) if _alt is not None else math.nan
        fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
        self.pub_fix.publish(fix)
        self._publish_estimate(now, seq_id, fix.latitude, fix.longitude, meta,
                               valid=True, reason="",
                               details=status)

        self._success_count += 1
        self.get_logger().info(
            f"[cn] ✅ frame={seq_id}  lat={fix.latitude:+.5f}  lon={fix.longitude:+.5f}  "
            f"log-odds={log_odds}  "
            f"(total: ok={self._success_count} reject={self._reject_count} skip={self._skip_count})"
        )


    def _sigma_m(self):
        """Stated 1-sigma horizontal accuracy: attitude error x ~111 km/deg (NaN = unknown)."""
        s = self.attitude_sigma_deg
        return s * 111_195.0 if math.isfinite(s) and s > 0 else None

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
        sigma = self._sigma_m()
        if sigma:
            est.position_covariance = [sigma ** 2, 0.0, 0.0, 0.0, sigma ** 2, 0.0, 0.0, 0.0, 0.0]
            est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
        else:
            est.position_covariance      = [0.0] * 9
            est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        est.source     = PositionEstimate.SOURCE_CELESTIAL
        est.mode       = PositionEstimate.MODE_MEASURED
        est.valid      = bool(valid)
        est.confidence = 0.0        # hard-coded 0.95 is NOT a measurement — see module doc
        est.reason     = reason
        est.sensor_stamp = exposure_stamp(meta, now)
        est.producer   = "cn_subscriber"
        est.model_id   = "astrometry.net"
        try:
            est.frame_index = int(seq_id)
        except (TypeError, ValueError):
            est.frame_index = -1
        est.details_json = json.dumps({**details, "utc_source": meta.get("utc_source") if isinstance(meta, dict) else None}, default=str)
        self.pub_est.publish(est)


CN_SUBSCRIBER_ESTIMATE_DOC = """Typed contract notes (estimator step 7):
Covariance UNKNOWN and confidence 0.0 by design: the astrometry log-odds rates the star
match only, not the attitude or time used to turn it into a position; the old match_score was a
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
