# Lab 3 — A navigation library and a mission planner

**Goal:** write `navlib.py`, a small navigation library with functions, exceptions, two classes
with inheritance and a `Track` class computed with NumPy; then use it in `mission.py` to decide
whether two vehicles can fly an inspection on a desert coast and to analyse a recorded survey
track. You finish with a short written report.
**Time:** about 3–4 hours (more if Python classes are new to you — that is normal).

Your files (already open): [navlib.py](file:./navlib.py) (TODO 1–9),
[mission.py](file:./mission.py) (TODO A–C), [report.md](file:./report.md), and the data
[harbour_track.csv](file:./harbour_track.csv) (synthetic: one position per second, in metres east and
north of the take-off point).

Work in small steps: write one TODO, save (`Ctrl+S`), run the demo, compare with the docstring
example, and only then go on.

## Step 1 — Warm up in the interpreter

```bash
python3
```

Type these lines one by one at the `>>>` prompt and **predict** each result before you press
`Enter`:

```python
f"{7.020985:8.2f}|"
f"{'quad':<8}|{263:5d}|"
round(2.5), round(3.5), round(30.2149, 1)
import math
math.degrees(math.asin(4 / 15))
math.asin(15 / 4)
import numpy as np
a = np.array([0.0, 12.1, 24.3, 36.0])
np.diff(a), a - 100, a > 20, np.argmax(a > 20)
math.cos(a)
exit()
```

Two of these lines raise an error on purpose. Read the **last line** of each traceback:
`ValueError: math domain error` (asin of a number above 1) and
`TypeError: only length-1 arrays can be converted to Python scalars` (`math.cos` on an array —
use `np.cos`). You will meet both again; now you know what they mean.

## Step 2 — Functions and the wind triangle (TODO 1–3)

Run the demo of the library. Every line says `not written yet`:

```bash
python3 navlib.py
```

> [!TASK]
> In [navlib.py](file:./navlib.py):
> - **TODO 1** `heading_vector(heading_deg)` returns the tuple `(east, north)` of the unit vector,
>   headings clockwise from north.
> - **TODO 2** `ground_velocity(airspeed_ms, heading_deg, wind_east_ms=0.0, wind_north_ms=0.0)`
>   returns `(east, north)` of air velocity + wind. Call `heading_vector()`; don't repeat it.
> - **TODO 3** `wind_correction(airspeed_ms, track_deg, wind_east_ms, wind_north_ms)` returns
>   `(heading_deg, ground_speed_ms)` with the heading in `[0, 360)`, and **raises `ValueError`**
>   when `|w_cross| > airspeed` or when the ground speed is `<= 0`. The formulas are in the course
>   (section 6).

Run the demo again:

```bash
python3 navlib.py
```

`wind_correction(15, 0, 4, 0)` must give `(344.5, 14.46)` and the "too windy" line must show
`ValueError: crosswind 20.0 m/s is stronger…` (your own message). Check the lab's case by hand
against the worked example of the course:

```bash
python3 -c "from navlib import wind_correction; print(wind_correction(12, 30, -3, -4)); print(wind_correction(12, 210, -3, -4))"
```

Expected: about `(32.86, 7.02)` out and `(207.14, 16.95)` back.

> [!TIP]
> If you get `ValueError: math domain error` from `math.asin`, you forgot the check before it, or
> you divided the wrong way round (`V / w` instead of `w / V`). If a heading comes out as `-15.47`,
> use `% 360.0`: in Python, `-15.47 % 360` is `344.53`.

## Step 3 — Exceptions: refuse impossible inputs (TODO 4)

> [!TASK]
> **TODO 4** `flight_time_min(battery_wh, power_w, reserve_frac=0.2)` returns minutes of flight,
> and raises `ValueError` if `battery_wh <= 0`, `power_w <= 0`, or `reserve_frac` is not in
> `[0, 1)`.

Test it on **several** battery sizes, not only 100 Wh — a formula like `battery_wh - 20` gives the
right answer for 100 Wh by luck:

```bash
python3 -c "from navlib import flight_time_min as f; print(f(100, 400), f(50, 400), f(77, 154), f(100, 400, 0.0))"
```

Expected: `12.0 6.0 24.0 15.0`. Then see your exception being **caught** by a caller:

```bash
python3 -c "from navlib import flight_time_min as f
try:
    print('NOT refused (bug):', f(100, 400, 1.0))
except ValueError as e:
    print('refused:', e)"
```

Expected: `refused: …` followed by **your own** error message. If you see
`NOT refused (bug): 0.0`, your test lets `reserve_frac = 1.0` pass: the interval `[0, 1)` excludes 1,
so the test must be `>= 1` (or `not 0 <= reserve_frac < 1`), not `> 1`.

## Step 4 — Classes and inheritance (TODO 5–7)

Read the class `Multirotor` in `navlib.py`: it is already written and shows the pattern —
`super().__init__(...)` first, then the new attribute.

> [!TASK]
> - **TODO 5** `Vehicle.__init__`: raise `ValueError` if `cruise_ms <= 0`, then store
>   `self.name`, `self.cruise_ms`, `self.battery_wh`, `self.power_w` (exactly these names).
> - **TODO 6a** `Vehicle.endurance_s(reserve_frac=0.2)` in seconds, using `flight_time_min()`.
> - **TODO 6b** `Vehicle.range_m(reserve_frac=0.2, wind_along_ms=0.0)`: ground speed ×
>   endurance, `0.0` when the ground speed is `<= 0`.
> - **TODO 7a** `FixedWing.__init__`: call `super().__init__(...)`, raise `ValueError` if
>   `cruise_ms <= stall_ms`, store `self.stall_ms`.
> - **TODO 7b** `FixedWing.turn_radius_m(bank_deg=30.0)`: `r = v² / (g·tan φ)`.

