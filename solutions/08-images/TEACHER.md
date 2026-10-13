# Mission 08 — teacher notes (Digital images: arrays, filters and geometric transforms)

Teacher only. Rebuilt 2026-10-13 on NAVERA Lite (`navera_lite/image.py`, reference in
`solutions/_navera_lite/navera_lite/image.py`, tags `# @part 08 todo 1–7`; given: `to_gray`, `histogram`,
`gaussian_kernel`, `SOBEL_X`, `sobel`, `pixel_or_zero`). No NAVERA code: NAVERA's night/day vision is described
in words and numbers only (ENGINEERING_BACKLOG LOC-7, LOC-16, LOC-24; VALIDATION_STATUS 2026-10-03).
The old mission read NAVERA's data folder live; it now reads `/data/academy/08-images/` only.

**Data** (`PYTHONPATH= python3 solutions/08-images/make_dataset.py [path of NAVERA's day frame 5]`, deterministic,
1.1 MB): `map_patch.png` (render_view 'pseudo', north up, 512 px at 0.967527 m/px = zoom 17 at 35.8942°, Port El
Kantaoui marina), `drone_photo.jpg` (same renderer, **true heading 35.0°**, 0.60 m/px, 640 × 480, effects: blur 1.3,
noise 5, gamma 1.35, brightness 0.72, illum 0.25, vignette 0.3, warmer), `thermal16.png` (synthetic uint16, 7 150–8 430,
Sousse harbour render + noise), `real_frame.jpg` (NAVERA's day frame 5, copied as data, owner decision §7.2; its
place and imagery source are NOT established — the validation report says replay frames do not show the places
their CSV names, and it looks like a commercial satellite crop: **owner to confirm source and licence**; lessons
call it "a real aerial frame from NAVERA's day-camera test data", no place), `info.json` (the compass heading
**31.0°**, i.e. a 4° error on purpose).

**Centre convention of the data (fix round 1).** render_view puts (lat, lon) at pixel (w/2, h/2) in pixel-centre
coordinates; the course puts it at ((w − 1)/2, (h − 1)/2). make_dataset.py therefore renders one pixel more each
way and drops the first row and column (`centred()`). Checked with phase correlation: like_map of a photo vs the
map now shows no heading-dependent shift (before: ≈ 0.5 px per axis at 90°/180°). A heading-independent ≈ 0.2 map-px
offset remains when the photo and map m/px differ (render_view samples its intermediate orthophoto half a pixel
off at its own resolution) — a datasets/_map property, negligible here (NCC unchanged to 0.001). The w/2 bug in
like_map changes the lab's NCC by < 0.005: the check catches it on its centroid test (±0.15 px), and the lesson now
says honestly why the convention matters (later missions), not that it changes this lab's numbers. Hidden check data:
`PYTHONPATH= python3 solutions/08-images/make_hidden.py` → `courses/08-images/hidden/photo_b.png` (orchard near
Monastir, heading 250°, 0.45 m/px) and `like_b.png` (reference like_map). Lesson figures:
`PYTHONPATH= python3 solutions/08-images/make_figures.py` (cold_open, like_map_steps, thermal_wrap; prints the §7
worked example). SVGs: pixels, convolution (÷ 8 added), affine (unchanged), heading (new).
Map attribution "© OpenStreetMap contributors" is on every figure that shows the map and in the dataset README.

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 dtypes: predict wrap/truncation, convert safely | §1, §2 (7 500 → 76 / 255 / 70), ✏️ thermal 7 200–7 455 | Steps 0–2 (TODO 1–3, `cast`, NAIVE_…) | 1, 2, 3, 4 |
| 2 convolve by hand and in code, explain the flip | §4 (1-D worked example, reflect 101, Sobel ÷ 8), ✏️ [5, 5, 5, 9] | Steps 3–4 (HAND_…, TODO 4, `filters`, EXPLAIN_FLIP) | 5, 6 |
| 3 affine matrix about a point; inverse mapping + bilinear | §5 (30°, 0.5, (100, 50)), §6 (37.6 example) | Steps 5–6 (CORNER_UV, TODO 5–6, `warp`) | 7, 8, 9 |
| 4 photo → map (heading, GSD), NCC sensitivity | §7 (heading figure, medina worked example, NCC, same-renderer caveat) | Steps 7–9 (LIKE_TRACE, TODO 7, `like`, `sweep`, `scale`, report) | 10, 11, 12, 13 |

Badges: **Darkroom** = checks 1–6 (session 1), **Map matcher** = all 13.

