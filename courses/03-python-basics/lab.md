# Lab 3 — Flight planner and track detective

**Goal:** write the first two parts of NAVERA Lite, `vehicle.py` and `track.py`; decide whether a quad
can fly an inspection in the wind and find its wind limit; then build a fleet with classes and hunt a
wrong GPS fix in a recorded flight with NumPy.
**Time:** 3 to 4 h in two sessions (a strong programmer: about 2 h 30; up to 6 h if Python is new to you).
**Fast track:** if you know Python, skip the 🧰 boxes and the "Stuck?" boxes; Steps 1–2 should take you
10 minutes. Then do "Going further" at the end of each session.

Your files (📝 Code tab):

- [navera_lite/vehicle.py](file:./navera_lite/vehicle.py) — **your code**, TODO 1–9;
- [navera_lite/track.py](file:./navera_lite/track.py) — **your code**, TODO 10–13;
- [answers.py](file:./answers.py) — predictions, numbers, explanations;
- [plan_mission.py](file:./plan_mission.py) — runs your parts on the lab's situations and draws them (you
  don't edit it);
- the recorded flight is read only, at `/data/academy/03-python-basics/harbour_track.csv`.

| Lesson | Lab | You write |
|---|---|---|
| §1 Functions | Steps 1–2, 4 | `heading_vector`, `ground_velocity`, `endurance_s` |
| §2 Wind triangle | Steps 3–5 | `wind_components`, `heading_for_track`, then your own `my_limit.py` |
| §3 Classes | Steps 6–7 | `Vehicle.__init__`, `Vehicle.endurance_s`, `Vehicle.range_m`, `FixedWing.__init__` |
| §4 NumPy | Steps 8–11 | `Track.add`, `length_m`, `speeds_mps`, `glitches`, then your own `no_glitch.py` |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` is written **before** you run the step. It is never marked
> right or wrong; being wrong and finding out why is the point.

## Session 1 — Flight planner (about 1 h 45)

## Step 0 — Your stack

NAVERA Lite is a Python **package**: a folder of modules with an `__init__.py`. Look at what this mission
gives you:

```bash
cat navera_lite/PARTS.md
```

Both parts are yours this time. Each TODO has a docstring with its goal, units and one `Example:` with
its result; the body is a stub. Run the test mode of the runner:

```bash
python3 plan_mission.py test
```

Every line says "not written yet". Each time you finish a TODO, save (`Ctrl+S`) and run this again.
Your code is imported as `from navera_lite.vehicle import heading_vector`; run every command from this
folder (`~/lessons/03-python-basics`), the folder that holds `navera_lite/`.

## Step 1 — Warm up in the interpreter

```bash
python3
```

At the `>>>` prompt, type these lines one by one, and **predict** each result before `Enter`:

```python
import math
math.sin(30), math.sin(math.radians(30))
-36.87 % 360
math.degrees(math.asin(6 / 10))
math.asin(9 / 8)
f"{7.020985:.2f}|{263:5d}|"
exit()
```

`0.49999999999999994` is 0.5 up to float rounding (like `6.1e-17` in Step 2).
`math.asin(9 / 8)` stops with `ValueError: math domain error`: no angle has a sine above 1. That is the
crosswind case of lesson §2, and the reason your function will check first.

## Step 2 — Headings and velocities (TODO 1–2)

**TODO 1** `heading_vector` and **TODO 2** `ground_velocity` in [vehicle.py](file:./navera_lite/vehicle.py)
(lesson §2). TODO 2 calls TODO 1: never write the same formula twice.

```bash
python3 plan_mission.py test
```

The first three lines must be ✔. (`6.1e-17` is 0 up to rounding: cos 90° is not exactly 0 in floats.)

<details><summary>Stuck? Hints</summary>

1. Degrees to radians first: `h = math.radians(heading_deg)`; then return two values: `return a, b`.
2. `heading_vector(90)` gives `(0.0, 1.0)` and `heading_vector(0)` gives `(1.0, 0.0)`: sine and cosine are
   swapped. A heading counts from **north**: east is the sine.
3. `heading_vector(30)` gives `(-0.988, 0.154)`: you passed degrees to `math.sin`.
4. TODO 2: `e, n = heading_vector(heading_deg)`, then airspeed × each component, plus the wind's.
</details>

## Step 3 — The wind triangle (TODO 3–4)

**TODO 3** `wind_components`: two dot products (lesson §2). **TODO 4** `heading_for_track`: call TODO 3,
then the crab angle, heading and ground speed, and **raise `ValueError`** in the two impossible cases,
before `math.asin`. Keep the heading in [0, 360) with `% 360.0`.

<details><summary>🧰 raise and a sentence</summary>

```python
if depth_m < 0:
    raise ValueError(f"depth_m must be >= 0, got {depth_m}")    # the function stops here
