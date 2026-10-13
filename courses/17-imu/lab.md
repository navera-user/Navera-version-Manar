# Lab 17 — From raw IMU samples to an attitude you can trust

**Goal:** write NAVERA Lite's IMU part (`navera_lite/imu.py`) and use it on a simulated 5-minute flight near
Monastir: measure the gyroscope's bias and drift, catch gravity being fooled in a turn, choose the
complementary filter's time constant from measured errors, correct a compass and a whole attitude to true
north, and build the frozen-sensor detector that NAVERA's item IMU-1 needed.
**Time:** 3 h 30 to 4 h 30 (session 1: 1 h 30–2 h, session 2: 2 h–2 h 30); a strong programmer who knows
numpy and quaternions: about 2 h 30.
**Fast track:** if you know numpy and quaternions well, skip the 🧰 boxes and the "Stuck?" boxes; do
"Going further" at the end.

Your files (📝 Code tab): [navera_lite/imu.py](file:./navera_lite/imu.py) (**your code**: `TODO 1–7`),
[answers.py](file:./answers.py), [report.md](file:./report.md), and a tool you only run:
[run_imu.py](file:./run_imu.py) (runs your functions on the flight and draws the results).
`navera_lite/rotations.py` is your mission-16 toolbox, finished: `q_mul`, `q_from_axis_angle`, `q_rotate`,
`q_normalize`, `rot_x`, `rot_y` are imported at the top of `imu.py`, ready to use.

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §1–§2 sensors, gyro, drift | Steps 1–2 | the pad bias; `integrate_gyro` (TODO 1) |
| §3 tilt from gravity | Step 3 | `tilt_from_accel` (TODO 2) |
| §4 complementary filter | Step 4 | `complementary` (TODO 3); choose τ |
| §5 compass, true north | Steps 5–6 | `mag_heading`, `true_heading`, `q_true_north` (TODO 4–6) |
| §6 frozen data | Step 7 | `StaleDetector.update` (TODO 7) |
| all | Step 8 | the attitude memo |

> [!NOTE]
> **The data.** NAVERA's IMU is not connected to the course computers, so you work on a **simulated** log
> (`/data/academy/17-imu/`): 50 samples per second, the three sensors in the body frame, the IMU chip's own
> attitude, and the **truth**, so every method can be measured. Its sensor errors were chosen for teaching;
> they are not measurements of NAVERA's hardware.
>
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step; it is never
> marked right or wrong. `python3 run_imu.py test` tries every docstring example (and a few traps). Angles:
> radians inside the functions, degrees in the headings and in `answers.py`.

## Session 1 — Drift hunter (about 1 h 30; 2 h if numpy is rusty)

## Step 0 — What does a still accelerometer read?

No code, no lesson yet. A drone sits still on a table, level.

> [!TASK]
> **Predict** (`PREDICT_REST` in `answers.py`): does its accelerometer read 0, +9.81 or −9.81 m/s² on its z
> axis (up)? Write one reason. Save the file (`Ctrl+S`). Then read lesson §1–§2.

## Step 1 — Look at the log, and measure the gyro's bias on the pad

```bash
python3 run_imu.py look
```

Open `out/look.png`. The drone sits still on its pad for the first 10 s (shaded), then takes off and flies
four turns. The columns are described in `/data/academy/17-imu/README.md`.

On the pad the true rate is zero, so the mean gyro reading **is** the bias (lesson §2). Compute it yourself,
in **°/s**, for the samples with `t_s < 10`.

<details><summary>🧰 numpy: read a CSV by column names, select rows, average, convert</summary>

```python
import numpy as np
L = np.genfromtxt("some_file.csv", delimiter=",", names=True)   # L["speed"] is a whole column
fast = L["speed"] > 3.0                  # a mask: True/False for every row
L["temp"][fast].mean()                   # the mean temperature of the fast rows only
np.degrees(0.01)                         # 0.5729… — radians → degrees (also works on arrays)
```

Try it in `python3` (the interactive prompt) or in one line: `python3 -c "…"`.
</details>

