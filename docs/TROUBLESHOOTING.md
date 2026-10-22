# NAVERA — Troubleshooting

Symptom → cause → check → fix. Messages in `monospace` are the exact log or web messages
(numbers and names vary).

**Where to look.** Each service logs to the journal: `journalctl -u <unit> -n 100` or
`-f` to follow (units: `navera-discover`, `navera-estimator`, `navera-gps`, `navera-imu`, `navera-rtc`,
`navera-pipeline-day|night|cn`, `navera-output`, `navera-vehicle-link`, `navera-web`).
`check` commands without `sudo` run in the **NAVERA shell** — the services' environment:

```bash
sudo -u navera -H bash
source /opt/ros/humble/setup.bash
source /home/navera/isaac_ros_common/install/setup.bash
set -a; . /etc/navera/navera.env; . /var/lib/navera/settings.env 2>/dev/null; . /var/lib/navera/discovered.env 2>/dev/null; set +a
cd /home/navera/isaac_ros_common
```

The quickest overall check is `python3 navera_tools/check_box.py` (PASS / WARN / FAIL per
item; add `--camera`, with the pipeline stopped, to open the camera itself; `--no-ros` for
the settings and files only). It reads `discovered.env` and checks the configuration
statically first (serial ports used twice, MAVLink addresses, relay without vehicle link,
forwarding settings, ROS network).

---

## Camera

### No camera / the pipeline restarts every 10 s

`cannot open the camera (/dev/…) — exiting so the service restarts` (journal of
`navera-pipeline-day`), or `check_box --camera`: `FAIL camera device — cannot open … (in use by
the pipeline? unplugged?)`.

| Cause | Check | Fix |
|---|---|---|
| Service user not in the `video` group (the pipeline units do not add it) | `id navera` | `sudo usermod -aG video navera`, then `sudo systemctl restart navera-pipeline-day` |
| Wrong device: `/dev/videoN` changed with plug order | `ls -l /dev/v4l/by-id/` | `NAVERA_CAMERA_DEVICE=/dev/v4l/by-id/usb-…-video-index0` in `/etc/navera/navera.env` |
| Camera held by another process (e.g. `check_box --camera` or `calibrate_camera.py` while the pipeline runs, or the reverse) | `sudo fuser -v /dev/video*` | stop one of them (`sudo systemctl stop navera-pipeline-day` before calibrating or testing) |
| Camera not in webcam mode / unplugged | `ls /dev/v4l/by-id/` is empty | set the camera to USB webcam mode, replug |
| `the camera stopped sending frames — exiting so the service restarts` | cable, power of the camera | — |
| `camera gives 1280x720, set to 1920x1080` | the camera's supported modes | set `NAVERA_CAMERA_SIZE` to a mode it delivers (and calibrate at that size) |
| CSI / gst input does not open | `gst-launch-1.0 nvarguscamerasrc num-buffers=10 ! fakesink` (CSI) or the `NAVERA_CAMERA_GST_PIPELINE` with `fakesink`; `python3 -c "import gi; gi.require_version('Gst','1.0')"` | the camera / pipeline must work in `gst-launch-1.0`; install `python3-gi gir1.2-gstreamer-1.0`; a gst pipeline must end in `appsink name=sink` with `format=BGR` |

### The pipeline does not start: camera settings

`set NAVERA_CAMERA_CALIBRATION (navera_tools/calibrate_camera.py) or at least
NAVERA_CAMERA_HFOV_DEG` — `check_box`: `FAIL camera settings`. Fix: calibrate the lens
(deploy/README.md §4), or at least set `NAVERA_CAMERA_HFOV_DEG`.

### Calibration refused

