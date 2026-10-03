# NAVERA — Troubleshooting

Symptom → cause → check → fix. Messages in `monospace` are the exact log or web messages
(numbers and names vary).

**Where to look.** Each service logs to the journal: `journalctl -u <unit> -n 100` or
`-f` to follow (units: `navera-estimator`, `navera-gps`, `navera-imu`, `navera-rtc`,
`navera-pipeline-day|night|cn`, `navera-output`, `navera-vehicle-link`, `navera-web`).
`check` commands without `sudo` run in the **NAVERA shell** — the services' environment:

```bash
sudo -u navera -H bash
source /opt/ros/humble/setup.bash
source /home/navera/isaac_ros_common/install/setup.bash
set -a; . /etc/navera/navera.env; . /var/lib/navera/settings.env 2>/dev/null; set +a
cd /home/navera/isaac_ros_common
```

The quickest overall check is `python3 navera_tools/check_box.py` (PASS / WARN / FAIL per
item; add `--camera`, with the pipeline stopped, to open the camera itself).

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
| Frozen relay: the source repeats the same attitude | `ros2 topic echo <imu topic>` | fix the source |

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
| `serial`: receiver has no fix yet — `No fix (qual=0)` | `journalctl -u navera-gps -n 20` | clear sky view, wait for the fix |
| `serial`: wrong port / baud, port missing — `Serial error: … — exiting so the service restarts`, or the unit restarting every 10 s | `ls -l /dev/ttyTHS1`; `NAVERA_GPS_PORT`, `NAVERA_GPS_BAUD` | correct port and baud; the user needs `dialout` |
| `vehicle`: the autopilot has no second GPS, or it has no 3D fix | `ros2 topic echo /navera/vehicle/gps2 --once`; vehicle link status | configure the real receiver as the autopilot's GPS 2 (ARDUPILOT_INTEGRATION.md §7) |
| `ros`: `NAVERA_GPS_SOURCE=ros needs NAVERA_ROS_GPS_TOPIC` | `journalctl -u navera-gps` | set `NAVERA_ROS_GPS_TOPIC` |
| `ros`: topic not visible | see "ROS topics invisible" | |
| `NAVERA_GPS_SOURCE=…: expected serial, vehicle or ros` | spelling | fix the value |

### GPS refused by NAVERA

`GPS refused: implausible jump 2400 m in 1.0 s (max 150 m at 100 m/s) — possible spoofing`,
`GPS refused: GPS drifting away from day vision: …`. The arbiter refuses a GPS the vehicle
could not have reached, or one that disagrees with day vision; it is re-accepted when it
agrees again with an independent fix (`GPS confirmed by … — re-accepted`). Check that
`NAVERA_MAX_SPEED_KMH` is right for the vehicle (too low refuses real movement). See
ARCHITECTURE.md §3.

### Day vision always "no position"

Frame reasons in the journal of `navera-pipeline-day` (`[day] ✗ frame=… no position: …`) and
`ros2 topic echo /day/day_status`.

| Reason | Cause | Fix |
|---|---|---|
| `no map tiles (or no texture) in the search circle` | the route's map is not generated/activated, or the vehicle is outside it | page `/mission`: Generate the route map, then Activate it. `check_box`: `FAIL satellite map of the route — not prepared (page /mission: Generate, Activate)` |
| `too few features in the frame (uniform ground, blur, darkness)` | over sea, desert, uniform fields; motion blur; night | known limitation: day vision is unreliable over uniform terrain (VALIDATION_STATUS.md) |
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
`journalctl -u navera-output`.

Vision and celestial positions are DEGRADED, and DEGRADED positions are not sent unless
enabled. Fix (only with a measured accuracy): `NAVERA_FORWARD_DEGRADED=true` and
`NAVERA_DEGRADED_SIGMA_M=<metres>` in `/etc/navera/navera.env`, then
`sudo systemctl restart navera-output`. Other reasons in the same log line:

| Message | Meaning |
|---|---|
| `forward_degraded requires degraded_sigma_m > 0: the accuracy sent to the vehicle must be stated, not invented` (service restarting) | forwarding enabled without `NAVERA_DEGRADED_SIGMA_M` |
| `position measured 2.4 s ago (max 2.0 s)` | the position is older than `NAVERA_MAX_MEASUREMENT_AGE_S` (slow vision, loaded CPU) |
| `position too coarse for the autopilot (±55.0 km > 1.0 km)` | celestial fix: never forwarded |
| `arbiter silent` | `navera-estimator` not running or not visible (domain) |
| `output failed: … — exiting so the service restarts` | serial port unplugged / network error |
| `MAVLink address '…': expected serial:/dev/<port>:<baud>, udpin:<ip>:<port>, udpout:<ip>:<port> or tcp:<ip>:<port>` | malformed `NAVERA_MAVLINK_URL` |

