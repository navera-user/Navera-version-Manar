# Mission 12 — teacher notes (The position contract: covariance, stamps and honest uncertainty)

Teacher only. Rebuilt 2026-10-13 on NAVERA Lite. Students write `navera_lite/estimate.py` TODO 1–4
(`is_covariance`, `stated_sigma`, `staleness_m`, `eligible`; reference in `solutions/_navera_lite/navera_lite/estimate.py`,
tags `# @part 12 todo 1–4`; `age_s` is `@part 12` given; `Estimate`, `horizontal`, `classify`, the constants are
given since 09). They attack the given arbiter v0 (09) with replay scenarios, then run it with
`-p use_eligible:=true`, which calls their `eligible()` and `stated_sigma()`. Mission files (hand-written):
`contract_lab.py` (runner), `answers.py`, `attacks/honest.csv` (given model), `runner_kit.py` (copy of `_lib`).

**Lightened (rebuild plan §B):** eigenvalues, ellipse axes, the 39 %/86 % ellipse probabilities, Mahalanobis and
χ² are gone (mission 27); the lesson mentions only "the tilted ellipse's longest axis is 15 m — mission 27".
σ_max/√2 dropped. The old excerpts of NAVERA's message and estimator code, `my_source.py` against NAVERA's
arbiter and the multiple-choice quiz are gone. NAVERA is described in words only ("In NAVERA": ARCHITECTURE §3,
VALIDATION_STATUS 2026-10-03 robustness table and "vision positions carried to the present", backlog EST-2,
LOC-17). Covariance notation a / b / c as in CONVENTIONS §5. Hold-off is defined (§5).

Numbers: `python3 solutions/12-position-message/expected.py` (lag study) and `make_dataset.py` (writes
`datasets/12-position-message/day_vision_lag.csv`, seed 1203, 160 rows; the README there is neutral). The
check's unseen eligibility situations: `courses/12-position-message/hidden/eligible_faults.json` (20 cases).

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 fill an estimate honestly (measured stamp, m², type, nan) | §1 (+ 🧰 dataclass, worked day fix, ✏️ celestial), §3 types | Step 1 `MY_ESTIMATE` | 1 |
| 2 is it a covariance; stated σ | §2 (worked 25/30/16, ✏️ three matrices), §3 (worked tilted, ✏️ four σ) | Steps 2–3 (TODO 1–2) | 2, 3, 4, 5 |
| 3 age vs latency, staleness, future stamps | §4 (worked 40 m/s × 1.8 s, σ is not a maximum, ✏️), figure | Step 0 (dead GPS), Step 4 (TODO 3, lag study, 🧰 "within 30 m"), Step 8 (revival: PREDICT/EXPLAIN_REVIVE) | 6, 7, 13 |
| 4 predict a verdict, find a judge's holes | §5 (checklist, worked three sources, attacker's view, ✏️ night type 0) | Steps 5–8 (attacks, TODO 4, live), Step 9 | 8, 9, 10, 11, 12, 14 |

Badges: **Contract keeper** = checks 1–7 (session 1), **Honest judge** = all 14.

## Answer key

