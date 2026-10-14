# Mission 29 — teacher notes (Who to trust? The arbiter as a state machine)

Teacher only. Rebuilt 2026-10-14 on NAVERA Lite. Students write `navera_lite/arbiter.py` TODO 1–5 (`candidates`,
`track_since`, `pick`, `Arbiter.receive`, `Arbiter.step`; reference in `solutions/_navera_lite/navera_lite/arbiter.py`,
tags `# @part 29 todo 1–5`; `Decision`, `source_report`, `no_fix_reason` and the `Arbiter.__init__` are given) and
`experiment.py` TODO A (`holdoff_metrics`) and TODO B (`true_sigma`). Given new part: `ros/arbiter_node.py` (`@part 29`):
the student's `Arbiter` as the ROS node "arbiter" on arbiter v0's topics (it replaces v0 from now on; it stops with one
plain sentence when a TODO is missing). Mission files (hand-written): `judge_lab.py` (offline runner: test, play with
`--v0`, `--v0 --eligible`, `--open-door`, status), `play_scenario.py` (live player + race against
`/data/academy/29-arbiter/reference_run.json`, `--offline`), `experiment.py`, `answers.py`, `report.md`, `runner_kit.py`.

**What changed from the old mission 25/29.** The old lab raced NAVERA's real estimator node and asked code-reading
questions on its source: gone (students never see NAVERA code). The race is now against the course's reference run on
the same scenario, recorded by `make_dataset.py`. The arbiter-v0 thread of missions 09–12 ends here: the revival found in
mission 12 (`PREDICT_REVIVE`/`EXPLAIN_REVIVE`) is closed by the door (`receive`), and Step 5 shows two more effects of a
stored future fix (lockout by "old news", poisoned jump gate). **Never present the revival as a NAVERA fact**: the lesson quotes NAVERA's documented EST-2 ("a future timestamp kept
a dead source fresh", critical, fixed, review 2026-09-28) and NAVERA's documented rule (ARCHITECTURE §3, quoted: "a fix stamped in
the future does not set the order; it is refused by eligibility"; the course's door gets both effects by never storing it) — nothing about NAVERA's mechanism. The door also refuses a non-finite
stamp ("bad stamp", fix round 1: a NaN passes every `x > limit` test and would never age; note for mission 12's owner:
`estimate.eligible` could refuse a non-finite age too). Selection vs fusion: experiment.py's given `fuse()` calls mission 27's `navera_lite.uncertainty.fuse` (σ² I covariances).

Course decision in `pick()`: the winner is the first candidate (priority order) that is the current winner or has waited
the hold-off; a lost winner is replaced at once. So day vision that has waited replaces night even while a returning GPS
is still waiting (a stricter "only the best candidate may replace" rule is a common student variant: check 3 and the
`judge_lab.py test` line "night wins; day has waited…" catch it). NAVERA's documents state only "a higher-priority source
must stay usable for switch_holdoff_s (2 s) before it takes over"; do not claim more about NAVERA.

Numbers: `python3 solutions/29-arbiter/make_dataset.py` (writes `datasets/29-arbiter/`: race/revival/lockout/flapping
CSVs, `reference_run.json`, a neutral README; deterministic) and `make_hidden.py` (writes `courses/29-arbiter/hidden/
cases.json`: the check's unseen cases and the reference's answers). Run both from the academy root with ROS sourced.
`solutions/29-arbiter/my_run.json` is a real live race recorded in the sandbox; `results.json` is `experiment.py`'s output.

## Alignment

