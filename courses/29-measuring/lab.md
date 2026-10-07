# Lab 29 — Measure two flights, beat the baseline, write it honestly

**Goal:** compute the error statistics, the availability and the "repeat the last position" baseline
of two recorded simulator flights, plot them, check a source's stated accuracy with NAVERA's own
`evaluate_session.py`, and write a short, honest result.
**Time:** about 1 h 30.

Your files: [measure.py](file:./measure.py) (TODO 1–6), [answers.py](file:./answers.py),
[report.md](file:./report.md) (your result).

The data (`/data/academy/29-measuring/`, read only) was recorded with the mission simulator exactly as
in lesson 28 (`/data/academy/28-simulator/record_sample.sh`): a drone over Sousse at ~15 m/s, GPS
**jammed 60 s**, later **spoofed** 30 s. Two flights, one difference — what replaces GPS:

| File | Vision when GPS is lost | What it represents |
|---|---|---|
| `flight_target.csv` | simulated, *target* profile: 15 m, stated | the accuracy **goal** — not a measured performance |
| `flight_measured.csv` | simulated, *former day vision* profile: ~440 m median, uncertainty unknown | the error **measured** on real frames for the former DINOv2 method |

Both are **simulation only**. The simulator's own error column has been removed: you compute the
errors yourself, from `truth_lat/lon` and `navera_lat/lon`.

## Step 1 — Look at the data

```bash
head -3 /data/academy/29-measuring/flight_target.csv
```

```bash
cut -d, -f2,3,4,5 /data/academy/29-measuring/flight_target.csv | uniq -c
```

The second command counts the seconds spent in each (phase, GPS mode, NAVERA state, source): you see
the whole story of the flight in a dozen lines. Do the same for `flight_measured.csv`: what is
different while the GPS is jammed?

## Step 2 — Errors and statistics (TODO 1–3)

Open [measure.py](file:./measure.py):

- **TODO 1** `errors(rows)`: one `(t, error)` per *en route* row where NAVERA gave a position.
  `haversine_m()` is below the line.
- **TODO 2** `percentile(values, p)`: the nearest-rank rule of `evaluate_session.py` (the course shows
  the two lines).
- **TODO 3** `stats(values)`: count, mean, median (`percentile(…, 50)`), p90 and max.

```bash
python3 measure.py /data/academy/29-measuring/flight_target.csv
```

You get NAVERA's error on the whole flight, while GPS is used, and while GPS is jammed.

## Step 3 — Availability (TODO 4)

`availability(rows, gps_mode=None)`: the percentage of *en route* rows with a usable position (state
`FIX` or `DEGRADED` **and** a position). With `gps_mode="jammed"`, only the jammed rows.

```bash
python3 measure.py /data/academy/29-measuring/flight_target.csv /data/academy/29-measuring/flight_measured.csv
```

## Step 4 — The baseline and the picture (TODO 5–6)

**TODO 5** `baseline_errors(rows)`: what if NAVERA had simply kept saying the last GPS position it had
before the jam? Find the first jammed row, the last NAVERA position given by GPS before it, and for every
jammed *en route* row the distance from the truth to that frozen position.

**TODO 6**: add the baseline to the plot as a red line. Run both flights again:

```bash
python3 measure.py /data/academy/29-measuring/flight_target.csv /data/academy/29-measuring/flight_measured.csv
```

Open [error_flight_target.png](file:./error_flight_target.png) and
[error_flight_measured.png](file:./error_flight_measured.png). The yellow band is the jam. The red
line grows steadily: the drone flies away from the frozen position at ~15 m/s.

> [!QUESTION]
> In `flight_measured`, compare the blue dots and the red line **at the start** of the jam and **at the
> end**. Is the vision method better than doing nothing all the time? What would happen with a jam of
> 10 s? Of 5 minutes?

<details><summary>Think about it</summary>
At the start of a jam the frozen position is still close (the drone has not gone far): a ~440 m method
is <i>worse</i> than doing nothing for the first tens of seconds. It only wins once the drone has
flown farther than its typical error. A method must beat the baseline <b>over the situations that
matter</b>, not on average over one flight.
</details>

> [!TASK]
> Complete TODO 1–6 and run `measure.py` on **both** flights. "Done" means `results_flight_target.json`,
> `results_flight_measured.json` and the two PNG files exist, with the right numbers. Press
> **✔ Check my work**.

## Step 5 — Is the stated accuracy honest? (`evaluate_session.py`)

On a real flight you will not have a simulator's truth: NAVERA's tool uses GPS as the truth for vision,
in a recorded ROS 2 bag (shadow mode). `/data/academy/29-measuring/shadow_bag/` is a small bag in that
format, **synthesised** from the target flight's true track: a GPS, and a day-vision source that
**states σ 15 m**. Run the product's own tool on it:

```bash
python3 ~/navera/navera_tools/evaluate_session.py /data/academy/29-measuring/shadow_bag
```

Read the second table, *stated accuracy vs truth*: how often the error is within 1, 2, 3 × the stated
σ (honest: ~39 / 86 / 99 %), and the σ that **would** be honest.

> [!TASK]
> Answer [answers.py](file:./answers.py) from the tool's output and from your results.

## Step 6 — Write the result

Fill in [report.md](file:./report.md): what was measured, the table with your numbers, and one honest
paragraph. A good conclusion says **what** is better **by how much**, **compared with what**, on **how
much data**, measured **where** — and what it does **not** prove.

> [!TASK]
> Complete `report.md`: no `(…)` placeholder left, the table filled with your numbers (rounded to the
> metre), and a conclusion of at least 80 words that mentions the baseline and that the flights are
> simulated. Press **✔ Check my work**.

## Going further (optional)

- **Your own flight.** Run `python3 measure.py ~/lessons/28-simulator/flight.csv` on the flight you flew
  in lesson 28. Same numbers as the sample? Why not exactly?
- **The spoof.** During the 30 s spoof, which source did NAVERA use and with what error? Add a
  `gps_mode == "spoof_jump"` line to `main()`.
- **A better baseline.** "Repeat the last position" ignores that the drone was moving. Write
  `baseline_dead_reckoning`: continue the last GPS velocity in a straight line (lesson 23). Does vision
  still beat it? That is a harder, fairer baseline — which one would you publish?
