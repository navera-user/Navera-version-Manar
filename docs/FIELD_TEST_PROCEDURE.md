# NAVERA — first real test: procedure

Goal of the first campaign: **record** camera, attitude, GPS and NAVERA's decisions
together, so that every accuracy figure can be measured on real data
(`docs/VALIDATION_STATUS.md` holds only bench, replay and simulation figures today).
GPS stays valid and in charge during the recording flights; vision runs in *shadow
mode* beside it. A GPS-denied flight comes only after the recordings show vision
working (step 8).

## 1. Hardware

| Item | Setting |
|---|---|
| Camera | Insta360 ONE R, **4K wide-angle module**, **USB webcam mode** → `/dev/videoN` on the Jetson |
| Mount, multirotor | **on a gimbal** holding it straight down (`NAVERA_CAMERA_GIMBAL=true`). A fixed camera leans with the drone: 45° at speed in simulation, the limit (`NAVERA_CAMERA_MAX_TILT_DEG`, default 45) |
| Mount, plane / boat / robot | fixed, looking straight down, image top towards the nose (`NAVERA_CAMERA_MOUNT_RPY=0,0,0`; otherwise measure and enter the angles) |
| IMU | BNO085 on I²C bus 1 (0x4A), rigidly fixed; mounting angles in `/etc/navera/imu_params.yaml` or the `/mission` page |
| GPS | Neo-M8N on `/dev/ttyTHS1`, 9600 baud, antenna with a clear sky view, away from the Jetson |
| Clock | DS3231 on I²C bus 1 (0x68), backup cell fitted |
| Vehicle link (if used) | one autopilot port for NAVERA's reading (`NAVERA_VEHICLE_MAVLINK_URL`), one for NAVERA's GPS output |

## 2. Lens calibration (once per camera and resolution)

1. Print a 9×6 (inner corners) checkerboard, measure one square, stick it on a rigid board.
2. Stop the pipelines (`sudo systemctl stop navera-pipeline-day`), then:
   ```bash
   python3 navera_tools/calibrate_camera.py --device /dev/video0 --size 1920x1080 \
       --board 9x6 --square-mm <measured> --out /etc/navera/camera.yaml
   ```
3. Show the board at 30 positions: corners and edges of the image, tilted, near and far.
4. Accept when RMS < 0.5 px. Then set `NAVERA_CAMERA_CALIBRATION=/etc/navera/camera.yaml`.

The tool recovers a known lens to 0.1 % in focal length and 0.1° in field of view
(`navera_tools/tests/test_calibrate_camera.py`).

## 3. Settings (`/etc/navera/navera.env`, or the `/mission` page)

```
NAVERA_CAMERA=live
NAVERA_CAMERA_INPUT=usb
NAVERA_CAMERA_DEVICE=/dev/video0
NAVERA_CAMERA_SIZE=1920x1080
NAVERA_CAMERA_CALIBRATION=/etc/navera/camera.yaml
NAVERA_CAMERA_GIMBAL=true            # multirotor
NAVERA_SENSOR_SOURCE=box             # or vehicle (+ NAVERA_VEHICLE_MAVLINK_URL), or ros (+ NAVERA_ROS_IMU_TOPIC)
NAVERA_MAX_SPEED_KMH=<cruise + 50 %>
NAVERA_GROUND_ALTITUDE_M=<site elevation, if known>
```

## 4. Map of the test area

Page `/mission` (port 8181): import the autopilot's mission file (or click the route),
**Generate the map**, then **Activate this map**.

## 5. Pre-flight check (every time)

```bash
python3 navera_tools/check_box.py --camera     # with the pipelines stopped: opens the camera
python3 navera_tools/check_box.py              # with everything running: topics and rates
```
Fly only with **READY** (no FAIL). Read every WARN.

## 6. Ground checks (vehicle on the ground, motors off)

1. **Static, 2 minutes**, recorded (`record_session.sh /data/navera/rec/static day`):
   gives the real IMU and GPS noise (today the covariances are datasheet values).
2. **Heading**: point the vehicle at a known direction (a landmark, a surveyed line, or
   north from a phone at a distance from the vehicle): `heading_deg` in
   `/day/frame_meta` must match within a few degrees. This confirms the BNO085 frame
   convention (backlog IMU-3).
3. **Camera latency**: film a phone stopwatch with the camera while recording; the
   difference between the frame stamp and the time shown is `NAVERA_CAMERA_LATENCY_S`.

## 7. Recording flights (GPS valid, vision in shadow mode)

Start the day pipeline in shadow mode and record:
```bash
ros2 launch simulation_web day_pipeline.launch.py shadow_mode:=true
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

Then: `python3 navera_tools/evaluate_session.py /data/navera/rec/flight1` — day vision
error against GPS per frame (median, p90, share within 50 m), and the frames with no
position and why. These figures replace the simulation ones in `VALIDATION_STATUS.md`.

## 8. GPS-denied flight (only after step 7 shows vision working)

With a safety pilot able to take manual control: NAVERA as the autopilot's GPS
(`navera-output`), GPS unplugged or jammed in software on the box at cruise, over the
recorded route. Abort on the first autopilot failsafe or position jump.

## What the simulation already shows (not a substitute for steps 6–8)

Simulated physical camera (lens, true attitude, light) through NAVERA's real chain,
GPS jammed 240 s: gimbal at 72 km/h — 190 matches, vision < 1 m, autopilot error
median 11 m, mission completed; fixed camera — frames at the 45° tilt limit, autopilot
failsafe. The simulated camera sees the map's own imagery over flat ground: real
frames will match less often and less accurately.
