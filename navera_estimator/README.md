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
| `future_tolerance_s` | 0.5 | stamps further in the future are refused |
| `switch_holdoff_s` | 2.0 | dwell before a higher-priority source takes over |
| `max_speed_mps` | 100 | **set per vehicle** — GPS jump / spoofing gate |
| `gps_jump_margin_m` | 50 | GPS noise allowance in that gate |
| `fix_max_sigma_m` | 25 | largest horizontal sigma still reported as FIX |
