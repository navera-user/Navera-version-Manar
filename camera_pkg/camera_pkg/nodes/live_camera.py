#!/usr/bin/env python3
"""
live_camera.py — NAVERA live camera: real frames with the data vision needs.

Image input (parameter `input`):
    usb   a USB camera (V4L2), e.g. the Insta360 ONE R in webcam mode: /dev/videoN
    csi   a CSI camera through GStreamer (nvarguscamerasrc)
    ros   any sensor_msgs/Image topic (`input_topic`): the vehicle's own camera

For each frame published, at the instant it was taken (grab time - capture_latency_s):
    attitude   from `imu_topic` (sensor_msgs/Imu, body ENU): NAVERA's BNO085, or the
               vehicle's IMU relayed by vehicle_link / remapped from the vehicle's ROS
    altitude   height above ground (navera_common.altitude): `altitude_topic`
               (sensor_msgs/Range: rangefinder or the vehicle's AGL), the image (map
               matches, `vision_altitude_topic`) carried by the vehicle's height above
               home (`relative_altitude_topic`, barometer) or the GPS altitude
    GPS        `gps_topic` (NavSatFix), recorded in the meta for evaluation only
The frame is undistorted (calibration file from navera_tools/calibrate_camera.py, or
an ideal lens of `camera_hfov_deg`) and straightened to a level straight-down view
(navera_common.frame_builder), then published like camera_publisher does:
    <ns>/image_raw, <ns>/frame_meta (JSON), <ns>/camera_info
with the same start gate (<ns>/start), localizer handshake (`ready_topic`) and
back-pressure (`ack_topic`): the NEWEST frame is sent when the localizer is free,
never a queue of old ones.
"""
import json
import math
import threading
import time

import numpy as np
import rclpy
from navera_common import state_store
from navera_common.altitude import AltitudeEstimator
from navera_common.camera_model import CameraModel
from navera_common.frame_builder import FrameBuilder
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from navera_common.sensor_history import History, slerp
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from geometry_msgs.msg import PointStamped
from sensor_msgs.msg import CameraInfo, Image, Imu, NavSatFix, NavSatStatus, Range
from std_msgs.msg import Bool, Int32, String

LATCHED = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)


def stamp_s(stamp) -> float:
    return stamp.sec + stamp.nanosec * 1e-9


