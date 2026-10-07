# Lab 29 — Measure three flights, beat the baseline, put error bars on it

**Goal:** compute the error statistics (CEP50, CEP95, RMSE), availability and longest gap of three
recorded flights; compare NAVERA with the "repeat the last position" baseline; implement the
bootstrap (iid and block), the paired difference and the Wilson interval; test your confidence
intervals with a coverage experiment; check a source's stated σ with NAVERA's own
`evaluate_session.py`; and write an honest report.
**Time:** about 3 h.

Your files:
[measure.py](file:./measure.py) (TODO 1–6),
[bootstrap.py](file:./bootstrap.py) (TODO 7–10),
[answers.py](file:./answers.py) and [report.md](file:./report.md).

The data (`/data/academy/29-measuring/`, read only). NAVERA's test area is **Sousse, Tunisia**, where
NAVERA is developed: the flights were recorded with NAVERA's mission simulator there (lesson 28,
`/data/academy/28-simulator/record_sample.sh`). A drone flies at ~15 m/s; the GPS is **jammed for
60 s**, later **spoofed** for 30 s. One row per second.

| File | What replaces GPS during the jam | What it represents |
|---|---|---|
| `flight_target.csv` | simulated vision, *target* profile (states 15 m) | the accuracy **goal** — not a measured performance |
| `flight_measured.csv` | simulated vision, *former day vision* profile (~440 m median, σ unknown) | the error **measured** on real frames for the former DINOv2 method |
| `flight_selective.csv` | `flight_measured` with every vision position > 300 m off **removed** | **synthetic**: the availability trap |
| `shadow_bag/` | a ROS 2 bag: GPS + a day-vision source that states σ = 15 m | **synthetic**, for `evaluate_session.py` |

The simulator's own error column has been removed: you compute the errors yourself from
`truth_lat/lon` and `navera_lat/lon`.

> [!NOTE]
> The shared simulator is **not** needed for this lab: everything uses recorded data. If you flew your
> own mission in lesson 28, you can measure it too ("Going further").

## Step 1 — Look at the data (10 min)

```bash
head -3 /data/academy/29-measuring/flight_target.csv
```

```bash
cut -d, -f2,3,4,5 /data/academy/29-measuring/flight_target.csv | uniq -c
```

The second command counts the seconds spent in each (phase, GPS mode, NAVERA state, source): the
whole story of the flight in a dozen lines. Now the synthetic one:

```bash
cut -d, -f2,3,4,5 /data/academy/29-measuring/flight_selective.csv | uniq -c | head -25
```

During the jam you see `NO FIX` holes: these are the positions that were removed. Keep that picture
in mind for Step 3.

## Step 2 — Errors and statistics (TODO 1–3, 30 min)

Open [measure.py](file:./measure.py). Each function has a docstring that says exactly what to return.

- **TODO 1** `errors(rows)`: one `(t, error_m)` per *en route* row where NAVERA gave a position.
  `haversine_m()` is written for you below the line.
- **TODO 2** `percentile(values, p)`: the nearest-rank rule of `evaluate_session.py` (lesson, §2).
  Use Python's `round()`: the check tests a case where `round(4.5) == 4` matters.
- **TODO 3** `stats(values)`: a dict with the keys `n`, `mean`, `rmse`, `cep50`, `p90`, `cep95`, `max`.

Test TODO 3 on the lesson's worked example before you use real data. `python3 -c` runs one line:

```bash
python3 -c "import measure; print(measure.stats([2.1, 3.4, 1.8, 4.6, 2.9, 3.1, 12.5, 2.4, 3.8, 2.6]))"
```

You should get mean 3.92, rmse 4.915, cep50 2.9, p90 4.6, cep95 12.5, max 12.5. Then:

```bash
python3 measure.py /data/academy/29-measuring/flight_target.csv
```

You get NAVERA's error on the whole flight, while GPS is used, and while GPS is jammed. Compare RMSE
/ CEP50 in each line with the Gaussian value 1.2 (lesson §2). Which line looks Gaussian?

> [!WARNING]
> Common errors: `TypeError: '<' not supported between 'NoneType' and 'float'` — you forgot to skip
> rows without a position (`navera_lat is None`). `IndexError` in `percentile` — the index must never
> exceed `len(s) - 1` (use `min`).

## Step 3 — Availability, gaps and the baseline (TODO 4–6, 30 min)

