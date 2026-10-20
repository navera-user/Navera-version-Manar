# NAVERA — Validation status and known limitations

**Release 0.2 — field validation pending.** Last updated 2026-10-03.

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
| Day vision — stated sigma on real drone flights (UAV-VisLoc, 8 flights, 2026-10-20) | **Model alone unsafe (65 % within 3σ); self-calibration + 30 m floor safe (99.8 / 99.9 %) only with a pose–attitude guard not yet in the product — as-is 70 of 2600 fixes 100–325 m off, 13 of them beyond the self-calibrated 3σ** | below: "Day: real drone flights" |
| Day vision — DINOv2 tile retrieval (former method, fallback) | **Not accurate enough to replace GPS** | Median 442 m on labelled replay frames |
| Night vision (STHN homography) | Frames scaled and turned north-up from altitude, camera field of view and heading; motion gate; **simulator only — not validated on real thermal** | 8–13 m median on synthetic frames (250–600 m, any heading); simulated night mission, GPS jammed, vehicle barometer (2026-10-07): 10 m median, 21 m max, stated accuracy (simulator-calibrated) 100 % within 3 sigma; **needs an independent height (barometer) after GPS loss** |
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

**Proposed (not applied; `day_subscriber`/`local_matcher` untouched): pose–attitude guard.** Use
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

For reference, the frame centre (the first flight-03 run, before `--position`): 21.9 m median,
2 fixes > 100 m, floor 30 m 0.998, self-cal 0.995 (flight 03 alone reproduces the earlier
0.998 within 3σ, median σ 17–18 m).

**Verdict on the stated sigma (real drone imagery, 8 flights, 2600 accepted fixes):**
- The model alone (`day_fix_sigma_m`, matcher sigma 5–25 m) is **unsafe on every flight**:
  42–84 % within 3σ (100 % only on flight 10's 8 fixes), 65–71 % pooled. Confirmed on 8 flights.
- In-flight self-calibration plus the 30 m floor before calibration is **safe only with the
  pose–attitude guard**: then 0.999 (floor) / 0.998 (self-cal) within 3σ pooled, every flight
  ≥ 0.993, and no fix over 100 m hidden by its stated 3σ except the eval artefact above.
  **As the code is today it is not safe**: 70 accepted fixes 100–325 m off (2.7 %), all 70
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

### Celestial (`cn_pkg`)

- The latitude formula took a single root. Any camera facing the southern half of the sky
  produced positions hundreds to thousands of km off. It now computes both solutions and
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
clouds and light pollution, a real IMU.

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
| Estimator: GPS jumps 2 km and stays there, vision with a stated accuracy sees the true position | Refused for as long as it lasts (150 s tested); the true GPS re-accepted 2 s after it returns. Before the fix the spoof was accepted after offset / max speed (33 s) and then the true GPS was locked out |
| Estimator: GPS drifting from vision (estimator test) | Shown "GPS IN DOUBT" (DEGRADED) before it is refused, never FIX meanwhile |
| Estimator: GPS fix 0.8 s late, 60 m behind a vehicle at 75 m/s | Dropped as old news; GPS stays FIX (before: refused as "possible spoofing") |
| Estimator: GPS with an all-zero covariance, an undefined covariance type, a non-PSD covariance | DEGRADED "uncertainty unknown" / DEGRADED / not used (before: FIX with accuracy 0, FIX, republished) |
| Vehicle sensors published BEST_EFFORT (integrator's script, boat IMU) | Received: 3/3 frames usable (before: 4/4 unusable, "no attitude") |
| Output: forwarding switch `enabled` / `on`, sigma above 1000 m | Refused at start with the reason (before: silently false / accepted) |
| Web: control without token / cross-site request / bad input | Refused (401 / 415 / 400) |
| Web: 100 wrong control codes in a row | After 5 wrong codes in 60 s the address is refused (429) for 60 s (before: no delay) |

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
2. **Day vision is not accurate enough** (see above).
3. **No inertial navigation.** The IMU gives the camera's attitude and heading changes;
   it is not integrated into a position. Without vision matches, day vision dead-reckons
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
