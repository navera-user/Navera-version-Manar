# navera_msgs

Interface definitions for NAVERA. **Interfaces only — this package contains no code**
(ROS2 convention for `rosidl` packages; built with `ament_cmake` + `rosidl_generate_interfaces`).
Shared Python helpers live in `navera_common`. No nodes, no parameters.

## Messages

| Message | Published on | By | Consumed by |
|---|---|---|---|
| `PositionEstimate` | `/navera/estimate/{gps,day,night,cn}` | `gps_pkg`, `day_pkg`, `night_pkg`, `cn_pkg` | `navera_estimator` |
| `PositionEstimate` | `/navera/position` (the elected position) | `navera_estimator` | `navera_output`, `simulation_web` bridges |
| `NavStatus` (with `SourceHealth[]`) | `/navera/nav_status` | `navera_estimator` | `navera_output`, `simulation_web`, `navera_tools/check_box.py` |

### `msg/PositionEstimate.msg`

One geodetic position produced by one source, with its provenance and its uncertainty.
Every localization source publishes this, and the arbiter (`navera_estimator`) plus the
operator interface consume it. It replaces the current pattern of a bare
`sensor_msgs/NavSatFix` that has to be joined by `frame_id` against a `std_msgs/String`
JSON status topic to be interpretable.

| Field | Purpose |
|---|---|
| `header` | `stamp` = publication instant, `frame_id` = sensor frame |
| `latitude` / `longitude` / `altitude` | WGS84 degrees; altitude in m above the ellipsoid, `NaN` if unknown |
| `position_covariance` | 3x3 ENU, row-major, m² — same convention as `NavSatFix` |
| `position_covariance_type` | `UNKNOWN` / `APPROXIMATED` / `DIAGONAL_KNOWN` / `KNOWN` |
| `source` | which source produced it (`uint8` enum) |
| `mode` | `MEASURED` / `PROPAGATED` / `HELD` / `REPLAYED` |
| `valid` | `false` = do not use this position |
| `confidence` | `[0,1]`, **source-local, not comparable across sources** |
| `reason` | human-readable explanation of a rejection or degradation |
| `sensor_stamp` | instant of the measurement itself (image exposure, NMEA sentence) |
| `producer` / `model_id` / `frame_index` | traceability |
| `details_json` | source-specific diagnostic extras |

### `msg/NavStatus.msg`

The navigation system's decisional summary, published by `navera_estimator`: do we have a usable
position and how much do we trust it, who provides it, which sources are alive.

| Field | Purpose |
|---|---|
| `header` | `stamp` = instant this status was computed |
| `state` | `STATE_INITIALIZING` (0) / `STATE_NO_FIX` (1) / `STATE_FIX` (2: fresh MEASURED position with bounded uncertainty) / `STATE_DEGRADED` (3: MEASURED with UNKNOWN uncertainty, or PROPAGATED / HELD) |
| `active_source` | source owning the published solution (same `SOURCE_*` values as `PositionEstimate`); `SOURCE_UNKNOWN` while INITIALIZING / NO_FIX |
| `active_mode` | `MODE_*` of the winning estimate (same values as `PositionEstimate`) |
| `sources` | `SourceHealth[]`, one row per watched source |
| `reason` | one line for display, never parsed |

### `msg/SourceHealth.msg`

Liveness of one source, one row per watched source inside `NavStatus.sources[]`.

| Field | Purpose |
|---|---|
| `source` | `SOURCE_*` (same values as `PositionEstimate`) |
| `alive` | heard from within this source's liveness timeout |
| `last_seen` | `builtin_interfaces/Time` of the last message; zero if never heard |
| `contributing` | true iff this source feeds the current published solution (the IMU is alive but never contributing) |

`SOURCE_*` values (all three messages, append-only, keep in sync): 0 UNKNOWN, 1 GPS, 2 DAY_VISION,
3 NIGHT_VISION, 4 CELESTIAL, 5 INERTIAL, 6 FUSED, 7 VLM (reserved), 8 EXTERNAL (reserved).
`MODE_*`: 0 MEASURED, 1 PROPAGATED, 2 HELD, 3 REPLAYED.

## The three rules

**1. Fuse on covariance, gate on confidence.** `position_covariance` is the only quantity
that may be combined mathematically. `confidence` is source-local: a DINOv2 cosine
similarity of 0.8 and an STHN inverse-RMS score of 0.8 do not mean the same thing.
Filters use the covariance; gating and the UI use the confidence against a **per-source**
threshold.

**2. `mode` is not optional.** Today a pipeline that replays dataset ground truth, one that
dead-reckons, and one that actually ran its model all publish an indistinguishable
`NavSatFix`. `mode` makes that distinction structural: `MODE_REPLAYED` must never be able
to pass itself off as `MODE_MEASURED`. This is the field the certification dossier rests on.

**3. Nothing decides on `details_json`.** It is diagnostic payload. The moment a value in it
becomes decisional, promote it to a typed field.

## Honesty about uncertainty

Publish `COVARIANCE_TYPE_UNKNOWN` rather than an invented matrix — downstream, a fabricated
covariance is indistinguishable from a measured one. `gps_node` derives its covariance from HDOP
(`ros_gps_node` copies the receiver's). The day, night and celestial pipelines now state an
`APPROXIMATED` covariance when they have a stated accuracy; how far those stated accuracies are
measured (and on which data) is recorded in `docs/VALIDATION_STATUS.md`, not here.

## Build

```bash
source /opt/ros/humble/setup.bash
colcon build --packages-select navera_msgs
source install/setup.bash
ros2 interface show navera_msgs/msg/PositionEstimate
ros2 topic echo /navera/nav_status        # on a running system
```

Changing this message requires rebuilding every package that depends on it.
