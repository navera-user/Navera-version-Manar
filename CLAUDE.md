# CLAUDE.md — NAVERA Product Engineering Guide

> Read this file fully at the start of every session. It governs how you work on this codebase.
> You are acting as a **senior ROS2 / embedded-systems engineer** building NAVERA from a working
> prototype into a clean, optimized, certification-ready **product** for IRIS Systems.

---

## 1. WHO & WHAT

- **Product:** NAVERA — GPS-denied autonomous navigation system.
- **Mission:** provide a reliable position fix when GPS is unavailable (jamming, failure, no coverage),
  by matching the vehicle camera against an onboard satellite image database, plus celestial and
  inertial fallback.
- **Owner:** IRIS Systems (sister company of Avionav). This is a **commercial product**, not a school project.
- **Target vehicles:** UAV, USV, UGV (multi-vehicle, modular).
- **Compute:** NVIDIA Jetson Orin Nano 8 GB, JetPack 6.2.1 (L4T R36.4.7), Ubuntu 22.04.
- **Runtime:** Isaac ROS Docker container, **ROS2 Humble**, CUDA 12.6, GPU available inside the container.

---

## 2. GOLDEN RULES (never break these)

1. **The system currently WORKS. Never break a working pipeline.** If unsure, stop and ask.
2. **Always work on a git branch**, never directly on `main`. Commit small, commit often.
3. **Never commit large files.** No `.mbtiles`, `.npz`, `.pth`, `.safetensors`, `.engine`, `.so`,
   `.whl`, model caches, `torch_jetson/`, `torchgen/`, `functorch/`, `.torch_cache/`. The `.gitignore`
   already excludes these — keep it that way. If you add a new large artifact, add it to `.gitignore`.
4. **Verify before destroying.** Before deleting or heavily rewriting a file, confirm it is not used
   (grep for imports/launch references). Prefer moving to an `archive/` folder over deleting.
5. **One concern per commit.** Cleaning, refactor, optimization, and new features go in separate commits.
6. **Measure, don't guess.** For any performance/accuracy claim, run a measurement and report the number.
   Never state a precision figure that hasn't been measured on representative data.
7. **Honesty over optimism.** If a result is only validated in simulation, say so. Real precision
   depends on real sensors (IMU, clock) and real flight data — which are not all integrated yet.

---

## 3. ARCHITECTURE (verified live — this is accurate)

Three localization pipelines share ONE chain. Only one runs at a time. Every source publishes
the typed contract `navera_msgs/PositionEstimate` on `/navera/estimate/<source>`, and
`navera_estimator` elects one winner.

```
camera_pkg (source) → [day|night|cn]_subscriber (localizer) → /navera/estimate/* ┐
gps_node ────────────────────────────────────────────────────→ /navera/estimate/gps ┼→ navera_estimator
                  → /navera/position + /navera/nav_status → simulation_web bridge (HTTP :8181) → /operator
```

### ROS2 packages
| Package | Executable | Role |
|---------|-----------|------|
| `camera_pkg` | `camera_publisher.py` | Frame source (CSV+image replay or live camera), sync protocol |
| `day_pkg` | `day_subscriber.py` (+`local_matcher.py`, `day_localizer.py`) | Day localization — **local feature matching** vs satellite around the prior (DINOv2 retrieval as fallback) |
| `night_pkg` | `night_subscriber.py` (+`night_localizer.py`) | Night localization — **STHN** homography |
| `cn_pkg` | `cn_subscriber.py` | Celestial — astrometry.net plate-solving |
| `gps_pkg` | `gps_node.py` | GPS driver (NMEA serial, checksummed) → estimator |
| `imu_pkg` | `imu_node.py` | Optional box IMU driver (BNO085, I²C bus 1 @ 0x4A); the reference IRIS kit's IMU is the **Insta360 One R camera's own IMU** (`camera_pkg` `insta360_imu_node`, gyro + accelerometer, no magnetometer — integration in progress, problem F37) |
| `rtc_pkg` | `rtc_node.py` | Real-time clock (DS3231, I²C bus 1 @ 0x68) |
| `navera_estimator` | `estimator_node.py` | Position arbiter: GPS > day > night > celestial |
| `navera_msgs` / `navera_common` | — | Message contracts / shared helpers (lifecycle, geodesy) |
| `simulation_web` | `navera_web_bridge.py`, `navera_stellar_bridge.py` | ROS→HTTP bridge, operator view, dashboard |