```

Your message is for the person who called the function: say what was wrong and the value received.
</details>

```bash
python3 plan_mission.py test
```

<details><summary>Stuck? Hints</summary>

1. `wind_components`: the unit vector of the track is `heading_vector(track_deg)`, the one to its right
   `heading_vector(track_deg + 90)`; a dot product is `a_e * b_e + a_n * b_n`.
2. `wind_components(0, 2, -5)` gives `(-5.0, -2.0)`: the cross sign is reversed (you used the vector to
   the **left**). It must be `+2.0`: a wind blowing east pushes a northbound drone to the right.
3. `heading_for_track(0, 10, 6, 0)` gives `36.87` instead of `323.13`: you added the crab angle. The drone
   points **into** the wind: `track − crab`.
4. `ValueError: math domain error` instead of your own message: test `abs(cross) > tas_mps` **before**
   `math.asin`.
5. The ground-speed case: compute `gs`, then `if gs <= 0: raise …`.
6. `(-0.6435, 8.0)` or `(359.36, …)` for `heading_for_track(0, 10, 6, 0)`: your crab angle is in radians.
   `c = math.degrees(math.asin(cross / tas_mps))`, and use `math.radians(c)` inside `math.cos`.
</details>

**The mission.** A quad must inspect a lighthouse **7.5 km** away on the ground track **030°**, and come
back on 210°. It flies at 12 m/s through the air. The forecast: wind **from 020° at 6 m/s**.

> [!TASK]
> **Predict** (`PREDICT_WIND`): on the way out, will the heading to fly be left or right of 030°, and by
> roughly how much?

```bash
python3 plan_mission.py wind
```

It prints the wind vector and its along/cross components on each leg, nothing more. The heading and the
ground speed are your job: call **your** `heading_for_track` with the track, the airspeed and that wind
vector, for the way out (030°) and the way back (210°).

<details><summary>🧰 calling your function from the terminal</summary>

```python
python3 -c "from navera_lite.vehicle import heading_for_track; print(heading_for_track(TRACK, 12.0, WE, WN))"
```

Replace `TRACK`, `WE` and `WN` by numbers (the wind vector printed by `wind`). Or open `python3` and type
the two lines.
</details>

Then open `out/wind.png`: drawn with your heading, the air velocity plus the wind must land on the dashed
track. If it does not, your heading is wrong.

> [!TASK]
> Write `OUT_HEADING_DEG`, `OUT_GS_MPS` and `BACK_GS_MPS` (2 decimals).

## Step 4 — Endurance and go / no-go (TODO 5)

**TODO 5** `endurance_s`: seconds, with the reserve, and `ValueError` for a battery or a power ≤ 0, or a
reserve outside [0, 1). The physics is the 🧰 box of lesson §1.

<details><summary>🧰 an interval test in one line</summary>

```python
if not 0.0 <= ratio < 1.0:        # True for -0.1, 1.0 and 1.5; False for 0.0 and 0.99
    raise ValueError(...)
