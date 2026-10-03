# NAVERA — Installation and automatic start-up

This folder installs NAVERA on a Jetson Orin Nano so that it starts **by itself at power-on**,
with no login and no manual step: sensors, the vision pipeline, the position arbiter, the
output to the vehicle and the web interface.

Reference platform: Jetson Orin Nano 8 GB, JetPack 6.2.1 (L4T R36.4.7), Ubuntu 22.04,
ROS 2 Humble installed in `/opt/ros/humble`, CUDA 12.6. Everything runs **on the host**
(systemd services), not in the Isaac ROS development container.

Related documents:
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) (nodes and topics),
[docs/ARDUPILOT_INTEGRATION.md](../docs/ARDUPILOT_INTEGRATION.md) (wiring and autopilot parameters),
[docs/FIELD_TEST_PROCEDURE.md](../docs/FIELD_TEST_PROCEDURE.md) (first real test),
[docs/TROUBLESHOOTING.md](../docs/TROUBLESHOOTING.md),
[docs/VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md) (every measured figure).

---

## 1. The services

NAVERA is split into independent systemd services. Each one starts, fails and restarts on
its own; none depends on the start order of the others (they talk over DDS, which is
discovery-based, and the camera ↔ localizer handshake uses latched topics).

| Unit | Started by | Runs | Enable it when |
|---|---|---|---|
| `navera-discover` | `navera_boot_discover.sh` | Once per boot, before the others: finds what is connected and decides the sources left to `auto` (§5) → `/var/lib/navera/discovered.env`, report `/var/lib/navera/discovery.json` | Always |
| `navera-estimator` | `navera_boot_estimator.sh` | Position arbiter: GPS > day > night > celestial → `/navera/position`, `/navera/nav_status` | Always |
| `navera-gps` | `navera_boot_gps.sh` | NAVERA's GPS source, per `NAVERA_GPS_SOURCE` (box receiver, autopilot's 2nd GPS, or a ROS topic) | Always (NAVERA needs a GPS fix at start, in every mode — see §5) |
| `navera-pipeline-day` | `navera_boot_pipeline_day.sh` | Day camera + day vision (GPU) | Day operation (default) |
| `navera-pipeline-night` | `navera_boot_pipeline_night.sh` | Thermal camera + STHN night vision (GPU) | Night operation, **instead of** day |
| `navera-pipeline-cn` | `navera_boot_pipeline_cn.sh` | Celestial pipeline (astrometry.net, CPU) | See §10 — as shipped it replays a bundled sky image |
| `navera-imu` | `navera_boot_imu.sh` | Box IMU (BNO085, I²C bus 1 @ 0x4A) → `/navera/sensors/imu` | `NAVERA_SENSOR_SOURCE=box` and a BNO085 fitted |
| `navera-rtc` | `navera_boot_rtc.sh` | Real-time clock (DS3231, I²C bus 1 @ 0x68) → `/navera/sensors/rtc_time` | A DS3231 is fitted (the reference box has one) |
| `navera-vehicle-link` | `navera_boot_vehicle_link.sh` | Reads the autopilot over MAVLink → `/navera/vehicle/*` (attitude, rangefinder, barometric height, 2nd GPS, armed state) | `NAVERA_SENSOR_SOURCE=vehicle` or `NAVERA_GPS_SOURCE=vehicle`; also recommended with any MAVLink autopilot, so that `/mission` knows when the vehicle is armed |
| `navera-output` | `navera_boot_output.sh` | Output to the vehicle: NMEA, MAVLink `GPS_INPUT`, ROS `NavSatFix` on `/navera/fix` | NAVERA feeds the autopilot or a ROS consumer |
| `navera-web` | `navera_boot_web.sh` | Web bridge on port 8181: operator view `/operator`, dashboard `/`, mission preparation `/mission` | Always |

All ten units run as user `navera`, from the workspace `/home/navera/isaac_ros_common`
(`WorkingDirectory=` of every unit, and `NAVERA_WS` in `navera_boot_lib.sh`), and execute
the wrapper scripts installed in `/home/navera/` (`ExecStart=/home/navera/navera_boot_*.sh`).

| Other file | Role |
|---|---|
| `systemd/navera_boot_lib.sh` | Steps shared by the wrappers: enter the workspace, source ROS 2 and the NAVERA overlay, prune old ROS logs, check the data files exist |
| `navera.env.example` | Site settings template → `/etc/navera/navera.env` |
| `sudoers/navera-web` | The only root rights of the web service (restart NAVERA units, exact commands) → `/etc/sudoers.d/navera-web` |

