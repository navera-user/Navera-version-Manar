# NAVERA — first real test: procedure

Goal of the first campaign: **record** camera, attitude, GPS and NAVERA's decisions
together, so that every accuracy figure can be measured on real data
(`docs/VALIDATION_STATUS.md` holds only bench, replay and simulation figures today).
GPS stays valid and in charge during the recording flights; vision runs in *shadow
mode* beside it. A GPS-denied flight comes only after the recordings show vision
working (step 8).

Prerequisite: the box is installed as described in [deploy/README.md](../deploy/README.md)
(workspace `/home/navera/isaac_ros_common`, services installed, `/etc/navera/navera.env`,
the data disk mounted on `/data` with the map — deploy/README.md §3.10).

## 0. The NAVERA shell

Every command below that is not prefixed with `sudo` is run in a shell that has the same
environment as the services. Open it with:

```bash
sudo -u navera -H bash
source /opt/ros/humble/setup.bash
source /home/navera/isaac_ros_common/install/setup.bash
set -a; . /etc/navera/navera.env; . /var/lib/navera/settings.env 2>/dev/null; . /var/lib/navera/discovered.env 2>/dev/null; set +a
cd /home/navera/isaac_ros_common
```

Commands prefixed with `sudo` (including `sudoedit`) are run from your administrator account (the `navera` user
has no sudo rights). Recordings go on the data disk:

```bash
sudo install -d -o navera -g navera /data/navera/rec
```

## 1. Hardware

| Item | Setting |
|---|---|
| Camera | Insta360 ONE R in **USB webcam mode** — the **4K wide-angle module**, or the **360 module** (two lenses in one 1920x1080 picture, top / bottom halves 1920x540: point one lens straight down and set `NAVERA_CAMERA_CROP=top` or `bottom` for it; calibrate with the same `--crop`; its straightened view is 111° x ~37°, so at 100 m it sees ~290 x 80 m — bench results were at ~520 m equivalent). Address it by its stable name `/dev/v4l/by-id/usb-…-video-index0` (`ls -l /dev/v4l/by-id/`), not `/dev/videoN` |
| Mount, multirotor | **on a gimbal** holding it straight down (`NAVERA_CAMERA_GIMBAL=true`). A fixed camera leans with the drone: 45° at speed in simulation, the limit (`NAVERA_CAMERA_MAX_TILT_DEG`, default 45) |
| Mount, plane / boat / robot | fixed, looking straight down, image top towards the nose (`NAVERA_CAMERA_MOUNT_RPY=0,0,0`; otherwise measure and enter the angles). A fixed camera's frames taken while the vehicle rotates faster than `NAVERA_CAMERA_MAX_RATE_DPS` (30°/s) are not used: fly smooth turns on the recording legs |
| IMU | BNO085 on I²C bus 1 (0x4A), rigidly fixed. Mounting angles: `NAVERA_IMU_MOUNT_RPY` (roll,pitch,yaw in degrees) in `/etc/navera/navera.env` or on the `/mission` page |
| GPS | Neo-M8N on `/dev/ttyTHS1`, 9600 baud (`NAVERA_GPS_SOURCE=serial`), antenna with a clear sky view, away from the Jetson |
| Clock | DS3231 on I²C bus 1 (0x68), backup cell fitted |
| Vehicle link (if used) | one autopilot port, owned by `navera-vehicle-link` (`NAVERA_VEHICLE_MAVLINK_URL`), which relays NAVERA's GPS output (`NAVERA_MAVLINK_URL=udpout:127.0.0.1:14650` — what navera-discover sets up); or two ports; or mavlink-router — see [ARDUPILOT_INTEGRATION.md](ARDUPILOT_INTEGRATION.md). PX4: [PX4_INTEGRATION.md](PX4_INTEGRATION.md) (not tested; no MAVLink output) |

## 2. Lens calibration (once per camera and resolution)

1. Print a 9×6 (inner corners) checkerboard, measure one square, stick it on a rigid board.
2. Stop the pipeline (it holds the camera), then calibrate as the service user:
   ```bash
   sudo systemctl stop navera-pipeline-day
   ```
   In the NAVERA shell:
   ```bash
   python3 navera_tools/calibrate_camera.py \
       --device /dev/v4l/by-id/usb-<maker>_<model>_<serial>-video-index0 --size 1920x1080 \
       --board 9x6 --square-mm <measured> --out /home/navera/camera.yaml
   ```
3. Show the board at 30 positions (the default `--views`): corners and edges of the image,
   tilted up to ~45°, near and far.
4. Accept when the tool reports RMS < 0.5 px ("good"; 0.5–1 px is "usable", above 1 px
   redo it). Install the file and point NAVERA at it:
   ```bash
   sudo install -m 0644 /home/navera/camera.yaml /etc/navera/camera.yaml
   sudoedit /etc/navera/navera.env      # NAVERA_CAMERA_CALIBRATION=/etc/navera/camera.yaml
   sudo systemctl start navera-pipeline-day
   ```

