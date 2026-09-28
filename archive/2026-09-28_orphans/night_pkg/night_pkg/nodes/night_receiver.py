#!/usr/bin/env python3
"""
night_receiver.py  —  NAVERA Night Receiver  (port 5001)
========================================================
Flask server — STHN-based night localization.

Compatible with navera.html which polls:
  POST /frame                    — receive drone frame + telemetry
  GET  /flight_log.csv           — CSV log polled every 1 s by frontend
  GET  /gps_status.json          — GPS/localization status polled every 0.5 s
  GET  /position                 — latest fix { lat, lon, conf, source }
  POST /api/set_mission          — configure mission parameters
  POST /api/precollect           — tile pre-collection (stub for night mode)
  GET  /api/precollect_progress  — precollect progress (stub)
  GET  /api/cache_status         — cache ready status
  GET  /api/status               — health check

Real-time flow:
  PC-Nour ───frame (lat,lon OR None)───▶  /frame
                                          │
                                  ┌───────┴────────┐
                          gps_valid?              !gps_valid?
                                  │                      │
                                  ▼                      ▼
                        emit "active" status      run STHN inference,
                        with raw (lat,lon)        emit "predicted" with
                                                  STHN (lat,lon,conf)
                                          │
                                          ▼
                                navera.html (polls /flight_log.csv
                                & /gps_status.json) animates drone
                                to the right position.

Run:
  cd ~/isaac_ros_common/night_pkg
  python3 night_pkg/night_receiver.py \
      --sthn-dir  ~/Desktop/pfeAutonomTest/STHN \
      --weights   ~/Desktop/pfeAutonomTest/STHN/weights/model_best.pth \
      --mbtiles   ~/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles
"""

import argparse
import base64
import csv
import io
import json
import logging
import math
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import cv2
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

# ─── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("night_receiver")

# ─── App ────────────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# ─── Global state ───────────────────────────────────────────────────────────────
localizer = None
_localizer_lock = threading.Lock()

latest_fix = {
    "lat": None, "lon": None, "conf": 0.0,
    "source": "night_sthn", "ts": 0,
    "dt_ms": 0, "rms_px": 0,
}
_fix_lock = threading.Lock()

mission_cfg = {}
_pending_frame = None
_frame_lock = threading.Lock()

_running = False
_worker_thread = None

# ─── Flight log (mirrors vision_pkg receiver CSV so navera.html can parse it) ──
# Columns: frame_id, timestamp, image_file, lat, lon, alt_m, heading_deg,
#          speed_mps, gps_valid, predicted_lat, predicted_lon, match_score
_flight_log_rows = []
_flight_log_lock = threading.Lock()
_flight_log_header = [
    "frame_id", "timestamp", "image_file",
    "lat", "lon", "alt_m", "heading_deg", "speed_mps",
    "gps_valid", "predicted_lat", "predicted_lon", "match_score",
]

# ─── GPS / mission status (what navera.html polls every 500 ms) ─────────────────
_gps_status = {
    "status": "idle",
    "mission_started": False,
    "lat": None,
    "lon": None,
    "last_valid_lat": None,
    "last_valid_lon": None,
    "frame_id": 0,
    "search_radius_m": 300,
    "score": 0.0,
    "total_ms": 0,
    "dataset_ms": 0,
    "dataset_images": 0,
    "match": "",
    "error": "",
}
_gps_status_lock = threading.Lock()
_last_valid_lat = None
_last_valid_lon = None

# ─── Precollect stub state (night mode skips precollection) ─────────────────────
_precollect_state = {"running": False, "done": 1, "total": 1,
                     "pct": 100, "success": True, "files": 1, "error": ""}


# ═════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _optional_float(value):
    """CSV / JSON value → float, or None for empty/'None'/'nan'/'null'."""
    if value is None:
        return None
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"", "none", "nan", "null"}:
            return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _csv_text():
    """Render the in-memory flight log as CSV text."""
    with _flight_log_lock:
        rows = list(_flight_log_rows)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=_flight_log_header, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


