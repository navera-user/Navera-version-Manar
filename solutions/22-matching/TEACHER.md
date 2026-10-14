# Mission 22 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

Two sessions: **Session 1 — Geometer** (Steps 0–6, badge **Geometer** = checks 1–7, milestone `geometer`) and
**Session 2 — Learned matcher** (Steps 7–13, badge **Matchmaker** = all 15 checks). Lesson Part A (§1–§5) before
session 1, Part B (§6–§8) before session 2. Owner decision §7.5 (2026-10-14): the student builds NAVERA Lite "from
training to simulation"; here the network trained in mission 21 becomes a matcher, and the AI half is **decisions
graded by measurement** (a threshold, a heading limit, a policy), not transcription. Owner instruction for this
rebuild: the student writes the DLT homography (the plan had moved it to optional).

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. Ratio test, precision | §1 (250/290) | Step 1 (TODO 1), `ratio` | 1, 7 |
| 2. Similarity (LSQ) and homography (normalised DLT), degrees of freedom | §2 (s = 1.6, θ = −120°; s ≈ 2.15), §3 (4 vs 2 pairs) | Steps 2–3 (TODO 2–3), `fit` | 2, 3, 7 |
| 3. RANSAC sample count, RANSAC | §4 (11; 74) | Steps 4–5 (TODO 4–5), `iters`, `ransac` | 4, 5, 7 |
| 4. Trust gates: what each costs and protects | §5 (bunched) | Step 6 (TODO 6), `gates` | 6, 7 |
| 5. A learned descriptor as a matcher: prior, threshold, envelope, policy | §6 (upright point), §7, §8 | Steps 7–11 (TODO 7–9 + 3 DECISIONS) | 8–14 |

## Answer key (recomputed on the Jetson, OpenCV 4.11, torch 2.8, 2026-10-14, reference weights = mission 21's
solutions/21-features/my_desc.pt as shipped in courses/22-matching/files/ref_desc.pt)

- Step 0: any prediction. Most will say the sea; the honest hardest is `wrong_place` (accepted by the prototype rule).
- Step 1 (`ratio`, city, 1 500 SIFT points each side): no ratio 1 500 pairs, 548 right, **PRECISION_NONE = 0.365**;
  0.6: 520/518 (0.996); 0.7: 532/526 (0.989); 0.8: **KEPT_08 = 571**, 534 right, **PRECISION_08 = 0.935**; 0.9:
  738/540 (0.732).
- Step 3 (`fit`, on the pairs the truth calls right): city 534 pairs, similarity median 0.11 px (p90 0.41), homography
  0.11; city_tilt 473 pairs, similarity **RESID_SIM_TILT = 7.74** px (p90 17.72; s = 1.540, θ = −35.2°), homography
  **RESID_H_TILT = 0.19** px (p90 0.67). OpenCV gives the same medians (7.74, 0.20).
- Step 4 (`iters`, p = 0.99): w 0.9: 3 / 5; 0.5: 17 / 72; 0.3: 49 / 567; **0.2: ITERS_SIM_W02 = 113 / ITERS_H_W02 =
  2 876**; 0.1: 459 / 46 050.
- Step 5 (`ransac city_tilt`, 520 pairs, 473 right, w = 0.91): formula samples 3 / 4 → similarity 187 inliers, 1.23 m;
  homography **5 inliers, 82.3 m** (a clean but bad sample: the "read after" box); 500 samples → similarity 202
  inliers, **CENTRE_ERR_SIM_TILT = 1.91 m**; homography 474 inliers, **CENTRE_ERR_H_TILT = 0.21 m**; OpenCV 210 / 2.00 m
  and 474 / 0.21 m.
- Step 6 (`gates`):

  | pair | pairs | inliers | scale | θ | prototype | gates | truth |
  |---|---|---|---|---|---|---|---|
  | city | 571 | 534 | 1.60 | −35.0 | accept | ok | 0.2 m |
  | city_tilt | 520 | 202 | 1.49 | −35.2 | accept | ok | 1.9 m |
  | olives | 401 | 350 | 1.60 | −35.0 | accept | ok | 0.2 m |
  | olives_shaken | 2 | 2 | 1.60 | −120.2 | refuse | too few inliers | (1.5 m) |
  | harbour | 447 | 365 | 1.60 | 60.0 | accept | ok | 0.3 m |
  | sea | 0 | 0 | — | — | refuse | no fit | — |
  | wrong_place | 61 | 14 | 0.00 | −93.7 | **accept** | **scale off** | another place |
  | hills | 348 | 299 | 2.24 | −35.0 | accept | **scale off** | 0.3 m (a right match refused) |

  **REASON_WRONG_PLACE = REASON_HILLS = "scale off"**, **PROTOTYPE_WRONG = wrong_place**. The wrong place's 14 inliers
  are many map points paired with almost one photo point (scale 0.00): the classic many-to-one failure.