| Message | Cause | Fix |
|---|---|---|
| `calibration /etc/navera/camera.yaml is for 1280x720, the camera is set to 1920x1080` | a calibration is valid for one resolution | calibrate at `NAVERA_CAMERA_SIZE`, or set the size back |
| `calibration … was made with camera usb-A…, this one is usb-B…: calibrate this camera` | the file records the camera's `/dev/v4l/by-id` name (`camera_id`); another camera (or another unit of the same model) is plugged in | calibrate this camera (`navera_tools/calibrate_camera.py`) |
| `only 5 views with the board: at least 8 needed (20-40 recommended)` (calibration tool) | board not found often enough | better light, flat board, fill more of the image |
| Calibration result "POOR — redo with more, sharper views", or `check_box`: `WARN lens calibration … RMS 0.8 px` | blurred or too few varied views | redo; aim for RMS < 0.5 px |

### Frames "turning too fast"

`vehicle turning 45 deg/s at the exposure (max 30): the camera's tilt at that instant is
uncertain — not compared with the map`; operator view: `… % of the last minute's frames
unusable: the vehicle turns too fast for a fixed camera`.

| Cause | Check | Fix |
|---|---|---|
| Fixed camera, vehicle rolling / turning faster than `NAVERA_CAMERA_MAX_RATE_DPS` (30°/s) | `rate_dps` in `ros2 topic echo /day/frame_meta --field data` | fly smoother turns, fit a gimbal (`NAVERA_CAMERA_GIMBAL=true`: no rate limit), or raise the limit knowingly (1–360) — a stamp error then costs degrees of tilt |
| Rates high while the vehicle is still | `rate_dps` on the ground | the attitude source is noisy or jumps: check the IMU / vehicle link |

### Frames "too tilted"

`camera tilted 52 deg from vertical (max 45): not compared with the map` (frame reason), and
`68 % of the last minute's frames were too tilted to use: the vehicle leans too much for a
fixed camera — fit a gimbal or fly slower`.

| Cause | Check | Fix |
|---|---|---|
| Fixed camera on a multirotor at speed (it leans 30–45°) | `ros2 topic echo /day/frame_meta --field data` → `tilt_deg` | fit a gimbal and set `NAVERA_CAMERA_GIMBAL=true`, or cruise slower |
| Gimbal fitted but not declared | `NAVERA_CAMERA_GIMBAL` | `NAVERA_CAMERA_GIMBAL=true` (only the heading is then used) |
| Wrong camera mounting angles | tilt reported while the vehicle is level on the ground | measure and set `NAVERA_CAMERA_MOUNT_RPY` |
| Wrong IMU mounting angles | roll/pitch in `frame_meta` while level | set `NAVERA_IMU_MOUNT_RPY` (navera.env or `/mission`) |

### "No attitude"

`no attitude at the frame's exposure (IMU or vehicle link silent): the camera's tilt is
unknown`, or `attitude frozen (identical samples): frames not used until it moves`;
`check_box`: `FAIL attitude — nothing on /navera/sensors/imu`.

| Cause | Check | Fix |
|---|---|---|
| `NAVERA_SENSOR_SOURCE` does not match the installation | `check_box` line "sensor source" | `box` = BNO085, `vehicle` = autopilot, `ros` = `NAVERA_ROS_IMU_TOPIC` |
| `box`: IMU service down or BNO085 not found — `BNO085 init failed on I2C bus 1 @ 0x4A: …` | `journalctl -u navera-imu -n 50`; `id navera` (group `i2c`); `sudo i2cdetect -y -r 1` shows `4a` | wiring (SDA pin 27, SCL pin 28, 3.3 V), address, `i2c` group |
| `vehicle`: vehicle link not connected | see "Vehicle link" below | |
| `ros`: topic not visible | see "ROS topics invisible" | |
| `ros`: topic visible but nothing received | `ros2 topic info -v <imu topic>` (QoS) | NAVERA subscribes BEST_EFFORT and receives both kinds of publishers since this release; an older install subscribed RELIABLE and received nothing from BEST_EFFORT drivers: update |
| `box`: `NAVERA_BOX_IMU=0` — `no box IMU found at boot (NAVERA_BOX_IMU=0): IMU service idle` | `cat /var/lib/navera/discovered.env`; `sudo i2cdetect -y -r 1` | the BNO085 did not answer at boot: wiring, then `sudo systemctl restart navera-discover navera-imu` |
| Frozen relay: the source repeats the same attitude | `ros2 topic echo <imu topic>` | fix the source |