`day_sim.launch.py` (pipeline + bridge in one command) remains for development and
demonstration; it is not used at boot.

## 2. Boot behaviour

At power-on systemd starts each enabled unit as user `navera`. Each wrapper:

1. enters the workspace `/home/navera/isaac_ros_common` (exits with an error if it is missing);
2. (GPU pipelines only) puts CUDA (`/usr/local/cuda/bin`, `/usr/local/cuda/lib64`) on
   `PATH` / `LD_LIBRARY_PATH` — normally done by `~/.bashrc`, which systemd never reads;
3. sources `/opt/ros/humble/setup.bash`, then `install/setup.bash`;
4. deletes ROS log folders (`~/.ros/log`) older than 7 days (a restart loop would otherwise fill the disk);
5. (pipelines) checks its data exists: day `NAVERA_MBTILES` and `DAY_DATASET_DIR`; night
   `NAVERA_MBTILES`, `NAVERA_STHN_DIR`, `NAVERA_STHN_WEIGHTS`. If the data disk is not
   mounted yet, the wrapper exits and systemd retries 10 s later: a pipeline never runs half-blind;
6. `exec`s its `ros2 launch` / `ros2 run` command, which becomes the unit's main process
   (clean stop and restart).

**No network wait.** The units are ordered only after `local-fs.target` (`navera-web`
after `network.target`, to bind its port). A vehicle in the field often has no network,
and all NAVERA nodes talk over DDS on the box.

**Settings.** Every unit loads `/etc/navera/navera.env`, then
`/var/lib/navera/settings.env` (written by the `/mission` page), which overrides it. Both
are optional for systemd (`EnvironmentFile=-…`), but NAVERA needs the first one.

### Automatic restart

`ros2 launch` exits with code 0 even when one of its nodes crashed, so `Restart=on-failure`
would never restart anything. Instead:

- every node of the boot launch files has `on_exit=Shutdown`: if **one** node dies, the
  whole launch stops (a camera is never left waiting for a dead localizer);
- every unit has `Restart=always`, `RestartSec=10` and `StartLimitIntervalSec=0`: systemd
  restarts it 10 s after any exit, forever. A deliberate `systemctl stop` is not undone;
- nodes that lose their hardware exit on purpose so this cycle retries: `gps_node` when the
  serial port is missing or disconnects, `vehicle_output` when an output cannot be opened or
  written, the live camera when the camera cannot be opened or stops sending frames.

A restart in flight does not start from scratch: the ground altitude and day vision's last
position are kept on disk (§9).

> **Validation status.** The split into services was validated by a reboot on the Jetson
> on 2026-07-15 (services up, bridge answering HTTP 200 on `:8181`, nodes running). That
> was before `navera-estimator`, `navera-output`, `navera-vehicle-link`, `Restart=always` /
> `on_exit=Shutdown` and `/etc/navera/navera.env` were added: **the reboot test must be
> repeated** on a deployed unit:
>
> ```bash
> sudo reboot
> /home/navera/isaac_ros_common/deploy/check_boot.sh   # every enabled unit active? restarts? pre-flight check
> sudo pkill -f gps_node; sleep 15; deploy/check_boot.sh   # a killed node comes back
> ```

## 3. Installation on a new Jetson

**One command** does §3.1–§3.9 (safe to run again to update; `--dry-run` shows what it
would do; `--help` for the options):

```bash
git clone <NAVERA repository> ~/Navera && cd ~/Navera
sudo deploy/install.sh                 # typical units; --units "..." to choose, --start to start now
sudoedit /etc/navera/navera.env        # first install: the site settings (below)
```

It never overwrites an existing `/etc/navera/navera.env`, and switches the Jetson to a
headless boot only with `--headless` (that ends the desktop session). The steps it runs
are detailed below, for a manual installation or a review.

Run on the target Jetson, as an administrator account (commands that need root show `sudo`).

### 3.1 System packages and service user

