# navera_tools/isaac — NAVERA flown in NVIDIA Isaac Sim (SIMULATION, development only)

The closest thing to a flight test without flying: Isaac Sim (Windows PC, RTX 4060 8 GB) renders
a vehicle flown by ArduPilot SITL over a 3-D model of a real place; NAVERA's **real nodes**
(live_camera → day_subscriber → navera_estimator, ros_gps_node) run unchanged in a ROS 2 Humble
container on the same PC and navigate from what that camera sees. Nothing here is product code.

```
 Jetson (prepared once)                     PC: Windows                 PC: WSL2 / Docker (navera-humble, --gpus all)
 fetch_scene_data.py  Wayback 2022 imagery  isaac_flight.py             isaac_link.py  camera model + IMU/baro/GPS + record
 prepare_scene.py     DEM, footprints  ───▶ (Isaac Sim 6.0, RTX)  ───▶  live_camera ─▶ day_subscriber ─▶ estimator
 sitl_record.py       ArduPilot flight      frames/*.jpg, session.json  ros_gps_node                       │
                                            window "NAVERA - Isaac      live_plot.py (WSLg) ◀── position.csv, live.json
                                            Sim flight"                 window "NAVERA - live error"
```

## What is simulated, and how real it is

| Item | How | Not modelled / limits |
|---|---|---|
| Ground imagery | Esri World Imagery **Wayback 2022-03-16** (z18, 0.48 m/px, 4 x 4 km, Kalaa Kebira) — NAVERA matches against its own ~2025 map (z17 MBTiles export) | one season; satellite roofs keep their baked-in shadows |
| Relief | AWS Terrain Tiles (SRTM-class, ~10 m grid at z14), 257 x 257 mesh, -25…+51 m around the origin | no trees as 3-D objects |
| Buildings | 8 217 Microsoft ML footprints (OSM maps 50 here), extruded 1–4 floors x 3.2 m (deterministic draw: no heights in the data), roofs textured with the imagery at their place, plain walls | heights invented; footprints may be offset a few metres |
| Light | sun at its true position (NOAA equations) for date/time/place, soft shadows; sky dome; drifting cloud shadows (cut-out layer at 1.5 km) | Isaac real-time renderer, not path-traced; no volumetric haze in the render |
| Flight | ArduPilot SITL (ArduPlane `plane`, ArduCopter `quad`) flies the circuit with wind 4–7 m/s + turbulence; its 50 Hz attitude/position drive the scene | autopilot uses its own perfect SITL GPS (NAVERA not in the loop) |
| Camera | Hikvision visible lens: fisheye calibration (`hik_visible_lens_2026-10-20.yaml`, scaled to the 1344 x 760 sub-stream, read as `model: fisheye` — the file itself lacks the key), vignetting, auto-exposure, motion blur over the exposure, haze (slant range), shot/read noise, H.264 (libx264 CBR 1 Mbit/s), ~2-3 frames/s through the camera model (rendered at 10 fps), delivered **1.3 s** after exposure (stamped at arrival; NAVERA's auto_latency has to find it), mounting error 1.5/-1.0/2.0 deg unknown to NAVERA | no rolling shutter; render is a wide pinhole resampled through the lens model |
| IMU | 100 Hz: gyro = truth + turn-on bias (<= 0.27 deg/s) + 0.077 deg/s white per sample, accel + 0.0015 g (the measured Insta360 One R figures); attitude = truth x AHRS error (0.3/0.3/1.5 deg bias + slow wander) | no vibration spectrum, no clipping |
| Baro / GPS | baro: height above take-off + 1.5 m bias + random walk + 0.3 m noise; GPS: NMEA GGA/RMC 5 Hz, 12 satellites, ~1.5 m Gauss-Markov noise, on a pseudo-terminal read by NAVERA's **real gps_node** (`navera_tools/sim/nmea_gps.py`); cut = jammed (no fix); optional slow spoof (3 m/s) before the cut | |

The rendered camera sees the same 2022 imagery as the scene, NOT the map NAVERA uses: cross-date
matching is real. Measured offline on Isaac frames (raw renders vs the 2025 map, truth prior):
DISK+LightGlue 10/10 matched (80–200 inliers), SIFT 2/10 — NAVERA's default matcher (`auto`) is
the learned one, which needs the GPU: the container runs with `--gpus all`, beside Isaac Sim.

## Closed loop: the autopilot flies on NAVERA (`run_closed_loop.sh`)

ArduPilot SITL 4.5.7 (copter, on the PC) with NAVERA's recommended parameters (GPS_TYPE 14,
SIM_GPS_DISABLE 1, EK3_SRC1_VELZ 0, Copter EK3_GLITCH_RAD 100, docs/ARDUPILOT_INTEGRATION.md; `--set
K=V,...` adds or overrides parameters): its only position is
NAVERA's `GPS_INPUT` (navera_output `vehicle_output_node`, forward_degraded, `--sigma` stated).
`sitl_demo.py` streams SITL's truth to Isaac Sim (the vehicle and its gimballed camera) and to
the link (IMU, baro, NMEA GPS), takes off on GPS, flies a 500 m diamond at 250 m / 8 m/s, cuts
the GPS 15 s after reaching altitude, RTLs and holds over home. MAVProxy map + console show the
autopilot's view.

