# NAVERA — first real test: procedure

Goal of the first campaign: **record** camera, attitude, GPS and NAVERA's decisions
together, so that every accuracy figure can be measured on real data
(`docs/VALIDATION_STATUS.md` holds only bench, replay and simulation figures today).
GPS stays valid and in charge during the recording flights; vision runs in *shadow
mode* beside it. A GPS-denied flight comes only after the recordings show vision
working (step 8).

Prerequisite: the box is installed as described in [deploy/README.md](../deploy/README.md)
(workspace `/home/navera/isaac_ros_common`, services installed, `/etc/navera/navera.env`).

## 0. The NAVERA shell

Every command below that is not prefixed with `sudo` is run in a shell that has the same
environment as the services. Open it with:

```bash
sudo -u navera -H bash
source /opt/ros/humble/setup.bash
source /home/navera/isaac_ros_common/install/setup.bash
set -a; . /etc/navera/navera.env; . /var/lib/navera/settings.env 2>/dev/null; set +a
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
| Camera | Insta360 ONE R, **4K wide-angle module**, **USB webcam mode**. Address it by its stable name `/dev/v4l/by-id/usb-…-video-index0` (`ls -l /dev/v4l/by-id/`), not `/dev/videoN` |
| Mount, multirotor | **on a gimbal** holding it straight down (`NAVERA_CAMERA_GIMBAL=true`). A fixed camera leans with the drone: 45° at speed in simulation, the limit (`NAVERA_CAMERA_MAX_TILT_DEG`, default 45) |
| Mount, plane / boat / robot | fixed, looking straight down, image top towards the nose (`NAVERA_CAMERA_MOUNT_RPY=0,0,0`; otherwise measure and enter the angles) |
| IMU | BNO085 on I²C bus 1 (0x4A), rigidly fixed. Mounting angles: `NAVERA_IMU_MOUNT_RPY` (roll,pitch,yaw in degrees) in `/etc/navera/navera.env` or on the `/mission` page |
| GPS | Neo-M8N on `/dev/ttyTHS1`, 9600 baud (`NAVERA_GPS_SOURCE=serial`), antenna with a clear sky view, away from the Jetson |
| Clock | DS3231 on I²C bus 1 (0x68), backup cell fitted |
| Vehicle link (if used) | one autopilot port for NAVERA's reading (`NAVERA_VEHICLE_MAVLINK_URL`), one for NAVERA's GPS output (`NAVERA_MAVLINK_URL`), or one shared through mavlink-router — see [ARDUPILOT_INTEGRATION.md](ARDUPILOT_INTEGRATION.md) |

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

The vehicle settings can be set either there or on the `/mission` page (port 8181):
`NAVERA_MAX_SPEED_KMH=<cruise + 50 %>`, `NAVERA_VEHICLE_TYPE`, `NAVERA_IMU_MOUNT_RPY`,
`NAVERA_DECLINATION_DEG`. Then restart:

```bash
sudo systemctl restart navera-estimator navera-imu navera-gps navera-pipeline-day navera-web
```

Whatever the sources, NAVERA needs a GPS fix when the test starts: it is the first
position day vision searches around.

## 4. Map of the test area

Page `/mission` (`http://<jetson-ip>:8181/mission`, with the control token): import the
autopilot's mission file (or click the route), **Generate the map**, then **Activate this
map**. Day vision only matches against the activated map: without it, it reports no
position. Generating and activating are refused while the vehicle is armed or NAVERA is
navigating without GPS — prepare on the ground.

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
3. **Camera latency**: film a phone stopwatch with the camera while recording; the
   difference between the frame's exposure stamp (`image_stamp_ns` in `/day/frame_meta`) and
   the time shown in the image is `NAVERA_CAMERA_LATENCY_S`.

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
   and fails safe (measured in simulation, `navera_output/README.md`).
3. **Lose GPS** at cruise, over the recorded route — unplug the receiver, or cut it in
   software on the box:
   ```bash
   sudo systemctl stop navera-gps
   ```
   and `sudo systemctl start navera-gps` to restore it.
4. Abort on the first autopilot failsafe or position jump.

## What the simulation already shows (not a substitute for steps 6–8)

Simulated physical camera (lens, true attitude, light) through NAVERA's real chain,
GPS jammed 240 s: gimbal at 72 km/h — 190 matches, vision < 1 m, autopilot error
median 11 m, mission completed; fixed camera — frames at the 45° tilt limit, autopilot
failsafe. The simulated camera sees the map's own imagery over flat ground: real
frames will match less often and less accurately.
