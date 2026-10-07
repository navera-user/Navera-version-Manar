# Lab 14 — Tests that catch bugs

**Goal:** run NAVERA's test suite, break NAVERA on purpose and repair it with git; write example
tests ([test_geo_tools.py](file:./test_geo_tools.py)) and property tests
([test_properties.py](file:./test_properties.py)) strong enough to kill the checker's mutants; test
NAVERA's real `geo.py` ([test_navera_geo.py](file:./test_navera_geo.py)); and write a launch test of
NAVERA's arbiter ([test_estimator_launch.py](file:./test_estimator_launch.py)). Analysis in
[report.md](file:./report.md).
**Time:** about 3 h. One terminal is enough.

## Part A — NAVERA's tests

### Step 1 — Start from a clean copy

Lesson 13 changed a setting of NAVERA. Ask git:

```bash
git -C ~/navera status
```

If you did lesson 13, git lists `modified: navera_estimator/navera_estimator/config/estimator_params.yaml`.
See the change, then throw it away (`git restore` cannot be undone — be sure):

```bash
git -C ~/navera diff
```

```bash
git -C ~/navera restore navera_estimator/navera_estimator/config/estimator_params.yaml
```

```bash
git -C ~/navera status
```

`nothing to commit, working tree clean` (untracked files such as `.pytest_cache/` are fine).

### Step 2 — One test file, then the whole suite

Go into your copy and run the geography tests, verbosely:

```bash
cd ~/navera
```

```bash
python3 -m pytest -v navera_common/test/test_geo.py
```

23 lines `PASSED`. Open [test_geo.py](file:navera/navera_common/test/test_geo.py) beside the output:
the `[brackets]` are parametrized cases. Now every unit test of every package (about 1 minute 20):

```bash
navera_tools/run_tests.sh
```

At the end: `359 passed … in …s` and **`ALL TESTS PASSED`**. Warnings about a failed download are
normal (no internet in the sandbox). Note the number of tests and the time for your report.

> [!NOTE]
> The machine is shared. If one GPU test (`test_gpu_and_cpu_matching_agree`) fails while the GPU is
> busy, run its file alone — `python3 -m pytest -q day_pkg/test/test_local_matcher.py` — and note
> it in your report: a test that depends on machine load is a **flaky** test, a real engineering
> problem.

### Step 3 — Break NAVERA on purpose

Open [geo.py](file:navera/navera_common/navera_common/geo.py), find `is_finite_latlon`, and replace
its last line `return not (lat == 0.0 and lon == 0.0)` by the "small change" of the course's story:

```python
    return True
```

Save, and run the geography tests again:

```bash
python3 -m pytest -q navera_common/test/test_geo.py
```

**2 failed, 21 passed.** Read the report as the course explains: `test_is_finite_latlon[0.0-0.0-False]`
(`assert True is False`) — and `test_invalid_start_is_refused`, a test of **another** function,
`dead_reckon`, which calls `is_finite_latlon`. Find that call in `geo.py`.

### Step 4 — Repair with git

```bash
git diff
```

The removed line starts with `-`, the added one with `+`. Throw the change away and check:

```bash
git restore navera_common/navera_common/geo.py
```

```bash
python3 -m pytest -q navera_common/test/test_geo.py
```

`23 passed`. Change, run the tests, read, fix: the daily loop of a software engineer. Go back to the
lab folder:

```bash
cd ~/lessons/14-testing
```

## Part B — Example tests

### Step 5 — Why one test is not enough

Open [geo_tools.py](file:./geo_tools.py): six **correct** helpers. Do not change them (except for the
experiment below). Run the two example tests:

```bash
python3 -m pytest -v test_geo_tools.py
```

`3 passed` (the parametrized test counts twice). Now delete `* math.cos(math.radians(lat_deg))` in
`meters_to_degrees`, save, and run again: still `3 passed` — nobody noticed. Undo with `Ctrl+Z` and save.

### Step 6 — Write the tests (TODO 1 to 4)

> [!TASK]
> In `test_geo_tools.py`, write the tests of TODO 1–4: at least 3 for `haversine_m`, 3 for
> `meters_to_degrees` / `offset_to_latlon`, one **parametrized** test with 6+ cases for
> `is_valid_position`, and 2 more for `speed_mps`. Use the `muscat` **fixture** in at least one test of
> yours. In total at least 10 tests, all passing on the correct code.

```bash
python3 -m pytest -v test_geo_tools.py
```

Then **attack your own tests** as the checker will: break one function (remove the `cos`, swap the
two return values of `meters_to_degrees`, make `is_valid_position` return `True` at the end, delete
the `if dt_s <= 0` block…), run the tests, check that **at least one fails**, undo (`Ctrl+Z`, save).

