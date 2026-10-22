# navera_tools — field tools and bench / simulation tools

Two kinds of tools live here. **Field tools** are made to run on the installed box, in the
NAVERA shell (deploy/README.md §11), and change nothing on it except their own output
files. **Bench and simulation tools** publish simulated data or start their own NAVERA
nodes: run them on a test machine or a bench box, **never on a box installed on a vehicle**
(their fake data would reach the real arbiter on the same ROS domain).

**Field tools** (on the box):

| Tool | |
|---|---|
| `check_box.py [--camera] [--no-ros] [--seconds N]` | pre-flight check: discovery report, static configuration checks, data files, then the live topics; PASS / WARN / FAIL, exit 0 = no FAIL (deploy/README.md §11) |
| `calibrate_camera.py` | lens calibration (once per camera and resolution; stop the pipeline first) — below |
| `record_session.sh <dir> [day\|night\|cn]` | record a test session (all sensors, estimates, decision, camera) into a ROS 2 bag, on the data disk |
| `evaluate_session.py <bag dir> [--csv file]` | measure each source against GPS in a recorded session (median / p90 / within 50-100-300 m) and whether the stated accuracy is honest |
| `mission_bundle.py plan\|build\|check\|env` | **offline mission bundle**: the route's corridor map, day-vision area and features, IERS table and star catalogue in one directory, with a sha256 manifest; `check` proves it works with the network off — below |

`check_boot.py` (the reboot check with the ROS node of every unit; `--user --prefix
navera-stage-` for the staged test, `deploy/stage_check.sh`) and `trace_matrix.py` (regenerates
docs/certification/REQUIREMENTS.md and TRACEABILITY.md from `requirements.yaml` and the tests;
`--check` fails on a broken link) are read-only too.

`deploy/check_boot.sh` (the reboot test) and `deploy/install.sh` are the box's other
tools; both have `--help`.

**Bench and simulation tools** (test machine only):

| Tool | |
|---|---|
| `run_tests.sh [--integration]` | the test suite (unit; integration starts real nodes on an isolated ROS domain) |
| `tests/test_estimator.py`, `tests/test_gps_serial.py`, … | integration tests |
| `sensor_sim.py` | simulated GPS/IMU/RTC on the real topics (refuses to run without `NAVERA_ALLOW_SIM=1`) |
| `navera_fakes.py` | fake publishers for the whole graph (rqt_graph; `NAVERA_ALLOW_SIM=1`) |
| `run_scenario.sh` | scripted GPS-loss scenario with `sensor_sim` |
| `run_sim.sh` | **mission simulator** (below): control page on :8190, real NAVERA nodes, ArduPilot autopilot in the loop |
| `run_demo.sh [measured\|target]` | **demonstration**: simulated mission over Sousse with GPS jamming, on the real arbiter and operator view (`demo_mission.py`) |
| `tests/sitl_ardupilot.py`, `tests/sitl_vehicle_link.py`, `tests/sitl_discovery.py` | the vehicle output, vehicle link and discovery against ArduPilot SITL (needs an ArduPilot build) |
| `tests/sitl_f7_height.py` | F7: ArduCopter SITL fed NAVERA's GPS_INPUT (vision, wrong / jumping / drifting heights): EKF height must stay on the barometer, horizontal position follow vision; `EK3_SRC1_POSZ = 3` as the sensitivity control (~9 min, dataflash log analysed) |
| `bench/camera_chain.py`, `bench/day_wrong_altitude.py` | offline benchmarks of the camera chain |
| `bench/night_conditions.py [--n 24] [--only names\|groups] [--csv f]` | night vision (STHN) stress test: 53 simulated conditions (thermal look, blur, lights, weather, occluders, geometry, terrain, no-information frames) with ground truth — match rate, error, wrong accepts, time. Synthetic frames from the matched map; loads one STHN model (`nice` it on a shared box) |

## Lens calibration (`calibrate_camera.py`)

