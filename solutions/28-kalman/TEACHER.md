# Mission 28 — teacher notes (The Kalman filter: predict, update, and stay honest)

Teacher only. Rebuilt 2026-10-14 on NAVERA Lite: `navera_lite/kalman.py`, reference in
`solutions/_navera_lite/navera_lite/kalman.py`, tags `# @part 28 todo 1–5, 7` (cv_model, kf_predict, kf_update,
Height1D.update, nees, run_filter); given: `Height1D.__init__`, `gate_threshold` (closed-form χ²₂ quantile).
TODO 6 `nees_band` lives in the lesson folder's `band_sim.py` (an experiment, not a part). No other part is
needed (no dependency on mission 27's `uncertainty.py`, rebuilt in parallel). This is the SECOND HALF of the old
mission 26 (covariance/gating/fusion is mission 27 now). No NAVERA code, no NAVERA file: the old lab imported
NAVERA's own day-vision class to race against; now the race target is `reference_heights.csv`, made by the course's
own `Height1D`, and the model is described **in words** as the height filter in NAVERA's day-vision code (it exists
there with unit tests, but the running system does not fly on it: see the NAVERA facts below).

Regenerate (from the repository root, on the host):
- `python3 tools/lite_build.py 28-kalman` — starter + solution of the part;
- `python3 solutions/28-kalman/make_dataset.py` — `datasets/28-kalman/` (seeds 2834 track, 2829 heights; the
  generator lives HERE, never in datasets/);
- `python3 solutions/28-kalman/make_expected.py` — `courses/28-kalman/hidden/expected.json`: unseen inputs and the
  reference outputs for TODOs 1–5 and 7 (seed 2830/2831), reference NEES bands from 200 000 flights, and every lab
  number read back from `run_kalman.py`'s own functions run on the reference;
- `python3 solutions/28-kalman/make_figures.py` — the five SVGs in `courses/28-kalman/assets/`.

## The data (`/data/academy/28-kalman/`, SIMULATED)

- `heights.csv` (131 rows, t 1.06–149.65 s): truth 80 m → climb to 140 m (20–60 s, cosine profile, peak
  acceleration 0.185 m/s²) → hold → descent to 100 m (100–125 s) → hold. Sources at random: baro σ 1.5 m,
  gps-ground σ 3 m, vision σ = 3 % of the height. Two gps-ground rows read 0.0 ("no reading", rows 24 and 63); one
  baro/gps-ground pair shares a time stamp.
