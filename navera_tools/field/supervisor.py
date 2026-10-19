#!/usr/bin/env python3
"""Watch a field sky test from the Jetson itself: one status screen and an alert log, so the owner (or Claude,
remotely) sees at a glance what is happening and what to do. It only READS the test: it never writes into a
session's files and never starts or ends a test.

    python3 -m navera_tools.field.supervisor [--root ~/navera-field] [--url URL] [--interval 20] [--once]

Every --interval seconds it reads the newest test folder (frames.jsonl, phone.jsonl, events.jsonl) and the
server's /api/state, writes <root>/STATUS.txt (one screen) and appends to <root>/ALERTS.log each problem
when it appears (with what to do) and when it clears. When a 360 test is finished it runs
`reprocess360 --fit 12` once and keeps its output in <root>/<test>_reprocess360.txt.

run_field.sh starts it next to the server.
"""
import argparse
import json
import os
import shutil
import ssl
import statistics
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

IMU_SILENT_S = 30.0
NO_FRAME_S = 60.0
PHONE_SILENT_S = 60.0
DISK_MIN_GB = 2.0
SOLVE_SLOW_S = 6.0
NO_USE_FIX_S = 600.0


def read_jsonl(path, tail=None):
    """Records of a .jsonl file (a half-written last line is skipped)."""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as f:
        if tail:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - tail))
        lines = f.read().decode("utf-8", "replace").splitlines()
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return out


def newest_session(root):
    """The newest test folder (holding session.json), or None."""
    ds = [os.path.join(root, n) for n in os.listdir(root) if os.path.exists(os.path.join(root, n, "session.json"))] \
        if os.path.isdir(root) else []
    return max(ds, key=lambda d: (os.path.getmtime(os.path.join(d, "session.json")), d)) if ds else None


