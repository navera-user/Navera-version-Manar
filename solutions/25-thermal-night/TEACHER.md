# Mission 25 — teacher notes

Not visible to students. Alignment, answer key, rubrics, data provenance, measured times, difficulties, class plan.

Two sessions: **Session 1 — Night watch** (Steps 0–7, badge **Night watch** = checks 1–9, milestone `night-watch`)
and **Session 2 — Night navigator** (Steps 8–18, badge **Night navigator** = all 19 checks). Round 1 (2026-10-15)
added Step 13, an ablation: the student turns OFF one of the author's design decisions (normalisation, augmentation,
ρ scaling) and measures it against their own network. Lesson Part A (§1–§5)
before session 1, Part B (§6–§9) before session 2. Owner decision §7.5 (2026-10-14): the student TRAINS a small
4-point homography network (HomographyNet-style) on thermal-like ↔ day pairs they cut from scenes rendered from the
OSM map, and compares it with NCC template matching (OpenCV), measured; NAVERA's STHN is described in words and
numbers only. The old mission 24-part-1 (NCC on NAVERA's replay frames, read live from NAVERA's data folder) is
replaced: the replay frames are now copied as DATA into `datasets/25-thermal-night/replay/` and audited.

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. What a thermal camera sees; audit a "thermal" dataset | §1 (shadows on "night" frames) | Steps 0, 2 | 7 |
| 2. NCC, template matching, where it fails across modalities | §2 (noon NCC 0.39; \|NCC\|) | Steps 1, 6 (TODO 1, 5) | 1, 5, 9 |
| 3. Footprint, coverage, preparing a frame, minimum height | §3–§4 (heading 90°; one warp) | Steps 3–5 (TODO 2–4) | 2, 3, 4, 8 |
| 4. 4-point network: outputs, input normalisation, loss, overfitting; train it, test a design decision, measured vs NCC | §6–§8 (pure shift; loss term) | Steps 8–14 (TODO 7–11, ablation) | 10–18 |
| 5. Motion gate and honest limits (distribution shift, strict loading, lock-in) | §5, §9 (gap; three things to measure) | Steps 7, 14–16 | 6, 9, 18, 19 |

## Data (made by `make_dataset.py`, deterministic; `check_values.py` makes the check's unit cases)

