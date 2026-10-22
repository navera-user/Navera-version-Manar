#!/usr/bin/env python3
"""
live_camera.py — NAVERA live camera: real frames with the data vision needs.

Image input (parameter `input`):
    usb   a USB camera (V4L2), e.g. the Insta360 ONE R in webcam mode: /dev/videoN
    csi   a CSI camera through GStreamer (nvarguscamerasrc)
    ros   any sensor_msgs/Image topic (`input_topic`): the vehicle's own camera
    insta360  the Insta360 kit's straight-down view (camera_pkg insta360_node, which owns the
          camera in USB Android mode): an image topic stamped at the exposure, an ideal lens

For each frame published, at the instant it was taken (grab time - capture_latency_s, and the
day node's in-flight delay estimate on top of it, `delay_topic`: the delay learned against the GPS
also dates the attitude, so a banked plane is straightened with the attitude at the exposure):
    attitude   from `imu_topic` (sensor_msgs/Imu, body ENU): NAVERA's BNO085, or the
               vehicle's IMU relayed by vehicle_link / remapped from the vehicle's ROS
    altitude   height above ground (navera_common.altitude): `altitude_topic`
               (sensor_msgs/Range: rangefinder or the vehicle's AGL), the image (map
               matches, `vision_altitude_topic`) carried by the vehicle's height above
               home (`relative_altitude_topic`, barometer) or the GPS altitude; over
               relief, minus the terrain under the vehicle when the map has a DEM
               (`terrain_dir`: "area" = $DAY_DATASET_DIR/terrain; default off) and the arbiter's
               position (`position_topic`) is known
    GPS        `gps_topic` (NavSatFix), recorded in the meta for evaluation only
The frame is undistorted (calibration file from navera_tools/calibrate_camera.py, or
an ideal lens of `camera_hfov_deg`) and straightened to a level straight-down view
(navera_common.frame_builder), then published like camera_publisher does:
    <ns>/image_raw, <ns>/frame_meta (JSON), <ns>/camera_info
with the same start gate (<ns>/start), localizer handshake (`ready_topic`) and
back-pressure (`ack_topic`): the NEWEST frame is sent when the localizer is free,
never a queue of old ones.

Frozen pictures (D24 / H-01b): a frame whose time does not advance, whose picture is
identical to the previous one, or nearly identical while the IMU / GPS say the vehicle
moved (navera_common.health.FrozenFrameDetector) is published marked unusable ("camera
image frozen: ..."), so no localizer turns it into a position; <ns>/camera_health (JSON)
reports it, and a camera input frozen longer than `frozen_restart_s` exits so the service
restarts and reopens the device. The first new picture ends the freeze.

Camera stall: a camera input (usb / csi / gst) that delivers no frame for
`camera_stall_restart_s` (unplugged, USB reset, stuck driver, stalled stream, or a grab that
never returns) is reported on <ns>/camera_health ("stalled") and the node exits so the service
restarts and reopens it (camera_pkg.grab_watchdog).
"""
import json
import math
import os
import threading
import time

