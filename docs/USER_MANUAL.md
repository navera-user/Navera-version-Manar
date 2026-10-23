# NAVERA — User manual

For the **integrator** who installs NAVERA on a vehicle and the **operator** who flies with it.
You do not need to be a software developer. Commands to type are shown in grey boxes. Settings
are lines in one text file, `/etc/navera/navera.env` (appendix A lists them).

Release covered: the NAVERA software as of 2026-10-22, reference box Jetson Orin Nano 8 GB.
The detailed engineering documents are named at the end of each section, for your technical team.

> **Status of this release — read this first**
>
> - **NAVERA has not flown yet.** Every accuracy figure comes from a bench, from replayed
>   real flights of other cameras, or from simulation (`docs/VALIDATION_STATUS.md`).
> - **NAVERA has not yet been connected to a real autopilot.** The ArduPilot connection is
>   verified in ArduPilot's simulator (SITL) only. PX4 is **not tested**, and PX4 cannot
>   receive NAVERA's vision positions today (section 5.6).
> - **By default, NAVERA does not send its vision positions to the autopilot.** When GPS is
>   lost, the autopilot receives "no fix" and its own failsafe acts. Sending vision positions
>   is a setting you switch on deliberately, with an accuracy you have measured (section 5.4).
> - The first campaign must be **recording flights with GPS in charge** ("shadow mode",
>   section 9.3). A GPS-denied flight comes after, with a safety pilot.

---

## Contents

1. What NAVERA is and what it does
2. The hardware: reference box, sensors, shopping list
3. Installing NAVERA — three ways (A: IRIS kit, B: client's equipment, C: ROS 2 vehicle)
4. Connecting a GPS
5. Connecting the autopilot
6. Cameras
7. Before each mission
8. In flight
9. After the flight
10. Troubleshooting and limits
- Appendix A — Settings you may change (`navera.env`)
- Appendix B — Useful commands
- Appendix C — Words used in this manual

---

## 1. What NAVERA is and what it does

NAVERA is a small computer that you fit on a vehicle (drone, plane, ground robot, boat). It
gives the vehicle its **position when GPS cannot be trusted** — jammed (no signal) or spoofed
(a false signal).

It does this by **looking at the ground**. A camera points straight down. NAVERA compares each
picture with a satellite map stored on the box. When the picture matches a place on the map,
NAVERA knows where the vehicle is.

```
                 +--------------------------- NAVERA box (Jetson Orin Nano) -------------------------+
                 |                                                                                   |
  GPS receiver --+--> GPS check -----------+                                                         |
  (or autopilot's|    (refuses jumps,      |                                                         |
   2nd GPS, ROS) |     drift, spoofing)    v                                                         |
                 |                    +-----------+     +-------------------+                        |
  Day camera  ---+--> day vision ---->|  ARBITER  |---->|  OUTPUT           |--> autopilot (MAVLink  |
  (looks down)   |    (picture vs     | GPS first,|     |  GPS_INPUT, NMEA, |    or NMEA "GPS")      |
                 |     offline map)   | then day, |     |  ROS /navera/fix) |--> ROS 2 vehicle       |
  Thermal cam ---+--> night vision -->| night,    |     +-------------------+                        |
  (optional)     |                    | celestial |-------------------------------> web page :8181   |
  Star camera ---+--> celestial ----->|           |                                 (operator view)  |
  (experimental) |                    +-----------+                                                  |
  IMU / attitude-+--> straightens the pictures, carries the heading                                    |
  GPS time ------+--> trusted time for the stars (kept by the box after the GPS is lost)            |
                 +-----------------------------------------------------------------------------------+
```

**The arbiter** decides which position to use, in this order: **GPS > day vision > night
vision > celestial**. A good GPS always wins. When GPS is lost or refused, vision takes over.

### The operating rules

1. **GPS must be good at take-off.** NAVERA needs one GPS fix at start: it is the first position
   that vision searches around. The autopilot also needs a real GPS fix at power-on to set its
   origin. (Where there is no GPS at all, see "Start without GPS", section 7.5.)
2. **After take-off, NAVERA keeps navigating if GPS is jammed or spoofed** — for as long as the
   camera keeps matching the map, possibly for the whole flight. Between matches it carries the
   last position along the measured track for **at most 2 minutes / 500 m**, then it says "no
   position". It does **not** integrate the IMU into a position (no inertial navigation).
3. **NAVERA is fully offline in flight.** The map package of the route is prepared **before
   departure** (section 7). No internet, no network link is needed in the air.
4. **Autopilots:** ArduPilot is supported (verified in simulation only). PX4: only as a plain
   GPS pass-through over NMEA; not tested (section 5.6).
5. **Day camera vision is the main source.** At **night you need a thermal camera** (night
   vision, not flown yet). **Star (celestial) navigation is experimental** and coarse
   (kilometres).

### What NAVERA also does

- **Checks the GPS.** It refuses a GPS position the vehicle could not have reached (sudden
  jump) and a GPS that slowly drifts away from what the camera sees (slow spoofing). This check
  needs the camera to match; over sea or uniform ground a slow spoof is not caught.
- **Detects its own sensors at boot** and chooses the sources by itself (section 3.2).
- **Restarts by itself.** Every part is a separate service. A part that crashes, or loses its
  camera or GPS, is restarted 1 s later, forever (a part that keeps failing is retried less
  often, at most every 30 s). In flight without GPS, the autopilot keeps being given a position
  while a part restarts (section 10.1, "a NAVERA service crashed in flight").
- **Shows its state** on a web page (operator view) on port 8181.

---

## 2. The hardware

### 2.1 The reference box

| Part | What NAVERA uses | Required? |
|---|---|---|
| Computer | **NVIDIA Jetson Orin Nano 8 GB**, JetPack 6.2.1, Ubuntu 22.04, ROS 2 Humble | **Required** — the only platform NAVERA is built and tested on |
| Data disk | a disk mounted at `/data` (NVMe SSD or USB disk) for maps, models and recordings | **Required** |
| Swap | an 8 GB swap file on disk (the installer makes it) | **Required** — the day vision was killed for lack of memory without it |
| Power | the Jetson's own supply, as the carrier board specifies | **Required** — module draw measured 10.5 W mean, 12.1 W max under a mixed GPU load (on-module monitor, deploy/README.md §3.11); the whole box at the DC jack and brown-out behaviour are not measured yet: size the supply for at least 25 W for the module (MAXN_SUPER is not power-capped) plus the peripherals |

NAVERA's own sensors, fitted to the box:

| Sensor | Model the code supports | Connection | Required? |
|---|---|---|---|
| Day camera | **Insta360 ONE R 360 module in USB "Android" mode** (the IRIS kit: a straight-down view cut from its 360 picture, section 3.1); or any USB (UVC) camera, a Jetson CSI camera, a network (RTSP) camera, or the vehicle's ROS camera | USB / CSI / Ethernet / ROS | **Required** (vision does not work without it) |
| GPS receiver | NMEA serial receiver; **u-blox NEO-M8N** gave a valid fix on the box | UART `/dev/ttyTHS1`, 9600 baud | **Required: one GPS** — the box's own, or the autopilot's second GPS, or the vehicle's ROS GPS |
| IMU (IRIS kit) | the **Insta360 ONE R's own IMU** (gyroscope + accelerometer, ~500 Hz, measured gyro noise 0.003 °/s/√Hz), read over the camera's USB link by the same program as its picture (`navera-insta360`) | USB (camera in "Android" USB mode) | The IRIS kit's IMU: gives the **attitude** (roll / pitch from gyro + accelerometer; heading from the gyro, set by the GPS course and vision — **no magnetometer**), section 3.1 |
| IMU (optional / legacy) | **Bosch BNO085** (I²C, address 0x4A or 0x4B) | I²C bus 1 (pins 27/28) or bus 7 (pins 3/5), 3.3 V | Optional. Still supported and still detected automatically; no longer part of the IRIS kit |
| Attitude for the vision | one source giving roll, pitch and heading: the Insta360 kit's own IMU, the autopilot (MAVLink), the vehicle's ROS IMU, or a BNO085 | — | **Required for a fixed camera** (see 3.1); with a gimbal, a gyro is enough |
| Clock | **Maxim DS3231** real-time clock with its coin cell fitted | I²C, address 0x68 | **Optional** (2026-10-22). The star navigation's time comes from the **GPS at take-off**, kept by the box afterwards, cross-checked with the autopilot's time; a DS3231 only helps after a box reboot with the GPS denied and no autopilot time (section 6.6) |
| Thermal camera | any LWIR camera NAVERA can read (USB, RTSP) | USB / Ethernet | Optional — needed only for night |
| Star camera | a USB camera pointing up | USB | Optional — experimental |

### 2.2 Shopping list — the client's "ready to plug" test equipment

IRIS supplies the NAVERA box with its own kit (Jetson Orin Nano 8 GB, data disk, Insta360 ONE R
camera with its IMU, GPS receiver, DS3231 clock, cables). This list is what **the client's
platform** must provide so that the box can be plugged in for a test.

**Required on the client's side**

| Item | Exact models / settings the code supports | Why |
|---|---|---|
| An **autopilot** with a free telemetry port | **ArduPilot** (Copter, Plane, Rover 4.5 verified in SITL), MAVLink 2 (`SERIALn_PROTOCOL = 2`), 3.3 V TTL TELEM port; or MAVLink on the network (UDP 14550 / 14551) | NAVERA's position goes to it as GPS 1 (`GPS_TYPE = 14`); its attitude, barometric height and armed state come back. PX4: GPS pass-through over NMEA only (section 5.6) |
| A **TELEM cable** to the Jetson: a **3.3 V USB-to-serial adapter** (FTDI-type, appears as `/dev/ttyUSB*` with a `/dev/serial/by-id/` name) and a cable to the TELEM connector (e.g. JST-GH on Pixhawk-class boards) | The adapter is detected automatically; never RS-232 or 5 V logic |
| **Attitude** for the camera (recommended) | the autopilot's attitude over MAVLink (detected automatically, preferred when present), or the vehicle's ROS 2 IMU (ENU, yaw from true north, ≥ 25 Hz) | A **fixed** camera needs roll and pitch at each picture. The IRIS kit computes them from the Insta360's own IMU (3.1); the autopilot's filter (GPS, compass, vehicle dynamics) is better during long accelerations |
| A **GPS fix at take-off** | IRIS's receiver on the box, or the autopilot's **second** GPS (a real receiver, `GPS_TYPE2` ≠ 14), or a ROS `NavSatFix` with covariance | NAVERA starts from it; the autopilot needs it to set its origin |
| A **camera mount** looking straight down, top of the image to the nose | on a multirotor: a **gimbal** holding the camera level (any model; NAVERA does not control it, it is only told `NAVERA_CAMERA_GIMBAL=true`) | Pictures tilted more than 45° are not used; a multirotor leans 30–45° at speed |
| **Power** for the box | the supply the Jetson carrier board specifies, from the vehicle | NAVERA's power draw and brown-out behaviour are not measured yet: use a supply with margin |
| A **laptop or tablet** on the vehicle's network | any browser | the operator view (port 8181) and the `/mission` page |

**Recommended**

| Item | Why |
|---|---|
| A **downward rangefinder** on the autopilot (ArduPilot `RNGFNDx_ORIENT = 25`) | Gives NAVERA the true height above ground (better than GPS height over hills) |
| A second free TELEM port | Wiring B (section 5.1): output and vehicle link on separate ports |
| The route's **map imagery** under a licence that allows offline storage, 2 m or finer, under 5 years old | Day vision only works over a map of the route (section 7.2) |

**Optional**

| Item | Model | Status |
|---|---|---|
| Thermal camera for night | **FLIR Boson 640 or Boson+ 640, 50° lens, USB, 9 Hz export version** (IRIS research recommendation; same camera family as the night model's training data) | Not yet tested with NAVERA. Second choice: InfiRay Micro III Lite 640 (6.9 mm lens, USB-C board). Smoke test only: InfiRay P2 Pro (256 × 192) |
| Thermal camera, bench | Hikvision **DS-2TD2617B-3/PA** (RTSP over Ethernet) | Used by IRIS on the bench only: its thermal picture is 160 × 120 and it is a mains-powered security camera, **not flight hardware** |
| A client camera instead of IRIS's | any UVC USB camera, a Jetson CSI camera, an RTSP camera, or a ROS image topic | Needs its own lens calibration and delay measurement (section 6) |
| A **BNO085** I²C IMU on the box | legacy, still supported | Gives a full attitude (with magnetometer) when the vehicle cannot share one |
| Star camera | a USB camera pointing up | Experimental (section 1, rule 5) |

**Not supported yet:** inertial navigation; PX4 receiving vision positions; two vision
pipelines at once (day and night cannot run together); a computer other than the Jetson Orin
Nano 8 GB; NAVERA controlling a gimbal.

### 2.3 Cables and wiring of the IRIS kit

```
  Jetson 40-pin header                                 Sensors
  --------------------                                 -------
  pin 1  (3.3 V) ----------------------+--------------> DS3231  VCC      (3.3 V)
  pin 6  (GND)   ----------------------+--------------> DS3231  GND
  pin 27 (I2C bus 1 SDA) --------------+--------------> DS3231  SDA      (address 0x68)
  pin 28 (I2C bus 1 SCL) --------------+--------------> DS3231  SCL
                                       :
                                       +.............> BNO085 (optional / legacy, same 4 wires,
                                                        address 0x4A; not in the IRIS kit)

  UART TX  (/dev/ttyTHS1) ---------------------------> GPS  RX     crossed
  UART RX  (/dev/ttyTHS1) <--------------------------- GPS  TX     crossed
  GND      ------------------------------------------- GPS  GND
  (power the GPS as its board requires; 3.3 V logic only)

  USB port  <=========================================  Insta360 ONE R, USB mode "Android" (360 picture + its own IMU)
  USB port  <=========================================  USB-serial adapter --> autopilot TELEM (section 5)
  NVMe / USB <========================================  Data disk (/data)
```

- On the **Jetson Orin Nano developer kit** `/dev/ttyTHS1` is the 40-pin header's only UART:
  **pin 8 = TX, pin 10 = RX** (GND e.g. pin 6); `/dev/ttyTHS2` is not on the header — use a
  USB-serial adapter for the autopilot (deploy/README.md §3.11). On another carrier board, check
  its pinout.
- The Jetson header is **3.3 V logic**. Never connect it to RS-232 levels, or to 5 V logic
  without a level shifter.
- Mount the camera **rigidly, lying, one lens straight down** (3.1): its IMU measures the camera's own rotation. Keep the GPS antenna
  away from the Jetson, with a clear view of the sky.
- A BNO085, if you fit one, is also found on bus 7 (pins 3/5).

---

## 3. Installing NAVERA

### 3.0 Common steps (done once, usually by IRIS)

The software is installed by one command on the Jetson. Your IRIS contact provides the code
(private repository or archive) and the data files (map, models).

1. Mount the data disk at `/data` **first** (`deploy/README.md` §3.10 gives the exact steps).
2. Install:
   ```bash
   cd ~/Navera
   sudo deploy/install.sh            # add --headless for a box with no screen
   ```
3. Copy the data files delivered by IRIS to `/data/navera/` and give them to the `navera` user:
   ```bash
   sudo rsync -a /media/<usb>/navera/ /data/navera/
   sudo chown -R navera:navera /data/navera
   ```
4. Edit the site settings:
   ```bash
   sudoedit /etc/navera/navera.env
   ```
   Set at least, for **every** vehicle:
   - `NAVERA_MAX_SPEED_KMH` — the vehicle's top speed + 50 %. Examples: multirotor 108, boat 72,
     ground robot 36, fixed-wing 250. NAVERA refuses any position the vehicle could not reach at
     this speed (this is how it catches a GPS jump).
   - `NAVERA_WEB_TOKEN` — the access code of the web page. Make one with `openssl rand -hex 16`.
     Without it the web page is read-only.
   - `NAVERA_CAMERA=live` — the default `replay` plays recorded pictures (demonstration only).
5. Apply the settings (this one command restarts everything, detection first):
   ```bash
   sudo systemctl restart navera-discover navera-estimator navera-gps navera-imu navera-insta360 \
       navera-rtc navera-vehicle-link navera-pipeline-day navera-output navera-web
   ```
6. Check the box (section 7.6).
7. Once, do the reboot test: `sudo reboot`, wait 2 minutes, then
   `/home/navera/isaac_ros_common/deploy/check_boot.sh`. Every service must be "active".

> **Rule for every setting:** a number setting must have a value **or** be commented out
> with `#`. A line like `NAVERA_DAY_HFOV_DEG=` (empty) is not "unset": some services refuse to start.

After any change to `navera.env`, run the restart command of step 5 again.

### 3.1 Way A — with IRIS's own sensors (the Insta360 kit)

The box carries its own camera, GPS receiver and clock. The camera is an **Insta360 ONE R (360
module)** read in its USB **"Android" mode**: it is **both the day camera and the IMU** (its
built-in gyroscope and accelerometer). The kit has **no BNO085** and needs **no autopilot
attitude**. One program owns the camera — the `navera-insta360` service — and gives the rest of
NAVERA a straight-down picture cut out of the 360 picture and the vehicle's attitude computed from
the camera's own IMU.

1. **Camera USB mode: Android.** On the camera: *Settings → USB mode → Android*. Plug it into
   the Jetson. Check it with `lsusb`: it must show `2e1a:0002 … Insta360 ONERS`. In **webcam**
   mode it gives only two cropped strips and no IMU: not usable for the kit (the box check says so).
2. **Mount it lying, one lens straight down.** Default (`NAVERA_INSTA360_MOUNT_AXES=+x,+z,-y`):
   the camera lies on its side with its **left lens** (the left circle of the 360 picture) looking
   straight down and its **top** (the side that is up when the camera stands) towards the
   vehicle's **nose**. Straight down is then the centre of that lens (its best resolution, about
   10 pixels per degree); the other lens sees the sky. Fix it **rigidly**: the IMU is inside the
   camera, so any play between camera and vehicle is an attitude error. Another orientation:
   write its axes in `NAVERA_INSTA360_MOUNT_AXES` (see `deploy/navera.env.example`). A camera
   **standing** (lenses horizontal) has straight down on the seam between the lenses: the box check
   warns, and day vision there is poor.
3. **Install** (section 3.0). The installer adds the camera's USB permission
   (`/etc/udev/rules.d/99-insta360.rules`), the Python modules it needs (pyusb, PyAV) and the
   `navera-insta360` service. **Unplug and replug the camera** after the install.
4. **Copy its calibrations** (made by IRIS on the bench: lenses on a screen dot grid, IMU in 6
   positions) to the box:
   ```bash
   sudo install -o navera -g navera -m 0644 insta360_usb_lens.json /var/lib/navera/insta360_lens.json
   sudo install -o navera -g navera -m 0644 insta360_usb_imu.json  /var/lib/navera/insta360_imu.json
   ```
   No `NAVERA_CAMERA_CALIBRATION` is needed: the straight-down picture is computed from the lens
   calibration (an ideal lens of `NAVERA_INSTA360_VIEW_HFOV_DEG`, 100° by default).
5. Leave the sources on `auto` (the default). At boot NAVERA finds the DS3231, the GPS receiver
   and the One R in Android mode, and chooses `NAVERA_CAMERA_INPUT=insta360` and — when no BNO085,
   no autopilot and no ROS IMU is found — `NAVERA_SENSOR_SOURCE=insta360`. When an autopilot is
   connected, **its** attitude is used and the camera stays the kit's (decision: the autopilot's
   filter has the GPS, a compass and the vehicle's dynamics; the camera's filter has only gravity
   and the gyro — see the limits below).
