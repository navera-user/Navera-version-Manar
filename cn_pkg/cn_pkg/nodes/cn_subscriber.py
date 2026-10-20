#!/usr/bin/env python3
"""cn_subscriber.py — NAVERA Celestial Navigation ROS2 subscriber.

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
    solver_mode    (str, default "geoloc") — "geoloc": narrow-field astrometry.net with the
                   boresight from tilt/azimuth; "allsky360": the 360 camera's full dual-fisheye
                   frame, all-sky star identification + quality gate (cn_pkg.allsky, the same
                   code as the field tools) with 'up' from the camera or the vehicle IMU through
                   the camera-to-body mount rotation (allsky_* parameters, see __init__).
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
from navera_common.qos import SENSOR_QOS
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from navera_common.pairing import FramePairer, exposure_stamp, stamp_ns
from navera_common.geo import haversine_m
from navera_common.sensor_history import slerp
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from sensor_msgs.msg import Image, Imu, NavSatFix, NavSatStatus, TimeReference
from navera_msgs.msg import PositionEstimate
import math
from std_msgs.msg import Int32, String
from cv_bridge import CvBridge

from cn_pkg.nodes import solver as cn_solver
from cn_pkg.nodes.celestial_math import boresight_altaz
from cn_pkg import allsky_mount


def _rate_dps(q0, q1, dt_s: float) -> float:
    """Rotation rate (deg/s) between two orientations dt_s apart."""
    if dt_s <= 0:
        return 0.0
    # the angle of q1 relative to q0 by atan2 (acos is noisy near identity)
    w = sum(a * b for a, b in zip(q0, q1))
    x0, y0, z0, w0 = q0
    x1, y1, z1, w1 = q1
    vx = w0 * x1 - x0 * w1 - (y0 * z1 - z0 * y1)
    vy = w0 * y1 - y0 * w1 - (z0 * x1 - x0 * z1)
    vz = w0 * z1 - z0 * w1 - (x0 * y1 - y0 * x1)
    return math.degrees(2.0 * math.atan2(math.sqrt(vx * vx + vy * vy + vz * vz), abs(w))) / dt_s


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
        # how the star camera is mounted on the vehicle. 90 / 0 = pointing up.
        # magnetic_declination_deg: leave 0 — imu_node already publishes a TRUE-north
        # orientation (World Magnetic Model); set it only for an IMU source that
        # reports magnetic north, or the declination would be applied twice.
        declare_float(self, "camera_mount_elevation_deg", 90.0)
        declare_float(self, "camera_mount_azimuth_deg", 0.0)
        declare_float(self, "magnetic_declination_deg", 0.0)
        self.declare_parameter("imu_topic", "/navera/sensors/imu")
        declare_float(self, "imu_timeout_s", 1.0)
        # 1-sigma attitude accuracy of the IMU (deg). Each degree of attitude
        # error moves the fix by ~111 km, so it sets the stated accuracy; NaN =
        # unknown (the fix is then published with an unknown covariance).
        declare_float(self, "attitude_sigma_deg", float("nan"))
        # frames taken while the vehicle rotates faster than this (deg/s) are not solved: a
        # 50 ms attitude error at 20-60 deg/s is degrees, i.e. hundreds of km (simulator
        # 2026-10-07: 122-517 km spikes in climbs and turns, stated 55 km)
        declare_float(self, "max_rotation_dps", 3.0)
        declare_float(self, "imu_max_gap_s", 0.1)
        # Without prior_lat/lon, the last valid GPS fix is the prior.
        self.declare_parameter("gps_topic", "/navera/estimate/gps")
        # ── 360 all-sky mode (solver_mode "allsky360") ──
        # where 'up' comes from: "camera" (frame_meta up_imu, the camera's accelerometer), "vehicle" (the IMU
        # orientation at the exposure through allsky_R_cam_body), "auto" (camera when the frame carries it)
        self.declare_parameter("allsky_up_source", "auto")
        # camera-to-body mount rotation, 9 values row-major: camera-frame vector = R @ body (FLU) vector.
        # Default: the camera standing on a level vehicle (camera +x up, +y left, +z back).
        self.declare_parameter("allsky_R_cam_body", [float(v) for v in allsky_mount.R_CAM_BODY_STANDING.ravel()])
        self.declare_parameter("allsky_lens_file", "")          # "" = sky360.LENS_FILE (NAVERA_INSTA360_LENS)
        self.declare_parameter("allsky_catalogue", "")          # "" = the bundled bright-star list (offline)
        self.declare_parameter("allsky_f_scale_search", [0.96, 1.0, 1.04])
        self.declare_parameter("allsky_cal_min_samples", allsky_mount.CAL_MIN_SAMPLES)
        self.declare_parameter("allsky_cal_samples", allsky_mount.CAL_SAMPLES)
        # a GPS fix older than this is no reference for learning the tilt of 'up'
        declare_float(self, "allsky_cal_gps_max_age_s", 2.0)
        # the vehicle counts as still (tilt calibration samples) below this rotation rate
        declare_float(self, "allsky_cal_still_dps", 0.5)

        self.min_log_odds = float(self.get_parameter("min_log_odds").value)
        self.camera_fov_deg = float(self.get_parameter("camera_fov_deg").value)
        image_topic = self.get_parameter("image_topic").value
        meta_topic = self.get_parameter("meta_topic").value
        fix_topic = self.get_parameter("fix_topic").value
        status_topic = self.get_parameter("status_topic").value
        self.solver_mode = str(self.get_parameter("solver_mode").value).lower()
        self.tilt = float(self.get_parameter("tilt").value)
        self.azimuth = float(self.get_parameter("azimuth").value)
        self.utc_time = str(self.get_parameter("utc_time").value)
        self.prior_lat = float(self.get_parameter("prior_lat").value)
        self.prior_lon = float(self.get_parameter("prior_lon").value)
        self.mount_el = float(self.get_parameter("camera_mount_elevation_deg").value)
        self.mount_az = float(self.get_parameter("camera_mount_azimuth_deg").value)
        self.declination = float(self.get_parameter("magnetic_declination_deg").value)
        self.imu_timeout = float(self.get_parameter("imu_timeout_s").value)
        self.max_rot_dps = float(self.get_parameter("max_rotation_dps").value)
        self.imu_max_gap = float(self.get_parameter("imu_max_gap_s").value)
        self._rate_dps = 0.0                  # rotation rate at the last exposure
        self._recent = deque(maxlen=5)        # (t, lat, lon): accepted fixes, consistency check
        self.attitude_sigma_deg = float(self.get_parameter("attitude_sigma_deg").value)
        # IMU history (stamp ns, quaternion): the attitude used is the one at the
        # frame's EXPOSURE, not at processing time — on a moving vehicle the
        # difference is degrees, i.e. hundreds of km (found in the simulator).
        # 60 s at 50 Hz: a frame that waited (solver busy, node starting) still finds the
        # attitude of its exposure
        self._imu_hist = deque(maxlen=3000)
        self._gyro = deque(maxlen=3000)       # (t_ns, |angular velocity| deg/s) when the IMU gives it
        self._gps_prior = None    # last valid GPS fix (lat, lon)
        self._gps_t = None        # time.monotonic() of that fix
        self.allsky = None
        if self.solver_mode == "allsky360":
            self.allsky = self._make_allsky()
        self.create_subscription(Imu, self.get_parameter("imu_topic").value, self._on_imu, SENSOR_QOS)
        self.create_subscription(PositionEstimate, self.get_parameter("gps_topic").value,
                                 self._on_gps, 10)
        self._rtc_sample = None   # (rtc_epoch, system_epoch_at_read)
        self.create_subscription(TimeReference, self.get_parameter("rtc_topic").value,
                                 self._on_rtc, 10)

        # ── State ───────────────────────────────────────────────
        self.bridge = CvBridge()
        self._busy_lock = threading.Lock()
        self._pairer = FramePairer()   # image/meta matched on the image stamp
        self._frame_count = 0
        self._success_count = 0
        self._skip_count = 0
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
        self.pub_fix = self.create_publisher(NavSatFix, fix_topic,    10)
        self.pub_status = self.create_publisher(String,    status_topic, 10)
        # Typed source contract for navera_estimator (additive, estimator step 7).
        self.pub_est = self.create_publisher(PositionEstimate, "/navera/estimate/cn", 10)
        # solved (or failed): the live star camera may send the next frame
        self.pub_done = self.create_publisher(Int32, "/celestial/frame_done", 1)

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
    def _make_allsky(self):
        """The 360 mode's state (catalogue loaded once, lenses, tilt calibration)."""
        from cn_pkg.allsky_locator import AllSkyLocator
        g = lambda n: self.get_parameter(n).value          # noqa: E731
        att = self.attitude_sigma_deg
        loc = AllSkyLocator(
            catalogue_path=str(g("allsky_catalogue")) or None, lens_file=str(g("allsky_lens_file")) or None,
            f_scale_search=list(g("allsky_f_scale_search")), R_cam_body=list(g("allsky_R_cam_body")),
            up_source=str(g("allsky_up_source")),
            base_sigma_deg=att if math.isfinite(att) and att > 0 else allsky_mount.ATTITUDE_SIGMA_360_DEG,
            cal_min_samples=int(g("allsky_cal_min_samples")), cal_samples=int(g("allsky_cal_samples")),
            cal_still_dps=float(g("allsky_cal_still_dps")))
        self.get_logger().info(f"  allsky360       : {len(loc.cat.vec)} stars, up from {loc.up_source}, "
                               f"R_cam_body {np.round(loc.R_cam_body, 4).tolist()}")
        return loc

    def on_image(self, msg: Image):
        try:
            img = self.bridge.imgmsg_to_cv2(msg, desired_encoding="mono8" if self.allsky else "bgr8")
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
        w = msg.angular_velocity
        if msg.angular_velocity_covariance[0] != -1.0 and (w.x, w.y, w.z) != (0.0, 0.0, 0.0):
            self._gyro.append((stamp_ns(msg.header.stamp), math.degrees(math.sqrt(w.x * w.x + w.y * w.y + w.z * w.z))))

    def _imu_at(self, t_ns):
        """(orientation at t_ns, rotation rate deg/s): interpolated between the IMU samples
        around it (no more than imu_max_gap_s apart), else the nearest within imu_timeout_s;
        the rate from _rate_at; None without one.
        """
        hist = list(self._imu_hist)
        if not hist:
            return None
        q = None
        for (t0, q0), (t1, q1) in zip(hist, hist[1:]):
            if t0 <= t_ns <= t1 and t1 > t0:
                if (t1 - t0) / 1e9 <= self.imu_max_gap:
                    q = slerp(q0, q1, (t_ns - t0) / (t1 - t0))
                break
        if q is None:
            ts, q = min(hist, key=lambda s: abs(s[0] - t_ns))
            if abs(ts - t_ns) > self.imu_timeout * 1e9:
                return None
        return q, self._rate_at(t_ns, hist)

    def _rate_at(self, t_ns, hist) -> float:
        """Rotation rate around the exposure (deg/s): the gyro (80th percentile of its
        magnitude within +-0.25 s), else the attitude change over a 0.5 s baseline. Two
        attitude samples a few ms apart are no rate: autopilot messages arrive in bursts
        stamped at reception (0.01-0.05 deg over ~1 ms read 10-90 deg/s, 2026-10-07).
        """
        win = 0.25e9
        g = sorted(r for t, r in self._gyro if abs(t - t_ns) <= win)
        if g:
            return g[min(len(g) - 1, int(0.8 * len(g)))]
        before = [x for x in hist if x[0] <= t_ns - win]
        after = [x for x in hist if x[0] >= t_ns + win]
        a = before[-1] if before else hist[0]
        b = after[0] if after else hist[-1]
        dt = (b[0] - a[0]) / 1e9
        return _rate_dps(a[1], b[1], dt) if dt >= 0.3 else 0.0

    def _on_gps(self, msg: PositionEstimate):
        if msg.valid and msg.mode == PositionEstimate.MODE_MEASURED and \
                math.isfinite(msg.latitude) and math.isfinite(msg.longitude):
            self._gps_prior = (msg.latitude, msg.longitude)
            self._gps_t = time.monotonic()

    def _attitude(self, meta):
        """(tilt, azimuth, source): frame_meta, else a fresh IMU, else parameters."""
        if meta.get("tilt") is not None and meta.get("azimuth") is not None:
            return float(meta["tilt"]), float(meta["azimuth"]), "frame"
        exp = meta.get("image_stamp_ns")
        got = self._imu_at(int(exp) if exp is not None else self.get_clock().now().nanoseconds)
        if got is not None:
            q, self._rate_dps = got
            if self._rate_dps > self.max_rot_dps:
                return (float("nan"), float("nan"),
                        f"imu: rotating {self._rate_dps:.1f} deg/s (max {self.max_rot_dps:.0f})")
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
        reading exists, else the system clock.
        """
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
            try:
                self.pub_done.publish(Int32(data=int(seq_id)))   # done with it: send the next
            except (TypeError, ValueError):
                pass
            return

        threading.Thread(
            target=self._process_frame, args=(seq_id, img, meta), daemon=True
        ).start()

    def _utc_for(self, meta):
        """(UTC used, source): frame_meta, else the utc_time parameter, else the RTC / system clock."""
        utc = meta.get("utc_time") or self.utc_time
        src = "frame" if meta.get("utc_time") else "parameter"
        if not utc:
            utc, src = self._utc_now()
        return utc, src

    def _solve_allsky(self, img, meta):
        """360 mode: the whole sky above the camera, 'up' from the camera or the vehicle (AllSkyLocator)."""
        utc, meta["utc_source"] = self._utc_for(meta)
        meta["utc_used"] = utc
        exp = meta.get("image_stamp_ns")
        got = self._imu_at(int(exp) if exp is not None else self.get_clock().now().nanoseconds)
        q, rate = got if got is not None else (None, 0.0)
        self._rate_dps = rate
        up, src, _ = self.allsky.up(meta, q)
        meta.update(attitude_source=f"allsky360 up from {src}", prior=None, prior_source="none (all-sky)")
        if src == "vehicle" and q is not None and rate > self.max_rot_dps:
            return {"success": False, "source": "allsky360",
                    "error": f"frame not solved: imu: rotating {rate:.1f} deg/s (max {self.max_rot_dps:.0f})"}
        ref = None
        if self._gps_prior and self._gps_t is not None and \
                time.monotonic() - self._gps_t <= float(self.get_parameter("allsky_cal_gps_max_age_s").value):
            ref = self._gps_prior
        t0 = time.monotonic()
        result = self.allsky.process(img, utc, meta, q, rate, ref)
        result["solve_s"] = round(time.monotonic() - t0, 1)
        if result.get("tilt_calibrated"):
            self.get_logger().info(f"[cn] allsky360 tilt of 'up' learned: {result['tilt_calibrated']}")
        return result

    def _process_frame(self, seq_id, img, meta):
        try:
            if self.allsky is not None:
                self.get_logger().info(f"[cn] 🛰  solving frame={seq_id} (mode=allsky360)…")
                self._publish_result(seq_id, meta, self._solve_allsky(img, meta))
                return
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
                utc, utc_src = self._utc_for(meta)
                meta["utc_source"] = utc_src
                meta["utc_used"] = utc
                if att_src.startswith("imu: rotating"):
                    result = {"success": False, "error": f"frame not solved: {att_src}"}
                elif not (math.isfinite(tilt) and math.isfinite(azimuth)):
                    exp = meta.get("image_stamp_ns")
                    hist = list(self._imu_hist)
                    near = None
                    if hist and exp is not None:
                        near = (min(abs(ts - int(exp)) for ts, _ in hist) / 1e9,
                                (hist[0][0] - int(exp)) / 1e9, (hist[-1][0] - int(exp)) / 1e9)
                    result = {"success": False,
                              "error": "camera attitude (tilt/azimuth) unknown — needs the IMU "
                                       f"({len(hist)} IMU samples on {self.get_parameter('imu_topic').value}"
                                       + (f", nearest {near[0]:.2f} s from the exposure; they span "
                                          f"{near[1]:+.1f} to {near[2]:+.1f} s around it" if near else "")
                                       + ")"}
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
            try:
                self.pub_done.publish(Int32(data=int(seq_id)))
            except (TypeError, ValueError):
                pass

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
        allsky = result.get("source") == "allsky360"
        if allsky:
            # the all-sky gate (allsky.accept) already judged the match; the sigma is the fix's own
            status["sigma_m"] = result.get("sigma_m")
            status.update({k: result[k] for k in (
                "up_source", "up_cam", "moving", "spots", "matched", "used", "rms_deg", "p_chance",
                "lens_disagree_deg", "sigma_fit_deg", "f_scale", "f_scale_found", "matched_per_lens", "raw_lat",
                "raw_lon", "tilt_cal", "cal_sample", "tilt_calibrated", "retried_with") if k in result})

        log_odds = result.get("log_odds")
        if result.get("success") and not allsky and (log_odds is None or log_odds < self.min_log_odds):
            self._reject_count += 1
            status["success"] = False
            status["rejected"] = True
            status["reason"] = f"star match log-odds {log_odds} < {self.min_log_odds:.1f}"
            self.get_logger().warn(f"[cn] ⚠  frame={seq_id} REJECTED ({status['reason']})")

        if status["success"]:
            # a fix far from the median of the last ones (beyond 3 sigma) is an attitude
            # transient, not where the vehicle is
            lat, lon = float(result["predicted_lat"]), float(result["predicted_lon"])
            t_now = time.monotonic()
            recent = [r for r in self._recent if t_now - r[0] <= 600.0]
            sig = status["sigma_m"]
            if len(recent) >= 3 and sig:
                mlat = sorted(r[1] for r in recent)[len(recent) // 2]
                mlon = sorted(r[2] for r in recent)[len(recent) // 2]
                d = haversine_m(lat, lon, mlat, mlon)
                if d > 3.0 * sig:
                    status["success"], status["rejected"] = False, True
                    status["reason"] = (f"{d / 1000:.0f} km from the median of the last {len(recent)} fixes "
                                        f"(> 3 sigma = {3 * sig / 1000:.0f} km)")
                    self._reject_count += 1
            self._recent.append((t_now, lat, lon))

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
        fix.header.stamp = now
        fix.header.frame_id = "celestial_camera_link"
        # Legacy/diagnostic topic; the authoritative output is /navera/position.
        # service 0 = not a GNSS position; dead-reckoning is not a fix.
        fix.status.status = NavSatStatus.STATUS_FIX
        fix.status.service = 0
        fix.latitude = float(result["predicted_lat"])
        fix.longitude = float(result["predicted_lon"])
        _alt = meta.get("altitude_m")
        fix.altitude = float(_alt) if _alt is not None else math.nan
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
        """Stated 1-sigma horizontal accuracy: (attitude error + the attitude change during the
        IMU's own timing error, ~50 ms at the exposure's rotation rate) x ~111 km/deg (None =
        unknown).
        """
        s = self.attitude_sigma_deg
        return (s + 0.05 * self._rate_dps) * 111_195.0 if math.isfinite(s) and s > 0 else None

    def _publish_estimate(self, now, seq_id, lat, lon, meta, valid, reason, details):
        """Additive: emit the typed source contract on /navera/estimate/cn."""
        est = PositionEstimate()
        est.header.stamp = now
        est.header.frame_id = "celestial_camera_link"
        if valid and lat is not None and lon is not None:
            est.latitude, est.longitude = float(lat), float(lon)
        else:
            est.latitude = est.longitude = math.nan
            valid = False
        _alt = meta.get("altitude_m") if isinstance(meta, dict) else None
        est.altitude = float(_alt) if _alt is not None else math.nan
        sigma = details.get("sigma_m") if isinstance(details, dict) and "sigma_m" in details else self._sigma_m()
        if sigma:
            est.position_covariance = [sigma ** 2, 0.0, 0.0, 0.0, sigma ** 2, 0.0, 0.0, 0.0, 0.0]
            est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
        else:
            est.position_covariance = [0.0] * 9
            est.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_UNKNOWN
        est.source = PositionEstimate.SOURCE_CELESTIAL
        est.mode = PositionEstimate.MODE_MEASURED
        est.valid = bool(valid)
        est.confidence = 0.0        # hard-coded 0.95 is NOT a measurement — see module doc
        est.reason = reason
        est.sensor_stamp = exposure_stamp(meta, now)
        est.producer = "cn_subscriber"
        est.model_id = "allsky360" if details.get("source") == "allsky360" else "astrometry.net"
        try:
            est.frame_index = int(seq_id)
        except (TypeError, ValueError):
            est.frame_index = -1
        est.details_json = json.dumps(
            {**details, "utc_source": meta.get("utc_source") if isinstance(meta, dict) else None}, default=str)
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