### Autopilot reports "GPS glitch", "EKF variance", "GPS not healthy", or fails safe

| Cause | Check | Fix |
|---|---|---|
| The autopilot fuses a stale GPS velocity after GPS loss (vision sends none) | `EK3_SRC1_VELXY`, `EK3_SRC1_VELZ` | set both to 0 (ARDUPILOT_INTEGRATION.md §3) |
| Stated accuracy too optimistic: the EKF rejects positions that jump more than it was told | `NAVERA_DEGRADED_SIGMA_M` vs your measured error | state the measured value (simulation: ±300 m stated for a 351 m median error → EKF failsafe in 45 s) |
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
| `NAVERA_VEHICLE_MAVLINK_URL is not set (see /etc/navera/navera.env)` | journal | set it |
| Wrong port or baud | `SERIALn_BAUD` on the autopilot = the baud in the URL; `ls -l /dev/ttyTHS*` | match them |
| TX/RX not crossed, no common ground | wiring | TX→RX, RX→TX, GND–GND (ARDUPILOT_INTEGRATION.md §2) |
| The autopilot port is not MAVLink | `SERIALn_PROTOCOL` | 2 (MAVLink 2) |
| The port is already used by `navera-output` | both URLs point to the same device | one port per connection, or mavlink-router |
| Only a ground station (or another companion) heartbeats on that link | — | vehicle_link deliberately ignores non-autopilot heartbeats: connect it to the autopilot itself |

---

## Web interface

### "Apply", "Activate" or "Generate" refused

| Message | Cause | Fix |
|---|---|---|
| `refused: the vehicle is armed: disarm it before changing NAVERA` | armed (from `navera-vehicle-link`) | disarm, then apply |
| `refused: NAVERA is navigating without GPS right now: a restart would interrupt it` | `nav_status` is DEGRADED | wait for GPS, or apply on the ground |
| `control disabled: set NAVERA_WEB_TOKEN` | no token configured: read-only | set `NAVERA_WEB_TOKEN`, `sudo systemctl restart navera-web` |
| `missing or wrong X-Navera-Token` | wrong code typed | use the token from `/etc/navera/navera.env` |
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
behaviour: it comes back by itself 10 s after the hardware does.

---

## ROS topics invisible

`ros2 topic list` shows only `/parameter_events` and `/rosout`; `check_box` FAILs every topic;
the vehicle's computer does not see `/navera/fix`, or NAVERA does not see the vehicle's topics.

| Cause | Check | Fix |
|---|---|---|
| The shell does not have the services' environment (different `ROS_DOMAIN_ID`) | `echo $ROS_DOMAIN_ID $ROS_LOCALHOST_ONLY` | open the NAVERA shell (top of this page) |
| `ROS_LOCALHOST_ONLY=1`: NAVERA's DDS stays on the box (template default) | navera.env | for a ROS vehicle: `ROS_LOCALHOST_ONLY=0` and the vehicle's `ROS_DOMAIN_ID`, then restart all NAVERA units (deploy/README.md §6) |
| Different domain id on the vehicle | `echo $ROS_DOMAIN_ID` on both machines | same id |
| Different ROS 2 distribution or RMW on the vehicle | `echo $RMW_IMPLEMENTATION` on both | align them |

## Automatic detection (navera-discover)

| Symptom | Check | Fix |
|---|---|---|
| A sensor / autopilot / camera is not used | `navera_tools/check_box.py` (first lines) or `cat /var/lib/navera/discovery.json`; `journalctl -b -u navera-discover` | connected after boot: `sudo systemctl restart navera-discover` then the units concerned; else impose it in `navera.env` instead of `auto` |
| "is held by another program: not probed" | `fuser <port>` | another program opened the port at boot (modem manager, a console on `ttyTHS0`): stop it, or impose the source |
| Autopilot not found on a serial port | its telemetry port must send MAVLink (ArduPilot `SERIALn_PROTOCOL=2`) at a standard baud | or set `NAVERA_DISCOVER_MAVLINK=serial:/dev/ttyXXX:921600` / `NAVERA_VEHICLE_MAVLINK_URL` |
| ROS vehicle not found | `ros2 topic list` with the vehicle's `ROS_DOMAIN_ID` and `ROS_LOCALHOST_ONLY=0` | add its domain to `NAVERA_DISCOVER_ROS_DOMAINS`; check the network (same subnet, multicast allowed) |
| ROS camera chosen but it looks forward | discovery cannot know a camera's direction | fit NAVERA's downward camera (found first), or impose `NAVERA_CAMERA_INPUT` |

