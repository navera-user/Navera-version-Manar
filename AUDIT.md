# NAVERA Codebase Audit (read-only)

> **Historical document (2026-06-30).** The current status of every finding is tracked in
> [docs/ENGINEERING_BACKLOG.md](docs/ENGINEERING_BACKLOG.md).

> **Date:** 2026-06-30 · **Branch:** `produit-clean` · **Scope:** the 8 NAVERA ROS2 packages
> (`camera_pkg`, `day_pkg`, `night_pkg`, `cn_pkg`, `gps_pkg`, `imu_pkg`, `simulation_web`) plus the
> legacy `vision_pkg`. The vendored `isaac_ros_*` / `isaac_common*` packages and
> `night_pkg/STHN/` (third-party model repo) were **not** line-audited.
>
> This document is **descriptive only** — no source files were modified. It is the input to the
> "Clean & document" roadmap item. Nothing here has been changed or deleted yet.

---

## Executive summary

- **The product genuinely works** as three independent chains sharing one protocol:
  `camera_pkg → [day|night|cn]_subscriber → web bridge (:8181) → browser`. Only one mode runs at a time.
- **The live path of every package is small and clean.** The clutter is concentrated in:
  (a) `.bak`/`.backup`/`.BACKUP` strays, (b) orphan alternate HTTP/Flask front-ends that duplicate the
  ROS path, (c) the legacy `vision_pkg`, and (d) the nested `STHN/STHN/` + `.git` bloat.
- **No hardcoded secrets / API keys were found** anywhere (full scan of `.py/.json/.yaml/.cfg`). Good.
- **`.gitignore` is solid** — no forbidden large artifacts are tracked (320 files tracked; `.mbtiles`,
  `torch_jetson/`, weights, etc. all excluded). **Two exceptions live in git:** `mission.zip` (4.2 MB)
  and `NAVERA_FULL_DOCUMENTATION.pdf` (673 KB) are tracked binaries that should not be.
- **Three systemic patterns repeat in every package** (consolidated below, not re-listed per package):
  1. **Implicit QoS on the two output publishers** (`position_estimate` / `*_status`) — depth-`10` int
     shorthand instead of an explicit `QoSProfile`.
  2. **`package.xml` build-type inconsistency** — every package declares
     `<buildtool_depend>ament_cmake_python</buildtool_depend>` while being a pure `ament_python`
     (`setup.py`) package. Harmless today, wrong on paper.
  3. **Console entry points named with a `.py` suffix** (e.g. `day_subscriber.py=…:main`) to match
     `executable='…py'` in launch files — unusual but internally consistent; **do not "fix" naively**,
     it would break every launch file.

---

## Cross-cutting findings (apply to all packages)

### Repository / git hygiene
| Item | Status | Action |
|------|--------|--------|
| `.gitignore` | Solid; excludes weights, mbtiles, caches, `torch_jetson/`, `.bak`, etc. | Keep. |
| `mission.zip` (4.2 MB) | **Tracked binary at root** | Remove from git, archive externally. |
| `NAVERA_FULL_DOCUMENTATION.pdf` (673 KB) | **Tracked binary** | Keep `.md`, drop the `.pdf` from git. |
| Committed `__pycache__/*.pyc` | Present in `cn_pkg/nodes`, `night_pkg`, `day_pkg`, `simulation_web` (already gitignored, but on disk) | Delete from working tree. |
| `night_pkg/STHN/STHN/` (24 MB) + `STHN/.git` (21 MB) + `STHN/STHN/.git` | Untracked bloat **and** a correctness hazard | Remove nested copy + `.git` dirs (see night_pkg §5). |

### `sousse_satellite.mbtiles` — the load-bearing data asset (TWO copies, absolute paths)
The satellite basemap is referenced by **absolute path in ~7 live files** (`simulation_web` bridges +
all three `*_sim.launch.py` + `night_subscriber.py`/launch). There appear to be **two copies on disk**:
a ~10 GB file at repo root (`sousse_satellite.mbtiles`) and one under
`vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles`. Both are gitignored (not committed). This is
the single most fragile dependency in the system: **any move/clean of `vision_pkg` or the root file
breaks day/night/cn navigation.** Recommended fix (roadmap): relocate ONE canonical copy to a neutral
shared data dir (e.g. `data/` or an env var `NAVERA_MBTILES`), update all references, delete the duplicate.

### Output-publisher QoS (every localizer + bridge)
All localizer nodes publish `position_estimate` (NavSatFix) and `*_status` (String) with bare `depth=10`
(implicit RELIABLE/VOLATILE) instead of an explicit `QoSProfile`. The subscribers/bridges also use
depth-10 defaults, so it *currently matches* — but it's an undocumented contract. Make these explicit.
Exact lines: `day_subscriber.py:140-141`, `night_subscriber.py:160-161`, `cn_subscriber.py:112-113`,
`camera_publisher.py:154-155`, `navera_web_bridge.py:105-106`, `navera_stellar_bridge.py:101-102`.

---

## camera_pkg

### Role
Frame source / sensor publisher (replaces the legacy host PC). ONE reusable node
`camera_publisher.py` launched 3× under separate namespaces (thermal / celestial / day). Replays a flight
CSV + image folder (or a live CSI/USB camera). Publishes `image_raw`, `camera_info`, `gps` (NavSatFix),
`frame_meta` (String/JSON). Implements the start gate, the `localizer_ready` handshake, and the
`frame_done` ack back-pressure. Launch files: `all_cameras` (includes the 3), `day/celestial/thermal`.

