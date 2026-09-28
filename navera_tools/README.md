# navera_tools — test and bench tools (never on a live box)

| Tool | |
|---|---|
| `run_tests.sh [--integration]` | the test suite (unit; integration starts real nodes on an isolated ROS domain) |
| `tests/test_estimator.py`, `tests/test_gps_serial.py` | integration tests |
| `sensor_sim.py` | simulated GPS/IMU/RTC on the real topics |
| `navera_fakes.py` | fake publishers for the whole graph (rqt_graph) |
| `run_scenario.sh` | scripted GPS-loss scenario with `sensor_sim` |
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
| `measured` | matches today's day vision (median ~440 m, uncertainty unknown) | VISION · DEGRADED | 445 m median |
| `target` | the accuracy target, 15 m sigma per axis (**not measured**) | VISION · FIX | 17–21 m median |

With GPS the output error is 3–5 m (simulated receiver, 1.5 m sigma). The demonstration shows
the system's behaviour — switching, states, operator view — not its accuracy: the vision errors
are drawn by the simulator. Never present the `target` profile as measured performance.

`demo_mission.py`, `sensor_sim.py` and `navera_fakes.py` publish fake data on the real topics: they refuse to run
unless `NAVERA_ALLOW_SIM=1` is set.
