# Mission 22 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

Two sessions: **Session 1 — Geometer** (Steps 0–6, badge **Geometer** = checks 1–7, milestone `geometer`) and
**Session 2 — Learned matcher** (Steps 7–13, badge **Matchmaker** = all 13 checks). Lesson Part A (§1–§5) before
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
| 5. A learned descriptor as a matcher: prior, threshold, envelope, policy | §6 (upright point), §7, §8 | Steps 7–11 (TODO 7–9 + 3 DECISIONS) | 8, 9, 10, 11, 12, 13 |

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
- Step 8 (`learned olives_shaken`, prior 126° ± 5°): SIFT **2 pairs** (both right), network (ratio 0.8) **47 pairs**,
  46 right, 46 inliers, 1.53 m. `learned city`: SIFT 571/534, network 222/208 (0.06 m).
- Step 9 (`curve`, 12 pairs, 15 876 SIFT and 6 532 network map points). SIFT ratio: 0.5 2 049/2 039 (0.995), 0.6
  0.987, 0.7 2 814/2 707 (0.962), 0.75 0.933, **0.8 3 401/2 948 (0.867)**, 0.85 0.749, 0.9 0.568, 0.95 0.375. Network
  ratio: 0.5 1 185/1 168 (0.986), 0.6 1 339/1 303 (0.973), **0.7 1 439/1 361 (0.946)**, 0.75 1 522/1 388 (0.912), **0.8
  1 672/1 410 (0.843)**, 0.85 0.742, 0.9 0.591, 0.95 3 680/1 463 (0.398). Network distance cut: 0.3 0.966, 0.4
  1 229/1 175 (0.956), 0.5 1 419/1 334 (0.940), 0.6 1 549/1 391 (0.898), 0.7 0.778, 0.8 0.594.
  **Defensible decisions:** ratio 0.7–0.8, or a distance cut 0.5–0.6 (alone or with a ratio ≤ 0.9). SIFT's 0.8 copied
  without looking passes the check (0.895 precision on the hidden photos) but EXPLAIN_THRESHOLD must compare it.
- Hidden decision test (check 10, 5 unseen photos, reference network): 0.5 → 151 right (fails: too strict, minimum
  224 = 0.4 × 561), 0.6 → 302 right, 0.99 precision; 0.7 → 415 right, 0.97; 0.8 → 0.895; 0.85 → 0.76 (fails: precision
  < 0.85); 0.95 → 0.35. Distance cut 0.6 alone: 0.95; 0.7 alone: 0.81 (fails).
- Step 10 (`envelope`, ratio 0.7): A — heading error 0/10/20/30/45/90°: city 240/207/104/**11 ok**/2/2, olives
  92/87/42/**0**/0/0. The network's envelope ends between 20° and 30° (trained on ±20°). B — zoom prior ×1.1 ok for
  both; ×1.2 and beyond "scale off" for **both** methods (the gate, ±15 %). C — blur2/3/4, shake9/13/17: city both
  always ok; olives network 50/4/0/46/**26**/5, SIFT 125/5/3/11/**3**/2: the network wins on shaken repetitive ground
  (shake13), both fail on strong Gaussian blur over olives. **HEADING_LIMIT_DEG**: 20 is the natural answer (15–25 is
  defensible; < 8 fails check 12 because the hidden shaken groves come with σ = 6–8°).
- Step 11 (`mission`, reference policy SIFT → network): m01 sift 570 right; m02 sift 121; m03 sift 385; **m04 network
  14 inliers right** (SIFT alone: refused); m05 refused (heading unknown, shaken); m06 refused (blur 4.5); m07 sift 51
  (σ 30°: no network); m08 sea refused; m09 another place refused; m10 wrong altitude refused (scale off).
  **5 right, 5 refused, 0 wrong.**
