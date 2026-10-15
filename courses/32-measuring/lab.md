# Lab 32 — Measure three flights, beat the baseline, put error bars on it

**Goal:** write NAVERA Lite's measuring part (`navera_lite/stats.py`, nine TODOs) and the baseline
(`baseline.py`, TODO A); measure three flights flown by NAVERA Lite's judge; decide with intervals whether a
vision source beats "repeat the last GPS position"; test your intervals with a coverage experiment; check
whether a recorded source states an honest σ; write a validation note.
**Time:** 4 h 30 to 6 h in two sessions (a strong programmer: about 3 h 30; new to numpy and pandas: up to 7 h — use the 🧰 boxes).
**Fast track:** if you know numpy and pandas well, skip the 🧰 boxes and the "Stuck?" boxes; do "Going further".

Your files (📝 Code tab): [navera_lite/stats.py](file:./navera_lite/stats.py) (**your code**: TODO 1–9),
[baseline.py](file:./baseline.py) (TODO A), [answers.py](file:./answers.py), [report.md](file:./report.md).
Given, you only run them: [measure_lab.py](file:./measure_lab.py) (calls your functions on the flights) and the
tool `navera_lite/tools/evaluate_bag.py`. `navera_lite/logbook.py` is mission 04's part, finished.

The data, in `/data/academy/32-measuring/` (synthetic, NAVERA's test area around Sousse, Tunisia): three versions
of one 240 s drone flight at 15 m/s, one row per second, with the decisions of NAVERA Lite's judge (the course's
reference judge of mission 29) and the true position. GPS is **jammed from 90 s to 149 s**; the judge then uses
day vision.

| File | Day vision during the jam |
|---|---|
| `flight_target.csv` | a "target" error profile; it finds no match for a while over a lake |
| `flight_retrieval.csv` | a retrieval-like profile (errors of hundreds of metres), a position every second |
| `flight_selective.csv` | `flight_retrieval` with every vision position more than 300 m off **withheld** |
| `shadow_bag/`, `shadow_truth.csv` | another flight, GPS good, GPS and day vision recorded (Step 9) |

| Lesson | Lab | You write |
|---|---|---|
| (nothing first) | Step 0 | nothing: look at the flights, predict |
| §1 | Step 1 | `errors_m` (TODO 1) |
| §2 | Step 2 | `percentile` (TODO 2), `summary` (TODO 3) |
| §3, §4 | Step 3 | `availability` (TODO 4), `longest_gap_s` (TODO 5), `last_fix_baseline` (TODO A) |
| §2 | Step 4 | nothing: the two percentile rules |
| §5, §6 | Step 5 | `bootstrap_ci` (TODO 6) |
| §6 | Step 6 | `paired_diff_ci` (TODO 7), the intervals of the flights |
| §7 | Step 7 | `wilson` (TODO 8) |
| §8 | Step 8 | `coverage_experiment` (TODO 9) |
| §9 | Step 9 | nothing: `evaluate_bag` on a bag |
| all | Step 10 | `report.md` |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step; it is never
> marked right or wrong. Each TODO's docstring says its goal and gives one example with its result;
> `python3 measure_lab.py test` tries every example. The lesson shows how; the code is yours.

## Session 1 — The numbers (2 h to 2 h 30)

## Step 0 — Look at the flights (no code)

```bash
head -3 /data/academy/32-measuring/flight_target.csv
```

The columns: time, GPS mode, the judge's state and source, the σ the winner states, the position the judge gave
(empty: no position), and the truth. Now the story of each flight, one line per stretch of identical rows:

```bash
cut -d, -f2-5 /data/academy/32-measuring/flight_target.csv | uniq -c
```

```bash
cut -d, -f2-5 /data/academy/32-measuring/flight_retrieval.csv | uniq -c
```

`cut -f2-5` keeps columns 2 to 5; `uniq -c` counts identical neighbouring lines. In the target flight you see a
stretch of `NO_FIX` in the middle of the jam: the lake.

> [!TASK]
> **Predict** (`PREDICT_BEAT` in `answers.py`): during the 60 s jam, will the retrieval-like vision of
> `flight_retrieval` beat the baseline "repeat the last GPS position", and by how much (median)? The drone flies
> at 15 m/s (lesson §4 shows how to estimate the baseline). Then read the lesson, §1 to §4.

