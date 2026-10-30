# Lab 14 — Pin the bugs, then hunt the mutants

**Goal:** run your stack's own suite, break the stack on purpose and restore it with git; write example
tests and properties of `geo.py` and `guard.py` strong enough to kill wrong versions of them; measure
your tests with mutants and find holes in the stack's own suite; then write a launch test of the
running judge.
**Time:** 3 h 30 to 5 h in two sessions (a fast student: about 3 h), after 80 to 110 minutes of reading.

Your files (📝 Code tab): [test_geo_examples.py](file:./test_geo_examples.py) (**TODO 1–4, 6b**),
[test_geo_properties.py](file:./test_geo_properties.py) (**TODO 5**), [my_mutants.py](file:./my_mutants.py)
(**TODO 6**), [test_arbiter_launch.py](file:./test_arbiter_launch.py) (**TODO 7**),
[answers.py](file:./answers.py), [report.md](file:./report.md). [hunt.py](file:./hunt.py) runs your tests
against mutants. The stack in `navera_lite/` is finished: you test it, you do not change it (except on
purpose, in Steps 1 and 6, and you restore it).

| Lesson | Lab | You write |
|---|---|---|
| §1 Levels | Steps 0–1 | nothing: run, break, restore |
| §2 Examples | Step 2 | TODO 1–4 in `test_geo_examples.py` |
| §3 Properties | Step 3 | TODO 5 in `test_geo_properties.py` |
| §4 Mutants | Steps 4–5 | TODO 6 in `my_mutants.py`, TODO 6b |
| §5 Launch tests | Step 6 | TODO 7 in `test_arbiter_launch.py` |

> [!WARNING] One terminal tab, and no judge left running
> Run every command in the same terminal tab. This mission starts no node by hand: the launch test of
> Step 6 starts its own judge. If `jobs` lists a node from an earlier mission, stop it first:
> `kill -INT $(jobs -p)`.

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` is written **before** you run the step. It is never marked
> right or wrong.

## Session 1 — Pin the bugs (about 2 h)

## Step 0 — The stack's own suite (no code)

NAVERA Lite ships with its tests in [navera_lite/tests/](file:./navera_lite/tests/test_geo.py).

> [!TASK]
> **Predict** (`PREDICT_SUITE`): how many tests does the suite hold, and how long will they take?

```bash
python3 -m pytest -q navera_lite/tests
```

One dot per passed test. Now ask pytest for the three slowest:

```bash
python3 -m pytest -q navera_lite/tests --durations=3
```

> [!TASK]
> `N_TESTS` (the number before `passed`) and `SLOWEST_TEST` (the name of the slowest one, as printed).

## Step 1 — Break it, then restore it with git

Your lesson folder is not a git repository yet. One script makes it one, with a first commit tagged
`start` (it sets a local name for git if you have none):

```bash
bash navera_lite/tools/init_repo.sh
```

```bash
git log --oneline
```

Now be the colleague of lesson §1. Open [navera_lite/geo.py](file:./navera_lite/geo.py), find
`is_finite_latlon`, and replace its last line `return in_range and not null_island` by:

```python
    return in_range