> [!TIP]
> A test that fails on the **correct** code is a wrong test: check the expected value (metres or
> degrees?) and the tolerance. Compute expected values independently (`M_PER_DEG` is at the top of the
> file), use `pytest.approx` for floats and `is` for `True`, `False`, `None`.

## Part C — Properties

### Step 7 — The example property

```bash
python3 -m pytest -v test_properties.py
```

One property, 100 generated examples, in a fraction of a second. Run it with statistics:

```bash
python3 -m pytest -q test_properties.py --hypothesis-show-statistics
```

### Step 8 — Your properties (TODO 5), and a counterexample

> [!TASK]
> In `test_properties.py`, write the properties a)–d) of TODO 5: symmetry, triangle inequality,
> validity of a small move, round trip.

Write the **validity** property first with the whole Earth as domain (`LAT`, `LON`) and
`@settings(deadline=None, max_examples=2000)`, then run:

```bash
python3 -m pytest -q test_properties.py
```

hypothesis prints a `Falsifying example: test_…(lat0=…, lon0=…, north=…, east=…)`. Copy it into your
report: what does it mean physically? (Course, section 3.) The example may be **near a pole**
(lat0 above about 80°) **or on the ±180° meridian** (lon0 = 180.0 or −180.0): both are the same
missing longitude wrap. Because the search is random, it may need
two or three runs; once found, hypothesis stores the example in `.hypothesis/` and replays it first.
Then restrict the domain of the validity and round-trip properties to |lat0| ≤ 80° and |lon0| ≤ 170°
(make two new strategies) and run again: all pass.

> [!WARNING]
> If a test fails with `DeadlineExceeded`, the shared machine was slow for one example: keep
> `@settings(deadline=None)` on every property.

## Part D — The real product

### Step 9 — Test NAVERA's geo.py (TODO 6)

> [!TASK]
> In `test_navera_geo.py`, write at least 5 tests of NAVERA's `is_finite_latlon`, `haversine_m` and
> `dead_reckon` (imported from your NAVERA copy), following the TODO.

The three functions are in [geo.py](file:navera/navera_common/navera_common/geo.py) — read their
docstrings first. `dead_reckon(lat, lon, heading_deg, speed_mps, dt_s)` moves a position along a
heading (degrees clockwise from north) at a speed (m/s) for dt seconds. It returns a tuple
`(lat, lon)`, or `None` when the motion is unknown or impossible (non-finite heading or speed, negative
speed, dt ≤ 0, or a start that `is_finite_latlon` refuses).

```bash
python3 -m pytest -v test_navera_geo.py
```

Prove that your tests protect the product: break `is_finite_latlon` in `~/navera` again (step 3), run
your file — your own test must fail — then repair NAVERA:

```bash
git -C ~/navera restore navera_common/navera_common/geo.py
```

### Step 10 — A launch test of the arbiter (TODO 7)

Read [test_estimator_launch.py](file:./test_estimator_launch.py): `generate_test_description()` starts
NAVERA's arbiter, `TestArbiter` runs while it runs, `TestShutdown` checks its exit code afterwards.

> [!TASK]
> **TODO 7a** — one GNSS estimate → `STATE_FIX` and exactly one position. **TODO 7b** — a NaN latitude
> → `STATE_NO_FIX`, `non-finite` in the reason, no position.

```bash
launch_test test_estimator_launch.py
```

About 10 seconds: the arbiter's log lines appear between the test results; at the end `Ran 3 tests
… OK` and the shutdown test `OK`. Try to make test 7a fail on purpose (expect two positions instead of
one) to see what a failing launch test prints — then put it back.

## Step 11 — Write the analysis

Make sure your NAVERA copy is clean (`git -C ~/navera status`), then fill [report.md](file:./report.md)
(at least 40 words per section): **NAVERA's tests**, **Mutants**, **Properties**.

Press **✔ Check my work**. The checker runs your tests on the correct code, then on **12 wrong
versions** of `geo_tools.py` and **5 wrong versions** of NAVERA's `geo.py`, runs your launch test,
and checks that NAVERA is restored. For each surviving mutant it tells you what kind of test would kill
it. About 2 minutes.

## Going further (optional)

- **Mutation score.** Install nothing: write a 30-line script that applies the checker's idea to
  `geo_tools.py` with your own list of mutants and prints the score. Find one **equivalent** mutant.
- **Test lesson 11's Tracker.** Copy `~/lessons/11-subscriber/gps_listener.py` here and write property
  tests for `Tracker`: the distance never decreases; a rejected fix changes nothing; the speed of a
  vehicle that does not move is 0.
- **Read a regression test.** In `~/navera/gps_pkg/test/test_ros_gps.py`,
  `test_a_zero_or_undefined_covariance_is_not_an_accuracy` protects a rule of lesson 12. Which one?
  Break `estimate_from_fix` in your copy to make it fail, then `git restore`.
