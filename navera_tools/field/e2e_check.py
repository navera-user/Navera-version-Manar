#!/usr/bin/env python3
"""End-to-end check of the field sky test, runnable from cron (no DISPLAY, never the real camera).

    python3 -m navera_tools.field.e2e_check --selftest       # a whole test on a synthetic 360 sky
    python3 -m navera_tools.field.e2e_check --live URL       # read-only health of the running server

--selftest starts the real server code on a free port with HTTPS (its own certificate) and a synthetic
360 camera (selftest360's star sky and gravity), then plays the phone over HTTPS the way the app does:
opens the link (key -> cookie), loads the page, manifest, service worker and icons, sends a GPS sample
every second, START, keeps sending until a position is solved (at least 60 s, at most 6 min), END. It
passes when the test folder holds the report, the phone's GPS track, the frames (records and images) and
a position within 20 km of the phone. The test is written in a temporary folder, removed when it passes.

--live only reads /api/state (never START or END): server answering, camera, camera IMU age, disk.

Both print one verdict line, append it to <NAVERA_FIELD_DIR>/E2E.log and exit 0 (pass) or 1.
"""
import argparse
import http.cookiejar
import json
import os
import shutil
import socket
import ssl
import sys
import tempfile
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg"), os.path.join(ROOT, "navera_tools", "sim")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FIELD_DIR = os.environ.get("NAVERA_FIELD_DIR", os.path.expanduser("~/navera-field"))
MAX_ERR_KM = 20.0


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname, c.verify_mode = False, ssl.CERT_NONE             # the Jetson's own certificate
    return c


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


class Phone:
    """The app's side of the conversation: one cookie jar, JSON over HTTPS."""

    def __init__(self, base):
        self.base = base.rstrip("/")
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ctx()),
                                              urllib.request.HTTPCookieProcessor(self.jar), NoRedirect())

    def get(self, path, timeout=10):
        try:
            with self.op.open(self.base + path, timeout=timeout) as r:
                return r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", ""), e.read()

    def post(self, path, body, timeout=90):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with self.op.open(req, timeout=timeout) as r:
            return json.loads(r.read())


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def selftest(limit_mag=3.0, min_s=60.0, max_s=360.0):
    """(ok, verdict line)."""
    import ssl as _ssl
    from datetime import datetime, timezone
    from http.server import ThreadingHTTPServer
    from navera_tools.field import selftest360 as st, server
    from navera_tools.field.store import read_jsonl
    now = datetime.now(timezone.utc)
    lon = st.night_longitude(now)
    frame, up = st.render(now.strftime("%Y-%m-%d %H:%M:%S"), st.LAT, lon, limit_mag)
    root = tempfile.mkdtemp(prefix="navera_e2e_")
    field = server.Field(root, st.SimCamera360(frame, up))
    field.interval_s = 5.0
    cert, key, _ = server.ensure_certificate(os.path.join(root, "tls"))
    port = free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), server.make_handler(field))
    c = _ssl.SSLContext(_ssl.PROTOCOL_TLS_SERVER)
    c.load_cert_chain(cert, key)
    httpd.socket = c.wrap_socket(httpd.socket, server_side=True)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    ph = Phone(f"https://127.0.0.1:{port}")
    fails = []

    def need(cond, what):
        if not cond:
            fails.append(what)
        return cond

    try:
        code, _, _ = ph.get(f"/field?k={field.key}")
        need(code == 303 and any(ck.name == "navera_k" for ck in ph.jar), f"link with key -> {code}, no cookie")
        code, ctype, body = ph.get("/field")
        need(code == 200 and b"START" in body and field.key.encode() in body, f"page {code}")
        code, ctype, body = ph.get("/manifest.webmanifest")
        need(code == 200 and json.loads(body or b"{}").get("start_url", "").endswith(field.key), f"manifest {code}")
        for p in ("/sw.js", "/static/icon-192.png", "/static/icon-512.png", "/static/apple-touch-icon.png"):
            code, _, body = ph.get(p)
            need(code == 200 and body, f"{p} {code}")
        code, _, _ = Phone(f"https://127.0.0.1:{port}").get("/api/state")
        need(code == 403, f"/api/state without the key -> {code}")

        def sample():
            ph.post("/api/phone", {"lat": st.LAT, "lon": lon, "acc": 5, "speed": 0,
                                   "phone_t_ms": int(time.time() * 1000), "gps_t_ms": int(time.time() * 1000)})
        for _ in range(3):
            sample()
            time.sleep(1.0)
        s = ph.post("/api/start", {})
        need(bool(s.get("recording")), "START did not start a recording")
        t0 = time.time()
        while time.time() - t0 < max_s:
            sample()
            s = json.loads(ph.get("/api/state")[2])
            if time.time() - t0 >= min_s and (s.get("fixes") or 0) > 0:
                break
            time.sleep(1.0)
        s = ph.post("/api/end", {})
        need(s.get("recording") is None and s.get("done"), "END did not close the test")
        d = os.path.join(root, s.get("done") or "?")
        files = set(os.listdir(d)) if os.path.isdir(d) else set()
        need({"report.json", "report.md", "phone.jsonl", "frames.jsonl", "events.jsonl"} <= files, f"files {sorted(files)}")
        gps = [p for p in read_jsonl(os.path.join(d, "phone.jsonl")) if p.get("lat") is not None]
        need(len(gps) >= 0.8 * min_s, f"phone track {len(gps)} samples")
        frames = read_jsonl(os.path.join(d, "frames.jsonl"))
        imgs = [f for f in frames if f.get("image") and os.path.exists(os.path.join(d, f["image"]))]
        need(frames and imgs, f"frames {len(frames)}, images {len(imgs)}")
        errs = [f["err_km_live"] for f in frames if f.get("solved") and isinstance(f.get("err_km_live"), (int, float))]
        need(errs and min(errs) <= MAX_ERR_KM, f"positions {errs[:5]}")
        verdict = (f"selftest {'PASS' if not fails else 'FAIL'}: {len(gps)} GPS samples, {len(frames)} frames "
                   f"({len(imgs)} images), {len(errs)} positions, best {min(errs) if errs else '-'} km"
                   + (f"; problems: {'; '.join(fails)}" if fails else ""))
    except Exception as e:
        fails.append(repr(e))
        verdict = f"selftest FAIL: {e!r}"
    finally:
        httpd.shutdown()
    if not fails:
        shutil.rmtree(root, ignore_errors=True)
    else:
        verdict += f" (kept in {root})"
    return not fails, verdict


