#!/usr/bin/env python3
"""The NAVERA side of the Isaac Sim flight: the vehicle's sensors, the real camera, the record.

Runs in the navera-humble container next to NAVERA's own nodes (run_navera_nodes.sh). It
reads the Isaac Sim run directory (isaac_flight.py: session.json, frames/, frames.jsonl) and
the same flight (flight_profile.Trajectory / Profile) and publishes what the vehicle's
equipment would give NAVERA — SIMULATED data, deliberately imperfect:

  camera   /isaac/camera/image_raw (sensor_msgs/Image), the real lens and sensor made from
           Isaac's wide distortion-free render: the Hikvision visible lens' fisheye model
           (calibration scaled to --lens-scale), vignetting, auto-exposure, motion blur over
           the exposure (the true motion), haze, sensor noise, H.264 (ffmpeg libx264, CBR 1 Mbit/s at 5 fps),
           delivered --delay-s after the exposure (stamped at arrival, like a network
           camera: NAVERA's auto_latency has to find the delay). No rolling shutter.
  IMU      /navera/sensors/imu 100 Hz: attitude = truth x a slowly wandering AHRS error,
           gyro = truth + turn-on bias (<= 0.27 deg/s) + white noise (0.077 deg/s per sample,
           the measured Insta360 One R figures), accel = specific force + 0.0015 g noise
  baro     /navera/vehicle/relative_alt 10 Hz: height above take-off + bias + drift + noise
  GPS      NMEA (GGA + RMC, 5 Hz, 12 satellites) on a pseudo-terminal read by NAVERA's real
           gps_node: truth + ~1.5 m Gauss-Markov noise (nmea_gps.py) until --gps-cut-s (live: when
           sitl_demo cuts it), then jammed (no fix); --spoof-mps drags it away from
           --spoof-start-s to the cut (a slow spoof)

Hardware in the loop (run_hil.sh: NAVERA runs on the real box, not next to this link):
  stream_url     the camera frames, at their delivery time, also go out as an H.264 network
                 camera: ffmpeg (libx264, zerolatency) publishes them to this RTSP URL (an RTSP
                 server, mediamtx, serves them to the box) — stream.csv logs each frame's send
                 time (this PC's clock) and its true exposure t
  nmea_tcp_port  the NMEA receiver is also served on this TCP port (the box's network GPS source)
  ros_camera     false: no /isaac/camera/image_raw (nobody on this PC reads it in HIL)

and records NAVERA's answers against the truth into --results (live, for live_plot.py):
  position.csv  every /navera/position (the arbiter's output): source, mode, sigma, error
                vs the truth at its sensor stamp
  day.csv       every /navera/estimate/day: the same + the error vs the truth at the frame's
                TRUE exposure, processing ms (frame_meta -> frame_done)
  live.json     latest status; navera_view/ the frames as NAVERA received them (small)
  summary.json  written at the end (Isaac's done.json): accepted %, errors after the GPS cut
"""
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time

import cv2
import numpy as np
import rclpy
import yaml
from geometry_msgs.msg import PointStamped
from navera_msgs.msg import NavStatus, PositionEstimate
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, Imu
from std_msgs.msg import Int32, String

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sim"))
from nmea_gps import NmeaGps  # noqa: E402
from flight_profile import GeoRef, LiveFeed, Profile, Trajectory, rpy_to_quat  # noqa: E402

G = 9.80665
SRC = {0: "unknown", 1: "gps", 2: "day", 3: "night", 4: "celestial", 5: "inertial", 6: "fused"}
MODE = {0: "measured", 1: "propagated", 2: "held", 3: "replayed"}
STATE = {0: "initializing", 1: "no_fix", 2: "fix", 3: "degraded"}


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def quat_to_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


