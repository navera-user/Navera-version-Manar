# Mission 04 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

The mission runs in two sessions: **Session 1 — Clean & measure** (Steps 0–4, badge **Log keeper** when checks 1–5
pass: the `log-keeper` milestone) and **Session 2 — Detect & report** (Steps 5–10, badge **Flight-test analyst** when
the mission is passed). Students write `navera_lite/logbook.py` TODO 1–7 (reference:
`solutions/_navera_lite/navera_lite/logbook.py`; rebuild with `python3 tools/lite_build.py 04-python-data`). TODO 7
(`unit_suspects`, Step 8) is the non-scaffolded challenge: docstring only, one collapsed "stuck after 20 minutes" box.

The campaign is **synthetic** (no NAVERA code or data), made by **`solutions/04-python-data/make_dataset.py`**
(teacher only: its docstring lists every planted defect; seed 404; `--seed N --out DIR` makes other campaigns). It
writes only the outputs and a neutral README into `datasets/04-python-data/`, mounted read only at
`/data/academy/04-python-data/`. Nothing a student can see names a defect (README, sheet notes, meta summary, the
check hints shown at the end of session 1).

## Objectives → practice → assessment

check.py: 1 TODO 1 · 2 TODO 2 · 3 TODO 3 · 4 Step 1 · 5 Steps 2–4 · 6 TODO 4 · 7 TODO 5 · 8 TODO 6 · 9 Step 6
corrections · 10 Step 6 unplanned outage · 11 Step 7 · 12 TODO 7 · 13 results.json · 14 report.md.

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. Clean with written rules, count each rule | §1 (NaN and masks), §2 (rule order) | Steps 1–2 (TODO 1) | 1, 4, 5, 13, 14 |
| 2. Per-flight quantities with groupby, without mixing flights | §3 (first-row NaN) | Steps 3, 5 (TODO 2, 5) | 2, 5, 7, 13 |
| 3. Outages as runs, and their durations | §4 | Steps 4–5 (TODO 3, 4) | 3, 5, 6, 10, 13, 14 |
| 4. Mean/σ vs median/MAD, percentiles, and the choice | §5 (σ 9.5 vs 1.6) | Step 7 (TODO 6) | 8, 11, 13, 14 |
| 5. Find systematic errors before any statistic | §6 (Quito clock) | Steps 0, 6, 8 (TODO 7) | 9, 10, 12, 13, 14 |

## Answer key

- Step 0 (`naive`): monastir_coast 8 274.2 km (a step to Null Island and back), top speed 2 066 494 m/s,
  sahel_hills max altitude 9 999 m, logged speed up to 76.1 "m/s" (grid_survey, km/h). The distances of sahel_hills
  (28.5 km) and sousse_port (27.6 km) include the jump from the previous flight's last row: no groupby.
- Step 1: `ROWS_RAW = 1402` (wc -l prints 1403 with the header). Mini-challenge: `cut -d, -f1 … | sort | uniq -c |
  sort -rn | head -n 2` → `MOST_ROWS_FLIGHT = "sahel_hills"` (426; grid 323, monastir 320, sousse 333);
  `cut -d, -f3 … | grep -c '^$'` → `EMPTY_LAT_ROWS = 31`. `DROPNA_ROWS_LOST = 119` (31 positions + 44 speeds +
  49 batteries, overlapping). `describe()` shows max alt 9999, min lat/lon 0.0, max speed 76.1.
- Step 2: removed `{"duplicates": 3, "null_island": 1, "bad_altitude": 1}`, 1397 rows left, 31 empty positions
  kept. `PREDICT_CLEAN` is graded as written; most students expect more removals.
- Step 3: the fastest step of every flight is a **day**-vision step (`FASTEST_SOURCE = "day"`): monastir 332 m
  (166 m/s), sousse 392 m (196 m/s), sahel 531 m (265 m/s), grid 47.5 m (23.7 m/s, ordinary noise). Four day
  matches were planted with jumps of 300, 380, 450 and 520 m (QA-9-like). They are not removed by cleaning: they are
  real behaviour of the source, and Step 7 shows what they do to σ.
- Step 4: `PREDICT_RUNS` answer `[(0, 2), (4, 5), (6, 9)]` (graded as written). Runs in the campaign (row numbers
  inside each flight): grid (300, 308), monastir (149, 179), sahel (279, 425), sousse (100, 130), (210, 260).
