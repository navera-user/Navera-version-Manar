# navera_estimator — position arbiter

`estimator_node` elects one position from the sources and publishes the decision:
`/navera/position` (the winning PositionEstimate, once per measurement) and
`/navera/nav_status` (5 Hz: FIX / DEGRADED / NO_FIX / INITIALIZING, active source, source
health, reason). Rules: [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §3.

## Parameters (`config/estimator_params.yaml`)
| Parameter | Default | |
|---|---|---|
| `publish_rate_hz` | 5.0 | decision rate |
| `gps_timeout_s`, `day_timeout_s`, `night_timeout_s`, `cn_timeout_s` | 3, 3, 5, 45 | freshness of each source (on `sensor_stamp`) |
| `imu_timeout_s` | 1.0 | IMU liveness |
| `future_tolerance_s` | 0.5 | stamps further in the future are refused — for good: a message that arrived from the future never becomes alive when the clock catches up, and freshness also needs the receive time within the source's timeout |
| `switch_holdoff_s` | 2.0 | dwell before a higher-priority source takes over |
| `max_speed_mps` | 100 | **set per vehicle** — GPS jump / spoofing gate: the top ground speed plus wind, e.g. 15 m/s multicopter → 25, fixed wing 30 m/s → 45, car 40 m/s → 45. Too high lets a spoofer drag GPS at that speed; too low refuses a real GPS |
| `gps_jump_margin_m` | 50 | GPS noise allowance in that gate |
| `gps_jump_window_s` | 20 | the gate also against every trusted fix of this window, with one margin: per fix only, a steady drag of max speed + margin/period passed (150 m/s with the defaults) |
| `fix_max_sigma_m` | 25 | largest horizontal sigma still reported as FIX |
