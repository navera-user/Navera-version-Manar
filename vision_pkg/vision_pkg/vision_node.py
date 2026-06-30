#!/usr/bin/env python3
"""
vision_node.py ── LIFECYCLE VERSION (Multi-Thread Pipeline)
════════════════════════════════════════════════════════════
Architecture multi-thread complète (inchangée) :

  Thread 1 ── CSV Watcher      : surveille flight_log.csv en continu (byte-offset)
  Thread 2 ── Inference Pipeline: lance NetVLAD + DINOv2 en parallèle dès dataset prêt
  Thread 3 ── Status Writer    : écrit gps_status.json de façon atomique
  Thread 4 ── Model Warmup     : précharge NetVLAD + DINOv2 au configure

Lifecycle states :
  UNCONFIGURED → on_configure() → INACTIVE   : init variables + pub/sub + warmup modèles
  INACTIVE     → on_activate()  → ACTIVE     : démarre les threads background
  ACTIVE       → on_deactivate()→ INACTIVE   : stoppe les threads proprement
  INACTIVE     → on_cleanup()   → UNCONFIGURED: libère mémoire
  *            → on_shutdown()  → FINALIZED  : arrêt total

Contrôle depuis CLI :
  ros2 lifecycle set /vision_node configure
  ros2 lifecycle set /vision_node activate
  ros2 lifecycle set /vision_node deactivate
  ros2 lifecycle set /vision_node cleanup
  ros2 lifecycle set /vision_node shutdown

Contrôle depuis fusion_node (programmatique) :
  ChangeState.Request(transition=Transition(id=Transition.TRANSITION_CONFIGURE))
  ChangeState.Request(transition=Transition(id=Transition.TRANSITION_ACTIVATE))
"""

import os
import math
import cv2
import json
import time
import csv
import threading
import queue
import shutil
from pathlib import Path
from threading import Thread, Lock, Event
from concurrent.futures import ThreadPoolExecutor

# ── ROS2 Imports (with Guard) ───────────────────────────────────────────────
try:
    import rclpy
    from rclpy.lifecycle import LifecycleNode, TransitionCallbackReturn, State
    from sensor_msgs.msg import Image, NavSatFix, NavSatStatus
    from geometry_msgs.msg import PoseStamped
    from std_msgs.msg import Float32
    from cv_bridge import CvBridge
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    print("⚠️  rclpy not found — running in standalone mode (file-based only)")

    # ── Stubs for standalone mode ──────────────────────────────────────────
    class TransitionCallbackReturn:
        SUCCESS = "SUCCESS"
        FAILURE = "FAILURE"
        ERROR   = "ERROR"

    class State:
        pass

    class LifecycleNode:
        def __init__(self, name):
            self.name = name
        def get_logger(self):
            class Logger:
                def info(self, m):  print(f"[INFO]  {m}")
                def warn(self, m):  print(f"[WARN]  {m}")
                def error(self, m): print(f"[ERROR] {m}")
                def debug(self, m): pass
                def warning(self, m): print(f"[WARN]  {m}")
            return Logger()
        def declare_parameter(self, n, v): pass
        def get_parameter(self, n):
            class Param:
                def __init__(self, v): self.value = v
            if n == "mbtiles_path":
                return Param(str(Path(__file__).resolve().parent / "dataset" / "sousse_satellite.mbtiles"))
            if n == "default_altitude_m":
                return Param(750)
            return Param(None)
        def create_subscription(self, *a, **kw): pass
        def create_publisher(self, *a, **kw):
            class Pub:
                def publish(self, m): pass
            return Pub()
        def get_clock(self):
            class Clock:
                def now(self):
                    class Time:
                        def to_msg(self): return None
                    return Time()
            return Clock()
        # Lifecycle stubs — called directly in standalone
        def on_configure(self, state): return TransitionCallbackReturn.SUCCESS
        def on_activate(self, state):  return TransitionCallbackReturn.SUCCESS
        def on_deactivate(self, state):return TransitionCallbackReturn.SUCCESS
        def on_cleanup(self, state):   return TransitionCallbackReturn.SUCCESS
        def on_shutdown(self, state):  return TransitionCallbackReturn.SUCCESS