- Step 5 prediction (PREDICT_RANSAC_MIN): most say yes ("91 % right: 4 samples are plenty"); the run shows 5 inliers and
  82 m off — a clean but bad sample.
- Step 8 (`learned olives_shaken`, prior 126° ± 5°): SIFT **2 pairs** (both right), network (ratio 0.8) **40 pairs**,
  36 right, 1.50 m. `learned city`: SIFT 571/534, network 224/206 (0.06 m). Check 12 compares PAIRS_LEARNED_SHAKEN with
  the student's OWN network on that pair (± 10 %), so a weaker network's honest count passes.
- Step 9 (`curve`, 12 pairs, 4 of them shaken 11–17 px like the hidden photos; reference network). SIFT ratio: 0.7
  0.944, 0.75 0.901, **0.8 2 586/2 139 (0.827)**. Network ratio (precision; share of the right pairs found at 0.95):
  0.6 0.973 / 0.82, 0.65 0.963 / 0.86, **0.7 0.934 / 0.89**, **0.75 0.893 / 0.92**, **0.8 0.829 / 0.94**, 0.85 0.699.
  Shaken photos only: 0.6 1.000 / 0.25, 0.65 0.986 / 0.38, **0.7 0.938 / 0.50**, 0.75 0.871 / 0.64, 0.8 0.779 / 0.74.
  Distance cut: 0.5 0.940, 0.6 0.900, 0.7 0.820. **Defensible decisions for the reference: ratio 0.7–0.75** (0.65
  if justified by the shaken table), or a distance cut 0.6 — always from the student's own tables.