def _append_flight_row(frame_id, ts, image_file,
                       lat, lon, alt_m, hdg, spd,
                       gps_valid, pred_lat, pred_lon, score):
    """Append one row.  ALWAYS provide pred_lat/pred_lon (real or STHN) so
    navera.html can animate the drone even on GPS-loss frames."""
    row = {
        "frame_id":     frame_id,
        "timestamp":    ts,
        "image_file":   image_file or "",
        "lat":          f"{lat:.7f}"  if lat  is not None else "None",
        "lon":          f"{lon:.7f}"  if lon  is not None else "None",
        "alt_m":        alt_m if alt_m is not None else 400,
        "heading_deg":  hdg   if hdg   is not None else 0,
        "speed_mps":    spd   if spd   is not None else 0,
        "gps_valid":    "True" if gps_valid else "False",
        "predicted_lat": f"{pred_lat:.7f}" if pred_lat is not None else "None",
        "predicted_lon": f"{pred_lon:.7f}" if pred_lon is not None else "None",
        "match_score":  float(score) if score is not None else 0.0,
    }
    with _flight_log_lock:
        _flight_log_rows.append(row)


# ─── Lazy-load localizer ────────────────────────────────────────────────────────

def _get_localizer(sthn_dir, weights, mbtiles, zoom=17):
    """Build the NightLocalizer on first request (so flask starts fast)."""
    global localizer
    if localizer is not None:
        return localizer
    with _localizer_lock:
        if localizer is not None:
            return localizer
        logger.info("Loading NightLocalizer (first request) …")
        sys.path.insert(0, str(Path(__file__).parent))
        from night_localizer import NightLocalizer
        localizer = NightLocalizer(
            sthn_dir=sthn_dir,
            weights=weights,
            mbtiles=mbtiles,
            zoom=zoom,
        )
        logger.info("NightLocalizer ready ✓")
    return localizer


# ═════════════════════════════════════════════════════════════════════════════
#  Background inference worker
# ═════════════════════════════════════════════════════════════════════════════

