#!/usr/bin/env python3
"""
camera_publisher.py — NAVERA camera_pkg, generic publisher

ONE reusable node. Launched 3 times (thermal, celestial, day) by 3 different
launch files. Each instance has its own namespace, so the topics are isolated:
    /<topic_ns>/image_raw    sensor_msgs/Image
    /<topic_ns>/camera_info  sensor_msgs/CameraInfo
    /<topic_ns>/gps          sensor_msgs/NavSatFix
    /<topic_ns>/frame_meta   std_msgs/String  (JSON metadata)

Sources (parameter `source`):
    csv     → replay a flight CSV + image folder (current default)
    camera  → live CSI/USB camera via OpenCV/GStreamer (kept for later)

GPS rule:
    The CSV may carry lat/lon, but `default_gps_valid: false` (thermal,
    celestial) forces gps_valid=False on every frame so the STHN downstream
    pipeline always predicts the position.
"""
import base64, csv, json, math, threading, time
from pathlib import Path

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from std_msgs.msg import String, Header, Bool, Int32
from sensor_msgs.msg import Image, CameraInfo, NavSatFix, NavSatStatus

try:
    from cv_bridge import CvBridge
    _HAVE_CV_BRIDGE = True
except Exception:
    _HAVE_CV_BRIDGE = False

try:
    import cv2
    _HAVE_CV2 = True
except Exception:
    _HAVE_CV2 = False


# ───────────────── helpers ─────────────────