```bash
# ROS 2 Humble must already be installed in /opt/ros/humble.
sudo apt update
sudo apt install -y git python3-pip python3-colcon-common-extensions python3-yaml \
    ros-humble-cv-bridge
# Celestial pipeline only: astrometry.net solver + Tycho-2 index (fields 1°–33°+)
sudo apt install -y astrometry.net astrometry-data-tycho2-10-19

# Service user, and its hardware access:
#   dialout  serial ports (GPS receiver, autopilot links)
#   i2c      I²C bus (BNO085 IMU, DS3231 clock)
#   video    USB / CSI cameras (/dev/video*) — the pipeline units do not add it themselves
#   gpio     needed by the Adafruit Blinka stack on Jetson, when the group exists
sudo useradd -m -s /bin/bash navera 2>/dev/null || true
sudo usermod -aG dialout,i2c,video navera
getent group gpio >/dev/null && sudo usermod -aG gpio navera
id navera          # check the groups
```

### 3.2 Get the code

The units expect the workspace at **`/home/navera/isaac_ros_common`** (historical name,
fixed in every unit file). Clone the NAVERA repository there, as the service user (the
repository is private: use the URL and credentials supplied by IRIS Systems, or extract
the delivered source archive to the same path):

```bash
sudo -u navera -H git clone https://github.com/navera-user/Navera /home/navera/isaac_ros_common
# a specific release:  sudo -u navera -H git -C /home/navera/isaac_ros_common checkout <tag>
```

### 3.3 Python dependencies (installed for the service user)

The services run as `navera`, so the packages must be installed **for `navera`**
(`sudo -u navera -H pip3 install --user …` → `/home/navera/.local`). PyTorch must be the
Jetson build (JetPack 6, CUDA 12.6), never the PyPI wheel.

```bash
sudo -u navera -H bash -c '
printf "torch==2.8.0\ntorchvision==0.23.0\nnumpy<2\nsetuptools<80\n" > ~/navera-constraints.txt
pip3 install --user --no-deps --index-url https://pypi.jetson-ai-lab.io/jp6/cu126/+simple \
    torch==2.8.0 torchvision==0.23.0
pip3 install --user -c ~/navera-constraints.txt \
    "numpy<2" "scipy>=1.11,<1.14" timm kornia safetensors einops huggingface_hub \
    scikit-learn pandas "astropy<7" opencv-python==4.11.0.86 \
    pyserial pynmea2 pymavlink pygeomag==1.1.0 \
    Jetson.GPIO adafruit-blinka adafruit-circuitpython-bno08x adafruit-circuitpython-ds3231
'
```

| Module | Used by |
|---|---|
| `torch`, `torchvision`, `scikit-learn`, `pandas` | day vision (DINOv2 retrieval, map preparation) |
| `torch`, `safetensors`, `kornia`, `timm`, `einops`, `scipy` | night vision (STHN) |
| `cv2` (OpenCV) | cameras, day vision, calibration |
| `astropy` | celestial pipeline |
| `serial` (pyserial), `pynmea2` | GPS driver, NMEA output |
| `pymavlink` | MAVLink output (`GPS_INPUT`) and the vehicle link |
| `pygeomag` | true north for the box IMU (World Magnetic Model 2025) |
| `board`, `busio`, `adafruit_bno08x`, `adafruit_ds3231` (Blinka) | box IMU and clock drivers |
| `yaml` | camera calibration files |

> **CSI cameras:** the `opencv-python` wheel is built without GStreamer; NAVERA reads CSI
> cameras (and `NAVERA_CAMERA_INPUT=gst` sources) through the system's GStreamer instead
> (`camera_pkg/gst_capture.py`, needs `python3-gi` and `gir1.2-gstreamer-1.0`, installed by
> `deploy/install.sh`).

GPU check (must print `True`):

```bash
sudo -u navera -H python3 -c "import torch; print(torch.cuda.is_available())"
```

### 3.4 Build

All twelve NAVERA packages are needed by the boot services (including `navera_output`,
launched by `navera-output` and `navera-vehicle-link`). The vendored `isaac_ros_*` folders
and `vision_pkg/` carry a `COLCON_IGNORE`.

```bash
sudo -u navera -H bash -c '
cd /home/navera/isaac_ros_common
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-up-to \
    navera_msgs navera_common navera_estimator navera_output gps_pkg imu_pkg rtc_pkg \
    camera_pkg day_pkg night_pkg cn_pkg simulation_web
'
```

### 3.5 Directories, site settings, root rights