### Communication protocol (camera ↔ localizer)
- **Start gate:** mission starts on command (`camera/start`, latched Bool).
- **Handshake:** camera waits for `localizer_ready` (latched Bool) before frame 1.
- **Back-pressure:** camera sends next frame only after `frame_done` ack (Int32). Strictly serial.
- Forward data: `image_raw` (Image), `frame_meta` (String/JSON). Output: `position_estimate`
  (NavSatFix), `*_status` (String/JSON: source, score, jump_m).
- QoS: data topics RELIABLE depth 10; ack depth 1; ready/start TRANSIENT_LOCAL (latched).

### Source-selection hierarchy
`GPS (if valid) → day vision → night vision → celestial` (navera_estimator). Inertial
navigation (integrating the IMU into a position) is not implemented and is not pursued with a
low-cost IMU (FEAT-2). The IMU gives the camera attitude, the gyro heading carried between vision
fixes (`day_pkg/gyro_heading.py`) and liveness; vision gaps are bridged along the last measured
track with a growing sigma (`day_pkg/vision_nav.py`).

### Important truths (do not "fix" these without discussion)
- **Measured accuracy lives in `docs/VALIDATION_STATUS.md`.** Day vision: local feature matching
  (default) 32/33 benchmark frames within 9 m — aerial frames from another source, NOT yet NAVERA's
  camera; the former DINOv2 retrieval (fallback) ~440 m median. Never quote a better number
  without a new measurement.
- **NetVLAD is present but UNTRAINED** in the day pipeline — retrieval is **DINOv2-only**. Don't assume NetVLAD works.
- **`vision_pkg/` is LEGACY** (old prototype). Treat as deprecated; do not build new work on it.
  Its `dataset/frames_gps/` frames ARE correctly labelled; `camera_pkg/data/day` frames are NOT.
- **Celestial** needs a measured camera attitude (IMU, not wired yet); without it cn reports no
  position. Time comes from the system clock (RTC-backed).
- **STHN geometry is fixed by its weights** (one_stage: corr_level 4, database 1536, resize 256).

---

## 4. ENVIRONMENT & HOW TO RUN

Deployment runs **on the host** (systemd services, `deploy/README.md`), not in a container.

```bash
source /opt/ros/humble/setup.bash
colcon build --symlink-install          # builds the 12 NAVERA packages (vendored/legacy dirs are COLCON_IGNOREd)
source install/setup.bash
set -a; . /etc/navera/navera.env; set +a   # data paths, ROS_DOMAIN_ID, ROS_LOCALHOST_ONLY, token
ros2 launch simulation_web day_sim.launch.py     # or night_sim / cn_sim
# Operator view: http://<jetson-ip>:8181/operator
navera_tools/run_tests.sh --integration          # the test suite — run it before every commit
```

- Large data (MBTiles map, tile dataset, STHN weights, model caches) is not in git; its paths
  come from the `NAVERA_*` / `DAY_DATASET_DIR` / `TORCH_HOME` environment variables.
- GPU check: `python3 -c "import torch; print(torch.cuda.is_available())"` → must be True.
- `Dockerfile.navera` and `docker/`, `scripts/` are Isaac ROS **development-container** tooling,
  kept for development only.

---

## 5. OPTIMIZATION TARGETS (GPU / Jetson)

When asked to optimize, prefer in this order:
1. **TensorRT** conversion: PyTorch → ONNX → `.engine` via `trtexec` (engine is hardware-specific, build ON the Jetson, never commit it). Expected speedups: STHN ~4–5×, DINOv2 ~5×.
2. **Mixed precision (fp16)** where accuracy allows.
3. **Memory discipline:** stay within the 8 GB envelope. Avoid loading two heavy models at once.
4. **I/O & preprocessing**: batch, reuse buffers, avoid recomputing descriptors (cache exists for DINOv2).