> [!TASK]
> Write `GYRO_BIAS_DEG_S` = the means of `gx`, `gy`, `gz` on the pad, in °/s, 4 decimals, as a tuple
> `(x, y, z)`.

<details><summary>Stuck? Hints, one at a time</summary>

1. Three steps: load `/data/academy/17-imu/imu_log.csv`, mask `L["t_s"] < 10`, mean of each gyro column.
2. The columns are in rad/s: `np.degrees(…)` after the mean.
3. One column at a time: the mask selects the pad rows of `L['gx']`, `.mean()` averages them, `np.degrees`
   converts. Print it, then the same for `gy` and `gz` (a `python3 -c "…"` line or the `python3` prompt).
4. You get numbers like 3.6 or 5.4? Those are degrees of rad/s converted twice, or not averaged: check one step at a time.
</details>

## Step 2 — Integrate the gyroscope (TODO 1)

Open the 📝 Code tab, then `navera_lite/imu.py`. Read the conventions at the top. Each `TODO` function keeps
its docstring and ends with `return None   # TODO…`: replace that line with your code.

<details><summary>🧰 numpy and Python: a loop that fills an array row by row</summary>

```python
out = np.empty((4, 2))                  # 4 rows, 2 columns, filled below
x = np.array([1.0, 0.0])
out[0] = x
for k in range(1, 4):                   # k = 1, 2, 3
    step = k * 0.5                      # something computed from step k
    x = x + step
    out[k] = x
float(np.linalg.norm([3.0, 4.0]))       # 5.0 — the length of a vector
```
</details>

**TODO 1** `integrate_gyro(q0, t_s, gyro_rad_s)`: lesson §2. Start from `q0` (normalised: `q_normalize`),
then for each step k = 1 … N−1 turn by the rate of sample k−1 during `t_s[k] − t_s[k−1]`. Your mission-16
`q_from_axis_angle` builds the small turn; which side of `q` does it go?

```bash
python3 run_imu.py test
```

The three lines of TODO 1 must be ✔ (the other TODOs show "not written yet").

Your bias from Step 1 is the gyro's error on z. The log is 300 s long.