## Answer key

| Item | Value | Where it comes from |
|---|---|---|
| NAIVE_COLDEST / NAIVE_HOTTEST | 238 / 238 | 7 150 % 256 and 8 430 % 256; they differ by 1 280 = 5 × 256 |
| HAND_BLUR | [2, 2, 3.5, 6.5, 8, 8] | reflect 101: padded [2, 2, 2, 2, 8, 8, 8, 8] |
| HAND_DERIV | [0, 0, 6, 6, 0, 0] | out(x) = img(x + 1) − img(x − 1); correlation gives the negatives |
| PREDICT_SPEED (ungraded) | ≈ 45–55× | `filters`: about 230 ms vs 4–5 ms on the Jetson (warp: about 190–220 ms vs 3–4 ms) |
| CORNER_UV | (55.0, 10.0) | a = 0, b = −0.5: M = [[0, −0.5, 55], [0.5, 0, 10]]; +90° gives (25, 50) |
| LIKE_TRACE | (0.620, 496, −72, +8) | s = 0.60/0.967527 = 0.6201; side = round(800 × 0.6201); c_in (319.5, 239.5), c_out (247.5, 247.5); half-pixel variants (−72.5, 7.5) / (−71.5, 8.5) get their own message |
| PREDICT_NCC (ungraded) | raw 0.027, compass 0.746 | `like` |
| NCC_COMPASS | 0.746 | like_map at 31.0° |
| BEST_HEADING_DEG | 35.0 (NCC 0.965) | `sweep` (default 21–41°, step 0.5°, peak off-centre), refined with `sweep 33 37 0.1` |
| COMPASS_ERROR_DEG | +4.0 | true − compass |
| HEADING_TOL_DEG | ±1.5 | NCC ≥ 0.9 from 33.5° (0.905) to 36.6° (0.1° steps); check accepts 1.0–2.0 |
| sweep shape | 21° 0.457, 24° 0.506, 31° 0.746, 35° 0.965, 41° 0.640 | symmetric about 35° |
| SCALE_TOL_PCT | ±2.3 % | `scale 35`: NCC ≥ 0.9 from 0.588 to 0.616 m/px (0.002 steps); with the default 0.005 steps 0.590–0.615 → 2.1 %; check accepts 1.5–3.1 |
| EXPLAIN_SCALE | heading costs more | 5 % scale (0.57 / 0.63): NCC 0.80 / 0.82; 5° heading (30° / 40°): 0.69; scale from height above ground + lens, heading from compass/IMU |

Lesson numbers (all recomputed from the reference): 7 500 → 76 / 255 / 70 (69.7); ✏️ 7 200 → 32, 7 455 → 31;
`np.array([300., -5., 254.9]).astype(np.uint8)` = [44, 0, 254] + RuntimeWarning on the Jetson (numpy 1.26);
[0, 0, 4, 0, 0] * [1, 2, 1]/4 = [0, 1, 2, 1, 0]; impulse [0, 0, 1, 0, 0] * [1, 2, 3] = [0, 1, 2, 3, 0] (correlation [0, 3, 2, 1, 0]); ✏️ [5, 5, 5, 9] * [1, 0, −1] = [0, 0, 4, 0]; Sobel 280 / 8 = 35;
affine 30°/0.5/(100, 50): tx 44.20, ty 53.35, (200, 50) → (143.3, 25.0); bilinear (2.3, 1.6) → 37.6;
§7 medina: s 0.4649, side 372, last column (490.19, 166.54) → (356.19, 112.54); NCC examples 1 / −1;
✏️ 1.2 m/px → s 1.237, side 990; check-yourself 1000 → 232, 100 m east at 35.8° → 0.00111°.
NAVERA numbers (VALIDATION_STATUS 2026-10-03, backlog 2026-09-28): LOC-16 at 250 m 149–263 → 11–13 m median,
400 m 11–215 → 8–11 m, 600 m 98–218 → 8–11 m (synthetic grey renders); day vision 21/33 → 32/33 accepted with
pre-scaling (+2 other changes), product 30/33, median 4 m (now only in TEACHER, cut from the lesson); replay
frames 190–300 m ground, 4.7 km "drift". **LOC-24 (backlog, commit only, no date):** "mono16 thermal converted to
bgr8 without scaling"; NAVERA's fix stretches between the 2nd and 98th percentiles (words only). The lesson no
longer claims NAVERA's bug was a modular wrap: the docs say a plain conversion "saturates or blanks the scene";
the lab's wrap picture is "the worst form of that mistake". Discussion question: why not min–max on a thermal
frame with a hot chimney?