Run it as `navera` with the pipeline stopped (it holds the camera), and write the result
where `navera` can write — **not** `/etc/navera`, which belongs to root (the example in the
tool's own help writes there: that works only with `sudo`):

```bash
sudo systemctl stop navera-pipeline-day
# in the NAVERA shell:
python3 navera_tools/calibrate_camera.py --device /dev/v4l/by-id/usb-<maker>_<model>_<serial>-video-index0 \
    --size 1920x1080 --board 9x6 --square-mm <measured> --out /var/lib/navera/camera.yaml
# then, as administrator:
sudo install -m 0644 /var/lib/navera/camera.yaml /etc/navera/camera.yaml
sudoedit /etc/navera/navera.env      # NAVERA_CAMERA_CALIBRATION=/etc/navera/camera.yaml
sudo systemctl start navera-pipeline-day
```

Procedure and acceptance: docs/FIELD_TEST_PROCEDURE.md §2.

## Measuring accuracy on a real session

The same recipe as docs/FIELD_TEST_PROCEDURE.md §7:

1. Enable **shadow mode** in the service, so vision runs while GPS is valid (not a second
   launch beside it):
   `sudoedit /etc/navera/navera.env` → `NAVERA_SHADOW_MODE=true`, then
   `sudo systemctl restart navera-pipeline-day`.
2. In the NAVERA shell, during the drive or flight (on the data disk: camera frames are
   large; one new directory per session):
   `navera_tools/record_session.sh /data/navera/rec/flight1 day`.
3. `python3 navera_tools/evaluate_session.py /data/navera/rec/flight1 --csv /data/navera/rec/flight1.csv`.
4. At the end of the campaign, set `NAVERA_SHADOW_MODE=false` (or remove it) and restart the
   pipeline.

Only numbers produced this way, on representative data, go into docs/VALIDATION_STATUS.md.

## Mission bundle (offline flight)

NAVERA flies with no network. Before departure, the route's **mission bundle** is built
(internet needed only then) and copied to the vehicle:

    source ~/navera_env.sh
    # 1. the estimate, nothing downloaded: tiles, MB, minutes, warnings (licence, height)
    python3 navera_tools/mission_bundle.py plan --start 35.8256,10.6385 --dest 35.6781,10.0963 \
        --corridor-m 2000 --max-height-m 600 --source onboard esri
    # 2. build (asks for confirmation, or --yes); GPU steps: DINOv2 cache, learned features
    python3 navera_tools/mission_bundle.py build /data/bundles/sousse_kairouan <same options>
    # 3. prove it offline (re-runs itself in a network namespace: `unshare -rn`)
    python3 navera_tools/mission_bundle.py check /data/bundles/sousse_kairouan [--deep] [--replay REC_DIR]
    # 4. point NAVERA at it (where the bundle is now)
    python3 navera_tools/mission_bundle.py env /data/bundles/sousse_kairouan

Inputs: start + destination, `--waypoint` (repeatable) or `--route-file` (GPX, KML, JSON,
Mission Planner `.waypoints`, QGroundControl `.plan`); `--corridor-m` (full width the vehicle
may stray in); `--min/max-height-m`, `--hfov`, `--frame-width` (the day camera). The map is
zoom 17 (what day and night match); the **maximum height** widens the map by the half
diagonal of the highest frame's footprint (the matcher reads the map under the whole frame)
and chooses the learned matcher's coarse map levels (`learned_matcher.map_level`: a 1500 m
frame of the 1200 px / 100 deg camera is matched on level 2, 4x coarser); `plan` warns when
the height is beyond what zoom 17 serves with that camera.

Tile sources (`--source`, in priority order; each tile is taken from the first that has it):
`onboard` (the onboard MBTiles, `--mbtiles` / `NAVERA_MBTILES`), `esri` (Esri World Imagery,
8 tiles/s, polite to HTTP 429 — **offline storage needs an Esri licence: evaluation only**),
`xyz:URL` (`--licence` required), `mbtiles:PATH`, and `fn:module:function[:source]`: a source
catalogue function `fetch(bbox=(west, south, east, north), source=name, zooms=[17]) ->
MBTiles path`, called per 16x16-tile block of the corridor (its MBTiles metadata gives the
licence, attribution and imagery date). Only corridor tiles enter the bundle.