| Item | Value | Where it comes from |
|---|---|---|
| Step 0 | FIX "gps: σ 3.0 m", `age_s` ≈ −29.5; after Ctrl+C the dead GPS stays FIX ≈ 33 s (30 s offset + 3 s timeout), then NO_FIX "gps: stale (3.1 s > 3.0 s)" | measured in the sandbox 2026-10-13: NO_FIX ≈ 35 s after the Ctrl+C |
| PREDICT_DEAD | ungraded; most students say "NO_FIX after 3 s" (mission 11) | |
| MY_ESTIMATE | `Estimate("night", 35.7712, 10.8265, 812.4, cov=(324, 0, 0, 0, 576, 0, 0, 0, 900), cov_type=COV_DIAGONAL_KNOWN, alt_m=nan)` | the check names each wrong field: 813.5 (published), σ not squared, type 3, alt 0.0 |
| LAG_PLANE_MEDIAN_M | 64.30 (± 0.06) | 40 m/s × age + match error; median age 1.592 s, p90 2.284 s, max 4.407 s |
| LAG_PLANE_WITHIN_PCT | 0.00 | every fix ≥ 38 m off at 40 m/s (min age 0.95 s) |
| LAG_DRONE_WITHIN_PCT | 76.88 (± 0.07) | 15 m/s: median 24.44 m, p90 34.48 m |
| LAG_OLD_WINDOW_REFUSED | 6 | the six "busy" frames, 3.2–4.6 s (none > 5 s) |
| LAG_SPEED_MAX_MPS | 13.1 expected (30 m ÷ p90 age 2.284 s = 13.13), 12.85–13.2 accepted | the lab asks to compute it from the p90 age, then confirm with one run: 13.1 → 89.38 %, 13.0 → 90.00 % (12.9 too), the exact limit with the match error is 13.064 |
| attacks (solution) | zero: type 1, a=b=c=0 → v0 FIX σ 0.0; unknown: type 0, a=c=4 → FIX σ 2.0; not_psd: type 1, a=64, b=100, c=81 → FIX σ 9.0; future: one fix, delay_s −60 → FIX for 63 s | the check rebuilds both verdicts with its own model of v0 and of an honest judge from the student's files |
| VERDICTS_V0 | four FIX, copied from the live `contract_lab.py status` line "FIX \| gps: σ …" (σ values depend on the files) | the check requires the live NO_FIX wording "no usable source (…" (the simulation prints a short form) |
| VERDICTS_MINE | zero, unknown: DEGRADED \| gps: σ unknown; not_psd: NO_FIX \| no usable source (gps: not a covariance); future: NO_FIX \| no usable source (gps: from the future) | |
| PREDICT_REVIVE (ungraded) / EXPLAIN_REVIVE | live, one fix stamped 60 s ahead (replay start 3 s): NO_FIX "from the future", then FIX "gps: σ 3.0 m" for ≈ 3.5 s about 60 s after the fix, then NO_FIX "stale". Offline `judge --eligible --until 70`: NO_FIX until 59.5 s, FIX 59.5–63.5 s, then stale | arbiter v0 keeps the newest fix of each source even when eligible() refuses it and re-tests it at every tick; once the clock passes stamp − 0.5 s the fix is no longer "in the future", and is fresh for the GPS timeout. eligible() is right; the judge around it keeps a refused message. Course decision: v0 stays naive; mission 29's arbiter must handle it. Do not present this as a NAVERA flaw (open product question, not course content) |
| Step 7 hand trace (now 500.0; key in the lab, in a details box) | day 495.2 → eligible (4.8 s ≤ 5 s); GPS (0,0) valid False → no position; celestial 500.9 type 2 non-PSD → not a covariance (rule 4 before 5); GPS NaN lat 500.3 → bad position | |
| fifth hole (Going further) | negative variances (a = c = −4, type 1): v0 reads √max(a, c, 0) = 0 → FIX σ 0.0; honest → NO_FIX "not a covariance". (A NaN covariance is NOT a hole: v0 says DEGRADED σ unknown.) | |

Relative tolerance (fix rounds 1–2): `is_covariance` allows tol × size on b and tol × size² on a·c − b², size =
max(1, |a|, |c|) — horizontal only (round 2: with the up variance in size, σU² = 10⁶ let a = 9, b = 10, c = 9 through,
ρ = 1.11, and the honest judge said FIX). With an absolute 10⁻⁹, 27 % of valid km-scale covariances with ρ = ±1 were refused
(expert review); lesson §2 example σ 3615.9 / 4706.3 m, ρ = 1 → a·c − b² = −0.0625 in float. The check adds
σ 1533.1 / 4338.7 m (−0.0156).