## Step 1 — Errors against the truth (TODO 1)

Open [navera_lite/stats.py](file:./navera_lite/stats.py). Read the top of the file (what a flight table holds),
then write **TODO 1**, `errors_m(df)`. `haversine_m` (mission 04) is imported at the top and works on whole
columns at once.

> [!TIP] 🧰 Keep the rows that have every value
> ```python
> import numpy as np
> a = np.array([[1.0, 2.0], [np.nan, 5.0], [3.0, 4.0]])
> ok = np.all(np.isfinite(a), axis=1)     # array([ True, False,  True]): one answer per row
> a[ok]                                   # only rows 0 and 2
> df[["lat", "lon"]].to_numpy(dtype=float)   # a DataFrame's columns as a numpy array (empty cell → nan)
> ```

```bash
python3 measure_lab.py test
```

The TODO 1 line must be ✔ (the other TODOs are still ✘: normal).

<details><summary>Stuck? Hints, one at a time</summary>

1. Four columns matter: `lat`, `lon`, `truth_lat`, `truth_lon`. A row counts only if all four are numbers.
2. Build the mask of good rows first, then call `haversine_m(truth lat, truth lon, lat, lon)` once on the kept
   columns — no loop needed.
3. You see `nan` in the result, like `(0.000, nan, 11.119)`? You kept the row without a position: the mask must
   drop it.
4. Your result is a pandas Series? Wrap it: `np.asarray(…, dtype=float)`.
</details>

## Step 2 — Percentiles and the summary (TODO 2, TODO 3)

**First a hand trace** (on paper, 3 minutes): the linear p25 and p80 of [12, 4, 9, 20, 6]. Check below, then
write **TODO 2**, `percentile(v, q)`, with the rule of lesson §2 — not with `np.percentile` (use it only to
test yours in a terminal).

<details><summary>The hand trace</summary>

Sorted [4, 6, 9, 12, 20], n − 1 = 4. p25: position 1.0 → **6.0**. p80: position 3.2 → 12 + 0.2 × 8 = **13.6**.
</details>

> [!TIP] 🧰 Whole and fractional part
> ```python
> import math
> pos = 3.2
> i = math.floor(pos)      # 3: the sample just below
> frac = pos - i           # 0.2 (to rounding): how far towards the next one
> ```

Then **TODO 3**, `summary(errs)`: seven numbers in a dict, the percentiles with YOUR `percentile()`.

```bash
python3 measure_lab.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. TODO 2: sort first; the position is (n − 1) · q / 100; when it is a whole number, the answer is that sample.
2. TODO 2: at q = 100 the position is n − 1: there is no "next" sample — return the last one (an `IndexError`
   says you read past the end).
3. TODO 2 gives 5.0 instead of 4.0 for `[7, 1, 3, 5], 50`? You took the nearest sample, or the position n·q/100 instead of (n − 1)·q/100:
   interpolate at (n − 1)·q/100.
   2.0? You forgot to sort.
4. TODO 3 gives rmse 3.0 instead of 5.831? That is the standard deviation; the RMSE is √(mean of e²), around 0,
   not around the mean.
5. TODO 3, empty list: return `{"n": 0}` with every other key `None` (no `max()` of an empty list).
</details>

## Step 3 — Availability, gaps and the baseline (TODO 4, TODO 5, TODO A)

**TODO 4** `availability(df)` and **TODO 5** `longest_gap_s(df)`: `usable_mask()` is given and says, row by row,
whether the autopilot can use it. For TODO 5, mission 04's `outage_runs()` is imported: it finds runs of 0.

> [!TIP] 🧰 True/False as numbers
> ```python
> m = np.array([True, False, True, True])
> m.mean()            # 0.75: True counts 1, False 0
> m.astype(int)       # array([1, 0, 1, 1]) — what outage_runs() expects
> ```

**TODO A** in [baseline.py](file:./baseline.py), `last_fix_baseline(df)`: the error of repeating the judge's
last GPS position during the jam (lesson §4). Read its docstring twice: *which* position is frozen matters.

> [!TIP] 🧰 Rows of a table that match a condition (pandas)
> ```python
> jam = (df["gps"] == "jammed").to_numpy()   # one True/False per row
> first = int(jam.argmax())                   # index of the first True (check jam.any() first)
> before = df.iloc[:first]                    # the rows above it
> g = before[before["source"] == "gps"]       # only the GPS rows among them
> g["lat"].iloc[-1]                           # the last of them
> ```

```bash
python3 measure_lab.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. TODO 4 is one line with `usable_mask()`; an empty table gives `float("nan")`.
2. TODO 5: a run (i0, i1) of unusable rows lasts `t_s[i1 − 1] − t_s[i0] + dt_s`; keep the largest, 0.0 if no run.
   Use `dt_s`, not 1: the check uses rows every 0.5 s.
