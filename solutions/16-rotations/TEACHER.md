# Mission 16 — teacher notes (Rotations and quaternions: describing an attitude)

Teacher only. Rebuilt 2026-10-13 on NAVERA Lite (`navera_lite/rotations.py`, reference in
`solutions/_navera_lite/navera_lite/rotations.py`, tags `# @part 16 todo 1–11`; given: `IDENTITY_Q`,
`q_normalize`, `rot_x`, `q_from_euler_zyx`, `heading_deg_from_q`, `rpy_human`). This is the FIRST HALF of
the old mission 16: the IMU (gyro integration, tilt from gravity, complementary filter, declination) is
mission 17. No NAVERA code: the old "compare with NAVERA" is `compare_oracle.py` against
`scipy.spatial.transform.Rotation` (SciPy 1.13.1 is installed in the sandbox; without SciPy the script
falls back to three course reference values and check.py skips its oracle checks with a message).

Regenerate: `python3 tools/lite_build.py 16-rotations` (starter + solution of the part),
`python3 solutions/16-rotations/make_dataset.py` (datasets/16-rotations/, seed 16),
`python3 solutions/16-rotations/make_figures.py` (assets: cold_open, frames, order, gimbal, qtrap; slerp.svg
is hand-drawn from the old lesson, schematic). Tests of the part: `navera_lite/tests/test_rotations.py`
(shipped from mission 17 on, not here).

## Conventions (the 16/17 pitch bug is closed here)

ENU world, FLU body, `R = Rz(yaw)·Ry(pitch)·Rx(roll)` with the **ROS** pitch (positive = nose DOWN),
quaternions **(x, y, z, w)** everywhere, heading = (90° − yaw) mod 360. The "human" angles are
`rpy_human(q) → (roll, pitch_up, heading)` with pitch_up = −ROS pitch — the same rule as NAVERA's own
human-readable attitude (checked in base/ on 2026-10-13: pitch positive nose up, roll positive right wing
down). Every runner line says which pitch it prints. Mission 17 must use the same functions.

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 compose and invert in the right order; columns = axes | §1 signs, §2 matrices, order figure, ✏️ Rz·Ry vs Ry·Rz | Step 0, Step 1 (TODO 1–2, pitch), Step 2 (TODO 3, order) | 1, 2, 3, 5, 6 |
| 2 Euler ↔ matrix, gimbal lock | §3 worked example (10°, 5°, 60°), gimbal figure, ✏️ lock | Step 3 (TODO 4, gimbal, LOCK_UP_YAW, NEAR_LOCK) | 4, 7 |
| 3 quaternions: ⊗, conjugate, rotate, slerp, angle | §4 worked q⊗v⊗q*, §5 slerp worked example | Steps 4–6 (TODO 5–11, pose, slerp) and Step 7 (oracle) | 8, 9, 10, 11, 12, 13 |
| 4 read/check conventions, diagnose a bug | §1, order-trap box (qtrap figure), common wrong ideas, In NAVERA | Step 5 (pose), Step 8 (detective TODO A–B), Step 9 (memo) | 5, 12, 14, 15 |

Badges: **Attitude reader** = checks 1–7 (session 1), **Quaternion detective** = all 15.

## Answer key

