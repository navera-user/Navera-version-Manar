# Lab 1 — Find your position, then fool yourself

**Goal:** run your first commands on the NAVERA computer, then write your own small position finder
in Python. You make it work, break it with a wrong clock, repair it, fool it with a spoofer, and
write NAVERA's jump gate.
**Time:** about 2 h 30 for this lab if Python is fresh in your mind, up to 4 h if it is not. Both
are normal.

Your files (open in the **📝 Code** tab):

- [beacons.py](file:./beacons.py): **your code**. Seven small functions, `TODO 1` to `TODO 7`.
- [answers.py](file:./answers.py): your answers, predictions and explanations.
- [where_am_i.py](file:./where_am_i.py): runs your functions on the lab's situations and draws
  pictures. You do not change it.

> [!NOTE]
> **Predict, then run.** Several steps ask you to write a guess in `answers.py` **before** you run
> something. A wrong guess is not a problem, and it is not graded right or wrong. It is how you
> notice what surprised you, and that is where you learn.

## Step 1 — The computer

Click the **⌨️ Terminal** tab. The line `student@navera:~/lessons/01-welcome$` is the **prompt**:
user `student`, computer `navera`, current folder `~/lessons/01-welcome`. Run these commands one by
one (▶ Run, or type them and press `Enter`):

```bash
whoami
```

```bash
uname -m
```

```bash
nproc
```

```bash
python3 --version
```

`uname -m` prints the type of processor: `aarch64` is 64-bit ARM, the processor of the NVIDIA
Jetson inside a NAVERA box (most laptops say `x86_64`). `nproc` prints the number of processor
cores you can use.

> [!TASK]
> In `answers.py`, write `ARCH` (text, **in quotes**: `ARCH = "aarch64"`) and `CPU_CORES` (a number,
> no quotes).

## Step 2 — The mission card (your first Python edit)

```bash
python3 hello_navera.py
```

In [hello_navera.py](file:./hello_navera.py), replace the three `"???"` **between the quotes** with
your name, a vehicle (`drone`, `car`, `boat` or `robot`) and your home town. Save with `Ctrl+S` and
run it again.

> [!WARNING]
> Keep the quotes. If you delete one, Python stops with
> `SyntaxError: unterminated string literal (detected at line 4)`. The line number tells you where
> to look.

## Step 3 — NAVERA's rules, in your copy

`~/navera` is your own copy of NAVERA. The arbiter's settings are in one file. Open
[estimator_params.yaml](file:navera/navera_estimator/navera_estimator/config/estimator_params.yaml)
in the editor and read it. Lines starting with `#` are comments that explain each setting.

Find the three settings of the course: the top speed (`max_speed_mps`), the jump margin
(`gps_jump_margin_m`) and how long a GPS fix stays fresh (`gps_timeout_s`). You can also let the
terminal find them (`grep` prints the lines that contain a word; lesson 2 teaches it):

```bash
grep -n "max_speed_mps\|gps_jump_margin_m\|gps_timeout_s" ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml
```

`gps_timeout_s` is the meaning of **fresh** (course §4): a GPS fix older than this is too old,
and the arbiter stops using it.

> [!TASK]
> Write `V_MAX_MPS`, `MARGIN_M` and `GPS_TIMEOUT_S` in `answers.py`. You will use the first two
> in Step 9.

## Step 4 — Your first two functions: distance and mismatch

A **function** takes inputs and **returns** a result. Here is one that is *not* in your file, as an
example:

```python
def middle(p, q):
    """The point halfway between p = (x1, y1) and q = (x2, y2)."""
    x = (p[0] + q[0]) / 2        # p[0] is the x of p, p[1] is its y
    y = (p[1] + q[1]) / 2
    return (x, y)

print(middle((0, 0), (4, 2)))    # (2.0, 1.0)
```

Open [beacons.py](file:./beacons.py).

**TODO 1 — `distance(p, q)`.** Use Pythagoras from the course (§1). `math.sqrt(25)` gives `5.0`,
and `a ** 2` is `a` squared.

**TODO 2 — `mismatch(p, beacons, measured, bias=0.0)`.** Follow the three numbered steps of the
course (§1, "How good is a guess?"). To walk through two lists together, use `zip`:

```python
for beacon, m in zip(beacons, measured):     # beacon = (0, 0) and m = 5.0, then the next pair…
    print(beacon, m)
```

The `bias=0.0` in `def mismatch(p, beacons, measured, bias=0.0)` is a **default value**: if you
call `mismatch(p, beacons, measured)` without a bias, Python uses 0.0.

Before you run it, check the worked example of the course by hand: at `(4, 4)` the mismatch is
1.409. Your function must give the same. Then test:

```bash
python3 where_am_i.py test
```

The first five lines must show ✔. The other ✘ lines are the next TODOs.

A number like `1.08e-07` means 1.08 × 10⁻⁷ = 0.000 000 108: almost exactly 0. That is fine (the
distances in the course are rounded to 3 decimals).

<details><summary>Stuck on mismatch? Hints, one at a time</summary>

1. Start with `total = 0.0` **before** the loop.
2. In the loop: what you *would* measure from `p` is `distance(p, beacon) + bias`.
3. Subtract `m`, square the difference, add it to `total`.
4. After the loop (not inside it!), `return total`.
5. You get 0.431 instead of 1.409? Look at the course table: 0.431 is beacon A alone. Your
   `return` is inside the loop, so the function stops after the first beacon.
</details>

## Step 5 — Where am I?

**TODO 3 — `find_position(beacons, measured)`.** Try every point `(x, y)` of the grid and keep the
one with the smallest mismatch. Go back to the course example "Which number has a square closest to
20?": your function is the same idea, with **two** loops (one for `x`, one inside it for `y`) and
`mismatch` instead of `err`.

```bash
python3 where_am_i.py test
```

```bash
python3 where_am_i.py clean
```

You should find `(3.0, 4.0)` with a mismatch of 0. Open the picture `out/clean.png` in the
📝 Code tab (file list on the left): the three circles meet where you found yourself.

<details><summary>Stuck? Hints, one at a time</summary>

1. **Before** both loops, two variables like in the course example: `best = None` and
   `best_m = None`.
2. `for i in range(101):` then, inside it, `for j in range(101):`. Then `p = (i / 10, j / 10)`.
3. Inside the two loops: compute the mismatch of `p`; if `best_m is None` or it is smaller than
   `best_m`, remember `p` and its mismatch.
4. After both loops (not indented under them), `return best`.
5. Your x is always 0.0, or always 10.0? Your `return`, or your `best = None`, is inside a loop.
</details>

## Step 6 — A clock 1 µs fast

Now the receiver's clock is 1 µs fast: every distance is 0.3 km too long (course §2).

> [!TASK]
> **Predict first.** In `PREDICT_CLOCK`, write where you think `find_position` will land now: still
> (3, 4), or somewhere else? Why?

```bash
python3 where_am_i.py clock
```

Look at part 1) and at `out/clock.png`. Write `CLOCK_ERROR_M`, the distance from the true position
in metres. The best point is wrong, **and** even the best mismatch is not 0: no point explains the
measurements.

Why 141 m and not 300 m? The search moves the point so that the three too-big circles fit as well
as possible; part of the extra 0.3 km cancels out between the three directions. With a larger clock
error, the position error grows.

**TODO 4 — `find_position_and_bias(beacons, measured)`.** Make the bias a third unknown: a third
loop inside the other two, over `k` in `range(21)` with `bias = k / 20` (0.00, 0.05, … 1.00). Return
`(x, y, bias)`: three numbers, not a point and a number. It takes a few seconds.

<details><summary>Stuck? Hints, one at a time</summary>

1. Start from a copy of your `find_position`.
2. Inside the `j` loop, add `for k in range(21):` and `bias = k / 20`.
3. Give the bias to mismatch as its 4th input: `mismatch(p, beacons, measured, bias)`. If you
   forget it, the bias found is always 0.0.
4. Remember the best `(x, y, bias)` together, and return `(best_x, best_y, best_bias)`, or the three
   values of one tuple.
</details>

```bash
python3 where_am_i.py clock
```

Part 2) now finds the right place, and the clock error.

> [!TASK]
> In `EXPLAIN_CLOCK`, explain why the third unknown fixed it. Use the words *bias* and *every
> distance* (or *all distances*).

## Step 7 — Two beacons are not enough

The clock is still unknown. What if beacon C is out of range, and you only hear A and B?

> [!TASK]
> **Predict first.** In `PREDICT_TWO`: with only A and B, how many guesses `(x, y, bias)` will
> explain the measurements? One? A few? Many?

```bash
python3 where_am_i.py two
```

It counts the guesses that fit almost perfectly: first with A, B and C, then with A and B only.
Open `out/two.png`: every blue dot is a position that fits, each one with **its own** bias (the
circles are drawn without bias, so the dots are not on them). With a finer grid there would be
even more dots: a whole line of positions fits.

> [!TASK]
> In `EXPLAIN_TWO`, explain the result by counting **unknowns** and **measurements**. Then say how
> many satellites a real GPS receiver needs, and why.

## Step 8 — Be the spoofer

