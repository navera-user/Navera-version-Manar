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
[docs/PX4_INTEGRATION.md](../docs/PX4_INTEGRATION.md) (PX4 — not tested with NAVERA),
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
| `navera-gps` | `navera_boot_gps.sh` | NAVERA's GPS source, per `NAVERA_GPS_SOURCE` (box receiver, autopilot's 2nd GPS, or a ROS topic); idle when none is found (`none`) | Always (NAVERA needs a GPS fix at start, or an operator start position — see §5) |
| `navera-pipeline-day` | `navera_boot_pipeline_day.sh` | Day camera + day vision (GPU) | Day operation (default) |
| `navera-pipeline-night` | `navera_boot_pipeline_night.sh` | Thermal camera + STHN night vision (GPU) | Night operation, **instead of** day |
| `navera-pipeline-cn` | `navera_boot_pipeline_cn.sh` | Celestial pipeline (astrometry.net, CPU) | See §10 — as shipped it replays a bundled sky image |
| `navera-imu` | `navera_boot_imu.sh` | Box IMU (BNO085, I²C bus 1 @ 0x4A) → `/navera/sensors/imu`; idle when navera-discover found no BNO085 (`NAVERA_BOX_IMU=0`) | `NAVERA_SENSOR_SOURCE=box` and a BNO085 fitted (enabling it elsewhere is harmless) |
| `navera-rtc` | `navera_boot_rtc.sh` | Real-time clock (DS3231, I²C bus 1 @ 0x68) → `/navera/sensors/rtc_time`; idle when no DS3231 was found (`NAVERA_BOX_RTC=0`) | A DS3231 is fitted (the reference box has one) |
| `navera-vehicle-link` | `navera_boot_vehicle_link.sh` | Reads the autopilot over MAVLink → `/navera/vehicle/*` (attitude, rangefinder, barometric height, 2nd GPS, armed state), and relays NAVERA's MAVLink output to it (local UDP 14650); idle when no autopilot is found or configured | `NAVERA_SENSOR_SOURCE=vehicle`, `NAVERA_GPS_SOURCE=vehicle`, or a MAVLink output through its relay; also recommended with any MAVLink autopilot, so that `/mission` knows when the vehicle is armed |
| `navera-output` | `navera_boot_output.sh` | Output to the vehicle: NMEA, MAVLink `GPS_INPUT`, ROS `NavSatFix` on `/navera/fix` | NAVERA feeds the autopilot or a ROS consumer |
| `navera-web` | `navera_boot_web.sh` | Web bridge on port 8181: operator view `/operator`, dashboard `/`, mission preparation `/mission` | Always |

All eleven units run as user `navera`, from the workspace `/home/navera/isaac_ros_common`
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
`/var/lib/navera/settings.env` (written by the `/mission` page), which overrides it, then
`/var/lib/navera/discovered.env` (written at boot by `navera-discover`, §5, only for the
settings left to `auto` or unset). All are optional for systemd (`EnvironmentFile=-…`),
but NAVERA needs the first one. `navera-discover` itself reads only the first two, so
last boot's choices never look written.

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

- a camera that gives no frame for 10 s (`camera_stall_restart_s`: unplugged, USB reset,
  stuck driver, stalled stream) makes the live camera exit for a restart; a replugged USB camera
  is found again under its `/dev/v4l/by-id/...` name.

### Memory, swap and logs (8 GB Jetson)

The day pipeline uses 2.5 GB (real flight replay, 100 m) to 5 GB (bench mission, ~520 m); it
was OOM-killed without swap (F5). `install.sh` therefore makes an 8 GB `/swapfile`
(`deploy/setup_swap.sh`, `NAVERA_SWAP_MB`) when less than `NAVERA_MIN_SWAP_MB` (4 GB) of swap
on disk is active — JetPack's zram is in RAM and does not count — and every pipeline start,
`check_boot.sh` and `check_box.py` warn without it. The units set who the kernel's OOM killer
takes first: the web page and the discovery (`OOMScoreAdjust=500`, capped by `MemoryHigh` /
`MemoryMax`, beyond which they go to swap), then the vision pipelines (-300), last the output
chain (estimator, output, GPS, IMU, RTC, vehicle link: -900; systemd-oomd never picks them).
The journal is capped at 1 GB with 2 GB kept free (`/etc/systemd/journald.conf.d/navera.conf`).

A restart in flight does not start from scratch: the ground altitude and day vision's last
position are kept on disk (§9).

> **Validation status.** The split into services was validated by a reboot on the Jetson
> on 2026-07-15 (services up, bridge answering HTTP 200 on `:8181`, nodes running). That
> was before `navera-discover`, `navera-estimator`, `navera-output`, `navera-vehicle-link`,
> `Restart=always` / `on_exit=Shutdown` and `/etc/navera/navera.env` were added: **the
> reboot test must be repeated** on a deployed unit (`deploy/check_boot.sh --help` explains
> its report):
>
> ```bash
> sudo reboot
> /home/navera/isaac_ros_common/deploy/check_boot.sh   # every enabled unit active? restarts? pre-flight check
> sudo pkill -f gps_node; sleep 15; deploy/check_boot.sh   # a killed node comes back
> ```
>
> **Without a box and without root** (any machine with ROS 2 Humble): `deploy/stage_check.sh`
> stages the install with `deploy/install.sh --root DIR`, checks every unit
> (`deploy/verify_units.py`: `systemd-analyze verify`, ExecStart, launch files, settings,
> sudoers), runs the staged units as user units on their own ROS domain, kills nodes and
> checks they come back (`navera_tools/check_boot.py --user --prefix navera-stage-`). It does
> not replace the reboot test above. Results and the exact commands for a production unit:
> [docs/certification/DEPLOYMENT_VALIDATION.md](../docs/certification/DEPLOYMENT_VALIDATION.md).

