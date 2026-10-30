# Mission 24 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

Two sessions: **Session 1 — Odometer** (Steps 0–5, badge **Odometer** = checks 1–7, milestone `odometer`) and
**Session 2 — Navigator** (Steps 6–11, badge **Navigator** = all 13 checks). Part A of the lesson (§1–§6) is read before
session 1, Part B (§7–§9) before session 2. Owner decision §7.5 (2026-10-14): the student's trained PatchNet
(`my_desc.pt`, mission 21) is loaded by `navera_lite.vo.keypoint_matches` and raced against phase correlation in
Step 5 (measured, not graded: its numbers depend on the student's weights). Students who never trained one (or lost
it) get the course's `ref_desc.pt` (a copy of solutions/21-features/my_desc.pt) — the runner says which file it used.

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. Phase correlation with numpy's FFT, compared with OpenCV | §2–§3 (spike at 5; peak (310, 5)) | Steps 1–2 (TODO 1) | 1, 5, 6 |
| 2. Pixels → metres east/north; dead reckoning | §5–§6 (θ = 180°; 4 % too long) | Steps 3–4 (TODO 2, 3) | 2, 3, 5, 6 |
| 3. Why derotate; keypoint odometry and the learned descriptor, measured | §4 (mean vs median) | Step 5 (TODO 4) | 4, 7 |
| 4. Drift = random walk + bias; find the biases from data | §6–§7 (25 and 400 steps) | Steps 4, 6 (TODO 5, 6) | 6, 8, 9, 12 |
| 5. Threshold, gate, inverse-variance blend, honest σ | §8–§9 (σ vs σ²; (14, 3)) | Steps 7–9 (TODO 7, 8) | 10, 11, 12, 13 |

## Answer key (recomputed on the Jetson, OpenCV 4.11, numpy 1.26, torch 2.8, 2026-10-14)

Data: `solutions/24-visual-odometry/make_dataset.py` (orthos cached in ~/.cache/navera-academy/24; ≈ 4 min from scratch,
of which ≈ 100 s for the 3 600 px flight ortho). Hidden defects of the flight: barometer 3 % low (116.4 m for 120 m),
IMU heading +2.0° (± 0.05°), a telemetry overlay on frames 80–87, the sea redrawn in every frame (moving water).
Expected values in check.py: `solutions/24-visual-odometry/check_values.py`.

- **Step 0:** SLIDE_PX = 20 / (2 · 116.38 · tan 35° / 320) = **39.3 px** (accepted 37.5–40.5; 38.1 with the true 120 m).
  The measured slide is 38.0 px: lab Step 1 now asks the student to compare dy with SLIDE_PX (3 % apart) and keep the
  thought for Step 4 — the barometer is discovered, not announced.
- **Step 1 (`pair 10`):** yours (+0.018, +38.024) px, response 0.251; OpenCV (+0.005, +38.094), response 0.921; the drone
  moved (+14.85, +12.46) m against the truth (+14.86, +13.38).
- **Step 2 (`compare`, 51 steps):** mean |yours − OpenCV| **0.061 px**, largest 0.151 px (step 21); responses yours median
  0.243 (0.040–0.379), OpenCV's 0.889; ≈ 17 ms against 8 ms per step on a quiet Jetson (both double when it is busy).
- **Step 4 (`leg`, 1 020 m):** barometer: final error 47.22 m, **DRIFT_BARO = 4.63**, **SCALE_RATIO = 1.032**,
  **HEADING_ERROR_DEG = 2.01** (clockwise); **TRUE_ALT_M ≈ 120.1** (116.4 × 1.032; accepted 119.1–121.1);
  `--altitude 120` → **3.51**; `--altitude 120 --heading-offset -2` → **0.07** (accepted 0–0.3). Expected by the error
  budget: 3 % and 100 · sin 2° = 3.5 m → √(3² + 3.5²) = 4.6 m per 100 m.