# camera axes in the body for the nadir mount (navera_common.camera_model.R_BODY_NADIR_CAM)
R_BODY_CAM = np.array([[0.0, -1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])


class Terrain:
    """Scene ground height (scene Z) from prepare_scene's terrain.npy, bilinear."""

    def __init__(self, scene_dir, geo, mos):
        p = os.path.join(scene_dir, "terrain.npy")
        self.h = np.load(p) if os.path.exists(p) else None
        if self.h is not None:
            self.xw, self.ys = geo.to_en(mos["lat_s"], mos["lon_w"])
            self.xe, self.yn = geo.to_en(mos["lat_n"], mos["lon_e"])

    def z(self, e, n):
        if self.h is None:
            return 0.0
        k = self.h.shape[0] - 1
        fx = min(max((e - self.xw) / (self.xe - self.xw) * k, 0), k - 1e-6)
        fy = min(max((n - self.ys) / (self.yn - self.ys) * k, 0), k - 1e-6)
        x0, y0 = int(fx), int(fy)
        dx, dy = fx - x0, fy - y0
        h = self.h
        return float((h[y0, x0] * (1 - dx) + h[y0, x0 + 1] * dx) * (1 - dy)
                     + (h[y0 + 1, x0] * (1 - dx) + h[y0 + 1, x0 + 1] * dx) * dy)


class RealCamera:
    """Isaac's wide pinhole render -> the frame a real fisheye camera would deliver."""

    def __init__(self, lens: dict, render: dict, fps: float, bitrate: str, haze_vis_m: float, seed: int):
        self.w, self.h = int(lens["image_width"]), int(lens["image_height"])
        K = np.array(lens["camera_matrix"], np.float64).reshape(3, 3)
        D = np.array(lens["distortion"], np.float64).reshape(4, 1)
        self.f = K[0, 0]
        uu, vv = np.meshgrid(np.arange(self.w, dtype=np.float64), np.arange(self.h, dtype=np.float64))
        pts = np.stack([uu, vv], -1).reshape(-1, 1, 2)
        und = cv2.fisheye.undistortPoints(pts, K, D).reshape(self.h, self.w, 2)
        rw, rh = int(render["width"]), int(render["height"])
        fr = (rw / 2) / math.tan(math.radians(render["hfov_deg"]) / 2)
        self.map_x = (und[..., 0] * fr + rw / 2 - 0.5).astype(np.float32)
        self.map_y = (und[..., 1] * fr + rh / 2 - 0.5).astype(np.float32)
        r2 = und[..., 0] ** 2 + und[..., 1] ** 2
        self.cos_t = (1.0 / np.sqrt(1.0 + r2)).astype(np.float32)          # cos of the ray's angle
        self.vignette = (0.35 + 0.65 * self.cos_t ** 3)[..., None].astype(np.float32)
        self.outside = (np.abs(self.map_x - rw / 2) > rw / 2 - 1) | (np.abs(self.map_y - rh / 2) > rh / 2 - 1)
        self.haze_vis_m = haze_vis_m
        self.to_lin = ((np.arange(256) / 255.0) ** 2.2).astype(np.float32)              # 8-bit -> linear
        self.to_srgb = ((np.arange(4096) / 4095.0) ** (1 / 2.2) * 255 + 0.5).astype(np.uint8)
        self.gain = None
        self.rng = np.random.default_rng(seed)
        self.fps = fps
        enc = ["ffmpeg", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{self.w}x{self.h}",
               "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
               "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", bitrate, "-g", str(int(2 * fps)),
               "-pix_fmt", "yuv420p", "-f", "h264", "-"]
        dec = ["ffmpeg", "-loglevel", "error", "-flags", "low_delay", "-probesize", "32", "-f", "h264", "-i", "-",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
        self.enc = subprocess.Popen(enc, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.dec = subprocess.Popen(dec, stdin=self.enc.stdout, stdout=subprocess.PIPE)
        self.out_q = queue.Queue()
        self.pending = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        n = self.w * self.h * 3
        while True:
            buf = self.dec.stdout.read(n)
            if len(buf) < n:
                return
            tag = self.pending.get()
            self.out_q.put((tag, np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)))

    # weather / lens conditions (campaign), set by IsaacLink from its parameters
    cond = {}

    def _conditions(self, lens, t):
        """Effects Isaac's renderer does not give, applied in linear light before exposure."""
        c, h, w = self.cond, self.h, self.w
        if c.get("season", 0) > 0:          # greener vegetation / fields than in the map's season
            k = c["season"]
            g = lens[..., 1]
            veg = np.clip((g - np.maximum(lens[..., 0], lens[..., 2]) * 0.92) * 20.0 + 0.3, 0, 1)[..., None]
            tint = lens * np.array([0.75, 1.3, 0.8], np.float32)
            lens = lens * (1 - k * veg) + tint * (k * veg) * 0.9 + lens * (k * (1 - veg)) * 0.0
        if c.get("fog", 0) > 0:             # fog patches drifting through the view
            if not hasattr(self, "_fog"):
                n = self.rng.random((24, 40)).astype(np.float32)
                self._fog = cv2.resize(np.tile(n, (2, 2)), (2 * w, 2 * h), interpolation=cv2.INTER_CUBIC)
            ox, oy = int(t * 6) % w, int(t * 3) % h
            f = self._fog[oy:oy + h, ox:ox + w]
            f = np.clip((f - (1 - c["fog"])) / 0.25, 0, 1)[..., None]
            lens = lens * (1 - 0.9 * f) + np.float32(0.7) * 0.9 * f
        if c.get("glare", 0) > 0:           # the sun in the lens: veiling glare + a flare
            if not hasattr(self, "_glare"):
                yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
                cx, cy = w * 0.82, h * 0.15
                r = np.hypot(xx - cx, yy - cy) / w
                streak = np.exp(-np.abs(yy - cy - 0.3 * (xx - cx)) / 6.0) * np.exp(-r * 2.0)
                self._glare = (np.exp(-r * 6.0) * 1.5 + 0.25 * np.exp(-r * 1.5) + 0.6 * streak)[..., None]
            lens = lens + c["glare"] * self._glare * np.array([1.0, 0.95, 0.85], np.float32)
        if c.get("rain", 0) > 0:            # raindrops on the window (blurred spots) + streaks
            k = c["rain"]
            if not hasattr(self, "_drops") or self.rng.random() < 0.1:
                m = np.zeros((h, w), np.float32)
                for _ in range(int(60 * k)):
                    cv2.circle(m, (int(self.rng.integers(0, w)), int(self.rng.integers(0, h))),
                               int(self.rng.integers(6, 30)), 1.0, -1)
                self._drops = cv2.GaussianBlur(m, (0, 0), 3)[..., None]
            blur = cv2.GaussianBlur(lens, (0, 0), 9)
            lens = lens * (1 - self._drops) + blur * self._drops * 1.1
            st = np.zeros((h, w), np.float32)
            for _ in range(int(400 * k)):
                x0, y0 = int(self.rng.integers(0, w)), int(self.rng.integers(0, h))
                cv2.line(st, (x0, y0), (x0 + 6, y0 + 40), 0.35, 1)
            lens = lens + st[..., None] * 0.6 + np.float32(0.04 * k)
        if c.get("outage"):                 # a cloud bank: nothing but grey
            lens = np.full_like(lens, 0.55) + self.rng.normal(0, 0.01, lens.shape).astype(np.float32)
        return lens

    def process(self, img, blur_px, agl_m, tag):
        """Render -> lens -> exposure -> blur -> haze -> noise -> H.264 (async: out_q)."""
        lens = cv2.remap(img, self.map_x, self.map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        lens = self.to_lin[lens]                                                  # linear light
        lens *= self.vignette
        lens[self.outside] = 0.0
        # haze: airlight over the slant range (AGL / cos theta)
        if self.haze_vis_m > 0:
            t = np.exp(-3.0 * (agl_m / self.cos_t) / self.haze_vis_m)[..., None]
            lens = lens * t + np.array(self.cond.get("haze_rgb", (0.55, 0.57, 0.6)), np.float32) * (1 - t) * 0.35
        lens = self._conditions(lens, tag[0])
        # auto-exposure: the mean of the centre towards 18 % grey, adapting over ~1 s
        c = float(lens[self.h // 4:3 * self.h // 4:2, self.w // 4:3 * self.w // 4:2].mean())
        want = 0.18 / max(c, 1e-4)
        self.gain = want if self.gain is None else self.gain * (want / self.gain) ** min(1.0, 1.0 / max(self.fps, 1.0))
        lens *= self.gain
        if blur_px is not None and math.hypot(*blur_px) > 0.7:
            L = int(math.ceil(math.hypot(*blur_px))) | 1
            k = np.zeros((L, L), np.float32)
            cx = L // 2
            cv2.line(k, (int(round(cx - blur_px[0] / 2)), int(round(cx - blur_px[1] / 2))),
                     (int(round(cx + blur_px[0] / 2)), int(round(cx + blur_px[1] / 2))), 1.0, 1)
            lens = cv2.filter2D(lens, -1, k / k.sum())
        # sensor noise (shot + read), in linear light, then the camera's gamma
        sig = np.sqrt(np.clip(lens, 0, None) * 0.0008 + 0.00002)
        lens = lens + self.rng.standard_normal(lens.shape, dtype=np.float32) * sig
        out = self.to_srgb[np.clip(lens * 4095.0, 0, 4095).astype(np.uint16)]
        self.pending.put(tag)
        self.enc.stdin.write(out.tobytes())
        self.enc.stdin.flush()

    def exposure_s(self):
        """Exposure time the auto-exposure chose (daylight: a few ms)."""
        return float(min(max(0.002 * (self.gain or 1.0), 0.0003), 0.03))


class IsaacLink(Node):
    def __init__(self):
        super().__init__("isaac_link")
        dyn = ParameterDescriptor(dynamic_typing=True)                   # 45 or 45.0 from the launcher
        p = lambda n, d: self.declare_parameter(n, d, dyn).value       # noqa: E731
        self.run_dir = p("run_dir", "/isaac/runs/run")
        self.scene_dir = p("scene_dir", "/isaac/scenes/kalaa")
        self.traj_dir = p("traj_dir", "/isaac/traj")
        self.results = p("results", "/results")
        self.lens_file = p("lens_file", "/data/lens/hik_visible_lens.yaml")
        self.lens_scale = float(p("lens_scale", 0.5))
        self.delay_s = float(p("delay_s", 1.3))
        self.gps_cut_s = float(p("gps_cut_s", 60.0))
        self.spoof_mps = float(p("spoof_mps", 0.0))
        self.spoof_start_s = float(p("spoof_start_s", 30.0))
        self.spoof_bearing = float(p("spoof_bearing_deg", 45.0))
        self.spoof_lead_s = float(p("spoof_lead_s", 30.0))       # live: seconds of spoof before the cut
        self._spoof_t0 = None
        self.haze_vis_m = float(p("haze_visibility_m", 12000.0))
        self.bitrate = str(p("bitrate", "1M"))
        self.camera_fps = float(p("camera_fps", 5.0))
        # live: the vehicle is flown NOW by ArduPilot SITL (sitl_demo.py streams its truth here);
        # the GPS is cut when sitl_demo says so
        self.truth_port = int(p("truth_udp_port", 0))
        # campaign conditions (camera post-effects, sensors)
        self.cond = dict(season=float(p("season", 0.0)), fog=float(p("fog", 0.0)), glare=float(p("glare", 0.0)),
                         rain=float(p("rain", 0.0)))
        hz = str(p("haze_rgb", ""))
        if hz:
            self.cond["haze_rgb"] = tuple(float(v) for v in hz.split("/"))
        self.outages = [tuple(float(v) for v in o.split("/")) for o in str(p("outages", "")).split(",") if o]
        self.gyro_bias_fixed = str(p("gyro_bias_dps", ""))
        self.imu_vib = float(p("imu_vibration_g", 0.0))
        seed = int(p("seed", 3))
        self.rng = np.random.default_rng(seed)
        os.makedirs(os.path.join(self.results, "navera_view"), exist_ok=True)
        # the GPS receiver: NMEA on a pseudo-terminal read by NAVERA's REAL gps_node (satellites,
        # HDOP, fix quality, as from a real module): navera_tools/sim/nmea_gps.py
        self.nmea = NmeaGps(seed)
        with open(os.path.join(self.results, "gps_port"), "w") as f:
            f.write(self.nmea.port)
        # hardware in the loop: the same NMEA on TCP, the camera as an RTSP stream
        nmea_tcp = int(p("nmea_tcp_port", 0))
        if nmea_tcp:
            self.nmea.serve_tcp(nmea_tcp)
            self.get_logger().info(f"NMEA receiver also on TCP port {nmea_tcp}")
        self.stream_url = str(p("stream_url", ""))
        self.stream_bitrate = str(p("stream_bitrate", "4M"))
        self.stream_gop = int(p("stream_gop", 5))
        self.ros_camera = bool(p("ros_camera", True))
        self.stream_q = queue.Queue(maxsize=10)
        self.stream_f = None

        lens = yaml.safe_load(open(self.lens_file))
        sc = self.lens_scale
        K = list(lens["camera_matrix"])
        K = [K[0] * sc, 0.0, K[2] * sc, 0.0, K[4] * sc, K[5] * sc, 0.0, 0.0, 1.0]
        self.lens = dict(model="fisheye", image_width=int(round(lens["image_width"] * sc)),
                         image_height=int(round(lens["image_height"] * sc)), camera_matrix=K,
                         distortion=list(lens["distortion"]),
                         source=f"{lens.get('source', '')} — scaled x{sc} (sub-stream), model fisheye")
        with open(os.path.join(self.results, "lens.yaml"), "w") as f:
            yaml.safe_dump(self.lens, f)
        scene = json.load(open(os.path.join(self.scene_dir, "scene.json")))
        self.geo = GeoRef(scene["lat0"], scene["lon0"])
        self.z_ref = z_ref = float(scene["z_ref_m"])
        self.terrain = Terrain(self.scene_dir, self.geo, scene["mosaic"])
        self.s, self.cam, self.seed = None, None, seed
        if self.truth_port:
            self.prof = LiveFeed(self.truth_port, self.geo, z_ref)
            self.get_logger().info(f"waiting for the live vehicle (SITL) on UDP {self.truth_port} …")
            while not self.prof.ready():
                self.prof.poll()
                time.sleep(0.05)
            self.t0 = float(self.prof.last["t0"])
            self.home_alt = z_ref
            self.gps_cut_s = float("inf")
        else:
            self._wait_session()
            self.t0 = float(self.s["t0_wall"])
            if self.s.get("traj"):
                self.prof = Trajectory(os.path.join(self.traj_dir, self.s["traj"]), self.geo, z_ref)
                h = self.prof.meta.get("home", "").split(",")
                self.home_alt = float(h[2]) if len(h) == 3 else z_ref
            else:
                pr = self.s["profile"]
                self.prof = Profile(radius_m=pr["radius_m"], speed_mps=pr["speed_mps"], height_m=pr["height_m"])
                self.home_alt = z_ref
        # sensor errors drawn once per flight
        self.gyro_bias = self.rng.uniform(-0.27, 0.27, 3)                       # deg/s
        if self.gyro_bias_fixed:
            self.gyro_bias = np.array([float(v) for v in self.gyro_bias_fixed.split("/")])
        self.att_bias = np.array([self.rng.normal(0, 0.3), self.rng.normal(0, 0.3), self.rng.normal(0, 1.5)])
        self.att_walk = np.zeros(3)
        self.baro_bias, self.baro_walk = self.rng.normal(0, 1.5), 0.0
        self.gps_err = np.zeros(2)

        self.pub_img = self.create_publisher(Image, "/isaac/camera/image_raw", qos_profile_sensor_data)
        self.pub_imu = self.create_publisher(Imu, "/navera/sensors/imu", qos_profile_sensor_data)
        self.pub_baro = self.create_publisher(PointStamped, "/navera/vehicle/relative_alt", qos_profile_sensor_data)
        # the sensors and the camera delivery run in their own threads, not in the executor: a
        # 3 MB image publish or the subscriptions must never hold the IMU / GPS back (measured
        # with executor timers: the 5 Hz GPS went silent for 35-40 s at a time)
        self._next = {"baro": 0.0, "gps": 0.0}
        self.create_subscription(PositionEstimate, "/navera/position", self._on_pos, 10)
        self.create_subscription(PositionEstimate, "/navera/estimate/day", self._on_day, 10)
        self.create_subscription(NavStatus, "/navera/nav_status", self._on_nav, 10)
        self.create_subscription(String, "/day/day_status", self._on_status, 10)
        self.create_subscription(String, "/day/frame_meta", self._on_meta, 10)
        self.create_subscription(Int32, "/day/frame_done", self._on_done, 10)

        self.arrival = {}            # header stamp ns -> true exposure t
        self.meta_t = {}             # live_camera frame_id -> (received wall, true exposure t)
        self.proc_ms = {}
        self.live = dict(state="initializing", source="-", t=0.0, gps="on", frames_in=0, frames_out=0)
        self.pos_f = open(os.path.join(self.results, "position.csv"), "a")
        self.day_f = open(os.path.join(self.results, "day.csv"), "a")
        if self.pos_f.tell() == 0:
            self.pos_f.write("t,lat,lon,source,mode,valid,sigma_m,truth_lat,truth_lon,err_m,gps\n")
            self.day_f.write("t,frame,lat,lon,mode,valid,sigma_m,err_m,err_frame_m,t_exposure,proc_ms,reason\n")
        self.proc_f = open(os.path.join(self.results, "proc.csv"), "a")
        if self.proc_f.tell() == 0:
            self.proc_f.write("t,frame,proc_ms\n")
        self.events = open(os.path.join(self.results, "events.jsonl"), "a")
        self.delivery = []           # (deliver at wall, header stamp, image)
        self.done = False
        self.ekf_f = open(os.path.join(self.results, "ekf.csv"), "a")
        if self.ekf_f.tell() == 0:
            self.ekf_f.write("t,ekf_lat,ekf_lon,truth_lat,truth_lon,err_m,gps\n")
        self._last_ekf = None
        threading.Thread(target=self._frames, daemon=True).start()
        threading.Thread(target=self._loop, args=(0.01, self._tick), daemon=True).start()
        threading.Thread(target=self._loop, args=(0.02, self._deliver), daemon=True).start()
        if self.stream_url:
            self.stream_f = open(os.path.join(self.results, "stream.csv"), "a")
            if self.stream_f.tell() == 0:
                self.stream_f.write("wall,t_exposure,n\n")
            threading.Thread(target=self._stream_out, daemon=True).start()
        self.get_logger().info(f"flight t0 {self.t0:.1f}, vehicle {self.prof.vehicle if self.truth_port else 'recorded'}, lens "
                               f"{self.lens['image_width']}x{self.lens['image_height']} fisheye, delay {self.delay_s} s, "
                               f"GPS cut at {self.gps_cut_s} s" + (f", spoof {self.spoof_mps} m/s" if self.spoof_mps else ""))

    def _wait_session(self):
        """Isaac Sim's session.json of THIS run (never an older one), then the camera model."""
        self.get_logger().info(f"waiting for {self.run_dir}/session.json (Isaac Sim) …")
        sess = os.path.join(self.run_dir, "session.json")
        started = time.time()
        while not (os.path.exists(sess) and os.path.getmtime(sess) > started - 5.0):
            time.sleep(0.5)
        time.sleep(0.5)
        self.s = json.load(open(sess))
        self.cam = RealCamera(self.lens, self.s["render"], self.camera_fps, self.bitrate, self.haze_vis_m, self.seed)
        self.cam.cond = dict(self.cond)
        threading.Thread(target=self._camera_out, daemon=True).start()

    def _live_tick(self):
        """Live: new truth packets; the GPS cut; the autopilot's EKF position vs the truth."""
        self.prof.poll()
        d = self.prof.last or {}
        t = self.t_now()
        if not d.get("gps", True) and not math.isfinite(self.gps_cut_s):
            self.gps_cut_s = t
            self.get_logger().info(f"GPS CUT at t={t:.1f} s (sitl_demo): NAVERA's output is now vision only")
            open(os.path.join(self.results, "gps_cut"), "w").write(f"{t:.2f}")
        self.live["phase"], self.live["ap_mode"] = d.get("phase", "-"), d.get("mode", "-")
        ekf = d.get("ekf")
        if ekf and ekf != self._last_ekf:
            self._last_ekf = ekf
            err, tl, tn = self._err(ekf[0], ekf[1], d["t"])
            self.ekf_f.write(f"{d['t']:.3f},{ekf[0]:.7f},{ekf[1]:.7f},{tl:.7f},{tn:.7f},{err:.2f},"
                             f"{'on' if d.get('gps', True) else 'cut'}\n")
            self.ekf_f.flush()
            self.live["ekf_err_m"] = round(err, 1)

    # ── truth ────────────────────────────────────────────────────────────
    def t_now(self):
        return time.time() - self.t0

    def truth(self, t):
        st = self.prof.state(max(t, 0.0))
        lat, lon = self.geo.to_latlon(st.e, st.n)
        return st, lat, lon

    def _stamp(self, msg_header, wall):
        msg_header.stamp.sec, msg_header.stamp.nanosec = int(wall), int((wall % 1) * 1e9)

    # ── sensors ──────────────────────────────────────────────────────────
    @staticmethod
    def _loop(period, fn):
        nxt = time.time()
        while rclpy.ok():
            try:
                fn()
            except Exception as e:                                       # noqa: BLE001 — keep going
                print(f"isaac_link {fn.__name__}: {e!r}", flush=True)
            nxt = max(nxt + period, time.time() - period)
            time.sleep(max(0.0, nxt - time.time()))

    def _tick(self):
        now = time.time()
        for name, period, fn in (("gps", 0.2, self._gps), ("baro", 0.1, self._baro)):
            if now >= self._next[name]:
                self._next[name] = max(self._next[name] + period, now - period)
                fn()
        self._imu()

    def _imu(self):
        if self.truth_port:
            self._live_tick()
        t = self.t_now()
        if t < -5:
            return
        st, _, _ = self.truth(t)
        self.att_walk += self.rng.normal(0, [0.002, 0.002, 0.004]) - 0.001 * self.att_walk
        err = self.att_bias + self.att_walk
        q_true = st.quat_enu()
        q_err = rpy_to_quat(err[0], err[1], err[2])
        q = quat_mul(q_err, q_true)
        m = Imu()
        self._stamp(m.header, time.time())
        m.header.frame_id = "base_link"
        m.orientation.x, m.orientation.y, m.orientation.z, m.orientation.w = q
        rates = np.array([st.p, st.q, st.r]) + np.radians(self.gyro_bias + self.rng.normal(0, 0.077, 3))
        m.angular_velocity.x, m.angular_velocity.y, m.angular_velocity.z = (float(v) for v in rates)
        R = quat_to_matrix(q_true)
        f_body = R.T @ np.array([st.ae, st.an, st.au + G]) + self.rng.normal(0, (0.0015 + self.imu_vib) * G, 3)
        m.linear_acceleration.x, m.linear_acceleration.y, m.linear_acceleration.z = (float(v) for v in f_body)
        m.orientation_covariance[0] = m.orientation_covariance[4] = math.radians(0.5) ** 2
        m.orientation_covariance[8] = math.radians(2.0) ** 2
        self.pub_imu.publish(m)

    def _baro(self):
        t = self.t_now()
        if t < -5:
            return
        st, _, _ = self.truth(t)
        rel = (st.alt_msl - self.home_alt) if math.isfinite(st.alt_msl) else st.u
        self.baro_walk += self.rng.normal(0, 0.03)
        m = PointStamped()
        self._stamp(m.header, time.time())
        m.point.z = float(rel + self.baro_bias + self.baro_walk + self.rng.normal(0, 0.3))
        self.pub_baro.publish(m)

    def _gps(self):
        t = self.t_now()
        if t < -5:
            return
        st, lat, lon = self.truth(t)
        cut = t >= self.gps_cut_s or (self.truth_port and not (self.prof.last or {}).get("gps", True))
        if cut:                                    # jammed: the receiver talks, without a fix
            self.nmea.set_mode("jammed")
            self.live["gps"] = "cut (jammed)"
        else:
            de = dn = 0.0
            if self.truth_port and self.spoof_mps > 0 and self._spoof_t0 is None:
                eta = (self.prof.last or {}).get("cut_eta")      # live: the spoof starts before the cut
                if eta is not None and eta <= self.spoof_lead_s:
                    self._spoof_t0 = t
                    self.get_logger().warn(f"GPS SPOOF starts: {self.spoof_mps} m/s, {eta:.0f} s before the cut")
            t_sp = self._spoof_t0 if self.truth_port else self.spoof_start_s
            if self.spoof_mps > 0 and t_sp is not None and t > t_sp:
                d = self.spoof_mps * (t - t_sp)
                de, dn = d * math.sin(math.radians(self.spoof_bearing)), d * math.cos(math.radians(self.spoof_bearing))
                self.live["gps"] = f"SPOOFED +{d:.0f} m"
            else:
                self.live["gps"] = "on"
            lat, lon = self.geo.to_latlon(st.e + de, st.n + dn)
        alt = st.alt_msl if math.isfinite(st.alt_msl) else st.u
        self.nmea.tick(lat, lon, alt, math.hypot(st.ve, st.vn), math.degrees(math.atan2(st.ve, st.vn)), 0.2)

    # ── camera ───────────────────────────────────────────────────────────
    def _blur(self, t, exp_s):
        """Pixel motion of the image centre over the exposure (true pose)."""
        pts = []
        for tt in (t, t + exp_s):
            st = self.prof.state(tt)
            q = rpy_to_quat(0.0, 0.0, st.yaw) if (self.s or {}).get("render", {}).get("gimbal") else st.quat_enu()
            R = quat_to_matrix(q) @ R_BODY_CAM
            pts.append((np.array([st.e, st.n, st.u]), R))
        (p0, R0), (p1, R1) = pts
        ray = R0 @ np.array([0.0, 0.0, 1.0])
        if ray[2] > -0.1:
            return None
        g = self.terrain.z(p0[0], p0[1])
        X = p0 + ray * (g - p0[2]) / ray[2]
        c = R1.T @ (X - p1)
        return (self.cam.f * c[0] / c[2], self.cam.f * c[1] / c[2])

    def _frames(self):
        """Tail Isaac's frames.jsonl and turn frames into the real camera's frames, at the camera
        rate --camera_fps: when processing falls behind, the backlog is skipped (newest frame
        first), as a live camera drops frames instead of delivering them late."""
        if self.cam is None:
            self._wait_session()
        path = os.path.join(self.run_dir, "frames.jsonl")
        while not os.path.exists(path):
            time.sleep(0.2)
        last_t, n, busy = -1e9, 0, []
        with open(path) as fh:
            buf, pending = "", None
            while rclpy.ok():
                line = fh.readline()
                if line:
                    buf += line
                    if buf.endswith("\n"):
                        pending, buf = json.loads(buf), ""
                    continue                                    # read up to the newest line
                if pending is None or float(pending["t"]) - last_t < 0.98 / self.camera_fps:
                    if os.path.exists(os.path.join(self.run_dir, "done.json")):
                        break
                    time.sleep(0.01)
                    continue
                rec, pending = pending, None
                img = cv2.imread(os.path.join(self.run_dir, "frames", rec["file"]))
                if img is None:
                    continue
                t0 = time.time()
                t = float(rec["t"])
                st = self.prof.state(t)
                agl = st.u - self.terrain.z(st.e, st.n)
                self.cam.cond["outage"] = any(math.isfinite(self.gps_cut_s) and
                                              self.gps_cut_s + a <= t < self.gps_cut_s + a + d for a, d in self.outages)
                self.cam.process(img, self._blur(t, self.cam.exposure_s()), agl, (t, rec["i"]))
                last_t, n = t, n + 1
                busy.append(time.time() - t0)
                self.live["frames_in"] = n
                if n % 50 == 0:
                    b = sorted(busy[-50:])
                    self.get_logger().info(f"camera model: {1000 * b[len(b) // 2]:.0f} ms/frame (median of 50), "
                                           f"lag {self.t_now() - t:.2f} s behind the render")
        self.cam.enc.stdin.close()
        time.sleep(3.0)
        self.done = True

    def _camera_out(self):
        k = 0
        while True:
            (t, i), img = self.cam.out_q.get()
            deliver = self.t0 + t + self.delay_s + abs(self.rng.normal(0, 0.03))
            self.delivery.append((deliver, t, img))
            if k % 5 == 0:
                small = cv2.resize(img, (img.shape[1] // 2, img.shape[0] // 2), interpolation=cv2.INTER_AREA)
                cv2.imwrite(os.path.join(self.results, "navera_view", f"n_{k // 5:05d}.jpg"), small,
                            [cv2.IMWRITE_JPEG_QUALITY, 85])
                tmp = os.path.join(self.results, "latest_frame.tmp.jpg")
                cv2.imwrite(tmp, small)
                os.replace(tmp, os.path.join(self.results, "latest_frame.jpg"))
            k += 1

    def _stream_out(self):
        """The delivered frames as an H.264 RTSP stream (HIL): one ffmpeg, wall-clock stamps,
        a keyframe every stream_gop frames (a receiver joining late decodes within ~1 s)."""
        enc, n = None, 0
        while True:
            t, img = self.stream_q.get()
            if enc is None or enc.poll() is not None:
                h, w = img.shape[:2]
                enc = subprocess.Popen(
                    ["ffmpeg", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
                     "-use_wallclock_as_timestamps", "1", "-i", "-", "-c:v", "libx264", "-preset", "ultrafast",
                     "-tune", "zerolatency", "-pix_fmt", "yuv420p", "-b:v", self.stream_bitrate,
                     "-g", str(self.stream_gop), "-f", "rtsp", "-rtsp_transport", "tcp", self.stream_url],
                    stdin=subprocess.PIPE)
                self.get_logger().info(f"camera stream: {w}x{h} H.264 {self.stream_bitrate} -> {self.stream_url}")
            try:
                enc.stdin.write(img.tobytes())
                enc.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                self.get_logger().error(f"camera stream: ffmpeg {e!r}, restarting it")
                enc = None
                continue
            self.stream_f.write(f"{time.time():.4f},{t:.4f},{n}\n")
            self.stream_f.flush()
            n += 1

    def _deliver(self):
        now = time.time()
        while self.delivery and self.delivery[0][0] <= now:
            _, t, img = self.delivery.pop(0)
            if self.stream_url:
                try:
                    self.stream_q.put_nowait((t, img))
                except queue.Full:
                    self.get_logger().warn("camera stream: encoder behind, frame dropped", throttle_duration_sec=5.0)
            if not self.ros_camera:
                self.live["frames_out"] += 1
                continue
            m = Image()
            self._stamp(m.header, now)
            m.header.frame_id = "camera"
            m.height, m.width, m.encoding, m.step = img.shape[0], img.shape[1], "bgr8", img.shape[1] * 3
            m.data = img.tobytes()
            self.arrival[m.header.stamp.sec * 1_000_000_000 + m.header.stamp.nanosec] = t
            self.pub_img.publish(m)
            self.live["frames_out"] += 1
        if self.done and not self.delivery:
            self._summary()
            self.done = False

    # ── record ───────────────────────────────────────────────────────────
    def _err(self, lat, lon, t):
        _, tl, tn = self.truth(t)
        e1, n1 = self.geo.to_en(lat, lon)
        e0, n0 = self.geo.to_en(tl, tn)
        return math.hypot(e1 - e0, n1 - n0), tl, tn

    @staticmethod
    def _sigma(m):
        return math.sqrt(m.position_covariance[0]) if m.position_covariance[0] > 0 else float("nan")

    def _on_pos(self, m):
        ts = m.sensor_stamp if m.sensor_stamp.sec else m.header.stamp
        t = ts.sec + ts.nanosec * 1e-9 - self.t0
        err, tl, tn = self._err(m.latitude, m.longitude, t) if m.valid else (float("nan"), 0, 0)
        self.pos_f.write(f"{t:.3f},{m.latitude:.7f},{m.longitude:.7f},{SRC.get(m.source, m.source)},"
                         f"{MODE.get(m.mode, m.mode)},{int(m.valid)},{self._sigma(m):.1f},{tl:.7f},{tn:.7f},"
                         f"{err:.2f},{self.live['gps']}\n")
        self.pos_f.flush()
        self.live.update(t=round(self.t_now(), 1), source=SRC.get(m.source, "?"), mode=MODE.get(m.mode, "?"),
                         err_m=None if math.isnan(err) else round(err, 1),
                         sigma_m=None if math.isnan(self._sigma(m)) else round(self._sigma(m), 1))
        self._write_live()

    def _on_day(self, m):
        ts = m.sensor_stamp
        t = ts.sec + ts.nanosec * 1e-9 - self.t0
        mt = self.meta_t.get(m.frame_index)
        t_exp = mt[1] if mt else float("nan")
        err = err_f = float("nan")
        if m.valid:
            err = self._err(m.latitude, m.longitude, t)[0]
            if mt:
                err_f = self._err(m.latitude, m.longitude, t_exp)[0]
        self.day_f.write(f"{t:.3f},{m.frame_index},{m.latitude:.7f},{m.longitude:.7f},{MODE.get(m.mode, m.mode)},"
                         f"{int(m.valid)},{self._sigma(m):.1f},{err:.2f},{err_f:.2f},{t_exp:.3f},"
                         f"{self.proc_ms.get(m.frame_index, float('nan')):.0f},\"{m.reason[:80]}\"\n")
        self.day_f.flush()

    def _on_nav(self, m):
        self.live["state"] = STATE.get(m.state, "?")
        self.live["reason"] = m.reason[:120]

    def _on_status(self, m):
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        self.live["day"] = {k: d.get(k) for k in ("frame_id", "success", "source", "reason", "inliers", "score")
                            if k in d}
        if "latency" in d:
            self.live["latency"] = d["latency"]
        self.events.write(json.dumps(dict(t=round(self.t_now(), 3), day_status=d)) + "\n")
        self.events.flush()

    def _on_meta(self, m):
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        t_exp = self.arrival.get(int(d.get("image_stamp_ns", 0)))
        self.meta_t[int(d["frame_id"])] = (time.time(), t_exp if t_exp is not None else float("nan"))

    def _on_done(self, m):
        mt = self.meta_t.get(m.data)
        if mt:
            self.proc_ms[m.data] = 1000.0 * (time.time() - mt[0])
            self.proc_f.write(f"{self.t_now():.3f},{m.data},{self.proc_ms[m.data]:.0f}\n")
            self.proc_f.flush()

    def _write_live(self):
        tmp = os.path.join(self.results, "live.tmp.json")
        json.dump(self.live, open(tmp, "w"))
        os.replace(tmp, os.path.join(self.results, "live.json"))

    def _summary(self):
        from summarise import summarise
        s = summarise(self.results, self.gps_cut_s)
        s.update(session={k: v for k, v in (self.s or {}).items() if k != "scene"}, gps_cut_s=self.gps_cut_s,
                 spoof_mps=self.spoof_mps, delay_s=self.delay_s, lens=self.lens, haze_visibility_m=self.haze_vis_m,
                 bitrate=self.bitrate, gyro_bias_dps=[round(v, 3) for v in self.gyro_bias],
                 att_bias_deg=[round(v, 2) for v in self.att_bias])
        json.dump(s, open(os.path.join(self.results, "summary.json"), "w"), indent=1)
        self.get_logger().info("summary: " + json.dumps(s.get("after_cut")))
        open(os.path.join(self.results, "finished"), "w").write("1")


def main():
    rclpy.init()
    node = IsaacLink()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
