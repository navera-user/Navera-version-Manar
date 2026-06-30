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

Three localization pipelines share ONE chain. Only one runs at a time.

```
camera_pkg (source) → [day|night|cn]_subscriber (localizer) → simulation_web bridge (HTTP :8181) → browser (Leaflet)
```

### ROS2 packages
| Package | Executable | Role |
|---------|-----------|------|
| `camera_pkg` | `camera_publisher.py` | Frame source (CSV+image replay or live camera), sync protocol |
| `day_pkg` | `day_subscriber.py` (+`day_localizer.py`) | Day localization — **DINOv2** retrieval vs satellite |
| `night_pkg` | `night_subscriber.py` (+`night_localizer.py`) | Night localization — **STHN** homography |
| `cn_pkg` | `cn_subscriber.py` | Celestial — astrometry.net plate-solving |
| `gps_pkg` | `gps_node.py` | GPS driver (NMEA serial) — **publishes, 0 subscribers (not yet wired)** |
| `imu_pkg` | `imu_node.py` | IMU driver (GY-87 I²C) — **publishes, 0 subscribers (not yet wired)** |
| `simulation_web` | `navera_web_bridge.py`, `navera_stellar_bridge.py` | ROS→HTTP bridge, dashboard |

### Communication protocol (camera ↔ localizer)
- **Start gate:** mission starts on command (`camera/start`, latched Bool).
- **Handshake:** camera waits for `localizer_ready` (latched Bool) before frame 1.
- **Back-pressure:** camera sends next frame only after `frame_done` ack (Int32). Strictly serial.
- Forward data: `image_raw` (Image), `frame_meta` (String/JSON). Output: `position_estimate`
  (NavSatFix), `*_status` (String/JSON: source, score, jump_m).
- QoS: data topics RELIABLE depth 10; ack depth 1; ready/start TRANSIENT_LOCAL (latched).

### Source-selection hierarchy (per frame)
`GPS (if valid) → vision (day/night) → celestial → inertial dead-reckoning`. First reliable source wins.

### Important truths (do not "fix" these without discussion)
- **NetVLAD is present but UNTRAINED** in the day pipeline — retrieval is **DINOv2-only**. Don't assume NetVLAD works.
- **`vision_pkg/` is LEGACY** (old prototype). Treat as deprecated; do not build new work on it.
- **gps_node / imu_node publish into the void** (0 subscribers). Wiring them is a real feature, not a bug fix.
- **Celestial** uses manual tilt/azimuth defaults; accurate celestial needs the **clock + IMU** (not yet integrated).

---

## 4. ENVIRONMENT & HOW TO RUN

```bash
# Start container (from host)
cd ~/isaac_ros_common && ./start_navera.sh
# Inside container:
source /opt/ros/humble/setup.bash
source /workspaces/isaac_ros-dev/install/setup.bash
# Run a pipeline:
ros2 launch simulation_web day_sim.launch.py     # or night_sim / cn_sim
# Dashboard: http://<jetson-ip>:8181/
```

- The workspace `~/isaac_ros_common` is mounted as `/workspaces/isaac_ros-dev` inside the container.
- Build with `colcon build` only when needed; `install/` is the compiled output (gitignored).
- GPU check inside container: `python3 -c "import torch; print(torch.cuda.is_available())"` → must be True.

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

Verified requirements are done. The roadmap = the not-yet-done items:
- **Clean & document** the codebase (remove legacy/dupes, add per-package READMEs, docstrings). ← start here
- **Wire real sensors:** gps_node → pipelines, imu_node → dead-reckoning + celestial.
- **Add a clock node** for accurate time reference (needed for celestial).
- **Optimize** models with TensorRT (latency).
- **Automatic startup** on boot (clean systemd service, not the old broken crontab).
- **Standardized vehicle-integration interface** (UAV/USV/UGV).
- **Validate on real data** (real thermal frames for STHN, real sensors for celestial).

Never claim these are done until measured/verified. Update this list as items complete.
