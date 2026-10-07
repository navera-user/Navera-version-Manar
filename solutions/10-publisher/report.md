# Lab 10 — analysis

## Timing

`ros2 topic hz /fake_gps/fix` gave an average rate of 2.000 Hz, a minimum period of 0.499 s, a
maximum of 0.502 s and a standard deviation of about 0.8 ms. The timer is very regular but not
exact: each interval differs a little from 0.5 s because the operating system schedules the process
with small delays. The node therefore integrates v times the measured dt, so the position always
matches the time stamp it carries, even when a tick is late.

## Flat Earth

For heading 30° the flat-Earth end point is 0.031 m from the great circle after 1 km, 3.09 m after
10 km and 312 m after 100 km: ten times the distance gives about one hundred times the error, the
d² law. The due-east column (0.034, 3.43, 343 m) agrees with d² tan(φ)/(2R) to better than 0.1 %.
For a bench test of a few kilometres the flat model is accurate to centimetres or decimetres,
much better than the 3 m the receiver states; beyond about 10 km I would use the spherical formula.