def _inference_worker(args_ns):
    """One-shot pulls _pending_frame, runs STHN if needed, updates state."""
    global _running, _pending_frame, _last_valid_lat, _last_valid_lon
    logger.info("Inference worker started")
    loc = _get_localizer(args_ns.sthn_dir, args_ns.weights,
                         args_ns.mbtiles, args_ns.zoom)

    while _running:
        frame_data = None
        with _frame_lock:
            if _pending_frame is not None:
                frame_data = _pending_frame
                _pending_frame = None

        if frame_data is None:
            time.sleep(0.05)
            continue

        img_bgr, metadata = frame_data
        frame_id  = metadata.get("frame_id", 0)
        prior_lat = _optional_float(metadata.get("lat"))
        prior_lon = _optional_float(metadata.get("lon"))
        gps_valid = bool(metadata.get("gps_valid", False)) \
                    and (prior_lat is not None) and (prior_lon is not None)
        alt_m     = metadata.get("altitude_m", 400)
        hdg       = metadata.get("heading_deg", 0)
        spd       = metadata.get("speed_mps", 0)
        ts        = metadata.get("timestamp", time.strftime("%H:%M:%S"))
        img_name  = metadata.get("image_file") \
                    or f"frame_{str(frame_id).zfill(4)}.jpg"

        # Update mission flags
        with _gps_status_lock:
            _gps_status["mission_started"] = True
            _gps_status["frame_id"]        = frame_id

        # Keep track of the last KNOWN-GOOD anchor for chained DR
        if gps_valid:
            _last_valid_lat = prior_lat
            _last_valid_lon = prior_lon

        # ───────────────────── CASE A: GPS valid ────────────────────────
        # Frame already has a known lat/lon — just publish it.  No STHN.
        if gps_valid:
            pred_lat, pred_lon = prior_lat, prior_lon
            score              = 1.0   # GPS = perfect confidence

            with _fix_lock:
                latest_fix.update({
                    "lat":    pred_lat,
                    "lon":    pred_lon,
                    "conf":   score,
                    "source": "gps",
                    "ts":     time.time(),
                    "dt_ms":  0.0,
                    "rms_px": 0.0,
                })
            with _gps_status_lock:
                _gps_status.update({
                    "status":          "active",   # navera.html: GPS OK
                    "lat":             pred_lat,
                    "lon":             pred_lon,
                    "last_valid_lat":  _last_valid_lat,
                    "last_valid_lon":  _last_valid_lon,
                    "score":           score,
                    "total_ms":        0,
                    "dataset_ms":      0,
                    "dataset_images":  1,
                    "match":           f"gps_frame_{frame_id}",
                    "search_radius_m": 0,
                    "error":           "",
                })
            logger.info(
                f"📍 GPS  #{frame_id}: ({pred_lat:.6f}, {pred_lon:.6f})")
            _append_flight_row(
                frame_id, ts, img_name,
                lat=prior_lat, lon=prior_lon,
                alt_m=alt_m, hdg=hdg, spd=spd,
                gps_valid=True,
                pred_lat=pred_lat, pred_lon=pred_lon,
                score=score,
            )
            continue

        # ───────────────────── CASE B: GPS lost — STHN ───────────────────
        # No (lat,lon) on this frame.  Use the last valid GPS point as
        # the anchor for the satellite reference patch, then run STHN.
        anchor_lat = _last_valid_lat
        anchor_lon = _last_valid_lon

        if anchor_lat is None or anchor_lon is None:
            # No anchor at all yet — cannot fetch tiles.  Skip.
            logger.warning(
                f"Frame {frame_id}: no GPS prior or last-known position, "
                f"cannot run STHN — skipped")
            with _gps_status_lock:
                _gps_status["status"] = "searching"
                _gps_status["error"]  = "No anchor — waiting for first GPS fix"
            _append_flight_row(
                frame_id, ts, img_name,
                lat=None, lon=None,
                alt_m=alt_m, hdg=hdg, spd=spd,
                gps_valid=False,
                pred_lat=None, pred_lon=None,
                score=0.0,
            )
            continue

        # First publish the "searching" state — navera.html will draw the
        # search disc and the GPS-LOST banner.
        with _gps_status_lock:
            _gps_status.update({
                "status":          "searching",
                "lat":             anchor_lat,
                "lon":             anchor_lon,
                "last_valid_lat":  anchor_lat,
                "last_valid_lon":  anchor_lon,
                "search_radius_m": 300,
                "error":           "",
            })

        # Run STHN
        result = loc.localize(img_bgr, anchor_lat, anchor_lon)

        if result.get("success"):
            pred_lat = result["lat"]
            pred_lon = result["lon"]
            score    = float(result.get("conf", 0.0))
            dt_ms    = float(result.get("dt_ms", 0.0))
            rms_px   = float(result.get("rms_px", 0.0))

            # Chained dead-reckoning: the STHN prediction becomes the new
            # anchor for the *next* GPS-loss frame.
            _last_valid_lat = pred_lat
            _last_valid_lon = pred_lon

            with _fix_lock:
                latest_fix.update({
                    "lat":    pred_lat,
                    "lon":    pred_lon,
                    "conf":   score,
                    "source": "night_sthn",
                    "ts":     time.time(),
                    "dt_ms":  dt_ms,
                    "rms_px": rms_px,
                })
            with _gps_status_lock:
                _gps_status.update({
                    "status":          "predicted",   # navera.html: STHN OK
                    "lat":             pred_lat,
                    "lon":             pred_lon,
                    "last_valid_lat":  anchor_lat,
                    "last_valid_lon":  anchor_lon,
                    "score":           score,
                    "total_ms":        dt_ms,
                    "dataset_ms":      dt_ms,
                    "dataset_images":  1,
                    "match":           f"night_sthn_frame_{frame_id}",
                    "search_radius_m": 300,
                    "error":           "",
                })
            logger.info(
                f"🌙 STHN #{frame_id}: ({pred_lat:.6f}, {pred_lon:.6f}) "
                f"conf={score:.2f}  {dt_ms:.0f}ms")
            _append_flight_row(
                frame_id, ts, img_name,
                lat=None, lon=None,     # GPS column stays empty
                alt_m=alt_m, hdg=hdg, spd=spd,
                gps_valid=False,
                pred_lat=pred_lat, pred_lon=pred_lon,
                score=score,
            )
        else:
            logger.warning(
                f"STHN failed on frame {frame_id} — falling back to anchor")
            with _gps_status_lock:
                _gps_status.update({
                    "status": "predicted",
                    "error":  "",
                    "score":  0.0,
                    "match":  f"fallback_anchor_{frame_id}",
                    "lat":    anchor_lat,
                    "lon":    anchor_lon,
                })
            _append_flight_row(
                frame_id, ts, img_name,
                lat=None, lon=None,
                alt_m=alt_m, hdg=hdg, spd=spd,
                gps_valid=False,
                pred_lat=anchor_lat, pred_lon=anchor_lon,
                score=0.0,
            )



