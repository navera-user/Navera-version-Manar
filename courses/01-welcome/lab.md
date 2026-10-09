# Lab 1 — Build a receiver, break it, attack it

**Goal:** write a small position solver from scratch, watch a bad clock break it, repair it, spoof it,
then play the attacker against NAVERA's jump gate and measure the hole in its defence.
**Time:** 2 h 30 to 4 h, depending on how fresh your Python is.

Your files (📝 Code tab):

- [beacons.py](file:./beacons.py) — **your solver**: seven functions, `TODO 1` to `TODO 7`.
- [answers.py](file:./answers.py) — your predictions, results and explanations.
- [where_am_i.py](file:./where_am_i.py) — runs your functions on the lab's scenarios and draws
  them. You do not edit it.

| Lesson | Lab | You write |
|---|---|---|
| §2 Least squares | Steps 4–5 | `distance`, `mismatch`, `find_position` |
| §3 The clock | Steps 6–7 | `find_position_and_bias` |
| §4 Attacking GPS | Step 8 | `spoof_measurements` |
| §5 The jump gate | Steps 9–10 | `gate_ok`, `count_refused`, the attacker's challenge |
| §5 The arbiter | Step 11 | (a decision, no code) |

> [!NOTE]
> **Predict, then run.** Several steps ask for a written guess (`PREDICT_…`) **before** you run. It is
> never marked right or wrong. Being wrong and finding out why is the point.

## Step 1 — The NAVERA computer

The **⌨️ Terminal** shows a prompt like `student@navera:~/lessons/01-welcome$` (user, computer,
current folder). Run:

```bash
whoami
```

```bash
uname -m
```

```bash
nproc
```

`aarch64` is 64-bit ARM, the processor family of the NVIDIA Jetson in a NAVERA box (laptops are
usually `x86_64`); `nproc` counts the CPU cores you may use.

> [!TASK]
> In `answers.py`: `ARCH` (text, in quotes) and `CPU_CORES` (a number, no quotes).

## Step 2 — First edit

Replace the three `"???"` in [hello_navera.py](file:./hello_navera.py) (keep the quotes), save with
`Ctrl+S`, and run it. A deleted quote gives `SyntaxError: unterminated string literal (detected at
line 4)`: the line number tells you where to look.

```bash
python3 hello_navera.py
```

## Step 3 — Read NAVERA's rules

Open [estimator_params.yaml](file:navera/navera_estimator/navera_estimator/config/estimator_params.yaml)
(the `#` lines explain each setting), or search it from the terminal:

```bash
grep -n "max_speed_mps\|gps_jump_margin_m\|gps_timeout_s" ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml
```

> [!TASK]
> Write `V_MAX_MPS`, `MARGIN_M` and `GPS_TIMEOUT_S`. Steps 9–11 use them.

## Step 4 — Residuals in Python

🧰 A function, a point, a power, a square root, two lists side by side:

```python
import math

def middle(p, q):                 # p and q are points: p[0] is x, p[1] is y
    return ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)

print(middle((0, 0), (4, 2)), 3 ** 2, math.sqrt(25))      # (2.0, 1.0) 9 5.0

for beacon, m in zip([(0, 0), (10, 0)], [5.0, 8.1]):      # zip walks two lists together
    print(beacon, m)
```

`def f(a, b=0.0)` gives `b` a **default**: `f(1)` means `f(1, 0.0)`.

In [beacons.py](file:./beacons.py): **TODO 1** `distance(p, q)` and **TODO 2**
`mismatch(p, beacons, measured, bias=0.0)` (lesson §2; with a bias, the predicted range is
`distance + bias`, lesson §3). Your result must match the lesson's worked example (1.409 at (4, 4)).

```bash
python3 where_am_i.py test
```

The first five lines must be ✔. (`1.08e-07` means 0.000000108: zero up to rounding.)

<details><summary>Stuck? Hints</summary>

1. Accumulate in a variable created **before** the loop; return it **after** the loop.
2. 0.431 instead of 1.409 is beacon A alone: your `return` is inside the loop. 0.253 is beacon C
   alone: your total is reset inside the loop.
