# navera_output — position output to the vehicle's autopilot

`vehicle_output_node` makes NAVERA look like a GPS to the vehicle. It sends the arbiter's
decision (`/navera/position`, `/navera/nav_status`) as:

- **NMEA 0183** (GGA + RMC) on a serial port — any system that accepts a GPS receiver
  (multirotors, fixed-wing, boats, ground robots);
- **MAVLink `GPS_INPUT`** — PX4 and ArduPilot.

## What the vehicle receives

| NAVERA state | NMEA | MAVLink GPS_INPUT |
|---|---|---|
| FIX (GPS) | GGA quality 1, HDOP = σ/2 m, satellites, altitude; RMC status A, mode A, speed and course from the receiver | fix_type 3, horiz/vert accuracy = σ, horizontal velocity from the receiver |
| FIX (vision / celestial with a stated σ ≤ 25 m) | GGA quality 1, no altitude | fix_type 3 with the altitude flagged ignored (`fix_type_without_alt`), no velocity |
| DEGRADED (vision, celestial, dead-reckoned) | **no fix by default**; with `forward_degraded`: quality 6 (estimated), HDOP from `degraded_sigma_m`, RMC mode E | **no fix by default**; with `forward_degraded`: accuracy = `degraded_sigma_m`, 0 satellites |
| NO_FIX, arbiter silent > 2 s, position older than 2 s | GGA quality 0 with empty position, RMC status V | fix_type 1, no position |

Each position is sent **once**, when it arrives. A 1 Hz vision fix repeated 5 times with fresh
timestamps made ArduPilot's filter see "stopped, then jumped" and trigger a glitch failsafe
(found in SITL). "No fix" is sent at `rate_hz`. A position is never repeated after it stops
being current.

**Why DEGRADED is withheld by default:** day vision measured a median error of ~440 m
([docs/VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md)). An autopilot that trusted it as a
GPS could fly far off course. Enable `forward_degraded` only with a `degraded_sigma_m`
you have measured for your vehicle and area — the autopilot will weight the position by it.
The node refuses to start with `forward_degraded` and no sigma.

## Configuration

`config/vehicle_output.yaml`, or on the box `/etc/navera/navera.env`
(`NAVERA_NMEA_PORT`, `NAVERA_NMEA_BAUD`, `NAVERA_MAVLINK_URL`) with `navera-output.service`.

| Parameter | Default | |
|---|---|---|
| `nmea_port` / `nmea_baud` | "" / 9600 | serial device to the autopilot's GPS input; "" = off |
| `mavlink_url` | "" | e.g. `/dev/ttyTHS2,57600` or `udpout:127.0.0.1:14550`; "" = off |
| `mavlink_system_id` / `mavlink_component_id` | 1 / 191 | this box's MAVLink identity (onboard computer) |
| `rate_hz` | 5.0 | output rate |
| `forward_degraded` / `degraded_sigma_m` | false / NaN | see above |
| `position_timeout_s` / `nav_status_timeout_s` | 2.0 / 2.0 | older = "no fix" |
| `gps_vel_timeout_s` | 1.0 | the GPS velocity sent with a GPS position must be younger than this |
| `fix_type_without_alt` | 3 | MAVLink fix_type for a position without altitude (vision). 3 = used by ArduPilot / PX4, which take height from the barometer; 2 = the literal label, which they ignore |

## Autopilot setup — ArduPilot (validated in SITL, Copter 4.5 and Rover)

Established with the mission simulator (`navera_tools/run_sim.sh`), where an ArduPilot SITL
autopilot's **only** position input is NAVERA's output:

| Parameter | Value | Why |
|---|---|---|
| `GPS_TYPE` (`GPS1_TYPE`) | 14 (MAVLink) or 5 (NMEA) | NAVERA is the GPS |
| `SERIALn_PROTOCOL` | 2 (MAVLink 2) or 5 (GPS) | on the port the box is wired to |
| `EK3_SRC1_VELXY` | **0** | position only from NAVERA. Vision fixes carry no velocity, and ArduPilot keeps fusing the *last* GPS velocity it received when none is sent: after GPS loss that stale velocity caused a glitch and an EKF failsafe (LAND) within 40 s. Velocity then comes from the autopilot's own IMU. |
| `EK3_SRC1_VELZ` | **0** | same |
| `EK3_SRC1_POSZ` | 1 (barometer, default) | vision fixes carry no altitude |

Measured in SITL, drone at 120 m, 10–15 m/s, GPS jammed in flight, vision at the *target*
accuracy (15 m σ, simulated): the autopilot kept flying the mission on NAVERA's position with
its own position error at 2–18 m for 2.5 min, no glitch, no failsafe. With vision at today's
measured accuracy (DEGRADED, withheld), the autopilot loses its position and its own failsafe
takes over (Copter: LAND; Rover/boat: HOLD) — the safe outcome.

Also found:
- **The autopilot needs one real GPS fix at power-on.** ArduPilot sets its navigation origin
  only from a GPS that passes its checks (satellites, HDOP); vision fixes report 0 satellites.
  Start the vehicle with GPS, or set the origin explicitly (`SET_GPS_GLOBAL_ORIGIN`).
- With `forward_degraded`, DEGRADED positions are sent with 0 satellites: arming checks that
  require satellites must be adapted by the integrator, knowingly.
- **NMEA:** ArduPilot treats GGA quality 6 (estimated) as a 3D fix.
- **PX4:** not tested.

## Tests

- Unit (`test/test_output.py`): decision rules, NMEA sentences parsed back with checksum
  verification in all four hemispheres, GPS_INPUT encoded/decoded with pymavlink, GPS week.
- Integration (`navera_tools/tests/test_vehicle_output.py`): simulated GPS → estimator →
  this node → a pseudo-terminal (NMEA) and UDP (MAVLink), then GPS loss → "no fix".

- SITL (`navera_tools/tests/sitl_ardupilot.py`, and the mission simulator): ArduCopter
  accepts the MAVLink and NMEA outputs. Not yet tested on a real autopilot.
