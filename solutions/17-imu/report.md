# Attitude memo — NAVERA Lite's IMU part

## The gyroscope alone

On the pad the drone is still, so the mean gyro reading is its bias: (0.0636, −0.0321, 0.0946) °/s.
Integrated alone for 300 s, the z bias turns the yaw to the left by about 0.0946 × 300 = 28.4°, and the
heading error at 300 s is −28.42°: the heading is 90° − yaw, so a yaw that grows too fast makes the heading
too small. With the pad bias subtracted, the error at 300 s falls to −1.75°. What is left comes from the
error of the bias estimate (500 noisy samples) and from the random walk of the noise. The gyro is excellent
for seconds, useless alone for minutes.

## Choosing τ

The accelerometer does not drift, but it cannot tell a tilt from an acceleration: in the turn at 99.8 s the
drone banks 15.1° while the accelerometer says 0.9°, because the thrust stays along the body z axis. In the
sweep, a small τ copies those errors (tilt RMS 4.82° at τ = 0.3 s), a large τ keeps the gyro bias for
longer (b·τ, 2.67° at τ = 300 s). The best of the sweep is τ = 30 s with a tilt RMS of 1.85°. For NAVERA
Lite I would keep τ = 30 s and re-check it on a real flight log, since the best τ depends on how often the
vehicle turns and on the gyro's bias.

## Compass, north and trust

Near Monastir the field dips about 50°, so a tilt mixes its large vertical part into the horizontal axes:
without tilt compensation the true-heading RMS is 4.98°, with the true tilt 0.81°. The WMM declination
there is +3.35°; the chip's attitude, referenced to magnetic north, is off by −3.35° on average until
q_true_north turns the world frame by −D (on the left). Finally, a frozen chip is caught by counting exact
repeats: 50 in a row trips at 13.34 s, one second after the freeze; 5 would raise a false alarm at the
5.08 s read hiccup.
