# Mission 31 — teacher notes: Simulation and fault injection

Rebuilt 2026-10-15 on NAVERA Lite. The old mission drove NAVERA's full simulator (ArduPilot SITL) and analysed
recordings that contained NAVERA output and paths: all removed. Students now fly **NAVERA Lite** in a headless
closed-loop world (`navera_lite/sim/`), as the test engineer of their own stack. NAVERA's simulator and SITL are
described in words and dated numbers only (VALIDATION_STATUS 2026-10-03, ENGINEERING_BACKLOG OUT-1…OUT-6); no base
code was read for this mission's facts.

## What the student builds (NAVERA Lite parts introduced here)

| Part | TODOs | Given |
|---|---|---|
| `navera_lite/output.py` — the messenger | 1 `decode_gps_input`, 2 `parse_frames`, 3 `lost_frames` | constants, `crc_x25`, `frame_crc`, `gps_time`, `gps_input_fields` (the honest-field rules), `encode_gps_input`, `ignored` (given since fix round 1) (byte-identical to pymavlink, checked at build) |
| `navera_lite/sim/sensors.py` | 4 `gauss_markov`, 5 `stationary_sigma`, 6 `autocorrelation`, 7 `rayleigh_quantile` | `sigma_for_median`, `GaussMarkov` (the world's receiver) |
| `navera_lite/sim/world.py`, `vision.py`, `run.py` | — | the world, the autopilot, the networks in the loop, the runner (`--mine`) |
| `campaign.py` (mission file) | 8 `latencies`, 9 `verdict` | metrics, report, plot, `run`/`report`/`one`/`test` |

**The world (sim/world.py).** Δt 0.1 s; kinematics with turn-rate and acceleration limits; GPS 5 Hz, Gauss–Markov
(τ 20 s, q 0.6, σ ≈ 1.9 m/axis), states σ 1.9 m (HDOP 0.95, = the model's stationary σ since fix round 1); faults gps ok/jammed/off/spoof_jump (2 km, seeded
direction)/spoof_drift (4 m/s), camera ok/blackout/late (1.5 s old, stamped on arrival)/delayed (1.5 s old,
honest stamp), imu ok/bias (3° tilt → alt·tan 3° shift of vision)/off (no vision), light day/night. Vision 1 Hz,
0.1 s after a GPS fix, 0.3 s latency; profiles target (15/25 m stated), measured (day median 440 m, night 25 %
motion; nothing stated), profile (a measured dict), mine (networks). The judge = 29's `Arbiter` wrapped by 30's
`GuardedArbiter` (guard on by default). The messenger sends each NEW winner measurement once and a no-fix frame
once a second in NO_FIX. **The autopilot** reads the link with the student's `parse_frames` + `decode_gps_input`
(only crc_ok True GPS_INPUT, fix_type ≥ 3), runs a CV Kalman filter with 28's `cv_model/kf_predict/kf_update`
(q 0.25, predicted with the IMU's measured acceleration: an INS), R = horiz_accuracy² or (100 m)² when the flag
says ignore, χ² gate 9.21, glitch reset after 5 s of refusals, failsafe (LAND drone/plane, HOLD boat/robot) after 5 s
without a usable fix. Rows every 0.2 s of mission time (since take-off).
Design §2.10's `sim/_lite` (rclpy stand-in) was not needed: the world calls the judge object directly — the same
object `ros/arbiter_node.py` wraps — so the world is pure Python and can be Sim Lite's world (see the build report).

**--mine.** `run.py` loads, each if finished (no stub marks, imports): `../29-arbiter/navera_lite/arbiter.py`,
`../30-spoofing/navera_lite/spoof.py`, `../28-kalman/navera_lite/kalman.py`; weights `../21-features/my_desc.pt`,
`../25-thermal-night/my_homography.pt` (loaded into the course's architectures, weights_only). Anything missing
or unfinished flies as the course's and the `# part` lines of the events log say why. Tested with the solutions
of 28/29/30/21/25 as sibling folders, with a stubbed arbiter and with a syntax error (fallbacks work).

**Vision "mine" (sim/vision.py).** Day: 480 × 360 photo, 90° camera, resampled from `day_ortho.png` (0.5 m/px) at
the true pose with a 1° (σ) unknown tilt, blur, gain, noise; map = the same ortho at 1 m/px; mission 22's
learned matching with the student's PatchNet (map descriptors computed once, ≈ 20 s, cached in
`my_runs/.map_features_<sha>.npz`), RANSAC similarity + gates. ≈ 0.7 s per fix on the CPU (a 100 s flight ≈ 2 min).
Night: mission 25's 64 × 64 pair (reference patch at the prior from `night_ref.png`, thermal patch at the truth
from `night_temp.png` through `thermal_camera`), HomographyNet offsets → centre shift. ≈ 0.1 s per fix.

## Alignment

| Objective | Lesson | Lab | Check |
|---|---|---|---|
| 1 test ladder, what a simulation proves | §1, §2, §6 | Steps 6, 11, 12 (EXPLAIN_PROVES, EXPLAIN_NETWORKS) | 15, 16 |
| 2 decode MAVLink, flags, lost frames | §3 | Steps 0–3 | 1, 2, 3, 4, 10 |
| 3 Gauss–Markov, autocorrelation, Rayleigh | §4 | Steps 4–5, 11 | 5, 6, 7, 15 |
| 4 expected values, campaign, verdicts, diagnosis | §5 | Steps 6–9, 12 | 8, 9, 11, 12, 13, 16 |
| 5 fly your own stack | §7 | Steps 10–11 | 14, 15 |

Badges: 📡 Messenger = checks 1–7; 🧪 Test engineer = all 16.

## Answer key (course's parts, deterministic; recomputed by make_expected.py)

**Session 1.** HEADER_LEN_BYTE 63 (yaw 0 → 2 zero bytes cut). Stream (13 399 bytes): (no longer asked) 182 frames (176 good
GPS_INPUT, 2 bad CRC, 3 HEARTBEAT, 1 "frame" of line noise with msgid 48897, crc_ok None); STREAM_BAD_CRC 2;
STREAM_LOST 6 (4 frames dropped by the generator + the 2 bad-CRC frames), STREAM_DOUBLED 1; VISION_FLAGS 189
(= 1 + 4 + 8 + 16 + 32 + 128; GPS frames 180); horiz_accuracy 1.9 and 15.0 m; first frame lat 35.8081271,
lon 10.5480014, week 2440, week ms 378 018 000 (2026-10-15 09:00 UTC). Noise (seed 31, 1 h): GM_SIGMA_MEASURED
1.964 (theory 1.902); autocorrelation 1 s 0.953, 10 s CORR_10S 0.636 (a⁵⁰ = 0.605), 20 s 0.441 (0.366), 60 s 0.163
(0.049) — one hour is only 180 τ: the estimate is noisy; 10 s averages spread 1.83 m (σ/√50 would be 0.27 m).
Rayleigh: PREDICT_RAYLEIGH_95 (2.45 σ; 36.72 m for σ 15); measured 17.7 / 36.8 / 45.6 for σ 15; 439.7 / 914.3 / 1135.0 for σ 373.7.

**Session 2.** JAM_RECOVER_S 3.4 (back at 70.0; the guard holds a returning GPS REFUSED until 2 agreeing vision fixes
— "jam, then spoof" — then the 2 s hold-off; false_refusal_s 1.4 in jam/off/jump/drift is that rule's price).
EXPECT_OFF_SWITCH_S 3.0 (gps_timeout_s; measured 3.0). EXPECT_JUMP_GATE_M 56 (30 × 0.2 + 50). EXPECT_DRIFT_REFUSED_S
16.0 (EXPECT_DRIFT_SIGMA_S_M = √(1.9² + 15² + 3²) = 15.41 m, γ 9.21, radius 46.7 m, crossed after 11.7 s → first disagreeing test at
12 s, 5th at 16 s). DRIFT_MEASURED_S 18.4 (IN_DOUBT at 12.4, one agreeing fix at 13.4 reset the streak, REFUSED
at 18.4; + 0.3 s latency). FAILED "R9".

| run | switch_s | recover_s | avail. | leak_s | max_err_m | error95_m | failsafe_s | false_ref_s | ap_max_err_m |
|---|---|---|---|---|---|---|---|---|---|
| baseline | – | – | 1 | 0 | 5.3 | 4.8 | – | 0 | 5.0 |
| jam | 0.0 | 3.4 | 1 | 0 | 56.2 | 31.8 | – | 1.4 | 14.3 |
| off | 3.0 | 3.4 | 1 | 0 | 45.1 | 32.7 | – | 1.4 | 13.0 |
| jump | 0.0 | 3.4 | 1 | 0 | 75.8 | 39.4 | – | 1.4 | 14.6 |
| drift | 18.4 | 3.4 | 1 | 0 | 76.4 | 49.1 | – | 1.4 | 93.0 |
| blind | 0.0 | – | 0.276 | 0 | 76.7 | 51.3 | 5.2 | 0 | 11.8 |
| plane_late | 4.4 | – | 1 | 0 | 137.0 | 121.5 | – | 40.0 | 88.7 |
| plane_delayed | – | – | 1 | 0 | 5.9 | 5.9 | – | 0 | 6.2 |

Verdicts R1–R8 PASS, **R9 FAIL** ("no GPS fault: an honest GPS is never refused"; plane_late false_refusal_s 40 > 0). Step 10's regression exercise (solution: confirm_n 2 → 6 in my_spoof.py; PREDICT_MINE written before the flight: +4 agreeing 1 Hz vision fixes → recover ≈ 3.4 + 4 = 7.4 s) moves R4 to FAIL (jam.recover_s 7.4 s); the events show `# part spoof: yours (my_spoof.py; changed: confirm_n 2 → 6)` and check 14 requires a change and re-flies jam to compare; refuse_n 5 → 2 or p_fa 0.1 move metrics only (drift switch 12.4 s; plane_late 45–45.6 s). The diagnosis: the plane's camera is 1.5 s
late and its pictures are stamped on arrival → each vision fix is 60 m behind (40 m/s × 1.5 s) but claims "now"
(vis_err_m ≈ 60) → the guard sees the honest GPS (gps_err_m ≈ 2) disagree: d² = 60²/(1.9² + 15² + 10²) ≈ 11 > 9.21,
5 in a row → REFUSED as a drift, the judge flies on the 60 m-wrong vision (max 137 m with noise), and the GPS stays
locked out (a refused GPS needs 2 AGREEING vision fixes). Fix: stamp at exposure (mission 20) — plane_delayed: 0 s
refused — or carry vision to the present (NAVERA's 2026-10-03 fix, lesson box after Step 9). The blind run's
max_err 76.7 m is the stale day fix (5 s old at 15 m/s) — good to discuss with "carried to the present".

Drift run, autopilot 93 m > NAVERA Lite's 76 m: after the refusal the autopilot's χ² gate refuses the jump back to
vision for 5 s (glitch reset at 53.4 s) while flying on its wrong belief — the closed-loop amplification of §2's ✏️.

Step 11 (course weights; the student's differ): day 39/40 fixes, median 2.43 m, p95 5.34, σ 2.07 → stated 5 m
(floor); night 80/80, median 25.43 m (NIGHT_MINE_MEDIAN_M), p95 83.05 (Rayleigh predicts 52.9: the network's
errors have a heavier tail than a Gaussian), σ 21.6 stated → FIX (a network at σ > 25 m states it and flies
DEGRADED: the Step 11 discovery). Each light has its own seed (3131 day, 3132 night); check 15 re-measures the
night alone with the read-only course tools and the student's weights (sha256 recorded in the profile). night_mine flight: NAVERA Lite max 94 m, autopilot
66 m (prior drift: the night network only corrects within ≈ ±90 m). day_mine: vision error ≈ 2–7 m, NAVERA Lite
median 12 m (positions up to 1.3 s old at 15 m/s).

Solution's own test (my_scenario.json): imu_bias_jam (bias at 20 s, jam at 30 s): ap_max_err_m 14.9 ≤ 20 PASS.

## Rubric for the written answers (the check only catches empty or off-topic text — tell students)

| Item | 2 (good) | 1 (partial) | 0 |
|---|---|---|---|
| EXPLAIN_63 | trailing zero bytes cut by MAVLink 2 + pad to 65 before unpacking | one of the two | "corrupted" |
| EXPLAIN_FLAGS | alt and horizontal velocity flagged, because vision does not measure them; inventing them would mislead the autopilot's filter | names the flags only | — |
| EXPLAIN_LOST | bad CRC → dropped → its seq is missing → counted lost (6 = 4 + 2) | "CRC error" without the link to seq | — |
| EXPLAIN_AVERAGE | correlation (τ 20 s ≫ 10 s) → effective samples ≈ 1 → spread barely drops; quotes the numbers | "correlated" only | "√50" |
| EXPLAIN_MEDIAN | median of the 2-D (Rayleigh) error = 1.177 σ per axis → σ = 440/1.177 | "different distribution" | — |
| EXPLAIN_DRIFT | noise broke the 5-in-a-row streak once (+2 s), vision latency 0.3 s; requirement = rule + margin | one cause | "the code is wrong" |
| EXPLAIN_FAIL | late pictures stamped on arrival → 60 m behind → guard refuses honest GPS (5 tests) → locked out (needs 2 agreeing) → names BOTH layers: honest exposure stamp (fixes the guard) AND carry to now with grown σ (the autopilot fuses on arrival; NAVERA's design); fix: exposure stamp / carry to present; confirmed by plane_delayed | stamp or delay, no chain | "the guard is bad" |
| EXPLAIN_MINE | the rule changed, PREDICT_MINE vs the result (requirement and value), why (e.g. +4 agreeing 1 Hz fixes) | rule and result without the why | — |
| EXPLAIN_NETWORKS | what the night network did (errors, failures) + optimism (synthetic, cut from the same reference) + needs real thermal frames/flight | two of three | — |
| EXPLAIN_MY_TEST / MY_* | a fault, a requirement written before, a coherent metric | a fault without a reason | — |
| EXPLAIN_PROVES | behaviour (logic, timing, integration) vs not accuracy (models, synthetic pictures, real sensors) | one side | — |

## Difficulties expected (no simulated-student run yet — see the build report)

- `parse_frames` resync rule (after a bad CRC, the next byte — not the next frame): the docstring and hint 4 state
  it; check 2's streams include noise inside frames.
- `d[:-0]` is empty in numpy (lag 0) — hint 4 of Step 4.
- `isinstance(True, int)` — hint 2 of Step 3.
- Students edit `campaign/*.json` to make R9 pass: check 12 refuses edited scenario files.
- `campaign.py one my_run` must use the scenario's own name (Step 12 says so).
- Day "mine" flight is ≈ 2 min of CPU (optional); vision_check ≈ 1 min.

## Class plan (2 × 3 h)

Session 1: 20 min §1–§3 together (decode one frame on the board from `mav_lab.py hex`), 60 min TODOs 1–3, 15 min
§4 (Gauss–Markov worked example), 45 min TODOs 4–7, 10 min debrief "why averaging does not help".
Session 2: 15 min §5 (the drift rule worked example, metrics), 30 min Steps 6–8, 45 min Step 9 in pairs (each pair
presents its diagnosis — do NOT give it), 30 min Steps 10–11, 30 min Step 12 + debrief §6 "what we proved".
Fast students: Going further (measured vision against a drift; IMU off + jam; the 10-bit week). Struggling: give
the drift computation of Step 8 in full; let them skip the optional day_mine flight.

## Mutants (wrong-but-plausible solutions; all caught)

| Mutant | Caught by (check) | Message (short) |
|---|---|---|
| no zero padding | 1, 10, 12 | "pad the payload with zero bytes up to 65 first" |
| lat/lon not /1e7 | 1, 10, 12 | "still in 1e-7 degrees — divide by 1e7" |
| lat // 1e7 (integer division) | 1 | "a whole number: divide by 1e7 with /, not //" |
| signature bytes ignored | 2 | "stream 3: … a signed frame's 13 extra bytes …" |
| jump the whole frame after a bad CRC | 2 | "stream 1: 3 frames found …" |
| no end-of-data check | 2 | "stream 1: 6 frames found …" |
| msgid from 1 byte | 2 | "a frame's msgid … (msgid: 3 bytes, little-endian)" |
| checksum read big-endian | 2 (+10, 12…) | "a frame's crc_ok is False, not right" (or, when no frame passes, "… little-endian") |
| lost without modulo | 3 | "after 255 comes 0: count modulo 256" |
| GM stores x before the step | 4–5 | "the first sample must already be one step after x0" |
| GM without √dt | 4–5 | "√dt multiplies q …" |
| GM with exp(−dt/τ) | 4–5 | "is not right (… a = 1 − dt/τ)" |
| continuous σ (q√(τ/2)) | 4–5 | "σ² = q²dt/(1 − a²), then √" |
| ACF divided by the overlap | 6–7 | "divided by the sum over the WHOLE series" |
| Rayleigh ln(p) | 6–7 | "ln(1 − p), not ln(p)" |
| latencies with > t0 | 8, 12 | "latencies(<rows>, 11.2, 13.6) … is wrong" |
| latencies: '' counted as GPS | 8 | "latencies(<rows>, 12.1, 13.5) … is wrong" |
| verdict strict < | 9, 12, 14 | "verdict(4.0, '<=', 4.0) gives 'FAIL'" |
| verdict None → PASS | 9 | "verdict(None, '>=', 0.95) gives 'PASS'" |
| FAILED wrong id | 13 | "FAILED is not the id of the requirement that fails" |
| vague EXPLAIN_FAIL | 13 | "does not explain the late, wrongly stamped pictures yet" |
| wrong σ_s (variances not summed) | 11 | "EXPECT_DRIFT_SIGMA_S_M … the SUM of the three variances" |
| hand-edited my_vision_profile.json | 15 | "not what vision_check.py measures with your night network" |
| results_mine.json copied from results.json | 14 | "results_mine.json: jam.error95_m is not what my_runs/mine/jam.csv gives" |

## Regenerating

1. `PYTHONPATH= python3 solutions/31-simulator/make_dataset.py` (corridor ≈ 3 min of Mapnik; `stream` needs the
   reference parts: run it from `solutions/_navera_lite` with `NAVERA_LITE_SIM_DATA` pointing at the dataset).
2. `python3 tools/lite_build.py 31-simulator`, then `python3 solutions/31-simulator/make_expected.py` (≈ 1 min) and
   `python3 solutions/31-simulator/make_figures.py`.
3. Re-run both whenever arbiter.py (29), spoof.py (30), kalman.py (28), learned_match/learned_desc (21–22),
   homography_net (25) or the reference weights change: every campaign number, the hidden flights and the answer
   key move with them.
