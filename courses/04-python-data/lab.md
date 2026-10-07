# Lab 4 — The flight analyst

**Goal:** load a flight log with Python and answer the engineer's questions: number of rows,
highest altitude, average speed, GPS outages, a summary file and two pictures of the flight.
**Time:** about 1 hour 15 minutes.

Your files: [flight_log.csv](file:./flight_log.csv) (the data) and
[flight_log.py](file:./flight_log.py) (your program, with 8 TODOs).

## Step 1 — Look at the data with the terminal

Before writing any code, look at the file. You know the tools from lesson 2:

```bash
head -n 5 flight_log.csv
```

```bash
wc -l flight_log.csv
```

`wc` says 279 lines: 1 header + 278 rows. Which rows have no GPS? `grep` can tell — the rows from
day vision end with `day_vision`:

```bash
grep -c day_vision flight_log.csv
```

Remember that number: your Python program must find the same one.

## Step 2 — Lists and dicts in interactive mode

Start Python:

```bash
python3
```

Try these lines one by one, and predict each answer before pressing `Enter`:

```python
alts = [0.0, 8.0, 16.0, 120.5, 151.4]
alts[0]
alts[-1]
len(alts)
alts[1:3]
sum(alts) / len(alts)
max(alts)
row = {"time_s": 40.0, "alt_m": 121.3, "source": "gps"}
row["alt_m"]
row["alt_m"] + 10
row.get("battery_pct", "unknown")
for a in alts: print(a, "#" * round(a / 10))

exit()
```

(After the `for` line, press `Enter` twice: the empty line tells Python the loop is finished.)

## Step 3 — Read the CSV (TODO 1)

Open [flight_log.py](file:./flight_log.py) and run it as it is:

```bash
python3 flight_log.py
```

It says `rows read : 0` — `read_log()` reads the file but throws every line away (`pass` does
nothing). Look at the loop:

```python
        for line in csv.DictReader(f):
            # TODO 1: build a new dict with the converted values and append it to rows
            pass
```

`line` is a dict of **strings**. Replace `pass` by code that builds a new dict with the **same keys**
and **converted** values, and appends it to `rows`. Here is the start — finish it with the other
columns (`lat`, `lon`, `speed_mps`, `battery_pct`):

```python
            row = {
                "time_s": float(line["time_s"]),
                "alt_m": float(line["alt_m"]),
                "gps_valid": int(line["gps_valid"]),
                "source": line["source"],
            }
            rows.append(row)
```

Watch the indentation: these lines are inside the `for` (12 spaces).

```bash
python3 flight_log.py
```

You should see `rows read : 278` and the first row printed as a dict, with **numbers** (no quotes
around `0.0`) and the text `'gps'`.

> [!TASK]
> **TODO 1** — `read_log(path)` returns a list of 278 dicts; `time_s`, `lat`, `lon`, `alt_m`,
> `speed_mps` and `battery_pct` are floats, `gps_valid` is an int, `source` stays a string. It must
> read the file given in `path` (the checker also gives it another file).

## Step 4 — The questions (TODO 2–6)

Now each function receives `rows`, your list of dicts. Use the patterns of the course: **best so
far**, **accumulator**, **counter**.

> [!TASK]
> - **TODO 2** `max_altitude(rows)` — the highest `alt_m`. Write it with a `for` loop and an `if`
>   (start from the first row, not from 0).
> - **TODO 3** `average_speed(rows)` — the average of `speed_mps`.
> - **TODO 4** `count_gps_lost(rows)` — how many rows have `gps_valid == 0`.
> - **TODO 5** `longest_outage_rows(rows)` — the longest run of consecutive `0`s (look at the
>   picture with `run` and `best` in the course).
> - **TODO 6** `count_by_source(rows)` — a dict `{source: number of rows}`.

Run after each function:

```bash
python3 flight_log.py
```

Compare `rows without GPS` with the `grep -c` of step 1: they must be equal. And check `max_altitude`
against Python's own `max()` — in interactive mode, import your file:

```bash
python3
```

```python
from flight_log import *
rows = read_log("flight_log.csv")
max_altitude(rows), max([r["alt_m"] for r in rows])
average_speed(rows), sum([r["speed_mps"] for r in rows]) / len(rows)
exit()
```

Both numbers of each line must be the same.

<details><summary>Stuck on TODO 5?</summary>

Write the two variables before the loop, `run = 0` and `best = 0`. In the loop:
if the row has no GPS, `run` grows by 1, and if `run` is now bigger than `best`, `best` takes its
value. Otherwise (GPS OK), `run` goes back to 0. After the loop, return `best`.
</details>

The longest outage is a number of rows. One row is written every 2 seconds, so multiply by 2 to
get seconds. How long did the drone fly **without GPS**, in one go, relying on day vision only?

## Step 5 — Write the summary file (TODO 7)

The engineer wants a small text file she can paste in her test report.

> [!TASK]
> **TODO 7** — `write_summary(rows, path)` writes **exactly** the 6 lines shown in its docstring
> (`rows: …`, `duration_s: …`, `max_altitude_m: …`, `average_speed_mps: …`, `gps_lost_rows: …`,
> `longest_outage_rows: …`), floats with 1 decimal (`:.1f`), each line ending with `"\n"`.
> Call your own functions inside it.

```bash
python3 flight_log.py
```

```bash
cat summary.txt
```

## Step 6 — Pictures of the flight (TODO 8)

First, a chart made only of text.

> [!TASK]
> **TODO 8** — `ascii_altitude(rows, every=10)` returns a **list of strings**, one for every 10th row:
> the time on 5 characters (`:5.0f`), then `" s |"`, then one `#` per 10 m of altitude
> (`round(alt_m / 10)` of them). Look at the examples in its docstring.

```bash
python3 flight_log.py
```

You should see the take-off, the cruise at 120 m, the higher leg at 150 m and the landing, drawn
with `#`.

Now the real picture: the end of the program calls `plot_track()` (already written, below the
line), which saves **track.png**. Open [track.png](file:./track.png) in the editor (click the
file in the list on the left if it does not refresh). Blue dots: GPS. Red dots: GPS lost — the
position then came from day vision, which is why those red parts are a bit more wobbly.

## Step 7 — Check your work

Press **✔ Check my work**. The checker tests your functions on the lab's log **and** on small
invented flights (negative altitudes, an outage at the very end, a source called `night_vision`…).
If one fails, its message gives the input it used: try the same case in interactive mode.

## Going further (optional)

- Add `min_battery(rows)` and a 7th line `min_battery_pct: …` to the summary (the checker only
  looks at the first 6 lines… so check it yourself!).
- Draw the **altitude over time** with matplotlib into `altitude.png`, following the example in the
  course (times on the x axis, altitudes on the y axis). Colour the GPS-lost rows in red with a
  second `plt.scatter(...)`.
- Read NAVERA's real thermal log, where missing GPS is an **empty** cell, and count the frames
  without GPS. `float("")` crashes: test the cell first (`if line["lat"] == "":`).
  The file is `~/navera/camera_pkg/camera_pkg/data/thermal/flight_ready.csv`.