- **TODO 4a** `availability(rows, gps_mode=None)`: the percentage of *en route* rows with a usable
  position (`usable(r)` is written for you). With `gps_mode="jammed"`, only the jammed rows.
- **TODO 4b** `longest_gap_s(rows)`: the longest run of consecutive *en route* rows without a usable
  position (one row = one second).
- **TODO 5** `baseline_errors(rows)`: what if NAVERA had kept the last GPS position it had before the
  jam? Find the first jammed row, the last NAVERA position given by GPS before it, and for every jammed
  *en route* row the distance from the truth to that frozen position.
- **TODO 6**: in `main()`, plot the baseline as a red line.

Run the three flights:

```bash
python3 measure.py /data/academy/29-measuring/flight_target.csv /data/academy/29-measuring/flight_measured.csv /data/academy/29-measuring/flight_selective.csv
```

Open [error_flight_target.png](file:./error_flight_target.png),
[error_flight_measured.png](file:./error_flight_measured.png) and
[error_flight_selective.png](file:./error_flight_selective.png). The yellow band is the jam. The red
line grows steadily: the drone flies away from the frozen position at ~15 m/s.

> [!QUESTION]
> In `flight_measured`, compare the blue dots and the red line at the **start** of the jam and at the
> **end**. Is the vision method better than doing nothing all the time? Now compare `flight_measured`
> and `flight_selective`: the selective CEP50 during the jam is much smaller. Is the navigation better?

<details><summary>Think about it</summary>
At the start of a jam the frozen position is still close: a ~440 m method is <i>worse</i> than doing
nothing for the first tens of seconds; it wins only once the drone has flown farther than its typical
error. The selective flight is the same method with the bad seconds deleted: the CEP50 improves only
because it is computed on 14 easy seconds out of 60. Its availability while jammed is about 23 % and
its longest gap 13 s — an autopilot would lose its position.
</details>

> [!TASK]
> Complete TODO 1–6 and run `measure.py` on the **three** flights. "Done" means: the functions pass the
> unit checks (worked example, a small hand-made flight), and `results_flight_target.json`,
> `results_flight_measured.json`, `results_flight_selective.json` and the three PNG files exist with
> the right numbers (CEP50, RMSE, CEP95, max of the whole flight, the jam and the baseline;
> availability; longest gap). Press **✔ Check my work** — checks 1–5, 10 and 12 should be green.

## Step 4 — The bootstrap (TODO 7–8, 40 min)

Open [bootstrap.py](file:./bootstrap.py).

- **TODO 7b** `_resample_idx(rng, n, block)`: the indices of **one** resample. With `block == 1`:
  `rng.integers(0, n, size=n)`. With `block > 1`: k = ceil(n / block) random block starts in
  `[0, n − block]`, each giving `block` consecutive indices; join them and cut to n.
- **TODO 7a** `bootstrap_ci(values, stat, B, alpha, seed, block)`: B resamples, the statistic of each,
  then the 2.5 / 97.5 percentiles (`np.percentile`). Use `np.random.default_rng(seed)` so that the
  same call always gives the same interval — results must be **reproducible**.
- **TODO 8** `paired_diff_ci(a, b, ...)`: the same, but each resample computes
  `stat(a[idx]) - stat(b[idx])` with the **same** `idx` for both lists.

`numpy` indexing with an array of indices: `x[idx]` picks the values at those positions (`x` must be a
numpy array, which the starter code already makes).

```bash
python3 bootstrap.py
```

You should see the lesson's numbers: median 3.85 m, CI [3.05, 5.40]; mean CI about [3.47, 10.99].

Now run the flights again: `measure.py` calls your functions with the nearest-rank median and blocks
of 10 s.

```bash
python3 measure.py /data/academy/29-measuring/flight_target.csv /data/academy/29-measuring/flight_measured.csv /data/academy/29-measuring/flight_selective.csv
```

Look at the lines "95 % CI". Then look at the paired difference in detail:

```bash
python3 -c "import json; print(json.load(open('results_flight_measured.json'))['ci'])"
```

> [!QUESTION]
> For `flight_measured`, does the CI of "CEP50 of NAVERA − CEP50 of the baseline" contain 0? For
> `flight_target`? What exactly may you write in each case?

## Step 5 — Wilson and the coverage experiment (TODO 9–10, 40 min)

- **TODO 9** `wilson(k, n, z=1.96)`: the three lines of the lesson (§5). Test it on the local matcher's
  "32/33":

