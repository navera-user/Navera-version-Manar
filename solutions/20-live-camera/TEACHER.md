# Mission 20 — teacher notes (Live camera: frames, delay and the attitude at the exposure)

Teacher only. Rebuilt 2026-10-13 on NAVERA Lite. The mission's part is `navera_lite/timing.py` (reference in
`solutions/_navera_lite/navera_lite/timing.py`, tags `# @part 20 todo 1–6`; given: `DEFAULTS`,
`load_camera_settings`, `exposure_time`, `tilt_deg`) and the given live node `navera_lite/ros/camera_node.py`
(`# @part 20`). It needs `rotations.py` (16: slerp, q_angle_deg, q_to_matrix, rpy_human) and `camera.py` (18:
K_from_hfov, camera_rotation, backproject_ground, nadir_homography), both shipped finished. **No camera is
needed and none is opened by any graded step**; `grab_real.py` (Step 12) is optional and only opens a booked,
free device. No NAVERA code: the old lab ran NAVERA's live camera node, its GStreamer class and its attitude
history; all of that is now course code or words.

The design (`reviews/fledgling-design.md` §2.6) put the mission-20 functions in `camera.py`; they live in their own
part, `timing.py`, so that missions 19 (fisheye, rebuilt in parallel) and 20 never edit the same file. Signatures
differ slightly from §2.6: `attitude_at(t_s, imu_t, imu_q, max_gap_s=0.2)` (as designed), plus
`rotation_rate_dps(...)` and `time_error_m(...)`; `usable(q, rate_dps, cfg)` takes the attitude and the rate (not a
meta dict). `exposure_time` is given (one line).

Recompute everything: `python3 solutions/20-live-camera/make_dataset.py` (≈ 45 s, renders the map),
`python3 solutions/20-live-camera/check_values.py` (≈ 25 s: `courses/20-live-camera/hidden/flight_table.json` and
every lab number), `source /opt/ros/humble/setup.bash && python3 tools/lite_build.py 20-live-camera`, then
`tools/try_lesson.py 20-live-camera --solution`.

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 describe a frame stream; normal vs risk | §1 (decode, newest frame), §2 (worked example, 🧰 ddof) | Steps 1–2 (TODO 1), Step 10 (queue) | 1, 4, 5, 14, 15 |
| 2 measure the delay with flashes; choose the setting | §3 (d = s + w + L, NAVERA's 0.138 s in words) | Steps 3–4 (TODO 2), Step 9 (scan) | 2, 6, 7, 13, 15 |
| 3 a time error in metres | §4 (worked 9.2 m, O-F2 story) | Step 0, Step 5 (TODO 3), Step 7 (straighten) | 3, 8, 12 |
| 4 attitude at the exposure; refuse frames | §5 (bracket, f, slerp, 🧰 bisect, gap rule), §6 (rules) | Steps 6–8 (TODO 4–6), Step 10 (live) | 9, 10, 11, 12, 13, 14 |

Badges: **Timekeeper** = checks 1–8 (session 1), **Shutter** = all 15.

## The data (`datasets/20-live-camera/`, made by `make_dataset.py`, seed 20261020)

- `bench/`: 30 **real** Insta360 ONE R frames (MJPG 1920 × 1080, NAVERA's bench 2026-10-06, bottom half
  pixelated) and the real `insta360_top.yaml` (latency_s 0.138, out_hfov 111) — copied as data (owner decision §7.2).
- Simulated, with hidden truths: **the class's test camera has L = 0.118 s** (same camera on the bench and the
  plane), the bench screen s = 0.020 s (the lab gives s; never give L). 28.8 frames/s, exposure 8 ms.
- `grab_log.csv`: 60 s, ≈1 % single drops, two double drops, a 0.35 s stall at 41.3 s, late USB grabs.
- `flashes.csv` / `bench_frames.csv`: 21 flashes, flash 8 hidden (not seen), flash 14 hit by a USB stall.
- `flight/`: a survey plane, 150 m (± 3 m), 25 m/s, coordinated turns: bank +30° (3–5 s), level (11–13 s), IMU
  dropout 14.6–15.2 s, bank −48° in 1 s (17–18 s), level slowly (20–23 s). IMU 50 Hz ± 1 ms with 0.03° noise;
  frames 28.8/s, grab = exposure + 0.118 s + |N(0, 1.5 ms)|. `map.jpg` = render_view pseudo style, 3 600 px at
  0.6 m/px around (35.8290, 10.6330), © OpenStreetMap contributors. frames.csv holds the true pose at the exposure
  but not the exposure time (so L cannot be read off).

