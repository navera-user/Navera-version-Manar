# NAVERA — Safety analysis: hazard log and FMEA

Status 2026-10-21, code at `acd37fd` (branch `work/cert-deploy-2026-10-21`). Sources: the code
(cited as `file::symbol`), [VALIDATION_STATUS.md](../VALIDATION_STATUS.md),
[ENGINEERING_BACKLOG.md](../ENGINEERING_BACKLOG.md), [ARDUPILOT_INTEGRATION.md](../ARDUPILOT_INTEGRATION.md),
the git log, and the shared problems log "NAVERA — problems found" (IDs **B**n bugs, **D**n
design limits, **C**n documentation, **F**n test and flight observations). Requirement IDs
(NAV-…) are in [REQUIREMENTS.md](REQUIREMENTS.md).

**Scope and role.** NAVERA is an *advisory / substitute position source*: it feeds an autopilot
(ArduPilot `GPS_INPUT` or NMEA) that keeps its own EKF and failsafes. The top-level hazard is
**the vehicle is given a wrong position it trusts** (integrity), ahead of **the vehicle is given
no position** (availability — the autopilot's own failsafe then acts, by design, F2).
NAVERA has **not flown**: every likelihood below is a judgement from simulator, bench and
public-data evidence, not a field rate.

## 1. Method

- One row per failure mode of a component or of its environment (camera, vision, map, GPS,
  clock, IMU, timing, compute, power, autopilot configuration, storage).
- **Effect** at the vehicle, **detection** and **mitigation in code** (with the location),
  **evidence level** of the mitigation (A analysis · UT test · SIM simulator/SITL · BENCH real
  NAVERA hardware on a bench · PUB public real data · HW hardware in role · FLT flight — none).
- **Severity** (UAS, after ED-280 / SORA language): **Cat** loss of control over people /
  fly-away; **Haz** large position error accepted by the autopilot (vehicle leaves its corridor);
  **Maj** loss of navigation → autopilot failsafe (land / hold), mission lost; **Min** degraded
  accuracy inside the stated sigma.
- **Residual risk** after the mitigations: **High** (not acceptable for a product claim —
  must be closed before a flight campaign without a safety pilot), **Medium** (acceptable for
  supervised tests with a safety pilot and GPS available as reference), **Low**.

## 2. Top 10 hazards (residual risk ranked)

| # | Hazard | Worst credible effect | Residual | Why it is not lower |
|---|---|---|---|---|
| H-07 | Slow GPS spoof where vision cannot match (sea, desert, night without thermal) | Haz: vehicle dragged 60–390 m+ while NAVERA states FIX | **High** | every spoof check needs an independent source with a stated sigma (D1); no inertial navigation (FEAT-2) |
| H-13 | Autopilot misconfigured (`EK3_SRC1_POSZ = 3`, velocity sources, `GPS_AUTO_SWITCH`) | Cat: EKF height −277 m in 20 s, vehicle climbs to 825 m (SITL) | **High** | NAVERA cannot read or enforce autopilot parameters; documentation only |
| H-01b | Camera image frozen (same picture delivered again) | Haz: a static vision fix repeated as fresh; with GPS trusted, the growth test may refuse the GOOD GPS | **Medium** | frame-content freeze detector + UT (NAV-SAF-19); not yet seen on a real stuck driver |
| H-03 | Wrong night (thermal) fix accepted | Haz if forwarded | **High** (unvalidated) | 0 wrong accepts is on synthetic grey renders only; real LWIR never run (B4/B14, D22, F24) |
| H-11 | Compute overload / out of memory / thermal throttling | Maj: OOM kill ends navigation (F5); stale fixes | **Medium** | compute health monitor + degraded flag (NAV-SAF-21, UT); swap file made by install.sh and warned at boot, OOM order and memory caps in the units (NAV-PERF-06, UT; to run as root on a box); integrity kept by freshness windows |
| H-02 | Wrong day-vision fix accepted | Haz if forwarded: 100–650 m jumps (F16 tilted camera, F20 shake) | **Medium** | 1 / 2599 > 100 m on real drone data (PUB) but 2–7 wrong fixes per run under shake on the bench; F16/F20 open |
| H-08 | Clock wrong (no battery RTC, F27) | Haz for celestial (≈28 km per minute of error, thousands of km at 16 h); wrong GPS time sent to the autopilot | **Medium** | celestial now solves only on a trusted time (NAV-SAF-20, UT); GPS_INPUT / NMEA time still from the system clock; a box can lack the DS3231 |
| H-10 | Latency mismatch camera ↔ position | Haz/Min: along-track error (1.71 s uncompensated: 39.8 m at 80 m/s, F9) | **Medium** | per-camera delay is a setting / online fit; `GPS_DELAY_MS` recommendation not verified |
| H-12 | Power loss / brown-out / reboot in flight | Maj: NAVERA silent ≥ boot time; GPS-denied restart needs a prior | **Medium** | boot-to-first-fix time never measured; reboot test of today's restart mechanism pending (DEP-14) |
| H-09 | IMU bias / wrong heading / wrong mount | Haz/Min: day straightening error (4° at 300 m → 11 m median), night heading misses, celestial ~111 km/° | **Medium** | heading reference not checked on the real BNO085 (IMU-3); covariances are datasheet values |

Below them: H-01a camera loss (Medium → Low for integrity), H-04 wrong celestial fix (Low:
never forwarded), H-05 outdated map (Medium availability, Low integrity), H-06 fast spoof (Low),
H-14 storage full (Low), H-15 integrator settings (Medium), H-16 simulation on a live box (Low).

## 3. FMEA / hazard log

### H-01 Camera loss or freeze

| | |
|---|---|
| Failure modes | (a) device lost / USB reset / no frames; (b) frames frozen: driver or stream returns the same image while the vehicle moves (Insta360 IMU feed stopped after 50 samples while video went on, F14) |
| Effect | (a) day/night vision stops → NAVERA falls back or NO_FIX → autopilot failsafe (Maj). (b) a stale picture is matched as a fresh frame; repeated agreeing fixes can re-acquire a wrong track (`vision_nav`: two agreeing fixes re-acquire); while GPS is trusted the vision–GPS offset grows with the vehicle's motion and the growth test can **refuse a good GPS** (Haz) |
| Detection | (a) `camera_pkg/camera_pkg/nodes/live_camera.py::LiveCamera._grab_loop`: open failure or > 50 failed grabs → node exits → launch exits → `Restart=always`; estimator freshness `day_timeout_s` 5 s (`EstimatorNode._eval_source`). (b) frame content: `navera_common/health.py::FrozenFrameDetector` in `LiveCamera._check_frozen` — time not advancing, picture bit-identical, or nearly identical while IMU / GPS say the vehicle moved (`LiveCamera._moved`); attitude freeze: `LiveCamera._on_imu`, `FrozenSampleDetector` (IMU) |
| Mitigation | (a) restart + fallback chain (`EstimatorNode._select`), output "no fix" / bounded bridge 10 s (`navera_output/policy.py::bridge`). (b) the frame is published unusable ("camera image frozen: …"): day / night / celestial publish no position for it (`cn_subscriber.py::CNSubscriber._process_frame`); `<ns>/camera_health` reports it; a camera device frozen > 20 s exits for a restart; the first new picture ends it (NAV-SAF-19) |
| Evidence | (a) SIM: "GPS jammed + camera failed → NO FIX → autopilot failsafe"; UT `camera_pkg/test/test_gst_capture.py::test_a_bad_pipeline_is_not_opened`, `navera_tools/tests/test_live_camera.py`. (b) UT `navera_tools/tests/test_live_camera_frozen.py`, `test_health.py`, `cn_pkg/test/test_cn_gates.py` — not yet on a real stuck driver |
| Residual | (a) **Medium** (availability; integrity protected). (b) **Medium** (detector tested in UT; not yet seen on a real stuck driver / RTSP stall) |
| Open items | O-1 (problems log D24): done in code + UT (NAV-SAF-19) — reproduce a real stall (unplug / RTSP pause) on the box; O-2: re-check of F14 (IMU feed dead while video runs) on the product driver |

### H-02 Wrong day-vision fix accepted

| | |
|---|---|
| Failure modes | wrong place matched (repetitive texture, old imagery), wrong pose (VL-1), wrong height/scale, blur/shake (F20), tilted camera near a screen (F16), timing (F9) |
| Effect | position off by 100–650 m with a small stated sigma; if forwarded (`forward_degraded`) the autopilot follows it (Haz); used as the GPS cross-check reference it can make a good GPS look "in doubt" |
| Detection | scale ±15 % and ≥ 8 inliers (`day_pkg/local_matcher.py::LocalMatcher._locate_once`), spread / strip rejection and kinematic gate (`day_pkg/vision_nav.py::VisionNavigator.update`, `kinematic_margin_m`), pose–attitude guard 4° (`local_matcher.py::refine_with_pose`), rotation-rate / tilt gate (`navera_common/frame_builder.py::FrameBuilder.build`), local-fix check (`day_subscriber.py::DaySubscriber._check_local_fix`) |
| Mitigation | honest sigma: model + in-flight self-calibration against GPS, 30 m floor without (`day_pkg/fix_sigma.py::SigmaCalibration`); DEGRADED, never FIX; not forwarded by default (`policy.py::decide`); cross-check needs 2–5 fixes beyond 3 σ, never one (`gps_crosscheck.py::GpsCrossCheck`) |
| Evidence | PUB: UAV-VisLoc 8 flights, 2599 fixes, 1 > 100 m (bench artefact), 0.993 / 0.999 within 3 σ (NAV-FUN-08, NAV-PERF-07). PUB: 0 wrong on the 33-frame benchmark. BENCH: wind/shake 2–7 wrong (> 50 m) per run, output up to 266 m (F20); tilted 360 camera 100–650 m forwarded (F16) |
| Residual | **Medium** |
| Open items | O-3 F20: refuse frames at high angular rate / low sharpness on a real vehicle; O-4 F16: track-consistency gate (jump vs speed and stated sigma) — in progress; O-5 D17: a wrong accepted fix keeps a small sigma (multi-hypothesis); O-6 VL-2: flights that never self-calibrate stay at the 30 m floor |

### H-03 Wrong night (thermal) fix accepted

| | |
|---|---|
| Failure modes | STHN matches a wrong place (sea, cloud, low contrast, crossover, wrong heading/height) |
| Detection | re-run from a centre 150 m away must agree within 25 m, gradient NCC ≥ 0.05 (`night_localizer.py::NightLocalizer._recheck`, `verify_match`), footprint ≥ 85 % (`normalize_query`), featureless mask (off by default, D21), track gate and re-acquisition (`night_tracker.py::NightTracker.gate`, `offer`; B16, D22) |
| Mitigation | measured sigma from the two-centre agreement and height (`fix_sigma_m`, D3); DEGRADED; not forwarded by default |
| Evidence | SIM only: wrong accepts 228 / 1272 → 0 (1 at 55 m) on synthetic renders; real Insta360 night screen bench: every frame failed the map check (F24) |
| Residual | **High** (unvalidated) — acceptable only with GPS as reference in a test |
| Open items | O-7 real LWIR recording (the Hikvision DS-2TD2617B is now on the Jetson); O-8 re-fit thresholds and sigma on it before enabling night positions for the vehicle |

### H-04 Wrong celestial fix

| | |
|---|---|
| Failure modes | wrong star identification, wrong 'up' (vehicle acceleration, D8; smooth-road standstill, D12), mount error (D11), wrong time (H-08) |
| Detection | quality gate ≥ 7 stars, rms, chance probability, lens agreement (`cn_pkg/allsky.py::accept`); no attitude → no fix (NAV-FUN-12); ambiguous roots → none (`celestial_math.py::choose_candidate`) |
| Mitigation | stated sigma tens of km; `max_forward_sigma_m` 1 km: **never forwarded** to the autopilot (`policy.py::decide`, QAS-2) |
| Evidence | SIM 0/24 junk accepted (F11); BENCH 0 wrong of 87 re-judged (F26) |
| Residual | **Low** for the vehicle; Medium for its use as a coarse cross-check |
| Open items | O-9 real night sky with known time / place / attitude; O-10 gyro-propagated vertical in the product (D8) |

### H-05 Map outdated or wrong

| | |
|---|---|
| Failure modes | imagery years older than the ground (fields → greenhouses), seasonal change, coverage gap, wrong georeferencing |
| Effect | mostly **no match** (availability); a wrong match is caught as in H-02 |
| Detection / mitigation | refuse rather than guess (scale, inliers, guard); missing coverage reported at route preparation (`day_pkg/prepare_area.py`, `mission_prep.py::AreaJobs.plan`); no position outside coverage (whole-map search off) |
| Evidence | BENCH: 2017 imagery (8 years) → no match with any matcher, no wrong fix; PUB: flight 05 9 % accepted on a newer map; D19 0/30 offshore |
| Residual | **Medium** availability, **Low** integrity |
| Open items | O-11 record the imagery date per area and warn on /mission; O-12 ESRI / imagery licence for offline commercial use (DEP-11) |

### H-06 GPS spoof — fast (jump)

| | |
|---|---|
| Detection | kinematic gate `max_speed_mps × Δt + margin` and drag over a window (`estimator_node.py::EstimatorNode._check_gps_plausibility`, `_window_drag`; D2) |
| Mitigation | refused GPS comes back only with independent agreement (`_independent_reference`); "jam then spoof" handled the same way (EST-11) |
| Evidence | UT 5 km jump refused; SITL boat 2 km refused within 1 s, true GPS back 2–3 s after it returns |
| Residual | **Low** (requires `NAVERA_MAX_SPEED_KMH` set per vehicle — check_box / launch warn when unset) |

### H-07 GPS spoof — slow (drift)

| | |
|---|---|
| Detection | size rules (5 fixes beyond 3 σ / 2 beyond 5 σ + 50 m over 3 s) and growth test (`navera_common/gps_crosscheck.py::GpsCrossCheck`, `GpsDriftTrend`); "GPS in doubt" before refusal (`EstimatorNode._in_doubt`) |
| Mitigation | refused GPS replaced by vision; status says why |
| Evidence | SIM 4 m/s refused at ~140 m; BENCH replay 3 m/s at ~72 m (30 m floor), 0 false refusals on 108 real-camera runs and 7.2 h UAV-VisLoc |
| Residual | **Medium** over textured land, **High** where vision has no match: no independent source (D1: a 2 m/s drag over the sea caught only at the coast, ~390 m) |
| Open items | O-13 inertial dead-reckoning with a stated sigma (FEAT-2) as a second independent source; O-14 operator alarm for "no independent source: spoof undetectable" |

### H-08 Clock wrong (F27)

| | |
|---|---|
| Failure modes | no DS3231 / dead coin cell → Jetson boots at 1970 or the last saved time (16 h off on 2026-10-21), NTP step mid-mission, RTC in local time |
| Effect | celestial ≈ 28 km per minute of error; GPS_INPUT week time and NMEA date from `datetime.now()` (`vehicle_output_node.py::VehicleOutputNode._tick`) wrong; logs misdated |
| Detection | `rtc_pkg/rtc_pkg/nodes/rtc_node.py::RTCNode.publish_rtc` (valid only if UTC, power kept, drift explained); future stamps refused and never revived (`EstimatorNode._eval_source`, B6); clock step back resets histories (`sensor_history.py::History`) |
| Mitigation | celestial solves only on a trusted time (`navera_common/trusted_time.py::TrustedClock`, `cn_subscriber.py::CNSubscriber._utc_for`): DS3231 valid and not lost_power, a GNSS time (`gps_node.py::GPSNode._publish_time`) within 300 s, or NTP — with no wall-clock step since and none in the last 60 s; else no position, reason "no trusted time: …" (both solver modes; same rule as the field tools, db2f95c) |
| Evidence | HW: DS3231 reboot −0.148 s (2026-07-14); F27 shows a box can lack it; UT `test_trusted_time.py`, `cn_pkg/test/test_cn_gates.py` (no source / lost power / clock step → no solve) |
| Residual | **Medium** (celestial is never forwarded; time to the autopilot unverified) |
| Open items | O-15 done (UT) — run once on the box with the DS3231 removed and NTP off; O-16 check_box FAIL when no valid RTC; O-17 install procedure requires the coin cell / DS3231 |

### H-09 IMU bias, wrong heading or mount

| | |
|---|---|
| Effect | straightening error on day frames; night query turned wrong (heading); celestial ~111 km per degree |
| Detection / mitigation | frozen samples → reinit (`imu_node.py::IMUNode.publish_imu`); WMM declination + mount rotation (`imu_pkg/orientation.py`); attitude term in the day sigma (`fix_sigma.py::day_fix_sigma_m`); pose–attitude guard; night heading / height retries (D20); celestial mount tilt learned on stopped fixes (field, D11) |
| Evidence | SIM straightening with 0.3°/1.5° bias: 33/33 within 2.6 m; HW BNO085 data at 50 Hz (no reference heading) |
| Residual | **Medium** |
| Open items | O-18 IMU-3: heading against a known heading; noise measured for the covariances |

### H-10 Latency mismatch

| | |
|---|---|
| Effect | position along-track error = speed × delay error; sigma too small |
| Mitigation | exposure stamp = grab − `NAVERA_CAMERA_LATENCY_S` (`LiveCamera._grab_loop`), delay stored with the calibration (887497d), online fit frozen when GPS untrusted (`latency_cal.py::LatencyCalibrator`); speed × 0.05 s term in the day sigma; output carries vision to now with the lag in the sigma (`policy.py::decide`), refuses > 5 s old |
| Evidence | BENCH: 1.71 s 360 stream, 39.8 → 3.3 m at 80 m/s (F9); 1.5 s video stamp lag found and corrected (F15) |
| Residual | **Medium** |
| Open items | O-19 measure the delay of each production camera mode and of the full chain on the box; verify `GPS_DELAY_MS` advice in SITL / flight |

### H-11 Compute overload, out of memory, thermal throttling

| | |
|---|---|
| Effect | frames processed late or not at all (F4: failed frames 6–20 s), OOM kill of the day pipeline after 4.6 min without swap (F5), GPU clocks throttled |
| Detection | `navera_estimator/nodes/compute_health_node.py::ComputeHealthNode` (`navera_common/compute_health.py`): temperatures, memory, swap, GPU load, throttling from /sys and /proc without root → `/diagnostics`, `/navera/compute_health`; no swap reported at start; freshness windows make late fixes ineligible (`EstimatorNode._eval_source`); output refuses measurements > 5 s old |
| Mitigation | at 95 C or ≤ 8 % memory available the latched `/navera/compute/degraded` makes day and night skip their optional height / heading retries (`compute_health.py::watch_degraded`); strictly serial back-pressure camera → localizer (camera waits for `frame_done`); one GPU pipeline (`Conflicts=`); coarser map level at height (D14); uniform frames rejected early (3180629); restart after a kill (`Restart=always`); swap on disk made by `deploy/setup_swap.sh` (install.sh, 8 GB when < 4 GB active; zram does not count), warned by every pipeline start (`navera_boot_lib.sh::navera_check_swap`), `check_boot.sh` and `check_box.py`; OOM order in the units: output chain (estimator, output, GPS, IMU, RTC, vehicle link) `OOMScoreAdjust=-900` + systemd-oomd `omit`, vision pipelines -300 + `avoid`, web and discovery +500 with `MemoryHigh` / `MemoryMax` (beyond it they go to swap, never into the pipeline's RAM), checked by `verify_units.py` |
| Evidence | BENCH: F5, D14 (3.7 GB RSS at 1500 m); 2026-10-22: product day chain on a real recorded flight (104 m) 2.48 GB RSS, day_perf mission bench (~520 m) 5.0 GB RSS; UT `test_compute_health.py`, `test_compute_health_node.py`, `deploy/test/test_swap.py`, `deploy/test/test_memory_protection.py`; read without root on the Orin Nano |
| Residual | **Medium** (integrity protected; availability not) |
| Open items | O-20 swap file and OOM scores / memory caps: done in deploy (UT, staged) — to run once as root on a box (DEPLOYMENT_VALIDATION.md §2) and an OOM provoked there; O-21 temperature / throttle monitor done (NAV-SAF-21) — still to show on the operator view and in check_box; O-22 TensorRT (latency) |

### H-12 Power loss or reboot in flight

| | |
|---|---|
| Effect | NAVERA silent during the boot; the autopilot's own failsafe acts |
| Mitigation | every unit starts without login or network; day anchor saved and reused for 300 s after a restart (`day_subscriber.py`, `state_store`, `ANCHOR_MEMORY_S`); ground height saved 12 h (`live_camera`); RTC keeps time |
| Evidence | HW reboot 2026-07-15 (old mechanism); staged restart test 2026-10-21 (DEPLOYMENT_VALIDATION.md) |
| Residual | **Medium** |
| Open items | O-23 reboot validation of the current units on a deployed box (DEP-14) and boot-to-first-fix time; O-24 power supply hold-up / brown-out behaviour on the vehicle |

### H-13 Autopilot misconfiguration (EK3_SRC1_POSZ = 3 and friends)

| | |
|---|---|
| Failure modes | `EK3_SRC1_POSZ = 3` (GPS height), `EK3_OGN_HGT_MASK` set, `EK3_SRC1_VELXY/VELZ` not 0, `GPS_AUTO_SWITCH` switching to a receiver NAVERA refused, `GPS_DELAY_MS`, NMEA forwarding of vision |
| Effect | with POSZ = 3 vision positions (no altitude, read as 0 m AMSL) pull the EKF height to −277 m in 20 s; the vehicle climbs to 150 m then 825 m to "hold" 40 m (Cat); stale GPS velocity → EKF failsafe (OUT-1) |
| Detection | none in NAVERA (it never reads the autopilot's EKF parameters); `discovery.py` reads only `GPS_TYPE*` |
| Mitigation | `IGNORE_ALT` for every non-GNSS position (`mavlink_out.py::gps_input_fields`, F7); NMEA vision off by default; documented parameter table (ARDUPILOT_INTEGRATION.md §3) |
| Evidence | SIM: SITL F7 test (POSZ 1: EKF = baro within 0.1 m; POSZ 3: 431 m off) |
| Residual | **High** with an unchecked integrator, Medium with the documented checklist |
| Open items | O-25 vehicle link reads `EK3_SRC1_POSZ`, `EK3_SRC1_VELXY/VELZ`, `EK3_OGN_HGT_MASK`, `GPS_AUTO_SWITCH` (PARAM_REQUEST_READ, as discovery already does for GPS_TYPE) and **refuses to forward degraded positions** when they are unsafe; check_box FAIL |

### H-14 Storage full

| | |
|---|---|
| Effect | ROS logs / recordings fill the disk: nodes cannot write logs or state; settings write fails |
| Mitigation | ROS log folders > 7 days pruned at each unit start, then the oldest above 1 GB, and a warning below 2 GB free (`navera_boot_lib.sh::navera_prune_logs`); `state_store` never raises on an unwritable directory; recordings on the data disk; tile download checks free space (simulator) |
| Evidence | A; UT `navera_common/test/test_state_store.py::test_an_unwritable_directory_does_not_raise`, `deploy/test/test_boot_logs.py` |
| Residual | **Low** (a restart loop's log folders are capped at 1 GB) |
| Open items | O-26 done at unit start (size cap, free-space warning; UT); still: free space in check_box, journald `SystemMaxUse` |

### H-15 Integrator settings (forwarding)

`forward_degraded` with a stated sigma smaller than measured (R-10), above ArduPilot's 100 m cap,
or NMEA forwarding of vision. Mitigations: sigma required and never better than the source
(`policy.py::Config.validate`, `decide`), 1 km ceiling, check_box WARNs above 100 m and on NMEA
forwarding (`check_box.py::config_findings`), drift alarm in the log above 100 m
(`VehicleOutputNode._check_drift`, e535f62 — UT `test_bridge_flow.py`; not shown on the operator view). Residual **Medium**.

### H-16 Simulation or a second arbiter on a live box

Fakes refuse without `NAVERA_ALLOW_SIM=1`; DDS localhost-only on an isolated domain; a second
arbiter is reported (`EstimatorNode._check_single_arbiter`, UT `test_estimator_rules.py`); the operator view marks
simulated data. Residual **Low**.

## 4. Open items (summary)

| # | Item | Hazard | Kind |
|---|---|---|---|
| O-1 | frame-content freeze detector + test — done (UT); real stall on the box to reproduce | H-01 | code / test |
| O-25 | read and check the autopilot's EK3 / GPS parameters | H-13 | code |
| O-13 | inertial dead-reckoning as an independent source (FEAT-2) | H-07 | code |
| O-7, O-8 | real LWIR data; re-fit night thresholds | H-03 | data |
| O-15–O-17 | trusted-time gate in product celestial (done, UT); RTC mandatory | H-08 | code / install |
| O-20, O-21 | swap + OOM / memory limits (done in deploy, UT; root run on a box pending); thermal monitoring (monitor done, UT) | H-11 | deploy |
| O-23 | reboot validation on a deployed box (commands in DEPLOYMENT_VALIDATION.md) | H-12 | test |
| O-27 | install from a clean release clone; install.sh no longer copies .git, .claude/worktrees, caches or recordings (B18 fixed, UT) | H-12, deployment | deploy |
| O-3, O-4 | shake / tilt gates (F20, F16) on a real vehicle | H-02 | code / test |
| O-19 | full-chain latency on the box | H-10 | measurement |
| O-26 | storage checks (log cap + free-space warning at unit start done, UT; check_box, journald open) | H-14 | deploy |
| O-11, O-12 | imagery date, imagery licence | H-05 | data / legal |
| — | first recorded flight with camera + GPS + IMU (every accuracy claim) | all | test |
