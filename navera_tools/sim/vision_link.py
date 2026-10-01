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

from navera_common.geo import haversine_m
from PIL import Image as PILImage, ImageEnhance, ImageFilter, ImageOps
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, Int32, String

from day_pkg.prepare_area import plan_tiles, tile_nw

HFOV_DEG = 84.0          # camera horizontal field of view
FRAME_W, FRAME_H = 640, 480
BUFFER_M = 1000.0        # corridor half-width around the route
MAX_PREPARE_KM = 1000.0  # ~40 000 tiles, ~40 min, ~800 MB (+ the same again in the dataset)
# Measured on the Jetson (34.5 km route, 1411 tiles, 93 s): downloads ~25 tiles/s
# (8 connections), DINOv2 descriptors ~50 tiles/s, a tile ~20 kB. Used for the
# estimate shown before a preparation starts (kept slightly conservative).
DL_TILES_S, DESC_TILES_S, TILE_KB = 22.0, 45.0, 20.0


def _tile_xy(lat, lon, z):
    n = 2 ** z
    r = math.radians(lat)
    return ((lon + 180.0) / 360.0 * n,
            (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n)


# Online imagery for areas the onboard map lacks (development / demonstration).
# Storing it for offline use in a product needs the provider's licence.
TILE_URL = os.environ.get(
    "NAVERA_TILE_URL",
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}")


class MultiTiles:
    """Tiles from several MBTiles readers, first hit wins (onboard map, then cache)."""

    def __init__(self, readers):
        self.readers = readers
        self.path = readers[0].path

    def exists(self):
        return any(r.exists() for r in self.readers)

    def get(self, z, x, y):
        for r in self.readers:
            data = r.get(z, x, y)
            if data:
                return data
        return None


class AreaManager:
    """Route plans and map preparation, kept PER ROUTE (several pages or users may
    plan different routes at the same time; each prepares exactly its own)."""

    def __init__(self, mbtiles, work_dir, log):
        self.mbtiles = mbtiles
        self.cache = os.path.join(work_dir, "world_tiles.mbtiles")
        self.dir = os.path.join(work_dir, "areas")
        os.makedirs(self.dir, exist_ok=True)
        self.log = log
        self.lock = threading.Lock()
        self.plans = {}            # area id -> plan
        self.preps = {}            # area id -> {"stage", "done", "total", "status", "error"}
        self.current = None        # area id shown in the flight view (the mission's)
        self._proc = None
        self._running = None       # area id being prepared

    @staticmethod
    def area_id(route, buffer_m=BUFFER_M):
        key = json.dumps([[round(a, 5), round(b, 5)] for a, b in route] + [buffer_m])
        return hashlib.sha1(key.encode()).hexdigest()[:12]

    def path(self, aid):
        return os.path.join(self.dir, aid)

    def is_prepared(self, aid):
        return os.path.exists(os.path.join(self.path(aid), "descriptors_cache.npz"))

    def make_plan(self, route, buffer_m=BUFFER_M):
        route = [[float(a), float(b)] for a, b in route]
        p = plan_tiles(self.mbtiles, route, buffer_m, 17, self.cache)
        aid = self.area_id(route, buffer_m)
        length = sum(haversine_m(a[0], a[1], b[0], b[1]) for a, b in zip(route, route[1:]))   # great circle, as the dashboard
        plan = dict(id=aid, route=route, buffer_m=buffer_m, zoom=17, length_m=length,
                    tiles=len(p["needed"]), present=p["present"], missing=p["missing"],
                    in_base=p["in_base"], in_cache=p["in_cache"],
                    prepared=self.is_prepared(aid), max_prepare_km=MAX_PREPARE_KM,
                    too_long=length > MAX_PREPARE_KM * 1000.0,
                    est_s=len(p["missing"]) / DL_TILES_S + len(p["needed"]) / DESC_TILES_S,
                    est_mb=len(p["missing"]) * TILE_KB / 1024.0)
        with self.lock:
            self.plans[aid] = plan
            if len(self.plans) > 50:                   # keep memory bounded
                for k in list(self.plans)[:-50]:
                    if k not in (self.current, self._running):
                        self.plans.pop(k, None)
        return plan

    def plan_for(self, route):
        """The plan of this route (computed if needed) with its preparation status."""
        aid = self.area_id([[float(a), float(b)] for a, b in route])
        with self.lock:
            plan = self.plans.get(aid)
        if plan is None:
            plan = self.make_plan(route)
        with self.lock:
            prep = dict(self.preps[aid]) if aid in self.preps else None
            running = self._running
        out = dict(plan, missing_n=len(plan["missing"]), present_n=len(plan["present"]))
        if plan["tiles"] > 3000:                  # too many to draw: counts only
            out.update(present=[], missing=[])
        return dict(plan=out, prep=prep, busy_other=running not in (None, aid))

    def start_prepare(self, route):
        plan = self.plan_for(route)["plan"]
        aid = plan["id"]
        if plan["too_long"]:
            raise ValueError(f"route too long to prepare: {plan['length_m'] / 1000:.0f} km "
                             f"(max {MAX_PREPARE_KM:.0f} km, {plan['tiles']} tiles). Vision needs "
                             f"the tiles along the whole route: shorten the mission")
        with self.lock:
            if self._proc and self._proc.poll() is None:
                other = self.preps.get(self._running, {})
                pct = (f" ({other.get('stage')} {other.get('done')}/{other.get('total')})"
                       if other else "")
                raise ValueError("another map preparation is running" + pct + " — try again when it ends"
                                 if self._running != aid else "this map is already being prepared")
            self.preps[aid] = dict(stage="starting", done=0, total=plan["tiles"], status="running",
                                   error=None, t_start=time.time())
            self._running = aid
        cmd = ["ros2", "run", "day_pkg", "prepare_area.py", "--mbtiles", self.mbtiles,
               "--out", self.path(aid), "--buffer-m", str(plan["buffer_m"]),
               "--fetch-url", TILE_URL, "--cache", self.cache,
               "--route"] + [f"{a},{b}" for a, b in plan["route"]]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, start_new_session=True)
        threading.Thread(target=self._read, args=(self._proc, aid, plan), daemon=True).start()
        dl = len(plan["missing"])
        self.log("info", f"map: preparing {plan['tiles']} tiles for vision "
                         f"({plan['length_m'] / 1000:.1f} km route, ±{plan['buffer_m']:.0f} m)"
                         + (f"; downloading {dl} tiles the onboard map lacks" if dl else ""))

    def _read(self, proc, aid, plan):
        tail = deque(maxlen=5)
        for line in proc.stdout:
            tail.append(line.strip())
            try:
                d = json.loads(line)
            except ValueError:
                continue
            with self.lock:
                if aid in self.preps and "stage" in d and d["stage"] != "warning":
                    self.preps[aid].update(stage=d["stage"], done=d.get("done", 0),
                                           total=d.get("total", 0))
        code = proc.wait()
        ok = code == 0 and self.is_prepared(aid)
        if ok:
            try:                                  # coverage changed: tiles were downloaded
                self.make_plan(plan["route"], plan["buffer_m"])
            except Exception as e:                # noqa: BLE001
                self.log("warn", f"map: coverage refresh failed: {e}")
        with self.lock:
            self.preps[aid]["status"] = "done" if ok else "failed"
            self.preps[aid]["error"] = None if ok else " / ".join(tail)
            self._running = None
        if ok:
            info = json.load(open(os.path.join(self.path(aid), "area.json")))
            missing = len(info.get("missing") or [])
            self.log("ok", f"map: area ready — {info['prepared']} tiles with vision descriptors "
                           f"in {info['build_s']:.0f} s" + (f" ({missing} tiles could not be "
                                                             f"downloaded)" if missing else ""))
        else:
            self.log("error", f"map: preparation failed ({' / '.join(tail)})")

    def state(self):
        """Plan of the mission's route (flight view), with its preparation."""
        with self.lock:
            aid = self.current
            p = self.plans.get(aid) if aid else None
            plan = None if p is None else dict(p)
        if plan and plan["tiles"] > 3000:            # polled every 0.6 s: counts only
            plan.update(missing_n=len(plan["missing"]), present_n=len(plan["present"]),
                        present=[], missing=[])
        with self.lock:
            prep = dict(self.preps[aid]) if aid in self.preps else None
        return dict(plan=plan, prep=prep)

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


