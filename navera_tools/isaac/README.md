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
| Camera | Hikvision visible lens: fisheye calibration (`hik_visible_lens_2026-10-20.yaml`, scaled to the 1344 x 760 sub-stream), vignetting, auto-exposure, motion blur over the exposure, haze (slant range), shot/read noise, H.264 (libx264 CBR 2 Mbit/s), 10 fps, delivered **1.3 s** after exposure (stamped at arrival; NAVERA's auto_latency has to find it), mounting error 1.5/-1.0/2.0 deg unknown to NAVERA | no rolling shutter; render is a wide pinhole resampled through the lens model |
| IMU | 100 Hz: gyro = truth + turn-on bias (<= 0.27 deg/s) + 0.077 deg/s white per sample, accel + 0.0015 g (the measured Insta360 One R figures); attitude = truth x AHRS error (0.3/0.3/1.5 deg bias + slow wander) | no vibration spectrum, no clipping |
| Baro / GPS | baro: height above take-off + 1.5 m bias + random walk + 0.3 m noise; GPS 5 Hz: 1.5 m correlated (30 s) + 0.3 m white, cut at 60 s; optional slow spoof (3 m/s) before the cut | |

The rendered camera sees the same 2022 imagery as the scene, NOT the map NAVERA uses: cross-date
matching is real. Measured offline on Isaac frames (raw renders vs the 2025 map, truth prior):
DISK+LightGlue 10/10 matched (80–200 inliers), SIFT 2/10 — NAVERA's default matcher (`auto`) is
the learned one, which needs the GPU: the container runs with `--gpus all`, beside Isaac Sim.

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
