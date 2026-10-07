# Lab 4 — The flight-test analyst

**Goal:** clean a messy flight-test log of four flights, compute per-flight statistics with pandas,
distances and speeds with vectorised NumPy, find every GPS outage with run-length logic, compare the
noise of GPS and day vision, draw two figures, and write a short test report.
**Time:** about 4–5 hours (pandas is new for most students: take your time in Step 3).

Your files (already open): [flight_analysis.py](file:./flight_analysis.py) (TODO 1–9),
[campaign.csv](file:./campaign.csv) (the data: 1556 rows, synthetic, four flights near Sousse, Tunisia) and
[report.md](file:./report.md).

> [!NOTE]
> `flight_analysis.py` imports pandas, NumPy and matplotlib at the top. Importing them takes 1–3 s on
> the Jetson: a short pause before each run is normal.

## Step 1 — Look at the data with the shell

Before any code, look at the raw file (lesson 2):

```bash
head -n 4 campaign.csv
```

```bash
wc -l campaign.csv
```

`1557` lines: a header and 1556 rows. How many rows say that no source had a position?

```bash
grep -c NO_FIX campaign.csv
```

And one of those lines — note the two empty cells for `lat` and `lon`:

```bash
grep NO_FIX campaign.csv | head -n 2
```

## Step 2 — The csv module, and its limits

Count the rows per flight with `csv.DictReader` and a dict (lesson 3 patterns):

```bash
python3 -c "
import csv
with open('campaign.csv', newline='') as f:
    rows = list(csv.DictReader(f))
counts = {}
for r in rows:
    counts[r['flight_id']] = counts.get(r['flight_id'], 0) + 1
print(len(rows), counts)
print(rows[0]['alt_m'], type(rows[0]['alt_m']))
"
```

Every value is a string. Now try to convert all the latitudes:

```bash
python3 -c "
import csv
with open('campaign.csv', newline='') as f:
    lats = [float(r['lat']) for r in csv.DictReader(f)]
"
```

`ValueError: could not convert string to float: ''` — an empty cell. pandas handles this for you.

## Step 3 — Explore with pandas

Start the interpreter:

```bash
python3
```

and type these lines one by one. Before each, predict what you will see:

```python
import pandas as pd
df = pd.read_csv("campaign.csv")
df.shape
df.dtypes
df.isna().sum()
df.duplicated().sum()
df[df.duplicated(keep=False)]
df.describe().round(1)
df[(df["lat"] == 0) & (df["lon"] == 0)]
df["state"].value_counts()
df.groupby("flight_id")["alt_m"].max()
exit()
```

Three facts to note for the report: there are **3 duplicate rows**; `describe()` shows a maximum
altitude of **9999 m** (impossible for these drones); one row sits at **(0°, 0°)** — "Null Island",
in the Gulf of Guinea, the classic value of a receiver that outputs zeros instead of nothing.

## Step 4 — Clean (TODO 1)

> [!TASK]
> **TODO 1** `clean(df)` returns a **new** DataFrame: without exact duplicates, without the glitch
> rows (`lat == 0` and `lon == 0`, or `alt_m` outside `[ALT_MIN_M, ALT_MAX_M]`), **keeping** the
> NO_FIX rows with an empty position, sorted by `flight_id` then `time_s`, index renumbered from 0.

```bash
python3 -c "from flight_analysis import *; df = clean(load_log('campaign.csv')); print(len(df), df['alt_m'].max(), df['lat'].isna().sum(), list(df.index[:3]))"
```

Expected: `1551 251.5 31 [0, 1, 2]`. If you get 1520, you dropped the NO_FIX rows too: a test of
`lat == 0` is False for NaN, but `dropna()` removes them.

## Step 5 — Distances and speeds (TODO 2–3)

> [!TASK]
> - **TODO 2** `haversine_m(lat1, lon1, lat2, lon2)`: the formula of the course with NumPy
>   functions, so that it works on numbers, arrays and Series (NaN gives NaN).
> - **TODO 3** `add_motion(df)`: a copy of `df` with `dt_s`, `step_m` and `gs_mps`, computed
>   **within each flight** (`groupby("flight_id")` then `.shift()`).

```bash
python3 -c "from flight_analysis import haversine_m; print(haversine_m(51.507, -0.128, 48.857, 2.352))"
```

Expected: `343479.76…` m (London–Paris, the worked example of the course). Then:

```bash
python3 -c "from flight_analysis import *; df = add_motion(clean(load_log('campaign.csv'))); print(df[['flight_id', 'time_s', 'dt_s', 'step_m', 'gs_mps']].iloc[[0, 1, 2, 361, 362]])"
```

Rows 0 and 361 are the first rows of two flights: their `dt_s` and `step_m` must be `NaN`. If row 361
has a step of hundreds of kilometres, your `shift()` crossed from one flight into the next.

## Step 6 — One line per flight (TODO 4)

> [!TASK]
> **TODO 4** `flight_summary(df)`: one row per flight (index `flight_id`) with the columns
> `rows`, `duration_s`, `distance_km`, `max_alt_m`, `mean_speed_mps` (the logged speed) and
> `min_battery_pct`. Use one `groupby(...).agg(...)` with named aggregations.
> `duration_s` is the **last `time_s` minus the first `time_s`** of the flight (no `+ Δt`).

```bash
python3 -c "from flight_analysis import *; print(flight_summary(add_motion(clean(load_log('campaign.csv')))).round(2).to_string())"
```

The `grid_survey` flight should show `13.03` km in `720` s.

## Step 7 — Outages (TODO 5–6)