def live(url, key=None):
    """(ok, verdict line): read-only health of a running server."""
    if key is None:
        try:
            key = open(os.path.join(FIELD_DIR, "access_key.txt")).read().strip()
        except OSError:
            key = ""
    req = urllib.request.Request(url.rstrip("/") + "/api/state", headers={"Cookie": f"navera_k={key}"})
    try:
        with urllib.request.urlopen(req, timeout=10, context=_ctx()) as r:
            s = json.loads(r.read())
    except Exception as e:
        return False, f"live FAIL: {url} does not answer ({e!r})"
    cam = next((c for c in s.get("checks") or [] if c.get("id") == "camera"), {})
    imu = s.get("imu_age_s")
    free = shutil.disk_usage(FIELD_DIR).free / 1e9 if os.path.isdir(FIELD_DIR) else None
    probs = []
    if cam.get("status") != "ok":
        probs.append(f"camera {cam.get('detail') or cam.get('status')}")
    if s.get("mode") == "360" and (imu is None or imu > 5.0):
        probs.append(f"camera IMU {'silent' if imu is None else f'{imu:.0f} s old'}")
    if free is not None and free < 2.0:
        probs.append(f"disk {free:.1f} GB free")
    if s.get("disk_error"):
        probs.append("cannot write to disk")
    rec = s.get("recording")
    return not probs, (f"live {'OK' if not probs else 'PROBLEM'}: step {s.get('step')}, "
                       + (f"recording {rec}, {s.get('frames')} frames, {s.get('fixes')} positions" if rec else "not recording")
                       + (f", disk {free:.0f} GB free" if free is not None else "") + (f"; {'; '.join(probs)}" if probs else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--selftest", action="store_true")
    g.add_argument("--live", metavar="URL")
    ap.add_argument("--key", help="--live: the link's key (default: <NAVERA_FIELD_DIR>/access_key.txt)")
    ap.add_argument("--min-s", type=float, default=60.0, help="--selftest: seconds of driving before END")
    a = ap.parse_args()
    ok, verdict = selftest(min_s=a.min_s) if a.selftest else live(a.live, a.key)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {verdict}"
    print(line, flush=True)
    try:
        os.makedirs(FIELD_DIR, exist_ok=True)
        with open(os.path.join(FIELD_DIR, "E2E.log"), "a") as f:
            f.write(line + "\n")
    except OSError:
        pass
    os._exit(0 if ok else 1)          # the server's background threads must not hold the exit


if __name__ == "__main__":
    main()