def _to_float_or_none(value):
    """Parse a CSV cell into float, or None for empty / 'None' / 'nan'."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("", "none", "nan", "null", "n/a"):
            return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def build_gst_pipeline(sensor_id, width, height, fps, flip):
    """GStreamer pipeline for a CSI camera on Jetson (nvarguscamerasrc)."""
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, "
        f"framerate={int(round(fps))}/1 ! "
        f"nvvidconv flip-method={flip} ! "
        f"video/x-raw, format=BGRx ! videoconvert ! "
        f"video/x-raw, format=BGR ! appsink drop=true max-buffers=1"
    )


# The producer thread must stop before the publishers are torn down. Bounded, so a
# wedged producer can never hang the process on shutdown.
_WORKER_JOIN_TIMEOUT_S = 5.0


# ───────────────── node ─────────────────

class CameraPublisher(Node):
    def __init__(self):
        super().__init__("camera_publisher")

        # Created first: both the startup wait below and the producer key off it.
        self._stop = threading.Event()
        self._frame_count = 0

        # ── parameters ──
        self.declare_parameter("camera_type", "generic")     # thermal|celestial|day
        self.declare_parameter("topic_ns", "camera")
        self.declare_parameter("source", "csv")              # csv | camera
        self.declare_parameter("fps", 0.1)
        self.declare_parameter("loop", False)
        self.declare_parameter("start_index", 0)
        self.declare_parameter("frame_id", "camera_link")
        self.declare_parameter("image_encoding", "bgr8")     # bgr8 | mono8 | mono16
        self.declare_parameter("default_gps_valid", True)    # force GPS off for thermal/celestial
        self.declare_parameter("start_paused", False)        # true: wait for 'camera/start' (Bool) before streaming
        self.declare_parameter("start_delay_s", 0.0)         # delay after start command, before frame 1
        # ── back-pressure (flow control) ──
        self.declare_parameter("flow_control", "rate")       # rate | ack  (rate = legacy fixed-fps)
        self.declare_parameter("ack_topic", "frame_done")    # Int32 frame_id acked by the subscriber
        self.declare_parameter("ack_timeout_s", 30.0)        # safety: continue if no ack within this delay
        # ── handshake "ready" + cadence (Problème 1) ──
        self.declare_parameter("wait_for_ready", False)      # true: gate frame 1 on subscriber-ready (model loaded)
        self.declare_parameter("ready_topic", "/day/localizer_ready")  # Bool latched published by the subscriber
        self.declare_parameter("ready_timeout_s", 0.0)       # 0 = wait indefinitely; >0 = start anyway after delay
        self.declare_parameter("min_frame_interval", 1.0)    # cadence min visible entre frames (ack mode)

        # CSV replay
        self.declare_parameter("csv_path", "")
        self.declare_parameter("images_dir", "")

        # Live camera (kept ready for later)
        self.declare_parameter("camera_kind", "csi")         # csi | usb
        self.declare_parameter("sensor_id", 0)
        self.declare_parameter("device", "/dev/video0")
        self.declare_parameter("width", 1280)
        self.declare_parameter("height", 720)
        self.declare_parameter("flip_method", 0)
        self.declare_parameter("startup_delay", 3.0)

        p = self.get_parameter
        self.camera_type     = p("camera_type").value
        self.topic_ns        = p("topic_ns").value.strip("/")
        self.source          = p("source").value
        self.fps             = float(p("fps").value)
        self.loop            = bool(p("loop").value)
        self.start_index     = int(p("start_index").value)
        self.frame_id        = p("frame_id").value
        self.image_encoding  = p("image_encoding").value
        self.default_gps_valid = bool(p("default_gps_valid").value)
        self.start_paused      = bool(p("start_paused").value)
        self.start_delay_s     = float(p("start_delay_s").value)
        self.flow_control      = str(p("flow_control").value)
        self.ack_topic         = p("ack_topic").value
        self.ack_timeout_s     = float(p("ack_timeout_s").value)
        self.wait_for_ready    = bool(p("wait_for_ready").value)
        self.ready_topic       = p("ready_topic").value
        self.ready_timeout_s   = float(p("ready_timeout_s").value)
        self.min_frame_interval = float(p("min_frame_interval").value)

        self.csv_path   = Path(p("csv_path").value) if p("csv_path").value else None
        self.images_dir = Path(p("images_dir").value) if p("images_dir").value else None

        self.camera_kind = p("camera_kind").value
        self.sensor_id   = int(p("sensor_id").value)
        self.device      = p("device").value
        self.width       = int(p("width").value)
        self.height      = int(p("height").value)
        self.flip_method = int(p("flip_method").value)

        # ── publishers ──
        # RELIABLE so it matches the day_subscriber image QoS (back-pressure: at the
        # slow per-frame rate, reliable delivery is free and removes DDS frame drops).
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )
        self.pub_image = self.create_publisher(Image, "image_raw", sensor_qos)
        self.pub_info  = self.create_publisher(CameraInfo, "camera_info", sensor_qos)
        self.pub_gps   = self.create_publisher(NavSatFix, "gps", 10)
        self.pub_meta  = self.create_publisher(String, "frame_meta", 10)

        self.bridge = CvBridge() if _HAVE_CV_BRIDGE else None

        # ── banner ──
        self.get_logger().info("=" * 60)
        self.get_logger().info(f"  NAVERA camera_pkg — {self.camera_type.upper()} camera")
        self.get_logger().info(f"  topic namespace : /{self.topic_ns}")
        self.get_logger().info(f"  source          : {self.source}")
        self.get_logger().info(f"  fps             : {self.fps:.4f}  (1 frame / {1.0/max(self.fps,1e-6):.0f}s)")
        self.get_logger().info(f"  encoding        : {self.image_encoding}")
        self.get_logger().info(f"  GPS default     : {'valid' if self.default_gps_valid else 'INVALID (STHN will predict)'}")
        if self.source == "csv":
            self.get_logger().info(f"  csv_path        : {self.csv_path}")
            self.get_logger().info(f"  images_dir      : {self.images_dir}")
        self.get_logger().info("=" * 60)

        # STARTUP_DELAY_SLEEP_MARKER : let ROS2 discovery propagate before the
        # first publication, otherwise subscribers that started a moment earlier
        # may miss the first frame (typical on Jetson + Fast-DDS).
        _delay = float(self.get_parameter("startup_delay").value)
        if _delay > 0:
            self.get_logger().info(f"  ⏳ waiting {_delay:.1f}s for ROS2 discovery…")
            if self._wait_startup(_delay):
                self.get_logger().info("  ✅ discovery wait done, starting publication")
            else:
                # A signal landed mid-startup and rclpy closed the context. Carrying
                # on would raise "rcl node's context is invalid" on the first
                # create_subscription() below. Abort construction instead.
                raise ExternalShutdownException()

        # ── Option A: start/pause gate ──
        self._go = threading.Event()
        self._restart = threading.Event()
        if not self.start_paused:
            self._go.set()
        else:
            self.get_logger().info("  ⏸ start_paused=true — waiting for start command before streaming")
        cmd_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,   # latched: timing-robust
            history=HistoryPolicy.KEEP_LAST, depth=1,
        )
        self.sub_start = self.create_subscription(Bool, "camera/start", self._on_start_cmd, cmd_qos)

        # ── back-pressure ack gate ──
        self._ack_event   = threading.Event()
        self._last_ack_id = None
        self._ack_lock    = threading.Lock()
        if self.flow_control == "ack":
            ack_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                history=HistoryPolicy.KEEP_LAST, depth=1,
            )
            self.sub_ack = self.create_subscription(Int32, self.ack_topic, self._on_ack, ack_qos)
            self.get_logger().info(f"  🔁 flow_control=ack — waiting for '{self.ack_topic}' after each frame")

        # ── handshake "ready" gate (frame 1 attend le subscriber prêt) ──
        self._ready_event = threading.Event()
        if self.wait_for_ready:
            ready_qos = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                durability=DurabilityPolicy.TRANSIENT_LOCAL,   # latched: capte un ready publié avant notre abonnement
                history=HistoryPolicy.KEEP_LAST, depth=1,
            )
            self.sub_ready = self.create_subscription(Bool, self.ready_topic, self._on_ready, ready_qos)
            self.get_logger().info(
                f"  🤝 wait_for_ready=true — frame 1 attend '{self.ready_topic}' "
                f"(timeout {'∞' if self.ready_timeout_s<=0 else f'{self.ready_timeout_s:.0f}s'})")
        if self.min_frame_interval > 0 and self.flow_control == "ack":
            self.get_logger().info(f"  🎞 cadence min entre frames : {self.min_frame_interval:.1f}s")

        # ── start producer thread ──
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def _wait_startup(self, seconds: float) -> bool:
        """Sleep `seconds`, aborting early if the node is shutting down.

        Runs inside __init__, i.e. before spin(): nothing sets _stop that early, so
        a SIGINT/SIGTERM here surfaces only as rclpy.ok() going False. Poll it.
        Returns True if the full delay elapsed, False if it was cut short.
        """
        deadline = time.perf_counter() + seconds
        while rclpy.ok() and not self._stop.is_set():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return True
            self._stop.wait(min(remaining, 0.2))
        return False

    # ───── producer ─────

    def _on_start_cmd(self, msg: Bool):
        if msg.data:
            self.get_logger().info("▶ start command — (re)start from frame 1")
            self._restart.set()      # force a fresh pass even if one is in progress
            self._go.set()
        else:
            self.get_logger().info("⏸ pause command — pause + rewind")
            self._go.clear()

    def _on_ack(self, msg: Int32):
        with self._ack_lock:
            self._last_ack_id = int(msg.data)
        self._ack_event.set()

    def _on_ready(self, msg: Bool):
        if msg.data and not self._ready_event.is_set():
            self.get_logger().info("📨 localizer_ready reçu — le subscriber a chargé le modèle")
        if msg.data:
            self._ready_event.set()

    def _wait_for_ready(self):
        """Bloque jusqu'au signal 'ready' du subscriber (modèle chargé), ou timeout.
        Interruptible (stop/pause). Retourne True si ready reçu, False si timeout."""
        if self._ready_event.is_set():
            return True
        self.get_logger().info(f"⏳ frame 1 en attente du subscriber prêt ('{self.ready_topic}')…")
        deadline = (time.perf_counter() + self.ready_timeout_s) if self.ready_timeout_s > 0 else None
        while not self._stop.is_set() and self._go.is_set():
            if self._ready_event.wait(timeout=0.5):
                self.get_logger().info("✅ subscriber prêt — démarrage frame 1")
                return True
            if deadline is not None and time.perf_counter() >= deadline:
                self.get_logger().warn(
                    f"⚠ subscriber pas prêt après {self.ready_timeout_s:.0f}s — démarrage quand même")
                return False
        return False

    def _wait_for_ack(self, frame_id):
        """Block until the subscriber acks `frame_id` (back-pressure), or timeout.
        Interruptible: returns early on stop/pause. Returns True if acked."""
        target = frame_id if isinstance(frame_id, int) else None
        self.get_logger().info(f"⏳ awaiting ack for frame={frame_id}…")
        deadline = time.perf_counter() + self.ack_timeout_s
        while not self._stop.is_set() and self._go.is_set():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                self.get_logger().warn(
                    f"⚠ no ack for frame={frame_id} within {self.ack_timeout_s:.0f}s "
                    f"— continuing (subscriber down?)")
                return False
            if self._ack_event.wait(timeout=min(remaining, 0.5)):
                self._ack_event.clear()
                with self._ack_lock:
                    acked = self._last_ack_id
                if target is None or acked == target:
                    return True
                # stale/older ack → keep waiting for the right frame
        return False

    def _run(self):
        try:
            if self.source == "csv":
                self._run_csv()
            elif self.source == "camera":
                self._run_camera()
            else:
                self.get_logger().error(f"Unknown source '{self.source}' (use 'csv' or 'camera')")
        except Exception as e:
            self.get_logger().error(f"Producer crashed: {e}")

    def _run_csv(self):
        if not self.csv_path or not Path(self.csv_path).exists():
            self.get_logger().warn(f"csv_path missing or empty: {self.csv_path} — node idle")
            return
        if not self.images_dir or not Path(self.images_dir).is_dir():
            self.get_logger().warn(f"images_dir missing: {self.images_dir} — node idle")
            return

        period = 1.0 / max(self.fps, 1e-3)
        iteration = 0
        while not self._stop.is_set():
            # ── gate: wait for the start command (start_paused / pause) ──
            if not self._go.is_set():
                self.get_logger().info("⏸ paused — waiting for 'camera/start'…")
                while not self._go.wait(timeout=0.5):
                    if self._stop.is_set():
                        return
                self.get_logger().info("▶ start — streaming from the beginning")
            self._restart.clear()

            # délai de démarrage : dans le THREAD de streaming (jamais dans _on_start_cmd),
            # après le rewind, juste avant la 1re publication
            if self.start_delay_s > 0:
                self.get_logger().info(f"⏳ start delay {self.start_delay_s:.1f}s — letting subscriber + map settle…")
                self._stop.wait(self.start_delay_s)   # interruptible sleep (respects _stop)
                if self._stop.is_set() or not self._go.is_set():
                    continue                          # annulé/pause pendant l'attente → retour au gate

            # ── handshake : ne PAS streamer la frame 1 tant que le subscriber
            #    (modèle chargé) n'a pas signalé qu'il est prêt ──
            if self.wait_for_ready:
                self._wait_for_ready()                # bloque jusqu'au ready (ou timeout)
                if self._stop.is_set() or not self._go.is_set():
                    continue                          # annulé/pause pendant l'attente → retour au gate

            iteration += 1
            if self.loop:
                self.get_logger().info(f"=== Streaming pass #{iteration} ===")

            with open(self.csv_path, newline="") as fp:
                reader = csv.DictReader(fp)
                for idx, row in enumerate(reader):
                    if self._stop.is_set():
                        return
                    if self._restart.is_set() or not self._go.is_set():
                        break          # pause/restart → abandon pass (rewind)
                    if idx < self.start_index:
                        continue

                    t_start = time.perf_counter()

                    frame_id = row.get("frame_id") or str(idx)
                    try: frame_id = int(frame_id)
                    except ValueError: pass

                    image_name = (row.get("image_file") or "").strip()
                    lat = _to_float_or_none(row.get("lat"))
                    lon = _to_float_or_none(row.get("lon"))
                    alt = _to_float_or_none(row.get("altitude_m")) or 400.0
                    hdg = _to_float_or_none(row.get("heading_deg")) or 0.0
                    spd = _to_float_or_none(row.get("speed_mps")) or 5.0

                    # GPS rule: must be valid in CSV AND allowed by config
                    gps_valid = (lat is not None) and (lon is not None) and self.default_gps_valid

                    img_path = Path(self.images_dir) / image_name
                    if not img_path.exists():
                        self.get_logger().warn(f"[{frame_id}] image missing: {img_path}")
                        continue

                    meta = {
                        "frame_id": frame_id, "lat": lat if gps_valid else None,
                        "lon": lon if gps_valid else None, "gps_valid": gps_valid,
                        "altitude_m": alt, "heading_deg": hdg, "speed_mps": spd,
                        "timestamp": time.strftime("%H:%M:%S"),
                        "image_file": image_name, "camera_type": self.camera_type,
                    }
                    if self.flow_control == "ack":
                        # back-pressure: clear before publishing, then wait until the
                        # subscriber has fully processed THIS frame before the next one.
                        self._ack_event.clear()
                        self._publish_from_file(img_path, meta)
                        self._wait_for_ack(frame_id)
                        # cadence minimale VISIBLE : garantit que chaque position s'affiche
                        # avant la suivante, même si le calcul du subscriber est très rapide.
                        if self.min_frame_interval > 0:
                            remaining = self.min_frame_interval - (time.perf_counter() - t_start)
                            if remaining > 0:
                                self._stop.wait(remaining)
                    else:
                        # legacy fixed-rate cadence
                        self._publish_from_file(img_path, meta)
                        elapsed = time.perf_counter() - t_start
                        sleep = period - elapsed
                        if sleep > 0:
                            self._stop.wait(sleep)

            # ── end of pass ──
            if self._restart.is_set() or not self._go.is_set():
                continue                        # rewind: next pass restarts from the top
            if not self.loop:
                self.get_logger().info("=== End of CSV — done (auto-pause) ===")
                self._go.clear()                # one-shot: idle until next start command
                continue

    def _run_camera(self):
        if not _HAVE_CV2:
            self.get_logger().error("OpenCV not available → cannot use live camera")
            return
        if self.camera_kind == "csi":
            pipeline = build_gst_pipeline(self.sensor_id, self.width, self.height,
                                          max(self.fps, 1.0), self.flip_method)
            self.get_logger().info(f"Opening CSI: {pipeline}")
            cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        else:
            self.get_logger().info(f"Opening USB: {self.device}")
            cap = cv2.VideoCapture(self.device)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        if not cap.isOpened():
            self.get_logger().error("Failed to open camera")
            return

        period = 1.0 / max(self.fps, 1e-3)
        while not self._stop.is_set():
            t_start = time.perf_counter()
            ok, frame = cap.read()
            if not ok:
                self.get_logger().warn("Camera read failed")
                self._stop.wait(0.1); continue

            meta = {
                "frame_id": self._frame_count, "lat": None, "lon": None,
                "gps_valid": self.default_gps_valid, "altitude_m": 400.0,
                "heading_deg": 0.0, "speed_mps": 5.0,
                "timestamp": time.strftime("%H:%M:%S"),
                "image_file": f"live_{self._frame_count:06d}.jpg",
                "camera_type": self.camera_type,
            }
            self._publish_cv_frame(frame, meta)
            elapsed = time.perf_counter() - t_start
            sleep = period - elapsed
            if sleep > 0:
                self._stop.wait(sleep)

        cap.release()

    # ───── publish helpers ─────

    def _make_header(self):
        h = Header()
        h.stamp = self.get_clock().now().to_msg()
        h.frame_id = self.frame_id
        return h

    def _publish_gps_and_meta(self, header, meta):
        fix = NavSatFix(); fix.header = header
        if meta["gps_valid"]:
            fix.status.status = NavSatStatus.STATUS_FIX
            fix.latitude  = float(meta["lat"])
            fix.longitude = float(meta["lon"])
            fix.altitude  = float(meta["altitude_m"])
        else:
            fix.status.status = NavSatStatus.STATUS_NO_FIX
            fix.latitude  = float("nan")
            fix.longitude = float("nan")
            fix.altitude  = float(meta["altitude_m"])
        self.pub_gps.publish(fix)

        m = String(); m.data = json.dumps(meta)
        self.pub_meta.publish(m)

    def _log_frame(self, meta):
        tag = "📍 GPS" if meta["gps_valid"] else "🌙 NO-GPS"
        lat = f"{meta['lat']:.5f}" if meta["lat"] is not None else "—"
        lon = f"{meta['lon']:.5f}" if meta["lon"] is not None else "—"
        self.get_logger().info(f"[{self.camera_type}] {tag}  frame={meta['frame_id']}  lat={lat:>10}  lon={lon:>10}")

    def _publish_cv_frame(self, cv_img, meta):
        header = self._make_header()
        if self.bridge is not None:
            enc = self.image_encoding if self.image_encoding != "bgr8" else "bgr8"
            img_msg = self.bridge.cv2_to_imgmsg(cv_img, encoding=enc)
            img_msg.header = header
            self.pub_image.publish(img_msg)
        self._publish_gps_and_meta(header, meta)
        self._frame_count += 1
        self._log_frame(meta)

    def _publish_from_file(self, img_path, meta):
        header = self._make_header()
        if _HAVE_CV2 and self.bridge is not None:
            if self.image_encoding in ("mono8", "mono16"):
                cv_img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            else:
                cv_img = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if cv_img is not None:
                img_msg = self.bridge.cv2_to_imgmsg(cv_img, encoding=self.image_encoding)
                img_msg.header = header
                self.pub_image.publish(img_msg)
        self._publish_gps_and_meta(header, meta)
        self._frame_count += 1
        self._log_frame(meta)

    def destroy_node(self):
        """Stop the producer BEFORE tearing the publishers down.

        The worker publishes from its own thread; destroying the publishers while
        it sits inside publish() is a use-after-free on the rclpy handles. Setting
        _stop alone is enough to unblock it — every wait it can park in polls _stop
        at 0.5 s — and, unlike waking the gates, it cannot let the worker take one
        more step (and publish one more frame) on the way out.
        """
        self._stop.set()
        worker = getattr(self, "_worker", None)   # __init__ may have failed before it existed
        if worker is not None and worker.is_alive():
            worker.join(timeout=_WORKER_JOIN_TIMEOUT_S)
            if worker.is_alive():
                self.get_logger().warn(
                    f"producer thread still alive after {_WORKER_JOIN_TIMEOUT_S:.0f}s "
                    f"— tearing down anyway")
        super().destroy_node()


def main(args=None):
    """Entry point. Exits cleanly (code 0) on SIGINT and SIGTERM.

    rclpy installs handlers for both signals and shuts the context down itself,
    so spin() returns with the context already closed — an unconditional
    rclpy.shutdown() here would then raise RCLError. Hence the rclpy.ok() guard.
    """
    rclpy.init(args=args)
    node = None
    try:
        node = CameraPublisher()   # may abort if a signal lands during the startup wait
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