```
</details>

Make sure `endurance_s(100, 400, 1.0)` raises **your** `ValueError` (the reserve interval excludes 1),
and that your formula is not right by luck on one battery only.

<details><summary>Two probes to run (open if you want them ready-made)</summary>

```bash
python3 -c "from navera_lite.vehicle import endurance_s as f; print(f(50.0, 200.0, 0.1), f(100.0, 400.0))"
```

```bash
python3 -c "from navera_lite.vehicle import endurance_s as f; print('NOT refused (bug):', f(100.0, 400.0, 1.0))"
```

The second must end in a traceback with **your** message. `NOT refused (bug): 0.0` means your test lets
1.0 pass.
</details>

<details><summary>Stuck? Hints</summary>

1. Usable Wh = battery × (1 − reserve); Wh ÷ W = hours; × 3600 = seconds.
2. `13.5` instead of `810.0`: that is minutes; the name ends in `_s`.
3. Check the inputs at the **top** of the function, before computing anything.
</details>

> [!TASK]
> **Predict** (`PREDICT_TRIP`): in still air, the round trip (15 km at 12 m/s) takes 20.8 min. With this
> wind (a headwind out, a tailwind back), will it take longer, less, or the same? Why?

```bash
python3 plan_mission.py gonogo
```

It prints the still-air time, each leg with the wind, and the endurance. The round trip and the decision
are yours.

> [!TASK]
> Write `TRIP_MIN` (the round trip with the wind), `ENDURANCE_MIN` (2 decimals) and `DECISION` (`"GO"` or
> `"NO-GO"`). (Adding the two rounded legs may give 27.68 instead of 27.67: both are fine.) Then
> `EXPLAIN_TRIP`: why does the wind cost time on a round trip, although it helps on the way back?

<details><summary>Read this after you wrote EXPLAIN_TRIP: the asymmetry</summary>
Time = distance ÷ speed. The slow leg lasts long, so the headwind acts for a long time; the fast leg is
short, so the tailwind has little time to give anything back. With a pure head/tailwind w:
L/(V − w) + L/(V + w) = 2LV/(V² − w²), always more than 2L/V. Here the out leg takes 20.7 min, the back
leg only 7.0 min.

Your turn (not graded): show that with a crosswind part the round trip is also always longer than in still
air. Hint: the drone keeps only V cos c < V of its own speed along the track.
</details>

## Step 5 — The engineer's question: the wind limit

The pilot asks: "up to which wind can I still go?" Answer it with **your own script**. Create the file
`my_limit.py` in this folder (📝 Code tab → new file) that, for winds from 020° at 0.0, 0.5, 1.0 … m/s,
computes the round trip with **your** functions, compares it with the endurance, and prints GO or NO-GO.
Stop the loop at the first NO-GO (or when `heading_for_track` raises: no heading works). The **last line**
your script prints must be `MAX_WIND_MPS = ` followed by the last GO speed, e.g. `MAX_WIND_MPS = 1.5`: the
check runs your script and reads that line.

<details><summary>🧰 a script that imports your part, a loop in steps of 0.5, and catching an error</summary>

```python
from navera_lite.vehicle import heading_vector

for i in range(5):                   # i = 0, 1, 2, 3, 4
    x = i * 0.5                      # 0.0, 0.5, 1.0, 1.5, 2.0  (range takes whole numbers only)
    try:
        print(x, 1.0 / (1.5 - x))
    except ZeroDivisionError:
        print(x, "impossible")
        break                        # leave the loop