```bash
cd /home/navera/isaac_ros_common

# State and settings written by NAVERA itself (must be writable by navera):
#   /var/lib/navera           settings.env (page /mission) + state kept across restarts (§9)
#   /data/navera/areas        route maps generated by /mission (NAVERA_AREAS_DIR)
sudo install -d -o navera -g navera /var/lib/navera /data/navera/areas

# Site settings (holds the web token: readable by root and navera only)
sudo install -d -m 0755 /etc/navera
sudo install -m 0640 -o root -g navera deploy/navera.env.example /etc/navera/navera.env
sudoedit /etc/navera/navera.env
```

Set at least, for **every** vehicle: `NAVERA_MAX_SPEED_KMH`, the sensor and GPS sources
(§5), the camera (§4), the data paths, and `NAVERA_WEB_TOKEN`. Leave a numeric setting you
do not use **commented out** — an empty `KEY=` is not "unset" and stops some launch files.

```bash
# The only root right of the web service: restart NAVERA units (exact commands, §8)
sudo install -m 0440 deploy/sudoers/navera-web /etc/sudoers.d/navera-web
sudo visudo -c
```

### 3.6 Install the wrappers and the units

```bash
cd /home/navera/isaac_ros_common
# Wrappers in the service user's home (ExecStart=/home/navera/navera_boot_*.sh)
sudo install -o navera -g navera -m 0755 deploy/systemd/navera_boot_*.sh /home/navera/
# Units
sudo install -m 0644 deploy/systemd/navera-*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

The wrappers are installed in `~navera` rather than run from the repository so that the
running configuration only changes when it is re-installed. After a `git pull`, repeat the
build (§3.4) and this step.

### 3.7 Camera calibration

See §4. Do it before the first real test: without it the lens is assumed distortion-free.

### 3.8 Offline model cache

The vehicle may boot without internet. Fill the DINOv2 cache (`TORCH_HOME` in
`navera.env`) once, with internet:

```bash
sudo -u navera -H bash -c 'set -a; . /etc/navera/navera.env; set +a; \
  python3 -c "import torch; torch.hub.load(\"facebookresearch/dinov2\", \"dinov2_vits14\")"'
```

### 3.9 Enable the services

Pick from the table in §1. A typical box with its own sensors, feeding an autopilot over MAVLink:

```bash
sudo systemctl enable navera-estimator navera-gps navera-imu navera-rtc \
    navera-pipeline-day navera-output navera-web
# The vehicle's sensors / 2nd GPS over MAVLink, or the armed lock on /mission:
sudo systemctl enable navera-vehicle-link

# Boot without a graphical session
sudo systemctl set-default multi-user.target

# Start now without rebooting
sudo systemctl start navera-estimator navera-gps navera-imu navera-rtc \
    navera-pipeline-day navera-output navera-web navera-vehicle-link
```

Then run the pre-flight check (§11) and, once, the reboot test (§2).

## 4. Camera

Settings (`/etc/navera/navera.env`): `NAVERA_CAMERA=live` (the default `replay` plays recorded
frames, for demonstration), `NAVERA_CAMERA_INPUT=usb|csi|ros`, `NAVERA_CAMERA_DEVICE`,
`NAVERA_CAMERA_SIZE`, `NAVERA_CAMERA_CALIBRATION`, mounting and gimbal — all described in
`navera.env.example`.

**Address a USB camera by its stable name.** `/dev/videoN` numbers change with plug order.
Use the `/dev/v4l/by-id/` link, which contains the maker, model and serial number:

```bash
ls -l /dev/v4l/by-id/
# e.g. NAVERA_CAMERA_DEVICE=/dev/v4l/by-id/usb-<maker>_<model>_<serial>-video-index0
```

**Calibrate the lens** (once per camera and resolution) with
`navera_tools/calibrate_camera.py`. The tool writes the YAML file that
`NAVERA_CAMERA_CALIBRATION` points to, and records the camera's `/dev/v4l/by-id` name
(`camera_id`). The live camera then **refuses** a calibration made with another camera, or
at another resolution than `NAVERA_CAMERA_SIZE`. Procedure (board, number of views,
acceptance) in [FIELD_TEST_PROCEDURE.md §2](../docs/FIELD_TEST_PROCEDURE.md):

```bash
sudo systemctl stop navera-pipeline-day          # the pipeline holds the camera
sudo -u navera -H bash -c '
source /opt/ros/humble/setup.bash; source /home/navera/isaac_ros_common/install/setup.bash
python3 /home/navera/isaac_ros_common/navera_tools/calibrate_camera.py \
    --device /dev/v4l/by-id/usb-<maker>_<model>_<serial>-video-index0 --size 1920x1080 \
    --board 9x6 --square-mm <measured> --out /home/navera/camera.yaml
