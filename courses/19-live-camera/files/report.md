# Lab 19 — report: timing a live camera

Name: TODO

Write short, precise sentences. Quote your numbers from `results.json` (and the units).
Replace every TODO. At least 250 words in total.

## Frame timing

TODO: the 60 s grab log — fps (2 decimals), median period, jitter, largest gap, number of
dropped frames. Why is the jitter (standard deviation) so much larger than the typical
scatter you see in out/jitter.png? Then your own GStreamer measurement: fps without work and
with 50 ms of work per frame, and what happened to the frames you could not process.

## Camera delay

TODO: the latency bench — median, smallest and largest delay, and their spread compared with
one frame period. Explain where the spread comes from, and why the median over-estimates the
camera's delay (what is included besides the camera?). Compare with the 0.138 s NAVERA uses.

## Attitude at the exposure

TODO: the three methods (latest_at_grab, nearest_at_exposure, slerp_at_exposure): median and
maximum angle error, and the median ground error at 150 m. How many frames were unusable and
why? Where in the flight (out/attitude_error.png) is each method worst, and why?
Did your attitude_at() agree with NAVERA's (compare_with_navera.py)?

## Recommendation

TODO: three or more concrete recommendations for a NAVERA installation on a survey drone
(for example: frame rate offered to day vision, IMU rate, how to re-measure the delay,
what to do when the IMU goes silent).