| Item | Value | Where it comes from |
|---|---|---|
| PITCH_UP_DEG | −6.88 (check: −6.8755 ± 0.05) | −degrees(0.12); `run_rotations.py pitch` prints the nose (+0.993, 0, −0.120) |
| PREDICT_ORDER (ungraded) | A: left wing **up**; B: left wing **west** | `run_rotations.py order`: A nose north, top east; B nose up, top south |
| EXPLAIN_ORDER | not the same attitude; A = yaw first, then roll about the new nose | left-to-right reading about moving axes. The check refuses an answer naming only B, and one naming no letter |
| PREDICT_LOCK (ungraded) | all four → (0°, 90°, 45°, locked=True) | yaw − roll = 45° for every pair |
| LOCK_UP_YAW_DEG | 80.0 | roll 30°, ROS pitch −90°, yaw 50°: at −90° only ψ + φ survives. 20 = used ψ − φ (+90° rule); 50 = no lock guard (rounding noise; roll ≈ 30, locked False) |
| NEAR_LOCK_YAW_JUMP_DEG | 63.43 | `gimbal`: ROS pitch 89.5°, then 1° about world east (x) → roll 63.44°, pitch 88.88°, yaw 63.43° |
| POSE (−0.1245, 0.0134, −0.8834, 0.4516) | roll −8.00°, pitch_up 12.00°, heading 215.01° (check: 11.997 / 215.005 ± 0.1) | made from roll −8°, pitch_up 12°, heading 215°, rounded to 4 decimals (length 1.000009) |
| Q360_W | −1.0 | cos(2π/2); +1 = forgot the half angle |
| PREDICT_LERP (ungraded) | the lag at t = 0.2: 5.45° (the lesson's 20° turn: 0.0095° at t = 0.25); the error grows much faster than the turn angle | |
| LERP_ERR_DEG | +5.45 | `slerp`, t = 0.2: slerp 42.00°, linear 36.55° (t = 0.1: 26.00 / 22.25; t = 0.5 equal; lerp length 0.766 at mid) |
| PREDICT_SUSPECT (ungraded) | (a) pitch sign: pad row unchanged (roll 0, heading 30); (b) conjugate: roll 0, heading 150; (c) order swap: roll 60, heading 270 — only (c) fits the real row | recomputed with the reference |
| PAD_HEADING_DEG | 30.0 | detective line 1 (t < 9 s) |
| COLLEAGUE_PAD_ROLL_DEG | 60.0 | colleague: roll 60.0°, pitch_up 0.0°, heading 270.0° |
| COLLEAGUE_MAX_TILT_DEG | 174.0 | at t = 111.7 s, true heading 270.5° (true max tilt 13.5°) |
| FLIP_T_S | 111.4 (111.5 accepted) | detective line 5: q0·q1 = −1.0000, q_angle_deg 0.356° |
| Line 4 of detective | largest step 1.520° in both readings, difference 0.00e+00° | the permutation keeps every 4-D dot product |
| Line 0 of detective | 0.05° (the colleague table is rounded to 0.1°) | misread + rpy_human |

Lesson numbers (all from the reference, `make_figures.py` and the runner): Rz(30°)·east = (0.866, 0.5, 0);
(10°, 5°, 60°) → R rows (0.4981, −0.8453, 0.1933), (0.8627, 0.5055, −0.0125), (−0.0872, 0.1730, 0.9811),
q = (0.0537, 0.0812, 0.4943, 0.8638); ✏️ §1: yaw −135° → heading 225°, 0.2 rad = 11.46°;
✏️ §2: Rz(90)Ry(90)·x = down, Ry(90)Rz(90)·x = north; ✏️ §3: (10°, +90°, 40°) → (0°, 90°, 30°);
§4 worked: q⊗v = (0.7071, 0.7071, 0, 0), then (0, 1, 0, 0); 180° about x sends (0, 1, 0) to (0, −1, 0);
§5: q0 = (0, 0, 0.6428, 0.7660), q1 = (0, 0, 0.7660, 0.6428), d = 0.9848, Θ = 10°, slerp(0.25) =
(0, 0, 0.6756, 0.7373) = yaw 85°; normalised lerp 4.9905° instead of 5° (behind); d > 0.9995 ⇔ less than 3.62°
apart; mission brief 150 m · tan 10° = 26.4 m. Order figure: Rx(90)Ry(90): nose north, fin east;
Ry(90)Rx(90): nose down, fin south.

Round 1 additions (all recomputed): gimbal-lock box R = [[0, −sin(ψ−φ), cos(ψ−φ)], [0, cos(ψ−φ), sin(ψ−φ)],
[−1, 0, 0]] at θ = +90° (difference to the reference matrix < 1e-16); "two stories" box Rz(90°)·Ry(90°)·(0, 0, 1)
= north; §4 second product (0.7071, 0.7071, 0, 0) ⊗ (0, 0, −0.7071, 0.7071) = (0, 1, 0, 0) (cross term
(−0.5, 0.5, 0)); 🔬 box cos α·v + sin α·u × v (checked with q_rotate); Check yourself 4 (0, 0, 0.5, 0.8660) →
yaw 60°, heading 30°; Going further max turn rate 1.520°/0.1 s = 15.2°/s < 30°/s.

**Apollo 11 quote (verified 2026-10-13).** NASA Apollo Lunar Surface Journal, "Gimbal Angles, Gimbal Lock,
and a Fourth Gimbal for Christmas" (E. M. Jones and P. Fjeld, rev. 29 April 2011,
apollojournals.org/alsj/gimbals.html): 104:59:35 Garriott (CapCom): "Columbia, Houston. We noticed you are
maneuvering very close to gimbal lock. I suggest you move back away. Over." … 105:00:30 Collins: "(Faint,
joking) How about sending me a fourth gimbal for Christmas." About two hours after the landing. Same page:
in the LM the computer flashed a gimbal-lock warning at 70° and froze the IMU at 85° (Fjeld); MIT document
E-1344 (D. Hoag, 1963) discussed and declined a redundant fourth gimbal. The lesson quotes only these.

