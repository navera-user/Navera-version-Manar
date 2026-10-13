# Mission 18 — teacher notes (The camera as a measuring instrument)

Teacher only. Rebuilt 2026-10-13 on NAVERA Lite (`navera_lite/camera.py`, reference in
`solutions/_navera_lite/navera_lite/camera.py`, tags `# @part 18 todo 1–8`; given: `R_BODY_NADIR_CAM`,
`camera_rotation`, `camera_rotation_hpr`, `off_nadir_deg`, `warp_point`; needs mission 16's `rotations.py`,
shipped finished). Only the mission-18 functions: fisheye is mission 19, timing/attitude mission 20.
No NAVERA code: the old `compare_with_navera.py` (NAVERA's camera model and matcher) is replaced by
`compare_with_opencv.py` (cv2.projectPoints, cv2.undistortPoints, cv2.findHomography, cv2.warpPerspective).
The old photos (cut from the Esri satellite map) are replaced by OpenStreetMap renders (`make_dataset.py`, ray
traced with the lesson's model; truth in `truth.json`, teacher only).

Recompute everything: `python3 tools/lite_build.py 18-camera-model`, then
`python3 solutions/18-camera-model/make_dataset.py` (photos, ~1.5 min), `lesson_numbers.py` (every lesson
number), `check_values.py` (check constants and the values of typical mistakes), and the lab commands with
`tools/try_lesson.py 18-camera-model --solution --shell "python3 measure_pad.py"` etc.

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 project with K and a pose; back-project onto flat ground | §1 frames, §2 pinhole/K (worked 1), §3 (worked 2, 🧰 third column) | Steps 0–3 (TODO 1–4, CENTRE_ROLL, EXPLAIN_T), Step 5 (photo T, own what-if computations), Step 10 (OpenCV) | 1, 2, 3, 6, 7, 14 |
| 2 footprint, GSD, a height from a known object | §4 | Step 4 (TODO 5, A, C), Step 6 (TODO 6) | 4, 5, 7, 8, 11 |
| 3 height error → scale error; attitude error → position error | §5, §6 | Step 5 (level assumption), Step 7, Step 8 (TODO 7, attacker) | 7, 9, 11, 12 |
| 4 straighten with K·R·K⁻¹; what it needs and cannot fix | §7 | Step 9 (TODO 8), Step 10, Step 11 memo | 10, 13, 14, 15 |

Badges: **Measurer** = checks 1–7 (session 1), **Straightener** = all 15.

## Answer key

| Item | Value | Where it comes from |
|---|---|---|
| PREDICT_TILT (ungraded) | behind (south), 53.6 m | 200 · tan 15° |
| VFOV_INSTA_DEG | 44.51 | f = focal_px(111, 1920) = 659.79; 2·atan(270/f). 22.26 = forgot the 2 (caught); 111 = HFOV (caught) |
| MAST_LEAN_PX | 37.7 | foot (608.0, 190.0), top (640.0, 170.0): √(32² + 20²) = 37.74. 32 or 20 alone caught |
| CENTRE_ROLL_E_M / _N_M | −62.41 / −17.58 (±0.3) | own backproject_ground, 200 m, hdg 40, pitch −15, roll +10, pixel (480, 270); swapped caught |
| EXPLAIN_T | world → camera needs the inverse = transpose; back-projection goes camera → world = R_wc | graded on topic |
| CENTRE_BEHIND_M | 53.59 | `run_camera.py centre`, −15° line (north −53.59); negative sign caught |
| HEIGHT_A_M / HEIGHT_B_M | 134.0 / 261.8 | pads 43 px / 22 px, h = 480 · 12 / px; true 135 / 260 m (truth.json) |
| HEIGHT_B_RANGE_M | 23.9 | ±1 px: 250.4 to 274.3 (A: 130.9 to 137.1, 6.2 m); 11.95 = half range (caught) |
| PAD_T_E_M / PAD_T_N_M | −17.9 / −66.0 | mask centre (600.1, 321.8); truth (−18, −66) |
| LEVEL_ERROR_M | 45.9 | student computes it: same pixel, camera_rotation_hpr(40) → (20.8, −41.4) |
| HEIGHT_SHIFT_M | 8.04 (±0.15) | same pixel, 150 m instead of 170 m → (−15.8, −58.2); = 20/170 × 68.35 m because the ground point scales with h for a fixed ray; 20 caught |
| TODO C height_from_size | (1000, 12, 40) → 300; (659.79, 4.5, 18) → 164.95 | inverted forms 3.33 / 0.48 caught |
| PREDICT_AREA (ungraded) | 1.92 | |
| AREA_RATIO_30 | 1.92 | 97 405 / 50 625 m² (`run_camera.py footprint`; also −10°: 54 063, −20°: 66 466); 0.52 inverted (caught) |
| SCALE_PLATEAU / VERDICT_PLATEAU | 0.60 / "refused" | predicted 520 − 120 = 400 m, true 520 − 280 = 240 m; 1.67 inverted (caught) |
| HEIGHT_FROM_SCALE_M | 324.0 | 300 × 1.08; 277.8 = divided (caught) |
| ATTACK_DTILT_DEG / ATTACK_DTILT_35_DEG | 6.60 / 4.36 | bisection on 250·(tan(θ+δ) − tan θ) = 30. Small-angle formula gives 6.74 / 4.61 (caught); level camera atan(30/250) = 6.84 (caught) |
| PREDICT_STRAIGHT (ungraded) | ≈ 34 px, ≈ (429, 456) | 12 / gsd(170) = 33.9 px; from Step 5's position (same question in lab and answers.py) |
| STRAIGHT_PAD_PX | 35 (check accepts 34–36) | `run_camera.py straighten`: centre (429.2, 456.5); the under-drone point (522.0, 149.9) → (480.0, 270.0) |
| STRAIGHT_PAD_E_M / N_M | −18.0 / −66.1 (±0.4) | (u − 480)·0.35417, −(v − 270)·0.35417 = −17.99 / −66.05; positive N caught |

Lesson numbers (`lesson_numbers.py`): lesson camera 1280 × 720, f = 800 → HFOV 77.32°, VFOV 48.46°; Insta360
straightened f 659.8; narrow 30° on 1920 → 3 582.8, VFOV 17.14°; worked 1 → (800, 120); check f(70°, 1 600) =
1 142.5, VFOV(900) 43.0°; X_c (−20, 10, 200) → (560, 400); worked 2: 120 m, 20° → slant 127.7 m, 43.7 m behind,
edges 8.9 m ahead / 116.8 m behind; nadir footprint 192 × 108 m; table 0/−15/−30°: areas 20 736 / 23 693 /
36 714 m², centre 0 / 32.2 / 69.3 m behind, far edge 54 / 98 / 166.6 m behind, width 192 / 226 / 299.5 m; GSD
Insta360 150 m 0.227 m/px; Sousse z18 0.484 m/px, ratio 0.47; oblique GSD 120 m, 20°: 0.160 / 0.170 m; car 30 px
→ 120 m, 31 px → 116.1 m; bus 40 px, f 1000 → 300 m (307.7 / 292.7); mountain 300/1800 = 0.17; tilt error 150 m,
10°, 1° = 2.708 m (linear 2.699, nadir 2.618); 185·tan 8.6° = 28 m; 300·tan 2° = 10.5 m; worked 3 (pitch −10°):
centre → (640, 501.1), under-drone (640, 218.9) → (640, 360); roll 8° check → (527.6, 360).

NAVERA figures quoted (all from VALIDATION_STATUS.md, Release 0.2): straightened 33/33 within 2.6 m, median
1.1 m vs 28 m median and 1 wrong without straightening (offline, 2026-10-02, SIMULATED camera over the map's own
imagery — the report calls it optimistic; tilts ≤ 12°, 120–250 m, IMU bias). The lesson's "8.6° at 185 m" is
labelled an illustration (back-solved, no document gives it); heights
+40 %: 0/33 → 27/33 with the altitude window, height within 0.4 %; local matching 2026-10-01: ±15 % scale gate,
≥ 6 inliers, wrong accepted 1 → 0 with the scale check. Pipeline facts (straightening, 45° limit, height
sources) from ARCHITECTURE.md §5. The Insta360 calibration (fx 660.5 / fy 721.4) is a FISHEYE model: the lesson
no longer equates it with the pinhole f = 659.8 of the 111° view (that closeness is a coincidence).

## Rubric for written answers (check only verifies "written and on topic")

| Item | 2 — good | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_MAST | top is closer (smaller depth, 120 m vs 150 m), so the same offset is divided by less → farther from the centre; flat-ground model misplaces raised points | one of the two | "perspective" only |
| EXPLAIN_TILT | camera fixed to the body; nose down turns the belly/optical axis backwards; h·tan θ | direction right, no reason | "ahead" |
| EXPLAIN_PIXEL | pad smaller in px at B (22 vs 43), so ±1 px is a larger fraction (≈ 4.5 % vs 2.3 %) | "B is higher" only | — |
| EXPLAIN_LEVEL | ignores pitch/roll: rays turned, ≈ 46 m off; needs the attitude at the exposure (IMU) to back-project or straighten | names the attitude only | — |
| EXPLAIN_FOOTPRINT | far edge seen at a longer slant range, so a fixed angle covers more ground (perspective) | "it is tilted" | — |
| EXPLAIN_ATTACK | ground distance h·tan θ grows faster at large θ (slope 1/cos²θ): same error costs more | "tilt makes it worse" without why | — |
| EXPLAIN_STRAIGHT | same centre, pure rotation: rays only turn, K·Rᵀ·R·K⁻¹ maps pixel rays without depth; metres then need h and flat ground | one of the two ideas | — |
| report.md | three sections with the numbers and a clear "needs attitude / needs height" conclusion | numbers without reasoning | — |

## Typical mistakes (all verified on mutants: runner `test` line and check message)

| Mistake | Runner shows | Check says |
|---|---|---|
| degrees in tan (focal_px / gsd) | −99.9 / 0.337 | "math.tan got DEGREES" |
| whole angle instead of half | 369.5 | "you used the whole angle" |
| K transposed (cx in the bottom row) | ✘ K line | "cx and cy belong in the LAST COLUMN" |
| project with R_wc instead of R_wc.T | [819.4, 451.7] on the tilted line (level line passes!) | "world → camera needs the TRANSPOSE" |
| project without − C | None on the level line | "did you subtract the camera centre C?" |
| no depth test | [480, 270] for a point above | "behind it … return None" |
| backproject with R_wc.T | [−6.99, 21.31] | "R_wc @ (not R_wc.T @)" |
| backproject ignoring C | ✘ on the shifted-camera line | "X = C + λ·d" |
| no sky test | a number instead of None | "return None when d[2] ≥ 0" |
| footprint corner order | ✘ footprint line | "right four corners, wrong order" |
| tilt error small-angle / h·δθ | 1.799 / 1.745 | "small-angle formula" / "ignores the tilt" |
| homography rotations swapped / not scaled | [[1.398 …]] / H[2,2] 1.024 | "two rotations are swapped" / "not scaled" |
| pad width without +1 / rows / (row, col) centre | 10 / 3 / (3.0, 14.33) | "+1" / "number of ROWS" / "swap them" |

25 mutants (round 1: + pitch-sign rotations.py, fake ALL MATCH, inverse homography, `R_wc.T @ X − C`, K as a list,
inverted TODO C, degrees in TODO 7), all caught by check.py; the runner names the symptom and the hint to open.
Check 14 compares `camera_rotation_hpr` with the conventions (catches a changed rotations.py) and verifies the
sha256 of the shipped `compare_with_opencv.py`: **if you edit that file, update `COMPARE_SHA256` in check.py**
(`sha256sum courses/18-camera-model/files/compare_with_opencv.py`). The oracle builds its own R with
cv2.Rodrigues (part 0), so "fly your own rotations" can fail.

## Difficulties to expect

- **R vs Rᵀ** is the classic. The level, nose-north camera has a symmetric R_wc, so the mistake hides until a
  tilted camera: say it in class before Step 2.
- **Behind, not ahead** (Step 0): most predict "ahead". Draw the side view on the board after the lab's Step 3.
- **(u, v) vs img[row, col]** in TODO B.
- Students who skip `np.asarray` get "unsupported operand type(s) for -: 'list'": the runner adds the fix.
- Step 8 needs a loop in a small script: the 🧰 box shows the pattern; weak students may need the teacher.

## Class plan (2 sessions of about 2 h, plus reading)

1. Before session 1: lab Step 0, lesson §1–§3 (40 min). Session 1: 10 min side-view board drawing; Steps 1–5;
   badge **Measurer**. Fast students: "Going further: oblique GSD".
2. Before session 2: lesson §4–§7 (35 min). Session 2: Steps 6–9, 15 min OpenCV check (Step 10) and memo; badge
   **Straightener**. Close with "why 28 m became 1 m" (Look back 1).

Differentiation: fast — "Sloped ground", "Heading up", the scale-gate statistics; struggling — give the
side-view drawing of §3 printed, pair on TODO 8 with the trace on paper first.
