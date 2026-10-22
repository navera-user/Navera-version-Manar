# NAVERA — Validation status and known limitations

**Release 0.2 — field validation pending.** Last updated 2026-10-22 (the dated sections below
give each measurement's date; the summary and the known limitations reflect all of them).

This document states what has been measured, how, and what still has to be validated in
the field. Every number below comes from a run on the Jetson Orin Nano (bench, replay and
synthetic data). None of them comes from a real flight. Anything not listed here has not
been measured. Open engineering items are tracked in
[ENGINEERING_BACKLOG.md](ENGINEERING_BACKLOG.md).

## Summary

| Capability | Status | Evidence |
|---|---|---|
| GPS pass-through, fix arbitration, operator display | Working, bench-tested | Scripted tests, virtual serial port, simulated sensors |
| Automatic restart after a crash | Mechanism verified; not yet reboot-tested on a deployed unit | Node exit → launch exit, verified |
| Day vision — local feature matching (default since 2026-10-01) | **Accurate on aerial test frames; measured with NAVERA's camera on a screen bench only (not flown)** | 32/33 frames within 9 m (median 4 m), no wrong position accepted, 0.16 s/frame |
| Day vision — DISK + LightGlue matcher, navigation between matches (2026-10-06/07) | **Screen bench with the Insta360 (other-date imagery) and simulator; not flown** | below: "Day vision with NAVERA's camera — screen bench" |
| Day vision — stated sigma on real drone flights (UAV-VisLoc, 8 flights, 2026-10-20) | **Model alone unsafe (65 % within 3σ); self-calibration + 30 m floor safe with the pose–attitude guard, in the product since 2026-10-20 (VL-1, `pose_tilt_guard_deg`): median 16 m, p90 34 m, 1 of 2599 fixes > 100 m, 0.999 (floor) / 0.993 (self-cal) within 3σ. Without the guard (code before VL-1): 70 fixes 100–325 m off** | below: "Day: real drone flights" |
| Day vision — a real flight replayed through the whole chain: IMU straightening, tracking, estimator (MARS-LVIG, 2026-10-21) | **Real drone camera and IMU replayed (not NAVERA's camera, 80–130 m, one valley flight + 55 s of another):** GPS cut after 120 s, 310 s without: fixes 6–7 m median, never over 17 m, 100 % within 3σ, 0 over 50 m in 1 493; 36 % of frames matched at z17 (54 % at z18); dead-reckoning alone 4 / 12 m (median / max) over 70 s after two fixes of this branch | below: "Day: a real flight replayed" |
| Day vision — DINOv2 tile retrieval (former method, fallback) | **Not accurate enough to replace GPS** | Median 442 m on labelled replay frames |
| Night vision (STHN homography) | Frames scaled and turned north-up from altitude, camera field of view and heading; motion gate; **not flown. Real aerial thermal (2026-10-21, orthomosaic frames, below): night LWIR 28–38 % of frames give a position at 700–1000 m, 10–12 m median, 0 wrong accept with a 640 px camera; a 160 px camera made wrong accepts through the retries** | 8–13 m median on synthetic frames (250–600 m, any heading); simulated night mission, GPS jammed, vehicle barometer (2026-10-07): 10 m median, 21 m max, stated accuracy (simulator-calibrated) 100 % within 3 sigma; **needs an independent height (barometer) after GPS loss** |
| Celestial 360 all-sky solver (`cn_pkg.allsky`) on **real night skies** (public ESO all-sky cameras, 2026-10-21) | **Real sky, but single up-looking fisheye cameras, not NAVERA's Insta360; mount 'up' known (fixed camera / truth fit)** | 559 real frames: 0 wrong positions accepted (61 wrong identifications all refused); clear moonless nights 100 % solved, 2.9 km median; below: "Celestial 360 on real night skies" |
| Celestial (astrometry.net) | Run end to end on simulated star fields; **coarse: bounded by the IMU attitude (~111 km per degree); simulator only — not run on a real sky** | 5.5–6.5 km with a perfect attitude; 24–119 km with a BNO085-class IMU; simulated night mission without barometer (2026-10-07): 29 km median, 40 km max, 100 % within its stated sigma |
| Day vision dead-reckoning along the measured track (no match: sea, uniform ground, frame unusable) | Implemented 2026-10-02; **simulator only** | Land route: no failsafe, error median 10 m, max 33 m; across the bay: carried 90 s over the sea stating ±300 m, true error at most 146 m |
| Vision position carried to the present (output, operator view) | Implemented; unit tests and simulator only | 1.5 s old photo at 40 m/s: moved 60 m, stated ±31.5 m |
| Inertial navigation (integrating the IMU) | **Not implemented** — the IMU gives attitude and heading changes | — |
| Vehicle outputs | ArduPilot SITL only; **PX4 not tested** (and PX4 ignores `GPS_INPUT`) | below; PX4_INTEGRATION.md |

## Position output contract

Every position NAVERA publishes carries its source, whether it was measured or
dead-reckoned, and whether its uncertainty is known:

- **FIX**: a fresh measured position with a stated uncertainty of at most 25 m (a defined
  covariance type and a sigma of at least 1 cm). Today only GPS reaches it.
- **DEGRADED**: a position is available, but its uncertainty is unknown or above 25 m, or
  it is dead-reckoned. All vision and celestial positions are reported as DEGRADED, and so
  is a GPS "in doubt" (vision contradicts it).
- **NO_FIX**: no source is usable. No old position is re-sent as current.
- **OFFLINE**: on the operator view, the arbiter itself is not answering.

## Measurements

### Day vision (`day_pkg`, DINOv2 + tile retrieval against z17 satellite tiles)

Data: 33 labelled replay frames around Sousse (`vision_pkg/.../frames_gps`), 1120 tiles.

| Method | Median error | Within 300 m |
|---|---|---|
| DINOv2, search limited to 600 m around the previous true position | 442 m | 41 % |
| Random tile in the same circle (baseline) | 536 m | 17 % |
| Repeating the previous position (baseline) | 480 m | 31 % |
| DINOv2, whole map, no prior | 1 696 m | 12 % |
| Best tile available (resolution limit) | 107 m | 94 % |

In a simulated GPS loss (GPS for 3 frames, then 30 frames of vision), the error grew to
**4–5 km**. The similarity score stays high on wrong matches, so it cannot flag them.

Whole-map search, score discrimination (33 labelled frames, 4 within 300 m): scores of the
good matches (0.942–0.974) lie inside the range of the bad ones (0.823–0.972). The best
possible score threshold classifies 94 % correctly, against 88 % for "always reject". The
top-1/top-2 and top-1/top-5 gaps do no better than "always reject". **Whole-map search is
therefore disabled by default** (`allow_global_search: false`). Day vision reports no
position until it has a prior (the last GPS fix, or its own tracked matches).

**Conclusion:** the retrieval method must not be relied on as a GPS replacement. It is replaced
by local feature matching (below) and kept as the fallback when the frame scale is unknown.

#### Local feature matching (`day_pkg/local_matcher.py`, 2026-10-01)

The frame is scaled to the map's resolution (altitude + `camera_hfov_deg`), its SIFT features
are matched to those of the map tiles in the search circle, and a rotation + scale +
translation is fitted (RANSAC). A match is accepted only if it has ≥ 6 inliers **and** the
fitted scale is the one the altitude predicts (±15 %) — a wrong place almost never matches at
the right scale. Same 33 frames and rule as above (search within 600 m of the previous true
position):

| Variant | Accepted | Error of accepted | Wrong (> 50 m) accepted | Time per frame (Jetson) |
|---|---|---|---|---|
| prototype, no scale check, ≥ 12 inliers | 10/33 | median 4 m, worst 1097 m | 1 | 4.7 s |
| + scale check (frame scale known) | 21/33 | median 4 m, worst 5 m | 0 | 3.5 s |
| + frame pre-scaled, map features per tile, margin 300 m | 32/33 | median 4 m, worst 9 m | 0 | 0.42 s (CPU) |
| product module (`LocalMatcher`, ≥ 6 inliers, GPU matching) | 30/33 | median 4 m, worst 5 m | 0 | 0.11 s (GPU) |

Re-measured 2026-10-20 (`navera_tools/bench/learned_matchers.py`, same 33 frames, 600 m search,
scale ±15 %, other GPU jobs running so times are high), with the inlier minimum the product
ships (`local_min_inliers` 8) and the 6 the table above used:

| Matcher | prior = previous frame, ≥ 6 / ≥ 8 inliers | prior carried along the velocity, ≥ 6 / ≥ 8 | wrong | error median |
|---|---|---|---|---|
| SIFT (`LocalMatcher`) | 27/33 / 23/33 | 29/33 / 24/33 | 0 | 3.3–3.5 m |
| DISK + LightGlue (`LearnedMatcher`, the default "auto") | 29/33 / 29/33 | 28/33 / 28/33 | 0 | 3.3–3.6 m |

The minimum of 8 costs SIFT 4–5 of 33 frames and nothing to DISK + LightGlue (~190 inliers);
neither minimum let a wrong position through.

The frames are aerial images from another source and date than the map, rotated ~50° and at
~3× the map's resolution: a fair test of cross-source matching, **not** frames from NAVERA's
camera (lens, blur, haze, oblique view). The benchmark camera's scale (0.62 of a 768 px frame)
is its calibration, as `camera_hfov_deg` is for a real camera. Positions are stated at 30 m
(`local_sigma_m`) until measured with the real camera.

**Dead-reckoning along the measured track (2026-10-02, simulator only).** When a frame
gives no match (sea, uniform ground, frame too tilted), day vision carries its last measured
position along the ground velocity fitted to the measured fixes of the last 20 s (GPS while
trusted, vision matches at their photo's instant), turned by the heading change the IMU
measures, published PROPAGATED with a stated accuracy that grows (velocity error × t + 5°
heading error × distance), for at most 120 s / 500 m. Mission simulator, GPS jammed, gimbal
camera: land route — no failsafe (before: EKF failsafe), error median 10 m, max 33 m;
across the bay — carried 90 s over the sea stating ±300 m with a true error of at most
146 m, no failsafe within the 240 s run (before: failsafe at t+97 s). Not measured with a
real camera or a real IMU. Never used as an independent check of GPS.

**Rotation-rate gate (fixed camera).** Straightening itself is right at plane conditions
(benchmark, 300 m, roll 0 / 10 / 18°, BNO085-class noise: 33/33 within 2.9 m). The
simulator's fixed-camera plane runs were taken during a ±26° roll oscillation of the
simulated plane (also with GPS working: a simulator issue, tracked): those frames are now
refused (144–185°/s against the 30°/s limit). Fixed-camera plane results from the simulator
are therefore not representative.

In flight (simulator, desert near Gabès — where retrieval failed, see Long route): 147 matches
in a row, 0 rejected, ~1 m (the simulated camera is cut from the map's own imagery:
optimistic); day vision 0.16 s/frame; the autopilot flew 230 s of the 240 s test on vision
alone (45–91 s with retrieval), its own position error 27 m median. Remaining gaps over 3 s
came from the simulated camera's rendering under a CPU saturated by another simulation, not
from day vision.

> The replay frames in `camera_pkg/data/day` do not show the places their CSV labels
> say. Earlier accuracy figures computed on them are not valid.

### Day vision with NAVERA's camera — screen bench (2026-10-06/07)

The Insta360 One R (top lens, calibrated fisheye, straightened to 111°, 0.14 s delay
measured) films the Jetson's screen, on which Esri Wayback imagery **2–3 years older than
NAVERA's map** scrolls like a flight: racetrack with turns, height ±20 %, simulated IMU
heading ±5°, 25 m/s, ~520 m equivalent height; GPS for 90 s, then lost
(`navera_tools/bench/screen_mission.py`; truth = the camera axis calibrated against the
terrain imagery itself). Matcher DISK + LightGlue (fp16, 1536/768 keypoints, SIFT fallback)
with `day_pkg/vision_nav.py` between matches. Campaign 4 (before the last carry fix),
GPS lost, NAVERA output error median / p95 / max:

| Terrain | Fixes | Available | Error (m) | Within 3 stated sigma |
|---|---|---|---|---|
| City (2 runs) | 95.6 % | 100 % | 5.2 / 17 / 36 | 100 % |
| Olive groves | 96.4 % | 100 % | 4.2 / 9 / 90 | 100 % |
| Dry hills | 97.3 % | 100 % | 3.6 / 20 / 307 | 97 % |
| Farm fields | 86.6 % | 99.3 % | 4.5 / 110 / 554 | 96 % |
| Coast (half sea) | 32.8 % | 51.6 % ("no position" otherwise) | 7.3 / 63 / 84 | 100 % |
| City, 18 min (killed for memory) | 94 % | 100 % | 5.5 / 17 / 49 — no drift | 100 % |

The 307 m and 554 m maxima were the carried position folding turns; fixed after
(frame-by-frame carry): replayed on the same matches, non-coast max 554 → 42 m. Imagery
8 years older than the map (2017): no match with any matcher. Limits: the screen is flat
(no relief, no perspective of buildings), no vibration or real blur; the camera was
re-aimed between campaigns. **Not a flight measurement.**

**Offline regression benchmark (2026-10-22, NAV-PERF-02, `navera_tools/bench/day_perf.py`,
`navera_tools/tests/test_perf_day_vision.py`, nightly with `NAVERA_PERF=1`, ~3.7 min on the GPU).**
Campaign 4 recorded no frames, so it cannot be replayed. Two offline proxies, product matcher
(`matcher:=auto`, DISK + LightGlue, the node's gates): (1) 80 recorded real Insta360 frames of the
2026-10-20 screen flights (clear 20 / 60 m/s, heavy rain, flare; the screen showed NAVERA's own map,
prior 0–150 m off): 80/80 located, median 2.9–3.9 m, p95 8–13 m, max 13 m, 0 wrong; (2) campaign 4's
mission (racetrack, height ±20 %, IMU heading ±5°, one 135 s lap after the GPS loss, VisionNavigator +
FrameOdometry) with the camera replaced by the other-date terrain cut at its geometry: land median
0.9–2.0 m, p95 1.6–2.7 m (farms once 10.5 m), coast median 3.2 m, availability 100 % everywhere, 0
wrong, 100 % within 3σ. Far better than campaign 4 on the same terrains: the losses there (coast
availability, farm p95) come from the screen + camera chain, which only part (1) carries. The test
asserts campaign 4's numbers (land median ≤ 5.5 m, p95 ≤ 20 m, coast ≥ 50 % / ≤ 7.3 m, 0 wrong) and
this baseline with ~2× margin.

### Day: real drone flights (UAV-VisLoc, 8 flights, 2026-10-20)

NAVERA has not flown. The closest evidence is the public UAV-VisLoc dataset
(github.com/IntelliSensing/UAV-VisLoc): real fixed-wing drone photos with their GPS position,
height and attitude, and a satellite map per flight. Each photo is located by NAVERA's day
matcher (DISK + LightGlue, `LearnedMatcher`) from a prior 250 m off in a random direction
(search 350 m, heading from the dataset, no tracking between photos), then the stated sigma is
scored as a flight (`replay_sigma_cal.py`): the first 30 % of the accepted fixes with GPS (every 2nd one calibrates,
`SigmaCalibration`, min 15 samples), the rest after a GPS loss.

Tools: `navera_tools/bench/uavvisloc_tiles.py` (map → z17 tiles), `uavvisloc_dem.py` (ground
height), `uavvisloc_eval.py` (matcher, `--position pose` as `day_subscriber`), `replay_sigma_cal.py
--table` (the tables below; `--position guard:4`, `--exclude`). Data on the ADATA disk
(`NAVERA_TESTDATA/uavvisloc/full/`, flights downloaded from the dataset's Hugging Face mirror
`mvidem/UAV-VisLoc`, every file checked against the size and CRC of the official zip); results
in `~/.navera_sim/uavvisloc/more/` (`f*_pose.json`, `table_pose_2026-10-20.txt`).

| Flight | Region, ground (DEM) | Date | Height above ground | Photos | Accepted |
|---|---|---|---|---|---|
| 03 | Taizhou, flat, 0–14 m | 2018-10 | 462 m | 768 | 693 (90 %) |
| 04 | Taizhou, flat, 0–11 m | 2018-10 | 539 m | 738 | 661 (90 %) |
| 01 | Yangtze (Jiujiang), flat, 9–41 m | 2018-09 | 387 m | 817 | 161 (20 %) |
| 05 | Yunnan, hills, 1911–2125 m | 2016-06 | 375 m (190–406) | 473 | 44 (9 %) |
| 06 | Zhuxi, mountain valley, 495–602 m | 2022-10 | 309 m | 262 (*) | 206 (79 %) |
| 08 | Huzhou, flat, 0–10 m | 2019-06 | 549 m | 1033 | 285 (28 %) |
| 10 | Huailai, 473–490 m | 2018-09 | 293 m | 144 | 8 (6 %) |
| 11 | Shandan (Gansu), 1713–2013 m | 2023-10 | 778 m (246–860) | 590 | 542 (92 %) |

(*) 82 photos of flight 06 (06_0099–06_0180) are left out: their GPS labels are ~360 m
off **along the track** (cross-track < 40 m, sign flips with the flight direction, matches with up
to 222 inliers) — a time-tagging error of the dataset, not of the matcher.

Three facts about the data the first run (flight 03 only) did not need: the dataset's
"height" is **above sea level** (Yunnan: 2313 m over ground at 1900–2125 m), so the eval
subtracts the ground height of a public DEM (AWS Terrain Tiles, ~30 m); its positions are the
**drone's** (under the camera), not the photo centre's — the centre errors follow
height × tan(attitude) (correlation 0.74–0.98 on every flight); and the maps are newer than the
photos (flight 05: fields of 2016 are greenhouses on the map — 9 % accepted). The camera field
of view is fitted per flight (52–58°).

**Product mode, as the code is today** (`hfov_deg` given: the position is the point under the
camera from the fitted pose, `local_matcher.refine_with_pose`). Error of the accepted fixes,
fixes > 100 m, share within 3 stated sigma: model alone (`day_fix_sigma_m`), never calibrated
(`sigma_floor_no_cal_m` 30 m, whole flight), self-calibrated (after the GPS loss); last column:
fixes > 100 m off **and** beyond 3 published sigma — wrong positions the stated accuracy hides:

| Flight | Median / p90 / max (m) | > 100 m | Model | Floor 30 m | Self-cal (f, b) | Self-cal median σ | > 100 m beyond 3σ: floor / self-cal |
|---|---|---|---|---|---|---|---|
| 03 | 12.1 / 25 / 127 | 5 | 0.815 | 0.990 | 0.992 (1.9, 17 m) | 20 m | 5 / 3 |
| 04 | 14.1 / 34 / 155 | 6 | 0.641 | 0.989 | 0.985 (2.4, 14 m) | 19 m | 6 / 2 |
| 01 | 35.4 / 126 / 202 | 21 | 0.487 | **0.839** | 1.000 (4.4, 58 m) | 90 m | 21 / 0 |
| 05 | 40.1 / 137 / 281 | 9 | 0.419 | **0.795** | **0.806** (not calibrated: 7 samples) | 30 m | 9 / 6 |
| 06 | 26.5 / 58 / 121 | 1 | 0.538 | 0.990 | 1.000 (2.1, 27 m) | 32 m | 1 / 0 |
| 08 | 20.4 / 78 / 325 | 22 | 0.620 | **0.916** | 0.995 (3.6, 32 m) | 44 m | 22 / 1 |
| 10 | 35.4 / 78 / 115 | 1 | 0.500 | **0.875** | **0.833** (not calibrated: 1 sample) | 30 m | 1 / 1 |
| 11 | 22.0 / 39 / 162 | 5 | 0.563 | 0.991 | 1.000 (3.9, 23 m) | 33 m | 5 / 0 |
| **All** | 17.0 / 46 / 325 (2600 fixes) | **70** | 0.647 | 0.969 | 0.990 | 29 m | **70 / 13** |

The wrong fixes are the pose's: their pose tilt is 9–26° while the drone was within 1–3° of
level (flight 03: pose 14°, attitude 1°, 110–127 m off). On a flat scene seen through a ~52° lens,
tilt and offset trade against each other and the pose solver picks a wrong pair with a small
reprojection error; the matcher's sigma (5–25 m) does not know. On the 2 flights with few matches
(05, 10) self-calibration never starts and the 30 m floor is published over 100–280 m errors.

**Proposed, replayed on the runs above (applied since, see below): pose–attitude guard.** Use
the pose position only when its tilt agrees with the tilt the attitude says the frame has —
for frames straightened with the IMU, about 0° — within 4°; otherwise keep the frame centre
(not refuse: refusing the match instead loses 13 % of the fixes overall — 47 % on flight 01,
44 % on 06 — for the same safety). Scored on
the same runs (`--position guard:4`; the eval's photos are not straightened, so a fallback to the
centre still carries height × tan(attitude): pessimistic):

| Flight | Median / p90 / max (m) | > 100 m | Model | Floor 30 m | Self-cal (f, b) | Self-cal median σ | > 100 m beyond 3σ: floor / self-cal |
|---|---|---|---|---|---|---|---|
| 03 | 12.0 / 23 / 50 | 0 | 0.833 | 1.000 | 1.000 (1.8, 12 m) | 15 m | 0 / 0 |
| 04 | 14.1 / 35 / 122 | 2 | 0.644 | 0.997 | 0.996 (2.9, 16 m) | 23 m | 2 / 1 |
| 01 | 19.7 / 39 / 89 | 0 | 0.832 | 1.000 | 1.000 (2.1, 17 m) | 37 m | 0 / 0 |
| 05 | 27.6 / 53 / 80 | 0 | 0.839 | 1.000 | 1.000 (not calibrated) | 30 m | 0 / 0 |
| 06 | 15.9 / 32 / 64 | 0 | 0.717 | 1.000 | 0.993 (1.6, 14 m) | 19 m | 0 / 0 |
| 08 | 18.9 / 37 / 69 | 0 | 0.745 | 1.000 | 1.000 (2.7, 17 m) | 29 m | 0 / 0 |
| 10 | 25.5 / 32 / 35 | 0 | 1.000 | 1.000 | 1.000 (not calibrated) | 30 m | 0 / 0 |
| 11 | 21.8 / 37 / 78 | 0 | 0.568 | 1.000 | 1.000 (3.8, 22 m) | 32 m | 0 / 0 |
| **All** | 15.8 / 34 / 122 | 2 | 0.712 | **0.999** | **0.998** | 23 m | 2 / 1 |

The 2 fixes over 100 m left are on flight 04; 04_0420 (attitude 14.6°, pose 1.2°: the pose
is wrong again) falls back to the eval's unstraightened centre, 122 m off where height ×
tan(attitude) is 141 m — with the IMU straightening the frame first it would not be there.
Guard threshold 3° / 5°: floor 0.999 / 0.999, self-cal 0.997 / 0.996, 3 / 2 fixes > 100 m. GPS phase 10 % / 50 % of the fixes (guard 4°): self-cal 0.995 / 0.998,
the 30 m floor 0.999 in all cases; as-is with 10 % GPS: 0.966, 51 wrong fixes inside 3σ.

**Applied (VL-1, 2026-10-20): `pose_tilt_guard_deg` (default 4; `local_matcher.refine_with_pose`).**
`day_subscriber` gives the matcher the frame's tilt by its attitude (0 for a frame straightened
with the IMU or without attitude, else `tilt_deg`); a consistent pose further than 4° from it
is not used: the frame centre is published (status `position_from`, `pose_guard`). Re-measured
through the real code path (`uavvisloc_eval.py --pose-tilt-guard 4`, the photo's recorded
attitude tilt as the expected tilt since the photos are not straightened; new runs, same
priors and field of view; `f*_guard4.json`, `table_guard4_2026-10-20.txt`; 06_0099–0180 excluded):

| Flight | Accepted | Median / p90 / max (m) | > 100 m | Pose kept / guarded | Floor 30 m | Self-cal (f, b) | > 100 m beyond 3σ: floor / self-cal |
|---|---|---|---|---|---|---|---|
| 03 | 694 | 12.2 / 23 / 55 | 0 | 663 / 31 | 1.000 | 1.000 (1.6, 11 m) | 0 / 0 |
| 04 | 660 | 14.9 / 36 / 119 | 1 | 614 / 46 | 0.998 | 0.976 (2.2, 13 m) | 1 / 1 |
| 01 | 164 | 20.1 / 43 / 76 | 0 | 85 / 79 | 1.000 | 1.000 (2.5, 21 m) | 0 / 0 |
| 05 | 48 | 23.8 / 46 / 98 | 0 | 25 / 23 | 0.979 | 0.971 (not calibrated) | 0 / 0 |
| 06 | 207 | 17.1 / 32 / 65 | 0 | (*) | 1.000 | 0.993 (1.1, 15 m) | 0 / 0 |
| 08 | 284 | 18.1 / 36 / 62 | 0 | 241 / 43 | 1.000 | 1.000 (3.4, 20 m) | 0 / 0 |
| 10 | 7 | 21.6 / 32 / 45 | 0 | 1 / 6 | 1.000 | 1.000 (not calibrated) | 0 / 0 |
| 11 | 535 | 21.8 / 39 / 77 | 0 | 503 / 32 | 1.000 | 1.000 (3.2, 18 m) | 0 / 0 |
| **All** | 2599 | 16.0 / 34 / 119 | **1** | | **0.999** | **0.993** | **1 / 1** |

(*) flight 06 counts include the excluded photos: 256 accepted, 114 guarded. Before (same table,
guard off): 70 fixes > 100 m, floor 0.969, self-cal 0.990, 70 / 13 hidden. The one fix left is
04_0420 again (attitude 14.6°, pose 7.2°: the unstraightened centre, 119 m — a bench artefact).
Self-cal 0.993 instead of the 0.998 replayed: the GPU matcher is not bit-reproducible between
runs (inliers differ by a few), flight 04's calibration came out tighter (f 2.2 vs 2.9) and 11 of
its fixes fall just outside 3σ, none wrong. GPS phase 10 %: self-cal 0.984, floor 0.999.
Screen bench (`replay_gyro_heading.py`, clear_v20 / clear_v60 / heavyrain07_v20, `--hfov 100`,
the render's field of view): guard on = identical to no pose at all (median 2.7 / 3.5 / 4.0 m,
max 6 / 10 / 15 m, 0 wrong); guard off every clear fix 280–292 m off (the pose of a filmed
screen is meaningless). No new wrong fix.

For reference, the frame centre (the first flight-03 run, before `--position`): 21.9 m median,
2 fixes > 100 m, floor 30 m 0.998, self-cal 0.995 (flight 03 alone reproduces the earlier
0.998 within 3σ, median σ 17–18 m).

**Verdict on the stated sigma (real drone imagery, 8 flights, 2600 accepted fixes):**
- The model alone (`day_fix_sigma_m`, matcher sigma 5–25 m) is **unsafe on every flight**:
  42–84 % within 3σ (100 % only on flight 10's 8 fixes), 65–71 % pooled. Confirmed on 8 flights.
- In-flight self-calibration plus the 30 m floor before calibration is **safe only with the
  pose–attitude guard**: then 0.999 (floor) / 0.998 (self-cal) within 3σ pooled, every flight
  ≥ 0.993, and no fix over 100 m hidden by its stated 3σ except the eval artefact above.
  **Without the guard (the code before VL-1) it is not safe**: 70 accepted fixes 100–325 m off (2.7 %), all 70
  beyond the 30 m floor's 3σ and 13 beyond the self-calibrated 3σ; flights 05 and 10 at
  0.81 / 0.83 because too few matches arrived while GPS was trusted to calibrate. The earlier
  flight-03 result (0.998) holds only for the frame centre; with the pose (product) it is 0.992
  with 3 hidden wrong fixes.
- The calibrated sigma is honest but not small: median 15–37 m per flight (f 1.6–3.9,
  b 12–22 m): the error on real imagery does not shrink with the inlier count as the model
  assumes. A flight that matches rarely never calibrates and stays at 30 m.
- Limits: a 250 m-off prior per photo, no tracking, no IMU straightening (the dataset's
  attitude is used only to score the guard), one camera type, maps newer than the photos by
  up to 7 years, and the dataset's own GPS errors (flight 06). Still **not a NAVERA flight**.

### Day: a real flight replayed through the whole chain — IMU, tracking, estimator (MARS-LVIG, 2026-10-21)

NAVERA has not flown. The UAV-VisLoc result above is single photos located one by one from a
perturbed prior: no IMU straightening, no tracking, no estimator. This one replays **real recorded
flights with their real IMU** through the product code, as a flight would run it.

**Data.** MARS-LVIG (HKU MaRS lab, mars.hku.hk/dataset.html). **Licence CC BY-NC-SA 4.0, academic
use only — commercial use needs the authors' permission: this is internal evaluation, nothing is
redistributed; ask HKU before quoting it as product evidence.** A DJI M300 RTK with a downward
global-shutter camera (Hikvision CA-050, 2448×2048, 10 Hz, 80° lens, calibrated; replayed at half
resolution, 1224×1024), the drone's IMU/attitude, GNSS and height (DJI OSDK), and its RTK (cm-level,
the truth). Sequences: **AMvalley03** (Armenia, a valley: 545 s, lawnmower at 12 m/s, 130 m above
take-off — the ground under the drone rises and falls by ~100 m, 27–146 m above ground, median
104 m) — complete; **AMtown02** (Armenian village, flat, 80 m, 8 m/s) — **its first 176 s only**:
Google Drive's download quota blocked the rest of it and all of HKisland03 (Hong Kong) for the
whole afternoon. Maps: Esri World Imagery z17 (and z18 for one run), prepared with
`prepare_area.py --fetch-url` as for a mission — evaluation only, its licence does not allow
storing it in a product. Also considered: VPAIR (access on request, no IMU), AerialVL (CC BY 4.0
but 56 GB of zipped frames, GNSS only, no IMU), UAV-VisLoc (above; photos, not a sequence),
Mid-Air (synthetic), EuRoC (indoor).

**What runs** (`navera_tools/bench/replay_flight_dataset.py`; frames from `mars_lvig_extract.py`;
mount from `flight_mount_cal.py`): the camera side as `live_camera` does it (`FrameBuilder`:
undistortion, straightening with the attitude at the exposure, tilt and rotation-rate gates,
heading; `AltitudeEstimator`: height above take-off — the vehicle barometer — GPS altitude while GPS
lasts, and the heights the day node publishes back), frames offered at 1 Hz (`fps` default) and
only after the previous frame's ack; `DaySubscriber` and `EstimatorNode` built by their own
`__init__` (every shipped default; matcher `auto` = DISK + LightGlue on the GPU, SIFT fallback),
wired in-process as the ROS graph wires them (day estimate → estimator → `/navera/position` and
NavStatus → day node), on a virtual clock that advances with the **real processing time on this
Jetson** (a slow frame costs what it costs in flight; GPU shared with other jobs). The drone's GNSS
(5 Hz) is NAVERA's GPS for the first 120 s of the replay, then stops (jamming: no messages, no GPS
altitude). Before the loss the node runs its GPS-check frames (sigma calibration, map bias,
camera-delay samples, vision height, GPS cross-check). The camera mount (yaw −92°, roll/pitch
residual < 2°) was measured once against the RTK on AMvalley03's climb (`flight_mount_cal.py`, an
installer's boresight) and reused for AMtown02 (same rig). The DJI height-above-take-off topic reads
0 in these bags: the barometer is the RTK altitude minus its take-off value. Height truth: RTK
minus a 30 m DEM (AWS Terrain Tiles). Arms: **imu** — frames straightened with the drone's
attitude, heading from it (an IMU with a trusted heading: the product's normal case); **dr** — the
same with no map matching after the loss (NAVERA's dead-reckoning alone: track velocity turned by
the IMU heading + frame-to-frame odometry); **gyro** — no attitude in the frames (not straightened,
no heading), the gyro rate feeding the day node's gyro heading carry.

AMvalley03, replay 40–470 s: GPS for 120 s (climb, hover with a 245° yaw turn, first leg), then
310 s without (7 legs and 6 U-turns). Error of every position published after the loss (day
estimate; the estimator republishes the winner, its error is the same); share within 3 stated σ;
"available" = estimator ticks with a position (FIX or DEGRADED):

| Run | Code | Fixes after loss | Fix error median / p90 / max | Output error median / p90 / max | > 100 m | In 3σ | Available |
|---|---|---|---|---|---|---|---|
| imu | as found | 110 / 310 (36 %) | 6.6 / 9.0 / 13.3 m | 8.3 / 13.0 / 24.0 m | 0 | 100 % | 84 % |
| imu | fixed | 110 / 309 (36 %) | 6.8 / 8.6 / 11.7 m | 8.5 / 18.3 / 28.2 m | 0 | 100 % | 82 % |
| imu | fixed, repeat | 112 / 310 (36 %) | 6.7 / 9.3 / 12.8 m | 8.3 / 16.9 / 36.2 m | 0 | 100 % | 85 % |
| dr (no map matching) | as found | — | — | 98 / 299 / 358 m (71 s) | 35 | 100 % | 24 % |
| dr (no map matching) | fixed | — | — | **4.0 / 9.6 / 12.1 m** (70 s) | 0 | 100 % | 23 % |
| gyro (no attitude) | before the DR fixes | 0 / 310 | — | 124 / 602 / 720 m | 29 | 100 % | 19 % |
| gyro + `local_heading_search` | before the DR fixes | 0 / 51 (6.8 s/frame) | — | — | — | — | 3 % |

Variants of the imu arm (one run each, on intermediate code: the altitude fix only for the first
two, also 16b5f50 alone for the 10° and 0.15 s rows — whose 200 m output maxima are that commit's
post-turn excursion, see below; the GPU matcher is not bit-reproducible, acceptance moves by ±3
points between identical runs):

| Variant | Fixes after loss | Fix error median / p90 / max | Output max | Note |
|---|---|---|---|---|
| true height above ground fed as a rangefinder | 103 / 310 (33 %) | 6.5 / 8.5 / 11.5 m | 246 m (in 3σ) | the height is **not** what limits matching here |
| heights retried 0.8 / 1.25 / 0.64 / 0.5 × | 113 / 287 (39 %) | 6.6 / 9.2 / 11.5 m | 22 m | p90 1.26 s/frame; not kept (no real gain) |
| **z18 map** (instead of z17) | **125 / 232 (54 %)** | 5.2 / 8.6 / 16.8 m | 40 m | p90 2.2 s/frame; the product is fixed at z17 |
| IMU heading 10° wrong | 115 / 308 (37 %) | 6.2 / 8.5 / 11.9 m | 226 m (in 3σ) | within `local_heading_tol_deg` 20° |
| frames stamped 0.15 s late | 114 / 303 (38 %) | 6.7 / 9.3 / 11.5 m | 203 m (in 3σ) | auto latency: 5 of 20 samples, not applied |
| same, GPS for 260 s (170 s denied) | 89 / 170 (52 %) | 6.7 / 9.0 / 9.9 m | 49 m | latency 12 of 20 samples, not applied; available 100 % |

AMtown02, first 176 s only (flat village, 80 m, 8 m/s): GPS 75 s, then **55 s** without (one
leg, 10 s after a 65° turn), fixed code: imu arm 33 / 56 frames matched (59 %), fixes 4.5 / 6.6 /
8.5 m, output 4.5 / 7.9 / 11.2 m, available 100 %, height 2 m off (median, flat ground);
dead-reckoning alone 50 / 93 m (median / max, in 3σ) — the GPS was lost 10 s after a turn, so the
20 s velocity fit is a chord of it (the remaining dead-reckoning weakness). Too short to say more.

Findings (all on real imagery and a real IMU, through the product code):
- **IMU straightening is what makes it work.** After the loss the camera was tilted 12° from vertical
  (median; p90 17°, max 26°): straightened with the attitude at the exposure, the fixes were 6–7 m
  (median) and never above 17 m in any run; 100 % of fixes and of published positions within their
  stated 3σ in every run (self-calibrated σ, median 14 m; 30 m before calibration). No accepted fix
  over 50 m in 1 493 accepted after the loss across 15 runs (mostly the same flight replayed: not
  independent). The pose–tilt guard kept the frame centre on 103 of 112 fixes: on a slope the pose's
  tilt is the ground's, not the camera's.
- **Matching depends on the height above ground at z17.** Accepted share by true height: < 60 m 0 %,
  60–80 m ~10 %, 80–100 m ~20 %, 100–120 m ~40 %, 120–140 m ~73 % (z17 = 0.92 m/px: a 60 m-high
  frame covers ~100 map pixels). A z18 map raised the share from ~36 % to 54 %. NAVERA's design
  heights (300–600 m) are above this regime: this flight is a hard case, not a typical one.
- **The height over relief.** The barometer keeps the height above take-off; the ground under the
  drone moved by up to 100 m: the height used was 28–31 m off (median), 97 m (p90). The heights the
  matches measured were right (median −0.8 to +1.3 m, p90 16–19 m) but only hold where they were
  measured. Fixed (19e1185): the carried image height's stated σ was ~4 m whatever the time since
  the image — 28 % within 2σ; now 57 %. Feeding the true height did not raise acceptance (above),
  so the relief costs honesty more than fixes here; a DEM in the map package (height = barometer
  altitude + take-off ground − DEM under the position) is the real answer (not done).
- **Dead-reckoning through turns — fixed (16b5f50, 482ed90).** The carry turns the track velocity by
  the IMU heading change since it was measured, but that heading came only from a vision fix: right
  after a GPS loss, or on a track of odometry steps, the velocity went straight on — a U-turn 20 s
  after the loss put it 100–360 m off. Now the frames' attitude headings date the velocity; the
  frame-to-frame odometry is still checked against the measured (unturned) velocity — letting it
  through the turn (16b5f50 alone) made the 20 s velocity fit a chord of the U-turn and the carry
  after it ran 4.5 m/s slow (3/3 runs, 200 m excursions, in 3σ). NAVERA's dead-reckoning alone over
  70 s and a U-turn: 98 / 358 m → 4 / 12 m (median / max). Its stated σ is far more cautious
  (≈ 500 m after 70 s, then no output): the 0.25 m/s² unseen-acceleration term dominates — not
  changed.
- **Without a trusted IMU heading, nothing.** The gyro arm got 0 GPS-check matches and 0 fixes: the
  learned matcher needs a heading to turn the frame north-up, the SIFT fallback found nothing on this
  imagery, so the gyro heading (reset only by a vision fix) never started; `local_heading_search`
  (12 headings) took 6.8 s per frame and still found nothing. Use the vehicle's / a magnetometer
  heading; a reset of the gyro heading from the GPS course while GPS is trusted would help (not done).
- **Auto camera delay** needs 20 GPS-check samples above 5 m/s and out of turns: 5 in 120 s and 12
  in 260 s of GPS here — never applied (safe: a 0.15 s stamp error costs 1.8 m at 12 m/s here).
- **GPS cross-check:** the real GPS was never refused or put in doubt during the GPS phases (~1 200
  arbiter ticks per valley run, 730 on the town).
- **Time on the Jetson** (GPU shared with other agents' jobs, frames 1224×1024): median 630–680 ms
  per frame after the loss, p90 ~0.9 s; GPS-check frames ~0.4 s, idle GPS frames ~70 ms; frames
  offered ≈ 1 per second. The estimator's output lags the vehicle by that processing time:
  error at the publication instant median 10.9 m vs 8.5 m at the exposure.

**Still not a NAVERA flight:** machine-vision camera (global shutter, calibrated, sharp) instead of
NAVERA's; 80–130 m above take-off instead of 300–600 m; a multirotor at 8–12 m/s; the IMU is the
M300 flight controller's attitude (better than a BNO085); the mount was calibrated against RTK; maps
are online Esri tiles of another date; one complete flight plus 55 s of another; in-process replay
(no DDS, no camera driver or USB delay). Data: `NAVERA_TESTDATA/mars_lvig/` on the ADATA disk
(bags, `ext/`, `maps/`, `runs/*.json` with every frame).

#### Follow-ups on the same replay (2026-10-21, branch work/day-followups-2026-10-21)

Same tool and data (AMvalley03 replay 40–470 s, GPS for 120 s, 310 s without; AMtown02 first
176 s); one run each (acceptance moves ±3 points between identical runs).

**DEM in the map package** (`prepare_area --dem copernicus`, mission bundle by default;
Copernicus DEM GLO-90 here — GLO-30 is withheld for Armenia; free licence with attribution;
camera side: `AltitudeEstimator` with the arbiter's position, `live_camera terrain_dir`).
Height truth uses another DEM (AWS terrarium): the two differ by 2.6 m median, 15 m p90.

| Run (imu arm) | Height error median / p90 / max | Within 2σ | Fixes after loss | Fix error median / p90 / max | Output median / p90 / max |
|---|---|---|---|---|---|
| AMvalley03 without DEM (merge run) | +28.6 / 97.7 / 127 m | 58 % | 112 / 310 (36 %) | 6.7 / 9.3 / 12.8 m | 8.3 / 16.9 / 36.2 m |
| AMvalley03 with DEM | −3.2 (abs 10.5) / 94 / 121 m | 94 % | 108 / 309 (35 %) | 6.0 / 9.2 / 14.1 m | 8.3 / 39.4 / 60.3 m |
| AMtown02 without / with DEM | 2.0 / 8.9 → 0.2 / 0.8 m | 100 % | 33 → 29 / 56 | 4.5 → 5.5 m median | 4.5 / 7.9 / 11.2 → 5.5 / 7.5 / 11.1 m |

The height is now right where the position is known (the large p90 left is the stretch without
any arbiter output, read over a wide disc of the DEM with a matching sigma). It did **not** raise
acceptance (as the rangefinder variant above predicted), and in both DEM runs the dead-reckoning
over the low stretch (137–198 s, 25–90 m above ground) got worse: output p90 17 → 34–39 m, max
36 → 60–63 m (0 > 100 m, 100 % within 3σ). Not understood (suspect: frame odometry scaled by the
now-correct low height); **so the DEM is stored but live_camera uses it only on request**
(`terrain_dir: area`).

**Map zoom from the area.** The node reads `area.json` (`zoom`, `zooms`; no file = 17) and, with
several zooms (`prepare_area --extra-zoom 18`), picks the finest zoom ≥ 2× coarser than the frame
(`day_pkg/map_levels.py`). AMvalley03 with a z17 + z18 area: every frame chose z18; 124 / 229
fixes (54 %) vs 112 / 310 (36 %) at z17, fix error 5.4 / 8.6 / 16.4 m, 0 > 50 m; cost: p90 2.3 s per
frame (0.87 s at z17), so fewer frames. An area with one zoom behaves as before.

**Gyro heading from the GPS course** (gyro arm: no attitude in the frames): while GPS is trusted the
gyro heading is reset from the GPS course (camera offset from the mount yaw, then learned from
vision) and given to the matcher. GPS-check matches 0 → 8, fixes after the loss 0 → 1, output
error 124 / 601 / 720 → 24 / 50 / 59 m (> 100 m: 29 → 0), availability 18 % (unchanged). What still
blocks fixes: unstraightened frames (12° tilt) are refused by the pose–tilt guard, and the heading
ages out ~85 s after the loss.

Screen bench recordings (`replay_gyro_heading.py`, 10 recordings, before / after): **not a valid
check yet** — the tool had been crashing since the camera-delay estimation was added (fixed), and
it now runs but publishes no output in either version (tiles of its default area missing,
e.g. `tile_17_69415_51534.jpg`): identical 0 / 0, no evidence either way.

### Night vision (`night_pkg`, STHN one-stage)

- Before 2026-09-28 the model ran with **random weights**: the checkpoint keys never
  matched. Inputs, output reading and configuration were also wrong. It is now rebuilt
  exactly as trained (`weights/one_stage/config.json`), and it refuses to start if the
  weights do not load.
- Synthetic test: greyscale satellite crops stand in for thermal frames, at 2 locations.
  Known shifts of 100–150 m are recovered within **3–17 m**. One 320 m shift failed
  (238 m error), yet its consistency score was 0.93, so it was not flagged.
- GPU: ~225 ms per frame (fp32) vs ~1.5 s on CPU, identical positions (≤ 0.02 m). The Jetson
  PyTorch build cannot load CUDA linear algebra on JetPack 6, so the small homography
  solves run on the CPU automatically. fp16 brought no speed, memory or accuracy gain.
- **Scale (LOC-16, fixed 2026-09-30).** STHN expects the thermal image to cover 512 px of the
  satellite map at map resolution, north-up. Each frame is now resampled from the altitude
  (frame_meta) and the camera's horizontal field of view (`camera_hfov_deg`, required), turned
  north-up with the heading (frame_meta, else the IMU) and cropped to that footprint. Synthetic
  frames (grey renders of the map, 84° camera, prior 100–250 m off, 12 per case):

  | Altitude | Unscaled (before) | Scaled (now) |
  |---|---|---|
  | 250 m | 149–263 m median | 11–13 m median, p90 ≤ 32 m |
  | 400 m | 11–215 m | 8–11 m |
  | 600 m | 98–218 m | 8–11 m |

- **Minimum ground coverage and motion gate.** Tracking along a route at 300 m with a
  diagonal heading (the rotated frame covering 77 % of the reference) ran away to 2.4 km
  while the consistency stayed ~0.9. Frames covering < 85 % of the reference are refused
  ("fly higher": ≥ ~350 m with an 84° camera), and a fix implying a speed above
  `max_speed_mps` (30) is rejected. At 400 m: worst 13 m over 5 headings × 30 frames.
- **Mission simulator, drone at 400 m, night, GPS jammed:** 290 matches, median 6 m, p90
  11 m, max 37 m; with its positions given to the autopilot the drone kept flying its
  mission. Optimistic: the thermal images are grey renders of the same map. Measured with
  an 84° thermal view. The simulator's physical thermal camera was 56.7° × 48°: it covers
  85 % of the reference only from ~480 m, above the simulated drone's 400 m ceiling — no
  night position was possible (acceptance test R12, 2026-10-03); it is now ~75° × 63°
  (from ~350 m). The minimum height depends on the thermal camera's
  field of view: footprint ≥ ~500 m × 425 m.
- **The replay set cannot be used for night vision.** Its frames cover only ~190–300 m of
  ground, mostly sea (measured by correlation with the map at 0.12–0.2 m/px); the former
  4.7 km "drift" came from feeding them at the wrong scale. The node now refuses them
  ("footprint too small").
- **Conditions stress test (2026-10-17, `navera_tools/bench/night_conditions.py`).**
  Synthetic frames rendered from the map through the simulator's camera geometry (75° ×
  63°, 640 × 512, true attitude, straightened by `FrameBuilder` with a 0.5°/2° IMU error,
  3 % height error, prior 100–250 m off, 400 m unless stated), 24 frames per condition,
  the same poses in every condition. Before the fix STHN accepted **every** frame, including
  frames with no position information, each 200–1000 m wrong with consistency ~1: 228 wrong
  accepts (> 50 m) out of 1272. Each fix is now re-run from a search centre 150 m away and
  kept only if both agree within 25 m, and the map warped into the frame must correlate
  with it (gradient NCC ≥ 0.05); empty wedges of a straightened frame no longer count as
  ground. Accepted / 24, median / max error (m), wrong accepts:

  | Condition | Before | After |
  |---|---|---|
  | Nominal (urban + farmland) | 24, 10 / 20, 0 | 24, 10 / 24, 0 |
  | Polarity inverted, NETD ×4, stale-NUC stripes, vignetting + narcissus, AGC jumps, hot spots (percentile or min-max AGC), birds + aircraft, occluded corner, fog (transmission 0.35), rain | 24, 9–11 / 18–25, 0 | 23–24, 9–11 / 16–29, 0 |
  | Material remap (heuristic night emission: man-made warm, vegetation cool, water warm) | 24, 9 / 66, **1** | 21, 8 / 19, 0 |
  | Crossover contrast ×0.12 / ×0.05 | 24 / 24, 11 / 19, 0 / **9** | 22 / 13, 10 / 10, 0 / 0 |
  | Fog transmission 0.12 | 24, 11 / 26, 0 | 22, 10 / 21, 0 |
  | Microbolometer smear 10–100 m/s (τ 12 ms) | 24, 10 / 20, 0 | 24, 9–10 / 24, 0 (≤ 1 px: no effect at 400 m) |
  | Cloud below, 30 % / 60 % of the frame | 24 / 24, 69 / 208, **13 / 23** | 9 / 1, 11 / 13, 0 / 0 |
  | Height 350 / 600 / 1000 / 1500 m (150–250 m: refused, footprint) | 6 / 24 / 24 / 24, 11–20, 0 | 5 / 24 / 23 / 23, 10–22, 0 |
  | Heading error 5° / 10° / 20° / 30° | 24 each, 12 / 25 / 198 / 236, 0 / **4 / 22 / 24** | 23 / 16 / 0 / 0, 11 / 18, 0 / 1 (55 m) / 0 / 0 |
  | … with `heading_retry_deg` 10,−10,20,−20 (12 frames) | — | 20°: 11/12, 30°: 8/12, 20 m median, 1 at 55 m; 1.4–1.8 s per frame |
  | Tilt 10° / 20° (straightened) | 24 / 24, 9 / 10, **1 / 7** | 20 / 15, 8 / 8, 0 / 0 |
  | Height error −20 % / −10 % / +10 % / +20 % | 0 / 12 / 24 / 24, —/15/10/16, 0 / 0 / **2 / 7** | 0 / 11 / 20 / 13, —/14/10/11, 0 |
  | Prior 50 / 500 / 750 / 1000 m off | 24 each, 10 / 20 / 689 / 950, 0 / **2 / 24 / 24** | 24 / 13 / 0 / 0, 8 / 10, 0 |
  | Terrain urban / farmland / coast | 24, 8 / 10 / 11, 0 | 24 / 22 / 24, 7 / 10 / 11, 0 |
  | Coast with the sea as one temperature (LWIR) | 24, 15 / 225, **5** | 15, 11 / 25, 0 |
  | Open sea / salt flat / sensor noise / uniform frame | 24 each, 236–269, **24 each** | 0 each |

  Stated sigma: 100 % of accepted fixes within 3 sigma after (as low as 0–8 % before on the
  failing conditions). Cost: a second STHN inference per accepted frame (~570 vs ~450 ms
  per frame here, CPU shared with another job; ~225 ms per inference on an idle GPU). The
  search area is ±745 m: a prior farther off cannot be found (now refused, not wrong).
  Optimistic: the frames are grey renders of the very map STHN matches against; real LWIR
  contrast follows materials and temperature, not visible albedo.

**Not validated:** real thermal imagery (which differs from grey satellite images), real
camera calibration, and the wrong-fix thresholds (re-check 25 m, map correlation 0.05),
set on synthetic frames only: a real thermal frame will correlate less with a daylight map.
STHN's consistency score does not detect a wrong match; the re-check and the motion gate do.

**Offline regression benchmark (2026-10-22, NAV-PERF-03, `navera_tools/bench/night_perf.py`,
`navera_tools/tests/test_perf_night_vision.py`, nightly with `NAVERA_PERF=1`, ~3.5 min on the GPU; 7 min the first time, while the thermal frames are rendered into `~/.cache/navera_perf`).**
NightLocalizer with the node's default gates and retries. Synthetic (`night_conditions.py`, 24 poses):
nominal 400 m 24/24, 10.8 / 16.2 / 23.4 m (median / p90 / max), 600 m 24/24, 10.5 / 16.5 / 18.0 m,
farmland 22/24, 10.8 m, open sea and uniform frames 0/24 accepted, 0 wrong. Real night LWIR (below,
Bordeaux, the 60 poses of 2026-10-21, 1000 m): Boson 640 23/60, 10.3 / 20.3 / 31.5 m; Hikvision 160 17/60,
10.7 / 26.0 / 49.7 m; 0 wrong, 100 % within 3σ — identical to the retry-gate runs below. The earlier
"8–13 m median at 250–600 m" used an 84° camera; with the 75° camera 250 m is refused and 350 m mostly (5/24, footprint, 2026-10-17).

### Night vision on REAL aerial thermal imagery (2026-10-21)

`navera_tools/bench/night_real_thermal.py` (+ `thermal_ortho.py`). **Real thermal radiometry,
synthetic geometry; still not a NAVERA flight.**

**Data.** STHN's own data (Boson-nighttime / satellite-thermal-dataset v1–v3, Hugging Face
`xjh19972/boson-nighttime`, 131 GB) is **gated and licensed "non-commercial research only"**;
the Caltech Aerial RGB-Thermal dataset is CC BY-NC. Neither was downloaded: using them to
validate a commercial product needs the owners' written permission (IRIS decision). Used
instead, both under Licence Ouverte (Etalab, commercial reuse with attribution), on the ADATA
disk under `NAVERA_TESTDATA/thermal/`:

- **Bordeaux Métropole, "Thermographie aérienne hiver 2018"** — aircraft infrared scanner
  flown at **night** (15–17 Nov 2017, 8–9 and 22–23 Feb 2018), 0.5 m, ~34 × 34 km (540 tiles,
  1.4 GB). Published as a rainbow palette (169 levels) and turned back into a scalar by hue;
  ~7 % of the area is clipped at the warm end (mostly the Garonne).
- **CRAIG, "Thermographie 1 m – Clermont-Ferrand – été 2024"** — FLIR MWIR (3–5 µm),
  11 Aug 2024 16–18 h (**day**, heat wave), 1 m float temperature, ~10 × 11 km (228 MB); one
  area the producer masked (airport) excluded.
- Map: Esri World Imagery z17 (NAVERA's map provider), fetched for the poses (7.1 k tiles).
  Neither area is in STHN's training data (US flights): every frame is held-out.

**Method.** A nadir camera at a random true position (fully inside the data), random heading,
is rendered from the orthomosaic (supersampled, 0.5 px optics blur, noise, percentile AGC,
white-hot) at the sensor's resolution; NightLocalizer.localize is called exactly as
`night_subscriber` (map check 0.05, re-check 150 m / 25 m, heading retries ±10/±20°, height
retries +10/−10/+20 %), measured height 3 % 1σ, heading 2° 1σ, prior 100–250 m off in a random
direction; the same poses for every sensor / height. Limits: orthophoto geometry (no relief,
building lean or motion blur), nadir only, one frame at a time (no tracker / motion gate),
the thermal products' own registration against Esri (a few m), the Bordeaux palette
quantisation. Jetson Orin Nano, STHN fp32 on the GPU (shared machine: GPU held by a lock,
CPU busy with other jobs).

**Results (after the centring fix below).** Accepted / frames, error of accepted fixes
(median / p90 / max, m), wrong accepts (> 50 m), median time per frame:

| Data | Camera | 500 m | 700 m | 1000 m |
|---|---|---|---|---|
| Bordeaux **night** LWIR | Boson 640, 50° | 16/60, 14/26/29, 0 | 22/60, 11/22/30, 0, 2.1 s | 23/60, 10/20/32, 0 |
| | Hikvision 160 × 120, 50° | 10/60, 16/21/30, 0 | 17/60, 12/22/36, 0 | 21/60, 12/50/176, **2** |
| Clermont **day** MWIR | Boson 640, 50° | 35/50, 7/14/21, 0 | 41/50, 7/13/19, 0, 0.53 s | 42/50, 8/14/20, 0 |
| | Hikvision 160 × 120, 50° | 30/50, 9/23/33, 0 | 43/50, 7/14/31, 0 | 39/50, 8/14/36, 0 |

- **Night: about one frame in three gives a position (28–38 % at 700–1000 m), with no wrong
  accept for the Boson-class camera.** Refusals: map check failed (23–28 of 60), not confirmed
  from the second centre (14–18), and at 500 m footprint too small (33–48: a 50° camera covers
  the 433 m reference only from ~540 m; the +10/+20 % height retry passes some of them).
  Time: ~0.55 s for an accepted frame (two inferences + map check), ~2.2 s for a refused one
  (up to 7 retries × 2 inferences). Day MWIR: 70–86 %.
- **Gates on real thermal (gates off, no retry, Bordeaux, 180 frames, Boson 700/1000 m +
  Hikvision 700 m): raw STHN is wrong (> 50 m) on 99 of 180 frames** (median 53–56 m), with
  consistency ~1. The default gates (map NCC ≥ 0.05, re-check ≤ 25 m) keep 57 frames, 55 of them
  within 25 m, 0 wrong; re-check 35 m: 0 wrong, +2; 50 m: 4 wrong. The thresholds set on
  synthetic frames hold on real thermal; they are kept.
- **Stated sigma:** 99.4 % of 477 accepted real-thermal fixes within 3σ (the synthetic fit gave
  99.4 %). The three outside are 160 px frames accepted after a retry.
- **Wrong accepts come from retries on 160 px frames.** Over all real-thermal runs (runs
  before and after the fix counted separately): 640 px cameras, 511 accepts, **0 > 100 m**, 2 at
  51–58 m (first attempt; one with a forced 15° heading error); 160 px cameras, 384 accepts,
  **2 > 100 m (171, 176 m) and 3 at 56–91 m** — the two > 100 m and the 91 m one after a heading
  or +20 % height retry (143 retry accepts), the 56 and 61 m ones first-attempt (241). Heading
  retries with a nominal (2° 1σ) heading on 160 px frames: 4 accepts, 2 wrong. With retries
  off, the 160 px camera has 0 accept > 100 m (Bordeaux after the fix: 0/60, 14/60, 12/60 at
  500/700/1000 m, 0 wrong). With a real 15° heading error (Clermont, 700 m, 50 frames) the
  retries recover 76–82 % with 1 wrong (58–61 m) per camera.
- **Polarity:** black-hot Bordeaux (Boson 700 m) 18/60, 9 m median, 0 wrong (white-hot 22/60).
- **Other cameras (Clermont day, 700 m, 40 frames, before the fix):** InfiRay 640 63° 34/40,
  8 m; Boson 640 95° 33/40, 9 m; Lepton 160 × 120 57° 28/40, 12 m, **1 wrong (171 m, after
  a −20° heading retry)**; Boson 640 50° 33/40, 8 m, 1 at 51 m.
- **Control** (frames rendered from the Esri map itself, same poses, Bordeaux 700 m): Boson
  57/60, Hikvision 59/60, 7–8 m median: the night failures are the thermal-vs-day-map gap,
  not the geometry. They are not explained by the map's vegetation share; by eye they are
  tree-covered suburbs and uniform pine forest/heath (winter night thermal vs summer day
  map), successes dense urban/industrial blocks and field/wetland edges.
- **Residual bias.** Exact map crops given to the pipeline (no rendering, 3 maps: Bordeaux,
  Clermont, Sousse; 330 fixes) come back 2–6 m north and 1–4 m west of the truth at every
  site: a property of the STHN weights (or their training labels), ~1 STHN pixel. The real-
  thermal errors add the products' registration to Esri (Bordeaux ~+12 m N, Clermont ~+7 m
  N in the means). Not corrected: `map_offset_lat/lon_deg` can absorb it once measured on
  NAVERA's own map and flights.

**Bug fixed (night_pkg).** `normalize_query` turned the frame about (w/2, h/2) on a padded
canvas then cropped with a floor: the frame's optical centre missed the query centre by up to
~1 camera pixel — up to 7 m for a 160 × 120 camera at 1000 m, 0.4–2 m for a 640 px one,
depending on the heading. Now one affine map places it exactly (residual 0.001 m; regression
test `test_frame_centre_lands_on_the_query_centre`). Effect: Clermont Hikvision 700 / 1000 m
median 11 → 7 m and 12 → 8 m (36 → 39 accepted at 1000 m), Boson 8 → 7 m; Bordeaux Boson
700 m p90 26 → 22 m, Hikvision 500 m median 18 → 16 m; Boson: no new wrong accept. Bordeaux
Hikvision 1000 m changed from 1 wrong (56 m) to 2 (176 m after a −10° heading retry, 91 m
after a +20 % height retry): both frames were refused before; the retries on 160 px frames
are the weak point, not the centring (see above). Synthetic A/B, same 72 poses, before /
after: farmland 60 / 60 accepted, 0 / 0 wrong; olives 55 / 54, 0 / 0; tilt 15° 47 / 48, 0 / 0;
coast with a flat sea 49 / 46, **1 / 2 wrong** (59 → 60 m on the same frame, and one frame
refused before by 28 m vs the 25 m re-check now accepted 92 m off). Net over everything
measured: **2 more wrong accepts (Hikvision 1000 m, flat-sea coast), all on frames that were
at a gate's edge before**; no systematic change, but not "0 new wrong accepts" — keep or
revert the fix is a review decision.

**Retry gate (2026-10-21, after the above).** Every hypothesis of every frame was recorded
(`--probe-jsonl`, `night_retry_probe.py`: all retries run, not only up to the first success) and
localize's choice replayed with and without a gate (`night_retry_gate_eval.py`). Real code
path, Bordeaux Hikvision 1000 m: 21/60, 2 wrong (max 176 m) → 17/60, 0 wrong, 11 m median,
max 50 m — as the replay predicted. 1940 frames: real thermal Bordeaux night (Boson 640 / Hikvision
160 × 120 at 500/700/1000 m, black-hot, 15° heading error), Clermont day (same, plus InfiRay
640, Boson 640 95°, Lepton 160 at 700 m), synthetic `night_conditions.py` (the 13 conditions of
the earlier set incl. `terrain_coast_flat_sea`, the 72-pose A/B set, heading 10/20°, height
−10/+20 %, field of view −10 %, 350 m) with the product retries on.

- **What separates right from wrong retried fixes:** STHN's own quad consistency. Wrong
  retried fixes (7 chosen, 53–176 m; 3 more, 55–228 m, behind an earlier right one): 0.85–0.97;
  first-try right fixes ≥ 0.95 (1st percentile). The map-check NCC (wrong 0.06–0.43), the
  second-centre distance (wrong 4–24 m: a < 15 m re-check would keep 4 of the 7), the
  shifted-map control margin (negative for most right real-thermal fixes too: the peak is
  broad), agreement with the other hypotheses (wrong ones 4–31 m from another answer) and
  the number of retries did not separate them.
- **Gate:** a retry is kept only with consistency ≥ 0.97 (`retry_min_conf`; NCC / re-check /
  per-try penalty available, defaults as a first try: each cost more right fixes for no wrong
  one removed — re-check 20 m kept 91 %, +0.005 NCC per try 90 %). A refused retry does not
  stop the search. Margin: the closest wrong retry was 0.9698 (synthetic heading 20° off, 53 m,
  +10° retry; the +20° retry is then kept, 18 m); 0.96 lets it through, 0.975 keeps 94.5 %.

| Set (frames) | Accepted before → after | Wrong (> 50 m) | Right retried | Wrong retried |
|---|---|---|---|---|
| Bordeaux night, 640 px (180) | 61 → 61 | 0 → 0 | 19 → 19 | 0 → 0 |
| Bordeaux night, 160 px (180) | 48 → 44 | **2 → 0** | 20 → 18 | 2 → 0 |
| Bordeaux black-hot, Boson 700 / Hik 1000 (120) | 37 → 36 | **1 → 0** (Boson, 170 m) | 6 → 6 | 1 → 0 |
| Bordeaux heading 15° off, 1000 m (120) | 35 → 33 | 2 → 2 (first try, 60–65 m) | 32 → 30 | 0 → 0 |
| Clermont day, 640 / 160 px (300) | 230 → 225 | 0 → 0 | 63 → 58 | 0 → 0 |
| Clermont heading 15° off, 700 m (100) | 79 → 77 | 2 → 2 (first try, 58–61 m) | 56 → 54 | 0 → 0 |
| Clermont other cameras, 700 m (160) | 126 → 125 | 1 → 1 (first try, 54 m) | 13 → 12 | 0 → 0 |
| Synthetic 13 conditions (312) | 195 → 194 | **2 → 1** (flat sea 92 m, first try) | 7 → 7 | 1 → 0 |
| Synthetic A/B 72 poses (288) | 226 → 222 | **4 → 2** (flat sea 92 / 60 m, first try) | 16 → 14 | 2 → 0 |
| Synthetic heading/height errors (180) | 161 → 160 | **2 → 1** (first try) | 96 → 96 | 1 → 0 |
| **All (1940)** | 1198 → 1177 | **16 → 9** | 328 → 314 (95.7 %) | **7 → 0** |

  Wrong retried accepts: 7 → 0 everywhere. The 9 left are all first tries, 51–92 m: the
  flat-sea coast (92 m; it was a first try too in the 2026-10-21 runs, not a retry), and a 15°
  heading error accepted at the given heading. They are outside a retry gate. The Lepton 171 m
  retry accept seen before the centring fix did not recur. One frame at a time; the tracker
  (`night_track.py`) only sees fewer retried fixes and was not re-run.

**Camera verdict (what resolution / field of view is needed).**
- **Resolution:** STHN works at ~1.7 m/px internally, so the Boson 640 (0.7–1.5 m/px at
  500–1000 m) and the 160 × 120 Hikvision (3–6 m/px) reach similar availability by day and at
  night; but the 160 px camera is less accurate at night (p90 22–50 m vs 20–26 m) and produced
  the only wrong accepts > 100 m. **640 × 512 is the requirement for flight**; a 160 × 120
  camera (Hikvision bench unit, Lepton) is usable on the bench; since the retry gate its retries
  made no wrong accept (they did before: turn them off, `heading_retry_deg:=""`,
  `height_retry:=""`, if the gate is disabled).
- **Field of view / height:** with 50° the footprint covers the 433 m reference from ~540 m;
  at 500 m most frames are refused (or pass only through the +10/+20 % height retry). Fly
  ≥ 600–700 m with a 50° lens, or use a wider lens (62.9° InfiRay / 95° Boson worked at 700 m
  by day: 34/40, 33/40, 0 wrong).
- **Night availability, not accuracy, is the limit:** ~1 frame in 3 over a European city
  at night against a summer day map (no wrong accept with the 640 px camera). A real night
  flight with the product camera remains the blocker for any accuracy claim.

### Celestial (`cn_pkg`)

- The latitude formula took a single root (the arcsine's principal value). It was right only
  when the boresight's hour angle satisfied |H| < 90°; any other pointing produced positions
  hundreds to thousands of km off. It now computes both solutions and
  picks the one matching a prior position. If the prior can't tell them apart, no
  position is reported.
- Star coordinates are now corrected for precession to the date of observation. The
  error was about 0.4° in right ascension in 2026, i.e. tens of km.
- The node no longer uses a fixed test date or camera angles. Without a measured camera
  attitude (from the IMU), it reports no position.
- Round trip over 20 000 random camera pointings: 0 wrong positions, 1–2 % reported ambiguous.

- **End to end, 2026-09-30** (astrometry.net 0.89, Tycho-2 index 10–19), on star fields drawn
  from the Yale Bright Star Catalogue for a known position, time and attitude (60° camera):
  - the solver's fit was anchored near an image edge and came out ~1° off at the centre
    (111 km); `--resort` made it 46′. Now anchored at the centre, 4th-order fit: 2.9′;
  - astrometry.net's Python helpers use `np.bool` (gone in NumPy 1.26): nothing was solved;
    those steps are skipped;
  - attitude now from the IMU **at the frame's exposure** (it was read at processing time:
    degrees of error on a moving drone).

  | Camera attitude | Position error |
  |---|---|
  | perfect, camera up / at 75° | 5.5 km / 6.5 km (solve 3–13 s) |
  | tilt error 0.5° | 53 km |
  | tilt 0.5° + heading 2° | 91 km |
  | simulated BNO085-class IMU (0.3° / 1.5°), drone in flight | 24–119 km, ~50 km typical |

  Each degree of attitude error costs ~111 km: **celestial is a coarse fix** (region,
  GPS sanity), stated with `attitude_sigma_deg`, never a position to fly a mission on. A
  levelled (gimballed) star camera and a better attitude source are what improve it.

- **First real sky photo, 2026-10-01** (`ImageTest.jpeg`, 1200×1600, found on the data disk in an
  earlier project; no date, place or attitude recorded): with NAVERA's solver settings the image
  centre is identified in 20 s, **1.7′ from an independent earlier solution** (Siril/astrometry).
  This checks star identification on a real photograph; it cannot check a position (no time,
  place or attitude). It also exposed that the secondary `wcs` solver mode failed on real photos
  (`np.bool` in astrometry.net's line removal) — fixed.

**Not validated:** a real sky image with known time, place and attitude (position accuracy),
clouds and light pollution, a real IMU (for the 360 all-sky solver, real skies with known time
and place: next section).

### Celestial 360 on real night skies — public all-sky cameras (2026-10-21)

The 360 all-sky solver (`cn_pkg/allsky.py`: detector, lost-in-space identification, focal
refinement, quality gate — the code the flight node `solver_mode allsky360` and the field
service run) on **real** night-sky frames with an exact UTC and a surveyed position, before its
first real drive. Tool: `navera_tools/bench/realsky_validate.py`; data and per-frame results
(JSON lines) on the data disk under `NAVERA_TESTDATA/sky/` (frames from the ESO archive).

**Sources** (ESO Science Archive, public, FITS with `DATE-OBS`; site VLT platform, Paranal,
-24.6276°, -70.4051°, 2635 m):

| Camera | Frames used | What it is | Pixel |
|---|---|---|---|
| MASCOT | 343 (38 nights, Jan 2023–Oct 2026, 9 per night spread dusk to dawn) + 168 (14 nights picked for clouds) | cheap CCD + fisheye, fixed; 8 s exposures with the moon up, 90 s without; hot pixels, blooming, vignetting, VLT laser guide stars | 0.22°/px |
| ALPACA | 48 (12 nights, 2023–2026) | science CMOS + Canon 12 mm fisheye on a **tracking** mount, 120 s; binned to 2048 px | 0.084°/px (≈ the Insta360's 0.10°/px) |

Conditions covered: moonless and full-moon nights, moon glare at any altitude, real clouds
(thin cirrus to overcast, moonlit altocumulus), nautical/astronomical twilight, airglow,
satellite and laser streaks, real noise, real PSFs and vignetting. Not covered: colour
(both cameras are monochrome; the Insta360 is a Bayer sensor), H.264, two lenses (the
lens-agreement test cannot be exercised), a moving vehicle.

**Adapter (honest about what differs):** each camera is ONE fisheye lens looking up, given to
the solver as one `sky360.Lens` with its own frame as the "IMU" frame; the frame is turned into
the 8-bit, gamma-encoded image NAVERA's camera delivers and passed **unchanged** to
`allsky.locate` (calibrated focal, `f_scales=(1.0,)`, bundled BSC5 catalogue to mag 4.0). Lens
(centre, f, k1, mirror) and mount (camera-to-ENU rotation → 'up') are measured from the stars of
separate calibration nights at their true alt/az (astropy, site pressure) by a brute-force
grid + least squares on pixel residuals — not with the solver under test (MASCOT 0.23 px rms,
941 stars, 5 frames of 2023-08-12; ALPACA 0.35–0.42 px, three lens epochs: the lens or its
focus changed in 2023-10 and again before 2025-01, seen as a 1.6 % focal change). Calibration
nights are excluded from the results. 'up': MASCOT is bolted down → one fixed 'up' for all
3.8 years (exactly NAVERA's situation, mount known once); ALPACA's tracking mount moves
0.0–0.5° between frames → its 'up' is fitted per frame on the truth, so ALPACA errors are the
star fit alone (identification and refinement), not a mount test.

**Results** (fix = accepted by the gate; error = great circle to the truth; "wrong" > 50 km;
"wrong ids" = identifications > 50 km off seen with the gate opened, all refused):

| Set | Night (sun < -18°) solved | median / p90 / max km | Moon down | Moon up | Twilight (-18..-6°) | Wrong accepted | Wrong ids refused | Right ids refused |
|---|---|---|---|---|---|---|---|---|
| MASCOT | 248/263 (94 %) | 3.7 / 12.0 / 17.6 | 117/117, 2.9 km | 131/146, 4.4 km | 38/80 | **0** | 12 | 6 |
| MASCOT cloudy nights | 70/139 (50 %) | 8.7 / 14.4 / 19.4 | 10/14 | 60/125 | 9/29 | **0** | 21 | 13 |
| ALPACA (star fit only) | 24/24 (100 %) | 1.1 / 2.0 / 2.1 | 18/18 | 6/6 | 24/24 | **0** | 0 | 0 |
| MASCOT, shallow copy | 144/263 (55 %) | 3.4 / 10.2 / 16.8 | 112/117 | 32/146 | 0/80 | **0** | 23 | 8 |
| MASCOT cloudy, shallow | 11/139 (8 %) | 12.6 / 15.1 / 16.4 | 7/14 | 4/125 | 0/29 | **0** | 5 | 2 |
| ALPACA, Insta360-depth copy | 18/24 (75 %) | 0.9 / 4.1 / 6.1 | 18/18 | **0/6** | 3/24 | **0** | 20 | 3 |

"Shallow" copies (`--degrade`): the real frame with the sky above background scaled down
(MASCOT ×0.15, ALPACA ×0.01: ~29 spots, matched stars to mag ~3.9), 2 DN noise and JPEG q75 —
real positions, PSFs, glare and clouds, but a depth like a short video exposure. The Insta360's
real depth on a real sky is still unknown; these bracket it.

- **No wrong position was accepted in 1 118 frame solves** (559 real frames, each also as a shallow copy).
  Pooled, 702 identifications were made with the gate opened: 621 right, 81 wrong; the gate
  accepts 587 right and 0 wrong. The wrong ones had m ≤ 6 (41, refused by `MIN_MATCHED`) or
  m 7–10 with rms ≥ 0.151° (40; one with p 0.0098 — a third-tier p — refused by its rms ≤ 0.10°).
- **The 2026-10-19 third tier (p ≤ 1e-2 and rms ≤ 0.10°) is confirmed on real skies**: it adds
  21 right fixes (566 → 587) and no wrong one; the closest wrong identification is 0.05° above
  its rms limit. Loosening was replayed and is **not proposed**: rms ≤ 0.12/0.14 (+2), p ≤ 0.1
  (+4), 6 stars with rms ≤ 0.06 (+12) or ≤ 0.10 (+16) all stay at 0 wrong here, but the margins
  shrink (a wrong 6-star identification at rms 0.114°, right ones up to 0.095°). Gate unchanged.
- **Error budget, fixed camera (MASCOT):** within a night the solver scatters 1.7 km median
  (p90 3.8 km) about the night's mean; the night's mean wanders 0–14 km over 3.8 years because
  the camera's tilt drifted ~0.13° (one calibration from 2023 used throughout). Learning the
  tilt on each night's first 3 fixes (what the field's `TiltCalibration` does with the phone)
  gives 2.7 km median, 5.1 km p90, 8.2 km max on the later fixes. **'up' — not the stars —
  sets the accuracy.**
- **Time stamp:** MASCOT's `DATE-OBS` is the exposure start; a fixed camera's trailed stars are
  centred at mid-exposure. Using the start put every 8 s frame 16 km east-west of the 90 s
  frames (the sky turns 0.46 km/s). The solver must be given the exposure's **middle** — the
  field server's frame stamp (exposure + `FRAME_STAMP_LAG_MS`) must keep meaning that.
- **Moon:** at full depth the moon costs little (MASCOT 90 % solved, 4.4 km); at an
  Insta360-like depth a moon ≥ 50 % lit leaves too few stars (ALPACA copy 0/6, MASCOT copy
  22 %): the gate refuses, it does not guess.
- **Clouds:** on the cloudy nights, the frames where < 30 % of the mag ≤ 3 stars show
  (overcast, or cloud lit by the moon) → 36/104 solved at full depth, 2/130 shallow; 0 wrong.
- **Twilight:** MASCOT starts at sun ≈ -10°: at -9..-12° 35/77 solved at full depth, 0/77
  shallow; ALPACA (120 s) 23/23 at -9..-15°, its Insta360-depth copy 3/24 in twilight. Plan on
  the sun below -12° (better -15°).
- **Junk:** the detector's hot-pixel test rejected 263 spots that are not catalogue stars
  (≤ mag 4.5) and 1 that is, on 12 MASCOT frames (one frame: 18 → 45 stars among the 60
  brightest thanks to it); on 3 binned ALPACA frames it lost 2 of 1 134 catalogue stars.
  Lasers, satellites and lit clouds are rejected as `extended` (≤ 11 per frame) or end in
  refused identifications.
- **Time on the Jetson** (2 cores, `nice 19`, machine shared with other jobs — load 7–18):
  `locate` median 2.1 s (MASCOT 580×512) and 2.7 s (ALPACA 2048×2048, one lens); half of it
  was building rays one spot at a time in the focal refinement. Vectorised (commit
  `perf(allsky)`, identical answers on 33 real frames): median 3.6 → 2.3 s.

**For the real drive:** (1) the moon is 81–100 % lit 21–27 Oct and high most of the night —
expect many refusals; the moon-down windows are short (e.g. 22 Oct after ~02:15 UT); (2) count on
fixes only once the sun is below -12°; (3) let the tilt calibration learn on the first stopped
fixes (it removes the dominant error); (4) keep the raw recorder on — the real Insta360 depth
(how many stars a video frame shows) is the remaining unknown; (5) a refusal is the expected
answer under cloud or bright moon, not a fault.

### Robustness (bench)

| Test | Result |
|---|---|
| GPS: line without checksum / bad checksum | Ignored |
| GPS: receiver in its own dead-reckoning (GGA quality 6) | Reported invalid |
| GPS: serial port unplugged | Node exits (code 1), launch exits, systemd restarts it every 10 s |
| Estimator: one measurement | Published once (it was re-published at 5 Hz) |
| Estimator: timestamp 60 s in the future | Refused ("clock problem") |
| Estimator: GPS flapping every 0.5 s | One source switch in 8 s, no zig-zag |
| Estimator: GPS jumps 5 km in 1 s (spoofing / glitch) | Refused ("possible spoofing"), re-accepted once plausible again |
| Estimator: GPS silent 4 s (jammed), then back 2 km away while vision (stated accuracy) disagrees ("jam, then spoof") | Refused; true GPS accepted as soon as it agrees with vision |
| Estimator: GPS pulled away gradually (40 m/s bench, 4 m/s simulator) while vision (stated accuracy) stays on the truth | Refused once 5 independent fixes in a row are beyond 3 σ, or beyond 5 σ + 50 m for 3 s (simulator, 4 m/s: ~140 m with the 3 σ streak rule, 2026-10-02; ~160–200 m with the 5 σ rule alone, 2026-09-28); status says "GPS refused: … drifting away" |
| Estimator: slow GPS drift (0.5–5 m/s) replayed on the real screen-bench vision (79 F22 campaign runs + 29 of 2026-10-20, one vision fix per 2 s as the GPS checks; `replay_spoof_trend.py`), growth test (`GpsDriftTrend`, 2026-10-20) | False refusals 0 (recorded drift < 10 m, and every run with a good GPS); UAV-VisLoc 7.2 h with a good GPS: 0. Drift at refusal, 3 m/s: 30 m vision σ floor ~120 m → ~72 m; self-calibrated σ: size rules never (the calibration fed by the drifting GPS inflates σ), growth ~60 m; 1 m/s: ~34 m (180/237, self-calibrated σ), not within the run at the 30 m floor; 0.5 m/s: not within the run. Synthetic (σ 10/30 m, AR(1) bias, 2 % wrong fixes 100–300 m): 0 false in 40 h; no gain over the size rules when the vision jitter is as large as its stated σ |
| Estimator: slow GPS drift vs the relative-motion test (`GpsMotionCheck`, GPS displacement vs the day node's visual odometry, 2026-10-21; `replay_spoof_motion.py`: real screen-bench frames of 2026-10-20 (10 runs, VO at 1 Hz full resolution), 8 UAV-VisLoc flights, 40 h synthetic) | False refusals 0 added (bench 10 runs x 3 GPS-noise seeds, UAV-VisLoc 8 flights, 40 h synthetic with 1-4 % VO-scale jumps; the one synthetic refusal is the size rule on two wrong map fixes, present without the test). Bench, where the VO tracks (clear / heavy rain / flare): 3 m/s at 20 m/s refused at 18-42 m instead of 69-78 m, 5 m/s at 18-33 m instead of 105-120 m; at 60 m/s rarely earlier (scale allowance 3 % x speed + 0.5 m/s); 0.5-1 m/s not within the 57 s drift phase. VO lost (vibration 0.7, wind, clouds overlays): unchanged (growth test). UAV-VisLoc: photos 3-5 s apart, phase-correlation VO mostly fails (and the labels' heading is ~10-20 deg off frame to frame): no gain, no false refusal. Not yet measured in flight |
| Estimator: GPS jumps 2 km and stays there, vision with a stated accuracy sees the true position | Refused for as long as it lasts (150 s tested); the true GPS re-accepted 2 s after it returns. Before the fix the spoof was accepted after offset / max speed (33 s) and then the true GPS was locked out |
| Estimator: GPS drifting from vision (estimator test) | Shown "GPS IN DOUBT" (DEGRADED) before it is refused, never FIX meanwhile |
| Estimator: GPS fix 0.8 s late, 60 m behind a vehicle at 75 m/s | Dropped as old news; GPS stays FIX (before: refused as "possible spoofing") |
| Estimator: GPS with an all-zero covariance, an undefined covariance type, a non-PSD covariance | DEGRADED "uncertainty unknown" / DEGRADED / not used (before: FIX with accuracy 0, FIX, republished) |
| Vehicle sensors published BEST_EFFORT (integrator's script, boat IMU) | Received: 3/3 frames usable (before: 4/4 unusable, "no attitude") |
| Output: forwarding switch `enabled` / `on`, sigma above 1000 m | Refused at start with the reason (before: silently false / accepted) |
| Web: control without token / cross-site request / bad input | Refused (401 / 415 / 400) |
| Web: 100 wrong control codes in a row | After 5 wrong codes in 60 s the address is refused (429) for 60 s (before: no delay) |
| Camera stops sending (GStreamer source ends: unplugged, USB reset, stalled stream; `test_live_camera_stall.py`, 2026-10-22) | `camera_health` "stalled", node exits 2.8 s after the last frames (`camera_stall_restart_s` 3 s in the test, 10 s shipped), systemd restarts the pipeline (before: > 50 failed grabs — 100 s with GStreamer's 2 s pull timeout, minutes with V4L2's 10 s, never for a grab that blocks) |
| Frozen camera picture on a real recorded flight (MARS-LVIG AMvalley03 at 1 Hz, 513 frames incl. 52 still on the ground / in the hover; `test_frozen_replay.py`, 2026-10-22) | 0 false freezes; real frames while moving differ by ≥ 16.2 grey levels (threshold 0.5); a driver re-delivering the last picture: caught on every frame; a stream re-encoding the stuck picture: caught from its 2nd frame — one JPEG re-encode changes it by 0.9 (q95) – 3.6 (q75) grey levels, so the 1st one (~1 s old) passes |

### Memory of the day pipeline (Orin Nano 8 GB, 2026-10-22)

F5: a 30 min day run reached 3.5 GB and was OOM-killed after 4.6 min without swap. Measured
again on this Jetson (16 GB swap file present, other jobs idle), RSS of the process and the
system's used memory (MemTotal − MemAvailable) sampled every 0.5 s:

| Run | Peak RSS | System used (from → peak) | Swap used added |
|---|---|---|---|
| Product day chain (DaySubscriber + EstimatorNode in one process, learned matcher DISK + LightGlue, every shipped default) replaying the real MARS-LVIG AMvalley03 flight 40–470 s (104 m above ground median, z17 map; `replay_flight_dataset.py --arm imu`); fixes after the loss 6.1 / 8.7 / 12.3 m (median / p90 / max) | **2.48 GB** | 2.99 → 4.50 GB | 0 |
| `day_perf.py mission` (city + coast at ~520 m equivalent height; the bench's terrain imagery in the same process) | **5.0 GB** | 2.70 → 6.79 GB | +0.26 GB |

The peak grows with the height (a bigger search area and map level): 2.5 GB at 100 m, 3.5–3.7 GB
at 1500 m (F5, D14), 5 GB in the bench mission with its imagery. On the 8 GB box with the rest of
the stack this needs swap on disk: `deploy/install.sh` now makes an 8 GB `/swapfile` when less
than 4 GB is active, every pipeline start and `check_boot.sh` warn without it, and the units set
the OOM order (output chain last, web page first). Not yet run as root on a box.

### Autopilot in the loop (ArduPilot SITL — simulation)

`navera_tools/run_sim.sh`: ArduPilot SITL (Copter 4.5, Rover, motorboat) whose only position
input is NAVERA's output; NAVERA's GPS driver reads a simulated receiver over a
pseudo-terminal. The world and the vision errors are simulated, so these are **behaviour**
results, not accuracy results.

| Scenario | Result |
|---|---|
| Drone, GPS OK, 120 m, 10–15 m/s | NAVERA error 1–4 m; autopilot position error 1–3 m |
| Drone, GPS jammed in flight, vision at the target accuracy (15 m σ, simulated) | Mission continues on NAVERA's vision fix; autopilot error 2–18 m for 2.5 min, no failsafe |
| Boat, 2 km GPS spoof for 150 s | Refused within 1 s; boat continues on vision (3–21 m) |
| Drone, GPS jammed 30 s then spoofed 2 km for 30 s | Spoof refused throughout; true GPS re-accepted 3 s after it returns |
| Drone, GPS spoofed by a slow drift (4 m/s) | Refused at ~160–200 m offset (2026-09-28, 5 σ rule; ~140 m since the 3 σ streak rule of 2026-10-02, item 7); the autopilot followed the drift to ~200 m, then recovered on vision without failsafe |
| Robot, GPS jammed, vision at today's measured accuracy (DEGRADED, withheld) | Autopilot loses its position → its own failsafe (HOLD); stays in it when GPS returns (an autopilot does not resume a mission by itself after a failsafe): the operator resumes it |
| GPS jammed + camera failed | NAVERA: NO FIX → autopilot failsafe (Copter LAND, Rover HOLD) |

**Vision positions carried to the present (2026-10-03).** Before: a vision position was sent
as it was, describing the photo's instant 1–2.5 s earlier while stating the matcher's ±30 m —
plane at 40 m/s with a gimbal: match error 0–1 m, output error 83 m median (0 % within the
stated sigma); drone at 15 m/s: 12–23 m. Now carried along the measured ground velocity,
its accuracy grown by the lag (unit tests: a 1.5 s old photo at 40 m/s is moved 60 m and
stated ±31.5 m; with no velocity known, ±120 m, stamped as measured). The day-vision
freshness window is 5 s (it was 3 s: under load NAVERA alternated FIX / NO_FIX on 20–60 %
of samples and the autopilot landed during a 6.7–9.2 s gap). **Simulator only.**

**With the real day vision** (`day_subscriber`, DINOv2) on simulated camera images, drone at
150 m (≈270 m footprint), 7.5 km route prepared with `prepare_area.py` (356 tiles), GPS jammed
in flight: vision searched a 600 m circle around the last GPS fix (18–21 candidate tiles) and
matched every frame; NAVERA's error 27–187 m, median match error 96 m. With its positions given
to the autopilot (stated accuracy 300 m), the drone continued the mission (autopilot error
27–209 m, one glitch warning, no failsafe); with NAVERA's default (not given), the autopilot
landed. **These accuracies are optimistic:** the camera images are cut from the same satellite
map vision matches against. The best-match score stayed at 0.95–0.98 for good and bad matches
alike, as on real data.

Integration defects found and fixed this way: no velocity sent (ArduPilot assumed zero or
stale velocity → EKF failsafe during take-off); vision fixes labelled 2D (ignored by
ArduPilot); the same fix repeated at 5 Hz; the spoofing gate above; positions forwarded on a
5 Hz timer while arriving at 5 Hz, which dropped or doubled messages — ArduPilot reported
"GPS not healthy" and refused to arm (the estimator and the output now act on arrival). The ArduPilot settings
this requires are in navera_output/README.md.

**QA campaign (2026-09-30)** — scripted missions with every fault, command and invalid input
(backlog §7). Two critical product defects found and fixed: (1) with the real vision, a GPS
spoof left NAVERA without any position and the drone landed — vision idled behind the spoofed
GPS and took the first spoofed fix as its search centre; it now takes its GPS reference from
the arbiter's vetted output and starts as soon as GPS is refused (re-test: 3/3 spoofs taken
over by vision, median 59–129 m, mission continued); (2) a celestial fix (±55 km) forwarded to
the autopilot moved its position by 125 km — positions coarser than `max_forward_sigma_m`
(1 km) are no longer forwarded.

### Long route (simulator, 2026-10-01)

Paris → Tunisia, 1768 km, mapped as ≤ 10 km great-circle legs: 79 775 tiles generated in
105 min (78 904 downloaded), 980 MB on disk. Day vision loads the model and the 80 000-tile
area in 30 s; per frame it compares the 21 tiles of its 600 m circle, as on a small area
(ranking 3–4 ms instead of 289 ms before the grid index); ~1.1 GB more memory in use (1.6 GB
left available on the 8 GB Jetson with the simulator running).

Flown with the real day vision from km 1755 (13 km before the end, uniform terrain near
Gabès), GPS jammed: 185 matches, **median 351 m, p90 853 m**, 44 frames rejected by the motion
gate (jumps of 360–570 m). With vision forwarded at ±300 m, ArduCopter's EKF failed safe
(LAND) after 45 s. Over textured ground (Sousse, same day) the median was 111 m and the
drone flew on. **Day vision is unreliable over uniform terrain** (desert, sea) — consistent
with the project report. Same 13 km, same protocol (GPS jammed 4 min):

| Flight | Rejected frames | Samples with no position | Autopilot failsafe |
|---|---|---|---|
| 80 000-tile area, ±300 m | 44 | — | 45 s |
| 536-tile area of the same place, ±300 m | 58 | 13 / 48 | 61 s |
| 80 000-tile area, ±500 m | 40 | 18 / 48 | 91 s |

The small area fails the same way: **the terrain is the cause, not the size of the map**. An
honest ±500 m delays the failsafe but cannot prevent it: about a third of the time day vision
has no acceptable match (jumps rejected by the motion gate) and nothing bridges the gaps —
no inertial dead-reckoning yet (FEAT-2). Cures: LOC-14 (local features around the prior) and
FEAT-2. **Update — with local feature matching** (same flight): 147 matches, 0 rejected, the
autopilot held 230 s (end of test); see Day vision. (A first ±500 m run was discarded: an orphan estimator from the simulator was
competing with the real one — fixed in 6bff3d6.)

## Real camera chain in simulation (2026-10-02)

The simulated camera is now physical (`navera_tools/sim/physical_camera.py`): fisheye
lens of the Insta360 4K wide-angle class, the TRUE attitude from ArduPilot's flight
physics, the mission's light, motion blur, noise, JPEG. Its raw frames go through
NAVERA's real `live_camera` (undistortion, straightening with the simulated BNO085 —
biased — or the autopilot's attitude, height above ground) to the real day vision.
GPS jammed 240 s at cruise, Sousse, Jetson heavily loaded by another simulation:

| Configuration | Matches | Vision error | Autopilot's error | Outcome |
|---|---|---|---|---|
| gimbal, 72 km/h, box sensors | 190, 0 rejected | < 1 m | median 11 m, max 23 m | arrived |
| gimbal, 72 km/h, vehicle sensors (MAVLink) | 168, 0 rejected | < 1 m | median 10 m, max 19 m | arrived |
| fixed camera, 43 km/h | frames at the 45° tilt limit | — | — | EKF failsafe after 40 s |

Offline, 33 places, random tilts ≤ 12°, heights 120–250 m, IMU bias 0.3°/1.5°
(`navera_tools/bench/camera_chain.py`): straightened 33/33 within 2.6 m (median 1.1 m);
without straightening (the former nadir assumption) median 28 m, 1 wrong. Forward tilts
25 / 35 / 45°: 33 / 33 / 31 of 33. Wrong altitude by +40 % (hills): 0/33 before the
altitude-uncertainty window, 27/33 after (`navera_tools/bench/day_wrong_altitude.py`,
real aerial frames), the measured height within 0.4 % of the truth.

**Optimistic:** the simulated camera sees the map's own imagery over flat ground. A
fixed camera on a multirotor at speed exceeds the tilt limit: use a gimbal.

## Hardware results recorded in the project report (2026-06-02)

The final project report (`rapport_vFinal_Navera.pdf`, 83 pages, found deleted on the data disk)
holds the only results from the real sensors. No sensor recording (log, bag) was kept.

| Sensor | What the report records | Used here |
|---|---|---|
| GPS u-blox Neo-M8N, `/dev/ttyTHS1`, 9600 baud | a valid fix, `$GNRMC,141621.00,A,3544.04006,N,01034.55091,E,…`: 35.734 N, 10.576 E, M'saken — the test site | the receiver's multi-constellation `GN` sentences, with that position, go through `gps_node` over a serial line in `test_gps_serial.py`: accepted, position exact (2026-10-01) |
| Clock DS3231 | specifications only (±2 ppm); the reboot test of 2026-07-14 (−0.148 s vs NTP) is in the git history | — |
| IMU **GY-87** (MPU6050 0x68, QMC5883L 0x0D, BMP180 0x77) on I²C bus 7 | wiring and addresses only, no measurement | replaced by the **BNO085** (bus 1, 0x4A), the IMU on the box: driver rewritten and **verified live on the Jetson on 2026-07-13** — orientation, rates and accelerations at 50 Hz, the gyro responding to motion (commit b51aa5f; no values kept). Not yet checked: its heading reference with a known heading (IMU-3), its noise (covariances are datasheet values) |
| Camera Insta360 ONE R (nadir, fisheye corrected) | the 30-frame `sousse_flight` replay set (25 with GPS, 5 without) | the frames do not show the places their labels say (see Day vision) |
| Celestial, the sky photo `ImageTest.jpeg` | RA 106.1123°, Dec 37.6187°, solve 13 s | NAVERA's solver today: centre RA 106.109°, Dec 37.606° — **0.8′ from the report**, 1.7′ from Siril |
| Night (STHN) on the Jetson | 370 ms/frame (302–419), first 1030 ms, 0 CUDA crash on 5 frames — RGB frames, not thermal | consistent with the ~225 ms measured since on the GPU |

## Known limitations

1. **Accuracy is not established on real data.** No real flight has been recorded with
   camera, GPS and IMU together. This is the first thing to do with a vehicle.
2. **Day vision accuracy is measured on public real imagery and on a bench, not with NAVERA's
   camera in flight.** Local matching (the default since 2026-10-01; DISK + LightGlue, SIFT
   fallback) with the pose–attitude guard: 8 real drone flights (UAV-VisLoc) median 16 m,
   p90 34 m, 1 of 2599 fixes > 100 m; a real flight replayed through the whole chain
   (MARS-LVIG) 6–7 m median, never over 17 m, but only 36 % of frames matched at z17; screen
   bench with the Insta360 3.6–7.3 m median. The stated sigma is honest only after in-flight
   self-calibration (30 m floor before it). The former DINOv2 tile retrieval (fallback,
   `NAVERA_DAY_MATCHER=retrieval`) is **not** accurate enough (442 m median) and must not be
   used to replace GPS. See [PRODUCT_READINESS.md](certification/PRODUCT_READINESS.md).
3. **No inertial navigation (not pursued: FEAT-2, NAV-FUN-20).** The IMU gives the camera's
   attitude and heading changes; it is not integrated into a position — a low-cost MEMS IMU
   would drift hundreds of metres within a minute. Without vision matches, day vision dead-reckons
   along the track measured before the gap for at most 2 minutes / 500 m (simulator figures
   above), then NAVERA gives no position.
4. **One pipeline at a time.** Day and night cannot both be loaded within 8 GB.
5. **Map coverage is Sousse only** (z13–z19 MBTiles). Other areas need their own map, or
   tiles downloaded through `NAVERA_TILE_URL` when a route is generated on `/mission`
   (deploy/README.md §8). The imagery licence must allow offline commercial use.
   **At sea** there are no landmarks: away from the coast vision gives nothing beyond the
   2-minute dead-reckoning; a low camera on a boat (a few metres above the water) has not
   been tested at all. The boat results above are simulator runs with simulated vision.
6. **Vehicle output validated in simulation only** (ArduPilot SITL, above); not yet on a real
   autopilot, and not on PX4 — which does not handle the `GPS_INPUT` message NAVERA sends
   (PX4_INTEGRATION.md; no PX4 SITL run). ArduPilot needs `EK3_SRC1_VELXY = 0` /
   `EK3_SRC1_VELZ = 0` (which also removes GPS velocity fusion while GPS is good) and one
   real GPS fix at power-on (navera_output/README.md); it caps a stated accuracy at 100 m.
   NMEA carries no accuracy: vision positions are not sent over it by default.
7. **GPS spoofing:** a sudden jump beyond the vehicle's maximum speed (`max_speed_mps`, set
   per vehicle) is refused, and stays refused until an independent source with a **stated**
   accuracy (vision / celestial with a known covariance) confirms it. A GPS returning after an
   outage must agree with that source too ("jam, then spoof"), and a trusted GPS that drifts
   away from it is refused (gradual spoofing: 5 distinct fixes in a row beyond 3 σ, or 2
   beyond 5 σ + 50 m for 3 s; never on one fix). A refused GPS comes back only when 2
   distinct independent fixes agree within 3 σ. From 2 fixes in a row beyond 3 σ the GPS is
   shown and sent **"in doubt"** (DEGRADED, accuracy no better than the gap, up to 500 m)
   before it is refused. **All these protections need that independent source.** Day vision provides one while GPS is good (a local match every 2 s
   around the GPS position, stated σ 30 m — not yet measured with NAVERA's camera).
   Measured in the mission simulator (gimbal camera, GPS pulled away at 4 m/s): refused at
   ~140 m and held; NAVERA error median 15 m, max 143 m (before: median 417 m, max 902 m,
   never refused). The autopilot (ArduPilot SITL) absorbed the switch; its later failsafe
   came from a stretch without vision fixes. Over terrain vision cannot match (sea,
   uniform ground) there is no independent source and a gradual spoofer is not caught.
8. **Security model:** DDS is limited to the box itself (`ROS_LOCALHOST_ONLY`). The web
   control API needs a token. The web interface is HTTPS when a certificate is configured
   (NAVERA_TLS_CERT / NAVERA_TLS_KEY), plain HTTP otherwise; 5 wrong codes in 60 s lock an
   address out for 60 s. The /mission page refuses restarts and map generation while the
   vehicle is armed, moving faster than 1.5 m/s, or navigating without GPS. The mission
   simulator (`navera_tools/run_sim.sh`, a development tool) listens on all interfaces
   (ports 8190 / 8443) with **no authentication**: never run it on a networked vehicle.
9. **Start without GPS.** NAVERA needs one GPS fix at start, or an operator start position
   (`/mission`, a search area for day vision only — never a published position). Verified:
   accepted, a bad latitude refused, a vision node started later receives it (latched);
   not tested in flight.