### Wrong heading (frames turned, night positions off, heading check fails)

| Cause | Check | Fix |
|---|---|---|
| `ros`: the vehicle's IMU gives a **magnetic** or arbitrary yaw | `heading_deg` in `frame_meta` vs a known direction | NAVERA expects ENU with yaw from true north from a ROS IMU (deploy/README.md §6): fix it at the source |
| `box`: no position yet and no `NAVERA_DECLINATION_DEG` | IMU log | the heading is magnetic until the first position; set the declination |

---

## GPS and position

### No GPS fix / no prior

Day vision: `[day] ✗ frame=12 no position: no position prior (waiting for a GPS fix);
whole-map search disabled — not reliable`. `check_box`: `WARN GPS — nothing received (no
receiver, or no fix yet)`.

NAVERA needs **one GPS fix at start, in every mode**: the first position is the prior vision
searches around (whole-map search is disabled because it is not reliable).

| Cause | Check | Fix |
|---|---|---|
| No GPS found at boot — `no GPS found or configured (NAVERA_GPS_SOURCE=none): GPS idle` | `check_box.py` first lines ("GPS: none — NO GPS found …"); `cat /var/lib/navera/discovery.json` | connect / power the receiver: navera-hotplug fills the idle GPS within seconds (a new port), or within `NAVERA_HOTPLUG_RESCAN_S` (60 s: a port or CAN bus already there) — vehicle **disarmed** when NAVERA has an autopilot link (`journalctl -u navera-hotplug`: "not switched to: the vehicle is armed"); or `sudo systemctl restart navera-discover navera-gps`; or write `NAVERA_GPS_SOURCE` and its port. A port that sends NMEA without satellite data (GSV/GSA) is not taken as a receiver ("an autopilot's NMEA output?") |
| DroneCAN GPS not found — "can0 is down", "a DroneCAN device asks for a node id and nothing gives one", "pydronecan is not installed" | `ip -details link show can0`; `check_box.py` | bring the bus up (deploy/README.md, CAN bus; needs root); a GPS alone on NAVERA's CAN: `NAVERA_GPS_CAN_ALLOCATE=1`; `pip3 install --user dronecan` |
| u-blox "UBX without NAV-PVT" (u-blox 6, or NAV-PVT off) | discovery report | use its NMEA output, or `NAVERA_GPS_CONFIGURE=1` on a receiver NAVERA owns (u-blox 7+) |
| `vehicle_gps1`: `autopilot's first GPS NOT read: GPS1 is fed over MAVLink (type 14)` | `check_box.py`; `GPS_TYPE` on the autopilot | NAVERA feeds GPS 1: use wiring B (`vehicle`, the real GPS as GPS 2) — NAVERA never reads its own output |
| No GPS at all in the area | — | `/mission` → "Start without GPS" gives day vision a search area (deploy/README.md §8) |
| `serial`: receiver has no fix yet — `No fix (qual=0)` | `journalctl -u navera-gps -n 20` | clear sky view, wait for the fix |
| `serial`: wrong port / baud, port missing — `Serial error: … — exiting so the service restarts`, or the unit restarting every 10 s | `ls -l /dev/ttyTHS1`; `NAVERA_GPS_PORT`, `NAVERA_GPS_BAUD` | correct port and baud; the user needs `dialout` |
| `vehicle`: the autopilot has no second GPS, or it has no 3D fix | `ros2 topic echo /navera/vehicle/gps2 --once`; vehicle link status | configure the real receiver as the autopilot's GPS 2 (ARDUPILOT_INTEGRATION.md §7) |
| `vehicle` not chosen by discovery: "the autopilot's second GPS is fed over MAVLink — NAVERA's own output: never used" or "… types could not be read" | `GPS_TYPE2` / `GPS2_TYPE` on the autopilot | type 14 is NAVERA's own feed (a loop): the second GPS must be a real receiver |
| `ros`: `NAVERA_GPS_SOURCE=ros needs NAVERA_ROS_GPS_TOPIC` | `journalctl -u navera-gps` | set `NAVERA_ROS_GPS_TOPIC` |
| `ros`: topic not visible | see "ROS topics invisible" | |
| `NAVERA_GPS_SOURCE=…: expected serial, network, dronecan, vehicle, vehicle_gps1 or ros` | spelling | fix the value |