### Files to archive
- `nodes/camera_publisher.py.bak` — **materially older**: lacks the entire ready-handshake
  (`wait_for_ready`, `ready_topic`, `_wait_for_ready`, min-cadence sleep). Archive.
- `launch/day.launch.py.bak`, `launch/thermal.launch.py.bak` — both **differ materially** from live
  (missing the ready/cadence/flow-control args). Archive. (No `celestial.launch.py.bak` — asymmetric set.)

### Code smells
- Unused import `base64` (line 21).
- **Dead publisher**: `pub_info` for `camera_info` (line 153) is created but **never published**; the
  `CameraInfo` import (line 29) exists only for it.
- Redundant `import time as _time` inside `__init__` (line 177) shadowing the top-level `time`.
- Blocking `time.sleep(startup_delay)` in the constructor (lines 175-179) — blocks node construction.
- No-op ternary at line 483 (`enc = … if … != "bgr8" else "bgr8"`).
- **No bare `print()`** — logging is clean. Comments are mixed FR/EN.

### Hardcoded paths / params / QoS
- `ready_topic` default `"/day/localizer_ready"` baked into the generic node (line 97);
  `thermal.launch.py:38` points it at a **non-existent `/night/...` namespace** (latent — `wait_for_ready`
  is `false` there).
- `device` default `/dev/video0` (line 108, live-camera path only).
- No filesystem absolute paths in code (CSV/images resolved via `get_package_share_directory` in launch) — good.
- All `get_parameter` calls have matching `declare_parameter` (lines 80-112) — clean.
- Implicit QoS: `pub_gps` (154), `pub_meta` (155). `image_raw`/`camera_info`/start/ack/ready use explicit QoS.

### Risks
- **Handshake deadlock**: `day.launch.py` sets `wait_for_ready=true` + `ready_timeout_s=0.0` (wait forever)
  against the hardcoded `/day/localizer_ready`. Wrong topic/namespace ⇒ frame 1 never streams. The ready
  sub is TRANSIENT_LOCAL specifically to catch an early ready — don't change its durability.
- **Latched `camera/start`** (TRANSIENT_LOCAL depth-1) and the **ack back-pressure** (`frame_done` Int32,
  RELIABLE depth-1, 30 s timeout) are the heart of the serial protocol — topic/type/QoS changes stall it.
- `image_raw` must stay RELIABLE/KEEP_LAST/depth-1 to match `day_subscriber` (switching to BEST_EFFORT
  breaks QoS matching).
- GPS validity coupling: NavSatFix carries **NaN** lat/lon when invalid (lines 466-467) — downstream must
  tolerate NaN. Header stamps are wall-clock at publish, not CSV capture time.

### GPU/memory
- Low relevance — runs at ~0.05-0.1 fps (one frame/10-20 s); CPU `imread`+`cv2_to_imgmsg` is fine.
- If live capture is ever enabled at real rates, the GStreamer path copies off-GPU to host BGR
  (lines 67-69), forfeiting zero-copy — keep frames in NVMM / use NITROS there. Remove dead `pub_info`.

---

## day_pkg

### Role
Day visual localization. Live frame → DINOv2 (GeM-pooled, L2-normalized) → cosine match vs a pre-built
descriptor cache of zoom-17 satellite tiles, optionally restricted to a spatial circle around the last
anchor. **NetVLAD/ResNet50 is built and loaded but UNUSED for retrieval** (`RETRIEVAL_BACKBONE="dinov2"`),
as documented.

| File | Role | Wired? |
|------|------|--------|
| `nodes/day_subscriber.py` | Live ROS2 localizer node (handshake, ack, anti-jump/dead-reckon) | **YES** (entry point + launch) |
| `nodes/day_localizer.py` | `DayLocalizer` engine library (`predict()`) | YES (imported) |
| `nodes/day_node.py` | HTTP tile-server + process manager (port 8181) | **NO — orphan, partly broken** |
| `nodes/mbtiles_extractor.py` | Offline MBTiles→JPEG tool | **NO — orphan utility** |
| `nodes/receiver_aonly.py` | Standalone Flask "A-only" pipeline (819 lines, own models) | **NO — orphan** |

### Files to archive
- `nodes/day_subscriber.py.bak`, `nodes/day_localizer.py.bak`, `launch/day_subscriber.launch.py.bak` —
  all pre-"spatial window" / pre-"DINOv2-only" versions, superseded. Archive.
- `nodes/day_node.py` — orphan **and broken**: launches `PKG_DIR/"receiver.py"` (line 219) which **does
  not exist**, and `receiver_aonly.py` via a wrong path; references cross-package receivers. Archive.
- `nodes/mbtiles_extractor.py` — orphan, hardcoded dead `/workspaces/...` paths. Move to `tools/`.
- `nodes/receiver_aonly.py` — orphan, reachable only via the broken `day_node.py`. Archive.

### Code smells
- `day_localizer.py`: **`print()` instead of ROS logger throughout** (lines 164,167,169,171,176,186,192,
  199-210,221) — this is a library shared by the ROS node, so they bypass rclpy.
- **Dead code in the live retrieval path**: `fused_reranking` (139-152), `gps_consistency_score`
  (128-137), and the `top_k=50` param of `predict()` (232) are unused now (the `.bak` used them).
