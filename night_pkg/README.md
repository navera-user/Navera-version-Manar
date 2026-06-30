# night_pkg — NAVERA Night Localization

STHN-based GPS-denied night localization for NAVERA.  
Port **5001** (mirrors `vision_pkg` on 5000).

---

## Architecture

```
night_pkg/
├── night_localizer.py        ← STHN inference engine (MBTiles + homography)
├── night_receiver.py         ← Flask server port 5001
├── ros2_night_node.py        ← ROS2 node (pubs /navera/night_fix)
├── test_night_standalone.py  ← Standalone test (no ROS2)
└── requirements_night.txt
```

---

## Step 0 — Prerequisites

### 1. STHN weights
Download from HuggingFace:
```bash
pip install huggingface_hub
python3 -c "
from huggingface_hub import hf_hub_download, snapshot_download
snapshot_download('xjh19972/STHN', local_dir='~/Desktop/pfeAutonomTest/STHN/weights')
"
```
The relevant file is usually `model_best.pth` or `local_*.pth`.

### 2. Python deps (in ai_env)
```bash
~/pfeAutonomTest/ai_env/bin/python3 -m pip install einops timm kornia flask flask-cors
```

---

## Step 1 — Standalone test (no ROS2)

```bash
cd ~/isaac_ros_common/night_pkg

~/pfeAutonomTest/ai_env/bin/python3 test_night_standalone.py \
    --sthn-dir ~/Desktop/pfeAutonomTest/STHN \
    --weights  ~/Desktop/pfeAutonomTest/STHN/weights/model_best.pth \
    --mbtiles  ~/pfeAutonomTest/sousse_satellite.mbtiles \
    --lat 36.8189 --lon 10.6367 \
    --n 5
```

With a real frame:
```bash
~/pfeAutonomTest/ai_env/bin/python3 test_night_standalone.py \
    --sthn-dir ~/Desktop/pfeAutonomTest/STHN \
    --weights  ~/Desktop/pfeAutonomTest/STHN/weights/model_best.pth \
    --mbtiles  ~/pfeAutonomTest/sousse_satellite.mbtiles \
    --image /path/to/night_frame.jpg
```

---

## Step 2 — Flask receiver (port 5001)

```bash
~/pfeAutonomTest/ai_env/bin/python3 night_receiver.py \
    --sthn-dir ~/Desktop/pfeAutonomTest/STHN \
    --weights  ~/Desktop/pfeAutonomTest/STHN/weights/model_best.pth \
    --mbtiles  ~/pfeAutonomTest/sousse_satellite.mbtiles

# Test:
curl http://localhost:5001/api/status
```

---

## Step 3 — Install as ROS2 package

```bash
# Copy to ros2_ws
cp -r ~/isaac_ros_common/night_pkg \
      ~/isaac_ros_common/ros2_ws/src/night_pkg

cd ~/isaac_ros_common/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select night_pkg
source install/setup.bash
```

---

## Step 4 — Run ROS2 node

```bash
source ~/isaac_ros_common/ros2_ws/install/setup.bash

ros2 run night_pkg night_node \
    --ros-args \
    -p sthn_dir:=$HOME/Desktop/pfeAutonomTest/STHN \
    -p weights:=$HOME/Desktop/pfeAutonomTest/STHN/weights/model_best.pth \
    -p mbtiles:=$HOME/pfeAutonomTest/sousse_satellite.mbtiles \
    -p zoom:=17
```

Monitor output:
```bash
ros2 topic echo /navera/night_fix
ros2 topic echo /navera/night_status
```

---

## API Reference (Flask)

| Endpoint | Method | Description |
|---|---|---|
| `/frame` | POST | `{image: base64, lat, lon}` → queues inference |
| `/position` | GET | Latest fix `{lat, lon, conf, source, dt_ms}` |
| `/api/set_mission` | POST | Mission config |
| `/api/status` | GET | Health check |
| `/api/localize` | POST | Synchronous inference (for testing) |

---

## STHN Model Notes

- Uses `local_pipeline/model/network.py` — the homography estimation network
- Input: query frame (drone cam) + satellite patch (from MBTiles at GPS prior)
- Output: 4-corner offsets → converted to lat/lon displacement
- Bias correction: Bing↔ESRI ~4m south / 5m east at zoom 17 over Sousse
- Rolling average: 5 frames for smoothing

---

## Weights — what to look for

From `xjh19972/STHN` HuggingFace:
- `model_best.pth` — best local pipeline checkpoint
- Files with `local_` prefix are for the local homography pipeline (what we use)
- Files with `global_` prefix are for global retrieval (not needed here)
