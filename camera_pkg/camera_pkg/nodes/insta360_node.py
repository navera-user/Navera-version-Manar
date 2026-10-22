#!/usr/bin/env python3
"""insta360_node — the Insta360 kit: the One R (USB Android mode) as NAVERA's day camera AND IMU.

ONE process owns the camera (only one can: the webcam mode, the field server and this node exclude
each other). It reads every packet (live over USB, or replayed from a field raw recording) and
publishes:

  <imu_topic>    (default /navera/sensors/insta360/imu)  sensor_msgs/Imu, 100 Hz, RELIABLE depth 50
      orientation      body FLU -> world ENU (camera_pkg.insta360_attitude): roll / pitch from the
                       gyro + accelerometer (Mahony, acceleration rejection), yaw from the gyro,
                       set by the GPS course while the GPS is trusted and by day-vision headings
      orientation_covariance  diag(tilt^2, tilt^2, yaw^2) rad^2 — yaw pi^2 while no heading
                       source has set it (it is then only the gyro's relative yaw)
      angular_velocity / linear_acceleration / covariances: as insta360_imu_node (body frame,
                       bias at rest removed, specific force with gravity, measured noise)
      header.stamp     host time of the sample (the camera's ms clock mapped by its IMU packets)
  <image_topic>  (default /navera/sensors/insta360/nadir/image_raw)  sensor_msgs/Image bgr8
      the body-fixed straight-down view cut from the dual fisheye (camera_pkg.insta360_view),
      header.stamp = the EXPOSURE (its own packet's camera ms - exposure_lag_ms, F15), at most max_fps
  <status_topic> (default /navera/sensors/insta360/status)  std_msgs/String JSON every 2 s

The live camera reads them with NAVERA_CAMERA_INPUT=insta360 (the image topic, an ideal lens of
view_hfov_deg, no mount offset: the mount is applied here) and NAVERA_SENSOR_SOURCE=insta360 (the
IMU topic, also the day pipeline's gyro heading carry and the night / celestial attitude).

Inputs for the heading: <position_topic> (navera_msgs/PositionEstimate, the arbiter's output: GPS
fixes it vouched for give the course and the speed); <vision_status_topic> + <vision_meta_topic>
(the day node's status: a good fix's fitted rotation = the frame top's azimuth at that frame's
exposure).

A camera lost (unplugged, USB error for camera_lost_exit_s) makes the node exit: systemd restarts
it and it opens the camera again.
"""
import json
import math
import threading
import time

import rclpy
from navera_common.insta360_protocol import IMU_CALIBRATION, load_imu_calibration
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from navera_msgs.msg import PositionEstimate
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image, Imu
from std_msgs.msg import String

from camera_pkg.insta360_attitude import AttitudeFilter, GpsCourse
from camera_pkg.insta360_imu import (
    MEASURED_ACCEL_SAMPLE_STD_G, MEASURED_GYRO_SAMPLE_STD_DPS, G, ImuStream, UsbImuSource, covariance_diag,
    mount_rotation)
from camera_pkg.insta360_kit import KIT_EXPOSURE_LAG_MS, Insta360Kit, replay_all
from camera_pkg.insta360_view import NadirView, load_lenses

IMU_QOS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE,
                     history=HistoryPolicy.KEEP_LAST, depth=50)
IMG_QOS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.VOLATILE,
                     history=HistoryPolicy.KEEP_LAST, depth=1)
STATUS_PERIOD_S = 2.0
LOG_PERIOD_S = 30.0


def vision_heading(meta: dict, status: dict, min_inliers: int):
    """(exposure s, frame-top azimuth deg) of a good day fix, or None: the status of an accepted
    match with at least min_inliers and a fitted rotation, paired with its frame's meta."""
    if not status.get("success") or status.get("rotation_deg") is None:
        return None
    if int(status.get("inliers") or 0) < min_inliers:
        return None
    ns = meta.get("image_stamp_ns")
    if not ns:
        return None
    try:
        return int(ns) / 1e9, float(status["rotation_deg"]) % 360.0
    except (TypeError, ValueError):
        return None


