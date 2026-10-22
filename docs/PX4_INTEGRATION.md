# NAVERA — PX4 integration

What can and cannot be done today between NAVERA and a PX4 autopilot. Read
[deploy/README.md](../deploy/README.md) first; the ArduPilot equivalent is
[ARDUPILOT_INTEGRATION.md](ARDUPILOT_INTEGRATION.md).

> **Status: not tested with NAVERA.** No PX4 SITL run and no PX4 vehicle has been connected
> to NAVERA ([VALIDATION_STATUS.md](VALIDATION_STATUS.md), limitation 6). Everything below
> comes from reading the PX4 source code and documentation (PX4 v1.16.0, the current stable
> release, unless stated; checked 2026-10-03, sources at the end). Each item is marked:
>
> - **PX4 source** — read in the PX4 source or documentation, not exercised with NAVERA;
> - **Not verified** — a recommendation to be confirmed on a PX4 SITL or vehicle.

## 1. Summary

| NAVERA function | With PX4 |
|---|---|
| MAVLink output (`GPS_INPUT`, `NAVERA_MAVLINK_URL`) | **Does not work: PX4 does not handle `GPS_INPUT`** (the message is ignored). navera-discover leaves it off for a PX4 autopilot (and says so); a written `NAVERA_MAVLINK_URL` should be `off` |
| NMEA output (`NAVERA_NMEA_PORT`) | Possible for **GPS pass-through** (PX4's NMEA driver). Not for vision positions: PX4 would trust them far beyond their accuracy (§3) |
| Vision positions to the autopilot (`NAVERA_FORWARD_DEGRADED`) | **No supported path today** (§4) |
| Vehicle link (`navera-vehicle-link`: attitude, rangefinder, height, armed state) | Probably usable (it recognises PX4 heartbeats and requests messages with `MAV_CMD_SET_MESSAGE_INTERVAL`) — *not verified* |
| The autopilot's second GPS as NAVERA's GPS (`NAVERA_GPS_SOURCE=vehicle`) | Not selected by navera-discover (it reads ArduPilot's `GPS_TYPE2` / `GPS2_TYPE`, which PX4 does not have); writing it by hand depends on PX4 streaming `GPS2_RAW` — *not verified* |
| ROS output `/navera/fix` | Available to the vehicle's ROS 2 software; feeding it into PX4 needs the integrator's own bridge (§4) |

## 2. The MAVLink output and PX4

NAVERA's MAVLink output sends `GPS_INPUT` (#232). PX4's MAVLink receiver has no handler for
it in v1.15.4, v1.16.0, release/1.18 or main: the message is silently dropped (*PX4 source*).
`gps_id`, `ignore_flags` and `GPS_TYPE = 14` are ArduPilot features with no PX4 equivalent.

Consequences:

- **Nothing to set with the default settings.** When navera-discover finds a PX4
  autopilot (heartbeat `autopilot = MAV_AUTOPILOT_PX4`) and `NAVERA_MAVLINK_URL` is empty,
  it leaves the MAVLink output **off** and reports
  "CHECK output: the autopilot is PX4, which ignores MAVLink GPS_INPUT …" (shown as WARN by
  `check_box.py`; code: `navera_common/discovery.py`). Writing `NAVERA_MAVLINK_URL=off` makes
  that explicit and silences the CHECK line.
- **Do not write a `NAVERA_MAVLINK_URL` address on a PX4 vehicle**: a written value is
  always kept, and the `GPS_INPUT` messages would reach PX4 and be ignored without any error
  that `check_box.py` could see.
- The ArduPilot results in VALIDATION_STATUS.md (SITL, autopilot in the loop) say nothing
  about PX4.

PX4 accepts a MAVLink GPS in another form — `HIL_GPS` (#113) with the parameter
`MAV_USEHILGPS = 1`, from a sender using the autopilot's own system id (`MAV_SYS_ID`); its
`eph` / `epv` fields are read as the accuracy (cm), and its velocity is always used
(*PX4 source*). **NAVERA does not send `HIL_GPS`.**

## 3. NMEA output to PX4 (GPS pass-through)

NAVERA side (`/etc/navera/navera.env`), then `sudo systemctl restart navera-output`:

```
NAVERA_NMEA_PORT=/dev/ttyTHS2
NAVERA_NMEA_BAUD=9600
NAVERA_MAVLINK_URL=off
# keep these at their defaults: no vision position over NMEA
#NAVERA_FORWARD_DEGRADED=false
#NAVERA_NMEA_FORWARD_DEGRADED=false
```

PX4 parameters (names as in v1.16; *PX4 source*, *not verified with NAVERA*):

| Parameter | Value | Why |
|---|---|---|
| `GPS_1_CONFIG` | the serial port wired to NAVERA (e.g. TELEM 2 / GPS 2) | the port the GPS driver opens |
| `GPS_1_PROTOCOL` | **6** (NMEA) | NMEA is never auto-detected; reboot required. On flash-constrained boards the NMEA driver may not be built in (`CONFIG_GPS_NMEA`) |
| `SER_xxx_BAUD` of that port | = `NAVERA_NMEA_BAUD` | |

What PX4's NMEA driver takes from NAVERA's sentences (*PX4 source*, PX4-GPSDrivers
`nmea.cpp`): from GGA the position, altitude, geoid separation, satellites and HDOP, and the
fix type (quality 1 → 3D fix); from RMC the horizontal velocity. **The position accuracy
(`eph` / `epv`) is read only from GST sentences, which NAVERA does not send**, so PX4 has no
accuracy from NAVERA (it is left unset — inferred from the source, not traced end to end).
EKF2 then uses its own floor, `EKF2_GPS_P_NOISE` (0.5 m by default), as the position noise:
a GPS pass-through is fused as a good receiver, which is what it is; **a vision position
over NMEA would be fused as a 0.5 m GPS**. Keep `NAVERA_NMEA_FORWARD_DEGRADED` off.

Whether EKF2's GPS quality checks (`EKF2_GPS_CHECK`, §5) accept NAVERA's GGA + RMC stream
— in particular the EPH (`EKF2_REQ_EPH`) and PDOP (`EKF2_REQ_PDOP`) checks with no GST
or GSA sentence — has **not been checked**: test on a PX4 SITL or on the bench before
flying, and watch the ground station's GPS / EKF status.

When NAVERA reports "no fix" (GPS lost, vision withheld), PX4 sees its GPS lose the fix and
its own failsafe acts — the same safe outcome as with ArduPilot.

## 4. Vision positions to PX4: no supported path today

With the current NAVERA release there is **no supported way to give PX4 NAVERA's vision
positions**:

- `GPS_INPUT` is ignored (§2);
- NMEA carries no accuracy (§3);
- PX4's documented route for an external global position from a companion computer is the
  ROS 2 interface (`px4_ros2` GlobalPositionMeasurementInterface → the uORB topic
  `aux_global_position`, through uXRCE-DDS), fused by EKF2 as an *auxiliary global
  position* (v1.16: `EKF2_AGP_CTRL`, `EKF2_AGP_DELAY`, `EKF2_AGP_NOISE`, `EKF2_AGP_GATE`;
  release/1.18 and main also accept the MAVLink message `GLOBAL_POSITION_SENSOR` with
  `EKF2_AGP0_ID` … per-slot parameters). NAVERA does not implement it. An integrator could
  bridge `/navera/fix` (sensor_msgs/NavSatFix, accuracy in the covariance, vision positions
  marked `status.service = 0`) to it in their own ROS 2 node — **not provided, not
  tested**.

If such a bridge is built, note that EKF2 bounds the position noise it uses: for a GPS,
noise = max(stated accuracy, `EKF2_GPS_P_NOISE`), capped at `EKF2_NOAID_NOISE` (10 m by
default) when GNSS is the only horizontal aiding source (*PX4 source*, v1.16
`gps_control.cpp`) — a stated accuracy above that cap is trusted more than stated, as with
ArduPilot's 100 m cap. Check the equivalent for the auxiliary-position path before relying
on it.

## 5. EKF2 GPS settings (reference)

For the NMEA pass-through (§3). Names and defaults of PX4 v1.16.0 (*PX4 source*,
`src/modules/ekf2/params_gnss.yaml`); none tuned or verified with NAVERA.

| Parameter | Default | Meaning |
|---|---|---|
| `EKF2_GPS_CTRL` | 7 | bitmask: bit 0 latitude/longitude, bit 1 altitude, bit 2 3D velocity, bit 3 dual-antenna heading. Clearing bit 2 stops GPS velocity fusion (the PX4 counterpart of ArduPilot's `EK3_SRC1_VELXY = 0`, with the same cost: no GPS velocity also while GPS is healthy) |
| `EKF2_GPS_DELAY` | 110 ms (0–300) | GPS delay relative to the IMU; reboot required. Release 1.18 replaces it by `SENS_GPS0_DELAY` / `SENS_GPS1_DELAY` |
| `EKF2_GPS_CHECK` | 1023 | bitmask of quality checks before GPS is used: satellites (`EKF2_REQ_NSATS`, 6), PDOP (`EKF2_REQ_PDOP`, 2.5), EPH (`EKF2_REQ_EPH`, 3 m), EPV (`EKF2_REQ_EPV`, 5 m), speed accuracy (`EKF2_REQ_SACC`, 0.5 m/s), drift and speed offsets (`EKF2_REQ_HDRIFT` 0.1 m/s, `EKF2_REQ_VDRIFT` 0.2 m/s), spoofing |
| `EKF2_REQ_GPS_H` | 10 s | how long the checks must pass at start-up before GPS is used; reboot required |
| `EKF2_GPS_P_NOISE` | 0.5 m | floor of the GPS position noise |
| `EKF2_GPS_P_GATE` | 5 σ | position innovation gate |
| `EKF2_GPS_V_NOISE` / `EKF2_GPS_V_GATE` | 0.3 m/s / 5 σ | velocity noise and gate |
| `EKF2_NOAID_NOISE` | 10 m | also the cap on the GPS position noise when GPS is the only horizontal aiding |

Any fix type below 3D fails the GPS checks whatever the mask. As with ArduPilot, **PX4
needs a GPS that passes its checks at power-on** to initialise its global position: start
with GPS. On PX4 `main` these checks are renamed (`GNSS_CHECK`, `GNSS_REQ_*`); use the
parameter reference of your firmware version.

## 6. Two GPS: selection and blending

PX4 handles up to two GPS receivers (*PX4 source*, v1.16 `vehicle_gps_position`):

| Parameter | Default | Meaning |
|---|---|---|
| `SENS_GPS_MASK` | 7 | which accuracies weight the **blending** of the two receivers (bit 0 speed, bit 1 horizontal, bit 2 vertical accuracy); 0 = no blending |
| `SENS_GPS_PRIME` | 0 | preferred receiver when not blending (the other is used only if it times out); −1 = equal priority; no effect while blending |
| `SENS_GPS_TAU` | 10 s | time constant of the offset correction between receivers |

Without blending, PX4 picks the receiver with the best fix type, then the most satellites,
unless the preferred one has a 3D fix. With NAVERA as one GPS and a real receiver as the
other, blending would mix NAVERA's output with the very receiver NAVERA may have refused
(spoofing) — consider `SENS_GPS_MASK = 0` and `SENS_GPS_PRIME` set to NAVERA's instance,
weighed against your failsafe strategy (*not verified*). On `main` these are
`SENS_GNSS_MASK`, `SENS_GNSS_PRIME`, `SENS_GNSS_TAU`.

## 7. What it would take to support PX4

Tracked as backlog OUT-4 (validate on PX4). A PX4 SITL run is the first step: NMEA
pass-through and the vehicle link, then a vision-position path (a `HIL_GPS` output or a
ROS 2 / uXRCE-DDS `aux_global_position` bridge) with its accuracy handling measured. Until
then, use PX4 with NAVERA only for GPS pass-through over NMEA and for the operator view.

## Sources

PX4 source and documentation read on 2026-10-03:

- MAVLink receiver (no `GPS_INPUT` handler; `HIL_GPS` handling):
  https://github.com/PX4/PX4-Autopilot/blob/v1.16.0/src/modules/mavlink/mavlink_receiver.cpp
- `MAV_USEHILGPS`: https://github.com/PX4/PX4-Autopilot/blob/main/src/modules/mavlink/mavlink_params.yaml
- GPS driver parameters (`GPS_1_PROTOCOL`, `GPS_1_CONFIG`):
  https://github.com/PX4/PX4-Autopilot/blob/main/src/drivers/gps/params.yaml,
  https://github.com/PX4/PX4-Autopilot/blob/main/src/drivers/gps/module.yaml
- NMEA parser: https://github.com/PX4/PX4-GPSDrivers/blob/main/src/nmea.cpp
- NMEA example in the PX4 guide:
  https://docs.px4.io/main/en/gps_compass/rtk_gps_holybro_unicore_um982.html
- EKF2 GPS parameters and noise:
  https://github.com/PX4/PX4-Autopilot/blob/v1.16.0/src/modules/ekf2/params_gnss.yaml,
  https://github.com/PX4/PX4-Autopilot/blob/v1.16.0/src/modules/ekf2/EKF/aid_sources/gnss/gps_control.cpp
- EKF tuning guide: https://docs.px4.io/main/en/advanced_config/tuning_the_ecl_ekf.html
- Parameter reference: https://docs.px4.io/main/en/advanced_config/parameter_reference.html
- Two-GPS selection and blending:
  https://github.com/PX4/PX4-Autopilot/blob/v1.16.0/src/modules/sensors/vehicle_gps_position/params.c
- Auxiliary global position (ROS 2 interface, uXRCE-DDS):
  https://docs.px4.io/main/en/ros2/px4_ros2_navigation_interface.html,
  https://docs.px4.io/main/en/middleware/uxrce_dds.html,
  https://github.com/PX4/PX4-Autopilot/blob/main/src/modules/ekf2/params_aux_global_position.yaml
- Release notes 1.18 (GPS delay parameters): https://docs.px4.io/main/en/releases/1.18.html