- **Scenes**: 160 × 160 px, 7.75 m/px (8 × the zoom-17 pixel at Sousse), 1.24 km, north-up, rendered twice with
  `render_view` ('pseudo'): the day reference (with its sun shadows) and a no-shadow render turned into a
  "temperature" picture by a material model (water, vegetation, asphalt, light roof, metal roof, soil; weights from
  colour; night / noon / dawn tables in the generator's docstring). It is **thermal-like, not thermal**: the lesson
  and the README say so. 293 train, 58 val (also noon and dawn), 54 test (→ 512 hidden pairs, never shipped),
  4 coast (≥ 50 % sea). Places on two 1.3 km grids; 3.9 km cells assigned to splits by hash; a scene within 1.3 km of
  a later split's scene is dropped (no shared ground). 25 MB total in datasets/25-thermal-night (20 MB) + hidden (11 MB).
  Rendering: 877 s with 3 workers on a busy Jetson (2026-10-14).
- **Flight**: 12 frames 640 × 512, 75° × 63° (render_view's square pixels: 2·atan(tan 37.5° · 0.8) = 63.1°), 20 m/s,
  3 s apart, heading ≈ 62°, 420–440 m except **frame 7 at 300 m** (refused). Priors are truth ± 60 m. Inside a val cell.
- **night_fixes.csv**: 25 m/s, heading 40°, ±5 m noise, a 238 m wrong match at t = 8 s (score 0.93, NAVERA's number),
  no fix 20–30 s, a 300 m wrong match at t = 32 s (score 0.91).
- **Replay frames** (NAVERA data, copied as data, 768 px wide): the 30 "thermal" frames are NAVERA's day frames
  shifted by 8 (night k = day k + 8 mod 30) and darkened (mean ≈ 10 grey levels, sun shadows visible), carrying the
  labels of other frames. 5 of the 30 label rows (frames 4, 18, 19, 20, 24) are empty in both CSVs; over the 20
  usable rows, night k's label (= day k's label) is **1.8–5.9 km (median 3.2 km)** from the place the frame shows.
  The validation report only says the set "cannot be used for night vision" (footprint); the darkened-copy finding
  was first measured for this mission and is logged as **NAVERA problem B14** (shared problems doc). Students
  rediscover it; do not tell them in advance. Never claim the imagery's source or place.
- Assets: `look.jpg` (val scene 20) by make_dataset; `thermal.svg`, `coverage.svg` from the old mission (edited:
  no NAVERA identifier), `corners.svg`, `homnet.svg` new.

## Answer key (numbers recomputed on the Jetson, OpenCV 4.x, torch 2.8, 2026-10-14)

- Step 0: any honest prediction. Typical: B easiest (shapes visible), D hardest (flat grey). The measurement (Step 6)
  shows the surprise: noon is no easier than night for NCC (22–25 % good), dawn is hopeless (2 %).
- Step 2 (`audit`): **TWIN_OF_NIGHT_01 = 9** (night k ↔ day k + 8, all 30); best NCC 0.853–0.932, **median 0.899**
  (AUDIT_BEST_NCC 0.90; the check accepts 0.893–0.905); median second best 0.098. Mean brightness night ≈ 6–22,
  day ≈ 90–180. Clues: NCC ≈ 0.9 (a real night frame of the same place: low or negative, lesson §2 example −0.33),
  sun shadows, labels 8 frames apart (night 1 labelled 35.8288, 10.6361 = day 1's place, but it shows day 9): over
  the 20 usable rows the labels are 1.8–5.9 km (median 3.2 km) from the place shown; 5 rows are empty (B14).
- Steps 3–4 (`coverage`, reference 495.8 m): lesson camera 84° × 68°:

  | height | 0° | 30° | 45° | 90° |
  |---|---|---|---|---|
  | 250 m | 0.618 | 0.607 | 0.603 | 0.618 |
  | 300 m | 0.816 | 0.781 | 0.769 | 0.816 |
  | 350 m | **0.952** | 0.896 | 0.883 | 0.952 |
  | 400 m | 1.000 | 0.956 | 0.947 | 1.000 |

  Minimum heights (85 %): lesson camera 312 / 333 m (0° / 45°); flight camera 75° × 63° 344 / 375 m (NAVERA: "from
  ~350 m"); first simulator camera 56.7° × 48° **474 / 524 m** (NAVERA: "only from ~480 m", above the 400 m
  ceiling: acceptance test R12, 3 October 2026). **COV_350_0 = 0.952**, by hand: 2·350·tan 42° = 630 m (> 495.8),
  2·350·tan 34° = 472.2 m → 472.2 / 495.8 = 0.952 (check ±0.003; 1.0 is named as "how HIGH is it?").
- Step 5 (`prepare`): coverage 0.937–0.960 for frames at 420–440 m; **frame 7 refused** (300 m, 0.669, "fly higher").
- Step 6 (`ncc`, 256 val pairs per condition, good = within 3 px): day vs day **1.00** (median 0.4 px); night
  **0.23** (14.3 px); night inverted **0.39** (8.8 px); noon 0.25 (12.2 px); dawn 0.02 (16.1 px). The check accepts
  ±0.015 (the shares are deterministic for a correct ncc_locate). Noon fails although C "looks like" A: the road is
  hottest, trees and water cool — another order, not a gain (lab read-after box).
- Step 7 (`gate`): refused **8, 34, 36, 38, 40 s**. 8 s: jump 256 m from the 6 s anchor, reach 90 m. 10 s accepted
  (103 m, reach 150 m: the anchor is still 6 s). 32 s accepted: 291 m from the 18 s anchor, reach 30 · 14 + 30 = 450 m.
  Then lock-in: 333 m in 2 s (max 90), 381 in 4 (150), 408 in 6 (210), 455 in 8 (270): the gap closes slowly
  (243 → 185 m), so the lock-in is temporary. NAVERA's night gate (base code, read only) compares with its OWN last
  accepted fix after GPS loss (reach = max speed × elapsed + margin), so it can lock in for a while too; while it
  dead-reckons between fixes it moves its anchor and restarts the clock, which can lengthen the wait.
- Step 8 (`pairs`): any; the label is 8 offsets; corners not H entries because of scale balance (lesson §6).
- Step 10: fc1's input "?" = 64 maps × 4 × 4 = 1 024 (the docstring no longer gives it); fc1 = 128 × (1 024 + 1) =
  **131 200** (131 072 without biases: the check names it). Per layer: conv1 304,
  conv2 4 640, conv3 18 496, conv4 36 928, fc1 131 200, fc2 1 032 = 192 600. PREDICT_PARAMS: fc1 (68 %).
- Step 11 (`train`, 16 000 pairs from 293 places, 8 epochs, batch 128, Adam 1e-3, seed 0): train loss 0.17 → 0.057,
  val loss 0.135 → 0.078; **val median centre error 3.8 px** (3.71–3.84 over runs; ≈ 30 m), corner error 4.5 px, 37–39 %
  within 3 px. GPU: **32–53 s** of training + 19 s to make the pairs (busy Jetson). Quick run (3 000 pairs, 3 epochs):
  a few seconds, loss 0.21 → ≈ 0.15. The check compares VAL_CENTRE_PX with the student's own
  `logs/my_homography.pt.json` (±0.05); the solution ships its record (`solutions/25-thermal-night/logs/`).
- Step 12 (overfit, round 1: 1 000 pairs from **3** places, 30 epochs, 12 s GPU): train 0.21 → 0.016; val 0.21 →
  minimum ≈ 0.159 near epoch 17, then 0.18; val centre error 7.1 px. Stop near epoch 17. Hidden pairs: 6.15 / 6.42 px
  (two runs) — still under 6.5, so check 15 also refuses any weights whose training log says < 50 places.
- Step 13 (ablation, 16 000 pairs, 8 epochs, GPU, one run each; baseline val 3.7–3.8 px): **(a) `--norm none` 5.08 px**
  (worse: gain and pale reference must be learned), **(b) `--no-augment` 3.60 px** (no worse: the author's
  augmentation is not justified by this measurement at 293 places — a good discussion), **(c) `--rho 1` 4.16 px**
  (slightly worse: targets 16 × too large for fresh layers). Seed noise ≈ 0.1–0.2 px. The check reads the run's log
  (ablation letter, ABLATION_PX ±0.05); the runner refuses to overwrite my_homography.pt with an ablation.
- Step 14 (`compare`, val places; median px / share within 3 px):

  | condition | prior | NCC | untrained | trained (reference) |
  |---|---|---|---|---|
  | night | 9.5 / 6 % | **14.5** / 24 % | 9.6 / 5 % | **3.7–3.8** / 37–39 % |
  | dawn | 9.5 / 6 % | 16.2 / 2 % | 9.6 / 5 % | 9.4–10.0 / 5 % |
  | noon | 9.5 / 6 % | 13.1 / 22 % | 9.6 / 5 % | **11.8–12.1** / 6–7 % |
  | coast | 9.5 / 5 % | 17.7 / 0 % | 9.6 / 6 % | 7.7–8.4 / 16 % |
  | shift 22 px | 17.2 / 1 % | 20.7 / 18 % | 17.3 / 1 % | 12.4–12.6 / 14 % |

  NCC_NIGHT_PX = 14.5 (check ±0.3); NET_NIGHT_PX and NET_NOON_PX are recomputed by the check from the student's own
  my_homography.pt on the same pairs (hidden/compare_pairs.npz) — ±0.3 px.
- Step 15 (`sabotage`): **MISSING_KEYS = 12** (12 unexpected); strict=False → no error, median 9.6 px (= untrained,
  = prior); strict=True → RuntimeError "Missing key(s) in state_dict". NAVERA: refuses to start if the weights do
  not load (validation report).
- Step 16 (`fly`): network median **25–26 m** over 11 frames (priors 10–77 m, NCC 85–198 m); frame 7 refused; every
  fix passes the gate. The check accepts 3–80 m.
- Hidden test (check 15): 512 night pairs from 54 test places: reference net **3.42 px**, prior 9.55, NCC 16.53; pass
  ≤ **6.5 px** and trained on ≥ 50 places (from logs/my_homography.pt.json, when present). The CPU recipe (3 000
  pairs, 6 epochs) gave **5.78 / 5.95 / 5.86 px** (seeds 0/1/2, expert): it passes with 0.55–0.72 px of margin; batch
  32 gives 5.64 px (858 s): not worth a new option.

## Rubric for the written answers (the check only catches empty or off-topic answers — say so to students)

| Item | 2 — good | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_AUDIT | darkened day frames; ≥ 2 clues among NCC ≈ 0.9 vs ~0.1, sun shadows, labels 8 frames off | "not thermal" with one clue | restates the table |
| EXPLAIN_COVERAGE | corners of the square outside the turned rectangle; 474–524 m > 400 m ceiling → never | one of the two | numbers only |
| EXPLAIN_NCC | NCC undoes gain/offset only; night reverses some materials but not others (non-monotonic); inversion fixes only the reversed ones | "different sensors" without why | — |
| EXPLAIN_GATE | reach 90 m at 8 s; 14 s gap → 450 m reach; wrong anchor → later truths refused (lock-in) | two of three | — |
| EXPLAIN_CORNERS | 8 = (x, y) offsets of the 4 corners in px; H's entries have very different scales, corners are balanced/bounded | meaning only | — |
| EXPLAIN_NORM | AGC/gain/offset meaningless, pale reference, per channel; + 1 protects uniform patches (sea) from amplified noise | one part | — |
| EXPLAIN_OVERFIT | train ↓ to ~0.02, val minimum ~epoch 17 then ↑; 3 places memorised; stop at the minimum | curves without why | — |
| EXPLAIN_ABLATION | compares with their OWN error (number); why the choice matters (gain / variety / target scale), or honestly that it did not (b); one run vs seed noise | comparison without why | — |
| EXPLAIN_LEARNED | trained on nights only (distribution shift), confident anyway; real thermal frames with truth, seasons, weather, terrains | one part | — |
| EXPLAIN_STRICT | strict=False loads nothing silently, random weights still answer; NAVERA now refuses to start (LOC-6) | one part | — |

## Measured cost (Jetson Orin Nano 8 GB, shared, 2026-10-14)

- GPU training 16 000 pairs × 8 epochs: 32–53 s (34 s alone in a test harness); pair making 12–19 s on the CPU.
  GPU memory: **139 MB allocated, 220 MB reserved** (torch.cuda.max_memory_*), plus the CUDA context; the whole
  process peaks at **1.4 GB RSS** (Jetson memory is shared CPU/GPU; the 16 000 pairs are 131 MB of uint8 and stay
  on the CPU, batches go to the GPU). Model 192 600 parameters, weights file 0.8 MB.
- CPU (2 threads): 3 000 pairs × 6 epochs = **664 s** quiet, **~1 300 s** with 3 trainings at load ~20 (expert,
  2026-10-14). The 656 k variant of the network (first design) took 63 ms per pair-step and was dropped.
- Ablation runs: 33–51 s each on the GPU. Overfit run (3 places): 12 s.
- Check: ≈ 25 s on a quiet Jetson; **104–116 s** at load average 26 (3 CPU hogs, 2026-10-15, after the round-1 fix:
  torch at 1 thread in check 14, in the checker AND the student's process; before it, 160–210 s and a 120 s time-out
  in check 14 — the flaky 17/18). `check_timeout_s` 420. It never retrains a real network: check 14 runs a few CPU
  epochs on 96 pairs; my_homography.pt is loaded with weights_only=True into a network the check builds.

## Mutants (wrong-but-plausible code; round 1 rerun 2026-10-15, see r1_fixes.md for every message)

ncc without the means; footprint in degrees / half size; coverage with full sizes / heading in degrees; prepare turned
the wrong way / without `need` / with the corner-based centre; ncc_locate returning the top-left corner / the
unnormalised mode; motion_gate with a negative elapsed time / with the constants instead of the arguments; cut_pair
inverted / with a 64-px SQUARE; to_input by std alone / with global statistics; HomographyNet with a final ReLU /
without the fc1 ReLU; offsets_to_H inverted / ignoring `side`; train without / RHO_PX, with the validation loss
measured before the epoch, **without `opt.zero_grad()`** (round 1: 3 one-batch epochs compared with 3 plain Adam
steps, solution 2.9e-5, mutant 2.2e-3, threshold 3e-4), **validation targets not / RHO_PX**; prepare with **one
scale** for x and y, **mirrored** turn (round 1, from the weak student). Each fails a named check with a specific
message; the runner's `test` catches most of them locally too.

## Difficulties to expect (author's estimate — not yet tested with students)

- Coverage: students compare with full sizes (1.0) or forget radians (right at 0°, wrong at 90°).
- prepare: the direction of the turn (picture y down) and one scale for x and y (weak reviewer: 50 min); the runner's
  "heading 90°" and "90° × 40°" lines name them.
- `GATE_REFUSED` as a list; students copy only the first refusal.
- cut_pair: warping from SQUARE to the corners (the inverse).
- The GPU queue: with more than three trainings at once the runner waits up to 10 min, then uses the CPU; tell
  students to start Step 11 early, or to use the CPU recipe.
- The lesson is long (≈ 5 300 words with tables and answers; the weak reviewer read it in ≈ 1 h 55): Part A before
  session 1, Part B before session 2.
- Validation targets not divided by RHO_PX: val loss ≈ 50; the runner now prints a ⚠ line.

## Class plan (2 × 3 h)

- Session 1: 15 min hook (LOC-6, the replay audit question); Steps 0–2 together; pairs for Steps 3–5; demo of a
  wrong turn in prepare; Steps 6–7; 10 min debrief on lock-in (missions 29–30 will fix it with the arbiter).
- Session 2: 10 min recap of mission 21's training loop; Steps 8–11 (start the training by minute 60); Step 12 while
  waiting; Step 13 (ablation: assign a, b, c to thirds of the class and compare on the board); Steps 14–16; 15 min
  discussion "what would we need to validate night vision?" (NAVERA's not-validated list).
- Fast students: Going further (two passes; dawn/noon training; NCC on gradients). Struggling: give the Method A grid
  for coverage and pair them for prepare; the report can be shortened to sections 1 and 3.