- `BackboneNetVLAD`/`NetVLAD`/`GeM` ResNet50 (77-98) only used in `_build_cache`.
- `day_subscriber.py`: `SCORE_MIN=0.0` (line 59) makes the dead-reckon branch (423-431) unreachable by
  config. Heavy emoji logging (cosmetic). No bare `print()` here.
- `receiver_aonly.py` (orphan): module-level side effects at import (model thread, dir/cache creation).

### Hardcoded paths / params / QoS
- **Good**: `day_localizer.py:11-44` resolves the dataset dir via `$DAY_DATASET_DIR` → ament share →
  source layout (robust). `day_subscriber.py` declares all ROS params (67-78).
- **Bad (all in orphans)**: `day_node.py:59` `HF_HOME=/usr/local/share/hf_cache`; `mbtiles_extractor.py:5-7`
  and `receiver_aonly.py:31,52-54` hardcode `/workspaces/isaac_ros-dev/...` (wrong root on this Jetson).
- Tuning constants `GSD_M_PER_PX`, `FOOTPRINT_MULT`, `ALTITUDE_MULT`, `R_MIN_M`, `R_MAX_M`, `SCORE_MIN`
  (lines 54-59) are module constants — candidates for `declare_parameter` so the field can tune without rebuild.
- Implicit QoS: `pub_fix`/`pub_status` (140-141). Docstring says image is BEST_EFFORT but code uses
  RELIABLE (override explained at 126-127) — doc/code mismatch.

### Risks
- **Don't delete NetVLAD blindly**: `_build_cache` (203) still writes a `netvlad_descriptors` array into
  the cache `.npz`, so removing the ResNet50 load breaks cache *building* (not retrieval).
- **Descriptor-cache schema** (`netvlad_descriptors`, `dinov2_descriptors`, `coords`, `valid_indices`,
  CSV `filename`→`imageName` rename) is load-bearing — changing keys/alignment silently corrupts lat/lon.
  If the `.npz` is absent, the node rebuilds it at runtime (slow, loads both models).
- **Node↔lib contract**: `predict()` must keep returning `spatial`, `spatial_empty`, `radius_m`,
  `top5`, `predicted_lat/lon` — the node's spatial branch consumes them.
- Handshake: latched `/day/localizer_ready`; `frame_done` ack in a `finally` (242) for every outcome.

### GPU/memory (8 GB envelope)
- **Biggest win: stop loading the unused ResNet50/NetVLAD** (loaded permanently at `day_localizer.py:168`,
  never used for retrieval). Make it conditional on cache-build / diag only, then free. Saves ~100 MB + headroom.
- **Enable fp16 for DINOv2** — `USE_FP16=False` (line 58) leaves the autocast path dormant; `receiver_aonly`
  already runs fp16. Validate score/threshold parity first.
- **TensorRT / torch.compile** the DINOv2 ViT-S/14 forward (fixed 224×224) — cuts first-frame + steady-state.
- Descriptor caching is already the right pattern (only the query is encoded per frame). Keep it.
- Keep the orphan HTTP stack disabled — running it alongside `day_subscriber` loads a second model set ⇒ OOM.

---

## night_pkg

### Role
Night localization. Thermal frame + telemetry → if GPS valid, republish truth; if GPS lost, run STHN
homography (thermal↔satellite mosaic stitched from MBTiles) → NavSatFix; dead-reckon on low confidence.

| File | Role | Wired? |
|------|------|--------|
| `nodes/night_subscriber.py` | Live ROS2 node (handshake, ack, serial) | **YES** (entry point + launch) |
| `nodes/night_localizer.py` | `NightLocalizer` engine (mosaic + STHN forward) | YES (imported) |
| `nodes/night_receiver.py` | Flask HTTP server (port 5001), parallel non-ROS path | **NO — orphan** |
| `nodes/patch_localizer.py`, `nodes/patch_receiver.py` | One-shot source-rewriting scripts (already applied) | **NO — spent tooling** |

### Files to archive
- **Stray backups at package root**: `night_localizer.py.backup`, `night_localizer.py.BACKUP` (second
  differently-cased copy), `night_receiver.py.backup`.
- **More backups under `nodes/`** than expected: `night_subscriber.py.bak`, `…bak-prefp16`, `…bak-prelog`,
  `night_localizer.py.backup-003005`, `night_localizer.py.bak-prefp16`.
- **`STHN/STHN/`** — full nested duplicate of the vendored repo (24 MB), bloat **and** correctness hazard.
- **`STHN/.git` + `STHN/STHN/.git`** (~21 MB each) — vendor without `.git`.
- **`README_FIXED.md` vs `README.md`** — two divergent, both stale (reference a non-existent
  `ros2_night_node.py`, neither names the real `night_subscriber.py`). Consolidate to one.
- `test_night_standalone.py` — keep as a smoke test but it's orphan tooling. `__pycache__/` — committed bytecode.

### Code smells
- Unused imports: `night_subscriber.py:34-35` (`cv2`, `numpy` — decode goes via cv_bridge);
  `night_localizer.py:11` (`os`); redundant inner `import cv2` at `night_localizer.py:310`.
- **No bare `print()`** in the live node files. `print()` only in the spent `patch_*.py` and the standalone test.
- `night_localizer.py:386` `pass  # empty_cache disabled` (no-op placeholder); redundant nested
  `torch.no_grad` (342 + 388).