You are at (3, 4). A spoofer wants your receiver to believe it is at **(7, 2)**. To do that, it
sends exactly the pseudoranges a receiver at (7, 2) would measure.

**TODO 5 — `spoof_measurements(beacons, fake_position, bias)`.** Return the list of what a receiver
at `fake_position` would measure: for each beacon, its distance to the fake position plus the bias.
(The spoofer can choose any bias: your receiver will simply find it as "the clock error". Here it
chooses 0.3 km.)

To build a list in a loop, start empty and **append** one value each time:

```python
squares = []
for n in [1, 2, 3]:
    squares.append(n * n)
print(squares)          # [1, 4, 9]
```

<details><summary>Stuck? Hints, one at a time</summary>

1. `result = []` before the loop.
2. `for beacon in beacons:` and, inside, `result.append(...)` with the distance from
   `fake_position` to `beacon`, plus `bias`.
3. After the loop, `return result`.
</details>

> [!TASK]
> **Predict first.** In `PREDICT_SPOOF`: will your receiver notice something is wrong? What could
> it look at?

```bash
python3 where_am_i.py spoof
```

Look at the mismatch and at `out/spoof.png`.

> [!TASK]
> In `EXPLAIN_SPOOF`, explain why the mismatch is 0 at the fake position, and what this means for a
> real GPS receiver.

## Step 9 — NAVERA's jump gate

Now you are NAVERA's arbiter. Positions are in **metres** here, time in seconds.

**TODO 6 — `gate_ok(last, new, elapsed_s, v_max_mps, margin_m)`.** The rule of the course (§4):
accept the new fix if its distance to the last trusted fix is at most `v_max × elapsed + margin`.
Your `distance` function works in metres too. Return `True` or `False`.

**TODO 7 — `count_refused(fixes, dt_s, v_max_mps, margin_m)`.** Walk through the fixes like the
arbiter:

1. Before the loop: `last` = the first fix (trusted), the time since it = 0, refused = 0.
2. Loop over the **other** fixes: `fixes[1:]` is the list without its first element.
3. For each fix, the time since `last` grows by `dt_s`. Ask `gate_ok`.
4. Accepted: this fix becomes `last`, and the time goes back to 0.
5. Refused: add 1 to refused (`last` does not change, so the time keeps growing).
6. After the loop, return refused.

Check yourself on the course figure: the 500 m jump gives 4. You get 3? You forgot step 4: the time
must go back to 0 when a fix is accepted.

```bash
python3 where_am_i.py test
```

Two attacks, with NAVERA's real settings (your `V_MAX_MPS` and `MARGIN_M`), one fix per second:
**A)** the GPS jumps **300 m** and stays there; **B)** the GPS is dragged 20 m further every second,
for a minute.

> [!TASK]
> **Predict first.** In `PREDICT_GATE`: how many fixes of attack A will be refused? And of attack B?
> (Use the gate formula and the course figure, with 300 m instead of 500 m.)

```bash
python3 where_am_i.py gate
```

> [!TASK]
> Write `JUMP_REFUSED` and `DRIFT_REFUSED`. Then in `EXPLAIN_GATE`: why can't the gate alone stop
> these attacks, and what does NAVERA add (course §4)?

## Step 10 — Threat analysis

> [!TASK]
> Fill [threats.md](file:./threats.md): for **outage**, **jamming**, **spoofing** and
> **meaconing**, 2–4 sentences each (at least 100 words in total). Use at least one number from your
> own runs (for example what the spoofer achieved, or what the gate did).

## Step 11 — Check your work

Press **✔ Check my work** at the bottom left. The check also tests your functions on **other**
beacons and numbers than the lab's, so a function must really work, not only on the examples. Each
red line says what is wrong and gives a hint. Fix, save, check again — as many times as you like.

## Going further (optional)

- **A real receiver in 3-D.** [gnss_fix.py](file:./gnss_fix.py) is a receiver on the coast at
  Sousse with 8 satellites: x, y, z and the clock bias, four unknowns. It does not try a grid: it
  improves a guess with algebra (course §2, note). Run `python3 gnss_fix.py`, then set
  `USE_SATELLITES` to 6, 5, 4, 3. What happens at 3? Why is the "residual" exactly 0 at 4? Then set
  `SPOOF_EAST_M = 500.0`: do you recognise your Step 8?
- **Your own spoofer path.** In `where_am_i.py`, attack B drags 20 m per second. Find the slowest
  speed at which the gate refuses at least one fix. Explain the number with `v_max` and `margin`.
- **A finer grid.** Change your `find_position` to steps of 0.01 km. How much longer does it take?
  Why would a grid be impossible in 3-D with a clock at 1 m steps?
