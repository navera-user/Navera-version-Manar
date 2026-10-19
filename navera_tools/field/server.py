#!/usr/bin/env python3
"""NAVERA field test server: the camera, the star check, the real celestial solver and the
phone, behind one page the phone opens.

    navera_tools/field/run_field.sh          (prints the address to open on the phone)

What it does, in the order of the page's steps:
  1 connect  the phone shares its GPS, tilt and clock with this server (HTTPS: browsers only
             give a page the GPS and the tilt over HTTPS)
  2 mount    the camera must point straight up; the phone's tilt says how far it is off
  3 sky      every second: undistorted camera frame, star detector (cn_pkg.star_detect), the
             verdict on the sky and the stars that survive every filter
  4 drive    every INTERVAL seconds a frame goes to the real solver (cn_pkg solver, the same
             code the celestial pipeline calls) with the phone's tilt, the corrected UTC and a
             coarse prior; the answer is compared with the phone's GPS
  5 finish   report.json / report.md with the problems found

Everything is written to NAVERA_FIELD_DIR/<test>/ as it happens (navera_tools/field/store.py).
This server does not run the ROS pipeline: it calls the same solver on the same kind of frame,
so what it measures is the celestial method with this camera, not the full box. It is
read-only for the vehicle: nothing here is sent to an autopilot.
"""
import collections
import io
import json
import math
import os
import shutil
import socket
import ssl
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
for pkg in ("navera_common", "cn_pkg"):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), pkg))

from navera_tools.field import analyze as report_mod  # noqa: E402
from navera_tools.field import attitude  # noqa: E402
from navera_tools.field.store import FieldSession, list_sessions  # noqa: E402

MIN_STARS = report_mod.MIN_STARS
# astrometry.net cannot match a rectilinear picture wider than ~65 degrees (edges stretched 3x, simulated 111 degree
# strip: never solved; its central 40-62 degrees: 4-15 km). Wider cameras are solved on their central window.
SOLVE_MAX_HFOV = 62.0
SOLVE_WINDOW_HFOV = 52.0
# 360 mode: the camera's own accelerometer (6-position calibrated) gives 'up'; the lens-to-IMU mounting is not
# measured yet, so the stated accuracy keeps a margin until a night calibrates it (first guess).
ATTITUDE_SIGMA_360_DEG = 0.3
# vehicle moving: 'up' may hold its acceleration. The |a| gate (allsky.ACCEL_NORM_TOL) does not bound it: 1-2 Hz body
# bounce moves the 1 s mean of the vertical by 0.01-0.02 g, which hides 0.2 g of braking (simulated drive,
# sim/car360_drive.py: 'up' up to 10.6 deg off in frames that passed every gate; 3.0 deg left 26 of 6872 outside 3 sigma).
MOVING_ATTITUDE_SIGMA_DEG = 5.0
STOPPED_SOLVE_GAP_S = 4.0                            # 360: while stopped, a frame every 4 s (a solve takes ~1-5 s)
PHONE_MOVING_MPS = 1.0                               # phone GPS speed above which the car is not stopped (GPS noise ~0.3 m/s)
F_SCALE_SEARCH = (0.90, 0.95, 1.0, 1.05, 1.10)       # lens focal length not measured: searched once, then kept
# 360: the lens-to-IMU mounting angle and the accelerometer's residual tilt are one fixed tilt of 'up' in the camera
# (1 deg = ~111 km on every fix; nothing in the stars shows it). While a reference position exists (the phone here,
# NAVERA's GPS before it is lost in the product), stopped fixes measure it; it is learned on the first
# CAL_SAMPLES of them, then frozen, so every later corrected fix is judged on frames the fit never saw.
CAL_MIN_SAMPLES = 4
CAL_SAMPLES = 12
CAL_SIGMA_FLOOR_DEG = 0.05


def solver_view(img, hfov):
    """(picture, field of view in degrees) given to the plate solver: the whole picture, or its central window."""
    if hfov <= SOLVE_MAX_HFOV:
        return img, hfov
    h, w = img.shape[:2]
    f = (w / 2.0) / math.tan(math.radians(hfov) / 2.0)
    cw = min(w, int(round(2 * f * math.tan(math.radians(SOLVE_WINDOW_HFOV) / 2.0))))
    x0 = (w - cw) // 2
    return img[:, x0:x0 + cw], 2 * math.degrees(math.atan(cw / 2.0 / f))
CALIBRATION_SEARCH = (os.environ.get("NAVERA_CAMERA_CALIBRATION", ""), "/etc/navera/camera.yaml",
                      "/var/lib/navera/camera.yaml",
                      os.path.expanduser("~/.navera_sim/bench_2026-10-06/calib/insta360_top.yaml"))
DEFAULT_DEVICE = "/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0"
ATTITUDE_SIGMA_DEG = 0.5            # phone accelerometer, first guess until measured against a level


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


class Camera:
    """The Insta360's top lens, undistorted, newest frame only."""

    def __init__(self, device, calibration):
        import yaml
        from navera_common.camera_model import CameraModel
        self.device = device
        with open(calibration) as f:
            d = yaml.safe_load(f)
        self.cal_path = calibration
        self.model = CameraModel.from_calibration(d)
        self.crop = d.get("crop") or [0, 0, 1920, 540]
        self.latency_s = float(d.get("latency_s") or 0.0)
        self.hfov = float(self.model.out_hfov_deg)
        self._frame = None
        self._t = 0.0
        self._lock = threading.Lock()
        self.error = None
        threading.Thread(target=self._grab, daemon=True).start()

    def _grab(self):
        while True:
            cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            cap.set(cv2.CAP_PROP_FPS, 30)
            if not cap.isOpened():
                self.error = f"cannot open {self.device} (is another program using it?)"
                time.sleep(3)
                continue
            self.error = None
            fails = 0
            while fails < 30:
                ok, img = cap.read()
                if not ok:
                    fails += 1
                    time.sleep(0.05)
                    continue
                fails = 0
                x, y, w, h = self.crop
                with self._lock:
                    self._frame, self._t = img[y:y + h, x:x + w], time.time()
            cap.release()
            self.error = "camera stopped sending frames"

    def latest(self):
        """(undistorted grey frame, exposure time) or (None, 0)."""
        with self._lock:
            f, t = self._frame, self._t
        if f is None or time.time() - t > 3.0:
            return None, 0.0
        g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) if f.ndim == 3 else f
        return self.model.undistort(g), t - self.latency_s