The file records the camera's `/dev/v4l/by-id` name: the live camera refuses it with
another camera ("calibrate this camera"), and refuses it at another resolution than
`NAVERA_CAMERA_SIZE`. The tool recovers a known lens to 0.1 % in focal length and 0.1° in
field of view (`navera_tools/tests/test_calibrate_camera.py`).

## 3. Settings

The camera and sensor settings are edited in `/etc/navera/navera.env`
(`sudoedit /etc/navera/navera.env`) — the `/mission` page does **not** set them:

```
NAVERA_CAMERA=live
NAVERA_CAMERA_INPUT=usb
NAVERA_CAMERA_DEVICE=/dev/v4l/by-id/usb-<maker>_<model>_<serial>-video-index0
NAVERA_CAMERA_SIZE=1920x1080
NAVERA_CAMERA_CALIBRATION=/etc/navera/camera.yaml
NAVERA_CAMERA_GIMBAL=true            # multirotor
NAVERA_SENSOR_SOURCE=box             # or vehicle (+ NAVERA_VEHICLE_MAVLINK_URL), or ros (+ NAVERA_ROS_IMU_TOPIC)
NAVERA_GPS_SOURCE=serial             # or vehicle (autopilot's 2nd GPS), or ros (+ NAVERA_ROS_GPS_TOPIC)
NAVERA_GROUND_ALTITUDE_M=<site elevation above the WGS84 ellipsoid, if known>
```

(Writing the sources, as above, makes the test independent of what navera-discover finds;
`auto` also works — check its choices in the first lines of `check_box.py`.)

The vehicle settings can be set either there or on the `/mission` page (port 8181):
`NAVERA_MAX_SPEED_KMH=<cruise + 50 %>`, `NAVERA_VEHICLE_TYPE`, `NAVERA_IMU_MOUNT_RPY`,
`NAVERA_DECLINATION_DEG`. Then restart every NAVERA unit you have enabled (one command:
systemd runs navera-discover first; drop the units you have not enabled):

```bash
sudo systemctl restart navera-discover navera-estimator navera-gps navera-imu navera-rtc \
    navera-vehicle-link navera-pipeline-day navera-output navera-web
```

Whatever the sources, NAVERA needs a GPS fix when the test starts: it is the first
position day vision searches around. (Where there is no GPS at all, the `/mission` page's
"Start without GPS" gives day vision a search area instead — not needed for these tests.)

## 4. Map of the test area

Page `/mission` (`http://<jetson-ip>:8181/mission`, with the control token): import the
autopilot's mission file (or click the route), **Generate the map**, then **Activate this
map**. Day vision only matches against the activated map: without it, it reports no
position. Generating and activating are refused while the vehicle is armed, moving
(faster than 1.5 m/s) or NAVERA is navigating without GPS — prepare on the ground. Outside
the delivered Sousse map, tiles must come from `NAVERA_TILE_URL` (internet while
generating; check the imagery licence — deploy/README.md §8). Read the page's terrain
warning: route the recording legs over textured ground, with leg 5 as the only deliberate
uniform stretch.

## 5. Pre-flight check (every time)

With the pipeline stopped (`sudo systemctl stop navera-pipeline-day`), in the NAVERA shell:

```bash
python3 navera_tools/check_box.py --camera     # also opens the camera itself
```

Then `sudo systemctl start navera-pipeline-day`, wait ~30 s, and with everything running:

```bash
python3 navera_tools/check_box.py              # topics and rates, 15 s
```

Fly only with **READY** (no FAIL). Read every WARN. Without a lens calibration or a field
of view the camera settings FAIL; with a field of view only, "lens calibration" WARNs.

## 6. Ground checks (vehicle on the ground, motors off)

1. **Static, 2 minutes**, recorded — gives the real IMU and GPS noise (today the
   covariances are datasheet values). In the NAVERA shell (Ctrl-C after 2 minutes):
   ```bash
   navera_tools/record_session.sh /data/navera/rec/static day
   ```
2. **Heading**: point the vehicle at a known direction (a landmark, a surveyed line, or
   north from a phone at a distance from the vehicle). `heading_deg` in the frame metadata
   must match within a few degrees:
   ```bash
   ros2 topic echo /day/frame_meta --field data
   ```
   This confirms the BNO085 frame convention (backlog IMU-3). With the box IMU, the heading
   is true north once a GPS position is known (World Magnetic Model), or uses
   `NAVERA_DECLINATION_DEG` until then.
