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
CALIBRATION_SEARCH = (os.environ.get("NAVERA_CAMERA_CALIBRATION", ""), "/etc/navera/camera.yaml",
                      "/var/lib/navera/camera.yaml",
                      os.path.expanduser("~/.navera_sim/bench_2026-10-06/calib/insta360_top.yaml"))
DEFAULT_DEVICE = "/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0"
ATTITUDE_SIGMA_DEG = 0.5            # phone accelerometer, first guess until measured against a level
PRIOR_ROUND_DEG = 5.0               # the prior only picks between two far-apart candidates


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
        self.live: dict = {}
        self.preview: bytes = b""
        self.step = 1
        self.mount_confirmed = False
        self.session: Optional[FieldSession] = None
        self.frame_idx = 0
        self.interval_s = float(os.environ.get("NAVERA_FIELD_INTERVAL_S", "20"))
        self.last_solve_t = 0.0
        self.solving = False
        self.last_fix: dict = {}
        self.usable_skies = ("clear", "hazy")       # the only skies whose stars count and are solved
        threading.Thread(target=self._loop, daemon=True).start()

    # ── phone ───────────────────────────────────────────────────────────
    def on_phone(self, d: dict):
        now = time.time()
        with self.lock:
            if d.get("phone_t_ms") is not None:
                self.offsets.append(now - float(d["phone_t_ms"]) / 1000.0)
            self.phone, self.phone_recv = dict(d), now
        s = self.session
        if s is not None:
            s.log("phone", self._phone_record(d))

    def _phone_record(self, d):
        rec = {k: d.get(k) for k in ("lat", "lon", "acc", "alt", "speed", "course", "beta", "gamma", "compass")}
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
        add("camera", "Camera running", "ok" if t and now - t < 3 else "bad", self.camera.error or "")
        add("phone_gps", "Phone sharing GPS", "bad" if not fresh or acc is None else ("ok" if acc <= 30 else "wait"),
            "no GPS from the phone: allow location on the page" if not fresh or acc is None else f"accuracy {acc:.0f} m")
        add("phone_tilt", "Phone sharing tilt", "ok" if att else "bad", "" if att else "allow motion sensors on the page")
        add("clock", "Phone clock matches Jetson", "wait" if off is None else ("ok" if abs(off) <= 0.5 else "bad"),
            "" if off is None else f"{off:+.2f} s")
        if att:
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
                if img is not None:
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
    def _maybe_solve(self, img, texp):
        s = self.session
        if s is None or self.step != 4 or self.solving or time.time() - self.last_solve_t < self.interval_s:
            return
        self.last_solve_t = time.time()
        self.frame_idx += 1
        idx, live, att = self.frame_idx, dict(self.live), self._attitude()
        rec = {"idx": idx, "detected": live.get("detected"), "confirmed": live.get("confirmed"), "sky": live.get("sky"),
               "rejected": live.get("rejected"), "shift_px": live.get("shift_px"), "solved": False}
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        rec["image"] = s.save_frame(idx, jpg.tobytes()) if ok else None
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
        self.solving = True
        threading.Thread(target=self._solve, args=(s, rec, jpg.tobytes(), att, texp), daemon=True).start()

    def _solve(self, s, rec, jpg, att, texp):
        import base64
        from cn_pkg.nodes.solver import solve_image_b64_geoloc
        try:
            off = self.clock_offset_s() or 0.0
            utc_epoch = texp - off                    # phone time = Jetson time - offset
            utc = datetime.fromtimestamp(utc_epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            p = self.phone
            prior_lat = prior_lon = float("nan")
            if p.get("lat") is not None:
                prior_lat = round(p["lat"] / PRIOR_ROUND_DEG) * PRIOR_ROUND_DEG
                prior_lon = round(p["lon"] / PRIOR_ROUND_DEG) * PRIOR_ROUND_DEG
            t0 = time.time()
            r = solve_image_b64_geoloc(base64.b64encode(jpg).decode(), att["alt"], att["az"], utc,
                                       prior_lat, prior_lon, self.camera.hfov)
            rec["solve_s"] = round(time.time() - t0, 1)
            rec["utc_used"] = utc
            rec["prior"] = [prior_lat, prior_lon]
            if r.get("success"):
                sigma = ATTITUDE_SIGMA_DEG * report_mod.KM_PER_DEGREE + abs(off) * report_mod.SKY_KM_PER_SECOND
                rec.update(solved=True, lat=r["predicted_lat"], lon=r["predicted_lon"], ra=r.get("ra_deg"),
                           dec=r.get("dec_deg"), log_odds=r.get("log_odds"), sigma_km=round(sigma, 1))
                truth = {k: p.get(k) for k in ("lat", "lon")}
                if truth["lat"] is not None:
                    rec["err_km_live"] = round(report_mod.haversine_km(r["predicted_lat"], r["predicted_lon"],
                                                                       truth["lat"], truth["lon"]), 1)
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
        step = int(step)
        if step == 4 and self.session is None:
            self.session = FieldSession(self.root, {"camera_device": self.camera.device,
                                                    "calibration": self.camera.cal_path, "interval_s": self.interval_s,
                                                    "min_stars": MIN_STARS, "attitude_sigma_deg": ATTITUDE_SIGMA_DEG,
                                                    "clock_offset_s": self.clock_offset_s(),
                                                    "operator_note": ""})
            self.frame_idx = 0
            self.last_solve_t = 0.0
            self.tracker.__init__()
            self.session.event("step", to=4)
        elif step == 5 and self.session is not None:
            self.finish()
        elif self.session is not None:
            self.session.event("step", to=step)
        self.step = step

    def finish(self):
        s = self.session
        if s is None:
            return None
        deadline = time.time() + 60
        while self.solving and time.time() < deadline:
            time.sleep(0.5)
        s.update_meta(clock_offset_s=self.clock_offset_s())
        s.event("step", to=5)
        s.close()
        r = report_mod.write_report(s.dir)
        s.update_meta(verdict=r["verdict"], frames=r["frames"], solved=r["solved"],
                      problems=[p["id"] for p in r["problems"]])
        self.session = None
        self.step = 5
        self.last_done = s.id
        return r

    def state(self):
        s = self.session
        return {"step": self.step, "checks": self.checks(), "live": self.live, "mount_confirmed": self.mount_confirmed,
                "recording": s.id if s else None, "frames": self.frame_idx if s else 0,
                "last_fix": self.last_fix, "solving": self.solving, "interval_s": self.interval_s,
                "done": getattr(self, "last_done", None), "server_time_ms": int(time.time() * 1000)}


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
            self._send(code, "application/json", json.dumps(obj, allow_nan=False, default=str).encode())

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
            return hmac.compare_digest(given.encode(), field.key.encode())

        def _deny(self):
            self._send(403, "text/html; charset=utf-8",
                       b"<!doctype html><meta name=viewport content='width=device-width'><body style='font:18px system-ui;padding:24px;"
                       b"background:#0b0d12;color:#d9dde8'><h2>This link is not valid</h2><p>Ask the owner for the test link.</p>")

        def do_GET(self):
            u = urlparse(self.path)
            path = u.path.rstrip("/")
            q = parse_qs(u.query)
            if not self._authed(q):
                return self._deny()
            if "k" in q:           # first visit from the link: keep the key in a cookie and drop it from the address bar
                return self._send(303, "text/plain", b"", {"Location": "/field", "Set-Cookie":
                                  f"navera_k={q['k'][0]}; Max-Age=31536000; Path=/; Secure; HttpOnly; SameSite=Lax"})
            if path in ("", "/", "/field"):
                with open(os.path.join(HERE, "page.html"), "rb") as f:
                    return self._send(200, "text/html; charset=utf-8", f.read())
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
            if path == "/api/step":
                field.go(d.get("to", 1))
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


def access_key(root):
    """The secret in the operator's link. Kept in <root>/access_key.txt; delete the file for a new link."""
    p = os.path.join(root, "access_key.txt")
    if not os.path.exists(p):
        import secrets
        with open(p, "w") as f:
            f.write(secrets.token_urlsafe(12))
        os.chmod(p, 0o600)
    with open(p) as f:
        return f.read().strip()


def ensure_certificate(tls_dir):
    """A self-signed certificate valid for every address this machine has now."""
    os.makedirs(tls_dir, exist_ok=True)
    cert, key, ips_file = (os.path.join(tls_dir, n) for n in ("cert.pem", "key.pem", "ips.txt"))
    try:
        ips = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.split()
    except Exception:
        ips = []
    ips = sorted(i for i in ips if ":" not in i)
    old = open(ips_file).read().split() if os.path.exists(ips_file) else None
    if not (os.path.exists(cert) and os.path.exists(key)) or (old is not None and not set(ips) <= set(old)):
        san = ",".join(["DNS:navera-field", "DNS:localhost", "IP:127.0.0.1"] + [f"IP:{i}" for i in ips])
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650", "-subj", "/CN=navera-field",
                        "-addext", f"subjectAltName={san}", "-keyout", key, "-out", cert], check=True, capture_output=True)
        with open(ips_file, "w") as f:
            f.write(" ".join(ips))
    return cert, key, ips