6. Apply the settings with the restart command of section 3.0 step 5 (it includes
   `navera-insta360`).
7. Connect the autopilot if there is one (section 5), then run the checks (section 7.6). The
   kit's lines: `Insta360 kit settings`, `Insta360 camera` (Android mode, USB permission),
   `Python module usb / av`, `Insta360 lens calibration`, `Insta360 day view` (straight down
   through which lens), `Insta360 IMU calibration`, and with the services running
   `attitude` (100 Hz on `/navera/sensors/insta360/imu`) and `Insta360 kit` (frames, tilt
   uncertainty, heading and its source).

> **One program per camera.** IRIS's field-test server (`navera-field`, a bench tool, not part of
> the product) also opens the camera in Android mode. On a flight box: `sudo systemctl disable --now navera-field`.

Reference settings for Way A (written instead of `auto`, if you prefer fixed choices):

```
NAVERA_SENSOR_SOURCE=insta360        # attitude from the Insta360's own IMU (vehicle: the autopilot's)
NAVERA_GPS_SOURCE=serial
NAVERA_GPS_PORT=/dev/ttyTHS1
NAVERA_GPS_BAUD=9600
NAVERA_CAMERA=live
NAVERA_CAMERA_INPUT=insta360         # the kit's straight-down view (navera-insta360)
NAVERA_INSTA360_MOUNT_AXES=+x,+z,-y  # lying, left lens down, camera top to the nose
#NAVERA_INSTA360_MOUNT_RPY=0,0,0     # small trim, if measured
#NAVERA_INSTA360_VIEW_SIZE=1200x900
#NAVERA_INSTA360_VIEW_HFOV_DEG=100
```

`NAVERA_CAMERA_CALIBRATION`, `NAVERA_CAMERA_CROP`, `NAVERA_CAMERA_SIZE` and a non-zero
`NAVERA_CAMERA_MOUNT_RPY` do not apply to the kit (the live camera refuses a mount or a crop
written for it).

#### Attitude and heading on the IRIS kit (Insta360 IMU, no magnetometer)

`navera-insta360` publishes the vehicle's attitude on `/navera/sensors/insta360/imu`
(`sensor_msgs/Imu`, 100 Hz, **with an orientation** and its uncertainty), computed from the
camera's gyroscope and accelerometer (`camera_pkg/insta360_attitude.py`):

| Part | How | Its uncertainty (published) |
|---|---|---|
| **Roll and pitch** (the tilt) | the gyro, integrated, pulled slowly (20 s) towards the accelerometer's "down" — **only when the vehicle is not accelerating**: the pull is off when the measured acceleration differs from 1 g by more than 3 %, when the vehicle turns about the vertical faster than 1 °/s (a curve: the centripetal acceleration tilts "down"), or rotates faster than 20 °/s. While the GPS is trusted, the turn and speed-change accelerations are computed from the GPS track and removed, and the turn rule is not needed. Stopped (2 s still), the pull is fast (2 s). The gyro's bias is re-measured at every stop | 0.5° while the accelerometer is used with the GPS speed known (or stopped); 1.0° without it (GPS lost); growing while it is off |
| **Heading** | the gyro, integrated about the vertical. It is **not** a heading until a source sets it: (1) the **GPS course** while the GPS is trusted, above 5 m/s on a straight leg (±10°: the nose may not point along the track — wind, sideslip); (2) **vision**: each good day match (≥ 20 matched points) measures the picture's rotation (±2°). Then carried by the gyro, its uncertainty growing with the gyro bias left (0.05 °/s assumed; up to 0.047 °/s creep measured at rest) | "unknown" (published variance π²) until set; a source that disagrees with a still-valid heading by more than 3 σ is refused |

The live camera straightens each picture with the roll and pitch at its exposure. It writes the
picture's heading only when the heading's uncertainty is **5° or less**; otherwise the day
pipeline uses its own gyro-carried vision heading (`day_pkg/gyro_heading.py`, fed by the same
camera gyro), as before:

| Step | How the day pipeline's heading is obtained | When |
|---|---|---|
| 1. From the GPS course | while GPS is trusted, above 5 m/s on a steady course, the heading of the picture = the GPS course + the camera's offset from it (learned from vision, else the camera's mounting yaw; ±5° assumed for crab) | before GPS is lost |
| 2. From vision | each good map match measures the picture's rotation, i.e. its heading | every good match (at least 20 matched points) |
| 3. Carried by the gyro | between matches the heading is carried by integrating the gyro's rate about the vertical; its uncertainty grows with the gyro bias (0.1 °/s assumed) and noise (0.004 °/s/√Hz assumed; 0.0025–0.0033 measured at rest) | until its uncertainty passes 10°: then no heading, the position is carried straight on |

Pictures are stamped at their **exposure** on the IMU's clock. Each key frame (2 per second) is
decoded on its own as soon as it arrives; the 1.5 s offset measured on the bench (F15) was the
decoder holding three key frames, so the kit stamps a picture with its own packet time (0 s lag).

**Measured (`navera_tools/bench/insta360_attitude_eval.py`, `navera_tools/bench/insta360_kit_replay.py`):**

