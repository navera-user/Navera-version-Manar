# NAVERA — GPS-denied positioning box

NAVERA is an onboard unit (NVIDIA Jetson Orin Nano, ROS 2 Humble) that keeps providing a
position when GPS fails, is jammed or has no coverage. It works by matching the vehicle's
camera against an onboard satellite map, with night (thermal) and celestial (star camera)
fallbacks. It is vehicle-agnostic (UAV, USV, UGV). By IRIS Systems.

> **Release 0.2 — field validation pending.** Positioning accuracy is measured on bench and
> replay data only; day vision is not yet accurate enough to replace GPS. See
> [docs/VALIDATION_STATUS.md](docs/VALIDATION_STATUS.md) for every measured number and
> [docs/ENGINEERING_BACKLOG.md](docs/ENGINEERING_BACKLOG.md) for open work.

## How it works

```
GPS (NMEA) ─────────────┐
camera → day_subscriber ─┤                         ┌→ /navera/position   (winning estimate)
camera → night_subscriber┼→ /navera/estimate/* → navera_estimator ┤
camera → cn_subscriber ──┘   (one typed contract)       └→ /navera/nav_status (FIX/DEGRADED/NO_FIX + why)
IMU, RTC (liveness, time)                                            │
                                               web bridge :8181 ─────┘→ operator view (/operator)
```

- Every source publishes the same message, `navera_msgs/PositionEstimate`: the position,
  its covariance, **which source it came from** and **whether it was measured,
  dead-reckoned or replayed**.
- `navera_estimator` picks one winner with priority GPS > day > night > celestial. It
  rejects stale, future-stamped or non-finite estimates, and publishes each measurement once.
- **FIX** is only given when the uncertainty is known (today, only GPS). Vision and
  celestial positions are **DEGRADED**. With no usable source, the state is **NO_FIX**,
  and no old position is re-sent as current.

## Packages

| Package | Role |
|---|---|
| `navera_msgs` | `PositionEstimate`, `NavStatus`, `SourceHealth` message contracts |
| `navera_estimator` | Position arbiter → `/navera/position`, `/navera/nav_status` |
| `navera_common` | Shared helpers (process lifecycle, geodesy / dead-reckoning) |
| `gps_pkg` | GPS driver (NMEA over serial, checksummed, auto-restart on port loss) |
| `imu_pkg` | IMU driver (BNO085, I²C) — liveness only for now |
| `rtc_pkg` | Real-time clock (DS3231, I²C) |
| `camera_pkg` | Frame source (live camera or CSV + image replay) with start/ack protocol |
| `day_pkg` | Day localization (DINOv2 retrieval against satellite tiles) |
| `night_pkg` | Night localization (STHN thermal-to-satellite homography) |
| `cn_pkg` | Celestial localization (astrometry.net plate solving) |
| `simulation_web` | Web bridge: operator view, dashboard, map tiles, launch files |
| `navera_tools` | Bench tools (`sensor_sim.py`, scenario scripts) — test machines only |

`vision_pkg/` is legacy (the first prototype) and is not used. The `isaac_ros_*` and
`isaac_common*` folders are vendored NVIDIA packages; no NAVERA package depends on them.

## Build

On the Jetson (JetPack 6, ROS 2 Humble installed):

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-up-to \
  navera_msgs navera_common navera_estimator gps_pkg imu_pkg rtc_pkg \
  camera_pkg day_pkg night_pkg cn_pkg navera_output simulation_web
source install/setup.bash
```

Python dependencies (user install, pinned to the Jetson PyTorch build):

```bash
printf 'torch==2.8.0\ntorchvision==0.23.0\nnumpy<2\nsetuptools<80\n' > /tmp/constraints.txt
pip3 install --user --no-deps --index-url https://pypi.jetson-ai-lab.io/jp6/cu126/+simple \
  torch==2.8.0 torchvision==0.23.0
pip3 install --user -c /tmp/constraints.txt "numpy<2" "scipy>=1.11,<1.14" timm kornia \
  safetensors einops huggingface_hub scikit-learn pandas flask flask-cors pyserial pynmea2 "astropy<7" \
  pymavlink pygeomag==1.1.0
# box sensors (BNO085 IMU, DS3231 clock) — see deploy/README.md for the service user
pip3 install --user adafruit-blinka adafruit-circuitpython-bno08x adafruit-circuitpython-ds3231
```

## Data (not in git)

| Setting | Content |
|---|---|
| `NAVERA_MBTILES` | Satellite map, MBTiles (Sousse z13–z19, ~10 GB) |
| `DAY_DATASET_DIR` | Day tile dataset: `dataset.csv` + `images/` (the descriptor cache is built on first run) |
| `NAVERA_STHN_DIR`, `NAVERA_STHN_WEIGHTS` | STHN code and `one_stage/model.safetensors` (HuggingFace `xjh19972/STHN`) |
| `TORCH_HOME` | DINOv2 weights cache (pre-fill it: the vehicle may have no internet) |

Set these in `/etc/navera/navera.env` (see [deploy/navera.env.example](deploy/navera.env.example)).

## Run

Everything at boot, as systemd services: see [deploy/README.md](deploy/README.md).

By hand, for development:

```bash
set -a; . /etc/navera/navera.env; set +a
ros2 launch navera_estimator estimator.launch.py &
ros2 launch gps_pkg gps.launch.py serial_port:=/dev/ttyTHS1 &
ros2 launch simulation_web day_sim.launch.py          # day pipeline + web bridge
# Operator view:  http://<jetson-ip>:8181/operator
```

Bench test without any hardware (test machine only):

```bash
NAVERA_ALLOW_SIM=1 python3 navera_tools/sensor_sim.py
```

## Web interface

- `/operator`: the operator view. It shows the arbiter's decision (source, FIX /
  DEGRADED / NO FIX / OFFLINE, age, reason). The vehicle marker disappears whenever
  there is no valid position.
- `/`: the mission planner and replay dashboard.
- Starting a mission (`POST /api/set_mission`) needs the `X-Navera-Token` header
  (`NAVERA_WEB_TOKEN`). Without a token the interface is read-only.

## Documentation

- [docs/VALIDATION_STATUS.md](docs/VALIDATION_STATUS.md): what is measured, how, and the known limitations
- [deploy/README.md](deploy/README.md): boot services, installation (in French)
- [CLAUDE.md](CLAUDE.md): engineering rules for this codebase
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): data flow, topics, the position contract, protocols, web API
- [AUDIT.md](AUDIT.md): codebase audit (2026-06-30, historical)