3. `NameError: name 'sqrt'`: write `math.sqrt`, with `import math` at the top.
</details>

## Step 5 — Solve by search

**TODO 3** `find_position(beacons, measured)`: grid search as in lesson §3, in 2-D (the docstring
gives the grid).

```bash
python3 where_am_i.py clean
```

You should land on `(3.0, 4.0)`; open `out/clean.png`.

<details><summary>Stuck? Hints</summary>

1. `best` and `best_m` start as `None`, **before** both loops.
2. The inner loop sits inside the outer one; `p = (i / 10, j / 10)`.
3. x always 0.0 or 10.0? A `return` or a `best = None` sits inside a loop.
</details>

## Step 6 — A clock 1 µs ahead

The ranges are now pseudoranges, all 0.3 km too long.

> [!TASK]
> **Predict** (`PREDICT_CLOCK`): where does `find_position` land, and what will its minimum mismatch
> be?

```bash
python3 where_am_i.py clock
```

Write `CLOCK_ERROR_M` (part 1, "distance from the true position").

Why about 140 m, not 300 m? You are **inside** the beacon triangle, so a uniform +0.3 km on the three
ranges mostly cancels: the best continuous point is about 115 m away, and your 0.1 km grid can only
reach (3.1, 4.1), 141 m away. Outside the triangle it would not cancel so well.

**TODO 4** `find_position_and_bias`: add `b` as a third unknown (lesson §3). Return `(x, y, bias)`,
three numbers. Run `clock` again: part 2 must find the true position and the clock error.

<details><summary>Stuck? Hints</summary>

1. A third loop inside the other two, with the same trick as `x = i / 10`, for 21 biases 0.00 … 1.00.
2. Give the bias to `mismatch` as its 4th argument; otherwise the bias found is always 0.
3. `((3.0, 4.0), 0.3)` is a point and a number: return three numbers.
</details>

> [!TASK]
> `EXPLAIN_CLOCK`: why does adding the bias as an unknown repair the solution?

## Step 7 — Count the unknowns

Same clock error, but beacon C is out of range.

> [!TASK]
> **Predict** (`PREDICT_TWO`): with only A and B, how many `(x, y, bias)` fit almost perfectly?

```bash
python3 where_am_i.py two
```

Each blue dot in `out/two.png` fits, with **its own** bias; with a finer grid you would get a whole
curve. (Only y between 0 and 10 is searched, so the mirror branch below A–B is not shown.)

> [!TASK]
> `EXPLAIN_TWO`: explain the count with unknowns vs measurements, and say how many satellites a real
> receiver needs.

## Step 8 — Be the spoofer

You are at (3, 4). Make the receiver believe (7, 2). **TODO 5** `spoof_measurements(beacons,
fake_position, bias)` returns the pseudoranges a receiver at the fake position would measure, one per
beacon, in a list. The spoofer may pick any bias; it uses 0.3 km here.

🧰 `values = []`, then `values.append(x)` inside a loop, builds a list.

> [!TASK]
> **Predict** (`PREDICT_SPOOF`): what will your solver find, and with what mismatch? Would the
> receiver notice anything?

```bash
python3 where_am_i.py spoof
```

> [!TASK]
> `EXPLAIN_SPOOF`: why is the mismatch 0 at the fake position, and what does this mean for a real
> receiver?

<details><summary>Now read: why spoofing is so dangerous (only after you ran it)</summary>

