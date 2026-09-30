"""Mission area preparation and the camera for the REAL day-vision node.

AreaManager   plans the corridor around a route (which MBTiles tiles it needs,
              which the map lacks) and prepares the day-vision dataset for it
              with the product tool `prepare_area.py` (run as a subprocess,
              progress read from its JSON lines). Prepared areas are kept in
              <work>/areas/<id> and reused.
DayCamera     the vehicle's downward camera: renders what it would see from the
              true position and altitude (north-up — the image is assumed
              de-rotated with the heading), and feeds it to day_subscriber with
              the same protocol as camera_pkg (latched start + ready handshake,
              image + frame_meta paired on the image stamp, one frame in flight
              until frame_done). It records the vision node's own status
              (search circle, candidates, match, score) for the control page.

The picture is cut from the same satellite map vision matches against: it
shows how the pipeline behaves, not how accurate it is on a real camera.
"""
import hashlib
import io
import json
import math
import os
import subprocess
import threading
import time
from collections import deque

from PIL import Image as PILImage, ImageEnhance, ImageFilter, ImageOps
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, Int32, String

from day_pkg.prepare_area import plan_tiles, tile_nw

HFOV_DEG = 84.0          # camera horizontal field of view
FRAME_W, FRAME_H = 640, 480
BUFFER_M = 1000.0        # corridor half-width around the route


def _tile_xy(lat, lon, z):
    n = 2 ** z
    r = math.radians(lat)
    return ((lon + 180.0) / 360.0 * n,
            (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n)


class AreaManager:
    def __init__(self, mbtiles, work_dir, log):
        self.mbtiles = mbtiles
        self.dir = os.path.join(work_dir, "areas")
        os.makedirs(self.dir, exist_ok=True)
        self.log = log
        self.lock = threading.Lock()
        self.plan = None           # last plan (for the page)
        self.prep = None           # {"id", "stage", "done", "total", "status", "error"}
        self._proc = None

    @staticmethod
    def area_id(route, buffer_m):
        key = json.dumps([[round(a, 5), round(b, 5)] for a, b in route] + [buffer_m])
        return hashlib.sha1(key.encode()).hexdigest()[:12]

    def path(self, aid):
        return os.path.join(self.dir, aid)

    def is_prepared(self, aid):
        return os.path.exists(os.path.join(self.path(aid), "descriptors_cache.npz"))

    def make_plan(self, route, buffer_m=BUFFER_M):
        p = plan_tiles(self.mbtiles, route, buffer_m, 17)
        aid = self.area_id(route, buffer_m)
        length = sum(math.hypot((b[1] - a[1]) * 111320 * math.cos(math.radians(a[0])),
                                (b[0] - a[0]) * 111320) for a, b in zip(route, route[1:]))
        plan = dict(id=aid, route=route, buffer_m=buffer_m, zoom=17, length_m=length,
                    tiles=len(p["needed"]), present=p["present"], missing=p["missing"],
                    prepared=self.is_prepared(aid))
        with self.lock:
            self.plan = plan
        return plan

    def start_prepare(self):
        with self.lock:
            plan = self.plan
            if plan is None:
                raise ValueError("plan the route first")
            if self._proc and self._proc.poll() is None:
                raise ValueError("already preparing")
            if not plan["present"]:
                raise ValueError("the map has no tiles along this route")
            self.prep = dict(id=plan["id"], stage="starting", done=0, total=len(plan["present"]),
                             status="running", error=None)
        cmd = ["ros2", "run", "day_pkg", "prepare_area.py", "--mbtiles", self.mbtiles,
               "--out", self.path(plan["id"]), "--buffer-m", str(plan["buffer_m"]),
               "--route"] + [f"{a},{b}" for a, b in plan["route"]]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, start_new_session=True)
        threading.Thread(target=self._read, args=(self._proc, plan["id"]), daemon=True).start()
        self.log("info", f"map: preparing {len(plan['present'])} tiles for vision "
                         f"({plan['length_m'] / 1000:.1f} km route, ±{plan['buffer_m']:.0f} m)")

    def _read(self, proc, aid):
        tail = deque(maxlen=5)
        for line in proc.stdout:
            tail.append(line.strip())
            try:
                d = json.loads(line)
            except ValueError:
                continue
            with self.lock:
                if self.prep and self.prep["id"] == aid and "stage" in d and d["stage"] != "warning":
                    self.prep.update(stage=d["stage"], done=d.get("done", 0), total=d.get("total", 0))
        code = proc.wait()
        with self.lock:
            if self.prep and self.prep["id"] == aid:
                ok = code == 0 and self.is_prepared(aid)
                self.prep["status"] = "done" if ok else "failed"
                self.prep["error"] = None if ok else " / ".join(tail)
                if self.plan and self.plan["id"] == aid:
                    self.plan["prepared"] = ok
        if code == 0:
            info = json.load(open(os.path.join(self.path(aid), "area.json")))
            self.log("ok", f"map: area ready — {info['prepared']} tiles with vision descriptors "
                           f"in {info['build_s']:.0f} s")
        else:
            self.log("error", f"map: preparation failed ({' / '.join(tail)})")

    def state(self):
        with self.lock:
            p = self.plan
            plan = None if p is None else {k: p[k] for k in (
                "id", "route", "buffer_m", "length_m", "tiles", "prepared")} | {
                "present": p["present"], "missing": p["missing"]}
            return dict(plan=plan, prep=dict(self.prep) if self.prep else None)

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