### GPS always DEGRADED ("uncertainty unknown")

The GPS is used, but `nav_status` says `GPS fix, uncertainty unknown` and it is not sent to
the autopilot as a fix. NAVERA counts an accuracy only with a defined covariance type and a
sigma of at least 1 cm. Typical with `ros` (a NavSatFix without covariance, or all zeros)
and `vehicle` (an autopilot that sends no `h_acc` in `GPS2_RAW`). Fix it at the source:
publish the receiver's covariance. A covariance that is not symmetric / positive
semi-definite is refused entirely (`non-finite position or covariance`).

### GPS refused by NAVERA

`GPS refused: implausible jump 2400 m in 1.0 s (max 150 m at 100 m/s) — possible spoofing`,
`GPS refused: GPS drifting away from day vision: …`, `GPS refused: 240 m from day vision
(3 sigma 90 m)`. The arbiter refuses a GPS the vehicle could not have reached, or one that
disagrees with day vision; it is re-accepted when 2 independent fixes agree with it within
3 σ (`GPS confirmed by … (2 fixes) — re-accepted`). Before refusing a drifting GPS it shows
it **in doubt**: `… — GPS IN DOUBT: day vision disagrees by 104 m (possible slow spoofing)`,
DEGRADED, its accuracy no better than the gap. Check that `NAVERA_MAX_SPEED_KMH` is right
for the vehicle (too low refuses real movement). A fix arriving out of order is dropped
(`GPS fix older than the last one received: dropped`, information only). See
ARCHITECTURE.md §3.

### Day vision always "no position"

Frame reasons in the journal of `navera-pipeline-day` (`[day] ✗ frame=… no position: …`) and
`ros2 topic echo /day/day_status`.

| Reason | Cause | Fix |
|---|---|---|
| `no map tiles (or no texture) in the search circle` | the route's map is not generated/activated, or the vehicle is outside it | page `/mission`: Generate the route map, then Activate it. `check_box`: `FAIL satellite map of the route — not prepared (page /mission: Generate, Activate)` |
| `too few features in the frame (uniform ground, blur, darkness)` | over sea, desert, uniform fields; motion blur; night | known limitation: day vision is unreliable over uniform terrain (VALIDATION_STATUS.md) |
| `too few features …` over long stretches of sea / uniform ground | no landmarks (the `/mission` terrain warning) | NAVERA carries on dead-reckoning (PROPAGATED, accuracy growing) for up to 120 s / 500 m, then gives no position: route over textured ground |
| `dead-reckoning uncertainty 5xx m > 500 m` / `dead-reckoning limit 120s reached` | no map match for ~40 s: the carried position's honest accuracy (it grows with the square of the time since the last match: unseen acceleration) passed the limit | intended — the position is withdrawn instead of going on with a wrong small accuracy (the simulator's drone flew away at 17 m/s on one stated ±244 m after 100 s, 1200 m real). Fix the cause of the missing matches: `camera tilted 48 deg from vertical (max 45)` = the vehicle leans over 45° at speed; `fitted scale …` = wrong height |
| `velocity unknown (too few measured fixes), cannot dead-reckon` | fewer than 3 measured fixes over 4 s, or a gap of more than 5 s between them, and no carried velocity to continue with | normally transient (after GPS loss, a new match restores it); long stretches: matches too rare to dead-reckon, see the rows above |
| `frame altitude unknown or on the ground` | no height above ground yet (on the ground, or no GPS / rangefinder / barometer) | normal on the ground; in flight check the altitude source in `frame_meta` |
| `camera_hfov_deg unknown` | replay frames without `NAVERA_DAY_HFOV_DEG` | set it (live frames carry their own field of view) |
| `fitted scale 0.62 ≠ 1 expected from the altitude (±15%): wrong place` | a false match rejected (normal now and then); if constant, a wrong height above ground (hills, wrong ground altitude) | if constant: set `NAVERA_GROUND_ALTITUDE_M`, or use a rangefinder (`vehicle` source) |
| `no attitude …` / `camera tilted …` | see Camera above | |
| `DAY_DATASET_DIR=… does not exist (data disk not mounted?)` (pipeline restarting) | data disk not mounted, or map path wrong | mount the disk; regenerate/activate the map |