Lesson numbers: ρ = 30/(5·4) = 1.5, 400 − 900 = −500, variance along (0.707, −0.707) = 12.5 − 30 + 8 = −9.5 m²;
✏️ 100/−60/49 → 1300, ρ −0.86; 9/4/1 → −7, ρ 1.33; −4/0/−9 → det +36 but negative variances. Tilted:
83.25·177.75 − 81.84² = 8100, ρ = 0.67, stated √177.75 = 13.33 m, longest axis 15 m (eigenvalues 225, 36). ✏️ σ:
20 m FIX, None, None, 25 m FIX. §4: 40 × 1.8 = 72 m; 15 × 1.5 = 22.5 m; ages 0.3 / −0.4 / −1.0 s. §5 worked:
GPS stale 3.5 s, day DEGRADED "day: σ 30.0 m > 25.0 m". Check yourself: 49·16 − 900 = −116, ρ 1.07;
√0.0001 = 0.01 (believed: `0.01 < 0.01` is False in Python); 1.2 s / 1.5 s / 30 m; gate 150 m.
NAVERA figures (VALIDATION_STATUS, last updated 2026-10-03): 83 m median, 0 % within σ (40 m/s, 1–2.5 s old,
simulator); 60 s future → refused; zero / undefined type / non-PSD → DEGRADED / DEGRADED / not used (before:
FIX 0, FIX, republished); 1.5 s at 40 m/s → moved 60 m, ±31.5 m (unit tests, simulator only); day window 5 s
(was 3 s). Argos classes: 3 < 250 m, 2 250–500 m, 1 500–1500 m, 0 > 1500 m, A/B no estimate, Z invalid.

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_REVIVE | the judge stores the refused fix as the source's newest and re-tests it every tick; when now reaches stamp − 0.5 s it is no longer "future" and is fresh for 3 s: a dead source wins again; a judge must forget (or mark) a fix refused as future | sees the FIX at ≈ 60 s and blames "the clock" without the stored fix | "my eligible() is wrong" |
| EXPLAIN_DEAD | stamps 30 s ahead → negative age → "age > 3 s" never true until 30 + 3 s after the last fix; names the missing future rule | "the stamps were wrong" without the negative-age mechanism | "the GPS kept sending" |
| EXPLAIN_LAG | the position describes the photo's instant; the vehicle flies speed × age during the 1–2.5 s; the stated σ ignores it (so 0 % within at 40 m/s) | only "latency" or only "speed" | blames the matcher's accuracy |
| EXPLAIN_HONEST | a 3 m covariance is valid and fresh: eligible() checks form and time, never truth; only an independent witness (cross-check, jump gate for jumps) or a validation measurement can show the lie | names a fix without saying why the checklist cannot | proposes a new rule on the nine numbers |

## Difficulties expected (to confirm with the simulated students and the pilot)

- Step 1: stamp 813.5 and σ not squared are the common slips; type 3 vs 2 (the check names each one).
- TODO 1: forgetting the `try` (None, 12.0); testing the determinant before the variances (a = c = −1 passes);
  `!=` instead of a tolerance for symmetry; ignoring the `tol` argument (the check passes tol = 0.5).
- TODO 2: passing the nine numbers instead of the Estimate; averaging a and c; the hard-coded 0.01.
- TODO 4: `KeyError` on an unknown source (TIMEOUT_KEY looked up before the membership test); `>=` instead of `>`;
  two decimals in the stale reason; checking the future before the covariance.
- Step 5: a σ above 25 m in the `unknown` attack (v0 then says DEGRADED, not FIX); a 5 km jump that the jump gate
  refuses. Step 8: students may think their eligible() is wrong when the dead future fix comes back as FIX
  (≈ 60 s): it is the judge's memory (the lab says so after the EXPLAIN task).
- Leftover nodes: the live check stops with the publishers_ok message if a judge or replay still runs.
- One terminal tab (each tab has its own network): nodes run with `&`, `kill -INT %%` / `$(jobs -p)`; the
  runner's `status` (rclpy, latched status) prints "STATE | message" and `status --watch N` the changes.
- Session 1's time: the weak simulated student needed ≈ 5 h 50 in total (meta: 5 h 30).

## Class plan (two sessions)

- **Session 1 (≈ 2 h):** 10 min Step 0 live together (prediction poll before the kill) · 30 min lesson §1–§2 with
  the ✏️ checks on paper · 50 min Steps 1–3 · 20 min §4 + Step 4 · 10 min check → Contract keeper.
- **Session 2 (≈ 2 h 30):** 15 min §5 (do the worked example on the board, then "list v0's missing questions" in
  pairs) · 40 min Steps 5–6 (red team) · 40 min Step 7 · 30 min Step 8 live incl. the 75 s revival watch · 10 min Step 9 discussion: what can
  catch an honest-looking lie (link to mission 30).
- **Fast students:** Going further (fifth hole, close the revival in a copy of NaiveJudge, `my_source.py`). **Struggling students:** give the
  `honest.csv`-to-`zero.csv` edit as a demo, pair them for Step 5; TODO 4 with the hand trace done together.

## Build notes

- The check takes ≈ 20 s (one live test: arbiter v0 with the student's `eligible()`, a replay of a GPS stamped 30 s
  ahead, written to a temp CSV in the lesson folder — an input, not an answer).
- Mutants verified (wrong-but-plausible solutions, all caught with a specific message): see
  `~/academy-test/review/12-position-message/reports/build.md`.