def fetch_state(url, key, timeout=5.0):
    """The server's /api/state (dict), or None when it does not answer."""
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE        # the Jetson's own certificate
    req = urllib.request.Request(url.rstrip("/") + "/api/state", headers={"Cookie": f"navera_k={key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read())
    except Exception:
        return None


def use_fix(f):
    """A fix made while stopped (the trusted ones), as watch.py judges them."""
    return bool(f.get("solved")) and f.get("stopped", True) and not f.get("stopped_but_phone_moving")


def assess(state, folder, now=None, root=None):
    """(status lines, {alert id: (message, what to do)}) from the server's state and the newest test."""
    now = time.time() if now is None else now
    lines, alerts = [], {}
    lines.append(f"NAVERA field test - {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}")
    if state is None:
        lines.append("server: NOT ANSWERING")
        alerts["server"] = ("the field server does not answer", "check navera-field is running (run_field.sh / systemctl status navera-field)")
    else:
        rec = state.get("recording")
        lines.append(f"server: ok   step {state.get('step')}   "
                     + (f"RECORDING {rec}" if rec else f"not recording (last test {state.get('done') or '-'})"))
        checks = {c.get("id"): c for c in state.get("checks") or []}
        cam = checks.get("camera", {})
        imu = state.get("imu_age_s")
        lines.append(f"camera: {cam.get('status', '?')} {cam.get('detail') or ''}".rstrip()
                     + (f"   IMU age {imu:.1f} s" if isinstance(imu, (int, float)) else ""))
        if state.get("mode") == "360" and (imu is None or imu > IMU_SILENT_S):
            alerts["imu"] = (f"camera IMU silent ({'never' if imu is None else f'{imu:.0f} s'})",
                             "the server reconnects by itself; if it lasts, unplug and replug the camera USB (USB mode Android)")
        live = state.get("live") or {}
        lines.append(f"sky: {live.get('sky') or '-'}   stars {live.get('confirmed') if live.get('confirmed') is not None else '-'}"
                     f"   frames {state.get('frames', 0)}   fixes {state.get('fixes', 0)}")
        if state.get("disk_error"):
            alerts["disk_write"] = ("cannot write the test to disk", "free space or check the disk; the test is not being saved")
    if folder:
        frames = read_jsonl(os.path.join(folder, "frames.jsonl"), tail=2_000_000)
        phone = read_jsonl(os.path.join(folder, "phone.jsonl"), tail=200_000)
        meta = json.load(open(os.path.join(folder, "session.json")))
        running = meta.get("ended") is None
        lines.append(f"test {os.path.basename(folder)}: {'running' if running else 'finished'}, "
                     f"{len(frames)} frames, {sum(1 for f in frames if f.get('solved'))} solved")
        solved = [f for f in frames if f.get("solved")]
        if solved:
            f = solved[-1]
            verdict = "USE" if use_fix(f) else "IGNORE"
            lines.append(f"last fix {now - f.get('t', now):.0f} s ago: {verdict}  err {f.get('err_km_live')} km"
                         f"  corrected {f.get('err_km_cal_live', '-')} km  sigma {f.get('sigma_km')} km")
        cal = [f.get("cal_sample") for f in frames if f.get("cal_sample")]
        lines.append(f"tilt calibration samples: {max(cal) if cal else 0}")
        if phone:
            p = phone[-1]
            lines.append(f"phone GPS: {now - p.get('t', now):.0f} s ago, accuracy {p.get('acc')} m")
        else:
            lines.append("phone GPS: none yet")
        if running:
            if not frames or now - frames[-1].get("t", 0) > NO_FRAME_S:
                alerts["frames"] = ("no frame recorded for over a minute", "check the camera is plugged in and on (USB mode Android)")
            if not phone or now - phone[-1].get("t", 0) > PHONE_SILENT_S:
                alerts["phone"] = ("the phone sent no GPS for over a minute",
                                   "the operator must keep the NAVERA app open with location on (it sends what it kept later)")
            ss = [f["solve_s"] for f in frames[-40:] if isinstance(f.get("solve_s"), (int, float))]
            if len(ss) >= 5 and statistics.median(ss) > SOLVE_SLOW_S:
                alerts["slow"] = (f"solves slow (median {statistics.median(ss):.1f} s)", "the Jetson is overloaded or hot: stop other jobs")
            fooled = sum(1 for f in frames if f.get("solved") and f.get("stopped_but_phone_moving"))
            if fooled:
                alerts["fooled"] = (f"{fooled} fix(es) called stopped while the phone moved",
                                    "the stillness test was fooled (smooth road): those fixes are ignored, nothing to do")
            started = meta.get("started") or 0
            last_use = max([f.get("t", 0) for f in frames if use_fix(f)] or [started])
            if now - started > NO_USE_FIX_S and now - last_use > NO_USE_FIX_S:
                alerts["no_use"] = ("no trusted (stopped) fix for 10 minutes",
                                    "the driver must stop 20 s every 2-3 min; check the sky (clouds, lights) and the star count")
    if root:
        free = shutil.disk_usage(root).free / 1e9
        lines.append(f"disk free: {free:.1f} GB")
        if free < DISK_MIN_GB:
            alerts["disk"] = (f"only {free:.1f} GB free", "delete old tests or move them off the Jetson")
    for k, (msg, fix) in sorted(alerts.items()):
        lines.append(f"ALERT {k}: {msg} -> {fix}")
    return lines, alerts


def reprocess(root, folder):
    """Score a finished 360 test once (mounting angle fitted on the first 12 stopped fixes)."""
    out = os.path.join(root, os.path.basename(folder) + "_reprocess360.txt")
    if os.path.exists(out):
        return None
    frames = read_jsonl(os.path.join(folder, "frames.jsonl"))
    if not any(f.get("mode") == "360" for f in frames):
        return None
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([ROOT, os.path.join(ROOT, "navera_common"), os.path.join(ROOT, "cn_pkg")]))
    try:
        r = subprocess.run([sys.executable, "-m", "navera_tools.field.reprocess360", folder, "--fit", "12"],
                           capture_output=True, text=True, timeout=1800, env=env, cwd=ROOT)
        text = r.stdout + (("\n" + r.stderr[-2000:]) if r.returncode else "")
    except Exception as e:
        text = f"reprocess360 failed: {e!r}"
    with open(out, "w") as f:
        f.write(text)
    return out


def default_url():
    port = os.environ.get("NAVERA_FIELD_PORT", "8443")
    return f"http://127.0.0.1:{port}" if os.environ.get("NAVERA_FIELD_PLAIN") == "1" else f"https://127.0.0.1:{port}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=os.environ.get("NAVERA_FIELD_DIR", os.path.expanduser("~/navera-field")))
    ap.add_argument("--url", default=default_url())
    ap.add_argument("--interval", type=float, default=20.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    state_file = os.path.join(a.root, ".alerts_active.json")       # the alerts already logged (survives a restart)
    try:
        active = json.load(open(state_file))
    except (OSError, ValueError):
        active = {}
    while True:
        try:
            key = open(os.path.join(a.root, "access_key.txt")).read().strip()
        except OSError:
            key = ""
        folder = newest_session(a.root)
        lines, alerts = assess(fetch_state(a.url, key), folder, root=a.root)
        tmp = os.path.join(a.root, "STATUS.txt.tmp")
        with open(tmp, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, os.path.join(a.root, "STATUS.txt"))
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(a.root, "ALERTS.log"), "a") as f:
            for k, v in alerts.items():
                if active.get(k) != v[0]:
                    f.write(f"{stamp} ALERT {k}: {v[0]} -> {v[1]}\n")
            for k in set(active) - set(alerts):
                f.write(f"{stamp} cleared {k}\n")
        active = {k: v[0] for k, v in alerts.items()}
        with open(state_file, "w") as f:
            json.dump(active, f)
        if folder and json.load(open(os.path.join(folder, "session.json"))).get("ended"):
            reprocess(a.root, folder)
        if a.once:
            return 0
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