Always report before/after numbers (latency ms/frame, memory MB, accuracy MAE) when optimizing.

---

## 6. CODE STANDARDS

- **Python:** PEP 8, type hints on public functions, docstrings (module + function), no dead code,
  no commented-out blocks left behind. Logging via ROS2 logger, not bare `print`.
- **ROS2:** clear node names, parameters declared with defaults + descriptions, QoS explicit,
  topics namespaced, launch files parameterized (no hardcoded paths).
- **Files:** remove `.bak`, `.backup`, `.BACKUP`, `_old`, duplicate variants — but ARCHIVE first if unsure.
- **Each package:** a `README.md` describing purpose, nodes, topics (in/out), parameters, how to run.
- **No secrets in code or docs.** Ever.

---

## 7. WORKFLOW FOR EVERY TASK

1. **Understand:** read the relevant files before changing anything.
2. **Branch:** `git checkout -b <task-name>` off `main`.
3. **Change:** make the smallest coherent change.
4. **Verify:** does it still build? does the pipeline still launch? (run it if possible).
5. **Commit:** clear message, one concern.
6. **Report:** summarize what changed, what was verified, what's the risk, what's next.

If a change is risky or large, describe the plan and ask before executing.

---

## 8. CURRENT PRIORITIES (the roadmap — tracked by the certification dossier)

Verified requirements are done. The roadmap = the not-yet-done items.

### Done — validated on real hardware
- **Clock node** (`rtc_pkg`, DS3231 on I²C bus 1, addr `0x68`). Validated by a full power-cycle
  reboot on the Jetson (2026-07-14): the `navera-rtc` systemd service comes up on its own,
  the node reports `valid:true` and `lost_power:false` **after** the reboot (the CR2032 backup
  battery holds the clock through the power cut), and measured drift is **-0.148 s vs NTP**.
- **Automatic startup** — 6 systemd services then, 10 units today (validated by reboot 2026-07-15; the restart
  mechanism was reworked 2026-09-28 and needs a new reboot validation).

### Done — bench-verified 2026-09-28 (not on a vehicle)
- Localization maths corrected (day tile centres, night STHN contract and weights, celestial
  geometry/precession), honest dead-reckoning, GPS parsing/recovery, estimator de-dup and
  clock checks, web control token, honest operator view. See `docs/VALIDATION_STATUS.md`.
- Vehicle outputs (`navera_output`: NMEA GGA/RMC, MAVLink GPS_INPUT) accepted by ArduPilot
  Copter-4.5 SITL (`navera_tools/tests/sitl_ardupilot.py`).
- STHN on the GPU (~225 ms/frame): on JetPack 6 the small homography solves run on the CPU
  automatically because the Jetson torch build cannot load CUDA linear algebra.
- Night: frames scaled/oriented from altitude + `camera_hfov_deg` + heading, motion gate
  (LOC-16). Celestial: solver fixed, IMU attitude at exposure (CN-1/2). Synthetic data only.

### Not yet done
- **Validate on real data** (camera + GPS + IMU recorded together; real thermal for STHN;
  real sky for celestial). ← the blocker for every accuracy claim
- **Day vision redesign** — done in code (local feature matching, `day_pkg/local_matcher.py`):
  32/33 benchmark frames within 9 m; **to measure with NAVERA's real camera**.
- **Wire the IMU** → dead-reckoning (heading/speed); its attitude now feeds celestial and night heading.
- **Real thermal and real sky data** for night and celestial (both now run end to end on
  synthetic data: night 6–13 m, celestial 24–119 km, bounded by the IMU).
- **Optimize** models with TensorRT (latency).
- **Clean & document** (per-package READMEs, remove legacy/orphans).

Never claim these are done until measured/verified. Update this list as items complete.