| Objective | Lesson | Lab | check.py |
|---|---|---|---|
| 1 a judge as a state machine; predict the next decision from the memory | §1 (🧰 state table, worked hold-off table, ✏️), figure judge.svg | Step 0 (v0 zig-zag), Step 4 hand trace, TODO 5 | 6, 7, 8 |
| 2 eligibility + priority; a door that never stores a refused fix | §2 (worked now = 500, 🧰 order, ✏️), §3 (revival figure, door rules, ✏️ four fixes, box after Step 5) | Steps 1, 3, 4 (revival plays), 5 (door left open) | 1, 4, 5, 9 |
| 3 hysteresis and its cost | §4 (rule, figure, 🧰 dict.get, worked e^(−h/μ), ✏️) | Step 2 (TODO 2–3, hand trace), Step 6 race (EXPLAIN_WAIT), Step 7 (TODO A, experiment A) | 2, 3, 11, 12, 14 |
| 4 winner → FIX / DEGRADED / NO_FIX with a reason | §5 (figure, table, ✏️) | Step 4 (TODO 5), Step 6 live | 6, 7, 10, 11 |
| 5 selection vs fusion with numbers | §6 (availability worked, ✏️), §7 (worked 3/30 m, ρ 0.8, spoof, ✏️) | Step 8 (TODO B, tables B and C), Step 9 report | 13, 14, 15 |

Badges: **Fair judge** = checks 1–9 (check 8 = Steps 0 and 4) (Session 1, offline), **Steady hand** = all 15.

## Answer key

| Item | Value | Where it comes from |
|---|---|---|
| Step 0 `V0_FLAP_SWITCHES` | **29** (v0 on flapping.csv) | `judge_lab.py play … --v0`; the check requires 29 |
| Step 4 `MINE_FLAP_SWITCHES` / `EXPLAIN_FLAP` | **7**; day vision 2.5–24.5 s: every GPS return before 22.5 s was broken by a "no fix" before 2 s (since forgotten); the run from 22.5 s is the first to last 2 s → GPS at 24.5 s (then lost at 25.0, back at 29.5) | the check requires 7 and keywords (hold-off; which run) |
| `PREDICT_FLAP` | ungraded; most students guess 5–15 | |
| TODO 1 docstring | `["day"]` | GPS 4.0 s old > 3 s |
| TODO 2 docstring | `{"gps": 100.0, "day": 90.0}` | night forgotten |
| TODO 3 docstring | `"day"` at 100.0, `"gps"` at 101.0 (exactly 2.0 s: `>=`) | |
| Step 2 hand trace | day (GPS 0.5 s, day 10 s ≥ 2 s); without night: GPS at once | lab box |
| TODO 4 docstring | `(False, "from the future (20.0 s ahead)")`, latest `{}`, refused `{"gps": …}` | |
| Step 4 hand trace | 100.0 FIX gps, switches `[(100.0, None, "gps")]`; 104.0 DEGRADED day "day: σ 30.0 m > 25.0 m" (GPS 4.5 s old); 108.0 NO_FIX "no usable source (gps: stale (8.5 s > 3.0 s); day: stale (6.0 s > 5.0 s))"; switches + `(104.0, "gps", "day")`, `(108.0, "day", None)` | `judge_lab.py test` |
| revival.csv (simulated clock) | v0 naive: FIX gps 1.0–33.2 s (the future fix is "fresh"); v0 + eligible (mission 12): DEGRADED day from 10.0 s, **FIX gps 29.6–33.2 s** (revival, position of t = 10 s: 390–460 m behind at 20 m/s), then day; student's judge: FIX gps until 12.2 s, then DEGRADED day; "⤫ refused at the door: from the future (20.0 s ahead)" at 10.0 s | `judge_lab.py play` |
| `play_scenario.py --offline` | 11 of 11, switches —→gps 1.0, gps→day 11.2, day→gps 16.0, gps→day 17.5, day→night 26.6, night→— 28.2 | reference_run.json |
| lockout.csv `--open-door` | 10.5 DEGRADED day (stored future fix: GPS "from the future"); honest fixes 11–30 s **old news** (20 of them); 31.0 and 32.0 refused as jumps (410 m > 100 m in 0.5 s, 430 m > 200 m in 1.5 s); **32.0 FIX gps** (the stored fix, eligible since 30.0, hold-off 2 s; its position is from t = 10.5 s: 430 m behind); 33.0 / 34.0 jumps; 33.6 DEGRADED day (the stored fix stale); 37.0 FIX gps (honest fix of 35.0 accepted, hold-off); student's judge: FIX gps all along, one refusal at 10.5 s | `judge_lab.py play` |
| `PREDICT_LOCKOUT` | ungraded; most students predict "nothing changes, the honest fixes win" | |
| `EXPLAIN_LOCKOUT` | stored future fix sets the order → honest fixes dropped as old news; when the clock reaches stamp − 0.5 s it becomes eligible, waits the hold-off, wins FIX with an old position; it also became the jump gate's trusted fix, so honest fixes are refused as jumps until 35 s | rubric below |
| Race live | 11 of 11, switches within ±0.35 s (sandbox 2026-10-14: 1.01, 11.10, 16.10, 17.51, 26.70, 28.10 s) | `play_scenario.py` |
| `EXPLAIN_WAIT` | the hold-off: GPS back at 14.0 s, eligible for 1.0 s only at 15.0 s; takes over at 16.0 s, DEGRADED (it states σ 40 m) | |
| Experiment A | hold-off 0 / 0.5 / 1 / 2 / 4 / 8 s → changes per minute **31.1** / 24.5 / 20.3 / **12.1** / 4.4 / 0.8; GPS share 0.624 / 0.498 / 0.394 / 0.243 / 0.099 / 0.034; eligible GPS unused **0.0** / 75.4 / 138.2 / **228.8** / 314.8 / 354.0 s of 600 s | `experiment.py` (seed 2901) |
| Experiment B (given) | window 2 / 3 / 4 / 5 / 6 / 8 s → usable 56.3 / 75.1 / 84.9 / 89.5 / 92.9 / 98.1 %; dropouts 131 / 82 / 32 / 24 / 18 / 10; largest staleness at 40 m/s 80 / 120 / 160 / 200 / 240 / 319 m | seed 2902 |
| Experiment C | GPS weight 0.9846; claimed σ **2.481 m**; real σ with ρ = 0.6 **2.658 m** (> 2.5 m GPS alone); spoof 1500 m → fused **1476.9 m** | TODO B |
| TODO B docstring | 2.985 (ρ 0), 3.213 (ρ 0.8) | lesson §7 |
| `PREDICT_HOLDOFF` | ungraded | |