```
</details>

**Self-test before the loop.** Make your script first print the wind vector for 6 m/s: `print(we, wn)` must
show −2.05 −5.64, the same as `plan_mission.py wind`. +2.05 +5.64 means you built the wind blowing FROM
020°, not TOWARDS 200° (the check looks at the winds your script really uses).

```bash
python3 my_limit.py
```

> [!TASK]
> `MAX_WIND_MPS`: the value your script prints (the strongest wind, in 0.5 m/s steps, that is still GO).

<details><summary>Stuck? Hints</summary>

1. "From 020°" is a wind **towards** 200°: `e, n = heading_vector(200.0)`, then `we, wn = speed * e, speed * n`.
2. Each wind: two `heading_for_track` calls (030° and 210°), time = 7500 / ground speed for each leg.
3. Compare seconds with seconds: `endurance_s(160.0, 350.0, 0.2)` (the quad: 160 Wh, 350 W).
4. Everything NO-GO, even at 0 m/s? You compare seconds with minutes, or you forgot one leg.
5. Check your wind first: for 6 m/s, `print(we, wn)` must give −2.05, −5.64, the same as
   `plan_mission.py wind`. With `heading_vector(20)` you get +2.05, +5.64: the wind blowing the wrong way.
   On an out-and-back trip the answer looks the same, but the out and back legs are swapped.
6. The last line: `print("MAX_WIND_MPS =", last_go)` after the loop, where `last_go` is updated each time
   a speed is GO.
</details>

**Now by algebra.** For a pure head/tailwind w, the box after Step 4 gives the round trip
2LV/(V² − w²). Set it equal to the quad's endurance (in seconds) and solve for w, on paper or in
`python3`.

> [!TASK]
> `ANALYTIC_WIND_MPS` (2 decimals). Compare it with `MAX_WIND_MPS`, and predict where the true limit of
> the real wind (from 020°, not exactly along the track) lies: below, between or above your two values?
> Why? (Not graded; Going further finds it.)

<details><summary>Stuck? Hints</summary>

1. V² − w² = 2LV / endurance, so w = √(V² − 2LV / endurance).
2. L = 7500 m (one leg), V = 12 m/s, endurance = your `endurance_s(160.0, 350.0, 0.2)` in seconds.
3. `ValueError: math domain error` (or `nan`): a negative number under the root — the endurance was in
   minutes, so 2LV / endurance is far bigger than V².
</details>

> [!TIP] 🏅 End of session 1 — Flight planner
> Press **✔ Check my work**. When checks 1–9 pass (TODO 1–5 and Steps 3–5), you earn the **Flight
> planner** badge. Fast? Going further: "Best heading for the round trip" below.

## Session 2 — Fleet and track detective (about 2 h)

## Step 6 — The Vehicle class (TODO 6–8)

Read the class `Vehicle` in [vehicle.py](file:./navera_lite/vehicle.py): `__repr__` is finished;
`__init__`, `endurance_s` and `range_m` are yours (lesson §3).

- **TODO 6** `__init__`: refuse `cruise_mps <= 0` and `max_speed_mps < cruise_mps`, then store the five
  attributes with **exactly** their parameter names (`self.cruise_mps = cruise_mps` …).
- **TODO 7** `endurance_s(self, reserve=0.2)`: one line that calls the **module** function `endurance_s`
  of TODO 5 with this vehicle's values. (Inside a method, `endurance_s(...)` is the module's function;
  `self.endurance_s(...)` is the method.)
- **TODO 8** `range_m`: the docstring says what; `0.0` when the vehicle does not move forwards.

```bash
python3 plan_mission.py test
```

<details><summary>Stuck? Hints</summary>

1. `AttributeError: 'Vehicle' object has no attribute 'battery_wh'`: a `self.battery_wh = battery_wh` line
   is missing (or misspelt) in `__init__`.
2. `range_m` returns `None` (for example `range_m(-0.5) -> None`): a path of your `if`/`else` has no
   `return`. Write `return …` on BOTH paths: `return 0.0` when stopped, `return gs * self.endurance_s(reserve)`
   otherwise.
3. `RecursionError` in `endurance_s`: you wrote `self.endurance_s(...)` inside `endurance_s`: it calls
   itself forever. Call the module function, with `self.battery_wh` and `self.power_w`.
   `TypeError: Vehicle.endurance_s() takes from 1 to 2 positional arguments but 4 were given`: the same
   mistake; `self.endurance_s` is the method (it only takes `reserve`). Python counts `self` as an argument.
</details>

## Step 7 — Inheritance: a fixed wing (TODO 9)

Read `Multirotor`: it inherits **everything** from `Vehicle` and adds one method, `hover_s`. A fixed
wing needs more: a stall speed, and a check. **TODO 9** `FixedWing.__init__`: `super().__init__(...)`
first (lesson §3, `Camera`), then refuse a cruise speed that is not above the stall speed, then store
`self.stall_mps`.

<details><summary>Stuck? Hints</summary>

1. `TypeError: Vehicle.__init__() takes 6 positional arguments but 7 were given`: remove `self` from
   `super().__init__(...)`; Python passes it for you (lesson §3, `Camera`).
2. No `ValueError` for cruise = stall: "above" means `cruise_mps <= stall_mps` is refused.
</details>

```bash
python3 plan_mission.py fleet
```

> [!TASK]
> `WING_TRIP_MIN` (2 decimals): the fleet table gives the wing's endurance only; compute its round trip
> yourself with your `heading_for_track` at 20 m/s (your `my_limit.py` already does it for the quad), and
> `WING_DECISION` (`"GO"` or `"NO-GO"`). `WHERE_ENDURANCE_FROM`: `FixedWing` defines no `endurance_s()`. The
> line `wing.endurance_s()` runs the code of which class? (one class name)

<details><summary>Stuck? Hint</summary>

The same two legs as the quad, with the wing's airspeed: `heading_for_track(30.0, 20.0, we, wn)` and
`heading_for_track(210.0, 20.0, we, wn)` with the 6 m/s wind vector of Step 3; time = 7500 / ground speed per
leg, in minutes. Compare with the endurance printed by `fleet`.
</details>

Now print a wing:

```bash
python3 -c "from navera_lite.vehicle import FixedWing; wing = FixedWing('wing', 20, 35, 150, 220, 12); print(wing)"
```

> [!TASK]
> `PRINT_WING`: the text printed. `WHERE_REPR_FROM`: `print` calls `__repr__`; FixedWing has none — whose
> `__repr__` ran? (one class name). `EXPLAIN_REPR`: why does the text still say `FixedWing`? (Read
> `__repr__`: `type(self)` is the class of the object, not of the code.)

Now break it on purpose. In `FixedWing.__init__`, put a `#` in front of the `super().__init__(...)` line,
save, and run:

