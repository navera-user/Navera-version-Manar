# night_pkg — NAVERA Night Localization  🌙

STHN-based drone-to-satellite homography matching, compatible with **navera.html Night Mode**.

---

## 🐛 Bugs Fixed (summary)

| # | File | Bug | Fix |
|---|------|-----|-----|
| 1 | `night_receiver.py` | `/flight_log.csv` endpoint missing — navera.html polls it every 1 s | Added `GET /flight_log.csv` serving in-memory CSV |
| 2 | `night_receiver.py` | `/gps_status.json` endpoint missing — navera.html polls it every 0.5 s | Added `GET /gps_status.json` |
| 3 | `night_receiver.py` | `/api/cache_status`, `/api/precollect`, `/api/precollect_progress` missing | Added all three (night mode stubs that return ready=True) |
| 4 | `night_receiver.py` | `/frame` expected `{"image":…}` but navera.html sends `{"image_b64":…, "metadata":{…}}` | Accept both field names; unwrap `metadata` sub-object |
| 5 | `night_receiver.py` | Background worker never wrote flight log or GPS status — frontend saw nothing | Worker now appends rows to `_flight_log_rows` and updates `_gps_status` |
| 6 | `night_receiver.py` | Default `--mbtiles` path wrong (`~/pfeAutonomTest/…`) | Fixed to `~/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles` |
| 7 | `night_localizer.py` | `model(q_t, db_t)` forward call may fail if STHN uses kwargs; no fallback | Try positional first, fall back to `query=`/`db=` kwargs |
| 8 | `night_localizer.py` | Model loading: `checkpoint` might be a raw state_dict, not a wrapped dict | Handle both; also try `"state_dict"` key |
| 9 | `night_localizer.py` | `Network` import hardcoded to `local_pipeline.model.network`; fails if STHN not installed as package | Added fallback: walk `sthn_dir` recursively for `network.py` |
| 10 | `ros2_night_node.py` | `msg.status.status >= NavSatStatus.STATUS_NO_FIX` was **inverted** — skipped ALL valid GPS fixes | Fixed to `< NavSatStatus.STATUS_FIX` |
| 11 | `ros2_night_node.py` | Default `--mbtiles` ROS2 param pointed to wrong path | Fixed to correct dataset path |
| 12 | `setup.py` | `install_requires` was `['setuptools']` only — Flask, OpenCV, Torch missing | Added `flask`, `flask-cors`, `numpy`, `opencv-python`, `torch`, `torchvision` |

---

## Directory layout (unchanged)

```
~/isaac_ros_common/night_pkg/
├── night_pkg/
│   ├── __init__.py
│   ├── night_localizer.py      ← STHN wrapper
│   ├── night_receiver.py       ← Flask server (port 5001)
│   └── ros2_night_node.py      ← ROS2 node
├── package.xml
├── README.md
├── resource/
│   └── night_pkg
├── setup.py
└── test_night_standalone.py
```

---

## Prerequisites

```bash
# 1. Python deps (on navera-desktop, NOT inside ROS2 venv)
pip install flask flask-cors numpy opencv-python --break-system-packages
# torch should already be installed; if not:
# pip install torch torchvision --break-system-packages

# 2. STHN repo must be cloned
ls ~/Desktop/pfeAutonomTest/STHN/local_pipeline/   # must exist
ls ~/Desktop/pfeAutonomTest/STHN/weights/model_best.pth   # must exist

# 3. MBTiles must be at:
ls ~/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles
```

---

## How to run

### A) Standalone — Flask only (no ROS2 needed)

```bash
cd ~/isaac_ros_common/night_pkg

python3 night_pkg/night_receiver.py \
    --sthn-dir ~/Desktop/pfeAutonomTest/STHN \
    --weights  ~/Desktop/pfeAutonomTest/STHN/weights/model_best.pth \
    --mbtiles  ~/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles \
    --port 5001
```

The server starts at **http://0.0.0.0:5001**.

### B) Verify it works

```bash
# Health check
curl http://localhost:5001/api/status

# Cache status (navera.html polls this)
curl http://localhost:5001/api/cache_status

# GPS status (navera.html polls this every 0.5 s)
curl http://localhost:5001/gps_status.json

# Flight log (navera.html polls this every 1 s)
curl http://localhost:5001/flight_log.csv
```

### C) Test the STHN pipeline alone (no Flask, no ROS2)

```bash
cd ~/isaac_ros_common/night_pkg

python3 test_night_standalone.py \
    --sthn-dir ~/Desktop/pfeAutonomTest/STHN \
    --weights  ~/Desktop/pfeAutonomTest/STHN/weights/model_best.pth \
    --mbtiles  ~/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles \
    --lat 35.8288 --lon 10.6360 \
    --n 3

# With a real drone image:
python3 test_night_standalone.py \
    --sthn-dir ~/Desktop/pfeAutonomTest/STHN \
    --weights  ~/Desktop/pfeAutonomTest/STHN/weights/model_best.pth \
    --mbtiles  ~/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles \
    --image /path/to/night_frame.jpg \
    --lat 35.8288 --lon 10.6360
```

### D) With ROS2 (after sourcing)

```bash
source /opt/ros/humble/setup.bash
source ~/isaac_ros_common/install/setup.bash

ros2 run night_pkg night_node \
    --ros-args \
    -p sthn_dir:=/home/navera/Desktop/pfeAutonomTest/STHN \
    -p weights:=/home/navera/Desktop/pfeAutonomTest/STHN/weights/model_best.pth \
    -p mbtiles:=/home/navera/isaac_ros_common/vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles \
    -p zoom:=17
```

---

## navera.html Night Mode integration

When the user selects **🌙 Night Mode** in the config overlay, navera.html sets:

```javascript
RECEIVER = 'http://localhost:5001'   // → night_receiver.py
```

It then calls:
| Endpoint | When |
|----------|------|
| `POST /api/set_mission` | On Launch — sends waypoints + mission config |
| `POST /api/precollect` | On ⚡ Pré-collecter — night mode returns instant success |
| `GET /api/precollect_progress` | Polled until done |
| `GET /api/cache_status` | Polled every 3 s; `ready:true` enables Launch button |
| `POST /frame` | Every ~8 s during flight — sends `{image_b64, metadata}` |
| `GET /flight_log.csv` | Polled every 1 s by flight monitor |
| `GET /gps_status.json` | Polled every 0.5 s by flight monitor |

All endpoints are now implemented. ✅

---

## Architecture diagram

```
navera.html (pc_nour browser)
     │
     │  POST /frame  {image_b64, metadata}
     │  GET  /flight_log.csv         (every 1 s)
     │  GET  /gps_status.json        (every 0.5 s)
     │  GET  /api/cache_status       (every 3 s)
     ▼
night_receiver.py  :5001  (navera-desktop)
     │
     ├─ background worker thread
     │       │  STHN forward pass
     │       ▼
     │   night_localizer.py
     │       │  fetches 3×3 tile mosaic
     │       ▼
     │   sousse_satellite.mbtiles
     │       └── returns (lat, lon, conf)
     │
     └─ writes flight_log.csv (in-memory)
        writes gps_status.json (in-memory)
```