| What | Data | Result |
|---|---|---|
| Tilt (roll / pitch) error vs truth, GPS speed known | **simulated** motion (fixed wing survey and steep turns, multirotor, car) carrying the **real** camera's noise (residuals of 3 recordings at rest) and a gyro bias left of 0.02–0.04 °/s | median 0.20–0.33°, 95 % under 0.51–0.65°, max 0.71°; 100 % inside 3 stated σ |
| The same, GPS lost (speed unknown) | same | median 0.43–0.76°, 95 % under 1.23–2.07°, max 2.21° (steep turns); 99.9–100 % inside 3 σ |
| The accelerometer trusted blindly in a coordinated turn (the D8 trap) | simulated steep turns | > 5° (unit test); with the gates < 2.5° |
| Real camera at rest | 3 recordings of the user's One R standing on a table (37–45 s) | roll / pitch steady within 0.006–0.10° (std); heading drift 0.02–0.08 °/min (gyro bias re-measured at rest) |
| End to end: kit → day pipeline | **synthetic** recording (`navera_tools/sim/insta360_raw_sim.py`: the camera's packets and timing, its dual fisheye drawn over the bench map at 400 m, 30 m/s with turns; the matcher compares with the **same** imagery — a plumbing proof, not an accuracy figure), GPS lost after 40 s, SIFT matcher | 166/166 frames with the kit's attitude, 0 refused; 139 fixes in 140 frames after the GPS loss (error 0.5 m median, 1.0 m max on this same-imagery data); tilt error at the frames 0.91° median, 1.46° max; heading in 137 frames' meta, error 0.6° median, 1.3° max |
| The same before this change (the Insta360 IMU without orientation) | same recording | 295/295 frames refused "no attitude at the frame's exposure", 0 fixes after the GPS loss (only dead-reckoning, then nothing) |

Not yet measured: the tilt on the **real** camera **moving** against truth, and anything on a
vehicle. On the bench (camera facing the screen dot grid of `navera_tools/bench/lens_calib_screen.py`,
turned by hand during the run; nothing else may hold the camera):

```bash
sudo systemctl stop navera-field navera-insta360        # one program per camera
python3 navera_tools/bench/attitude_check.py --kit --seconds 120 --out /tmp/attitude_kit.csv
#   tilt error median / max (sharp frames), and the best stamp offset (expected near 0 ms)
python3 navera_tools/bench/insta360_kit_replay.py <recording> --area <map images> --verbose
#   any raw recording (field START/END, or insta360_raw_sim.py) through the kit + day chain
```

**Limits of the kit (this release):**

- **No real motion with truth yet.** The tilt accuracy above is from simulated motion carrying the
  camera's real noise, and from the real camera at rest. Before a flight, run the dot-grid bench
  with the camera turned by hand (`navera_tools/bench/attitude_check.py`) and, in flight, compare
  with the autopilot's attitude in shadow mode.
- **Long accelerations without GPS.** After the GPS loss, a steady acceleration under 3 % of g,
  or a turn slower than 1 °/s, still pulls the tilt slowly (simulated: up to ~2°).
- **No heading before a source sets it.** With no GPS course yet (stopped, slow, turning) and no
  vision match, pictures carry no heading: the day matcher searches without one.
- **Lens-to-IMU mount angle** is not measured on a vehicle: measure it and write
  `NAVERA_INSTA360_MOUNT_RPY` (1° of tilt error = about 17 m of position error at 1,000 m).
- The celestial 360 mode still uses IRIS's field tools; the kit gives the day pipeline its frames.

### 3.2 Way B — with the client's own equipment ("auto-plug")

Here NAVERA uses what is already on the platform: the vehicle's GPS, its autopilot's attitude,
a camera already fitted. You plug things in; NAVERA looks for them at every boot.

#### What NAVERA detects by itself at boot

A service called **navera-discover** runs once at every power-on (about 20 s, before the
others). It looks for:

| What | Where it looks | How it recognises it |
|---|---|---|
| Box IMU and clock | I²C buses 1 and 7 | BNO085 at 0x4A / 0x4B, DS3231 at 0x68 |
| GPS receiver | serial ports `/dev/ttyTHS*`, `/dev/ttyUSB*`, `/dev/ttyACM*`, at 9600 to 921600 baud | valid NMEA **with satellite data** (GSV/GSA). An autopilot's NMEA output has none, so it is not mistaken for a receiver |
| Autopilot (MAVLink) | the same serial ports, and the network on UDP 14550 and 14551 | a heartbeat **from an autopilot** (ground stations, cameras and other computers are ignored). NAVERA then asks it for attitude, rangefinder, height and its GPS types |
| ROS 2 vehicle | ROS domain 0 and NAVERA's own domain | IMU, GPS, camera and rangefinder topics (section 3.3) |
| Cameras | USB (`/dev/v4l/by-id/…`), CSI (Jetson camera inputs), and an Insta360 ONE R in USB "Android" mode (USB id `2e1a:0002`, read from the system's USB list: the camera is not opened) | an Insta360 in **webcam** mode is reported "CHECK … set its USB mode to Android" |

It never opens a port another program holds, a system console port, or a login port. It only
writes to a port once it has identified an autopilot there.

#### The "auto" priority rules

| Need | First choice | Second | Third | None found |
|---|---|---|---|---|
| **Attitude** (`NAVERA_SENSOR_SOURCE`) | box IMU (BNO085, if fitted) | autopilot | ROS IMU topic, then the Insta360 kit's own IMU | warning: pictures unusable |
| **GPS** (`NAVERA_GPS_SOURCE`) | box GPS receiver | the autopilot's **second** GPS, only if it is a real receiver | ROS GPS topic | GPS service idle; NAVERA needs a GPS fix at start |
| **Camera** (`NAVERA_CAMERA_INPUT`) | the Insta360 kit (One R in Android mode) | USB, then CSI | ROS image topic | warning |
| **Output** | an autopilot found → NAVERA's position over MAVLink on the same link (`HIL_GPS` for PX4) | a ROS vehicle found → `/navera/fix` | — | message: set `NAVERA_NMEA_PORT` for an NMEA GPS input |

More rules:

- Several GPS receivers: the one with a fix, a wired port first; a warning asks you to choose.
- Several USB cameras: the first one, with a warning. **Set `NAVERA_CAMERA_DEVICE`** to the one
  looking down.
- A ROS camera is used with a warning "check it looks at the ground": NAVERA cannot know which way
  a camera points.
- **The autopilot's second GPS** is used only if the autopilot's `GPS_TYPE2` says it is a real
  receiver. It is never type 14 (the MAVLink GPS that NAVERA itself feeds — that would be a loop).
- **PX4 autopilot found:** NAVERA sends its position as `HIL_GPS` (PX4 ignores `GPS_INPUT`) and
  the report checks the PX4 parameters it needs (section 5.6): a "CHECK PX4 …" line names each
  one to change on the autopilot.
- **Detection runs once per boot.** A device plugged in later, or a vehicle computer that boots
  after NAVERA, is not seen. Reboot, or:
  ```bash
  sudo systemctl restart navera-discover
  ```
  then restart the services concerned (section 3.0, step 5).

#### What the client may have to set

| Situation | What to set in `navera.env` |
|---|---|
| Several cameras | `NAVERA_CAMERA_DEVICE=/dev/v4l/by-id/…` (the one looking down) |
| Several GPS receivers | `NAVERA_GPS_PORT` (and `NAVERA_GPS_BAUD`) |
| Autopilot on an unusual address (another UDP port, TCP) | `NAVERA_DISCOVER_MAVLINK=udpin:0.0.0.0:14560` (comma-separated list) or directly `NAVERA_VEHICLE_MAVLINK_URL` |
| Several autopilots answer | `NAVERA_VEHICLE_MAVLINK_URL` to choose |
| Network (RTSP) camera | `NAVERA_CAMERA_INPUT=gst` and `NAVERA_CAMERA_GST_PIPELINE` (section 6.4) — not detected automatically |
| ROS vehicle on another domain | see Way C |
| Every vehicle | `NAVERA_MAX_SPEED_KMH`, `NAVERA_WEB_TOKEN`, camera calibration |

#### Overriding "auto"

Any value you **write** in `navera.env` instead of `auto` is always kept; detection only fills
the settings left on `auto` or empty. Examples:

```
NAVERA_SENSOR_SOURCE=vehicle      # attitude from the autopilot (box | vehicle | ros | insta360)
NAVERA_GPS_SOURCE=vehicle         # the autopilot's second GPS (serial | vehicle | ros)
NAVERA_CAMERA_INPUT=csi           # usb | csi | gst | ros | insta360
NAVERA_VEHICLE_MAVLINK_URL=serial:/dev/serial/by-id/usb-FTDI_<serial>-if00-port0:921600
```

#### Seeing what was found

Run the box check (section 7.6). Its first lines say what was found and what was chosen; a line
with **NO** or **CHECK** is a warning. The full report is in `/var/lib/navera/discovery.json`.

> **Never point NAVERA at a position it produces itself:** not the autopilot's fused position,
> not a GPS fed by NAVERA's output, not `/navera/fix`. NAVERA would check its output against itself.

### 3.3 Way C — on a ROS 2 vehicle or network

For a boat, robot or drone whose own computer runs ROS 2: NAVERA can read the vehicle's IMU,
GPS, camera and height topics, and publish its position back as a ROS topic.

#### Joining the vehicle's ROS network

By default NAVERA keeps its ROS traffic **on the box** (`ROS_LOCALHOST_ONLY=1`, domain 42): no
other machine sees it, and none can publish into it. To work with a ROS vehicle, set in
`navera.env`:

```
ROS_LOCALHOST_ONLY=0
ROS_DOMAIN_ID=<the vehicle's domain number>
```

then restart all NAVERA services. Both computers must use **ROS 2 Humble**-compatible versions
and the same middleware (RMW).

- `ROS_DOMAIN_ID=auto` asks detection to join the domain of a ROS vehicle it finds (and to stay
  on 42, box only, if none). This is checked by unit tests only, not on a real vehicle network:
  **writing the domain number is the verified way.**
- A domain number you write is never changed by detection.
- Once joined, **any machine on that network and domain can publish into NAVERA.** Keep that
  network closed.
- A vehicle computer that boots after NAVERA is not found by `auto`: write its topics (below)
  instead of relying on detection.

#### What NAVERA needs from the vehicle's topics (exact contract)

| Setting | Message type | Contract |
|---|---|---|
| `NAVERA_ROS_IMU_TOPIC` (**required** with `NAVERA_SENSOR_SOURCE=ros`) | `sensor_msgs/Imu` | `orientation` = the vehicle body's attitude in **ENU** (x east, y north, z up; body x forward, y left, z up — REP-103), unit quaternion. **Yaw referenced to TRUE north** — NAVERA applies no declination to a ROS IMU; a magnetic or arbitrary yaw (6-axis IMU) gives wrong headings. Time stamps on a clock synchronised with the box. **25 Hz or more** (the check warns below 25 Hz, fails below 10 Hz). 50 identical samples in a row = frozen sensor |
| `NAVERA_ROS_ALTITUDE_TOPIC` (optional) | `sensor_msgs/Range` | height above ground in metres (downward rangefinder); a reading at `min_range` / `max_range` means "no echo" |
| `NAVERA_ROS_GPS_TOPIC` (with `NAVERA_GPS_SOURCE=ros`) | `sensor_msgs/NavSatFix` | a **real receiver** (never the fused position, never `/navera/fix`); altitude above the **WGS84 ellipsoid**; a covariance with a defined type and a sigma of at least 1 cm. Without it the GPS is used as DEGRADED ("uncertainty unknown") and is never sent on as a FIX |
| `NAVERA_CAMERA_TOPIC` (with `NAVERA_CAMERA_INPUT=ros`) | `sensor_msgs/Image` | a camera **looking down**; the image time stamp is taken as the exposure instant (minus `NAVERA_CAMERA_LATENCY_S`) |

Quality of service: NAVERA receives both BEST_EFFORT and RELIABLE publishers.

#### What NAVERA publishes

| Topic | Type | Content |
|---|---|---|
| `/navera/fix` (`NAVERA_ROS_FIX_TOPIC`; set but empty = off) | `sensor_msgs/NavSatFix` | NAVERA's chosen position. A GPS position: status FIX, `status.service` = GPS. A vision / celestial position: status FIX with `status.service` = 0 (no satellites), so a consumer can tell them apart. The accuracy is always in the covariance |
| frame | `header.frame_id` = `NAVERA_ROS_FIX_FRAME_ID` (default `navera`) | set it to a frame of the vehicle's TF tree when a consumer such as `navsat_transform` uses it |

Vision positions **are** sent on `/navera/fix` by default (`NAVERA_ROS_FORWARD_DEGRADED=true`),
always with their accuracy — unlike the autopilot output. Set it to `false` to give ROS "no fix"
for them.

Other topics for monitoring (in the NAVERA shell, appendix B): `/navera/position` (the
arbiter's decision) and `/navera/nav_status` (its state).

---

## 4. Connecting a GPS

NAVERA needs **one real GPS fix at take-off**: it is NAVERA's start position, the point every
vision pipeline searches around. After that the GPS may be jammed or lost for hours — that
is what NAVERA is for — but the vehicle must leave with a GPS fix.

You can plug the GPS in any of the common ways below. With the settings left to `auto` (the
default), NAVERA finds it by itself at every boot, and also when it is plugged in after the
box has started (as long as NAVERA had no GPS yet — a working GPS is never replaced, and the
GPS is never switched while the vehicle is armed).

**NAVERA only listens to your GPS.** It never changes the receiver's configuration, and it
sends nothing on a CAN bus, unless you explicitly allow it (`NAVERA_GPS_CONFIGURE=1`,
`NAVERA_GPS_CAN_ALLOCATE=1`, see below).

ArduPilot parameter names below are those of ArduPilot 4.5 (`GPS_TYPE`, `GPS_TYPE2`); on 4.6 and
later they are `GPS1_TYPE`, `GPS2_TYPE`. Type 14 = "MAV": a GPS fed over MAVLink — that is
NAVERA.

### 4.1 Which connection?

| | Your GPS goes to | NAVERA feeds the autopilot as | Choose it when |
|---|---|---|---|
| **A** | NAVERA (USB or UART), NMEA or u-blox UBX | GPS 1 (`GPS_TYPE=14`) | recommended: NAVERA sees the raw GPS and is the autopilot's only GPS |
| **B** | the autopilot, as its **second** GPS | GPS 1 (`GPS_TYPE=14`) | the GPS must stay on the autopilot |
| **C** | the autopilot, as its **first** GPS (unchanged) | GPS 2 (`GPS_TYPE2=14`) | you cannot change the autopilot's GPS setup |
| **D** | the autopilot (unchanged), plus a Y-cable tap to NAVERA | GPS 2 (`GPS_TYPE2=14`) | as C, without relying on the autopilot's telemetry |
| **E** | a DroneCAN GPS (Here3 / Here4, Holybro DroneCAN…) on a CAN bus NAVERA listens to | GPS 1 or 2 | your GPS is a CAN GPS |
| **F** | the network (NMEA or UBX over TCP / UDP) | GPS 1 | a boat or ground vehicle already shares its GPS on Ethernet |
| **G** | a ROS topic (`sensor_msgs/NavSatFix`) | — (ROS output `/navera/fix`) | a ROS robot or boat |

A and B are the configurations verified with ArduPilot SITL in flight (NAVERA as GPS 1). In C
and D NAVERA reads the GPS correctly (verified in SITL), but whether the autopilot flies on
NAVERA when its own GPS is lost depends on its GPS switching (`GPS_AUTO_SWITCH`), which has not
been verified in flight with NAVERA — prefer A or B for GPS-denied flight.

In every wiring: **NAVERA never uses a GPS it feeds itself** (an autopilot GPS of type 14, or of
type 5 — NMEA — while NAVERA's NMEA output is on). It would be checking its own output against
itself.

---

### 4.2 A — GPS directly to NAVERA (USB or UART)

```
   GPS receiver                         NAVERA box (Jetson)
  ┌────────────┐   USB cable           ┌──────────────────────┐
  │  u-blox /  │══════════════════════>│ USB  (/dev/ttyACM0,  │
  │  any NMEA  │                       │       /dev/ttyUSB0)  │
  └────────────┘                       │                      │      autopilot
        or, on the UART (3.3 V):        │                      │   ┌────────────┐
  GPS TX ─────────────────────────────> │ RX  /dev/ttyTHS1     │   │            │
  GPS RX <───────────────────────────── │ TX                   │   │            │
  GND    ────────────────────────────── │ GND                  │   │            │
  5 V    <───────── power ───────────── │                      │   │            │
                                        │ TELEM UART / USB ════│══>│ TELEM port │
                                        └──────────────────────┘   └────────────┘
                                          NAVERA's position = the autopilot's GPS 1
```

**Automatic:** the port, the baud rate (4800 – 921600) and the protocol. NMEA (with satellite
data) and u-blox UBX (`NAV-PVT`) are both recognised, even mixed. With UBX NAVERA uses the
receiver's own accuracy (`hAcc` / `vAcc`), its velocity and its time. u-blox 6 receivers have no
`NAV-PVT`: use their NMEA output.

**On the autopilot (ArduPilot):** `GPS_TYPE=14` (NAVERA as GPS 1), the MAVLink port to NAVERA,
and the other settings of the ArduPilot integration guide (`EK3_SRC1_VELXY=0`,
`EK3_SRC1_VELZ=0`, `GPS_DELAY_MS`).

**Optional:** `NAVERA_GPS_CONFIGURE=1` lets NAVERA turn on `NAV-PVT` / `NAV-DOP` in a u-blox
that only sends NMEA (in the receiver's RAM only; its saved configuration is not changed).

### 4.3 B — GPS on the autopilot as its second GPS

```
   GPS receiver           autopilot                         NAVERA box
  ┌──────────┐  GPS 2   ┌──────────────────┐  MAVLink      ┌──────────────┐
  │   GPS    │═════════>│ GPS2 port         │<═════════════>│ TELEM link   │
  └──────────┘          │ GPS_TYPE2 = real  │  GPS2_RAW  ──>│ reads GPS 2  │
                        │ GPS_TYPE  = 14    │<── GPS_INPUT  │ feeds GPS 1  │
                        └──────────────────┘               └──────────────┘
```

**Automatic:** NAVERA finds the autopilot (serial, UDP 14550/14551, TCP 127.0.0.1:5760),
reads its GPS types, and uses its second GPS (`GPS2_RAW`) when `GPS_TYPE2` is a real
receiver.

**On the autopilot:** `GPS_TYPE=14` (NAVERA), `GPS_TYPE2` = your receiver's type (1 = auto,
2 = u-blox, 9 = DroneCAN…), `SERIALn_PROTOCOL=5` on the port of the real GPS. To keep the
autopilot on NAVERA only (and not on a GPS NAVERA refused as spoofed): `GPS_AUTO_SWITCH=0`,
`GPS_PRIMARY=0` — weigh it against your failsafe strategy.

### 4.4 C — GPS on the autopilot as its first GPS, NAVERA as GPS 2

```
   GPS receiver           autopilot                         NAVERA box
  ┌──────────┐  GPS 1   ┌──────────────────┐  MAVLink      ┌──────────────┐
  │   GPS    │═════════>│ GPS port          │<═════════════>│ TELEM link   │
  └──────────┘          │ GPS_TYPE  = real  │ GPS_RAW_INT ─>│ reads GPS 1  │
                        │ GPS_TYPE2 = 14    │<── GPS_INPUT  │ feeds GPS 2  │
                        └──────────────────┘               └──────────────┘
```

**Automatic:** NAVERA reads the autopilot's first GPS (`GPS_RAW_INT`) **only while the
autopilot's own `GPS_TYPE` says it is not NAVERA** (not 14). It checks again every 30 s and at
every reconnection, and stops at once if `GPS_TYPE` becomes 14. `NAVERA_GPS_MONITOR_GPS1=0`
forbids this source.

**On the autopilot:** nothing changes for your GPS; `GPS_TYPE2=14` for NAVERA. See the note
above on `GPS_AUTO_SWITCH` (not verified in flight).

### 4.5 D — Passive tap (Y-cable) on the GPS wire to the autopilot

```
   GPS receiver                         autopilot
  ┌────────────┐  TX ─────┬──────────> RX  GPS port (GPS_TYPE = 1 / 2: UBX at 230400)
  │  u-blox    │  RX <────┼─────────── TX
  │            │  GND ────┼──┬──────── GND
  └────────────┘          │  │
                          │  │         NAVERA box
                          └──┼──────>  RX  /dev/ttyTHS1  (or a USB-serial adapter's RX)
                             └──────── GND
                     NAVERA's TX is NOT connected: NAVERA only listens
```

**Automatic:** NAVERA recognises the u-blox binary stream ArduPilot configured (UBX `NAV-PVT`,
usually at 230400 baud) or NMEA, and uses it exactly as in A. It never sends anything to the
receiver — the autopilot stays the only one configuring it.

**On the autopilot:** nothing changes for your GPS; NAVERA's output as `GPS_TYPE2=14` (as C).

**Wiring rules:** connect only the GPS's TX and GND to NAVERA. The voltages must match (the
Jetson's UART is 3.3 V; most GPS modules' TX is 3.3 V). Keep the tap short.

### 4.6 E — DroneCAN GPS (Here3, Here4, Holybro DroneCAN GNSS…)

```
  On the vehicle's CAN bus (shared with the autopilot):

   120 Ω                                                                  120 Ω
    ├────────── CAN H / CAN L ───────────┬───────────────────────────────────┤
    │                                    │                                   │
  ┌─┴────────┐                      ┌────┴──────┐                     ┌──────┴──────┐
  │ Here3 /  │  Fix2 messages ────> │ autopilot │                     │ NAVERA box  │
  │ Here4    │                      │ (node 10) │                     │ can0, listen│
  └──────────┘                      └───────────┘                     │ only        │
                                                                      └─────────────┘
  or alone on NAVERA's CAN bus:     Here3 ═══ CAN ═══ NAVERA (NAVERA_GPS_CAN_ALLOCATE=1)
```

The Jetson's CAN controller needs a CAN transceiver (3.3 V, e.g. SN65HVD230) on the carrier
board's CAN pins, or use a USB-CAN adapter (`slcan:/dev/ttyACM0`, or a SocketCAN adapter that
appears as `can1`). The bus needs a 120 Ω terminator at each end.

**Once, at installation (needs root):** bring the CAN interface up at 1 Mbit/s:

```bash
sudo ip link set can0 up type can bitrate 1000000 restart-ms 100       # now
sudo install -m 0644 deploy/can/80-navera-can0.network /etc/systemd/network/
sudo systemctl enable --now systemd-networkd                           # at every boot
```

**Automatic:** NAVERA listens to every CAN interface that is up for GPS fixes
(`uavcan.equipment.gnss.Fix2`), without a node id — it sends nothing on the bus. The
autopilot's own re-broadcast of its GPS (a node that also commands motors) is never taken.
Several GPS: NAVERA picks one and says so (`NAVERA_GPS_CAN_NODE` to choose).

**A DroneCAN GPS alone on NAVERA's bus** gets no node id (the autopilot normally gives it):
set `NAVERA_GPS_CAN_ALLOCATE=1`, and NAVERA becomes the bus's node-id allocator (it then
transmits, as node 125). The discovery report tells you when a device is waiting for an id.

**On the autopilot:** for a GPS it also uses, nothing changes. NAVERA's output: `GPS_TYPE=14`
if the CAN GPS is the autopilot's second GPS (`GPS_TYPE2=9`, as B), or `GPS_TYPE2=14` if it is
its first (as C).

### 4.7 F — GPS over the network

```
  ship / vehicle network                     NAVERA box
  ┌────────────────────┐  NMEA or UBX       ┌──────────────┐
  │ GPS / NMEA server  │ ── TCP 10110 ────> │ Ethernet     │
  │ (or UDP broadcast) │ ── UDP 10110 ────> │              │
  └────────────────────┘                    └──────────────┘
```

**Automatic, once you give the address** (NAVERA never connects to an address it was not
given): `NAVERA_DISCOVER_GPS_URLS=tcp:192.168.1.50` (its ports 10110, 2000, 4001 are tried),
`tcp:192.168.1.50:5017`, or `udp` / `udp:10110` (NAVERA listens). Or impose it:
`NAVERA_GPS_SOURCE=network`, `NAVERA_GPS_URL=tcp:192.168.1.50:10110`.

### 4.8 G — ROS GPS topic

`NAVERA_GPS_SOURCE=auto` finds a `sensor_msgs/NavSatFix` topic on NAVERA's ROS domain (or set
`NAVERA_GPS_SOURCE=ros`, `NAVERA_ROS_GPS_TOPIC=/your/gps/fix`). Give it a covariance: without
one NAVERA treats the GPS as "uncertainty unknown" (DEGRADED).