> [!TASK]
> - **TODO 5** `outage_runs(gps_valid)`: the list of `(start, stop)` pairs (stop excluded) of the
>   runs of 0, **without a Python loop over the rows** (pad, `np.diff`, `np.flatnonzero`).
> - **TODO 6** `outage_table(df, dt_s=DT_S)`: per flight, `n_outages`, `longest_outage_s`,
>   `total_outage_s`; a run lasts `time_s[stop−1] − time_s[start] + dt_s`; a flight without outage
>   has 0 everywhere.

```bash
python3 -c "from flight_analysis import outage_runs; print(outage_runs([1, 0, 0, 1, 0]), outage_runs([1, 1]), outage_runs([0, 0, 1, 0, 0, 0]))"
```

Expected: `[(1, 3), (4, 5)] [] [(0, 2), (3, 6)]` — the last outage reaches the end of the list.

> [!NOTE]
> **Python note.** For TODO 6, collect one dict per flight in a dict
> `rows[fid] = {"n_outages": …, "longest_outage_s": …, "total_outage_s": …}`, then build the table
> with `pd.DataFrame.from_dict(rows, orient="index")` (course, section 2, "A table from a dict").
> `max(durations, default=0.0)` gives `0.0` for an empty list instead of an error.

```bash
python3 -c "from flight_analysis import *; print(outage_table(add_motion(clean(load_log('campaign.csv')))))"
```

## Step 8 — What NAVERA reported, and how noisy each source is (TODO 7–8)

> [!TASK]
> - **TODO 7** `state_shares(df)`: % of rows in each state per flight, columns exactly
>   `FIX, DEGRADED, NO_FIX` (0.0 when a state never occurs).
> - **TODO 8** `speed_error(df)`: `|gs_mps − speed_mps|` per row, rows with NaN dropped, grouped
>   by `source`: columns `median_mps` and `p95_mps`.

> [!NOTE]
> **Python note.** `"median"` can be written as a name inside `.agg()`, but the 95th percentile
> needs a parameter: give a `lambda`, as in the course (section 2):
> `p95_mps=("err", lambda x: x.quantile(0.95))`.

```bash
python3 -c "from flight_analysis import *; df = add_motion(clean(load_log('campaign.csv'))); print(state_shares(df).round(1)); print(speed_error(df).round(2))"
```

Compare the two lines of `speed_error` with the prediction of the course (section 3: about 1.1 m/s
of noise for GPS, 4.2 m/s for day vision). Are you in the right ratio?

## Step 9 — Figures and results (TODO 9)

> [!TASK]
> **TODO 9** `plot_altitude(df, flight_id, path)`: altitude against time for one flight, every
> outage shaded with `ax.axvspan`, axis labels with units, a title with the flight id, saved to
> `path`.

Now run the whole analysis. `main()` (already written) calls your functions, writes
**results.json**, **tracks.png** (all flights, coloured by source, with the helper `plot_tracks()`)
and **altitude.png** (the flight with the longest outage):

```bash
python3 flight_analysis.py
```

```bash
cat results.json
```

Open [tracks.png](file:./tracks.png) and [altitude.png](file:./altitude.png) in the editor (click
the file in the list if the view does not refresh). In tracks.png, the orange parts were flown on day
vision. Look at the `sousse_port` panel: there is a **hole** in the track — where is it, and which state
explains it?

## Step 10 — The report

> [!TASK]
> Fill [report.md](file:./report.md): keep the four `##` headings (Data cleaning, Flights,
> Outages, Speed check), replace every "(write here)" with 2–5 sentences of your own (at least 150
> words in total). The check looks for: how many rows cleaning removed (or kept), the flight with
> the longest outage **and** its duration in seconds, and the median speed errors of GPS and of day
> vision in m/s with 2 decimals.

Explain, not only list: why NO_FIX rows must be kept; why one flight's distance is probably too
large and another's too small; why the vision speeds are noisier.

## Step 11 — Check your work

Press **✔ Check my work**. The checker tests each function on small invented tables first (an
outage that lasts until the last row, a flight without outage, empty cells, two flights mixed),
then on the campaign, then runs `flight_analysis.py` and reads results.json and report.md. If a
check fails on a small table, its message describes the table: rebuild it in `python3` and test.

## Going further (optional)

- **How wrong is the flat Earth across Europe?** Write `enu_from_latlon(lat, lon, lat0, lon0)` with
  the flat-Earth formulas of the course (section 3, with `np.radians` and `np.cos`, so that it
  accepts numbers **and** arrays). With London (51.507, −0.128) as the reference, compute
  `np.hypot(east, north)` for Paris (48.857, 2.352), Amsterdam (52.370, 4.895), Edinburgh
  (55.953, −3.188) and Madrid (40.417, −3.704) in **one** call on arrays, and compare with your
  `haversine_m()`. You should find about −0.72 %, +0.91 %, +0.78 % and −0.44 % (−2.5, +3.3, +4.2 and
  −5.6 km). Why is the error positive for some cities and negative for others? (Hint: which
  latitude does `cos φ0` use?) Up to what distance would you trust the flat formula?

- **Smoother speeds.** Compute a speed over a 10 s window instead of 2 s
  (`groupby(...)["lat"].shift(5)`). How much smaller is the day-vision error? This is the idea behind
  NAVERA's 20 s velocity fit in `navera_common/track.py`.
- **Distance without the noise.** Recompute the `sahel_hills` distance using only GPS rows. How much of the
  "extra" kilometres came from the vision noise?
- **Battery model.** Fit a straight line to `battery_pct` against `time_s` for each flight
  (`np.polyfit(t, b, 1)`, dropping NaN first). What is the consumption in % per minute, and how
  long could each flight have lasted down to a 20 % reserve?