```bash
python3 -c "import bootstrap; print(bootstrap.wilson(32, 33))"
```

You should get about (0.847, 0.995).

- **TODO 10** `coverage(trials, n, rho, block, B, seed)`: does a "95 %" interval really contain the
  truth 95 % of the time? `make_errors(rng, n, rho)` (below the line) simulates a flight of n errors
  from a 2-D Gaussian with σ = 10 m per axis, whose true median is known exactly
  (`TRUE_MEDIAN` = 1.1774 × 10 m). With `rho = 0.9`, each second keeps 90 % of the previous error, like
  a real vision source. For each trial: make a flight, compute its CI of the median with
  `seed=1000 + t`, and count whether `covers(lo, hi, TRUE_MEDIAN)`.

```bash
python3 bootstrap.py --coverage
```

It takes about a minute and writes `coverage.json` with four cases. Expected shape: independent
errors give about 95 %; correlated errors with the iid bootstrap give **much less**; blocks of 10 s
help but do not reach 95 % (n_eff ≈ 3 — see the lesson).

> [!TASK]
> Complete TODO 7–10. "Done" means: `bootstrap_ci` reproduces the demo interval and makes block
> intervals wider on a trending series; `paired_diff_ci` gives exactly (5, 5) when a = b + 5;
> `wilson(32, 33)` ≈ (0.847, 0.995); `coverage.json` shows the correlation effect; and the three
> `results_flight_*.json` contain your confidence intervals (run `measure.py` again).
> Press **✔ Check my work** — checks 6–11 should be green.

## Step 6 — Is the stated σ honest? (`evaluate_session.py`, 15 min)

On a real flight you will not have a simulator's truth: NAVERA's tool uses GPS as the truth for
vision, in a recorded ROS 2 bag (shadow mode). `shadow_bag/` is a small bag in that format,
**synthesised** from the target flight's true track: a GPS, and a day-vision source that **states
σ = 15 m**. Run the product's own tool on it:

```bash
python3 ~/navera/navera_tools/evaluate_session.py /data/academy/29-measuring/shadow_bag
```

Read the second table, *stated accuracy vs truth*: the share of errors within 1, 2, 3 × the stated σ
(honest: ~39 / 86 / 99 %), and the σ that **would** be honest (p86 / 2). The bag was made with a true
error of 22 m per axis: how close is the tool's "honest sigma"?

> [!TASK]
> Answer the eight questions of [answers.py](file:./answers.py) from your results, `coverage.json` and
> the tool's output. Press **✔ Check my work** — check 13.

## Step 7 — Write the report (30–45 min)

Fill in [report.md](file:./report.md). It is the kind of short technical note an engineer attaches to
a pull request or a validation document: what was measured, how, the table, whether the difference
is real, the limits of validity, and a conclusion.

A good conclusion says **what** is better, **by how much** (with a CI), **compared with what**, on
**how much data**, measured **where** — and what it does **not** prove. Avoid "accurate", "robust",
"works well" without a number.

> [!TASK]
> Complete `report.md`: no "(fill in …)" paragraph and no `(m)`, `(%)`, `(s)`, `[lo, hi]` cell left;
> the table filled with your numbers (rounded to the metre); "Is the difference real?" (40+ words,
> says whether each CI of the difference contains 0), "Validity: simulation vs field" (60+ words) and
> "Conclusion" (100+ words). The report must name the baseline, the confidence interval and
> availability, and say that the flights are simulated over Sousse. Press **✔ Check my work** —
> all 15 checks should be green.

## Going further (optional)

- **Your own flight.** If you recorded `flight.csv` in lesson 28, run
  `python3 measure.py ~/lessons/28-simulator/flight.csv`. Same numbers as the sample? Why not exactly?
  Would a CI computed on your flight cover the sample's CEP50?
- **A fairer baseline.** "Repeat the last position" ignores that the drone was moving. Write
  `baseline_dead_reckoning(rows)`: continue the last GPS velocity (from the last two GPS fixes) in a
  straight line. Does the target-profile vision still beat it? Which baseline would you publish, and
  why must you publish the harder one?
- **How many seconds of jamming do you need?** With `make_errors` and `rho = 0.9`, find the n for which
  the block-bootstrap CI of the median is narrower than ±10 %. Translate into minutes of flight for a
  field campaign over Wahiba Sands.
- **Rule of three.** Simulate 0 failures in n trials for a true failure rate of 1 %: how often do you
  see 0 failures with n = 33? With n = 300?