```bash
python3 navlib.py
```

Expected in Part B: `endurance_s()` → `720`, `range_m(wind_along_ms=-3)` → `6480`,
`turn_radius_m(30)` → `70.62`. Now explore your objects interactively:

```bash
python3 -c "from navlib import *; w = FixedWing('wing', 20, 150, 220, 12); print(w, w.stall_ms, w.endurance_s() / 60, isinstance(w, Vehicle))"
```

> [!QUESTION]
> `FixedWing` never defines `endurance_s()`. Where does `w.endurance_s()` come from, and which
> battery value does it use? What would happen if you deleted the `super().__init__(...)` line?
> (Try it, run the command above, read the error, then put the line back.)

## Step 5 — The Track class with NumPy (TODO 8–9)

The class `Track` keeps three lists `t`, `east`, `north`. `arrays()` (already written) turns them
into NumPy arrays: from there, **no Python loop** is needed.

> [!TASK]
> - **TODO 8** `Track.add(t, east, north)`: raise `ValueError` if the list is not empty and
>   `t <= self.t[-1]`; otherwise append the three values as floats.
> - **TODO 9a** `length_m()`: total length with `np.diff`, `np.hypot`, `np.sum` (`0.0` with fewer
>   than 2 points). **TODO 9b** `speeds_ms()`: the array of the `n − 1` segment speeds (an empty
>   array with fewer than 2 points).

```bash
python3 navlib.py
```

The demo track `(0,0) → (3,4) → (3,10)` must give `length_m() → 11` and `speeds_ms() → [5. 6.]`
(compare with the worked example at the end of the course, section 7). Then load the real file and look at the speeds:

```bash
python3 -c "from navlib import load_track; import numpy as np; tr = load_track('harbour_track.csv'); s = tr.speeds_ms(); print(len(tr), tr.length_m(), np.median(s), s.max(), np.round(s[145:152], 1))"
```

The median speed is close to the 12 m/s cruise, but the maximum is above 50 m/s, and two speeds
(index 149 and 150) are far too high. A multirotor does not do that: a **glitch** — one wrong GPS
fix — hides in the data. You will find its time in Step 6.

## Step 6 — The mission planner (TODO A–C)

Open [mission.py](file:./mission.py). It imports your library. Read the scenario at the top: 9 km
out on track 030°, back on 210°, wind `(-3, -4)` m/s.

```bash
python3 mission.py
```

As long as a TODO of `navlib.py` is missing, `mission.py` tells you which one.

> [!TASK]
> Complete `mission.py` so that `python3 mission.py` writes **results.json** with every key named
> in the TODO comments:
> - **TODO A** `out_heading_deg`, `out_ground_speed_ms` (the quad, outbound);
> - **TODO B1** the function `round_trip_min(vehicle)`; **TODO B2** for `quad` and `wing`:
>   `<name>_endurance_min`, `<name>_round_trip_min`, `<name>_can_do_it` (a `bool`), and
>   `wing_turn_radius_m` (30° bank);
> - **TODO C** `track_points`, `track_length_m`, `track_max_speed_ms`, `track_median_speed_ms`,
>   `glitch_time_s` (the time of the **first** point reached at more than 25 m/s — a boolean mask
>   and `np.argmax`; remember that speed `i` ends at point `i + 1`).

```bash
python3 mission.py
```

```bash
cat results.json
```

`json` cannot write some NumPy types: wrap numbers in `float(...)` or `int(...)` and booleans in
`bool(...)`. If you see `TypeError: Object of type int64 is not JSON serializable` (or `bool_`),
that is the reason.

## Step 7 — Write the report

> [!TASK]
> Fill [report.md](file:./report.md): keep the three `##` headings, replace each "(write here)" by
> 2–4 sentences of your own (at least 100 words in total), with numbers and units from
> results.json. The check looks for the quad's **round-trip time** (min) and the **glitch time**
> (s), and for the three headings.

Questions to answer in it: why the heading is not 030°; why a 25-minute trip in still air does not
fit in 21.9 minutes of endurance with this wind; why the **median** speed describes the track
better than the mean or the maximum.

## Step 8 — Check your work

Press **✔ Check my work**. The checker calls your functions with other values than the demo
(other headings, winds, batteries, other tracks…), checks your exceptions, builds your
classes, runs `mission.py` and reads `results.json` and `report.md`. Each ✘ shows the call and the
value you returned: run that same call with `python3 -c "…"` to see it yourself.

## Going further (optional)

- **Farthest point from home.** Add a method `Track.max_distance_from(east0=0.0, north0=0.0)` that
  returns the largest distance between the track and the point `(east0, north0)`, with NumPy and no
  loop (`e - east0` subtracts a number from every element). For `harbour_track.csv` and the take-off
  point `(0, 0)` you should find about 1362 m. Lesson 4 then shows **broadcasting**, the general
  rule behind `e - east0`.

- **Best heading for a round trip.** For the fixed wing, which outbound track (0°–359°, step 1°)
  gives the **longest** round trip with this wind, and which the shortest? Do it with NumPy:
  compute `w_along` and `w_cross` for an array of 360 tracks at once (no loop), then `np.argmax`.
- **Remove the glitch.** Add a method `Track.without_glitches(max_speed_ms)` that returns a new
  `Track` without the points reached faster than `max_speed_ms`. How much does the length change?
  (Careful: removing one point changes the next speed too.)
- **Read NAVERA.** Open [track.py](file:navera/navera_common/navera_common/track.py) and find
  where `TrackVelocity.propagate()` makes the stated uncertainty `sigma` grow with time. Which
  terms grow like `t` and which like `t²`?
