# Lab 1 — Build a receiver, break it, attack it, defend it

**Goal:** write a position solver (brute force, then Gauss–Newton), spoof it fully and partially, play
detective on a spoofed survey flight, and finish as attacker and defender of NAVERA's jump gate.
**Time:** 2 h 30 to 4 h (a strong programmer: about 2 h; up to 7 h if Python is new to you).
**Fast track:** if you know Python and numpy, skip every 🧰 box and every "Stuck?" box. Steps 1–2 should
take you under 10 minutes; if so, do "A smarter spoofer" from Going further right after Step 6.

Your files (📝 Code tab): [beacons.py](file:./beacons.py) (**your code**: nine functions, `TODO 1–9`),
[answers.py](file:./answers.py) (predictions, results, explanations), [where_am_i.py](file:./where_am_i.py)
(runs your functions on the scenarios and draws them; you don't edit it) and
[flight.csv](file:./flight.csv) (a simulated survey flight).

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | nothing: you watch a hijack |
| §2–§3 Least squares, brute force | Steps 1–2 | `distance`, `mismatch`, `find_position` |
| §3 Clock, Gauss–Newton | Steps 3–5 | `find_position_and_bias`, `gauss_newton` |
| §4 Attacking GPS | Step 6 | `spoof_measurements` |
| §5 Arbiter, gate, cross-check | Steps 7–10 | `gate_ok`, `count_refused`, `first_disagreement`, then your own experiments |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` is written **before** you run the step. It is never marked
> right or wrong; being wrong and finding out why is the point.

## Session 1 — Build & spoof (about 2 h)

## Step 0 — Hijack a position

Open the **⌨️ Terminal** tab. The prompt `student@navera:~/lessons/01-welcome$` tells you the user, the
computer and the current folder. Press **▶ Run** (or type the command and press `Enter`):

```bash
python3 where_am_i.py hijack
```

A ready-made receiver computes your position from three beacons. Then a spoofer switches on. Watch what
the receiver says, and open `out/hijack.png` in the 📝 Code tab.

No alarm, 4.5 km off, and the "mismatch" (how badly the signals disagree with the computed position)
stays exactly zero. Before you can defend against this, you need
to understand why. From Step 1 on, you build that receiver yourself.

## Step 1 — Residuals

<details><summary>🧰 Python refresher (open if needed)</summary>

```python
import math

def middle(p, q):                 # p and q are points: p[0] is x, p[1] is y
    return ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)

print(middle((0, 0), (4, 2)), 3 ** 2, math.sqrt(25))      # (2.0, 1.0) 9 5.0
for beacon, m in zip([(0, 0), (10, 0)], [5.0, 8.1]):      # zip walks two lists together
    print(beacon, m)
