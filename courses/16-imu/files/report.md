# Lab 16 — report

Write in English, short sentences. Replace every `TODO` with your own text and numbers
(copy the numbers from the output of `python3 imu_filters.py` or from `results.json`).
Keep the five headings exactly as they are: the checker looks for them.

## 1. Gyroscope drift

TODO: the heading error of the gyroscope-only attitude after 300 s (in degrees), the value
you predicted from the bias with `error = bias × time`, and one sentence that explains the
difference.

## 2. Tilt: accelerometer and complementary filter

TODO: the largest roll error of the accelerometer alone and WHEN it happens (what is the
drone doing?), the best time constant tau of your sweep, and why a very small tau and a very
large tau are both bad in general.

## 3. Compass and true north

TODO: the declination at the place of the log, the RMS error of your true heading, the RMS
error without tilt compensation, and one sentence on why tilt compensation matters here.

## 4. Declination in Oman

TODO: a small table with the declination (October 2026) in Muscat, Sohar, Nizwa, Salalah and
Masirah, and the side error after 10 km flown from Muscat if the declination of Muscat is
ignored (metres).

## 5. Comparison with NAVERA

TODO: name the NAVERA functions that do the same job as your `quat_to_matrix` and your
`slerp`, and explain in one or two sentences the quaternion ORDER difference between your
code and NAVERA's code.
