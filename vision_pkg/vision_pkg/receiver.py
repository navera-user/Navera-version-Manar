#!/usr/bin/env python3
"""
receiver.py ── FINAL v7 — GPU-Optimized for Jetson Orin Nano
Improvements:
  - Non-blocking async matching (never blocks GPS frames)
  - GPU-accelerated visual place recognition (DINOv2/NetVLAD)
  - Efficient descriptor extraction with batching
  - Timeout-based matching to prevent hangs
"""
import base64
import csv
import json
import math
import os
import queue
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# ── Paths ─────────────────────────────────────────────────────────────────────
PKG_DIR          = Path(__file__).resolve().parent
BASE_PATH        = PKG_DIR / "dataset"
MBTILES_PATH     = BASE_PATH / "sousse_satellite.mbtiles"
FRAMES_GPS_DIR   = BASE_PATH / "frames_gps"
FRAMES_NOGPS_DIR = BASE_PATH / "frames_nogps"
CSV_PATH         = BASE_PATH / "flight_log.csv"
GPS_STATUS_PATH  = BASE_PATH / "gps_status.json"
FIRST_FRAME_FLAG = BASE_PATH / ".first_frame_received"
FALLBACK_DATASET = BASE_PATH / "fallback_dataset"
FALLBACK_IMAGES  = FALLBACK_DATASET / "images"

FRAMES_GPS_DIR.mkdir(parents=True, exist_ok=True)
FRAMES_NOGPS_DIR.mkdir(parents=True, exist_ok=True)
FALLBACK_DATASET.mkdir(parents=True, exist_ok=True)
FALLBACK_IMAGES.mkdir(parents=True, exist_ok=True)

R_EARTH = 6_371_000.0

# GPU configuration
GPU_ENABLED = True
MATCH_TIMEOUT_SEC = 5.0  # Never block GPS frames
DESCRIPTOR_QUEUE_SIZE = 50  # Async descriptor extraction queue