Layout (relative paths; `manifest.json` is written last and lists every other file's size and
sha256; a bundle without it is incomplete):

| Path | |
|---|---|
| `map/corridor.mbtiles` | corridor tiles, zoom 17; metadata `source`, `licence`, `attribution`, `imagery_date`, `downloaded`, `bounds`, `minzoom/maxzoom`, `navera_corridor` (route, half-width) → `NAVERA_MBTILES` |
| `day/` | `prepare_area.py` area from that map: `images/`, `dataset.csv`, `area.json` (terrain), `descriptors_cache.npz` (DINOv2) → `DAY_DATASET_DIR` |
| `day/terrain/` | the corridor's DEM (Copernicus DEM GLO-30, else GLO-90; free, commercial use with attribution; `--no-dem` to skip): the height above ground over relief (live_camera); `manifest.json` `day.dem`; `check` reads the route's heights from it offline |
| `day/learned_features/` | DISK features of every corridor chunk at every map level the heights need (none computed in flight) |
| `celestial/finals2000A.all` | IERS-A table (`fetch_iers.py`; `--fetch-iers` refreshes it) → `NAVERA_IERS_FILE` |
| `celestial/bsc5_mag4.5.csv` | star catalogue → `NAVERA_STAR_CATALOGUE` (cn_subscriber `allsky_catalogue`) |
| `models/hub/` | `--include-models`: DINOv2, DISK, LightGlue weights → `TORCH_HOME` (else the manifest records the sha256 of the ones required) |
| `extra/` | `--extra NAME=PATH` (lens / IMU calibrations) |
| `bundle.env`, `manifest.json` | environment for where it was built; versions, valid-until (IERS predictions), the estimate, build times |

`check` (exit 0 = PASS): every file against its sha256; every corridor tile in the MBTiles and
the area; tile metadata (source, licence, date); day matching **from the bundle's images alone**
(synthetic nadir frames rendered from its tiles along the route, 150 m prior error, 4 headings);
`--replay REC_DIR` locates recorded camera frames with truth (`screen_flight.py --record`);
every learned chunk present (`--deep`: the models load offline and the learned matcher
locates the frames computing no chunk); the IERS table gives UT1-UTC for the mission date
(`--date`) from the bundle only; the catalogue loads. It runs in its own network namespace
(`unshare -rn`, no root) when the kernel allows it, and refuses every socket call in-process
as well: any attempt is reported as a failure.

Measured on this Jetson (Orin Nano, bundles on the ADATA USB disk, 2026-10-21):

| Corridor | Tiles | Download | Bundle | Build | Estimate shown before |
|---|---|---|---|---|---|
| Sousse → Kairouan, 51.7 km, ±1 km, max 600 m (map ±1.9 km) | 3701 (2290 onboard + 1411 Esri) | 1411 tiles, 24 MB, 186 s at the 8 tiles/s limit | 454 MB (map 64, images 61, DINOv2 5.5, learned level 0: 871 chunks 320) | map-only 298 s (download included); full build from the downloaded map 264 s | 1411 tiles / 24.4 MB / 2.9 min download; 345 MB |
| Sousse 22 km, ±1 km, max 1500 m (map ±3.2 km), `--include-models` | 3056 onboard | none | 449 MB (map 40, images 38, DINOv2 4.5, learned levels 0-2: 934 chunks 225, models 138) | 302 s (day area 120 s, learned 156 s) | 419 MB / 358 s |

`check --deep --replay` of the Sousse bundle, in a network namespace (only `lo`, outbound
connect refused, no socket call attempted): every one of the 4203 files matches its sha256; the
synthetic frames are located by SIFT and by the learned matcher; **30 recorded frames of the
real Insta360 (bench screen flight `rec_clear_v20`, 1360-1500 m) are located from the bundle
alone: 30/30, median 2.2 m, max 5.1 m**; UT1-UTC comes from the bundle's IERS-A table (valid to
2027-10-04); 518 catalogue stars load. Those frames film a screen showing the same Esri
imagery as the map: an upper bound, not a field figure. The last 9 km of that corridor are at
sea (terrain profile): nothing to match there.

