# Mission 27 — teacher notes (How sure are we? Covariance, gating and fusion)

Teacher only. Rebuilt 2026-10-14 on NAVERA Lite: `navera_lite/uncertainty.py`, reference in
`solutions/_navera_lite/navera_lite/uncertainty.py`, tags `# @part 27 todo 1–3, 5–9` (sample_cov, ellipse,
mahalanobis2, propagate, polar_to_en, gate, fuse, make_covariance); TODO 4 (`d2_samples`, the χ² simulation) is in
the lesson folder's `chi2_sim.py` (an experiment, not a part). Given in the part: `chi2_threshold` (closed forms for
1 and 2 degrees of freedom — no scipy in NAVERA Lite), `p_inside`, `ellipse_outline`. `estimate.py` (mission 12)
ships finished with its tests; `make_covariance` calls its `is_covariance`, the runner's `publish` uses `Estimate`,
`stated_sigma` and `classify` — never edited. This is the FIRST HALF of the old mission 26/27 ("uncertainty +
Kalman"); the Kalman filter, NEES and the height-filter race are mission 28 now. No NAVERA code, no NAVERA file:
the old version filled NAVERA's position message and called the product judge's private methods.

Regenerate (from the repository root, on the host):
- `python3 tools/lite_build.py 27-uncertainty` — starter + solution of the part;
- `python3 solutions/27-uncertainty/make_dataset.py --hidden` — `datasets/27-uncertainty/` (seed 2727) and
  `courses/27-uncertainty/hidden/drive.csv` (seed 2799, street at −25°). The generator lives HERE, never in datasets/
  (the old `datasets/27-uncertainty/make_dataset.py` was removed; heights.csv / track.csv / truth.json are mission
  28's and have their own copy in `datasets/28-kalman/`);
- `python3 solutions/27-uncertainty/make_expected.py` — `courses/27-uncertainty/hidden/expected.json`: unseen inputs
  and the reference's outputs for TODOs 1–3 and 5–9 (seed 2777 + edge cases), the reference "gate, then fuse" on
  the hidden drive, and every lab number read back from `run_uncertainty.py` run on the solution;
- `python3 solutions/27-uncertainty/make_figures.py` — the six SVGs in `courses/27-uncertainty/assets/`.
`solutions/_navera_lite/navera_lite/tests/test_uncertainty.py` (12 tests) exists for later missions (not shipped in
27: it would show the answers).

## The data (`/data/academy/27-uncertainty/`, all synthetic)

- `static_fixes.csv`: 600 fixes, one every 10 s, of a receiver on a surveyed pillar. True error: zero-mean Gaussian,
  long axis 3.4 m at −55° (NW–SE, "multipath from a warehouse wall"), short axis 1.5 m. Independent draws (the 10 s
  spacing is the story that justifies it; real GNSS errors are time-correlated over minutes — say so if asked).
- `judge.json`: prediction after 40 s on visual odometry, track bearing 120°: P_pred = σ 60 m along × 25 m across
  ([[2856.25, −1288.21], [−1288.21, 1368.75]] m²), GPS σ 3 m, a "never-grown" predictor diag(25, 25), a 160 m circle
  rule, six candidates: A = 150 m along (the truth in the story), B = 150 m across (a spoofer), C = −100 along + 20
  across, D = 400 m along, E = 15 along + 78 across (79.4 m), F = −90 along − 45 across.
- `fusion.csv`: 400 s at 10 m/s: open sky (GPS σ 3 m round), street canyon t 120–279 s at 40° from east (GPS long
  axis 18 → 34 → 18 m along the street, 6 m across, drawn from the stated covariance: an honest GPS), open sky. Day
  vision states 15 m, honest (N(0, 15²) per axis) except 24 wrong matches (120–400 m, random direction), flagged
  `vis_wrong` (used only for scoring).

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 covariance from a cloud, ellipse, what one σ misses | §1 (worked 4 points, ✏️ 3 points), §2 🧰 λ/θ formulas, worked [[12,5],[5,6]], √2 bound, ✏️ | Steps 0–2 (TODO 1–2, cloud) | 1, 2, 7 |
| 2 Mahalanobis d², the χ² law by simulation, Rayleigh | §3 worked d² = 8.17, simulation, table 1-D/2-D, Rayleigh + mission 11's parked car, ✏️ | Step 3 (TODO 3–4, cloud, chi2_sim) | 3, 4, 7 |
| 3 J P Jᵀ and its limits | §4 derivation, mission-11 difference, radar worked example, banana, ✏️ 500 m | Step 4 (TODO 5–6, radar, radar wide) | 5, 6, 8 |
| 4 gate and fuse, and their costs | §5 worked 80 m east / 40 m north, attacker √(χ²λ), lock-out; §6 information form, canyon worked example, three conditions, ✏️ | Steps 5–7 (TODO 7–8, judge, attack, fuse) | 9, 10, 12, 13 |
| 5 publish honestly | §7 type table, refuse impossible matrices, the judge's σ vs the long axis (20.2 m vs 28 m) | Step 8 (TODO 9, publish), Step 9 memo | 11, 14, 15 |

Badges: **Ellipse maker** = checks 1–8 (session 1), **Gatekeeper** = all 15.

## Answer key (reference run; check tolerances in brackets)

| Item | Value | Where it comes from |
|---|---|---|
| PREDICT_CLOUD (Step 1) | written: north worse, ρ < 0 (Step 2 shows ρ = −0.62) | `look`, `head` |
| ELLIPSE_A_M, _B_M, _ANGLE_DEG | 3.36, 1.53, −57.3 (± 0.02, 0.02, 0.5) | `cloud`; sample P = [[4.968, −4.071], [−4.071, 8.691]] |
| LONG_AXIS_BEARING_DEG | 147.3 (± 0.6; 327.3 refused with "[0, 180)"; not printed by the runner) | 90° − (−57.29°) |
| JUDGE_SIGMA_M | 2.95 (± 0.02) | √8.691 |
| INSIDE_1SIGMA_PCT | 38.5 (± 0.3) | `cloud` (2σ 87.5 %; theory 39.3 / 86.5 / 98.9) |
| INSIDE_3SIGMA_PCT, CIRCLE_3_PCT | 99.2, 98.8 (± 0.1 of 99.17, 98.83) | `cloud`: at k = 3 the circle (8.8 m) is shorter than the long axis (10.1 m) and loses; at k = 1 it holds 53.3 % |
| SIM_P95 | 6.03 with the reference `d2_samples` (accepted 5.6–6.4: other correct implementations draw other numbers) | `chi2_sim.py` (seed 27; 39.7 % ≤ 1, p99 9.48, mean 2.01) |
| RADAR_A_M, MC_A_M | 52.4, 52.2 (± 0.1) | `radar`: 3 000 m, 300°, σ 8 m / 1°; b 8.0 / 8.05; 94.9 % of draws inside the 95 % ellipse |
| WIDE_INSIDE_PCT | 46.7 (± 0.3) | `radar wide` (σβ 10°): J P Jᵀ a = 523.6, b = 8.0; draws a = 514.0, b = 64.2 |
| D2_A, N_ACCEPT_99 | 6.23 (± 0.02), 3 | `judge`: d² A 6.23, B 35.49, C 3.40, D 44.33, E 9.65, F 5.44; 99 % accepts A, C, F; 95 % C, F; never-grown refuses all; circle accepts all but D |
| PREDICT_ATTACK | written (by hand: √(9.21·3 609) = 182 m at 120°/300°, √(9.21·634) = 76 m at 30°/210°; the runner no longer prints the ellipse line) | |
| ATTACK_MAX_M, ATTACK_MIN_M | 182.3, 76.4 (± 0.3) | `attack`: at bearings 120° and 30° = √(9.21·3 609), √(9.21·634) |
| RMS_GPS_M, RMS_ALL_M, RMS_GATED_M | 19.0, 33.3, 12.1 (± 0.06 of 19.03, 33.35, 12.13) | `fuse` (p95: 43.8 / 26.2 / 24.8 m; vision alone RMS 75.6 m) |
| COVER_GATED_PCT, COVER_LIAR_PCT | 93.0, 75.5 (± 0.06) | `fuse` (GPS alone also 93.0 %: 400 draws, ± 1.1 % binomial) |
| LIAR_REFUSED | 159 | `fuse` (honest vision: 7 good refused = 1.9 %, 24/24 wrong caught) |
| STATED_SIGMA_M, WORST_SIGMA_M, FALSE_FIX_S | 22.8, 29.3 (± 0.06), 64 | `publish` at t = 160 s (GPS long axis 29.3 m at 40°); fused: 10.8 / 13.4 m |
| Hidden drive (check 13) | RMS 11.10 m, coverage 94.5 %, 30/30 wrong caught, 4 good refused | `make_expected.py` |

Lesson numbers (all recomputed by `~/academy-test/review/27-uncertainty/build/verify_lesson.py`, a copy of the
checks is in the build report): §1 [[10, 4.67], [4.67, 3.33]], ρ 0.81; ✏️ [[1, 0], [0, 3]]; §2 λ 14.83 / 3.17, a 3.85,
b 1.78, θ 29.5°, √12 = 3.46; ✏️ (4, 2, 45°), √10 = 3.16 (21 % short), (5, 2, 90°); §3 d² 8.17 and 12.26; shares
39.3 / 86.5 / 95 / 98.9 / 99 % and 68.3 / 95.4 / 98.6 / 99.7 / 99.8 %; Rayleigh 1.25σ / 1.18σ / 2.45σ; parked car
1.25 × 4.24 = 5.3 m/s; §4 [[94.9, −121.1], [−121.1, 234.7]], 17.5 m, 500 m → 4.4 m; §5 d² 3.98 / 14.7, 122 / 32 m,
✏️ 8.26, 98 m; §6 (24.0, 1.4), σ 13.4 × 5.6, outlier 240 m, d² 80 and 1.18, ✏️ 2.94 m; §7 a = c = 410 → 20.2 m.

## NAVERA facts used (words and numbers only; sources: base/docs, checked 2026-10-14)

- Brief: long route (VALIDATION_STATUS, "Long route (simulator, 2026-10-01)"): uniform terrain near Gabès, median
  351 m, p90 853 m, ±300 m → ArduCopter failsafe after 45 s, ±500 m → 91 s. QA campaign 2026-09-30 (backlog §7 QA-2):
  a ±55 km celestial fix reached the autopilot, its position jumped 125 km; backlog OUT-6: celestial ~55 km sent as
  300 m (the larger is now sent); `max_forward_sigma_m` 1 km. Backlog R-10 (review 2026-10-01): vision forwarded at
  ±300 m while measuring 442 m median; default 500 m.
- In NAVERA: the contract (ARCHITECTURE §2: ENU, m², "UNKNOWN rather than an invented value"); the judge refuses a
  non-covariance ("would break a consumer's filter"); FIX ≤ 25 m from a horizontal σ ≥ 1 cm; the judge's σ is
  √max(a, c) (mission 12 and CONVENTIONS say so; verified in base/ code, read only); dead-reckoning σ growth
  "velocity error × t + 5° heading error × distance", ≤ 120 s / 500 m, 90 s over the bay at ±300 m with ≤ 146 m
  true error (2026-10-02, simulator); vision carried to the present ±31.5 m (unit tests); GPS in doubt: accuracy no
  better than the gap, up to 500 m; cross-check in sigmas (3 σ, 5 σ + 50 m); vision takes its search centre from the
  judge's vetted output (QA campaign) → not independent; 30 m not yet measured with NAVERA's camera.
- The mechanism is stated in TROUBLESHOOTING ("the EKF rejects positions that jump more than it was told") and
  ARDUPILOT_INTEGRATION §3 (accuracy clamped to 100 m: R = constrain(accuracy, EK3_POSNE_M_NSE, 100 m)²). Note
  (round 1, expert): by §3's Rayleigh rule a round ±300 m PREDICTS a median of 353 m — the stated σ was right about
  the median and wrong about the tail (p90 853 m vs 644 m predicted); both flights reached the EKF as ±100 m. The
  brief, the new §3 ✏️ "back to the mission brief" and "In NAVERA" say so. Expected Step 10 answer: told 100 m,
  errors 3.5–8.5σ → large normalised innovations: the tail refused by the EKF's innovation gate (EK3_POS_I_GATE, set in standard deviations, range 1–10 σ in ArduPilot's parameter list — not a NAVERA doc; its default was not verified here, check the firmware's parameter list), the rest accepted as over-precise jumps → failsafe; the 45 vs 91 s are single flights
  with different rejection counts, both clamped at 100 m: not causal evidence. The desert problem is still open
  (backlog R-11 🔧); the 125 km jump is fixed (QA-2 ✅, max_forward_sigma_m 1 km).

## Rubric for the written answers (the check only catches empty or off-topic text)

| Item | 3 (good) | 2 | 1 |
|---|---|---|---|
| EXPLAIN_CHI2 | two squared normal errors are added on a map → d² larger; names χ² with 2 dof, 5.99 vs 3.84 (or "mean 2, one per dimension"); the k = 3 circle is shorter than the long axis, so far fixes along it escape | two of three | restates the numbers |
| EXPLAIN_RADAR | sideways error = r·σβ (52 m) vs 8 m along; with 10° the positions lie on an arc, J P Jᵀ is a straight-line (linear) approximation | one idea | "the ellipse is wrong" |
| EXPLAIN_JUDGE | direction: E is across the track where σ is 25 m (d² 9.65); never-grown refuses the truth A and every later fix (lock-out); the circle accepts the spoofer B | two of three | one |
| EXPLAIN_ATTACK | along the long axis (track, bearing 120°/300°); √(χ²·λ); a smaller S or lower p shrinks the room at the cost of refusing honest fixes | two of three | one |
| EXPLAIN_FUSE | the 24 wrong matches are fused with weight (up to ~70 % in the canyon) → errors of 100–300 m dominate the RMS (squares), while most seconds improve (p95); the liar's σ is too small → coverage 75 %, S too small → 159 false alarms | outliers + liar without numbers | one cause |
| EXPLAIN_PUBLISH | the judge reads the largest DIAGONAL term; the ellipse is tilted 40°; up to √2; read √λ₁ (or the source states its worst axis) | two of three | one |
| report.md memo | three headings answered with the student's numbers (39 %, a coverage, an RMS, the √2 or the false-FIX count), correct gate/fusion conditions | numbers but thin reasoning | generic text |

## Wrong-but-plausible solutions (all caught; messages verified 2026-10-14)

22 builder mutants plus the reviewers' (dof fixed at 2, unclamped λ on a matrix that really rounds negative) in `~/academy-test/review/27-uncertainty/build/mutants/` (make_mutants.py): ÷N, no mean, raw eigh angle,
variances instead of axes, no clamp, bearing angle, √d², diagonal-only d², uniform draws, (x+y)², J P J, σβ in
degrees, sin/cos swapped, dof 1, d vs threshold, "d² < 9", element-wise 1/P, swapped weights, b copied to both
places, no refusal, always KNOWN, numpy floats. Each fails its check with a message naming the mistake. `python3 run_uncertainty.py test` already flags 19 of them
(the bearing angle only as "the angle should be 26.565°"); the 3 others — "d² < 9", b copied to both places, numpy
floats — only Check my work sees.

## Difficulties to expect

- **The angle convention** (from east towards north, in (−90, 90]) after missions that used bearings; eigh's sign.
  The 🧰 box and the runner say "the right line, but…".
- **Shapes** in numpy (`J @ P @ J` works for 2 × 2 and fails only for 1 × 2: the runner's second case exists for that).
- **σβ in degrees**: the most common error in the old version's testing; the runner names it.
- **Coverage** is a new idea: insist that "93 % vs 95 %" is fine with 400 samples, 75 % is not.
- `make_covariance` (least help, by design): the asymmetric case — students "helpfully" average b; the lesson's
  ✏️ 5 in Check yourself and the check's message explain why not.

## Class plan (2 × 2 h + reading)

1. Session 1 (after §1–§4 read at home, 70–100 min; §3's box after Step 3): 10 min Step 0 pooled predictions (most say 68; reveal 39 %). 20 min
   §2 by hand ([[10, 6], [6, 10]]). Lab Steps 1–4. Badge Ellipse maker.
2. Session 2 (after §5–§7): 10 min "judge" game on paper with judge.json (vote A–F, then run). Lab Steps 5–9.
   Debrief: why NAVERA selects instead of fusing (§6 conditions) — leads into missions 28 and 29.

Differentiation: fast students — Going further (honest_sigma, ROC, correlated sources); struggling — do Step 4 with the
runner's numbers only (TODO 5–6 with hints 1–2), skip "radar wide" prediction, and pair for the memo.

## Notes for the lead

- `datasets/27-uncertainty/` was fully replaced (old Kalman files removed; 28 keeps its own copies).
- The cold-open figure shows simulated scatter for the 351 m median (illustration, labelled with the real numbers).
