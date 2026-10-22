# NAVERA — PX4 integration

How NAVERA works with a PX4 autopilot. Read [deploy/README.md](../deploy/README.md) first; the
ArduPilot equivalent is [ARDUPILOT_INTEGRATION.md](ARDUPILOT_INTEGRATION.md).

> **Status: PX4 SITL only (v1.15.4, SIH quadrotor, 2026-10-22).** No PX4 vehicle has been
> connected to NAVERA. Each item is marked:
>
> - **PX4 SITL** — exercised in PX4 v1.15.4 SITL with NAVERA's own output and vehicle-link nodes
>   (`navera_tools/tests/sitl_px4.py`, §4);
> - **PX4 source** — read in the PX4 source (v1.15.4 unless stated), not exercised;
> - **Not verified** — a recommendation to be confirmed on a vehicle.

## 1. Summary

| NAVERA function | With PX4 |
|---|---|
| MAVLink output (`NAVERA_MAVLINK_URL`) | **`HIL_GPS` (#113)** instead of `GPS_INPUT`, which PX4 does not handle. Chosen automatically: navera-discover writes `NAVERA_MAVLINK_MESSAGE=hil_gps` when the autopilot's heartbeat says PX4, and the output node switches by itself on a PX4 heartbeat (`auto`). PX4 needs `MAV_USEHILGPS = 1` and the EKF2 settings of §2 — *PX4 SITL* |
| Vision positions to the autopilot (`NAVERA_FORWARD_DEGRADED`) | Same rules as ArduPilot (forwarded only when enabled, with a stated accuracy), sent as `HIL_GPS` with the stated `eph` — *PX4 SITL*: a GPS-denied AUTO mission flown on them (§4) |
| Vehicle link (`navera-vehicle-link`: attitude, height, armed state, the relay) | Works: "connected to PX4", relays NAVERA's `HIL_GPS` on the one autopilot link — *PX4 SITL* |
| NMEA output (`NAVERA_NMEA_PORT`) | GPS pass-through only (§5), *not verified*: NMEA carries no accuracy |
| The autopilot's GPS as NAVERA's GPS (`NAVERA_GPS_SOURCE=vehicle*`) | Not selected by navera-discover for PX4 (it reads ArduPilot's GPS type parameters): with the `HIL_GPS` output, PX4's GPS **is NAVERA** — never read it back |
| ROS output `/navera/fix` | Available to the vehicle's ROS 2 software |

## 2. The MAVLink output: `HIL_GPS`

**Why `HIL_GPS`** (*PX4 source*, §Sources). PX4's MAVLink receiver has no `GPS_INPUT` handler
(v1.15.4; also v1.16.0 / main read on 2026-10-03). It turns `HIL_GPS` into a `sensor_gps`
instance — a GPS that EKF2 fuses like a receiver — when `MAV_USEHILGPS = 1` and the message comes
from **the autopilot's own system id** (NAVERA uses it: `NAVERA_MAVLINK_SYSID`, written by
navera-discover). Its `eph` / `epv` (cm) are the accuracy, its `fix_type` must be 3, and **its
velocity is always taken as valid** (fixed 0.5 m/s accuracy, no "ignore" flag) and so is its
altitude. NAVERA therefore sends (`navera_output/mavlink_out.py::hil_gps_fields`):

| Field | GPS fix (forwarded receiver) | Vision / celestial position (forwarded) | "No fix" |
|---|---|---|---|
| `fix_type` | 3 | 3 | 1 |
| `lat` / `lon` | the receiver's | NAVERA's, carried to the present | 0 |
| `eph` | the receiver's stated accuracy | the stated accuracy (`NAVERA_DEGRADED_SIGMA_M`, or the source's when worse) | unknown |
| `alt` / `epv` | the receiver's MSL altitude / accuracy | **the last GNSS altitude held, `epv` unknown (655 m)** — never a vision height (F7) | 0 / unknown |
| `vn` / `ve` / `vel` / `cog` | the receiver's velocity | NAVERA's track velocity when trustworthy, else 0 with `vel` / `cog` unknown | 0 |
| `vd` | 0 (NAVERA measures none) | 0 | 0 |
| `satellites_visible` | the receiver's | 0 | 0 |

