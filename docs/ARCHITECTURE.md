# NAVERA — Architecture and interfaces

Reference for integrators and developers. Measured performance and limitations are in
[VALIDATION_STATUS.md](VALIDATION_STATUS.md); open work is in
[ENGINEERING_BACKLOG.md](ENGINEERING_BACKLOG.md).

## 1. Data flow

```
                         /navera/estimate/gps
gps_node ──────────────────────────────────────────┐
  (NMEA serial)                                    │
camera_publisher ─► day_subscriber ── /navera/estimate/day ───┤
  (/day/*)          (DINOv2 tiles)                           │
camera_publisher ─► night_subscriber ─ /navera/estimate/night ┼─► navera_estimator ─┬─► /navera/position
  (/thermal/*)      (STHN)                                   │   (arbiter)         └─► /navera/nav_status
camera_publisher ─► cn_subscriber ─── /navera/estimate/cn ────┤                          │
  (/celestial/*)    (astrometry.net)                          │                          ▼
imu_node ── /navera/sensors/imu (liveness) ───────────────────┘              navera_web_bridge (:8181)
rtc_node ── /navera/sensors/rtc_time ─► cn_subscriber (time)                 /operator, /, /tiles
```

- One vision pipeline runs at a time (GPU memory), selected by the systemd service enabled
  and by `NAVERA_PIPELINE` for the web bridge.
- The vision pipelines use the last valid GPS fix (`/navera/estimate/gps`) as their search
  prior. While GPS is healthy they stay idle; when it drops, they continue from its last fix.
- All nodes run on the box and talk over loopback DDS (`ROS_LOCALHOST_ONLY=1`, own
  `ROS_DOMAIN_ID`). Operators reach the box over HTTP only.

## 2. The position contract — `navera_msgs/PositionEstimate`

Every source publishes the same message on `/navera/estimate/<source>`:

| Field | Meaning |
|---|---|
| `latitude`, `longitude`, `altitude` | WGS84; altitude above the ellipsoid, NaN if unknown |
| `position_covariance[9]`, `position_covariance_type` | ENU, m², row-major; `UNKNOWN` rather than an invented value |
| `source` | GPS, DAY_VISION, NIGHT_VISION, CELESTIAL, … |
| `mode` | MEASURED, PROPAGATED (dead-reckoned), HELD, REPLAYED (test data, never valid) |
| `valid`, `reason` | whether the position may be used, and why not |
| `sensor_stamp` | instant of the measurement (image exposure, NMEA sentence) |
| `header.stamp` | publication instant |
| `producer`, `model_id`, `frame_index`, `details_json` | traceability; nothing may decide on `details_json` |

## 3. The arbiter — `navera_estimator`

- Priority: GPS > day > night > celestial. A source is eligible when `valid`, `mode` is
  MEASURED or PROPAGATED, its `sensor_stamp` is fresh (per-source timeout, not in the
  future), and its position and covariance are finite.
- GPS must also pass a kinematic gate: a fix the vehicle could not have reached
  (`max_speed_mps` × elapsed time + margin) is refused ("possible spoofing") until it is
  reachable again.
- A higher-priority source must stay usable for `switch_holdoff_s` before it takes over.
- `/navera/position`: the winning estimate, published once per new measurement.
- `/navera/nav_status` (5 Hz): the state, the active source and mode, the health of each
  source, and the reason in plain words. The states are:
  - **FIX:** measured, with a known sigma ≤ `fix_max_sigma_m`;
  - **DEGRADED:** a position with an unknown or large uncertainty, or dead-reckoned;
  - **NO_FIX:** no usable source;
  - **INITIALIZING:** nothing received yet since start-up.

## 4. Topics

| Topic | Type | From | To |
|---|---|---|---|
| `/navera/sensors/gps_fix` | sensor_msgs/NavSatFix | gps_node | diagnostics |
| `/navera/sensors/gps_vel` | geometry_msgs/TwistStamped (ENU m/s) | gps_node | — |
| `/navera/sensors/imu` | sensor_msgs/Imu | imu_node | estimator (liveness) |
| `/navera/sensors/rtc_time`, `rtc_status` | TimeReference, String (JSON) | rtc_node | cn_subscriber |
| `/navera/estimate/{gps,day,night,cn}` | navera_msgs/PositionEstimate | sources | estimator, vision (GPS prior) |
| `/navera/position` | navera_msgs/PositionEstimate | estimator | web bridge, vehicle |
| `/navera/nav_status` | navera_msgs/NavStatus | estimator | web bridge, vehicle |
| `/<cam>/image_raw`, `/<cam>/frame_meta` | Image, String (JSON) | camera_publisher | localizer |
| `/<cam>/camera/start` | Bool (latched) | web bridge | camera, localizer |
| `/<loc>/localizer_ready` | Bool (latched) | localizer | camera, web bridge |
| `/<cam>/frame_done` | Int32 | localizer | camera |
| `/<loc>/position_estimate`, `/<loc>/<loc>_status` | NavSatFix, String (JSON) | localizer | web bridge (dashboard) |

`<cam>` / `<loc>`: `day`/`day`, `thermal`/`night`, `celestial`/`cn`.

## 5. Camera ↔ localizer protocol

1. **Start gate:** the camera streams only after `camera/start` is true, a latched command
   sent by the web bridge on mission start. A `false` means pause and rewind; the localizer
   then resets its tracking.
2. **Handshake:** frame 1 waits for `localizer_ready`, which is latched once the model is
   loaded and warmed up.
3. **Back-pressure:** the next frame is sent only after `frame_done` acknowledges the previous
   one. Processing is strictly serial.
4. **Pairing:** each `frame_meta` carries `image_stamp_ns`, the stamp of its image; the
   localizer pairs image and meta on it. A frame whose image is missing or undecodable is
   acknowledged at once and declared invalid.

## 6. Web interface (`navera_web_bridge`, port 8181)

| Endpoint | Purpose |
|---|---|
| `GET /operator` | Operator view: the arbiter's decision (FIX / DEGRADED / NO FIX / OFFLINE / LINK LOST). The vehicle marker is removed whenever there is no valid position |
| `GET /api/operator_position` | That decision as JSON (`valid`, `state`, `source`, `mode`, `age_s`, `reason`) |
| `GET /` | Mission planner and replay dashboard |
| `GET /tiles/{z}/{x}/{y}` | Satellite tiles from the MBTiles map (read-only, bounded) |
| `POST /api/set_mission` | Start/rewind the mission; requires `X-Navera-Token` (`NAVERA_WEB_TOKEN`) |
| `GET /health` | Liveness of the bridge process |

No CORS headers are sent; request bodies are limited to 4 KiB of JSON; idle connections time out after 10 s.
With `NAVERA_TLS_CERT` / `NAVERA_TLS_KEY` set, the bridge serves HTTPS only (TLS ≥ 1.2).

## 7. Deployment

Services, installation, pipeline selection and site settings are covered in
[deploy/README.md](../deploy/README.md). Tests: `navera_tools/run_tests.sh [--integration]`.
