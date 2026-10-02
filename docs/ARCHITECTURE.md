# NAVERA — Architecture and interfaces

Reference for integrators and developers. Measured performance and limitations are in
[VALIDATION_STATUS.md](VALIDATION_STATUS.md); open work is in
[ENGINEERING_BACKLOG.md](ENGINEERING_BACKLOG.md); installation in
[deploy/README.md](../deploy/README.md).

## 1. Data flow

```
GPS source (navera-gps, NAVERA_GPS_SOURCE)
  gps_node      (serial NMEA)          ─┐
  ros_gps_node  (/navera/vehicle/gps2   ├─► /navera/sensors/gps_fix
                 or a vehicle ROS topic)─┘   /navera/estimate/gps ───────────────────────┐
                                                                                          │
attitude / height (NAVERA_SENSOR_SOURCE)                                                  │
  imu_node ─► /navera/sensors/imu            (box)                                        │
  vehicle_link_node ─► /navera/vehicle/imu, altitude_agl, relative_alt, gps2, status      │
  the vehicle's ROS topics                    (ros)                                       │
        │                                                                                 │
        ▼                                                                                 ▼
live_camera (or replay camera_publisher) ─► day_subscriber ─── /navera/estimate/day ──► navera_estimator
  /day/*            ▲                       (local feature matching)                    (arbiter)
                    │ prior: /navera/position (GPS)                                       │
live_camera ─► night_subscriber ─── /navera/estimate/night ───────────────────────────► │
  /thermal/*        (STHN)                                                                │
camera_publisher ─► cn_subscriber ── /navera/estimate/cn ─────────────────────────────► │
  /celestial/*      (astrometry.net)   ◄── rtc_node (/navera/sensors/rtc_time)            │
                                                                                          ▼
                                         /navera/position  +  /navera/nav_status
                                             │                       │
                    vehicle_output_node ◄────┤                       ├──► navera_web_bridge (:8181)
                    NMEA / MAVLink GPS_INPUT / /navera/fix           │    /operator  /  /mission
                                             ▼                       │
                                     the vehicle's autopilot   imu_node (WMM declination)
```

- One GPU vision pipeline runs at a time (day **or** night), selected by the systemd unit
  enabled and, for the web bridge, by `NAVERA_PIPELINE`. The celestial pipeline (CPU) can
  run beside it.
- Every node runs on the box and talks over DDS. The default site settings keep DDS on
  loopback (`ROS_LOCALHOST_ONLY=1`, own `ROS_DOMAIN_ID`); operators reach the box over HTTP.
  A ROS-based vehicle requires joining its graph (deploy/README.md §6).

### How the prior reaches the vision pipelines

Vision does not search the whole map (measured unreliable; disabled): it searches around a
prior. Day and night vision take their prior from **the arbiter's output**,
`/navera/position`, and only while the arbiter's active source is GPS — never from the raw
GPS topic, so a GPS the arbiter has refused (spoofing) cannot move the search centre. While
GPS is in use the pipelines stay idle (except in shadow mode, `NAVERA_SHADOW_MODE=true`) and
keep tracking it; when the arbiter stops using GPS they continue from its last vetted
position (day vision starts from its own last fix instead when that fix shows the GPS was
drifting away). **NAVERA therefore needs one
GPS fix at start, whatever its sources.** After a service restart, day vision reuses its
last position if it is less than 5 minutes old (`navera_common/state_store.py`,
`NAVERA_STATE_DIR`). The celestial node uses its `prior_lat` / `prior_lon` parameters, else
the last valid `/navera/estimate/gps` fix.

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
  MEASURED or PROPAGATED, its stamp is fresh (per-source timeout, not more than 0.5 s in the
  future), and its position and covariance are finite.
- A higher-priority source must stay usable for `switch_holdoff_s` (2 s) before it takes over.
- `/navera/position`: the winning estimate, published once per new measurement.
- `/navera/nav_status` (5 Hz): the state, the active source and mode, the health of each
  source, and the reason in plain words. The states are:
  - **FIX:** measured, with a known σ ≤ `fix_max_sigma_m` (25 m) — today only GPS;
  - **DEGRADED:** a position with an unknown or larger uncertainty, or dead-reckoned — every
    vision and celestial position today (day vision states 30 m until measured);
  - **NO_FIX:** no usable source;
  - **INITIALIZING:** nothing received yet since start-up.
