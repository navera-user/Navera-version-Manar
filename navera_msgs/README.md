# navera_msgs

Interface definitions for NAVERA. **Interfaces only — this package contains no code**
(ROS2 convention for `rosidl` packages). Shared fill helpers will live in a separate
`navera_common` Python package.

## Messages

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
covariance is indistinguishable from a measured one. At the time of writing, only `gps_node`
computes a real covariance (from HDOP). The vision pipelines need their `σ(score)` calibrated
against ground truth before they can claim `APPROXIMATED`, and celestial has no calibrated
uncertainty at all (its `match_score` is a hardcoded constant).

## Build

```bash
source /opt/ros/humble/setup.bash
colcon build --packages-select navera_msgs
source install/setup.bash
ros2 interface show navera_msgs/msg/PositionEstimate
```

Changing this message requires rebuilding every package that depends on it.
