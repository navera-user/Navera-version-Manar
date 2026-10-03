# NAVERA — ArduPilot integration

How to connect NAVERA to an ArduPilot autopilot: NAVERA as the autopilot's GPS (output), and
optionally NAVERA reading the autopilot's sensors (vehicle link). Read
[deploy/README.md](../deploy/README.md) first.

**Verification status.** NAVERA has **not yet been connected to a real autopilot**. Each item
below is marked:

- **SITL** — verified in ArduPilot SITL (`navera_tools/tests/sitl_ardupilot.py`,
  `navera_tools/tests/sitl_vehicle_link.py`, the mission simulator `navera_tools/sim/`),
  ArduCopter 4.5.7 source tree, plus Rover / motorboat in the simulator. *Verified in
  ArduPilot SITL only.*
- **Source** — read in the ArduPilot 4.5.7 source code, not exercised.
- **Not verified** — recommendation to be confirmed on the real vehicle.

PX4: not tested, and NAVERA's MAVLink output (`GPS_INPUT`) is not a message PX4 handles —
see [PX4_INTEGRATION.md](PX4_INTEGRATION.md).

## 1. The two connections

| Connection | Direction | NAVERA service | Setting |
|---|---|---|---|
| Output: NAVERA as a GPS | NAVERA → autopilot | `navera-output` | `NAVERA_MAVLINK_URL` (MAVLink `GPS_INPUT`) or `NAVERA_NMEA_PORT` (NMEA) |
| Vehicle link | autopilot → NAVERA | `navera-vehicle-link` | `NAVERA_VEHICLE_MAVLINK_URL` |

**One program per serial port.** Three ways to connect:

- **One TELEM port (what navera-discover sets up):** `navera-vehicle-link` owns the port
  (`NAVERA_VEHICLE_MAVLINK_URL`) and relays the output, which sends to it locally
  (`NAVERA_MAVLINK_URL=udpout:127.0.0.1:14650`). The output then depends on the vehicle
  link: while no vehicle link is connected to an autopilot, `navera-output` logs every 30 s
  that "the autopilot receives NOTHING from NAVERA", and `check_box.py` FAILs this setting
  when `NAVERA_VEHICLE_MAVLINK_URL` is empty. *Verified in ArduPilot SITL only*
  (`navera_tools/tests/sitl_discovery.py`).
- **Two TELEM ports:** the output and the vehicle link each open their own.
- **mavlink-router** on the Jetson shares one port (§6, *not verified*).

`check_box.py` FAILs a serial port named by two settings (GPS, NMEA output, MAVLink
output, vehicle link). `NAVERA_MAVLINK_URL=off` turns the MAVLink output off.

MAVLink addresses use one format everywhere (`navera_output/mavlink_url.py`):
`serial:/dev/ttyTHS2:921600` (documented form; `/dev/ttyTHS2,921600` is also accepted),
`udpin:<ip>:<port>`, `udpout:<ip>:<port>`, `tcp:<ip>:<port>`.

## 2. Wiring (Jetson UART ↔ autopilot TELEM port)

| Jetson | Autopilot TELEM | |
|---|---|---|
| UART TX | RX | crossed |
| UART RX | TX | crossed |
| GND | GND | common ground — always |
| — | +5 V | **not connected** (the Jetson and the autopilot each have their own supply) |
| (RTS / CTS) | (CTS / RTS) | optional; if not wired, disable flow control on that autopilot port (`BRD_SERn_RTSCTS = 0`) — *not verified* |