- The IMU topic it watches for liveness follows `NAVERA_SENSOR_SOURCE` (`imu_topic`).

### GPS protection (anti-spoofing)

1. **Kinematic gate.** A GPS fix farther from the last trusted fix than the vehicle could
   have travelled (`max_speed_mps` × elapsed + `gps_jump_margin_m` 50 m; the speed comes from
   `NAVERA_MAX_SPEED_KMH`) is refused ("implausible jump … — possible spoofing").
2. **Cross-check against vision while GPS is good.** While GPS is trusted, day vision still
   matches one frame around the GPS position every 2 s (`gps_check_period_s`, within
   `gps_check_radius_m` 600 m) and publishes it as an independent estimate with its stated
   accuracy. The estimator compares every GPS fix with the freshest independent source of
   **stated** accuracy (vision or celestial with a known covariance), at the instant that
   source measured. GPS is refused ("GPS drifting away from …") when either:
   - it disagrees beyond 5 σ (+ 50 m + max speed × time gap) for 3 s
     (`gps_crosscheck_sigmas`, `gps_crosscheck_persist_s`), with at least **2 distinct**
     independent fixes disagreeing (one wrong vision fix never refuses GPS); or
   - **5 distinct independent fixes in a row** disagree beyond 3 σ (+ max speed × time gap)
     — a slow drift, caught before the 5 σ gate.
3. **Re-acceptance.** A GPS refused by the cross-check, or returning after an outage ("jam,
   then spoof"), is re-accepted **only when it agrees with an independent fix** (within the
   5 σ tolerance: "GPS confirmed by … — re-accepted"). Only if no independent source of
   stated accuracy has been heard for 120 s is GPS judged on its own again (kinematic gate).

All three protections need an independent source with a stated accuracy. With vision of
unknown accuracy only the kinematic gate applies: a sudden jump is caught, a patient or
gradual spoofer is not (VALIDATION_STATUS.md, known limitation 7).

## 4. Nodes

| Node (package) | Service | Role |
|---|---|---|
| `gps_node` (gps_pkg) | navera-gps, `NAVERA_GPS_SOURCE=serial` | NMEA receiver (checksummed) → `/navera/sensors/gps_fix`, `/navera/sensors/gps_vel`, `/navera/estimate/gps`; exits when the port is lost |
| `ros_gps_node` (gps_pkg) | navera-gps, `vehicle` / `ros` | Republishes a NavSatFix (`/navera/vehicle/gps2`, or `NAVERA_ROS_GPS_TOPIC`) exactly like gps_node: `/navera/sensors/gps_fix` + `/navera/estimate/gps` (valid only with a fix) |
| `imu_node` (imu_pkg) | navera-imu | BNO085 → `/navera/sensors/imu`, vehicle frame, true north (WMM at `/navera/position`) |
| `rtc_node` (rtc_pkg) | navera-rtc | DS3231 → `/navera/sensors/rtc_time`, `/navera/sensors/rtc_status` |
| `vehicle_link_node` (navera_output) | navera-vehicle-link | Autopilot over MAVLink → `/navera/vehicle/imu`, `altitude_agl`, `relative_alt`, `gps2`, `status` (link, armed). Ignores non-autopilot heartbeats; never reads the autopilot's fused position |
| `live_camera` (camera_pkg) | pipelines, `NAVERA_CAMERA=live` | The real camera, see §5 |
| `camera_publisher` (camera_pkg) | pipelines, `NAVERA_CAMERA=replay`; celestial | Replays recorded frames (CSV + images) with the same protocol |
| `day_subscriber` (day_pkg) | navera-pipeline-day | Day vision: local feature matching against the activated route map around the prior (DINOv2 retrieval as fallback when the frame scale is unknown) |
| `night_subscriber` (night_pkg) | navera-pipeline-night | Night vision: STHN thermal-to-satellite homography |
| `cn_subscriber` (cn_pkg) | navera-pipeline-cn | Celestial: astrometry.net plate solve + attitude at exposure (`imu_topic`) |
| `estimator_node` (navera_estimator) | navera-estimator | The arbiter (§3) |
| `vehicle_output` (navera_output) | navera-output | Output to the vehicle (§6) |
| `navera_web_bridge` / `navera_stellar_bridge` (simulation_web) | navera-web | HTTP :8181 (§8) |

## 5. The live camera — `camera_pkg/live_camera.py`

