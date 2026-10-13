# Mission 06 — teacher notes (Geodesy for navigation: WGS84, ECEF and ENU)

Teacher only. Rebuilt 2026-10-13 on NAVERA Lite (`navera_lite/geo.py`, reference in
`solutions/_navera_lite/navera_lite/geo.py`, tags `# @part 06 todo 1–12`). No NAVERA code: the old
`compare_navera.py` is replaced by `compare_oracle.py` (Vincenty, course-written from the 1975 formula;
pyproj if installed — not installed on the Jetson today, so Part 3 prints "skipped").
Numbers: every value below comes from the reference (`make_figures.py`, the check constants, and the
runner outputs); recompute with `python3 tools/lite_build.py 06-coordinates` then
`tools/try_lesson.py 06-coordinates --solution --shell "python3 run_geo.py cos"` etc.

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 flat shortcut, where to take cos φ | §1 (Δλ wrap, Null Island), §2 London→Paris table | Step 1 (TODO 1–2), Step 3 (R-6 audit) | 1, 2, 8 |
| 2 haversine, bearing, great circle, offset | §3, §4 | Steps 2, 4 (TODO 3–6), R-2 audit | 3, 4, 5, 6, 7, 9 |
| 3 geodetic ↔ ECEF ↔ ENU, verified | §5–§7 | Steps 5–8 (TODO 7–12, oracle) | 10–14, 15 (radii, geocentric, drop), 16 |
| 4 heights; choose a model with numbers | §8, bird's-eye view | Step 7 (H_ELLIPSOID_M), Step 9 (TODO A, explanation box after EXPLAIN_STUDY), Step 10 report | 15, 17, 18 |

Badges: **Navigator** = checks 1–9 (session 1), **Surveyor** = all 18.

## Answer key

| Item | Value | Where it comes from |
|---|---|---|
| TURN_DEG | +4.70 | departure 158.15°, arrival (bearing Tunisia→Paris + 180) 162.85°; 184.7 = forgot the +180 |
| ROUTE_FLAT_START_KM / GC (mean shown by the runner: 1 769.7) | 1 746.9 / 1 767.8 | `run_geo.py cos`; endpoints = NAVERA's route test (48.8535, 2.3484) → (33.8439, 9.4001) |
| OFFSET_KM / LEG_OFFSET_M | 34.2 km / 1.09 m | `run_geo.py route` (leg 88–89 of 176, 10 044 m) |
| KM_PER_DEG_LON_ANCHORAGE | 53.736 | N(61.2181) = 6 394 600.3 m |
| SCALE_NORTH_ZERO_LAT_DEG | 54.81 | bisection on M·π/180 = 111 320 m (54.8085°) |
| GEOCENTRIC_DIFF_DEG | 0.1664 | 30° − 29.8336° |
| GEOCENTRIC_MAX_AT_DEG | 45.1 (45.096°; check accepts ±0.2) | tan φ = 1/√(1 − e²); max 0.1924°; EXPLAIN_GEOCENTRIC: the angles agree at 0° and 90° (graded on topic) |
| PREDICT_LEG (ungraded) | ≈ 1.10 m | 34.21 km × (10.044/1 767.8)²; run prints 1.09 m |
| PREDICT_SPHERE (ungraded) | +0.56 % / −0.11 % | 6 371/6 335.4 − 1, 6 371/6 378.1 − 1 |
| PREDICT_COS (ungraded) | ≈ −22 km / ≈ +1 km | lab's method: Δφ −15.0°, Δλ +7.05°, east with cos 48.85° / cos 41.35°, then √(e² + n²) (−21.9 / +0.9 km with these rounded spans); true −20.9 / +1.9 km. Scaling London → Paris's percentages gives about −72 km: that is the trap the lab warns about |
| Oracle Part 2 | gap −4.1 mm / −0.51 m = s³/(6R²); last column 7.8 / 196 m = d²/2R | a reversed Up axis is caught by the extra u = +100 line |
| DROP_M | −530.6 | Tallinn in Helsinki's ENU (e −10 486.5, n −81 634.7) |
| H_ELLIPSOID_M | 283.8 | 312.4 + (−28.6) |
| SPHERE_ERR_NORTH/EAST_PCT_QUITO | +0.561 / −0.112 | `compare_oracle.py` part 1 |
| D_1M_SOUSSE_M | 477.4 | results.json (grid value; Quito 220.4, Reykjavik 285.1; 10 m at 4 855.9 m) |
| slopes | 1.0 below 1 km everywhere; above 100 km 0.88 (Quito), 1.95 (Sousse), 1.98 (Reykjavik) | error_study |

Lesson numbers: London→Paris haversine 343 556.1 m, flat 341 087.6 / 343 603.3 / 346 121.9 m
(start / mean / end), bearing 148.1° / back 330.0°, great-circle midpoint (50.1886, 1.1466) vs straight
(50.1820, 1.1122): 2.56 km; New York–London figure max offset 736 km; WGS84 b = 6 356 752.314 m,
e² = 0.00669438; at 45° M 6 367 381.8, N 6 388 838.3, 111.132 / 78.847 km; Quito ECEF
(1 275 671.8, −6 252 140.0, −19 989.7); Cape Town → Cape Point ENU (6 706.6, −47 910.4, −184.1),
d²/2R at 48.4 km = 183.7 m; acos at 1 m north gives 0.996 m at 48° N, 1.005 m at 45° N.

