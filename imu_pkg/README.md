# imu_pkg — box IMU driver (BNO085, optional)

> **Reference kit.** The IRIS reference kit no longer fits a BNO085: its IMU is the **Insta360
> One R camera's own IMU** (gyroscope + accelerometer, ~500 Hz, no magnetometer and no attitude
> quaternion), read over the camera's USB link by `camera_pkg`'s `insta360_node`
> (`/navera/sensors/insta360/imu`, attitude from `camera_pkg/insta360_attitude.py`), started at
> boot by `navera-insta360` and selected with `NAVERA_SENSOR_SOURCE=insta360` (or `auto`)
> — deploy/README.md §5.1 (F37). The BNO085 described here stays supported and auto-detected, as an option.
> GPS: any NMEA serial receiver (a u-blox NEO-M8N gave a fix on the box), or the autopilot's /
> the vehicle's ROS GPS.

`imu_node` reads the BNO085 (9-DoF with on-chip fusion) over I²C and publishes
`/navera/sensors/imu` (sensor_msgs/Imu) — by default on bus 1 (header pins 27 SDA / 28 SCL)
at address 0x4A, 50 Hz. Started at boot by `navera-imu.service`
(`ros2 launch imu_pkg imu.launch.py i2c_bus:=<bus> publish_rate:=50.0`, the bus where
navera-discover found the chip, `NAVERA_BOX_IMU_BUS`, default 1). When navera-discover found
no BNO085 on I²C buses 1 and 7 (`NAVERA_BOX_IMU=0`), the service stays idle ("no box IMU
found at boot … IMU service idle") instead of restarting in a loop.

Used when `NAVERA_SENSOR_SOURCE=box` (chosen first by `auto` when the chip is found, and
used when the key is absent): the live camera straightens frames with its attitude and
checks the rotation rate, day vision's dead-reckoning turns with the heading change it
measures, the night pipeline takes its heading, the celestial pipeline the star camera's
attitude, and the estimator checks its liveness. With `vehicle` or `ros` those nodes read
the vehicle's attitude instead, and this service is not needed. (A vehicle ROS IMU must
itself give yaw from true north: NAVERA converts only this box IMU —
deploy/README.md §6.)

## Orientation

- **Vehicle frame.** The published orientation, rates and accelerations are the
  vehicle's: the IMU's mounting on the vehicle is removed (`mount_roll_deg`,
  `mount_pitch_deg`, `mount_yaw_deg`; body x forward, y left, z up; ROS fixed-axis
  roll/pitch/yaw). Example: IMU turned 90° to the left → yaw 90.
- **True north.** The BNO085 rotation vector is referenced to magnetic north. With
  `auto_declination` (default true) the node subscribes to `/navera/position` and, once a
  position is known, applies the World Magnetic Model declination there (`pygeomag`,
  WMM 2025, valid 2025–2030; recomputed every ~20 km). Until then it applies
  `declination_deg` (east positive); if that is unset, the heading stays **magnetic** until
  the first position. Without `pygeomag` installed, the node logs
  "World Magnetic Model unavailable (…)" and uses `declination_deg` only.
- Frame: local ENU (REP-103). The BNO085 frame convention is to be confirmed on the
  hardware with a known heading (backlog IMU-3; FIELD_TEST_PROCEDURE.md step 6).

## Installation settings

The launch file applies these from the environment (`/etc/navera/navera.env`, or the
`/mission` page, which writes `/var/lib/navera/settings.env`), over the YAML defaults:

| Variable | Parameter(s) | Default |
|---|---|---|
| `NAVERA_IMU_MOUNT_RPY` | `mount_roll_deg`, `mount_pitch_deg`, `mount_yaw_deg` ("roll,pitch,yaw", each within ±180°) | 0,0,0 |
| `NAVERA_DECLINATION_DEG` | `declination_deg` (±90°, east positive) | none |

An invalid value stops the launch with an explicit error. There is no separate IMU
parameter file to edit on the box: the defaults are in `imu_pkg/imu_pkg/config/imu_params.yaml`
(installed with the package).

`NAVERA_DECLINATION_DEG` is **not** `NAVERA_MAGNETIC_DECLINATION_DEG`: the latter is used only
by the celestial pipeline, for an attitude source that reports magnetic north. Since this
node already publishes true north, leave `NAVERA_MAGNETIC_DECLINATION_DEG` unset with the box
IMU, or the declination is applied twice.

## Parameters (`config/imu_params.yaml`)

| Parameter | Default | |
|---|---|---|
| `i2c_bus` | 1 | 1 (pins 27/28) or 7 (pins 3/5) |
| `i2c_address` | 0x4A | 0x4B if the address pin is pulled high |
| `publish_rate` | 50.0 | Hz |
| `frame_id` | `imu_link` | |
| `gravity_compensated` | true | gravity-free `linear_acceleration`; false for REP-145 consumers |
| `orientation_stddev` / `angular_velocity_stddev` / `linear_acceleration_stddev` | 0.02 rad / 0.005 rad/s / 0.08 m/s² | datasheet estimates, **not measured** |
| `mount_roll_deg` / `mount_pitch_deg` / `mount_yaw_deg` | 0 | see above |
| `auto_declination` | true | World Magnetic Model at the vehicle's position |
| `declination_deg` | NaN | used until a position is known |

## Health

A sensor that stops reporting is detected (1 s of bit-identical samples) and
re-initialised; reconnection is attempted at most every 2 s. Initialisation errors are
logged as "BNO085 init failed on I2C bus 1 @ 0x4A: …".

The IMU gives attitude and heading changes only: there is no inertial navigation
(accelerations are not integrated into a position). Day vision's dead-reckoning carries its
last position along the velocity measured from recent fixes, turned by the heading change
this IMU measures (docs/ARCHITECTURE.md §5).

## Requirements

The Adafruit Blinka stack (`board`, `busio`, `adafruit_bno08x`: pip packages
`adafruit-blinka`, `adafruit-circuitpython-bno08x`), `pygeomag==1.1.0` for true north, and
the service user in the `i2c` group (see deploy/README.md §3). Subscriptions to this topic
are BEST_EFFORT (depth 50) in NAVERA's nodes; this node publishes RELIABLE, which they
receive.
