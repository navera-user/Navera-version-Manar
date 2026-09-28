# imu_pkg — IMU driver (BNO085)

`imu_node` reads the BNO085 (on-chip fusion) over I²C bus 1 at 0x4A and publishes
`/navera/sensors/imu` (sensor_msgs/Imu) at 50 Hz.

- Orientation is the BNO085 rotation vector: referenced to **magnetic** north, in the sensor
  frame (no declination or mounting correction yet).
- `linear_acceleration` is gravity-free by default (`gravity_compensated`); set it false for
  REP-145 consumers.
- Covariances are datasheet estimates (`*_stddev` parameters), not measured values.
- A sensor that stops reporting is detected (1 s of bit-identical samples) and re-initialised;
  reconnection is attempted at most every 2 s.

Today the estimator uses the IMU for liveness only (no inertial navigation yet).
Needs the Adafruit Blinka stack (`board`, `busio`, `adafruit_bno08x`) and the `i2c` group.
