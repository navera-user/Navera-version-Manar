# Mission 14 — teacher notes

Not visible to students. Alignment, answer key, rubrics, known difficulties, class plan.

Two sessions: **Session 1 — Pin the bugs** (Steps 0–3, TODO 1–5, badge **Bug pinner** = milestone `bug_pinner`,
checks 1–8) and **Session 2 — Hunt and launch** (Steps 4–7, TODO 6–7, badge **Mutant hunter** when every check
passes). Rebuilt 2026-10-13 on NAVERA Lite: no NAVERA code, files or launch. The stack is finished in this
mission (manifest `solutions/_navera_lite/manifest.d/14-testing.json`: every part of 09–13 + the reference suite,
89 tests, + `navera_lite/tools/init_repo.sh`, new here and reused by 33). The students write test files only.
Hook: Ariane 501 (Inquiry Board report, J.-L. Lions, July 1996), in words. NAVERA facts, in words, from
ENGINEERING_BACKLOG.md (review of 28 September 2026: LOC-4, EST-1 and the "done = fixed, tested and committed"
rule; review of 1 October 2026: R-5) and VALIDATION_STATUS.md (last updated 2026-10-03: the robustness table).

## Objectives → practice → assessment

| Objective | Lesson (✏️ Check) | Lab | check.py test |
|---|---|---|---|
| 1. Example tests: tolerances, `is`, `raises`, parametrize, fixtures, limits | §2 (60° tolerance worked example; ✏️ 45°/75°, `valid_heading`) | Step 2, TODO 1–4 (+ `hunt.py`) | 2, 3, 4, 5, 6 |
| 2. Property tests, counterexamples, bug or domain | §3 (`pack_speed` = Ariane in miniature; ✏️ tests after the fix; read-after box) | Step 3, TODO 5 | 7, 8 |
| 3. Mutants, mutation score, equivalent mutants | §4 (cos² table, `np.minimum` "almost equivalent", ✏️ gate `<`) | Steps 2, 4, 5 (TODO 6, 6b) | 3–7, 9, 10 |
| 4. Run the suite, break/restore with git, launch test of a node | §1 (✏️ unit vs smoke), §5 (✏️ flaky) | Steps 0–1, 6 (TODO 7) | 1, 11, 12, 13 |
| (all) written analysis | — | Step 7 | 14 |

## Answer key (measured in the sandbox, `try_lesson --who build14`, 2026-10-13)

- **Step 0:** `PREDICT_SUITE` first (the lesson gives no count). `89 passed in 11.1–11.3 s`. `--durations=3`: `10.35s call navera_lite/tests/test_ros_smoke.py::
  test_arbiter_v0_judges_the_replayed_demo`, then 0.05 s (test_convert) and 0.01 s. `N_TESTS = 89`,
  `SLOWEST_TEST` contains `test_ros_smoke` (the check accepts any text with "smoke").
- **Step 1:** `init_repo.sh` → "git repository created …, 51 files committed, tagged 'start'" (the count
  includes the student's starter files). With `return in_range`: **1 failed, 88 passed** —
  `test_geo.py::test_null_island_and_bad_values_are_refused`, line 16, `assert not True`. `N_FAILED = 1`.
  The grep lists `estimate.py:170` (eligible, which has its own "null island" rule first), `ros/trip_node.py:60`,
  `ros/arbiter_v0.py:79` (jump gate only for valid GPS) and `:97` (`usable`). Arbiter v0 would now take (0, 0) as a
  usable GPS fix and say FIX; no test of the judge or of the trip node sends (0, 0). That is NAVERA's LOC-4 in
  miniature. `git restore` → clean, 89 passed again.
- **Step 2:** the starter's 5 given tests pass (4 parametrized bearing cases + 1). The reference solution has 40
  example tests (41 with the given property in `hunt.py test`). Training mutants (`hunt.py`): reference **5 of
  6 killed**, survivor 3 (equivalent). A typical first attempt (no limits, no non-numbers, gate only at 1 s,
  build/wrong/w1) kills **2 of 6** (1 and 4): mutant 2 survives a test at 200° (outside 190°), 5 needs a date-line
  `enu_flat` test, 6 needs an elapsed time ≠ 1 s.
- **Step 3:** whole Earth, `max_examples=2000`: `Falsifying example: … lat0=89.55257463757103, lon0=0.0, e=0.0,
  n=49751.430354205564` → `offset` gives (90.00000000000001, 0.0). Found with 4 of 5 seeds tried while building;
  the other run passed (the lab says: run again). The round trip c) on the whole Earth fails more rarely (seen with
  2000 examples: lat0 ≈ 89.7–89.86). Restricting the start to ±80° (or ±89°) makes all pass; the check refuses an
  offset property still drawn from ±90° unless an `assume` restricts it. `COUNTEREXAMPLE` is graded by recomputing
  `offset` (valid start, |e|, |n| ≤ 50 km, invalid result): any true counterexample passes, e.g. the shrunk one.
