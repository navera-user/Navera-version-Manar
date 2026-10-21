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
| `EK3_SRC1_POSZ` | 1 (barometer, default) — **never 3** | vision fixes carry no altitude (ArduPilot reads it as 0 m) | SITL, EKF height logged (below) |
| `EK3_OGN_HGT_MASK` | 0 (default) — **never set** | it would correct the EKF origin height from that 0 m | Source |
| `GPS_DELAY_MS` (`GPS1_DELAY_MS`) | 0 (default: 200 ms for a MAVLink GPS) — see §5 | lag compensation; vision positions are carried to the present, 1 ms changed nothing measurable | SITL closed loop |
| `EK3_GLITCH_RAD` | **100** on Copter (default 25); default on Plane | with ±30 m vision fixes the default makes EKF3 reset onto almost every fix and the position controller's target random-walks with the resets: RTL landings 136–290 m from home → 4–21 m | SITL closed loop (§3, "Closed loop") |
| `FS_EKF_ACTION` / `FS_EKF_THRESH` | defaults (1 = LAND, 0.8) | a copter loses its EKF ~25 s into a vision outage whatever the threshold; LAND is the safe outcome | SITL closed loop |
| `AHRS_OPTIONS`, `ARSPD_OPTIONS` (Plane) | defaults (0, 11) | disabling the DCM fallback / the airspeed check made a 60 s outage worse (5 km off track) | SITL closed loop |

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

### Height: NAVERA's positions never move the vehicle's height (F7) — SITL 2026-10-20

`navera_tools/tests/sitl_f7_height.py` (ArduCopter 4.5.7 SITL, no simulated GPS, the
parameters above; home 300 m AMSL, hover at 40 m in GUIDED). It plays NAVERA: every
`GPS_INPUT` is built by `mavlink_out.gps_input_fields()` from the simulator's true position
(vision: ±3 m noise, stated 15 m, 0 satellites). After take-off on a passed-through GPS, the
GPS is cut and the phases are: *vision* (exactly as sent: no altitude, `IGNORE_ALT`) 20 s;
*garbage_z* (ignored alt field = truth + 5000 m) 10 s; then, injected on the wire although
NAVERA never sends it (a bug, or a spoofed GNSS height passed through), an altitude flagged
**valid**: *wrong_z* (200 m low) 15 s, *jumps* (±300 m every 2 s) 16 s, *drift* (position
**and** altitude pulled 90 m north / up at 1 m/s) 90 s, *hold* 10 s. Analysed from the
dataflash log (XKF1 PD/PN/PE core 0, BARO Alt, SIM truth, GPS Alt, XKF3 IPD, XKF4 SH):

| Phase | Recommended (`POSZ = 1`): EKF − baro max | EKF height at end (true) | `POSZ = 3`: EKF − baro max | EKF height at end (true) |
|---|---|---|---|---|
| gps | 0.3 m | 39.9 m (38.2) | 1.9 m | 40.0 m (40.1) |
| vision | **0.0 m** | 40.0 m (38.3) | **431 m** | **−277 m (150 m)** |
| garbage_z | 0.0 m | 40.0 m (38.3) | 587 m | −297 m (278 m) |
| wrong_z | 0.0 m | 40.0 m (38.3) | 661 m | 234 m (468 m) |
| jumps | 0.0 m | 40.0 m (38.3) | 397 m | 334 m (643 m) |
| drift | 0.0 m | 40.0 m (38.3) | 404 m | 915 m (825 m) |
| hold | 0.0 m | 40.0 m (38.3) | 55 m | 899 m (809 m) |

