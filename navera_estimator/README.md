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
| `gps_crosscheck_sigmas`, `gps_crosscheck_persist_s` | 5, 3 | size rules: a trusted GPS disagreeing with an independent fix of stated accuracy beyond 5 sigma + margin for 3 s, or beyond 3 sigma at 5 fixes in a row, is refused (`navera_common.gps_crosscheck`) |
| `gps_trend_enabled` | true | growth test (slow spoofing, `GpsDriftTrend`): the GPS - fix offset (vector, GPS interpolated at the fix's instant) GROWING steadily, not its size |
| `gps_trend_z` | 6 | growth needed in units of the noise the fixes show (80th-percentile jitter around the trend) |
| `gps_trend_min_growth_sigmas` | 1.5 | growth needed in units of the combined stated sigma (vision and GPS): a change inside the stated accuracy never refuses |
| `gps_trend_bias_rate_mps` | 0.2 | slow vision-bias change allowed before counting growth |
| `gps_trend_min_jitter_m` | 3 | floor of the measured jitter |
| `gps_trend_min_fixes`, `gps_trend_confirm_n` | 6, 3 | fixes in a window (each quarter >= 3), and windows passing at this many fixes in a row before refusing |
| `gps_trend_windows_s` | 8 … 128 | window lengths tested at every fix (first quarter / middle half / last quarter must grow in order: a run of wrong fixes is a step, not a growth) |

A growth refusal is lifted only once the offset is back nearer its value before the growth (it
refuses inside 3 sigma, so "agrees within 3 sigma" alone would let the spoofed GPS straight back).
Measured (`navera_tools/bench/replay_spoof_trend.py`, real screen-bench campaigns, one vision fix
per 2 s as the day node's GPS checks): no false refusal; a 3 m/s drift refused at ~70 m instead of
~120 m with the 30 m uncalibrated vision sigma — see docs/VALIDATION_STATUS.md.

## `compute_health_node` — compute health (hazard H-11)

Started by `estimator.launch.py` next to the arbiter (respawned on failure, never stops it).
Every 2 s it reads, without root, the files tegrastats uses (`navera_common/compute_health.py`):
thermal zones, throttling cooling devices, `/proc/meminfo` (memory, swap) and the GPU load, and
publishes `/diagnostics` (one status `navera: compute health`), `/navera/compute_health` (JSON) and
the latched `/navera/compute/degraded` (Bool). A box without swap is reported at start (F5).

| Parameter | Default | |
|---|---|---|
| `period_s` | 2.0 | sampling period |
| `temp_warn_c`, `temp_degrade_c` | 85, 95 | hottest zone: WARN, then degraded (cleared 5 C below) |
| `mem_warn_pct`, `mem_degrade_pct` | 15, 8 | memory available (% of total): WARN, then degraded (cleared 4 % above) |

While degraded, day vision skips its height retries and night vision its heading / height retries
(`watch_degraded`): fewer inferences per frame on a hot or memory-starved box.
