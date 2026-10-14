# Mission 23 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

Two sessions: **Session 1 — Finder** (Steps 0–11, badge **Finder** = checks 1–8, milestone `finder`) and
**Session 2 — Locator** (Steps 12–17, badge **Locator** = all 13 checks). Lesson Part A (§1–§6) is read before session
1, Part B (§7–§9) before session 2. Owner decision §7.5 (2026-10-14): AI is part of the course and students build it
themselves. Here: global retrieval with embeddings — DINOv2 ViT-S/14 used as it is (pretrained, /data/models) and
TileNet, a 257 344-parameter CNN the student builds and trains with InfoNCE on pairs made from the map — both measured
against NAVERA's honest baselines (stay at the prior, random tile in the circle, the best-tile limit), then OpenCV
local matching (SIFT, ratio test, RANSAC similarity, NAVERA's gates) for the exact latitude and longitude, the
student's own rule for when retrieval is worth running, an error budget and the four numbers.

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. Embeddings, cosine, DINOv2's input | §2 (d, e cosines), §3 (white pixel, ViT-B/16 tokens) | Steps 1–3 (TODO 1, 2) | 1, 2, 4 |
| 2. Honest evaluation, baselines, limit, failures | §4 (seven photos), §5 (σ 30 / 600) | Steps 3–6 (TODO 3) | 3, 4 |
| 3. Train an embedding net with InfoNCE; design choices; accuracy and cost | §6 (hard row τ; GAP shape) | Steps 7–11 (TODO 4, 5) | 5, 6, 7, 8 |
| 4. Search radius, gates, centre → lat/lon, the retrieval rule | §5, §7 (5 inliers; scale 1.18), §8 (k = 3 vs 10) | Steps 12–14 (TODO 6, 7, 8) | 9, 10, 11, 13 |
| 5. Error budget vs measured errors | §9 (tilt 0.3° at 400 m) | Steps 15–16 (TODO 9) | 12, 13 |

## Answer key (recomputed on the Jetson, OpenCV 4.11, torch 2.8, DINOv2 ViT-S/14, 2026-10-14)

Data: 80 lab photos (52 textured, 18 sparse, 10 sea), priors σ 200 m (Gaussian per axis); index of the 2 208 zoom-17
tiles of the test area (lat 35.77–35.87, lon 10.55–10.68). Search radius 600 m ≈ 18 tiles; 1 200 m ≈ 74; 1 500 m ≈ 112.

- Step 0: free. The view usually spans parts of 4 tiles; the best tile's centre is 100 m (median) from the truth.
- Step 2: **N_PATCHES = 256** (16 × 16; 16 = one side is the classic slip, named by the check). Your preprocess vs the
  index: largest difference ≈ 0.0006 (GPU vs GPU); BGR or no /255 gives > 0.02 and `embed` refuses. DINOv2 on the GPU
  0.07–0.10 s per photo (80 photos ≈ 6–8 s); on the CPU ≈ 2 s per photo (busy Jetson).
- Step 4 (`retrieve`, σ 200 m): **MED_DINO = 181** (p90 559, within 300 m 64 %), **MED_PRIOR = 246**
  (p90 442), **MED_RANDOM = 457**, **MED_BEST = 103**. DINOv2 beats the prior by about 65 m but has a
  worse tail (p90): the same shape as NAVERA's 442 / 480 / 536 m. By terrain: textured 135 m (best tile chosen 54 %), sparse 236 m (39 %), sea 545 m (0 %).
  Similarity of the top tile: right 0.445–0.865, wrong 0.280–0.802 (overlap, as NAVERA's 0.942–0.974 vs 0.823–0.972).
- Step 5 (σ 800 m, r 1 500 m): **MED_DINO_800 = 559**, **MED_PRIOR_800 = 816**, random 1 224, best 110.
  Retrieval is worth it when σ is large; at σ 200 m the prior is nearly as good.
- Step 6: **WORST_TERRAIN = sea** (best tile chosen 0 %).
- Step 8: **N_PARAMS = 257 344** (conv1 896, conv2 18 496, conv3 73 856, conv4 147 584, fc 16 512); 256 864 without
  biases, 503 104 for a flattening fc (both named by the check).
- Step 9 (`train`, defaults: 8 000 pairs, 12 epochs, batch 64, τ 0.1, shift 0.5, augmentation; GPU): train loss 3.6 → 0.92, validation loss → 2.29, validation recall (1 of 256) 0.29 after 12 epochs; 172–233 s of training on a busy GPU (load 10–15), pairs ≈ 15–30 s.
  **MED_MINE_400 = 215** (two default runs: 215 and 215 m — the runner sets cudnn.deterministic, so the same code gives the same weights — GPU runs are not bit-identical). **MED_DINO_400 =
  240**, prior 494, random 874 (σ 400 m, lab photos).
- Step 10 (one experiment, σ 400 m lab median; reference runs): defaults 215 m; `--no-augment` **813 m** (worse than the prior: it never saw black corners, light or blur); `--shift 0` 483 m; `--n-train 2000` 555 m; `--tau 0.5` 473 m. Every single change hurts; the reference exp.pt is the --no-augment run (EXP_MEDIAN = 813).
- Step 11 (`speed`, CPU, 2 threads, busy Jetson): DINOv2 1 319 ms, TileNet 7.5 ms per photo (22 056 576 vs 257 344
  parameters).
- Step 13: **LOCAL_ERR_P02 = 3.0 m** (σ 50 m prior, r 150 m). p01 (sea): "0 inliers (min 6)"; p02 with σ 400 m:
  "circle too large for one patch (3 048 px > 2 000 px)".
- Step 14 (`sweep`, 20 photos, finder my_tiles.pt): 

  | σ (m) | radius | fine only | retrieval | s/photo fine / retr. |
  |---|---|---|---|---|
  | 50 | 150 | 11/20, median 3.3 m | 10/20, 4.3 m | 0.6 / 0.7 |
  | 100 | 300 | 9/20, 3.4 m | 11/20, 3.6 m | 0.9 / 1.3 |
  | 200 | 600 | 7/20, 4.5 m | 13/20, 5.4 m | 1.9 / 0.9 |
  | 400 | 1 200 | 0/20 (patch too large) | 10/20, 4.5 m | 0.0 / 0.9 |

  0 wrong everywhere. Sweep ≈ 3 min.

  The rule: fine only is as good or better up to r = 150–300 m; at 600 m it gives fewer positions than retrieval and
  is slower; at 1 200 m it cannot run at all (patch > 2 000 px). **DIRECT_MAX_R_M**: the check accepts 150 ≤ value
  < 600 (reference 300) and names ≥ 727 m (no patch fits).
- Step 15: **BUDGET_TOTAL = 5.16** (tilt 0.5° at 360 m 3.14 m, matcher 1.94 m, timing 2.00 m, map 3.00 m).
- Step 16 (`run`, σ 200 m priors → r 600 m > 300 m: retrieval with my_tiles.pt, k = 3): **FINAL_AVAIL = 0.61**,
  **FINAL_MEDIAN = 3.6**, **FINAL_P90 = 7.6**, **FINAL_WRONG = 0**; by terrain textured 40/52, sparse 9/18, sea 0/10.
  The budget (5.2 m) is close to the measured p90/median: the photos have no timing error, their real budget is
  smaller; the matcher term is larger on this drawn map than 2 px.

Hidden tests: TileNet on 36 hidden photos over land (σ 400 m priors): reference 251 m, DINOv2 259 m, prior 450 m;
pass ≤ **380 m** (experiments: --no-augment 862, --shift 0 595, --n-train 2000 648, --tau 0.5 507 m — all fail; untrained 1 024 m). locate() on hidden photos h02, h03, h11, h31,
h34 (σ 40 m: fine step, < 10 m), h02/h03/h11 with σ 400 m (finder called once with (1200.0, 3)), h31 with
direct_max_r_m = 100, h08 (sea, refused), h14 (found 1 214 m from a prior whose circle is 1 200 m → "outside").

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_BASELINE | gain over the prior is small vs the gain over random; tail worse; best tile ≈ 100 m because a tile is 248 m and never centred | one half | "DINOv2 works" |
| EXPLAIN_SIGMA | the prior's error grows like 1.18 σ, retrieval's stays near the tile limit while the right tile is still found: worth it for large σ, not for small | states the numbers only | "always use AI" |
| EXPLAIN_SCORE | ranges overlap → a score cannot flag a wrong tile; an independent test (gates) must decide; never trust a confident wrong position | "no" without consequence | "higher score = right" |
| EXPLAIN_PAIRS | photos are taken anywhere in a tile (offset); effects = what real photos vary in, learned invariance | one half | describes the picture |
| EXPLAIN_EXPERIMENT | names the one change, quotes both medians, explains with what the data taught | numbers without why | "it changed" |
| EXPLAIN_CHOICE | weighs accuracy (medians) and cost (ms, parameters, memory on a shared Jetson); honest that TileNet was tested on drawn maps only | one side | "AI is better" |
| EXPLAIN_DECISION | quotes the sweep (positions, wrong 0, s/photo), the patch limit, picks a radius consistent with them | a value without numbers | contradicts the sweep |
| EXPLAIN_REFUSED | a real photo id, the gate and its reason, why "no fix" is safer | gate named, no why | "it failed" |

Predictions are never marked. In class: who predicted DINOv2 would crush the prior? Show NAVERA's table next to theirs.

## Difficulties seen in testing (mutants and the author's runs; no student pilot yet)

24 wrong-but-plausible solutions, all caught by the check with their own message (build/mut in the review folder):
preprocess kept BGR ("still in OpenCV's BGR order") / no /255 ("values up to 1101"); rank with dot products / smallest
first; evaluate with a nearest-rank p90 / availability over the accepted only; TileNet flattening (the mat1/mat2 error
translated); info_nce without τ / summed; search_radius without the floor; place without + 0.5 ("0.7 m off") / without
the scale gate; locate never calling the finder / without the outside-the-circle rule / stopping at the first
candidate (h33, h37: their first tile is wrong) / a fixed 300 m instead of cfg; budget as a plain sum; answers with
MED_DINO/MED_PRIOR swapped, N_PARAMS without biases, N_PATCHES = 16, DIRECT_MAX_R_M = 1 000, BUDGET as a plain sum;
my_tiles.pt replaced by another file (fingerprint); exp.pt with the same settings as my_tiles.pt.

- **Memory.** A sandbox has 1.8 GB. CUDA + cuDNN + the pairs nearly fill it: the runner trains in a child process
  (all GPU memory returns when it ends) and measures afterwards on the CPU; pairs stay uint8 (8 000 pairs = 197 MB) and
  batches of 64; `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. Measured peak anonymous memory of a training:
  anonymous memory 1.23 GB, cgroup total ≤ 1.77 GB of the 1.8 GB limit (batch 64, deterministic cuDNN). With cuDNN's default algorithms batch 64 reached the limit and was OOM-killed (memory.events oom_kill); batch 32 fits but trains a much worse network (median 439–456 m: fewer in-batch negatives). Two trainings at once in one sandbox will be killed ("Killed"): the runner says so.
- **CPU training** is a poor fallback here (a 64 × 64 colour CNN): `--device cpu --n-train 3000 --epochs 6` took
  41 min on a busy Jetson and gave 712 m at σ 400 m on the lab photos (worse than the prior) (hidden far above the bar). Students should wait for a GPU slot (3 in the class).
- `embed` refuses a wrong preprocess (difference > 0.02) before embedding the photos: the most common silent bug.
- `sweep` takes ≈ 3 min, `run` ≈ 2–3 min (SIFT on CPU), more on a busy machine.

## Class plan (two sessions of about 3 h 30)

- Session 1: 10 min Step 0 → 60 min Part A with the ✏️ checks → Steps 1–4 (60 min; show NAVERA's table after Step 4) →
  Steps 5–6 together (20 min: the sea and the score overlap) → Steps 7–9 (45 min; with 3 GPU slots, a class of 15
  queues ≈ 10 min: start trainings in waves, read §6 again meanwhile) → Steps 10–11 → badge.
- Session 2: 15 min recap (draw the chain on the board; the half pixel) → Steps 12–13 (40 min) → Step 14 (60 min, sweep
  while reading §9) → Steps 15–16 → discussion of the rules chosen in the class.
- Fast students: Going further (flatten vs average, top k). Struggling: the runner's `test` names each symptom; for
  TODO 8 give the paper plan (radius → if small: one fine step; else: one finder call, try the candidates; last: the
  circle).

## Data and files

- `make_dataset.py` (teacher only, ≈ 3 min with the GPU free): photos (render_view, map style, controlled effects),
  photos.csv/truth.csv, the DINOv2 index (reference preprocess), and `courses/23-locate-on-map/hidden/` (40 photos,
  queries.json with truth, priors σ 40/100/400 m, DINOv2's top-5 at σ 400 m and the σ 400 m candidate tiles,
  views64.npz). datasets/23 = 4.9 MB, hidden = 2.1 MB. The old datasets/23 (Wayback tiles, NAVERA bench photos,
  make_dataset.py visible to students) was removed.
- `check_values.py`: the expected values of checks 1–3, 6, 9, 10, 12 from the reference. `hidden_ref.py`: the
  reference's outcomes on the hidden photos and the hidden median of weight files.
- `my_tiles.pt` + `logs/my_tiles.pt.json`, `exp.pt` + `logs/exp.pt.json` (the --no-augment run), `out/run_csv.json`:
  the reference student's files. `assets/views.jpg` is `run_locate.py look` (photo p02), scaled to 75 %.
- Map data © OpenStreetMap contributors (README, lab, runner pictures). DINOv2: Meta AI, Apache-2.0.