def find_calibration():
    for p in CALIBRATION_SEARCH:
        if p and os.path.exists(p):
            return p
    sys.exit("no camera calibration file found: set NAVERA_CAMERA_CALIBRATION (navera_tools/calibrate_camera.py makes it)")


def main():
    root = os.environ.get("NAVERA_FIELD_DIR", os.path.expanduser("~/navera-field"))
    port = int(os.environ.get("NAVERA_FIELD_PORT", "8443"))
    device = os.environ.get("NAVERA_CAMERA_DEVICE", DEFAULT_DEVICE)
    cal = find_calibration()
    log(f"camera {device}\ncalibration {cal}\ntests saved in {root}")
    field = Field(root, Camera(device, cal))
    public = os.environ.get("NAVERA_FIELD_PUBLIC_URL", "")          # e.g. https://navera-academy.tail27d06f.ts.net:8443
    if os.environ.get("NAVERA_FIELD_PLAIN") == "1":
        # behind Tailscale (serve/funnel): it provides the trusted HTTPS address, this stays on this machine
        httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(field))
        links = [f"{public or 'https://<tailscale address>'}/field?k={field.key}"]
    else:
        cert, key, ips = ensure_certificate(os.path.join(root, "tls"))
        httpd = ThreadingHTTPServer(("0.0.0.0", port), make_handler(field))
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        links = [f"https://{ip}:{port}/field?k={field.key}" for ip in ips]
        log("(on the local network the phone warns about the certificate once: Advanced, then continue)")
    httpd.daemon_threads = True
    with open(os.path.join(root, "LINK.txt"), "w") as f:
        f.write("\n".join(links) + "\n")
    for link in links:
        log(f"link for the operator's phone:  {link}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        if field.session is not None:
            field.finish()


if __name__ == "__main__":
    main()