```

`def f(a, b=0.0)` gives `b` a default: `f(1)` means `f(1, 0.0)`.
</details>

**TODO 1** `distance` and **TODO 2** `mismatch` (lesson §2; with a bias the predicted range is
`distance + bias`, lesson §3). Your mismatch must give the lesson's 1.409 at (4, 4).

```bash
python3 where_am_i.py test
```

The first five lines must be ✔. (`1.08e-07` is zero up to rounding.)

<details><summary>Stuck? Hints</summary>

1. Accumulate in a variable created **before** the loop; return it **after** the loop.
2. 0.431 instead of 1.409 is beacon A alone: your `return` is inside the loop. 0.253 is beacon C
   alone: your total is reset inside the loop.
3. `NameError: name 'sqrt'`: write `math.sqrt`.
4. 1.08 at (3, 4) with bias 0.3 (= 3 × 0.6²): you add the bias instead of subtracting it. Brackets:
   `measured − (distance + bias)`.
</details>

## Step 2 — Brute force

**TODO 3** `find_position`: the grid search of lesson §3, in 2-D (the docstring gives the grid).

```bash
python3 where_am_i.py clean
```

<details><summary>Stuck? Hints</summary>

1. `best` and `best_m` start as `None`, **before** both loops; the inner loop sits inside the outer one.
2. x always 0.0 or 10.0? A `return` or a `best = None` sits inside a loop.
3. `TypeError: 'float' object cannot be interpreted as an integer`: `range` takes whole numbers only;
   use `for i in range(101):` and `x = i / 10`.
</details>

## Step 3 — A clock 1 µs ahead

> [!TASK]
> **Predict** (`PREDICT_CLOCK`): with pseudoranges 0.3 km too long, where does `find_position` land, and
> what is its minimum mismatch?

```bash
python3 where_am_i.py clock
```

Write `CLOCK_ERROR_M` (part 1). Before you open the box below, try to explain why it is far less than
300 m.

<details><summary>Open only after you ran it: why less than 300 m?</summary>
You are <b>inside</b> the beacon triangle: moving away from one beacon brings you closer to the others,
so a uniform +0.3 km on all three ranges mostly cancels. The continuous least-squares optimum is about
115 m away; the 0.1 km grid can only reach (3.1, 4.1), 141 m away. Outside the triangle it would not
cancel so well ("Going further").
</details>

**TODO 4** `find_position_and_bias`: the bias becomes a third unknown, searched on the docstring's grid.
Return three numbers. Run `clock` again: part 2 must find the true position and b = 0.3 km.
(`0.30000000000000004` is 0.3: computers store decimals with tiny rounding errors.)

<details><summary>Stuck? Hints</summary>

1. A third loop inside the other two; same integer trick as `x = i / 10`, for 21 biases 0.00 … 1.00.
2. Give the bias to `mismatch` as its 4th argument; otherwise the bias found is always 0.
3. `((3.0, 4.0), 0.3)` is a point and a number: return three numbers.
</details>

> [!TASK]
> `EXPLAIN_CLOCK`: why does adding the bias as an unknown repair the solution?

## Step 4 — Count the unknowns

> [!TASK]
> **Predict** (`PREDICT_TWO`): with beacon C out of range, how many `(x, y, bias)` fit almost
> perfectly?

```bash
python3 where_am_i.py two
```

Each blue dot in `out/two.png` fits, with its own bias. The plot shows only a short piece of the curve
(biases 0–1 km only), which is why it looks almost straight. Which curve is it? Subtract the two
pseudorange equations ρ_A = ‖p − A‖ + b and ρ_B = ‖p − B‖ + b: what happens to b? Which curve is the set
{p : ‖p − A‖ − ‖p − B‖ = ρ_A − ρ_B}? Check it on two blue dots with your `distance` (by calculator, or
`python3 -c "from beacons import distance; print(distance((2.9, 4.2), (0, 0)) - distance((2.9, 4.2), (10, 0)))"`;
expect agreement to
about 0.1 km only: the dots sit on a 0.1 km grid and fit only to a mismatch below 0.005).

<details><summary>Stuck? Hint</summary>
Remember the conics: an ellipse is where the <b>sum</b> of the distances to two fixed points is constant.
When the <b>difference</b> is constant, you get its sister curve, with two separate branches (a signed
difference, as here, gives one of them). (This is how
LORAN, a radio navigation system from the Second World War, found ships.)
</details>

> [!TASK]
> `EXPLAIN_TWO` (unknowns vs measurements; satellites needed by real GPS) and `CURVE` (one word).

## Step 5 — Gauss–Newton

**TODO 5** `gauss_newton(beacons, measured, guess, steps)`: lesson §3. At each step build `H` (one row
`[uₓ, u_y, 1]` per beacon) and `r` (measured − predicted), solve, update.

🧰 numpy in three lines:

```python
import numpy as np
H = np.array([[1.0, 0.0], [0.0, 2.0], [1.0, 1.0]]);  r = np.array([1.0, 2.0, 2.0])
delta, *_ = np.linalg.lstsq(H, r, rcond=None)        # least-squares solution of H · delta ≈ r
```

`lstsq` returns four things; `delta, *_ =` keeps the first and throws the others away.

Check your first step against the lesson's worked table:
`python3 -c "import beacons; print(beacons.gauss_newton([(0,0),(10,0),(0,10)], [5.3,8.362,7.008], (4,4,0), 1))"`
must give about (3.021, 3.997, 0.338). (`gn` below starts from (5, 5, 0), so it needs one step more than
the lesson.) Then:

```bash
python3 where_am_i.py gn
```

<details><summary>Stuck? Hints</summary>

1. Inside the step loop: two empty lists `H` and `r`, one row each per beacon, then one `lstsq`.
2. Sign check: `uₓ = (x − beacon_x) / d`; the residual is measured − (d + b).
3. Jumping away instead of converging? You add `−Δ`, or your residual has the opposite sign.
4. `operands could not be broadcast … (3,) (0,)`, `only length-1 arrays can be converted to Python
   scalars`, or the one-step check prints
   `(array([...]), array([]), 3)`: you wrote `delta = np.linalg.lstsq(...)` without `, *_`, so `delta`
   holds all four results.
</details>

<details><summary>Still stuck? An outline to fill in</summary>

```python
x, y, b = guess
for _ in range(steps):
    H, r = [], []
    for beacon, m in zip(beacons, measured):
        d = ...                      # distance from (x, y) to the beacon
        H.append([..., ..., 1.0])    # u_x, u_y, 1
        r.append(...)                # measured − (d + b)
    delta, *_ = np.linalg.lstsq(np.array(H), np.array(r), rcond=None)
    x, y, b = ..., ..., ...          # add the correction