```

Save. Your stack now accepts Null Island.

> [!TASK]
> **Predict** (`PREDICT_FAILS`): how many of the suite's tests will fail?

```bash
python3 -m pytest -q navera_lite/tests
```

Read the report the way lesson §2 does: which test, which line, which values. Then look for everything
in the stack that **uses** the function you broke (`-rn`: every file, with line numbers):

```bash
grep -rn "is_finite_latlon(" navera_lite --include=*.py
```

See your change as git sees it, throw it away, and check:

```bash
git diff
```

```bash
git restore navera_lite/geo.py
```

```bash
git status
```

`nothing to commit, working tree clean`. Run the suite once more: everything passes again.

```bash
python3 -m pytest -q navera_lite/tests
```

> [!TASK]
> `N_FAILED`, and `EXPLAIN_ONE_TEST`: why so few? Which other parts use `is_finite_latlon` (the grep), and
> did their tests notice?

## Step 2 — Example tests (TODO 1–4)

Open [test_geo_examples.py](file:./test_geo_examples.py). Read its three rules at the top: ✔ Check my
work enforces them. Two tests are already written (lesson §2). Run them, verbosely:

```bash
python3 -m pytest -v test_geo_examples.py
```

Five lines `PASSED`: the parametrized test counts four times.

<details><summary>🧰 Three pytest options you will use all the time (open if needed)</summary>

```
python3 -m pytest -v file.py             one line per test (and per case)
python3 -m pytest -v file.py -k gate     only the tests whose name contains "gate"
python3 -m pytest -x file.py             stop at the first failure
```
A test fails on correct code? It is a **wrong test**: check the expected value (metres or degrees?), the
order of the arguments, and the tolerance.
</details>

**TODO 1 — `haversine_m`, at least 3 tests.** Adapt lesson §2's worked example: one degree along a
meridian, one along a parallel far from the equator, one more of your choice (a long one: a quarter of
the equator, or the docstring's London → Paris). Each tolerance gets a comment that says why.

<details><summary>Stuck? Hints, one at a time</summary>

1. Expected values come from `M_PER_DEG` (top of the file), never from `haversine_m` itself (rule 2).
2. Along a meridian the arc is a great circle: a tight `rel` works. Along the 60° parallel the great
   circle is 0.5 m shorter than `M_PER_DEG × cos 60°`: lesson §2 says which `rel` to choose.
3. Your test fails with `assert 55596.934… == 55597.463… ± 0.0555975`? Your tolerance is `rel=1e-6`:
   correct code fails it.
4. Obtained about 111 or 55.6? Your expected value is in metres and the result in kilometres, or the
   reverse: `haversine_m` returns metres.
5. Expected value negative, or strange like −105 903? `math.cos` takes **radians**:
   `math.cos(math.radians(60))` is 0.5, `math.cos(60)` is −0.95.
6. Testing the docstring's London → Paris? It says *about* 343 556.1: rounded to 0.1 m, so the tolerance
   must be at least `abs=0.05`.
</details>

**TODO 2 — `is_finite_latlon`, one parametrized test, at least 8 cases.** First, on paper: list the
rules of its docstring. For each rule, one case that breaks **that rule alone**; then the limits
themselves; then a normal position; then things that are not numbers at all.

<details><summary>🧰 <code>math.nan</code>, <code>math.inf</code> and a parametrize list (open if needed)</summary>

```python
import math
math.nan, math.inf, -math.inf        # "not a number" and infinity, as floats
math.nan == math.nan                 # False! NaN equals nothing, not even itself

@pytest.mark.parametrize("word, n", [("a", 1), ("abc", 3)])      # names in ONE string, then the cases
def test_length(word, n):                                         # the same names, as arguments
    assert len(word) == n
