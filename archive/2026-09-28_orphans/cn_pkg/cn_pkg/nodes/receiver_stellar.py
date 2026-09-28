#!/usr/bin/env python3
from flask import Flask, request, jsonify
from flask_cors import CORS
import os, sys, subprocess, json, re, time, threading, base64
from datetime import datetime, timezone
from pathlib import Path

app = Flask(__name__)
CORS(app)

BASE_DIR   = Path("/home/navera/isaac_ros_common")
SOLVER     = BASE_DIR / "cn_pkg/cn_pkg/drone_sky_prep.py"
GPS_STATUS = BASE_DIR / "simulation_web/gps_status.json"
SAVE_DIR   = BASE_DIR / "cn_pkg/cn_pkg/images"

SAVE_DIR.mkdir(parents=True, exist_ok=True)
GPS_STATUS.parent.mkdir(parents=True, exist_ok=True)

TILT_MANUAL    = 75.46
AZIMUTH_MANUAL = 283.18
USE_MANUAL     = True
_solve_lock    = threading.Lock()

def write_gps(d):
    with open(str(GPS_STATUS), "w") as f:
        json.dump(d, f)
    try:
        import urllib.request as _ur
        _req = _ur.Request("http://localhost:8181/api/stellar_gps",
                           data=json.dumps(d).encode(),
                           headers={"Content-Type":"application/json"})
        _ur.urlopen(_req, timeout=2)
    except Exception:
        pass

write_gps({"status": "idle"})

def parse_solver_output(output):
    lat, lon, ra, dec = None, None, None, None
    for line in output.splitlines():
        if re.search(r'Latitude\s*:', line):
            m = re.search(r'([-+]?\d+\.?\d*)\s*[°]?\s*([NSns])?', line.split(':',1)[-1])
            if m:
                lat = float(m.group(1))
                if m.group(2) and m.group(2).upper()=='S': lat = -lat
        elif re.search(r'Longitude\s*:', line):
            m = re.search(r'([-+]?\d+\.?\d*)\s*[°]?\s*([EWew])?', line.split(':',1)[-1])
            if m:
                lon = float(m.group(1))
                if m.group(2) and m.group(2).upper()=='W': lon = -lon
        elif re.search(r'\bRA\s*:', line):
            m = re.search(r'([-+]?\d+\.?\d*)', line.split(':',1)[-1])
            if m: ra = float(m.group(1))
        elif re.search(r'\bDec\s*:', line):
            m = re.search(r'([-+]?\d+\.?\d*)', line.split(':',1)[-1])
            if m: dec = float(m.group(1))
    return lat, lon, ra, dec

def run_solver(img_path, filename):
    if not _solve_lock.acquire(blocking=False):
        print("⚠ Solver already running"); return
    try:
        write_gps({"status": "solving", "image": filename})
        print(f"\n🔭 Solving: {filename}")
        now      = datetime(2026, 3, 10, 20, 20, 0, tzinfo=timezone.utc)  # UTC fixe pour etoiles.jpeg
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        cmd = [sys.executable, str(SOLVER), img_path, date_str, time_str]
        if USE_MANUAL:
            cmd += [str(TILT_MANUAL), str(AZIMUTH_MANUAL)]
        t0 = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            write_gps({"status":"error","error":"timeout","image":filename}); return
        except Exception as e:
            write_gps({"status":"error","error":str(e),"image":filename}); return
        solve_time = round(time.time()-t0, 2)
        output = result.stdout
        print(output[-1000:])
        lat, lon, ra, dec = parse_solver_output(output)
        if lat is None or lon is None:
            write_gps({"status":"error","error":"solve-field could not identify stars","image":filename,"log":output[-500:]})
            print("❌ No position found"); return
        ts = now.isoformat()
        print(f"✅ Position: {lat:.5f}°N  {lon:.5f}°E  ({solve_time}s)")
        write_gps({"status":"predicted","lat":lat,"lon":lon,"ra_deg":ra,"dec_deg":dec,
                   "image":filename,"solve_time_s":solve_time,"timestamp":ts,
                   "source":"stellar","tilt":TILT_MANUAL,"azimuth":AZIMUTH_MANUAL})
    finally:
        _solve_lock.release()

def _save_and_solve(img_bytes, filename):
    save_path = str(SAVE_DIR / filename)
    with open(save_path, "wb") as f: f.write(img_bytes)
    print(f"\n📥 Saved: {filename} ({len(img_bytes)} bytes)")
    threading.Thread(target=run_solver, args=(save_path, filename), daemon=True).start()

@app.route("/upload", methods=["POST"])
def upload():
    if "image" not in request.files:
        return jsonify({"success":False,"error":"No image field"}), 400
    f = request.files["image"]
    _save_and_solve(f.read(), f.filename or "frame.jpg")
    return jsonify({"success":True,"message":f"Received {f.filename}, solving..."})

@app.route("/frame", methods=["POST"])
def frame():
    data = request.get_json(force=True, silent=True) or {}
    img_b64 = data.get("image_b64","")
    if not img_b64:
        return jsonify({"success":False,"error":"No image_b64"}), 400
    meta = data.get("metadata",{})
    filename = data.get("filename") or meta.get("frame_id","") or f"frame_{int(time.time())}"
    if not filename.endswith((".jpg",".jpeg",".png")): filename += ".jpg"
    try:
        img_bytes = base64.b64decode(img_b64)
    except Exception as e:
        return jsonify({"success":False,"error":f"base64 error: {e}"}), 400
    _save_and_solve(img_bytes, filename)
    return jsonify({"success":True,"message":f"Received {filename}, solving..."})

@app.route("/gps_status.json", methods=["GET"])
def gps_status():
    try:
        with open(str(GPS_STATUS)) as f: data = json.load(f)
        resp = jsonify(data)
        resp.headers["Cache-Control"] = "no-store"
        return resp
    except Exception:
        return jsonify({"status":"idle"})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok":True,"solver":str(SOLVER),"solver_exists":SOLVER.exists()})

@app.route("/api/cache_status", methods=["GET"])
def cache_status():
    return jsonify({"ready":True,"source":"stellar"})

@app.route("/api/precollect", methods=["POST"])
@app.route("/api/set_mission", methods=["POST"])
def noop():
    return jsonify({"ok":True,"source":"stellar"})

if __name__ == "__main__":
    print("="*60)
    print("🌟  NAVERA Stellar Receiver — port 5001")
    print(f"   Solver  : {SOLVER}")
    print(f"   Exists  : {SOLVER.exists()}")
    print(f"   Images  : {SAVE_DIR}")
    print(f"   GPS out : {GPS_STATUS}")
    print(f"   Mode    : MANUAL tilt={TILT_MANUAL}° az={AZIMUTH_MANUAL}°")
    print("="*60)
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
