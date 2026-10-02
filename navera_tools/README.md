# navera_tools — test and bench tools (never on a live box)

| Tool | |
|---|---|
| `run_tests.sh [--integration]` | the test suite (unit; integration starts real nodes on an isolated ROS domain) |
| `tests/test_estimator.py`, `tests/test_gps_serial.py` | integration tests |
| `sensor_sim.py` | simulated GPS/IMU/RTC on the real topics |
| `navera_fakes.py` | fake publishers for the whole graph (rqt_graph) |
| `run_scenario.sh` | scripted GPS-loss scenario with `sensor_sim` |
| `run_sim.sh` | **mission simulator** (below): control page on :8190, real NAVERA nodes, ArduPilot autopilot in the loop |
| `run_demo.sh [measured\|target]` | **demonstration**: simulated mission over Sousse with GPS jamming, on the real arbiter and operator view (`demo_mission.py`) |
| `record_session.sh <dir> [day\|night\|cn]` | record a test session (all sensors, estimates, decision, camera) into a ROS 2 bag |
| `evaluate_session.py <bag>` | measure each source against GPS in a recorded session (median / p90 / within 50-100-300 m) |
| `tests/sitl_ardupilot.py` | validate the vehicle output against ArduPilot SITL (needs an ArduPilot build) |

## Measuring accuracy on a real session

1. Start the pipeline in **shadow mode** so vision runs while GPS is valid (GPS only seeds
   its track once): `ros2 launch simulation_web day_pipeline.launch.py shadow_mode:=true`.
2. `navera_tools/record_session.sh /data/sessions/2026-10-01_drive1 day` during the drive or
   flight (on the data disk: camera frames are large).
3. `python3 navera_tools/evaluate_session.py /data/sessions/2026-10-01_drive1 --csv errors.csv`.

Only numbers produced this way, on representative data, go into docs/VALIDATION_STATUS.md.

## Mission simulator

    source ~/navera_env.sh
    navera_tools/run_sim.sh

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
needs ≥ 350 m with the simulated 84° camera. For development without root, astrometry.net can
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
| `gps_node` (reads NMEA from a pseudo-terminal), **`day_subscriber` (DINOv2 day vision)**, `navera_estimator`, `vehicle_output` (MAVLink GPS_INPUT), web bridge + operator view, `prepare_area.py`, **ArduPilot** (SITL: Copter 4.5 for the drone, Rover for the boat and robot) whose only position input is NAVERA | the world (ArduPilot's physics), the GPS receiver, IMU and clock samples, the camera images (cut north-up from the same satellite map, 84° field of view — so vision looks **better than with a real camera**), the vision error when the profile mode is chosen |

A new mission restarts NAVERA's nodes, like powering the box on at a new place. Needs an
ArduPilot SITL build (`./waf configure --board sitl && ./waf copter rover`, default
`~/ardupilot`, or `$NAVERA_ARDUPILOT`). One instance at a time; ROS domain 79, loopback only;
logs in `~/.navera_sim/`. The control page has no password: run it on a trusted network.

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