3. **Camera latency**: film a phone stopwatch with the camera while recording. The frame's
   exposure stamp (`image_stamp_ns` in `/day/frame_meta`) is already the grab time minus the
   current `NAVERA_CAMERA_LATENCY_S`, so the difference between it and the time shown in the
   image is the ERROR of the current setting, not the latency:
   new `NAVERA_CAMERA_LATENCY_S` = current setting + (stamp - time shown). (Or set it to 0 for
   this check: the difference stamp - time shown is then the latency itself.) On the bench, `navera_tools/bench/camera_latency.py`
   measures it directly (screen flashes, median - frame period / 2); with `--calib <calibration.yaml>`
   it is written into the camera's calibration file, and the day node then uses it as the set delay
   (stated with 0.1 s). This is the main source of the delay: the GPS may be lost right after
   take-off. Re-measure after any change of camera, resolution, frame rate, encoder or stream
   settings. In-flight calibration (`auto_latency`) needs at least two turns of ≥ 90° at cruise
   speed more than 20 s before the GPS can be lost (day_pkg/README.md, "Camera delay").

## 7. Recording flights (GPS valid, vision in shadow mode)

Shadow mode makes the pipeline run while GPS is valid and publish its own positions for
comparison. Enable it in the service, not with a second launch beside it:

```bash
sudoedit /etc/navera/navera.env            # NAVERA_SHADOW_MODE=true
sudo systemctl restart navera-pipeline-day
```

Keep `NAVERA_FORWARD_DEGRADED` unset (false) for these flights: the autopilot flies on GPS.
Record each flight in the NAVERA shell (Ctrl-C after landing; one new directory per flight):

```bash
navera_tools/record_session.sh /data/navera/rec/flight1 day
```

Fly the prepared route, in this order:

| Leg | Height | Speed | Why |
|---|---|---|---|
| 1 | 100 m | slow | baseline |
| 2 | 150 m | cruise | nominal |
| 3 | 250 m | cruise | footprint and scale |
| 4 | 150 m | turns, climb, descent | attitude and altitude changes |
| 5 | over uniform ground (fields, sand, water edge) | cruise | known weak case |

Then, in the NAVERA shell:

```bash
python3 navera_tools/evaluate_session.py /data/navera/rec/flight1
```

It gives day vision's error against GPS per frame (median, p90, share within 50 / 100 /
300 m), the frames with no position, and **whether the accuracy NAVERA states is honest**:
how often the error is within 1 / 2 / 3 × the stated sigma (honest: ~39 / 86 / 99 %), and
the sigma that would be honest. If it says "stated sigma too optimistic", use the honest
value for `NAVERA_DEGRADED_SIGMA_M` (step 8) and for the matcher's `local_sigma_m`. These figures replace the simulation ones in
`VALIDATION_STATUS.md`. At the end of the campaign set `NAVERA_SHADOW_MODE=false` (or
remove it) and restart the pipeline.

## 8. GPS-denied flight (only after step 7 shows vision working)

With a safety pilot able to take manual control:

1. **Autopilot**: NAVERA is its GPS (`navera-output`, parameters in
   [ARDUPILOT_INTEGRATION.md](ARDUPILOT_INTEGRATION.md)). The autopilot needs one real GPS
   fix at power-on: take off with GPS.
2. **Forward vision positions.** Vision positions are DEGRADED and **nothing is sent to the
   autopilot without GPS unless forwarding is enabled**. In `/etc/navera/navera.env`:
   ```
   NAVERA_FORWARD_DEGRADED=true
   NAVERA_DEGRADED_SIGMA_M=<the "honest sigma" evaluate_session.py gave in step 7, metres>
   ```
   then `sudo systemctl restart navera-output`. The output service refuses to start with
   forwarding and no accuracy. An autopilot told a position is better than it is rejects it
   and fails safe (measured in simulation, `navera_output/README.md`). ArduPilot caps a
   stated accuracy at 100 m (it would trust a larger value more than stated; `check_box.py`
   WARNs). Forward over **MAVLink**: NMEA carries no accuracy, and vision positions are not
   sent over it (`NAVERA_NMEA_FORWARD_DEGRADED` stays off).
3. **Lose GPS** at cruise, over the recorded route — unplug the receiver, or cut it in
   software on the box:
   ```bash
   sudo systemctl stop navera-gps
   ```
   and `sudo systemctl start navera-gps` to restore it.
4. Abort on the first autopilot failsafe or position jump. An autopilot does not resume its
   mission by itself after a failsafe: the safety pilot takes over.

## What the simulation already shows (not a substitute for steps 6–8)

Simulated physical camera (lens, true attitude, light) through NAVERA's real chain,
GPS jammed 240 s: gimbal at 72 km/h — 190 matches, vision < 1 m, autopilot error
median 11 m, mission completed; fixed camera — frames at the 45° tilt limit, autopilot
failsafe (such frames are now also refused when the vehicle turns faster than 30°/s).
With day vision's dead-reckoning along the measured track (simulator, GPS jammed, gimbal):
land route without failsafe, error median 10 m, max 33 m; across the bay, carried 90 s
over the sea stating ±300 m with a true error of at most 146 m. The simulated camera sees
the map's own imagery over flat ground: real frames will match less often and less
accurately.
