# Mission 26 — teacher notes (Navigating by the stars)

Teacher only. Rebuilt 2026-10-14 on NAVERA Lite: `navera_lite/stars.py`, reference in
`solutions/_navera_lite/navera_lite/stars.py`, tags `# @part 26 todo 1–9` (julian_date, gmst_deg, altaz,
lat_from_polaris, detect_stars, boresight_altaz, both_roots, choose, error_km); given: `load_catalogue`,
`find_star`, `precess` (IAU 1976, course-written), `radec_to_vec`, `vec_to_radec`, `sep_deg`, `pixel_rays`,
`fit_rotation` (SVD/Wahba), `plate_solve` (a small course-written lost-in-space solver: pair-angle voting, rotation
fit, verification by projection), constants (`KM_PER_DEG`, `POLARIS_P_DEG` = 0.6253, `CAM_TILT_DEG` = 20,
`CAM_AXIS_BODY`, `R_BODY_STAR_CAM`). `imu.py` (17: `q_true_north`, `declination_deg`) and `camera.py` (18) ship
finished; `rotations.py` (16) through the closure. This is the SECOND HALF of the old mission 24/26 (night vision is
mission 25 now). No NAVERA code, no NAVERA file: the old lab ran NAVERA's celestial maths and read NAVERA's star
catalogue; now the student writes the maths and the catalogue is a public one shipped with the mission.

Regenerate (from the repository root, on the host):
- `python3 tools/lite_build.py 26-stars` — starter + solution of the part;
- `python3 solutions/26-stars/make_dataset.py [--raw catalog.gz]` — `datasets/26-stars/` (seed 2626; downloads the
  BSC from CDS when `--raw` is not given; 3.9 MB). The generator lives HERE, never in datasets/;