**About R-2's "~17 km".** The backlog says the straight line was "~17 km" from the flown path. With the
route's endpoints (from NAVERA's own route test) the max gap is 34.2 km (nearest-point definition) or
34.7 km (same fraction); NAVERA's own test comment says "~35 km". The lesson does not quote 17 km
(rebuild-plan risk 11). If a student finds the 17 km in the backlog, it is a fine discussion: a figure
in a report must say how it was measured. R-6's 1 750 km is best matched by cos(start latitude): 1 746.9
km with R = 6 371 km, 1 748.9 km with 111 320 m/°; the backlog does not record the formula or the exact
end points.

## Rubric for written answers (check only verifies "written and on topic")

| Item | 2 — good | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_BEARING | great circle not constant-bearing; meridians converge so the angle changes; heading grows (right turn) flying SE in the north | "the Earth is round" only | wrong/absent |
| EXPLAIN_COS | names the start latitude as the closest candidate (1 746.9; 1 748.9 with 111 320 m/°; the last km unexplained — the backlog does not record the formula); mean latitude = typical value | one of the two | — |
| EXPLAIN_ROUTE | north-east (towards the pole), up to 34 km ≫ ±1 km, legs ≤ 10 km make the gap ~1 m | side or legs only | "west" / no reason |
| EXPLAIN_SPHERE | M(0) = 6 335 < 6 371 → N–S too long; N(0) = 6 378 > 6 371 → E–W too short | "the Earth is flattened" only | — |
| EXPLAIN_STUDY | slope 1 near home = scale error from the sphere's radius (≈0.2 % at Sousse, 0.56 % N–S on the equator); slope 2 far = curvature / meridian convergence (weak on the equator) | says curvature only | — |
| report.md | reproduces both bugs with numbers, recommends great-circle legs + ellipsoid/M–N for metre comparisons, distinguishes cancelling vs non-cancelling scale errors | numbers without reasoning | — |

## Difficulties expected (from wrong-solution testing; pilot with real students still to do)

- cos of the start latitude (runner: east 171 638.9); `math.cos` in degrees (274 803.0); missing date-line
  wrap (check: −38 million m at Fiji).
- `offset` with cos of the old latitude: only the 7th decimal differs — the runner shows ✘ with
  18.434938 vs 18.434937; Step 1 hint 3 explains.
- haversine with `math.` (fails on arrays; max_offset then crashes — both runner and check explain);
  missing factor 2 / missing /2.
- `atan2(north, east)` (301.9° for London→Paris), missing `% 360`, missing `math.degrees`.
- great circle by linear interpolation of angles; `f = k / n`; `atan2(z, x)` for latitude.
- max_offset with same-fraction pairs (2.558 instead of 2.48), `min(axis=0)`, metres instead of km.
- radii with degrees in sin, M/N swapped; Z with N instead of N(1 − e²); radians given to radii in the
  iteration; one iteration only (0.6 mm–0.4 m); E/N rows swapped (det −1); R instead of R.T; tuple
  subtraction without numpy.
- TODO A: `return` inside the loop (24.645), bearing in degrees (66.005).
All of these (43 mutants, lists in the round-1, round-2 and round-3 fix logs) were run against check.py and give the named
message; the runner self-tests (run_geo.py test, error_study.py self-test, compare_oracle direction check)
catch the same ones before the checker, except `% 360` (shown by `run_geo.py bearings`).

## Class plan (2 × 2 h 30 + reading)

- Before session 1: lesson §1–§4 (25 min). Session 1: Step 0 together (2 min, collect predictions on
  the board: east/west?), Steps 1–2 (45 min), Step 3 audit + short discussion "which latitude did the
  server use?" (15 min), Step 4 (45 min). Badge check.
- Before session 2: §5–§8 (25 min). Session 2: Steps 5–7 (70 min), Step 8 (10 min), Step 9 with
  predictions first (30 min), report (20 min).

**Fast students:** Going further (Bowring, ellipsoidal flat frame, rhumb line, two haversines).
**Struggling students:** give the 🧰 boxes first; pair them on TODO 5–6 and TODO 9; allow them to skip
TODO 6's broadcasting with a double loop (it passes the check, just slower).

## Notes for the lead

- Mission 04 gives `logbook.haversine_m` (same formula, numpy). 06 treats it as "you used it; now see
  why, and write geo's version" (lesson §3, lab Step 2, Going further "Two haversines").
- `tests/test_geo.py` exists in the reference (11 tests) for mission 14 onward; not shipped in 06.
- F-22 date-line failure, February 2007: verified by the expert review (CNN/DoD-reported; cause unpublished — the lesson says so).
- Durations (round 1 fix): lesson cut to about 3 800 words incl. formulas (reading 50 min, up to 1 h 15);
  lab 3–5 h; meta 5 h 30. The weak simulated student needed 1 h 45 + 5 h on the longer first version.
- Forward references: the lesson now says only "later missions use geo.py, finished". When 10 and 23 are
  rebuilt, mission 10 should move its simulated GPS with `geo.offset` and 23 use `geo` for photo → position.