---

### 4.9 Imposing the GPS by hand

Write in `/etc/navera/navera.env` instead of `auto` (a written value is always kept):

| Setting | Values |
|---|---|
| `NAVERA_GPS_SOURCE` | `serial`, `network`, `dronecan`, `vehicle` (autopilot GPS 2), `vehicle_gps1` (autopilot GPS 1), `ros` |
| `NAVERA_GPS_PORT`, `NAVERA_GPS_BAUD` | serial port and baud (`serial`) |
| `NAVERA_GPS_URL` | `tcp:<host>:<port>` or `udp:<port>` (`network`) |
| `NAVERA_GPS_CAN_IFACE`, `NAVERA_GPS_CAN_NODE` | CAN interface and node id, 0 = any (`dronecan`) |
| `NAVERA_GPS_CONFIGURE=1` | NAVERA may turn on UBX `NAV-PVT` in the receiver (RAM only) |
| `NAVERA_GPS_CAN_ALLOCATE=1` | NAVERA gives DroneCAN node ids (a GPS alone on its CAN) |
| `NAVERA_GPS_MONITOR_GPS1=0` | never use the autopilot's first GPS |

Then `sudo systemctl restart navera-gps navera-vehicle-link`.

### 4.10 Checking that it works

1. **Before the flight, outdoors, with a clear sky:**
   ```bash
   python3 navera_tools/check_box.py
   ```
   The first lines are the discovery report, e.g.
   `GPS: serial — the receiver on /dev/ttyUSB0 (u-blox UBX)`,
   `GPS: dronecan — DroneCAN GNSS node 124 on can0`,
   `GPS: vehicle_gps1 — the autopilot's first GPS (type 2; NAVERA does not feed it: NAVERA is its second GPS, type 14)`.
   Lines with `NO` or `CHECK` need your attention (no GPS found, several receivers, a CAN
   interface down, a DroneCAN GPS waiting for a node id…). Then the live check must show
   `GPS … fixes` and `NAVERA FIX`.
2. **The full report:** `cat /var/lib/navera/discovery.json` (what was found where), and
   `journalctl -u navera-hotplug` for a GPS connected after boot.