## Answer key

| Item | Value | Where it comes from |
|---|---|---|
| PREDICT_ERROR (ungraded) | 8.4 m | 120 · tan(40 × 0.10°) = 8.39 |
| DECODE_MS / CORES_ALL_FRAMES | ≈ 15.6 ms / 0.45 on the Jetson (varies) | `bench`; check: CORES = 28.8 × DECODE_MS / 1000 ± 5 %; DECODE_MS in 0.5–500 |
| FPS_LOG / DROPPED_LOG | 28.27 / 32 | `stats`, 60 s: n 1697, median 34.76 ms, max gap 383.3 ms |
| JITTER_40S_MS / JITTER_60S_MS | 5.00 / 9.72 | first 40 s: n 1135, fps 28.37, 17 dropped, max 103.8 ms; swapped caught |
| DELAY_MEDIAN / MIN / MEAN (ms) | 156.3 / 141.1 / 166.1 | `flashes` (max 352.9 = flash 14, std 44.4, 20 of 21 seen) |
| UNSEEN_FLASH / OUTLIER_FLASH | 8 / 14 | |
| LATENCY_SETTING_S | 0.119 (accepted 0.110–0.128) | 156.3 − 17.4 − 20 = 118.9 ms; min − s = 121.1 ms; truth 0.118. Traps named: 0.156 (median), 0.141 (min), 0.136 (median − s), 0.139 (median − T/2), 0.129 (mean − T/2 − s). Must equal camera.yaml ± 0.5 ms |
| BUDGET_300_M | 5.45 | 300 · tan(30/28.8 °); 0.138 s instead of one period caught |
| DT_FOR_30M_S | 0.45 (± 0.006) | atan(0.2) = 11.31°, / 25 = 0.452 s; small-angle 0.458 → "0.46" caught |
| GRAB_MEDIAN_M / GRAB_MAX_M | 3.28 / 21.42 | `turn` (independent of the setting) |
| COPIED_MEDIAN_M | 0.54 | `turn --latency 0.138`, slerp line (nearest line 0.36 caught; p95 1.32, max 3.66) |
| MINE_MEDIAN_M | 0.05 at 0.119 | table lookup for the student's camera.yaml latency (0.118: 0.06, 0.121: 0.07, 0.156: 1.13) |
| STRAIGHT_GRAB_M | 7.4 | `straighten`: frame 111 (grab 3.85 s), held at the grab 7.4 m; yours 0.1 m at 0.119 (1.2 m at 0.138) |
| N_TURNING / N_TILTED / N_NO_ATTITUDE | 23 / 69 / 7 at 0.119 | table lookup (at 0.138: 23 / 69 / 6; rate unknown 5 or 6; ok 746) |
| BEST_LATENCY_S | 0.118 (± 0.0025) | `scan` (0.060–0.200 by 2 ms): 0.06 m at 0.118 and 0.120 |
| QUEUE_WAITED_S | ≈ 1.98 (accepted 1.5–2.5) | `-p queue:=4`, 2 frames/s: each frame waits 4 × 0.5 s; attitude error ≈ 25° |