- **Silent error masking**: `night_subscriber.py:136-141` bare `except TypeError` re-builds the model
  *without* `conf_threshold`/`mixed_precision` — any unrelated TypeError silently downgrades the model.
- `night_localizer.py` logs via the Python `logging` module (not the ROS logger) — warnings may not reach rosout.

### Hardcoded paths / params / QoS
- Absolute `/home/navera/...` defaults for `sthn_dir`/`weights`/`mbtiles` in both `night_subscriber.py:60-65`
  and `night_subscriber.launch.py:24-28` (params, so overridable). `night_localizer.py:237` `save_dir="/tmp"`;
  lines 90-91 hardcoded Bing↔ESRI bias constants.
- Orphan `night_receiver.py` points at a **different** weights file (`model_best.pth` under `~/Desktop/...`)
  and a hardcoded fallback prior `35.8288/10.6360`.
- `sys.path.insert(0, …)` hacks to import vendored STHN (`night_localizer.py:137-139, 167-169`).
- Params are all declared, but `mixed_precision`, `dr_step_min_m`, `done_topic`, `ready_topic` are **not
  exposed in the launch file** (silently use code defaults).
- Implicit QoS: `pub_fix`/`pub_status` (160-161).

### Risks
- **Nested `STHN/STHN/` shadowing (highest risk).** `_load_model` does `sys.path.insert(0, sthn_dir)` then
  `rglob("local_pipeline/model/network.py")` (line 161) — with the duplicate present this returns **two**
  candidates and loads whichever the filesystem orders first, potentially pulling `update`/`corr` from the
  wrong tree. **Deleting `STHN/STHN/` removes the ambiguity** and is the single highest-value cleanup here.
- `sys.path.insert(0, …)` front-pollution makes generic module names (`update`, `corr`,
  `datasets_4cor_img`) resolve unpredictably if a second path is ever inserted.
- `load_state_dict(strict=False)` (line 298) — a mismatched checkpoint loads silently as a partly-garbage net.
- Heavy deps replaced with `MagicMock` (172-189) — a future STHN rev that actually calls one gets a mock, not an error.
- Handshake: `localizer_ready=True` is published only **after** model load; a load failure hangs the camera.
- Two weights conventions (`model.safetensors` vs `model_best.pth`) — easy to point at an incompatible checkpoint.

### GPU/memory
- **fp16 is partial** — autocast covers only `fnet1` + `update_block_4`; the cuSOLVER homography solve stays
  fp32, so today's fp16 gives only a fraction of the possible speedup.
- **No TensorRT** — CLAUDE.md expects ~4-5× for STHN; current path is eager PyTorch. Exporting the
  local_pipeline backbone to TensorRT/torch.compile is the biggest win.
- **No warmup** (302-303) → first real frame pays cuDNN-autotune cost. `empty_cache()` deliberately disabled
  ("crashes Jetson allocator") — fine given single-model/single-frame discipline. Per-frame `mean`/`std`
  tensors (319-320) could be cached on-device.

---

## cn_pkg

### Role
Celestial fix via astrometry.net `solve-field` plate-solving + a tilt/azimuth/UTC → ground lat/lon geometry
step. Uses **local `solve-field` binary, not the nova.astrometry.net web API** (so no API key exists to leak).

| File | Role | Wired? |
|------|------|--------|
| `nodes/cn_subscriber.py` | Live ROS2 node (geoloc + wcs modes, skip-if-busy worker) | **YES** (entry point + launch) |
| `nodes/solver.py` | Library: runs `solve-field` / shells to `drone_sky_prep.py`, regex-parses stdout | YES (imported) |
| `nodes/drone_sky_prep.py` | CLI compute core (Siril → solve-field → geometry) | YES (subprocess — **not** an orphan) |
| `nodes/celestial_node.py` | rclpy node that only serves an HTTPServer on port 5002 | **NO — orphan** |
| `nodes/receiver_stellar.py` | Standalone Flask app (port 5001), stale paths | **NO — orphan** |

### Files to archive
- `nodes/solver.py.backup` — stale (single `solve_image_b64`, different scale/timeout). Archive.
- `nodes/celestial_node.py`, `nodes/receiver_stellar.py` — orphan HTTP/Flask front-ends. Archive.
- `nodes/__pycache__/*.pyc` — committed bytecode, remove.
- **Duplicate config**: `nodes/astrometry.cfg` and `data/astrometry.cfg` are byte-identical; `setup.py`
  installs the `data/` one — the in-tree `nodes/` copy is redundant.
- Bundled `data/astrometry/*.fits` index sets are likely unused (cfg uses system `/usr/share/astrometry`
  + autoindex) — confirm before relying on them.

### Code smells
- Unused imports: `cn_subscriber.py:39` `numpy`; `solver.py:34` `WCS`; `drone_sky_prep.py:23,28`
  `get_constellation` (constellation hardcoded `"N/A"` at 298).
- **`drone_sky_prep.py` is print-only throughout** (CLI subprocess — defensible, BUT the live path
  regex-scrapes this stdout, which is fragile). `receiver_stellar.py` uses `print` for all logging.
  `celestial_node.py` correctly uses `get_logger()`.
- **Hardcoded magic numbers**: tilt `75.46` / azimuth `283.18` (calibrated to the sample `etoiles.jpeg`)
  appear as param defaults (`cn_subscriber.py:69-70`) and constants (`receiver_stellar.py:19-20`); an
  undocumented azimuth offset `+313.18` (`drone_sky_prep.py:236,241`); inconsistent scale ranges
  (`50/90` vs `50/70`). Hardcoded sample UTC `"2026-03-10 20:20:00"` (`cn_subscriber.py:71`).