Web view: **not available yet — no page calls the bundle tool; make bundles with the CLI
above.** For a future page, `simulation_web.mission_prep.bundle_command(action, route, out_dir, ...)` builds the
validated command line (`plan --json`, `build --progress-json`: one `{"stage", "done",
"total"}` JSON object per line — stages `estimate`, `copy`, `download`, `day_tiles`,
`day_descriptors`, `learned`, `manifest`, `done` — then a summary line; `check --json`:
the report, `report["ok"]`); `bundle_plan(route)` returns the estimate. Python API:
`MissionSpec`, `make_sources`, `plan_bundle`, `build_bundle`, `check_bundle`.

## Mission simulator

    source ~/navera_env.sh
    navera_tools/run_sim.sh

> **Development tool — no authentication.** The simulator's control server listens on
> **all network interfaces** (port 8190, and 8443 with HTTPS) with **no password and no
> token**: anyone who can reach the machine can start missions, inject faults and drive the
> simulated autopilot. Run it only on a trusted, closed network, never on a box installed
> on a vehicle or on a networked vehicle; firewall ports 8190 and 8443 otherwise.

Open **`http://<jetson-ip>:8190`** (dashboard), or **`https://<jetson-ip>:8443`** (same page over
HTTPS with a self-signed certificate created at first start — browsers give a page the device's
location only over HTTPS or on localhost). The product's own operator view is
`http://<jetson-ip>:8181/operator` (SIMULATION banner).

The dashboard follows the original NAVERA mission planner: a **pre-flight setup** (day / night,
vehicle, speed and altitude, what gives the position when GPS is lost, whether vision positions
go to the autopilot), then the **mission planner** on a world map (hybrid satellite + place names,
satellite, street map, or the onboard map offline; switches to the onboard map by itself without
internet), with **place search** (OpenStreetMap Nominatim) or typed coordinates, **My location**
(the device's location, else the box's own position), A/B points (click, search result or drag),
and the **Map** tab to prepare any route in the world (tiles the onboard map lacks are
downloaded); then the **flight monitor**. English, French and Arabic.

1. **Plan:** choose the vehicle (drone, boat, ground robot), click the map for the **start** and
   the **destination**, set speed and altitude (the camera footprint is shown). The page
   checks the MBTiles coverage of a ±1 km corridor around the route and draws it (missing
   tiles in red).
2. **Prepare the map:** extracts the corridor's tiles and computes their DINOv2 descriptors
   with the product tool `day_pkg prepare_area.py`, with a progress bar (about 16 s for
   5 km). Prepared areas are kept in `~/.navera_sim/areas/` and reused.
3. **Fly:** choose what gives the position when GPS is lost — **Real NAVERA day vision**
   (drone only: the real `day_subscriber` on the simulated camera images) or a simulated error
   profile (*Measured today* / *Target*, the latter not a measured performance) — and whether
   vision positions are given to the autopilot (NAVERA's default: no, so the autopilot's own
   failsafe acts). **Start mission.** The autopilot waits until it accepts NAVERA's position
   (30–60 s), arms, takes off and goes to the destination. Click the map at any time for a new
   destination (a warning is logged when it leaves the prepared area).
4. **Inject faults** at any time: GPS jammed / spoofed (2 km jump) / spoofed (slow drift) / off,
   camera failed, night, IMU failed.

**Night missions** (step 3, *Night*): the real night vision (`night_subscriber`, STHN, no map
preparation) receives heading-up grey "thermal" images and the real celestial node
(`cn_subscriber`, astrometry.net) receives star images drawn from the Yale Bright Star
Catalogue for the true position and attitude at a simulated night sky time (20:30 UTC +
elapsed). The map shows the night search square and matched footprint, and the celestial fix
with its stated accuracy circle. The simulated IMU has BNO085-class attitude errors (0.3° tilt,
1.5° heading, drawn per mission), which set the celestial error (tens of km). Night vision
needs the thermal footprint to cover ~500 m × 425 m: with the simulator's physical thermal
camera (640×512, ~75° × 63°) that means flying at ~350 m or higher — below, every frame
is refused ("fly higher"). For development without root, astrometry.net can
be unpacked from the Ubuntu packages into `~/.navera_sim/astrometry/` (`solve-field` wrapper +
`astrometry.cfg`); the simulator uses it when no `solve-field` is installed.

