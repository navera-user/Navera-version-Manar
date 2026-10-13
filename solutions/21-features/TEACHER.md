# Mission 21 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

Two sessions: **Session 1 — Scout & detector** (Steps 0–5, badge **Corner hunter** = checks 1–7, milestone
`corner-hunter`) and **Session 2 — Learner** (Steps 6–13, badge **Learner** = all 14 checks). Part A of the lesson
(§1–§6) is read before session 1, Part B (§7–§9) before session 2. Owner decision §7.5 (2026-10-14) added the AI
half: the student builds, trains and tests a small CNN patch descriptor with PyTorch; mission 22 matches with it and
Sim Lite (31) can fly it.

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. Gradients, structure tensor, eigenvalues, Harris | §1–§2 (R of two windows) | Steps 1–3 (TODO 1–4), house | 1, 2, 3, 4, 6 |
| 2. Measure a detector: repeatability vs chance; scale | §3–§4 (chance level) | Step 4 (TODO 5) | 5, 7 |
| 3. Descriptors (ORB/Hamming, SIFT); matchability of terrains | §5–§6 (128 bits; bunched score) | Steps 0, 5, 6 (TODO 6) | 7, 8, 13 |
| 4. Tensors, layers, loss, gradient descent, train/val, overfitting | §7–§9 (shapes; GD step; 0.99 vs 0.70) | Steps 7–10 (TODO 7–9) | 9, 10, 11, 13 |
| 5. Train a CNN descriptor, compare with ORB/SIFT, measured | §9 (matching score) | Steps 9, 11, 12 | 12, 13, 14 |

## Answer key (numbers recomputed on the Jetson, OpenCV 4.11, torch 2.8, 2026-10-13)

- Step 0: any ranking. Most students put the city first and the fields in the middle. Measured (SIFT, default
  contrast): olives 13 504, city 4 032, coast 2 147, saltpans 513, fields 71, sea 0.
