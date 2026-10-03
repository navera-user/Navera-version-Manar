# navera_output — output to the vehicle, and the vehicle link

Two nodes:

- **`vehicle_output_node`** (`navera-output.service`) makes NAVERA look like a GPS to the
  vehicle. It sends the arbiter's decision (`/navera/position`, `/navera/nav_status`) as
  **NMEA 0183** (GGA + RMC) on a serial port, **MAVLink `GPS_INPUT`** (ArduPilot, PX4), and
  **ROS `sensor_msgs/NavSatFix`** on `/navera/fix`.
- **`vehicle_link_node`** (`navera-vehicle-link.service`) reads the vehicle's own sensors
  from its autopilot over MAVLink (any MAVLink autopilot): attitude, downward rangefinder,
  barometric height above home, second GPS, armed state.

Wiring and autopilot parameters: [docs/ARDUPILOT_INTEGRATION.md](../docs/ARDUPILOT_INTEGRATION.md).

## What the vehicle receives

| NAVERA state | NMEA | MAVLink GPS_INPUT | ROS `/navera/fix` |
|---|---|---|---|
| FIX (GPS; or a source with a stated σ ≤ 25 m) | GGA quality 1, HDOP = σ/2 m, satellites, altitude; RMC status A, mode A, speed and course from the receiver | fix_type 3, horiz/vert accuracy = σ, horizontal velocity from the receiver | status FIX, covariance from σ |
| FIX without altitude (vision / celestial) | GGA quality 1, no altitude | fix_type 3 with the altitude flagged ignored (`fix_type_without_alt`), no velocity | |
| DEGRADED (vision, celestial, dead-reckoned) | **no fix by default**; with `forward_degraded`: quality 6 (estimated), HDOP from `degraded_sigma_m`, RMC mode E | **no fix by default**; with `forward_degraded`: accuracy = `degraded_sigma_m`, 0 satellites | no fix by default; with `forward_degraded`: status FIX too — the accuracy is only in the covariance |
| NO_FIX; arbiter silent > 2 s; no new position for 5 s; measured more than `max_measurement_age_s` ago; coarser than `max_forward_sigma_m` | GGA quality 0 with empty position, RMC status V | fix_type 1, no position | STATUS_NO_FIX, NaN position |

Today **every vision and celestial position is DEGRADED** (the estimator gives FIX only with
a stated σ ≤ `fix_max_sigma_m` = 25 m; day vision states 30 m until measured with NAVERA's
camera). So with the defaults, **nothing but GPS reaches the autopilot**: when GPS is lost,
it receives "no fix" and its own failsafe acts.

Each position is sent **once**, when it arrives, **stamped with the instant it was measured**
(camera exposure for vision), not the sending instant. A 1 Hz vision fix repeated 5 times
with fresh timestamps made ArduPilot's filter see "stopped, then jumped" and trigger a
glitch failsafe (found in SITL). A position measured more than `max_measurement_age_s`
(2 s) ago is not sent at all: a 3 s old vision fix sent as current is 45 m wrong at 15 m/s.
"No fix" is sent at `rate_hz`. A position is never repeated after it stops being current.

**Why DEGRADED is withheld by default.** Day vision's accuracy is not established with
NAVERA's camera ([docs/VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md)): local feature
matching put 32/33 benchmark frames within 9 m (median 4 m), but those are aerial frames from
another source, not NAVERA's camera; the former DINOv2 retrieval, still the fallback, had a
442 m median; and day vision is unreliable over uniform terrain (desert, sea). An autopilot
that trusted a position as better than it is could fly far off course. Enable
`forward_degraded` only with a `degraded_sigma_m` you have **measured** for your camera,
vehicle and area — the autopilot weights the position by it. The node refuses to start
with `forward_degraded` and no sigma.

Measured in the simulator (2026-10-01) with the former retrieval method: with ±300 m
forwarded over uniform desert (median error 351 m, p90 853 m, jumps of 360–570 m rejected by
the motion gate), ArduCopter's EKF reported "EKF variance" and switched to LAND after 45 s —
an autopilot told a position is better than it is rejects it and fails safe. Over textured
ground (Sousse, median 111 m) the same setting flew on.

## Configuration

On the box: `/etc/navera/navera.env`, read by `navera-output.service` and
`navera-vehicle-link.service`. Elsewhere: `config/vehicle_output.yaml` and launch arguments.

| Environment (navera.env) | Parameter | Default | |
|---|---|---|---|
| `NAVERA_NMEA_PORT` / `NAVERA_NMEA_BAUD` | `nmea_port` / `nmea_baud` | "" / 9600 | serial device to the autopilot's GPS input; "" = off |
| `NAVERA_MAVLINK_URL` | `mavlink_url` | "" | MAVLink address (below); "" = off |
| `NAVERA_ROS_FIX_TOPIC` | `ros_fix_topic` | `/navera/fix` | NavSatFix output; the node default is always on |
| `NAVERA_FORWARD_DEGRADED` | `forward_degraded` | false | send DEGRADED positions as "estimated" |
| `NAVERA_DEGRADED_SIGMA_M` | `degraded_sigma_m` | NaN | accuracy stated for them (m, 1 σ); required with forwarding. When the source states a worse one, the worse is sent |
| `NAVERA_MAX_MEASUREMENT_AGE_S` | `max_measurement_age_s` | 5.0 | older measurements are not sent; younger vision positions are carried to the present, accuracy grown by their age |
| — | `max_forward_sigma_m` | 1000 | a forwarded position coarser than this is withheld (a celestial fix moved a SITL autopilot by 125 km) |
| — | `mavlink_system_id` / `mavlink_component_id` | 1 / 191 | this box's MAVLink identity (onboard computer) |
| — | `rate_hz` | 5.0 | "no fix" rate |
| — | `position_timeout_s` / `nav_status_timeout_s` | 2.0 / 2.0 | older = "no fix" |
| — | `gps_vel_timeout_s` | 1.0 | the GPS velocity sent with a GPS position must be younger than this |
| — | `fix_type_without_alt` | 3 | MAVLink fix_type for a position without altitude (vision). 3 = used by ArduPilot / PX4, which take height from the barometer; 2 = the literal label, which they ignore |

