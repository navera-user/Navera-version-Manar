# navera_output — output to the vehicle, and the vehicle link

Two nodes:

- **`vehicle_output_node`** (`navera-output.service`) makes NAVERA look like a GPS to the
  vehicle. It sends the arbiter's decision (`/navera/position`, `/navera/nav_status`) as
  **NMEA 0183** (GGA + RMC) on a serial port, **MAVLink `GPS_INPUT`** (ArduPilot; PX4 does
  not handle this message — [docs/PX4_INTEGRATION.md](../docs/PX4_INTEGRATION.md)), and
  **ROS `sensor_msgs/NavSatFix`** on `/navera/fix`.
- **`vehicle_link_node`** (`navera-vehicle-link.service`) reads the vehicle's own sensors
  from its autopilot over MAVLink (any MAVLink autopilot): attitude, downward rangefinder,
  barometric height above home, second GPS, armed state — and relays the output's MAVLink
  to the autopilot when they share one link.

Wiring and autopilot parameters: [docs/ARDUPILOT_INTEGRATION.md](../docs/ARDUPILOT_INTEGRATION.md).

## Nodes and topics

| Executable | Node name | Unit |
|---|---|---|
| `vehicle_output_node.py` | `vehicle_output` | `navera-output.service` (`navera_boot_output.sh`: `ros2 launch navera_output vehicle_output.launch.py`) |
| `vehicle_link_node.py` | `vehicle_link` | `navera-vehicle-link.service` (`navera_boot_vehicle_link.sh`: `ros2 run navera_output vehicle_link_node.py` with `mavlink_url`, `source_system`) |

`vehicle_output_node` (all QoS depth 10, reliable):

| | Topic | Type | |
|---|---|---|---|
| in | `/navera/position` | `navera_msgs/PositionEstimate` | the arbiter's elected position |
| in | `/navera/nav_status` | `navera_msgs/NavStatus` | FIX / DEGRADED / NO_FIX |
| in | `/navera/sensors/gps_vel` | `geometry_msgs/TwistStamped` | receiver velocity sent with a GPS position |
| in | `/navera/vehicle/status` | `std_msgs/String` (JSON) | only when `mavlink_url` is the local relay (`udpout:127.0.0.1:…`) |
| out | `ros_fix_topic` (default `/navera/fix`; empty = off) | `sensor_msgs/NavSatFix` | |
| out | serial `nmea_port` / MAVLink `mavlink_url` | NMEA GGA + RMC / `GPS_INPUT` (ArduPilot) or `HIL_GPS` (PX4) | not ROS topics |