## 3. Installation on a new Jetson

**One command** does §3.1–§3.9 (safe to run again to update; `--dry-run` shows what it
would do; `--help` for the options):

```bash
git clone <the repository URL supplied by IRIS Systems> ~/Navera && cd ~/Navera
sudo deploy/install.sh                 # typical units; --units "..." to choose, --start to start now
sudoedit /etc/navera/navera.env        # first install: the site settings (below)
```

**Mount the data disk first** (§3.10): `install.sh` creates `/data/navera` and
`/data/navera/areas` owned by `navera`; created before the disk is mounted on `/data`,
they would be hidden under the mount point.

It never overwrites an existing `/etc/navera/navera.env`, and switches the Jetson to a
headless boot only with `--headless` (that ends the desktop session). It enables
`navera-discover navera-estimator navera-gps navera-imu navera-rtc navera-vehicle-link
navera-pipeline-day navera-output navera-web` unless `--units` says otherwise. The steps
it runs are detailed below, for a manual installation or a review.

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
sudo -u navera -H git clone <the repository URL supplied by IRIS Systems> /home/navera/isaac_ros_common
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
#   /data/navera              the data disk's NAVERA folder (model cache, §3.10)
#   /data/navera/areas        route maps generated by /mission (NAVERA_AREAS_DIR)
# each level is named: install -d leaves the parents it creates owned by root
sudo install -d -o navera -g navera /var/lib/navera /data/navera /data/navera/areas

# Site settings (holds the web token: readable by root and navera only)
sudo install -d -m 0755 /etc/navera
sudo install -m 0640 -o root -g navera deploy/navera.env.example /etc/navera/navera.env
sudoedit /etc/navera/navera.env
```

Set at least, for **every** vehicle: `NAVERA_MAX_SPEED_KMH`, the sensor and GPS sources
(§5, or leave them to `auto`), the camera (§4), the data paths (§3.10), and
`NAVERA_WEB_TOKEN`. Leave a numeric setting you
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

### 3.8b TensorRT engines (night STHN; optional day DISK)

Engines are specific to the Jetson, its TensorRT and the precision: they are built ON the box, once
after installation (and after a JetPack upgrade), never committed. Without them NAVERA runs its
PyTorch paths (night: the GPU graph, see `night_pkg` `sthn_backend`).

```bash
sudo apt install python3-libnvinfer libnvinfer-bin          # TensorRT Python bindings + trtexec (JetPack repo)
sudo -u navera -H pip3 install --user onnx==1.16.2 "protobuf>=4.25,<5"   # export only
sudo -u navera -H bash -c 'set -a; . /etc/navera/navera.env; set +a; cd /home/navera/isaac_ros_common; \
  python3 navera_tools/trt/build_engines.py --only sthn --precision fp32'      # ~5 min
# optional, off by default (NAVERA_TRT=1 to use it): python3 navera_tools/trt/build_engines.py --only disk --precision fp16  (~10 min)
```

Engines go to `NAVERA_TRT_DIR` (default `~/.navera_sim/trt/`). `NAVERA_TRT=0` in `navera.env`
turns every engine off, `NAVERA_TRT=1` turns on also those not on by default. Measured gains and
accuracy gates: `docs/test_reports/perf_2026-10-21.md`.

### 3.9 Enable the services

Pick from the table in §1. A typical box with its own sensors, feeding an autopilot over MAVLink:

```bash
sudo systemctl enable navera-discover navera-estimator navera-gps navera-imu navera-rtc \
    navera-pipeline-day navera-output navera-web
# The vehicle's sensors / 2nd GPS over MAVLink, the MAVLink output relay, or the armed
# lock on /mission:
sudo systemctl enable navera-vehicle-link

# Boot without a graphical session
sudo systemctl set-default multi-user.target

# Start now without rebooting (one command: systemd runs navera-discover first)
sudo systemctl restart navera-discover navera-estimator navera-gps navera-imu navera-rtc \
    navera-vehicle-link navera-pipeline-day navera-output navera-web
