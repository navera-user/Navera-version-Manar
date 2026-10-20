# navera_common — shared helpers

Pure-Python library used by every NAVERA package (ament_python, no nodes, no topics of its
own). Most modules have no ROS dependency so they can be unit-tested alone; `params` and
`qos` import `rclpy`.

## Modules
| Module | Content |
|---|---|
| `lifecycle` | `die_with_parent()`: a node dies with its launcher (no orphans) |
| `params` | `declare_float()`: float parameters that accept integer overrides |
| `qos` | `SENSOR_QOS` (BEST_EFFORT, VOLATILE) for the sensor topics NAVERA reads from others (a vehicle's IMU, GPS, rangefinder) |
| `geo` | `dead_reckon()` (refuses unknown motion), `is_finite_latlon()` |
| `prior` | `GpsPrior`: last valid GPS fix as the vision prior |
| `pairing` | `FramePairer`: image/meta pairing on the image stamp; `exposure_stamp()` |
| `health` | `FrozenSampleDetector`, `RetryTimer` for sensor drivers |
| `altitude` | `AltitudeEstimator`: height of the camera above the ground (AGL), from the sources a vehicle may have |
| `camera_model` | `CameraModel` and camera geometry (rotations, nadir homography, ground m/px, `parse_crop`) shared by the camera node and the vision pipelines |
| `covariance` | `horizontal_sigma()`, `covariance_sane()`: checks and summaries of a 3x3 position covariance (row-major, E/N/U, m²) |
| `frame_builder` | `FrameBuilder`: a raw camera frame + the sensors at its exposure → a frame vision can use |
| `sensor_history` | `History`, `slerp`, `lerp`: short time-indexed sensor histories, read at a frame's exposure time |
| `track` | `TrackVelocity`: ground velocity from the vehicle's recent measured positions, for dead-reckoning |
| `state_store` | `save()` / `load()`: small facts NAVERA must remember across a restart of its services |
| `gps_crosscheck` | trusted GPS against an independent position of stated accuracy: when to refuse GPS |
| `vehicle` | vehicle settings shared by the launch files (max speed, IMU, sensor topics, live camera, shadow mode) |
| `discovery` | what is connected to the box (I²C, serial NMEA/MAVLink, cameras, ROS topics) and which source to use for what; also a CLI |

## Environment variables read
- `vehicle`: `NAVERA_MAX_SPEED_KMH`, `NAVERA_SHADOW_MODE`, `NAVERA_SENSOR_SOURCE`,
  `NAVERA_GPS_SOURCE`, `NAVERA_ROS_IMU_TOPIC`, `NAVERA_ROS_GPS_TOPIC`,
  `NAVERA_ROS_ALTITUDE_TOPIC`, `NAVERA_IMU_MOUNT_RPY`, `NAVERA_DECLINATION_DEG`,
  `NAVERA_GROUND_ALTITUDE_M`, and the live-camera keys under the prefixes `NAVERA_CAMERA_*` /
  `NAVERA_STAR_CAMERA_*` (`INPUT`, `DEVICE`, `TOPIC`, `SIZE`, `FPS`, `HFOV_DEG`, `CALIBRATION`,
  `CROP`, `GIMBAL`, `GST_PIPELINE`, `LATENCY_S`, `MAX_RATE_DPS`, `MAX_TILT_DEG`, `MOUNT_RPY`).
- `discovery`: `ROS_DOMAIN_ID`, `NAVERA_DISCOVER_ROS_DOMAINS`, `NAVERA_DISCOVER_MAVLINK`,
  `NAVERA_SENSOR_SOURCE`, `NAVERA_GPS_SOURCE`, `NAVERA_CAMERA_INPUT` (`auto` or unset = decide),
  and writes the decided `NAVERA_*` settings (GPS port/baud, MAVLink URL/sysid, ROS topics,
  box IMU/RTC buses, camera devices…).
- `state_store`: `NAVERA_STATE_DIR` (default `/var/lib/navera` when writable, else
  `~/.local/state/navera`).

## How to run
Imported by the nodes; nothing to launch. The one command-line entry point is the boot
discovery, run by `navera-discover.service` (`deploy/systemd/navera_boot_discover.sh`):

```bash
python3 -m navera_common.discovery --env-out /var/lib/navera/discovered.env \
    --json-out /var/lib/navera/discovery.json      # --ros-wait 8.0 (s) by default
```

Unit tests: `navera_common/test/`.