```bash
python3 -c "from navera_lite.vehicle import FixedWing; w = FixedWing('wing', 20, 35, 150, 220, 12); print(w.stall_mps); print(w.endurance_s())"
```

> [!TASK]
> `SUPER_ERROR`: the exception name on the **last line** of the traceback. `EXPLAIN_SUPER`: why does
> `stall_mps` print fine and `endurance_s()` fail? What did the `super()` line do?
> Then **remove the `#`**, save, and run `fleet` again.

## Step 8 — A track that keeps time order (TODO 10)

Open [track.py](file:./navera_lite/track.py). A `Track` keeps three lists, `self.t_s`, `self.e_m`,
`self.n_m`; `arrays()` (finished) turns them into NumPy arrays, `load_track()` (finished) reads a CSV file
with your `add`. **TODO 10** `add`: refuse a time that is not strictly after the last one, else append the
three values as floats.

<details><summary>🧰 the last item of a list, and an empty list</summary>

```python
times = []
if times:                  # an empty list counts as False: this block is skipped
    print(times[-1])
times.append(float("3"))   # [3.0]
times[-1]                  # 3.0: the last item
```
</details>

```bash
python3 plan_mission.py test
```

<details><summary>Stuck? Hints</summary>

1. `IndexError: list index out of range`: `self.t_s[-1]` on an empty list. Test `if self.t_s and …`.
2. The very first `add` raises your `ValueError`: you append first and test after, so the new time is
   compared with itself. Test, then append.
</details>

## Step 9 — Length and speeds with NumPy (TODO 11–12)

**TODO 11** `length_m` and **TODO 12** `speeds_mps`: lesson §4's worked example, **without a Python loop**
(the check looks). Start from `t, e, n = self.arrays()`.

```bash
python3 plan_mission.py test
```

<details><summary>Stuck? Hints</summary>

