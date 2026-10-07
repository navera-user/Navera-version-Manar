# Lab 14 — Tests that catch bugs

**Goal:** run NAVERA's own tests, break NAVERA on purpose and watch a test catch it, put everything
back with git, then write your own tests — strong enough to catch the wrong code the checker will
try on them.
**Time:** about 1 hour 30 minutes.

One terminal is enough today.

## Part A — NAVERA's tests

### Step 1 — Start from a clean copy

In lesson 13 you changed a setting of NAVERA. Let's see what git says about your copy:

```bash
cd ~/navera
```

```bash
git status
```

If you did lesson 13, git lists `modified: navera_estimator/navera_estimator/config/estimator_params.yaml`.
See the change itself:

```bash
git diff
```

The line `fix_max_sigma_m` went from `25.0` to `2.0`. Put the file back exactly as it was in the last
commit — `git restore` throws your change away (be sure before using it!):

```bash
git restore navera_estimator/navera_estimator/config/estimator_params.yaml
```

```bash
git status
```

`nothing to commit, working tree clean` (or only "untracked files" you created — that's fine).

### Step 2 — Run one test file

Still in `~/navera`, run the tests of NAVERA's geography helpers:

```bash
python3 -m pytest -v navera_common/test/test_geo.py
```

23 lines `PASSED`, then `23 passed`. Open
[test_geo.py](file:navera/navera_common/test/test_geo.py) next to the output and match a few names
with their functions. Notice the cases in `[brackets]`: they come from `@pytest.mark.parametrize`.

### Step 3 — Run all the unit tests

NAVERA's official test script runs every unit test of every package. It takes about one minute:

```bash
navera_tools/run_tests.sh
```

At the end: `… passed` and **`ALL TESTS PASSED`**. A few warnings (for example about a failed
download — your sandbox has no internet) are normal. This is what NAVERA's engineers run before
every change is accepted.

### Step 4 — Break NAVERA on purpose

Open [geo.py](file:navera/navera_common/navera_common/geo.py) and find the function
`is_finite_latlon`. Its last line refuses Null Island:

```python
    return not (lat == 0.0 and lon == 0.0)
```

Replace it with the "small change" of the course's story, and save:

```python
    return True
```

Run the geography tests again:

```bash
python3 -m pytest -q navera_common/test/test_geo.py
```

**2 failed, 21 passed.** Read the report like in the course:

- `test_is_finite_latlon[0.0-0.0-False]`: `assert True is False` — `is_finite_latlon(0.0, 0.0)` returned
  `True`. Caught in a fraction of a second.
- `test_invalid_start_is_refused`: a test of **another** function, `dead_reckon`, failed too —
  because `dead_reckon` uses `is_finite_latlon` to refuse a bad start. One broken helper, two broken
  behaviours.

> [!QUESTION]
> Which line of `dead_reckon` calls `is_finite_latlon`? What would a drone do if dead-reckoning
> started from (0, 0)?

### Step 5 — Repair with git

What exactly did you change?

```bash
git diff
```

Git shows the line you removed (`-`) and the one you added (`+`). Throw the change away:

```bash
git restore navera_common/navera_common/geo.py
```

```bash
python3 -m pytest -q navera_common/test/test_geo.py
```

`23 passed`. This loop — **change, run the tests, read, fix** — is the daily life of a software
engineer.

> [!NOTE]
> `git status` may now list `.pytest_cache/` or `.hypothesis/` as *untracked*: pytest's own notes,
> not a change of NAVERA. You can ignore them.

Go back to your lab folder:

```bash
cd ~/lessons/14-testing
```

## Part B — Your own tests

### Step 6 — Run the example

Open [geo_tools.py](file:./geo_tools.py): four **correct** helpers, like the ones of lesson 6. Do not
change them. Then open [test_geo_tools.py](file:./test_geo_tools.py): one example test, and four TODOs.

```bash
python3 -m pytest -v test_geo_tools.py
```

`1 passed`. Now see why one test is not enough: in `geo_tools.py`, temporarily delete
`* math.cos(math.radians(lat_deg))` in `meters_to_degrees`, save, and run the tests again. Still
`1 passed` — nobody noticed the bug! Press `Ctrl+Z` in the editor to put the code back, and save.

### Step 7 — Write the tests (TODO 1 to 4)

> [!TASK]
> In `test_geo_tools.py`, write **at least 8 more tests** — at least 2 for `haversine_m`, 2 for
> `meters_to_degrees`, 3 for `is_valid_position` and 2 for `speed_mps`. The comments give ideas.
> All of them must pass on the correct `geo_tools.py`.

Run them often:

```bash
python3 -m pytest -v test_geo_tools.py
```

Then **attack your own tests** like the checker will: break one function of `geo_tools.py` (remove the
`cos`, swap the two return values, make `is_valid_position` return `True` at the end, remove the
`if dt_s <= 0` block…), run the tests, and check that **at least one test fails**. Undo the change
(`Ctrl+Z`, save) after each attack.

> [!TIP]
> If a test fails on the **correct** code, the test is wrong, not the code: check your expected value
> (is it in metres? degrees?) and your tolerance. Write `pytest.approx(…)` for decimals and `is None` /
> `is False` for exact values.

### Step 8 — Test the real product (TODO 5)

> [!TASK]
> In [test_navera_geo.py](file:./test_navera_geo.py), write **at least 3 tests** of NAVERA's
> `is_finite_latlon` and `haversine_m` (imported from your NAVERA copy): Sousse is a position, (0, 0),
> NaN and `None` are not, and 1 degree of latitude is about 111 195 m.

```bash
python3 -m pytest -v test_navera_geo.py
```

These tests import `navera_common.geo` from **your NAVERA copy**. Try it: break `is_finite_latlon`
again in `~/navera` as in step 4, run your test file — your own test must fail now — then repair NAVERA
with `git -C ~/navera restore navera_common/navera_common/geo.py`.

### Step 9 — Check your work

Make sure your NAVERA copy is clean (`git -C ~/navera status`), then press **✔ Check my work**. The
checker runs your tests on the correct code, then on **10 wrong versions** of `geo_tools.py` and
**3 wrong versions** of NAVERA's `geo.py`. For each wrong version that your tests do not catch, it
tells you which bug survived and what kind of test would catch it.

## Going further (optional)

- **Your test, NAVERA's style.** Rewrite your invalid-position tests as one test with
  `@pytest.mark.parametrize`, like NAVERA's `test_is_finite_latlon`.
- **Test lesson 11's Tracker.** Copy `~/lessons/11-subscriber/gps_listener.py` here and write tests for
  `Tracker.update()`: first fix, two fixes, `dt = 0`. No ROS needed — that was the point of separating
  the logic!
- **Read a regression test.** In `~/navera/gps_pkg/test/test_ros_gps.py`, the test
  `test_a_zero_or_undefined_covariance_is_not_an_accuracy` protects a rule you met in lesson 12. Which
  one? Break `estimate_from_fix` in your copy to make it fail, then `git restore`.