```
</details>

<details><summary>Stuck? Hints, one at a time</summary>

1. The docstring has four rules: two finite numbers; latitude in [−90, 90]; longitude in [−180, 180];
   not exactly (0, 0).
2. "The limits themselves" means latitude 90 and −90, longitude 180 and −180: valid. Just outside each
   one: invalid.
3. `In test_…: function uses no argument 'ok'`: the names in the first string and the arguments of the
   function must be the same.
4. Compare with `is ok`, not `== ok`: a function returning `0` would pass `== False`.
5. "Not numbers at all": `None`, or a text such as `"35.8"`. The docstring says the result is False.
</details>

**TODO 3 — `offset`, `enu_flat` and `great_circle_points`, at least 4 tests.** Read the docstrings again
(mission 06). Place a point by hand (for example 0.01° north and 0.02° east of a start), and compute its
metres yourself. For `great_circle_points`, its docstring says when it raises a `ValueError`: pin it with
`pytest.raises` (lesson §2).

<details><summary>Stuck? Hints, one at a time</summary>

1. North: `M_PER_DEG` metres north is exactly 1° of latitude, and the longitude must not move.
2. East at 60°: the parallel is half as long, so `M_PER_DEG` metres east is 2° of longitude.
3. `enu_flat` uses the **mean** latitude of the two points for the east scale (its docstring):
   `cos(radians(mean latitude))`.
4. The ±180° meridian: offset's docstring has an example (5 km east of 179.99°). What range must the
   longitude stay in?
5. `with pytest.raises(ValueError):` then, indented under it, the one call that must raise. Two points are
   opposite when their latitudes have opposite signs and their longitudes differ by 180°.
</details>

**TODO 4 — the jump gate, at least 3 tests.** The least help: the docstrings of `gate_ok` and `JumpGate`
in [navera_lite/guard.py](file:./navera_lite/guard.py) are your specification, and mission 01's lesson
table is a regression test waiting to be written. Before you code, trace by hand: with 100 m/s and 50 m,
which distances are accepted after 0 s, 1 s and 2 s? What does "a refused fix changes nothing" mean
for the NEXT fix? And does every one of your jumps move only east?

<details><summary>Stuck? Hints, one at a time</summary>

1. `gate_ok((0.0, 0.0), (d, 0.0), elapsed_s, 100.0, 50.0)`: choose `d` exactly on the limit, and just
   above it (lesson §4's check).
2. The docstring says what a negative elapsed time means. Choose a distance that ONLY that rule accepts:
   if −1 s counts as 0 s, the gate is the margin, 50 m; if it does not, the gate is −50 m. Which distance
   tells the two apart? (60 m is refused either way and pins nothing.)
3. With the `gate` fixture and the `gps(e_m, t_s)` helper: a first fix, then a jump that must be refused,
   then a fix that would be accepted from the jump but not from the first fix.
4. `gate.check(…)` returns a tuple `(ok, reason)`: compare `[0]` with `is True` / `is False`.
</details>

Run your file, then let `hunt.py` check the rules and that every test passes on the stack as given:

```bash
python3 -m pytest -v test_geo_examples.py
```

```bash
python3 hunt.py test
```

> [!TASK]
> **Predict** (`PREDICT_TRAINING`): `hunt.py` will try 7 wrong versions of `geo.py` and `guard.py`
> (it prints each change). How many will your tests kill?

```bash
python3 hunt.py
```

Read every survivor: which input would show the difference? Add tests to TODO 1–4 until only one
survivor is left, then go on (Step 4 comes back to the last one).

<details><summary>Stuck? Hints for survivors</summary>

1. Mutant 5 survives? Which pair of longitudes is 0.1° apart on the globe but 359.9° apart as numbers?
   Write an `enu_flat` test for that pair.
2. Mutant 6 survives? At which single value of `elapsed_s` are `v_max × elapsed_s` and `v_max` equal?
   Every one of your gate tests probably uses it.
3. Mutant 2 survives? Which of the docstring's rules has no "just outside" case in your list?
4. Mutant 7 survives? Hint 2 of TODO 4.
</details>

## Step 3 — Properties (TODO 5)

Open [test_geo_properties.py](file:./test_geo_properties.py) and run the property already written:

```bash
python3 -m pytest -v test_geo_properties.py
```

```bash
python3 -m pytest -q test_geo_properties.py --hypothesis-show-statistics
```

The statistics say how many examples ran, and how fast. Now **TODO 5**: write a) symmetry and
b) the triangle inequality, run them; then c) the round trip and d) validity, **both on the whole Earth**
(`LAT`, `LON`), d) with `@settings(deadline=None, max_examples=2000)`. Use `assume` for the valid start.

> [!TASK]
> **Predict** (`PREDICT_COUNTEREXAMPLE`): will hypothesis find a start and a move of at most 50 km whose
> result is not a valid position? Where on the Earth?

```bash
python3 -m pytest -q test_geo_properties.py
```

Read the `Falsifying example` of d) (scroll up to it). If d) passes, run it again (up to three times): a
50 km move can only fail within 0.45° of a pole, a band that holds 0.5 % of the latitudes hypothesis draws —
lesson §3's point about rare edges. Once found, an example is stored in `.hypothesis/` and tried first.
c) may fail on the whole Earth too, more rarely.

> [!TASK]
> `COUNTEREXAMPLE`: its four numbers as `(lat0, lon0, e_m, n_m)`, and `EXPLAIN_COUNTEREXAMPLE`: what
> happens physically, and is it a bug of `offset` or a limit of its domain? Then open lesson §3's box
> "Read this after lab Step 3".

Now make the domain explicit: a new strategy for the start latitude (for example `LAT_80`, from −80 to
80) used by c) and d). Every property must pass:

```bash
python3 -m pytest -q test_geo_properties.py
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Symmetry: two calls of `haversine_m` with the points swapped, compared with `pytest.approx(…, abs=1e-6)`.
2. Triangle inequality: six numbers drawn (three points); allow `+ 1e-6` for rounding.
3. Round trip: `enu_flat(lat0, lon0, *offset(lat0, lon0, e, n))` against `(e, n)`; `pytest.approx` accepts
   a tuple.
4. `assume(is_finite_latlon(lat0, lon0))` throws away the starts that are not valid, such as (0, 0).
5. `DeadlineExceeded`? A property without `@settings(deadline=None)`.
6. `Unsatisfiable` or `FailedHealthCheck: … filter`? An `assume` throws away almost every example: draw
   from a domain where it is rarely false instead.
7. The check reads the strategy of your start latitude in c) and d): `st.floats(-80.0, 80.0)`, a
   `.filter(…)`, or an `assume(abs(lat0) <= 80)` all work; the whole-Earth `LAT` does not, even when a run
   is lucky.
