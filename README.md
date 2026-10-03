# NAVERA — GPS-denied positioning box

NAVERA is an onboard unit (NVIDIA Jetson Orin Nano, ROS 2 Humble) that keeps providing a
position when GPS fails, is jammed or has no coverage. It works by matching the vehicle's
camera against an onboard satellite map, with night (thermal) and celestial (star camera)
fallbacks. It is vehicle-agnostic (UAV, USV, UGV). By IRIS Systems.

> **Release 0.2 — field validation pending.** Positioning accuracy is measured on bench,
> replay and simulator data only, never with NAVERA's own camera on a real vehicle: day
> vision's accuracy as a GPS replacement is therefore not established. The vehicle outputs
> are verified in ArduPilot SITL only; PX4 is not tested. See
> [docs/VALIDATION_STATUS.md](docs/VALIDATION_STATUS.md) for every measured number.

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
  rejects stale, future-stamped or non-finite estimates and impossible covariances, drops a
  GPS fix older than the last one received, and publishes each measurement once.
- **FIX** is only given when the uncertainty is stated (a defined covariance type, sigma
  ≥ 1 cm) and at most 25 m — today, only GPS. Vision and celestial positions are
  **DEGRADED**. With no usable source, the state is **NO_FIX**, and no old position is
  re-sent as current.
- GPS is protected against spoofing: an impossible jump is refused; a GPS that day vision
  contradicts is first shown and sent **"in doubt"** (DEGRADED, its accuracy no better than
  the gap), then refused; it is re-accepted only when independent fixes agree again
  ([docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §3).

## Packages

| Package | Role |
|---|---|
| `navera_msgs` | `PositionEstimate`, `NavStatus`, `SourceHealth` message contracts |
| `navera_estimator` | Position arbiter → `/navera/position`, `/navera/nav_status` |
| `navera_common` | Shared helpers (process lifecycle, geodesy, track velocity, QoS, boot discovery) |
| `gps_pkg` | GPS driver (NMEA over serial, checksummed, auto-restart on port loss) |
| `imu_pkg` | Box IMU driver (BNO085, I²C): attitude for the camera, true north |
| `rtc_pkg` | Real-time clock (DS3231, I²C) |
| `camera_pkg` | Frame source (live camera or CSV + image replay) with start/ack protocol |
| `day_pkg` | Day localization (local feature matching against satellite tiles around the prior; DINOv2 retrieval as fallback; dead-reckoning along the measured track) |
| `night_pkg` | Night localization (STHN thermal-to-satellite homography) |
| `cn_pkg` | Celestial localization (astrometry.net plate solving) |
| `navera_output` | Output to the vehicle (NMEA, MAVLink `GPS_INPUT`, ROS `/navera/fix`) and the vehicle link (autopilot → NAVERA) |
| `simulation_web` | Web bridge: operator view, dashboard, `/mission` page, map tiles, launch files |
| `navera_tools` | Field tools (`check_box.py`, `record_session.sh`, `evaluate_session.py`, `calibrate_camera.py`) and bench / simulation tools (`sensor_sim.py`, mission simulator, demo) — see [navera_tools/README.md](navera_tools/README.md) |

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

Python dependencies — the same list as [deploy/README.md §3.3](deploy/README.md) (which
installs them for the `navera` service user), pinned to the Jetson PyTorch build:

```bash
printf 'torch==2.8.0\ntorchvision==0.23.0\nnumpy<2\nsetuptools<80\n' > ~/navera-constraints.txt
pip3 install --user --no-deps --index-url https://pypi.jetson-ai-lab.io/jp6/cu126/+simple \
  torch==2.8.0 torchvision==0.23.0
pip3 install --user -c ~/navera-constraints.txt \
  "numpy<2" "scipy>=1.11,<1.14" timm kornia safetensors einops huggingface_hub \
  scikit-learn pandas "astropy<7" opencv-python==4.11.0.86 \
  pyserial pynmea2 pymavlink pygeomag==1.1.0 \
  Jetson.GPIO adafruit-blinka adafruit-circuitpython-bno08x adafruit-circuitpython-ds3231
```

## Data (not in git)

| Setting | Content |
|---|---|
| `NAVERA_MBTILES` | Satellite map, MBTiles (Sousse z13–z19, ~10 GB) |
| `DAY_DATASET_DIR` | Day tile dataset: `dataset.csv` + `images/` (the descriptor cache is built on first run) |
| `NAVERA_STHN_DIR`, `NAVERA_STHN_WEIGHTS` | STHN code and `one_stage/model.safetensors` (HuggingFace `xjh19972/STHN`) |
| `TORCH_HOME` | DINOv2 weights cache (pre-fill it: the vehicle may have no internet) |

Set these in `/etc/navera/navera.env` (see [deploy/navera.env.example](deploy/navera.env.example));
the data disk and how the files get onto it: [deploy/README.md §3.10](deploy/README.md). Maps
of other areas are generated on the `/mission` page (deploy/README.md §8; check the imagery
licence).

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

Bench test without any hardware (a test machine, never a box on a vehicle):

```bash
NAVERA_ALLOW_SIM=1 python3 navera_tools/sensor_sim.py
```

## Web interface

- `/operator`: the operator view. It shows the arbiter's decision (source, e.g.
  `DAY VISION · DEGRADED · ±34 m`, age, reason); a vision position is shown carried to now
  along NAVERA's track ("photo 1.8 s old, carried to now"), and a warning appears when 30 %
  of the last minute's camera frames could not be used (too tilted, turning too fast, no
  attitude). The vehicle marker disappears whenever there is no valid position.
- `/mission`: mission preparation — vehicle settings, route maps, terrain warning, start
  without GPS (deploy/README.md §8).
- `/`: the mission planner and replay dashboard.
- Every control action needs the `X-Navera-Token` header (`NAVERA_WEB_TOKEN`); without a
  token the interface is read-only. After 5 wrong codes in 60 s an address is refused for
  60 s.

## Documentation

- [docs/VALIDATION_STATUS.md](docs/VALIDATION_STATUS.md): what is measured, how, and the known limitations
- [deploy/README.md](deploy/README.md): installation, boot services, sources, outputs, data disk, `/mission`
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): data flow, topics, the position contract, protocols, web API
- [docs/ARDUPILOT_INTEGRATION.md](docs/ARDUPILOT_INTEGRATION.md): wiring and ArduPilot parameters
- [docs/PX4_INTEGRATION.md](docs/PX4_INTEGRATION.md): PX4 — what is and is not possible (not tested)
- [docs/FIELD_TEST_PROCEDURE.md](docs/FIELD_TEST_PROCEDURE.md): the first real test
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): symptom → cause → fix
- Package READMEs: [navera_output](navera_output/README.md), [imu_pkg](imu_pkg/README.md), [navera_tools](navera_tools/README.md)