3. TODO A: find the first jammed row (`df["gps"] == "jammed"`); keep the rows before it whose `source` is
   `"gps"`; the last of them is the frozen position. Then the distance from it to the truth of every jammed row.
4. TODO A: the frozen position is the judge's `lat, lon`, not `truth_lat, truth_lon` (the baseline repeats what
   the autopilot was given), and it is not simply the last row before the jam (that row may be day vision).
</details>

Now the three flights:

```bash
python3 measure_lab.py flights
```

Open [out/errors_target.png](file:./out/errors_target.png),
[out/errors_retrieval.png](file:./out/errors_retrieval.png) and
[out/errors_selective.png](file:./out/errors_selective.png) (the error axis is logarithmic above 10 m). Yellow:
the jam. Red: the baseline. Grey ticks: no position.

> [!TASK]
> In `answers.py`: `RETR_JAM_MEDIAN_M`, `BASE_JAM_MEDIAN_M`, `TARGET_LONGEST_GAP_S`, `SELECTIVE_JAM_MEDIAN_M`,
> `SELECTIVE_JAM_AVAIL_PCT` (in %), then `EXPLAIN_MAX` (the target flight's worst error: when, and why so large?
> Clue: just before the grey ticks of the lake the error grows by about 15 m every second — what moves at 15 m/s,
> and what does mission 29's judge keep giving while its last day fix is younger than the 5 s timeout?) and `EXPLAIN_SELECTIVE` (is the selective flight's navigation better?).
> Compare your answer with `PREDICT_BEAT`.

## Step 4 — Two percentile rules

```bash
python3 measure_lab.py rules
```

Your linear `percentile()` against the given `pct_nearest()` (the nearest-sample rule) on the jam errors of
each flight.

> [!TASK]
> `EXPLAIN_RULE`: for `flight_target` (51 errors during the jam) the two rules give the same median but p95
> values about 7 m apart. Why exactly the same for one, and so different for the other? (Compute the positions.)
> Press **✔ Check my work** — checks 1–7 should be green: badge **Honest ruler**.

## Session 2 — Error bars (2 h 30 to 3 h 30)

## Step 5 — The bootstrap (TODO 6)

**TODO 6**, `bootstrap_ci(x, stat, B, alpha, seed, block)`: lesson §5 for `block = 1`, §6 for blocks. Write the
iid case first, test it, then add blocks.

> [!TIP] 🧰 Random indices with numpy
> ```python
> rng = np.random.default_rng(7)          # a generator; the same seed gives the same numbers
> rng.integers(0, 5, size=3)              # 3 whole numbers from 0 to 4 — the upper bound 5 is EXCLUDED
> x = np.array([10., 20., 30., 40., 50.])
> x[np.array([4, 0, 4])]                  # array([50., 10., 50.]): an array of indices picks values
> np.arange(3, 3 + 4)                     # array([3, 4, 5, 6]): 4 consecutive indices from 3
> np.concatenate([np.arange(0, 2), np.arange(7, 9)])   # array([0, 1, 7, 8])
> np.percentile(reps, [2.5, 97.5])        # two percentiles at once (linear rule)
> ```

> [!TIP] 🧰 Functions are values
> `bootstrap_ci(x, np.median)` passes the *function* `np.median`, without calling it; inside, `stat(sample)`
> calls it. Like `sorted(words, key=len)`. Any function of one array works, including your own:
> `bootstrap_ci(x, lambda v: np.percentile(v, 90))`.

**Hand trace first** (blocks, 3 minutes): n = 7, block = 3. Which start indices are allowed? How many runs do
you need to reach 7 values, and how many values do you cut at the end?

<details><summary>The hand trace</summary>