> [!TASK]
> **Before running**, write `DRIFT_FORECAST_DEG`: the size of the heading error you expect after 300 s,
> from your z bias. And `PREDICT_DRIFT_SIGN`: will the heading error be positive or negative? Why? (Lesson
> §2's worked example and "heading = 90° − yaw" are enough to decide.)

```bash
python3 run_imu.py gyro
```

Now subtract your own bias estimate (three numbers, in °/s, from `GYRO_BIAS_DEG_S`) and run again:

```bash
python3 run_imu.py gyro 0.0 0.0 0.0
```

(replace the three zeros by your bias). Open `out/gyro.png` and `out/gyro_bias.png`.

> [!TASK]
> Write `GYRO_HEADING_ERR_DEG` (first run) and `CORRECTED_HEADING_ERR_DEG` (with your bias): the heading
> errors at 300 s, with their signs. `EXPLAIN_DRIFT`: why is the sign what it is, and what is left after you
> subtract the bias? Why is it not zero?

<details><summary>Stuck? Hints, one at a time</summary>

1. The shape: `t = np.asarray(t_s, dtype=float)`, `w = np.asarray(gyro_rad_s, dtype=float)`, an `out` array
   of shape `(len(t), 4)`, `q = q_normalize(q0)`, `out[0] = q`, then the loop of the 🧰 box.
2. In the loop: `dt = t[k] - t[k - 1]`, `angle = float(np.linalg.norm(w[k - 1])) * dt`. The small turn is
   `q_from_axis_angle(w[k - 1], angle)`.
3. ✘ "the nose went up / the turn was applied about the WORLD axes": the gyro measures in the body frame, so
   the turn goes on the **right**: `q = q_mul(q, dq)` (lesson §2, retrieval question 2).
4. ✘ "a rate of (0, 0, 0) has no axis": `q_from_axis_angle` refuses a zero axis. Only turn `if angle > 0`.
5. ✘ "you used the rate of sample k": `w[k - 1]`, the rate at the start of the step. ✘ "dt is not the same":
   compute `dt` inside the loop.
6. Your z bias is positive but the heading error is negative? Not a bug: what does a positive rate about Up
   do to the yaw, and what does that do to heading = 90° − yaw?
7. ✘ "you used the first-order update q + ½·dt·q ⊗ ω" (a formula found online): it is 0.01° off at 50 Hz but 1° off on the test's long steps: not
   exact. Build the exact small turn with `q_from_axis_angle(ω, |ω|·dt)` (lesson §2).
</details>

## Step 3 — Tilt from gravity, and the turn that fools it (TODO 2)

Read lesson §3. **TODO 2** `tilt_from_accel(ax, ay, az)`: the two formulas of §3, written with `np.arctan2`
and `np.hypot` so that one call works on single numbers **and** on whole columns (🧰 box of §3).

```bash
python3 run_imu.py test
```

> [!TASK]
> **Predict** (`PREDICT_SPEEDUP`): between 10 s and 20 s the drone speeds up from 0 to 10 m/s. A multirotor
> speeds up by pitching its nose down. Compared with the true pitch_up, will the accelerometer's pitch_up be
> the same, more nose-down, or less nose-down? Why? Then:

```bash
python3 run_imu.py tilt
```

Open `out/tilt.png`: the grey cloud is single samples (vibration), the coloured line their 1-second average.
In steady cruise (60–85 s, for example) the accelerometer agrees with the truth: −4.0°, the nose-down tilt
that holds the drone against the air drag. The braking row (280–290 s) is the mirror of the speed-up: the
accelerometer misses the nose-up tilt that slows the drone and keeps only the drag tilt, so it even reads
slightly nose-down (lesson §3).

> [!TASK]
> Write `TURN_TRUE_BANK_DEG` and `TURN_ACCEL_ROLL_DEG`: the true roll and the accelerometer's roll in the
> turn at t ≈ 99.8 s. (Not exactly 0: a 1-second average still carries some vibration, and the simulated
> drone wobbles about 1°.) `EXPLAIN_TURN`: why does the accelerometer report that (which force does it feel, and
> where does that force point in a coordinated turn)?

<details><summary>Stuck? Hints</summary>

1. `roll = np.arctan2(ay, az)`; the pitch needs a minus sign and `np.hypot(ay, az)` (lesson §3).
2. ✘ "the pitch has the wrong sign": ROS pitch is positive nose **down**, and a nose-down drone reads a
   negative `ax`.
3. ✘ "only length-1 arrays can be converted": you used `math.atan2`; use `np.arctan2`.
4. ✘ "these are degrees": the function returns radians (np.arctan2 already does).
5. ✘ the roll-60° line fails but the others pass: the pitch denominator is `np.hypot(ay, az)`, not `az`.
</details>

> [!TIP] 🏅 End of session 1 — Drift hunter
> Press **✔ Check my work**. When the checks of TODO 1–2 and Steps 1–3 pass (checks 1–4; the others are
> session 2), you earn the **Drift hunter** badge. If the class session ends here, stop here.

## Session 2 — Attitude engineer (about 2 h; 2 h 30 if quaternions are rusty)

Read lesson §4–§6 first.

## Step 4 — The complementary filter, and your choice of τ (TODO 3)

**TODO 3** `complementary(q0, t_s, gyro_rad_s, accel_mps2, tau_s)`: lesson §4, "In three dimensions". Each
step has two parts: the gyro step of TODO 1, then the gravity step.

> [!TASK]
> **Before you code**, trace the docstring example by hand (lesson §4, "one gravity step", shows the method with
> other numbers): τ = 1.5 s, dt = 0.5 s, the estimate is level and gravity says 30° right wing down. What are α
> and 1 − α? Write `TRACE_FIRST_ROLL_DEG`: the roll (degrees) after the first step.

<details><summary>🧰 numpy: the cross product and an angle from atan2</summary>

```python
a = np.array([0.0, 0.6, 0.8]); up = np.array([0.0, 0.0, 1.0])
np.cross(a, up)                           # array([0.6, 0. , 0. ]) — at right angles to both
s = float(np.linalg.norm(np.cross(a, up))); c = float(a @ up)
math.degrees(math.atan2(s, c))            # 36.87 — the angle between a and up (safer than acos near 0°)
```
</details>

```bash
python3 run_imu.py test
```

**Your role: the engineer who chooses τ for NAVERA Lite.** `tau` runs your filter on the whole flight for
seven values of τ, with the raw gyro (bias included, on purpose) and the accelerometer fooled in every
turn and speed change.

> [!TASK]
> **Predict** (`PREDICT_TAU`): which τ of 0.3, 1, 3, 10, 30, 100, 300 s will give the smallest tilt error?
> Why? Then (about 20 s):

```bash
python3 run_imu.py tau
```

Open `out/tau.png`.

> [!TASK]
> Write `BEST_TAU_S` and `BEST_TILT_RMS_DEG` (the "tilt RMS" column). `EXPLAIN_TAU`: what goes wrong with a
> small τ, and with a large τ, and why is the best τ in between? Use the table: which errors grow at each end?

> [!QUESTION] Check one number
> Your pad bias on x is about 0.064 °/s, so b·τ at τ = 300 s would be about 19°. The table says 2.7°. Look at
> `out/gyro.png` from Step 2 (the roll error changes sign at the turns): why is the large-τ end so gentle on
> *this* flight? (Lesson §4, "b·τ is a worst case".)

<details><summary>Read this after you wrote EXPLAIN_TAU</summary>
A body-axis bias turns with the drone: after each 180° turn it tilts the estimate the other way, so over
this flight it partly cancels; and with τ = 300 s the filter never settles in 5 minutes, so b·τ is never
reached. On a long straight flight the large-τ end would be much worse. The runs also start from the true
attitude, so the other cost of a large τ (forgetting a wrong start slowly) does not show here: Going further
shows it.
</details>

<details><summary>Stuck? Hints, one at a time</summary>

1. Copy your loop of TODO 1 (gyro step). After it, still inside the loop, the gravity step.
2. `f = accel[k]`; skip the gravity step if `np.linalg.norm(f)` is 0. `seen_up = q_rotate(q, f / norm)`.
3. `axis = np.cross(seen_up, (0, 0, 1))`; `s = np.linalg.norm(axis)`; if `s` is (almost) 0 there is nothing
   to correct. Otherwise `error = math.atan2(s, seen_up[2])`, `alpha = tau_s / (tau_s + dt)`.
4. The nudge is `q_from_axis_angle(axis, …)` by gravity's share of the error. Which side of `q` does it go,
   and why? (Lesson §4, Common wrong ideas, 3rd bullet.) Normalise, store in `out[k]`.
5. ✘ "α and 1 − α are swapped": gravity gets the small share, 1 − α. ✘ "the roll went the WRONG way": the
   axis is `seen_up × up`, in that order. ✘ "the heading moved": the nudge multiplies on the left.
   ✘ "7.16° instead of 7.5°": you used s = |seen_up × up| (the sine) as the angle; use
   `error = math.atan2(s, seen_up[2])`.
6. ✘ "seen_up is exactly up" or ✘ "f = (0, 0, 0)", or `tau` stops with "nan/inf from row …": a division by a
   zero length — the skips of hints 2 and 3 are missing. They are not optional: a level drone at rest, or a
   free-fall sample, happens in real data.
7. Still stuck? The nudge line is `q = q_mul(q_from_axis_angle(axis, (1 - alpha) * error), q)`.
</details>

## Step 5 — A compass that knows where true north is (TODO 4, TODO 5)

**TODO 4** `mag_heading(mag_uT, roll_rad, pitch_rad)`: lesson §5, tilt compensation then atan2 in **FLU**.
**TODO 5** `true_heading(mag_heading_deg, declination_deg)`.

```bash
python3 run_imu.py test
```

```bash
python3 run_imu.py compass
```

It prints the declination at the log's place (from the given `declination_deg`, the WMM), then your
compass three ways: without tilt compensation, compensated with the **true** roll and pitch, and with your
accelerometer's (Step 3). Open `out/compass.png`.

> [!TASK]
> Write `DECLINATION_DEG`, `COMPASS_NO_TILT_RMS_DEG` and `COMPASS_TILT_RMS_DEG` (the **true**-heading RMS,
> right-hand column: no compensation, and compensated with the TRUE tilt). `EXPLAIN_COMPASS`: why does the
> compass need the tilt? (Lesson §5: the field near Monastir dips 50.5°.)

A boat navigator in **Cape Town** on 15 October 2026 (lat −33.92, lon 18.42, decimal year 2026.79) forgets
the declination and steers 5 km in a straight line by a magnetic compass. How far to the side of the
intended track does she end? Get D with the given function:

```bash
python3 -c "from navera_lite.imu import declination_deg; print(declination_deg(-33.92, 18.42, 2026.79))"
```

> [!TASK]
> `CAPE_TOWN_SIDE_M`: the distance to the side, in metres (lesson §5's London example shows how).

<details><summary>Stuck? Hints</summary>

1. `m_level = rot_y(pitch_rad) @ rot_x(roll_rad) @ np.asarray(mag_uT, dtype=float)`, then
   `math.degrees(math.atan2(m_level[1], m_level[0])) % 360.0`.
2. ✘ "270° is the mirror image": in FLU, y is LEFT: atan2(y, x), not atan2(−y, x).
3. ✘ "23.7° = no tilt compensation": you took atan2 of the raw field. ✘ the tilted line fails but the level
   one passes, by a little: the order — the roll is undone first, so `rot_x` is next to the vector.
4. `true_heading`: ✘ "you subtracted the declination": true = magnetic + D. Keep the result in [0, 360).
5. Cape Town: D is negative; the distance to the side is 5000 · sin(|D|), with D in **degrees**:
   `math.sin(math.radians(abs(D)))`. 4976 m means sin was given degrees as if they were radians.
</details>

## Step 6 — True north for a whole attitude (TODO 6)

The log also has the IMU chip's own attitude (`chip_qx … chip_qw`), referenced to magnetic north, like the
BNO085's (NAVERA's item IMU-3). **TODO 6** `q_true_north(q_mag, declination_deg)`: lesson §5, the last
formula. Left or right? The `test` line "banked 30°" tells them apart; a level drone cannot.

```bash
python3 run_imu.py test
```

```bash
python3 run_imu.py compass
```

> [!TASK]
> Write `CHIP_MEAN_ERR_DEG`: the chip's mean heading error **as delivered** (before your correction).
> `EXPLAIN_NORTH`: why is it about that number? Why does `q_true_north` multiply on the **left**, and what
> would multiplying on the right do?

<details><summary>Stuck? Hints</summary>

1. Two parts: the turn of the world, `q_from_axis_angle` about Up `(0.0, 0.0, 1.0)` by −D (in radians); then
   one `q_mul` with `q_mag`. Which one comes first in `q_mul`? (Lesson §5.)
2. ✘ "you multiplied on the RIGHT": `q_mul(turn, q_mag)`, the turn first. ✘ "the wrong sign": the yaw
   decreases by D. ✘ "D is in degrees": `math.radians`.
</details>

## Step 7 — The frozen IMU (TODO 7)

`/data/academy/17-imu/imu_frozen.csv` is 20 s of a drone sitting on its pad: the same nine columns as the
flight log, one sample every 20 ms. Somewhere in it the chip stops answering and the library keeps handing
back its last report.

**TODO 7** `StaleDetector.update(sample)` in `imu.py`: the least guided TODO. Read the class first: `__init__`
is given and keeps `self.max_repeat`, `self.last` and `self.repeats` for you. The docstring of `update` gives
the goal and an example. Trace the example by hand first: for each of the six samples, what are `self.last`,
`self.repeats` and the result? (🧰 box of lesson §6.)

```bash
python3 run_imu.py test
```

```bash
python3 run_imu.py stale
```

> [!TASK]
> **Predict** (`PREDICT_STALE`): NAVERA uses 50 repeats (1 s at 50 Hz). Would 5 (0.1 s, ten times faster) be
> better? What will a detector with `max_repeat = 5` do on this file? Then:

```bash
python3 run_imu.py stale 5
```

Surprised? Look at the file around t = 5 s:

```bash
sed -n 245,262p /data/academy/17-imu/imu_frozen.csv
```

> [!TASK]
> Write `FROZEN_T_S` (max_repeat 50) and `SMALL_N_T_S` (max_repeat 5): the first time each detector says
> "frozen". `EXPLAIN_STALE`: why does a live sensor never repeat a whole sample exactly? Why are the fresh
> timestamps no proof? Why 50 and not 5?

<details><summary>Stuck? Hints</summary>

1. Turn the sample into something you can compare: `s = tuple(float(v) for v in sample)`.
2. Two cases: `s` equals `self.last` (one more repeat), or not (remember `s`, the count starts again at 0).
3. Then one comparison decides the answer. Check it on the docstring's trace: the 3rd sample (the 2nd
   repeat) is the first True.