While GPS is valid, day vision is idle (`GPS valid — vision idle, tracking GPS as prior`)
except for a check every 2 s, unless `NAVERA_SHADOW_MODE=true`.

---

## Output to the autopilot

### Nothing sent to the autopilot without GPS

`output → no fix (degraded position not forwarded (forward_degraded=false))` in
`journalctl -u navera-output`. (A ROS consumer of `/navera/fix` does get vision positions
by default, `NAVERA_ROS_FORWARD_DEGRADED`.)

Vision and celestial positions are DEGRADED, and DEGRADED positions are not sent unless
enabled. Fix (only with a measured accuracy): `NAVERA_FORWARD_DEGRADED=true` and
`NAVERA_DEGRADED_SIGMA_M=<metres>` in `/etc/navera/navera.env`, then
`sudo systemctl restart navera-output`. Other reasons in the same log line:

| Message | Meaning |
|---|---|
| `forward_degraded requires degraded_sigma_m > 0: the accuracy sent to the vehicle must be stated, not invented` (service restarting) | forwarding enabled without `NAVERA_DEGRADED_SIGMA_M` |
| `degraded_sigma_m 2000 m > max_forward_sigma_m 1000 m: nothing would ever be forwarded` (service restarting) | `NAVERA_DEGRADED_SIGMA_M` above 1000 m |
| `NAVERA_FORWARD_DEGRADED='enabled': expected true or false` (launch stops) | only true / false (1/0, yes/no, on/off) are accepted, also for `NAVERA_NMEA_FORWARD_DEGRADED` and `NAVERA_ROS_FORWARD_DEGRADED` |
| `degraded position not sent over NMEA (no accuracy field)` | intended: NMEA carries no accuracy; forward over MAVLink |
| `degraded position with no stated accuracy` | the source states none and no `NAVERA_DEGRADED_SIGMA_M` is set (ROS output) |
| `position measured 5.4 s ago (max 5.0 s)` | the position is older than `NAVERA_MAX_MEASUREMENT_AGE_S` (slow vision, loaded CPU) |
| `MAVLink output goes to navera-vehicle-link's relay, but no vehicle link is connected to an autopilot: the autopilot receives NOTHING from NAVERA …` (every 30 s) | `NAVERA_MAVLINK_URL=udpout:127.0.0.1:…` and `navera-vehicle-link` not enabled, idle, or not connected: see "Vehicle link" below |
| `position too coarse for the autopilot (±55.0 km > 1.0 km)` | celestial fix: never forwarded |
| `no new position for 2.6 s: bridging along the last one (at most 10 s)` | the vision positions stopped; the last one is carried along its velocity and re-sent about once a second, its accuracy growing (`bridge_max_s`) |
| `output → no fix (reacquiring after a gap: waiting for a velocity of the new fixes …)` | after 5 s without a position sent, vision positions wait until their own velocity is known (±8 m/s, ~7 good fixes): the autopilot resets its velocity onto the first one (`reacquire_after_s`, F28). Normal for 5–20 s after a gap |
| Copter: "GPS Glitch or Compass error" when vision takes over | EKF3's `gps_glitching` status: NAVERA states its vision velocity accuracy (> 1.5 m/s). A status, not a failsafe (docs/ARDUPILOT_INTEGRATION.md §3) |
| `bridge ended: gap of 11 s longer than the bridge (10 s)` / `bridged position too coarse (…)` | the gap outlasted the bridge: "no fix" from here, the autopilot's own failsafe acts (Copter SITL: LAND ~8 s after the last position). Find why vision stopped: the day log (`day: invalid (… velocity unknown …` / `dead-reckoning uncertainty 5xx m > 500 m`) |
| `arbiter silent` | `navera-estimator` not running or not visible (domain) |
| `output failed: … — exiting so the service restarts` | serial port unplugged / network error |
| `MAVLink address '…': expected serial:/dev/<port>:<baud>, udpin:<ip>:<port>, udpout:<ip>:<port> or tcp:<ip>:<port>` | malformed `NAVERA_MAVLINK_URL` |