1. `np.diff` on each array, `np.hypot` for the lengths; `float(np.sum(...))` for one number.
2. `speeds_mps()` of the test track gives `[10.0, 12.0]` instead of `[5.0, 12.0]`: you return the segment
   lengths. Divide by `np.diff(t)`: the first segment took 2 s.
3. Fewer than 2 positions: `return 0.0` / `return np.array([])` before the maths.
</details>

Now the recorded survey of a harbour breakwater (synthetic, one position per second, metres east and north
of the take-off point):

```bash
python3 plan_mission.py track
```

It prints the length, the median and the mean. Open `out/track.png`: which of median, mean and maximum is
closest to the cruise speed you see in the plot? The number of positions and the maximum speed: find them
yourself, with `load_track`, `len()` and your `speeds_mps()` (one `python3 -c` line, or three lines in
`python3`).

<details><summary>Stuck? Hint</summary>

`tr = load_track("/data/academy/03-python-basics/harbour_track.csv")` (import it from `navera_lite.track`),
then `print(len(tr), tr.speeds_mps().max())`.
</details>

> [!TASK]
> Write `TRACK_POINTS`, `TRACK_LENGTH_M` (1 decimal), `MEDIAN_SPEED_MPS`, `MAX_SPEED_MPS` (2 decimals), and
> `EXPLAIN_MEDIAN`: why does the median describe this flight better than the mean or the maximum?

## Step 10 — The glitch hunt (TODO 13)

**TODO 13** `glitches(max_mps)`: the least guided TODO. Before you write it, do the docstring's example by
hand: list the speeds of the four positions, mark those above 50, and turn the marked **speed** indices
into **position** indices (lesson §4, figure). Then write it with a mask, no loop.

```bash
python3 plan_mission.py test
```

<details><summary>Stuck? Hints</summary>

1. Which NumPy function from lesson §4 turns a mask into indices?
2. The example gives `[2]` instead of `[3]`: those are speed indices; the position reached is one more.
3. `glitches() must return a list of Python ints`: end with `.tolist()`.
</details>

> [!TASK]
> **Predict** (`PREDICT_GLITCH`): the file contains **one** wrong GPS fix. How many positions will
> `glitches()` list at the quad's maximum speed (20 m/s)?

```bash
python3 plan_mission.py glitch
```

Open `out/glitch.png` (labels are times in seconds).

> [!TASK]
> Write `GLITCHES` (the list printed), `BAD_FIX_T_S` (the time of the **wrong** fix: which listed point is
> far from its neighbours?) and `EXPLAIN_GLITCH`: why does one wrong fix give that many entries?

<details><summary>Read this after you wrote BAD_FIX_T_S and EXPLAIN_GLITCH</summary>
A wrong fix makes two fast segments: the one INTO it and the one OUT of it, back to the true track. The
second listed position is a good fix, reached "fast" only because its segment starts at the wrong one. A
detector that deletes every listed position throws away a good fix; mission 01's jump gate avoids that by
comparing with the last <b>trusted</b> fix, not with the previous one.
</details>

**The threshold.** Why 20 m/s? Try a stricter one, close to the cruise speed:

```bash
python3 -c "from navera_lite.track import load_track; tr = load_track('/data/academy/03-python-basics/harbour_track.csv'); print(len(tr.glitches(15)))"
```

And with the limit of the **wrong vehicle**, a plane's 100 m/s (lesson "In NAVERA", R-1): change 15 into
100 in the same command.

> [!TASK]
> `FLAGGED_AT_15` (a number), `FLAGGED_AT_100` (the list `tr.glitches(100)` returns) and
> `EXPLAIN_THRESHOLD`: what does a threshold of 15 m/s cost, what does 100 m/s miss, and why is the
> vehicle's maximum speed the right limit?

**Clean it.** Write `no_glitch.py`: load the track, build a **new** `Track` with every position except the
wrong fix (a loop over `range(len(tr))` and your `add`), and print both lengths.

<details><summary>🧰 one position of a track, and skipping one</summary>