Lesson numbers: T = 34.7 ms, T/2 = 17.4 ms, T/√12 = 10.0 ms; worked §2: fps 8.0, median 100 ms, jitter 43.3 ms,
1 dropped; ✏️ §2: 19.05 frames/s, 2 dropped; §3 ✏️: 141 − 17 − 15 = 109 ms, 125 − 15 = 110 ms; NAVERA's 0.138 −
0.017 − (0.010…0.030) ≈ 0.09–0.11 s; §4 worked: 25 × 0.14 = 3.5°, 150 · tan 3.5° = 9.17 m; 40 × 0.14 = 5.6 m;
40 m/s × 1–2.5 s = 40–100 m; ✏️ §4: 2 · 60 · sin 4.5° = 9.4 m; §5 worked: tₑ = 500.162, f = 0.1, yaw 31.05°, held at
the grab ≈ 34.5°; ✏️ §5: 17.1 s f = 0.125, 17.65 s f = 0.8125; §6: 60 °/s × 10 ms = 0.6° → 1.57 m at 150 m.
NAVERA facts (words only): VALIDATION_STATUS 2026-10-03 (83 m median, 0 % within σ, 1–2.5 s, 40 m/s, match
0–1 m; fixed), ENGINEERING_BACKLOG CN-2, ARCHITECTURE §5 (exposure stamp, 0.2 s, 30 °/s, 45°, frozen IMU 50
samples, newest frame, decode only the one sent), VALIDATION (144–185 °/s refused; 32/33 within 9 m, median 4 m),
FIELD_TEST_PROCEDURE (stopwatch method), the calibration file (0.138 s, 2026-10-06), NAVERA's flash tool (median
of 20, includes the screen: "at most").

## Rubric for the written answers (the check only catches empty or off-topic text)

| Item | 3 — good | 2 — partly | 1 — weak |
|---|---|---|---|
| EXPLAIN_DECODE | decode cost × 28.8/s wasted, vision needs ~1/s; grabbing keeps the newest frame and its time | "decoding is slow" only | restates the question |
| EXPLAIN_JITTER | the 0.38 s stall; std squares differences; median = normal, std/max gap = risk | names the stall only | "more data, more jitter" |
| EXPLAIN_SPREAD | random wait w for the next exposure, 0 to T, independent of the clock | "frames every 35 ms" | "noise" |
| EXPLAIN_LATENCY | removes s (20 ms) and T/2 (17 ms) from the median, says why not the min (one flash) | one of the two | uses the median as is |
| EXPLAIN_BUDGET | h · tan: height multiplies; ω · δt: no rotation, no angle error | one of the two | — |
| EXPLAIN_TURN | roll-in/out (3–5 s, 17–18 s), error = rate × L | when, not why | — |
| EXPLAIN_REFUSE | leftover timing error (setting ± ms, exposure blur, rolling shutter) × rate | "too fast" | — |
| EXPLAIN_SCAN | 0.118 vs bench 0.119 agree; a real plane has no true attitude (only a simulator) | one of the two | — |
| EXPLAIN_QUEUE | the frame waited ~2 s, the stamp "now − L" does not know it; no setting fixes it | "old frames" | — |

## Difficulties expected (from the build's wrong-solution runs; not yet tested with students)

- `frame_stats`: n vs n − 1, ddof = 1 (pandas habit), seconds vs ms, `round(x/m)` without − 1, counting with the
  mean instead of the median (the stall). All named by the runner and the check.
- `delay_from_flashes`: "brighter than dark" instead of the midpoint (half-lit frames), `>=` at the midpoint,
  forgetting None (lists shorter than the flashes).
- `attitude_at`: the fraction upside down, (w, x, y, z), averaging the four numbers instead of slerp (wrong when a
  neighbour is stored as −q: the check's history has one), hard-coding 0.2, returning None at the ends.
- `usable`: rule order (tilt before rate), hard-coded 30/45, the reason's format (`:.1f`), the gimbal.
- Step 4 is the engineering decision: many students first write the median (0.156). The check names each trap.
- Step 10 runs ROS in the student's sandbox; discovery takes 1–2 s for `ros2 topic echo`. The queue line appears
  only once the queue is full (after ≈ 2 s).
- The "nearest sample beats slerp with 0.138 s" result surprises; it is the point of Step 9 (a wrong instant).

## Class plan (2 × 2 h, plus reading)

Session 1 (Timekeeper): 10 min hook (the 83 m story, ask "where did 82 m come from?"); Steps 0–2 (40 min); Step 3
with the prediction before §3 (35 min); Step 4 as a pair discussion: each pair defends a setting (15 min); Step 5
(20 min). Session 2 (Shutter): 10 min recap of slerp (mission 16); Steps 6–7 (50 min); Step 8 (30 min); Steps 9–10
(25 min, ROS live on the projector); memo as homework. Fast students: Going further (MAD jitter, number of
flashes). Struggling students: give Step 4's formula after their own try; pair them for TODO 4 (hints 1–5 in order).
The real camera (Step 12) is optional and shared: book it for a demo, never needed for the badge.