Starts 0 to n − L = 4 (that is `rng.integers(0, 5)`); 3 runs give 9 values; cut the last 2. With block = n only
start 0 is possible: the resample is the data itself.
</details>

```bash
python3 measure_lab.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Turn `x` into a numpy array first (`np.asarray(x, dtype=float)`), so that `x[idx]` works.
2. Make ONE generator from `seed` before the loop; inside the loop, draw the indices of one resample, then
   `stat(x[idx])`; store the B results.
3. The interval: the percentiles `100 · alpha / 2` and `100 · (1 − alpha / 2)` of the B results; return two floats.
4. Blocks: draw the run starts with `rng.integers(0, n − block + 1, …)`; each start s gives
   `np.arange(s, s + block)`; join, cut to n. Runs never wrap around the end.
5. The check says "every resample must have len(x) values"? You did not cut the joined runs to n. "the first
   value is always 0" fails? Your runs wrap around (`% n`) or start beyond n − L.
</details>

## Step 6 — The intervals of the flights (TODO 7)

**TODO 7**, `paired_diff_ci(a, b, stat, …)`: as TODO 6, but each resample uses ONE set of indices for both lists
(lesson §6). If you want, move the drawing of indices into a small helper function used by both TODOs.

```bash
python3 measure_lab.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Check the lengths first: `ValueError` if they differ.
2. One `idx` per resample, then `stat(a[idx]) − stat(b[idx])`: a minus b, in this order.
3. The docstring's example gives something wide like (0.800, 9.000) instead of (5.0, 5.0)? You drew separate
   indices for a and b: the pairs were broken.
</details>

> [!TASK]
> **Predict** (`PREDICT_BLOCK`): for which flight will the block interval of the jam median differ most from the
> iid one, and why? Then run:

```bash
python3 measure_lab.py ci
```

The block interval of `flight_selective` is **n/a**: 41 of its 60 jam seconds are missing, so a "block" of 10
kept values would join seconds far apart (lesson §6).

> [!TASK]
> `EXPLAIN_PAIRED`: for `flight_retrieval`, what may you write about "vision vs baseline"? Quote the interval.
> `EXPLAIN_SELECTIVE_CI`: `flight_selective`'s paired interval lies entirely below 0. Has it proved that it beats
> the baseline? Why not?

> [!NOTE] Behind the curtain (read after you wrote your answers)
> `flight_retrieval`'s vision errors were drawn from a profile whose TRUE median is 436 m — really 14 m better
> than the baseline's 450 m. Your interval [about −282, 190] m was right not to claim it: a real 14 m gain is
> invisible in one 60 s jam with n_eff ≈ 7. "Contains 0" means "not shown", never "equal". One more confession:
> its random seed was picked among 40 so that the flight looks like NAVERA's 442 vs 480 m — a best-of-N, fine
> for a demonstration only because we tell you.

## Step 7 — Success rates (TODO 8)

**TODO 8**, `wilson(k, n, z)`: the three lines of lesson §7. `ValueError` for impossible counts.

```bash
python3 measure_lab.py wilson
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Work in shares (0 to 1), not in per cent: `p = k / n`.
2. `measure_lab.py test` shows (0.552, 1.048) — or (0.552, 1.000) if you already clip — for
   `wilson(8, 10)`? That is the naive interval: compute the
   centre and the half-width of lesson §7.
3. For k = 0 the lower end must come out 0.0 (to rounding): clip with `max(0.0, …)` and `min(1.0, …)`.
</details>

> [!TASK]
> `WILSON_LO_PCT` (32 of 33, lower end, in %) and `ZERO_UPPER_PCT` (0 of 33, upper end, in %). Compare the
> second with the rule of three.

## Step 8 — Do the intervals keep their promise? (TODO 9)

**TODO 9**, `coverage_experiment(make_sample, ci_of, true_value, trials, seed)`: lesson §8. This one has the
least help. Trace on paper what happens for 2 trials of the docstring's example, then write it.

```bash
python3 measure_lab.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. One generator for the whole experiment, made before the loop.
2. Each trial: a sample, its interval, a hit or not. Both functions get the same `rng`.
3. You got 932 instead of about 0.93? Return the share, not the count.
</details>