'
sudo install -m 0644 /home/navera/camera.yaml /etc/navera/camera.yaml
# then in /etc/navera/navera.env:  NAVERA_CAMERA_CALIBRATION=/etc/navera/camera.yaml
sudo systemctl start navera-pipeline-day
```

Without a calibration, `NAVERA_CAMERA_HFOV_DEG` (an ideal, distortion-free lens) is the
minimum: `check_box.py` reports **FAIL** "camera settings" with neither, and **WARN** "lens
calibration — none" with the field of view only.

## 5. Sensor and GPS sources

### Automatic detection (default: `auto`)

With `NAVERA_SENSOR_SOURCE`, `NAVERA_GPS_SOURCE` and `NAVERA_CAMERA_INPUT` set to `auto`
(the template's default), **navera-discover** looks at every boot (~20 s, before the other
units) for:

| What | How it is found |
|---|---|
| The box's IMU and clock | I²C buses 1 and 7: BNO085 at 0x4A/0x4B, DS3231 at 0x68 |
| A GPS receiver | checksummed NMEA **with satellite data** (GSV/GSA: an autopilot's NMEA output has none) on `/dev/ttyTHS*`, `/dev/ttyUSB*`, `/dev/ttyACM*` (4800–921600 baud); several: the one with a fix, wired UART first, and a warning |
| An autopilot (any MAVLink) | an autopilot heartbeat (ground stations, cameras, companions ignored) on those serial ports, on UDP 14550/14551, or on `NAVERA_DISCOVER_MAVLINK`; it is then asked for attitude, rangefinder, height above home and its GPS receiver types (`GPS_TYPE`/`GPS_TYPE2`). Several: its wired TELEM port first, and a warning when they are different autopilots |
| A ROS vehicle | `sensor_msgs` Imu / NavSatFix / Image / Range topics on ROS domain 0, `ROS_DOMAIN_ID` and `NAVERA_DISCOVER_ROS_DOMAINS` |
| Cameras | USB (`/dev/v4l/by-id/*-video-index0`, except the star camera), CSI (Jetson video inputs); several: a warning — set `NAVERA_CAMERA_DEVICE` |

and chooses: **attitude** box IMU > autopilot > ROS; **GPS** box receiver > autopilot's 2nd GPS
> ROS; **camera** USB > CSI > ROS (depth images excluded; a ROS camera is flagged "check it
looks at the ground"). The autopilot's second GPS is used only when `GPS_TYPE2` says it is
a real receiver (fix or not yet) — never type 14, the MAVLink-fed GPS that NAVERA itself
feeds (a loop), and not when the types cannot be read. **No GPS found: the GPS service
stays idle** — no default port is ever opened. **Outputs:** an autopilot found → NAVERA's
position over MAVLink, as the autopilot's companion (its system id), on the same link,
relayed by `navera-vehicle-link` (local UDP 14650), no mavlink-router needed
(`NAVERA_MAVLINK_URL=off` to never send it); a ROS vehicle → `/navera/fix`. A ROS vehicle
is used only on NAVERA's ROS domain, or with `ROS_DOMAIN_ID=auto` (NAVERA then joins it);
written ROS network settings are never changed. A port another program holds, the kernel
console and a login terminal are never probed; only an identified autopilot is written to
(its data-stream and parameter requests).

A value written in `navera.env` instead of `auto` is always kept. See what was found:
`navera_tools/check_box.py` (first lines) or `/var/lib/navera/discovery.json`. After
connecting something new: reboot, or `sudo systemctl restart navera-discover` then the
units concerned. Verified: this Jetson's bench (a ROS robot simulation found, no box
sensors), virtual serial GPS/autopilot ports (unit tests), ArduPilot SITL with a second
GPS (`navera_tools/tests/sitl_discovery.py`: autopilot found, attitude and GPS taken from
it, NAVERA's messages relayed). Not yet with real box sensors or a real autopilot.

### Imposing a source

**Attitude and height — `NAVERA_SENSOR_SOURCE`** (read by the live camera, the night and
celestial pipelines and the estimator's IMU liveness check; `navera_common/vehicle.py`):

| Value | Attitude | Height above ground | Needs |
|---|---|---|---|
| `box` (auto finds nothing) | `/navera/sensors/imu` (BNO085) | from the GPS altitude and the image | `navera-imu` |
| `vehicle` | `/navera/vehicle/imu` (autopilot attitude) | `/navera/vehicle/altitude_agl` (downward rangefinder), `/navera/vehicle/relative_alt` (barometric height above home) | `navera-vehicle-link`, `NAVERA_VEHICLE_MAVLINK_URL` |
| `ros` | `NAVERA_ROS_IMU_TOPIC` (sensor_msgs/Imu, ENU) — required | `NAVERA_ROS_ALTITUDE_TOPIC` (sensor_msgs/Range), optional | the vehicle's ROS graph (§6) |

**GPS — `NAVERA_GPS_SOURCE`** (`navera_boot_gps.sh`; every mode publishes
`/navera/sensors/gps_fix` and `/navera/estimate/gps` the same way):

| Value | GPS | Node |
|---|---|---|
| `serial` (auto finds nothing) | the box's receiver, NMEA on `NAVERA_GPS_PORT` (default `/dev/ttyTHS1`) at `NAVERA_GPS_BAUD` (default 9600) | `gps_node` |
| `vehicle` | the autopilot's **second** GPS (`GPS2_RAW`), read by `navera-vehicle-link` and republished from `/navera/vehicle/gps2` | `ros_gps_node` |
| `ros` | the vehicle's `sensor_msgs/NavSatFix` topic `NAVERA_ROS_GPS_TOPIC` (required) | `ros_gps_node` |

**NAVERA needs a GPS fix at start, in every mode.** The first GPS position is the prior
every vision pipeline searches around: without it day vision reports "no position prior
(waiting for a GPS fix)" (whole-map search is disabled because it is not reliable). After a
service restart in flight, day vision can resume from its last position if it is less than
5 minutes old (§9).

> **Never point NAVERA at a position it produces itself:** not the autopilot's fused
> position (`GLOBAL_POSITION_INT`, a ROS "global position" topic), not a GPS instance that
> NAVERA's own `GPS_INPUT`/NMEA output feeds, not `/navera/fix`. NAVERA would check its
> output against itself. This is why `vehicle` mode reads only the autopilot's **second**
> GPS, which must be a real receiver (NAVERA then feeds GPS 1 — see
> [ARDUPILOT_INTEGRATION.md](../docs/ARDUPILOT_INTEGRATION.md)).

Box IMU settings (used by `navera-imu`): `NAVERA_IMU_MOUNT_RPY` (mounting angles) and
`NAVERA_DECLINATION_DEG` (declination used until a position is known; the IMU node then
switches to the World Magnetic Model). See [imu_pkg/README.md](../imu_pkg/README.md).

## 6. ROS vehicles: joining the vehicle's ROS graph

The template sets `ROS_LOCALHOST_ONLY=1` and `ROS_DOMAIN_ID=42`: NAVERA's DDS traffic stays
on the box, and **no other machine sees NAVERA's topics, nor NAVERA theirs**. That is right
for a stand-alone box. When NAVERA must exchange topics with a boat's or robot's ROS 2
computer — `NAVERA_SENSOR_SOURCE=ros`, `NAVERA_GPS_SOURCE=ros`, `NAVERA_CAMERA_INPUT=ros`, or
a ROS consumer of `/navera/fix` — set in `/etc/navera/navera.env`:

```
ROS_LOCALHOST_ONLY=0
ROS_DOMAIN_ID=<the vehicle's domain id>
```

then restart all NAVERA units. Both computers must use the same ROS 2 distribution and a
compatible RMW. Consequence: any machine on that network and domain can then publish into
NAVERA (a test laptop running `navera_tools/sensor_sim.py`, for instance) — keep that network
closed.

**ROS output.** `navera-output` always publishes the arbiter's decision as
`sensor_msgs/NavSatFix` on `/navera/fix` (`NAVERA_ROS_FIX_TOPIC` sets another name; parameter
`ros_fix_topic` of `vehicle_output`), with the same rules as the NMEA and MAVLink outputs
(§7). The accuracy is in the covariance.

## 7. Output to the vehicle

`navera-output` turns the arbiter's decision into a GPS for the vehicle:

| Setting | Output |
|---|---|
| `NAVERA_NMEA_PORT`, `NAVERA_NMEA_BAUD` | NMEA 0183 GGA + RMC on a serial port |
| `NAVERA_MAVLINK_URL` | MAVLink `GPS_INPUT` (ArduPilot, PX4), e.g. `serial:/dev/ttyTHS2:921600` |
| `NAVERA_ROS_FIX_TOPIC` | ROS NavSatFix (default `/navera/fix`) |

**Vision positions are DEGRADED, and DEGRADED positions are not sent by default.** Day
vision's accuracy is not yet established with NAVERA's camera
([VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md)), so when GPS is lost the autopilot
receives "no fix" and its own failsafe acts — unless forwarding is enabled explicitly:

| Setting | Default | Meaning |
|---|---|---|
| `NAVERA_FORWARD_DEGRADED` | false | `true`: send vision / celestial positions, flagged "estimated" |
| `NAVERA_DEGRADED_SIGMA_M` | none | the accuracy (m, 1 σ) the autopilot must assume — **required** with forwarding (the node refuses to start without it); use a value you have measured |
| `NAVERA_MAX_MEASUREMENT_AGE_S` | 5.0 | a position measured longer ago is not sent; a younger vision position is carried to the present along the measured ground velocity, its accuracy grown by its age |

A position coarser than 1 km is never forwarded (`max_forward_sigma_m`). Full rules:
[navera_output/README.md](../navera_output/README.md). MAVLink addresses: one format
everywhere (`serial:/dev/<port>:<baud>`, `udpin:`, `udpout:`, `tcp:`); one autopilot port
per NAVERA connection (output and vehicle link), or `mavlink-router` to share one. Wiring
and autopilot parameters: [ARDUPILOT_INTEGRATION.md](../docs/ARDUPILOT_INTEGRATION.md).

## 8. Web interface and the `/mission` page

`navera-web` serves, on port 8181 (all interfaces): `/operator` (operator view), `/`
(dashboard) and `/mission` (mission preparation; day and night bridges — the celestial
bridge, `NAVERA_PIPELINE=cn`, has no `/mission` page).

**Control token.** Every control action (start a mission, any `/mission` change) needs the
`X-Navera-Token` header equal to `NAVERA_WEB_TOKEN`; with no token configured the interface
is read-only. Over plain HTTP the token crosses the network in clear: set
`NAVERA_TLS_CERT` / `NAVERA_TLS_KEY` (HTTPS only, TLS ≥ 1.2; see `navera.env.example`), and
do not expose port 8181 beyond the vehicle's own network (no port forwarding; firewall it
on any interface that leaves the vehicle).

**What `/mission` can change** (`simulation_web/mission_prep.py`, `SETTINGS`) — written to
`/var/lib/navera/settings.env`, which overrides `navera.env`:

| Key | Validation |
|---|---|
| `NAVERA_VEHICLE_TYPE` | drone, plane, boat, robot, other (label) |
| `NAVERA_MAX_SPEED_KMH` | 4–1890 |
| `NAVERA_DAY_HFOV_DEG` | 5–170 |
| `NAVERA_THERMAL_HFOV_DEG` | 5–170 |
| `NAVERA_IMU_MOUNT_RPY` | roll,pitch,yaw, each −180…180 |
| `NAVERA_DECLINATION_DEG` | −90…90 |

plus `DAY_DATASET_DIR`, set only by "Activate" (the route map in use). An empty field
removes the key (back to `navera.env`). **It does not set the camera (`NAVERA_CAMERA_*`),
the sensor or GPS sources, the outputs or the network**: those are edited in
`/etc/navera/navera.env` by an administrator.

**Route maps.** The page imports the autopilot's mission file (or a route drawn on the map),
**generates** the satellite map of the route corridor into `NAVERA_AREAS_DIR` (tiles from
`NAVERA_MBTILES`, missing tiles downloaded from `NAVERA_TILE_URL` when set) and
**activates** it (sets `DAY_DATASET_DIR`, restarts `navera-pipeline-day`). Day vision only
matches against the activated map.

**Refused in flight.** "Apply settings", "Activate" and "Generate" are refused while the
vehicle is **armed** (`refused: the vehicle is armed: disarm it before changing NAVERA`) or
while NAVERA is **navigating without GPS** (`refused: NAVERA is navigating without GPS right
now: a restart would interrupt it`). The armed state comes from `navera-vehicle-link`
(`/navera/vehicle/status`): without it, only the second condition is checked. Saving
settings is still possible; they take effect at the next "Apply".

**Root rights.** The sudoers file `deploy/sudoers/navera-web` allows the web service exactly
two commands:

- `systemctl restart navera-pipeline-day.service` — "Activate" a route map;
- `systemctl try-restart navera-estimator.service navera-imu.service navera-pipeline-day.service navera-pipeline-night.service navera-pipeline-cn.service`
  — "Apply settings" (`NAVERA_UNITS` in `navera_web_bridge.py`); `try-restart` restarts only
  the units that are running.

These are the units that read the page's settings. `navera-gps`, `navera-output`,
`navera-vehicle-link` and `navera-web` are **deliberately not restarted**: none of them reads
a `/mission` setting, and restarting them would cut the autopilot's GPS feed, drop the
autopilot link, or kill the web service answering the request.

## 9. State kept across a restart

A service restarted in the air (watchdog, crash, power blip) resumes with what it knew:

| Fact | Kept | Reused when |
|---|---|---|
| Ground altitude (taken at the first GPS fix) | 12 h | the vehicle is within 2 km of where it was taken |
| Day vision's last position | 5 min | always within that age |

They are JSON files in `NAVERA_STATE_DIR` (default `/var/lib/navera` when writable by the
service user, else `/home/navera/.local/state/navera`). `/var/lib/navera` must therefore be
owned by `navera` (§3.5); otherwise the state silently goes to the home directory.

## 10. Switching pipelines (day / night / celestial)

Only one GPU vision pipeline fits in memory: `navera-pipeline-day` and
`navera-pipeline-night` are mutually exclusive (`Conflicts=`; starting one stops the other).
The web bridge follows `NAVERA_PIPELINE`.

```bash
# Example: switch to night
sudo sed -i 's/^NAVERA_PIPELINE=.*/NAVERA_PIPELINE=night/' /etc/navera/navera.env
sudo systemctl disable --now navera-pipeline-day
sudo systemctl enable --now navera-pipeline-night
sudo systemctl restart navera-web
```

The celestial unit (CPU only) has no `Conflicts=`: it can run beside day or night, and the
arbiter uses it after them (GPS > day > night > celestial). **As shipped, however, the
celestial launch (`cn_pipeline.launch.py`) replays a bundled sample sky image** with
launch-time attitude, time and operating-area constants (Sousse); its camera waits for a
mission start from the celestial bridge (`NAVERA_PIPELINE=cn`). It is a demonstration of
the chain, not a live star-camera installation. Star-camera settings:
`NAVERA_STAR_CAMERA_ELEVATION_DEG`, `NAVERA_STAR_CAMERA_AZIMUTH_DEG`,
`NAVERA_MAGNETIC_DECLINATION_DEG`, `NAVERA_ATTITUDE_SIGMA_DEG` (see `navera.env.example`).

## 11. Checks

A shell that inspects the live system must load the same environment as the services
(otherwise it is on another ROS domain and sees nothing):

```bash
sudo -u navera -H bash        # or any account in the navera group
source /opt/ros/humble/setup.bash
source /home/navera/isaac_ros_common/install/setup.bash
set -a; . /etc/navera/navera.env; . /var/lib/navera/settings.env 2>/dev/null; . /var/lib/navera/discovered.env 2>/dev/null; set +a
```

Then:

```bash
# Pre-flight check: PASS / WARN / FAIL per item, "READY" when no FAIL
python3 /home/navera/isaac_ros_common/navera_tools/check_box.py
ros2 topic echo /navera/nav_status --once
```

From any shell:

```bash
systemctl status 'navera-*'                 # every enabled unit "active (running)"
systemctl is-enabled navera-estimator navera-gps navera-web navera-pipeline-day
journalctl -u navera-pipeline-day -f        # live log of one unit
curl -s http://localhost:8181/health        # {"ok": true}  (with TLS: curl -sk https://…)
sudo reboot                                  # full test: everything must come back alone
```

Operator view: `http://<jetson-ip>:8181/operator` (`https://` with TLS).

## 12. Uninstall / disable

```bash
# One service (e.g. the day pipeline)
sudo systemctl disable --now navera-pipeline-day
sudo rm /etc/systemd/system/navera-pipeline-day.service
sudo systemctl daemon-reload

# Everything
sudo systemctl disable --now navera-estimator navera-gps navera-imu navera-rtc \
    navera-pipeline-day navera-pipeline-night navera-pipeline-cn \
    navera-output navera-vehicle-link navera-web
sudo rm /etc/systemd/system/navera-*.service /etc/sudoers.d/navera-web
sudo rm /home/navera/navera_boot_*.sh
sudo systemctl daemon-reload
# Settings and state, if no longer wanted:  sudo rm -r /etc/navera /var/lib/navera
```
