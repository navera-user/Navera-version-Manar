# Lab 31 report — fault-injection campaign on NAVERA's mission simulator

Author: example solution

## 1. Set-up

The campaign has five drone flights over Sousse (NAVERA's test map), recorded with NAVERA's mission
simulator: ArduPilot SITL (Copter, quad model) whose only position input is NAVERA's MAVLink
GPS_INPUT, the real gps_node, estimator_node and vehicle_output, and a simulated GNSS receiver,
IMU and vision. Four flights use the simulated vision "target" profile (σ 15 m per axis, stated);
one uses the "measured" profile (median ~440 m, uncertainty unknown, DEGRADED and forwarded to the
autopilot). The faults were injected about 30 s after the drone started flying to its destination:
GPS jammed 60 s then spoofed by a 2 km jump for 30 s (two flights), a slow 4 m/s drift for 80 s,
GPS off for 39 s, and GPS jammed with the camera failing 20 s later. Each flight is one CSV row per
second; latencies therefore have a resolution of about 1 s.

## 2. Results

| Flight | Fault | Switch (s) | Recovery (s) | Availability | p50 / p95 (m) | Verdicts |
|---|---|---|---|---|---|---|
| jam_spoof_target | jammed | 0.0 | 2.0 | 1.0 | 20.0 / 33.0 | R1 R3 R4 PASS |
| jam_spoof_target | spoof_jump | 1.0 | 4.1 | 1.0 | 18.7 / 34.9 | R3 R4 R5 PASS |
| jam_spoof_measured | jammed | 0.0 | 2.0 | 1.0 | 426.9 / 851.8 | R1 R3 R4 PASS |
| jam_spoof_measured | spoof_jump | 0.0 | 2.0 | 1.0 | 550.1 / 915.2 | R3 R4 R5 PASS |
| drift_target | spoof_drift | 18.3 | 3.1 | 1.0 | 19.8 / 58.1 | R3 R4 R5 R7 PASS |
| off_target | off | 2.1 | 1.0 | 1.0 | 17.9 / 30.6 | R2 R3 R4 PASS |
| jam_camfail_target | jammed | 0.0 | 0.0 | 0.362 | 23.1 / 38.0 | R1 R3 PASS (R4 not applicable) |
| jam_camfail_target | camera failed | — | — | 0.051 | — | R6 PASS (NO FIX after 4.1 s, autopilot LAND) |

In total 25 requirements PASS and 0 FAIL: 22 for the recorded campaign and 3 (R1, R3, R4) for my own
Sim Lite run my_run (a 40 s GPS jam, see Observations d). The MAVLink stream had 784 frames, 3 with a bad CRC and
2 lost frames (sequence gap); 385 GPS_INPUT frames were 3D fixes.

## 3. Observations

a) GPS off: the CSV gives a switch latency of 2.1 s, but the events log shows the injection at
12:53:26 and DAY VISION at 12:53:29, so the real latency is 3 s — the gps_timeout_s. The recorder
writes a row and then injects the fault, so the first row that shows "off" is up to 1 s late, and
every latency measured from that row is up to 1 s too short. During those 3 s NAVERA still gives the
last GPS fix, which falls behind the drone at 15 m/s: the error reached 32 m (15 m/s × 2 s), and
would reach 45 m after 3 s.

b) Spoof drift: the GPS was refused 18.3 s after the drift started; while NAVERA still used the
spoofed GPS its error reached 72.8 m, and the autopilot's own error reached 109.3 m, because its EKF
had followed the drift and needed time to converge back on vision. VALIDATION_STATUS.md reports a
refusal at ~160–200 m: that line comes from an earlier run; this version also refuses GPS after 5
independent vision fixes in a row beyond 3σ, which catches the drift earlier. One run is not enough
to give a number with confidence (lesson 32).

c) Target vision: the median error during the jam was 20.0 m, more than the Rayleigh prediction of
17.7 m for σ = 15 m. The simulated vision gives one fix per second, and the recorded position is the
last fix, so it lags behind the drone by up to 15 m. The Monte Carlo with a uniform lag of 0–1 s at
15 m/s predicts a median of 19.0 m, much closer to the measurement.

d) My own run in Sim Lite (my_scenario.json: GPS jammed 30 s after "en route", restored at 70 s,
target vision profile): NAVERA switched to day vision in the same second (switch 0.0 s in the 1 Hz
CSV) and was back on GPS 2.0 s after the GPS was good again. During the jam the median error was
17.8 m and the p95 34.3 m, close to the recorded target flight (20.0 / 33.0 m). It is one run of a
simpler world (no ArduPilot physics, no images), so it confirms the behaviour, not the accuracy.

## 4. Fidelity

This campaign proves behaviour, not accuracy: the arbiter's switching, timeouts, hold-off, spoof
gates and the autopilot's failsafe work as designed, in a closed loop with the real autopilot
firmware. It cannot prove the accuracy of NAVERA's vision, because the vision errors are drawn by the
simulator's profiles; it cannot show how a real receiver degrades under real jamming, nor the timing
on a loaded, hot Jetson. Each scenario was run once, so the numbers have no confidence interval.

## 5. Next campaign

1. Repeat each scenario 10 times to get the spread of the latencies and errors (lesson 32).
2. A spoof jump directly after a long jam ("jam, then spoof") with the measured vision profile, where
   the cross-check cannot help, to measure the documented weakness.
3. The same scenarios on the boat and the ground robot, whose failsafes differ (HOLD).
