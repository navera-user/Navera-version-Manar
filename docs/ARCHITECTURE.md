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
GPS fix at start, whatever its sources** — or, for day vision, an operator start position
(`/navera/operator/start_position`, latched, sent by the `/mission` page's "Start without
GPS"): while no GPS is trusted, day vision searches there in a circle as wide as the stated
accuracy (5–20000 m). That message is a search area, never published on
`/navera/position` nor sent to the vehicle. After a service restart, day vision reuses its
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
  future), its position is finite and in range, and its covariance is one: finite,
  non-negative variances, symmetric, horizontal block positive semi-definite (a covariance
  that is not would break a consumer's filter: the estimate is not used at all).
- Freshness windows (production config `navera_estimator/config/estimator_params.yaml`):
  GPS 3 s, day vision 5 s (frames come every 1–4 s under load: 3 s made NAVERA flicker
  NO_FIX, e1d0674; the node's own default is the same 5 s — C4), night 5 s, celestial 45 s.
- **Stated accuracy.** An accuracy counts only with a defined bounded covariance type
  (approximated, diagonal known, known) and a horizontal sigma of at least 1 cm. Otherwise
  (type unknown or undefined, all-zero covariance) the position is DEGRADED "uncertainty
  unknown" and is never used as an independent reference.
- **A late GPS fix** (stamped before the newest one received: serial / MAVLink buffering,
  DDS reordering) is dropped, not scored as a jump. A fix stamped in the future does not set
  the order; it is refused by eligibility.
- A higher-priority source must stay usable for `switch_holdoff_s` (2 s) before it takes over.
- `/navera/position`: the winning estimate, published once per new measurement
  (de-duplicated on its stamps **and** content: a source holding its header stamp while its
  position changes does not freeze the output).
- `/navera/nav_status` (5 Hz): the state, the active source and mode, the health of each
  source, and the reason in plain words. The states are:
  - **FIX:** measured, with a stated σ ≤ `fix_max_sigma_m` (25 m) — today only GPS;
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
   accuracy. The estimator compares every GPS fix with the most accurate fresh independent
   source of **stated** accuracy (a MEASURED vision or celestial position — never a
   dead-reckoned one), at the instant that source measured. σ below is that source's stated
   accuracy; "time gap" is the time between the two measurements.
   - **In doubt.** From **2 distinct independent fixes in a row** beyond 3 σ (+ max speed ×
     time gap), GPS is still used but **"in doubt"**: its published accuracy is made no
     better than the gap (which makes it DEGRADED: in practice the gap exceeds 25 m), and
     the reason reads `GPS IN DOUBT: day vision disagrees by N m (possible slow spoofing)`.
     The operator sees it and the autopilot already weighs GPS less before any switch to
     vision. A gap above 500 m is more likely a wrong vision match: then no doubt is applied.
   - **Refused** ("GPS drifting away from …") when either **5 distinct independent fixes in
     a row** disagree beyond 3 σ (+ max speed × time gap) — a slow drift; or it disagrees
     beyond 5 σ + 50 m (+ max speed × time gap) for 3 s (`gps_crosscheck_sigmas`,
     `gps_crosscheck_persist_s`) with at least **2 distinct** independent fixes disagreeing
     (one wrong vision fix never refuses GPS).
3. **Re-acceptance.** A GPS refused by the cross-check, or returning after an outage ("jam,
   then spoof"), is re-accepted **only when 2 distinct independent fixes agree with it
   within 3 σ** (+ max speed × time gap): "GPS confirmed by … (2 fixes) — re-accepted". An
   independent fix beyond 3 σ keeps it refused. Only if no independent source of stated
   accuracy has been heard for 120 s is GPS judged on its own again (kinematic gate).

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
by `/dev/v4l/by-id/…`), **csi** (`nvarguscamerasrc`) or **gst** (any GStreamer pipeline,
`NAVERA_CAMERA_GST_PIPELINE`) — both read through the system's GStreamer
(`camera_pkg/gst_capture.py`) — or **ros** (any `sensor_msgs/Image` topic,
`NAVERA_CAMERA_TOPIC`). Frames are grabbed at the camera's rate and only the one sent is
decoded, always grabbed after the request. The same node, with the `NAVERA_STAR_CAMERA_*`
settings and `camera_type=star`, is the celestial pipeline's live star camera (frames
undistorted, not straightened; `cn_subscriber` takes the IMU attitude at each exposure).
For every frame offered to day/night vision:

1. **Exposure stamp:** grab time − `NAVERA_CAMERA_LATENCY_S` (ROS input: the image stamp −
   latency). Every sensor value below is taken at that instant.
2. **Attitude** at the exposure, interpolated from the `imu_topic` history (box IMU, vehicle
   link or the vehicle's ROS IMU, per `NAVERA_SENSOR_SOURCE`; received BEST_EFFORT, depth 50,
   so BEST_EFFORT and RELIABLE publishers both work — the GPS and rangefinder subscriptions
   too). The orientation is read as ENU with yaw from true north (no declination is applied
   here). No attitude within 0.2 s of the exposure → the frame is marked unusable ("no
   attitude at the frame's exposure …"); a frozen attitude (50 identical samples in a row)
   is not used. **Rotation rate:** the rotation between the attitude 0.2 s before the
   exposure and at it gives `rate_dps` (in the frame meta); with a fixed camera a frame
   taken while rotating faster than `NAVERA_CAMERA_MAX_RATE_DPS` (30°/s) is marked unusable
   (never with a gimbal).
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

### Dead-reckoning (day vision)

When a frame gives no match (sea, uniform ground, frame too tilted), day vision carries the
last measured position along the ground velocity fitted to the measured fixes of the last
20 s (`navera_common/track.py`: GPS while trusted, vision matches at their photo's instant),
turned by the heading change the IMU measured since. It is published PROPAGATED with a
stated accuracy that grows with the time since the last *measured* fix (velocity error × t +
5° heading error × distance + ½ a t², a = `dead_reckon_accel_mps2` = 0.5 m/s²), for at most
`max_dead_reckon_s` (120 s) and `dead_reckon_max_sigma_m` (500 m); never used as an
independent check of GPS.

### What is connected — `navera_common/discovery.py`

`navera-discover` (once per boot, before the other units) probes I²C, the serial ports
(NMEA, MAVLink heartbeats), UDP 14550/14551, the ROS graph and the cameras, and decides
the sources left to `auto`: attitude box IMU > autopilot > ROS; GPS box receiver >
autopilot's 2nd GPS > ROS; camera USB > CSI > ROS; MAVLink output relayed by
`vehicle_link` (UDP 14650) on the autopilot link it owns; `/navera/fix` on a ROS
vehicle's domain. Written settings always win. Rules:

- a GPS receiver must send checksummed NMEA **with satellite data** (GSV/GSA; an
  autopilot's NMEA output has none); several: the one with a fix, wired UART first, a
  warning;
- the autopilot's second GPS only when `GPS_TYPE2` / `GPS2_TYPE` (read from it) says it is
  a real receiver — never type 14 (the MAVLink-fed GPS that NAVERA's own `GPS_INPUT`
  feeds), never when the types cannot be read;
- no GPS found: `NAVERA_GPS_SOURCE=none`, the GPS service idles (no default port opened);
- several autopilots: the wired port first, a warning when they are different systems;
  `NAVERA_MAVLINK_SYSID` = the autopilot's system id;
- `ROS_DOMAIN_ID` / `ROS_LOCALHOST_ONLY` written in navera.env are never changed; a ROS
  vehicle on another domain is reported; `ROS_DOMAIN_ID=auto` joins it (deploy/README.md §6);
- cameras: the star camera is not a candidate, a written `NAVERA_CAMERA_DEVICE` is kept,
  several → a warning;
- ports held by another program, the kernel console and serial-getty ports are never
  probed;
- `NAVERA_BOX_IMU` / `NAVERA_BOX_RTC` record whether the chips answer; `navera-imu` /
  `navera-rtc` idle without them.

## 6. Output to the vehicle — `navera_output`

`vehicle_output` sends the arbiter's decision as NMEA (GGA + RMC), MAVLink `GPS_INPUT` and a
ROS `NavSatFix` on `/navera/fix` (`NAVERA_ROS_FIX_TOPIC`). FIX is sent as a fix with its
accuracy. DEGRADED is withheld from the autopilot unless `NAVERA_FORWARD_DEGRADED=true`
with a stated `NAVERA_DEGRADED_SIGMA_M`, and then goes over MAVLink only — NMEA carries no
accuracy, so it says "no fix" for it unless `NAVERA_NMEA_FORWARD_DEGRADED=true`. ROS gets
DEGRADED positions by default (`NAVERA_ROS_FORWARD_DEGRADED`), with `status.service` 0 and
the stated accuracy in the covariance. Everything else is an explicit "no fix". Each
position is sent once, stamped with its measurement instant, and not at all if measured
more than `NAVERA_MAX_MEASUREMENT_AGE_S` (5 s) ago; a position older than
`position_timeout_s` (5 s) is no longer current. A vision / celestial position is carried
to the present along the ground velocity fitted to the recent positions (20 s), its
accuracy grown by the speed error × its age; with no velocity known it is sent stamped when
measured, its accuracy grown by the maximum speed × its age. Details:
[navera_output/README.md](../navera_output/README.md), autopilot setup:
[ARDUPILOT_INTEGRATION.md](ARDUPILOT_INTEGRATION.md), [PX4_INTEGRATION.md](PX4_INTEGRATION.md).

## 7. Topics

| Topic | Type | From | To |
|---|---|---|---|
| `/navera/sensors/gps_fix` | sensor_msgs/NavSatFix | gps_node / ros_gps_node | live camera, diagnostics |
| `/navera/sensors/gps_vel` | geometry_msgs/TwistStamped (ENU m/s) | gps_node | vehicle_output (velocity with GPS fixes) |
| `/navera/sensors/imu` | sensor_msgs/Imu | imu_node | live camera, night, celestial, estimator (`NAVERA_SENSOR_SOURCE=box`) |
| `/navera/sensors/rtc_time`, `rtc_status` | TimeReference, String (JSON) | rtc_node | cn_subscriber, check_box |
| `/navera/vehicle/imu`, `altitude_agl`, `relative_alt` | Imu, Range, PointStamped | vehicle_link_node | live camera and pipelines (`vehicle`) |
| `/navera/vehicle/gps2` | sensor_msgs/NavSatFix | vehicle_link_node | ros_gps_node (`NAVERA_GPS_SOURCE=vehicle`) |
| `/navera/vehicle/status` | String (JSON) | vehicle_link_node | web bridge (armed lock), vehicle_output (relay check), check_box |
| `/navera/operator/start_position` | navera_msgs/PositionEstimate (latched; source EXTERNAL) | web bridge (`/mission`) | day_subscriber (search area only) |
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
| `GET /operator` | Operator view: the arbiter's decision (FIX / DEGRADED / NO FIX / OFFLINE / LINK LOST) with the source and stated accuracy; a vision position carried to now; a camera warning when 30 % of the last minute's frames were unusable. The vehicle marker is removed whenever there is no valid position |
| `GET /api/operator_position` | That decision as JSON (`valid`, `state`, `source`, `source_name`, `mode`, `age_s`, `reason`, and when known `accuracy_m`, `measured_age_s`, `carried_s`, `measured_lat`/`measured_lon`, `camera_warning`) |
| `GET /` | Mission planner and replay dashboard |
| `GET /mission`, `GET /api/mission/state` | Mission preparation: vehicle settings, route, route map |
| `POST /api/mission/{settings,apply,plan,generate,activate,cancel,start_position,save_mission,delete_mission}` | Mission preparation actions; token required |
| `GET /tiles/{z}/{x}/{y}` | Satellite tiles from the MBTiles map (read-only, bounded) |
| `POST /api/set_mission` | Start/rewind the mission; token required |
| `GET /health` | Liveness of the bridge process |

Control endpoints require the `X-Navera-Token` header equal to `NAVERA_WEB_TOKEN` (none
configured = read-only, 403); a wrong code gets 401, and after 5 wrong codes within 60 s the
address gets 429 for 60 s. No CORS headers are sent; request bodies are limited to 4 KiB of
JSON (512 KiB for an imported mission file); idle connections time out. With `NAVERA_TLS_CERT` / `NAVERA_TLS_KEY` set, the bridge
serves HTTPS only (TLS ≥ 1.2).

**`/mission`** (`simulation_web/mission_prep.py`): sets only `NAVERA_VEHICLE_TYPE`,
`NAVERA_MAX_SPEED_KMH`, `NAVERA_DAY_HFOV_DEG`, `NAVERA_THERMAL_HFOV_DEG`,
`NAVERA_IMU_MOUNT_RPY`, `NAVERA_DECLINATION_DEG` (validated, written to
`/var/lib/navera/settings.env`) and, through "Activate", `DAY_DATASET_DIR`. It plans a route
from an autopilot mission file (`.waypoints`, `.plan`) or a drawn route, generates its
corridor map (`day_pkg/prepare_area.py`) and activates it; it estimates the stretches
without landmarks at planning and measures them at generation. "Apply", "Activate" and
"Generate" are refused while the vehicle is armed (from `/navera/vehicle/status`), while
NAVERA's own track (`/navera/position`) moves faster than 1.5 m/s, or while NAVERA is
navigating without GPS (`nav_status` DEGRADED). "Start without GPS" publishes the operator
start position (§1). The only root rights are the exact `systemctl` commands in
`deploy/sudoers/navera-web`.

## 10. Deployment

Services, installation, sources, pipeline selection and site settings:
[deploy/README.md](../deploy/README.md). Problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
Tests: `navera_tools/run_tests.sh [--integration]`.
