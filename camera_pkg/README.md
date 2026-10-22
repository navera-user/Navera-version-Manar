# camera_pkg — frame source

`camera_publisher` feeds a localizer with frames, either replayed from a CSV + image folder
(test data) or from a live CSI/USB camera. The same node runs under the `day`, `thermal`
and `celestial` namespaces (launch files `day.launch.py`, `thermal.launch.py`,
`celestial.launch.py`).

## Outputs (relative to the namespace)
| Topic | Type | |
|---|---|---|
| `image_raw` | sensor_msgs/Image | the frame |
| `frame_meta` | std_msgs/String (JSON) | frame id, `image_stamp_ns` (pairing key), CSV lat/lon when GPS is "valid" in the replay, altitude/heading/speed **only when known** (else null), `image_missing` |
| `gps` | sensor_msgs/NavSatFix | replayed CSV position (NaN when not valid) |

## Inputs
`camera/start` (Bool, latched: true = go, false = pause + rewind), the localizer's
`localizer_ready` (Bool, latched) and `frame_done` (Int32 ack) — see
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §5.

## Key parameters
`source` (csv | camera), `csv_path`, `images_dir`, `fps`, `flow_control` (rate | ack),
`wait_for_ready`, `start_paused`, `default_gps_valid` (replay: treat CSV lat/lon as GPS),
`image_encoding` (bgr8 | mono8 | mono16).

## Notes
- Unknown motion is never invented: a CSV row without speed/heading/altitude produces null.
- Live mode never claims GPS (the GPS is a separate node).
- A `camera_info` publisher is created but not yet populated (no calibration published).
- `live_camera` (the live source) refuses frozen pictures (D24): a frame whose time does not
  advance, whose picture is identical to the previous one, or nearly identical while the IMU / GPS
  say the vehicle moved is published with `usable: false`, reason `camera image frozen: …` (no
  localizer makes a position from it), reported on the latched `camera_health` topic (JSON:
  `frozen`, `reason`, `frozen_frames`, `frozen_s`); a camera device frozen longer than
  `frozen_restart_s` (20 s) exits so systemd reopens it. Parameters `frozen_still_diff`,
  `frozen_motion_deg`, `frozen_motion_m`, `frozen_restart_s`.
- A camera device (usb / csi / gst) that gives no frame for `camera_stall_restart_s` (10 s:
  unplugged, USB reset, stuck driver, stalled stream, or a grab that never returns) is reported on
  `camera_health` (`stalled: true`, `reason`) and `live_camera` exits, so systemd restarts the
  pipeline and reopens it (`camera_pkg/grab_watchdog.py`). Before, it waited for 50 failed grabs,
  which with V4L2's 10 s grab timeout took minutes. Use the stable `/dev/v4l/by-id/...` name: a
  replugged camera may get another `/dev/videoN`.

## `insta360_imu` — the Insta360 One R's own IMU as `sensor_msgs/Imu`