- **Step 5 (`odometers`, 8 pairs per group, right = within 1 px; median error px; reference weights 2026-10-14):**
  TURN_LIMIT_DEG = asin(1/160) = **0.358°** (accepted 0.30–0.40; 20.5 = radians not converted, named by the check).

  | group | phase | phase+IMU | OpenCV+IMU | ORB+IMU | learned+IMU | ORB fit | learned fit |
  |---|---|---|---|---|---|---|---|
  | straight | 8 (0.08) | 8 (0.08) | 8 (0.19) | 8 (0.30) | 8 (0.09) | 8 (0.06) | 8 (0.06) |
  | turn4 | **1** (3.34) | 8 (0.08) | 8 (0.12) | 8 (0.15) | 8 (0.06) | 8 (0.10) | 8 (0.07) |
  | turn12 | 0 (27.8) | 8 (0.09) | 8 (0.11) | 8 (0.19) | 8 (0.13) | 8 (0.07) | 8 (0.11) |
  | turn30 | 0 (62.5) | 8 (0.07) | 8 (0.10) | 8 (0.28) | 8 (0.13) | 8 (0.16) | 8 (0.26) |
  | coast | 2 (1.21) | 6 (0.26) | 8 (0.24) | **4** (71.7) | 4 (55.4) | 2 (80.7) | 3 (—) |
  | sea | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

  Mean mutual matches: ORB ≈ 254–266 on the city, **6** on the coast, 3 at sea; learned fit (no IMU) **208** straight →
  198 (4°) → 174 (12°) → **114** (30°), learned+IMU 198 at 30° (weights eca2b40): past PatchNet's ±20° training range it loses about 40 % of its matches (RANSAC still
  copes). ms/pair (GPU, loaded Jetson): phase 17–19, OpenCV 6, ORB 16–17, learned 150–165; on the CPU learned ≈ 3–4 s
  per pair (the whole command ≈ 6 min). OK_PHASE_TURN4 = 1, **OK_ORB_COAST = 4**, LEARNED_IMU_TURN30 = 198,
  LEARNED_MATCHES_TURN30 = 114 (review round 2): the runner saves out/odometers.json and the check compares the copied
  numbers with the student's own run (±1; a swapped column is named). The learned pair isolates rotation from overlap:
  the same frames with and without derotation (a straight-vs-30° comparison could never fail: any turn lowers the overlap,
  ORB+IMU 266 → 254). A network that keeps its matches without the IMU (≥ 90 % of the derotated count, e.g. rot90
  augmentation from mission 21's Going further) is accepted when EXPLAIN_ODOMETERS says what was trained differently.
  Coast, the window: pair 43 fails only with the numpy Hann product (10.3 px off); OpenCV's √ window keeps the border
  texture (0.5 px) — the reason for OpenCV+IMU 8/8 against phase+IMU 6/8; a Going-further task. cv2.phaseCorrelate with
  a window overwrites its inputs (OpenCV 4.11, verified): opencv_shift copies via to_gray32. (NAVERA builds fresh arrays
  before its call, so this is not a product problem.) The coast group (pairs 40–47) was chosen by texture
  only (35–65 % water, < 40 ORB corners in the clean frame), never by any odometer's result.
- **Step 6 (`drift_sim.py`):** after 100 steps random 5.03 m (theory 5.00), bias 10.00 (10.00), both 11.22 (11.18);
  **EXPONENT_RANDOM = 0.50**, **EXPONENT_BIAS = 1.00**; PREDICT_GROWTH (the Monte-Carlo error, not in the lesson): ≈ 0.6 % in
  drift_sim's table (5.03 m), 2.2 % for simulate_drift(100, 0.5, 0) alone, spread over seeds about ±1.6 %
  (1/√(2·2000)); ∝ 1/√trials, so 200 flights ≈ √10 ≈ 3× wider (the lab's 20-seed command prints std 4.6 % against 1.8 %: ratio ≈ 2.5, theory 3.2); **N_CROSS = σ²/b² = 25** (5 or 50 named by the check).
- **Step 7 (`responses`, 89 steps):** right steps' lowest responses 0.040 (step 51, coast), 0.051 (78), 0.092 (79),
  0.111 (80); wrong steps: 26 over the water and the coast approach (steps 52–77, 0.020–**0.030**), and the 7 overlay
  steps 81–87 (0.288–0.465). **SEA_MAX_RESPONSE = 0.030**; **MIN_RESPONSE** in (0.030, 0.040] (check: 0.0305–0.0401, the failure names step 51 / steps 66 and 77; the window is knife-edge by design and the lab
  now says so;
  the solution uses 0.035). Any threshold ≥ 0.1 is named by the check (it refuses right steps and still misses the
  overlay).
- **Step 9 (`fuse`, σ model 0.3 m / 0.7 m, gate 3 × 2 m/s):**

  | stage | weak | gate | worst | final | within 2σ |
  |---|---|---|---|---|---|
  | A every step | 0 | 0 | 570.1 m | 570.1 m | 58 % |
  | B + threshold | 26 | 0 | 159.0 m | 159.0 m | 92 % |
  | C + gate | 26 | 7 | **52.6 m** | 39.0 m | 100 % |
  | D + map fixes | 26 | 7 | **18.9 m** | 5.3 m | **78 %** |

  GATE_REFUSED = **7** (steps 81–87). Coverage story (review round 1, data NOT re-seeded): the misses are frames
  **20–39 only**, right after the fixes at 20 and 30, which are 7.0 and 6.5 m from the truth against a stated σ of 4 m per
  axis (the generator draws σ = 3 m: 2.3σ draws for it, 1.7σ per axis against the stated 4 m; right after a fix the
  stated 2σ is ≈ 7.1 m and both fixes are 6.5–7 m off to the south, so the track sits on the band's edge). `--bias 0.9` → 85 % removes only the late-tooth misses
  (20–25 and 30–36 remain). Frames are correlated (about 7 fix intervals), so 78 % against 86 % is weak evidence. Do not
  teach "the bias 0.7 is too small, so σ is optimistic": 0.92 m per step is a total length, 0.7 m is per axis.
- **Unseen-flight check (5):** 12 steps, 18 m/s, 90 m high, 5 × 6° turn: reference largest error 0.13 m (pass < 0.6 m).

## Rubrics (EXPLAIN items; the check only catches empty or off-topic answers)

| Item | 2 (good) | 1 (partial) | 0 |
|---|---|---|---|
| EXPLAIN_SUBPIXEL | same integer peak; parabola vs centroid and a different window (OpenCV's is √(hann·hann)); differences < 0.2 px | "rounding" without naming the refinement | "OpenCV is better" |
| EXPLAIN_BIAS | height 3 % → scale; heading 2° → direction; same error every step, adds linearly | one cause | "noise" |
| EXPLAIN_ODOMETERS | translation only → derotate with the IMU; coast: phase uses every pixel, ORB starves (≈ 6 matches); PatchNet ≈ 10× slower and loses half its matches past ±20° without the IMU | two of three | "learned is best" |
| EXPLAIN_THRESHOLD | moving water: no common motion, flat surface; overlay: static, high peak at zero → threshold blind; margin only 0.01 → not safe alone | two of three | "the sea is dark" |
| EXPLAIN_FUSION (typical weak answer: "78 % is near 86 %, σ is fine" with no one-flight caveat → 1) | fix pulls back (saw-tooth); worst at the end of the sea gap; misses right after fixes 20 and 30 (7.0 / 6.5 m off) → the fixes' stated σ, not only the VO bias, decides coverage; one correlated flight is a hint | three of four | "σ is dishonest" with no evidence |

## Difficulties expected (not yet seen with simulated students — to be filled after the review rounds)

- TODO 1 is long: row/column order, the conj order and the negative-shift rule produce the runner's named symptoms
  (verified with mutants: 75 instead of −5; (2, −5); (5, −2); response 55.8 without normalisation).
- The sub-pixel neighbours at the edge (`% w`) are forgotten by many; only matters for shifts near 0 or W/2.
- Step 4: the sign of `--heading-offset` (the steps point clockwise → subtract). The runner's wording "your steps point
  2.01° clockwise of the true ones" was checked against the hidden +2° IMU bias.
- Step 7: students look for one threshold that removes every wrong step; the point is that it cannot.
- Weak students: the 🧰 boxes cover fft2/unravel_index, cumsum, median/hypot, rng/cumsum/RMS. Strong students: Going
  further (on-line calibration from fixes, NAVERA's high-pass).

## Class plan

Session 1 (3 h): 10 min Step 0 + hook; 50 min Part A §1–§3 with the ✏️ checks; 60 min TODO 1 (circulate: print r.shape,
argmax); 20 min Steps 2–3; 20 min Step 4 (whole-class discussion: which height makes k = 1?); 20 min Step 5 race and
the fair-race box. Session 2 (2 h 30): 40 min Part B; 30 min Step 6; 20 min Step 7 (vote on thresholds); 30 min
Steps 8–9; 20 min report. Differentiation: fast students do "calibrate on the fly"; struggling students may skip the
`--bias` question and Going further.

## NAVERA facts used (words and numbers only)

From docs/VALIDATION_STATUS.md (3 Oct 2026) and ARCHITECTURE.md: dead reckoning along the measured track (20 s fit,
turned by the IMU heading change, PROPAGATED, σ growth velocity error × t + 5° × distance, ≤ 120 s / stated σ ≤ 500 m), simulator:
land median 10 m / max 33 m; bay 90 s at ±300 m, true error ≤ 146 m; not measured with real camera/IMU; never a GPS
check; Release 0.2. Frame odometry described in words from the product's design (checked against base/, not copied):
derotation by the IMU heading change and rescaling by the height change, OpenCV phase correlation at half resolution on a
high-passed frame, refused below a response of 0.15 or beyond a quarter-frame shift, optional prediction shift; "cannot
work over open water". No frame-odometry accuracy is published: the lesson says so.

## Deviations from the design (§3 row 24)

- No `reference_steps.csv` in datasets/: it would publish the outputs of the graded function on the lab flight (students
  read datasets/). The oracle is OpenCV (`compare`, live) and the exact truth; the race is against other odometers.
- `navera_nav.py` became the runner's `fuse` command (stages A–D) using the student's `blend`, `vo_gate`, `drift_sigma`.
- Frames are heading-up with turns (not north-up): derotation by the IMU is part of the lesson, as in the product.
- `frame_m_per_px` is mission 18's `camera.gsd` (same function, given finished).