Lesson numbers: §1 table 41.0/42.0/43.0 → switch at 43.0 (2.0 s ≥ 2 s); ✏️ 43.5 day at once, 44.0 since = 44.0,
GPS from 46.0. §2 worked: GPS 3.2 s stale, day 2.0 s, night no position, celestial 30 s ≤ 45 s → `["day", "celestial"]`;
✏️ `["gps", "day", "celestial"]` (day 0.3 s ahead is within 0.5 s). §3 ✏️ (a) stored, (b) future 1.0 s, (c) old news,
(d) gate 100 × 0.5 + 50 = 100 m < 800 m: jump; (e) bad stamp. §4 e^(−2/3) = 0.513; ✏️ 54.0 s; e^(−0.5) = 0.607. Figure holdoff.svg:
6 changes vs 2, unused 0.8 + 0.7 + 2.0 = 3.5 s. §6 uniform 1–4: 7/3 / 2.5 = 93.3 %, T = 2: 1.833 / 2.5 = 73.3 %,
120 m; ✏️ uniform 2–6, T = 5: 3.875 / 4 = 96.9 %, 75 m. §7 w₁ = 100/101 = 0.990, σ̂ = 2.985 m, ρ 0.8 → 3.213 m,
spoof 1980 m; ✏️ σ 4 / 12: w₁ 0.900, σ̂ 3.79 m, 450 m. NAVERA facts (words only): VALIDATION_STATUS 2026-10-03
(robustness table: flapping 0.5 s → one switch in 8 s; 60 s future refused; 0.8 s late fix at 75 m/s dropped as old
news; one measurement published once; "vision positions carried to the present": day window 3 → 5 s, FIX/NO_FIX
on 20–60 % of samples, landing in a 6.7–9.2 s gap, simulator only), ENGINEERING_BACKLOG review 2026-09-28 (EST-2,
EST-3), ARCHITECTURE §3 (rules, windows, hold-off, prior from the arbiter's output), ARDUPILOT_INTEGRATION (EKF3).

## Rubric for the written answers (the check only catches empty or off-topic answers — say so to students)

| Item | Good (2) | Partial (1) | Weak (0) |
|---|---|---|---|
| EXPLAIN_LOCKOUT (the check needs three keyword groups: old news / old position FIX / jump-gate) | the three effects: honest fixes dropped as old news because the stored future fix is "newer"; at ≈ 30 s it became eligible, waited the hold-off and won FIX with a 20 s old position (and/or the gate trusted it, so honest fixes were jumps) | one effect, or "the clock caught up" without what was stored | "the GPS was bad" |
| EXPLAIN_WAIT | hold-off: GPS eligible since 14.0 s, needs 2 s without a break, takes over at 16.0 s | "hold-off" without numbers | "GPS is worse" (σ does not choose the winner) |
| EXPLAIN_HOLDOFF | numbers from table A for both sides (31.1 → 12.1 changes/min; 228.8 s unused, share 0.62 → 0.24) and a judgement | one side only | no numbers |
| report §1–3 | own numbers, a choice argued with them, the cost named | numbers without argument | copied lesson text |
| report §4 | a hold-off and a window for the plane AND the boat with one reason each tied to speed × age or chattering; limits of synthetic data | one vehicle, or no reason | none |

## Difficulties expected (from the mutants run on the check and the hints)

- `candidates` walking the dict instead of `SOURCES` (wrong order) — check 1 and test line 2.
- `track_since` giving `now_s` to everybody (the hold-off never ends: the GPS never comes back in the unseen flight) or
  never forgetting (a break is not a break).
- `pick` with `>` (boundary), with "only the best may replace", or waiting the hold-off after a LOSS (the judge stays
  without a winner: NO_FIX instead of day vision).
- `receive` storing before testing (refused fixes kept: revival), the future test after the jump gate (gate poisoned:
  a fix stamped 12 s ahead and 600 m off becomes the trusted fix, and the honest GPS is refused as jumps — hidden
  scenario c and receive case 7), `abs(ahead)` (every vision fix older than 0.5 s refused as "from the future"),
  no "old news" test, the jump refusal not remembered in `refused`.
- `step` calling `pick` before `track_since`, STARTING whenever `latest` is empty (wrong after a refused fix), switches
  logged only towards a real source.
- Session 2: forgetting to restart the node between races (the player refuses: "your judge already says …"), a node
  left running before ✔ Check my work (check 10 fails with "N node(s) publish…").

Mutants (17, `~/academy-test/review/29-arbiter/build/mutants/`): every one fails at least one check with a message
naming the input; see the build report.

## Class plan

Honest duration (fix round 1, weak persona measured ≈ 7 h 20): 6 to 7 h 30 in all.

- **Session 1 (≈ 3 h).** 10 min Step 0 together (count the zig-zags on the projector) · 45 min lesson §1–§3 with the
  ✏️ in pairs · 20 min TODO 1 · 40 min TODO 2–3 (hand trace on the board first) · 30 min TODO 4 · 40 min TODO 5 and the
  offline plays · 20 min Step 5 (predict in pairs, run, discuss) · 5 min check.
- **Session 2 (≈ 2 h 30).** 15 min lesson §4–§7 recap · 30 min live node + race (pairs restart each other's judge) ·
  30 min Step 7 · 30 min Step 8 · 40 min report (designer role: half the class designs for the plane, half for the boat,
  then compare) · 5 min check.
- **Fast students:** Going further (model vs simulation, own scenario where the "first that has waited" rule matters, a
  per-source hold-off, flying their own mission-12 `estimate.py`). **Struggling students:** give the Step 2 and Step 4
  hand traces on paper first; let them use `judge_lab.py test` after each line they write; pair them for the ROS step.