# ══════════════════════════════════════════════════════════════════════════════
#  WAYPOINT NAVIGATOR
# ══════════════════════════════════════════════════════════════════════════════
def haversine_dist(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

class WaypointNavigator:
    def __init__(self):
        self.waypoints    = []
        self.current_idx  = 0
        self.mission_mode = 'known'
        self.vehicle      = 'drone'

    def load(self, config_path: str):
        try:
            with open(config_path) as f:
                cfg = json.load(f)
            wps = cfg.get('waypoints', [])
            self.waypoints    = [{'lat': w['lat'], 'lon': w.get('lon', w.get('lng', 0))} for w in wps]
            self.mission_mode = cfg.get('mission_mode', 'known')
            self.vehicle      = cfg.get('vehicle', 'drone')
            self.current_idx  = 0
            print(f"  [Navigator] {len(self.waypoints)} WPs | mode={self.mission_mode} | vehicle={self.vehicle}")
        except Exception as e:
            print(f"  [Navigator] Pas de config: {e}")

    def update_from_gps(self, lat: float, lon: float):
        while self.current_idx < len(self.waypoints) - 1:
            wp   = self.waypoints[self.current_idx]
            dist = haversine_dist(lat, lon, wp['lat'], wp['lon'])
            if dist < 150:
                self.current_idx += 1
                print(f"  [Navigator] WP{self.current_idx-1} atteint → WP{self.current_idx}")
            else:
                break

    def heading_to_next(self, lat: float, lon: float) -> float:
        if not self.waypoints or self.current_idx >= len(self.waypoints):
            return 0.0
        wp   = self.waypoints[self.current_idx]
        dlon = math.radians(wp['lon'] - lon)
        x    = math.sin(dlon) * math.cos(math.radians(wp['lat']))
        y    = math.cos(math.radians(lat))*math.sin(math.radians(wp['lat'])) - \
               math.sin(math.radians(lat))*math.cos(math.radians(wp['lat']))*math.cos(dlon)
        return (math.degrees(math.atan2(x, y)) + 360) % 360

    @property
    def target_wp(self):
        if not self.waypoints or self.current_idx >= len(self.waypoints): return None
        return self.waypoints[self.current_idx]

navigator = WaypointNavigator()

# ── Shared state ──────────────────────────────────────────────────────────────
_state_lock    = threading.Lock()
_gps_active    = True
_last_lat      = 0.0
_last_lon      = 0.0
_pred_lat      = 0.0
_pred_lon      = 0.0
_match_score   = 0.0
_match_file    = ""
_anchor_lat    = 0.0
_anchor_lon    = 0.0
_match_ms      = 0.0
_frame_count   = 0
_match_count   = 0
_matching_busy = False
_search_radius = 800
_dataset_ready = False
_active_dataset = None
_precollect_running = False
_precollect_progress = 0
_precollect_total = 0
_precollect_success = None
first_frame_received = FIRST_FRAME_FLAG.exists()

# ── Localizer init ────────────────────────────────────────────────────────────
def _find_dataset_dir():
    """Find a dataset dir that has coords.json + descriptors.npy"""
    candidates = []
    # Check fallback_dataset first (priority)
    if (FALLBACK_DATASET / "coords.json").exists():
        candidates.insert(0, str(FALLBACK_DATASET))
    # Then check home dir fallback
    home_fallback = Path.home() / "Bureau/pfeReserve/ros2_ws/src/vision_pkg/vision_pkg/dataset/fallback_dataset"
    if (home_fallback / "coords.json").exists():
        candidates.append(str(home_fallback))
    return candidates[0] if candidates else None

def _init_localizer():
    global _dataset_ready, _active_dataset
    # Load waypoints config
    config_path = BASE_PATH / "mission_config.json"
    if config_path.exists():
        navigator.load(str(config_path))

    # Try to initialize GPU models
    try:
        import sys
        sys.path.insert(0, str(PKG_DIR))
        from gps_localizer import set_model_type, DEVICE, MODEL_TYPE
        
        if GPU_ENABLED and DEVICE == "cuda":
            print(f"  [Localizer] GPU available — using {MODEL_TYPE} for visual localization")
            try:
                set_model_type("dinov2")
                print("  [Localizer] ✅ DINOv2 loaded (GPU-accelerated)")
            except Exception as e:
                print(f"  [Localizer] ⚠ DINOv2 failed: {e}, trying NetVLAD...")
                try:
                    set_model_type("netvlad")
                    print("  [Localizer] ✅ NetVLAD loaded (GPU-accelerated)")
                except:
                    print("  [Localizer] ⚠ GPU models unavailable, using MobileNetV3")
        else:
            print(f"  [Localizer] {DEVICE.upper()} only — using CPU-optimized inference")
    except Exception as e:
        print(f"  [Localizer] GPU init warning: {e}")

    dataset_dir = _find_dataset_dir()
    if dataset_dir is None:
        print("  [Localizer] No dataset with coords.json found — visual matching disabled")
        print("  [Localizer] GPS frames will be saved and index built automatically")
        return

    print(f"  [Localizer] Dataset found: {dataset_dir}")
    # Auto-generate coords.json if missing
    coords_file = Path(dataset_dir) / "coords.json"
    images_dir = Path(dataset_dir) / "images"
    if not coords_file.exists() and images_dir.exists():
        print("  [Localizer] Auto-generating coords.json from image filenames...")
        import json as _json
        coords = []
        for img in sorted(images_dir.glob("*.jpg")):
            parts = img.stem.split("__")
            if len(parts) == 2:
                try:
                    lat, lon = map(float, parts[1].split("_"))
                    coords.append({"file": f"images/{img.name}", "lat": lat, "lon": lon})
                except: pass
        with open(str(coords_file), "w") as f:
            _json.dump(coords, f)
        print(f"  [Localizer] ✅ coords.json generated: {len(coords)} entries")
    desc_file = Path(dataset_dir) / "descriptors.npy"
    if not desc_file.exists():
        print(f"  [Localizer] No descriptors.npy — building index...")
        _build_index_async(dataset_dir)
    else:
        print(f"  [Localizer] descriptors.npy found — ready for matching ✅")
        with _state_lock:
            _dataset_ready  = True
            _active_dataset = dataset_dir

def _build_index_async(dataset_dir: str):
    def _do_build():
        global _dataset_ready, _active_dataset
        try:
            import sys
            sys.path.insert(0, str(PKG_DIR))
            from gps_localizer import build_index, BATCH_SIZE
            
            print(f"  [Localizer] Building index for {dataset_dir} (batch_size={BATCH_SIZE})...")
            build_index(dataset_dir, batch_size=BATCH_SIZE)
            with _state_lock:
                _dataset_ready  = True
                _active_dataset = dataset_dir
            print(f"  [Localizer] Index built ✅ — visual matching active")
        except Exception as e:
            print(f"  [Localizer] build_index ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    threading.Thread(target=_do_build, daemon=True, name="GPUIndexBuilder").start()

# ── Dead reckoning ────────────────────────────────────────────────────────────
def dead_reckon(lat, lon, heading_deg, speed_mps, delta_t):
    hdg  = math.radians(heading_deg)
    dlat = (speed_mps * math.cos(hdg) * delta_t) / R_EARTH
    dlon = (speed_mps * math.sin(hdg) * delta_t) / \
           (R_EARTH * math.cos(math.radians(lat)) + 1e-9)
    return lat + math.degrees(dlat), lon + math.degrees(dlon)

# ── GPS status JSON ───────────────────────────────────────────────────────────
def _atomic_write(data):
    try:
        tmp = str(GPS_STATUS_PATH) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, str(GPS_STATUS_PATH))
    except Exception:
        pass

def _write_status_active(lat, lon, frame_id=0):
    _atomic_write({"status": "active", "timestamp": time.time(),
                   "lat": lat, "lon": lon, "frame_id": frame_id})

def _write_status_searching(ref_lat, ref_lon, radius_m, frame_id=0):
    _atomic_write({"status": "searching", "timestamp": time.time(),
                   "lat": ref_lat, "lon": ref_lon,
                   "search_radius_m": radius_m, "frame_id": frame_id,
                   "message": f"GPS LOST — Visual localization active (r={radius_m:.0f}m)"})

def _write_status_predicted(pred_lat, pred_lon, score, match_file,
                             ref_lat, ref_lon, radius_m, total_ms, frame_id=0):
    _atomic_write({"status": "predicted", "timestamp": time.time(),
                   "lat": pred_lat, "lon": pred_lon,
                   "score": score, "match": match_file,
                   "search_radius_m": radius_m,
                   "last_valid_lat": ref_lat, "last_valid_lon": ref_lon,
                   "frame_id": frame_id, "total_ms": total_ms})

# ── Background visual matching ────────────────────────────────────────────────
_match_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="GPUMatch")

