# Results — NAVERA during a GPS jam (my measurement)

## What was measured

Two drone flights recorded with NAVERA's mission simulator over Sousse (ArduPilot SITL, NAVERA's real
nodes, simulated world), one row per second: 284 s and 190 s en route. In each, the GPS was jammed for
60 s (60 samples), then spoofed for 30 s. The only difference is the simulated vision used when GPS is
lost: the "target" profile (15 m, the goal, not a measured performance) and the "former day vision"
profile (the ~440 m median measured on real frames for the former DINOv2 method).

## Results

| Flight (vision profile) | NAVERA median during the jam | p90 | max | Baseline median | Availability during the jam |
|---|---|---|---|---|---|
| target (15 m, not measured) | 20 m | 32 m | 64 m | 455 m | 100 % |
| measured (former day vision) | 430 m | 743 m | 1082 m | 452 m | 100 % |

## Conclusion

With the target vision profile, NAVERA beats the "repeat the last GPS position" baseline by a factor
of about 20 during the 60 s jam (median 20 m against 455 m), with a usable position all the time. With
the error profile of the former day vision, it barely beats the baseline: 430 m against 452 m on the
median, and its worst error (1082 m) is larger than the baseline's (890 m) — on this jam, the method is
hardly better than doing nothing, as the replay benchmark already showed (442 m against 480 m). These
are two simulated flights of one minute of jamming each, with simulated vision errors: they show the
system's behaviour and why a method must be compared with a baseline, not NAVERA's real accuracy, which
needs real flights with NAVERA's camera.