import numpy as np
import rclpy
from navera_common import state_store
from navera_common.qos import SENSOR_QOS
from navera_common.altitude import AltitudeEstimator
from navera_common.camera_model import CameraModel, parse_crop
from navera_common.frame_builder import FrameBuilder
from navera_common.geo import haversine_m
from navera_common.health import FrozenFrameDetector
from camera_pkg.grab_watchdog import GrabWatchdog
from navera_common.lifecycle import die_with_parent
from navera_common.params import declare_float
from navera_common.sensor_history import History, slerp
from navera_common.terrain import Terrain
from navera_msgs.msg import PositionEstimate
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
        self.declare_parameter("input", "usb")                 # usb | csi | gst | ros | insta360
        # input gst: any GStreamer pipeline ending in "appsink name=sink" giving BGR frames
        # (an IP/RTSP camera, a gimbal's video stream...)
        self.declare_parameter("gst_pipeline", "")
        self.declare_parameter("device", "/dev/video0")
        self.declare_parameter("input_topic", "/vehicle/camera/image_raw")
        self.declare_parameter("width", 1920)
        self.declare_parameter("height", 1080)
        declare_float(self, "fps", 1.0)                         # frames offered to the localizer, max
        declare_float(self, "capture_latency_s", 0.0)           # exposure → grab delay (measure it)
        # the day node's camera-delay estimate (navera_common.latency_cal.delay_message): the attitude,
        # altitude and rotation rate are taken correction_s before the stamp. "auto": /day/camera_delay
        # for a day camera, none otherwise; "none": off
        self.declare_parameter("delay_topic", "auto")
        declare_float(self, "max_attitude_shift_s", 3.0)
        self.declare_parameter("calibration_file", "")
        declare_float(self, "camera_hfov_deg", float("nan"))    # ideal lens when no calibration file
        declare_float(self, "mount_roll_deg", 0.0)
        declare_float(self, "mount_pitch_deg", 0.0)
        declare_float(self, "mount_yaw_deg", 0.0)
        declare_float(self, "max_tilt_deg", 45.0)
        declare_float(self, "max_rate_dps", 30.0)              # fixed camera: rotation rate limit
        self.declare_parameter("crop", "")                      # "", top/bottom/left/right, x,y,w,h
        self.declare_parameter("gimbal", False)                 # camera held level by a stabiliser
        # frames with no attitude at exposure are marked unusable (fixed camera); false only
        # for an installation with no attitude source at all
        self.declare_parameter("require_attitude", True)
        self.declare_parameter("imu_topic", "/navera/sensors/imu")
        self.declare_parameter("attitude_source", "imu")        # label recorded in the meta
        # an attitude whose yaw is not a heading (orientation_covariance yaw sigma above this, e.g.
        # the Insta360's gyro yaw before the GPS course or vision set it): the frame is straightened
        # but carries no heading_deg, and the day node uses its gyro-carried vision heading instead
        declare_float(self, "max_heading_sigma_deg", 5.0)
        self.declare_parameter("gps_topic", "/navera/sensors/gps_fix")
        self.declare_parameter("altitude_topic", "/navera/sensors/altitude_agl")
        self.declare_parameter("vision_altitude_topic", "/navera/vision/altitude_agl")
        # the vehicle's height above home (barometer), from vehicle_link: survives GPS loss
        self.declare_parameter("relative_altitude_topic", "/navera/vehicle/relative_alt")
        declare_float(self, "ground_altitude_m", float("nan"))  # site elevation (else first fix)
        # the corridor's DEM stored with the map (prepare_area --dem / mission bundle): "area" = the
        # day area's ($DAY_DATASET_DIR/terrain), a directory, or "none" (default: off until the
        # dead-reckoning regression seen with it on MARS-LVIG AMvalley03 is understood, see
        # docs/VALIDATION_STATUS.md); and where the vehicle is
        self.declare_parameter("terrain_dir", "none")
        self.declare_parameter("position_topic", "/navera/position")
        declare_float(self, "measured_altitude_sigma_m", 1.0)   # 1-sigma of the altitude_topic source
        self.declare_parameter("start_paused", False)
        self.declare_parameter("wait_for_ready", True)
        self.declare_parameter("ready_topic", "/day/localizer_ready")
        self.declare_parameter("ack_topic", "frame_done")
        declare_float(self, "ack_timeout_s", 10.0)
        # frozen pictures: below this mean grey difference a picture counts as unchanged when the
        # vehicle moved (rotation > frozen_motion_deg or travel > frozen_motion_m since the last frame)
        declare_float(self, "frozen_still_diff", 0.5)
        declare_float(self, "frozen_motion_deg", 0.5)
        declare_float(self, "frozen_motion_m", 5.0)
        # a camera input (not a ROS topic) frozen this long exits: systemd restarts and reopens it
        declare_float(self, "frozen_restart_s", 20.0)
        # a camera input that gives no frame this long exits: systemd restarts and reopens it
        declare_float(self, "camera_stall_restart_s", 10.0)
        self.declare_parameter("frame_id", "camera_link")
        p = lambda n: self.get_parameter(n).value               # noqa: E731

        self.input, self.w, self.h = p("input"), int(p("width")), int(p("height"))
        # the part of the picture that looks at the ground (a 360 camera: one lens' half);
        # the calibration, the frames and every size below are of that part
        self.crop = parse_crop(p("crop"), self.w, self.h)
        self.cw, self.ch = (self.crop[2], self.crop[3]) if self.crop else (self.w, self.h)
        self.period = 1.0 / max(float(p("fps")), 1e-3)
        self.latency_s = float(p("capture_latency_s"))
        self.att_shift_s, self.max_att_shift_s = 0.0, float(p("max_attitude_shift_s"))
        from navera_common.delay_monitor import DelayChangeMonitor
        self.delay_mon = DelayChangeMonitor()
        cam = self._camera_model(p("calibration_file"), float(p("camera_hfov_deg")))
        self.builder = FrameBuilder(cam, (p("mount_roll_deg"), p("mount_pitch_deg"), p("mount_yaw_deg")),
                                    float(p("max_tilt_deg")), p("camera_type"), bool(p("gimbal")),
                                    bool(p("require_attitude")), float(p("max_rate_dps")))
        self.attitude_source, self.frame_id = p("attitude_source"), p("frame_id")
        from navera_common.camera_model import mount_identity
        self.mount_ident = mount_identity((p("mount_roll_deg"), p("mount_pitch_deg"), p("mount_yaw_deg")),
                                          p("calibration_file"), cam.out_hfov_deg, self.crop)
        self.measured_sigma_m = float(p("measured_altitude_sigma_m"))
        self.att = History(maxlen=4000, max_gap_s=0.2, interp=slerp)
        self.yaw_sigma = History(maxlen=4000, max_gap_s=0.2)    # deg, from orientation_covariance
        self.max_heading_sigma = float(p("max_heading_sigma_deg"))
        self._last_q, self._same, self._frozen_n = None, 0, 50     # 1 s at 50 Hz
        self._tilt_log = []                     # (time, too tilted) of the last minute's frames
        self.gps = History(maxlen=600, max_gap_s=1.5)
        g = float(p("ground_altitude_m"))
        # the ground taken at power-on survives a restart of this service (12 h, same site)
        self.alt = AltitudeEstimator(ground_altitude_m=g if math.isfinite(g) else None,
                                     saved_ground=state_store.load("ground", 12 * 3600.0),
                                     on_ground=lambda d: state_store.save("ground", d))
        tdir = str(p("terrain_dir")).strip()
        if tdir != "none":
            terrain = Terrain.load(os.environ.get("DAY_DATASET_DIR", "") if tdir in ("", "area") else tdir)
            self.alt.set_terrain(terrain)
            if terrain is not None:
                self.get_logger().info(f"height above ground over relief: DEM {terrain.describe()}")

        qos_img = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST)
        self.pub_img = self.create_publisher(Image, "image_raw", qos_img)
        self.pub_meta = self.create_publisher(String, "frame_meta", 10)
        self.pub_info = self.create_publisher(CameraInfo, "camera_info", qos_img)
        self.pub_health = self.create_publisher(String, "camera_health", LATCHED)
        self.freeze = FrozenFrameDetector(float(p("frozen_still_diff")))
        self.frozen_motion_deg, self.frozen_motion_m = float(p("frozen_motion_deg")), float(p("frozen_motion_m"))
        self.frozen_restart_s = float(p("frozen_restart_s"))
        self.watchdog = GrabWatchdog(float(p("camera_stall_restart_s")))
        self._prev_t = None                                     # exposure of the previous frame sent
        # sensors in their own callback group: converting images never delays them
        sensors = MutuallyExclusiveCallbackGroup()
        # the vehicle's sensors may publish BEST_EFFORT (navera_common.qos)
        self.create_subscription(Imu, p("imu_topic"), self._on_imu, SENSOR_QOS, callback_group=sensors)
        self.create_subscription(NavSatFix, p("gps_topic"), self._on_gps, SENSOR_QOS, callback_group=sensors)
        self.create_subscription(Range, p("altitude_topic"), self._on_alt, SENSOR_QOS, callback_group=sensors)
        self.create_subscription(Range, p("vision_altitude_topic"), self._on_vision_alt, 10, callback_group=sensors)
        self.create_subscription(PointStamped, p("relative_altitude_topic"),
                                 lambda m: self.alt.add_relative(stamp_s(m.header.stamp), m.point.z),
                                 SENSOR_QOS, callback_group=sensors)
        self.create_subscription(PositionEstimate, p("position_topic"), self._on_position, 10,
                                 callback_group=sensors)
        self.create_subscription(Int32, p("ack_topic"), self._on_ack, 10)
        dtopic = str(p("delay_topic")).strip()
        if dtopic == "auto":
            dtopic = "/day/camera_delay" if p("camera_type") == "day" else "none"
        if dtopic not in ("", "none"):
            self.create_subscription(String, dtopic, self._on_delay, LATCHED)
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
        if self.input in ("ros", "insta360"):
            # sensor-data QoS (best effort): accepts both best-effort and reliable camera publishers;
            # the Insta360 kit's own reliable view (2 frames/s, a lost 3 MB frame is a lost fix)
            qos = qos_img if self.input == "insta360" else qos_profile_sensor_data
            self.create_subscription(Image, p("input_topic"), self._on_image, qos,
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
            if cam.size != (self.cw, self.ch):
                raise ValueError(f"calibration {calib_file} is for {cam.size[0]}x{cam.size[1]}, "
                                 f"the camera gives {self.cw}x{self.ch}"
                                 + (f" (crop {list(self.crop)})" if self.crop else ""))
            if list(d.get("crop") or []) != list(self.crop or []):
                raise ValueError(f"calibration {calib_file} was made with crop {d.get('crop')}, the camera "
                                 f"uses {list(self.crop) if self.crop else 'the whole picture'}: calibrate again")
            if self.input == "usb" and d.get("camera_id"):
                from navera_common.vehicle import camera_identity
                here = camera_identity(str(self.get_parameter("device").value))
                if here is not None and here != d["camera_id"]:
                    raise ValueError(f"calibration {calib_file} was made with camera {d['camera_id']}, "
                                     f"this one is {here}: calibrate this camera")
            if self.latency_s == 0.0 and d.get("latency_s"):
                # measured with the camera (navera_tools/bench/camera_latency.py --calib):
                # NAVERA_CAMERA_LATENCY_S, when set, wins
                self.latency_s = float(d["latency_s"])
                self.get_logger().info(f"camera delay {self.latency_s:.3f} s (from {calib_file})")
            return cam
        if not math.isfinite(hfov):
            raise ValueError("set calibration_file (navera_tools/calibrate_camera.py) or camera_hfov_deg")
        if self.input == "insta360":                            # a computed view: an ideal lens by construction
            return CameraModel.ideal(hfov, (self.cw, self.ch))
        self.get_logger().warn("no calibration file: the lens is taken as distortion-free — "
                               "calibrate it (navera_tools/calibrate_camera.py) before a real test")
        return CameraModel.ideal(hfov, (self.cw, self.ch))

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
        v = float(m.orientation_covariance[8])
        self.yaw_sigma.add(stamp_s(m.header.stamp), math.degrees(math.sqrt(v)) if v > 0 and math.isfinite(v) else 0.0)

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

    def _on_position(self, m: PositionEstimate):
        """The arbiter's position (GPS, or vision after its loss): where the DEM is read."""
        if not m.valid or m.position_covariance_type == PositionEstimate.COVARIANCE_TYPE_UNKNOWN:
            return
        cov = list(m.position_covariance)
        st = m.sensor_stamp if (m.sensor_stamp.sec or m.sensor_stamp.nanosec) else m.header.stamp
        self.alt.add_position(stamp_s(st), m.latitude, m.longitude, math.sqrt(max(cov[0], cov[4], 0.0)))

    def _on_delay(self, m: String):
        """The day node's camera-delay estimate: the attitude is taken correction_s before the stamp."""
        from navera_common.latency_cal import attitude_shift_s
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        shift = attitude_shift_s(d, self.latency_s, self.max_att_shift_s)
        if abs(shift - self.att_shift_s) >= 0.05:
            self.get_logger().info(f"attitude taken {shift:+.2f} s before the frame stamp (the day node's camera "
                                   f"delay {d.get('delay_s')} +- {d.get('sigma_s')} s)")
        self.att_shift_s = shift

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
        self.watchdog.start(time.monotonic())
        while not self._stop.is_set():
            ok = cap.grab()                                     # paced by the camera itself
            t = self.get_clock().now().nanoseconds * 1e-9 - self.latency_s
            if ok:
                self._watch_delay(cap)
            frame = None
            if ok and self._want.is_set():
                ok, frame = cap.retrieve()                      # decode only the frame to send
            elif ok:
                fails = 0
                self.watchdog.ok(time.monotonic())
                continue
            if not ok or frame is None:
                fails += 1
                stalled = self.watchdog.stalled(time.monotonic())
                if fails > 50 or stalled:
                    self._camera_stalled(stalled or f"{fails} failed grabs")
                    return
                time.sleep(0.05)
                continue
            fails = 0
            self.watchdog.ok(time.monotonic())
            if frame.shape[1] != self.w or frame.shape[0] != self.h:
                self.get_logger().error(f"camera gives {frame.shape[1]}x{frame.shape[0]}, set to {self.w}x{self.h}",
                                        throttle_duration_sec=10.0)
                continue
            if self.crop:
                x, y, w, h = self.crop
                frame = frame[y:y + h, x:x + w]
            with self._lock:
                self._latest = (frame, t)
            self._want.clear()
        cap.release()

    def _watch_delay(self, cap) -> None:
        """Feed navera_common.delay_monitor with the frame's (arrival, source stamp): the V4L2
        buffer timestamp (CLOCK_MONOTONIC) or the GStreamer buffer PTS (running time). A change
        of the queueing after the source stamps the frame is a change of the camera delay."""
        try:
            if isinstance(getattr(cap, "stamps", None), tuple):
                self.delay_mon.add(*cap.stamps)
            elif self.input == "usb":
                import cv2
                ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                if ms and ms > 0:
                    self.delay_mon.add(time.monotonic(), ms / 1000.0)
        except Exception:                                   # noqa: BLE001 — the monitor is optional
            pass

    def _on_image(self, m: Image):
        from cv_bridge import CvBridge
        img = CvBridge().imgmsg_to_cv2(m, "bgr8")
        if img.shape[1] != self.w or img.shape[0] != self.h:
            self.get_logger().error(f"{self.get_parameter('input_topic').value} is {img.shape[1]}x{img.shape[0]}, "
                                    f"set to {self.w}x{self.h}", throttle_duration_sec=10.0)
            return
        if self.crop:
            x, y, w, h = self.crop
            img = img[y:y + h, x:x + w]
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
            if self.input not in ("ros", "insta360") and not requested:
                # camera inputs: a frame decoded for an earlier request (while this loop
                # slept for the frame rate) is up to one period old — ask for a new one
                with self._lock:
                    self._latest = None
                self._want.set()
                requested = True
            with self._lock:
                item, self._latest = self._latest, None
            if item is None:
                # a grab that never returns is seen here (the grab thread cannot judge itself)
                stalled = self.watchdog.stalled(time.monotonic()) if self.input not in ("ros", "insta360") else None
                if stalled:
                    self._camera_stalled(stalled)
                    break
                time.sleep(0.02)
                continue
            requested = False
            raw, t = item
            frozen = self._check_frozen(raw, t)
            if self._stop.is_set():
                break
            # the exposure by the day node's delay estimate: the attitude to straighten with is then
            # (the stamp stays the camera's: the day node moves it by the same correction)
            shift = self.att_shift_s
            te = t - shift
            out, meta = self.builder.build(raw, self.count, int(t * 1e9), self.att.at(te), self.attitude_source,
                                           self.alt.estimate(te), self.gps.at(t),
                                           time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)),
                                           self._rate_dps(te))
            msg = bridge.cv2_to_imgmsg(np.ascontiguousarray(out), "bgr8")
            msg.header.stamp.sec, msg.header.stamp.nanosec = int(t), int((t % 1) * 1e9)
            meta["image_stamp_ns"] = msg.header.stamp.sec * 1_000_000_000 + msg.header.stamp.nanosec
            self._check_heading(meta, te)
            meta["capture_latency_s"] = self.latency_s          # already subtracted: the localizers' set delay
            meta["attitude_delay_s"] = round(shift, 4)          # attitude taken this long before the stamp
            meta.update(self.mount_ident)                       # what a learned mount calibration belongs to
            meta["delay_monitor"] = self.delay_mon.state()     # the delay's change since start (no GPS needed)
            if self.delay_mon.significant:
                self.get_logger().warn(f"camera delay changed by {self.delay_mon.change_s:+.3f} s since the start "
                                       "(queueing after the camera's stamp)", throttle_duration_sec=30.0)
            if meta.get("utc_time"):
                meta["utc_source"] = "system_clock"         # not a trusted time by itself (celestial, H-08)
            if frozen:
                # never a position from a stale picture: the localizers publish "no fix" with this reason
                meta.update(usable=False, reason=f"camera image frozen: {frozen}")
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

    def _check_heading(self, meta, t):
        """Drop the frame's heading when the attitude's yaw is not a heading (sigma too large)."""
        if meta.get("heading_deg") is None:
            return
        s = self.yaw_sigma.at(t)
        if s is not None and s > self.max_heading_sigma:
            meta.update(heading_deg=None, heading_sigma_deg=round(min(s, 180.0), 1),
                        heading_note=f"attitude yaw sigma {min(s, 180.0):.0f} deg > {self.max_heading_sigma:.0f}: "
                                     "no heading from the attitude (the day node carries the vision heading)")

    def _moved(self, t0, t1):
        """True when the IMU or the GPS says the vehicle moved between two exposures, False when
        both say it did not, None when neither knows.
        """
        if t0 is None:
            return None
        verdicts = []
        a, b = self.att.at(t0), self.att.at(t1)
        if a is not None and b is not None:
            dot = min(1.0, abs(sum(x * y for x, y in zip(a, b))))
            verdicts.append(math.degrees(2.0 * math.acos(dot)) > self.frozen_motion_deg)
        g0, g1 = self.gps.at(t0), self.gps.at(t1)
        if g0 is not None and g1 is not None:
            verdicts.append(haversine_m(g0[0], g0[1], g1[0], g1[1]) > self.frozen_motion_m)
        return any(verdicts) if verdicts else None

    def _check_frozen(self, raw, t):
        """Why the picture is frozen (None: fresh); reports it on camera_health and exits a camera
        input frozen longer than frozen_restart_s so systemd reopens the device.
        """
        was = self.freeze.frozen
        why = self.freeze.update(raw, t, self._moved(self._prev_t, t))
        self._prev_t = t
        since = (t - self.freeze.frozen_since) if why else 0.0
        if why:
            self.get_logger().error(f"camera image frozen ({self.freeze.repeats} frame(s), {since:.0f} s): {why} "
                                    "— frames not used for positions", throttle_duration_sec=5.0)
        elif was:
            self.get_logger().warn("camera image changes again: frames used again")
        if why or was or self.count == 0:
            self.pub_health.publish(String(data=json.dumps({
                "frozen": bool(why), "reason": why or "", "frozen_frames": self.freeze.repeats,
                "frozen_s": round(since, 1), "input": self.input})))
        if why and self.input not in ("ros", "insta360") and since > self.frozen_restart_s:
            self.get_logger().fatal(f"camera image frozen for {since:.0f} s — exiting so the service restarts "
                                    "and reopens the camera")
            self._stop.set()
            self.context.try_shutdown()
        return why

    def _camera_stalled(self, why):
        """Report a stalled camera input and exit: systemd restarts the service, which reopens it."""
        if self._stop.is_set():
            return
        self._stop.set()
        self.pub_health.publish(String(data=json.dumps({
            "frozen": False, "stalled": True, "reason": why, "input": self.input})))
        self.get_logger().fatal(f"the camera stopped sending frames ({why}) — exiting so the service restarts "
                                "and reopens it")
        self.context.try_shutdown()

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