- Step 5 (no answers to copy; the numbers go into the report): grid 1 / 16 s, monastir 1 / 60 s, sahel 1 / **292 s**
  (rows 560 s → 850 s + 2 s; the outage ends 09:24:12, 2 s after the sheet's landing, because the last row stands
  for one logging period), sousse 2 / 100 s longest, 160 s total. States (% FIX / DEGRADED / NO_FIX): grid
  97.5 / 2.5 / 0.0, monastir 90.6 / 9.4 / 0.0, sahel 65.6 / 31.8 / 2.6, sousse 75.8 / 18.1 / 6.0.
- Step 6: before corrections, `schedule` shows sahel_hills 10:19:20–10:24:12 UNPLANNED and "jammer on
  09:19:20 → 09:35:00 but NO outage", plus sousse 08:27:00 UNPLANNED. Evidence: sahel's first logged time 36 600 s =
  10:10:00 vs take-off 09:10:00 on the sheet (+3600 s; Tunisia is UTC+1 all year), and its logged 10:10–10:24 overlaps
  grid_survey (10:05:00–10:15:44) with the same drone LITE-2. grid_survey: median logged speed 71.92 vs 19.96 m/s from
  positions, ratio 3.60 → km/h (and 72 > the 30 m/s of mission 03's VEHICLES["drone"]); other flights 0.97–1.00.
  `CLOCK_FIX_S = {"sahel_hills": -3600}`, `SPEED_FACTOR = {"grid_survey": 1/3.6}` (check: ±0.002). With corrections,
  `schedule` prints the checks: sahel's first row 09:10:00 = sheet take-off, grid's corrected ratio 1.00.
  `UNPLANNED_FLIGHT = "sousse_port"`, `UNPLANNED_START_UTC = "08:27:00"` (to 08:28:40, 100 s, the "port cranes"
  outage of the generator; the report should flag it for investigation, not explain it away). Reference script:
  `detective.py` in this folder.
- Step 7: theory (lesson §5): GPS √2·1.5/2 = 1.06 m/s, with 0.3 m/s logged noise √(1.06² + 0.3²) = **1.10**; day
  √2·6/2 = 4.24, with 0.3: **4.25** m/s. Measured, with corrections: gps n 1095, mean 0.005, std 1.190, median 0.013,
  **mad_sigma 1.188**, p95 |err| 2.170; day n 224, mean 7.093 (0.83 without the 7 jump errors), std **35.689**, median
  1.078, **mad_sigma 3.745**, p95 9.192. Without corrections: gps mean −14.2, std 23.3, median −0.55, mad_sigma 1.98,
  p95 53.5 — the km/h flight is a third of the GPS rows, so the robust statistics moved too (1.19 → 1.98; day 3.75 →
  4.28).
  **Measured vs predicted.** Regenerating the campaign with 40 other seeds (`make_dataset.py --seed 1000…1039`,
  verified 2026-10-13, also reproduced by the expert reviewer) gives day 4.11 ± 0.31 (3.41–4.69) and gps 1.11 ± 0.03
  (1.04–1.19) m/s. GPS: the formula is right (1.10). Seed 404's 1.188 is 2.2 spreads high with the 1.17/√n scatter of
  0.036 (2.6–2.7 with the lab's rounded 1.11 ± 0.03: accept anything from 2 to 3), higher than all 40 other
  seeds (max 1.187): an unlucky campaign (a 2.2-spread gap either way happens about 1 time in 35), and with 1 095 errors the
  scatter is only 3 % (1.17/√n). A student who says "larger than the scatter" is right. Day: 3.75 is 1.2 spreads
  below 4.11, ordinary sampling with 224 errors (8 %). And 4.11 itself is about 3 % below the formula's 4.25: not
  sampling (standard error of the 40-seed mean 0.05), but the limit of a linear formula: a 6 m noise is not small
  against a 20 m step, so part of it becomes the positive bias below and not spread (expert's simulation: 4.07 at
  10 m/s, 4.15 at 14, 4.20 at 20). The gps↔day transition rows change nothing measurable. Debrief: one gap is chance,
  one is the limit of a linear formula; telling them apart needs the scatter (1.17/√n) and a simulation. The lab's
  Step 7 "read after the run" box gives students these figures (collapsed, so it does not spoil PREDICT_NOISE).
  **Day's median error is positive (+1.08; 0.98 ± 0.27 over the 40 seeds):** a speed from positions is the length of
  a noisy step; cross-track noise always lengthens it, by about σ²/(v·Δt) metres, i.e. σ²/(v·Δt²) in speed: +0.9 m/s
  at 10 m/s (sahel, most day rows), +0.64 at 14 m/s; GPS +0.06 at 10 m/s, +0.03 at 20. Verified by simulation
  (median bias 0.89 / 0.63 m/s for day, 0.054 / 0.026 for GPS). The jumps add only positive errors (7 beyond +20 m/s, none below −20: `out/noise.png`).
- Step 8 (TODO 7): on the raw campaign `unit_suspects` → `{"grid_survey": "km/h"}`; check 12 uses a knots flight with
  a wild position speed (medians needed), a km/h flight 2.8 % off 3.6 (relative tolerance needed), a 1.04 flight
  (left out with tol 0.05, "?" with tol 0.02), a 1.30 flight ("?"), a second knots flight t (ratio 1.945: catches an
  inverted ratio or the 0.5144 factor) and a flight w with ratio 0.5 ("?": catches a one-sided test).
- Step 9: results.json (rows 1402 → 1397, longest sahel 292 s, one unplanned outage, no jamming window without
  outage, noise as Step 7). The runner prints only a one-line summary; the file is read in the editor. A model report
  is `report.md` in this folder.
- Going further: nearest-rank vs linear p95 of |error| on the 224 day errors: 9.25 vs 9.19 m/s (almost the same on
  a large sample); on the lesson's nine errors p90 is 6 (nearest) vs 54.8 (linear). 10 s speeds (`shift(5)`): robust σ
  gps 1.19 → 0.49, day 3.75 → 0.99 m/s — less than the 5× of the formula, because the logged speed's own noise and
  the speed changes within 10 s now dominate. sahel_hills: 10 407 m with every step, 8 500 m without the 4 steps
  longer than 100 m (two jumps, in and out): the jumps add about 1.9 km; the median step is not moved.

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_KEEP_NOFIX | NO_FIX rows are real moments with no position; dropping them shortens or removes outages and hides the time the judge had nothing; only written rules remove rows | "they are real data" without the outage consequence | "NaN is fine" |
| EXPLAIN_DETECTIVE | clock: log vs sheet, exactly 3600 s, local time UTC+1 (and/or the overlap with grid_survey); speed: ratio 3.6 of two independent measures (and/or > 30 m/s) → km/h; both with numbers | one correction justified with numbers | corrections stated with no evidence |
| EXPLAIN_ROBUST | a few huge errors (vision jumps, 160–265 m/s) dominate std because errors are squared; MAD-based σ = typical noise; report adds the tail (p95/max) and n; robust statistics did not protect against the km/h flight (systematic, a third of the GPS rows: 1.98 → 1.19 after correction) | two of the three ideas | "std is bigger because vision is worse" |
| report.md | five sections with numbers and units; cleaning counts and why NO_FIX stays; both corrections with evidence and "raw not edited"; outages incl. the unplanned one flagged; both robust σ compared with theory, each gap judged against its own scatter (day ±8 %: sampling; gps ±3 %: 2–3 spreads, flagged or explained), the tail explained; honest limits (synthetic, n, logged speed not truth, the small upward bias of speeds from positions) | numbers right but little explanation, or one section thin | lists of numbers copied from results.json |

Predictions (`PREDICT_…`) are never marked. In class, ask who expected the jammer to be broken in Step 6.

## Difficulties (round 1 reviews: strong, weak and expert simulated students; all mutants re-run after the fixes)

Each wrong version below was run against check.py and the runner's `test`; both now reject it, with these messages.

- `clean`: `dropna()` (✘ "the row with an EMPTY position was removed"), a "keep where in range" altitude rule that drops
  NaN altitudes (✘ "EMPTY altitude"), no `reset_index` (✘ index list shown), returning only the DataFrame ("return two
  things"), masks computed on `df` instead of on the remaining rows (✘ "null_island = 2"; the runner's 7-row test
  shows it too).
- `add_motion`: `shift()` without groupby (✘ "dt_s = 482"; runner shows dt −6.0), lat/lon shifted outside the
  groupby (✘ "step_m on the first row of a flight must be NaN"), dividing by a fixed 2 s (✘ "divides by a fixed 2 s").
- `outage_runs`: padding only the start (✘ "pad BOTH ends"), stops + 1 (✘ "one too far"), `valid == 0` on a plain
  list (AttributeError 'bool'… astype: lab Step 4 hint 5 and the 🧰 box start with `np.asarray`).
- `outage_table`: no `+ dt_s`, flights without outage skipped, `DT_S` instead of `dt_s`: each named.
- `state_shares`: fractions (✘ "multiply by 100"); numpy floats (✘ in the check AND in the runner's test now).
- `noise_by_source`: `np.std` (✘ "ddof 0"), MAD not scaled, error sign reversed, p95 of signed errors (✘ "take it on
  |err|").
- `unit_suspects`: means instead of medians, absolute tolerance, flights that look right included, `tol` ignored,
  ratios below 1 never flagged (✘ "a ratio far BELOW 1 is suspect too"), ratio inverted or knots factor 0.5144
  (✘ "flight t … compared with KN_PER_MPS"): each named (round 2).
- `noise_by_source` with `df.dropna()` on the whole log (✘ check 8 "a row with an empty battery_pct was dropped";
  the runner's test shows n 6 too); `outage_table` taking the times from the whole table instead of the flight
  (✘ check 6 "flight b …"; the runner's test has the same case) (round 2).
- report.md: a student who keeps the template's intro paragraph must pass check 14 (only the text after the first
  `## ` is searched for "(write here)"); a σ with one decimal gets "write it with two" (round 2).
- Answers: ROWS_RAW 1403, MOST_ROWS_FLIGHT "flight_id", clock +3600, factor 3.6, clock not fixed (UNPLANNED
  "sahel_hills"), report with the uncorrected or non-robust σ: each gets its own message.
- Weak student (round 1): about 6 h in all (lesson 95 min, sessions 2 h 30 and 2 h 45); give-up points were
  detective.py and TODO 3. Fixes: the Step 6 🧰 box now shows the two `clean`/`add_motion` lines, `display.width`
  and `to_string()`; hint 5 and the `schedule` output check each correction; Step 4 hint 5 covers the list trap.
- Strong student (round 1): 55 min + 2 h 10, wanted less copying: Step 5 and Step 7 numbers are no longer typed into
  answers.py (they go into the report), Step 1 is a pipeline challenge, Step 8 is unscaffolded.
- check 13 re-runs the runner: it needs the data mounted (as in the sandbox). Run outside the sandbox only with
  `LOGBOOK_DATA` set.

## Suggested class plan (reading at home, about 1 h 15 + 2 sessions of 2 h 15; about 5 h – 6 h in all)

0. **Before session 1:** read the lesson (about 75 min, up to 95 for weak readers) with the ✏️ checks.
1. **Session 1 — hook (10 min):** the cold open and VALIDATION_STATUS's sentence on the replay frames: "the computation
   was careful; why were the numbers withdrawn?" Collect answers.
2. **Board (10 min):** the rule-order question of §2 and the padded `np.diff` of §4 by hand.
3. **Lab (110 min):** Steps 0–4; Log keeper badge at the end-of-session box.
4. **Session 2 — retrieval (10 min):** Check-yourself 2–3 on paper.
5. **Lab (95 min):** Steps 5–9. When most are at Step 6, a 5-minute stop: "is the jammer broken?" — vote, then let
   them find the clock. Fast students take Step 8 (TODO 7) without hints.
6. **Debrief (30 min):** two EXPLAIN_ROBUST answers against the rubric; the 3.75-vs-4.25 gap and the 40-seed
   scatter; back to the replay frames: which check of the lab would have caught mislabelled pictures (none of the
   statistics; only an independent record, e.g. comparing pictures with the map).

**Differentiation.** Fast students: Step 8 without the hint box, then Going further. Students who struggle with pandas:
pairs; the §3 worked table on paper for TODO 2; TODO 3 as a loop; Step 8 with its hint box (or at home).
