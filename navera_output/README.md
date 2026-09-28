# navera_output — position output to the vehicle's autopilot

`vehicle_output_node` makes NAVERA look like a GPS to the vehicle. It sends the arbiter's
decision (`/navera/position`, `/navera/nav_status`) as:

- **NMEA 0183** (GGA + RMC) on a serial port — any system that accepts a GPS receiver
  (multirotors, fixed-wing, boats, ground robots);
- **MAVLink `GPS_INPUT`** — PX4 and ArduPilot.

## What the vehicle receives

| NAVERA state | NMEA | MAVLink GPS_INPUT |
|---|---|---|
| FIX (GPS today) | GGA quality 1, HDOP = σ/2 m, satellites, altitude; RMC status A, mode A | fix_type 3 (2 if the altitude above sea level is unknown), horiz/vert accuracy = σ |
| DEGRADED (vision, celestial, dead-reckoned) | **no fix by default**; with `forward_degraded`: quality 6 (estimated), HDOP from `degraded_sigma_m`, RMC mode E | **no fix by default**; with `forward_degraded`: accuracy = `degraded_sigma_m`, 0 satellites |
| NO_FIX, arbiter silent > 2 s, position older than 2 s | GGA quality 0 with empty position, RMC status V | fix_type 1, no position |

A position is never repeated after it stops being current.

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

## Autopilot side (to verify on the target vehicle)

- **NMEA:** connect the box's serial TX to a GPS port of the autopilot and set that port's
  GPS type to NMEA at the same baud rate. Whether GGA quality 6 is accepted as a fix depends
  on the autopilot and its settings.
- **ArduPilot / PX4 MAVLink:** set the GPS type to MAVLink (ArduPilot: `GPS1_TYPE = 14`,
  formerly `GPS_TYPE`) on the telemetry port the box is connected to.
- The satellite count for DEGRADED positions is 0: arming checks that require satellites must
  be adapted by the integrator, knowingly.

## Tests

- Unit (`test/test_output.py`): decision rules, NMEA sentences parsed back with checksum
  verification in all four hemispheres, GPS_INPUT encoded/decoded with pymavlink, GPS week.
- Integration (`navera_tools/tests/test_vehicle_output.py`): simulated GPS → estimator →
  this node → a pseudo-terminal (NMEA) and UDP (MAVLink), then GPS loss → "no fix".

Not yet tested against a real autopilot or an autopilot simulator (SITL).
