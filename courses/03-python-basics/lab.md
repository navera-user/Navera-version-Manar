# Lab 3 — The mission calculator

**Goal:** write the small navigation functions every mission planner needs — speed conversions,
travel time, battery endurance and the 600 m circle — and see them answer real questions.
**Time:** about 1 hour 15 minutes.

You will work in two files, already open in the **📝 Code** tab:
[mission.py](file:./mission.py) (a warm-up) and [nav_math.py](file:./nav_math.py) (the real work).
After each change: save with `Ctrl+S`, run the file in the **⌨️ Terminal**, read what it prints.

## Step 1 — Python as a calculator

Start Python in interactive mode:

```bash
python3
```

The prompt becomes `>>>`. Type these one by one (press `Enter` after each) and predict the answer
**before** you see it:

```python
54 / 3.6
15 * 60
130 // 60
130 % 60
300 ** 2 + 400 ** 2
import math
math.sqrt(300 ** 2 + 400 ** 2)
"GPS" + " LOST"
f"{707.1068:.0f} m"
50 >= 50
```

Now make a mistake on purpose:

```python
"Battery: " + 35
```

Read the last line: `TypeError: can only concatenate str (not "int") to str`. Python tells you
exactly what is wrong. Leave interactive mode:

```python
exit()
```

## Step 2 — Warm-up: variables and f-strings

Run the warm-up as it is:

```bash
python3 mission.py
```

It prints the drone and its speed. Open [mission.py](file:./mission.py) and read it.

> [!TASK]
> **TODO A** — replace `mission_time_min = 0` by a calculation that uses the variables
> `mission_distance_km` and `cruise_speed_kmh` (hours = distance ÷ speed, then × 60).
> **TODO B** — at the end of the file, add one `print` with an f-string that shows the drone name and
> the time rounded to 1 decimal, for example `NAVERA-1 flies 12 km at 54 km/h: 13.3 minutes`.

```bash
python3 mission.py
```

You should see `13.3 minutes`. Now change `cruise_speed_kmh` to `72` and run again: the time
changes by itself (`10.0`). That is the power of variables: you change one value, everything that
depends on it follows.

## Step 3 — Speeds, distances, times (TODO 1–4)

Open [nav_math.py](file:./nav_math.py). Every function ends with a line like
`raise NotImplementedError("TODO 1")`. That line means "not written yet". **Replace it** by your
code. Run the file to see where you are:

```bash
python3 nav_math.py
```

Every line says `not written yet`. Let's write the first one together. Replace:

```python
    # TODO 1: return the speed in m/s
    raise NotImplementedError("TODO 1")
```

by:

```python
    return speed_kmh / 3.6
```

Keep the 4 spaces in front: the line belongs to the function. Save, run again:

```bash
python3 nav_math.py
```

The first line now says `kmh_to_ms(36) -> 10.0`. 🎉

> [!TASK]
> Write **TODO 2** (`ms_to_kmh`), **TODO 3** (`distance_m`) and **TODO 4** (`travel_time_s`).
> For TODO 4, the drone never arrives when the speed is 0 or negative: in that case return `None`
> **before** dividing (dividing by 0 is an error). The docstring under each `def` (the text in
> triple quotes) gives an example with the expected answer.

<details><summary>Stuck on the shape of TODO 4?</summary>

```python
    if speed_ms <= 0:
        return None
    return ...
```
The second `return` is only reached when the `if` was false.
</details>

Run the file again and compare every answer with the example in the docstrings:

```bash
python3 nav_math.py
```

## Step 4 — The battery (TODO 5–6)

> [!TASK]
> **TODO 5** — `flight_time_min(battery_wh, power_w, reserve_percent=20)` returns the flight time in
> **minutes**, keeping the reserve unused. Write it in three lines with three variables:
> `usable_wh`, `hours`, and the `return`.
> **TODO 6** — `battery_status(percent)` returns `"OK"` (50 or more), `"LOW"` (20 or more) or
> `"LAND NOW"` (below 20). Use `if` / `elif` / `else`.

Test your functions one by one in interactive mode — a very useful habit. From the terminal, start
Python and **import** your file (without the `.py`):

```bash
python3
```

```python
from nav_math import flight_time_min, battery_status
flight_time_min(100, 400)
flight_time_min(100, 400, 0)
battery_status(50)
battery_status(20)
battery_status(19.9)
exit()
```

You should get `12.0`, `15.0`, `'OK'`, `'LOW'` and `'LAND NOW'`. The values **50** and **20** are
the dangerous ones: they test whether you wrote `>` or `>=`.

> [!WARNING]
> Python reads your file only once, at the `import`. If you change `nav_math.py`, leave with
> `exit()` and start `python3` again to see your change.

Now answer the question of the course with your own functions: a 100 Wh battery, 400 W,
20 % reserve — can the drone fly the 12 km at 54 km/h?

```bash
python3 -c "from nav_math import *; print(flight_time_min(100, 400), travel_time_s(12000, kmh_to_ms(54)) / 60)"
```

`python3 -c "..."` runs a short program written directly on the command line. The first number is
the endurance (12.0 min), the second the time needed (13.3 min). Verdict: it would **not** make it.

## Step 5 — The 600 m circle (TODO 7–9)

Positions are in metres from home: `x` to the east, `y` to the north. Look at the picture in the
course tab if you need it.

> [!TASK]
> **TODO 7** — `distance_from_home_m(x_m, y_m)`: Pythagoras, with `math.sqrt` (already imported at
> the top of the file).
> **TODO 8** — `inside_circle(x_m, y_m, radius_m=HOME_RADIUS_M)`: `True` inside the circle or exactly
> on it, `False` outside. Call your `distance_from_home_m()`; don't repeat the formula.
> **TODO 9** — `status_line(name, x_m, y_m)` returns (not prints!) exactly
> `"drone-1 is 500 m from home: INSIDE"` — the distance with `:.0f`, then `INSIDE` or `OUTSIDE`.

```bash
python3 nav_math.py
```

The last lines should read:

```
  inside_circle(300, 400)                -> True
  inside_circle(500, -500)               -> False
  status_line("drone-1", 300, 400)       -> 'drone-1 is 500 m from home: INSIDE'
  status_line("drone-2", 500, -500)      -> 'drone-2 is 707 m from home: OUTSIDE'
```

(The quotes `' '` around the text show that the function **returned** a string.)

## Step 6 — Check your work

Press **✔ Check my work**. The checker calls your functions with many values — including the tricky
ones (0, negative numbers, exactly 50 %, exactly 600 m). If a line is red, its message shows the call
and the value you returned: try that same call in interactive mode to understand.

## Going further (optional)

- Add a function `seconds_to_text(total_s)` that turns `130` into `"2 min 10 s"` with `//` and `%`,
  and use it in `status_line` to show how long the drone needs to fly home at 15 m/s.
- The drone is at `(450, 380)` and flies east at 12 m/s. After how many **whole seconds** does it
  leave the 600 m circle? Write a small `while` loop… or wait for lesson 4, which teaches loops.
- NAVERA receives GPS speeds in **knots** (nautical miles per hour). Find the conversion factor it
  uses: `grep -rn "KNOTS" ~/navera/gps_pkg ~/navera/navera_output --include=*.py`. Write
  `knots_to_ms()` with it.