- Hidden policy test (check 12, 13 scenes): reference 8 right, 5 refused, 0 wrong (h04 and h12 need the network).
  SIFT only: 6 right (fails: ≥ 7 needed, message names the unused network); heading limit 5: 6 (fails); network first:
  10 right, 0 wrong (passes); no gates (≥ 6 inliers only): **2 wrong** (h07 beach photo at the town map, 30 inliers at
  scale 0.0; h11 another grove, 15 inliers) — fails.

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_RATIO | a close second = ambiguous point (repetitive texture, a point not in the photo); unique pairs survive; quotes 0.365 → 0.935 | "it removes bad pairs" without why | restates the formula |
| EXPLAIN_DOF | perspective/trapezoid needs 8 DOF; the similarity's 4 cannot; cost = 4-point samples, many more iterations (567 vs 49), more sensitive to noise | one half | "homography is better" |
| EXPLAIN_GATES | hills: a right match refused because the altitude is wrong (availability lost); kept because wrong places almost never match at the right scale, and a wrong accepted fix (1 097 m) is far worse than a missed frame | names the cost or the benefit | describes the table |
| EXPLAIN_THRESHOLD | quotes their own curve (precision and right at 2+ thresholds), compares with SIFT at 0.8, explains the trade (RANSAC w, wrong-place risk vs too few pairs on blurred photos) | numbers without trade-off, or trade-off without numbers | "0.8 like SIFT" |
| EXPLAIN_ENVELOPE | fails beyond ≈ 20–30° of heading error and outside the scale gate; beats SIFT on shaken/blurred repetitive ground; links both to the training data (±20°, 0.8–1.25, blur, noise; no orientation/scale of its own) | measurements without the training link | "AI is better/worse" |
| EXPLAIN_POLICY | order and why (SIFT needs no prior; network only with a trusted heading), every attempt through the same gates with the prior's zoom, refusal when none passes; mentions what the mission run showed | the order without the safety net | describes the code line by line |
| report.md | four sections with their own numbers, the decisions justified, honest about synthetic data (drawn map, not a camera) | numbers without interpretation | copy of the runner output |

Predictions are never marked. In class, ask who predicted the sea as the hardest pair and who the wrong place.

## Difficulties seen in testing (mutants of the reference; no student pilot yet)

13 wrong-but-plausible versions, each run through the full check (`~/academy-test/review/22-matching/build/mut/`):
see the build report for every message. Main ones: ratio test with `<=` or against the farthest distance (check 1
names it); θ sign error (check 2, "θ has the wrong sign"); DLT without normalisation (check 3, "badly scaled", 9.9 px
vs 0.9 px); `int()` instead of ceil (check 4); RANSAC without the final refit (check 5), sampling with
`rng.integers` (check 5's iters = 1 test names the sampling rule); gates in the wrong order (check 6); learned_pairs
leaving the photo points in the upright picture (check 8 names A⁻¹); ratio_curve with `<=` (check 9); a policy without
gates (check 12: wrong positions accepted); decisions too loose (ratio 0.95, check 10) or a heading limit of 5° (check
12 names the unused network).

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
  ≈ 12 min from scratch, ≈ 20 s with `--cache DIR`. datasets/22-matching = 6.0 MB (maps, 47 photos, 4 JSON files,
  README with © OpenStreetMap contributors). Hidden: lp pair + expected learned_pairs (reference weights), 13 scenes
  (`scenes.npz` 3.7 MB, `scenes.json`). Places are ≥ 0.8 km from every place of mission 21's patch sets (the two
  "only photographed" wrong places excepted: beach 0.7 km).
- **ref_desc.pt** is in `courses/22-matching/files/` (copied by make_dataset.py from solutions/21-features/my_desc.pt),
  not in datasets/ (readable from every mission). **Whenever mission 21's reference is retrained, run make_dataset.py
  again** (lp_expected.npz depends on it).
- No training in this mission; the network runs on the CPU (2 threads, `academy_gpu.limit_threads`), no GPU slot is
  taken. Measured 2026-10-14: `describe` of 1 000 patches 1.6 s at load 18; `learned_pairs` 2.4 s, `match_photo`
  0.5–4 s per scene; `envelope` ≈ 60 s; `curve` ≈ 20 s; the whole check 100 s at low load, **169 s at load 21**
  (before the decision check was halved; re-measure on the class machine). Memory: ≈ 400 MB per Python process with
  torch (no GPU memory).
- NAVERA facts: its default day matcher is learned (DISK + LightGlue, GPU) with SIFT local matching as fallback and DINOv2 retrieval as a separate fallback; the validation report (2026-10-03) measures only the SIFT matcher, so the lesson quotes no figures for the learned one.
- Nondeterminism: on a loaded machine the network's inlier counts move by a few units between runs (CPU float
  order); the checks use tolerances or outcomes, never exact network counts. SIFT numbers are exact.