```bash
~/Navera/navera_tools/isaac/run_closed_loop.sh --name demo --sigma 15        # ~14 min
#   --gate FILE: prepare everything, open no window until FILE exists; --hold S: keep windows S s
```

Endurance (GPS only at take-off, then hours without it): `--endurance S` repeats the diamond for S s
after the cut, then RTL (infinite SITL battery, battery failsafes off); `--isaac-args "--sun-ramp 1"`
moves the sun in real time; `resource_monitor.sh` writes `resources.csv` (GPU, each node's RSS, WSL,
Isaac Sim, disk) every 30 s; `endurance_report.py <dir>` gives per-15-min blocks, `error_vs_time.png`,
`ENDURANCE.md` (with the autopilot EKF velocity error from `sitl/mav.tlog`).

```bash
run_closed_loop.sh --name endur_2h --endurance 7200 --cut-after 12 --sigma 15 --time 10:00 --isaac-args "--sun-ramp 1"
```
2026-10-22 (`endur_2h`): EKF failsafe LAND 60.5 min after the cut — the autopilot's EKF velocity (no
velocity source) drifted in growing episodes and flew the vehicle off the map; NAVERA's fixes flat
(~15 m at the stated time, 6 m at exposure, 0 wrong) the whole hour.

### Soak on the Jetson without Isaac Sim (`memory_soak.sh`, F40)

`memory_soak.sh OUT [minutes] [--no-trace] [-- day_subscriber -p k:=v ...]` runs NAVERA's real
chain on the Jetson for hours without the PC: `stand_in_render.py` writes an Isaac-like run
directory (frames cut from the scene's orthophoto along a 500 m circle at 250 m, 8 m/s — no relief,
no 3-D, no light: not an accuracy test), `isaac_link.py` turns it into the real camera, IMU, baro
and NMEA GPS exactly as in the closed loop (1.3 s camera delay, GPS cut at 150 s), and gps_node,
estimator, live_camera and day_subscriber run as in `run_navera_nodes.sh`; day_subscriber under
`navera_tools/bench/memprofile.py` (tracemalloc top growth by source line, torch CUDA memory, gc
counts, node containers, every 60 s -> `day_mem.jsonl`), every node's RSS -> `rss.csv`. Own ROS
domain (refused if another process uses it), GPU lock held for the whole run.

## Results (2026-10-21, simulation only — Isaac Sim scene, not a flight)