Position i of a track is `tr.t_s[i], tr.e_m[i], tr.n_m[i]` (`tr[i]` does not exist: `Track` has no
`__getitem__`). Skip one with `if i == bad: continue`. Here times start at 0, one per second, so the index
of time 150 s is 150. Create the new track with `Track()` (import `Track` from `navera_lite.track`).
</details>

```bash
python3 no_glitch.py
```

> [!TASK]
> `GLITCH_EXTRA_M`: how many metres the wrong fix adds to the length (1 decimal).

## Step 11 — A loop against NumPy

> [!TASK]
> **Predict** (`PREDICT_SPEEDUP`): on 200 000 positions, how many times faster than a plain Python loop
> will your `speeds_mps()` be?

```bash
python3 plan_mission.py speed
```

> [!TASK]
> `SPEEDUP_X`: the first "times faster" number (it depends on the computer and the moment: run it twice; if
> the numbers differ a lot, the computer was busy — take the higher one). Look at the
> second one too: what costs the most in your `speeds_mps()`?

## Step 12 — Check, then look back

Press **✔ Check my work**: it calls your functions on winds, vehicles and tracks they have never seen.
When every check passes, you earn the **Track detective** badge. Then look back, without the lesson:

1. The Mars Climate Orbiter and NAVERA's R-1: what one habit from this lab would have caught each?
2. Which prediction was the most wrong, and why?
3. Your `glitches()` lists two positions for one bad fix. How would you change the rule so that it
   lists only the bad one? (Mission 01 already did it.)
4. The honest maximum here is 18.9 m/s against a limit of 20: what would mission 01 add to this rule to
   survive a noisier GPS?

## Going further (optional)

- **The exact limit.** Your sweep gives the limit to 0.5 m/s, your algebra the pure-headwind value. Find
  the true limit of the real wind from 020° to 0.01 m/s by **bisection**: start from the last GO and the
  first NO-GO, test the middle, keep the half where GO changes to NO-GO, repeat. Where does it fall
  compared with your two answers, and why?
  <details><summary>Answer</summary>About 2.72 m/s: a little above the pure-headwind value, because the
  real wind is not exactly along the track (part of it is crosswind, which costs less).</details>
- **Best heading for the round trip.** For the wing (20 m/s), which outbound track (0°–359°, 1° steps)
  gives the longest round trip with this wind, and which the shortest? Use arrays of 360 tracks:
  `T = np.radians(np.arange(360))`, then the lesson's formulas with `np.sin`, `np.cos`, `np.arcsin`, and
  `np.argmax`.
  <details><summary>Answer</summary>Longest on 020° (and 200°), along the wind axis: 13.74 min. Shortest on
  110° (and 290°), across the wind: 13.10 min.</details>
- **Turn radius.** `FixedWing.turn_radius_m` (finished) uses `r = v² / (g · tan φ)`: in a level turn the
  horizontal part of the lift, `m g tan φ`, is the centripetal force `m v² / r`. At what bank does the
  wing turn inside a 50 m circle? Why does a camera's view tilt during such a turn (mission 20)?
  <details><summary>Answer</summary>tan φ = v² / (g r) = 400 / (9.81 × 50) → φ ≈ 39.2°. The camera is
  fixed to the airframe, so it banks with it and looks sideways instead of straight down.</details>
- **The unit saboteur.** [suspect.py](file:./suspect.py) has four helpers whose names promise their units. One lies.
  Without reading the code, write `test_suspect.py` with `assert` lines that check physics you trust
  (compare with `VEHICLES`, with a leg you can compute by hand…) and run
  `python3 -m pytest -q test_suspect.py`. Which function lies, in which unit?
  <details><summary>Answer</summary><code>max_speed_mps</code> returns <b>knots</b> (drone 58.3 instead
  of 30.0 m/s; 1 knot = 1852 m/h).</details>
- **A boat.** Add `class Boat(Vehicle)` in your `vehicle.py` with a `draft_m` attribute and a check, and
  plan the same inspection at 8 m/s. (The course's version of `vehicle.py` in later missions will not have
  it: keep your file.)
