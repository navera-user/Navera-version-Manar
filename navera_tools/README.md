# navera_tools — test and bench tools (never on a live box)

| Tool | |
|---|---|
| `run_tests.sh [--integration]` | the test suite (unit; integration starts real nodes on an isolated ROS domain) |
| `tests/test_estimator.py`, `tests/test_gps_serial.py` | integration tests |
| `sensor_sim.py` | simulated GPS/IMU/RTC on the real topics |
| `navera_fakes.py` | fake publishers for the whole graph (rqt_graph) |
| `run_scenario.sh` | scripted GPS-loss scenario with `sensor_sim` |

`sensor_sim.py` and `navera_fakes.py` publish fake data on the real topics: they refuse to run
unless `NAVERA_ALLOW_SIM=1` is set.