class DayCamera:
    """Simulated downward day camera → the real day_subscriber."""

    def __init__(self, node, tiles, truth_fn, log):
        self.node, self.tiles, self.truth_fn, self.log = node, tiles, truth_fn, log
        latched = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             history=HistoryPolicy.KEEP_LAST, depth=1)
        rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST,
                         depth=10)
        self.pub_img = node.create_publisher(Image, "/day/image_raw", rel)
        self.pub_meta = node.create_publisher(String, "/day/frame_meta", rel)
        self.pub_start = node.create_publisher(Bool, "/day/camera/start", latched)
        node.create_subscription(Bool, "/day/localizer_ready", self._on_ready, latched)
        node.create_subscription(Int32, "/day/frame_done",
                                 self._on_done, QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                                                           history=HistoryPolicy.KEEP_LAST, depth=1))
        node.create_subscription(String, "/day/day_status", self._on_status, 10)
        self.lock = threading.Lock()
        self.enabled = False
        self.ready = False
        self.failed = False
        self.night = False
        self.frame_id = 0
        self.in_flight = None          # (frame_id, sent_at)
        self.last_jpeg = None
        self.last_status = None
        self.last_frame_truth = {}     # frame_id -> (lat, lon)
        self.matches = deque(maxlen=300)
        self.stats = dict(frames=0, matched=0, rejected=0, idle=0)
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    # ---- protocol ----
    def _on_ready(self, msg):
        with self.lock:
            was, self.ready = self.ready, bool(msg.data)
        if self.ready and not was:
            self.log("ok", "day vision: DINOv2 model and area descriptors loaded — ready")

    def _on_done(self, msg):
        with self.lock:
            if self.in_flight and self.in_flight[0] == msg.data:
                self.in_flight = None

    def _on_status(self, msg):
        try:
            d = json.loads(msg.data)
        except ValueError:
            return
        fid = d.get("frame_id")
        with self.lock:
            truth = self.last_frame_truth.pop(fid, None)
            d["t"] = time.monotonic()
            src = d.get("source")
            if truth and d.get("lat") is not None and src in ("visual_match", "predicted"):
                d["err_m"] = _haversine(truth, (d["lat"], d["lon"]))
            if src == "gps_active":
                self.stats["idle"] += 1
            elif d.get("success"):
                self.stats["matched"] += 1
                self.matches.append((d["lat"], d["lon"], d.get("err_m")))
            else:
                self.stats["rejected"] += 1
            self.last_status = d

    def start(self):
        with self.lock:
            self.enabled, self.ready, self.in_flight = True, False, None
            self.frame_id = 0
            self.last_status = None
            self.matches.clear()
            self.stats = dict(frames=0, matched=0, rejected=0, idle=0)
        self.pub_start.publish(Bool(data=True))

    def stop(self):
        with self.lock:
            self.enabled = False
        self.pub_start.publish(Bool(data=False))

    # ---- rendering ----
    def render(self, lat, lon, alt_m):
        """North-up nadir view of the map for this position and altitude."""
        footprint = max(40.0, 2.0 * max(alt_m, 1.0) * math.tan(math.radians(HFOV_DEG / 2)))
        z = 18 if footprint <= 600 else 17
        tile_m = 40_075_016.7 * math.cos(math.radians(lat)) / 2 ** z
        half = int(math.ceil(footprint / 2 / tile_m)) + 1
        x, y = _tile_xy(lat, lon, z)
        tx, ty = int(x), int(y)
        side = (2 * half + 1) * 256
        mosaic = PILImage.new("RGB", (side, side), (20, 24, 28))
        for dx in range(-half, half + 1):
            for dy in range(-half, half + 1):
                data = self.tiles.get(z, tx + dx, ty + dy)
                if data:
                    try:
                        mosaic.paste(PILImage.open(io.BytesIO(data)).convert("RGB"),
                                     ((dx + half) * 256, (dy + half) * 256))
                    except Exception:
                        pass
        cx, cy = (x - tx + half) * 256, (y - ty + half) * 256
        w_px = footprint / tile_m * 256
        h_px = w_px * FRAME_H / FRAME_W
        img = mosaic.crop((int(cx - w_px / 2), int(cy - h_px / 2),
                           int(cx + w_px / 2), int(cy + h_px / 2))).resize((FRAME_W, FRAME_H),
                                                                           PILImage.BILINEAR)
        if self.night:        # a day camera at night: almost nothing visible
            img = ImageEnhance.Brightness(ImageOps.grayscale(img).convert("RGB")).enhance(0.08)
            img = PILImage.blend(img, PILImage.effect_noise((FRAME_W, FRAME_H), 30).convert("RGB"),
                                 0.15)
        return img, footprint

    # ---- frame loop ----
    def _loop(self):
        last = 0.0
        while not self._stop.is_set():
            time.sleep(0.05)
            with self.lock:
                if not (self.enabled and self.ready) or self.failed:
                    continue
                if self.in_flight and time.monotonic() - self.in_flight[1] < 10.0:
                    continue              # one frame in flight, like camera_pkg
            if time.monotonic() - last < 1.0:
                continue
            tr = self.truth_fn()
            if tr is None:
                continue
            last = time.monotonic()
            try:
                self._send(tr)
            except Exception as e:
                self.log("error", f"camera: {e}")

    def _send(self, tr):
        lat, lon, alt = tr[0], tr[1], max(tr[2], 0.0)
        img, footprint = self.render(lat, lon, alt)
        stamp = self.node.get_clock().now().to_msg()
        with self.lock:
            self.frame_id += 1
            fid = self.frame_id
            self.in_flight = (fid, time.monotonic())
            self.last_frame_truth[fid] = (lat, lon)
            if len(self.last_frame_truth) > 50:
                self.last_frame_truth.pop(next(iter(self.last_frame_truth)))
            self.stats["frames"] += 1
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        self.last_jpeg = buf.getvalue()
        msg = Image()
        msg.header.stamp = stamp
        msg.header.frame_id = "day_camera_link"
        msg.height, msg.width, msg.encoding = FRAME_H, FRAME_W, "bgr8"
        msg.step = FRAME_W * 3
        r, g, b = img.split()
        msg.data = PILImage.merge("RGB", (b, g, r)).tobytes()
        meta = {"frame_id": fid, "image_stamp_ns": stamp.sec * 1_000_000_000 + stamp.nanosec,
                "lat": None, "lon": None, "gps_valid": False, "altitude_m": round(alt, 1),
                "heading_deg": None, "speed_mps": None, "camera_type": "day",
                "timestamp": time.strftime("%H:%M:%S"), "image_file": f"sim_{fid:06d}.jpg",
                "simulated": True, "footprint_m": round(footprint)}
        self.pub_meta.publish(String(data=json.dumps(meta)))
        self.pub_img.publish(msg)

    def state(self):
        with self.lock:
            st = dict(self.last_status) if self.last_status else None
            if st:
                st["age_s"] = round(time.monotonic() - st.pop("t"), 1)
            return dict(enabled=self.enabled, ready=self.ready, failed=self.failed,
                        status=st, stats=dict(self.stats),
                        matches=[list(m) for m in self.matches])

    def close(self):
        self._stop.set()


def _haversine(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, h)))


__all__ = ["AreaManager", "DayCamera", "BUFFER_M", "tile_nw"]