The other choices considered, and why not (§6): `VISION_POSITION_ESTIMATE` / `ODOMETRY` (local
frame, NAVERA would need PX4's origin and EKF2 treats it as odometry), NMEA (no accuracy), the ROS 2
`aux_global_position` interface (needs uXRCE-DDS and a ROS 2 PX4 message bridge on the vehicle).

### PX4 parameters (set them on the autopilot)

Tested values in PX4 v1.15.4 SITL (§4). navera-discover reads the first six from the autopilot
and reports a "CHECK PX4 …" line for each value that breaks the output (the last two only with
`NAVERA_FORWARD_DEGRADED=true`).

| Parameter | Value | Default | Why |
|---|---|---|---|
| `MAV_USEHILGPS` | **1** | 0 | PX4 reads `HIL_GPS` only then (otherwise it has no position: SITL, no home, no arming) |
| `EKF2_GPS_CTRL` | **1** (lat/lon only) | 7 | `HIL_GPS`'s velocity is always "valid" (an unknown one is 0) and its altitude is not a measurement for a vision position: neither may be fused. Also ArduPilot's choice (`EK3_SRC1_VELXY/VELZ = 0`): no GPS velocity also while GPS is good |
| `EKF2_HGT_REF` | **0** (barometer) | 1 (GPS) | NAVERA gives no height in GPS-denied flight; reboot required |
| `EKF2_GPS_CHECK` | **240** | 245 | clears bit 0 (satellites: a vision position has none) and bit 2 (EPH ≤ `EKF2_REQ_EPH` 3 m: a vision position states 10–30 m). EKF2 runs these checks on **every** sample, not only at start: a failing one is skipped and GPS fusion stops after ~7 s. Keep bit 8 clear (vertical speed discrepancy: NAVERA sends `vd` 0). NAVERA itself checks the receiver before forwarding it (FIX state) |
| `EKF2_GPS_V_GATE` | **100** | 5 | the velocity is not fused, but its innovation is still reported: `vd` 0 in a climb tripped the post-takeoff navigation test ("Navigation failure! Land and recalibrate sensors" → DESCEND during the take-off, SITL). The gate is used for nothing else with `EKF2_GPS_CTRL = 1` |
| `SYS_HAS_GPS` | 1 | 1 | the sensors hub must process `sensor_gps` |
| `COM_POS_FS_EPH` | **25** (≥ 20) | 5 | the position is declared invalid above 2.5 × this once valid: 12.5 m by default, below the 15–20 m eph of a vision-fed EKF — failsafe right after the GPS loss (§4, `px4_defaults`) |
| `EKF2_NOAID_NOISE` | **≥ the stated sigma** (50) | 10 | EKF2 caps the GPS position noise at this value while GPS is its only aiding: a stated 30 m would be fused as 10 m |
| `NAV_ACC_RAD` (multicopter) | 25 | 10 | waypoint acceptance larger than the position noise, or the vehicle circles a waypoint it "misses" by its vision error |
| `COM_VEL_FS_EVH` | 3 | 1 | velocity invalid above 2.5 × this; position-only fusion gives evh 1.5–2 m/s (SITL) |
| `SENS_GPS_MASK` / `SENS_GPS_PRIME` | with a second, real receiver: §8 | | |

`EKF2_GPS_DELAY` (110 ms) is left at its default: PX4 stamps `HIL_GPS` on arrival, and NAVERA
carries a vision position to the present before sending it (`policy.decide`).

Like ArduPilot, **PX4 needs a GPS fix at power-on** to set its origin and home: start with
NAVERA on GPS. In SITL PX4 armed ~35 s after the first fix (`EKF2_REQ_GPS_H` 10 s of passing
checks, then its pre-flight checks).

### What PX4 does when NAVERA stops (failsafe)

"No fix" (`fix_type` 1) and silence both stop the position: EKF2 skips the samples, stops GPS
fusion after ~5–7 s and invalidates the position; the commander then starts **its own
position-loss failsafe** (`Failsafe activated`; in AUTO a multicopter DESCENDs blind —
`COM_POSCTL_NAVL` / `NAV_*` settings decide). When NAVERA's positions come back, PX4 clears the
failsafe and **resumes the mission** (SITL, `output_restart`). Configure that failsafe; the
gap NAVERA bridges (`NAVERA_BRIDGE_MAX_S`, 10 s) is longer than PX4's ~5 s: a longer bridge does
not help PX4 unless the vision gaps are short.

## 3. Setup on the NAVERA side

Nothing to write by default: navera-discover finds the PX4 heartbeat, writes
`NAVERA_VEHICLE_MAVLINK_URL` (the autopilot port), `NAVERA_MAVLINK_SYSID` (its system id),
`NAVERA_MAVLINK_URL=udpout:127.0.0.1:14650` (the vehicle link's relay) and
`NAVERA_MAVLINK_MESSAGE=hil_gps`, and reports the PX4 parameters it read. To forward vision
positions (after the shadow-mode flights of deploy/README.md §7):

```
NAVERA_FORWARD_DEGRADED=true
NAVERA_DEGRADED_SIGMA_M=30          # your measured accuracy; PX4: EKF2_NOAID_NOISE >= this
```

`check_box.py` shows the CHECK lines; `journalctl -u navera-output | grep HIL_GPS` shows
"MAVLink output: the autopilot is PX4 — sending HIL_GPS".

## 4. PX4 SITL results (2026-10-22, simulation only)

`navera_tools/tests/sitl_px4.py`: PX4 v1.15.4 SITL, SIH quadrotor (headless, real time, no wind),
**no simulated GPS** (`SENS_EN_GPSSIM 0`): PX4's only horizontal position is NAVERA's `HIL_GPS`.
The chain is the product's: NAVERA's real `vehicle_output_node` (policy, bridge, reacquire,
`mavlink_message auto`) → the relay → NAVERA's real `vehicle_link_node` → PX4's onboard MAVLink
port. NAVERA's arbiter is emulated from the simulator's truth like the ArduPilot closed-loop
script: GPS = truth + 0.7 m at 5 Hz (stated 1.5 m); day vision one photo a second, 0.3–1.0 s late,
its error **replayed** from the real UAV-VisLoc results (pool "good": delivered median 17 m, p90
36–44 m), stated 30 m (`NAVERA_DEGRADED_SIGMA_M`). Mission: take-off 80 m, legs 300 / 400 / 400 /
400 m at 8 m/s, RTL and land; GPS lost at waypoint 1 for good (~260 s GPS-denied to touchdown).
Parameters of §2. Errors are PX4's EKF2 global position vs the simulator's truth (PX4's own log).
Run on the Jetson (shared CPU), one run per row.

| Run | PX4 EKF error on the GPS-denied legs med / p90 / max (m) | RTL + landing (m) | PX4 eph med / p90 (m) | Mission | End | PX4 events after the GPS loss |
|---|---|---|---|---|---|---|
| GPS phase (all runs) | 1.0–1.5 / — / 3.8 | | | | | |
| `nominal` | **14.8 / 50 / 89** | 15.8 / 42 / 81 | 17.9 / 24 | **done** (4 legs, RTL) | landed **86 m from home** | position invalid 3.7 s in the last metres of the descent (a 12 s run of refused photos, bridged 10 s: DRIFT ALARM ±114 m), `Failsafe activated`, DESCEND 6 s |
| `nominal`, vision only above 30 m (first run) | 15.8 / 36 / 73 | 15.9 / 48 / 122 | 17.4 / 44 | done | landed 109 m from home | no vision below 30 m: position invalid, blind DESCEND for the last 30 m |
| `navera_stop` (NAVERA silent at +90 s) | 18.2 / 30 / 50 (until the stop) | — | — | not done (2 of 4 legs) | landed 12 m from where NAVERA stopped (no wind) | output "no fix" at once (arbiter silent); position invalid ~2 s later; `Failsafe activated` → DESCEND without position control, 80 m in ~118 s |
| `output_restart` (output killed at +60 s, back 10 s later) | 17.4 / 59 / 90 | 21.6 / 39 / 67 | 18.1 / 26 | **done** | landed **19 m from home** | `Failsafe activated` 4.7 s after the kill → DESCEND, 13 m of height lost; mission **resumed by PX4** 24 s after the kill (10 s RestartSec + node start + the reacquire wait) |
| `px4_defaults` (`COM_POS_FS_EPH` 5, `EKF2_NOAID_NOISE` 10, `EKF2_GPS_V_GATE` 5) | 15.4 / 33 / 139 | — | **7.3 / 8.8** (true error ~15) | **not done** | landed 354 m from home | at take-off: "Navigation failure! Land and recalibrate sensors" → DESCEND 11 s; 97 s after the loss: position invalid (eph > 12.5 m) → DESCEND blind to the ground |
| `no_hil_param` (`MAV_USEHILGPS` 0) | — | — | — | not armed | on the ground | PX4 ignores every `HIL_GPS`: no home, no position, arming refused for 120 s — the safe outcome |

Findings:

1. **PX4 flies a GPS-denied AUTO mission on NAVERA's `HIL_GPS`** with the parameters of §2:
   EKF error on the legs median 15 m (the replayed vision itself: median 17 m, p90 36 m), the
   mission completed and RTL flown. ArduPilot with the same replayed errors (ARDUPILOT_INTEGRATION.md
   §3, Copter nominal) was better: 9.6–13 / 19–25 m — PX4 fuses the position only (no velocity),
   its EKF velocity is poor (evh 1.5–2 m/s) and its p90 is larger (36–59 m). The legs took
   55–100 s for 400 m at 8 m/s commanded.
2. **The landing is where it fails.** Any vision gap longer than PX4's ~5 s tolerance (bridged
   by NAVERA up to 10 s, but carried along a velocity that can be wrong) during the last metres
   made PX4 declare its position invalid and descend blind: 86 m and 109 m from home in two
   nominal runs (19 m in `output_restart`). A precision landing on vision alone is not
   available; land on GPS, with a rangefinder / optical flow, or under pilot control.
3. **PX4's position-loss failsafe acts after ~5 s** without a position (EKF2 GPS timeout, then
   `COM_POS_FS_DELAY`): shorter than NAVERA's 10 s bridge and than a service restart
   (`RestartSec=10`). PX4 then DESCENDs without position control in a mission, and **resumes the
   mission** when positions return (`output_restart`). Configure the failsafe for your vehicle.
4. **PX4's defaults are not usable with vision positions** (`px4_defaults`): `EKF2_NOAID_NOISE`
   10 m makes PX4 claim ±7 m while it is ~15 m off, and `COM_POS_FS_EPH` 5 m (invalid above
   12.5 m) ends the mission in a blind descent; `EKF2_GPS_V_GATE` 5 trips the post-takeoff
   navigation test on NAVERA's zero vertical speed. navera-discover checks these values.
5. Without `MAV_USEHILGPS` PX4 has no position at all and refuses to arm (`no_hil_param`).
6. The automatic choice works end to end: the output node switched to `HIL_GPS` on the PX4
   heartbeat seen in the vehicle link's status ("MAVLink output: the autopilot is PX4 — sending
   HIL_GPS"), through the relay, from the autopilot's own system id (4 for SITL instance 3).

Re-run: `nice -n 19 python3 navera_tools/tests/sitl_px4.py --px4 <PX4-Autopilot>` after
`make px4_sitl_default` (needs `pyulog`; results in `~/.navera_sim/px4_sitl/`).

## 5. NMEA output to PX4 (GPS pass-through)

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

Whether EKF2's GPS quality checks (`EKF2_GPS_CHECK`, §7) accept NAVERA's GGA + RMC stream
— in particular the EPH (`EKF2_REQ_EPH`) and PDOP (`EKF2_REQ_PDOP`) checks with no GST
or GSA sentence — has **not been checked**: test on a PX4 SITL or on the bench before
flying, and watch the ground station's GPS / EKF status.

When NAVERA reports "no fix" (GPS lost, vision withheld), PX4 sees its GPS lose the fix and
its own failsafe acts — the same safe outcome as with ArduPilot.

## 6. Paths not chosen

- **`VISION_POSITION_ESTIMATE` / `ODOMETRY`** (*PX4 source*: handled, → `vehicle_visual_odometry`,
  EKF2 external vision `EKF2_EV_CTRL`): a **local** NED/FRD position. NAVERA would have to know
  PX4's EKF origin (`GPS_GLOBAL_ORIGIN`) and convert; EKF2 treats external vision as odometry (a
  frame it may rotate, a position-bias estimator against GPS, resets by `reset_counter`) and does
  not raise the global position from it the way a GPS does. More conversions, more PX4-version
  coupling, and a different failure behaviour than the GPS path NAVERA already serves to
  ArduPilot.