def _do_match_with_timeout(img_bytes: bytes, frame_id: int,
                          anchor_lat: float, anchor_lon: float,
                          ref_lat: float, ref_lon: float, radius_m: float,
                          timeout_sec: float = MATCH_TIMEOUT_SEC):
    """
    GPU-accelerated async matching with timeout.
    Never blocks frame reception.
    Updates navigator when visual match completes.
    """
    global _pred_lat, _pred_lon, _match_score, _match_file
    global _match_ms, _match_count, _matching_busy

    def _match_task():
        with _state_lock:
            ready   = _dataset_ready
            dset    = _active_dataset

        if not ready or dset is None:
            print(f"  [#{frame_id:04d}] ⚠ Localizer not ready — keeping DR")
            with _state_lock:
                _matching_busy = False
            return None

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
                tf.write(img_bytes)
                tmp_path = tf.name

            import sys
            sys.path.insert(0, str(PKG_DIR))
            from gps_localizer import match

            t0 = time.perf_counter()
            try:
                result = match(
                    query_img   = tmp_path,
                    dataset_dir = dset,
                    anchor_lat  = anchor_lat,
                    anchor_lon  = anchor_lon,
                    top_k       = 5,  # Get top-5 for robustness
                    timeout_sec = timeout_sec
                )
            except Exception as match_err:
                print(f"  [#{frame_id:04d}] ⚠ match() exception: {match_err}")
                result = None
            
            elapsed = (time.perf_counter() - t0) * 1000

            with _state_lock:
                _match_ms = round(elapsed, 1)

            if result is not None:
                best = result.get("best", result)
                pred_lat = best["lat"]
                pred_lon = best["lon"]
                score    = best["score"]
                
                with _state_lock:
                    _pred_lat    = pred_lat
                    _pred_lon    = pred_lon
                    _match_score = score
                    _match_file  = str(best.get("index", ""))
                    _match_count += 1
                    # Update navigator with visual match result
                    if navigator.target_wp:
                        try:
                            navigator.update_from_gps(pred_lat, pred_lon)
                        except Exception as nav_err:
                            print(f"  [#{frame_id:04d}] ⚠ Navigator update error: {nav_err}")
                
                print(f"  [#{frame_id:04d}] ✅ VISUAL MATCH lat={pred_lat:.5f} lon={pred_lon:.5f} "
                      f"score={score:.3f} {elapsed:.0f}ms → CONTINUING TO WP")
                _write_status_predicted(pred_lat, pred_lon, score, str(best.get("index","")),
                                       ref_lat, ref_lon, radius_m, elapsed, frame_id)
                return result
            else:
                print(f"  [#{frame_id:04d}] ❌ NO VISUAL MATCH {elapsed:.0f}ms — dead reckoning")
                # Write failed match result back to JSON so frontend knows DR is final
                with _state_lock:
                    cur_dr_lat = _pred_lat
                    cur_dr_lon = _pred_lon
                _write_status_predicted(cur_dr_lat, cur_dr_lon, 0.0, "dead_reckoning_final",
                                       ref_lat, ref_lon, radius_m, elapsed, frame_id)
                return None

        except Exception as e:
            print(f"  [#{frame_id:04d}] ⚠ match() ERROR: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except:
                    pass
            with _state_lock:
                _matching_busy = False

    future = _match_executor.submit(_match_task)
    try:
        result = future.result(timeout=timeout_sec)
        return result
    except TimeoutError:
        print(f"  [#{frame_id:04d}] ⏱ Visual match timeout ({timeout_sec}s) — continuing with DR")
        with _state_lock:
            _matching_busy = False
            cur_dr_lat = _pred_lat
            cur_dr_lon = _pred_lon
        # Write timeout result to JSON
        _write_status_predicted(cur_dr_lat, cur_dr_lon, 0.0, "dead_reckoning_timeout",
                               ref_lat, ref_lon, radius_m, timeout_sec * 1000, frame_id)
        return None
    except Exception as e:
        print(f"  [#{frame_id:04d}] ⚠ Future exception: {e}")
        with _state_lock:
            _matching_busy = False
        return None

def _schedule_async_match(img_bytes: bytes, frame_id: int,
                          anchor_lat: float, anchor_lon: float,
                          ref_lat: float, ref_lon: float, radius_m: float):
    """Non-blocking wrapper for matching."""
    if not GPU_ENABLED:
        return
    
    with _state_lock:
        busy = _matching_busy
    
    if not busy:
        with _state_lock:
            _matching_busy = True
        _match_executor.submit(_do_match_with_timeout, img_bytes, frame_id,
                              anchor_lat, anchor_lon, ref_lat, ref_lon, radius_m)

# ── CSV writer ────────────────────────────────────────────────────────────────
_csv_queue: queue.Queue = queue.Queue(maxsize=500)

def _csv_writer_thread():
    with open(str(CSV_PATH), "w", newline="") as f:
        csv.writer(f).writerow([
            "frame_id","timestamp","image_file","lat","lon",
            "alt_m","heading_deg","speed_mps","gps_valid",
            "predicted_lat","predicted_lon","match_score"
        ])
        f.flush()
    with open(str(CSV_PATH), "a", newline="") as f:
        w = csv.writer(f)
        while True:
            try:
                row = _csv_queue.get(timeout=2.0)
                if row is None: break
                w.writerow(row)
                f.flush()
                _csv_queue.task_done()
            except queue.Empty:
                continue

threading.Thread(target=_csv_writer_thread, daemon=True, name="CSVWriter").start()

_img_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ImgWriter")
def _save_image(path, data):
    try: Path(path).write_bytes(data)
    except Exception as e: print(f"  [ImgWriter] {e}")

# ── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(PKG_DIR), static_url_path="")
CORS(app)

@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"]  = "*"
    r.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return r

@app.route("/frame", methods=["OPTIONS"])
def preflight(): return jsonify({}), 200

@app.route("/frame", methods=["POST"])
def receive_frame():
    global first_frame_received, _frame_count
    global _gps_active, _last_lat, _last_lon, _pred_lat, _pred_lon
    global _anchor_lat, _anchor_lon, _matching_busy, _search_radius

    try:
        data      = request.get_json(force=True)
        meta      = data.get("metadata", {})
        img_b64   = data.get("image_b64", "")
        
        # Safely decode base64
        try:
            img_bytes = base64.b64decode(img_b64) if img_b64 else b""
        except Exception as e:
            print(f"  [receive_frame] Base64 decode error: {e}")
            return jsonify({"error": "invalid image encoding"}), 400

        frame_id  = meta.get("frame_id", 0)
        gps_valid = meta.get("gps_valid", False)
        alt       = meta.get("altitude_m", 400)
        heading   = meta.get("heading_deg", 0)
        speed     = meta.get("speed_mps", 0)
        delta_t   = meta.get("delta_t_s", 3.0)
        ts        = datetime.now().isoformat()
        ts_p      = datetime.now().strftime("%H:%M:%S")

        # Search radius
        footprint = alt * 0.24 * 224 / 1000
        radius_m  = max(footprint * 3, alt * 2)

        with _state_lock:
            _frame_count  += 1
            _search_radius = radius_m

        if not first_frame_received:
            first_frame_received = True
            FIRST_FRAME_FLAG.write_text(str(os.getpid()))

        # ── CASE 1: GPS VALID ─────────────────────────────────────────────────────
        if gps_valid:
            lat = meta.get("lat", 0.0)
            lon = meta.get("lon", 0.0)
            with _state_lock:
                _gps_active  = True
                _last_lat    = lat
                _last_lon    = lon
                _pred_lat    = lat
                _pred_lon    = lon
                _anchor_lat  = lat
                _anchor_lon  = lon

            try:
                navigator.update_from_gps(lat, lon)
            except Exception as e:
                print(f"  [Navigator] update_from_gps error: {e}")
            
            print(f"[{ts_p}] #{frame_id:04d} GPS    lat={lat:.5f} lon={lon:.5f}")
            _write_status_active(lat, lon, frame_id)

            fname = f"frame_{frame_id:04d}_lat{lat:.5f}_lon{lon:.5f}_alt{alt}m.jpg"
            _img_executor.submit(_save_image, FRAMES_GPS_DIR / fname, img_bytes)
            try:
                _csv_queue.put_nowait([frame_id, ts, f"frames_gps/{fname}",
                    lat, lon, alt, heading, speed, True, lat, lon, 1.0])
            except queue.Full: pass

            return jsonify({"status": "ok", "action": "gps_frame_saved",
                            "lat": lat, "lon": lon})

        # ── CASE 2: GPS LOST ──────────────────────────────────────────────────────
        # CRITICAL: Return IMMEDIATELY with dead reckoning, never wait for GPU
        with _state_lock:
            if _gps_active:
                _gps_active = False
                print(f"\n🔴 GPS LOST at frame #{frame_id}! Starting visual navigation...")

            # Use best available position (visual match if available, else last GPS)
            base_lat  = _pred_lat if _pred_lat != 0.0 else _last_lat
            base_lon  = _pred_lon if _pred_lon != 0.0 else _last_lon
            ref_lat   = _last_lat
            ref_lon   = _last_lon
            anc_lat   = _anchor_lat
            anc_lon   = _anchor_lon
            latest_score = _match_score

        # ─── IMMEDIATE DEAD RECKONING (no wait for GPU) ───────────────────────
        try:
            nav_heading = navigator.heading_to_next(base_lat, base_lon)
            effective_heading = nav_heading if navigator.target_wp else heading
        except Exception as e:
            print(f"  [Navigator] heading_to_next error: {e}, using dead reckoning")
            effective_heading = heading
        
        try:
            dr_lat, dr_lon = dead_reckon(base_lat, base_lon, effective_heading, speed, delta_t)
        except Exception as e:
            print(f"  [dead_reckon] Error: {e}, keeping current position")
            dr_lat, dr_lon = base_lat, base_lon

        # Return position IMMEDIATELY (dead reckoning + latest visual match if available)
        with _state_lock:
            _pred_lat = dr_lat
            _pred_lon = dr_lon

        # ✅ WRITE DEAD RECKONING TO GPS STATUS IMMEDIATELY for frontend update
        _write_status_predicted(dr_lat, dr_lon, 0.0, "dead_reckoning",
                               ref_lat, ref_lon, radius_m, 0, frame_id)

        # ─── ASYNC VISUAL MATCHING IN STRICT BACKGROUND (never blocks) ─────────
        # Launch visual matching WITHOUT blocking response
        if _dataset_ready:
            try:
                _schedule_async_match(img_bytes, frame_id,
                                     anc_lat, anc_lon, ref_lat, ref_lon, radius_m)
            except Exception as e:
                print(f"  [async_match] Error: {e}")

        fname = f"frame_{frame_id:04d}_NOGPS_alt{alt}m.jpg"
        _img_executor.submit(_save_image, FRAMES_NOGPS_DIR / fname, img_bytes)

        # ─── PREPARE RESPONSE (BEFORE GPU completes) ──────────────────────────
        with _state_lock:
            cur_lat   = _pred_lat
            cur_lon   = _pred_lon
            cur_score = latest_score
            # Update navigator with current position for next waypoint calculation
            if navigator.target_wp:
                try:
                    navigator.update_from_gps(cur_lat, cur_lon)
                except Exception as e:
                    print(f"  [Navigator] update_from_gps error: {e}")

        try:
            _csv_queue.put_nowait([frame_id, ts, f"frames_nogps/{fname}",
                "None", "None", alt, heading, speed, False, cur_lat, cur_lon, cur_score])
        except queue.Full: pass

        source = "visual_match" if cur_score > 0.5 else "dead_reckoning"
        print(f"[{ts_p}] #{frame_id:04d} NO GPS ⚡ {source} ({cur_lat:.5f}, {cur_lon:.5f})")

        # RESPOND IMMEDIATELY (never blocking on GPU)
        return jsonify({
            "status":        "ok",
            "action":        "nogps_frame_localized",
            "lat":           cur_lat,
            "lon":           cur_lon,
            "predicted_lat": cur_lat,
            "predicted_lon": cur_lon,
            "match_score":   round(cur_score, 4),
            "source":        source,
            "frame_id":      frame_id,
            "predicted":     True,
            "visual_matching": "async_background",  # Inform client matching is async
            "next_waypoint": navigator.target_wp if navigator.target_wp else None,
        })
    
    except Exception as e:
        import traceback
        print(f"  [receive_frame] CRITICAL ERROR: {e}")
        traceback.print_exc()
        return jsonify({
            "error": str(e),
            "action": "frame_processing_error"
        }), 500

# ── Extra routes ──────────────────────────────────────────────────────────────
@app.route("/api/precollect", methods=["POST", "OPTIONS"])
def api_precollect():
    if request.method == "OPTIONS": return jsonify({}), 200
    global _precollect_running, _precollect_progress, _precollect_total, _precollect_success
    
    body     = request.get_json(force=True)
    lat      = float(body.get("lat", 0))
    lon      = float(body.get("lon", 0))
    alt_m    = int(body.get("alt_m", 400))
    zoom     = int(body.get("zoom", 17))
    radius_m = float(body.get("radius_m", 5500))  # Increased from 800m to get ~2000 tiles
    if not MBTILES_PATH.exists():
        return jsonify({"success": False, "error": f"MBTiles not found: {MBTILES_PATH}"}), 500
    
    print(f"\n  [Precollect] lat={lat:.5f} lon={lon:.5f} alt={alt_m}m zoom={zoom} R={radius_m:.0f}m")
    
    def _do_precollect():
        global _precollect_running, _precollect_progress, _precollect_total, _precollect_success
        try:
            import sys
            sys.path.insert(0, str(PKG_DIR))
            from gps_localizer import precollect_dataset
            
            with _state_lock:
                _precollect_running = True
                _precollect_progress = 0
                _precollect_success = None
            
            result = precollect_dataset(lat=lat, lon=lon, alt_m=alt_m,
                                        mbtiles_path=str(MBTILES_PATH),
                                        output_dir=str(FALLBACK_IMAGES),
                                        zoom=zoom, radius_m=radius_m)
            
            if result.get("success"):
                with _state_lock:
                    _precollect_total = result.get("images", 0)
                    _precollect_progress = _precollect_total
                    _precollect_success = True
                print(f"  [Precollect] ✅ {_precollect_total} tiles extracted to {FALLBACK_IMAGES}")
                _build_index_async(str(FALLBACK_DATASET))
            else:
                with _state_lock:
                    _precollect_success = False
                print(f"  [Precollect] ❌ {result.get('error', 'unknown error')}")
        except Exception as e:
            print(f"  [Precollect] Error: {e}")
            with _state_lock:
                _precollect_success = False
        finally:
            with _state_lock:
                _precollect_running = False
    
    # Start async task
    with _state_lock:
        _precollect_running = True
        _precollect_progress = 0
        _precollect_total = 0
        _precollect_success = None
    
    threading.Thread(target=_do_precollect, daemon=True).start()
    return jsonify({"status": "started", "success": True})

@app.route("/api/gpu_config", methods=["GET", "POST", "OPTIONS"])
def api_gpu_config():
    """Get/set GPU model configuration (dinov2 or netvlad)"""
    if request.method == "OPTIONS":
        return jsonify({}), 200
    
    if request.method == "GET":
        try:
            import sys
            sys.path.insert(0, str(PKG_DIR))
            from gps_localizer import MODEL_TYPE, DEVICE
            return jsonify({
                "model": MODEL_TYPE,
                "device": DEVICE,
                "gpu_enabled": GPU_ENABLED
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    # POST: set model
    try:
        body = request.get_json(force=True)
        model_name = body.get("model", "dinov2")
        
        import sys
        sys.path.insert(0, str(PKG_DIR))
        from gps_localizer import set_model_type
        
        set_model_type(model_name)
        return jsonify({"status": "ok", "model": model_name}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/current_position", methods=["GET"])
def api_current_position():
    """Get current best estimate (GPS or visual)"""
    with _state_lock:
        return jsonify({
            "gps_active": _gps_active,
            "lat": _pred_lat if _gps_active else _pred_lat,
            "lon": _pred_lon if _gps_active else _pred_lon,
            "last_gps_lat": _last_lat,
            "last_gps_lon": _last_lon,
            "match_score": round(_match_score, 4),
            "source": "gps" if _gps_active else ("visual" if _match_score > 0.5 else "dead_reckoning"),
            "waypoint": navigator.target_wp if navigator.target_wp else None,
            "heading_to_wp": navigator.heading_to_next(_pred_lat, _pred_lon) if navigator.target_wp else None,
        })

@app.route("/api/cache_status", methods=["GET"])
def api_cache_status():
    with _state_lock:
        ready = _dataset_ready
        dset  = _active_dataset or ""
    return jsonify({"ready": ready, "dataset": dset, "localizer": ready})

@app.route("/api/set_mission", methods=["POST", "OPTIONS"])
def api_set_mission():
    if request.method == "OPTIONS": return jsonify({}), 200
    body = request.get_json(force=True)
    try:
        config_path = BASE_PATH / "mission_config.json"
        config_path.write_text(json.dumps(body, indent=2))
        navigator.load(str(config_path))
    except Exception as e:
        print(f"  [Mission] Error: {e}")
    return jsonify({"status": "ok"})

@app.route("/api/node", methods=["GET"])
def api_node():
    return jsonify({"status": "ok", "message": "vision integrated in receiver"})

@app.route("/api/precollect_progress", methods=["GET"])
def api_precollect_progress():
    with _state_lock:
        running = _precollect_running
        progress = _precollect_progress
        total = _precollect_total
        success = _precollect_success
        ready = _dataset_ready
    
    # Count actual files to sync with true state - from FALLBACK_IMAGES
    files = list(Path(FALLBACK_IMAGES).glob("*.jpg")) if Path(FALLBACK_IMAGES).exists() else []
    num_files = len(files)
    
    # If running, use file count; if done, use tracked total
    if running:
        actual_progress = max(progress, num_files)
        actual_total = max(total, num_files + 50)  # Estimate remaining
    else:
        actual_progress = num_files
        actual_total = num_files
    
    # Calculate percentage for UI (5% to 95% range for phase 1)
    if actual_total > 0:
        pct = 5 + int((actual_progress / actual_total) * 50)  # 5% + up to 50% = 55%
    else:
        pct = 5
    
    return jsonify({
        "running": running,
        "success": success,
        "done": actual_progress,
        "total": actual_total,
        "pct": min(95, pct),  # Cap at 95% until cache is ready
        "files": num_files,
        "ready": ready
    })

@app.route("/api/precollect_all", methods=["POST", "OPTIONS"])
def precollect_all():
    if request.method == "OPTIONS": return jsonify({}), 200
    return jsonify({"status": "ok"})

@app.route("/status", methods=["GET"])
def status():
    with _state_lock:
        return jsonify({
            "server":          "receiver.py v6",
            "gps_active":      _gps_active,
            "last_gps_lat":    _last_lat,
            "last_gps_lon":    _last_lon,
            "predicted_lat":   _pred_lat,
            "predicted_lon":   _pred_lon,
            "match_score":     round(_match_score, 4),
            "anchor_lat":      _anchor_lat,
            "anchor_lon":      _anchor_lon,
            "frame_count":     _frame_count,
            "match_count":     _match_count,
            "last_match_ms":   _match_ms,
            "localizer_ready": _dataset_ready,
            "active_dataset":  _active_dataset or "none",
            "matching_busy":   _matching_busy,
        })

@app.route("/health", methods=["GET"])
def health():
    with _state_lock:
        return jsonify({"ok": True, "localizer": _dataset_ready,
                        "frames": _frame_count, "matches": _match_count})

@app.route("/gps_status.json", methods=["GET"])
def serve_gps_status():
    try:
        if not GPS_STATUS_PATH.exists():
            return jsonify({"status": "idle", "timestamp": time.time()}), 200
        return send_file(str(GPS_STATUS_PATH), mimetype="application/json")
    except Exception as e:
        return jsonify({"status": "idle", "error": str(e)}), 200

@app.route("/api/visual_localize", methods=["POST", "OPTIONS"])
def api_visual_localize():
    """Visual localization when GPS is lost — uses NetVLAD + DINO"""
    if request.method == "OPTIONS":
        return jsonify({}), 200
    
    try:
        body = request.get_json(force=True)
        frame_path = body.get("frame_path")  # Path to frame to localize
        ref_lat = body.get("ref_lat", _last_lat)  # Reference position (last valid GPS)
        ref_lon = body.get("ref_lon", _last_lon)
        radius_m = body.get("radius_m", 3000)  # Search radius
        
        if not frame_path or not Path(frame_path).exists():
            return jsonify({"error": "frame_path not found"}), 400
        
        with _state_lock:
            if not _dataset_ready or _active_dataset is None:
                return jsonify({"error": "Visual localizer not ready"}), 503
            dataset_dir = _active_dataset
        
        # Run visual localization
        import sys
        sys.path.insert(0, str(PKG_DIR))
        from visual_localizer import VisualLocalizer
        
        t0 = time.perf_counter()
        loc = VisualLocalizer(dataset_dir)
        result = loc.localize(frame_path, ref_lat=ref_lat, ref_lon=ref_lon, 
                             radius_m=radius_m)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        
        # Update global state
        with _state_lock:
            _pred_lat = result["lat"]
            _pred_lon = result["lon"]
            _match_score = result["score"]
            _match_file = result.get("best_match_image", "")
        
        return jsonify({
            "status": "ok",
            "source": "visual",
            "lat": result["lat"],
            "lon": result["lon"],
            "score": result["score"],
            "confidence": min(max(result["score"] * 1.0, 0), 1),
            "best_match": result.get("best_match_image", ""),
            "top5": result.get("top5", []),
            "elapsed_ms": round(elapsed_ms, 1),
            "search_radius_m": radius_m
        }), 200
    
    except Exception as e:
        return jsonify({"error": str(e), "status": "error"}), 500

@app.route("/api/frames_nogps_list", methods=["GET"])
def api_frames_nogps_list():
    """List all frames without GPS for debugging/visualization"""
    try:
        frames = sorted([f.name for f in FRAMES_NOGPS_DIR.glob("*.jpg")])
        return jsonify({
            "count": len(frames),
            "frames": frames[-10:],  # Last 10 frames
            "directory": str(FRAMES_NOGPS_DIR)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/flight_log.csv", methods=["GET"])
def serve_flight_log():
    try:
        if not CSV_PATH.exists():
            return "frame_id,timestamp,image_file,lat,lon,alt_m,heading_deg,speed_mps,gps_valid,predicted_lat,predicted_lon,match_score\n", 200, {"Content-Type": "text/csv"}
        return send_file(str(CSV_PATH), mimetype="text/csv")
    except Exception as e:
        return "", 500

# ── Auto-process frames without GPS ────────────────────────────────────────
_visual_proc_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="VisualProc")

def _auto_process_nogps_frames():
    """Automatically process latest frames without GPS for visual localization"""
    try:
        frames = sorted([f for f in FRAMES_NOGPS_DIR.glob("*.jpg")])
        if not frames:
            return
        
        latest_frame = frames[-1]
        
        with _state_lock:
            if not _dataset_ready or _active_dataset is None:
                return
            dataset_dir = _active_dataset
            ref_lat = _last_lat
            ref_lon = _last_lon
        
        # Run visual localization on this frame
        from visual_localizer import VisualLocalizer
        
        print(f"\n[AUTO-PROCESS] Processing {latest_frame.name} with VisualLocalizer...")
        t0 = time.perf_counter()
        
        loc = VisualLocalizer(dataset_dir)
        result = loc.localize(
            str(latest_frame),
            ref_lat=ref_lat,
            ref_lon=ref_lon,
            radius_m=3000
        )
        
        elapsed_ms = (time.perf_counter() - t0) * 1000
        
        with _state_lock:
            _pred_lat = result["lat"]
            _pred_lon = result["lon"]
            _match_score = result["score"]
            _match_file = result.get("best_match_image", "")
        
        print(f"[AUTO-PROCESS] ✅ Estimated pos: ({result['lat']:.6f}, {result['lon']:.6f}) "
              f"score={result['score']:.3f} in {elapsed_ms:.0f}ms")
        
    except Exception as e:
        print(f"[AUTO-PROCESS] ERROR: {e}")

@app.route("/api/process_latest_nogps", methods=["POST", "OPTIONS"])
def api_process_latest_nogps():
    """Manually trigger processing of latest no-GPS frame"""
    if request.method == "OPTIONS":
        return jsonify({}), 200
    
    try:
        _visual_proc_executor.submit(_auto_process_nogps_frames)
        return jsonify({
            "status": "processing",
            "message": "Visual localization triggered for latest no-GPS frame"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*70)
    print("  NAVERA Receiver v7 — GPU-Optimized for Jetson Orin Nano")
    print("="*70)
    print(f"  PKG dir       : {PKG_DIR}")
    print(f"  Dataset       : {BASE_PATH}")
    print(f"  GPS status    : {GPS_STATUS_PATH}")
    print(f"  GPU enabled   : {GPU_ENABLED}")
    print(f"  Match timeout : {MATCH_TIMEOUT_SEC}s")
    print(f"  Endpoint      : http://0.0.0.0:5000/frame")
    print("="*70)
    _init_localizer()
    print(f"\n  Starting Flask (GPU-optimized)...\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