- **Logic levels:** the Jetson's 40-pin header UART is 3.3 V. Connect it only to a 3.3 V TTL
  port (Pixhawk-class TELEM ports are 3.3 V TTL — check your autopilot's documentation). Never
  to RS-232 levels; never to a 5 V TTL port without a level shifter.
- **Device names:** on the reference box `/dev/ttyTHS1` is the GPS receiver
  (`NAVERA_GPS_PORT`); the examples use `/dev/ttyTHS2` for the autopilot. Which `ttyTHS*`
  reaches which header pins depends on the carrier board — check its pinout. A USB-to-serial
  adapter also works: use its stable name `/dev/serial/by-id/…`. The service user needs the
  `dialout` group (`navera-output` and `navera-vehicle-link` also add it).
- **Baud rate:** the same on both ends (`SERIALn_BAUD` and the address). The vehicle link
  requests attitude at 50 Hz (`ATTITUDE` + `ATTITUDE_QUATERNION`), roughly 4–5 kB/s with the
  other messages: use at least 115200 baud (estimate, not measured); the examples use 921600.

## 3. Output: NAVERA as a MAVLink GPS (`GPS_INPUT`) — recommended

NAVERA side (`/etc/navera/navera.env`), then `sudo systemctl enable --now navera-output`:

```
NAVERA_MAVLINK_URL=serial:/dev/ttyTHS2:921600
```

Autopilot parameters (names as in ArduPilot 4.5: `GPS_TYPE`, `GPS_TYPE2`, `GPS_DELAY_MS`,
`GPS_DELAY_MS2`; recent firmware calls them `GPS1_TYPE`, `GPS2_TYPE`, `GPS1_DELAY_MS`,
`GPS2_DELAY_MS`):

| Parameter | Value | Why | Status |
|---|---|---|---|
| `GPS_TYPE` (`GPS1_TYPE`) | **14** (MAV) | NAVERA is GPS 1 | SITL |
| `SERIALn_PROTOCOL` | **2** (MAVLink 2) | on the TELEM port wired to NAVERA (SITL: `SERIAL1_PROTOCOL 2`) | SITL |
| `SERIALn_BAUD` | the NAVERA baud: 921 = 921600, 115 = 115200, 57 = 57600 | | Not verified (SITL used TCP) |
| `GPS_AUTO_CONFIG` | 0 | no receiver configuration sent to a "GPS" that is NAVERA | SITL |
| `EK3_SRC1_POSXY` | 3 (GPS, default) | position from NAVERA | SITL (default) |
| `EK3_SRC1_VELXY` | **0** | vision fixes carry no velocity, and ArduPilot kept fusing the *last* GPS velocity received: after GPS loss that stale velocity caused a glitch and an EKF failsafe (LAND) within 40 s. Cost: see below | SITL |
| `EK3_SRC1_VELZ` | **0** | same | SITL |
| `EK3_SRC1_POSZ` | 1 (barometer, default) | vision fixes carry no altitude | SITL (default) |
| `GPS_DELAY_MS` (`GPS1_DELAY_MS`) | see §5 | lag compensation | Not verified |

**What `EK3_SRC1_VELXY = 0` / `EK3_SRC1_VELZ = 0` cost.** These settings remove GPS velocity
fusion **at all times, also while the GPS is healthy** and NAVERA passes it through with the
receiver's velocity (*Source*: with the velocity source set to none, the EKF does not fuse
GPS velocity). The EKF then gets its velocity from integrating the IMU, corrected only
through position (and barometric height) fusion: velocity estimates are noisier and lag
more, which typically shows in position hold, wind estimation and the EKF's ability to
reject a GPS glitch by its velocity innovation. How much this matters for your vehicle has
**not been measured** with NAVERA; in SITL with GPS the autopilot's position error stayed at
1–3 m with these settings ([VALIDATION_STATUS.md](VALIDATION_STATUS.md), "Autopilot in the
loop"). Weigh it against the stale-velocity failsafe above. ArduPilot's alternative source
sets (`EK3_SRC2_*`, switched by an RC option or a script, §8) could keep GPS velocity while
GPS is good: *not tested with NAVERA*.

**Stated accuracy above 100 m.** ArduPilot's EKF3 limits the accuracy it uses for a GPS
position: R = constrain(reported accuracy, `EK3_POSNE_M_NSE`, 100 m)²
(`AP_NavEKF3_PosVelFusion.cpp`; `AP_NavEKF3_Measurements.cpp` also caps it at 100 m —
*Source*). A forwarded `NAVERA_DEGRADED_SIGMA_M` above 100 m (or a source's own accuracy,
plus its lag) is therefore trusted **as 100 m**, i.e. more than stated. `check_box.py`
WARNs above 100 m. With forwarding, state at most what you measured, and remember that
above 100 m the autopilot does not know how bad the position is.

**GPS 1 or GPS 2.** NAVERA sends `GPS_INPUT` with `gps_id = 0`. In ArduPilot 4.5.7 every GPS
instance of type 14 receives every `GPS_INPUT`, whatever its `gps_id` (*Source*), so
`GPS_TYPE2 = 14` would also be fed; newer firmware may route by `gps_id` to instance 1 only.
**NAVERA as GPS 1 is the configuration verified in SITL.** It is also required when the
autopilot's second GPS feeds NAVERA (§7).

**One real GPS fix at power-on.** ArduPilot sets its navigation origin only from a GPS that
passes its checks (satellites, HDOP); vision positions report 0 satellites. Start the
vehicle with GPS (NAVERA forwards it as a FIX), or set the origin explicitly
(`SET_GPS_GLOBAL_ORIGIN`). NAVERA itself also needs a GPS fix at start (deploy/README.md §5).
*SITL.*

**What the autopilot receives when GPS is lost.** Vision positions are DEGRADED and are
**not sent** unless `NAVERA_FORWARD_DEGRADED=true` with `NAVERA_DEGRADED_SIGMA_M` (the
accuracy the EKF must assume — use a measured value, at most 100 m as above). Without it
the autopilot receives "no fix" and its own failsafe acts (Copter LAND, Rover/boat HOLD in
SITL); an autopilot does not resume its mission by itself after a failsafe, even when
NAVERA has positions again. With it, positions are sent with 0 satellites, carried to the
present along the measured ground velocity and their accuracy grown by the lag
([navera_output/README.md](../navera_output/README.md)): arming checks that require
satellites must be adapted by the integrator, knowingly.

**GPS in doubt.** When day vision contradicts the GPS (2 fixes in a row beyond 3 σ),
NAVERA keeps passing the GPS on but states its accuracy no better than the gap (up to
500 m — so possibly above ArduPilot's 100 m cap) before it refuses it: the autopilot
already weighs it less when vision takes over ([ARCHITECTURE.md](ARCHITECTURE.md) §3).

Measured in SITL (simulated vision, not real accuracy): drone at 120 m, 10–15 m/s, GPS
jammed in flight, vision at the *target* accuracy (15 m σ): the autopilot flew the mission
on NAVERA's position, its own error 2–18 m for 2.5 min, no failsafe
([VALIDATION_STATUS.md](VALIDATION_STATUS.md), "Autopilot in the loop").

## 4. Output alternative: NMEA

For an autopilot (or any system) that takes a serial GPS receiver. NAVERA side:

```
NAVERA_NMEA_PORT=/dev/ttyTHS2
NAVERA_NMEA_BAUD=9600
```

| Parameter | Value | Status |
|---|---|---|
| `GPS_TYPE` (`GPS1_TYPE`) | **5** (NMEA) | SITL |
| `SERIALn_PROTOCOL` | **5** (GPS) | SITL (`SERIAL3_PROTOCOL 5`) |
| `SERIALn_BAUD` | **9** (9600, = `NAVERA_NMEA_BAUD`) | SITL (`SERIAL3_BAUD 9`) |
| `GPS_AUTO_CONFIG` | 0 | SITL |
| `EK3_SRC1_VELXY`, `EK3_SRC1_VELZ` | 0, 0 | as above (SITL with MAVLink) |

NAVERA sends GGA + RMC. **NMEA carries no accuracy ArduPilot uses**: it fuses an NMEA GPS
with its own position noise (`EK3_POSNE_M_NSE`, 0.5 m by default; accuracy is read only
from a vendor-specific sentence NAVERA does not send — *Source*, `AP_GPS_NMEA`). A 30 m
vision position sent over NMEA would be trusted as a 0.5 m GPS. So with
`NAVERA_FORWARD_DEGRADED=true`, degraded positions go over MAVLink and ROS only, and the
NMEA output says "no fix" for them, unless `NAVERA_NMEA_FORWARD_DEGRADED=true` (a warning
is logged and `check_box.py` WARNs; not recommended). **Use NMEA for GPS pass-through
only**; forward vision over MAVLink. (Were it forwarded, ArduPilot treats GGA quality 6 —
how NAVERA flags an estimated position — as a 3D fix.) With NMEA the output port carries no
MAVLink: the vehicle link needs its own port.

## 5. Latency: `GPS_DELAY_MS`

A vision position describes the instant the photo was taken, 1–2.5 s before it reaches the
output under load (`navera_output/policy.py`). NAVERA stamps every position it sends
(`GPS_INPUT` `time_week` / `time_week_ms`, NMEA time) and does not send one measured more
than `NAVERA_MAX_MEASUREMENT_AGE_S` (5 s) ago:

- **GPS** positions are sent stamped with their measurement instant (not carried);
- **vision / celestial** positions are carried to the present along the ground velocity
  fitted to NAVERA's recent positions, their accuracy grown by the speed error × their age,
  and sent stamped **now**; when no velocity is known they are sent stamped with their
  measurement instant, their accuracy grown by the maximum speed (`NAVERA_MAX_SPEED_KMH`) ×
  their age.

What ArduPilot does with it (*Source*, 4.5.7, MAVLink GPS): the `GPS_INPUT` time is mapped onto
the autopilot's clock by a transport-jitter correction that assumes the least-delayed of the
recent messages (re-estimated every 100 messages, delay capped at 2 s) arrived with no delay;
the EKF then places the fix `GPS_DELAY_MS` earlier still. Consequences:

- differences in delay between messages are preserved by NAVERA's timestamps;
- the **common, minimum delay is invisible to the autopilot**: only `GPS_DELAY_MS`
  (`GPS1_DELAY_MS`) compensates it. Range 0–250 ms, reboot required; 0 = the driver's
  default, 0.2 s for a MAVLink GPS. While NAVERA passes GPS through, that minimum is the GPS
  latency; carried vision positions are stamped at the instant they are sent, so their
  remaining delay is the short output path.

Recommendation (*not verified*): measure the latency on your box — in the NAVERA shell,
`ros2 topic echo /navera/position` shows `sensor_stamp` (measurement) and `header.stamp`
(publication) — and set `GPS_DELAY_MS` to the lowest latency you see, at most 250. Lowering
`NAVERA_MAX_MEASUREMENT_AGE_S` limits how stale a forwarded vision fix can be. The SITL
results above used the default lag. With NMEA, how ArduPilot uses the sentence time has not
been checked.

## 6. Vehicle link (autopilot → NAVERA)

Used for `NAVERA_SENSOR_SOURCE=vehicle` (attitude, rangefinder, barometric height),
`NAVERA_GPS_SOURCE=vehicle` (the autopilot's second GPS), and the armed lock of the
`/mission` page. NAVERA side, then `sudo systemctl enable --now navera-vehicle-link`:

```
NAVERA_VEHICLE_MAVLINK_URL=serial:/dev/ttyTHS1:921600   # a second TELEM port (ttyTHS1 is free when the box GPS is not used)
```

| Parameter | Value | Status |
|---|---|---|
| `SERIALm_PROTOCOL` | **2** (MAVLink 2) on a second TELEM port | SITL (`SERIAL2_PROTOCOL 2` in the simulator, `SERIAL1_PROTOCOL 2` in `sitl_vehicle_link.py`) |
| `SERIALm_BAUD` | the NAVERA baud | Not verified |
| Stream rates | none needed: vehicle_link requests its messages itself (`MAV_CMD_SET_MESSAGE_INTERVAL`: attitude 50 Hz, `GLOBAL_POSITION_INT` 10 Hz, `DISTANCE_SENSOR` 10 Hz, `GPS2_RAW` 5 Hz, `SYSTEM_TIME` 1 Hz), at every (re)connection | SITL (no `SRn_*` set) |
| `SRm_EXTRA1` / `SRm_POSITION` / `SRm_EXT_STAT` / `SRm_EXTRA3` | fallback only, if the autopilot ignores the interval requests: these groups carry `ATTITUDE`, `GLOBAL_POSITION_INT`, `GPS2_RAW`, `DISTANCE_SENSOR` + `SYSTEM_TIME` respectively in ArduCopter 4.5.7 | Source |
| Downward rangefinder | `RNGFNDx_ORIENT = 25` (down), for the height above ground | SITL |

In SITL, vehicle_link's attitude, height above home and rangefinder agreed with the
autopilot and the simulator (`sitl_vehicle_link.py`). *Verified in
ArduPilot SITL only.*

**Heartbeats.** vehicle_link waits for a heartbeat **from an autopilot**. Heartbeats from a
ground station, another onboard computer, a gimbal or a camera on the same link are
ignored, so a link that only carries a GCS heartbeat stays at "no heartbeat from an
autopilot on … — retrying".

**Sharing one autopilot port with mavlink-router** (*not verified*): mavlink-router owns the
serial port and offers it to both NAVERA nodes, e.g. over its TCP server:

```
# /etc/mavlink-router/main.conf (example)
[General]
TcpServerPort = 5760

[UartEndpoint autopilot]
Device = /dev/ttyTHS2
Baud = 921600
```

```
NAVERA_MAVLINK_URL=tcp:127.0.0.1:5760
NAVERA_VEHICLE_MAVLINK_URL=tcp:127.0.0.1:5760
```

Both NAVERA nodes use the autopilot's own MAVLink system id (`NAVERA_MAVLINK_SYSID`,
written by navera-discover when it finds the autopilot, default 1); the output uses
component 191, the vehicle link component 192.

## 7. The autopilot's second GPS as NAVERA's GPS (`NAVERA_GPS_SOURCE=vehicle`)

For a vehicle whose real GPS receiver is wired to the autopilot rather than to NAVERA:

- NAVERA feeds **GPS 1** (`GPS_TYPE = 14`, §3);
- the real receiver is **GPS 2** (`GPS_TYPE2` / `GPS2_TYPE` = its type, e.g. 1 auto);
- vehicle_link reads it from `GPS2_RAW` (3D fix or better) → `/navera/vehicle/gps2` →
  NAVERA's GPS source. The altitude is `alt_ellipsoid` when the autopilot sends it (NAVERA's
  altitudes are above the WGS84 ellipsoid); otherwise `alt` (above mean sea level) with a
  warning — then set `NAVERA_GROUND_ALTITUDE_M` as MSL too, or heights above ground are off
  by the geoid separation (tens of metres). The receiver's `h_acc` / `v_acc` become the
  accuracy; without `h_acc` the GPS is DEGRADED ("uncertainty unknown") and cannot be
  cross-checked.

navera-discover selects this source only when `GPS_TYPE2` / `GPS2_TYPE` (read from the
autopilot) is a real receiver type — fix or not yet — never 14 (MAV, the GPS NAVERA's own
`GPS_INPUT` feeds: a loop), and not when the parameters cannot be read. NAVERA must never
read back a GPS fed by its own output, nor the autopilot's fused position — vehicle_link
does not read them. *Discovery verified in SITL* (`sitl_discovery.py`: `GPS_TYPE2` 1 used,
14 refused); flying on the second GPS has not been run in SITL.

Consider (*not verified*): with automatic GPS switching (`GPS_AUTO_SWITCH`, default 1 = use
best), the autopilot may switch to GPS 2 by itself — for example when NAVERA reports "no fix"
or refuses a spoofed GPS — and fly on the very receiver NAVERA has refused. To make NAVERA
the only GPS the autopilot uses: `GPS_AUTO_SWITCH = 0` and `GPS_PRIMARY = 0`. Weigh this
against your vehicle's failsafe strategy.

## 8. Other EKF source settings

`EK3_SRC1_*` above is the only source set used in SITL. ArduPilot's alternative source sets
(`EK3_SRC2_*`, `EK3_SRC3_*`, switched by an RC option) have not been tested with NAVERA.

## 9. Checks after wiring

In the NAVERA shell (deploy/README.md §11):

```bash
journalctl -u navera-output -n 20          # "vehicle output: nmea=… mavlink=… ros=/navera/fix …",
                                           # then "output → fix (fix)" with GPS
journalctl -u navera-vehicle-link -n 20    # "connected to ArduPilot (system 1)"
journalctl -u navera-output -n 20 | grep -i nothing   # empty: the relay reaches the autopilot
ros2 topic echo /navera/vehicle/status --once
python3 /home/navera/isaac_ros_common/navera_tools/check_box.py
```

On the ground station: the autopilot's GPS 1 must report a 3D fix at the vehicle's position
while NAVERA has GPS, and "no fix" within a few seconds after `sudo systemctl stop navera-gps`
(unless degraded forwarding is enabled and vision has a position). Restart it with
`sudo systemctl start navera-gps`. Problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