return (x, y, b)
```
</details>

🧰 Scientific notation: `3.36e-05` is 0.0000336, still larger than `1e-6` = 0.000001.

> [!TASK]
> `GN_STEPS`: steps (from the `gn` table) until the mismatch is below 1e-6.

**How good is the geometry?** At the solution (3, 4), build `H` for A, B and C and compute
`HDOP = √((HᵀH)⁻¹ₓₓ + (HᵀH)⁻¹ᵧᵧ)` (lesson §3). Then move C to (10, 10), outside the triangle, and compute it
again.

🧰 `H = np.array(H)` (a list has no `.T`); `M = np.linalg.inv(H.T @ H)`; `HDOP = np.sqrt(M[0, 0] + M[1, 1])`
(the x and y entries of the diagonal, not the bias one). Expect a number between 1 and 2 inside the triangle.

> [!TASK]
> `HDOP_TRIANGLE` and `HDOP_OUTSIDE` (two decimals).

**Now break it on purpose.** Put three beacons on one line, (0, 0), (5, 0) and (10, 0), and build H at
the guess (4, 0) (b = 0); print `np.linalg.matrix_rank(np.array(H))`. Which column of H is all zeros?
That unknown is lost.

> [!TASK]
> `COLLINEAR_RANK`: the rank you found. `EXPLAIN_GN`: why is Gauss–Newton so much faster than brute
> force, what could make it fail, and what can it not determine with beacons on a line? Link the larger
> HDOP to the flatter valley of lesson §2.

## Step 6 — Be the spoofer

**TODO 6** `spoof_measurements(beacons, fake_position, bias)`: the pseudoranges a receiver at the fake
position would measure, one per beacon, in a list (`values = []`, then `values.append(…)`).

<details><summary>Stuck? Hints</summary>

1. One value per beacon: `distance(fake_position, beacon) + bias`.
2. Only one value back? Your `return` is inside the loop.
</details>

> [!TASK]
> **Predict** (`PREDICT_SPOOF`): Step 0 showed a ready-made receiver fooled. Will *your* Gauss–Newton
> be fooled the same way by a spoofer faking (7, 2) on all three beacons, and what clock bias will it
> report?

```bash
python3 where_am_i.py spoof
```

> [!TASK]
> `EXPLAIN_SPOOF`: why is the mismatch 0 at the fake position, what does it mean for a receiver, and why
> is jamming, by contrast, noticed?

Now a fourth beacon D = (10, 10) is added. The spoofer overpowers A, B and C, but D's real signal still
reaches you.

> [!TASK]
> **Predict** (`PREDICT_PARTIAL`): what changes in the solution and in the mismatch?

```bash
python3 where_am_i.py partial
```

Look at the partial solution: still about 4.5 km off. A residual says *something* is wrong, not *which*
signal, and not where you are.

<details><summary>Read after you ran it: what real receivers do with this</summary>
A full spoof is <b>consistent</b> (computed for one point), so the residual is zero and a simple receiver
has no alarm. A naive partial spoof (fake signals computed for the false point, the real ones still
coming from the true point; in the lab both use b = 0.3) leaves a residual that no single point removes:
with more satellites than unknowns, receivers check exactly this (receiver autonomous integrity
monitoring, RAIM). But a spoofer who knows where you are can tune its fake clock bias so that one real
satellite also fits (try it in "Going further"); each further real satellite takes one freedom away from
it, and with as many real satellites as unknowns only the true position (or, in some geometries, its mirror point) fits them all. Better receivers
add other partial defences: signal power monitoring, several antennas to see where signals come from,
signed navigation messages (Galileo OSNMA). Each has limits. A sensor that does not use radio at all (a
camera, the stars) is not fooled by a radio attack: NAVERA's approach.
</details>

> [!TASK]
> `EXPLAIN_PARTIAL`: why can a receiver with a spare measurement notice a partial spoof, why does that not
> help against a full one, and one defence that better receivers add.

> [!TIP] 🏅 End of session 1 — Ghost hunter
> Press **✔ Check my work** now. When every session-1 check passes (TODO 1–6 and Steps 3–6: checks 1–10; the other ✘ lines are session 2), you earn the
> **Ghost hunter** badge on your home page. If the class session ends here, this is the place to stop:
> session 2 starts with NAVERA's real rules.

## Session 2 — Detect & defend (about 2 h)

## Step 7 — The jump gate

First, NAVERA's own rules. In the **⌨️ Terminal**, search the arbiter's settings sheet, or open
[navera_settings.yaml](file:./navera_settings.yaml):

```bash
grep -n "max_speed_mps\|gps_jump_margin_m\|gps_timeout_s" navera_settings.yaml
```

> [!TASK]
> Write `V_MAX_MPS`, `MARGIN_M`, `GPS_TIMEOUT_S` and `DAY_TIMEOUT_S` (how long a day-vision fix stays
> fresh; it is in neither the lesson nor the grep above: extend the pattern or open the file) in
> `answers.py` (numbers, no quotes).
>
> **Predict** (`PREDICT_STEALTH`): with v_max and the margin, and one GPS fix per second, what is the
> fastest steady drag (m/s) the gate can never refuse? You will measure it in Step 10.

Now the gate itself. Positions are in metres from here on. **TODO 7** `gate_ok` (lesson §5): True if accepted. 🧰 `return a <= b`
already returns True or False; with an `if`, every path needs a `return`.

**TODO 8** `count_refused`: the least guided function. Redo the lesson's 7-row table by hand first, then
make your code do exactly that (its docstring example is that table: 5).

```bash
python3 where_am_i.py test
```

<details><summary>Stuck? Hints</summary>

1. What must you remember from one fix to the next? Create those variables before the loop.
2. 5 on the table but 3 on the 300 m jump (`test` labels both lines; `gate` shows it as attack A): `elapsed` is added **after** the test and
   never restarts — fix 1 arrives dt_s after fixes[0], so add dt_s **before** the test, and restart after an
   accept. 4 instead of 5: `elapsed` does not restart after an accept, or starts one step too high. 2: you
   compare with the previous fix instead of the last trusted one, or you count the accepted fixes.
   6 or 7: you update `elapsed` after the test, or you also restart it after a refusal. 1: two bugs at
   once (previous fix **and** no restart).
</details>

> [!TASK]
> **Predict** (`PREDICT_GATE`) for NAVERA's settings, one fix per second: A) a 300 m jump that stays;
> B) a drag of 20 m per second for a minute. Then run, and write `JUMP_REFUSED` and `DRIFT_REFUSED`.

```bash
python3 where_am_i.py gate
```

## Step 8 — Be the arbiter

No code. It is 12:00:10. The last GPS fix arrived at 12:00:08 with σ 35 m (few satellites visible), and
GPS has been the active source. Day vision is fresh with σ 30 m; night vision is fresh too.

> [!TASK]
> `ARBITER_SOURCE` and `ARBITER_STATE`.

## Step 9 — The detective

[flight.csv](file:./flight.csv) is a **simulated** survey flight (one row per second): the GPS
position, and the day-vision position with its σ when vision has a match (empty cells over the sea).
Somewhere in it, a spoofer is at work. **TODO 9** `first_disagreement`: NAVERA's 5 σ + 50 m cross-check
on the log (lesson §5), simplified: no 3 s persistence, no 3 σ streak rule, and no allowance for the
distance flown between the two fixes (mission 30 adds them).

🧰 Rows are dicts, and `None` means "no value":

```python
row = {"t_s": 3, "vision_x_m": None}
print(row["t_s"])                        # 3
for r in rows:
    if r["vision_x_m"] is None:
        continue                         # skip to the next row