- **Step 4:** `EQUIVALENT_MUTANT = 3` (`finite = math.isfinite(la)`): a NaN or infinite longitude is still refused by
  `abs(lo) <= 180.0` (any comparison with NaN is False, ∞ > 180), the null-island test is unchanged, so every input
  gives the same result.
- **Step 5 (TODO 6):** survivors of the suite that are easy to find: `abs(lo) <= 180.0 → 360.0` (or 181.0; the suite
  never tests a longitude beyond 180), `lon2 = (lon2 + 180.0) % 360.0 - 180.0 → lon2 = lon2` (the round-trip test of
  the suite starts far from ±180°), `if math.pi - d < 1e-9: → < 0.0` (opposite points never tested), `abs(la) <= 90.0 →
  < 90.0` (the poles), `np.minimum(1.0, a) → a` (killed only by the lesson's near-antipodal numbers). The docstring
  example (`abs(la) <= 95.0`) is killed by `test_estimate.py` and `test_geo.py`. The reference uses the first three.
- **Step 6 (TODO 7):** the starter launch test: test_0 ok, test_1/test_2 `AssertionError: TODO 7a/7b`,
  `FAILED (failures=2)`, shutdown test OK (≈ 3 s after the judge starts; ≈ 8 s in all). Solution: `Ran 3 tests in
  3.9 s OK`, judge log `gps fix refused: jump 5000 m > 152 m in 1.0 s` (elapsed 1.02 s), `NO_FIX: no usable source
  (gps: bad position)`; post-shutdown OK; exit code 0. With `if True:` (re-publishing judge): test_1 fails
  `12 != 1 : one measurement, one position`; **test_2 failed too** in the measured run (a re-published position
  still in flight after `positions.clear()`), so `REPUBLISH_FAILED` must name test_1 and may name test_2.
- **Lesson numbers:** 1° of longitude at 60°: parallel 55 597.46 m, great circle 55 596.93 m (9.5 × 10⁻⁶); at 45°:
  78 626.69 / 78 626.19 (6.3 × 10⁻⁶); at 75°: 28 779.36 / 28 779.02 (1.18 × 10⁻⁵). cos² mutant: London → Paris
  341 098.8 m, Paris → London 346 134.6 m, truth 343 556.1 m; the meridian, equator and 60° parallel examples give
  identical values. `np.minimum` removed: (−44.0875753669041, −1.6433686469012514) and its antipode give a =
  1.0000000000000002 → NaN (found by a 200 000-point random search). `pack_speed` property: shrunk to
  v = 327.67500000000007 with every seed (round → 32 768); the examples 0, 12.34, 30, 100 pass. Midpoint property of
  `great_circle_points`: 100 examples × seeds 1–3 never drew opposite points. Check yourself 2: 8/11 ≈ 73 %.

## Rubric for the written answers (the check only catches empty or off-topic answers)

| Item | 2 — good | 1 — partial | 0 — not yet |
|---|---|---|---|
| EXPLAIN_ONE_TEST | one test checks (0, 0); the judge (arbiter_v0) and the trip node use the function but their tests never send (0, 0); eligible has its own rule; v0 would now say FIX on Null Island | "only one test" without the users | "the suite is fine" |
| EXPLAIN_COUNTEREXAMPLE | a start near the pole + a move north crosses 90°; offset adds degrees (flat-Earth shortcut), so it is a domain limit: restrict / document (or implement pole crossing) | the pole, without bug-vs-domain | "hypothesis is wrong" |
| EXPLAIN_EQUIVALENT | the range test refuses NaN/∞ anyway (NaN comparisons are False, ∞ > 180), so no input differs; equivalent mutants leave the score | "no test kills it" without why | a wrong mutant number |
| report.md | own numbers; names which test pins which bug; says why the suite missed each own mutant; says what the launch test checks that unit tests cannot (wiring, QoS, publish-once, exit) | numbers without reasons | template text |

## Difficulties expected (from the wrong solutions and the sandbox runs)

- `rel=1e-6` at 60° (build/wrong/w2): the check prints pytest's `assert 55596.934… == 55597.463… ± 0.0555975`
  and calls it a wrong test. Lab hint 3 quotes the same line.
- Cases just outside a limit but not ON it (90.0, 180.0 never tested; 200° instead of 185°): the check names the
  surviving mutant ("refuses the poles", "longitudes up to ±360°") and the kind of test that kills it.
- No non-number case (None / a text): the "type check removed" mutant survives (a text becomes a number).
- Gate tests all at `elapsed = 1.0` and away from the limit: "exactly at the limit", "negative elapsed", "a refused
  fix becomes trusted" survive. Mission 01's lesson table is the regression test they need.
- Leaving the validity property on the whole Earth: a lucky run passes; the check's static rule refuses it with a
  message naming the test (the check's derandomized run did not find the pole with 2000 examples).
- Swapping e and n in COUNTEREXAMPLE: "gives a valid position: this is not a counterexample…".
- my_mutants: copying the docstring example (killed by the suite), a docstring-only change (refused: "changes no
  code"), a mutant their own tests miss (`abs(lo) <= 181.0` vs a test at 200°).
- Launch test without the position count: the re-publishing judge survives (check 12 names EST-1). Without
  `positions.clear()` at the start of test_2/test_1: lists from earlier tests leak in.
- Reading the reason words: students search the status message; the lab's hint points at `usable()` in arbiter_v0.py.
- A test file that reads the stack's source (`open(geo.__file__)`) would "kill" every mutant: the check refuses
  `open(`, `__file__`, `inspect`, `importlib`, … in the two test files (rule 3, build/wrong/w3). hunt.py does the same.
- `.hypothesis/` makes a found counterexample come back first: students who ran d) twice see it at once.

## Class plan (2 × 2 h)

- Session 1: 15 min hook (Ariane, then LOC-4 / EST-1), Steps 0–1 together on the projector (predict the number of
  failures first; most say "many"), 15 min §2 tolerances on the board, then Step 2 (TODO 1–4) with `hunt.py` as a
  scoreboard; Step 3 in the last 30 min. Badge **Bug pinner**.
- Session 2: 10 min §4 (cos² table), Step 4; **saboteur rounds** in pairs: each student gives the neighbour one
  mutant of `my_mutants.py` (a tuple on paper), the neighbour must kill it with one test in 5 minutes; then
  Step 5 alone; 15 min §5, then Step 6. Report at home.
- Fast students: Going further (spin_until, automatic mutant generator, TripComputer properties). Struggling
  students: give the docstring rule list of `is_finite_latlon` and `gate_ok` printed, and let them write one case
  per rule; pair them for the launch test (one writes 7a, the other 7b).

## Files

- `courses/14-testing/files/`: generated `navera_lite/` (incl. `tests/`, 89 tests, and `tools/init_repo.sh`) and
  `navera_lite.yaml`; hand-written `test_geo_examples.py`, `test_geo_properties.py`, `test_arbiter_launch.py`,
  `my_mutants.py`, `hunt.py` (training mutants, `test` / `mine` modes; it reads the given files from the git tag
  `start`), `pytest.ini` (hides launch_testing's private-API warning), `answers.py`, `report.md`.
- `solutions/14-testing/`: the four student files, answers, report, `_apply.sh` (runs init_repo.sh, as Step 1 does).
  No dataset.
- `check.py`: 21 hidden mutants (18 of geo.py/guard.py in 5 families, 3 of arbiter_v0.py) as string replacements of
  the GIVEN starter files (read from `/academy/courses/14-testing/files`); every run copies the given stack into a
  temporary folder, so a student's own edits never matter; hypothesis runs derandomized without shrinking (same
  profile as hunt.py). **If geo.py, guard.py or arbiter_v0.py change in the reference, re-run the check on the
  solution: a mutant whose old text no longer appears once stops the check with "checker problem".** Whole check on
  the solution ≈ 80 s (check_timeout_s 420); the starter ≈ 40 s.