(Heights above the EKF origin. The constant 1.7 m between the EKF and the truth in the
recommended run is the simulated barometer's own offset, present before the GPS cut.)

- **(a) Recommended parameters:** the EKF height followed the barometer within 0.1 m in every
  phase, whatever the message carried — no altitude (ArduPilot logged GPS Alt = 0 m AMSL,
  −300 m here), an ignored +5000 m, a valid altitude 200 m below the truth, jumps of ±300 m, a slow
  90 m drift. Height innovation |IPD| ≤ 0.1 m (barometer only).
- **(b) `EK3_SRC1_POSZ = 3` (control):** the very first phase — NAVERA's normal vision output
  — pulled the EKF height to the 0 m AMSL ArduPilot stores for an ignored altitude: −277 m
  within 20 s, while the vehicle climbed to 150 m to "hold" 40 m, then to 825 m as the wrong
  heights followed. The test is sensitive; the setting must never be used with NAVERA.
- **(c) Horizontal:** the same vision positions are used: during the 90 m drift spoof the EKF
  position moved 88 m north of the truth (92 m at the end of *hold*), i.e. it follows the
  vision position (and the vehicle was flown 90 m off by it — the cost of an undetected spoof,
  not a height effect). Unspoofed, the EKF stayed within 2.8–3.7 m of the truth.

**Change made with this test.** `mavlink_out` sends an altitude only for a satellite (GNSS)
position: a vision / celestial one goes out with `IGNORE_ALT` even if its producer attached a
height (unit test `test_gps_input_never_carries_a_vision_height`). Before, a non-GNSS position
with a height and a geoid separation would have been sent with a valid altitude — no vision
source does that today, so this closes a latent path, not an observed one.

What remains outside this test: the EKF origin's AMSL height is taken from the GPS fix when it
is set (a real GPS at power-on, above) — it only affects AMSL altitudes, not the height the
vehicle flies by; ArduPlane / Rover: run 2026-10-21, below; real barometers
drift (weather), which NAVERA cannot correct and does not try to.

**ArduPlane and Rover 4.5.7 (SITL 2026-10-21, `--vehicle plane|rover`)**, same phases (Plane:
AUTO take-off, then loiter at 60 m; Rover: armed, standing in HOLD). Both PASS:

| Vehicle | Recommended: EKF − baro max, every vision phase | EKF − truth max | `POSZ = 3` control: EKF − baro max | Drift spoof: EKF moved north (of 90 m) |
|---|---|---|---|---|
| Copter (2026-10-20) | 0.0 m | 1.7 m (baro offset) | 397–661 m | 88 m |
| Plane | 0.5–0.7 m | 3.1–3.2 m (baro offset, 3.8 m with GPS) | 289–626 m; the plane flew into the ground (true height 0.1 m at the end) | 94 m |
| Rover | 0.3 m | 0.1 m | 300 m (EKF height = the 0 m AMSL of the ignored altitude) | 92 m |

Run: `nice -n 19 python3 navera_tools/tests/sitl_f7_height.py [--vehicle copter|plane|rover]
[--instance N]` (both runs, ~9 min; `--keep` keeps the logs). The logging arming check is
excluded in this script only: on the loaded Jetson the SITL log thread misses its heartbeat
although the log is written.

### Closed loop: GPS-denied AUTO missions on NAVERA's positions only (SITL 2026-10-21)

`navera_tools/tests/sitl_closed_loop.py`, ArduCopter / ArduPlane 4.5.7 SITL, no simulated GPS,
the parameters of §3. *Simulation with a measured error model, not flight results.* The script
plays NAVERA with NAVERA's own code (`gps_crosscheck`, `TrackVelocity`, `policy.decide / hold /
bridge`, `mavlink_out`, the `vehicle_output_node` send logic) on the autopilot's clock:

- GPS: truth + 0.7 m at 5 Hz until the first waypoint, then lost for good;
- day vision, one photo per second, delivered 0.3–1.0 s later (uniform), its error **replayed photo
  by photo, in order** from the 8 real UAV-VisLoc flights with the pose–attitude guard
  (`f*_guard4.json`, [VALIDATION_STATUS.md](VALIDATION_STATUS.md)): an accepted photo gives its
  measured east/north error, a refused one no fix. Pool "good" (flights 03/04/06/11, 74–91 %
  accepted) for every scenario, "poor" (01/05/08/10, 5–27 % accepted, refusal runs up to 120
  photos) for *poor*. Stated accuracy: the 30 m floor (max(30 m, matcher sigma)),
  `NAVERA_DEGRADED_SIGMA_M = 30`; delivered errors after the loss: median 12–14 m, p90 25–31 m;
- scenarios (after the loss): *nominal*; *outageN* (no photo for N s from +40 s; NAVERA bridges
  ≤ 10 s, then "no fix"); *burst* (10 accepted fixes 150 m cross-track); *spoof* (from waypoint 1
  the GPS is pulled 2 m/s north while still received, jammed 120 s later); *poor*.

Missions: Copter 80 m, 10 m/s, legs 300 / 400 / 400 / 400 m then RTL and land; Plane 100 m,
~22 m/s, legs of 0.6–1.2 km then RTL (loiter over home). One run per row (seed 1; a second seed
of Copter nominal: EKF error median 12.5 m, landing 21 m from home — read differences of a few
metres as noise). "EKF error" = the autopilot's position minus the truth after the loss;
cross-track = the truth's distance to the leg, corners excluded.

| Run | EKF error med / p90 / max (m) | Cross-track med / p90 / max (m) | Mission | End | Autopilot events |
|---|---|---|---|---|---|
| Copter nominal, §3 params | 13.3 / 24.6 / 80 | 7.0 / 12.7 / 17 | done, 7.6 m/s instead of 10 | **landed 136 m from home** (RTL) | none |
| Copter nominal, + `EK3_GLITCH_RAD 100` | **9.6 / 18.7 / 26** | 6.0 / 12.4 / 16 | done, 9.2 m/s | **landed 9 m from home** | none |
| Copter outage 10 s, §3 | 13.5 / 26.7 / 96 | 6.5 / 16.2 / 80 | done | landed 264 m from home | none |
| Copter outage 10 s, + glitch 100 | 10.2 / 20.3 / 44 | 9.4 / 17.9 / 44 | done | landed 8 m from home | none |
| Copter outage 30 s (either) | 14 / 60–65 / 66–77 | — | **not done** | EKF failsafe → LAND ~18 s after the bridge ends, landed 377–402 m from home | EKF variance, EKF failsafe, "stopped aiding" |
| Copter outage 60 s, §3 | 23 / 65 / 66 | — | not done | same, 405 m from home | same |
| Copter outage 30 s, glitch 100 + bridge 60 s | 8.6 / 49 / 354 | 8.0 / 184 / 234 | done | landed 4 m from home | none — but 234 m off track while bridged |
| Copter outage 60 s, glitch 100 + bridge 60 s | 57 / 967 / 1428 | 138 / 559 / 663 | not done | LAND, 247 m from home | GPS glitch, EKF failsafe |
| Copter burst 150 m, §3 / glitch 100 | 14.2 / 29 / 168 — 11.2 / 27 / 143 | 6.7 / 21 / 31 — 6.1 / 17 / 24 | done | 290 m — **9 m** from home | none |
| Copter spoof, §3 / glitch 100 | 15.5 / 34 / 73 — 16.2 / 34 / 50 | 7.1 / 17 / 21 — 16.8 / 18 / 18 | done | 222 m — **8 m** from home | none; GPS refused after 22–24 s at 44–47 m offset |
| Copter poor terrain (either) | 28–32 / 70 / 84–100 | — | not done | EKF failsafe → LAND, 338–344 m from home | EKF variance, failsafe |
| Plane nominal | **6.6 / 15.9 / 24** | 5.5 / 16.5 / 24 | done, 23 m/s | RTL loiter centre 27 m from home | none |
| Plane outage 10 s / 30 s | 5.9 / 16.3 / 23 — 6.1 / 15.6 / 97 | 3.5 / 17 / 23 — 3.3 / 18 / 26 | done | 27 m / 26 m | none |
| Plane outage 60 s | 19 / 144 / **391** | 4.0 / 39 / 55 | done | 34 m | AHRS fell back to DCM 7 times after the outage |
| Plane burst 150 m | 8.3 / 28 / 90 | 6.3 / 15.6 / 19 | done (waypoint 2 missed by 95 m) | 28 m | none |
| Plane spoof | 9.1 / 78 / 88 | 2.6 / 8.2 / 10 | done | 28 m | none; GPS refused after 38 s at 76 m offset |
| Plane poor terrain | 230 / 761 / **799** | 366 / 679 / 699 | "done" in its own frame | 97 m | none (DCM fallbacks) |

Findings (each from the runs above; SITL, simulated sensors):

1. **Copter: raise `EK3_GLITCH_RAD` to 100.** With the default 25 m, EKF3 resets its position
   onto a fix whenever its own position variance exceeds 25 m (`posVarianceIsTooLarge`,
   `AP_NavEKF3_PosVelFusion.cpp`): with ±30 m fixes and no velocity aiding that is almost every
   fix — 123 position steps of median 16.6 m after the loss (24 per minute) in Copter nominal, 1
   with 100 m. The position controller moves its target with every reset
   (`AC_PosControl::handle_ekf_xy_reset`), so while hovering or descending the target random-walks:
   the RTL landings ended 136–290 m from home with §3 and **4–21 m with `EK3_GLITCH_RAD 100`**, the
   EKF error fell from 13.3 / 80 m (median / max) to 9.6 / 26 m, the copter flew 9.2 instead of
   7.6 m/s. Plane: no resets (airspeed fusion keeps its variance small); 100 brought nothing there
   and was worse after the 60 s outage (EKF error max 405 m, cross-track 1.1 km): keep the default
   on Plane until that outage case is understood (finding 4). Cost: a real GPS glitch below 100 m
   is no longer reset-to, only gated (`EK3_POS_I_GATE`).
2. **Copter cannot fly a GPS-denied gap longer than ~25 s.** NAVERA bridges 10 s; 15 s later EKF3
   stops aiding (`tiltDriftTimeMax_ms`, fixed in the code), the EKF failsafe trips (`FS_EKF_THRESH`
   0.8 default) and the copter LANDs, wherever it is — 377–405 m from home in the 30 / 60 s
   outages and on the poor-terrain pool. `FS_EKF_THRESH` cannot buy this time (the "stopped aiding"
   is not a threshold). A longer bridge (60 s) kept the copter in AUTO through a 30 s outage but
   flew it 234 m off track, and through 60 s 1.4 km off: **keep `NAVERA_BRIDGE_MAX_S` at 10 s**;
   for Copter, LAND on a long vision outage is the safer outcome. `FS_EKF_ACTION` = 1 (LAND, default)
   is the recommendation; 2 (AltHold) would leave a copter drifting.
3. **Plane flies GPS-denied missions well on day vision** (EKF error median 6–9 m, cross-track
   ≤ 26 m, RTL loiter 26–29 m from home) and through 10–30 s outages on airspeed dead reckoning
   (error ≤ 23 m after 30 s). No TECS / airspeed change was needed: height and speed come from
   barometer and airspeed sensor and were unaffected (95 m in RTL for 100 m commanded in every run).
4. **Plane, 60 s outage and sparse fixes: the EKF diverges when fixes come back.** Dead reckoning
   itself was good (14 m after 60 s), but at resumption EKF3 resets its velocity
   (`ResetVelocity`, after the velocity timeout) to the `GPS_INPUT` velocity — and ArduPilot's MAV
   GPS driver keeps the **last velocity it ever received** when a message carries none
   (`AP_GPS_MAV.cpp`: `state.velocity` updated only with `have_vel_h`): the real GPS velocity of the
   instant GPS was lost, in a direction the plane no longer flies. The plane's EKF then believed it
   flew north at 22.5 m/s while it flew south (log: XKF1 VN +22.5, truth −22.6), its position reset
   every ~15 s onto a fix, error up to 680 m between resets; AHRS fell back to DCM. With the DCM
   fallback disabled (`AHRS_OPTIONS 1`) and the airspeed never disabled (`ARSPD_OPTIONS 0`) it was
   worse: 5 km off track: **keep both defaults**. `EK3_SRC1_VELXY = 0` does not protect against this
   reset. The same mechanism explains the poor-terrain plane run (fixes 5–27 % of the time).
   NAVERA-side remedy tested below (*vision-velocity experiment*).
5. **Slow spoof:** NAVERA refused the drifting GPS after 22–24 s (Copter, 44–47 m offset) and 38 s
   (Plane, 76 m) with its trend test; the autopilot had followed it that far (EKF error max 50–88 m),
   then came back onto vision without any failsafe and completed the mission.
6. **Wrong-fix burst (10 fixes 150 m off, stated ±30 m):** EKF error max 143–168 m (Copter),
   90 m (Plane); missions completed, no failsafe; Plane missed the waypoint of that leg by 95 m. The
   EKF's 5-sigma gate does not reject a 150 m error stated ±30 m once its own variance has grown:
   the stated accuracy must cover the real errors (VALIDATION_STATUS: 30 m floor 0.999 within 3σ).
7. **`GPS_DELAY_MS`:** NAVERA sends a vision position carried to the present (stamped "now"), so
   the delay to compensate is only the output path. ArduPilot's default for a MAVLink GPS is
   200 ms (`GPS_Backend::get_lag`). Copter nominal with `GPS_DELAY_MS 1`: EKF error 9.5 / 18.2 /
   28 m vs 9.6 / 18.7 / 26 m with the default — no measurable effect at 10 m/s against ±16 m fixes.
   Recommendation: leave the default (0 = 200 ms); with a measured output-path latency, set it.
   Plane nominal with `GPS_DELAY_MS 1` (and the airspeed / DCM options of finding 4): 6.7 / 15.1 /
   25 m vs 6.6 / 16.7 / 25 m — no measurable effect at 22 m/s either.
8. **GPS accuracy fields:** NAVERA states max(30 m, matcher sigma) + lag growth, the EKF uses it as
   R (≤ 100 m cap, §3). `EK3_POSNE_M_NSE` only floors R (default 0.5 m): leave it. Do not send a
   smaller accuracy than measured: the burst shows what an over-trusted wrong fix does.

#### Vision-velocity experiment (NOT what NAVERA sends today)

`--vision-velocity`: the vision `GPS_INPUT` also carries NAVERA's track velocity
(`TrackVelocity`, zero when unknown) with its accuracy, so that EKF3's velocity reset (finding 4)
uses it instead of the stale GPS velocity. Not fused otherwise (`EK3_SRC1_VELXY = 0`).

| Run | EKF error med / p90 / max (m) | Cross-track med / p90 / max (m) | End |
|---|---|---|---|
| Plane outage 60 s: as sent today → with track velocity | 19 / 144 / 391 → **13 / 89 / 200** | 4 / 39 / 55 → 10 / **3198 / 3526** | RTL 34 m → 27 m |
| Plane poor terrain | 230 / 761 / 799 → 152 / 294 / 861 | 366 / 679 / 699 → 25 / 173 / 327 | RTL 97 m → 185 m |
| Copter nominal (glitch 100) | 9.6 / 18.7 / 26 → 9.7 / 19.0 / 26 | 6.0 / 12.4 / 16 → 7.1 / 12.8 / 17 | landed 9 m → 9 m |
| Copter outage 30 s (glitch 100) | 14 / 60 / 77 → 15 / 60 / 76 | — | LAND either way |

It removed the 180° velocity flip and halved the plane's EKF error after the outage, but in the
same run the plane flew 3.5 km past a waypoint while its EKF followed it (its position kept
up through resets every ~5 s, 123 resets of median 34 m: the velocity / wind states stayed
inconsistent with the positions, and L1 navigates on velocity). **Not a fix**: the Plane case of
a vision gap > 30 s, and of sparse vision, stays open (an ArduPilot-side behaviour — velocity
reset to a `GPS_INPUT` velocity — that NAVERA can only influence by what it sends). Until it is
understood, a plane mission should not rely on NAVERA over terrain where vision may be absent for
more than ~30 s. No change to `mavlink_out` was made.

#### With the real day pipeline in the loop

`navera_tools/tests/sitl_real_pipeline.sh` (mission simulator: ArduCopter SITL fed only by
`navera_output`, the camera rendered from the map, the real `day_subscriber`; scenario S11 of
`sitl_fault_campaign.py`: GPS cut 60 s after cruise, forwarding on, declared 30 m). It runs on the
Jetson (the simulator ran the same way on 2026-10-15/16, ~10 min per scenario at 1x) and holds the
GPU lock for the whole run. **Not run on 2026-10-21**: the GPU lock was queued behind six other GPU
jobs for the whole session. Relaunch: `navera_tools/tests/sitl_real_pipeline.sh` (waits for the
lock however long; results in `~/.navera_sim/real_pipeline_<date>/`). On a desktop with an NVIDIA
GPU: ROS 2 Humble + the NAVERA build, an ArduPilot SITL build (`./waf copter rover`), the map and
day dataset (`NAVERA_MBTILES`, `DAY_DATASET_DIR`, `TORCH_HOME` in `~/navera_env.sh`), then the same
command (`NAVERA_GPU_LOCK=/tmp/navera_gpu.lock`). Its imagery is cut from the map vision matches
against, so its accuracy is optimistic; the error-model runs above use measured real-flight errors.

#### Run / watch

```bash
# measurements (Jetson: ~5-8 min per run, 1x real time)
nice -n 19 python3 navera_tools/tests/sitl_closed_loop.py --vehicle copter \
    --scenarios nominal,outage10,outage30,outage60,burst,spoof,poor --set EK3_GLITCH_RAD=100 --instance 4
python3 navera_tools/tests/sitl_closed_loop.py --summarise ~/.navera_sim/sitl_closed_loop
# watch one mission on a desktop (MAVProxy map + console + live error plot)
bash navera_tools/tests/sitl_pc_setup.sh          # once
navera_tools/tests/sitl_watch.sh copter nominal --set EK3_GLITCH_RAD=100
```

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
(publication) — and set `GPS_DELAY_MS` to the lowest latency you see, at most 250 (closed-loop SITL 2026-10-21, vision
positions carried to the present: `GPS_DELAY_MS` 1 ms vs the 200 ms default made no measurable
difference on Copter or Plane, §3 "Closed loop"). Lowering
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
