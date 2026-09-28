# navera_tools — test and bench tools (never on a live box)

| Tool | |
|---|---|
| `run_tests.sh [--integration]` | the test suite (unit; integration starts real nodes on an isolated ROS domain) |
| `tests/test_estimator.py`, `tests/test_gps_serial.py` | integration tests |
| `sensor_sim.py` | simulated GPS/IMU/RTC on the real topics |
| `navera_fakes.py` | fake publishers for the whole graph (rqt_graph) |
| `run_scenario.sh` | scripted GPS-loss scenario with `sensor_sim` |
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

`sensor_sim.py` and `navera_fakes.py` publish fake data on the real topics: they refuse to run
unless `NAVERA_ALLOW_SIM=1` is set.