### Autopilot reports "GPS glitch", "EKF variance", "GPS not healthy", or fails safe

| Cause | Check | Fix |
|---|---|---|
| The autopilot fuses a stale GPS velocity after GPS loss (vision sends none) | `EK3_SRC1_VELXY`, `EK3_SRC1_VELZ` | set both to 0 (ARDUPILOT_INTEGRATION.md §3) |
| Stated accuracy too optimistic: the EKF rejects positions that jump more than it was told | `NAVERA_DEGRADED_SIGMA_M` vs your measured error | state the measured value (simulation: ±300 m stated for a 351 m median error → EKF failsafe in 45 s). Above 100 m ArduPilot uses 100 m anyway (ARDUPILOT_INTEGRATION.md §3) |
| Vision forwarded over NMEA (`NAVERA_NMEA_FORWARD_DEGRADED=true`) | navera.env | NMEA has no accuracy: the autopilot trusts it as a ~0.5 m GPS — turn it off, use MAVLink |
| PX4: no GPS on the ground station although NAVERA has a fix | discovery report (`check_box.py`): CHECK PX4 … lines; `journalctl -u navera-output \| grep HIL_GPS` | PX4 reads NAVERA only as `HIL_GPS` with `MAV_USEHILGPS = 1`, from its own system id (`NAVERA_MAVLINK_SYSID`), and needs `EKF2_GPS_CTRL 1`, `EKF2_HGT_REF 0`, `EKF2_GPS_CHECK 240` (PX4_INTEGRATION.md §2); `NAVERA_MAVLINK_MESSAGE=gps_input` is ignored by PX4 |
| Vision gaps over uniform terrain (no position for seconds) | `/day/day_status` reasons | route over textured ground; this is a known limitation |
| Latency not compensated | `GPS_DELAY_MS`; `sensor_stamp` vs `header.stamp` in `/navera/position` | ARDUPILOT_INTEGRATION.md §5 |
| No real GPS fix at power-on (origin not set; arming refused) | GCS messages | power on with GPS, or send `SET_GPS_GLOBAL_ORIGIN` |
| With forwarding: arming checks requiring satellites (vision reports 0) | GCS pre-arm messages | adapt the arming checks knowingly |

---

## Vehicle link: no heartbeat

`no heartbeat from an autopilot on serial:/dev/ttyTHS2:921600 — retrying`, or
`vehicle link: autopilot silent for 5 s — reconnecting`; `check_box`: `FAIL vehicle link — no
/navera/vehicle/status (navera-vehicle-link service?)`.