TOPICS = {
    "day": dict(img="/day/image_raw", meta="/day/frame_meta", start="/day/camera/start",
                ready="/day/localizer_ready", done="/day/frame_done", status="/day/day_status",
                frame="day_camera_link", name="day vision", model="DINOv2 model and area descriptors"),
    "night": dict(img="/thermal/image_raw", meta="/thermal/frame_meta",
                  start="/thermal/camera/start", ready="/night/localizer_ready",
                  done="/thermal/frame_done", status="/night/night_status",
                  frame="thermal_camera_link", name="night vision", model="STHN network"),
}
MATCH_SOURCES = ("visual_match", "predicted", "night_sthn")


class VisionCamera:
    """Simulated downward camera (day colour or night thermal) → the real localizer.

    day:   north-up colour image (the day pipeline does not de-rotate; the image
           is assumed de-rotated upstream).
    night: heading-up grey "thermal" image, as a fixed camera sees it; the night
           node scales it from the altitude and turns it north-up with the IMU.
    """

    def __init__(self, node, tiles, truth_fn, log, kind="day"):
        self.node, self.tiles, self.truth_fn, self.log = node, tiles, truth_fn, log
        self.kind = kind
        self.t = TOPICS[kind]
        latched = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL,
                             history=HistoryPolicy.KEEP_LAST, depth=1)
        rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST,
                         depth=10)
        self.pub_img = node.create_publisher(Image, self.t["img"], rel)
        self.pub_meta = node.create_publisher(String, self.t["meta"], rel)
        self.pub_start = node.create_publisher(Bool, self.t["start"], latched)
        node.create_subscription(Bool, self.t["ready"], self._on_ready, latched)
        node.create_subscription(Int32, self.t["done"],
                                 self._on_done, QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                                                           history=HistoryPolicy.KEEP_LAST, depth=1))
        node.create_subscription(String, self.t["status"], self._on_status, 10)
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
            self.log("ok", f"{self.t['name']}: {self.t['model']} loaded — ready")

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
            if truth and d.get("lat") is not None and src in MATCH_SOURCES:
                d["err_m"] = _haversine(truth, (d["lat"], d["lon"]))
            if src == "gps_active":
                self.stats["idle"] += 1
            elif d.get("success") and src in MATCH_SOURCES:
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
    def render(self, lat, lon, alt_m, heading_deg=0.0):
        """Nadir view of the map for this position and altitude (see class doc)."""
        footprint = max(40.0, 2.0 * max(alt_m, 1.0) * math.tan(math.radians(HFOV_DEG / 2)))
        z = 18 if footprint <= 600 else 17
        if z == 18 and not self.tiles.get(18, *map(int, _tile_xy(lat, lon, 18))):
            z = 17                        # area prepared at z17 only (downloaded tiles)
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
        if self.kind == "night" and heading_deg:
            # heading-up: the north-up view turned counter-clockwise by the heading
            mosaic = mosaic.rotate(heading_deg, resample=PILImage.BILINEAR, center=(cx, cy))
        w_px = footprint / tile_m * 256
        h_px = w_px * FRAME_H / FRAME_W
        img = mosaic.crop((int(cx - w_px / 2), int(cy - h_px / 2),
                           int(cx + w_px / 2), int(cy + h_px / 2))).resize((FRAME_W, FRAME_H),
                                                                           PILImage.BILINEAR)
        if self.kind == "night":      # thermal look: grey, stretched, soft, grainy
            g = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
            g = g.filter(ImageFilter.GaussianBlur(1.0))
            img = PILImage.blend(g, PILImage.effect_noise((FRAME_W, FRAME_H), 25), 0.10).convert("RGB")
        elif self.night:      # a day camera at night: almost nothing visible
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
        img, footprint = self.render(lat, lon, alt, tr[3])
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
        msg.header.frame_id = self.t["frame"]
        msg.height, msg.width, msg.encoding = FRAME_H, FRAME_W, "bgr8"
        msg.step = FRAME_W * 3
        r, g, b = img.split()
        msg.data = PILImage.merge("RGB", (b, g, r)).tobytes()
        meta = {"frame_id": fid, "image_stamp_ns": stamp.sec * 1_000_000_000 + stamp.nanosec,
                "lat": None, "lon": None, "gps_valid": False, "altitude_m": round(alt, 1),
                "heading_deg": None, "speed_mps": None, "camera_type": self.kind,
                "timestamp": time.strftime("%H:%M:%S"), "image_file": f"sim_{fid:06d}.jpg",
                "simulated": True, "footprint_m": round(footprint)}
        self.pub_meta.publish(String(data=json.dumps(meta)))
        self.pub_img.publish(msg)

    def state(self):
        with self.lock:
            st = dict(self.last_status) if self.last_status else None
            if st:
                st["age_s"] = round(time.monotonic() - st.pop("t"), 1)
            return dict(kind=self.kind, enabled=self.enabled, ready=self.ready, failed=self.failed,
                        status=st, stats=dict(self.stats),
                        matches=[list(m) for m in self.matches])

    def close(self):
        self._stop.set()