# ─── Dead-reckoning helper (PATCHED) ──────────────────────────────────────────
def _dead_reckon(lat, lon, heading_deg, speed_mps, dt_s=10.0):
    """Advance (lat,lon) by speed*dt along heading. Returns (lat,lon)."""
    import math as _m
    if lat is None or lon is None:
        return lat, lon
    dist = float(speed_mps or 5.0) * float(dt_s or 10.0)   # metres
    hdg  = _m.radians(float(heading_deg or 0.0))
    R    = 6371000.0
    dlat = (dist * _m.cos(hdg)) / R * (180.0 / _m.pi)
    dlon = (dist * _m.sin(hdg)) / (R * _m.cos(_m.radians(lat))) * (180.0 / _m.pi)
    return lat + dlat, lon + dlon


# ═════════════════════════════════════════════════════════════════════════════
#  Routes
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/frame", methods=["POST"])
def receive_frame():
    """
    Accepts both formats:

    1) navera.html / pc_nour_sender.py:
        { "metadata": {...}, "image_b64": "..." }

    2) Legacy flat:
        { "image": "...", "lat":..., "lon":..., "ts":... }
    """
    global _pending_frame

    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify({"error": f"bad JSON: {e}"}), 400

    img_b64 = data.get("image_b64") or data.get("image")
    if not img_b64:
        return jsonify({"error": "missing image_b64 or image field"}), 400

    # ── Decode image ──
    try:
        img_bytes = base64.b64decode(img_b64)
        arr       = np.frombuffer(img_bytes, dtype=np.uint8)
        img_bgr   = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            raise ValueError("cv2.imdecode returned None")
    except Exception as e:
        return jsonify({"error": f"image decode failed: {e}"}), 400

    # ── Extract metadata (both formats) ──
    meta = data.get("metadata")
    if not meta:
        meta = {
            "frame_id":    data.get("frame_id", 0),
            "lat":         data.get("lat"),
            "lon":         data.get("lon"),
            "gps_valid":   data.get("gps_valid",
                                    data.get("lat") is not None
                                 and data.get("lon") is not None),
            "altitude_m":  data.get("alt", 400),
            "heading_deg": data.get("heading_deg", 0),
            "speed_mps":   data.get("speed_mps", 0),
            "timestamp":   data.get("ts", time.strftime("%H:%M:%S")),
            "image_file":  data.get("image_file"),
        }

    # Queue for background worker (drop oldest — real-time, not buffered)
    with _frame_lock:
        _pending_frame = (img_bgr, meta)

    return jsonify({"queued":   True,
                    "frame_id": meta.get("frame_id", 0)})


@app.route("/flight_log.csv", methods=["GET"])
def flight_log_csv():
    """Polled by navera.html every 1 s."""
    text = _csv_text()
    return Response(text, mimetype="text/csv",
                    headers={"Cache-Control": "no-cache"})


@app.route("/gps_status.json", methods=["GET"])
def gps_status_json():
    """Polled by navera.html every 0.5 s."""
    with _gps_status_lock:
        status = dict(_gps_status)
    return jsonify(status)


@app.route("/position", methods=["GET"])
def get_position():
    with _fix_lock:
        fix = dict(latest_fix)
    if fix["lat"] is None:
        return jsonify({"available": False}), 204
    return jsonify({
        "available": True,
        "lat":    fix["lat"],
        "lon":    fix["lon"],
        "conf":   fix["conf"],
        "source": fix["source"],
        "ts":     fix["ts"],
        "dt_ms":  fix.get("dt_ms", 0),
        "rms_px": fix.get("rms_px", 0),
    })


@app.route("/api/set_mission", methods=["POST"])
def set_mission():
    global mission_cfg
    data = request.get_json(force=True)
    mission_cfg = data
    # Reset the flight log + state so a fresh mission starts clean.
    global _last_valid_lat, _last_valid_lon
    _last_valid_lat = _last_valid_lon = None
    with _flight_log_lock:
        _flight_log_rows.clear()
    with _gps_status_lock:
        _gps_status.update({
            "status":         "idle",
            "mission_started": True,
            "lat":            None,
            "lon":            None,
            "last_valid_lat": None,
            "last_valid_lon": None,
            "frame_id":       0,
            "score":          0.0,
            "match":          "",
            "error":          "",
        })
    with _fix_lock:
        latest_fix.update({"lat": None, "lon": None,
                           "conf": 0.0, "ts": 0})
    logger.info(f"Mission config received → flight log cleared: "
                f"{list(data.keys())}")
    return jsonify({"ok": True})


