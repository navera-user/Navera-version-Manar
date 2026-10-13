# Mission 15 — teacher notes (GNSS receivers and NMEA 0183: from satellites to a trusted fix)

Teacher only. Rebuilt 2026-10-13 on NAVERA Lite: the students write `navera_lite/gnss.py` (reference in
`solutions/_navera_lite/navera_lite/gnss.py`, tags `# @part 15 todo 1–10`; `to_float`, `to_int`, `fields`,
`sentence_type`, `utc_seconds`, `parse_gsv`, `read_log` and the constants are given). `geo.py` (06) ships finished
for the runner's distances. No NAVERA code: the old `gps_filter.py` (copied NAVERA's reason texts),
`compare_with_navera.py` (pynmea2 vs the student) and `play_to_gps_node.py` (replay into NAVERA's driver) are
gone. NAVERA is described in words in the lesson's "In NAVERA" (backlog GPS-1/2/4/5, EST-6, validation report
2026-10-03, hardware table of the project report 2026-06-02).

**Trimmed (rebuild plan §B):** UERE, DRMS, 2DRMS, CEP and the UERE estimate move to mission 32 (the lesson
only says "DOP multiplies the range error"); GSV is light (`parse_gsv` given). **Fixed:** the old `dops()` raised
`LinAlgError` on singular geometry (and the 30° case returned plausible numbers): `dops` now returns `None`
on `matrix_rank(G) < 4`, and the lesson's warning box + the check's 30° case teach why `try/except` is not
enough. **Deferred:** the design's `to_estimate(gga, t_s)` (needs `estimate.py`, mission 12) and
`ros/nmea_node.py` (the ROS layer, 09–14) are not in this mission; they belong to the rebuild of 09–14 (see the
build report). The mission is pure Python.

