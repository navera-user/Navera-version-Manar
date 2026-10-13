# Mission 19 — teacher notes (Lens calibration: fisheye models and Zhang's method)

Teacher only. Rebuilt 2026-10-13 on NAVERA Lite. The student writes `navera_lite/fisheye.py` (reference in
`solutions/_navera_lite/navera_lite/fisheye.py`, tags `# @part 19 todo 1–8`; given: `load_calibration`,
`save_calibration`, `theta_d_of`, `find_corners`, `calibrate_robust`, `BOARD`, `SQUARE_M`, `CRITERIA`) and uses the given
CLI `navera_lite/tools/calibrate.py` (`python3 -m navera_lite.tools.calibrate`, built on the student's `board_points`
and `calibrate_fisheye`). Reused finished: `camera.K_from_hfov` (18) and `rotations.py` (16, import closure).
**fisheye.py is a new part file**, not an extension of camera.py (camera.py is mission 18's and stays as it is).
No NAVERA code: the old `compare_navera.py` and the run of NAVERA's calibration tool are gone; the oracle is OpenCV
(`cv2.fisheye.projectPoints` in `run_lens.py project`, the check's references) and the course's own reference.

Recompute everything:
`python3 tools/lite_build.py 19-calibration`;
`python3 solutions/19-calibration/make_dataset.py` (needs the bench recording `~/.navera_sim/bench_2026-10-06/calib`,
host only; writes the 36 views, the yaml, README and `courses/19-calibration/hidden/corners.npz`);
`python3 solutions/19-calibration/make_assets.py` (coverage.png, before_after_small.jpg);
`python3 solutions/19-calibration/check_values.py` (every check constant and the values of typical mistakes);
then the lab commands with `tools/try_lesson.py 19-calibration --solution --shell "…"`.
`solutions/19-calibration/my_calib.yaml` is the CLI's output (the check needs it with --solution).

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 implement the fisheye model; a pixel's angle | §1, §2 (worked example, 🧰 polynomial), §3 (inverse; 🧰 bisection in lab Step 3) | Steps 0–3 (TODO 1, 2; STEP2_*, PINHOLE_GAP_PX, PIXEL_ANGLE_DEG) | 1, 2, 5 |
| 2 reprojection error; where a calibration is valid | §3 (coverage figure, extrapolation), §7 | Step 3 (EXPLAIN_TURN_BACK), Steps 7–8 (TODO 7, detective, FARTHEST_USED_DEG), Step 10 (REASON_BC) | 5, 9, 11, 12 |
| 3 calibrate and test on unseen views | §6 (Zhang), §7 (hold-out), §8 (OpenCV) | Steps 6–11 (TODO 5, 6, 8; stability; hold-out; CLI; REASON_FX) | 7, 8, 10, 11, 12, 13 |
| 4 justify the straight view's width | §4 (straightening), §5 (f_new, stretch, the 111° rule) | Steps 4–5 (TODO 3, 4; H_MAX_*, STRETCH_EDGE_111, EXPLAIN_FOV, bends), Step 11 (REASON_HFOV), memo | 3, 4, 6, 12, 13 |

Badges: **Lens modeller** = checks 1–6 (session 1), **Calibrator** = all 13. Times: reading 90 min (up to 2 h at B1),
lab 4 h–5 h 30 (strong ≈ 3 h 35 measured, weak ≈ 6 h); meta.json says 6 h 30 in total; a weak student needed ≈ 8 h 15.

## Answer key

| Item | Value | Where it comes from |
|---|---|---|
| PREDICT_EDGE (ungraded) | pinhole tan 80°/tan 40° = 6.76; fisheye 2 | not in the lesson (it uses 55.5°/83°) |
| STEP2_U / STEP2_V | 331.98 / 482.88 (±0.02) | fisheye_project((−1.6, 0.4, 1.4)); pinhole (182.22, 523.77) caught |
| PINHOLE_GAP_PX | 155.2 (±0.15) | at 49.7° off-axis; the lesson's example is 19.3 px at 29.2° |
| PIXEL_ANGLE_DEG | 47.82 (±0.03) | pixel (1500, 100): a' 0.8523, b' −0.3017, θ_d 0.9041 → 0.8345 rad. fx for both 48.26 (caught), θ_d in degrees 51.80 (caught), radians (caught) |
| PREDICT_STRETCH (ungraded) | 2.51 | the lesson's table hides it ("lab Step 4") |
| STRETCH_EDGE_111 | 2.51 | `run_lens.py stretch`; 1/cos²(55.5°) = 3.12 caught |
| H_MAX_DEG | 110.94 | 2·atan(960 / 660.48); half 55.47 caught |
| H_MAX_PARTNER_DEG | 121.28 | 2·atan(960 / 540); half caught |
| BEND_BEFORE_PX / BEND_AFTER_PX | 5.12 / 0.63 (±0.05) | `run_lens.py straighten` (f0216, worst row/column, cv2.fitLine) |
| PREDICT_FX (ungraded) | 670.3 (higher) | |
| MY_FX / MY_RMS / VIEWS_USED | 670.28 / 0.506 / 34 | `calibrate_lab.py calibrate`; 660.5 (bench) caught |
| REFUSED_VIEWS | ["f0023", "f0208"] | the two views reaching farthest right: 44.6° and 51.8°, columns up to 1468 / 1566 |
| FARTHEST_USED_DEG | 43.0 (±0.15) | f0323; 51.8 (refused view) caught |
| WORST_VIEW | "f0022" | 0.818 px |
| PREDICT_STD (ungraded) | 38.9 / 3.4 | |
| FX_STD_8 / FX_STD_30 | 38.9 / 3.4 (±0.3) | `stability`, seed 19, 10 draws: 8 → 686.4 ± 38.9 (3 failed), 12 → 678.7 ± 14.0, 20 → 667.0 ± 4.7 (1 failed), 30 → 669.7 ± 3.4 |
| TRAIN_RMS / TEST_RMS | 0.474 / 0.567 | `holdout`: test = every 5th view (f0022, f0080, f0090, f0114, f0216, f0252, f0286, f0323); train 28 → 24 used (f0081, f0111, f0208, f0023 refused), fx 670.1; swapped caught |
| BC_TEST_RMS | 0.570 | Brown–Conrady: train 0.541 (28 views), fx 752.3; on all 36: RMS 0.545, fx 737.7 |
| CLI_HFOV_DEG | 110.15 | computed BEFORE running the tool: 2·atan(960 / 670.28); the check compares it with the student's my_calib.yaml; 110.94 (bench fx) caught |

Lesson numbers (all recomputed, `~/academy-test/review/19-calibration/build/*.py` during the build, and
`check_values.py`): tan 55.5° 1.455, tan 83° 8.144, ratio 5.6; f 600: 346 / 1039 / 3403 px; worked example
(1.0, 0.5, 2.0) → (1250.35, 488.75), pinhole (1267.30, 498.01), 19.3 px; θ_d(0.8) 0.862 → 569 px (ideal 528, pinhole
680); curve top 67.39°, θ_d 1.2492, 825.1 px; edges 937.1 / 982.9 px (ideal FOV 166.5° × 42.8°); corners up to 52.1°
(bench session, with f0208); worked pixel (300, 200) → 51.2°; (100, 270): θ_d 1.269 → nan; straight 111° view samples
fisheye columns 229–1645, rows 30–604 (7 % black, bottom); stretch at 30° (111°) 1.212 (θ_d′ 1.099, 1/cos² 1.333);
table 111/150/166°: f_new 659.79 / 257.23 / 117.87, centre 99.9 / 38.9 / 17.8 %, at 30° 1.21 / 0.47 / 0.22, edge 2.51 /
nan / nan; VFOV 44.5 / 92.8 / 132.8°; H_max 110.94°; fx 800 on 1280 → 77.3°; 150 m footprint 436 m, GSD 0.227 m;
RMS example 0.87 (mean 0.83); unknowns 20 views 128 / 2160; hook: the whole picture scaled by 2/3 (top lens 1280 × 360),
its middle pixel (640, 180) believed 27.0° off-axis, really 4.3° (true source (960, 270)): 27.7° between the rays,
150·tan 27.7° = 78.7 m. (A reviewer's 27.83° is another scenario: one lens at 1280 × 720, pixel (640, 360) — not the
Insta360's two-half picture.) Straight 111° view: columns ≈ 225–1645 used (≈ 225 px left, ≈ 275 px right unused);
vertical centre detail 659.8/721.4 = 91.5 %; calibration valid up to 2 × 67.4° = 134.8° (crop.svg).

Why the student's fx (670.3) is not the bench's (660.5) — measured on the host from the bench recording: the bench
calibrated 39 original top halves, OpenCV refused f0023, 38 used → fx 660.48, RMS 0.5245 (exactly the bench file).
The course's 36 originals (no f0273/f0274: faces; no f0309) → fx 670.24, nothing refused; re-encoded as the dataset →
670.28, f0023 and f0208 refused, RMS 0.506. Removing f0309 alone gives 662.3. So: **the set of views** (3 left out, and
which ones OpenCV refuses) moves fx by ~10 px; JPEG re-encoding moves the corners by 0.01 px median (0.17 px max) and
fx by 0.04 px but changes which views are refused and the RMS. fx and the board distance trade against each other, so
the RMS cannot tell 660 from 670. Step 9's 30-view subsets range 664.8–675.1 px and never reach 660.5 (≈ 2.9 σ):
the view set matters more than the RMS shows. Accept: the view set (3 left out; the subsets never reach 660.5) +
fx poorly determined (spread, trade with distance). JPEG re-saving and the 2 refused views are *measured* to change
fx by 0.04 px each: score them 1 (partial) and show the lab's reveal box. The check requires both ideas (keywords
for "views left out / not the same views" and for "spread / subsets / distance"); "jpeg" and "refused" alone do not
pass.

NAVERA figures quoted: bench calibration 2026-10-06 (data: `insta360_top.yaml`, 38 views, RMS 0.525, fx 660.48,
fy 721.40, out_hfov 111); live camera refuses another resolution / another USB camera and straightens before day
vision (ARCHITECTURE.md §5); "not yet measured with NAVERA's camera" (VALIDATION_STATUS.md, 2026-10-03, day vision);
Release 0.2. The 110.94° cap and the tool's behaviour (three flags, drop refused views, file keys, camera identity)
are described in words from reading NAVERA's code; no code shown.

## Rubric for written answers (the check only verifies "written and on topic")

| Item | 2 — good | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_TURN_BACK | fitted on corners ≤ ~52°; beyond, the polynomial extrapolates (4 numbers, no data), so it may bend back; a real lens is monotonic | "the polynomial goes down" without why | — |
| EXPLAIN_FOV | 111°: f_new ≈ fx keeps ~100 % centre detail; 150°: 39 %, edges beyond the valid model (75° > 67.4°); matching needs centre detail | one number, or coverage only | "wider is better" |
| EXPLAIN_RESIDUAL | calibration RMS ~0.5 px + detector noise + non-flat screen (+ interpolation) | one cause | — |
| EXPLAIN_REFUSED | farthest-reaching views (44.6°, 51.8°, far right) with no other corners there → pose ill-conditioned; refusing them leaves no corner beyond 43° (edges unmeasured) | "they are blurred / bad" | — |
| EXPLAIN_STABILITY | RMS ~0.5 for every subset, yet fx spread 39 → 3 px: RMS hides it; take ≥ 30 varied views | numbers without conclusion | — |
| REASON_BC | test corners lie within ~43°, where both models fit the corner pixels (each with its own fx, principal point and board poses, so their angles differ by 1–3° inside the data); the hold-out does not test the edges, where BC runs away towards tan 90° (its angle curve flattens near 60° in my_curves.png) | one of the two | "BC is better" |
| REASON_FX | the view set (3 left out; subsets never reach 660.5) and fx poorly determined (spread, trade with distance) | one of those, or JPEG / refused views (measured 0.04 px each) | — |
| REASON_HFOV | the rule f_new ≥ fx; larger fx → 2·atan(960/670.3) = 110.15° | rule without the number | — |
| report.md | three sections with numbers; validity limits; a recommendation with checkable limits (views to 60°, RMS and hold-out limits, fx stability, recalibrate on resolution/crop/camera change) | numbers without reasoning | — |

## Typical mistakes (verified on 25 mutants: runner `test` line and check message)

| Mistake | Runner shows | Check says |
|---|---|---|
| θ = atan2(b, a) | [[1220.65, 472.53]] "angle from the AXIS" | differs by 2.75e4 px |
| lens polynomial missing (r = f·θ) | [[1238.19, 482.11]] "θ_d missing" | differs by 30.5 px |
| no r = 0 guard | axis point [nan, nan] | "a point ON the optical axis gives nan" |
| fx used for v | "u is right, v is not" | same |
| cv2.fisheye.projectPoints inside TODO 1 | passes the runner | "calls OpenCV's projection: write the five steps" |
| bisection on [0, π/2] (no top) | 1.3 → 1.5708 "return nan … never type a number" | "past the top of this lens' curve" |
| top hard-coded (1.2492) | "another lens" lines ✘ | another lens (D3): ✘ |
| stretch_at with degrees inside | "About 0 or negative? θ is still in degrees" | ✘ value |
| degrees returned / None instead of nan | "in DEGREES" / "= None … nan" | same |
| stretch without lens slope / θ_d/θ / no nan | 1.702 / 1.602 / −10.16 | "left out the lens' slope" / "θ_d/θ" / "must be nan" |
| undistort with K (not K_new) / (h, w) / BORDER_REPLICATE | centre from column 960 / shape (1920, 540, 3) / bottom row coloured | 7.7 grey levels / shape / "must stay BLACK" |
| board order column-major / float32 | "column index must change FASTEST" / dtype | same |
| no CHECK_COND / catching cv2.error / no FIX_SKEW | "⚠ no view refused" in `calibrate` / "returned None" / skew −0.278 | "refused nothing" / "do not catch" / "skew K[0, 1] = −4.35" |
| mean of per-view RMS / no sqrt / O @ R | 0.5 / 0.25 / 93.7 | "mean … is not the RMS" / "MEAN SQUARE" / "corners placed in the camera frame" |
| hold-out: solvePnP on raw pixels | 13.2 px | "the poses are wrong — undo the lens first" |

TODO 7/8 checks first verify fisheye_project and reprojection_rms ("fix check 1 / 9 first"), so a TODO 1 bug is not
reported as a hold-out bug. Expected values are constants (or OpenCV computed inside the sealed check); test input
corners in `hidden/corners.npz`.

## Difficulties to expect

- **K0 is ignored** by cv2.fisheye.calibrate without CALIB_USE_INTRINSIC_GUESS (verified: any K0 gives the same
  result; OpenCV starts from f = max(w, h)/π and the picture's centre). If a student asks why K0 = I works, that is why.
- **Brown–Conrady's fx (738–752 px)** is not comparable with the fisheye's: another model, its own principal point
  (cx 920.9, cy 354.9) and board distances. `curves` now plots the angle of the same pixels (row through the student's
  principal point): inside the data the models differ by 1–3°, beyond it the fisheye has no answer and BC flattens.
- **Radians vs degrees** (θ, stretch_at) and **(width, height) vs img.shape** — the runners name both.
- The **r = 0** case: most students divide directly; the runner's second TODO 1 line catches it.
- **Bisection on a curve that turns back**: weak students search [0, π/2]; insist on the paper plan of Step 3.
- **fx vs fy** when going back from a pixel (PIXEL_ANGLE_DEG).
- TODO 8 is the least guided: draw "unseen view → pose (undistortPoints + solvePnP, K = I) → reprojection_rms" on the
  board if many are stuck; hints 1–4 lead there.
- Detection takes ~30 s (`detect`), `stability` ~30 s: tell students to wait, not to rerun.
- Expect the question "why is my fx not 660.5?" — it is the point of Step 11; do not answer before they run Step 9.

## Class plan (2 sessions of about 2 h 30, plus reading)

1. Before session 1: lab Step 0, lesson §1–§3 (40 min). Session 1: 10 min on the hook (27.7° → 79 m); Steps 1–5;
   badge **Lens modeller**. Fast: "Fewer numbers" later, or §6 early.
2. Before session 2: lesson §4–§8 (35 min). Session 2: Steps 6–11, 15 min group discussion of REASON_FX (show the
   "Why the student's fx" paragraph above), memo; badge **Calibrator**.

Differentiation: fast — "Zhang by hand" (ZHANG_FX), "Fewer numbers" (FIX_K3/K4); struggling — pair on TODO 2 and 8
with the paper plan first, give the 🧰 boxes printed.

## Notes for later missions

- Mission 20 (live camera) can reuse `fisheye.load_calibration` and `undistort` (finished from 20 on) and the
  dataset's `insta360_top.yaml` (latency_s 0.138 is in that file).
- Lesson 18 says "the part grows: mission 19 adds the fisheye lens" about camera.py; with fisheye.py as its own part,
  that sentence should read "mission 19 adds the fisheye lens (fisheye.py)".