- **NMEA** (§5): no accuracy reaches EKF2 — a vision position would be fused as a 0.5 m GPS.
- **ROS 2 `aux_global_position`** (uXRCE-DDS, `px4_ros2` GlobalPositionMeasurementInterface;
  EKF2 `aux_global_position.cpp` exists in v1.15.4): a global position with its own accuracy and
  EKF2 parameters (`EKF2_AGP_*`), the cleanest PX4-side semantics — but it needs the uXRCE-DDS
  agent and the PX4 ROS 2 messages on the vehicle's companion side and a bridge NAVERA does not
  have. A candidate for a later PX4-only integration; not implemented.

`HIL_GPS` reuses NAVERA's one GPS-output policy (what is sent, when "no fix") and PX4's GPS
failsafe path. Its costs, all handled above: a fixed velocity accuracy (velocity must not be
fused), a mandatory altitude (held, `epv` unknown, height from the barometer), `MAV_USEHILGPS`,
and the name — PX4 may rename or restrict HIL messages in a future release: re-run
`sitl_px4.py` on each PX4 version you fly.

## 7. EKF2 GPS settings (reference)

Names and defaults of PX4 v1.15.4 (*PX4 source*, `src/modules/ekf2/module.yaml`); the values for
NAVERA's `HIL_GPS` output are in §2.