Numbers: every value below comes from the reference — `python3 solutions/15-gps-nmea/expected.py`, and the
runner with the solution (`tools/try_lesson.py 15-gps-nmea --solution --shell "python3 run_gnss.py drive"`).
Data: `python3 solutions/15-gps-nmea/make_dataset.py` writes `datasets/15-gps-nmea/{sousse_drive.nmea,
truth.csv}` (public, seed 1507) and `courses/15-gps-nmea/hidden/exam_drive.nmea` (sealed, seed 2215). It must
never go back into `datasets/` (its docstring lists every trap).

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 validate and parse; what a checksum cannot catch | §1, §2 (XOR table), §3 fields, §4 GSA | Steps 1–2 (TODO 1–2), Step 4 (TODO 5), Step 5 (forge) | 1, 2, 5, 6, 7, 13 (exam log) |
| 2 degrees-minutes with ranges; ellipsoidal height | §3 | Step 3 (TODO 3–4, IMPOSSIBLE_UTC/WHY) | 3, 4, 6 |
| 3 DOP from (GᵀG)⁻¹, singular geometry, VDOP > HDOP | §5 (+ mission 01's H), warning box, 🧰 2×2 inverse | Steps 6–7 (TODO 6–7, sky incl. PREDICT_LOW/EXPLAIN_LOW, dop) | 8, 9, 10 (EXPLAIN_LOW, EXPLAIN_STREET) |
| 4 decide: qualities, σ = 2 m × HDOP, FIX/DEGRADED/NO_FIX | §6, bird's-eye view | Step 8 (TODO 8–10, drive), Step 9 memo | 11, 12, 13, 14, 15 |

Badges: **Line inspector** = checks 1–7 (session 1), **Fix judge** = all 15.

## Answer key

| Item | Value | Where it comes from |
|---|---|---|
| BYTES_PER_S / LINK_LOAD_PCT | 410.6 / 42.8 | 438 916 B ÷ 1069 s; ÷ 960 char/s (10 bits per character). 34.2 = 8 bits per character (check message) |
| BAD_LINES | 7 | lines 361 (GGA flipped digit, 05:13:00), 901 (GGA cut), 1382 (RMC, no checksum), 1801 (garbage), 3122 (GGA+RMC glued), 3664 (GSV non-ASCII byte), 4083 (GSA flipped VDOP "1906") |
| IMPOSSIBLE_UTC | "051731" | `3574.17098` (74′, digits swapped; checksum still right). Also printed by Step 0's naive table: the task is now completed by IMPOSSIBLE_WHY |
| IMPOSSIBLE_WHY | dm_to_deg's minutes < 60 rule refuses it; XOR is blind to the order of characters | graded on topic (two keyword groups) |
| FORGE_KM | depends on the swap; e.g. 2001.509; class record 8 546.9 km | brute force over the 804 one-swaps that stay FIX: best `01045.14417` → `11045.04417` (110.75° E); `35`→`53` in the latitude; `01045`→`10045` in the longitude moves 7 786.5 km (100.75° E, still ≤ 180°). Check: exactly one swap, valid XOR, lat ≤ 90 / lon ≤ 180 / minutes < 60, > 1 km, FORGE_KM within 1 % |
| STREET_EDOP / NDOP | 3.26 / 0.80 | `sky` part 3 (az 5, 350, 175, 190, 120, 260; el 30, 55, 40, 65, 75, 80) |
| PREDICT_LOW (ungraded) / EXPLAIN_LOW | VDOP drops more (2.32 → 1.75) than HDOP (1.36 → 1.22) | the low satellite's −u_U ≈ −0.21, unlike the others' strongly negative values: the Up column stops looking like the clock column, so height and clock separate; horizontally it is one more direction among six |
| PREDICT_ROTATE (ungraded) | HDOP, VDOP unchanged (1.36, 2.32); EDOP/NDOP swap roles (0.86/1.06 → 1.04/0.89) | geometry turns with the sky; HDOP = trace of a block, invariant under rotation |
| `sky` part 4 | adding a 7th low satellite: HDOP 1.36 → 1.22, VDOP 2.32 → 1.75 | lesson §5 ✏️ 1 |
| DOP_MAX_DIFF / HDOP_MAX | 0.005 (largest of HDOP 0.0050, PDOP 0.0050, VDOP 0.0049; ≤ 0.006 accepted) / 18.8 | `dop`: 1007 seconds compared, 1 skipped (damaged GSV); 2-decimal rounding |
| N_FIX / N_DEGRADED / N_NO_FIX | 976 / 30 / 63 | `drive`; NO_FIX = 54 quality 0 (cold start 12 s, underpass, town), 5 quality 6, 3 seconds without a valid GGA (flip, cut, glue), 1 "no position" (the 74′ line) |
| SIGMA_MAX_M | 37.6 | HDOP 18.8 in the alley (4 satellites), first at 05:27:19; 18.8 itself is caught as "the HDOP" |
| JUMP_UTC | "052421" | minute digits swapped (0.36′): 665 m in 1 s, σ 1.5 m; the gate refuses (> 150 m); 666.9 m from the truth |
| Exam log (sealed) | 7 bad lines; 975 FIX, 46 DEGRADED, 48 NO_FIX over 1069 GGA-like lines | GN talker, NMEA 4.10 GSA, lower-case checksum at 05:25:41, DGPS stretch (quality 2) 400–430 s, one GGA without HDOP (σ unknown) |

Lesson numbers: XOR table `GPGSA,A,1` → 32; 10 × 142 = 1 420 char/s; `3544.04006` → 35.734001,
`01034.55091` → 10.575849 (the RMC of the project report, 2026-06-02); ÷100 mistake 0.2936° = 32.6 km;
Cape Town −33.925000, 18.423333; h = 95.3 + 32.1 = 127.4 m (illustrative GGA); worked DOP example HDOP 1.155,
VDOP 2.236, PDOP 2.517, TDOP 1.414, GDOP 2.887, σ 1.63 / 4.47 m; 30° without zenith: on the Jetson (numpy 1.26.4) `inv` returns
VDOP ≈ 9.5 × 10⁷ (no error), 40° raises; figure "bunched NE": HDOP 16.2, VDOP 12.8, PDOP 20.6, ellipse 32.0 m ×
4.6 m along azimuth 33°; σ examples 1.44 m (HDOP 0.72), 40 m (HDOP 20), FIX ⇔ HDOP ≤ 12.5; NAVERA's σ is √2 ×
theory when EDOP = NDOP.

## Rubric for written answers (the check only verifies "written and on topic")

| Item | 2 — good | 1 — partial | 0 |
|---|---|---|---|
| EXPLAIN_BAD | names ≥ 4 of the 7 damages correctly, says the checksum (or the $/length rules) refused them | 3 kinds, or no link to the rule | list without reasons |
| EXPLAIN_FORGE | XOR is order-blind (commutative); the swapped value is in range ("impossible" vs "wrong": 53° N or 110° E are real places); only plausibility (jump gate vs the last trusted fix, another sentence/source) can see it; adds that a checksum is not a signature | one of the two halves | "the checksum is weak" only |
| EXPLAIN_LOW | low satellite → −u_U ≈ 0 breaks the Up ≈ k·clock proportion (fact 1), so VDOP falls; horizontally only one more direction | "it adds a satellite" only | — |
| IMPOSSIBLE_WHY | range rule (minutes < 60) + XOR order-blind | one of the two | — |
| EXPLAIN_STREET | satellites along N–S constrain north (ranges change when moving N/S), not east → EDOP ≫ NDOP; contrasts with the bunched-NE figure (error along the satellites there, because the bunch is on one side; here both ends of the street are seen) | the direction without the reason | NDOP larger |
| EXPLAIN_JUMP | valid checksum, minutes < 60, quality 1 → every gnss check passes; σ 1.5 m from HDOP 0.77 describes noise, not damage; refused by the jump gate (665 m > 150 m) | two of three | — |
| report.md | the three parts with the numbers, distinguishes damage (wire) / guessing (quality) / geometry (σ) / plausibility (gate), names what still gets through (slow drag, spoofer → cross-check, mission 30) | numbers without reasoning | — |

## Difficulties expected (from 29 wrong-solution tests; pilot with real students still to do)

Each mutant below was run against check.py and the runner; the message it gets is in quotes.

| Mistake | Caught by | Message (short) |
|---|---|---|
| `f"{x:X}"` (no leading zero) | check 1, runner | "gives 'B': always 2 UPPER-case digits" / runner "A" vs "0A" |
| case-sensitive hex compare | check 2, 13 | "gives False for lower-case hex digits"; runner: "compare with given.upper()" |
| no strip | check 2 | "False for a good line ending with \r\n"; runner: "strip the line BEFORE…" |
| no `$`-inside check | check 2 | "`$GPGGA,1$GPGGA,2*27` gives True" (a glued pair whose XOR matches) |
| no minutes/degree range | checks 3, 4, 13 | "60 minutes must give None" |
| ÷ 100 | checks 3, 4 | "you divided by 100 — the last two digits … are MINUTES" |
| W not negative | checks 3, 4 | "W must be negative" |
| h_ell_m = MSL | check 4 | "is the sea-level altitude — add the geoid separation" |
| GSA `len(f) == 18` | check 5 | "a GN line with a system ID should be a dict, got None" |
| degrees in np.sin | checks 8, 9 | "degrees given to np.sin/np.cos?"; runner shows [[-0.1379, 0.0691, 0.988, 1.0]] |
| try/except around inv | check 9 | "four satellites at 30° (numpy's inv does NOT fail here: test the rank)" |
| HDOP with Q_UU | check 9 | "your HDOP includes Q_UU" |
| quality 6 after the generic rule / 6 treated as usable | checks 11, 13 | "the docstring asks for 'receiver dead reckoning (quality 6)'" / "gives 'FIX', expected 'NO_FIX'" |
| σ instead of σ² | checks 12, 13 | "cov[0] is σ (2.7 m), not the variance" |
| Up = 2σ² | check 12 | "its variance is (2σ)² = 4σ²" |
| unknown → `None` cov / HDOP 0 counted as known | check 12 | "still nine numbers (0.0)…" / "an unknown accuracy is (nine 0.0, 0)" |
| `>=` | check 13 | "HDOP 12.5 gives σ = 25.0 m exactly: that is FIX — use >" |
| hard-coded 25 m | check 13 | "fix_state ignores its fix_max_sigma_m argument" |
| GSA slice `f[3:14]` (12th PRN lost; r1 weak) | check 5; runner test; `dop` ⚠ (PDOP 0.0986, VDOP 0.1179) | "with all 12 slots used, your prns lose the last one … f[3:15]" |
| h_ell_m with only the geoid tested (crash on empty altitude; r1 weak) | check 4; runner | TypeError + "add the two heights only when BOTH exist" |
| latitude accepting E/W (r1 strong) | check 4; runner | "a latitude needs hemisphere N or S, a longitude E or W" |
| negative raw degrees-minutes accepted | check 3 | "a negative value … must give None" |
| length tested before strip (r2 weak) | check 2; runner | an 80-character line + \r\n → True: "strip BEFORE you test the length" |
| 90° limit also for E/W (r2 weak) | check 3; runner; `forge` | "a longitude may go up to 180°…" / forge: "X° E is a real longitude…" |
| `if … return True` without `return False` | check 2; runner | "is_valid returned None: … finish the function with `return False`" |
| geoid from field 10 | check 4; runner | "geoid_m is None, expected 32.1 — the geoid separation is field 11" |

Answer traps with their own messages: LINK_LOAD_PCT with 8 bits (34.2), STREET_EDOP/NDOP swapped,
SIGMA_MAX_M = 18.8 (the HDOP), FORGE_KM in metres, a forged line with two changes or 74 minutes.

## Class plan (2 sessions of about 2 h 15 to 2 h 30, plus 1 h of reading; meta 5 h 30)

- **Before session 1:** lesson §1–§4 (30 min). **Session 1:** Step 0 together on the projector (the naive
  reader's 50 km spike: it lands at sea, in the Gulf of Hammamet), then Steps 1–5. At the end, collect two forged lines on the board: who moved the fix
  the farthest with one swap (degree digits: 2 000 km; longitude `0`↔`1`: 7 787 km; best 8 546.9 km), and why no checksum
  can see it.
- **Before session 2:** §5–§6 (30 min). **Session 2:** Step 6 predictions first (vote: EDOP or NDOP?), then
  Steps 6–9. Debrief: σ = 2 m × HDOP describes noise; the 05:24:21 line (σ 1.5 m, 667 m off) is the reason a
  judge needs the jump gate and the cross-check.
- **Differentiation.** Fast: Going further (weighting, property test, RMC cross-check). Struggling: give the
  🧰 boxes and Step 3 hint 5 early; TODO 6–7 can be done with the lesson's worked example open; pair
  students on TODO 10's hand trace.

## Known limits

- The data is synthetic (the only real NAVERA receiver record is one RMC line). The receiver model is simple:
  integer az/el, unweighted DOPs, a single "alley" block for DEGRADED. Real receivers weight satellites and
  smooth positions.
- Pilot with real students and simulated-student reviews: still to do (timing 3–5 h of lab is an estimate).