@app.route("/api/precollect", methods=["POST"])
def precollect():
    """Night mode skips precollection — STHN reads tiles on demand."""
    _precollect_state.update({"running": False, "done": 1, "total": 1,
                              "pct": 100, "success": True, "files": 1})
    logger.info("Precollect requested (night mode — instant, no-op)")
    return jsonify({"success": True, "status": "started",
                    "message": "Night mode: STHN uses live MBTiles — "
                               "no pre-collection needed"})


@app.route("/api/precollect_progress", methods=["GET"])
def precollect_progress():
    return jsonify({"running": False, "done": 1, "total": 1,
                    "pct": 100, "success": True, "files": 1})


@app.route("/api/cache_status", methods=["GET"])
def cache_status():
    return jsonify({"ready": True, "running": False,
                    "images": 1, "mode": "night_sthn",
                    "message": "STHN live MBTiles — always ready"})


@app.route("/api/localize", methods=["POST"])
def api_localize():
    """Synchronous localize endpoint (for direct testing)."""
    data = request.get_json(force=True)
    img_b64 = data.get("image_b64") or data.get("image")
    if not img_b64:
        return jsonify({"error": "missing image"}), 400

    img_bytes = base64.b64decode(img_b64)
    arr     = np.frombuffer(img_bytes, dtype=np.uint8)
    img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        return jsonify({"error": "decode failed"}), 400

    prior_lat = _optional_float(data.get("lat")) or 35.8288
    prior_lon = _optional_float(data.get("lon")) or 10.6360

    args_ns = app.config["ARGS"]
    loc = _get_localizer(args_ns.sthn_dir, args_ns.weights,
                         args_ns.mbtiles, args_ns.zoom)
    result = loc.localize(img_bgr, prior_lat, prior_lon)
    return jsonify(result)


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify({
        "service":        "night_receiver",
        "version":        "1.2.0",
        "mode":           "STHN_night",
        "model_loaded":   localizer is not None,
        "worker_running": _running,
        "log_rows":       len(_flight_log_rows),
        "last_fix_age_s": (time.time() - latest_fix["ts"])
                          if latest_fix["ts"] else None,
    })


# ═════════════════════════════════════════════════════════════════════════════
#  Main
# ═════════════════════════════════════════════════════════════════════════════

def main():
    global _running, _worker_thread

    parser = argparse.ArgumentParser(
        description="NAVERA Night Receiver — STHN port 5001")
    parser.add_argument("--sthn-dir",
        default=os.path.expanduser("~/Desktop/pfeAutonomTest/STHN"),
        help="Path to cloned arplaboratory/STHN repo")
    parser.add_argument("--weights",
        default=os.path.expanduser(
            "~/Desktop/pfeAutonomTest/STHN/weights/model_best.pth"),
        help="Path to STHN local_pipeline checkpoint (.pth or .safetensors)")
    parser.add_argument("--mbtiles",
        default=os.path.expanduser(
            "~/isaac_ros_common/vision_pkg/vision_pkg/dataset/"
            "sousse_satellite.mbtiles"),
        help="Path to sousse_satellite.mbtiles")
    parser.add_argument("--zoom",       type=int, default=17)
    parser.add_argument("--port",       type=int, default=5001)
    parser.add_argument("--host",       default="0.0.0.0")
    parser.add_argument("--no-worker",  action="store_true",
        help="Disable background inference worker (synchronous mode)")
    args = parser.parse_args()

    # Validate paths
    for attr, label in [("sthn_dir", "STHN dir"),
                        ("weights",  "Weights"),
                        ("mbtiles",  "MBTiles")]:
        p = getattr(args, attr)
        if not Path(p).exists():
            logger.error(f"{label} not found: {p}")
            sys.exit(1)

    app.config["ARGS"] = args

    if not args.no_worker:
        _running = True
        _worker_thread = threading.Thread(
            target=_inference_worker, args=(args,), daemon=True)
        _worker_thread.start()
        logger.info("Background inference worker started")

    logger.info("=" * 64)
    logger.info(f"🌙 Night Receiver  →  http://{args.host}:{args.port}")
    logger.info(f"   STHN dir : {args.sthn_dir}")
    logger.info(f"   Weights  : {args.weights}")
    logger.info(f"   MBTiles  : {args.mbtiles}  zoom={args.zoom}")
    logger.info("=" * 64)

    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