- `python3 solutions/26-stars/make_expected.py` — `courses/26-stars/hidden/expected.json`: unseen inputs and the
  reference's outputs for TODOs 1–4 and 6–9 (seed 2627), and every lab number, read back from `run_stars.py`
  run on the reference (so the check's constants are exactly what a correct student sees);
- `python3 solutions/26-stars/make_figures.py` — the seven SVGs in `courses/26-stars/assets/`.
`solutions/_navera_lite/navera_lite/tests/test_stars.py` exists for later missions (not shipped in 26: it would
show the answers).

## The data (`/data/academy/26-stars/`)

- `bright_stars.csv`: 8 404 stars with V ≤ 6.5 from **the Bright Star Catalogue, 5th rev. ed. (Hoffleit & Warren
  1991, CDS V/50)**, J2000 positions (RA to 0.1 s, Dec to 1″), common names added by hand for 55 stars. Licence: no
  licence is stated in the CDS ReadMe (2022 version) nor in the Harvard bsc5 readme (both checked 2026-10-14); an
  earlier documentation file of the machine-readable catalogue describes it as public domain. NASA/ADC work, freely
  distributed by CDS, which asks for an acknowledgement; the dataset README says exactly this, with the citation. NAVERA's own copy of the BSC
  is not used and stays staff-only.
- `photos/night_01…06.png`: SYNTHETIC star-camera photos, 1280 × 960, 8-bit, ideal pinhole 60° wide (f = 1108.5 px,
  K centre (640, 480)), camera axis 20° from body up towards the nose. Rendered with the reference's own sky model
  (precess + GMST + altaz, no nutation/aberration/refraction/distortion), Gaussian PSF σ 1.0 px integrated over
  pixels, total signal 60 DN at V = 6.0, sky 18 DN (+6 towards the bottom), read noise 2.5 DN, 40 hot pixels
  (120–255). Photo 2 adds a glow (+70 DN, σ 380 px, bottom-right corner) and an aircraft trail. Because the world
  and the solver share one model, the "perfect attitude" fixes are within 0.2 km — far better than NAVERA's real
  5.5–6.5 km. Lab Step 8's note "Why 0.2 km here and 5.5–6.5 km in NAVERA?" says so to the students: NAVERA's
  number is mostly astrometry.net's 2.9′ centre fit (5.4 km); refraction would add 0.8–1.3 km at these altitudes
  (Bennett; `fix truth refraction` measures 1.0 km for photo 1, 1.2 km for photo 3), aberration ≤ 0.6 km,
  nutation ≤ 0.5 km. Owner decision (round 1): no lens distortion, no attempt to make the budget "real".
- `photo01_stars.csv`, `photo02_stars.csv`: true pixel positions of every catalogue star in photos 1 and 2 (the
  runner's `detect 1|2` truth comparison; photo 2 adds "stars found in the glowing corner").
- `photos.json`: UTC time, the chip quaternion (truth + BNO085-class errors σ 0.3° roll, 0.3° pitch, 1.5° heading,
  then turned to MAGNETIC north by the WMM declination at the truth), prior, truth (position, human angles, q).

| photo | place (truth) | UTC 2026 | heading / pitch_up / roll | IMU errors drawn (roll, pitch, heading) | D at truth | prior |
|---|---|---|---|---|---|---|
| 1 | Sousse 35.83, 10.64 | 20 Oct 20:30 | 60 / −4 / 0 | −0.33, +0.08, +1.22 | +3.34 | 36.45, 10.10 |
| 2 | near Sousse 35.52, 10.93 | 20 Oct 21:10 | 235 / −3 / 8 (glow, trail) | +0.43, +0.14, +0.43 | +3.36 | 36.45, 10.10 |
| 3 | Tromsø 69.65, 18.96 | 20 Oct 22:00 | 0 / −15 / 0 | −0.09, +0.50, −0.98 | +11.27 | 69.20, 19.90 |
| 4 | Cape Town −33.92, 18.42 | 20 Oct 20:00 | 170 / −5 / 0 | −0.43, −0.10, −0.03 | −26.80 | −33.20, 19.30 |
| 5 | Quito −0.18, −78.47 | 21 Oct 03:00 | 300 / −6 / −3 | +0.22, +0.29, −2.69 | −5.10 | 0.60, −77.80 |
| 6 | Reykjavik 64.15, −21.94 | 21 Oct 00:30 | 45 / −15 / 0 | +0.36, +0.23, −1.01 | −11.05 | 64.00, −21.20 |

Sun altitude at every photo below −30° (astropy). Photo 3 looks north 55° high: two valid roots, the asin root is
the wrong one (40.35 N, 161.04 W, 7 784 km away with the true attitude) — the LOC-10 situation. Photo 6 is near the
"fold" of the two roots: with the true attitude they are 157 km apart (both within 5° of the prior → no position);
with the IMU's attitude there is no root at all.

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 time → JD → sidereal time; 3 min 56 s | §1 sky frames figure, sidereal day, JD recipe, GMST, worked example London 7 Oct 2026 20:00 UTC, ✏️ Sirius/Orion, precession | Step 0, Step 1, Step 2 (TODO 1–2, clock) | 1, 2, 5 |
| 2 altitude/azimuth; latitude from Polaris | §2 triangle figure, worked example Capella from London (19.02°, 37.86°), ✏️ Canopus; §3 Polaris figure, worked ship example (47.68°), ✏️ 70 km | Steps 3–4 (TODO 3–4, sky capetown, polaris) | 3, 4, 6 |
| 3 star detection with OpenCV; plate solving | §4 five steps, 🧰 robust σ + OpenCV, centroid figure (4.167), ✏️ faint star; §5 pair angles, astrometry.net vs the given solver | Steps 5–6 (TODO 5, detect, detect 2, solve) | 7, 12 |
| 4 one direction in two frames → position; two roots; prior | §6 zenith case, R sin(φ+ψ), two-roots figure, worked table (8 808 km), choosing, ✏️ zenith camera / ambiguous prior; cold-open figure | Steps 7–8 (TODO 6–8, fix, fix truth/magnetic/oneroot) | 8, 9, 10, 13 |
| 5 error budget; check by simulation | §7 budget figure, rule, worked example 80 km / 55.6 km vs NAVERA 53/91 km, ✏️ 10 km fix; box "after Step 9" | Step 9 (TODO 9, budget, the integrator role), Step 10 memo | 11, 14, 15 |

Badges: **Stargazer** = checks 1–6 (session 1), **Star navigator** = all 15.

## Answer key

| Item | Value (check tolerance) | Where it comes from |
|---|---|---|
| PREDICT_SIDEREAL (ungraded) | a little earlier (3 min 56 s) | §1 |
| N_VOTE_STARS | 904 (exact; 903/905 or < 100 get the "≤ 4.5" message) | `(cat["vmag"] <= 4.5).sum()` |
| TRANSIT_SHIFT_S | 235.9 (± 0.3; the negative gets its own message) | `clock`: 20 Oct 15:58:46.44 UTC, 21 Oct 15:54:50.53 UTC |
| VEGA_SHIFT_ARCMIN | 10.62 (± 0.03) | `clock` (Polaris 9.12′, Sirius 17.30′) |
| VEGA_SHIFT_KM | 19.67 (± 0.15 around the student's arcmin × 1.852; × 111.2 gets a message) | |
| PREDICT_ACHERNAR (ungraded) | 90 − |−33.92 + 57.10| = 66.8° at transit; table 55.96° at az 144° (SE): before transit (H = −37°) | |
| ACHERNAR_ALT_DEG / AZ | 55.96 / 144.30 (± 0.02; swapped → message) | `sky capetown` (GMST 329.291°; Polaris −33.60°, below the horizon) |
| PREDICT_POLARIS (ungraded) | Reykjavik: the p² term grows with tan φ | |
| NAIVE_MAX_ERR_KM | 69.52 (± 0.1) | `polaris`: Reykjavik 69.50, London 69.47, Sousse 69.52, Singapore 69.42 |
| CORRECTED_MAX_ERR_KM | 0.781 (± 0.005) | Reykjavik 0.781, London 0.475, Sousse 0.274, Singapore 0.009 |
| PREDICT_DETECT (ungraded) | about 120 of 125; 0 hot pixels | |
| N_STARS_01 | 134 with the reference; the check compares with the student's OWN detector (exact) | `detect`: 122 of the 125 stars ≤ 5.0 found, RMS 0.174 px, worst 0.483 px, 0 "not stars" |
| CENTROID_RMS_PX | 0.174 with the reference; checked against the student's own detector (± 0.002), must be < 0.3 | |
| SOLVE_RMS_ARCSEC | 31.1 (10–60 and ± 8 of 31.1) | `solve`: 134 matched, centre ra 16.9916°, dec +44.3995° (of date) |
| PREDICT_PIXEL (ungraded) | more: 3.10′ = atan(1/1108.5) at the centre; 60°/1280 = 2.81′ is the average (edge pixels cover less) | |
| PIXEL_ARCMIN | 3.10 (± 0.01; 2.81 → message "the average") | atan(1/1108.5); × 1.852 = 5.74 km |
| TRACE_PSI_DEG | 29.19 (± 0.03; 60.81 = atan2 arguments swapped → message) | p = sin 37.13° = 0.6036, q = cos 37.13° · cos 295.02° = 0.3373 |
| MEDIAN_FIX_KM | 116.9 (± 2) | `fix`: 1 116.9, 2 30.2, 3 121.5, 4 49.5, 5 147.4 km, 6 no position (0 roots) |
| NO_FIX_PHOTO | 6 | |
| PERFECT_MAX_KM | 0.2 (accepted 0 < x < 1) | `fix truth`: 0.1, 0.1, 0.2, 0.1, 0.1; photo 6 no position (2 roots 157 km apart, both near the prior) |
| PREDICT_MAGNETIC (ungraded) | rule: 3.3° × cos 66° × 111.2 ≈ 150 km | |
| MAGNETIC_MOVE_01_KM | 197.4 (± 3; swapped with the error → message) | `fix magnetic`, column "moved from `fix`": 1 197.4, 2 152.4 km. 197.4 ≈ 1.30 × 150: the heading stretch of §7's box |
| MAGNETIC_ERR_01_KM | 313.7 (± 3) | `fix magnetic`: 1 313.7, 2 148.5; 3, 4, 5, 6 no position (roots beyond 5° of the prior) |
| ONE_ROOT_ERR_03_KM | 7 834.3 (± 20) | `fix oneroot`: photo 3 takes the asin root (39.88 N, 163.78 W) |
| PREDICT_BUDGET (ungraded) | any; measured RMS is ABOVE the formula, median below | |
| FORMULA_KM | 82.6 (± 0.2) | `error_km(0.424, 1.5, 66.00)` |
| MC_RMS_KM / MC_MEDIAN_KM | 103.1 / 74.8 (± 1.5; swapped → message) | `budget` (seed 26, 2 000 draws): p90 164.6, max 369.8, 0 no-fix |
| MOUNT_BIAS_MAX_DEG | 0.495 (± 0.005; the lab asks for 3 decimals) | 55 / 111.195 |
| report.md | headings, 150–420 words, a km value 110–125 (median), "0.x km" (perfect), "111 km" | |

Why 82.6 km (rule) and 103.1 km (simulation) differ (EXPLAIN_BUDGET): the heading part is stretched by
cos φ / (cos δ · |cos H|) = 1.30 for photo 1 (H = −29.5° = the boresight's hour angle), the tilt part by about 1.05:
111.2 × √((0.424·1.05)² + (0.61·1.30)²) = 101 km. Roll on the 20°-leaning axis (cos 20°) slightly *lowers* the
simulation. Median < RMS: a 2-D error's median is about 0.83 × RMS even for Gaussian errors, and photo 1's tail makes
it 0.73. Photo 6 sits at the fold (H = −91°, stretch ×56): `budget 6` gives 1 858 / 2 000 draws with no position.
Photo 4 (×1.60, `budget 4`: RMS 125.8 km vs rule 84.8) is stretched more than photo 3 (×1.37, 140.8 vs 106.7), so
"near the pole" is not the reason; |cos H| is. The single-root (asin) formula is right exactly when |H| < 90°
(checked by the expert reviewer on 19 946 random cases; photo 3 has H = 180°, Capella in §6 H = −123°). NAVERA's
document says "southern half of the sky" in NAVERA's own formulation; the lesson quotes it as NAVERA's statement and
gives the |H| condition for ours. Accept either reason (stretch / approximation of the rule) in the rubric.

Domain note (expert, round 1): the lab's one-direction method is NAVERA's. The full-rotation ("zenith") method —
`plate_solve`'s `R_eq_cam` + the IMU's vertical, φ = δ and λ = α − GMST of the zenith — is heading-free and unique:
errors 37.8 / 50.0 / 56.1 / 48.6 / 40.3 / 46.1 km with the chip attitude as delivered (magnetic does not matter);
2 000-draw RMS 47 km on every photo (tilt term 0.424° × 111.2). It is a lesson paragraph (end of §6) and a Going
further item, not graded. Use it for the "what would improve NAVERA" discussion (NAVERA's own advice: a levelled
camera and a better attitude source).

## Rubric for the EXPLAIN items (the check only catches empty or off-topic answers — keyword groups)

| Item | 2 — complete | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_SIDEREAL | orbit motion → ~361°/day relative to the stars → 3 min 56 s; time error → sky rotation → longitude error (15″/s) | one of the two | "the Earth turns" only |
| EXPLAIN_POLARIS | p ≈ 0.63° → up to ~70 km; p cos H puts Polaris back on its circle; the residual p² term grows with tan φ (Reykjavik) | two of three | restates the numbers |
| EXPLAIN_CENTROID | weighted mean gives sub-pixel centres (1 px ≈ 5.7 km); size limits refuse hot pixels/trail; local background keeps stars in the glow | two of three | "OpenCV finds stars" |
| EXPLAIN_ROOTS | sin takes each value twice (x, 180° − x); asin only returns [−90°, 90°], photo 3's φ + ψ > 90°; photo 6's roots too close (or none) → no position | two of three | "it is ambiguous" |
| EXPLAIN_NORTH | forgotten D = a heading error, × cos alt × 111 km (moved 197 km ≈ 1.3 × the rule's 150), the error adds to the IMU's own heading error; large D (Tromsø, Cape Town, Quito) pushes the roots beyond 5° of the prior → refused | two | "magnetic is wrong" |
| EXPLAIN_BUDGET | heading term dominates (1.5° × cos 66° = 0.61° vs 0.42° tilt); median ≈ 0.83 × RMS even for Gaussian, a tail widens it; the rule is approximate (heading stretch cos φ / (cos δ |cos H|) = 1.3) | two | numbers only |

## Mutants run (wrong-but-plausible code; every one fails with its own message)

`tools/try_lesson.py 26-stars --solution --overlay <mutant>` (script `~/academy-test/review/26-stars/build/run_mutants.py`,
22 mutants, 2026-10-14), and `run_stars.py test` on the same mutants:

| Mutant | check message (✘) | runner test |
|---|---|---|
| Jan/Feb rule missing | "January and February must count as months 13 and 14 of the PREVIOUS year" | J2000 "one day short: …", Feb case "Jan/Feb…" |
| minutes / 100 | "the minutes count as hundredths of an hour" | same |
| GMST without % 360 | "keep the angle in [0, 360)" | "… outside [0, 360): use % 360.0" |
| altaz with math.* (not vectorised) | "only length-1 arrays … use np.sin…" | same |
| azimuth from south | "the azimuth is measured from SOUTH" | same |
| longitude sign | "the longitude has the wrong sign: LST = gst + lon" | same |
| Polaris + p cos H | "the correction has the wrong sign" | same |
| cos of degrees (Polaris) | "cos got degrees" | same |
| plain centroid | "a lone star gives its PLAIN centre (4.0, 5.0) …" | "(4.0, 4.0) is the plain centre…" |
| no min_area | "a single hot pixel (1 pixel) is reported as a star" | "the hot pixel … was kept" |
| no max_area | "the aircraft trail is reported as a star" | — (docstring cases have no trail) |
| global background | "13 detections … Subtract the LOCAL background" | — |
| unsorted | "not sorted brightest first" | runner modes stop with "sort … BRIGHTEST FIRST" |
| u/v swapped | "u and v are swapped" | same |
| boresight atan2(N, E) | "measured from EAST counter-clockwise" | same |
| one root only | "only the asin root: … TWO solutions" | "only one root…" |
| longitude not wrapped | "a longitude is outside [−180, 180): wrap it" | — |
| invalid latitudes kept | "a root has |latitude| > 90°" | — |
| choose = nearest root | "both roots are within max_sep_deg … return None" | — |
| choose with lat/lon differences | "0.38° from the prior on the sphere … use sep_deg" | — |
| error_km added | "the two errors are ADDED" | same |
| error_km without cos | "the heading error is not multiplied by cos(alt)" | same |

Round 1 (2026-10-14, `--who fix1m`): 5 more of mine and the expert reviewer's 12 (`expert1/mut/`), all caught except
the expert's stable reverse sort (equivalent code, passes correctly):

| Mutant | check message (✘) | runner test |
|---|---|---|
| uint8 subtraction (`gray - bg` wraps) | "464 detections … did you subtract two uint8 arrays?" | grey-sky case "… uint8 … wraps around"; `detect` prints a ⚠ uint8 line |
| choose with a lat/lon box | "0.38° from the prior on the sphere … cos 64°" | "a latitude/longitude box is wrong" |
| both_roots without the no-root guard | "math domain error — … no root (return [])" | same; `fix` now shows the crash instead of "0 roots" |
| minutes not added | "the minutes (and seconds) are not added" | "30 minutes short" |
| error_km cos of degrees | "cos got degrees" | "cos got DEGREES" |
| expert: np.std σ | "nothing found … ROBUST σ (1.4826 × MAD)" | — |
| expert: mean-blur background | "almost: … Is your background a MEDIAN?" | — |
| expert: no T²/T³ in GMST | "the T² and T³ terms are missing" | — |
| expert: Polaris with sin H | "the correction uses sin H" | — |
| expert: error_km with sin(alt) | "the heading term uses sin(alt)" | — |
| expert: hours without minutes | "the minutes (and seconds) are not added" | "30 minutes short" |
| expert: raw-image weights, unwrapped azimuth, lon in [0, 360), choose `<` window, cos degrees | own messages (flux rank, % 360, wrap, max_sep, cos degrees) | — |

## Round 1 reviews (strong 8/9/9/8, weak 7/8/7, expert 8/7) — what changed

- Time: the weak persona needed ≈ 8 h 30 (strong ≈ 3 h 40). meta.json now says 7 h 30, the lab "4 h to 6 h", the
  lesson "90 min (2 h if spherical trigonometry is new)". Load cut: POLARIS_CAPE_ALT_DEG and PIXEL_KM removed (copy
  tasks), replaced by two predictions (PREDICT_ACHERNAR: culmination by hand; PREDICT_PIXEL: 2.81′ vs 3.10′);
  MAGNETIC_MOVE_01_KM added so the magnetic prediction is compared with the move, not the error.
- Lesson: §6 🧰 derivation of R sin(φ + ψ), the "no root" case (text, ✏️ item 3, figure), the |H| < 90° rule for the
  asin root (LOC-10, not CN-1), the whole-rotation paragraph; §7 box rewritten (stretch cos φ / (cos δ |cos H|),
  the fold); brief quotes "southern half" as NAVERA's wording; worked arithmetic collapsed; Emlen, median 0.83,
  aberration, UT1 fixed.
- Lab: Step 8 note on 0.2 km vs NAVERA's 5.5–6.5 km; `fix truth refraction`, `budget N`, the fold, the whole rotation
  and the stretch derivation in Going further; quoting note for the one-liner; uint8 hint first in Step 5.
- Runner: `detect 2` truth numbers (98 of 101 stars ≤ 5.0, 14 of 14 in the glowing corner, 0 not stars, RMS
  0.144 px), uint8 warning, both_roots errors shown, |lat| > 90° refused, "moved from `fix`" column, roots note,
  daylight note on Vega's transit, 24 test cases (grey sky, no root, one valid root across 180°, 64° N box, named
  traps for minutes, unwrapped azimuth, cos of degrees).

## Difficulties expected (weak-student test round 1 done; see above)

- `detect_stars` is the first OpenCV function the students write from scratch with several steps: the uint8
  wrap-around (`img - bg`), label 0 (background), `np.bincount` weights. The 🧰 box and hints 1–4 carry it; a loop
  over labels (`labels == i`) is accepted (0.4 s on photo 1 on the Jetson, measured 2026-10-14).
- `both_roots` is the hardest maths: hand-trace ψ first (TRACE_PSI_DEG). Students who return one root pass the
  docstring's first root only and get the "TWO solutions" message.
- Longitudes: east positive everywhere; the "wrong sign" message names it.
- The fix numbers depend on the given plate solve of the student's own detections; a weaker detector (e.g. no
  weighting) still solves but moves the fixes by < 1 km; the tolerances (± 2–3 km) absorb it.

## Class plan (2 sessions)

- Session 1 (2 h): 10 min Step 0 + hook (cold-open figure: one measurement, two places); 30 min §1–§2 with the
  London/Capella example on the board; students do Steps 1–3; 15 min §3, Step 4; badge.
- Session 2 (3 h): 20 min §4 (draw a 5 × 5 star on the board, plain vs weighted centre), Step 5; 10 min §5 demo
  `solve` on the projector; 30 min §6 two-roots figure, students trace ψ; Steps 7–8; 15 min §7, Step 9; memo as
  homework.
- Fast students: Going further (unweighted centre, near-pole budget, refraction). Struggling: give hint 3 of Step 5
  as a worked snippet; pair them for TODO 7 with the lesson's table open.

## NAVERA facts quoted (words and numbers only; from base/docs, VALIDATION_STATUS 2026-10-03, backlog)

Single asin root → hundreds–thousands of km (LOC-10); solver anchored off-centre ~1° = 111 km → 2.9′ (CN-1); no
precession: ~0.4° RA in 2026, tens of km; first real photo 2026-10-01: 1.7′ from Siril; end-to-end 2026-09-30:
perfect attitude 5.5–6.5 km (solve 3–13 s), tilt 0.5° → 53 km, + heading 2° → 91 km, BNO085-class 24–119 km (~50
typical), ~111 km per degree; 20 000 pointings: 0 wrong, 1–2 % ambiguous; attitude at exposure (CN-2); priority GPS >
day > night > celestial, celestial fresh 45 s (ARCHITECTURE); QA-2 ±55 km forwarded → 125 km jump, coarser than 1 km
no longer forwarded; not validated on a real sky with known time/place/attitude. The 5° prior window is NAVERA Lite's
rule (the lesson says so); NAVERA's window is not in the docs.