The product camera (Insta360 One R, USB "Android" mode, reverse-engineered protocol) streams its
gyro + accelerometer (~500 Hz) with the video. `insta360_imu.py` publishes it for the ROS
pipeline (day_subscriber's gyro heading carry, celestial "allsky360" up from the vehicle IMU).
The protocol and the raw-recording reader are **shared** with the field tools
(`navera_common/insta360_protocol.py`, imported by `navera_tools/field/insta360_usb.py`); the
processing (clock, bias, mount) is `camera_pkg/insta360_imu.py` (no ROS).

```bash
# replay a field recording (no camera needed): the recording's timeline, shifted to start now
ros2 launch camera_pkg insta360_imu.launch.py replay_path:=$HOME/navera-field/2026-10-20_1150/raw
# live camera (NOT while the navera-field service holds it: one process per camera)
ros2 launch camera_pkg insta360_imu.launch.py source:=live
# day pipeline on this gyro
ros2 run day_pkg day_subscriber.py --ros-args -p gyro_imu_topic:=/navera/sensors/insta360/imu \
    -p gyro_heading_noise_dps_rthz:=0.004 -p gyro_heading_bias_dps:=0.1
# the noise of a recording at rest (Allan deviation, bias creep)
python3 -m camera_pkg.insta360_imu ~/navera-field/2026-10-20_1150/raw
```

**Output** `/navera/sensors/insta360/imu` (`topic`), sensor_msgs/Imu, RELIABLE depth 50, 100 Hz
(500 Hz records averaged by `decimation` 5):

| Field | Content |
|---|---|
| `header.stamp` | host time (`time.time()`, the clock NAVERA frames are stamped with) of the sample: the camera's ms clock + an offset taken from the least-delayed IMU packet over 20 s (it follows drift at ≤ 2 ms/s, jumps on a host clock step or a camera restart; stamps never go backwards). A frame of the same stream maps the same way: `CameraClock.to_host(video packet ms - FRAME_STAMP_LAG_MS)` |
| `header.frame_id` | `frame_id` (default `insta360_imu_link`): a frame **aligned with the vehicle body** (x forward, y left, z up, REP-103) at the camera — the mount rotation is already applied |
| `angular_velocity` | rad/s, body frame, gyro bias removed (calibration file, then re-measured whenever the camera is at rest: `bias_at_rest`) |
| `linear_acceleration` | m/s², specific force **with** gravity (REP-145: +9.81 on z at rest), calibrated (bias/scale) |
| `orientation` | not given: `orientation_covariance[0] = -1` |
| covariances | diagonal: (`gyro_sample_std_dps`, `accel_sample_std_g` measured at rest)² / `decimation` |

**Mount (camera → body).** Camera IMU frame (measured 2026-10-17): +x up when the camera stands,
+y the LEFT fisheye circle's optical axis (the right circle looks along -y), +z = x × y.
`mount_axes` names the camera axes along body x, y, z: `+y,+z,+x` (default: standing, left circle
forward), `-y,-z,+x` (standing, right circle forward), `+x,+y,+z` (identity). Mirrors and repeated
axes are refused. `mount_roll_deg` / `mount_pitch_deg` / `mount_yaw_deg`: a small trim after it
(ROS fixed axis, body frame).

**Parameters** (`config/insta360_imu.yaml`): `source` (replay | live), `replay_path` (a `<test>/raw`
folder or one `raw360_NNNN.bin`), `replay_rate` (1 real time, 0 as fast as possible — pacing only),
`replay_clock` (now | recorded), `replay_loop`, `exit_at_end`, `topic`, `frame_id`, `mount_axes`,
`mount_*_deg`, `decimation`, `bias_at_rest`, `calibration_file` ("" = `NAVERA_INSTA360_IMU` or
`~/.navera_sim/insta360_usb_imu.json`, the 6-position calibration), `gyro_sample_std_dps` (0.085),
`accel_sample_std_g` (0.002).

**Measured at rest** (2026-10-20, recordings `2026-10-20_1150` and `day_image_2026-10-20/raw40`,
41 s and 40 s, camera standing on a table, 497.7 Hz):

| | |
|---|---|
| gyro white noise | 0.0025–0.0033 deg/s/√Hz (Allan deviation at 1 s, longest quiet stretch 13 s / 20 s); per-sample std 0.069–0.085 deg/s |
| gyro bias | Allan floor 0.0008–0.0026 deg/s; creep away from a 2 s at-rest estimate within 40 s: ≤ 0.015 / 0.047 deg/s (worst axis), ≤ 0.005 / 0.021 deg/s about the vertical; turn-on bias about the vertical −0.074 vs −0.266 deg/s in the two sessions |
| accelerometer | per-sample std 0.0011–0.0020 g |
| clock | IMU packets arrive 20 ms (median) above the least-delayed one, 91 ms at most |
| heading drift, 38 s at rest | with `bias_at_rest`: −0.02 / −0.03 deg; with the 2026-10-17 calibration file only: −1.7 / +5.0 deg |

For day_subscriber: `gyro_heading_noise_dps_rthz` **0.004** (measured 0.0025–0.0033);
`gyro_heading_bias_dps` **0.1** kept (0.05 is supported only within ~40 s of a rest; the bias
beyond a minute, in flight, is not measured — a longer still recording and a drive are needed).