- Bare `except:` (`drone_sky_prep.py:65`); duplicate `if not os.path.exists(TIF_OUT)` (125-126).
- **Runtime `pip install astropy --break-system-packages` on ImportError** (`drone_sky_prep.py:27`) —
  mutates the system environment mid-solve.

### Hardcoded paths / params / QoS
- **No secrets/API keys (scanned, clean).**
- **Two divergent `solve-field` invocations**: `/usr/local/astrometry/bin/solve-field` (absolute,
  `drone_sky_prep.py:142`) vs bare `solve-field` on `$PATH` (`solver.py:19`).
- `receiver_stellar.py:11-14` has **stale paths** that resolve to non-existent files (missing `/nodes/`,
  wrong image dir, cross-package `gps_status.json`).
- Hardcoded ports `5002` (`celestial_node.py:13`), `5001` (`receiver_stellar.py:155`); both bind `0.0.0.0`
  with CORS `*` (unauthenticated network exposure).
- `cn_subscriber.py` declares all its params (clean). `solver.py` scale/timeout hardcoded.
- Implicit QoS: `pub_fix`/`pub_status` (112-113). Comment says "depth-1 ONE-SHOT" but subs use depth-10 (mismatch).

### Risks
- **Stdout-regex coupling**: `solver.py:89-109` parses `drone_sky_prep.py`'s human-formatted banner
  (`"Latitude … °N"`). Any wording change silently breaks lat/lon extraction → `success:False`. **Do not
  "clean up" those prints.**
- **`match_score` is a hardcoded constant** (`0.95` geoloc / `0.99` wcs) — so `conf_threshold` only filters
  total failures, never real solve quality. Anyone tuning `conf_threshold` should know it's a near-no-op.
- Whole geoloc fix depends on correct tilt/azimuth/UTC; without `frame_meta` overrides it uses the sample
  values → confident-but-wrong position. The `313.18` offset is an undocumented mount calibration.
- Handshake: needs **both** image and meta to pair (no timeout/fallback if meta stops). Install copies
  `astrometry.cfg` next to `nodes/`; changing that copy logic breaks cfg discovery.

### GPU/memory
- None — `solve-field` + geometry are CPU-only. Minor: per-frame decode→re-encode→base64 round-trip
  (`cn_subscriber.py:144,197`) is wasteful but the celestial rate is slow. The tilt self-consistency scan
  (`drone_sky_prep.py:263-284`) is skipped on the live MANUAL path.

---

## gps_pkg

### Role
NMEA serial GPS driver. Node `gps_node` opens a serial port, parses NMEA (`pynmea2`) in a daemon thread,
publishes `/navera/sensors/gps_fix` (NavSatFix, from GGA) and `/navera/sensors/gps_vel` (TwistStamped,
from RMC). Event-driven (~1 Hz). **Publishes into the void — 0 subscribers** (not yet wired).

### Files to archive
- None. `test/` is empty despite `test_depend` entries in `package.xml` (dangling declaration).

### Code smells
- **No bare `print()`** — clean logging. No unused imports.
- Debug noise left in: line 45 `"READ LOOP RUNNING"`, line 52 raw-line dump every 30 lines; line 68 logs
  `"READ LOOP EXITED"` at **ERROR even on clean shutdown** (false error every normal exit); line 83
  `"No fix yet"` at info on every no-fix GGA (spammy before lock).

### Hardcoded paths / params / QoS
- Params declared: `serial_port` (`/dev/ttyTHS1`), `baud_rate` (9600); also in `config/gps_params.yaml`.
- Hardcoded (not params): serial `timeout=2` (34), topic names (29-30), `frame_id="gps"` (73,107),
  covariance model (HDOP fallback `2.0`, `(hdop*2)**2`, vertical `*4`, lines 90-92).
- Implicit QoS: both publishers depth-10 default (no `sensor_data`/BEST_EFFORT profile).

### Risks
- **Silent zombie on missing device**: `serial.Serial()` failure is caught, logged ERROR, and `__init__`
  `return`s — node stays alive via `rclpy.spin` doing nothing, **no retry/reconnect**.
- Device unplugged mid-run: `SerialException` ends the read loop permanently; node alive but mute.
- Parse/loop errors are caught (robust against malformed NMEA). `destroy_node` guards `self.ser`.

### Wiring readiness (roadmap)
- `NavSatFix` is well-formed: stamp, `frame_id`, `status`, and HDOP-derived `position_covariance` +
  `COVARIANCE_TYPE_APPROXIMATED` — consumable by `robot_localization`/`navsat_transform`. **Gap:** no-fix
  branch publishes `(0,0,0)` with `STATUS_NO_FIX` — consumers MUST check status.
- `gps_vel` (TwistStamped) only sets `linear.x` (speed), no covariance; `navsat_transform` doesn't consume
  TwistStamped — **likely unusable as-is**; convert to Odometry/TwistWithCovarianceStamped or drop.
- `frame_id="gps"` must exist in the TF tree before wiring.

---

## imu_pkg

### Role
GY-87 I²C driver. Node `imu_node` reads MPU6050 (accel/gyro), QMC5883L (mag), BMP180 (baro) on one bus via
`smbus2`, on a 10 Hz timer. Publishes `/navera/sensors/imu` (Imu), `/navera/sensors/mag` (MagneticField),
`/navera/sensors/altitude_baro` (Float64). **Publishes into the void — 0 subscribers** (not yet wired).

