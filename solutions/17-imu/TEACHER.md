# Mission 17 — teacher notes (The IMU: attitude from a gyroscope, gravity and a compass)

Teacher only. Rebuilt 2026-10-13 on NAVERA Lite: `navera_lite/imu.py`, reference in
`solutions/_navera_lite/navera_lite/imu.py`, tags `# @part 17 todo 1–7` (integrate_gyro, tilt_from_accel,
complementary, mag_heading, true_heading, q_true_north, StaleDetector.update); given: `G_MPS2`,
`declination_deg` (WMM2025 through pygeomag, installed in the sandbox), `StaleDetector` and its `__init__`.
`rotations.py` (16) ships finished with `tests/test_rotations.py`. This is the SECOND HALF of the old
mission 16 (rotations are mission 16 now). No NAVERA code: the old "compare with NAVERA's orientation
code/tests" is replaced by SciPy's `Rotation` (check oracle) and the course reference's outputs on hidden
inputs (`courses/17-imu/hidden/expected.json`).

Regenerate (from the repository root, on the host):
- `python3 tools/lite_build.py 17-imu` — starter + solution of the part;
- `python3 solutions/17-imu/make_dataset.py` — `datasets/17-imu/` (seed 1717: imu_log.csv, imu_log_meta.json,
  imu_frozen.csv, README.md). The generator lives HERE, never in datasets/ (students can read datasets/);
- `python3 solutions/17-imu/make_expected.py` — `courses/17-imu/hidden/expected.json` (seed 1771, the
  complementary filter's unseen inputs and the reference's outputs);
- `python3 solutions/17-imu/make_figures.py` — the six SVGs in `courses/17-imu/assets/`.
If you regenerate the dataset with other parameters, every number below and the constants at the top of
check.py change: recompute them with `run_imu.py` on the solution (see "How the numbers were made").

## The data (simulated, chosen for teaching)

5-minute multirotor flight near Monastir (35.76 N, 10.75 E, 15 Oct 2026 = 2026.79), 50 Hz, 15 001 rows.
Pad 0–10 s (still, heading 30°), speed-up 10–20 s to 10 m/s, four coordinated turns (30–40 s, 90–110 s,
160–170 s, 230–250 s; banks ≈ 15°), slow-down 280–290 s. Attitude physics: bank = atan(v·ψ̇/g), pitch =
4°·(v/10) nose down + atan(a_along/g), a wobble of 1° roll / 0.8° pitch only in flight; the accelerometer
reads Rᵀ(a + g·up), so it sees "level" in turns and in speed changes. Sensor errors: gyro bias
(0.05, −0.04, 0.10) °/s, gyro noise 0.003 rad/s per sample, accelerometer noise 0.3 m/s², magnetometer noise
0.4 µT (field = WMM at the place, D = +3.348°, I = 50.5°, F = 44.4 µT), chip quaternion = truth in a
MAGNETIC-north frame + 0.2° noise, w ≥ 0. The meta file gives place, date, rate, units — NOT the sensor
errors (students measure the bias). `imu_frozen.csv`: 20 s still on the pad, heading 75°; read hiccup = 10
repeats of the 4.98 s sample (t = 5.00–5.18); frozen from 12.36 s (last fresh sample 12.34 s).

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 integrate a gyro, predict drift from its bias, measure the bias | §1 models, §2 worked step, drift figure, ✏️ phone gyro | Step 0, Step 1 (pad bias), Step 2 (TODO 1, gyro, gyro BX BY BZ) | 1, 3 |
| 2 tilt from gravity, when it fails | §1 specific force + forces figure, §3 worked example, coordinated turn, ✏️ car | Step 3 (TODO 2, tilt, PREDICT_SPEEDUP) | 2, 4 |
| 3 complementary filter, choose τ | §4 1-D worked example, b·τ, memory of fooled gravity, 3-D nudge figure, ✏️ τ = 5 s | Step 4 (TODO 3, tau sweep, the engineer role) | 5, 6, 12 |
| 4 magnetic → true heading, whole attitude | §5 FLU atan2, tilt compensation worked example (348.1°), WMM table, London 212 m, q_true_north | Steps 5–6 (TODO 4–6, compass, Cape Town) | 7, 8, 9, 12 |
| 5 detect a frozen sensor, choose N | §6 + cold-open figure (IMU-1), probability of a repeat, 🧰 class | Step 7 (TODO 7, stale, stale 5) | 10, 11, 12 |