After the GPS cut. "vs stamp" = NAVERA's fix against the truth at the time NAVERA states;
"vs exposure" = against the truth when the photo was taken (the matching alone; the difference is
the 1.3 s camera delay, which NAVERA's auto_latency never learned: see findings). ms/frame on the
PC's RTX 4060, shared with Isaac Sim.

| Run | vehicle, camera | accepted | fix error vs stamp med / p90 / max | vs exposure med / p90 / max | wrong (>50 m) | output error med / p90 / max | autopilot EKF error | ms/frame |
|---|---|---|---|---|---|---|---|---|
| plane_morning (08:30) | ArduPlane SITL recorded, ~500 m, 19–32 m/s, body-fixed nadir | 364/367 (99.2 %) | 42 / 85 / 161 m | 19 / 56 / 116 m | 38 / 365 | 44 / 89 / 168 m | — | 485 |
| copter_noon_spoof (12:30) | ArduCopter SITL recorded, 300 m, 8–12 m/s, body-fixed (tilted ~35 deg) | 3/402 (0.7 %) | — | — | 0 | 46 / 61 / 98 m (dead-reckoning) | — | 679 |
| cl_test1 (closed loop, sigma 30) | ArduCopter LIVE, 250 m, gimbal | 350/500 (70 %) | 17 / 23 / 33 m | 6 / 11 / 24 m | 0 | 17 / 25 / 62 m | 33 / 86 / 542 m — diverged | 561 |
| cl_test2 (closed loop, sigma 15) | ArduCopter LIVE, 250 m, gimbal | 756/854 (88.5 %) | 13 / 20 / 33 m | 7 / 11 / 20 m | 0 | 13 / 22 / 139 m | 14 / 31 / 120 m | 429 |

Findings: (1) auto_latency never converged in ~60 s of GPS flight (samples rejected "turning" on
the circuits, "GPS history too short"; frozen at the cut) — the uncorrected 1.3 s delay doubles
the fix error. (2) A body-fixed camera on a copter leaning 35 deg (SITL quad at its speed limit)
gives almost no matches; on a gimbal 88 % — and the 3 m/s GPS spoof went unnoticed for want of
vision fixes. (3) Closed loop: stated sigma 30 m let the autopilot's EKF (no GPS velocity)
diverge after ~4 min and fly off the map; with 15 m (close to the measured 13 / 20 m) it flew all
4 waypoints and RTL on vision (EKF 14 m median), then lost vision below ~150 m while landing and
drifted ~500 m (now: RTL holds at altitude). (4) `ros_gps_node` forwards 0 satellites, so an
autopilot fed only by NAVERA never sets its EKF origin — the link therefore drives the real
gps_node with NMEA. (5) `hik_visible_lens_2026-10-20.yaml` has no `model: fisheye`: NAVERA would
read it as pinhole (47 deg instead of 77 deg).

## Hardware in the loop: the real box flies (`hil_flight.sh`, on the Jetson)

NAVERA runs on the Jetson **as deployed** — the product's systemd units, staged as user units by
`deploy/stage_check.sh --env-extra` (same install, wrappers, launch files, `navera.env`), nice 0 —
and the PC only simulates the world and the vehicle (`run_hil.sh`, started by the box over ssh):

```
 PC (WSL)                                              Jetson (staged product units, ROS domain 87)
 Isaac Sim -> isaac_link camera model -> ffmpeg x264 -> mediamtx RTSP :8564 --LAN--> navera-pipeline-day
                                                                         (gst: rtspsrc ! nvv4l2decoder)
 isaac_link NMEA receiver (5 Hz, jammed after the cut) --- TCP :10117 --> navera-gps (network source)
 ArduPilot SITL -I5 SERIAL1 (921600) ------------------- TCP :5812  <--> navera-vehicle-link (attitude, baro;
                                                                          relays navera-output's GPS_INPUT)
 sitl_demo truth (SIM_STATE 50 Hz + EKF) ---------------- UDP :15531 --> hil_record.py (+ tegrastats, units)
```

```bash
navera_tools/isaac/hil_flight.sh --name hil_base1 --kill navera-estimator@180          # ~10 min
navera_tools/isaac/hil_flight.sh --name hil_endur30 --kill navera-pipeline-day@1500 \
    --pc-args "--legs 32 --radius 400 --speed 10 --cut-after 75 --alt 250 --duration 2700"
python3 navera_tools/isaac/hil_summarise.py ~/.navera_sim/isaac/hil/<name>      # recompute
```
It waits for the PC lock, the box's GPU lock and a quiet box; results in `~/.navera_sim/isaac/hil/<name>`
(`hil_summary.json`, `hil_report.md`, `hil_*.csv`, `logs/`, `pc/`). Same mission as campaign `c3_base`
(copter 250 m, gimbal, 3 legs r 400 m at 10 m/s, GPS cut 75 s after altitude, sigma 15 m).
Differences from the container runs: attitude is the autopilot's (SITL `ATTITUDE`, 50 Hz over MAVLink),
not isaac_link's IMU model; the camera frames cross a real H.264 encode / RTSP / hardware decode.

### Result hil_base1 (2026-10-22, SIMULATION feeding the real box)

GPS-denied from the cut to the estimator kill (180 s, 344 frames) vs the container baseline c3_base
(whole denied phase, before F31's staged delay apply, so the "vs stamp" column is not like for like):

| | HIL (real box) | container c3_base |
|---|---|---|
| matched after the cut | 95.6 % | 98.7 % |
| fix error vs stamp med / p90 / max | 6.6 / 10.4 / 13.9 m | 12.8 / 20.7 / 30.0 m |
| fix error vs true exposure | 8.5 / 12.6 / 16.2 m | 6.5 / 12.2 / 14.8 m |
| wrong fixes (> 50 m) | 0 | 0 |
| output error | 6.8 / 10.7 / 22.8 m | 12.8 / 20.7 / 30.0 m |
| autopilot EKF error | 10.3 / 22.7 / 39.8 m | 14.6 / 28.6 / 40.7 m |
| day ms/frame (frame_meta -> frame_done) | 344 / 404 / 1277 (Orin Nano, DISK+LightGlue) | 429 / 538 / 1479 (RTX 4060 shared with Isaac) |

Latency per measured fix (median / p90): stream send -> box grab 36 / 74 ms; grab -> frame_meta
60 / 71 ms; day pipeline 341 / 403 ms; estimator 5 / 9 ms; box position -> autopilot's GPS_RAW_INT
160 / 262 ms; exposure -> /navera/position 1.8 / 1.9 s, of which 1.3 s is the simulated camera delay
(auto_latency applied 1.70 s in flight). Box: RAM 5.4 GB median / 6.4 GB max (+1.8 GB swap, other
jobs included), day pipeline 2.7-3.0 GB, CPU 49 % median, GPU 11 % median / 92 % p90, Tj <= 59.6 C,
VDD_IN 8.2 W median / 12.7 W max. Network (Wi-Fi box, wired PC): truth UDP one-way jitter
24 / 31 / 138 ms above its minimum; vehicle IMU 50 Hz, largest gap 348 ms; NMEA 5 Hz, largest gap 450 ms.
Restart test: the estimator node SIGKILLed at cut+180 s -> systemd restarted it (RestartSec 10),
/navera/position back after 15.4 s; the autopilot lost its GPS 2.3 s after the kill and ArduPilot's
EKF failsafe switched to LAND 7.6 s after it; GPS back at 21.5 s but the copter stayed in LAND and
landed 606 m from home: one crash of a critical node during GPS denial ends the mission.

### Result hil_endur30 (2026-10-22): 25 min GPS-denied on the real box

The same diamond 32 legs (~8 laps); GPS cut at t = 241 s, day pipeline killed at cut+1500 s.
Over those 1500 s (2838 frames): matched 97.2 %, fix error vs stamp 5.4 / 9.5 / 17.2 m, vs exposure
6.8 / 11.5 / 18.3 m, 0 wrong, output 5.5 / 9.8 / 28.3 m, autopilot EKF 8.0 / 19.4 / 35.4 m,
day 342 / 401 / 1385 ms per frame. No restart, no drift of the box over 25 min: RAM 5.67 GB median /
5.71 GB max (day pipeline 2.93 / 2.96 GB), CPU 47 % median, Tj <= 59.8 C, VDD_IN 8.4 W median.
Exposure -> /navera/position 1.8 / 2.1 / 3.3 s (1.3 s simulated); stream send -> grab 42 / 296 / 474 ms
(Wi-Fi: truth UDP one-way jitter 72 / 100 / 392 ms above its minimum, TCP round trip 3.1 / 7.0 / 48.5 ms);
box position -> autopilot GPS 209 / 276 ms. The delay started from the one learned in hil_base1 and
stored with the camera (F31: 1.70 s). Day pipeline SIGKILLed: restarted by systemd, /navera/position
back after 25.5 s; the autopilot lost its GPS after 2.9 s, EKF failsafe LAND after 7.8 s, landed
627 m from home (as hil_base1: a restart gap longer than ArduPilot's EKF tolerance ends the mission).

## Run (on the PC, from WSL)

```bash
~/Navera/navera_tools/isaac/run_isaac_flight.sh --name plane_morning --traj plane --time 08:30
~/Navera/navera_tools/isaac/run_isaac_flight.sh --name copter_noon_spoof --traj copter --time 12:30 --spoof 3
```
Options: `--date --duration --gps-cut --spoof --delay --clouds --haze (visibility m) --mount-err r,p,y
--matcher auto|local --max-speed`. Results in `~/navera_results/<name>/`: `summary.json`,
`position.csv` (every /navera/position vs truth), `day.csv`, `proc.csv`, `events.jsonl`,
`flight.mp4` (chase view + what NAVERA's camera delivered + live plot), `chase.mp4`,
`navera_view.mp4`, `plot_final.png`, `logs/` (every node). `summarise.py <dir>` recomputes the
numbers.

## Prepare (once, on the Jetson; then copy to the PC)

```bash
python3 navera_tools/isaac/fetch_scene_data.py --lat 35.8685 --lon 10.5352 --out ~/.navera_sim/isaac/kalaa
python3 navera_tools/isaac/prepare_scene.py --lat0 35.8685 --lon0 10.5352 --scene ~/.navera_sim/isaac/kalaa \
    --scene-out ~/.navera_sim/isaac/kalaa_scene \
    --map-tiles ~/.navera_sim/dayv_conditions/kalaa_map/images --area-out ~/.navera_sim/isaac/kalaa_area
python3 navera_tools/isaac/sitl_record.py --vehicle plane --lat 35.8685 --lon 10.5352 \
    --dem ~/.navera_sim/isaac/kalaa/dem --out ~/.navera_sim/isaac/traj/plane.csv --height 500 --speed 25
python3 navera_tools/isaac/sitl_record.py --vehicle copter --lat 35.8685 --lon 10.5352 \
    --dem ~/.navera_sim/isaac/kalaa/dem --out ~/.navera_sim/isaac/traj/copter.csv --height 300 --speed 12 \
    --radius 700 --wind 4 --turb 1.5 --instance 9
```
PC layout: `D:\navera_isaac\{scenes\kalaa, traj}` (scene + trajectories), `~/navera_data/isaac_kalaa_area`
(NAVERA's map), `~/navera_data/lens/hik_visible_lens.yaml`, `~/navera_data/torch_home` (DINOv2,
DISK, LightGlue weights — offline), image: `docker build -t navera-humble -f Dockerfile.humble .`

Isolation: the container uses ROS_DOMAIN_ID 77 and ROS_LOCALHOST_ONLY=1, its own state directory
(`NAVERA_STATE_DIR` in the results): it never talks to a NAVERA box. SITL runs as its own instance
(-I 8/9) in a temporary directory.

Data licences: Esri imagery and OSM / Microsoft footprints (ODbL) — internal evaluation only.