# ── Vision Imports ───────────────────────────────────────────────────────────
from gps_localizer import predict_gps, predict_gps_cached, is_cache_ready, _get_localizer
from dataset_gen import generate_dataset


# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

MAX_NOGPS_QUEUE   = 5       # Max queued no-GPS frames (older ones dropped)
MAX_PROC_FRAMES   = 2000    # Sliding window size for processed frame IDs
CSV_POLL_HZ       = 0.15    # CSV polling interval (seconds) — 150ms
STATUS_WRITE_HZ   = 0.05    # Status flush interval (seconds) — 50ms
DATASET_N_WORKERS = 8       # Threads for MBTiles tile extraction


# ═══════════════════════════════════════════════════════════════════════════════
#  VISION NODE  (LIFECYCLE VERSION)
# ═══════════════════════════════════════════════════════════════════════════════

class VisionNode(LifecycleNode):

    def __init__(self):
        super().__init__('vision_node')

        # ROS2 bridge (created here, used after configure)
        self.bridge = None

        # ── Pubs / Subs handles (set in on_configure) ───────────────────────
        self.gps_publisher   = None
        self.pose_publisher  = None
        self._image_sub      = None
        self._gps_sub        = None
        self._alt_sub        = None

        # ── Pre-loaded model handles (set in on_configure warmup) ───────────
        self._nv_model   = None
        self._dino_model = None

        # ── State (initialised in on_configure) ─────────────────────────────
        self.last_valid_lat   = None
        self.last_valid_lon   = None
        self.last_valid_alt   = None
        self.gps_lost         = False
        self.fixed_gps_loss   = None
        self.last_match_index = None

        self.target_lat       = None
        self.target_lon       = None
        self.mission_reached  = False
        self.active_folders   = []

        # ── Paths (stable across lifecycle) ─────────────────────────────────
        self.pkg_dir = Path(__file__).resolve().parent
        self.dataset_root = self.pkg_dir / "dataset"
        if not self.dataset_root.exists():
            self.dataset_root = Path(__file__).resolve().parent / "dataset"
        # No more hardcoded fallbacks — dataset_root is relative to this file

        self.csv_path            = self.dataset_root / "flight_log.csv"
        self.mission_config_path = self.dataset_root / "mission_config.json"
        self.gps_status_path     = self.dataset_root / "gps_status.json"
        self.temp_folder         = self.dataset_root / "temp"
        self.temp_folder.mkdir(parents=True, exist_ok=True)

        # ── Locks & Queues ──────────────────────────────────────────────────
        self._state_lock      = Lock()
        self._status_lock     = Lock()
        self._nogps_queue     = queue.Queue(maxsize=MAX_NOGPS_QUEUE)
        self._dataset_running = False

        # ── Stop event (reset on each activate) ─────────────────────────────
        self._stop_event  = Event()
        self._bg_threads  = []

        # ── CSV Watcher state ────────────────────────────────────────────────
        self._csv_offset   = 0
        self._csv_header   = None
        self.processed_frames = set()
        self.last_csv_row  = None

        # ── Pending status (batched write) ───────────────────────────────────
        self._pending_status = None
        self._status_dirty   = False

        self.get_logger().info("🧠 VisionNode (Lifecycle) created — waiting for configure")


    # ═══════════════════════════════════════════════════════════════════════════
    #  LIFECYCLE CALLBACKS
    # ═══════════════════════════════════════════════════════════════════════════

    def on_configure(self, state: State) -> TransitionCallbackReturn:
        """
        UNCONFIGURED → INACTIVE
        ─────────────────────────────────────────────────────────────────────
        • Declare ROS2 parameters
        • Create publishers / subscribers
        • Warm-up AI models (NetVLAD + DINOv2) in background
        • Write initial status JSON
        """
        self.get_logger().info("⚙️  VisionNode: configuring …")

        try:
            # ── ROS2 bridge ─────────────────────────────────────────────────
            if ROS2_AVAILABLE:
                self.bridge = CvBridge()

            # ── ROS2 Parameters ──────────────────────────────────────────────
            self.declare_parameter(
                'mbtiles_path',
                str(self.pkg_dir / 'dataset' / 'sousse_satellite.mbtiles')
            )
            self.declare_parameter('default_altitude_m', 750)

            # ── Publishers ───────────────────────────────────────────────────
            self.gps_publisher  = self.create_publisher(NavSatFix,    '/vision/predicted_gps',  10)
            self.pose_publisher = self.create_publisher(PoseStamped,  '/vision/predicted_pose', 10)

            # ── Subscribers ──────────────────────────────────────────────────
            self._image_sub = self.create_subscription(
                Image,     '/fusion/image_raw', self.image_callback,    10)
            self._gps_sub   = self.create_subscription(
                NavSatFix, '/drone/gps',        self.gps_callback,      10)
            self._alt_sub   = self.create_subscription(
                Float32,   '/drone/altitude',   self.altitude_callback, 10)

            # ── Initial status ───────────────────────────────────────────────
            self._queue_status("idle", None, None)

            # ── Pre-load AI models (non-blocking) ────────────────────────────
            Thread(target=self._warmup_models, daemon=True, name="ModelWarmup").start()

            self.get_logger().info(
                "✅ VisionNode configured\n"
                f"   CSV    : {self.csv_path}\n"
                f"   Status : {self.gps_status_path}\n"
                f"   Temp   : {self.temp_folder}"
            )
            return TransitionCallbackReturn.SUCCESS

        except Exception as e:
            self.get_logger().error(f"❌ on_configure failed: {e}")
            return TransitionCallbackReturn.FAILURE


    def on_activate(self, state: State) -> TransitionCallbackReturn:
        """
        INACTIVE → ACTIVE
        ─────────────────────────────────────────────────────────────────────
        • Clear stop event
        • Start background threads (CSV watcher, inference pipeline, status writer)
        """
        self.get_logger().info("🚀 VisionNode: activating …")

        try:
            # Reset stop event (handles re-activate after deactivate)
            self._stop_event.clear()

            # Reset CSV state on each activation so we start fresh
            self._csv_offset = 0
            self._csv_header = None
            self.processed_frames.clear()

            # Start background threads
            self._bg_threads = [
                Thread(target=self._csv_watcher_loop,
                       daemon=True, name="CSVWatcher"),
                Thread(target=self._inference_pipeline_loop,
                       daemon=True, name="InferencePipeline"),
                Thread(target=self._status_writer_loop,
                       daemon=True, name="StatusWriter"),
            ]
            for t in self._bg_threads:
                t.start()

            self.get_logger().info(
                "✅ VisionNode ACTIVE — 3 background threads running\n"
                f"   CSV poll : {CSV_POLL_HZ*1000:.0f}ms\n"
                f"   Status flush : {STATUS_WRITE_HZ*1000:.0f}ms"
            )
            return TransitionCallbackReturn.SUCCESS

        except Exception as e:
            self.get_logger().error(f"❌ on_activate failed: {e}")
            return TransitionCallbackReturn.FAILURE


    def on_deactivate(self, state: State) -> TransitionCallbackReturn:
        """
        ACTIVE → INACTIVE
        ─────────────────────────────────────────────────────────────────────
        • Signal all background threads to stop
        • Wait up to 3 s for clean exit
        """
        self.get_logger().info("⏸️  VisionNode: deactivating …")

        self._stop_event.set()

        # Give threads a chance to finish gracefully
        for t in self._bg_threads:
            t.join(timeout=3.0)

        self._bg_threads.clear()
        self.get_logger().info("✅ VisionNode INACTIVE — all threads stopped")
        return TransitionCallbackReturn.SUCCESS


    def on_cleanup(self, state: State) -> TransitionCallbackReturn:
        """
        INACTIVE → UNCONFIGURED
        ─────────────────────────────────────────────────────────────────────
        • Release model references
        • Reset internal state
        """
        self.get_logger().info("🧹 VisionNode: cleanup …")

        self._nv_model   = None
        self._dino_model = None
        self.gps_publisher  = None
        self.pose_publisher = None
        self._image_sub = None
        self._gps_sub   = None
        self._alt_sub   = None

        with self._state_lock:
            self.last_valid_lat  = None
            self.last_valid_lon  = None
            self.last_valid_alt  = None
            self.gps_lost        = False
            self.fixed_gps_loss  = None
            self.last_match_index = None

        self.get_logger().info("✅ VisionNode cleaned up")
        return TransitionCallbackReturn.SUCCESS


    def on_shutdown(self, state: State) -> TransitionCallbackReturn:
        """Called on any → FINALIZED transition."""
        self.get_logger().info("❌ VisionNode: shutting down …")
        self._stop_event.set()
        for t in self._bg_threads:
            t.join(timeout=2.0)
        return TransitionCallbackReturn.SUCCESS


    # ═══════════════════════════════════════════════════════════════════════════
    #  MODEL WARM-UP  (runs during on_configure, non-blocking)
    # ═══════════════════════════════════════════════════════════════════════════

    def _warmup_models(self):
        """Précharge NetVLAD + DINOv2 et effectue une inférence fantôme (Dummy) pour CUDA."""
        try:
            from gps_localizer import BackboneNetVLAD, DINOv2GeM
            import torch
            import numpy as np
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.get_logger().info("🔥 Warm-up modèles AI (Ultra Mode) en cours …")
            t = time.time()
            self._nv_model   = BackboneNetVLAD().to(device).eval()
            self._dino_model = DINOv2GeM().to(device).eval()

            if device == "cuda":
                self._nv_model.half()
                self._dino_model.half()
                # Dummy inference to load CUDA kernels
                dummy = torch.randn(1, 3, 224, 224).to(device).half()
                with torch.inference_mode():
                    _ = self._nv_model(dummy)
                    _ = self._dino_model(dummy)
                torch.cuda.synchronize()

            self.get_logger().info(
                f"✅ Modèles prêts et CUDA chaud en {time.time()-t:.1f}s — "
                f"Prêt pour du temps réel pur !"
            )
        except Exception as e:
            self.get_logger().warn(f"⚠️  Warm-up échoué: {e}")


    # ═══════════════════════════════════════════════════════════════════════════
    #  ROS2 CALLBACKS  (lightweight — never block)
    # ═══════════════════════════════════════════════════════════════════════════

    def altitude_callback(self, msg: Float32):
        if not math.isnan(msg.data) and msg.data > 0:
            with self._state_lock:
                self.last_valid_alt = msg.data

    def _load_mission_config(self):
        """Load destination Point B from mission_config.json"""
        if self.mission_config_path.exists():
            try:
                with open(self.mission_config_path, 'r') as f:
                    cfg = json.load(f)
                    if cfg.get("point_b"):
                        self.target_lat = cfg["point_b"]["lat"]
                        self.target_lon = cfg["point_b"]["lon"]
                        self.get_logger().info(
                            f"🎯 Destination Point B loaded: "
                            f"({self.target_lat}, {self.target_lon})"
                        )
            except Exception as e:
                self.get_logger().error(f"Error loading mission config: {e}")

    def gps_callback(self, msg):
        if not ROS2_AVAILABLE:
            return
        lat, lon = msg.latitude, msg.longitude
        invalid = (
            math.isnan(lat) or math.isnan(lon) or
            msg.status.status == NavSatStatus.STATUS_NO_FIX
        )
        with self._state_lock:
            if not invalid:
                self.last_valid_lat = lat
                self.last_valid_lon = lon
                self.gps_lost       = False
                self._queue_status("active", lat, lon)
            elif not self.gps_lost:
                self.gps_lost = True
                self.get_logger().warn(
                    f'📡 GPS PERDU ! Dernière position : '
                    f'({self.last_valid_lat}, {self.last_valid_lon})'
                )
                if self.target_lat is None:
                    self._load_mission_config()

    def image_callback(self, msg):
        """Save image async — never block ROS spin."""
        if not ROS2_AVAILABLE:
            return
        try:
            cv_image  = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            temp_path = self.temp_folder / 'received_image.jpg'
            cv2.imwrite(str(temp_path), cv_image)
        except Exception as e:
            self.get_logger().error(f"❌ image_callback: {e}")


    # ═══════════════════════════════════════════════════════════════════════════
    #  THREAD 1 — CSV WATCHER
    #  Reads only new bytes (byte-offset tracking). O(new_bytes) not O(file).
    # ═══════════════════════════════════════════════════════════════════════════

    def _csv_watcher_loop(self):
        self.get_logger().info(
            f"[CSVWatcher] Started — polling every {CSV_POLL_HZ*1000:.0f}ms"
        )
        while not self._stop_event.is_set():
            try:
                self._csv_tick()
            except Exception as e:
                self.get_logger().error(f"[CSVWatcher] {e}")
            time.sleep(CSV_POLL_HZ)
        self.get_logger().info("[CSVWatcher] Stopped")

    def _csv_tick(self):
        if not self.csv_path.exists():
            self._csv_offset = 0
            self._csv_header = None
            return

        file_size = self.csv_path.stat().st_size

        if file_size < self._csv_offset:
            self._csv_offset = 0
            self._csv_header = None
            self.processed_frames.clear()
            with self._state_lock:
                self.last_valid_lat   = None
                self.last_valid_lon   = None
                self.last_valid_alt   = None
                self.gps_lost         = False
                self.fixed_gps_loss   = None
                self.last_match_index = None
            self._queue_status("idle", None, None)
            self.get_logger().warn("[CSVWatcher] CSV truncated — Session reset")

        with open(self.csv_path, 'r', newline='') as f:
            if self._csv_header is None:
                line = f.readline()
                if not line:
                    return
                self._csv_header = [h.strip() for h in line.split(',')]
                self._csv_offset = f.tell()
            else:
                f.seek(self._csv_offset)

            new_lines = f.readlines()
            if new_lines:
                self._csv_offset = f.tell()

        for raw_line in new_lines:
            line = raw_line.strip()
            if not line:
                continue
            values = line.split(',')
            if len(values) < len(self._csv_header):
                self.get_logger().warn(f"[CSVWatcher] Line too short: {line}")
                continue

            row      = dict(zip(self._csv_header, values))
            frame_id = str(row.get('frame_id', '')).strip()
            if not frame_id or frame_id in self.processed_frames:
                continue

            self.get_logger().debug(f"[CSVWatcher] Processing frame {frame_id} from CSV")

            self.processed_frames.add(frame_id)
            if len(self.processed_frames) > MAX_PROC_FRAMES:
                self.processed_frames.discard(next(iter(self.processed_frames)))

            gps_valid = str(row.get('gps_valid', '')).strip().lower() in ('true', '1', 'yes')

            if gps_valid:
                try:
                    lat = float(row['lat'])
                    lon = float(row['lon'])
                    alt = float(row.get('alt_m', 400))
                    if not (math.isnan(lat) or math.isnan(lon)):
                        with self._state_lock:
                            self.last_valid_lat = lat
                            self.last_valid_lon = lon
                            self.last_valid_alt = alt
                            self.gps_lost       = False
                            self.fixed_gps_loss = None
                        self.last_csv_row = {**row, 'lat': lat, 'lon': lon, 'alt': alt}
                        self._queue_status("active", lat, lon)
                except (ValueError, KeyError):
                    pass

            else:
                with self._state_lock:
                    if not self.gps_lost:
                        self.gps_lost = True
                        self.fixed_gps_loss   = (self.last_valid_lat, self.last_valid_lon)
                        self.last_match_index = None

                    ref_lat   = self.last_valid_lat
                    ref_lon   = self.last_valid_lon
                    ref_alt   = self.last_valid_alt or 400.0
                    fixed_ref = self.fixed_gps_loss

                if ref_lat is None:
                    self.get_logger().warn(
                        f"[CSVWatcher] Frame {frame_id}: no GPS before NaN — skip"
                    )
                    continue

                img_file = str(row.get('image_file', '')).strip()
                task = {
                    'frame_id'  : frame_id,
                    'image_file': img_file,
                    'lat'       : ref_lat,
                    'lon'       : ref_lon,
                    'alt'       : ref_alt,
                    'fixed_lat' : fixed_ref[0] if fixed_ref else ref_lat,
                    'fixed_lon' : fixed_ref[1] if fixed_ref else ref_lon,
                }

                try:
                    self._nogps_queue.put_nowait(task)
                    self.get_logger().info(
                        f"[CSVWatcher] Frame {frame_id} → NoGPS queue "
                        f"(ref: {ref_lat:.5f}, {ref_lon:.5f})"
                    )
                except queue.Full:
                    try:
                        self._nogps_queue.get_nowait()
                    except queue.Empty:
                        pass
                    self._nogps_queue.put_nowait(task)
                    self.get_logger().warn(
                        "[CSVWatcher] NoGPS queue full — dropped oldest task"
                    )


    # ═══════════════════════════════════════════════════════════════════════════
    #  THREAD 2 — INFERENCE PIPELINE (Producer-Consumer)
    # ═══════════════════════════════════════════════════════════════════════════

    def _inference_pipeline_loop(self):
        """🚀 Stage 1: Async Task Picker & Pre-processing Thread"""
        self.get_logger().info("[InferencePipeline] Started — Ultra Mode active")
        while not self._stop_event.is_set():
            try:
                task = self._nogps_queue.get(timeout=1.0)
                self._run_fast_inference(task)
                self._nogps_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.get_logger().error(f"[InferencePipeline] {e}")
        self.get_logger().info("[InferencePipeline] Stopped")

    def _run_fast_inference(self, task):
        """Stage 2: Real-time Visual Localization"""
        with self._state_lock:
            self._dataset_running = True
        try:
            self._run_full_pipeline(
                frame_id  = task['frame_id'],
                lat       = task['lat'],
                lon       = task['lon'],
                alt       = int(task['alt']),
                image_file= task['image_file'],
                fixed_lat = task['fixed_lat'],
                fixed_lon = task['fixed_lon'],
            )
        finally:
            with self._state_lock:
                self._dataset_running = False

    def _run_full_pipeline(self, frame_id, lat, lon, alt, image_file, fixed_lat, fixed_lon):
        """
        Full pipeline:
          1. Update status → searching
          2. Locate wp_0000 dataset
          3. Resolve query image
          4. Sliding-window matching (NetVLAD + DINOv2 via predict_gps_cached)
          5. Publish predicted GPS on ROS2 topics
          6. Check if destination reached
          7. Write final status JSON
        """
        mbtiles_path    = self.get_parameter('mbtiles_path').value
        search_radius_m = self._compute_search_radius(alt)
        fallback_dir    = self.dataset_root / "fallback_dataset"

        # ── Step 0: status → searching ───────────────────────────────────────
        self._queue_status(
            "searching", lat, lon,
            search_radius_m = search_radius_m,
            message         = f"GPS perdu — frame {frame_id} · rayon {search_radius_m:.0f}m",
            frame_id        = frame_id,
        )

        # ── Step 1: dataset wp_0000 ──────────────────────────────────────────
        wp0_dir = fallback_dir / "wp_0000"
        if not wp0_dir.exists():
            self.get_logger().error(f"❌ Dataset wp_0000 not found at {wp0_dir}")
            self._queue_status("error", lat, lon, error="Dataset wp_0000 non trouvé")
            return

        ds_ms     = 0
        img_count = (
            len(list((wp0_dir / "images").glob("*.jpg")))
            if (wp0_dir / "images").exists() else 0
        )

        # ── Step 2: resolve query image ──────────────────────────────────────
        img_path = self._resolve_image_path(image_file)
        if img_path is None:
            self.get_logger().error(f"❌ Query image not found: {image_file}")
            self._queue_status("error", lat, lon, error=f"Image introuvable: {image_file}")
            return

        # ── Step 3: sliding-window matching ──────────────────────────────────
        self.get_logger().info("🔍 Running strict window matching on wp_0000 …")
        t1 = time.time()

        anchor   = None
        w_before = 500
        w_after  = 1000

        with self._state_lock:
            anchor = self.last_match_index

        if anchor is None:
            try:
                loc    = _get_localizer(str(wp0_dir))
                anchor = loc.find_closest_index(lat, lon)
                self.get_logger().info(
                    f"📍 Initial anchor: index {anchor} "
                    f"(nearest {lat:.5f}, {lon:.5f})"
                )
            except Exception as e:
                self.get_logger().error(f"❌ Failed to init anchor: {e}")

        pred = predict_gps_cached(
            str(img_path),
            str(wp0_dir),
            anchor_index  = anchor,
            window_before = w_before,
            window_after  = w_after,
        )
        loc_ms = (time.time() - t1) * 1000

        if pred is None:
            self.get_logger().warning("⚠️ No match in window — Sliding forward anyway")
            if anchor is not None:
                with self._state_lock:
                    self.last_match_index = min(img_count - 1, anchor + 5)
            self._queue_status(
                "error", lat, lon,
                error           = "Aucun match dans la fenêtre",
                search_radius_m = search_radius_m,
            )
            return

        p_lat  = float(pred["lat"])
        p_lon  = float(pred["lon"])
        score  = float(pred["score"])
        match  = str(pred["match"])
        idx    = int(pred["index"])

        # Reinject predicted position as new GPS reference
        with self._state_lock:
            self.last_valid_lat   = p_lat
            self.last_valid_lon   = p_lon
            self.last_match_index = idx

        self.get_logger().info(
            f"🌍 GPS predicted  lat={p_lat:.6f}  lon={p_lon:.6f}  "
            f"score={score:.3f}  match={match}  [{loc_ms:.0f}ms]"
        )

        # ── Step 4: publish on ROS2 ──────────────────────────────────────────
        if ROS2_AVAILABLE:
            stamp = self.get_clock().now().to_msg()

            gps_msg = NavSatFix()
            gps_msg.header.stamp             = stamp
            gps_msg.header.frame_id          = "vision_gps"
            gps_msg.status.status            = NavSatStatus.STATUS_FIX
            gps_msg.status.service           = NavSatStatus.SERVICE_GPS
            gps_msg.latitude                 = p_lat
            gps_msg.longitude                = p_lon
            gps_msg.altitude                 = 0.0
            gps_msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN
            self.gps_publisher.publish(gps_msg)

            pose_msg = PoseStamped()
            pose_msg.header.stamp    = stamp
            pose_msg.header.frame_id = "map"
            pose_msg.pose.position.x = p_lat
            pose_msg.pose.position.y = p_lon
            pose_msg.pose.position.z = float(alt)
            self.pose_publisher.publish(pose_msg)

            self.get_logger().info(
                "📡 Predicted GPS published → "
                "/vision/predicted_gps & /vision/predicted_pose"
            )

        # ── Step 5: check destination reached ───────────────────────────────
        dist_to_b = None
        if self.target_lat is not None:
            dist_to_b = self._haversine(p_lat, p_lon, self.target_lat, self.target_lon)
            self.get_logger().info(f"📏 Distance to Point B: {dist_to_b:.1f}m")
            if dist_to_b < 150.0:
                self.get_logger().info(
                    f"🏁 DESTINATION REACHED! Distance to B: {dist_to_b:.1f}m"
                )
                self.mission_reached = True
                self._queue_status(
                    "finished", p_lat, p_lon,
                    message=f"Point B atteint ({dist_to_b:.1f}m)"
                )

        # ── Step 6: write final status ───────────────────────────────────────
        if not self.mission_reached:
            self._queue_status(
                "predicted", p_lat, p_lon,
                score           = score,
                match           = match,
                last_valid_lat  = lat,
                last_valid_lon  = lon,
                search_radius_m = search_radius_m,
                frame_id        = frame_id,
                dataset_images  = img_count,
                dataset_ms      = ds_ms,
                loc_ms          = loc_ms,
                total_ms        = ds_ms + loc_ms,
                message         = f"Position prédite ✅ (score={score:.3f})",
            )


    # ═══════════════════════════════════════════════════════════════════════════
    #  THREAD 3 — STATUS WRITER  (batched, atomic)
    # ═══════════════════════════════════════════════════════════════════════════

    def _status_writer_loop(self):
        """Flush pending status to disk every STATUS_WRITE_HZ seconds."""
        while not self._stop_event.is_set():
            time.sleep(STATUS_WRITE_HZ)
            data = None
            with self._status_lock:
                if self._status_dirty and self._pending_status is not None:
                    data = self._pending_status.copy()
                    self._status_dirty = False
            if data is None:
                continue
            try:
                tmp = str(self.gps_status_path) + ".tmp"
                with open(tmp, 'w') as f:
                    json.dump(data, f)
                os.replace(tmp, str(self.gps_status_path))
            except Exception as e:
                self.get_logger().error(f"[StatusWriter] {e}")
        self.get_logger().info("[StatusWriter] Stopped")

    def _queue_status(self, status, lat=None, lon=None, **extra):
        """Queue a status update (non-blocking). Flushed by StatusWriter thread."""
        data = {
            "status"    : status,
            "timestamp" : time.time(),
            "lat"       : lat,
            "lon"       : lon,
            **extra,
        }
        with self._status_lock:
            self._pending_status = data
            self._status_dirty   = True


    # ═══════════════════════════════════════════════════════════════════════════
    #  HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    def _haversine(self, lat1, lon1, lat2, lon2):
        R    = 6371000
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi    = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = (
            math.sin(dphi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _compute_search_radius(altitude_m: float) -> float:
        """Dynamic search radius based on altitude."""
        footprint_m = altitude_m * 0.24 * 640 / 1000
        return max(footprint_m * 3, altitude_m * 2)

    def _resolve_image_path(self, image_file: str):
        """Try multiple base paths to find the query image, with retry for race conditions."""
        candidates = [
            self.pkg_dir / "dataset" / image_file,
            self.pkg_dir / "dataset" / Path(image_file).name,
            self.pkg_dir / "dataset" / "frames_nogps" / Path(image_file).name,
            self.pkg_dir / "dataset" / "frames_gps"   / Path(image_file).name,
        ]
        for _ in range(10):
            for p in candidates:
                if p.exists():
                    return p
            time.sleep(0.2)
        return None

    def _clear_fallback_dataset(self, fallback_dir: Path):
        """Clear old dataset directory quickly."""
        try:
            if fallback_dir.exists():
                shutil.rmtree(fallback_dir, ignore_errors=True)
            fallback_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.get_logger().error(f"[_clear_fallback_dataset] {e}")

    def destroy_node(self):
        self._stop_event.set()
        super().destroy_node()


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main(args=None):
    if ROS2_AVAILABLE:
        rclpy.init(args=args)

    node = VisionNode()

    if ROS2_AVAILABLE:
        # LifecycleNode needs a MultiThreadedExecutor so callbacks + transitions
        # don't block each other.
        executor = rclpy.executors.MultiThreadedExecutor()
        executor.add_node(node)
        try:
            executor.spin()
        except KeyboardInterrupt:
            pass
        finally:
            node.destroy_node()
            rclpy.shutdown()
    else:
        # Standalone mode — run full lifecycle manually for testing
        print("\n[STANDALONE] Running lifecycle sequence …")
        node.on_configure(State())
        time.sleep(2)   # wait for warmup
        node.on_activate(State())
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            node.on_deactivate(State())
            node.on_cleanup(State())


if __name__ == '__main__':
    main()