Badges: **Drift hunter** = checks 1–4 (session 1), **Attitude engineer** = all 12.

## Answer key

| Item | Value (check tolerance) | Where it comes from |
|---|---|---|
| PREDICT_REST (ungraded) | +9.81 (the table pushes up; specific force) | lesson §1 |
| GYRO_BIAS_DEG_S | (0.0636, −0.0321, 0.0946) °/s (± 0.0012 each) | mean of gx, gy, gz for t_s < 10 (500 samples), np.degrees. True biases (0.05, −0.04, 0.10): the 500-sample mean is off by up to 1.8σ (σ_mean = 0.0077 °/s), as the lesson predicts |
| DRIFT_FORECAST_DEG | 28.4 (± 0.5 around 300 × the student's own z bias, sign free) | 0.0946 × 300 |
| PREDICT_DRIFT_SIGN (ungraded) | negative: + z rate = turn left, yaw grows, heading = 90° − yaw shrinks | |
| GYRO_HEADING_ERR_DEG | −28.42 (± 0.15) | `run_imu.py gyro`, t = 300 (10 s: −0.94, 60 s: −5.75, 150 s: −13.65) |
| CORRECTED_HEADING_ERR_DEG | −1.75 (± 0.35: rounding of the typed bias) | `run_imu.py gyro 0.0636 -0.0321 0.0946`; 60 s −0.23, 150 s −0.58 |
| PREDICT_SPEEDUP (ungraded) | less nose-down: the accelerometer misses the atan(a/g) part | `tilt`: at 16.0 s true pitch_up −11.8°, accelerometer −3.1°; slowing at 285.3 s: +7.1° vs −2.1° |
| TURN_TRUE_BANK_DEG | 15.1 (± 0.15) | `tilt`, turn at 99.8 s (others: 35.6 s +14.4/+0.4, 165.4 s −14.7/−0.7, 239.8 s +15.1/+0.4) |
| TURN_ACCEL_ROLL_DEG | 0.9 (± 0.15) | 1-s average at 99.8 s. Whole flight, single samples: roll RMS 4.85°, pitch_up RMS 2.42° |
| TRACE_FIRST_ROLL_DEG | 7.5 (± 0.1; 22.5 = α swapped, own message) | α = 1.5/2.0 = 0.75, gravity's share 0.25 × 30° (lesson §4 'one gravity step' works the same method on other numbers: 20°, τ 1 s, dt 0.25 s → α 0.8 → 4°) |
| PREDICT_TAU (ungraded) | any | |
| BEST_TAU_S | 30 (exactly, one of the sweep) | `tau`: tilt RMS 4.82 / 4.63 / 3.92 / 2.56 / **1.85** / 2.26 / 2.67° for τ = 0.3 … 300 s; roll RMS best at 30 s (0.99°), pitch_up RMS best at 30 s too (1.56°; 100 s is close: 1.58°); the pitch curve is flat from 30 to 300 s because the speed changes fool it far less than the turns fool the roll. Why the large-τ end is gentle (2.67° at 300 s while b·τ = 0.064 × 300 ≈ 19°): the body-axis bias turns with the drone and reverses at every 180° turn, and with τ = 300 s nothing settles in 5 min (lesson §4 'b·τ is a worst case', lab 'Check one number'). Wrong start (`tau 10`, Going further, ungraded): tilt RMS 4.82 / 4.65 / 3.99 / **2.96** / 3.20 / 5.22 / 7.63° — the best moves to 10 s, the large-τ end pays for forgetting slowly |
| BEST_TILT_RMS_DEG | 1.85 (± 0.03) | worst tilt at 30 s: 3.07° |
| DECLINATION_DEG | 3.348 (± 0.02) | WMM2025 at (35.76, 10.75), 2026.79 |
| COMPASS_NO_TILT_RMS_DEG | 4.98 (± 0.05) | true-heading RMS, no compensation (mean +0.31°) |
| COMPASS_TILT_RMS_DEG | 0.81 (± 0.05) | true tilt (mean +0.01°). Accelerometer tilt: 4.37° (named mistake); filter tilt τ = 30 s (`compass 30`): 1.57° |
| CAPE_TOWN_SIDE_M | 2254.5 (± 10) | D = −26.80°; 5000·sin 26.80°. tan (2525 m) is refused with a message |
| CHIP_MEAN_ERR_DEG | −3.35 (± 0.05) | chip as delivered: mean −3.35°, RMS 3.36°; after q_true_north −0.00°, RMS 0.20° (a right-multiplying version gives almost the same on this flight: roll RMS 0.32° vs 0.20°, the reason the check uses large tilts) |
| PREDICT_STALE (ungraded) | the surprise: a false alarm at the 5 s hiccup | |
| FROZEN_T_S | 13.34 (± 0.011) | `stale`: 50th repeat of the 12.34 s sample; 334 samples flagged |
| SMALL_N_T_S | 5.08 (± 0.011) | `stale 5`: the hiccup (10 repeats) trips it; with 10: 5.18; with 11: 12.56 |

Lesson numbers (recomputed with the reference and `make_figures.py`; scripts kept in
~/academy-test/review/17-imu/build/lesson_numbers.py): §1 nose down 10° → (−1.70, 0, 9.66); hover = table;
climb 2 m/s² → 11.81. §2 step: Δq = (0, 0, −0.0035, 1.0000), q ⊗ Δq = (0, 0, 0.7046, 0.7096), heading 0.40°,
after 1 s 20.05°; 0.01 °/s → 6° in 600 s; noise 0.003 rad/s at 50 Hz → 0.60° (1σ) at 600 s; equal after
5.9 s; 0.172/√500 = 0.0077 °/s; ✏️ 20 s and 0.0045 °/s. §3 worked: roll 3.08°, pitch 9.98°; turn 12 m/s at
20°/s: v·ω = 4.19 m/s², bank 23.1°, |f| = 10.67; car −11.5°; noise 1.75°. §4: α = 0.9804, 0.196°/step,
6.28° after 1 s (63 %), b·τ; 23° turn of 12 s: τ = 1 s → 23.0°, τ = 30 s → 7.6°; ✏️ α = 0.9960, 1.0°, 12°.
Complementary figure (1-D, bias 0.1 °/s): τ = 30 s peaks at 9.1° (7.6° + bias) and keeps b·τ = 3°. §5:
Monastir H 28.25, Z 34.30, F 44.4 µT, I 50.5°; nose north, 10° bank: body (28.24, −5.95, −33.74) µT (from the rounded F 44.4, I 50.5°),
uncompensated 348.1°; table D/I from pygeomag 2026.79 (London +1.21/66.5, Reykjavik −11.05/75.4, Sydney
+12.83/−64.4, Singapore +0.24/−12.9, Sousse +3.34/50.6); London 10 km → 212 m; ✏️ Sydney 11.83°, chip 75° →
78.34° (Sousse's table D 3.34°). §6: one gyro axis quantised at 0.002 rad/s, σ 0.003: P(repeat) = Δ/(2σ√π) = 0.19; accelerometer
(0.004 m/s², σ 0.3) 0.0038; magnetometer (0.06 µT, σ 0.4) 0.042; all nine at once 2.7·10⁻¹⁴ (≈ 1 in 4·10¹³).
The steps are the BNO085's output resolution (1/512 rad/s, 1/256 m/s², 1/16 µT, rounded); the lab's log is written with more digits, so it never repeats (0 % per gyro axis) — the lesson now says so.

**NAVERA facts used** (VALIDATION_STATUS.md Release 0.2 of 2026-10-03; ENGINEERING_BACKLOG.md from the
2026-09-28 review; ARCHITECTURE.md; base code read only to check the frozen rule and the 20 km
recompute): BNO085 on I²C bus 1 at 50 Hz, verified live 2026-07-13, heading reference and noise not yet
checked (covariances datasheet values); fusion on the chip; inertial navigation not implemented; IMU-1
(H) fixed — frozen after 50 identical samples (1 s), not published, chip re-initialised; IMU-2 (M) fixed;
IMU-3 (M, 🔧) WMM2025 declination at the vehicle position, recomputed ~every 20 km, before a position: the
operator's declination_deg parameter if set, else magnetic (and logged), mounting roll/pitch/yaw, to confirm on the chip with a known heading; straightening offline 33/33
within 2.6 m (median 1.1 m) with IMU bias 0.3°/1.5° vs median 28 m unstraightened; celestial ~111 km per
degree, 5.5–6.5 km perfect attitude, 24–119 km BNO085-class (simulated star fields); 150 m · tan 10° = 26 m.

## Rubric for written answers (the check only verifies "written and on topic")

| Item | 2 — good | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_DRIFT | sign: + z rate = left turn → yaw grows → heading (90° − yaw) falls; residual = error of the 500-sample mean × t (+ random walk), why not zero | one of the two | "the gyro is broken" |
| EXPLAIN_TURN | the accelerometer feels thrust (specific force), which stays along body z; the banked turn makes f point along body z as when level → roll ≈ 0 | "acceleration confuses it" without the direction | |
| EXPLAIN_TAU | small τ: follows the fooled, noisy gravity (turn errors, 4.8°); large τ: keeps b·τ and recovers slowly (2.7° at 300 s); best = the measured compromise; it depends on this flight | one end only | |
| EXPLAIN_COMPASS | inclination 50.5°: the large vertical part Z leaks into body x/y when tilted; compensation removes roll and pitch first | "tilt changes the reading" | |
| EXPLAIN_NORTH | chip references magnetic north, D = +3.35° east → its heading is too small by D; the correction turns the world frame (left); right = about the body's up axis, same only when level | two of three | |
| EXPLAIN_STALE | noise changes ≥ 1 digit each sample (whole 9-number sample never repeats); stamps say when sent, not when measured; N trades false alarms (hiccup at 5 s with N = 5) against delay (1 s with 50) | two of three | |
| report.md | three sections with the numbers (bias, drift, τ = 30 s with 1.85°, D 3.35°, 4.98 → 0.81°, 13.34 s), an engineering choice and its limits (one simulated flight) | numbers without reasons | |

## Round 1 fixes (2026-10-13)

Reviews r1_{strong,weak,expert}.md: see ~/academy-test/review/17-imu/reports/r1_fixes.md. EXPLAIN_ keyword groups
tightened with the expert's lists (the six shallow answers of the expert now each fail; the solution passes);
EXPLAIN_TAU now asks "why is the best τ in between"; complementary must skip |f| = 0 and a zero axis (runner and
check test both); TRACE_FIRST_ROLL_DEG added; sin(error) and first-order-update variants get their own messages.

## Round 2 fixes (2026-10-13)

r2_fixes.md: first-order update named in all three `test` lines of TODO 1 (yaw 0.6828 in the uneven case); `tau 10` saves
out/tau_wrong_start.png; §5 worked vector (28.24, −5.95, −33.74) from the rounded F/I; keyword groups widened with
the weak student's correct phrasings (the expert's shallow answers still fail) and every "does not explain" message
carries an example phrase; lesson §4 worked gravity step now 20°, τ = 1 s, dt = 0.25 s → α 0.8, roll 0° → 4° (the
lab's trace keeps 30°/1.5 s/0.5 s → 7.5°, so it is a transfer, not a copy); COMPASS RMS: the LEFT (magnetic) column
5.83 / 3.44 has its own message.

## Mutants run (round 0: 32; all caught — the ✘ line of the check, and the runner's `test` line when it applies)

Check messages (sealed run with `tools/try_lesson.py 17-imu --solution --overlay`): integrate on the left
("multiplies on the LEFT (world axes)…"); rate of sample k ("you used the rate of sample k…"); no zero-rate
guard ("ValueError: the rotation axis must not be zero … skip the turn"); constant dt ("dt changes from step
to step…"); tilt pitch sign ("wrong sign: … nose DOWN"); pitch with az only ("the pitch uses only az…");
math.atan2 on arrays ("TypeError: only length-1 arrays … use np.arctan2"); degrees ("these are degrees");
complementary α swapped ("tilt jumped almost all the way: α and 1 − α are swapped"); axis reversed ("tilts
the drone AWAY from what gravity says"); nudge on the right ("wrong direction when the heading is not 90°: …
on the LEFT"); Euler-angle blend ("the tilt is right but the attitude is turned about the vertical … not a
blend of Euler angles"); gravity of sample k−1 ("on a bumpy unseen flight … row 6 is 1.47° from the right
one … gravity uses the force of sample k"); mag atan2(−y, x) ("mirror image"); no tilt compensation ("there
is no tilt compensation"); Rx·Ry order ("the two turns are in the wrong order"); no % 360 ("a heading is in
[0, 360)"); true = mag − D ("subtracts the declination"); q_true_north on the right ("multiplies on the
RIGHT"), in degrees ("D is in degrees"), +D ("turns the wrong way"); StaleDetector `>` ("one sample too
late"), no reset, latched, first number only ("after a frozen run, a DIFFERENT sample … must give False");
answers: bias in rad/s, heading error sign, BEST_TAU 100, COMPASS_TILT from the accelerometer line, Cape Town
with tan, FROZEN_T_S = freeze start, turn numbers swapped — each with its own message. Runner `test` names
the same mistakes for the function mutants (except the gravity-of-sample-k−1 and Euler-blend variants, which
the docstring cases cannot see; the check does). Overlays: ~/academy-test/review/17-imu/build/mutants/.

## Difficulties to expect (not yet seen with simulated students — to confirm in the pilot)

- Left vs right multiplication appears three times (gyro: right; gravity nudge and declination: left). The
  retrieval question 2 and the three ✘ messages carry it; spend 5 minutes on the board with a book.
- The sign of the drift (positive bias, negative heading error): expected confusion; hint 6 of Step 2.
- `math.atan2` on columns (TypeError): the 🧰 box of §3 and the runner message.
- TODO 3 is the longest (≈ 15 lines): weak students need hints 1–4; pair them. The check names each of the
  five typical mistakes.
- Students may take the accelerometer-tilt line for COMPASS_TILT_RMS_DEG: named by the check.

## Class plan (2 × 2 h + reading)

Session 1: 10 min Step 0 (vote: 0 / +9.81 / −9.81, then the spring-and-table explanation); 20 min §2 drift
on the board (b·t vs √t); 30 min Step 1–2 (pad bias, TODO 1, forecast vs measure); 15 min §3 coordinated
turn with a cup of water on a tray; 25 min TODO 2 + tilt; badge.
Session 2: 15 min §4 1-D filter by hand (two steps), then the 3-D nudge figure; 45 min TODO 3 + τ sweep
(each pair defends a τ in one sentence); 30 min compass + true north (TODO 4–6, Cape Town); 20 min IMU-1
story, TODO 7, stale/stale 5; memo as homework.
Differentiation: fast — Going further (heading filter, gating, hard iron); struggling — give Step 4 hints
1–3 orally, skip Cape Town (one line) if short of time, pair for TODO 3.

## How the numbers were made

Run on the host from a copy of the lesson folder with the solution:
`IMU_DATA=datasets/17-imu python3 run_imu.py <mode>` (the env var points the runner at the repository's
dataset; in the sandbox it reads /data/academy/17-imu). Check constants were pasted from those runs.

## Notes for the lead

- `datasets/17-imu/make_dataset.py` was removed from datasets/ (the generator is `solutions/17-imu/make_dataset.py`);
  datasets/17-imu holds outputs + a neutral README only. The meta file no longer lists the sensor errors.
- Old files removed: courses/17-imu/files/{quaternions.py, imu_filters.py}, solutions/17-imu/{quaternions.py,
  imu_filters.py}, the old assets (rpy/slerp/tilt/north/…).