def _haversine(a, b):
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * 6_371_000.0 * math.asin(math.sqrt(min(1.0, h)))


__all__ = ["AreaManager", "VisionCamera", "BUFFER_M", "tile_nw"]


class StarCamera:
    """Simulated upward star camera → the real cn_subscriber (astrometry.net).

    Draws the real sky (sky_view.SkyCamera) seen with the TRUE attitude at the
    simulated sky time, every `period_s`. The node computes the camera attitude
    from the (imperfect) IMU, as on the vehicle, so the fix error shows what the
    IMU's attitude error costs (~111 km per degree).
    """

    def __init__(self, node, work_dir, truth_fn, attitude_fn, utc_fn, log, hfov_deg=60.0,
                 period_s=15.0):
        self.node, self.truth_fn, self.attitude_fn, self.utc_fn, self.log = (
            node, truth_fn, attitude_fn, utc_fn, log)
        self.work, self.hfov, self.period = work_dir, hfov_deg, period_s
        rel = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST,
                         depth=10)
        self.pub_img = node.create_publisher(Image, "/celestial/image_raw", rel)
        self.pub_meta = node.create_publisher(String, "/celestial/frame_meta", rel)
        node.create_subscription(String, "/cn/cn_status", self._on_status, 10)
        self.lock = threading.Lock()
        self.enabled = False
        self.failed = False
        self.sky = None
        self.frame_id = 0
        self.last_jpeg = None
        self.last_status = None
        self.last_render = {}
        self.truth_at = {}
        self.stats = dict(frames=0, solved=0, failed=0)
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def _on_status(self, msg):
        try:
            d = json.loads(msg.data)
        except ValueError:
            return
        with self.lock:
            truth = self.truth_at.pop(d.get("frame_id"), None)
            if truth and d.get("success") and d.get("lat") is not None:
                d["err_m"] = _haversine(truth, (d["lat"], d["lon"]))
            self.stats["solved" if d.get("success") else "failed"] += 1
            d["t"] = time.monotonic()
            self.last_status = d
        if d.get("success"):
            self.log("ok", f"celestial: stars identified (log-odds {d.get('log_odds')}) — fix "
                           f"{(d.get('err_m') or 0) / 1000:.1f} km from the truth")
        else:
            self.log("warn", f"celestial: no fix — {str(d.get('error') or d.get('reason'))[:90]}")

    def start(self):
        with self.lock:
            self.enabled = True
            self.last_status = None
            self.stats = dict(frames=0, solved=0, failed=0)

    def stop(self):
        with self.lock:
            self.enabled = False

    def _loop(self):
        last = 0.0
        while not self._stop.is_set():
            time.sleep(0.2)
            if not self.enabled or self.failed or time.monotonic() - last < self.period:
                continue
            stamp = self.node.get_clock().now().to_msg()     # exposure = attitude sample
            tr, att = self.truth_fn(), self.attitude_fn()
            if tr is None or att is None:
                continue
            last = time.monotonic()
            try:
                self._send(tr, att, stamp)
            except Exception as e:                   # noqa: BLE001
                self.log("error", f"star camera: {e}")

    def _send(self, tr, att, stamp):
        if self.sky is None:
            from sky_view import SkyCamera
            self.sky = SkyCamera(self.work, hfov_deg=self.hfov)
        alt, az = att
        utc = self.utc_fn()
        img, n, sun = self.sky.render(tr[0], tr[1], utc, alt, az, roll_deg=tr[3])
        with self.lock:
            self.frame_id += 1
            fid = self.frame_id
            self.truth_at[fid] = (tr[0], tr[1])
            self.stats["frames"] += 1
            self.last_render = dict(stars=n, sun_alt=round(sun, 1), utc=utc,
                                    true_alt=round(alt, 2), true_az=round(az, 2))
        ok, jpg = __import__("cv2").imencode(".jpg", img)
        self.last_jpeg = jpg.tobytes() if ok else None
        msg = Image()
        msg.header.stamp = stamp
        msg.header.frame_id = "celestial_camera_link"
        msg.height, msg.width, msg.encoding = img.shape[0], img.shape[1], "mono8"
        msg.step = img.shape[1]
        msg.data = img.tobytes()
        meta = {"frame_id": fid, "image_stamp_ns": stamp.sec * 1_000_000_000 + stamp.nanosec,
                "utc_time": utc, "altitude_m": round(tr[2], 1), "gps_valid": False,
                "camera_type": "celestial", "simulated": True}
        self.pub_meta.publish(String(data=json.dumps(meta)))
        self.pub_img.publish(msg)

    def state(self):
        with self.lock:
            st = dict(self.last_status) if self.last_status else None
            if st:
                st["age_s"] = round(time.monotonic() - st.pop("t"), 1)
            return dict(enabled=self.enabled, failed=self.failed, status=st,
                        stats=dict(self.stats), render=dict(self.last_render))

    def close(self):
        self._stop.set()