`vehicle_link_node` publishes the `/navera/vehicle/*` topics listed in
[vehicle_link_node](#vehicle_link_node) (`/navera/vehicle/imu` depth 50, the others depth 10)
and subscribes to nothing; its input is the autopilot's MAVLink.

## How to run

```bash
ros2 launch navera_output vehicle_output.launch.py nmea_port:=/dev/ttyUSB1   # + navera.env overrides
ros2 run navera_output vehicle_link_node.py --ros-args -p mavlink_url:=serial:/dev/ttyTHS2:921600
```

`vehicle_output.launch.py` loads `config/vehicle_output.yaml`, the `nmea_port` / `nmea_baud`
launch arguments (defaults from `NAVERA_NMEA_PORT` / `NAVERA_NMEA_BAUD`), the environment
overrides below and the vehicle's maximum speed (`NAVERA_MAX_SPEED_KMH`).

## What the vehicle receives

| NAVERA state | NMEA | MAVLink GPS_INPUT | ROS `/navera/fix` |
|---|---|---|---|
| FIX (GPS; or a source with a stated σ ≤ 25 m) | GGA quality 1, HDOP = σ/2 m, satellites, altitude; RMC status A, mode A, speed and course from the receiver | fix_type 3, horiz/vert accuracy = σ, horizontal velocity from the receiver with `speed_accuracy` = `gnss_speed_sigma_mps` (none current: stated unknown, below) | status FIX, `service` GPS, covariance from σ |
| FIX without altitude (vision / celestial) | GGA quality 1, no altitude | fix_type 3 with the altitude flagged ignored (`fix_type_without_alt`), velocity as for DEGRADED | status FIX (no vision source reaches FIX today) |
| DEGRADED (vision, celestial, dead-reckoned; a GPS "in doubt") | **no fix** — even with `forward_degraded`, unless `nmea_forward_degraded`: then quality 6 (estimated), HDOP from the accuracy, RMC mode E | **no fix by default**; with `forward_degraded`: accuracy = the worse of `degraded_sigma_m` and the source's own, plus the lag; 0 satellites; NAVERA's own velocity with its accuracy, or "unknown" (below); held back after a gap until that velocity is known | **sent by default** (`ros_forward_degraded`): status FIX, `service` 0, the stated accuracy plus the lag in the covariance — only when an accuracy is stated (else no fix) |
| NO_FIX; arbiter silent > 2 s; no new position for 5 s; measured more than `max_measurement_age_s` ago; coarser than `max_forward_sigma_m` | GGA quality 0 with empty position, RMC status V | fix_type 1, no position | STATUS_NO_FIX, NaN position |

Today **every vision and celestial position is DEGRADED** (the estimator gives FIX only with
a stated σ ≤ `fix_max_sigma_m` = 25 m; day vision states 30 m until measured with NAVERA's
camera). So with the defaults, **nothing but GPS reaches the autopilot**: when GPS is lost,
it receives "no fix" and its own failsafe acts. A ROS consumer of `/navera/fix` does get the
vision positions, marked `service` 0, with their accuracy.

Each position is sent **once**, when it arrives. A 1 Hz vision fix repeated 5 times with
fresh timestamps made ArduPilot's filter see "stopped, then jumped" and trigger a glitch
failsafe (found in SITL). A position measured more than `max_measurement_age_s` (5 s) ago is
not sent at all. "No fix" is sent at `rate_hz`. A position is never repeated after it stops
being current.

**Altitude of a vision position: the autopilot reads 0 m.** A vision or celestial position has no
altitude: GPS_INPUT flags it ignored (fix_type 3, `IGNORE_ALT`). ArduPilot's MAVLink GPS driver
(AP_GPS_MAV) then stores **0 m AMSL** as the GPS altitude (SITL 2026-10-16: `GPS_RAW_INT` alt 0.0,
fix 3, from the GPS cut on). With the defaults this altitude is not used — EKF3 takes its height
from the barometer and fuses GPS height only with `EK3_SRC1_POSZ = 3` (GPS) or corrects its origin
from it only with `EK3_OGN_HGT_MASK` set. **Never set either with NAVERA**: the EKF would be pulled
towards 0 m and the vehicle would climb to hold its height. (Problems doc F7, a 140 → 569 m climb in
SITL 2026-10-15 while a runaway dead-reckoned position was forwarded, is not explained by this with
the default parameters; it disappeared once that position was withdrawn honestly — 142–164 m in the
2026-10-15/16 re-runs — and the autopilot's EKF height was not logged in the climbing run.)
*Verified in SITL with EKF height logged (2026-10-20, `navera_tools/tests/sitl_f7_height.py`,
results in docs/ARDUPILOT_INTEGRATION.md §3): with the recommended parameters the EKF height
stayed on the barometer within 0.1 m whatever altitude the messages carried — none, a garbage
ignored value, 200 m off, ±300 m jumps, a 90 m slow drift — while the horizontal position took
the vision positions; with `EK3_SRC1_POSZ = 3` the EKF height went to −277 m within 20 s and the
vehicle climbed to 150 m, then 825 m.* Only a satellite position ever carries an altitude in
GPS_INPUT: a non-GNSS one is sent with `IGNORE_ALT` even if its producer attached a height.

**A velocity with every position (F28).** ArduPilot's MAVLink GPS driver keeps the last
velocity and speed accuracy it received when a `GPS_INPUT` flags them ignored, and EKF3 resets
its velocity to that value when a position comes back after a timeout — also with
`EK3_SRC1_VELXY = 0`. With vision positions sent without a velocity, a plane's EKF was reset
to the GPS velocity of 60 s earlier, 180° wrong (SITL 2026-10-21). So every position goes out
with a horizontal velocity and its `speed_accuracy`: the receiver's for GPS; for vision /
celestial the velocity of NAVERA's recent fixes when it is trustworthy
(`TrackVelocity.autopilot_velocity`: ≥ 5 fixes over ≥ 4 s in a 10 s window, none across a 5 s
gap, on a straight line within their stated accuracy; σ = the fit's slope error + 0.5 m/s² ×
the fit's lag); otherwise **unknown: 0 m/s with `max_speed_mps` as its accuracy** — never
flagged ignored. A bridged position carries the velocity sent with the held one, its σ growing
by 0.5 m/s² × t. Never a vertical velocity (NAVERA measures none; ArduPilot never forgets one
it was given).

**After a gap, vision waits for its velocity.** When the autopilot was given no position for
`reacquire_after_s` (5 s: past the bridge, EKF3's position aiding has timed out), the next
vision positions are held back ("no fix") until the velocity of the new fixes is known to
`reacquire_vel_sigma_mps` (8 m/s: about 7 good fixes at 1 Hz). EKF3 resets its position AND
its velocity onto the first fix after a timeout; given "0, unknown", a plane's EKF velocity
stayed near 0 for 70 s (airspeed fusion needs a predicted airspeed > 1 m/s) and the plane flew
3.5 km past its waypoint (SITL 2026-10-21). Log line: `output → no fix (reacquiring after a
gap: …)`. A GPS fix and a bridged position never wait.

**Gaps are bridged, but not for long.** An autopilot lands on a silence (ArduPilot Copter SITL:
EKF failsafe → LAND about 8 s after the last position, even though the vehicle has hardly moved
from where it was last seen). With `forward_degraded`, when no new vision position has been sent
for `bridge_after_s` (2.5 s), the last one is carried along its ground velocity and sent again
about once a second (`bridge_period_s`), its accuracy growing with the gap: velocity error ×
t + 5° heading error × distance + ½ × `bridge_accel_mps2` × t² (without a velocity: the position
stays and the accuracy grows by `max_speed_mps` × t). After `bridge_max_s` (10 s), or when the
grown accuracy exceeds `max_forward_sigma_m`, it is "no fix" again and the autopilot's own
failsafe acts. Only a forwarded estimate is bridged — never a GPS fix, never while the arbiter is
silent — and the bridge never claims better than it knows. `bridge_max_s = 0` disables it.
Log lines: `no new position for 2.6 s: bridging along the last one`, `bridge ended: …`.

**Carried to the present.** A vision position describes where its photo was taken, 1–2.5 s
before it reaches the output; sent as it was, a plane at 40 m/s was 83 m off with a stated
±30 m (simulator). The node learns the ground velocity of the recent positions (any source,
weighted line fit over 20 s, `navera_common/track.py`) and carries a non-GPS position from
its measurement instant to now, adding the speed error × its age to its accuracy; it is
then stamped now. With no velocity known, it is sent **stamped with its measurement
instant**, its accuracy grown by `max_speed_mps` (from `NAVERA_MAX_SPEED_KMH`, default
30 m/s) × its age. GPS positions are sent stamped with their measurement instant and not
carried (small latency; the autopilot's `GPS_DELAY_MS`). Unit tests: a 1.5 s old photo at
40 m/s is moved 60 m and stated ±31.5 m; with no velocity, ±120 m, stamped as measured.

**Why DEGRADED is withheld by default.** Day vision's accuracy is not established with
NAVERA's camera ([docs/VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md)): local feature
matching put 32/33 benchmark frames within 9 m (median 4 m), but those are aerial frames from
another source, not NAVERA's camera; the former DINOv2 retrieval, still the fallback, had a
442 m median; and day vision is unreliable over uniform terrain (desert, sea). An autopilot
that trusted a position as better than it is could fly far off course. Enable
`forward_degraded` only with a `degraded_sigma_m` you have **measured** for your camera,
vehicle and area — the autopilot weights the position by it. The node refuses to start
with `forward_degraded` and no sigma, or a sigma above `max_forward_sigma_m` (nothing would
ever be sent). **ArduPilot's EKF3 caps a stated accuracy at 100 m**
(R = constrain(accuracy, `EK3_POSNE_M_NSE`, 100 m)²): a sigma above 100 m is trusted more
than stated (`check_box.py` WARNs).

**Why not over NMEA.** NMEA (GGA / RMC) carries no accuracy an autopilot uses: ArduPilot
fuses an NMEA GPS with its own ~0.5 m noise, so a 30 m vision position would be trusted as
a 0.5 m GPS. With `forward_degraded`, degraded positions go over MAVLink and ROS only; NMEA
says "no fix" for them unless `nmea_forward_degraded` is set (a warning is logged at start).

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
| `NAVERA_MAVLINK_URL` | `mavlink_url` | "" | MAVLink address (below); "" or `off` (also `none`, `false`, `0`) = off. navera-discover fills an empty one with the relay `udpout:127.0.0.1:14650` when it finds an autopilot |
| `NAVERA_MAVLINK_SYSID` | `mavlink_system_id` | 1 | the autopilot's own system id (written by navera-discover); PX4 reads `HIL_GPS` only from it |
| `NAVERA_MAVLINK_MESSAGE` | `mavlink_message` | auto | `gps_input` (ArduPilot) / `hil_gps` (PX4) / `auto`: `HIL_GPS` once the autopilot's heartbeat says PX4 (heard on the node's own link or in `/navera/vehicle/status`), else `GPS_INPUT`. navera-discover writes `hil_gps` for PX4 |
| — | `mavlink_component_id` | 191 | this box's MAVLink component (onboard computer) |
| `NAVERA_ROS_FIX_TOPIC` | `ros_fix_topic` | `/navera/fix` | NavSatFix output; set but empty = off |
| `NAVERA_ROS_FIX_FRAME_ID` | `ros_fix_frame_id` | `navera` | `header.frame_id` of the NavSatFix: a frame of the vehicle's TF tree for `navsat_transform` |
| `NAVERA_ROS_FORWARD_DEGRADED` | `ros_forward_degraded` | true | ROS gets DEGRADED positions (with their stated accuracy), independently of `forward_degraded` |
| `NAVERA_FORWARD_DEGRADED` | `forward_degraded` | false | send DEGRADED positions to the autopilot as "estimated" (MAVLink) |
| `NAVERA_NMEA_FORWARD_DEGRADED` | `nmea_forward_degraded` | false | also over NMEA (not recommended: no accuracy field) |
| `NAVERA_DEGRADED_SIGMA_M` | `degraded_sigma_m` | NaN | accuracy stated for them (m, 1 σ); required with forwarding, at most `max_forward_sigma_m`. When the source states a worse one, the worse is sent |
| `NAVERA_MAX_MEASUREMENT_AGE_S` | `max_measurement_age_s` | 5.0 | older measurements are not sent; younger vision positions are carried to the present |
| `NAVERA_MAX_SPEED_KMH` | `max_speed_mps` | 30 m/s | the lag allowance when no ground velocity is known |
| `NAVERA_BRIDGE_MAX_S` (`bridge_max_s` only) | `bridge_max_s` / `bridge_after_s` / `bridge_period_s` | 10 / 2.5 / 1.0 | a gap in the forwarded vision positions is bridged this long at most (0 = never), starting after 2.5 s without one, one position per second (see "Gaps are bridged") |
| — | `gnss_speed_sigma_mps` | 0.5 | `speed_accuracy` stated for the GPS receiver's velocity (RMC has none; ArduPilot floors it at `EK3_VELNE_M_NSE`) |
| — | `reacquire_after_s` / `reacquire_vel_sigma_mps` | 5.0 / 8.0 | after no position was sent for this long, vision positions wait until the new fixes' velocity is known to this σ (0 s = never wait; see "After a gap") |
| — | `bridge_accel_mps2` / `bridge_heading_sigma_deg` | 0.5 / 5 | unseen acceleration and heading error in the accuracy growth of a bridged position |
| — | `drift_alarm_sigma_m` | 100 | a forwarded position coarser than this logs `DRIFT ALARM: the vehicle is given a position of ±… m` every 5 s (the vehicle may be that far off: dead-reckoned or bridged) |
| — | `max_forward_sigma_m` | 1000 | a forwarded position coarser than this is withheld (a celestial fix moved a SITL autopilot by 125 km) |
| — | `rate_hz` | 5.0 | "no fix" rate |
| — | `position_timeout_s` / `nav_status_timeout_s` | 5.0 / 2.0 | older = "no fix" |
| — | `gps_vel_timeout_s` | 1.0 | the GPS velocity sent with a GPS position must be younger than this |
| — | `fix_type_without_alt` | 3 | MAVLink fix_type for a position without altitude (vision). 3 = used by ArduPilot / PX4, which take height from the barometer; 2 = the literal label, which they ignore |

The environment overrides are applied by `launch/vehicle_output.launch.py`
(`_env_overrides`). The three switches accept only true / false (`1`/`0`, `yes`/`no`,
`on`/`off`): any other value (`enabled`, …) stops the launch with the reason, never a
silent false. If an enabled output cannot be opened or written, the node exits so the
service restarts it.

**Relay.** When `mavlink_url` is a local `udpout:127.0.0.1:…` address (navera-vehicle-link's
relay), the node follows `/navera/vehicle/status` and, while no vehicle link is connected to
an autopilot, logs every 30 s: "MAVLink output goes to navera-vehicle-link's relay, but no
vehicle link is connected to an autopilot: the autopilot receives NOTHING from NAVERA".

### MAVLink addresses (`navera_output/mavlink_url.py`)

One format for every NAVERA MAVLink setting (`NAVERA_MAVLINK_URL` for this output,
`NAVERA_VEHICLE_MAVLINK_URL` for the vehicle link):

| Form | Example |
|---|---|
| serial (documented form) | `serial:/dev/ttyTHS2:921600` |
| serial (pymavlink's form, also accepted) | `/dev/ttyTHS2,921600` |
| network | `udpin:0.0.0.0:14551`, `udpout:127.0.0.1:14550`, `tcp:127.0.0.1:5762`, `tcpin:0.0.0.0:5770` |

A malformed address stops the node at start with "expected serial:/dev/<port>:<baud>, …".
One program per serial port: with one autopilot port, the vehicle link owns it and relays
this output (`udpout:127.0.0.1:14650`); with two TELEM ports each connection has its own; or
`mavlink-router` shares one port.

## vehicle_link_node

Started by `navera-vehicle-link.service` with `mavlink_url` = `NAVERA_VEHICLE_MAVLINK_URL`
and `source_system` = `NAVERA_MAVLINK_SYSID` (default 1). Without a URL (none written, no
autopilot found by navera-discover) the service stays idle ("no autopilot found or
configured (NAVERA_VEHICLE_MAVLINK_URL): vehicle link idle"). Publishes, stamped on receipt:

| Topic | Type | Content |
|---|---|---|
| `/navera/vehicle/imu` | sensor_msgs/Imu | attitude (ENU, body FLU) + rates — the attitude source for `NAVERA_SENSOR_SOURCE=vehicle` |
| `/navera/vehicle/altitude_agl` | sensor_msgs/Range | downward rangefinder (`DISTANCE_SENSOR`), tilt-corrected |
| `/navera/vehicle/relative_alt` | geometry_msgs/PointStamped | z = height above home (barometer) |
| `/navera/vehicle/gps2` | sensor_msgs/NavSatFix | the autopilot's **second** GPS (`GPS2_RAW`, 3D fix or better) — the GPS for `NAVERA_GPS_SOURCE=vehicle`. Altitude above the ellipsoid (`alt_ellipsoid`) when sent, else above mean sea level with a warning ("set NAVERA_GROUND_ALTITUDE_M as MSL too"); covariance from the receiver's `h_acc` / `v_acc` (none without `h_acc`) |
| `/navera/vehicle/gps1` (+ `gps1_satellites`) | sensor_msgs/NavSatFix | only with `read_gps1` (`NAVERA_GPS_SOURCE=vehicle_gps1`): the autopilot's **first** GPS (`GPS_RAW_INT`, always instance 1 in ArduPilot), published only while the autopilot's `GPS_TYPE` / `GPS1_TYPE` — re-read at every connection and every 30 s — is known and not 0, 14 (NAVERA's `GPS_INPUT`) or 5 while NAVERA's NMEA output is on (`navera_nmea_output`); `/navera/vehicle/status` then says `gps1_read` and why |
| `/navera/vehicle/status` | std_msgs/String (JSON) | link, autopilot, armed, message rates, relayed packets — the armed state locks the `/mission` page; the output's relay check reads `link` |

It waits for a heartbeat **from an autopilot** (heartbeats from a ground station, another
onboard computer, a gimbal or a camera on a shared link are ignored), requests its message
rates (`MAV_CMD_SET_MESSAGE_INTERVAL`: attitude at `attitude_hz`, default 50 Hz; position
10 Hz; rangefinder 10 Hz; GPS2 5 Hz; system time 1 Hz; plus the legacy data-stream request),
and sends a companion heartbeat every second. Without a heartbeat for 10 s it logs
"no heartbeat from an autopilot on <url> — retrying"; an autopilot silent for 5 s makes it
reconnect. The autopilot's own fused position is deliberately **not** read: when NAVERA
feeds the autopilot, that would be NAVERA's output coming back.

It also listens on local UDP `relay_port` (127.0.0.1:14650) and passes the MAVLink packets
it receives (vehicle_output's `GPS_INPUT`) to the autopilot over its own link.

Parameters: `mavlink_url`, `attitude_hz` (50), `source_system` (1), `source_component`
(192), `relay_port` (14650; 0 = off), `read_gps1` (false), `navera_nmea_output` (false).

## Autopilot setup

See [docs/ARDUPILOT_INTEGRATION.md](../docs/ARDUPILOT_INTEGRATION.md) for wiring, the
parameter table and what is verified in ArduPilot SITL only. Key points found in SITL:

- `EK3_SRC1_VELXY = 0` and `EK3_SRC1_VELZ = 0`: NAVERA's vision velocity is a fit to its own
  positions (correlated with them, late in a turn) — not to be fused as a measurement; and
  before F28 the vision fixes carried none, so ArduPilot fused the *last* GPS velocity it
  received (a glitch and an EKF failsafe, LAND, within 40 s). These settings also stop GPS
  velocity fusion while GPS is healthy (cost: docs/ARDUPILOT_INTEGRATION.md §3). EKF3 still
  uses the message velocity to RESET its own after a timeout: hence the velocity NAVERA sends.
- **The autopilot needs one real GPS fix at power-on**: ArduPilot sets its navigation origin
  only from a GPS that passes its checks (satellites, HDOP); vision fixes report 0
  satellites. Start the vehicle with GPS, or set the origin explicitly (`SET_GPS_GLOBAL_ORIGIN`).
- With `forward_degraded`, DEGRADED positions are sent with 0 satellites: arming checks that
  require satellites must be adapted by the integrator, knowingly.
- **NMEA:** no accuracy field: GPS pass-through only (above).
- **PX4:** it has no `GPS_INPUT` handler; the node sends `HIL_GPS` instead (`mavlink_message`
  auto / hil_gps, `MAV_USEHILGPS = 1` on PX4), verified in PX4 v1.15.4 SITL only
  (docs/PX4_INTEGRATION.md, `navera_tools/tests/sitl_px4.py`).

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