| Parameter | Default | Meaning |
|---|---|---|
| `EKF2_GPS_CTRL` | 7 | bitmask: bit 0 latitude/longitude, bit 1 altitude, bit 2 3D velocity, bit 3 dual-antenna heading |
| `EKF2_GPS_DELAY` | 110 ms | GPS delay relative to the IMU |
| `EKF2_GPS_CHECK` | 245 | checks run on every sample: bit 0 satellites (`EKF2_REQ_NSATS` 6), 1 PDOP (`EKF2_REQ_PDOP`), 2 EPH (`EKF2_REQ_EPH` 3 m), 3 EPV (`EKF2_REQ_EPV`), 4 speed accuracy (`EKF2_REQ_SACC` 0.5 m/s), 5–7 drift / speed on the ground (`EKF2_REQ_HDRIFT`, `EKF2_REQ_VDRIFT`), 8 vertical speed discrepancy. The fix type (≥ 3) is always checked |
| `EKF2_REQ_GPS_H` | 10 s | how long the checks must pass at start-up before GPS is used |
| `EKF2_GPS_P_NOISE` | 0.5 m | floor of the GPS position noise |
| `EKF2_GPS_P_GATE` | 5 σ | position innovation gate |
| `EKF2_GPS_V_NOISE` / `EKF2_GPS_V_GATE` | 0.3 m/s / 5 σ | velocity noise and gate |
| `EKF2_NOAID_NOISE` | 10 m | also the cap on the GPS position noise when GPS is the only horizontal aiding |
| `EKF2_NOAID_TOUT` | 5 s | no aiding this long: the horizontal position is reported invalid |