The environment overrides are applied by `launch/vehicle_output.launch.py`
(`_env_overrides`). If an enabled output cannot be opened or written, the node exits so the
service restarts it.

### MAVLink addresses (`navera_output/mavlink_url.py`)

One format for every NAVERA MAVLink setting (`NAVERA_MAVLINK_URL` for this output,
`NAVERA_VEHICLE_MAVLINK_URL` for the vehicle link):

| Form | Example |
|---|---|
| serial (documented form) | `serial:/dev/ttyTHS2:921600` |
| serial (pymavlink's form, also accepted) | `/dev/ttyTHS2,921600` |
| network | `udpin:0.0.0.0:14551`, `udpout:127.0.0.1:14550`, `tcp:127.0.0.1:5762`, `tcpin:0.0.0.0:5770` |

A malformed address stops the node at start with "expected serial:/dev/<port>:<baud>, …".
One autopilot port per NAVERA connection (output, vehicle link), or `mavlink-router` to share
one port between them.

## vehicle_link_node

Started by `navera-vehicle-link.service` with `mavlink_url` = `NAVERA_VEHICLE_MAVLINK_URL`
(the service exits with "NAVERA_VEHICLE_MAVLINK_URL is not set" without it). Publishes,
stamped on receipt:

| Topic | Type | Content |
|---|---|---|
| `/navera/vehicle/imu` | sensor_msgs/Imu | attitude (ENU, body FLU) + rates — the attitude source for `NAVERA_SENSOR_SOURCE=vehicle` |
| `/navera/vehicle/altitude_agl` | sensor_msgs/Range | downward rangefinder (`DISTANCE_SENSOR`), tilt-corrected |
| `/navera/vehicle/relative_alt` | geometry_msgs/PointStamped | z = height above home (barometer) |
| `/navera/vehicle/gps2` | sensor_msgs/NavSatFix | the autopilot's **second** GPS (`GPS2_RAW`, 3D fix or better) — the GPS for `NAVERA_GPS_SOURCE=vehicle` |
| `/navera/vehicle/status` | std_msgs/String (JSON) | link, autopilot, armed, message rates — the armed state locks the `/mission` page |

It waits for a heartbeat **from an autopilot** (heartbeats from a ground station, another
onboard computer, a gimbal or a camera on a shared link are ignored), requests its message
rates (`MAV_CMD_SET_MESSAGE_INTERVAL`: attitude at `attitude_hz`, default 50 Hz; position
10 Hz; rangefinder 10 Hz; GPS2 5 Hz; system time 1 Hz; plus the legacy data-stream request),
and sends a companion heartbeat every second. Without a heartbeat for 10 s it logs
"no heartbeat from an autopilot on <url> — retrying"; an autopilot silent for 5 s makes it
reconnect. The autopilot's own fused position is deliberately **not** read: when NAVERA
feeds the autopilot, that would be NAVERA's output coming back.

Parameters: `mavlink_url`, `attitude_hz` (50), `source_system` (1), `source_component` (191).

## Autopilot setup

See [docs/ARDUPILOT_INTEGRATION.md](../docs/ARDUPILOT_INTEGRATION.md) for wiring, the
parameter table and what is verified in ArduPilot SITL only. Key points found in SITL:

- `EK3_SRC1_VELXY = 0` and `EK3_SRC1_VELZ = 0`: vision fixes carry no velocity, and
  ArduPilot kept fusing the *last* GPS velocity it received; after GPS loss that stale
  velocity caused a glitch and an EKF failsafe (LAND) within 40 s.
- **The autopilot needs one real GPS fix at power-on**: ArduPilot sets its navigation origin
  only from a GPS that passes its checks (satellites, HDOP); vision fixes report 0
  satellites. Start the vehicle with GPS, or set the origin explicitly (`SET_GPS_GLOBAL_ORIGIN`).
- With `forward_degraded`, DEGRADED positions are sent with 0 satellites: arming checks that
  require satellites must be adapted by the integrator, knowingly.
- **NMEA:** ArduPilot treats GGA quality 6 (estimated) as a 3D fix.
- **PX4:** not tested.

Measured in SITL, drone at 120 m, 10–15 m/s, GPS jammed in flight, vision at the *target*
accuracy (15 m σ, simulated): the autopilot kept flying the mission on NAVERA's position with
its own position error at 2–18 m for 2.5 min, no glitch, no failsafe. With vision withheld
(DEGRADED, the default), the autopilot loses its position and its own failsafe takes over
(Copter: LAND; Rover/boat: HOLD) — the safe outcome.

## Tests

- Unit (`test/test_output.py`, `test/test_mavlink_in.py`): decision rules, NMEA sentences
  parsed back with checksum verification in all four hemispheres, GPS_INPUT encoded/decoded
  with pymavlink, GPS week, MAVLink input conversions.
- Integration (`navera_tools/tests/test_vehicle_output.py`): simulated GPS → estimator →
  this node → a pseudo-terminal (NMEA) and UDP (MAVLink), then GPS loss → "no fix".
- SITL (`navera_tools/tests/sitl_ardupilot.py`, `navera_tools/tests/sitl_vehicle_link.py`,
  and the mission simulator): ArduCopter accepts the MAVLink and NMEA outputs; vehicle_link
  reads attitude, height and rangefinder. Not yet tested on a real autopilot.