4. ✘ "one sample too late/early": compare your trace with the docstring's list. ✘ "it says True for (1, 6)
   after (1, 5)": the count must start again, and the whole tuple is compared. Two bugs at once? The test line
   prints what each sample should give: trace `self.last` and `self.repeats` after each sample.
</details>

## Step 8 — The attitude memo

Write [report.md](file:./report.md) (150–350 words, your own words, keep the three headings): what the
gyroscope alone does and what the pad bias buys; the τ you choose for NAVERA Lite, with the measured trade-off;
the compass, true north, and how you trust the data. Quote your numbers with their units.

> [!TASK]
> report.md has the three headings, 150–350 words, and quotes the best τ (in s) with its tilt RMS (in °), and
> the declination near Monastir (in °).

## Step 9 — Check, then look back

Press **✔ Check my work**: it tests your functions on rates, attitudes, fields and sample streams they have
never seen. When every check passes, you earn the **Attitude engineer** badge. Then look back, without the
lesson:

1. Explain to a colleague, in three sentences, why a drone needs both a gyroscope and an accelerometer.
2. Which of your predictions was the most wrong? What did you assume?
3. Your τ was chosen on one simulated flight. What would you need before you trust it on a real drone?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **A wrong start.** `python3 run_imu.py tau 10` starts every run with a 10° roll error and saves `out/tau_wrong_start.png`
  (your `out/tau.png` is kept), like a drone that took off from a sloping pad with a wrong initial tilt. How does the table change at the large-τ end? Why?