| Cause | Check | Fix |
|---|---|---|
| `no autopilot found or configured (NAVERA_VEHICLE_MAVLINK_URL): vehicle link idle` | journal; `check_box.py` discovery lines | connect the autopilot and `sudo systemctl restart navera-discover navera-vehicle-link`, or set `NAVERA_VEHICLE_MAVLINK_URL` |
| Wrong port or baud | `SERIALn_BAUD` on the autopilot = the baud in the URL; `ls -l /dev/ttyTHS*` | match them |
| TX/RX not crossed, no common ground | wiring | TX→RX, RX→TX, GND–GND (ARDUPILOT_INTEGRATION.md §2) |
| The autopilot port is not MAVLink | `SERIALn_PROTOCOL` | 2 (MAVLink 2) |
| The port is already used by `navera-output` (`check_box`: `FAIL serial ports — … is used by NAVERA_MAVLINK_URL, NAVERA_VEHICLE_MAVLINK_URL`) | both URLs point to the same device | one autopilot port: `NAVERA_MAVLINK_URL=udpout:127.0.0.1:14650` (the vehicle link relays it); or two ports; or mavlink-router |
| Several autopilots answer (`CHECK several autopilots answer …`) | discovery report | the wired port is used; set `NAVERA_VEHICLE_MAVLINK_URL` to choose |
| Only a ground station (or another companion) heartbeats on that link | — | vehicle_link deliberately ignores non-autopilot heartbeats: connect it to the autopilot itself |

---

## Web interface

### "Apply", "Activate" or "Generate" refused

| Message | Cause | Fix |
|---|---|---|
| `refused: the vehicle is armed: disarm it before changing NAVERA` | armed (from `navera-vehicle-link`) | disarm, then apply |
| `refused: the vehicle is moving (N m/s): stop it before changing NAVERA` | NAVERA's own positions move faster than 1.5 m/s (no autopilot link needed) | stop the vehicle |
| `refused: NAVERA is navigating without GPS right now: a restart would interrupt it` (or, for Generate, `… generating a map would take the processor vision needs`) | `nav_status` is DEGRADED | wait for GPS, or apply on the ground |
| `control disabled: set NAVERA_WEB_TOKEN` | no token configured: read-only | set `NAVERA_WEB_TOKEN`, `sudo systemctl restart navera-web` |
| `missing or wrong X-Navera-Token` | wrong code typed | use the token from `/etc/navera/navera.env` |
| `too many wrong codes from this address: wait N s` (HTTP 429) | 5 wrong codes within 60 s | wait 60 s, then use the right code |
| `restart refused: sudo: …` / `map selected, but the day pipeline could not be restarted (…) — restart the box` | sudoers file missing or altered | `sudo install -m 0440 deploy/sudoers/navera-web /etc/sudoers.d/navera-web && sudo visudo -c` |
| `NAVERA_CAMERA_DEVICE: not a setting of the web page` | the page only sets vehicle settings | camera, sources and outputs are edited in `/etc/navera/navera.env` |

Saving settings is allowed in flight; they take effect at the next "Apply".

---

## Services restarting in a loop

`systemctl status navera-<unit>` shows "activating (auto-restart)"; the journal shows why.

| Message | Fix |
|---|---|
| `[navera-boot] workspace /home/navera/isaac_ros_common not found` | the code must be at that path (deploy/README.md §3.2) |
| `[navera-boot] NAVERA_MBTILES is not set (see /etc/navera/navera.env)` / `… does not exist (data disk not mounted?)` | set the path / mount the data disk (the unit retries every 10 s) |
| `could not convert string to float: ''` (launch error) | a numeric setting is present but empty (`NAVERA_DAY_HFOV_DEG=`, `NAVERA_THERMAL_HFOV_DEG=`, `NAVERA_STAR_CAMERA_…=`): comment it out or give a value |
| `NAVERA_MAX_SPEED_KMH=5000 km/h is outside 4-1890 km/h` | fix the value |
| `NAVERA_SENSOR_SOURCE=ros needs NAVERA_ROS_IMU_TOPIC (the vehicle's attitude)` | set the topic |
| `ModuleNotFoundError: No module named '…'` | Python packages installed for another user: install them for `navera` (deploy/README.md §3.3) |
| `forward_degraded requires degraded_sigma_m > 0 …` | see "Nothing sent to the autopilot" |