Input (`NAVERA_CAMERA_INPUT`): **usb** (V4L2, e.g. Insta360 ONE R in webcam mode, addressed
by `/dev/v4l/by-id/…`), **csi** (GStreamer `nvarguscamerasrc`), or **ros** (any
`sensor_msgs/Image` topic, `NAVERA_CAMERA_TOPIC`). For every frame offered to vision:

1. **Exposure stamp:** grab time − `NAVERA_CAMERA_LATENCY_S` (ROS input: the image stamp −
   latency). Every sensor value below is taken at that instant.
2. **Attitude** at the exposure, interpolated from the `imu_topic` history (box IMU, vehicle
   link or the vehicle's ROS IMU, per `NAVERA_SENSOR_SOURCE`). No attitude → the frame is
   marked unusable ("no attitude at the frame's exposure …"); a frozen attitude (1 s of
   identical samples) is not used.
3. **Undistortion** with the lens calibration (`NAVERA_CAMERA_CALIBRATION`, from
   `navera_tools/calibrate_camera.py`; refused if made at another resolution or, for USB, with
   another camera), or an ideal lens of `NAVERA_CAMERA_HFOV_DEG`.
4. **Straightening** to a level, straight-down view with the attitude and the camera mount
   (`NAVERA_CAMERA_MOUNT_RPY`; with `NAVERA_CAMERA_GIMBAL=true` only the heading is used).
   Frames tilted more than `NAVERA_CAMERA_MAX_TILT_DEG` (45°) are marked unusable ("camera
   tilted N deg from vertical …").
5. **Height above ground** (`navera_common/altitude.py`): a downward rangefinder
   (`altitude_topic`), else the height measured from the image by day vision
   (`/navera/vision/altitude_agl`) carried forward by the barometric height above home
   (`/navera/vehicle/relative_alt`) or the GPS altitude above the ground altitude (the first
   GPS fix, or `NAVERA_GROUND_ALTITUDE_M`). The ground altitude survives a restart (12 h,
   within 2 km).
6. Publishes `<ns>/image_raw`, `<ns>/frame_meta` (JSON: exposure stamp, attitude, tilt,
   heading of the image top, altitude and its source, the field of view of the undistorted
   image, usable / reason, GPS for evaluation) and `<ns>/camera_info`, with the same start
   gate, handshake and back-pressure as the replay camera — but always the **newest** frame,
   never a queue.

## 6. Output to the vehicle — `navera_output`

`vehicle_output` sends the arbiter's decision as NMEA (GGA + RMC), MAVLink `GPS_INPUT` and a
ROS `NavSatFix` on `/navera/fix` (`NAVERA_ROS_FIX_TOPIC`). FIX is sent as a fix with its
accuracy; DEGRADED is withheld unless `NAVERA_FORWARD_DEGRADED=true` with a stated
`NAVERA_DEGRADED_SIGMA_M`; everything else is an explicit "no fix". Each position is sent
once, stamped with its measurement instant, and not at all if measured more than
`NAVERA_MAX_MEASUREMENT_AGE_S` (2 s) ago. Details:
[navera_output/README.md](../navera_output/README.md), autopilot setup:
[ARDUPILOT_INTEGRATION.md](ARDUPILOT_INTEGRATION.md).

## 7. Topics

| Topic | Type | From | To |
|---|---|---|---|
| `/navera/sensors/gps_fix` | sensor_msgs/NavSatFix | gps_node / ros_gps_node | live camera, diagnostics |
| `/navera/sensors/gps_vel` | geometry_msgs/TwistStamped (ENU m/s) | gps_node | vehicle_output (velocity with GPS fixes) |
| `/navera/sensors/imu` | sensor_msgs/Imu | imu_node | live camera, night, celestial, estimator (`NAVERA_SENSOR_SOURCE=box`) |
| `/navera/sensors/rtc_time`, `rtc_status` | TimeReference, String (JSON) | rtc_node | cn_subscriber, check_box |
| `/navera/vehicle/imu`, `altitude_agl`, `relative_alt` | Imu, Range, PointStamped | vehicle_link_node | live camera and pipelines (`vehicle`) |
| `/navera/vehicle/gps2` | sensor_msgs/NavSatFix | vehicle_link_node | ros_gps_node (`NAVERA_GPS_SOURCE=vehicle`) |
| `/navera/vehicle/status` | String (JSON) | vehicle_link_node | web bridge (armed lock), check_box |
| `/navera/vision/altitude_agl` | sensor_msgs/Range | day_subscriber | live camera (height from the image) |
| `/navera/estimate/{gps,day,night,cn}` | navera_msgs/PositionEstimate | sources | estimator |
| `/navera/position` | navera_msgs/PositionEstimate | estimator | vehicle_output, web bridge, day/night prior, imu_node (declination) |
| `/navera/nav_status` | navera_msgs/NavStatus | estimator | vehicle_output, web bridge, day/night |
| `/navera/fix` | sensor_msgs/NavSatFix | vehicle_output | the vehicle's ROS software |
| `/<cam>/image_raw`, `/<cam>/frame_meta`, `/<cam>/camera_info` | Image, String (JSON), CameraInfo | camera | localizer |
| `/<cam>/camera/start` | Bool (latched) | web bridge | camera, localizer |
| `/<loc>/localizer_ready` | Bool (latched) | localizer | camera, web bridge |
| `/<cam>/frame_done` | Int32 | localizer | camera |
| `/<loc>/position_estimate`, `/<loc>/<loc>_status` | NavSatFix, String (JSON) | localizer | web bridge (dashboard) |

`<cam>` / `<loc>`: `day`/`day`, `thermal`/`night`, `celestial`/`cn`.

## 8. Camera ↔ localizer protocol

1. **Start gate:** the replay camera streams only after `camera/start` is true, a latched
   command sent by the web bridge on mission start; a `false` means pause and rewind (the
   localizer then resets its tracking). The live camera starts unpaused.
2. **Handshake:** frame 1 waits for `localizer_ready`, latched once the model is loaded and
   warmed up.
3. **Back-pressure:** the next frame is sent only after `frame_done` acknowledges the previous
   one. Processing is strictly serial.
4. **Pairing:** each `frame_meta` carries `image_stamp_ns`, the stamp of its image; the
   localizer pairs image and meta on it. A frame whose image is missing or undecodable is
   acknowledged at once and declared invalid.

## 9. Web interface (`navera_web_bridge`, port 8181)

| Endpoint | Purpose |
|---|---|
| `GET /operator` | Operator view: the arbiter's decision (FIX / DEGRADED / NO FIX / OFFLINE / LINK LOST). The vehicle marker is removed whenever there is no valid position |
| `GET /api/operator_position` | That decision as JSON (`valid`, `state`, `source`, `mode`, `age_s`, `reason`) |
| `GET /` | Mission planner and replay dashboard |
| `GET /mission`, `GET /api/mission/state` | Mission preparation: vehicle settings, route, route map |
| `POST /api/mission/{settings,apply,plan,generate,activate,cancel}` | Mission preparation actions; token required |
| `GET /tiles/{z}/{x}/{y}` | Satellite tiles from the MBTiles map (read-only, bounded) |
| `POST /api/set_mission` | Start/rewind the mission; token required |
| `GET /health` | Liveness of the bridge process |

Control endpoints require the `X-Navera-Token` header equal to `NAVERA_WEB_TOKEN` (none
configured = read-only). No CORS headers are sent; request bodies are limited to 4 KiB of
JSON (512 KiB for an imported mission file); idle connections time out. With `NAVERA_TLS_CERT` / `NAVERA_TLS_KEY` set, the bridge
serves HTTPS only (TLS ≥ 1.2).

**`/mission`** (`simulation_web/mission_prep.py`): sets only `NAVERA_VEHICLE_TYPE`,
`NAVERA_MAX_SPEED_KMH`, `NAVERA_DAY_HFOV_DEG`, `NAVERA_THERMAL_HFOV_DEG`,
`NAVERA_IMU_MOUNT_RPY`, `NAVERA_DECLINATION_DEG` (validated, written to
`/var/lib/navera/settings.env`) and, through "Activate", `DAY_DATASET_DIR`. It plans a route
from an autopilot mission file (`.waypoints`, `.plan`) or a drawn route, generates its
corridor map (`day_pkg/prepare_area.py`) and activates it. "Apply", "Activate" and
"Generate" are refused while the vehicle is armed (from `/navera/vehicle/status`) or NAVERA
is navigating without GPS (`nav_status` DEGRADED). The only root rights are the exact
`systemctl` commands in `deploy/sudoers/navera-web`.

## 10. Deployment

Services, installation, sources, pipeline selection and site settings:
[deploy/README.md](../deploy/README.md). Problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
Tests: `navera_tools/run_tests.sh [--integration]`.