- **Why does the roll error flip?** In `out/gyro.png` the gyro-alone roll error reverses at the big turns.
  Rotate the pad bias (0.064, −0.032) °/s from the body into the world frame for heading 0° and 180°.

- **The filter's tilt for the compass.** `python3 run_imu.py compass 30` adds a line compensated with your
  filter's tilt. Where does it fall between the true tilt and the accelerometer's? Why?
- **A heading filter.** Gravity cannot fix the heading, the compass can. Write a second complementary filter
  for the heading (gyro yaw rate + your `true_heading`), with the wrap-around: blend with
  `h + (1 − α)·wrap180(h_mag − h)`. Which τ gives the smallest heading RMS?
- **Gate the accelerometer.** In a turn |f| is larger than g (10.67 vs 9.81 m/s² in the lesson's example).
  Skip the gravity step when ||f| − g| > 0.5 m/s² and run `tau` again: does the best τ change?
- **Hard iron.** Add a constant (5, −3, 2) µT to `mx, my, mz` (a magnetised screw), watch the heading error,
  then estimate the offset back by fitting a sphere to the samples (least squares on |m − c|² = r²).
- **Fly your own parts.** This mission ships the course's `rotations.py`. Copy yours over it
  (`cp ../16-rotations/navera_lite/rotations.py navera_lite/`) and run
  `python3 -m pytest -q navera_lite/tests` and `python3 run_imu.py test`.