</details>

Commit your tests, as in mission 05 (one concern per commit):

```bash
git add test_geo_examples.py test_geo_properties.py
```

```bash
git commit -m "test(geo): examples and properties of geo and guard"
```

> [!TIP] 🏅 End of session 1 — Bug pinner
> Press **✔ Check my work**. It runs your two files against **20 mutants you have not seen**, each
> function family on its own, and tells you, for each survivor, what kind of test would kill it. When
> the checks of Steps 0–1, TODO 1–5 and Step 3 pass, you earn the **Bug pinner** badge (the other ✘
> lines are session 2).

## Session 2 — Hunt and launch (about 2 h)

## Step 4 — The mutation score

```bash
python3 hunt.py
```

One training mutant survives whatever you add. Try anyway: write one more test aimed at it and run
`hunt.py` again. Then prove that no test can kill it: for which inputs could the two versions differ, and
what does the rest of the function do with those inputs?

> [!TASK]
> `EQUIVALENT_MUTANT` (its number) and `EXPLAIN_EQUIVALENT`.

<details><summary>Stuck? Hints, one at a time</summary>

1. Look at the survivor's change: it removes `math.isfinite(lo)`. Which longitudes could now get further
   than before? Only NaN, +infinity and −infinity.
2. Follow one of them through the next line, `in_range = finite and abs(la) <= 90.0 and abs(lo) <= 180.0`.
   What is `abs(math.inf) <= 180.0`? And `math.nan <= 180.0` (lesson §4's 🧰 box)? Try both in `python3`.
3. If `in_range` is False for every such input in both versions, the result is the same for every input:
   no test can tell them apart.
</details>

## Step 5 — The saboteur (TODO 6)

Now attack the **stack's own suite**. Read [navera_lite/tests/test_geo.py](file:./navera_lite/tests/test_geo.py)
and [test_guard.py](file:./navera_lite/tests/test_guard.py) beside [geo.py](file:./navera_lite/geo.py)
and [guard.py](file:./navera_lite/guard.py): which rule of a docstring does no test check? That is where
a mutant survives.

**TODO 6**: in [my_mutants.py](file:./my_mutants.py), write three mutants, each a tuple
`(file, old, new)`, that make the stack wrong but that the suite does not notice. Its docstring has an
example that does **not** count. Three rules: each one changes a different line, none of them repeats a
training mutant of `hunt.py`, and each one gives a WRONG RESULT for some input. A different error message,
a comment, or a float that becomes a numpy float does not count: `hunt.py` and the check compare what the
stack returns before and after your change on several hundred inputs. Try them:

```bash
python3 hunt.py mine
```

Each mutant needs two ✔: "the stack's own suite misses it", then "your tests kill it". For the second,
**TODO 6b**: add tests at the end of `test_geo_examples.py` until `hunt.py mine` says 3 good mutants. If
your TODO 1–4 tests already kill all three, good: say in report.md which of your tests kills each one.

<details><summary>Stuck? Hints, one at a time</summary>

1. `test_geo.py` checks `is_finite_latlon` with five positions. Which of the docstring's limits does it
   never touch?
2. `test_enu_flat_and_offset_are_inverse` starts at 60° and −22°, far from the ±180° meridian. What does
   `offset` do there that no test sees?
3. `great_circle_points` raises a `ValueError` in two cases (its docstring). Does the suite test both?
4. "the old text appears 0 times": copy it from the file with the editor (spaces count), or take a
   shorter, unique piece.
5. "changes no code": a mutant in a docstring or a comment is not a mutant.
</details>

Commit: `git add my_mutants.py test_geo_examples.py`, then `git commit -m "test(geo): kill my three mutants"`.

## Step 6 — A launch test of the judge (TODO 7)

Open [test_arbiter_launch.py](file:./test_arbiter_launch.py) beside lesson §5. Its test_0 is written:
it waits until the judge publishes and listens. Make sure no judge of yours runs (`jobs` must print
nothing), then run the file as it is:

```bash
jobs
```

```bash
launch_test test_arbiter_launch.py
```

About 5 to 10 seconds: the judge's log lines (`[arbiter-1] …`) appear between the test results. test_0
passes; test_1 and test_2 **fail** with `AssertionError: TODO 7a` / `TODO 7b`; at the end
`FAILED (failures=2)`, and then the shutdown test: `OK`.

**TODO 7a** and **TODO 7b**: their docstrings say what "done" means. Use the helpers of the class
(`send_gps`, `spin_for`, `drain`, `last_status`) and the 🧰 unittest box of lesson §5.

```bash
launch_test test_arbiter_launch.py
```

<details><summary>Stuck? Hints, one at a time</summary>

1. 7a in four moves: start from a clean list (`self.drain()`), send a good fix, wait about 1 s, send a
   fix 5000 m east, wait about 1 s, then assert.
2. `last_status()` returns `(values, message)`. The GPS source's own line is `values["src.gps"]`;
   print it once to see its words (`print(values)`, the output shows in the test log). The number in it
   is the gate for the REAL time between your two fixes (`jump 5000 m > 153 m in 1.0 s` after 1.03 s):
   assert that `"jump"` is in it, not the exact text.
3. "Exactly one position": `len(self.positions)`, and that one has the good fix's longitude:
   `self.positions[0].longitude` (a NavSatFix has `.latitude` and `.longitude`), compared with
   `assertAlmostEqual(…, places=7)`.
4. 7b: `send_gps(lat=math.nan, lon=math.nan)`. The reason's words are in
   [arbiter_v0.py](file:./navera_lite/ros/arbiter_v0.py), in `usable()`.
5. `values["src.gps"]` says `nothing received`? You read the status before the fix arrived: wait
   (`spin_for`) after each `send_gps`.
6. test_2 says `Lists differ: [sensor_msgs.msg.NavSatFix(…)] != []` (or `1 != 0` if you count with `len`)? The list still holds test_1's
   position: one judge, one tester node, one list for all tests. Start each test with `self.drain()`.
</details>

**Break the judge on purpose.** NAVERA's EST-1 was a judge that re-published the same measurement five
times per second. Make arbiter v0 do it: in
[navera_lite/ros/arbiter_v0.py](file:./navera_lite/ros/arbiter_v0.py), method `step`, replace
`if key != self.last_sent:` by `if True:` and save.

> [!TASK]
> **Predict** (`PREDICT_REPUBLISH`): which of your tests will fail, and how many positions will it count
> instead of 1? (The judge ticks at 5 Hz; read your test to see how long it listens.)

```bash
launch_test test_arbiter_launch.py
```

```bash
git restore navera_lite/ros/arbiter_v0.py
```

```bash
git status
```

> [!TASK]
> `REPUBLISH_FAILED`: the name of the test that failed, and `REPUBLISH_COUNT`: how many positions it
> counted (the number before `!= 1`). `git status` must show no change in `navera_lite/` (the check
> compares it with the given stack). If test_1 did not fail, your TODO 7a does not count the positions
> yet. test_2 does not fail: it drains the list after the NaN fix has arrived, and then the judge, in
> NO_FIX, has nothing to re-publish. The check runs your tests on this broken judge too.

## Step 7 — Report, check, look back

Fill [report.md](file:./report.md) (three headings, at least 40 words each, with your numbers), then
press **✔ Check my work**. It runs your files against mutants you have not seen, runs the stack's suite
against your own mutants, and runs your launch test five times: on the real judge and on four broken
ones (about two minutes). Every check passed: **Mutant hunter** badge.

Look back (not graded):

1. Which of your tests would have caught NAVERA's LOC-4 (a (0, 0) position used as an anchor) before it
   flew, and which level of test would have caught EST-1?
2. Your first `hunt.py` score: which kind of test were you missing — limits, directions, or a rule you
   did not read?
3. The property that found the pole: would you have written that example by hand?
4. Your launch test waits 1 s twice. On a loaded machine, what could make it flaky, and how would you
   make it wait for a condition instead of a time?

## Going further (optional)

- **Equivalent or not?** Lesson §4's `np.minimum(1.0, a)` mutant: how large must `a` be for
  `np.arcsin(np.sqrt(a))` to give NaN? Search for such points (numpy, a few million near-opposite pairs),
  or argue why none exist. Then add the mutant to `TRAINING` in a copy of `hunt.py`: what does your
  score do?
- **Test the trip computer.** Mission 11's `TripComputer` (in `navera_lite/ros/trip_node.py`): write
  properties — the distance never decreases; a refused fix changes nothing; a vehicle that does not move
  has speed 0.
- **Wait for a condition.** Rewrite `spin_for` into `spin_until(predicate, timeout_s)` and use it in
  test_1 and test_2. How much faster is the launch test?
- **A mutation tool.** Write a 40-line script that generates mutants automatically: every `<=` becomes `<`,
  every `+` becomes `-`, one at a time, in `guard.py`. How many does the suite kill?