**NAVERA facts used** (ARCHITECTURE.md; VALIDATION_STATUS.md and ENGINEERING_BACKLOG.md, 2026-10-03):
attitude interpolated at the exposure, unusable without an attitude within 0.2 s, fixed camera refused
above 30°/s, tilt > 45° refused, yaw read from true north; straightening benchmark 33/33 within 2.9 m
(300 m, roll 0/10/18°, BNO085-class noise); celestial ~111 km per degree, 5.5–6.5 km perfect attitude,
24–119 km BNO085-class (simulated star fields); IMU-3 open (chip frame to confirm with a known heading).

## Rubric for written answers (check only verifies "written and on topic")

| Item | 2 — good | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_PITCH | axis = +y (left wing), right-hand rule carries z → x, so x → −z: nose down; pilot sign opposite | "the convention says so" with the right direction | wrong direction |
| EXPLAIN_ORDER | names A, and the moving-axes (left-to-right) vs fixed-axes (right-to-left) reading | names A without the reason, or the reason without a clear choice | B / no reason |
| EXPLAIN_LOCK | roll axis lines up with yaw axis at ±90°, one DOF lost (only ψ ∓ φ); Apollo: 3 gimbals kept, warning/avoid, realign on stars | one of the two halves | "a bug in atan2" |
| EXPLAIN_SLERP | chord inside the sphere: short, normalised steps uneven; slower at ends, faster in the middle | "it is not normalised" only | |
| EXPLAIN_ORACLE | independent code + many random cases vs own (possibly same-misunderstanding) examples; ZYX yaw-first order / (x, y, z, w) | one of the two | |
| EXPLAIN_DETECTIVE | cause (w read first), what looks wrong (60° roll on pad, near upside-down flying west, heading stuck near 270), what does not (length 1, step angle identical), why (same permutation every sample), and line 5: q and −q are the same attitude (0.36°) | cause + one symptom | no cause |
| report.md | the three sections answered with numbers; a concrete test (known non-trivial attitude at the input boundary) and/or an independent comparison | numbers but vague prevention | |

## Mutants run (24; all caught; the message is the check's ✘ line)