## Rubric for written answers (the check only verifies "written and on topic")

| Item | 2 — good | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_CAST | astype keeps value mod 256; 1 280 = 5 × 256 so both ends map to 238 (bands, order lost); normalise works in float from the frame's own min/max, then rounds/clips | "it overflows" without why the two are equal | — |
| EXPLAIN_FLIP | correlation gives [0, 0, −6, −6, 0, 0] (sign reversed); Gaussian symmetric → identical | one of the two | — |
| EXPLAIN_SWEEP | NCC 0.965 → 0.746 for 4°, ≥ 0.9 only within ±1.5° → heading to ~1°; options: search over headings (cost, false matches), rotation-estimating methods (features, mission 21–22), better heading sensor | "the compass must be good" only | — |
| EXPLAIN_SCALE | names the heading as the costlier error with numbers, and height/lens vs compass/IMU | one of the two | — |
| report.md | the three sections with numbers (238, ≈ 230 vs 5 ms, 0.746 → 0.965, 35°, ±1.5°, ±2.3 %), the rule "compute in float, round/clip/convert", and a consequence for a pixel-matching system | numbers without reasoning | — |

## Difficulties expected (from 50 wrong-solution mutants, all caught, and the round-1 student reviews)

- `astype` without clip (300 → 44) or without rint (254.6 → 254): runner and check name each case.
- `to_float01` dividing uint16 by 255 (values up to 257); float64 returned.
- `normalise` without a float conversion (uint16 overflow of (g − min)·255), stretching by the dtype range,
  no uniform guard (zeros come out by luck: the check runs the student code with `-W error`), returning floats.
- correlation instead of convolution (signs reversed — also flagged by `filters`), `edge`/`constant`/`symmetric`
  padding, no ValueError for even kernels.
- affine clockwise (b sign), no translation, degrees in cos/sin, centre as (cy, cx).
- warp: forward mapping, nearest, size (w, h) swapped, weights swapped (caught only on the unseen photo, mean
  difference 0.75 > 0.6), float64.
- like_map: +heading, centres at w/2 (half a pixel: caught by the centroid test, ±0.15 px), no centre shift,
  scale inverted, normalise after the warp (caught on the unseen photo: grey levels 28 off), no to_uint8,
  side = max(w, h).
- A wrong earlier TODO makes like_map's check say "finish TODO k first" instead of a misleading like_map message.

## Class plan (two sessions of about 3 h)

1. Session 1 (Darkroom): Step 0 together (2 min) → read §1–§2 (25 min; the lab says the same) → Steps 1–2 (45 min) → show
   `out/thermal_naive.png` on the projector and discuss LOC-24 → §4 (20 min) → Steps 3–4 (50 min) → badge.
2. Session 2 (Map matcher): §5–§6 with the board (the 3 × 3 product T·S·R·T, the bilinear example), Steps 5–6
   (60 min) → §7 and the heading figure (15 min) → Step 7 (40 min) → sweep and discussion: why NAVERA's day
   vision does not turn its photos (rotation fitted by features, scale gate) → report.

Differentiation. Fast: Going further (scale sweep, separable convolution timing, aliasing, Sobel-magnitude
NCC). Struggling: give the 🧰 boxes first, pair on TODO 6 (the hardest: inverse + bilinear), and let them use the
runner's test lines as the first target; TODO 7 hints 1–4 are enough to finish.

## Fix round 1 (2026-10-13)

The grader refuses an image library imported in navera_lite/image.py (checks 5, 7, 8, 10; AST scan, also
`__import__`/`import_module`): the expert's OpenCV overlay got 12/12 before, now 9/13. Runner `test` warns the same.
warp_affine has a zoom (A ≠ I) case in `test` and in the check, and a WARP_INVERSE_MAP comparison (⚠ in `warp`,
message in the check). Checks: 13 (was 12): FLOAT64_BYTES and NCC_RAW removed; LIKE_TRACE (hand trace), PREDICT_NCC,
SCALE_TOL_PCT and EXPLAIN_SCALE added (Step 8b, about 15 min; meta 6 h).

## Known limits

- The map patch and the photo come from the same renderer (pseudo-aerial drawing of OSM data); the NCC values
  are optimistic compared with a real camera against a satellite map. The lesson says the data are drawn.
- The warp tolerance (mean 0.6 grey level vs cv2.warpAffine) is set because OpenCV rounds its bilinear weights;
  the reference is at 0.07 on the real frame, 0.42 on random noise.
