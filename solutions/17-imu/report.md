# Lab 17 — report

## 1. Gyroscope drift

After 300 s the gyroscope-only heading is wrong by -9.42 degrees. The z bias of the log is
0.03 deg/s, so I predicted 0.03 × 300 = 9.0 degrees. The difference of about 0.4 degrees comes
from the white noise (a random walk) and from the small biases on x and y, which leak into the
heading when the drone is tilted. The error only grows: nothing in the gyroscope can correct it.
The sign is negative because a positive z bias makes the integrated yaw grow too fast, and the
heading is 90 degrees minus the yaw, so the heading becomes too small.

## 2. Tilt: accelerometer and complementary filter

The accelerometer alone has a roll error of up to 19.3 degrees. It happens in the turns: the
drone banks about 14 degrees, but in a coordinated turn the specific force stays along the body
z axis, so the accelerometer believes the drone is level. Its RMS roll error is 4.82 degrees.
The best time constant of my sweep is tau = 30 s (roll RMS 0.53 degrees, pitch RMS 1.32 degrees).
But 30 s is the edge of the sweep. When I extended it, tau = 100 s was even better (roll 0.34,
pitch 0.78 degrees) and tau = 300 s was worse again (roll 0.51, pitch 0.92 degrees), so the
minimum for this simulated sensor is near 100 s.
A very small tau trusts the accelerometer, so the filter copies its noise and its errors in
turns and accelerations. A very large tau trusts the gyroscope, so the bias error b × tau grows
and the filter needs a long time to recover from a wrong start.

## 3. Compass and true north

The declination at the place of the log (near Monastir, October 2026) is +3.35 degrees. My true
heading (tilt-compensated magnetic heading + declination) has an RMS error of 1.37 degrees.
Without tilt compensation the RMS error is 4.92 degrees. Near Monastir the field dips about 50 degrees
below the horizon, so a large vertical component leaks into the horizontal axes as soon as the
drone pitches or rolls, and the heading moves even when the drone does not turn.

## 4. Declination around the world

| Place | Declination (deg, east +) |
|---|---|
| London | +1.21 |
| Reykjavik | -11.05 |
| Cape Town | -26.81 |
| Sydney | +12.83 |
| Singapore | +0.24 |

If the declination of London is ignored, the side error after 10 km is
10000 × tan(1.21°) = 212 m. This is much larger than the accuracy that a navigation system wants.
In Cape Town the error would be 10000 × tan(26.81°) = 5053 m: there a compass without the
declination is useless for navigation.

## 5. Comparison with NAVERA

NAVERA's `quat_to_matrix` in navera_common/camera_model.py does the same job as my
`quat_to_matrix`, and `slerp` in navera_common/sensor_history.py does the same job as my `slerp`.
NAVERA (like ROS) stores a quaternion as (x, y, z, w), with the scalar LAST; my code uses
(w, x, y, z), with the scalar FIRST. I must convert with xyzw_to_wxyz before I compare them,
otherwise the numbers are silently wrong.