```

The same `restart` command applies the settings after any change to
`/etc/navera/navera.env` (drop the units you have not enabled). Then run the pre-flight
check (§11) and, once, the reboot test (§2).

### 3.10 Data disk and data files

The map, the route maps, the STHN weights and the model cache are large and are not in
git; the template expects them on a data disk mounted at **`/data`**, in `/data/navera`.
NAVERA does not format or mount disks itself — this is the recommended setup (standard
Ubuntu; adapt the device):

```bash
lsblk -f                                    # find the disk, e.g. /dev/nvme0n1p1 (ext4)
sudo mkfs.ext4 -L navera-data /dev/nvme0n1p1   # ONLY for a new, empty disk: erases it
sudo blkid /dev/nvme0n1p1                   # note its UUID
sudo mkdir -p /data
# /etc/fstab — nofail: the Jetson still boots if the disk is absent or broken
echo 'UUID=<uuid>  /data  ext4  defaults,nofail,x-systemd.device-timeout=10s  0  2' | sudo tee -a /etc/fstab
sudo mount -a && findmnt /data
sudo install -d -o navera -g navera /data/navera /data/navera/areas
```

With `nofail` a missing disk does not stop the boot: the day / night pipelines then find
their files missing, log `… does not exist (data disk not mounted?)` and retry every 10 s
(§2); `check_box.py` reports FAIL for each missing file.

**What goes on it** (paths of `navera.env.example`; copy the files delivered by IRIS
Systems, e.g. from a USB disk, then give them to `navera`):

| Setting | Default path | Content | Needed by |
|---|---|---|---|
| `NAVERA_MBTILES` | `/data/navera/sousse_satellite.mbtiles` | satellite map, MBTiles (the delivered map covers Sousse, z13–z19, ~10 GB) | day and night pipelines, `/mission`, the operator map |
| `DAY_DATASET_DIR` | `/data/navera/day_dataset` | a prepared tile dataset (`dataset.csv`, `images/`, `descriptors_cache.npz`); in operation it is replaced by the route map that `/mission` activates (in `NAVERA_AREAS_DIR`) | day pipeline (must exist to start) |
| `NAVERA_STHN_DIR`, `NAVERA_STHN_WEIGHTS` | `/data/navera/STHN`, `…/STHN/weights/one_stage/model.safetensors` | STHN code and weights (HuggingFace `xjh19972/STHN`) | night pipeline |
| `TORCH_HOME` | `/data/navera/torch_cache` | DINOv2 model cache, filled once with internet (§3.8) | day pipeline |
| `NAVERA_AREAS_DIR`, `NAVERA_TILE_CACHE` | `/data/navera/areas`, `…/areas/downloaded_tiles.mbtiles` | route maps generated by `/mission`, downloaded tiles | `/mission`, day pipeline |

> **Licence of the delivered map.** The Sousse sample map (`sousse_satellite.mbtiles`) is
> presumed to be Esri World Imagery, whose terms forbid storing the tiles offline outside
> licensed ArcGIS applications. It is for **development and IRIS-internal demonstrations
> only**: it may not ship on a sold device, nor on a demo unit that leaves IRIS. A product
> needs a map built from imagery licensed for offline storage on the device (e.g. Airbus, or
> imagery the customer licenses in its own name); free Sentinel-2 (10 m) is legal but too
> coarse for day matching at 300–800 m. See
> [map_licensing_2026-10-21.md](../docs/research/map_licensing_2026-10-21.md).

```bash
sudo rsync -a --info=progress2 /media/<usb>/navera/ /data/navera/
sudo chown -R navera:navera /data/navera
sudo -u navera -H test -r /data/navera/sousse_satellite.mbtiles && echo readable
```

Recordings (`navera_tools/record_session.sh`) also go on this disk (§11, and
[FIELD_TEST_PROCEDURE.md](../docs/FIELD_TEST_PROCEDURE.md)). Maps of other areas: §8.

## 4. Camera

Settings (`/etc/navera/navera.env`): `NAVERA_CAMERA=live` (the default `replay` plays recorded
frames, for demonstration), `NAVERA_CAMERA_INPUT=usb|csi|gst|ros` (or `auto`, §5),
`NAVERA_CAMERA_DEVICE`, `NAVERA_CAMERA_SIZE`, `NAVERA_CAMERA_CALIBRATION`, mounting and
gimbal — all described in `navera.env.example`.

**Frames that are not used.** A frame is marked unusable when the camera is tilted more
than `NAVERA_CAMERA_MAX_TILT_DEG` (default 45°) from vertical, when no attitude is known at
its exposure, or — fixed camera only, never with `NAVERA_CAMERA_GIMBAL=true` — when the
vehicle rotates faster than `NAVERA_CAMERA_MAX_RATE_DPS` (default 30°/s, measured over the
0.2 s before the exposure): a few tens of ms of stamp error are then degrees of tilt, tens
of metres on the ground. The rate is in every frame's metadata (`rate_dps`); the operator
view warns when 30 % of the last minute's frames could not be used.

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

A network camera (RTSP / HTTP) is calibrated live too: replace `--device …` with
`--url "rtsp://<user>:<password>@<camera-ip>:554/<path>"` (read through OpenCV's FFmpeg
backend, over TCP; the password is not printed). `--size` is then only checked when given —
the stream has its own size, which must be `NAVERA_CAMERA_SIZE`. A file made from a URL
records no `camera_id` (that check is for USB cameras). Photos taken beforehand:
`--images <folder>`.

The tool runs as `navera`, which cannot write `/etc/navera`: write the file to a folder
`navera` owns (`/home/navera`, `/var/lib/navera`) and install it with `sudo` as above. (The
example at the top of `calibrate_camera.py` writes `--out /etc/navera/camera.yaml`
directly: that works only when the tool is run with `sudo`.)

Without a calibration, `NAVERA_CAMERA_HFOV_DEG` (an ideal, distortion-free lens) is the
minimum: `check_box.py` reports **FAIL** "camera settings" with neither, and **WARN** "lens
calibration — none" with the field of view only. The `/mission` page does **not** set
`NAVERA_CAMERA_HFOV_DEG`: its "day camera field of view" is `NAVERA_DAY_HFOV_DEG`, used only
for frames that do not state their own field of view (replayed frames); a live frame always
carries its own.

**Camera delay — measured, then learned in flight (`auto_latency`, on by default).** A
frame is dated "arrival − delay"; a wrong delay moves every vision fix by speed × error
along the track. The starting value is `NAVERA_CAMERA_LATENCY_S` (or, when it is 0, the
delay stored in the calibration file by `navera_tools/bench/camera_latency.py --calib`).
While the GPS is trusted, the **day** pipeline also estimates the delay itself from its
GPS-check matches against the GPS track (`navera_common/latency_cal.py`): it needs ≥ 20
samples taken at ≥ 5 m/s with heading or speed changes (a straight line at one speed never
gives one), and replaces the starting value only when the estimate is stable (σ < 0.1 s)
and more than 3 σ away from it. It freezes at a GPS loss or refusal and drops the last
20 s of samples. This is the `day_subscriber` ROS parameter `auto_latency` (default
`true`; `false` = estimate and publish only, in the status JSON `latency`); there is **no
`navera.env` key** for it. The night and celestial pipelines do not estimate the delay.
See [day_pkg/README.md](../day_pkg/README.md).

## 5. Sensor and GPS sources

### Automatic detection (default: `auto`)

With `NAVERA_SENSOR_SOURCE`, `NAVERA_GPS_SOURCE` and `NAVERA_CAMERA_INPUT` set to `auto`
(the template's default), **navera-discover** looks at every boot (~20 s, before the other
units) for:

| What | How it is found |
|---|---|
| The box's IMU and clock | I²C buses 1 and 7: BNO085 at 0x4A/0x4B, DS3231 at 0x68 → `NAVERA_BOX_IMU` / `NAVERA_BOX_RTC` (1 or 0) and their bus; without the chip `navera-imu` / `navera-rtc` stay idle |
| A GPS receiver | checksummed NMEA **with satellite data** (GSV/GSA: an autopilot's NMEA output has none) on `/dev/ttyTHS*`, `/dev/ttyUSB*`, `/dev/ttyACM*` (4800–921600 baud); several: the one with a fix, wired UART first, and a warning |
| An autopilot (any MAVLink) | an autopilot heartbeat (ground stations, cameras, companions ignored) on those serial ports, on UDP 14550/14551, or on `NAVERA_DISCOVER_MAVLINK`; it is then asked for attitude, rangefinder, height above home and its GPS receiver types (`GPS_TYPE`/`GPS_TYPE2`). Several: its wired TELEM port first, and a warning when they are different autopilots |
| A ROS vehicle | `sensor_msgs` Imu / NavSatFix / Image / Range topics on ROS domain 0, `ROS_DOMAIN_ID` and `NAVERA_DISCOVER_ROS_DOMAINS` (8 s of DDS discovery) |
| Cameras | USB (`/dev/v4l/by-id/*-video-index0`, except the star camera `NAVERA_STAR_CAMERA_DEVICE`), CSI (Jetson video inputs); a written `NAVERA_CAMERA_DEVICE` is always kept; several USB cameras: the first, with a warning — set `NAVERA_CAMERA_DEVICE` |

and chooses: **attitude** box IMU > autopilot > ROS; **GPS** box receiver > autopilot's 2nd GPS
> ROS; **camera** USB > CSI > ROS (depth images excluded; a ROS camera is flagged "check it
looks at the ground"). The autopilot's second GPS is used only when `GPS_TYPE2` says it is
a real receiver (fix or not yet) — never type 14, the MAVLink-fed GPS that NAVERA itself
feeds (a loop), and not when the types cannot be read. **No GPS found: the GPS service
stays idle** — no default port is ever opened. **Outputs:** an autopilot found → NAVERA's
position over MAVLink, as the autopilot's companion (its system id), on the same link,
relayed by `navera-vehicle-link` (local UDP 14650), no mavlink-router needed
(`NAVERA_MAVLINK_URL=off` to never send it). **A PX4 autopilot is recognised** (heartbeat
`MAV_AUTOPILOT_PX4`): PX4 ignores `GPS_INPUT`, so with `NAVERA_MAVLINK_URL` empty the output
is left off and the report says "CHECK output: the autopilot is PX4 …" — nothing to set by
hand; do not write an address there on a PX4 vehicle
([PX4_INTEGRATION.md](../docs/PX4_INTEGRATION.md)); `NAVERA_MAVLINK_SYSID` is
set to the autopilot's system id, used by both MAVLink nodes; a ROS vehicle →
`/navera/fix`. A ROS vehicle is used only when it is on NAVERA's ROS domain with
`ROS_LOCALHOST_ONLY` not 1, or with `ROS_DOMAIN_ID=auto` (NAVERA then joins it, §6);
otherwise the report says on which domain it was seen. A
`ROS_DOMAIN_ID` / `ROS_LOCALHOST_ONLY` written in `navera.env` is never changed. A port
another program holds, the kernel console (`console=` on the kernel command line) and a
port with an active `serial-getty` login are never probed; only an identified autopilot is
written to (its data-stream and parameter requests).

A value written in `navera.env` instead of `auto` is always kept. See what was found:
`navera_tools/check_box.py` (first lines; lines with "NO" or "CHECK" are WARN) or
`/var/lib/navera/discovery.json`. **Discovery runs once per boot.** A device connected
later — or a ROS vehicle whose computer boots after NAVERA — is not seen: reboot, or
`sudo systemctl restart navera-discover` then the units concerned (§3.9). For a ROS
vehicle that may boot late, write its sources (`NAVERA_SENSOR_SOURCE=ros`,
`NAVERA_ROS_IMU_TOPIC`, `NAVERA_GPS_SOURCE=ros`, `NAVERA_ROS_GPS_TOPIC`, …) and its
`ROS_DOMAIN_ID` instead of relying on `auto`. Verified: this Jetson's bench (a ROS robot simulation found, no box
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
| `ros` | `NAVERA_ROS_IMU_TOPIC` (sensor_msgs/Imu, contract in §6) — required | `NAVERA_ROS_ALTITUDE_TOPIC` (sensor_msgs/Range), optional | the vehicle's ROS graph (§6) |

**GPS — `NAVERA_GPS_SOURCE`** (`navera_boot_gps.sh`; every mode publishes
`/navera/sensors/gps_fix` and `/navera/estimate/gps` the same way):

| Value | GPS | Node |
|---|---|---|
| `serial` (the key absent) | the box's receiver, NMEA on `NAVERA_GPS_PORT` (default `/dev/ttyTHS1`) at `NAVERA_GPS_BAUD` (default 9600) | `gps_node` |
| `vehicle` | the autopilot's **second** GPS (`GPS2_RAW`, 3D fix or better), read by `navera-vehicle-link` and republished from `/navera/vehicle/gps2`: altitude above the ellipsoid when the autopilot sends `alt_ellipsoid` (otherwise above mean sea level, with a warning: then set `NAVERA_GROUND_ALTITUDE_M` as MSL too), accuracy from the receiver's `h_acc` / `v_acc` | `ros_gps_node` |
| `ros` | the vehicle's `sensor_msgs/NavSatFix` topic `NAVERA_ROS_GPS_TOPIC` (required); BEST_EFFORT or RELIABLE publishers | `ros_gps_node` |
| `none` (auto finds nothing) | no GPS: the service stays idle | — |

A GPS position is **FIX** only with a stated accuracy: a covariance of a defined type
(approximated, diagonal known or known) with a horizontal sigma of at least 1 cm. A
NavSatFix with no covariance, an all-zero one or an undefined type is used as **DEGRADED**
("uncertainty unknown"): it is not sent to the autopilot by default and cannot be checked
against vision. A covariance that is not symmetric with a positive semi-definite
horizontal block is refused outright.

**NAVERA needs a GPS fix at start, in every mode** — or an operator start position. The
first GPS position is the prior every vision pipeline searches around: without it day
vision reports "no position prior (waiting for a GPS fix)" (whole-map search is disabled
because it is not reliable). Where there is no GPS at all, the `/mission` page's **Start
without GPS** (§8) gives day vision a search area instead. After a service restart in
flight, day vision can resume from its last position if it is less than 5 minutes old (§9).

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
closed. `check_box.py` FAILs "ROS network" when a source is `ros` while
`ROS_LOCALHOST_ONLY=1`.

`ROS_DOMAIN_ID=auto`: at each boot navera-discover looks for a ROS vehicle (Imu / NavSatFix /
Image topics) on domain 0 and the domains of `NAVERA_DISCOVER_ROS_DOMAINS`. Found: it writes
`ROS_DOMAIN_ID=<that domain>` and `ROS_LOCALHOST_ONLY=0` in `/var/lib/navera/discovered.env`,
which every other NAVERA unit loads after `navera.env`, so they all join that domain. None
found: the units run on domain 42, loopback only (`navera_boot_lib.sh`). **Verified by unit
tests only** (`navera_common/test/test_discovery.py`: the decision, and discovery running with
`auto`); joining a real vehicle's network has not been tested. When the vehicle's domain is
known, writing its number (as above) is the deterministic choice. Discovery runs once per boot: a
vehicle computer that boots after NAVERA is not seen (restart navera-discover, or write
the sources).

**What NAVERA expects from the vehicle's ROS topics** (`NAVERA_SENSOR_SOURCE=ros`):

| Topic | Contract |
|---|---|
| `NAVERA_ROS_IMU_TOPIC` (sensor_msgs/Imu) | `orientation` = the vehicle body's attitude in **ENU** (REP-103: x east, y north, z up; body x forward, y left, z up), as a unit quaternion. **Yaw is referenced to true north**: NAVERA applies no declination to a ROS IMU (only its own box IMU node converts magnetic to true north), and it uses the heading to orient frames (night vision turns them north-up) and to turn day vision's dead-reckoning. An IMU whose yaw is magnetic, or arbitrary (6-axis IMU), gives wrong headings. Header stamps on the box's clock (synchronised computers). Rate **25 Hz or more** recommended: `check_box.py` WARNs below 25 Hz and FAILs below 10 Hz, and the live camera needs attitude samples less than 0.4 s apart around each exposure (0.2 s before it for the rotation-rate check). Identical samples for 50 messages in a row are treated as a frozen sensor. |
| `NAVERA_ROS_ALTITUDE_TOPIC` (sensor_msgs/Range) | height above ground, metres (a downward rangefinder); a reading at `min_range` / `max_range` is "no echo" |
| `NAVERA_ROS_GPS_TOPIC` (sensor_msgs/NavSatFix) | a real receiver (never the vehicle's fused position, never `/navera/fix`); altitude above the WGS84 ellipsoid; a covariance with sigma ≥ 1 cm and a defined type for a FIX (§5) |
| `NAVERA_CAMERA_TOPIC` (sensor_msgs/Image) | a downward camera; the image stamp is taken as the exposure instant (minus `NAVERA_CAMERA_LATENCY_S`) |

QoS: the IMU, GPS and rangefinder subscriptions are BEST_EFFORT (depth 50), so both
BEST_EFFORT publishers (most drivers, MAVROS) and RELIABLE ones are received.

**ROS output.** `navera-output` publishes the arbiter's decision as `sensor_msgs/NavSatFix`
on `/navera/fix` (`NAVERA_ROS_FIX_TOPIC` sets another name; set but empty turns it off):

- `header.frame_id` = `NAVERA_ROS_FIX_FRAME_ID` (default `navera`): set it to a frame of the
  vehicle's TF tree when a consumer such as `navsat_transform` uses it;
- a GPS position: status FIX, `status.service` = GPS; a vision / celestial position:
  status FIX with `status.service` = 0 (no satellite service), so a consumer can tell them
  apart; the accuracy (stated accuracy plus its lag, §7) is always in the covariance;
- vision / celestial positions are sent to ROS by default (`NAVERA_ROS_FORWARD_DEGRADED`,
  default true), independently of `NAVERA_FORWARD_DEGRADED` (the autopilot switch), and
  only with a stated accuracy — never with none. `false`: ROS gets "no fix" for them unless
  `NAVERA_FORWARD_DEGRADED=true`.

## 7. Output to the vehicle

`navera-output` turns the arbiter's decision into a GPS for the vehicle:

| Setting | Output |
|---|---|
| `NAVERA_NMEA_PORT`, `NAVERA_NMEA_BAUD` | NMEA 0183 GGA + RMC on a serial port |
| `NAVERA_MAVLINK_URL` | MAVLink `GPS_INPUT` (ArduPilot; **PX4 ignores this message**), e.g. `serial:/dev/ttyTHS2:921600`; `udpout:127.0.0.1:14650` = through `navera-vehicle-link`'s relay on the one autopilot link; `off` = never |
| `NAVERA_ROS_FIX_TOPIC` | ROS NavSatFix (default `/navera/fix`, §6) |

**Vision positions are DEGRADED, and DEGRADED positions are not sent to the autopilot by
default.** Day vision's accuracy is not yet established with NAVERA's camera
([VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md)), so when GPS is lost the autopilot
receives "no fix" and its own failsafe acts — unless forwarding is enabled explicitly:

| Setting | Default | Meaning |
|---|---|---|
| `NAVERA_FORWARD_DEGRADED` | false | `true`: send vision / celestial positions over MAVLink (and ROS), flagged "estimated", 0 satellites. Only `true`/`false` (`1`/`0`, `yes`/`no`, `on`/`off`): any other value stops the service with the reason |
| `NAVERA_DEGRADED_SIGMA_M` | none | the accuracy (m, 1 σ) the autopilot must assume — **required** with forwarding (the node refuses to start without it, or above 1000 m); when the source states a worse accuracy itself, the worse is sent. Use a value you have measured. **ArduPilot's EKF3 caps a stated accuracy at 100 m** (`AP_NavEKF3`: R = constrain(accuracy, `EK3_POSNE_M_NSE`, 100 m)²): above 100 m the autopilot trusts the position **more** than stated — `check_box.py` WARNs |
| `NAVERA_NMEA_FORWARD_DEGRADED` | false | NMEA carries no accuracy an autopilot uses (ArduPilot fuses an NMEA GPS with its own ~0.5 m noise): with forwarding, degraded positions go over MAVLink and ROS only and NMEA says "no fix" for them, unless this is `true` (a warning is logged; not recommended) |
| `NAVERA_MAX_MEASUREMENT_AGE_S` | 5.0 | a position measured longer ago is not sent (also: a position older than 5 s is no longer current) |
| `NAVERA_BRIDGE_MAX_S` | 10 | a gap in the forwarded vision positions is bridged this long at most (0 = never; 0 recommended on a fixed-wing with an airspeed sensor, docs/ARDUPILOT_INTEGRATION.md §3) |

**Vision positions are carried to the present.** A vision position describes where its
photo was taken, 1–2.5 s before it reaches the output. The output learns the ground
velocity from the recent positions (any source, weighted fit over 20 s) and carries a
non-GPS position from its measurement instant to now, adding the speed error × its age to
its accuracy; with no velocity known it sends it stamped with its measurement instant and
its accuracy grown by the maximum speed (`NAVERA_MAX_SPEED_KMH`) × its age. GPS positions
are not carried (the autopilot's `GPS_DELAY_MS` covers their small latency).

**Relay without a vehicle link.** When the MAVLink output goes to the local relay
(`udpout:127.0.0.1:…`) and no vehicle link is connected to an autopilot, the output logs
every 30 s that the autopilot receives NOTHING from NAVERA; `check_box.py` FAILs that
setting when `NAVERA_VEHICLE_MAVLINK_URL` is empty. `check_box.py` also FAILs a serial
port used by two programs (GPS, NMEA output, MAVLink output, vehicle link) and a MAVLink
address it cannot parse.

A position coarser than 1 km is never forwarded (`max_forward_sigma_m`). Full rules:
[navera_output/README.md](../navera_output/README.md). MAVLink addresses: one format
everywhere (`serial:/dev/<port>:<baud>`, `udpin:`, `udpout:`, `tcp:`). One serial port per
program: with a single autopilot port, `navera-vehicle-link` owns it and relays the output
(`NAVERA_MAVLINK_URL=udpout:127.0.0.1:14650`, what navera-discover writes); with two TELEM
ports each NAVERA connection can have its own; `mavlink-router` is a third way. Both
MAVLink nodes use the autopilot's system id (`NAVERA_MAVLINK_SYSID`, default 1). Wiring
and autopilot parameters: [ARDUPILOT_INTEGRATION.md](../docs/ARDUPILOT_INTEGRATION.md),
[PX4_INTEGRATION.md](../docs/PX4_INTEGRATION.md) (not tested).

## 8. Web interface and the `/mission` page

`navera-web` serves, on port 8181 (all interfaces): `/operator` (operator view), `/`
(dashboard) and `/mission` (mission preparation; day and night bridges — the celestial
bridge, `NAVERA_PIPELINE=cn`, has no `/mission` page).

**Control token.** Every control action (start a mission, any `/mission` change) needs the
`X-Navera-Token` header equal to `NAVERA_WEB_TOKEN`; with no token configured the interface
is read-only. After 5 wrong codes within 60 s, an address is refused (HTTP 429) for 60 s.
Over plain HTTP the token crosses the network in clear: set
`NAVERA_TLS_CERT` / `NAVERA_TLS_KEY` (HTTPS only, TLS ≥ 1.2; see `navera.env.example`), and
do not expose port 8181 beyond the vehicle's own network (no port forwarding; firewall it
on any interface that leaves the vehicle).

**What `/mission` can change** (`simulation_web/mission_prep.py`, `SETTINGS`) — written to
`/var/lib/navera/settings.env`, which overrides `navera.env`:

| Key | Validation |
|---|---|
| `NAVERA_VEHICLE_TYPE` | drone, plane, boat, robot, other (label) |
| `NAVERA_MAX_SPEED_KMH` | 4–1890 |
| `NAVERA_DAY_HFOV_DEG` | 5–170 — replayed frames only (a live frame states its own field of view; this is **not** `NAVERA_CAMERA_HFOV_DEG`) |
| `NAVERA_THERMAL_HFOV_DEG` | 5–170 — frames that do not state their own field of view |
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
matches against the activated map. Saving a mission under an existing name asks before
replacing it.

**Areas outside the delivered map.** The delivered MBTiles map covers Sousse only. For any
other route, either:

- set `NAVERA_TILE_URL` to an XYZ tile service (a URL template with `{z}`, `{x}` and `{y}`,
  in the order the provider uses) and generate the route on `/mission` **with internet access**: the
  tiles the onboard map lacks are downloaded into `NAVERA_TILE_CACHE`, then the route map
  works offline; or
- obtain an MBTiles map of the area (with zoom 17, the level route maps are built at by
  default) and point `NAVERA_MBTILES` at it; or, in the NAVERA shell (§11),
  `ros2 run day_pkg prepare_area.py --mbtiles <map> --out <dir> --route lat,lon lat,lon …
  [--fetch-url <template> --cache <mbtiles>]` (`--check` only reports the coverage), then
  point `DAY_DATASET_DIR` at `<dir>`.

**The imagery licence must allow storing its tiles offline in a product** — many public
tile services forbid it; check before setting `NAVERA_TILE_URL`
([VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md), limitation 5). **Esri World Imagery
does not allow it** (Esri Master Agreement §3.2(c): no download or storage outside Esri
Content Packages in licensed ArcGIS apps): use it for development only
([map_licensing_2026-10-21.md](../docs/research/map_licensing_2026-10-21.md)). Missing tiles are
reported: inside them day vision has nothing to match.

**Terrain warning.** At planning, the page estimates the stretches of the route without
landmarks (uniform tiles of the map files: sea, lakes, uniform ground) and says so; the
figure is measured again when the map is generated. Over those stretches vision has
nothing to match: NAVERA carries on along its measured course for up to 2 minutes (its
stated accuracy growing, at most 500 m), then gives no position and the vehicle relies on
its own navigation. Prefer a route along the coast or over varied ground.

**Boats and low cameras.** Day vision needs land with texture in the camera's footprint.
At sea there are no landmarks: away from the coast a boat gets at most the 2 minutes of
dead-reckoning above, then nothing. A camera only a few metres above the water sees a
small, oblique footprint, which the straight-down matching against a satellite map is not
designed for; NAVERA has **not** been tested on a boat with a real camera (the boat results
in VALIDATION_STATUS.md are ArduPilot simulator runs with simulated vision). Treat a boat
installation as unvalidated.

**Start without GPS.** Where there is no GPS at all at power-on, the page's "Start without
GPS" section (latitude, longitude and accuracy 5–20000 m, or the route's departure; the
access code) gives day vision a **search area**: the bridge publishes it latched on
`/navera/operator/start_position`, and day vision, while no GPS is trusted, searches there
in a circle as wide as the stated accuracy. It is never published as a position nor sent to
the autopilot: NAVERA gives a position only once vision matches. Night and celestial
vision do not use it.

**Refused in flight.** "Apply settings", "Activate" and "Generate" are refused while the
vehicle is **armed** (`refused: the vehicle is armed: disarm it before changing NAVERA`),
while NAVERA's own positions show it **moving** faster than 1.5 m/s (`refused: the vehicle
is moving (N m/s): stop it before changing NAVERA` — this works without any autopilot
link), or while NAVERA is **navigating without GPS** (`refused: NAVERA is navigating
without GPS right now: a restart would interrupt it`; for "Generate": `… generating a map
would take the processor vision needs`). The armed state comes from `navera-vehicle-link`
(`/navera/vehicle/status`). Saving settings is still possible; they take effect at the next
"Apply".

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

**Night uses the same camera settings as day.** The night launch
(`night_pipeline.launch.py`, `NAVERA_CAMERA=live`) reads the live camera with the
`NAVERA_CAMERA_*` keys — there is no separate thermal-camera key. Switching to night
therefore also means pointing those keys at the **thermal** camera, and back at the day
camera when switching to day:

```bash
# /etc/navera/navera.env — keep both blocks, one of them commented out
# --- day camera ---
#NAVERA_CAMERA_INPUT=usb
#NAVERA_CAMERA_DEVICE=/dev/v4l/by-id/usb-<day camera>-video-index0
#NAVERA_CAMERA_SIZE=1920x1080
#NAVERA_CAMERA_CALIBRATION=/etc/navera/camera.yaml
# --- thermal camera (e.g. an RTSP camera; a USB thermal core: usb + its by-id device) ---
NAVERA_CAMERA_INPUT=gst
NAVERA_CAMERA_GST_PIPELINE="rtspsrc location=rtsp://<user>:<password>@<camera-ip>:554/Streaming/Channels/201 latency=0 ! decodebin ! videoconvert ! video/x-raw,format=BGR ! appsink name=sink drop=true max-buffers=1 sync=false"
NAVERA_CAMERA_SIZE=1280x720
NAVERA_CAMERA_CALIBRATION=/etc/navera/thermal.yaml
NAVERA_CAMERA_LATENCY_S=1.0          # measured for this camera (Hikvision bench unit: ~1.0 s)
```

- Write `NAVERA_CAMERA_INPUT` explicitly: with `auto`, navera-discover picks the USB
  camera it finds (the day camera), and it never finds an RTSP camera.
- **Thermal calibration.** The thermal camera needs its own lens calibration file, made at
  its own resolution (the live camera refuses a file made at another `NAVERA_CAMERA_SIZE`).
  A thermal camera does not see a printed checkerboard: warm the board (sun, a heat lamp)
  or use a board of two materials of different emissivity, so the squares show in the
  thermal picture, then run `calibrate_camera.py` as in §4 — `--url <rtsp URL>` for a
  network camera, `--device` for a USB one — usually with `--model pinhole` (narrow
  thermal lenses). Without a calibration, set `NAVERA_CAMERA_HFOV_DEG` to the thermal
  lens's field of view (ideal lens; `check_box.py` warns).
- The camera delay (`NAVERA_CAMERA_LATENCY_S`) is per camera too; the screen-flash bench
  (`camera_latency.py`) does not work with a thermal camera (it does not see a screen):
  set it by hand. The day pipeline's automatic delay estimate (§4) does not run at night.
- `NAVERA_THERMAL_HFOV_DEG` is for **replayed** thermal frames only; a live frame states its
  own field of view (from the calibration or `NAVERA_CAMERA_HFOV_DEG`).
- Status: night vision is not flown; a 160 × 120 thermal camera is too coarse for it
  ([VALIDATION_STATUS.md](../docs/VALIDATION_STATUS.md)).

The celestial unit (CPU only) has no `Conflicts=`: it can run beside day or night, and the
arbiter uses it after them (GPS > day > night > celestial). It has two modes, chosen by
`NAVERA_STAR_CAMERA_INPUT` (`cn_pipeline.launch.py`):

- **`NAVERA_STAR_CAMERA_INPUT` set — a live star camera.** The live camera is read with the
  `NAVERA_STAR_CAMERA_*` settings (same keys as the day camera, prefix `NAVERA_STAR_CAMERA_`:
  `_INPUT`, `_DEVICE`, `_SIZE`, `_FPS`, `_CALIBRATION`, `_HFOV_DEG`, `_GST_PIPELINE`); the
  attitude comes from the IMU at each exposure (no IMU: no position), the time from the
  clock (DS3231 / system clock), the prior from NAVERA's last position. Mounting:
  `NAVERA_STAR_CAMERA_ELEVATION_DEG`, `NAVERA_STAR_CAMERA_AZIMUTH_DEG`; accuracy:
  `NAVERA_ATTITUDE_SIGMA_DEG`; `NAVERA_MAGNETIC_DECLINATION_DEG` only for an attitude source
  in magnetic north (see `navera.env.example`). A star camera on USB is never taken as the
  day camera when `NAVERA_STAR_CAMERA_DEVICE` is written. The celestial position is coarse
  (kilometres: ~1.85 km per arcminute of attitude error).
- **Unset (the template's default) — a demonstration.** The service replays a bundled sample
  sky image with launch-time attitude, time and operating-area constants (Sousse); its
  camera waits for a mission start from the celestial bridge (`NAVERA_PIPELINE=cn`). This
  is not navigation.

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
python3 /home/navera/isaac_ros_common/navera_tools/check_box.py --no-ros   # settings and files only
ros2 topic echo /navera/nav_status --once
```

`check_box.py` reads `discovered.env` itself (so it judges the settings the services run
with) and, before listening to the topics, checks the configuration statically: what
navera-discover found; one program per serial port; MAVLink addresses that parse; a relay
output without a vehicle link; the forwarding switch and accuracy (FAIL without an accuracy
or above 1000 m, WARN above 100 m); NMEA forwarding; ROS sources with
`ROS_LOCALHOST_ONLY=1`; the map file opens and holds tiles; the route map is prepared.

From any shell:

```bash
/home/navera/isaac_ros_common/deploy/check_boot.sh   # every enabled unit, restarts, then check_box
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
sudo systemctl disable --now navera-discover navera-estimator navera-gps navera-imu navera-rtc \
    navera-pipeline-day navera-pipeline-night navera-pipeline-cn \
    navera-output navera-vehicle-link navera-web
sudo rm /etc/systemd/system/navera-*.service /etc/sudoers.d/navera-web
sudo rm /home/navera/navera_boot_*.sh
sudo systemctl daemon-reload
# Settings and state, if no longer wanted:  sudo rm -r /etc/navera /var/lib/navera
```