```

<details><summary>Stuck? Hints</summary>

1. Skip the rows without vision first; `TypeError … NoneType` means you did not.
2. Use your `distance`; the limit is the lesson's 5 σ + 50 m written with the function's `k`, the row's σ
   and `margin_m`.
3. Return `r["t_s"]` (a time, not the row number) as soon as you find it; `return None` after the loop.
</details>

> [!TASK]
> **Predict** (`PREDICT_FLIGHT`): will the jump gate catch this spoofer? Will the cross-check? When?

```bash
python3 where_am_i.py flight
```

> [!TASK]
> Write `FLIGHT_REFUSED` and `CAUGHT_AT_S`. Open `out/flight.png`. `EXPLAIN_FLIGHT`: when did the spoof
> really start, how fast does it drag, and why was it caught so late? (NAVERA also requires the
> disagreement to last 3 s; mission 30 adds that.)

## Step 10 — Attacker vs defender

Now write your own experiments with your functions (a short script or `python3` in the terminal). A
drag list of `n` m/s for 60 s is `[(n * t, 0) for t in range(61)]`.

**Attacker.** With NAVERA's defaults and one fix per second, find `STEALTH_SPEED_MPS`, the highest
whole-number drag speed that is never refused, and `REFUSED_ONE_FASTER`, how many of the 60 fixes are
refused at 1 m/s more. Look at that second number: what does the gate do to a drag that is just too
fast?

🧰 To load the flight in your own script:

```python
from where_am_i import read_flight
from beacons import count_refused
rows = read_flight()
honest = [(r["gps_x_m"], r["gps_y_m"]) for r in rows if r["t_s"] < START]   # START: read it on the plot
```

Save your script as `step10.py` next to the other files and run `python3 step10.py`.

**Defender.** NAVERA's `max_speed_mps` is set per vehicle. Our survey drone flies at 15 m/s. With
`v_max = 15`, run your `count_refused` on the honest part of the flight (the GPS fixes before the spoof
started, which you found in Step 9) for several margins. Find `DEFENDER_MARGIN_M`, the smallest whole
margin with **zero** refused honest fixes (look at the multipath spikes in `out/flight.png`), and
`DEFENDER_STEALTH_MPS`, the attacker's best speed against your setting.

<details><summary>Stuck? Hints</summary>

1. Attacker: print `count_refused([(n * t, 0) for t in range(61)], 1.0, 100.0, 50.0)` for a few `n`.
   Compare with your `PREDICT_STEALTH`.
2. Defender: `for m in range(40, 80): print(m, count_refused(honest, 1.0, 15.0, m))`.
3. Against a gate, the best steady drag moves v_max × 1 s + margin per fix.
</details>

> [!TASK]
> Write the four numbers and `EXPLAIN_TRADEOFF`: what did tightening the gate gain, what does a smaller
> margin cost on real GPS, and what can the gate still never stop?

## Step 11 — Check, then look back

Press **✔ Check my work**: it also tests your functions on beacons and numbers they have never seen.
When every check passes, the mission is done and you earn the **Gatekeeper** badge.
Then look back, without the lesson:

1. Explain to a friend, in three sentences, how twenty ships ended up at an airport, and what NAVERA
   would and would not have done about it.
2. Which of your predictions was the most wrong, and why?
3. Which NAVERA limit would you work on first, and how would you test the fix?
4. What can a spare satellite reveal about a spoof, and when does it reveal nothing?

## Going further (optional)

- **A real receiver in 3-D.** [gnss_fix.py](file:./gnss_fix.py) is your Gauss–Newton in 3-D with 8
  satellites near Sousse. Set `USE_SATELLITES` to 6, 5, 4, 3: why is the residual exactly 0 at 4? Watch
  PDOP grow.
- **Geometry.** Move beacon C to (10, 10) and redo Step 3. Does the clock error hurt more or less outside
  the triangle? Relate it to the valley of lesson §2 and to `(HᵀH)⁻¹`.
- **A bad start.** Give `gauss_newton` the guess (−20, −20, 0): what happens? Then put the beacons on a
  line, (0, 0), (5, 0), (10, 0), with the truth at (3, 4) and b = 0.3 (build the ranges with your
  `spoof_measurements`). Start from (4, 0, 0): what happens to y, and why (rank)? Then from (4, 1, 0) and
  (4, −1, 0): which mirror point do you get?
- **A smarter spoofer.** In the partial case, choose the fake bias b′ = ρ_D − ‖(7, 2) − D‖, where ρ_D is
  D's real pseudorange. What is the mismatch now? Then make C real too (only A and B spoofed, same b′): what is the mismatch? So
  how many real satellites does RAIM need against a spoofer that keeps its fake point and only tunes its
  bias, and how many against one that may also move its fake point (it then has as many unknowns to play
  with as you do)?