> [!TASK]
> **Predict** (`PREDICT_COVERAGE`): correlated errors (ρ 0.9, 60 s) and the iid bootstrap: how often will a
> "95 %" interval of the median contain the true median? Then run (1 to 3 minutes; the class shares the machine):

```bash
python3 measure_lab.py coverage
```

> [!TASK]
> `EXPLAIN_COVERAGE`: why does the iid bootstrap fail on correlated errors, and why do blocks help only partly?
> (Lesson §6: n_eff.)

## Step 9 — Is the stated σ honest? (evaluate_bag)

A ROS 2 bag recorded in shadow mode: GPS good, GPS and day vision both recorded as `NavSatFix`. First what it holds:

```bash
ros2 bag info /data/academy/32-measuring/shadow_bag
```

Then the given tool, which uses YOUR `percentile()`. With the GPS of the bag as the truth (what you would have on
a real flight):

```bash
python3 -m navera_lite.tools.evaluate_bag /data/academy/32-measuring/shadow_bag
```

With the true track (a reference you rarely have):

```bash
python3 -m navera_lite.tools.evaluate_bag /data/academy/32-measuring/shadow_bag --truth /data/academy/32-measuring/shadow_truth.csv
```

And with the nearest-sample rule:

```bash
python3 -m navera_lite.tools.evaluate_bag /data/academy/32-measuring/shadow_bag --rule nearest
```

> [!TASK]
> From the run with `--truth`: `HONEST_SIGMA_DAY_M` and `DAY_WITHIN_2SIGMA_PCT`. Then `EXPLAIN_GPS_STATED`: the
> GPS states 2.0 m but its honest σ is smaller. Is that a problem? Why is it the better mistake for a judge?
> Compare the day source's numbers with GPS as the truth and with the true track: is GPS good enough as a truth
> for this source (lesson §1)?

## Step 10 — The validation note

Fill in [report.md](file:./report.md): what was measured, the table, whether each difference is real, whether
the stated σ is honest, the limits, a conclusion. A good conclusion says **what** is better, **by how much**
(with an interval), **compared with what**, on **how much data**, measured **where** — and what it does **not**
prove. No "accurate", "robust" or "works well" without a number.

> [!TIP] 🧰 A model sentence (another, made-up test — copy the structure, not the numbers)
> "On 4 synthetic 90 s jams over farmland near Kairouan, the new matcher's median error was 18 m against 41 m
> for repeating the last GPS position (paired difference −23 m, 95 % block interval [−31, −12] m), with 92 %
> availability and a longest gap of 6 s. This shows a gain on this terrain and in this simulator only: it does
> not show the gain over sand, at night or with a real camera, and the interval does not cover those."

> [!TASK]
> No "(fill in …)" and no "…" left; your numbers in the table (metres rounded to the metre, % to the per cent);
> the retrieval flight's block interval of the difference; the honest σ of the day source; sections 3 (40+
> words), 4 (25+), 5 (60+) and 6 (80+); the words baseline, interval, availability, synthetic or simulated, Sousse.
> Press **✔ Check my work** — all 15 checks green: badge **Auditor**. (The check reads that your explanations
> are written and on topic; your teacher reads what they say.)

## Look back (not graded)

1. Which number of a product sheet will you now read differently, and what would you ask its author?
2. Your coverage experiment gave a coverage below 95 % even with blocks. What would you change in a field test
   plan (length of the flights, number of flights) to get honest intervals?
3. `LOOK_BACK` in `answers.py`: one sentence for your future self.

## Going further (optional)

- **A fairer baseline.** "Repeat the last position" ignores that the drone was moving. Write a dead-reckoning
  baseline: continue the last GPS velocity (from the last two GPS fixes) in a straight line. Does the target
  vision still beat it? Which baseline would you publish, and why the harder one?
- **How long must a test be?** With `ar1_radial(rng, n, 0.9, 10.0)` and your coverage experiment, find the n for
  which the block bootstrap of the median reaches 90 % coverage. Translate it into minutes of jammed flight.
- **Best of N.** Simulate 5 flights with `ar1_radial` (ρ 0.9, n 60, σ 10 m) and report the smallest median, as a
  brochure would. Repeat 1 000 times: how far below the true median (11.8 m) is the "best of 5" on average?
- **Rule of three.** With a true failure rate of 1 %, how often do you see 0 failures in 33 trials? In 300?