With real vision, when GPS is lost the map zooms to vision's **search circle** (centred on the
last known position, 600 m), the candidate tiles with their scores, the tile it matched and the
position it gave; the Day vision card shows the frame's result, the score against the
threshold and the error against the truth.

The page shows the true vehicle and path, NAVERA's output (coloured by source), the autopilot's
own belief, NAVERA's state and reason, the autopilot's mode, fix and navigation filter, every
sensor, the error against the truth over time, the camera picture and an event log.

| Real (as on the box) | Simulated |
|---|---|
| `gps_node` (reads NMEA from a pseudo-terminal), **`day_subscriber` (day vision: local feature matching, DINOv2 retrieval as fallback)**, `live_camera` (with the physical camera), `navera_estimator`, `vehicle_output` (MAVLink GPS_INPUT), web bridge + operator view, `prepare_area.py`, **ArduPilot** (SITL: Copter 4.5 for the drone, Rover for the boat and robot) whose only position input is NAVERA | the world (ArduPilot's physics), the GPS receiver, IMU and clock samples, the camera images (rendered from the same satellite map vision matches against, through a simulated physical camera — lens, attitude, light, blur; flat ground — so vision looks **better than with a real camera**), the vision error when the profile mode is chosen |

A new mission restarts NAVERA's nodes, like powering the box on at a new place. Needs an
ArduPilot SITL build (`./waf configure --board sitl && ./waf copter rover`, default
`~/ardupilot`, or `$NAVERA_ARDUPILOT`). One instance at a time; ROS domain 79, loopback only;
logs in `~/.navera_sim/`. The control page has no password (see the warning above). The
simulator's arbiter loads the product's own `estimator_params.yaml`, so its freshness
windows are the box's; the default accuracy it forwards to the autopilot is 30 m (the
accuracy day vision states).

Files: `sim/sim_server.py` (world, sensors, mission, HTTP API), `sim/autopilot.py` (SITL
process and MAVLink), `sim/nmea_gps.py` (receiver), `sim/vision_link.py` (map preparation and
the camera for the real day vision), `sim/camera_view.py`, `sim/sim.html`.

## Demonstration (simulated mission)

    source ~/navera_env.sh            # NAVERA_MBTILES
    navera_tools/run_demo.sh measured # or: target

Open `http://<jetson-ip>:8181/operator`. A simulated vehicle flies a 14 km loop over Sousse at
25 m/s: GPS OK 40 s → GPS jammed 90 s → GPS restored 30 s, repeated. The real
`navera_estimator` and web bridge run on their own ROS domain (78, loopback). The view shows a red
**SIMULATION** banner, the true path (white), NAVERA's output coloured by source, and the error
against the truth. The terminal prints the output error per phase. Only one demo runs at a time: a second
`run_demo.sh` is refused (lock in `~/.navera_demo/`, where the node logs also go), and
`demo_mission.py` refuses to start if another simulated vehicle is already on the domain.

| Profile | Simulated vision error | What the operator sees during jamming | Measured on the bench (one cycle) |
|---|---|---|---|
| `measured` | matches the former DINOv2 retrieval (median ~440 m, uncertainty unknown); today's local matching: docs/VALIDATION_STATUS.md | VISION · DEGRADED | 445 m median |
| `target` | the accuracy target, 15 m sigma per axis (**not measured**) | VISION · FIX | 17–21 m median |

With GPS the output error is 3–5 m (simulated receiver, 1.5 m sigma). The demonstration shows
the system's behaviour — switching, states, operator view — not its accuracy: the vision errors
are drawn by the simulator. Never present the `target` profile as measured performance.

`demo_mission.py`, `sensor_sim.py` and `navera_fakes.py` publish fake data on the real topics: they refuse to run
unless `NAVERA_ALLOW_SIM=1` is set.
