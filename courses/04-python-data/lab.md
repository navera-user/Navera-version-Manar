# Lab 4 — The flight-test analyst

**Goal:** write NAVERA Lite's flight-log toolkit (`navera_lite/logbook.py`, TODO 1–7), use it on a messy
four-flight campaign, find the clock and the column that lie, measure how noisy each position source is,
and write the test report.
**Time:** 2 h 30 to 5 h (a strong programmer: about 2 h 15; 5 h or a little more if pandas and numpy are new
to you: plan the two sessions, and finish at home).
**Fast track:** if you know pandas, skip every 🧰 box and every "Stuck?" box; then do "Going further".

Your files (📝 Code tab): [navera_lite/logbook.py](file:./navera_lite/logbook.py) (**your code**: seven
functions, `TODO 1–7`; the given functions are finished), [answers.py](file:./answers.py)
(predictions, numbers, explanations, and your corrections), [report.md](file:./report.md) (the test report)
and [run_logbook.py](file:./run_logbook.py) (runs your functions on the campaign and draws them; you don't
edit it). The data is read only, in `/data/academy/04-python-data/`: `campaign.csv` (the logger's file),
`flight_sheet.csv` (the test director's sheet, times in UTC) and `README.txt`.

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | nothing: you read what the raw log claims |
| §1 A log is a table | Step 1 | nothing: you look at the data, in the shell and in pandas |
| §2 Cleaning | Step 2 | `clean` |
| §3 groupby | Step 3 | `add_motion` |
| §4 Outages | Steps 4–5 | `outage_runs`, `outage_table`, `state_shares` |
| §6 Systematic errors | Step 6 | a short script of your own, and two corrections |
| §5 Noise and robust statistics | Step 7 | `noise_by_source` |
| §6 again, on your own | Step 8 (challenge) | `unit_suspects` |
| all | Step 9 | the report |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` is written **before** you run the step. It is never marked
> right or wrong. pandas takes 1–3 s to import on this computer: a short pause before each run is normal.

## Session 1 — Clean & measure (about 1 h 30 to 2 h 30)

## Step 0 — What the raw log claims

```bash
python3 run_logbook.py naive
```

The runner reads the campaign as it is, takes "the previous row" for every row, and adds up distances. Open
`out/naive.png` in the 📝 Code tab. A small drone, ten minutes per flight: which of these numbers could be
true? Keep your doubts in mind. By Step 6 you will have found every reason.

## Step 1 — Look before you compute

First the shell (mission 02). The data folder is read only: you can look, not change.

```bash
cd /data/academy/04-python-data && head -n 3 campaign.csv && wc -l campaign.csv && cat flight_sheet.csv; cd -
```

**Mini-challenge (no pandas).** Write two pipelines yourself, with `cut`, `sort`, `uniq -c`, `grep` and
`wc`: (1) which flight has the most rows, and how many; (2) how many rows have an **empty** `lat` (the
3rd field)? Run them in the terminal.

<details><summary>Stuck? Hints</summary>

1. `cut -d, -f1 FILE` keeps the first field of every line; `sort | uniq -c` counts equal lines;
   `sort -rn | head -n 2` puts the biggest count first (the header line `flight_id` is counted once too:
   ignore it).
2. An empty field is an empty line after `cut`: `grep -c '^$'` counts the empty lines (`^$` = start, then
   end, nothing between).
</details>

Now pandas, in the interactive interpreter. Start it, then type the lines one by one (not the `>>>`),
and read each answer before the next line:

```bash
python3
```

```python
>>> import pandas as pd
>>> df = pd.read_csv("/data/academy/04-python-data/campaign.csv")
>>> df.shape
>>> df.dtypes
>>> df.isna().sum()
>>> df.duplicated().sum()
>>> df.describe().round(1)
>>> df["state"].value_counts()
>>> len(df) - len(df.dropna())
>>> exit()
```

> [!TASK]
> Write `ROWS_RAW`, `MOST_ROWS_FLIGHT`, `EMPTY_LAT_ROWS` and `DROPNA_ROWS_LOST` in answers.py. Then, **before** Step 2:
> `PREDICT_CLEAN`: how many rows will the three rules of the lesson's §2 remove (duplicates, (0, 0),
> impossible altitude), and which rule removes most? (`describe()` already gave you a clue.)

## Step 2 — Clean (TODO 1)

**TODO 1** `clean(df)` in [navera_lite/logbook.py](file:./navera_lite/logbook.py): the three rules, in
order, each counted (lesson §2; its docstring has the exact rules and an example). Return **two** things:
`return out, removed`.

<details><summary>🧰 pandas tools for TODO 1 (on another table)</summary>

```python
t = pd.DataFrame({"x": [1, 1, 5, 7], "y": [0.0, 0.0, None, 2.0]})
dup = t.duplicated()            # [False, True, False, False]: row 1 is a copy of row 0
t = t[~dup]                     # keep the rows that are NOT copies (a new DataFrame)
big = t["x"] > 6                # [False, False, True] — the empty y is not a problem here
int(big.sum())                  # 1: True counts as 1 (int() makes a plain Python number)
t = t.sort_values(["x"]).reset_index(drop=True)
counts = {"copies": int(dup.sum()), "big": int(big.sum())}      # a dict of counts
```
</details>

```bash
python3 run_logbook.py test
```

The first line must be ✔. Then on the campaign:

```bash
python3 run_logbook.py clean
```

<details><summary>Stuck? Hints, one at a time</summary>

1. One mask per rule, computed on the table the previous rule left: the duplicate mask on `df`, the
   (0, 0) mask on what remains, the altitude mask on what remains after that.
2. Keep rows with `out = out[~mask]` (the `~` keeps what the mask does NOT mark).
3. The runner says fewer than 31 empty positions kept? You used `dropna()`, or wrote a rule as "keep where
   …", which is False for NaN. Write each rule as "remove where …" and keep `~mask`.
4. The check says null_island = 2 when the (0, 0) row is written twice: you computed that mask on `df`
   instead of on what the duplicate rule left.
5. The runner says "a DataFrame, not two things": you returned only the DataFrame; return `out, removed`.
</details>

> [!TASK]
> `EXPLAIN_KEEP_NOFIX`: why must the NO_FIX rows stay in the clean log? Say what would happen to the
> outages if they were dropped.

## Step 3 — Speeds, one flight at a time (TODO 2)

**TODO 2** `add_motion(df)`: the three new columns of lesson §3, from the previous row **of the same
flight**. Use the given `haversine_m` for the distance; it takes whole columns.

<details><summary>🧰 groupby and shift (on another table)</summary>

```python
t = pd.DataFrame({"team": ["x", "x", "y", "y"], "score": [3, 5, 10, 11]})
g = t.groupby("team")
t["before"] = g["score"].shift()        # [NaN, 3.0, NaN, 10.0]: the previous row of the SAME team
t["gain"] = t["score"] - t["before"]    # [NaN, 2.0, NaN, 1.0]
out = t.copy()                          # work on a copy when a function must not change its input
```
</details>

```bash
python3 run_logbook.py test
```

```bash
python3 run_logbook.py motion
```

Read the first two rows of each flight: `dt_s` must be NaN on the first one and 2.0 on the second. Then
the fastest step of each flight. Is any of them possible for a drone whose top speed is 30 m/s (mission
03's `VEHICLES` table)? Which source made them?

<details><summary>Stuck? Hints</summary>

1. Three lines: `out["dt_s"] = …`, `out["step_m"] = haversine_m(…)`, `out["pos_speed_mps"] = …`, on
   `out = df.copy()`.
2. The previous position is `g["lat"].shift()` and `g["lon"].shift()`, with `g = out.groupby("flight_id")`.
3. A first row of a flight with `dt_s` of thousands of seconds, or negative: your `shift()` is not inside
   the groupby (`out["time_s"].shift()` crosses from one flight to the next).
4. The runner says the DataFrame has no `dt_s`: you added the columns to `out` but returned `df` (or the
   reverse).
</details>

> [!TASK]
> `FASTEST_SOURCE`: the source of those fastest steps (`"gps"`, `"day"` or `"none"`). Keep them in mind
> for Step 7: they are not removed by any cleaning rule, and they should not be.

## Step 4 — Outages as runs (TODO 3)

> [!TASK]
> **Predict** (`PREDICT_RUNS`): what will `outage_runs([0, 0, 1, 1, 0, 1, 0, 0, 0])` return? Write it
> before you write the code.

**TODO 3** `outage_runs(valid)`: lesson §4. A loop is allowed; the padded `np.diff` of the lesson is
shorter. Test it on your own prediction too:
`python3 -c "from navera_lite.logbook import outage_runs; print(outage_runs([0, 0, 1, 1, 0, 1, 0, 0, 0]))"`.

<details><summary>🧰 numpy tools for TODO 3 (on other numbers)</summary>

```python
import numpy as np
a = np.asarray([4, 4, 9, 9, 9, 4])           # FIRST make an array: a plain list == 9 is ONE False, not a mask
m = (a == 9).astype(int)                     # [0 0 1 1 1 0]: True/False become 1/0
p = np.concatenate([[0], m, [0]])            # [0 0 0 1 1 1 0 0]: one 0 added at each end
np.diff(p)                                   # [0 0 1 0 0 -1 0]: each element minus the one before
np.flatnonzero(np.diff(p) == 1)              # [2]: where the condition is True
list(zip([2, 7], [5, 9]))                    # [(2, 5), (7, 9)]
```
</details>

```bash
python3 run_logbook.py test
```

<details><summary>Stuck? Hints</summary>

1. Starts are where the padded diff is +1, stops where it is −1; there are as many of each.
2. A run at the very start or the very end is missing? You forgot the padding at that end.
3. Stops one too far (`(4, 6)` instead of `(4, 5)`)? A stop is the first row AFTER the run: read the −1
   positions as they are, without +1.
4. A loop version misses the last outage? A run still open after the loop must be closed at
   `len(valid)`.
5. `AttributeError: 'bool' object has no attribute 'astype'`: `valid` can be a plain list, and
   `[1, 0] == 0` is one `False`, not a mask. Start with `v = np.asarray(valid)`.
</details>

> [!TIP] 🏅 End of session 1 — Log keeper
> Press **✔ Check my work** now. When every session-1 check passes (TODO 1–3 and Steps 1–4: checks 1–5;
> the other ✘ lines are session 2), you earn the **Log keeper** badge on your home page.

## Session 2 — Detect & report (about 1 h 45 to 2 h 45)

## Step 5 — Outages and states per flight (TODO 4–5)

**TODO 4** `outage_table(df, dt_s=DT_S)`: per flight, with your `outage_runs` (lesson §4 durations, with
`+ dt_s`). **TODO 5** `state_shares(df)`: per flight, % of rows in each state, as a dict of dicts.

<details><summary>🧰 a table from a dict, shares, and missing keys (on other data)</summary>

```python
rows = {"x": {"n": 3, "worst_s": 8.0}, "y": {"n": 0, "worst_s": 0.0}}
pd.DataFrame.from_dict(rows, orient="index")      # one row per outer key: index x, y; columns n, worst_s
max([], default=0.0)                              # 0.0 instead of an error on an empty list
s = pd.Series(["red", "red", "blue", "red"])
share = s.value_counts(normalize=True) * 100      # red 75.0, blue 25.0 (green is absent)
float(share.get("green", 0.0))                    # 0.0: .get gives a default for a missing key
for fid, f in pd.DataFrame({"team": ["x", "y"]}).groupby("team"): ...   # f = the rows of one group
```
</details>

```bash
python3 run_logbook.py test
```

```bash
python3 run_logbook.py outages
```

```bash
python3 run_logbook.py shares
```

Open `out/outages.png`.

<details><summary>Stuck? Hints</summary>

1. TODO 4: loop over `df.groupby("flight_id")`; in each flight, the times as an array
   (`f["time_s"].to_numpy()`) and the runs of `f["gps_valid"]`; one dict per flight; then `from_dict`.
2. Indices from `outage_runs` are positions **inside the flight**: use them on the flight's own array,
   not on `df`.
3. Every duration 2 s too short: you forgot `+ dt_s`. A flight missing from the table: you only add
   flights that have outages; every flight needs a row.
4. TODO 5: the values must be plain floats and the three states must all be keys (use `STATES`).
</details>

Nothing to copy into answers.py here: the numbers go into your report (Step 9). Look at the picture
instead: which outage is longest, and what did the judge report meanwhile?

## Step 6 — The detective

Before any statistic on noise, check that the data means what its labels say (lesson §6). First, the
outages against the jammer's plan (no corrections yet):

```bash
python3 run_logbook.py schedule
```

Some outages look unplanned, and one jamming window shows no outage at all. A broken jammer, and a
mysterious outage? Or a lie in the data? Two independent records can help: the sheet's times, and two
ways of measuring the same speed. Write your own short script `detective.py` (📝 Code tab: new file) that
prints, **per flight**:

1. the first and the last `time_s` of the log, and the take-off and landing of the sheet in seconds;
2. the median of the logged `speed_mps` and the median of `pos_speed_mps` (after `clean` and
   `add_motion`).

<details><summary>🧰 for detective.py: times of day, and two tables side by side</summary>

```python
import pandas as pd
from navera_lite.logbook import load_log, clean, add_motion
pd.set_option("display.width", 200)                             # show every column, no "..."
df, removed = clean(load_log("/data/academy/04-python-data/campaign.csv"))   # clean returns TWO things
df = add_motion(df)
sheet = pd.read_csv("/data/academy/04-python-data/flight_sheet.csv").set_index("flight_id")
pd.to_timedelta(pd.Series(["01:00:30"])).dt.total_seconds()    # [3630.0]: "hh:mm:ss" → seconds of the day
first = df.groupby("flight_id")["time_s"].min()                 # a Series indexed by flight_id
t = pd.DataFrame({"log_first_s": first, "sheet_s": ...})       # Series with the same index line up
print(t.to_string())                                            # the whole table
```

`-3.6e-12` printed for a difference is 0 up to rounding. Run it with `python3 detective.py`.
</details>

<details><summary>Stuck? Hints</summary>

1. Compute `first - takeoff_s` per flight: three flights give 0, one gives a round number. What is
   Tunisia's offset from UTC?
2. Does the drone LITE-2 fly two flights at the same time in the log? Print each flight's first and last
   logged time as `hh:mm:ss` and compare.
3. For the speed, print the ratio of the two medians per flight. 1.00 means "same unit". Which unit gives
   the ratio you see? (Lesson §6 names two.)
4. The correction is what you ADD to `time_s` (a negative number if the log is ahead), and the factor
   that MULTIPLIES `speed_mps` (a number below 1 if the log is too big).
5. Check your corrections: run `schedule` again. Its last lines show each corrected flight's first row
   next to the sheet's take-off (they must be equal) and the corrected speed ratio (it must be close to
   1.00). Still UNPLANNED at a later hour, or a ratio far from 1? The sign or the factor is upside down.
</details>

> [!TASK]
> Write `CLOCK_FIX_S` and `SPEED_FACTOR` in answers.py (dicts, one entry each), and
> `EXPLAIN_DETECTIVE`: your evidence for each, with numbers. Then run `schedule` again: the runner now
> applies your corrections. Write `UNPLANNED_FLIGHT` and `UNPLANNED_START_UTC`.

```bash
python3 run_logbook.py schedule
```

## Step 7 — How noisy is each source? (TODO 6)

The day-vision positions of this campaign have a σ of about **6 m** per axis; the GPS positions about
**1.5 m**; the autopilot's logged speed has its own noise of about **0.3 m/s**. One row every 2 s.

> [!TASK]
> **Predict** (`PREDICT_NOISE`): with the lesson's §5 formula, what σ of the speed error do you expect
> for gps and for day vision?

<details><summary>🧰 Variance, σ, and which σ</summary>

For 2, 4, 4, 4, 5, 5, 7, 9: mean 5, variance = mean of (x − 5)² = 4, σ = 2 (in the unit of the data).
pandas' `.std()` divides by n − 1 (**ddof = 1**: 2.14 here); numpy's `np.std` divides by n (2.0). Say which
one you use. Independent errors add their **variances**: σ = 3 and σ = 4 together give 5.
</details>

**TODO 6** `noise_by_source(df)`: the least guided of the scaffolded TODOs. Read its docstring, compute the
lesson's worked example (§5, the nine errors) by hand once more, then write it. Its example in the
docstring is your first test.

```bash
python3 run_logbook.py test
```

```bash
python3 run_logbook.py noise
```

Open `out/noise.png`. Compare the two tables: without and with your corrections.

<details><summary>Stuck? Hints</summary>

1. Build one small DataFrame with two columns, `source` and `err`, then `.dropna()` it: only rows where
   both speeds are known remain.
2. One row per source: the outage-table pattern of TODO 4 (a loop over a groupby, a dict per group,
   `from_dict`) works here too.
3. MAD: the median of `(e - e.median()).abs()`, times `MAD_TO_SIGMA`. p95: `np.percentile(e.abs(), 95)`
   (or `e.abs().quantile(0.95)`: the same linear rule).
4. std 11.19 expected but you get 10.36 on the docstring example: you used numpy's `np.std` (ddof 0);
   pandas' `e.std()` is ddof 1. 1.0 instead of 1.483 for mad_sigma: you forgot `MAD_TO_SIGMA`.
5. A sign the other way (mean −4.714): the error is `pos_speed_mps − speed_mps`, not the reverse.
</details>

> [!TIP]
> Your measured σ will not equal your prediction. With 224 errors, a robust σ scatters by about 7–8 % from
> one campaign to the next (40 other campaigns made the same way give day vision 4.1 ± 0.3 m/s and GPS
> 1.11 ± 0.03 m/s). In the report, say whether your gap is larger than that.

> [!TASK]
> `EXPLAIN_ROBUST`: why is day vision's `std_mps` so much bigger than its `mad_sigma_mps` (look at Step 3),
> which one is "the noise", what must a report add, and what did the median **not** protect you from
> (compare the gps rows of the two tables)?

<details><summary>Read after the run: why is day vision's median error not 0?</summary>

A speed from positions is the LENGTH of a noisy step. Noise along the track makes it longer or shorter
equally, but noise across the track always makes it longer (Pythagoras). On average the step gains about
σ²/(v·Δt) metres, so the speed gains about σ²/(v·Δt²): with σ = 6 m, v = 10 m/s, Δt = 2 s, about +0.9 m/s
(+0.6 at 14 m/s). For GPS (σ = 1.5 m) it is about +0.03 m/s: invisible. This is a small **systematic**
error of the method itself, and a reason to compute speeds over longer intervals.
</details>

## Step 8 — Challenge: automate the detective (TODO 7)

No 🧰 box and no step-by-step hints this time: the docstring of **TODO 7** `unit_suspects(df, tol=0.05)` is
the whole specification. It flags the flights whose logged speed is in another unit, so that the next
campaign's mislabelled column is caught by code, not by luck. Write it, test it on its docstring example,
then run it on the campaign:

```bash
python3 run_logbook.py test
```

```bash
python3 run_logbook.py units
```

The check tests it on flights it has never seen (one in knots, one with a wild value, one almost right, and
another tolerance).

<details><summary>Only if you are stuck after 20 minutes</summary>

1. Per flight (a loop over a groupby, as in TODO 4): the median of each speed column, then their ratio.
2. "Within tol of r" is relative: `abs(ratio / r - 1) <= tol`. Test "looks right" (r = 1) first, then
   km/h, then knots, otherwise "?".
</details>

## Step 9 — The report

```bash
python3 run_logbook.py report
```

It writes `results.json` with everything, corrections applied (open it in the 📝 Code tab). Now fill
[report.md](file:./report.md): keep the five `##` headings and replace every "(write here)", at least 200
words in all. The check looks for the rows left or removed, both corrections with their numbers, the
longest outage (flight and seconds), the unplanned outage (flight and UTC time), and the two robust σ
(`mad_sigma_mps`, with your corrections) with two decimals. Explain, do not only list: a reader must know
what to trust.

## Step 10 — Check, then look back

Press **✔ Check my work**: it also tests your functions on small tables they have never seen (two flights
mixed, an outage until the last row, a flight with no outage, empty cells). When every check passes you
earn the **Flight-test analyst** badge. Then look back, without the lesson:

1. Which defect of the data would have changed your conclusions most if you had missed it, and why?
2. Which of your predictions was the most wrong?
3. The mission brief's replay frames: which check of this lab would have caught "labels that do not
   match the pictures", and which would not?

## Going further (optional)

- **Two percentile rules.** Recompute day vision's p95 of |error| with
  `np.percentile(x, 95, method="nearest")` (the nearest-rank rule NAVERA's evaluation uses, in words in
  the lesson). How far is it from the linear one, on 224 values? And on the 9 errors of the lesson?
- **Smoother speeds.** Compute the speed over 10 s instead of 2 s (`shift(5)` inside the groupby). By how
  much does the day-vision noise drop, and does it follow the lesson's formula with Δt = 10 s?
- **Distance without the jumps.** `sahel_hills`' total `step_m`, then the same without the steps longer than
  100 m. How many metres did the vision jumps add? Would the median step have been fooled?
- **Battery.** Fit a line to `battery_pct` against time per flight (`np.polyfit(t, b, 1)`, NaN dropped
  first). Consumption in % per minute? How long could each flight have lasted down to a 20 % reserve
  (mission 03's rule)?