class LiveCamera(Node):
    def __init__(self, **kwargs):
        super().__init__("live_camera", **kwargs)
        self.declare_parameter("camera_type", "day")
        self.declare_parameter("input", "usb")                 # usb | csi | gst | ros
        # input gst: any GStreamer pipeline ending in "appsink name=sink" giving BGR frames
        # (an IP/RTSP camera, a gimbal's video stream...)
        self.declare_parameter("gst_pipeline", "")
        self.declare_parameter("device", "/dev/video0")
        self.declare_parameter("input_topic", "/vehicle/camera/image_raw")
        self.declare_parameter("width", 1920)
        self.declare_parameter("height", 1080)
        declare_float(self, "fps", 1.0)                         # frames offered to the localizer, max
        declare_float(self, "capture_latency_s", 0.0)           # exposure → grab delay (measure it)
        self.declare_parameter("calibration_file", "")
        declare_float(self, "camera_hfov_deg", float("nan"))    # ideal lens when no calibration file
        declare_float(self, "mount_roll_deg", 0.0)
        declare_float(self, "mount_pitch_deg", 0.0)
        declare_float(self, "mount_yaw_deg", 0.0)
        declare_float(self, "max_tilt_deg", 45.0)
        declare_float(self, "max_rate_dps", 30.0)              # fixed camera: rotation rate limit
        self.declare_parameter("gimbal", False)                 # camera held level by a stabiliser
        # frames with no attitude at exposure are marked unusable (fixed camera); false only
        # for an installation with no attitude source at all
        self.declare_parameter("require_attitude", True)
        self.declare_parameter("imu_topic", "/navera/sensors/imu")
        self.declare_parameter("attitude_source", "imu")        # label recorded in the meta
        self.declare_parameter("gps_topic", "/navera/sensors/gps_fix")
        self.declare_parameter("altitude_topic", "/navera/sensors/altitude_agl")
        self.declare_parameter("vision_altitude_topic", "/navera/vision/altitude_agl")
        # the vehicle's height above home (barometer), from vehicle_link: survives GPS loss
        self.declare_parameter("relative_altitude_topic", "/navera/vehicle/relative_alt")
        declare_float(self, "ground_altitude_m", float("nan"))  # site elevation (else first fix)
        declare_float(self, "measured_altitude_sigma_m", 1.0)   # 1-sigma of the altitude_topic source
        self.declare_parameter("start_paused", False)
        self.declare_parameter("wait_for_ready", True)
        self.declare_parameter("ready_topic", "/day/localizer_ready")
        self.declare_parameter("ack_topic", "frame_done")
        declare_float(self, "ack_timeout_s", 10.0)
        self.declare_parameter("frame_id", "camera_link")
        p = lambda n: self.get_parameter(n).value               # noqa: E731

        self.input, self.w, self.h = p("input"), int(p("width")), int(p("height"))
        self.period = 1.0 / max(float(p("fps")), 1e-3)
        self.latency_s = float(p("capture_latency_s"))
        cam = self._camera_model(p("calibration_file"), float(p("camera_hfov_deg")))
        self.builder = FrameBuilder(cam, (p("mount_roll_deg"), p("mount_pitch_deg"), p("mount_yaw_deg")),
                                    float(p("max_tilt_deg")), p("camera_type"), bool(p("gimbal")),
                                    bool(p("require_attitude")), float(p("max_rate_dps")))
        self.attitude_source, self.frame_id = p("attitude_source"), p("frame_id")
        self.measured_sigma_m = float(p("measured_altitude_sigma_m"))
        self.att = History(maxlen=4000, max_gap_s=0.2, interp=slerp)
        self._last_q, self._same, self._frozen_n = None, 0, 50     # 1 s at 50 Hz
        self._tilt_log = []                     # (time, too tilted) of the last minute's frames
        self.gps = History(maxlen=600, max_gap_s=1.5)
        g = float(p("ground_altitude_m"))
        # the ground taken at power-on survives a restart of this service (12 h, same site)
        self.alt = AltitudeEstimator(ground_altitude_m=g if math.isfinite(g) else None,
                                     saved_ground=state_store.load("ground", 12 * 3600.0),
                                     on_ground=lambda d: state_store.save("ground", d))

        qos_img = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)
        self.pub_img = self.create_publisher(Image, "image_raw", qos_img)
        self.pub_meta = self.create_publisher(String, "frame_meta", 10)
        self.pub_info = self.create_publisher(CameraInfo, "camera_info", qos_img)
        # sensors in their own callback group: converting images never delays them
        sensors = MutuallyExclusiveCallbackGroup()
        self.create_subscription(Imu, p("imu_topic"), self._on_imu, 100, callback_group=sensors)
        self.create_subscription(NavSatFix, p("gps_topic"), self._on_gps, 10, callback_group=sensors)
        self.create_subscription(Range, p("altitude_topic"), self._on_alt, 10, callback_group=sensors)
        self.create_subscription(Range, p("vision_altitude_topic"), self._on_vision_alt, 10, callback_group=sensors)
        self.create_subscription(PointStamped, p("relative_altitude_topic"),
                                 lambda m: self.alt.add_relative(stamp_s(m.header.stamp), m.point.z),
                                 10, callback_group=sensors)
        self.create_subscription(Int32, p("ack_topic"), self._on_ack, 10)
        self._ready = threading.Event()
        self._go = threading.Event()
        if not bool(p("wait_for_ready")):
            self._ready.set()
        if not bool(p("start_paused")):
            self._go.set()
        self.create_subscription(Bool, p("ready_topic"), lambda m: self._ready.set() if m.data else None, LATCHED)
        self.create_subscription(Bool, "start", lambda m: self._go.set() if m.data else self._go.clear(), LATCHED)
        self.ack_timeout_s = float(p("ack_timeout_s"))
        self._awaiting, self._acked = None, threading.Event()
        self._acked.set()

        self._latest = None                                     # (raw image, exposure time s)
        # camera inputs: frames are grabbed (kept current, not decoded) at the camera's rate
        # and only the one sent is decoded: a 1080p MJPEG decode measured 51 ms on the Orin
        # Nano (under load) — 30 fps decoded was ~1.5 CPU cores for one frame used a second
        self._want = threading.Event()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.count = 0
        if self.input == "ros":
            # sensor-data QoS (best effort): accepts both best-effort and reliable camera publishers
            self.create_subscription(Image, p("input_topic"), self._on_image, qos_profile_sensor_data,
                                     callback_group=MutuallyExclusiveCallbackGroup())
        else:
            threading.Thread(target=self._grab_loop, args=(p("device"),), daemon=True).start()
        self._sender = threading.Thread(target=self._send_loop, daemon=True)
        self._sender.start()
        self.get_logger().info(
            f"live camera: input={self.input} {self.w}x{self.h}, lens "
            f"{'calibrated (' + cam.model + ')' if p('calibration_file') else 'ideal'}, "
            f"published field of view {cam.out_hfov_deg:.1f} deg, mount "
            f"{[p('mount_roll_deg'), p('mount_pitch_deg'), p('mount_yaw_deg')]}, attitude from {p('imu_topic')}")

    # ── setup ─────────────────────────────────────────────────────────────
    def _camera_model(self, calib_file: str, hfov: float) -> CameraModel:
        if calib_file:
            import yaml
            with open(calib_file) as f:
                d = yaml.safe_load(f)
            cam = CameraModel.from_calibration(d)
            if cam.size != (self.w, self.h):
                raise ValueError(f"calibration {calib_file} is for {cam.size[0]}x{cam.size[1]}, "
                                 f"the camera is set to {self.w}x{self.h}")
            if self.input == "usb" and d.get("camera_id"):
                from navera_common.vehicle import camera_identity
                here = camera_identity(str(self.get_parameter("device").value))
                if here is not None and here != d["camera_id"]:
                    raise ValueError(f"calibration {calib_file} was made with camera {d['camera_id']}, "
                                     f"this one is {here}: calibrate this camera")
            return cam
        if not math.isfinite(hfov):
            raise ValueError("set calibration_file (navera_tools/calibrate_camera.py) or camera_hfov_deg")
        self.get_logger().warn("no calibration file: the lens is taken as distortion-free — "
                               "calibrate it (navera_tools/calibrate_camera.py) before a real test")
        return CameraModel.ideal(hfov, (self.w, self.h))

    # ── sensor inputs ─────────────────────────────────────────────────────
    def _on_imu(self, m: Imu):
        q = (m.orientation.x, m.orientation.y, m.orientation.z, m.orientation.w)
        if not (all(math.isfinite(c) for c in q) and abs(sum(c * c for c in q) - 1.0) < 0.1):
            return
        # a real attitude always carries a little noise: the very same value for a second
        # means a frozen sensor or a stuck relay — not an attitude to straighten with
        self._same = self._same + 1 if q == self._last_q else 0
        self._last_q = q
        if self._same >= self._frozen_n:
            self.get_logger().error("attitude frozen (identical samples): frames not used until it moves",
                                    throttle_duration_sec=10.0)
            return
        self.att.add(stamp_s(m.header.stamp), q)

    def _on_gps(self, m: NavSatFix):
        if m.status.status >= NavSatStatus.STATUS_FIX and math.isfinite(m.latitude):
            t = stamp_s(m.header.stamp)
            self.gps.add(t, (m.latitude, m.longitude))
            self.alt.add_gps(t, m.altitude, m.latitude, m.longitude)

    def _on_alt(self, m: Range):
        if m.min_range < m.range < m.max_range:                 # at a limit = no echo (REP 117: ±inf)
            self.alt.add_measured(stamp_s(m.header.stamp), m.range, self.measured_sigma_m)

    def _on_vision_alt(self, m: Range):
        # field_of_view carries the 1-sigma (m) of the image-measured height
        self.alt.add_vision(stamp_s(m.header.stamp), m.range, m.field_of_view or 5.0)

    def _on_ack(self, m: Int32):
        if self._awaiting is not None and m.data == self._awaiting:
            self._acked.set()

    # ── image inputs ──────────────────────────────────────────────────────
    def _grab_loop(self, device: str):
        import cv2
        if self.input == "gst":
            from camera_pkg.gst_capture import GstCapture
            cap = GstCapture(str(self.get_parameter("gst_pipeline").value))
        elif self.input == "csi":
            # through GStreamer directly: the box's OpenCV has no GStreamer support.
            # device: the CSI sensor id ("0", "1"), default 0
            from camera_pkg.gst_capture import GstCapture, csi_pipeline
            sensor = int(device) if str(device).isdigit() else 0
            cap = GstCapture(csi_pipeline(self.w, self.h, sensor))
        else:
            cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.h)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)                 # newest frame, not a queue
        if not cap.isOpened():
            self.get_logger().fatal(f"cannot open the camera ({device if self.input == 'usb' else 'CSI'}) — "
                                    "exiting so the service restarts")
            self.context.try_shutdown()
            return
        fails = 0
        while not self._stop.is_set():
            ok = cap.grab()                                     # paced by the camera itself
            t = self.get_clock().now().nanoseconds * 1e-9 - self.latency_s
            frame = None
            if ok and self._want.is_set():
                ok, frame = cap.retrieve()                      # decode only the frame to send
            elif ok:
                fails = 0
                continue
            if not ok or frame is None:
                fails += 1
                if fails > 50:
                    self.get_logger().fatal("the camera stopped sending frames — exiting so the service restarts")
                    self.context.try_shutdown()
                    return
                time.sleep(0.05)
                continue
            fails = 0
            if frame.shape[1] != self.w or frame.shape[0] != self.h:
                self.get_logger().error(f"camera gives {frame.shape[1]}x{frame.shape[0]}, set to {self.w}x{self.h}",
                                        throttle_duration_sec=10.0)
                continue
            with self._lock:
                self._latest = (frame, t)
            self._want.clear()
        cap.release()

    def _on_image(self, m: Image):
        from cv_bridge import CvBridge
        img = CvBridge().imgmsg_to_cv2(m, "bgr8")
        if img.shape[1] != self.w or img.shape[0] != self.h:
            self.get_logger().error(f"{self.get_parameter('input_topic').value} is {img.shape[1]}x{img.shape[0]}, "
                                    f"set to {self.w}x{self.h}", throttle_duration_sec=10.0)
            return
        with self._lock:
            self._latest = (img, stamp_s(m.header.stamp) - self.latency_s)

    # ── output ────────────────────────────────────────────────────────────
    def _send_loop(self):
        from cv_bridge import CvBridge
        bridge = CvBridge()
        requested = False
        while not self._stop.is_set():
            if not (self._ready.is_set() and self._go.is_set()):
                time.sleep(0.1)
                continue
            if not self._acked.wait(self.ack_timeout_s) and self._awaiting is not None:
                self.get_logger().warn(f"no ack for frame {self._awaiting} in {self.ack_timeout_s:.0f} s — sending the next")
            t0 = time.monotonic()
            if self.input != "ros" and not requested:
                # camera inputs: a frame decoded for an earlier request (while this loop
                # slept for the frame rate) is up to one period old — ask for a new one
                with self._lock:
                    self._latest = None
                self._want.set()
                requested = True
            with self._lock:
                item, self._latest = self._latest, None
            if item is None:
                time.sleep(0.02)
                continue
            requested = False
            raw, t = item
            out, meta = self.builder.build(raw, self.count, int(t * 1e9), self.att.at(t), self.attitude_source,
                                           self.alt.estimate(t), self.gps.at(t),
                                           time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)),
                                           self._rate_dps(t))
            msg = bridge.cv2_to_imgmsg(np.ascontiguousarray(out), "bgr8")
            msg.header.stamp.sec, msg.header.stamp.nanosec = int(t), int((t % 1) * 1e9)
            meta["image_stamp_ns"] = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
            msg.header.frame_id = self.frame_id
            self._awaiting = self.count
            self._acked.clear()
            self.pub_img.publish(msg)
            self.pub_meta.publish(String(data=json.dumps(meta)))
            self.pub_info.publish(self._camera_info(msg.header))
            self._check_tilt(t, str(meta.get("reason", "")).startswith("camera tilted"))
            if self.count % 30 == 0:
                self.get_logger().info(
                    f"frame {self.count}: altitude {meta.get('altitude_m')} m ({meta.get('altitude_source')}), "
                    f"tilt {meta.get('tilt_deg', '?')} deg, attitude {meta['attitude_source']}"
                    + ("" if meta["usable"] else f" — {meta['reason']}"))
            self.count += 1
            time.sleep(max(0.0, self.period - (time.monotonic() - t0)))

    def _rate_dps(self, t):
        """The vehicle's rotation rate around the exposure (deg/s, from the attitude 0.2 s
        before it), or None when the attitude is not known then."""
        a, b = self.att.at(t - 0.2), self.att.at(t)
        if a is None or b is None:
            return None
        dot = min(1.0, abs(sum(x * y for x, y in zip(a, b))))
        return math.degrees(2.0 * math.acos(dot)) / 0.2

    def _check_tilt(self, t, too_tilted):
        """A fixed camera too tilted for a large part of the last minute: say why vision is
        missing positions, and what to change (gimbal, slower cruise)."""
        self._tilt_log = [x for x in self._tilt_log if t - x[0] <= 60.0] + [(t, too_tilted)]
        n = len(self._tilt_log)
        bad = sum(1 for _, b in self._tilt_log if b)
        if n >= 20 and bad > 0.3 * n:
            self.get_logger().error(f"{100 * bad // n} % of the last minute's frames were too tilted to use: "
                                    f"the vehicle leans too much for a fixed camera — fit a gimbal or fly slower",
                                    throttle_duration_sec=30.0)

    def _camera_info(self, header) -> CameraInfo:
        K = self.builder.cam.K_out
        ci = CameraInfo()
        ci.header, ci.width, ci.height = header, self.w, self.h
        ci.distortion_model, ci.d = "plumb_bob", [0.0] * 5           # published images are undistorted
        ci.k = [float(v) for v in K.ravel()]
        ci.r = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        ci.p = [K[0, 0], 0.0, K[0, 2], 0.0, 0.0, K[1, 1], K[1, 2], 0.0, 0.0, 0.0, 1.0, 0.0]
        return ci

    def destroy_node(self):
        self._stop.set()
        self._sender.join(timeout=2.0)
        super().destroy_node()


def main(args=None):
    die_with_parent()
    rclpy.init(args=args)
    node = LiveCamera()
    ex = MultiThreadedExecutor(num_threads=3)
    ex.add_node(node)
    try:
        ex.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