- Step 2 (`house`): point 1 (20, 60) Sxx 0.1, Syy 0.2, Sxy 0.0 → λ 0.2/0.1, **flat**; point 2 (110, 30) Sxx 0.2,
  Syy 383.5, Sxy −1.1 → λ 383.5/0.2, R ≈ −5 814, **edge** (the roof's top side); point 3 (90, 70) Sxx 103.1, Syy 103.3,
  Sxy 57.2 → λ 160.4/46.0, **R_POINT_3 = 5 674** from the printed values (5 672 unrounded; the check accepts ±30),
  **corner** (the inner corner of the L). The 12 Harris corners lie on the roof and courtyard corners and the wall's
  ends; none on the round tank's outline.
- Step 4 (`repeat`, 1 000 points, ε 3 px, chance 0.08 for every row, formula 0.088):

  | pair | harris | orb | sift |
  |---|---|---|---|
  | city_rot35 | **0.85** | 0.83 | 0.73 |
  | city_zoom2 | 0.92 | 0.45 | 0.87 |
  | city_zoom4 | **0.39** | 0.07 | **0.78** |
  | city_rot35_zoom | 0.91 | 0.57 | 0.89 |
  | olives_rot35_zoom | 0.96 | 0.35 | 0.83 |
  | fields_rot35_zoom | 0.69 | 0.73 | 0.73 |

  ORB's 0.07 at ×4 is below chance: its pyramid (8 levels × 1.2 ≈ 3.6×) cannot reach a 4× zoom from the map side.
- Step 5 (`terrain`): matchability city 1.00 ok, olives 0.81, fields 0.09, saltpans 0.56, coast 0.62, sea 0.00 "too
  few features"; drone_city 1.00, drone_city_dark 0.00 "too few features"; real_town 1.00, real_coast 0.44.
  **MOST_KEYPOINTS = olives**, **SIFT_FIELDS = 71** (493 with NAVERA's 0.02), **DARK 17 → 632** after CLAHE
  (matchability 0.00 → 0.94). CLAHE on real_coast: 4 316 → 6 160 keypoints, many on the water and seagrass.
- Step 6 (`hamming`, 1 296 pairs): **HAMMING_SAME = 61**, **HAMMING_RANDOM = 127**.
- Step 7: PatchNet = 88 896 parameters (conv1 160, conv2 4 640, conv3 18 496, fc 65 600); **N_PARAMS_CONV1 = 160**
  (144 if the biases are forgotten — the check names it).
- Step 9 (GPU, all 12 288 pairs, 8 epochs, ≈ 14 s): train loss 0.289 → 0.110, val loss 0.233 → 0.150, validation
  score **0.957–0.959** (GPU runs are not bit-identical). CPU, `--n-train 4096 --epochs 4`: ≈ 100 s on a quiet
  Jetson, 4 min 45 s at load 7 (others training), score 0.931–0.936; 8 epochs on all pairs on the CPU: 10–25 min (too long: say so).
- Step 10 (300 pairs, 30 epochs): train loss 0.46 → 0.001; val loss 0.43 → minimum 0.347 at epoch 12, then 0.363
  at epoch 30. Score 0.778 (validation), 0.766 (hidden test).
- Step 11 (`compare`, 2 048 validation pairs, groups of 256): raw pixels 0.741, **ORB 0.756**, **SIFT 0.875**
  (size 8 — the best of 8/12/16/24/32: 0.90/0.75/0.61/0.49/0.44 on a pilot set), **untrained 0.530** (seed 0; the
  check accepts 0.35–0.70), **learned 0.957**.
- Hidden test (check 12, 1 024 pairs from 4 places in no other set): raw 0.729, ORB 0.718, SIFT 0.825, untrained
  0.491, reference network 0.940, the 4 096-pair runs 0.908 (GPU) and 0.916 (CPU), overfit.pt 0.766. Threshold
  **0.85**: a full or a CPU-sized training passes; an overfitted or untrained one does not.

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_EIGEN | each λ = rate of change of the window's content in one principal direction; 2 small/1 large/2 large; det = λ1λ2 and trace = λ1+λ2 give R without square roots at every pixel | classification right, Harris reason missing | restates the formula |
| EXPLAIN_SCALE | R depends on eigenvalues only (rotation invariant) → 0.85; fixed window sees new small details at ×4 → 0.39; SIFT picks a scale per point → 0.78; all vs chance 0.08 | one of the two halves | "SIFT is better" |
| EXPLAIN_TERRAIN | names the surprise (olives: most keypoints; fields: few despite the look); repetitive look-alike points, bunched or uniform; real sea has texture that moves | one trap named | lists counts |
| EXPLAIN_HAMMING | unrelated bits are coin tosses → ½ × 256 = 128; same point ≈ 61 → a threshold or nearest-neighbour test separates most, not all (distributions overlap) | one half | "random is random" |
| EXPLAIN_OVERFIT | train loss → 0, val loss stalls ≈ 0.35 then rises (epoch ~12); memorised 300 patches; more data / early stop | describes curves without why | "it trained badly" |
| EXPLAIN_LEARNED | trained on this kind of pair (drawn views, these effects) → home advantage; needs a test on real frames / real camera / other light and seasons; SIFT was designed for any picture | one half | "AI is better" |
| report.md | four sections with the student's numbers, the scout's surprise named, overfitting and the learned-vs-SIFT comparison honest about synthetic data | numbers without interpretation | copy of the runner output |

Predictions are never marked. In class, ask who put the fields above the salt pans, and who expected the olives.

## Difficulties seen in testing (mutants and the author's runs; no student pilot yet)

- `cv2.Sobel(img, -1, …)` (uint8 output) and forgetting /8: caught by check 1 with the exact cause.
- eigen2 with `math.sqrt` fails on arrays; (smaller, larger) order: named by check 3.
- repeatability divided by all points instead of the inside ones: check 5 names it (0.625 vs 0.714).
- PatchNet: `super().__init__()` not first; a missing pooling gives `mat1 and mat2 shapes cannot be multiplied`
  (runner and check translate it); forgetting `F.normalize` (check 9 prints the row lengths).
- triplet_loss: the diagonal not excluded only shows when the positive is the nearest (runner's second case, check 10);
  `.item()` inside the loss kills the gradient (check 10).
- train: lr hard-coded (check 11 trains with lr = 0), validation loss measured before the epoch (check 11 recomputes
  it after training).
- Students on the CPU must use the reduced command; the full CPU run takes 10–25 min on a shared Jetson.

## Class plan (two sessions of about 3 h)

- Session 1: 10 min Step 0 in pairs (rankings on the board) → 45 min Part A reading with the ✏️ checks → Steps 1–4
  (75 min) → Step 5 and the reveal of the ranking (20 min) → badge.
- Session 2: 15 min recap of Part B (draw the network and one gradient-descent step on the board) → Steps 6–8 (60
  min) → Step 9 (30 min; stagger the GPU runs if 15+ students train at once: each run is ≈ 15 s alone) → Steps 10–11
  together, discussing the curves (30 min) → report.
- Fast students: Going further (harder negatives, rotation test). Struggling students: the runner's `test` names the
  symptom and the hint; for TODO 9 give the paper plan of the lab (once / per epoch / per batch / after the epoch).

## Data and files

- `make_dataset.py` (teacher only, ≈ 12 min): terrains, pairs (exact H, residual of SIFT+RANSAC inliers: median
  0.27–0.44 px, 1.14 px at ×4 where SIFT localisation dominates), drone views, house, patch sets (48 train places,
  8 val, 4 test on a 1.4 km grid; train 32 × 32, val/test 48 × 48), and `courses/21-features/hidden/patches_test.npz`.
  `--skip-patches` keeps the patch files. Real frames: `python3 make_dataset.py <folder of NAVERA's day frames>`
  copies frames 13 and 18 as data (place and source not established: never name a place).
- `make_assets.py`: `assets/terrains.jpg`. `my_desc.pt`: the reference weights (GPU run, validation 0.957, test 0.940).
- datasets/21-features = 27 MB. Map data © OpenStreetMap contributors (README, lab, runner pictures).