- `reference_heights.csv`: the reference `Height1D()` (climb_accel 0.5) after each row (9 decimals).
- `track.csv` (361 s, dt 1 s): truth = constant velocity with random accelerations q_true = 0.3 m²/s⁴ (the exact
  discrete model of `cv_model`), start velocity (−12, +2) m/s; fixes truth + N(0, 5²); no fix t = 150–189 s; 6
  wrong fixes 80–200 m off at t = 37, 96, 121, 233, 271, 318 (the README does not say any of this; `run_kalman.py`
  finds wrong fixes as > 50 m from the truth).

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 predict/update by hand and in code; gain = blend | §1 random walk, worked 50/60 m (K 0.8, P 20 → 21), sawtooth figure, ✏️ R = 100; §3 matrices, worked [104.5, 2.0], update2d figure, ✏️ R = 1 | Steps 1–2 (TODO 1–3, grow, hand trace, step) | 1, 2, 3, 5 |
| 2 F, Q; meaning of q and R | §2 Q = q g gᵀ derived, worked P⁻ = [[9, 3], [3, 2]], ✏️; §4 R and q in numbers, q_tradeoff figure | Step 1 (grow), Step 4 (heights 0.05 / 5 / 0.5) | 1, 5, 6 |
| 3 reproduce a described filter | §4 "The race" (NAVERA's model in words), ✏️ start climb variance | Step 3 (TODO 4, race) | 4, 6 |
| 4 2-D tracker, gate, lock-out | §5 tracker, gate, worked 40 m (0.98 vs 12.8), gate figure, ✏️ the judge (6.2 / 53) | Steps 6–8 (TODO 7, track, gate, judge, sweep, lock-out) | 9, 10, 12, 13 |
| 5 NEES honesty by simulation; tune q | §6 NEES, band by simulation, ✏️ 0.5; §7 honest first | Step 5 (TODO 5–6, band_sim), Step 8 (sweep), Step 9 memo | 7, 8, 11, 13, 14 |

Badges: **Height keeper** = checks 1–6 (session 1), **Tracker** = all 14.

## Answer key (reference run, 2026-10-14)

| Item | Value (check tolerance) | Where it comes from |
|---|---|---|
| SIGMA_40S_M | 89.49 m (± 0.1) | `grow`: P0 diag(9, 9, 1, 1), q 0.3, 40 × 1 s (q = 0 would give 40.1 m; one 40 s step 440 m) |
| TRACE_HEIGHT_M / CLIMB / SIGMA | 124.8 m / 1.2 m/s / 1.789 m (± 0.01) | S = 20, K = [0.8, 0.2], P⁺ = [[3.2, 0.8], [0.8, 1.2]], nis 1.8 |
| RACE_RMSE_RAW_M / FILTER | 2.789 / 1.832 m (± 0.005) | `race` (129 usable heights); largest difference to the reference 5e-10 m |
| RMSE_CA_005_M / 5 | 3.098 / 2.510 m (± 0.01) | `heights 0.05` (climb 3.35 m, level 1.55 m — worse than raw), `heights 5` (level 2.21 m); 0.2 would give 1.75 m |
| BAND_LOW / HIGH | 1.80 / 2.21 (± 0.02) | `band_sim.py`, n 2, N 361, 4 000 flights, seed 0 (theory χ²₇₂₂/361: 1.80–2.21) |
| NEES_NO_GATE | 16.48 (± 0.1) | `track 0.3` |
| SIGMA_END_JAM_M / ERR_END_JAM_M | 91.7 m (± 0.2) / 103.2 m (101.2 with the gate accepted, ± 0.3) | `track 0.3` |
| NEES_GATE, WRONG_REFUSED, GOOD_REFUSED | 2.07 (± 0.02), 6, 5 | `track 0.3 0.99` (5 of 315 = 1.6 %, chance: expected ≈ 3) |
| D2_AFTER_JAM | 1.40 (1.46 without the gate accepted, ± 0.02) | `track 0.3 0.99`, t = 190 s |
| JUDGE_D2 / JUDGE_ACCEPT | 150²/(σ² + 25) from the student's σ: 2.67 / True | lesson §5 ✏️ method |
| Q_BEST | 0.3 | `sweep`: 0.01 / 0.03 LOST (RMS 307 / 572 m, NEES 57.5 / 11.8), 0.1 overconfident (5.17 m, 3.18), **0.3 honest (4.69 m, 2.07)**, 1 / 3 / 10 pessimistic (4.87 / 5.29 / 5.70 m, NEES 1.74 / 1.70 / 1.70) |
| report.md | headings, 150–420 words, 1.8x m and 2.7x m, 2.0x and the band, q = 0.3 | Step 9 |

Lesson numbers (all recomputed): §1 K 0.8, x 58, P 20 → 21; steady state σ 2.13 m, K 0.18 (✏️ R = 100: K 0.095);
§2 P⁻ [[9, 3], [3, 2]]; §3 S 18, K [0.5, 0.167], x [104.5, 2.0], P [[4.5, 1.5], [1.5, 1.5]], NIS 0.5 (✏️ R = 1:
K [0.9, 0.3], 105.7 m, +0.9 m/s); §4 R 2.25 / 12.96 m², √(10·0.25) = 1.6 m/s; §5 d² 0.98 / 12.8, ✏️ 6.2 / 53;
§6 0.05–7.38 (χ²₂ 2.5 / 97.5 %, from mission 27's closed form 1 − exp(−d²/2)); real band of the lab's tracker
(200 simulated flights, q 0.3, 99 % gate, `build/real_band.py`): 1.61–2.64 (q 1: 1.36–1.99, q 0.1: 2.45–14.1); NIS of
accepted fixes behind the 99 % gate 1.93, √(8/2) = 2, √(0.5/2) = 0.5; check-yourself Q = [[1, 2], [2, 4]], √(18/2) = 3.

## Rubric for the EXPLAIN items (the check only catches empty or off-topic answers — keyword groups)

| Item | 2 — complete | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_GROW | the velocity error × t (40 m) AND the random accelerations making the velocity error itself grow (variance ∝ t³) | one of the two | "it grows" |
| EXPLAIN_Q | small q: lags in the climb (worse than raw), states a small σ because it trusts the model (overconfident); large q: follows the noise in level flight | two of three | restates the numbers |
| EXPLAIN_GATE | 1 % of honest fixes refused by definition (≈ 3 of 315; 5 is chance); wrong fixes believed with a small P pull the estimate far, NEES explodes | one | "the gate works" |
| EXPLAIN_TUNE | σ too small during the jam (32 m vs 118 m true error) → first fix after it has d² 14.7 > 9.21 → refused → prediction drifts, next fix farther → every fix refused (lock-out, one form of divergence); 0.1 has NEES 3.2 far above the band: overconfident, honest first; + notes that q = 1 (1.74) is a hint, not a verdict (the iid band is ~2.5× too narrow, lesson §6) | two of three | "q too small" |

## Mutants run (wrong-but-plausible code; every one fails with its own message)

See `~/academy-test/review/28-kalman/build/run_mutants.py` (19 mutants, sealed check via
`tools/try_lesson.py 28-kalman --solution --overlay`) and `mutants/results.txt` for the full messages. All 19 are
caught; the build report lists each mutant's ✘ message.

## Difficulties expected

- Shapes: `H` must be 2-D (`[[1, 0]]`), z a 1-element array; lists have no `.T` (convert first). The runner and the
  check turn matmul errors into one sentence.
- `Height1D` is the first stateful method of this block; the 🧰 box shows the pattern. The race reports the first
  row where the outputs differ (a "no reading" row is flagged).
- `run_filter` is the least guided TODO; the hand trace (P[0][0] = 25 + 400 + 0.25 at k = 1) is the plan.
- `nees_band` with numpy axes: summing over the steps (band ≈ 722) and averaging over dimensions (band ≈ 1) are the
  two classic slips; both are named by the check, and band_sim.py itself warns when the one-step band is not χ²₂.
- Downstream checks (Height1D, run_filter) say when the real fault is in TODOs 1–3.
- Measured (round 1, weak persona): 7 h 35 in all; meta.json says 7 h, the lesson 6 h to 7 h 30.
- `nees_band` computed analytically (χ² quantiles) instead of simulated would pass the check (indistinguishable);
  objective 5 asks for the simulation — look at the code if in doubt.

## Class plan (2 sessions)

- Session 1 (2 h 30): 10 min Step 0 + hook (cold-open figure); 25 min §1–§3 on the board (the 50/60 m example, then
  the [103, 1.5] example with the tilted ellipse); students do Steps 1–2; 10 min §4 (q, R, the race in words); Steps
  3–4; badge.
- Session 2 (3 h): 15 min §5 gate figure + the judge ✏️; 15 min §6 (one step vs mean); Steps 5–7; 10 min §7 + run
  `track 0.03 0.99` on the projector (lock-out); Step 8; memo as homework.
- Fast students: Going further (one big step: 440 m vs 89 m; NIS in flight; Joseph form; a height gate).
  Struggling: give the Step 2 hand trace on the board; pair for TODO 7 with the trace.

## NAVERA facts quoted (words and numbers only; base/docs: VALIDATION_STATUS 2026-10-03, ARCHITECTURE, TROUBLESHOOTING, ARDUPILOT_INTEGRATION, backlog)

Long route (simulator, 2026-10-01): day vision over uniform terrain near Gabès, median 351 m, p90 853 m; forwarded
at ±300 m → ArduCopter EKF failsafe after 45 s; small map 61 s; ±500 m 91 s; with local feature matching 147
matches and the autopilot held 230 s (end of test). Mechanism: TROUBLESHOOTING.md's cause row "the EKF rejects
positions that jump more than it was told". ArduPilot's EKF3 uses at most 100 m whatever is stated
(ARDUPILOT_INTEGRATION §3, repeated in TROUBLESHOOTING). R-10: ±300 m stated vs 442 m measured median → default
500 m, warning below 450 m. Dead reckoning along the measured track (2026-10-02, simulator only): 20 s velocity fit,
IMU heading change, σ = velocity error × t + 5° × distance, max 120 s, σ capped at 500 m; land median 10 m, max
33 m; bay 90 s at ±300 m, true error ≤ 146 m. Vision carried to the present: 1.5 s at 40 m/s → 60 m, ±31.5 m.
Inertial navigation **not implemented** (the IMU gives attitude and heading changes; the arbiter watches the IMU
topic for liveness only); FEAT-2 (IMU dead-reckoning) open. The arbiter selects one source (no position filter).

The day-vision height filter (σ_a 0.5 m/s², P0 diag(σ², 4), match height 3 % / 5 % with few inliers, heights ≤ 0
ignored, no gate, dt clamped at 0 for a late height — the course raises ValueError instead, said as a course choice)
is not in the docs: it was checked by reading NAVERA's base code (facts only, nothing copied). It exists in day
vision's code (navigation helper, unit tests), but the running node in the base snapshot does not feed it: the
camera's height comes from the priority rule of ARCHITECTURE §"Height above ground" (rangefinder, else the matched
height carried by baro/GPS, else baro or GPS minus the ground). Do not tell students NAVERA flies on it.
Apollo / Schmidt / NASA TM-86847 (1985): public history.