3. **The GPS itself:** `ros2 topic echo /navera/estimate/gps --once` — `valid: true`, your
   position, and a covariance (the receiver's accuracy); `journalctl -u navera-gps -f` shows
   `FIX #…` lines.
4. **The operator page** (`http://<box>:8181/operator`) shows the GPS as the active source
   with its accuracy, before take-off.

If NAVERA found no GPS, the GPS service waits (`journalctl -u navera-gps`: "GPS idle"): plug
the GPS in and wait a few seconds (or up to a minute for a receiver powered after the box, or
a CAN GPS) — with the vehicle **disarmed** if NAVERA is connected to an autopilot.

---

---

## 5. Connecting the autopilot

NAVERA talks to the autopilot in two directions:

| Connection | Direction | What it carries |
|---|---|---|
| **Output** | NAVERA → autopilot | NAVERA's position, as a GPS (MAVLink `GPS_INPUT`, or NMEA) |
| **Vehicle link** | autopilot → NAVERA | attitude, rangefinder, barometric height, second GPS, armed state |

The vehicle link is recommended with any MAVLink autopilot: it also lets the `/mission` page know
when the vehicle is armed (settings are then locked).

### 5.1 Wiring

**One program per serial port.** Choose one of these:

```
 Wiring A — ONE autopilot port (what auto-detection sets up)            [verified in SITL]

   NAVERA box                                         Autopilot
   +---------------------------------------+          +-----------------+
   | navera-output --UDP 14650--+          |          |                 |
   |  (GPS_INPUT)               v          |          |                 |
   |                 navera-vehicle-link --+--TX----->| TELEM RX        |
   |                 (owns the port, relays|<-RX------| TELEM TX        |
   |                  NAVERA's output)     |--GND-----| GND             |
   +---------------------------------------+          +-----------------+
   NAVERA_VEHICLE_MAVLINK_URL=serial:/dev/ttyTHS2:921600
   NAVERA_MAVLINK_URL=udpout:127.0.0.1:14650


 Wiring B — TWO autopilot ports

   NAVERA box                                         Autopilot
   +---------------------------------------+          +-----------------+
   | navera-output       (port 1) ---------+--TX/RX-->| TELEM 1         |
   | navera-vehicle-link (port 2) ---------+--TX/RX-->| TELEM 2         |
   |                               GND ----+----------| GND             |
   +---------------------------------------+          +-----------------+
   NAVERA_MAVLINK_URL=serial:/dev/ttyTHS2:921600
   NAVERA_VEHICLE_MAVLINK_URL=serial:/dev/serial/by-id/<adapter>:921600
```

| Jetson | Autopilot TELEM | |
|---|---|---|
| TX | RX | crossed |
| RX | TX | crossed |
| GND | GND | always |
| — | +5 V | **not connected** (each has its own supply) |

- 3.3 V logic only (Pixhawk-class TELEM ports are 3.3 V TTL — check your autopilot's documentation).
- If RTS/CTS are not wired, turn flow control off on that autopilot port (`BRD_SERn_RTSCTS = 0`).
- Same baud rate on both ends. Use at least 115200; the examples use 921600.
- A USB-to-serial adapter works: use its stable name `/dev/serial/by-id/…`.
- A third way, `mavlink-router` sharing one port, is described in `docs/ARDUPILOT_INTEGRATION.md`
  §6 (not verified).

Address format, the same in every NAVERA MAVLink setting: `serial:/dev/<port>:<baud>`,
`udpin:<ip>:<port>`, `udpout:<ip>:<port>`, `tcp:<ip>:<port>`. `NAVERA_MAVLINK_URL=off` turns the
MAVLink output off.

### 5.2 ArduPilot parameters (MAVLink output, recommended)

Names as in ArduPilot 4.5 (recent firmware: `GPS1_TYPE`, `GPS2_TYPE`, `GPS1_DELAY_MS`). Set
them with your ground station, then reboot the autopilot.

| Parameter | Value | Why |
|---|---|---|
| `GPS_TYPE` (`GPS1_TYPE`) | **14** (MAV) | NAVERA is GPS 1 |
| `SERIALn_PROTOCOL` | **2** (MAVLink 2) | on the TELEM port wired to NAVERA |
| `SERIALn_BAUD` | the NAVERA baud: 921 = 921600, 115 = 115200 | |
| `GPS_AUTO_CONFIG` | **0** | no receiver configuration sent to a "GPS" that is NAVERA |
| `EK3_SRC1_POSXY` | 3 (GPS, default) | position from NAVERA |
| `EK3_SRC1_VELXY` | **0** | do not fuse NAVERA's velocity as a measurement (see the cost below) |
| `EK3_SRC1_VELZ` | **0** | same |
| `EK3_SRC1_POSZ` | 1 (barometer, default) — **never 3** | vision positions carry no altitude; 3 would pull the height to 0 m (simulation: hundreds of metres of error) |
| `EK3_OGN_HGT_MASK` | 0 (default) — **never set** | same reason |
| `GPS_DELAY_MS` | 0 (default) | NAVERA already carries its vision positions to the present |
| `EK3_GLITCH_RAD` | **100 on Copter** (default 25); **default on Plane** | see 5.3 |
| `FS_EKF_ACTION` / `FS_EKF_THRESH` | defaults (1 = LAND, 0.8) | LAND is the safe outcome of a long vision outage on a copter |
| `AHRS_OPTIONS`, `ARSPD_OPTIONS` (Plane) | defaults | changing them made outages worse in simulation |

**The cost of `EK3_SRC1_VELXY = 0` / `VELZ = 0`:** the autopilot no longer fuses GPS velocity
**at any time, also while GPS is good**. Its velocity estimate is noisier and lags more
(position hold, wind estimate). How much this matters for your vehicle has not been measured.

**If the real GPS is wired to the autopilot** (not to NAVERA): make it **GPS 2**
(`GPS_TYPE2` = its real type, e.g. 1 = auto). NAVERA stays GPS 1 and reads GPS 2 through the
vehicle link. To make NAVERA the only GPS the autopilot uses, consider `GPS_AUTO_SWITCH = 0` and
`GPS_PRIMARY = 0`; otherwise the autopilot may switch to the very receiver NAVERA has refused as
spoofed (not verified — weigh it against your failsafe strategy).

**Vehicle link parameters:** on its TELEM port `SERIALm_PROTOCOL = 2` and the same baud. No
stream rates are needed: NAVERA asks for its messages itself.

### 5.3 Copter and Plane recommendations

| | Copter | Plane (with airspeed sensor) |
|---|---|---|
| `EK3_GLITCH_RAD` | **100** — with the default 25 m the autopilot resets onto almost every vision position and drifts (simulation: landings 136–290 m from home → 4–21 m with 100) | default (25) |
| `NAVERA_BRIDGE_MAX_S` (NAVERA side) | **10** (default) — NAVERA bridges a gap in vision positions for 10 s | **0** — the plane dead-reckons better on its airspeed than NAVERA carries a position |
| Longest vision gap survived (simulation) | about **25 s**: then the autopilot stops aiding and **LANDs where it is** | 60 s outages flown (after the 2026-10-21 velocity fix) |

A copter **cannot** fly a GPS-denied gap longer than about 25 s: do not raise
`NAVERA_BRIDGE_MAX_S` to try (simulation: 234 m to 1.4 km off track).

### 5.4 What the autopilot receives, and the failsafe

| Situation | Autopilot receives (default) | With vision forwarding on |
|---|---|---|
| GPS good | NAVERA passes the GPS through: 3D fix | same |
| GPS "in doubt" (vision disagrees) | the GPS, its accuracy made no better than the gap (up to 500 m) | same |
| GPS lost or refused, vision matching | **"no fix"** → the autopilot's own failsafe (Copter LAND, Rover/boat HOLD in simulation) | vision positions with **0 satellites**, the stated accuracy, a velocity, carried to the present |
| Short vision gap | "no fix" | the last position carried along its track, re-sent each second, for `NAVERA_BRIDGE_MAX_S` |
| Nothing usable | "no fix" → failsafe | "no fix" → failsafe |

**An autopilot does not resume its mission by itself after a failsafe**, even when NAVERA has
positions again. The safety pilot takes over.

**To send vision positions to the autopilot** (only after recording flights showed vision
working, section 9.3):

```
NAVERA_FORWARD_DEGRADED=true
NAVERA_DEGRADED_SIGMA_M=<the accuracy you measured, metres, 1 sigma>
```

then `sudo systemctl restart navera-output`.

- The output refuses to start with forwarding on and no accuracy, or an accuracy above 1000 m.
- **ArduPilot caps a stated accuracy at 100 m**: above 100 m it trusts the position **more** than
  stated. Stay at or below 100 m.
- Never state a better accuracy than measured: an autopilot told a position is better than it is
  follows wrong positions or fails safe.
- Arming checks that require satellites must be adapted by you, knowingly (vision reports 0).
- Copter prints **"GPS Glitch or Compass error"** once when vision takes over. It is a status,
  not a failsafe, and it is true: the autopilot is on a ±30 m position.

### 5.5 NMEA output (any system that takes a serial GPS)

```
NAVERA_NMEA_PORT=/dev/ttyTHS2
NAVERA_NMEA_BAUD=9600
```

ArduPilot: `GPS_TYPE = 5` (NMEA), `SERIALn_PROTOCOL = 5` (GPS), `SERIALn_BAUD = 9` (9600),
`GPS_AUTO_CONFIG = 0`, `EK3_SRC1_VELXY = 0`, `EK3_SRC1_VELZ = 0`.

**Use NMEA for GPS pass-through only.** NMEA carries no accuracy: the autopilot would trust a
30 m vision position as a 0.5 m GPS. So with forwarding on, vision positions go over MAVLink
and ROS only, and NMEA says "no fix" for them. Do not turn on `NAVERA_NMEA_FORWARD_DEGRADED`.
With NMEA the port carries no MAVLink: the vehicle link needs its own port.

### 5.6 PX4

**Tested in PX4 SITL only (v1.15.4).** PX4 does not read `GPS_INPUT`: NAVERA sends it the same
position as **`HIL_GPS`**. Detection does this by itself when it sees a PX4 autopilot
(`NAVERA_MAVLINK_MESSAGE=hil_gps`); you set the PX4 side:

| PX4 parameter | Value | Why |
|---|---|---|
| `MAV_USEHILGPS` | 1 | PX4 reads NAVERA's position only then |
| `EKF2_GPS_CTRL` | 1 | position only: no velocity, no height from NAVERA |
| `EKF2_HGT_REF` | 0 | height from the barometer (reboot) |
| `EKF2_GPS_CHECK` | 240 | a vision position has no satellites and a 10–30 m accuracy |
| `EKF2_GPS_V_GATE` | 100 | else PX4 may declare "Navigation failure" during the take-off |
| `COM_POS_FS_EPH` | 25 | else PX4 declares a vision-fed position invalid at 12.5 m |
| `EKF2_NOAID_NOISE` | ≥ `NAVERA_DEGRADED_SIGMA_M` | else PX4 trusts a vision position more than stated |
| `NAV_ACC_RAD` (multicopter) | 25 | waypoint radius larger than the vision error |

The detection report (`check_box.py`) shows a **CHECK PX4 …** line for each wrong value it can
read. NAVERA uses the autopilot's own system id (written by detection): PX4 ignores `HIL_GPS` from
any other id.

When NAVERA has no position for about 5 s (GPS lost with vision withheld, a vision gap, the output
service restarting), PX4 declares its position invalid and starts **its own failsafe** (a
multicopter in a mission descends without position control): configure it. When NAVERA's
positions return, PX4 resumes the mission. NMEA output to PX4: GPS pass-through only (its
sentences carry no accuracy). Details and the simulation results: docs/PX4_INTEGRATION.md.

### 5.7 Checks after wiring

On the ground station: the autopilot's GPS 1 shows a **3D fix** at the vehicle's position while
NAVERA has GPS. Then cut NAVERA's GPS in software:

```bash
sudo systemctl stop navera-gps      # within a few seconds: "no fix" on the ground station
sudo systemctl start navera-gps     # back to 3D fix
```

In the logs (appendix B): `journalctl -u navera-vehicle-link -n 20` shows
"connected to ArduPilot (system 1)" (or PX4); `journalctl -u navera-output -n 20 | grep -i nothing` must be
empty (otherwise the autopilot receives nothing from NAVERA).

Details: `docs/ARDUPILOT_INTEGRATION.md`, `docs/PX4_INTEGRATION.md`.

---

## 6. Cameras

### 6.1 Mounting

- The day camera looks **straight down** (nadir), **top of the image towards the nose**. Then
  `NAVERA_CAMERA_MOUNT_RPY=0,0,0`. Otherwise measure the angles and enter them (roll,pitch,yaw,
  degrees).
- **Multirotor: use a gimbal** that holds the camera level, and set `NAVERA_CAMERA_GIMBAL=true`.
  A fixed camera leans with the drone (30–45° at speed). Pictures tilted more than
  `NAVERA_CAMERA_MAX_TILT_DEG` (45°) are not used.
- **Plane, boat, robot:** a fixed camera is fine. Pictures taken while the vehicle turns faster
  than 30°/s (`NAVERA_CAMERA_MAX_RATE_DPS`) are not used: fly smooth turns.
- Insta360 ONE R **360 module, IRIS kit** (`NAVERA_CAMERA_INPUT=insta360`, section 3.1): lying,
  one lens straight down; the kit cuts a 1200 × 900, 100° straight-down view from it (at 100 m
  height about 240 × 180 m). No crop, no `NAVERA_CAMERA_MOUNT_RPY` (its mount is
  `NAVERA_INSTA360_MOUNT_AXES`).
- Insta360 ONE R in **webcam** mode (`usb`, not the kit): both lenses arrive in one 1920 × 1080
  picture (top and bottom halves). Point one lens straight down and set `NAVERA_CAMERA_CROP=top`
  or `bottom` for it. Its straightened view is 111° × ~37°: at 100 m height it sees about 290 × 80 m.
- Address a USB camera by its **stable name**, not `/dev/videoN` (that number changes with the
  plug order):
  ```bash
  ls -l /dev/v4l/by-id/
  # NAVERA_CAMERA_DEVICE=/dev/v4l/by-id/usb-<maker>_<model>_<serial>-video-index0
  ```

### 6.2 Lens calibration (once per camera and resolution) — required

Without a calibration NAVERA assumes a perfect lens. Before a real test, calibrate. (The Insta360
kit is calibrated differently — its two fisheye lenses on a screen dot grid by IRIS, files copied
in 3.1 step 4; this section is for the other cameras.)

1. Print a **9 × 6** (inner corners) checkerboard. Measure one square in mm. Stick it flat on a
   rigid board.
2. Stop the vision service (it holds the camera):
   ```bash
   sudo systemctl stop navera-pipeline-day
   ```
3. In the NAVERA shell (appendix B):
   ```bash
   python3 navera_tools/calibrate_camera.py \
       --device /dev/v4l/by-id/usb-<maker>_<model>_<serial>-video-index0 --size 1920x1080 \
       --board 9x6 --square-mm <measured> --model fisheye --out /var/lib/navera/camera.yaml
   ```
   - `--model fisheye` for wide lenses (the Insta360); `--model pinhole` for a normal lens.
     **The lens model is required** in the file: a fisheye read as pinhole gives a wrong field of
     view (the Hikvision visible lens: 47° instead of 77°). Files made by this tool include it.
   - 360 module: add the same `--crop top` (or `bottom`) as in `navera.env`.
   - A network or CSI camera: take 20–40 photos of the board with it and use
     `--images <folder>` instead of `--device`.
4. Show the board at **30 positions**: corners and edges of the image, tilted up to ~45°, near
   and far.
5. Accept when the tool reports **RMS < 0.5 px** ("good"). 0.5–1 px is "usable"; above 1 px, redo it.
6. Install it and point NAVERA at it:
   ```bash
   sudo install -m 0644 /var/lib/navera/camera.yaml /etc/navera/camera.yaml
   sudoedit /etc/navera/navera.env      # NAVERA_CAMERA_CALIBRATION=/etc/navera/camera.yaml
   sudo systemctl start navera-pipeline-day
   ```

**A calibration is saved per camera.** The file records the camera's serial name and the
resolution. NAVERA **refuses** it with another camera ("calibrate this camera") — even another
unit of the same model — and at another resolution than `NAVERA_CAMERA_SIZE`.

Without any calibration, `NAVERA_CAMERA_HFOV_DEG` (field of view of an ideal lens, degrees) is
the minimum: the box check fails with neither, and warns with the field of view only.

### 6.3 Camera delay (exposure → picture arrival)

A picture arrives some time after it was taken. A wrong delay puts every vision position off
along the track: **60 m per second of error at 60 m/s**. Measure it once per camera model.

| Method | How |
|---|---|
| Bench (recommended) | `python3 navera_tools/bench/camera_latency.py --device <camera> --calib /etc/navera/camera.yaml` — the camera films a screen that flashes. With `--calib` the result is **saved in that camera's calibration file** and used whenever `NAVERA_CAMERA_LATENCY_S=0` |
| On the vehicle | film a phone stopwatch while recording. With `NAVERA_CAMERA_LATENCY_S=0`, the difference "picture stamp − time shown" is the delay (`docs/FIELD_TEST_PROCEDURE.md` §6) |
| Set by hand | `NAVERA_CAMERA_LATENCY_S=<seconds>` — a value written here wins over the calibration file |

Measured values: Insta360 ONE R 360 module, USB webcam mode **0.14 s**; the Insta360 kit
stamps each picture at its exposure on the camera's IMU clock (`NAVERA_CAMERA_LATENCY_S` stays 0);
Hikvision over RTSP
about 1.0 s (bench). While GPS is trusted, day vision also estimates the delay itself and
corrects it only when its estimate is stable and clearly different.

### 6.4 Supported camera inputs

| `NAVERA_CAMERA_INPUT` | Camera | Notes |
|---|---|---|
| `usb` | a USB (UVC) camera, e.g. the **Insta360 ONE R in USB webcam mode** | detected automatically |
| `csi` | a Jetson CSI camera (through GStreamer `nvarguscamerasrc`); `NAVERA_CAMERA_DEVICE` = sensor id (0) | detected automatically; supported in code, not tested with a real CSI camera |
| `gst` | any GStreamer source: a network (RTSP) camera, a gimbal's video stream | **not detected automatically**; the pipeline must end in `appsink name=sink` with BGR |
| `ros` | a `sensor_msgs/Image` topic of the vehicle | must look down (section 3.3) |
| `insta360` | the IRIS kit: Insta360 ONE R in USB "Android" mode, read by `navera-insta360` (straight-down view + IMU) | detected automatically (USB id `2e1a:0002`); section 3.1 |

RTSP example (Hikvision URL format; thermal channel 201 on the DS-2TD2617B-3/PA bench unit —
check your camera's own URL). Keep the quotes:

```
NAVERA_CAMERA_INPUT=gst
NAVERA_CAMERA_GST_PIPELINE="rtspsrc location=rtsp://<user>:<password>@<camera-ip>:554/Streaming/Channels/201 latency=0 ! rtph264depay ! video/x-h264,stream-format=byte-stream,alignment=au ! nvv4l2decoder ! nvvidconv ! video/x-raw,format=BGRx ! videoconvert ! video/x-raw,format=BGR ! appsink name=sink drop=true max-buffers=1 sync=false"
```

The box decodes H.264 / H.265 in hardware (`nvv4l2decoder`) and has no `h264parse` or software
decoder, so a pipeline with `decodebin` finds no decoder for an RTSP camera and never delivers a
frame (measured 2026-10-22 in the hardware-in-the-loop test). Keep the byte-stream caps shown;
an H.265 camera: `rtph265depay ! video/x-h265,stream-format=byte-stream,alignment=au ! nvv4l2decoder`.

Other camera settings: `NAVERA_CAMERA_SIZE` (default 1920x1080; must be a mode the camera
delivers), `NAVERA_CAMERA_FPS` (pictures offered per second, default 1).

The Insta360's full-360 "Android" USB stream (both lenses and the camera's own IMU) is read at
boot by `navera-insta360` (`NAVERA_CAMERA_INPUT=insta360`, section 3.1). Only one program can
hold the camera: not with IRIS's field tools, and not in webcam mode.

### 6.5 Night: thermal camera

- The night pipeline replaces the day pipeline (they never run together). It uses the **same
  camera settings** (`NAVERA_CAMERA_*`): for night, point them at the thermal camera and its
  own calibration.
- Switch to night:
  ```bash
  sudo sed -i 's/^NAVERA_PIPELINE=.*/NAVERA_PIPELINE=night/' /etc/navera/navera.env
  sudo systemctl disable --now navera-pipeline-day
  sudo systemctl enable --now navera-pipeline-night
  sudo systemctl restart navera-web
  ```
- Night vision needs an independent height after GPS loss: a barometer
  (`NAVERA_SENSOR_SOURCE=vehicle`) or a rangefinder.
- Status: **not flown**. On real aerial thermal imagery a 640-pixel camera gave a position on
  28–38 % of frames at 700–1000 m (10–12 m median); a 160 × 120 camera is too coarse.

### 6.6 Stars: celestial navigation (experimental)

- Without a star camera configured, the celestial service plays a **sample sky** (demonstration).
- A real star camera: set `NAVERA_STAR_CAMERA_INPUT` and the other `NAVERA_STAR_CAMERA_*` settings
  (appendix A). It needs the IMU and a **trusted time** (1 s of clock error = ~0.5 km).
- **Time for the stars** (no battery clock needed). Operating rule: the GPS is good at take-off.
  NAVERA then takes the GPS receiver's UTC (only while the arbiter trusts the GPS: not refused,
  not suspected of spoofing) and keeps it with the box's own steady clock for the rest of the
  flight, however long the GPS is lost; its stated uncertainty grows slowly (0.5 s + 20 ppm of the
  time since: ~0.7 s after 3 h). In order, NAVERA uses: this **GPS time anchor** > the
  **autopilot's time** (MAVLink `SYSTEM_TIME`, which ArduPilot sets from its GPS) > a **DS3231**
  if fitted > the network time (NTP). The GPS anchor and the autopilot's time must agree within
  1 s; otherwise no star fix is made (one of them is wrong — a spoofed GPS can fake the time too)
  and the log says so. A later GPS time that jumps away from the anchor is ignored and logged.
  Without any of them, no star fix: never on a guessed clock. `/navera/time_status` shows the
  source and its uncertainty.
- **If the box reboots in flight with the GPS denied**, the GPS anchor is lost (it is not kept
  across a reboot: there is no battery clock to carry it). NAVERA then uses the autopilot's
  time (the autopilot keeps it while powered), or the DS3231 if one is fitted; with neither, the
  star navigation stays off until the GPS comes back.
- Accuracy: kilometres (24–119 km with a BNO085-class IMU in simulation). Never sent to the
  autopilot (coarser than 1 km).

Details: `deploy/README.md` §4 and §10, `docs/FIELD_TEST_PROCEDURE.md` §2.

---

## 7. Before each mission

### 7.1 Why: NAVERA is offline in flight

Day vision only matches against the **map of the route** that is active on the box. That map
must be prepared **before departure**, on the ground, with internet if tiles must be downloaded.
In flight NAVERA needs no network at all.

### 7.2 The map: age, resolution, licence

| Rule | Why |
|---|---|
| **Imagery less than 5 years old** | Day vision fails where the ground changed. In simulation a 3-year-old map matched 96 % of pictures, an 8-year-old one 0 %. The tool warns above 5 years, or when the date is unknown |
| **Real resolution 2 m or finer** | Measured on real drone photos: 2 m kept 84–89 % of matches, 3 m about 63–75 %, 5 m was marginal, **10 m (free Sentinel-2) does not work**. The map is stored at zoom 17 (~1 m per pixel), but NAVERA cannot tell if the imagery behind it was upscaled: check the real resolution with your imagery supplier |
| **The licence must allow storing the tiles offline in a product** | Many public tile services forbid it. **Esri World Imagery may be used for evaluation and development only**, not on a delivered product. Free 10 m imagery is legal but too coarse. A ~1 m product map needs a commercial licence (or the client's own licensed imagery) |
| **Avoid long stretches with no landmarks** | Sea, lakes, sand, uniform fields: nothing to match. Prefer a route over varied ground or along a coast |

The delivered map covers **Sousse only**. For any other area you need tiles for the route.

### 7.3 Preparing the map on the web page (`/mission`)

Open `http://<box-ip>:8181/mission` and enter the access code (`NAVERA_WEB_TOKEN`).

1. **Import** the autopilot's mission file, or draw the route on the map.
2. Read the **terrain warning**: the stretches without landmarks.
3. **Generate** the map of the route corridor. Tiles come from the onboard map; missing tiles are
   downloaded from `NAVERA_TILE_URL` if it is set (internet needed now, licence checked first).
4. **Activate** the map. Day vision restarts on it.

"Generate", "Activate" and "Apply settings" are **refused** while the vehicle is armed, moving
faster than 1.5 m/s, or navigating without GPS. Prepare on the ground.

The page can also set: vehicle type, maximum speed, IMU mounting, magnetic declination, and the
field of view for replayed pictures. **It does not set the camera, the sources, the outputs or
the network**: those are in `navera.env`.

### 7.4 The complete offline package (`mission_bundle.py`)

The mission package holds everything a mission needs offline, with a checksum for every file:
the corridor map, the day-vision data made from it, terrain heights, the time table and star
catalogue for celestial, optionally the model weights. **This is a command-line tool today; the
web page does not run it yet.** In the NAVERA shell:

```bash
# 1. estimate: tiles, size, time, warnings (licence, map age, height) — nothing downloaded
python3 navera_tools/mission_bundle.py plan --start 35.8256,10.6385 --dest 35.6781,10.0963 \
    --corridor-m 2000 --max-height-m 600 --source onboard
# 2. build (asks for confirmation)
python3 navera_tools/mission_bundle.py build /data/bundles/<mission> <same options>
# 3. prove it works with the network OFF
python3 navera_tools/mission_bundle.py check /data/bundles/<mission>
# 4. the settings that point NAVERA at it — copy them into /etc/navera/navera.env
python3 navera_tools/mission_bundle.py env /data/bundles/<mission>
```

- Route input: start and destination, `--waypoint lat,lon` (repeat), or `--route-file` (GPX, KML,
  JSON, Mission Planner `.waypoints`, QGroundControl `.plan`).
- `--corridor-m`: the full width the vehicle may stray in. `--max-height-m`: the highest flight height.
- Tile sources: `onboard`, `xyz:<URL>` (a licence statement is required), `mbtiles:<file>`,
  `esri` (evaluation only).
- `check` must end in **PASS** (exit code 0). Measured: a 51.7 km route, ±1 km corridor, built in
  about 5 minutes, 454 MB.

### 7.5 Start without GPS

Where there is **no GPS at all** at power-on, the `/mission` page's **Start without GPS** gives day
vision a search area (latitude, longitude, accuracy 5–20 000 m, or the route's departure). It is
never sent as a position: NAVERA gives a position only once vision matches. Night and celestial
do not use it. Not tested in flight. The autopilot still needs its own origin.

### 7.6 Check the box (every time)

1. The pre-flight check, camera included, with the vision service stopped (in the NAVERA shell):
   ```bash
   sudo systemctl stop navera-pipeline-day
   python3 navera_tools/check_box.py --camera
   sudo systemctl start navera-pipeline-day
   ```
2. Wait ~30 s, then with everything running:
   ```bash
   python3 navera_tools/check_box.py
   ```
   It gives **PASS / WARN / FAIL** per item and **READY** when there is no FAIL: what detection
   found, serial ports used twice, MAVLink addresses, the camera settings and calibration,
   forwarding settings, ROS network, the map opens and the route map is prepared, the topics and
   their rates.
3. Optional, from any account: `deploy/check_boot.sh` — every service active, restarts, swap,
   clock, then the same pre-flight check.
4. On the web operator view (`http://<box-ip>:8181/operator`): the badge shows **GPS · FIX**.

**Fly only with READY.** Read every WARN.

Also before each flight:

- [ ] `NAVERA_MAX_SPEED_KMH` is right for this vehicle.
- [ ] The route map is generated and **activated** (or the mission package installed).
- [ ] Camera clean, looking down, gimbal on (multirotor).
- [ ] GPS fix on the box and on the autopilot.
- [ ] The clock line says `valid: true`.
- [ ] You know whether vision forwarding is on (`NAVERA_FORWARD_DEGRADED`) and what the autopilot
      will do on GPS loss.

---

## 8. In flight

### 8.1 What the operator sees

Open `http://<box-ip>:8181/operator` (`https://` when a certificate is configured) on a laptop
or tablet on the vehicle's network. It shows:

- a **badge** with the source and the state, e.g. `GPS · FIX · ±3 m`, `VISION · DEGRADED · ±30 m`,
  `NO FIX`, `STARTING`, `OFFLINE`;
- the position (latitude, longitude) and its trace on the map, coloured by source;
- a detail line: how the position was obtained, its age ("photo 1.4 s old, carried to now"),
  the reason when there is no position, and camera warnings (e.g. "% of the last minute's frames
  unusable: the vehicle turns too fast for a fixed camera").

The dashboard is at `http://<box-ip>:8181/`. Keep port 8181 inside the vehicle's own network.

The web page is **not needed** for NAVERA to work: NAVERA runs on its own from power-on.

### 8.2 States

| State | Meaning | What the autopilot does |
|---|---|---|
| **FIX** | a fresh measured position with a stated accuracy of 25 m or better. **Today only GPS reaches it** | flies on the GPS that NAVERA passes through |
| **DEGRADED** | a position exists, but it comes from vision or stars, or is carried between matches, or its accuracy is unknown or above 25 m, or the GPS is "in doubt" (vision disagrees with it) | **by default receives "no fix" for vision positions → its own failsafe** (Copter LAND, Rover/boat HOLD). With forwarding on: flies on NAVERA's vision positions with their stated accuracy. A GPS in doubt is still passed on, with a worse accuracy |
| **NO FIX** | nothing usable (no GPS, no match, dead-reckoning limit of 2 min / 500 m reached) | "no fix" → failsafe |
| **STARTING** | NAVERA is starting | — |
| **OFFLINE / LINK LOST** | the web page cannot reach NAVERA (not the vehicle's state) | unaffected by the web page |

### 8.3 What happens when GPS is jammed or spoofed

- **Jammed (lost):** vision takes over at once (DEGRADED). The position follows the camera's
  matches; between matches it is carried along the track, its accuracy growing, for at most
  2 minutes / 500 m.
- **Spoofed by a jump:** a GPS position the vehicle could not reach (`NAVERA_MAX_SPEED_KMH`) is
  refused at once.
- **Spoofed slowly:** when vision disagrees with the GPS, NAVERA first marks it **in doubt**, then
  refuses it (simulation: refused after about 140 m of drift). This needs vision matches; over sea
  or uniform ground a slow spoof is not caught.
- A refused GPS comes back only when 2 independent vision positions agree with it.

### 8.4 Rules for the operator

- Do not change NAVERA in the air: the web page refuses it while armed, moving or without GPS.
  (Saving settings is allowed; they apply at the next "Apply" on the ground.)
- A GPS-denied flight on NAVERA's positions: only after recording flights showed vision working,
  over textured land, **with a safety pilot** able to take manual control. Abort on the first
  autopilot failsafe or position jump.

---

## 9. After the flight

### 9.1 Logs

Every service writes to the system journal. They are kept on the box (capped at 1 GB).

```bash
journalctl -u navera-estimator --since "1 hour ago"      # the arbiter's decisions
journalctl -u navera-pipeline-day --since "1 hour ago"   # every picture: matched, or why not
journalctl -u navera-output --since "1 hour ago"         # what was sent to the autopilot
journalctl -b -u 'navera-*' --no-pager > ~/flight_$(date +%F_%H%M).txt   # everything since boot, to a file
```

The autopilot's own log (dataflash) records what it received from NAVERA as its GPS 1.

### 9.2 Recordings

**NAVERA does not record flights automatically.** To record (camera pictures, sensors,
NAVERA's decisions — everything needed to replay and measure the flight), start the recorder
before take-off in the NAVERA shell, and stop it with Ctrl-C after landing. One new folder per
flight, on the data disk:

```bash
sudo install -d -o navera -g navera /data/navera/rec        # once
navera_tools/record_session.sh /data/navera/rec/flight1 day   # day | night | cn
```

Size: about 6 MB per camera picture, i.e. ~22 GB per hour at 1 picture/s. Copy recordings off
the box and delete them to keep space.

### 9.3 Measuring accuracy (the first campaign)

1. Turn on **shadow mode** so vision also runs while GPS is good:
   `NAVERA_SHADOW_MODE=true` in `navera.env`, then `sudo systemctl restart navera-pipeline-day`.
2. Keep `NAVERA_FORWARD_DEGRADED` off: the autopilot flies on GPS.
3. Record each flight (9.2). Suggested legs: 100 m slow; 150 m cruise; 250 m cruise; 150 m with
   turns, climb, descent; one leg over uniform ground.
4. After the flight:
   ```bash
   python3 navera_tools/evaluate_session.py /data/navera/rec/flight1
   ```
   It gives the vision error against GPS (median, p90), the pictures with no position, and the
   **"honest sigma"**. Use that value for `NAVERA_DEGRADED_SIGMA_M` if you later forward vision.
5. At the end of the campaign set `NAVERA_SHADOW_MODE=false` and restart the pipeline.

Full procedure: `docs/FIELD_TEST_PROCEDURE.md`.

---

## 10. Troubleshooting and limits

First run `python3 navera_tools/check_box.py` (NAVERA shell). Then look at the service's journal
(`journalctl -u <service> -n 100`). The full list is `docs/TROUBLESHOOTING.md`.

### 10.1 Common problems

| Symptom | Likely cause | Fix |
|---|---|---|
| Vision service keeps restarting, "cannot open the camera" | wrong device (number changed), camera not in webcam mode, unplugged, or held by another program | use the `/dev/v4l/by-id/` name; set the camera to USB webcam mode; stop the vision service before calibrating |
| "set NAVERA_CAMERA_CALIBRATION … or at least NAVERA_CAMERA_HFOV_DEG" | no lens information | calibrate (6.2) |
| "calibration … was made with camera usb-A…, this one is usb-B…" | another camera plugged in | calibrate this camera |
| "calibration is for 1280x720, the camera is set to 1920x1080" | resolution changed | calibrate at `NAVERA_CAMERA_SIZE` |
| "camera tilted 52 deg from vertical (max 45)" | fixed camera on a multirotor at speed; gimbal not declared; wrong mounting angles | fit a gimbal + `NAVERA_CAMERA_GIMBAL=true`; fly slower; set `NAVERA_CAMERA_MOUNT_RPY` / `NAVERA_IMU_MOUNT_RPY` |
| "vehicle turning 45 deg/s at the exposure (max 30)" | fixed camera, sharp turns | smoother turns, or a gimbal |
| "no attitude at the frame's exposure" | no attitude source for a fixed camera; the kit: `navera-insta360` down, the camera unplugged / not in Android mode | the kit: `journalctl -u navera-insta360 -n 50`, `lsusb` must show `2e1a:0002`; else `NAVERA_SENSOR_SOURCE=vehicle` and a working vehicle link; or a gimbal; a BNO085 if fitted: wiring (pins 27/28, 3.3 V) |
| `navera-insta360`: "Insta360 not found in USB mode 'Android'" / "Access denied" | the camera in webcam mode, unplugged, or the udev rule missing | camera menu: USB mode Android; `sudo install -m 0644 deploy/udev/99-insta360.rules /etc/udev/rules.d/`, replug |
| `navera-insta360`: "Resource busy" | another program holds the camera (IRIS's field server `navera-field`) | `sudo systemctl disable --now navera-field` |
| Wrong heading | a ROS IMU with magnetic yaw; a BNO085 with no position yet and no declination; gyro-carried heading expired (no match for long) | the ROS IMU must give true north; set `NAVERA_DECLINATION_DEG`; route over textured ground |
| "no position prior (waiting for a GPS fix)" | no GPS fix at start | get a fix (clear sky); or "Start without GPS" (7.5) |
| "no GPS found … GPS idle" | no receiver detected at boot | connect it, `sudo systemctl restart navera-discover navera-gps`; or write `NAVERA_GPS_SOURCE` and its port |
| GPS always "uncertainty unknown" | the GPS gives no accuracy (ROS fix without covariance, autopilot without `h_acc`) | publish the receiver's accuracy at the source |
| "GPS refused: implausible jump …" with a real GPS | `NAVERA_MAX_SPEED_KMH` too low | set the right speed |
| Day vision "no map tiles in the search circle" | route map not generated/activated, or vehicle outside it | `/mission`: Generate, Activate |
| Day vision "too few features in the frame" | sea, desert, uniform fields, blur, darkness, fog | a known limit: route over textured ground |
| "dead-reckoning limit 120s reached" | no match for a long time | intended: the position is withdrawn rather than guessed |
| Autopilot receives "no fix" without GPS | vision forwarding is off (the default) | intended; see 5.4 |
| "the autopilot receives NOTHING from NAVERA" (every 30 s) | output goes through the vehicle link, which is not connected | fix the vehicle link (wiring, baud, `SERIALn_PROTOCOL = 2`) |
| "no heartbeat from an autopilot on …" | wrong port or baud; TX/RX not crossed; port not MAVLink; only a ground station on that link | check wiring and parameters (5.1, 5.2) |
| Web page: "refused: the vehicle is armed" / "moving" / "navigating without GPS" | intended lock | disarm and stop; apply on the ground |
| Web page: "control disabled: set NAVERA_WEB_TOKEN" | no access code configured | set it, `sudo systemctl restart navera-web` |
| "too many wrong codes from this address" | 5 wrong codes in 60 s | wait 60 s |
| A service "activating (auto-restart)" with "could not convert string to float: ''" | a number setting left empty | give it a value or comment it out |
| "… does not exist (data disk not mounted?)" | data disk missing | mount `/data`; the service retries (every 30 s after a few tries) |
| "restart loop: N starts in 60 s — waiting …" | a service fails at every start | its journal says why (`journalctl -u <service> -n 100`); it keeps retrying by itself |
| A NAVERA service crashed in flight (journal: "process has died", "respawning", "restart: …") | a bug or the memory killer | nothing to do: it is back within seconds. Meanwhile the output keeps giving the autopilot the last vision position carried along its velocity, its accuracy growing ("bridging", at most 10 s); a restarted output resumes from what it last sent; a GPS refused for spoofing stays refused. Known limit (simulation): a restarted day vision service may not find its position again within those 10 s — the autopilot's own failsafe then acts. If the restarts repeat, report the journal |
| ROS topics invisible | the shell is not on NAVERA's domain; `ROS_LOCALHOST_ONLY=1`; different domain or ROS version on the vehicle | open the NAVERA shell; Way C settings (3.3) |
| A sensor plugged in after boot is not used | detection runs once per boot | `sudo systemctl restart navera-discover`, then the services |

### 10.2 Limits — what NAVERA cannot do (this release)

| Limit | What it means for you |
|---|---|
| **Not flown, not on a real autopilot** | Treat every figure as provisional. First campaign: shadow mode, GPS in charge |
| **Sea and water** | No landmarks. Away from the coast a boat gets at most the 2-minute dead-reckoning, then nothing. A low camera on a boat has **not been tested at all** |
| **Uniform ground** (desert, sand, large fields, lakes) | Few or no matches; slow GPS spoofing is not detected there |
| **Fog, low cloud, haze, smoke** | The camera does not see the ground: no matches |
| **Old maps** (over 5 years) | Matches fail where the ground changed (8-year-old map: 0 % in simulation) |
| **Coarse maps** (worse than 2 m) | 10 m imagery does not work; 5 m is marginal |
| **Night without a thermal camera** | The day camera sees nothing in the dark: no vision position. Night vision needs a thermal camera and is not flown yet |
| **Stars** | Experimental, accuracy in kilometres, never sent to the autopilot |
| **No inertial navigation** | Without matches, at most 2 minutes / 500 m of dead-reckoning |
| **Copter vision gaps** | About 25 s without positions → the autopilot lands where it is |
| **Fixed camera on a fast multirotor** | Pictures too tilted: fit a gimbal |
| **One vision pipeline at a time** | Day or night, not both (8 GB memory) |
| **PX4** | GPS pass-through over NMEA only; no vision positions |
| **Map coverage** | Delivered map: Sousse only. Other areas need their own map, with a licence that allows offline use |
| **Detection once per boot** | Late devices or vehicle computers are not seen |

---

## Appendix A — Settings you may change (`/etc/navera/navera.env`)

Edit with `sudoedit /etc/navera/navera.env`, then restart the services (section 3.0, step 5).
A commented-out line (`#`) means "use the default". The `/mission` page writes a few of these keys
(marked *web*) to `/var/lib/navera/settings.env`, which overrides `navera.env`.

**Vehicle**

| Setting | Default | Meaning |
|---|---|---|
| `NAVERA_MAX_SPEED_KMH` *web* | none (a warning; internal defaults apply) | top speed + 50 %, km/h (4–1890). **Set it** |
| `NAVERA_VEHICLE_TYPE` *web* | drone | drone, plane, boat, robot, other (label used by the box check) |
| `NAVERA_GROUND_ALTITUDE_M` | first GPS fix | take-off site elevation above the WGS84 ellipsoid, m |

**Sources** (section 3)

| Setting | Default | Meaning |
|---|---|---|
| `NAVERA_SENSOR_SOURCE` | auto | attitude: box, vehicle, ros, insta360 (the kit's own IMU, 3.1) |
| `NAVERA_GPS_SOURCE` | auto | GPS: serial, vehicle, ros (none = found nothing) |
| `NAVERA_GPS_PORT` / `NAVERA_GPS_BAUD` | found by auto (serial: /dev/ttyTHS1, 9600) | box receiver port and speed |
| `NAVERA_VEHICLE_MAVLINK_URL` | found by auto | autopilot address for the vehicle link |
| `NAVERA_ROS_IMU_TOPIC`, `NAVERA_ROS_ALTITUDE_TOPIC`, `NAVERA_ROS_GPS_TOPIC` | empty | vehicle ROS topics (3.3) |
| `NAVERA_DISCOVER_MAVLINK` | empty | extra MAVLink addresses for detection to try |
| `NAVERA_DISCOVER_ROS_DOMAINS` | empty | extra ROS domains for detection to look at |
| `NAVERA_IMU_MOUNT_RPY` *web* | 0,0,0 | BNO085 mounting (if fitted), roll,pitch,yaw degrees |
| `NAVERA_DECLINATION_DEG` *web* | none | BNO085 only: magnetic declination (east +) used until the first position |

**ROS network**

| Setting | Default | Meaning |
|---|---|---|
| `ROS_DOMAIN_ID` | 42 | NAVERA's ROS domain; the vehicle's number, or auto (3.3) |
| `ROS_LOCALHOST_ONLY` | 1 | 1 = box only; 0 to join a vehicle's network |

**Day camera** (section 6)

| Setting | Default | Meaning |
|---|---|---|
| `NAVERA_CAMERA` | replay | **live** for the real camera |
| `NAVERA_CAMERA_INPUT` | auto | usb, csi, gst, ros, insta360 (the kit, 3.1) |
| `NAVERA_CAMERA_DEVICE` | found by auto (/dev/video0) | the `/dev/v4l/by-id/…` name; CSI: sensor id |
| `NAVERA_CAMERA_GST_PIPELINE` | — | GStreamer source for gst (in quotes) |
| `NAVERA_CAMERA_TOPIC` | /vehicle/camera/image_raw | image topic for ros |
| `NAVERA_CAMERA_SIZE` | 1920x1080 | resolution |
| `NAVERA_CAMERA_CROP` | none | top, bottom, left, right or x,y,w,h (360 camera) |
| `NAVERA_CAMERA_FPS` | 1 | pictures per second offered to vision (0.05–30) |
| `NAVERA_CAMERA_CALIBRATION` | empty | lens calibration file (**required before a real test**) |
| `NAVERA_CAMERA_HFOV_DEG` | empty | field of view when there is no calibration (5–170) |
| `NAVERA_CAMERA_MOUNT_RPY` | 0,0,0 | camera mounting; 0,0,0 = straight down, image top to the nose |
| `NAVERA_CAMERA_GIMBAL` | false | true when a gimbal holds the camera level |
| `NAVERA_CAMERA_MAX_TILT_DEG` | 45 | pictures tilted more are not used (5–80) |
| `NAVERA_CAMERA_MAX_RATE_DPS` | 30 | fixed camera: pictures taken while turning faster are not used (1–360) |
| `NAVERA_CAMERA_LATENCY_S` | 0 (= value in the calibration file) | camera delay, seconds (0–2) |

**Insta360 kit** (section 3.1; `navera-insta360`)

| Setting | Default | Meaning |
|---|---|---|
| `NAVERA_INSTA360_MOUNT_AXES` | +x,+z,-y | the camera's IMU axes along the vehicle's x (forward), y (left), z (up); default: lying, left lens down, camera top to the nose |
| `NAVERA_INSTA360_MOUNT_RPY` | 0,0,0 | small trim after the axes, roll,pitch,yaw degrees (±30) |
| `NAVERA_INSTA360_VIEW_SIZE` | 1200x900 | the straight-down view's size |
| `NAVERA_INSTA360_VIEW_HFOV_DEG` | 100 | its width, degrees (30–140) |
| `NAVERA_INSTA360_LENS` | /var/lib/navera/insta360_lens.json | the 360 lenses' calibration |
| `NAVERA_INSTA360_IMU` | /var/lib/navera/insta360_imu.json | the IMU's 6-position calibration |

**Vision pipelines**

| Setting | Default | Meaning |
|---|---|---|
| `NAVERA_PIPELINE` | day | day, night, cn — which one the web page follows (6.5) |
| `NAVERA_SHADOW_MODE` | false | true: vision also runs while GPS is good (recording flights) |
| `NAVERA_DAY_MATCHER` | auto | auto (learned, SIFT fallback), learned, local, retrieval |
| `NAVERA_DAY_HFOV_DEG` *web* | none | field of view of **replayed** pictures only (not the live camera) |
| `NAVERA_THERMAL_HFOV_DEG` *web* | none | thermal field of view for pictures that do not state it |
| `NAVERA_STAR_CAMERA_INPUT`, `_DEVICE`, `_SIZE`, `_FPS`, `_CALIBRATION`, `_HFOV_DEG`, `_GST_PIPELINE` | unset (sample sky) | a live star camera (experimental) |
| `NAVERA_STAR_CAMERA_ELEVATION_DEG` / `_AZIMUTH_DEG` | 90 / 0 | star camera pointing |
| `NAVERA_MAGNETIC_DECLINATION_DEG` | 0 | celestial only, for an attitude source in magnetic north; leave unset with the box IMU |
| `NAVERA_ATTITUDE_SIGMA_DEG` | unknown | IMU attitude accuracy (sets the celestial accuracy) |

**Output to the vehicle** (section 5)

| Setting | Default | Meaning |
|---|---|---|
| `NAVERA_MAVLINK_URL` | decided by auto | MAVLink `GPS_INPUT` address; `off` = never (PX4) |
| `NAVERA_MAVLINK_SYSID` | the autopilot's (auto), else 1 | MAVLink system id NAVERA uses |
| `NAVERA_NMEA_PORT` / `NAVERA_NMEA_BAUD` | empty (off) / 9600 | NMEA GPS output |
| `NAVERA_FORWARD_DEGRADED` | false | true: send vision positions to the autopilot (MAVLink) |
| `NAVERA_DEGRADED_SIGMA_M` | none | **required** with forwarding: measured accuracy, m (≤ 100 for ArduPilot) |
| `NAVERA_NMEA_FORWARD_DEGRADED` | false | keep false |
| `NAVERA_ROS_FIX_TOPIC` | /navera/fix | ROS output topic; set but empty = off |
| `NAVERA_ROS_FIX_FRAME_ID` | navera | frame of `/navera/fix` |
| `NAVERA_ROS_FORWARD_DEGRADED` | true | vision positions on `/navera/fix` |
| `NAVERA_MAX_MEASUREMENT_AGE_S` | 5.0 | older positions are not sent |
| `NAVERA_BRIDGE_MAX_S` | 10 | bridge a vision gap this long; 0 on a plane with airspeed sensor |

**Maps and data**

| Setting | Default | Meaning |
|---|---|---|
| `NAVERA_MBTILES` | /data/navera/sousse_satellite.mbtiles | the onboard map |
| `DAY_DATASET_DIR` | /data/navera/day_dataset | the active route map (set by "Activate" or a mission package) |
| `NAVERA_AREAS_DIR` | /data/navera/areas | where `/mission` generates route maps |
| `NAVERA_TILE_URL` | empty | XYZ tile service for missing tiles (check the licence) |
| `NAVERA_TILE_CACHE` | /data/navera/areas/downloaded_tiles.mbtiles | downloaded tiles |
| `NAVERA_STHN_DIR`, `NAVERA_STHN_WEIGHTS` | /data/navera/STHN/… | night model |
| `TORCH_HOME` | /data/navera/torch_cache | model cache (filled once with internet) |
| `NAVERA_STATE_DIR` | /var/lib/navera | state kept across a restart in flight |

**Web page and system**

| Setting | Default | Meaning |
|---|---|---|
| `NAVERA_WEB_TOKEN` | empty (read-only) | access code for every control action |
| `NAVERA_TLS_CERT` / `NAVERA_TLS_KEY` | empty (plain HTTP) | HTTPS certificate and key (recommended with a token) |
| `NAVERA_WEB_PORT` | 8181 | keep 8181 on a box |
| `NAVERA_LOG_MAX_MB` / `NAVERA_MIN_FREE_MB` | 1024 / 2048 | ROS log folder cap / free-space warning |
| `NAVERA_SWAP_MB` / `NAVERA_MIN_SWAP_MB` | 8192 / 4096 | swap file the installer makes / warning level |

---

## Appendix B — Useful commands

**The NAVERA shell.** Commands without `sudo` in this manual (`check_box.py`, `calibrate_camera.py`,
`record_session.sh`, `mission_bundle.py`, `ros2 …`) run in a shell with the services'
environment. Open it with:

```bash
sudo -u navera -H bash
source /opt/ros/humble/setup.bash
source /home/navera/isaac_ros_common/install/setup.bash
set -a; . /etc/navera/navera.env; . /var/lib/navera/settings.env 2>/dev/null; . /var/lib/navera/discovered.env 2>/dev/null; set +a
cd /home/navera/isaac_ros_common
```

Commands with `sudo` run from your administrator account (the `navera` user has no sudo rights).

| Task | Command |
|---|---|
| Pre-flight check | `python3 navera_tools/check_box.py` (`--camera` with the vision service stopped; `--no-ros` settings and files only) |
| Reboot check | `/home/navera/isaac_ros_common/deploy/check_boot.sh` |
| Services running? | `systemctl status 'navera-*'` |
| Live log of a service | `journalctl -u navera-pipeline-day -f` |
| What detection found | `cat /var/lib/navera/discovery.json` |
| Re-run detection | `sudo systemctl restart navera-discover` (then the services) |
| NAVERA's state | `ros2 topic echo /navera/nav_status --once` |
| Web page alive | `curl -s http://localhost:8181/health` → `{"ok": true}` |
| Cut / restore NAVERA's GPS (ground test) | `sudo systemctl stop navera-gps` / `sudo systemctl start navera-gps` |

Services: `navera-discover` (detection), `navera-estimator` (arbiter), `navera-gps`,
`navera-imu`, `navera-insta360` (the Insta360 kit), `navera-rtc` (clock), `navera-pipeline-day` / `-night` / `-cn` (vision),
`navera-vehicle-link`, `navera-output`, `navera-web`.

---

## Appendix C — Words used in this manual

| Word | Meaning |
|---|---|
| Arbiter | the part of NAVERA that chooses which position to use |
| Attitude | the vehicle's roll, pitch and heading |
| Dead-reckoning | carrying the last known position along the measured track when there is no new measurement |
| Failsafe | what the autopilot does by itself when it loses its position (land, hold, return) |
| Forwarding | sending NAVERA's vision positions to the autopilot (off by default) |
| Jamming / spoofing | GPS signal blocked / GPS signal faked |
| MAVLink | the message protocol between autopilots and companion computers |
| Nadir | pointing straight down |
| NMEA | the plain text protocol of GPS receivers |
| Shadow mode | vision runs and records while GPS flies the vehicle, for measurement |
| SITL | ArduPilot's simulator ("software in the loop") |
| Sigma (σ) | the stated accuracy: about 68 % of positions are within 1 σ, 99 % within 3 σ |

Engineering references: `deploy/README.md`, `docs/ARDUPILOT_INTEGRATION.md`,
`docs/PX4_INTEGRATION.md`, `docs/FIELD_TEST_PROCEDURE.md`, `docs/TROUBLESHOOTING.md`,
`docs/VALIDATION_STATUS.md`, `docs/certification/DEPLOYMENT_VALIDATION.md`.