rot_y sign (check 1 "turns the wrong way… −sin goes in row 2, column 0"; also check 3 via nose); euler order
Rx·Ry·Rz ("wrong ORDER"); `*` instead of `@` ("multiplies element by element"); no lock guard ("`locked`
must be True"); no clamp ("math domain error … clamp it first"); q_mul w-first ("reads its inputs as
(w, x, y, z)"); q_mul cross reversed ("returns q ⊗ p"); full angle ("used the FULL angle"); q* v q ("turns
the vector the WRONG way"); q_to_matrix transposed ("returns the TRANSPOSE"); q_to_matrix not normalised
("length 2.5 … normalise"); slerp without shortest path ("… fails when q1 is given as −q1"); q_angle without
abs ("gives 269.54° instead of 90.46° … absolute value"); misread shifted the wrong way ("shifts the
numbers the wrong way"); tilt in radians ("returns radians"); PITCH_UP_DEG positive ("wrong sign"); q_conj
negating w ("changed w"); axis not normalised ("was not normalised"). Round 1 added: q_to_matrix sign typo
in one x/y term (check 10; `test` now has lesson §4's non-yaw example: "one of the 2·(…) terms has a wrong
sign"); q_angle_deg without clamp/normalisation (check 11 "q_angle_deg(q, q) must be 0 (clamp …)"; `test`
line "rounding makes q · q = 1.0000000003"); no ValueError for a zero axis (check 9; `test` line);
EXPLAIN_ORDER naming B (expert's overlay) and naming no letter; EXPLAIN_DETECTIVE without the line-5 idea. Each also gets a matching ✘ line in
`python3 run_rotations.py test` (except misread/tilt, which detective.py line 0 / check 14 report).
Overlays: /tmp/claude-1000/mut/ when built (regenerate with any small edit of the reference).

## Difficulties to expect (not yet seen with simulated students — to confirm in the pilot)

- The ROS pitch sign (Step 0 is there to make the surprise visible). Students who "fix" rot_y to get a
  nose-up pitch break TODO 3 and the oracle: point them to frames.svg and the right-hand rule.
- Radians vs degrees at the interface (all part functions take radians; only the human functions return
  degrees). The runner and check name the mistake.
- (x, y, z, w) unpacking: students coming from Eigen/textbooks write w first in q_mul; the runner's i⊗j
  line names it.
- "Reading a product left to right vs right to left" (EXPLAIN_ORDER) is the hardest written item; accept a
  correct choice with either reading.
- The detective's TODO A is two lines but conceptually confusing ("what the script believed" vs "our
  order"): hint 1 gives the unpacking idea; detective line 0 confirms.

## Class plan (2 × 2 h + reading)

Session 1: 10 min Step 0 + frames figure with a hand (right-hand rule, everyone does +pitch with a pen);
25 min §2 order with a book; 45 min TODO 1–3; 30 min §3 + gimbal (show the Apollo page) + TODO 4.
Session 2: 20 min §4 worked q⊗v⊗q* on the board; 50 min TODO 5–11; 15 min oracle; 35 min detective in
pairs (one reads the log, one the table), memo as homework.
Differentiation: fast — Going further (other sequences' locks, the tilt-error Monte Carlo); struggling —
skip Step 7's explanation detail, give hint 2 of Step 4 orally, pair for Step 8.

## Notes for the lead

- `datasets/16-rotations/` now holds only `attitude_log.csv`, `colleague_attitude.csv`, README.md (the old
  IMU log and its generator moved conceptually to 17; `datasets/17-imu/` already has the identical
  `imu_log.csv`; its `make_dataset.py` generator is still in datasets/17-imu/ — the 17 builder should move
  it to solutions/17-imu/).
- API fixed for 17/18/20/26 (radians in, numpy out, (x, y, z, w)): `rot_x/rot_y/rot_z(angle_rad)`,
  `euler_zyx_to_matrix(roll_rad, pitch_rad, yaw_rad)`, `matrix_to_euler_zyx(R) → (roll, pitch, yaw, locked)`,
  `q_mul`, `q_conj`, `q_from_axis_angle(axis, angle_rad)`, `q_rotate(q, v)`, `q_to_matrix(q)`,
  `slerp(q0, q1, t)`, `q_angle_deg(q0, q1)`, given `q_normalize`, `q_from_euler_zyx`, `heading_deg_from_q`,
  `rpy_human`, `IDENTITY_Q`.
