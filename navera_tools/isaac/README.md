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
SIM_GPS_DISABLE 1, EK3_SRC1_VELXY/VELZ 0, docs/ARDUPILOT_INTEGRATION.md): its only position is
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