The fake pseudoranges are <b>consistent</b>: they were computed for one point, so that point explains
them perfectly and the mismatch is 0. A simple receiver, like those of most small drones, has no alarm
against a good spoofer. Better receivers have partial defences: they watch the signal power, use
several antennas to see where the signals come from, or check digital signatures (Galileo OSNMA). They
cost more, and each has limits. A cross-check with a sensor that does not use radio at all (a camera,
the stars, the vehicle's own motion) is not fooled by a radio attack: that is NAVERA's approach.

Two wrong ideas to drop: "a mismatch of 0 proves the position" (it only proves consistency); "more
satellites protect" (a spoofer fakes them all; more systems and frequencies only make it harder).
</details>

## Step 9 — Write the jump gate

Positions are now in **metres**. **TODO 6** `gate_ok(last, new, elapsed_s, v_max_mps, margin_m)`:
True if accepted (lesson §5). 🧰 A comparison is already a boolean: `return a <= b` returns True or
False. If you use `if`, every path needs a `return`.

**TODO 7** `count_refused(fixes, dt_s, v_max_mps, margin_m)` is the least guided function of the lab.
First redo the lesson's 7-row table by hand, then make your code do exactly that. Its docstring
example is that table (5 refused).

```bash
python3 where_am_i.py test
```

<details><summary>Stuck? Hints</summary>

1. What must you remember from one fix to the next? Create those variables before the loop.
2. Compare a wrong count with your hand table, row by row.
3. 4 instead of 5: `elapsed` does not restart after an accept, or it starts one step too high.
   2: you compare with the previous fix instead of the last trusted one, or you count the accepted
   fixes. 6 or 7: you update `elapsed` after the test, or you also restart it after a refusal.
</details>

Two attacks with NAVERA's settings, one fix per second: **A)** a 300 m jump that stays; **B)** a drag
of 20 m per second for a minute.

> [!TASK]
> **Predict** (`PREDICT_GATE`): how many fixes are refused in A, and in B?

```bash
python3 where_am_i.py gate
```

> [!TASK]
> Write `JUMP_REFUSED`, `DRIFT_REFUSED`, and `EXPLAIN_GATE`: why can't the gate alone stop these
> attacks, and what does NAVERA need to do better (lesson §5)?

## Step 10 — The attacker's challenge

You are now the attacker. NAVERA's settings, one GPS fix per second, a constant drag in a straight
line (the fake position moves the same distance every second). Goal: move the drone **as far as
possible in 60 s without a single refused fix**.

> [!TASK]
> Find `STEALTH_SPEED_MPS`, the highest drag speed (m/s, to the nearest whole number) that the gate
> never refuses, and `STEALTH_DISTANCE_M`, how far that drag moves the drone in 60 s. Prove it **with
> your code**: build drag lists like attack B and run your `count_refused` on that speed and on the
> next one (in a small script, or in `python3`).

Compare that speed with what a survey drone can really fly. This is the hole NAVERA must close with a
cross-check (missions 25–27).

## Step 11 — Be the arbiter

No code. It is 12:00:10. The last GPS fix arrived at 12:00:08, with an uncertainty of 35 m (the
receiver sees few satellites). Day vision is fresh, with a stated uncertainty of 8 m. Night vision is
fresh too.

> [!TASK]
> `ARBITER_SOURCE` (`"gps"`, `"day"`, `"night"`, `"celestial"` or `"none"`) and `ARBITER_STATE`
> (`"FIX"`, `"DEGRADED"` or `"NO_FIX"`). Careful: priority, not precision.

## Step 12 — Threat analysis

> [!TASK]
> Fill [threats.md](file:./threats.md): outage, jamming, spoofing, meaconing, in 2–4 sentences each
> (≥ 100 words in total), with at least one number from your own runs.

## Step 13 — Check, then look back

Press **✔ Check my work**. It also tests your functions on **other** beacons and numbers, so they
must really work. Then, without the lesson: what surprised you most? Could you explain to a friend in
three sentences why a receiver can be fooled without noticing?

## Going further (optional)

- **A real receiver.** [gnss_fix.py](file:./gnss_fix.py) solves x, y, z and b with 8 satellites near
  Sousse by Gauss–Newton (lesson §3). Run it, then set `USE_SATELLITES` to 6, 5, 4, 3. Why is the
  residual exactly 0 at 4? Set `SPOOF_EAST_M = 500.0` and compare with your Step 8.
- **Beat the grid.** Make `find_position` 100× faster with the same answer: a coarse grid (1 km),
  then a fine grid around the best point. When can coarse-to-fine fail?
- **Geometry.** Move beacon C to (10, 10) and repeat Step 6. Does the clock error hurt more or less
  outside the triangle? Link it to the "valley" of lesson §2.