### Files to archive
- None. `test/` empty despite `test_depend` entries (dangling declaration).

### Code smells
- **No bare `print()`** — clean. All imports used.
- Dead computation: MPU temperature (line 77) and BMP `temp`/`pressure` (105,126) computed then discarded.
- `s16` helper redefined in 3 methods with differing byte order (intentional per datasheet endianness, but copy-paste).

### Hardcoded paths / params / QoS
- Params declared: `i2c_bus` (default 7), `publish_rate` (10.0); also in `config/imu_params.yaml`.
- Hardcoded: I²C addresses MPU `0x68`, BMP `0x77`, QMC `0x0D`; topic names; `frame_id='imu'`; scale
  constants and sea-level pressure `101325.0`.
- Implicit QoS: all three publishers depth-10 default.

### Risks
- **Most fragile of the two drivers — hard crash on startup if hardware absent.** `smbus2.SMBus()` (51),
  `_init_mpu6050` (67-68), and `_init_bmp180` (85) are **NOT** wrapped in try/except. Wrong bus number or a
  disconnected MPU/BMP raises during `__init__` and **crashes the node**. `_read_mpu6050` (71-81) is also
  unwrapped — a read failure propagates out of the timer callback. Only QMC + BMP-read + QMC-read are guarded.

### Wiring readiness (roadmap)
- `Imu`: stamp + `frame_id` + accel/gyro set; `orientation_covariance[0]=-1` correctly signals "no
  orientation" (REP-145). **Gap:** `linear_acceleration_covariance` / `angular_velocity_covariance` are
  **all-zeros** — robot_localization may treat zero as "perfectly certain" or reject. Set diagonals before fusion.
- Raw uncalibrated data (gyro bias, accel scale, mag hard/soft-iron not calibrated) — tuning roadmap item.
- `MagneticField`: usable but uncalibrated, zero covariance.
- `/navera/sensors/altitude_baro` is a bare `Float64` — **no header/stamp/frame_id**, not directly consumable
  by `robot_localization`; must be re-typed (e.g. PoseWithCovarianceStamped / Range) before wiring.

---

## simulation_web

### Role
ROS2→HTTP bridge + static Leaflet dashboard over MBTiles tiles. A bridge node runs an embedded
`http.server` on a daemon thread in the same process as the ROS node. One mode at a time.

| File | Role | Wired? |
|------|------|--------|
| `scripts/navera_web_bridge.py` | Day+night bridge (subs `*_status`/`position_estimate`, pubs latched `camera/start`; serves tiles/api on :8181) | **YES** (day_sim, night_sim) |
| `scripts/navera_stellar_bridge.py` | Celestial bridge (adds ra/dec/match_score) | **YES** (cn_sim) |
| `scripts/server.py` | Legacy static server on :8080 + heartbeat | **NO — legacy** |
| `launch/day_sim / night_sim / cn_sim` | The real entry points | YES |
| `launch/simulation_web.launch.py` | Runs legacy `server.py` | legacy |
| `launch/start_simulation.launch.py` | **Empty LaunchDescription — launches nothing** | dead |

### Files to archive
- `launch/night_sim.launch.py.bak`, `…bak-preoom`, `…bak-prefp16` — superseded (the `.bak` used port 8182;
  live uses **8181**).
- `resources/navera.html.bak`, `…bak_design`, `…bak-preorigin` — three stale dashboard copies (not served).
- `resources/navera_stellar.html` — **0 bytes**, dead (installed by glob but never referenced).
- `resources/navera_IMPROVED.html` — alternate dashboard, never served. Dead.
- `scripts/server.py` + `launch/simulation_web.launch.py` — legacy 8080 static path. Archive together.
- `launch/start_simulation.launch.py` — dead (empty).
- `data/*.log` (`vision_node.log`, `receiver.log`, `server.log`) + `data/flight_log.csv` — runtime logs
  checked in and installed via `setup.py data/*` glob. Remove/gitignore.
- `CMakeLists.txt` — ignored under `ament_python`, inconsistent with `setup.py` (see below).

### Code smells
- **No bare `print()`** — both bridges and `server.py` use `get_logger()`.
- **~90 lines of HTTP-handler code nearly duplicated verbatim** across the two bridges
  (`_send`/`_json`/`do_OPTIONS`/`_serve_static`/tile parsing). The two bridges are ~95% identical — a shared
  base module would remove the duplication.
- `self._point_a` is set but **never read** (dead field; anchoring works via `_gps_status` rewrite).
- Broad `except Exception: pass` in `do_POST` set_mission; `server.py:27` bare `except:`.

### Hardcoded paths / params / QoS
- **Hardcoded MBTiles absolute paths** in `_MBTILES_CANDIDATES` (`navera_web_bridge.py:51-54`,
  `navera_stellar_bridge.py:48-51`) and in every `*_sim.launch.py`; plus STHN absolute paths in
  `night_sim.launch.py:58-61`.
- Hardcoded port 8181 (bridges + launches; the "8182 night" only exists in the `.bak`). `server.py` 8080.
- **Hardcoded bind `0.0.0.0` + CORS `Access-Control-Allow-Origin: *`** on every response, no auth ⇒ anyone
  on the LAN can hit `POST /api/set_mission` (triggers camera rewind/start) and read live position. **Security
  concern for a fielded device.** Path-traversal guard is prefix-based (low risk).