A unit that keeps restarting while its hardware is absent (GPS port, camera) is the intended
behaviour: it comes back by itself 10 s after the hardware does. Units whose hardware was
not found at boot stay **idle** instead (active, logging why): `navera-gps`
(`NAVERA_GPS_SOURCE=none`), `navera-imu` / `navera-rtc` (`NAVERA_BOX_IMU=0` /
`NAVERA_BOX_RTC=0`), `navera-vehicle-link` (no URL). After connecting the hardware:
`sudo systemctl restart navera-discover` and the unit.

---

## ROS topics invisible

`ros2 topic list` shows only `/parameter_events` and `/rosout`; `check_box` FAILs every topic;
the vehicle's computer does not see `/navera/fix`, or NAVERA does not see the vehicle's topics.

| Cause | Check | Fix |
|---|---|---|
| The shell does not have the services' environment (different `ROS_DOMAIN_ID`) | `echo $ROS_DOMAIN_ID $ROS_LOCALHOST_ONLY` | open the NAVERA shell (top of this page) |
| `ROS_LOCALHOST_ONLY=1`: NAVERA's DDS stays on the box (template default); `check_box`: `FAIL ROS network` | navera.env | for a ROS vehicle: `ROS_LOCALHOST_ONLY=0` and the vehicle's `ROS_DOMAIN_ID` (a number), then restart all NAVERA units (deploy/README.md §6) |
| Different domain id on the vehicle | `echo $ROS_DOMAIN_ID` on both machines | same id |
| Different ROS 2 distribution or RMW on the vehicle | `echo $RMW_IMPLEMENTATION` on both | align them |

## Automatic detection (navera-discover)

| Symptom | Check | Fix |
|---|---|---|
| A sensor / autopilot / camera is not used | `navera_tools/check_box.py` (first lines) or `cat /var/lib/navera/discovery.json`; `journalctl -b -u navera-discover` | connected after boot: `sudo systemctl restart navera-discover` then the units concerned; else impose it in `navera.env` instead of `auto` |
| "is held by another program: not probed" | `fuser <port>` | another program opened the port at boot (modem manager, a console on `ttyTHS0`): stop it, or impose the source |
| Autopilot not found on a serial port | its telemetry port must send MAVLink (ArduPilot `SERIALn_PROTOCOL=2`) at a standard baud | or set `NAVERA_DISCOVER_MAVLINK=serial:/dev/ttyXXX:921600` / `NAVERA_VEHICLE_MAVLINK_URL` |
| ROS vehicle not found | `ros2 topic list` with the vehicle's `ROS_DOMAIN_ID` and `ROS_LOCALHOST_ONLY=0` | add its domain to `NAVERA_DISCOVER_ROS_DOMAINS`; check the network (same subnet, multicast allowed). Its computer booted after NAVERA: discovery runs once per boot — write its sources and domain in navera.env, or restart navera-discover then the units |
| `CHECK a ROS vehicle is on domain N, NAVERA is on domain 42 (loopback only) as written in navera.env: not used` | navera.env | written network settings are never changed: write `ROS_DOMAIN_ID=N` and `ROS_LOCALHOST_ONLY=0` — or `ROS_DOMAIN_ID=auto` (navera-discover then joins the domain it found at boot through `discovered.env`; verified by unit tests only, not yet on a real vehicle network: deploy/README.md §6) |
| `CHECK several GPS receivers` / `CHECK several cameras` | discovery report | set `NAVERA_GPS_PORT` / `NAVERA_CAMERA_DEVICE` |
| ROS camera chosen but it looks forward | discovery cannot know a camera's direction | fit NAVERA's downward camera (found first), or impose `NAVERA_CAMERA_INPUT` |