On PX4 `main` the checks are renamed (`GNSS_CHECK`, `GNSS_REQ_*`) and release 1.18 replaces
`EKF2_GPS_DELAY` by `SENS_GPS0_DELAY`: use the parameter reference of your firmware version.

## 8. Two GPS: selection and blending

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

## 9. What remains

Backlog OUT-4: a real PX4 vehicle (bench, then shadow-mode flights with GPS), a fixed-wing PX4
SITL run, PX4 v1.16 / main (re-run `sitl_px4.py`), the NMEA pass-through on PX4, and wind in the
simulation (SIH runs without wind here).

## Sources

PX4 v1.15.4 source, cloned and built 2026-10-22 (`make px4_sitl_default`, SIH quadrotor) — the
lines this document relies on:

- `src/modules/mavlink/mavlink_receiver.cpp`: `handle_message()` switch (no `GPS_INPUT` case;
  `VISION_POSITION_ESTIMATE` / `ODOMETRY` → `handle_message_vision_position_estimate` /
  `handle_message_odometry`, lines 179–184); `HIL_GPS` accepted only when HIL is on or
  `get_use_hil_gps() && msg->sysid == mavlink_system.sysid` (lines 366–376);
  `handle_message_hil_gps()` → `sensor_gps` (`PublicationMulti`), eph / epv cm → m, `s_variance_m_s`
  fixed 0.25, `vel_ned_valid = true`, `timestamp = hrt_absolute_time()` (arrival)
- `src/modules/mavlink/mavlink_params.c`: `MAV_USEHILGPS` (default 0)
- `src/modules/ekf2/EKF/gps_control.cpp`: GPS checks on every sample (a failing sample is skipped,
  fusion stops after `reset_timeout_max`), `GnssCtrl` HPOS / VEL bits, position noise
  max(eph, `EKF2_GPS_P_NOISE`) capped at `EKF2_NOAID_NOISE` when GPS is the only aiding;
  `gps_checks.cpp` `runGnssChecks()` (fix type always, the rest by `EKF2_GPS_CHECK`)
- `src/modules/ekf2/EKF/ekf_helper.cpp` `get_innovation_test_status()`: the GNSS 3D velocity test
  ratio is reported while GPS position is fused, even with velocity fusion off
- `src/modules/commander/HealthAndArmingChecks/checks/estimatorCheck.cpp`: post-takeoff
  navigation test (both position and velocity ratios ≥ 1 for 2 s → "Navigation failure"),
  `checkPosVelValidity()` (invalid above 2.5 × `COM_POS_FS_EPH` once valid)
- `src/modules/simulation/sensor_gps_sim/parameters.c`: `SENS_EN_GPSSIM`

PX4 source and documentation read on 2026-10-03 (v1.16.0 and main, not built):

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