- Implicit QoS on subscriptions (105-106 / 101-102). The `camera/start` publisher correctly uses
  RELIABLE + TRANSIENT_LOCAL (latched).
- **Build inconsistency**: `package.xml` declares `ament_python` build type but also `ament_cmake_python`
  buildtool + ships a `CMakeLists.txt`; the two installers disagree (CMake would ship all `.bak`). `setup.py` wins.

### Risks
- **Port 8181 shared by day/night/cn** — launching two modes at once ⇒ second bridge fails to bind ⇒ launch dies.
- **Topic-name + JSON-key contract** wired in 3 places each (subscriber launch param + bridge launch param +
  bridge default). The bridge hard-expects keys `success/lat/lon/error/reason/score/total_ms` (day) and
  `ra_deg/dec_deg/match_score` (stellar) — rename a topic or change the status schema ⇒ marker stuck at "idle".
- **Latched `camera/start`** drives the "Launch Mission" button — dropping the TRANSIENT_LOCAL durability ⇒
  camera never starts.
- Threading: ROS spin on main thread, HTTP `serve_forever` on a daemon thread; shared `_gps_status` guarded
  by `_state_lock`, SQLite by `_db_lock` (`check_same_thread=False`). Correct but fragile — don't remove a lock.
- `_on_fix` only fills when status is `idle` (intentional, so a real visual fix isn't clobbered).

### GPU/memory
- **None** — pure I/O glue. Tiles served as raw stored bytes from SQLite (no base64/re-encode on the hot path).
  `_db_lock` serializes tile fetches (minor throughput cap under heavy panning). No action needed.

---

## vision_pkg (LEGACY / deprecated)

### Role
The original GPS-denied prototype: replay a flight CSV, detect GPS loss (NaN), re-estimate position by
matching the camera frame vs satellite tiles using NetVLAD+DINOv2 (MobileNetV3/CosPlace fallbacks). Key
scripts: `vision_node.py` (ROS2 Lifecycle, 4-thread), `gps_localizer.py` (44 KB engine, in-RAM matching +
dead-reckoning), `receiver.py` (Flask), `build_trt.py` (TensorRT FP16+INT8 engine builder), plus
dataset-gen / simulation helpers.

### Is it truly unused?
**Code is dead; one data file is LIVE.** `setup.py` exposes only `vision_node`/`receiver`; **nothing outside
the package imports it.** BUT the live day/night/cn pipelines reference
`vision_pkg/vision_pkg/dataset/sousse_satellite.mbtiles` by **absolute path from ~7 files** — so the package
**cannot be deleted naively** without rehoming that mbtiles first.

### Files/dirs to archive
- `vision_node.py.bak`, `receiver_test.log` (empty), `__pycache__/` (incl. `server.cpython-310.pyc` — a
  deleted `server.py`). Empty `trt_models/`.
- `dataset/` — **~9.9 GB**, ~2636 JPG frames + the 9.7 GB mbtiles (+ `-shm`/`-wal`). Gitignored, NOT
  committed (only 6 small metadata files tracked). JPG frame folders are throwaway captures — archive out
  of the repo. **Keep the mbtiles** (relocate, see below).
- Redundant prototype docs (collapse to one): `GPU_OPTIMIZATION_GUIDE/INDEX.md`, `OPTIMIZATION_SUMMARY.md`,
  `GPS_LOSS_HANDLING/FIX_SUMMARY/FIX_APPLIED.md`, `QUICK_START(_GPS_FIX).md`, `DEPLOYMENT_CHECKLIST.txt`,
  stale `README.md`, `vision_pkg/TODO.md`.

### Reusable nuggets (salvage before archiving)
- **`build_trt.py`** — a real TensorRT recipe (ONNX export + FP16/INT8 with `Int8EntropyCalibrator2` +
  latency test). Worth porting into day/night/cn TensorRT work. It imports model classes from
  `gps_localizer.py`, so those defs must travel with it.
- **GPS-loss fallback logic** in `gps_localizer.py` (`localize_bytes()` zero-disk in-RAM matching,
  pre-normalized descriptors, windowed two-stage early-exit, dead-reckon-on-loss) — good reference for
  wiring real GPS loss into the new packages.
- Keep one consolidated GPU-optimization doc (Orin Nano FP16 / VRAM / batch-extraction guidance).

### Secrets / large files / red flags
- **No secrets found** (clean grep).
- **9.9 GB `dataset/` untracked** — repo not bloated, but a 9.7 GB mbtiles inside a "deprecated" package,
  referenced by absolute path from live code, is fragile.
- Stale `README.md`/`docker-compose.yml` reference a `server.py`/`navera.html`/`Dockerfile` that no longer exist.

### Recommendation
**Partial archive.** Archive all code + `.bak`/logs/pycache + empty `trt_models/` + JPG frame folders +
redundant docs. **First:** (1) salvage `build_trt.py` + model defs + one consolidated doc; (2) relocate
`sousse_satellite.mbtiles` to a neutral shared data dir and update all hard-coded references. Don't delete
the folder until the mbtiles dependency is rehomed.

---

## Root-level clutter (outside any package)

Tracked-but-questionable files at repo root:
- **`mission.zip` (4.2 MB)** — tracked binary; remove from git.
- **`NAVERA_FULL_DOCUMENTATION.pdf` (673 KB)** — tracked binary; keep the `.md`, drop the `.pdf`.
- `index.html` (126 KB, tracked) + `index.html.bak` (untracked), `server.js`, `navera_fakes.py`,
  `replay_mission.py`, `flight_log.csv`, `gps_status.json` — **none are referenced** by any package, launch,
  or startup script (grep clean). `navera_fakes.py` is a useful standalone rqt_graph dev tool (publishes the
  full 8-node graph without loading models) — keep it but label it a tool. The rest are prototype-era — archive.
- Live startup files to keep: `start_navera.sh`, `Dockerfile.navera`, `setup_night_deps.sh`, `README.md`,
  `ROS_TOPICS_AND_COMMUNICATION.md`, `NAVERA_FULL_DOCUMENTATION.md`, `VISUAL_LOCALIZATION_SUMMARY.md`.

---

## Recommended priorities

Ordered by value/risk. **Each is a separate branch + commit** (CLAUDE.md golden rule #5). None of these
changes have been made — this audit is read-only.

### P0 — Safe cleanup (low risk, do first)
1. **Archive all `.bak` / `.backup` / `.BACKUP` strays** across every package (move to `archive/`, don't
   delete). Biggest offenders: `night_pkg` (8 strays incl. a `.BACKUP` dupe), `day_pkg` (3), `camera_pkg` (3),
   `simulation_web` (6 launch/html), `cn_pkg`, `vision_pkg`. All are already gitignored.
2. **Remove the nested `night_pkg/STHN/STHN/` duplicate and the `STHN/.git` dirs** (~66 MB). This also kills
   the `rglob` model-shadowing hazard (night_pkg §5) — highest correctness value of any cleanup.
3. **Remove committed `__pycache__/*.pyc`** from `cn_pkg/nodes`, `night_pkg`, `day_pkg`, `simulation_web`.
4. **Drop `mission.zip` + the `.pdf` from git**; archive `data/*.log`, dead/empty HTML resources, the
   `start_simulation.launch.py` no-op, and the unreferenced root prototype scripts.
5. **Consolidate duplicate docs**: `night_pkg` README ×2 → 1; `cn_pkg` `astrometry.cfg` ×2 → 1; `vision_pkg`
   8 docs → 1.

### P1 — Documentation (the roadmap's "start here")
6. **Write a per-package `README.md`** (purpose, nodes, topics in/out, params, how to run) — none exist for
   the live packages; CLAUDE.md §6 requires them. Use this audit's "Role" sections as the seed.
7. **Mark orphans explicitly** (move to `archive/` or a clearly-named `tools/`): `day_node.py`,
   `receiver_aonly.py`, `mbtiles_extractor.py`; `cn` `celestial_node.py`, `receiver_stellar.py`;
   `night` `night_receiver.py`, `patch_*.py`. They duplicate the live ROS path and are a maintenance trap.

### P2 — Correctness / quality (medium risk — verify pipeline after each)
8. **Rehome `sousse_satellite.mbtiles`** to a neutral shared dir behind an env var / param, update the ~7
   absolute-path references, delete the duplicate copy. Unblocks archiving `vision_pkg` and de-risks the
   single most fragile dependency. **Run all three pipelines after.**
9. **Make output-publisher QoS explicit** on all `position_estimate`/`*_status` publishers (cross-cutting §).
10. **Fix `imu_node` startup crash** — wrap `SMBus()` + MPU/BMP init in try/except with graceful degradation
    (prerequisite before it can be wired without taking down a launch).
11. **Tidy logging**: route `day_localizer.py` and `night_localizer.py` through the ROS logger (not `print`/
    `logging`); demote `gps_node` false-ERROR-on-clean-exit and debug spam.
12. **Reconcile `package.xml` build type** (drop `ament_cmake_python` buildtool dep) in all 8 packages.
13. **Remove dead code**: `camera_pkg` dead `pub_info`/`base64`; `day_pkg` `fused_reranking`/`gps_consistency`;
    unused imports flagged per package.

### P3 — Feature work (tracked separately on the roadmap, NOT cleanup)
14. **Wire `gps_node`/`imu_node`** into the pipelines — first fix their message completeness (covariances,
    `altitude_baro` needs a stamped type, `gps_vel` likely needs Odometry). Real feature, not a bug fix.
15. **Stop loading the unused NetVLAD/ResNet50** in `day_pkg` (conditional-load + free) — frees VRAM headroom.
16. **TensorRT** for STHN (expected ~4-5×) and DINOv2 (~5×) using the salvaged `build_trt.py` recipe;
    enable/complete fp16 where accuracy allows. **Measure before/after** (CLAUDE.md golden rule #6).
17. **Harden the web bridge** for fielded use: bind to localhost or add auth, tighten CORS — currently
    `0.0.0.0` + `*` lets any LAN host trigger `set_mission`.

### Do-NOT-touch list (would break the working system)
- The camera↔localizer **protocol**: latched `camera/start`, `localizer_ready` handshake, `frame_done` ack,
  and the exact QoS (RELIABLE/KEEP_LAST/depth-1 image, TRANSIENT_LOCAL latches).
- `cn_pkg` **stdout banner format** in `drone_sky_prep.py` (regex-scraped by `solver.py`).
- `day_pkg` **descriptor-cache `.npz` schema** and CSV column rename.
- The single-mode **port 8181** assumption and the topic-name/JSON-key contract between subscribers and bridges.
- The `.gitignore` large-file exclusions.