- Hidden decision test (check 10, 7 unseen photos h02 h04 h06 h12 h13 h15 h16, shaken or blurred, σ ≤ 8°). Bars:
  precision ≥ **0.90** and ≥ **50 %** of the right pairs the STUDENT'S network keeps with a loose 0.95 (computed by the
  check, so it adapts to the network). Reference network (641 loose right pairs): 0.6 → 44 % (fails, too strict), 0.65
  → 0.986 / 56 %, 0.7 → 0.977 / 66 %, 0.75 → 0.951 / 76 %, **0.8 → 0.878 (fails)**, distance 0.6 → 0.955 / 66 %.
  Other networks (expert's set, ratio passing window): seed1 0.65–0.75, m10 0.65–0.75, cpu4k 0.7–0.75, exp **only
  0.7**, fc **only 0.75**; quick (fails mission 21's 0.85) has none. The lab's rule of thumb — the loosest ratio whose
  precision on ALL curve photos is about 0.85–0.90, checking that the SHAKEN table keeps about half — lands in the
  window for every network that passes mission 21 (cpu4k 0.75, exp 0.7, fc 0.75, m10 0.75, seed1 0.75, ref 0.75).
- Step 10 (`envelope`, ratio 0.7): A — heading error 0/5/10/15/20/25/30/35/40/60/90°: city 240/215/209/194/108/37/7…,
  olives 92/88/87/74/44/9/2/0…; both ok up to **NETWORK_MAX_ERR_DEG = 25**, olives 9 inliers there (**ENV_OLIVES_INLIERS = 9**, checked against the
  student's own network so the error cannot be guessed from the ±20° training range). At ratio 0.75: ref, seed1, m10,
  oldref 25; exp, cpu4k, fc and three networks trained with today's runner (seeds 2–4) 20; quick 10 — no network passing
  mission 21 had 15. B — zoom ×1.1 ok for both; ×1.2 and beyond "scale off" for both (the gate, ±15 %). C — olives shake13: network
  34 inliers ok, SIFT 3 refused; both fail on Gaussian blur 3–4 over olives. **HEADING_LIMIT_DEG**: the check wants
  2 × limit ≤ NETWORK_MAX_ERR_DEG (σ vs error, lesson §8: about 1 photo in 20 is beyond 2σ), and the hidden scenes need
  the network at σ 6–8°, so the window is **8–10°** for a 20° network, 8–12.5° for 25°. 180 fails (2σ rule), 5 fails
  (policy: 6 right).
- Step 11 (`mission`, 12 scenes, reference policy SIFT → network, ratio 0.7, limit 10): m01 sift 570, m02 sift 121,
  m03 sift 385, **m04 network 16**, m05 refused (no heading, shaken), m06 refused (blur 4.5), m07 sift 51, m08 sea
  refused, m09 another place refused, m10 wrong altitude refused (scale off), **m11 refused** (σ 15° > limit: SIFT only;
  with a limit ≥ 15 the network is tried 37° off and refused), **m12 network 24**. **6 right, 6 refused, 0 wrong**,
  10–45 s depending on load.
- Hidden policy test (check 14, 16 scenes, ≥ 7 right with at least one by the network, 0 wrong): reference 10 right, 6
  refused, 0 wrong (h04, h12, h15, h16 need the network; h14 is a σ = 15° prior 37° off). SIFT only: 6 (fails, the
  message names the unused network); limit 5: 6; network first: 10 right, 0 wrong (the network then answers h02, h06,
  h13 too); no gates or gates on all pairs: wrong positions accepted (h07, h11). At the strict end of the check-10
  window: ref/m10/s4e4 0.65 → 10, seed1 0.65 → 9, fc 0.75 → 9, s2 0.65 → 8 (h12 and h16 refused): a stricter threshold
  costs matches on shaken photos. The check prints how many right answers came from the network and how many scenes the
  limit let the network see with the prior outside the student's measured envelope (`mission` prints the same).
- Check 13 (crafted): the student's sift_pairs is replaced, inside the student process, by two crafted pair sets: 40
  inliers in one corner + 30 spread wrong pairs (must be refused: "inliers bunched"), and a zoom-4 match whose map points
  are in one corner but photo points spread (must be accepted). It catches gates on all pairs, gates on the map
  points, and a wrong predicted scale.

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_RATIO | a close second = ambiguous point (repetitive texture, a point not in the photo); unique pairs survive; quotes 0.365 → 0.935 | "it removes bad pairs" without why | restates the formula |
| EXPLAIN_DOF | perspective/trapezoid needs 8 DOF; the similarity's 4 cannot; cost = 4-point samples, many more iterations (567 vs 49), more sensitive to noise | one half | "homography is better" |
| EXPLAIN_GATES | hills: a right match refused because the altitude is wrong (availability lost); kept because wrong places almost never match at the right scale, and a wrong accepted fix (1 097 m) is far worse than a missed frame | names the cost or the benefit | describes the table |
| EXPLAIN_THRESHOLD | quotes their own curve (precision and right at 2+ thresholds), compares with SIFT at 0.8, explains the trade (RANSAC w, wrong-place risk vs too few pairs on blurred photos) | numbers without trade-off, or trade-off without numbers | "0.8 like SIFT" |
| EXPLAIN_ENVELOPE | fails beyond ≈ 20–30° of heading error and outside the scale gate; beats SIFT on shaken repetitive ground; links both to the training data (±20°, 0.8–1.25, blur, noise; no orientation/scale of its own); the σ limit is half the error because 1 photo in 20 is beyond 2σ | measurements without the training link or the σ argument | "AI is better/worse" |
| EXPLAIN_POLICY | order and why (SIFT needs no prior; network only with a trusted heading), every attempt through the same gates with the prior's zoom, refusal when none passes; mentions what the mission run showed | the order without the safety net | describes the code line by line |
| report.md | four sections with their own numbers, the decisions justified, honest about synthetic data (drawn map, not a camera) | numbers without interpretation | copy of the runner output |

Predictions are never marked. In class, ask who predicted the sea as the hardest pair and who the wrong place.

## Difficulties seen in testing (mutants and the round-1 reviews; no student pilot yet)

21 wrong-but-plausible versions run through the full check (`~/academy-test/review/22-matching/build/mut/`, list and
messages in reports/r1_fixes.md): ratio test `<=` / against the farthest (check 1); θ sign (2); DLT without
normalisation (3: "badly scaled", 14 px vs 1.1 px); floor instead of ceil (4); no refit, `rng.integers` sampling (5);
gate order (6); learned_pairs without A⁻¹ or without `valid` (8, each with its own diagnosis), ignoring max_dist (8);
ratio_curve `<=` (9); decisions None, ratio 0.95, 0.8 or 0.5 (10); NETWORK_MAX_ERR_DEG copied wrong, limit 180 (11);
gates on map points or on all pairs (13); no gates, limit 5 (14). The weak reviewer's worst moment ("`test` is all ✔,
the check 0/13") is fixed: `run_match.py test` now runs the edge cases (ties, one column, ValueErrors, big-pixel DLT,
refit, empty input, gate order, strict ratio_curve). Students copy stale numbers after fixing code: the check says
"run the step again". Round 2: 11 networks (`expert2/drive_all.json`) — the lab's rule of thumb
passes all 15 checks for every network that passes mission 21; exp and fc have a single-value window (0.7 / 0.75),
reached because the SHAKEN table keeps under half at the stricter step. ratio_test returning shape (0,) when empty is now
refused by `test` and check 1 (it used to crash `envelope` inside learned_pairs).

## Class plan (two sessions of about 3 h)

- Session 1: 10 min Step 0 in pairs → 50 min Part A reading with the ✏️ checks (do §2's worked example and §4's N on
  the board) → Steps 1–4 (75 min) → Step 5 (30 min; insist on the paper plan first) → Step 6 and the table on the
  board: which gate refused which pair, and the prototype column (20 min) → badge.
- Session 2: 15 min recap of Part B (draw §6's figure: photo → upright → map → back) → Steps 7–8 (40 min) → Step 9 in
  pairs: each pair defends its threshold with numbers (30 min) → Step 10 together, read table A against the training
  ranges (20 min) → Step 11 (40 min) → report.
- Fast students: Going further (learned first, rotation-proof network). Struggling: the runner's `test` names the
  symptom; for TODO 5 give the paper plan (once / each iteration / after); for TODO 9 the three hints.

## Data, files, time and memory

- `make_dataset.py` (teacher only): 10 places, fine orthophotos rendered once (render_view, pseudo), map patches and
  photos resampled from them with exact H (SIFT + RANSAC residual median 0.36–0.61 px on the session-1 pairs).
  ≈ 12 min from scratch, ≈ 20 s with `--cache DIR`. datasets/22-matching = 6.2 MB (maps, 49 photos, 4 JSON files,
  README with © OpenStreetMap contributors). Hidden: lp pair + expected learned_pairs (reference weights), 16 scenes
  (`scenes.npz` 3.7 MB, `scenes.json`). Places are ≥ 0.8 km from every place of mission 21's patch sets (the two
  "only photographed" wrong places excepted: beach 0.7 km).
- **ref_desc.pt** is in `courses/22-matching/files/` (copied by make_dataset.py from solutions/21-features/my_desc.pt),
  not in datasets/ (readable from every mission). **Whenever mission 21's reference is retrained, run make_dataset.py
  again** (lp_expected.npz depends on it).
- No training in this mission; the network runs on the CPU (2 threads, `academy_gpu.limit_threads`), no GPU slot is
  taken. Measured 2026-10-14: `describe` of 1 000 patches 1.6 s at load 18; `learned_pairs` 2.4 s, `match_photo`
  0.5–4 s per scene; `envelope` 130–250 s at load 13–18; `curve` ≈ 30–75 s; the whole check 1 min 10 s – 2 min 30 s
  at load 10–18 (sealed 2 min 23 s at load 11). Memory: ≈ 400 MB per Python process with
  torch (no GPU memory).
- NAVERA facts (base docs and code, in words): default day matcher learned (DISK + LightGlue, GPU), frame turned north up
  from the heading (or the previous match's rotation), learned first with a heading and SIFT as the fallback, a ±20°
  heading gate on the fitted rotation; DINOv2 retrieval a separate fallback. The validation report (2026-10-03) measures
  only the SIFT matcher (≥ 6 inliers in that bench; the product's current setting is 8); NAVERA's spread rejection
  applies below 30 inliers only. No numbers are quoted for the learned matcher (only code comments have them).
- Nondeterminism: on a loaded machine the network's inlier counts move by a few units between runs (CPU float
  order); the checks use tolerances or outcomes, never exact network counts. SIFT numbers are exact.