class Camera360:
    """The Insta360's full 360 frame and its own gravity over USB (USB mode "Android"); reconnects if it drops."""
    device = "insta360-usb (Android mode)"
    hfov = None
    latency_s = 1.71                                  # measured: day bench, 54 frames 20-80 m/s (screen toggles: 1.27-1.76 s)

    def __init__(self):
        from navera_tools.field import insta360_usb
        self._mod = insta360_usb
        self.cal_path = insta360_usb.IMU_CALIBRATION
        self.cam = None
        self.error = None
        self.frame_ms = None
        self._open()
        threading.Thread(target=self._watch, daemon=True).start()

    def _open(self):
        self.opened_at = time.time()
        try:
            self.cam = self._mod.Insta360Usb()
            self.error = None
        except Exception as e:
            self.cam, self.error = None, f"360 camera: {e}"

    def _watch(self):
        while True:
            time.sleep(3.0)
            f, t = self.cam.latest() if self.cam else (None, 0.0)
            if self.cam is not None and time.time() - self.opened_at < 20.0:
                continue                              # the decoder waits for the stream's next key frame
            imu_dead = self.cam is not None and self.cam.imu_age() > 10.0   # restarting the stream did not bring it back
            if f is None or time.time() - t > 8.0 or imu_dead:
                if self.cam is not None:
                    self.error = ("camera IMU silent for 10 s: reconnecting" if imu_dead
                                  else self.cam.error or "no frame for 8 s: reconnecting")
                    try:
                        self.cam.close()
                    except Exception:
                        pass
                    time.sleep(2.0)
                self._open()

    def latest(self):
        """(grey full 360 frame, exposure time) or (None, 0)."""
        f, t, ms = self.cam.latest_stamped() if self.cam else (None, 0.0, None)
        if f is None or time.time() - t > 3.0:
            return None, 0.0
        self.frame_ms = ms                            # the exposure on the IMU's clock: gravity()/stopped() judge it
        return (cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) if f.ndim == 3 else f), t - self.latency_s

    def gravity(self, at_frame=False):
        """'up' now (health checks) or at the last frame's exposure (a fix: the frame is ~1.7 s old)."""
        if not self.cam:
            return None, None, None
        return self.cam.gravity(at_ms=self.frame_ms) if at_frame and self.frame_ms is not None else self.cam.gravity()

    def imu_age(self):
        """Seconds since the camera's last IMU sample (None: no camera)."""
        return self.cam.imu_age() if self.cam else None

    def stopped(self, at_frame=False):
        if not self.cam:
            return {"stopped": False, "why": "no camera"}
        return self.cam.stopped(at_ms=self.frame_ms) if at_frame and self.frame_ms is not None else self.cam.stopped()