def frame_top_offset_deg(R_body_enu) -> float:
    """Azimuth of the straightened view's top minus the body's nose heading (deg): ~0 for the
    body-fixed nadir view near level; computed exactly so a tilted frame does not bias it."""
    import numpy as np
    from navera_common.camera_model import R_BODY_NADIR_CAM, heading_of_image_up_deg
    from camera_pkg.insta360_attitude import heading_of
    R = np.asarray(R_body_enu) @ R_BODY_NADIR_CAM
    return (heading_of_image_up_deg(R) - heading_of(np.asarray(R_body_enu)) + 180.0) % 360.0 - 180.0


class Insta360Node(Node):
    def __init__(self, **kwargs) -> None:
        super().__init__("insta360", **kwargs)
        self.declare_parameter("source", "live")               # live | replay
        self.declare_parameter("replay_path", "")
        declare_float(self, "replay_rate", 1.0)
        self.declare_parameter("replay_loop", False)
        self.declare_parameter("replay_clock", "now")
        self.declare_parameter("exit_at_end", True)
        self.declare_parameter("imu_topic", "/navera/sensors/insta360/imu")
        self.declare_parameter("image_topic", "/navera/sensors/insta360/nadir/image_raw")
        self.declare_parameter("status_topic", "/navera/sensors/insta360/status")
        self.declare_parameter("frame_id", "insta360_imu_link")
        self.declare_parameter("image_frame_id", "insta360_nadir_link")
        # camera IMU axes along body x, y, z (camera_pkg.insta360_imu.axes_matrix). Kit default:
        # LYING, the LEFT lens looking down, the camera's top towards the nose
        self.declare_parameter("mount_axes", "+x,+z,-y")
        declare_float(self, "mount_roll_deg", 0.0)
        declare_float(self, "mount_pitch_deg", 0.0)
        declare_float(self, "mount_yaw_deg", 0.0)
        self.declare_parameter("decimation", 5)
        self.declare_parameter("bias_at_rest", True)
        self.declare_parameter("calibration_file", "")         # IMU: "" = NAVERA_INSTA360_IMU / bench file
        self.declare_parameter("lens_file", "")                # "" = NAVERA_INSTA360_LENS / box / bench file
        declare_float(self, "view_hfov_deg", 100.0)
        self.declare_parameter("view_width", 1200)
        self.declare_parameter("view_height", 900)
        declare_float(self, "max_fps", 2.0)
        # a key frame's packet camera ms minus its exposure (camera_pkg.insta360_kit module doc: 0, from
        # the 1.5 s measured through the field driver's 3-key-frame decoder delay)
        declare_float(self, "exposure_lag_ms", float(KIT_EXPOSURE_LAG_MS))
        declare_float(self, "camera_lost_exit_s", 5.0)
        declare_float(self, "gyro_sample_std_dps", MEASURED_GYRO_SAMPLE_STD_DPS)
        declare_float(self, "accel_sample_std_g", MEASURED_ACCEL_SAMPLE_STD_G)
        # attitude filter (camera_pkg.insta360_attitude.AttitudeFilter)
        declare_float(self, "kp", 0.05)
        declare_float(self, "ki", 0.0005)
        declare_float(self, "acc_gate_g", 0.03)
        declare_float(self, "turn_gate_dps", 1.0)
        declare_float(self, "tilt_floor_deg", 0.5)
        declare_float(self, "heading_bias_dps", 0.05)
        # heading sources
        self.declare_parameter("position_topic", "/navera/position")
        declare_float(self, "course_sigma_deg", 10.0)
        declare_float(self, "course_min_speed_mps", 5.0)
        self.declare_parameter("vision_status_topic", "/day/day_status")
        self.declare_parameter("vision_meta_topic", "/day/frame_meta")
        self.declare_parameter("vision_min_inliers", 20)
        declare_float(self, "vision_heading_sigma_deg", 2.0)

        p = lambda n: self.get_parameter(n).value          # noqa: E731
        self.source = str(p("source")).strip().lower()
        if self.source not in ("live", "replay"):
            raise ValueError(f"source {self.source!r}: expected 'live' or 'replay'")
        self.frame_id, self.image_frame_id = str(p("frame_id")), str(p("image_frame_id"))
        R = mount_rotation(str(p("mount_axes")), float(p("mount_roll_deg")), float(p("mount_pitch_deg")),
                           float(p("mount_yaw_deg")))
        dec = max(1, int(p("decimation")))
        cal_path = str(p("calibration_file")).strip() or IMU_CALIBRATION
        stream = ImuStream(R, dec, load_imu_calibration(cal_path), bias_at_rest=bool(p("bias_at_rest")))
        flt = AttitudeFilter(kp=float(p("kp")), ki=float(p("ki")), acc_gate_g=float(p("acc_gate_g")),
                             turn_gate_dps=float(p("turn_gate_dps")), tilt_floor_deg=float(p("tilt_floor_deg")),
                             heading_bias_dps=float(p("heading_bias_dps")))
        self.course = GpsCourse(min_speed_mps=float(p("course_min_speed_mps")),
                                course_sigma_deg=float(p("course_sigma_deg")))
        lenses, self.lens_src = load_lenses(str(p("lens_file")).strip())
        self.view = NadirView(lenses, R, float(p("view_hfov_deg")), int(p("view_width")), int(p("view_height")))
        self.kit = Insta360Kit(stream, flt, self.view, speed_at=self.course.speed,
                               exposure_lag_ms=float(p("exposure_lag_ms")))
        self.gyro_cov = covariance_diag(math.radians(float(p("gyro_sample_std_dps"))), dec)
        self.accel_cov = covariance_diag(float(p("accel_sample_std_g")) * G, dec)
        self.min_period = 1.0 / max(1e-3, float(p("max_fps")))
        self.lost_exit_s = float(p("camera_lost_exit_s"))
        self.min_inliers = int(p("vision_min_inliers"))
        self.vision_sigma = float(p("vision_heading_sigma_deg"))

        self.pub_imu = self.create_publisher(Imu, str(p("imu_topic")), IMU_QOS)
        self.pub_img = self.create_publisher(Image, str(p("image_topic")), IMG_QOS)
        self.pub_status = self.create_publisher(String, str(p("status_topic")), 10)
        cb = MutuallyExclusiveCallbackGroup()
        self.create_subscription(PositionEstimate, str(p("position_topic")), self._on_position, 10, callback_group=cb)
        self._metas = {}                                       # frame_id -> meta (the last 64)
        self.create_subscription(String, str(p("vision_meta_topic")), self._on_meta, 10, callback_group=cb)
        self.create_subscription(String, str(p("vision_status_topic")), self._on_vision, 10, callback_group=cb)

        self.published = self.frames = self.vision_sets = self.vision_refused = 0
        self._last_state = None
        self._last_frame_pub = 0.0
        self._lost_since = None
        self._stop = threading.Event()
        self.finished = threading.Event()
        self._usb = None
        self._lock = threading.Lock()
        warn = self.view.warning()
        self.get_logger().info(
            f"Insta360 kit ({self.source}): IMU+attitude -> {p('imu_topic')}, nadir view {self.view.width}x"
            f"{self.view.height} {self.view.hfov_deg:.0f} deg -> {p('image_topic')}; mount_axes {p('mount_axes')} "
            f"trim {p('mount_roll_deg')}/{p('mount_pitch_deg')}/{p('mount_yaw_deg')} deg; view centre "
            f"{self.view.centre_lens} lens {self.view.centre_theta_deg} deg off axis, coverage "
            f"{self.view.coverage:.0%}; lens {self.lens_src}; IMU calibration {cal_path}")
        if warn:
            self.get_logger().warn(f"day view: {warn}")
        if self.lens_src.startswith("first guess"):
            self.get_logger().warn("no lens calibration file: the view is only roughly straight — copy the "
                                   "calibrated lens file to /var/lib/navera/insta360_lens.json")
        threading.Thread(target=self._frames_loop, daemon=True).start()
        if self.source == "replay":
            path = str(p("replay_path")).strip()
            if not path:
                raise ValueError("source 'replay' needs replay_path (a raw folder or a raw360_NNNN.bin file)")
            args = (path, float(p("replay_rate")), str(p("replay_clock")), bool(p("replay_loop")))
            threading.Thread(target=self._replay, args=args, daemon=True).start()
        else:
            self._usb = UsbImuSource(self._on_packet)
        self.create_timer(STATUS_PERIOD_S, self._status)
        self._last_log = 0.0

    # ── packets ───────────────────────────────────────────────────────────
    def _on_packet(self, arrival: float, packet: bytes) -> None:
        for s, st in self.kit.feed(arrival, packet):
            self.pub_imu.publish(self._imu_msg(s, st))
            self.published += 1
            self._last_state = st

    def _imu_msg(self, s, st) -> Imu:
        m = Imu()
        m.header.stamp.sec, m.header.stamp.nanosec = divmod(int(round(s.t * 1e9)), 1_000_000_000)
        m.header.frame_id = self.frame_id
        m.orientation.x, m.orientation.y, m.orientation.z, m.orientation.w = (float(v) for v in st.q)
        m.orientation_covariance = [float(v) for v in st.covariance()]
        m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z = (float(v) for v in s.gyro)
        m.linear_acceleration.x, m.linear_acceleration.y, m.linear_acceleration.z = (float(v) for v in s.accel)
        m.angular_velocity_covariance = self.gyro_cov
        m.linear_acceleration_covariance = self.accel_cov
        return m

    def _frames_loop(self) -> None:
        from cv_bridge import CvBridge
        bridge = CvBridge()
        while not self._stop.is_set():
            for fr in self.kit.wait_frames(0.5):
                now = time.monotonic()
                if now - self._last_frame_pub < self.min_period:
                    continue
                self._last_frame_pub = now
                msg = bridge.cv2_to_imgmsg(fr.image, "bgr8")
                msg.header.stamp.sec, msg.header.stamp.nanosec = divmod(int(round(fr.t * 1e9)), 1_000_000_000)
                msg.header.frame_id = self.image_frame_id
                self.pub_img.publish(msg)
                self.frames += 1

    def _replay(self, path: str, rate: float, clock: str, loop: bool) -> None:
        try:
            for t, pkt in replay_all(path, rate, clock, loop, stop=self._stop):
                self._on_packet(t, pkt)
            time.sleep(1.0)                                    # the last frames reach the decoder
            self.get_logger().info(f"replay finished: {self.published} IMU samples, {self.frames} frames")
        except Exception as e:
            self.get_logger().error(f"replay {path}: {e}")
        self.finished.set()

    # ── heading sources ───────────────────────────────────────────────────
    def _on_position(self, m: PositionEstimate) -> None:
        if m.source != PositionEstimate.SOURCE_GPS:
            return
        if not m.valid or m.mode != PositionEstimate.MODE_MEASURED:
            self.course.clear()
            return
        st = m.sensor_stamp if (m.sensor_stamp.sec or m.sensor_stamp.nanosec) else m.header.stamp
        t = st.sec + st.nanosec * 1e-9
        if t <= 0:
            return
        with self.kit._lock:
            self.course.add_fix(t, float(m.latitude), float(m.longitude))
            r = self.course.maybe_set(self.kit.attitude)
        if r is not None:
            self.get_logger().info(f"heading set from the GPS course: {r[0]:.1f} deg (+-{r[1]:.1f})",
                                   throttle_duration_sec=30.0)

    def _on_meta(self, m: String) -> None:
        try:
            d = json.loads(m.data)
            self._metas[int(d["frame_id"])] = d
        except (ValueError, KeyError, TypeError):
            return
        while len(self._metas) > 64:
            self._metas.pop(next(iter(self._metas)))

    def _on_vision(self, m: String) -> None:
        try:
            st = json.loads(m.data)
            meta = self._metas.get(int(st.get("frame_id")))
        except (ValueError, TypeError):
            return
        if meta is None:
            return
        v = vision_heading(meta, st, self.min_inliers)
        if v is None:
            return
        t, top = v
        with self.kit._lock:
            flt = self.kit.attitude
            R = flt.matrix_at(t)
            if R is None:
                return
            ok = flt.set_heading(t, (top - frame_top_offset_deg(R)) % 360.0, self.vision_sigma, "vision")
        if ok:
            self.vision_sets += 1
        else:
            self.vision_refused += 1

    # ── health ────────────────────────────────────────────────────────────
    def _status(self) -> None:
        st, k, now = self._last_state, self.kit, time.time()
        err = self._usb.error if self._usb is not None else None
        if err and err.startswith("camera lost"):
            self._lost_since = self._lost_since or now
            if now - self._lost_since > self.lost_exit_s:
                self.get_logger().fatal(f"{err} — exiting so the service restarts and opens the camera again")
                self._stop.set()
                self.context.try_shutdown()
                return
        else:
            self._lost_since = None
        imu_age = self._usb.imu_age() if self._usb is not None else None
        d = {"source": self.source, "imu_samples": self.published, "frames": self.frames,
             "imu_age_s": None if imu_age is None or not math.isfinite(imu_age) else round(imu_age, 2),
             "clock_offset_s": k.stream.clock.offset, "clock_resets": k.stream.clock.resets,
             "gyro_bias_dps": [round(math.degrees(b), 4) for b in k.stream.bias.bias],
             "bias_at_rest_updates": k.stream.bias.updates,
             "keyframes": k.keyframes, "decoded": k.decoded, "decode_errors": k.decode_errors,
             "view": {"coverage": round(self.view.coverage, 3), "centre_lens": self.view.centre_lens,
                      "centre_theta_deg": self.view.centre_theta_deg, "warning": self.view.warning(),
                      "lens_file": self.lens_src},
             "course_sets": self.course.sets, "vision_sets": self.vision_sets, "vision_refused": self.vision_refused,
             "error": err or k.last_error}
        if st is not None:
            d.update(roll_deg=round(st.roll_deg, 2), pitch_deg=round(st.pitch_deg, 2),
                     tilt_sigma_deg=round(st.tilt_sigma_deg, 2), still=st.still, accel_used=st.accel_used,
                     heading_deg=round(st.heading_deg, 1) if math.isfinite(st.heading_sigma_deg) else None,
                     heading_sigma_deg=round(st.heading_sigma_deg, 1) if math.isfinite(st.heading_sigma_deg) else None,
                     heading_source=st.heading_source)
        self.pub_status.publish(String(data=json.dumps(d)))
        if now - self._last_log > LOG_PERIOD_S:
            self._last_log = now
            att_txt = (f"roll {st.roll_deg:.1f} pitch {st.pitch_deg:.1f} (+-{st.tilt_sigma_deg:.1f}) heading "
                       f"{d.get('heading_deg')} ({st.heading_source}); ") if st else "no attitude yet; "
            self.get_logger().info(
                f"{self.published} IMU samples, {self.frames} frames ({k.keyframes} key frames, {k.decode_errors} "
                f"decode errors); {att_txt}clock offset {k.stream.clock.offset}"
                + (f"; {d['error']}" if d["error"] else ""))

    def close(self) -> None:
        self._stop.set()
        if self._usb is not None:
            self._usb.close()


def main(args=None):
    die_with_parent()
    rclpy.init(args=args)
    node = Insta360Node()
    exit_at_end = bool(node.get_parameter("exit_at_end").value)
    ex = MultiThreadedExecutor(num_threads=2)
    ex.add_node(node)
    try:
        while rclpy.ok():
            ex.spin_once(timeout_sec=0.2)
            if exit_at_end and node.finished.is_set():
                break
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.close()
        time.sleep(0.1)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
