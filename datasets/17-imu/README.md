# Mission 17 data

- `imu_log.csv` — a simulated 5-minute flight of a multirotor near Monastir, 50 samples per second:
  gyroscope `gx, gy, gz` (rad/s), accelerometer `ax, ay, az` (m/s²) and magnetometer `mx, my, mz` (µT),
  all in the body frame (x forward, y left, z up); the IMU chip's own attitude `chip_qx … chip_qw`
  (x, y, z, w); and the true attitude `true_roll_deg, true_pitch_up_deg, true_heading_deg`.
- `imu_log_meta.json` — place, date, rate and units of the log.
- `imu_frozen.csv` — 20 s of IMU samples from a drone sitting on its pad (same columns, no attitude).

Simulated data, written for the course.