class Field:
    def __init__(self, root, camera):
        self.root, self.camera = root, camera
        os.makedirs(root, exist_ok=True)
        self.key = access_key(root)
        from cn_pkg.star_detect import StarTracker
        self.tracker = StarTracker()
        self.lock = threading.Lock()
        self.phone: dict = {}
        self.phone_recv = 0.0
        self.offsets = collections.deque(maxlen=60)       # server time - phone time, seconds
        self.speeds = collections.deque(maxlen=120)       # (server time, phone GPS speed m/s): the stopped flag's referee
        self.live: dict = {}
        self.preview: bytes = b""
        self.step = 1
        self.mount_confirmed = False
        self.session: Optional[FieldSession] = None
        self.frame_idx = 0
        self.interval_s = float(os.environ.get("NAVERA_FIELD_INTERVAL_S", "20"))
        self.last_solve_t = 0.0
        self.solving = False
        self.solving_since = 0.0
        self.go_lock = threading.RLock()
        self.cam_ok = True
        self.last_done = None
        self.last_fix: dict = {}
        self.n_fixes = 0                            # positions solved in the test being recorded
        self.usable_skies = ("clear", "hazy")       # the only skies whose stars count and are solved
        self.mode = "360" if hasattr(camera, "gravity") else "strip"
        self.cat = None                             # 360: bright-star catalogue, built on the first solve
        self.f_scale = None                         # 360: lens focal length found by the first identified frame
        self.cal_samples: list = []                 # 360: (R_icrs_imu, up, true zenith) of stopped fixes with a reference
        self.tilt_cal: Optional[dict] = None        # 360: the fitted tilt of 'up' (see CAL_SAMPLES)
        self.spots: list = []
        self._recover()
        threading.Thread(target=self._loop, daemon=True).start()

    def _recover(self):
        """The server was stopped or crashed in the middle of a test: close the old ones with a report and
        carry on in the newest if it is recent, so the operator does not have to start again."""
        from navera_tools.field.store import read_jsonl
        open_ones = [m for m in list_sessions(self.root) if m.get("ended") is None]
        for i, m in enumerate(open_ones):                           # newest first
            folder = os.path.join(self.root, m["id"])
            frames = read_jsonl(os.path.join(folder, "frames.jsonl"))
            stamps = [x.get("t", 0) for x in frames if isinstance(x, dict)] or [m.get("started", 0)]
            if i == 0 and time.time() - max(stamps) < 6 * 3600:
                self.session = FieldSession.resume(folder)
                self.frame_idx = max([x.get("idx", 0) for x in frames if isinstance(x, dict)] or [0])
                self.step, self.mount_confirmed = 4, True
                log(f"resumed the unfinished test {m['id']} at frame {self.frame_idx}")
            else:
                try:
                    s = FieldSession.resume(folder)
                    s.event("interrupted")
                    s.close()
                    report_mod.write_report(folder)
                except Exception as e:
                    log(f"could not close {m['id']}: {e!r}")

    # ── phone ───────────────────────────────────────────────────────────
    def on_phone(self, d: dict):
        now = time.time()
        with self.lock:
            if d.get("phone_t_ms") is not None:
                self.offsets.append(now - float(d["phone_t_ms"]) / 1000.0)
            self.phone, self.phone_recv = dict(d), now
            if isinstance(d.get("speed"), (int, float)):
                self.speeds.append((now, float(d["speed"])))
        s = self.session
        if s is not None:
            s.log("phone", self._phone_record(d))

    def on_phone_batch(self, items: list) -> int:
        """Samples the phone kept while the network was down: filed at the time the phone took them
        (its clock plus the measured offset), so the truth has no hole where the link dropped."""
        sess = self.session
        if sess is None:
            return 0            # the page keeps its readings until a test is recording
        off = self.clock_offset_s() or 0.0
        n = 0
        for d in items[:500]:
            if not isinstance(d, dict) or d.get("phone_t_ms") is None:
                continue
            rec = self._phone_record(d)
            rec["t"] = float(d["phone_t_ms"]) / 1000.0 + off
            rec["late"] = True
            sess.log("phone", rec)
            n += 1
        return n

    def _phone_record(self, d):
        rec = {k: d.get(k) for k in ("lat", "lon", "acc", "alt", "speed", "course", "beta", "gamma", "compass")}
        if d.get("gps_t_ms") is not None and d.get("phone_t_ms") is not None:
            rec["gps_age_s"] = round((float(d["phone_t_ms"]) - float(d["gps_t_ms"])) / 1000.0, 1)
        if d.get("tilt_t_ms") is not None and d.get("phone_t_ms") is not None:
            rec["tilt_age_s"] = round((float(d["phone_t_ms"]) - float(d["tilt_t_ms"])) / 1000.0, 1)
        if d.get("gpsError"):
            rec["gps_error"] = str(d["gpsError"])[:80]
        if d.get("beta") is not None and d.get("gamma") is not None:
            rec["off_vertical_deg"] = round(attitude.boresight(d["beta"], d["gamma"], 0.0)[2], 2)
        return rec

    def clock_offset_s(self):
        """Jetson clock minus phone clock (includes the short network delay)."""
        with self.lock:
            return statistics.median(self.offsets) if len(self.offsets) >= 3 else None

    def _attitude(self):
        p = self.phone
        if not p or time.time() - self.phone_recv > 3.0 or p.get("beta") is None or p.get("gamma") is None:
            return None
        head, src = attitude.best_heading(p.get("course"), p.get("speed"), p.get("compass"))
        alt, az, off = attitude.boresight(p["beta"], p["gamma"], head)
        return {"alt": alt, "az": az, "off": off, "heading_source": src}

    # ── checks (what the page shows) ────────────────────────────────────
    def checks(self):
        p, now = self.phone, time.time()
        fresh = bool(p) and now - self.phone_recv < 4.0
        acc = p.get("acc") if fresh else None
        off = self.clock_offset_s()
        att = self._attitude()
        lv = self.live
        out = []

        def add(i, label, status, detail=""):
            out.append({"id": i, "label": label, "status": status, "detail": detail})

        _, t = self.camera.latest()
        if self.session is not None and self.session.io_error:
            add("disk", "Saving to disk", "bad", self.session.io_error[:80])
        add("camera", "Camera running", "ok" if t and now - t < 3 else "bad", self.camera.error or "")
        add("phone_gps", "Phone sharing GPS", "bad" if not fresh or acc is None else ("ok" if acc <= 30 else "wait"),
            "no GPS from the phone: allow location on the page" if not fresh or acc is None else f"accuracy {acc:.0f} m")
        if self.mode != "360":
            add("phone_tilt", "Phone sharing tilt", "ok" if att else "bad", "" if att else "allow motion sensors on the page")
        add("clock", "Phone clock matches Jetson", "wait" if off is None else ("ok" if abs(off) <= 1.0 else "bad"),
            "" if off is None else f"{off:+.2f} s")
        if self.mode == "360":
            up, g, rate = self.camera.gravity()
            if up is not None:
                tilt = math.degrees(math.acos(max(-1.0, min(1.0, float(up[0])))))      # IMU +x is up when standing
                add("steady", "Camera steady (its own sensor)", "ok", f"{tilt:.0f} degrees from standing upright")
            else:
                add("steady", "Camera steady (its own sensor)", "wait",
                    "no sensor data yet" if g is None else f"moving: {math.degrees(rate or 0):.1f} deg/s, {g:.2f} g")
        elif att:
            add("level", "Camera pointing straight up", "ok" if att["off"] <= 1.0 else ("wait" if att["off"] <= 3.0 else "bad"),
                f"{att['off']:.1f} degrees off vertical")
        else:
            add("level", "Camera pointing straight up", "wait", "waiting for the phone's tilt")
        n = lv.get("confirmed")
        if n is None:
            add("stars", f"Stars seen (need {MIN_STARS})", "wait", "waiting for frames")
        else:
            sky = lv.get("sky")
            why = {"blocked": "the camera sees something other than sky", "too bright": "too much light",
                   "cloudy": "clouds"}.get(sky, "")
            add("stars", f"Stars seen: {n} (need {MIN_STARS})", "ok" if n >= MIN_STARS else ("wait" if n >= 6 else "bad"),
                why or f"sky: {sky}")
        return out

    # ── analysis loop ───────────────────────────────────────────────────
    def _loop(self):
        from cn_pkg.star_detect import detect
        while True:
            t0 = time.time()
            try:
                img, texp = self.camera.latest()
                if (img is not None) != self.cam_ok:
                    self.cam_ok = img is not None
                    if self.session is not None:
                        self.session.event("camera_back" if self.cam_ok else "camera_lost", error=self.camera.error)
                if img is None:
                    self.live, self.preview = {}, b""
                    s = self.session
                    if s is not None and self.step == 4 and time.time() - self.last_solve_t >= self.interval_s:
                        self.last_solve_t = time.time()
                        self.frame_idx += 1
                        s.log("frames", {"idx": self.frame_idx, "solved": False, "why": "no camera frame",
                                         "sky": None})
                elif self.mode == "360":
                    self._live360(img, texp)
                    self._maybe_solve(img, texp)
                else:
                    det = detect(img)
                    res = self.tracker.update(det)
                    # only a clear or hazy night sky gives stars to count; anything else is not navigation data
                    confirmed = len(res.confirmed) if det.sky in self.usable_skies else 0
                    rej = {k: len(v) for k, v in res.rejected.items() if v}
                    self.live = {"t": texp, "detected": len(det.stars), "confirmed": confirmed, "sky": det.sky,
                                 "rejected": rej, "shift_px": round(res.pattern_shift_px, 1),
                                 "background": round(det.background, 1), "noise": round(det.noise, 2)}
                    self.preview = self._draw(img, det, res)
                    self._maybe_solve(img, texp)
            except Exception as e:                     # the loop must never die in the field
                log(f"analysis error: {e!r}")
            time.sleep(max(0.0, 1.0 - (time.time() - t0)))

    def _live360(self, img, texp):
        """Bright spots above the horizon in both circles (the all-sky solver's input) and the preview."""
        from navera_tools.field import allsky, sky360
        up, _, _ = self.camera.gravity()
        lenses = sky360.default_lenses()
        sky_px = np.concatenate([img[::8, int(L.cx - 400):int(L.cx + 400):8].ravel() for L in lenses])
        level = float(np.median(sky_px))
        spots, rejected = [], {}
        if level < 80:
            for L in lenses:
                st = {}
                spots += allsky.detect_spots(img, L, up_imu=up, min_alt=None if up is None else 12.0, stats=st)
                for k, v in st.items():
                    rejected[k] = rejected.get(k, 0) + v
        self.spots = spots
        sky = "too bright" if level >= 80 else "clear"
        self.live = {"t": texp, "detected": len(spots), "confirmed": len(spots), "sky": sky,
                     "rejected": {k: v for k, v in rejected.items() if v}, "shift_px": 0.0, "background": round(level, 1), "noise": None}
        vis = cv2.convertScaleAbs(cv2.cvtColor(cv2.resize(img, (1920, 960)), cv2.COLOR_GRAY2BGR), alpha=2.5, beta=0)
        for x, y, _ in spots[:150]:
            cv2.circle(vis, (int(x / 2), int(y / 2)), 9, (90, 211, 154), 2)
        vis = cv2.resize(vis, (960, 480))
        ok, jpg = cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 70])
        self.preview = jpg.tobytes() if ok else b""

    def _draw(self, img, det, res):
        vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        vis = cv2.convertScaleAbs(vis, alpha=2.5, beta=0)
        keep = {(round(s.x, 1), round(s.y, 1)) for s in res.confirmed}
        for s in det.stars:
            col = (90, 211, 154) if (round(s.x, 1), round(s.y, 1)) in keep else (75, 184, 242)
            cv2.circle(vis, (int(s.x), int(s.y)), 9, col, 2)
        for pts in res.rejected.values():
            for x, y in pts:
                cv2.drawMarker(vis, (int(x), int(y)), (92, 92, 255), cv2.MARKER_TILTED_CROSS, 10, 2)
        vis = cv2.resize(vis, (960, int(vis.shape[0] * 960 / vis.shape[1])))
        ok, jpg = cv2.imencode(".jpg", vis, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return jpg.tobytes() if ok else b""

    # ── solving ─────────────────────────────────────────────────────────
    def _due(self):
        """Time for the next frame: every interval_s, and in 360 mode also as soon as the camera says the vehicle is
        stopped (every STOPPED_SOLVE_GAP_S while it stays so): only stopped fixes are trusted and the driver stops
        for ~20 s, so a 20 s cadence alone gave 0-1 trusted fix per stop."""
        since = time.time() - self.last_solve_t
        if since >= self.interval_s:
            return True
        if self.mode != "360" or since < STOPPED_SOLVE_GAP_S or self.solving or not hasattr(self.camera, "stopped"):
            return False
        try:
            return bool(self.camera.stopped(at_frame=True).get("stopped"))
        except Exception:
            return False

    def _maybe_solve(self, img, texp):
        s = self.session
        if s is None or self.step != 4 or not self._due():
            return
        if self.solving:
            if time.time() - self.solving_since < (300 if self.mode == "360" else 90):   # 360: first solve searches the lens
                return
            self.solving = False                       # a hung solver must not stop the recording for good
            s.event("solver_hung", since_s=round(time.time() - self.solving_since))
        self.last_solve_t = time.time()
        self.frame_idx += 1
        idx, live, att = self.frame_idx, dict(self.live), self._attitude()
        rec = {"idx": idx, "detected": live.get("detected"), "confirmed": live.get("confirmed"), "sky": live.get("sky"),
               "rejected": live.get("rejected"), "shift_px": live.get("shift_px"), "solved": False}
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        rec["image"] = s.save_frame(idx, jpg.tobytes()) if ok else None
        if self.mode == "360":
            return self._maybe_solve360(s, rec, img, texp)
        why = None
        if att is None:
            why = "no phone tilt"
        elif live.get("confirmed", 0) < MIN_STARS:
            why = f"too few stars ({live.get('confirmed')})"
        elif live.get("sky") not in self.usable_skies:
            why = f"sky {live.get('sky')}"
        elif att["off"] > 5.0:
            why = f"camera {att['off']:.1f} degrees off vertical"
        if att:
            rec.update(tilt_used=round(att["alt"], 2), az_used=round(att["az"], 1), off_vertical_deg=round(att["off"], 2),
                       az_source=att["heading_source"])
        if why:
            rec["why"] = why
            s.log("frames", rec)
            return
        self.solving, self.solving_since = True, time.time()
        view, view_hfov = solver_view(img, self.camera.hfov)
        ok2, vjpg = cv2.imencode(".jpg", view, [cv2.IMWRITE_JPEG_QUALITY, 92])
        threading.Thread(target=self._solve, args=(s, rec, vjpg.tobytes() if ok2 else jpg.tobytes(), att, texp, view_hfov),
                         daemon=True).start()

    def _maybe_solve360(self, s, rec, img, texp):
        from navera_tools.field import allsky
        up, g, rate = self.camera.gravity(at_frame=True)
        rec.update(mode="360", up_imu=None if up is None else [round(float(v), 6) for v in up],
                   accel_g=None if g is None else round(g, 5), rate_dps=None if rate is None else round(math.degrees(rate), 2))
        st = self.camera.stopped(at_frame=True) if hasattr(self.camera, "stopped") else {"stopped": True}
        rec["stopped"] = bool(st.get("stopped"))          # moving: vehicle acceleration can tilt 'up' (not trusted)
        rec["stillness"] = {k: v for k, v in st.items() if k != "stopped"}
        v = self._phone_speed_at(texp)
        if v is not None:
            # the test's referee only, never used to decide: a stopped flag while the phone's GPS says the car moves
            # means the camera's stillness test was fooled (smooth road, gentle steady acceleration): ignore that fix
            rec["phone_speed_mps"] = round(v, 1)
            rec["stopped_but_phone_moving"] = bool(rec["stopped"] and v > PHONE_MOVING_MPS)
        why = None
        if up is None:
            why = "camera moving or turning (its own sensor)" if g is not None else "no camera sensor data"
        elif g is not None and abs(g - 1.0) > allsky.ACCEL_NORM_TOL:
            why = f"vehicle accelerating (|a| = {g:.3f} g): 'up' is not gravity"
        elif self.live.get("sky") not in self.usable_skies:
            why = f"sky {self.live.get('sky')}"
        elif (self.live.get("confirmed") or 0) < MIN_STARS:
            why = f"too few stars ({self.live.get('confirmed')})"
        if why:
            rec["why"] = why
            s.log("frames", rec)
            return
        self.solving, self.solving_since = True, time.time()
        rec["t_exp"] = round(texp, 3)                     # Jetson time of the exposure (the phone track is on this clock)
        threading.Thread(target=self._solve360, args=(s, rec, img, np.array(up), texp), daemon=True).start()

    def _phone_speed_at(self, t):
        """The phone's GPS speed (m/s) nearest to Jetson time t, if one is within 2 s."""
        with self.lock:
            pts = list(self.speeds)
        if not pts:
            return None
        tt, v = min(pts, key=lambda p: abs(p[0] - t))
        return v if abs(tt - t) <= 2.0 else None

    def _solve360(self, s, rec, img, up, texp):
        try:
            from navera_tools.field import allsky
            if self.cat is None:
                self.cat = allsky.Catalogue(limit_mag=4.0)
            off = self.clock_offset_s() or 0.0
            utc = datetime.fromtimestamp(texp - off, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            t0 = time.time()
            r = allsky.locate(img, up, utc, self.cat, f_scales=F_SCALE_SEARCH if self.f_scale is None else (self.f_scale,))
            rec.update(solve_s=round(time.time() - t0, 1), utc_used=utc, prior=None, spots=r.get("spots"))
            if r.get("solved"):
                if self.f_scale is None:
                    self.f_scale = r["f_scale"]
                    s.event("lens_focal_found", f_scale=self.f_scale)
                # the accelerometer (first guess) and the star fit (residuals, lenses' disagreement) add in quadrature
                att = math.hypot(ATTITUDE_SIGMA_360_DEG, r.get("sigma_fit_deg") or 0.0)
                if not rec.get("stopped", True):                 # moving: 0.1 g of braking/curve = ~6 deg of 'up'
                    att = math.hypot(att, MOVING_ATTITUDE_SIGMA_DEG)
                sigma = att * report_mod.KM_PER_DEGREE + abs(off) * report_mod.SKY_KM_PER_SECOND
                rec.update(solved=True, lat=r["lat"], lon=r["lon"], matched=r["matched"], used=r["used"],
                           rms_deg=r["rms_deg"], f_scale=r["f_scale"], sigma_km=round(sigma, 1), R_icrs_imu=r["R_icrs_imu"],
                           p_chance=r.get("p_chance"), lens_disagree_deg=r.get("lens_disagree_deg"),
                           matched_per_lens=r.get("matched_per_lens"))
                p = self.phone
                if p.get("lat") is not None:
                    rec["err_km_live"] = round(report_mod.haversine_km(r["lat"], r["lon"], p["lat"], p["lon"]), 1)
                self._tilt_corrected(s, rec, r, up, utc, off)
                self.n_fixes += 1
                self.last_fix = {"t": time.time(), "lat": r["lat"], "lon": r["lon"],
                                 "err_km": rec.get("err_km_live"), "sigma_km": rec["sigma_km"],
                                 "err_km_cal": rec.get("err_km_cal_live"), "sigma_km_cal": rec.get("sigma_km_cal"),
                                 "stopped": rec.get("stopped"), "stopped_but_phone_moving": rec.get("stopped_but_phone_moving")}
            else:
                rec["why"] = str(r.get("why") or "not solved")[:200]
                rec.update({k: r[k] for k in ("matched", "rms_deg", "p_chance", "lens_disagree_deg", "f_scale") if k in r})
        except Exception as e:
            rec["why"] = f"solver error: {e!r}"[:200]
        finally:
            self.solving = False
            s.log("frames", rec)

    def _tilt_corrected(self, s, rec, r, up, utc, off):
        """The fix again with the learned tilt of 'up' removed (lat_cal/lon_cal), then this fix taken as a
        calibration sample if the car is stopped and a fresh reference position exists."""
        from navera_tools.field import reprocess360 as rp
        R = np.array(r["R_icrs_imu"], float)
        cal = self.tilt_cal
        if cal is not None:
            lat, lon = rp.position(R @ (cal["Q"] @ up), utc)
            att = math.hypot(cal["sigma_deg"], r.get("sigma_fit_deg") or 0.0)
            if not rec.get("stopped", True):
                att = math.hypot(att, MOVING_ATTITUDE_SIGMA_DEG)
            rec.update(lat_cal=lat, lon_cal=lon, cal_samples=cal["n"],
                       sigma_km_cal=round(att * report_mod.KM_PER_DEGREE + abs(off) * report_mod.SKY_KM_PER_SECOND, 1))
            p = self.phone
            if p.get("lat") is not None:
                rec["err_km_cal_live"] = round(report_mod.haversine_km(lat, lon, p["lat"], p["lon"]), 1)
        p = self.phone
        trusted = rec.get("stopped") and not rec.get("stopped_but_phone_moving")
        fresh = p.get("lat") is not None and time.time() - self.phone_recv < 4.0 and (p.get("acc") or 999) <= 30
        if not trusted or not fresh or len(self.cal_samples) >= CAL_SAMPLES:
            return
        self.cal_samples.append((R, np.asarray(up, float), rp.zenith_icrs(p["lat"], p["lon"], utc)))
        rec["cal_sample"] = len(self.cal_samples)
        if len(self.cal_samples) < CAL_MIN_SAMPLES:
            return
        w = rp.fit_mount(self.cal_samples)
        Q = rp.rotvec(w)
        res = [math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(Rk @ (Q @ u) / np.linalg.norm(u), z))))))
               for Rk, u, z in self.cal_samples]
        n = len(res)
        rms = math.sqrt(sum(x * x for x in res) / n) * math.sqrt(n / max(n - 2, 1))
        self.tilt_cal = {"Q": Q, "n": n, "sigma_deg": max(rms, CAL_SIGMA_FLOOR_DEG)}
        s.event("tilt_calibrated", samples=n, tilt_deg=round(math.degrees(float(np.linalg.norm(w))), 3),
                rotvec_deg=[round(math.degrees(float(v)), 3) for v in w], residual_deg=round(rms, 3),
                frozen=n >= CAL_SAMPLES)

    def _solve(self, s, rec, jpg, att, texp, hfov):
        import base64
        try:
            from cn_pkg.nodes.solver import solve_image_b64_geoloc
            off = self.clock_offset_s() or 0.0
            utc_epoch = texp - off                    # phone time = Jetson time - offset
            utc = datetime.fromtimestamp(utc_epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            p = self.phone
            # Near the zenith the sky gives ONE position, so no prior is needed and none is given: the
            # solver accepts a fix only within 2 degrees of its prior, which would hide big errors
            # instead of measuring them. A strongly tilted camera has two candidate positions and
            # needs the phone's position to choose between them.
            prior_lat = prior_lon = float("nan")
            if att["alt"] < 60.0 and p.get("lat") is not None:
                prior_lat, prior_lon = p["lat"], p["lon"]
            t0 = time.time()
            r = solve_image_b64_geoloc(base64.b64encode(jpg).decode(), att["alt"], att["az"], utc,
                                       prior_lat, prior_lon, hfov)
            rec["solve_s"] = round(time.time() - t0, 1)
            rec["utc_used"] = utc
            rec["prior"] = None if prior_lat != prior_lat else [prior_lat, prior_lon]
            if r.get("success"):
                sigma = ATTITUDE_SIGMA_DEG * report_mod.KM_PER_DEGREE + abs(off) * report_mod.SKY_KM_PER_SECOND
                rec.update(solved=True, lat=r["predicted_lat"], lon=r["predicted_lon"], ra=r.get("ra_deg"),
                           dec=r.get("dec_deg"), log_odds=r.get("log_odds"), sigma_km=round(sigma, 1))
                truth = {k: p.get(k) for k in ("lat", "lon")}
                if truth["lat"] is not None:
                    rec["err_km_live"] = round(report_mod.haversine_km(r["predicted_lat"], r["predicted_lon"],
                                                                       truth["lat"], truth["lon"]), 1)
                self.n_fixes += 1
                self.last_fix = {"t": time.time(), "lat": r["predicted_lat"], "lon": r["predicted_lon"],
                                 "err_km": rec.get("err_km_live"), "sigma_km": rec["sigma_km"]}
            else:
                rec["why"] = str(r.get("error") or "not solved")[:200]
        except Exception as e:
            rec["why"] = f"solver error: {e!r}"[:200]
        finally:
            self.solving = False
            s.log("frames", rec)

    # ── session control ─────────────────────────────────────────────────
    def go(self, step):
        """Move to a step. Only the page's own order is allowed, so a second phone or a double tap cannot wreck a test."""
        try:
            step = int(step)
        except (TypeError, ValueError):
            return
        with self.go_lock:
            if step not in (1, 2, 3, 4, 5):
                return
            if self.session is not None and step not in (4, 5):
                return                                   # recording: only "finish" leaves step 4
            if step == 4 and self.session is not None:
                return                                   # already recording (double tap)
            if step == 5 and self.session is None:
                return
            if step == 4 and self.step != 3:
                return
            if step == 4:
                self.session = FieldSession(self.root, {"camera_device": self.camera.device,
                                                        "calibration": self.camera.cal_path, "interval_s": self.interval_s,
                                                        "min_stars": MIN_STARS, "attitude_sigma_deg": ATTITUDE_SIGMA_DEG,
                                                        "clock_offset_s": self.clock_offset_s(),
                                                        "mode": self.mode, "operator_note": ""})
                if self.mode == "360":
                    self.session.update_meta(attitude_sigma_deg=ATTITUDE_SIGMA_360_DEG, imu_calibration=_read_json(self.camera.cal_path),
                                             latency_s=self.camera.latency_s, f_scale=self.f_scale)
                self.frame_idx = 0
                self.n_fixes = 0
                self.last_fix = {}
                self.last_solve_t = 0.0
                self.tracker = type(self.tracker)()
                self.session.event("step", to=4)
            elif step == 5:
                self.finish()
                return
            self.step = step

    def start(self):
        """The operator's START: recording begins now whatever the sky (the camera, stars and steadiness are
        only reported, never waited for). A second START while recording changes nothing."""
        with self.go_lock:
            if self.session is not None:
                return
            self.mount_confirmed = True
            self.step = 3
            self.go(4)
            if self.session is not None:
                self.session.event("start", by="operator")

    def end(self):
        """The operator's END: the test is closed and reported."""
        with self.go_lock:
            if self.session is not None:
                self.session.event("end", by="operator")
                self.go(5)

    def finish(self):
        s = self.session
        if s is None:
            return None
        deadline = time.time() + 60
        while self.solving and time.time() < deadline:
            time.sleep(0.5)
        r = None
        try:
            s.update_meta(clock_offset_s=self.clock_offset_s())
            s.event("step", to=5)
            s.close()
            r = report_mod.write_report(s.dir)
            s.update_meta(verdict=r["verdict"], frames=r["frames"], solved=r["solved"],
                          problems=[p["id"] for p in r["problems"]])
        except Exception as e:                       # whatever failed, the operator must get out of step 4
            log(f"finish error: {e!r}")
        self.session = None
        self.step = 5
        self.last_done = s.id
        return r

    def state(self):
        s = self.session
        return {"step": self.step, "mode": self.mode, "checks": self.checks(), "live": self.live, "mount_confirmed": self.mount_confirmed,
                "recording": s.id if s else None, "frames": self.frame_idx if s else 0,
                "started": s.meta.get("started") if s else None, "fixes": self.n_fixes if s else 0,
                "camera_error": self.camera.error,
                "imu_age_s": _round(self.camera.imu_age(), 1) if hasattr(self.camera, "imu_age") else None,
                "last_fix": self.last_fix, "solving": self.solving, "interval_s": self.interval_s,
                "done": self.last_done, "disk_error": bool(s and s.io_error), "server_time_ms": int(time.time() * 1000)}


# ── HTTP ────────────────────────────────────────────────────────────────
def make_handler(field: Field):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, code, ctype, body: bytes, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            def clean(x):
                if isinstance(x, float) and not math.isfinite(x):
                    return None
                if isinstance(x, dict):
                    return {k: clean(v) for k, v in x.items()}
                if isinstance(x, (list, tuple)):
                    return [clean(v) for v in x]
                return x
            self._send(code, "application/json", json.dumps(clean(obj), default=str).encode())

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 100_000:
                return {}
            try:
                return json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return {}

        def _session_dir(self, sid):
            sid = os.path.basename(sid)
            p = os.path.join(field.root, sid)
            return p if os.path.isdir(p) and os.path.exists(os.path.join(p, "session.json")) else None

        def _authed(self, query):
            """True when the request carries the link's key (cookie, or ?k= which sets the cookie)."""
            import hmac
            cookie = self.headers.get("Cookie", "")
            have = next((c.split("=", 1)[1] for c in (x.strip() for x in cookie.split(";")) if c.startswith("navera_k=")), "")
            given = (query.get("k") or [have])[0]
            if not given or not field.key:
                return False
            return hmac.compare_digest(given.encode(), field.key.encode())

        def _deny(self):
            self._send(403, "text/html; charset=utf-8",
                       b"<!doctype html><meta name=viewport content='width=device-width'><body style='font:18px system-ui;padding:24px;"
                       b"background:#0b0d12;color:#d9dde8'><h2>This link is not valid</h2><p>Ask the owner for the test link.</p>")

        def do_GET(self):
            u = urlparse(self.path)
            path = u.path.rstrip("/")
            q = parse_qs(u.query)
            if path in PUBLIC_FILES:          # the app's icons and offline shell: no data, no key
                name, ctype = PUBLIC_FILES[path]
                with open(os.path.join(HERE, "static", name), "rb") as f:
                    extra = {"Service-Worker-Allowed": "/"} if name == "sw.js" else None
                    return self._send(200, ctype, f.read(), extra)
            if not self._authed(q):
                return self._deny()
            if "k" in q:           # first visit from the link: keep the key in a cookie and drop it from the address bar
                return self._send(303, "text/plain", b"", {"Location": "/field", "Set-Cookie":
                                  f"navera_k={q['k'][0]}; Max-Age=31536000; Path=/; Secure; HttpOnly; SameSite=Lax"})
            if path in ("", "/", "/field"):
                with open(os.path.join(HERE, "page.html"), "rb") as f:
                    # the key is already this phone's (cookie): an iPhone home-screen app needs it in its address
                    return self._send(200, "text/html; charset=utf-8", f.read().replace(b"__NAVERA_KEY__", field.key.encode()))
            if path == "/manifest.webmanifest":
                # authenticated: its start address carries the key, so the installed app opens straight in
                return self._send(200, "application/manifest+json", json.dumps(app_manifest(field.key)).encode())
            if path == "/api/state":
                return self._json(field.state())
            if path == "/api/preview.jpg":
                return self._send(200, "image/jpeg", field.preview) if field.preview else self._json({"error": "no frame"}, 404)
            if path == "/api/sessions":
                return self._json([{k: m.get(k) for k in ("id", "started", "ended", "verdict", "frames", "solved", "problems")}
                                   for m in list_sessions(field.root)])
            if path.startswith("/api/session/"):
                parts = path.split("/")[3:]
                d = self._session_dir(parts[0])
                if d is None:
                    return self._json({"error": "unknown test"}, 404)
                if len(parts) == 1:
                    return self._json(report_mod.analyze(d))
                if parts[1] == "zip":
                    tmp = tempfile.mktemp(suffix=".zip")
                    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
                        for dp, _, files in os.walk(d):
                            for fn in files:
                                z.write(os.path.join(dp, fn), os.path.join(os.path.basename(d), os.path.relpath(os.path.join(dp, fn), d)))
                    with open(tmp, "rb") as f:
                        data = f.read()
                    os.unlink(tmp)
                    return self._send(200, "application/zip", data,
                                      {"Content-Disposition": f'attachment; filename="{os.path.basename(d)}.zip"'})
                if parts[1] == "frame" and len(parts) == 3:
                    fp = os.path.join(d, "frames", os.path.basename(parts[2]))
                    if os.path.exists(fp):
                        with open(fp, "rb") as f:
                            return self._send(200, "image/jpeg", f.read())
                return self._json({"error": "not found"}, 404)
            return self._json({"error": "not found"}, 404)

        def do_POST(self):
            path = urlparse(self.path).path.rstrip("/")
            if not self._authed({}):
                return self._deny()
            d = self._body()
            if path == "/api/phone":
                field.on_phone(d)
                return self._json({"ok": True, "server_time_ms": int(time.time() * 1000)})
            if path == "/api/phone_batch":
                return self._json({"ok": True, "stored": field.on_phone_batch(d.get("items", []) if isinstance(d, dict) else [])})
            if path == "/api/step":
                field.go(d.get("to", 1))
                return self._json(field.state())
            if path == "/api/start":
                field.start()
                return self._json(field.state())
            if path == "/api/end":
                field.end()
                return self._json(field.state())
            if path == "/api/mount":
                field.mount_confirmed = bool(d.get("confirmed"))
                return self._json({"ok": True})
            if path == "/api/note":
                if field.session is not None:
                    field.session.event("note", text=str(d.get("text", ""))[:500])
                return self._json({"ok": True})
            if path == "/api/mark":
                if field.session is not None:
                    field.session.event("mark", text=str(d.get("text", ""))[:200])
                return self._json({"ok": True})
            if path == "/api/reanalyze":
                dd = self._session_dir(str(d.get("id", "")))
                return self._json(report_mod.write_report(dd)) if dd else self._json({"error": "unknown test"}, 404)
            return self._json({"error": "not found"}, 404)

    return H


PUBLIC_FILES = {"/sw.js": ("sw.js", "text/javascript; charset=utf-8"),
                "/static/icon-192.png": ("icon-192.png", "image/png"),
                "/static/icon-512.png": ("icon-512.png", "image/png"),
                "/static/apple-touch-icon.png": ("apple-touch-icon.png", "image/png")}


def app_manifest(key):
    """The installable phone app (Add to Home screen): NAVERA Sky Test, full screen, opening the test page."""
    return {"name": "NAVERA Sky Test", "short_name": "NAVERA Sky", "start_url": f"/field?k={key}", "scope": "/",
            "display": "standalone", "orientation": "portrait", "background_color": "#0b0d12", "theme_color": "#0b0d12",
            "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
                      {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]}


class NoCamera:
    """NAVERA_FIELD_CAMERA=none: the server without any camera (checks of the page and the phone; it never
    opens a USB or video device)."""
    device, cal_path, hfov, latency_s, error = "none", "none", None, 0.0, "no camera (NAVERA_FIELD_CAMERA=none)"

    def latest(self):
        return None, 0.0


def lan_addresses():
    """IPv4 addresses a phone can reach: Wi-Fi/Ethernet (same network) and Tailscale; never loopback or docker."""
    out = []
    try:
        lines = subprocess.run(["ip", "-4", "-o", "addr"], capture_output=True, text=True, timeout=5).stdout.splitlines()
    except Exception:
        lines = []
    for ln in lines:
        f = ln.split()
        if len(f) < 4:
            continue
        dev, ip = f[1], f[3].split("/")[0]
        if dev == "lo" or dev.startswith(("docker", "br-", "veth", "virbr")):
            continue
        out.append((dev, ip))
    return out


def write_links(root, key, public, lan_port):
    """LINK.txt (and LINK_QR.png when the qrcode module exists): every address of the operator's link."""
    lines, lan = [], []
    if public:
        lines.append(f"internet (phone hotspot with mobile data, Claude can watch): {public}/field?k={key}")
    if lan_port > 0 and subprocess.run(["systemctl", "is-active", "--quiet", "avahi-daemon"]).returncode == 0:
        lines.append(f"same Wi-Fi or hotspot by name (iPhone, most Android): https://{socket.gethostname()}.local:{lan_port}/field?k={key}")
    for dev, ip in lan_addresses():
        link = f"https://{ip}:{lan_port}/field?k={key}"
        if dev.startswith("tailscale"):
            lines.append(f"tailscale (devices on the tailnet): {link}")
        else:
            lines.append(f"same Wi-Fi or hotspot, no internet needed ({dev}): {link}")
            lan.append(link)
    with open(os.path.join(root, "LINK.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    qr = None
    try:
        import qrcode
        target = lan[0] if lan else (f"{public}/field?k={key}" if public else None)
        if target:
            qr = os.path.join(root, "LINK_QR.png")
            qrcode.make(target).save(qr)
    except ImportError:
        pass
    return lines, qr


def access_key(root):
    """The secret in the operator's link. Kept in <root>/access_key.txt; delete the file for a new link.
    A missing, empty or short key is replaced, so the link can never be open to everyone."""
    p = os.path.join(root, "access_key.txt")
    key = ""
    if os.path.exists(p):
        with open(p) as f:
            key = f.read().strip()
    if len(key) < 8:
        import secrets
        key = secrets.token_urlsafe(12)
        with open(p + ".tmp", "w") as f:
            f.write(key)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(p + ".tmp", 0o600)
        os.replace(p + ".tmp", p)
    return key


def ensure_certificate(tls_dir):
    """A self-signed certificate valid for every address this machine has now."""
    os.makedirs(tls_dir, exist_ok=True)
    cert, key, ips_file = (os.path.join(tls_dir, n) for n in ("cert.pem", "key.pem", "ips.txt"))
    try:
        ips = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.split()
    except Exception:
        ips = []
    ips = sorted(i for i in ips if ":" not in i)
    names = [f"{socket.gethostname()}.local"]        # the Jetson's name on the local network (mDNS)
    old = open(ips_file).read().split() if os.path.exists(ips_file) else None
    if not (os.path.exists(cert) and os.path.exists(key)) or (old is not None and not set(ips + names) <= set(old)):
        san = ",".join(["DNS:navera-field", "DNS:localhost", "IP:127.0.0.1"] + [f"DNS:{n}" for n in names] + [f"IP:{i}" for i in ips])
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650", "-subj", "/CN=navera-field",
                        "-addext", f"subjectAltName={san}", "-keyout", key, "-out", cert], check=True, capture_output=True)
        with open(ips_file, "w") as f:
            f.write(" ".join(ips + names))
    return cert, key, ips


def _round(v, n):
    return None if v is None or not math.isfinite(v) else round(float(v), n)


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def insta360_android_mode():
    """True when the Insta360 is plugged in USB mode "Android" (full 360 + its own IMU)."""
    try:
        import usb.core
        return usb.core.find(idVendor=0x2E1A, idProduct=0x0002) is not None
    except Exception:
        return False


def find_calibration():
    for p in CALIBRATION_SEARCH:
        if p and os.path.exists(p):
            return p
    sys.exit("no camera calibration file found: set NAVERA_CAMERA_CALIBRATION (navera_tools/calibrate_camera.py makes it)")


def main():
    root = os.environ.get("NAVERA_FIELD_DIR", os.path.expanduser("~/navera-field"))
    port = int(os.environ.get("NAVERA_FIELD_PORT", "8443"))
    choice = os.environ.get("NAVERA_FIELD_CAMERA", "auto")         # auto | 360 | strip | none
    if choice == "none":
        camera = NoCamera()
        log(f"camera: none (NAVERA_FIELD_CAMERA=none)\ntests saved in {root}")
    elif choice == "360" or (choice == "auto" and insta360_android_mode()):
        camera = Camera360()
        log(f"camera: Insta360 full 360 over USB (Android mode), own IMU, calibration {camera.cal_path}\ntests saved in {root}")
    else:
        device = os.environ.get("NAVERA_CAMERA_DEVICE", DEFAULT_DEVICE)
        cal = find_calibration()
        log(f"camera {device}\ncalibration {cal}\ntests saved in {root}")
        camera = Camera(device, cal)
    field = Field(root, camera)
    public = os.environ.get("NAVERA_FIELD_PUBLIC_URL", "")          # e.g. https://navera-academy.tail27d06f.ts.net:8443
    servers = []
    if os.environ.get("NAVERA_FIELD_PLAIN") == "1":
        # behind Tailscale (serve/funnel): it provides the trusted HTTPS address, this stays on this machine
        servers.append(ThreadingHTTPServer(("127.0.0.1", port), make_handler(field)))
        lan_port = int(os.environ.get("NAVERA_FIELD_LAN_PORT", "8445"))
    else:
        lan_port = int(os.environ.get("NAVERA_FIELD_LAN_PORT", str(port)))
    if lan_port > 0:
        # the same page on the local network (the phone's hotspot or the same Wi-Fi, no internet needed),
        # with this machine's own certificate: the phone warns once
        cert, key, _ = ensure_certificate(os.path.join(root, "tls"))
        lan = ThreadingHTTPServer(("0.0.0.0", lan_port), make_handler(field))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        lan.socket = ctx.wrap_socket(lan.socket, server_side=True)
        servers.append(lan)
        log("(on the local network the phone warns about the certificate once: Advanced, then continue)")
    for h in servers:
        h.daemon_threads = True
    import signal
    signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    links, qr = write_links(root, field.key, public, lan_port)
    for link in links:
        log(f"link for the operator's phone, {link}")
    log(f"QR code of the link: {qr}" if qr else "(no QR code: python module qrcode not installed)")
    httpd = servers[0]
    for h in servers[1:]:
        threading.Thread(target=h.serve_forever, daemon=True).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        if field.session is not None:
            field.finish()


if __name__ == "__main__":
    main()
