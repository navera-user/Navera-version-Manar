# Results — NAVERA during a 60 s GPS jam (simulated flights)

## What was measured

Three drone flights, one row per second. Two were recorded with NAVERA's mission simulator over
Sousse, Tunisia (ArduPilot SITL, NAVERA's real nodes, simulated world and simulated vision errors):
"target" (vision error profile of 15 m, the goal, not a measured performance) and "measured" (the
error profile of the former DINOv2 day vision, ~440 m median). The third, "selective", is synthetic:
the measured flight with every vision position more than 300 m off removed. In each flight the GPS
was jammed for 60 s, so each jam statistic rests on 60 samples (14 positions in the selective
flight). The truth is the simulator's own true position.

## Method

Horizontal error = great-circle distance between NAVERA's position and the truth, for each en-route
second with a position. CEP50, p90 and CEP95 use the nearest-rank percentile of evaluate_session.py;
RMSE is the root of the mean squared error. Availability = share of jammed seconds with a usable
position (FIX or DEGRADED); longest gap = longest run of seconds without one. Baseline = repeat the
last GPS position before the jam. 95 % confidence intervals: percentile bootstrap, B = 2000, seed 29,
moving blocks of 10 s (the errors are correlated from one second to the next); the difference with
the baseline is a paired bootstrap (the same seconds for both).

## Results

| Flight | n (jam, s) | NAVERA CEP50 [95 % CI] | CEP95 | RMSE | max | Baseline CEP50 | CEP50 NAVERA − baseline [95 % CI] | Availability (jam) | Longest gap |
|---|---|---|---|---|---|---|---|---|---|
| target (15 m profile, not measured) | 60 | 20 m [19, 23] | 32 m | 24 m | 64 m | 455 m | [-648, -201] | 100 % | 0 s |
| measured (former day vision) | 60 | 430 m [390, 554] | 847 m | 514 m | 1082 m | 452 m | [-297, 221] | 100 % | 0 s |
| selective (synthetic) | 60 (14 with a position) | 154 m [94, 239] (iid; a block CI is not meaningful here) | 287 m | 187 m | 296 m | 452 m | [-308, -5] | 23 % | 13 s |

## Is the difference real?

Target flight: the whole CI of the difference is below 0 (between -648 and -201 m), so NAVERA beats
the baseline on this jam. Measured flight: the CI [-297, 221] contains 0, so we cannot claim that the
former day vision beats "repeat the last position" — the 22 m difference of the medians is sampling
noise. Selective flight: the CI excludes 0 only because the comparison uses the 14 easy seconds that
were kept. I used a paired bootstrap because NAVERA and the baseline were measured at the same seconds,
and blocks of 10 s because the coverage experiment showed that an iid bootstrap on correlated errors
covers the truth only ~59 % of the time (block bootstrap ~73 %): even these intervals are probably too
narrow.

## Validity: simulation vs field

These are simulated flights over Sousse. The vision errors are drawn by the simulator from a profile,
the camera images and the GPS noise are simulated, and the drone flew one route once. They test
behaviour (does NAVERA switch, does the autopilot keep flying) and show how to compare a method with
a baseline; they do not measure NAVERA's real accuracy. A field test would need real flights with
NAVERA's camera, GPS and IMU together, an independent truth (RTK GPS), several routes, terrains and
times of day, and enough jammed minutes for narrow intervals.

## Conclusion

With the target vision profile, NAVERA's CEP50 during the 60 s jam is 20 m [19, 23] against 455 m for
the "repeat the last GPS position" baseline, with a position every second: the difference is clearly
larger than the sampling noise. With the error profile of the former day vision, the CEP50 is 430 m
against 452 m and the confidence interval of the difference contains zero: on this data the method is
not shown to beat doing nothing, and its worst error (1082 m) is larger than the baseline's (890 m).
Withholding the bad positions (selective flight) makes the CEP50 look better, 154 m, but availability
falls to 23 % with a 13 s gap. These are two simulated flights and one synthetic variant, 60 jammed
seconds each, over Sousse: they show the method and the baseline comparison, not NAVERA's accuracy in
the field, which needs real flights with NAVERA's camera.
