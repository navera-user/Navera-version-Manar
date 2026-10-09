# Lab 1 — Build a receiver, break it, attack it, defend it

**Goal:** write a position solver (brute force, then Gauss–Newton), spoof it fully and partially, play
detective on a spoofed survey flight, and finish as attacker and defender of NAVERA's jump gate.
**Time:** 2 h 30 to 4 h (a strong programmer: about 2 h).

Your files (📝 Code tab): [beacons.py](file:./beacons.py) (**your code**: nine functions, `TODO 1–9`),
[answers.py](file:./answers.py) (predictions, results, explanations), [where_am_i.py](file:./where_am_i.py)
(runs your functions on the scenarios and draws them; you don't edit it) and
[flight.csv](file:./flight.csv) (a simulated survey flight).

| Lesson | Lab | You write |
|---|---|---|
| §2 Least squares | Steps 2–3 | `distance`, `mismatch`, `find_position` |
| §3 Clock, Gauss–Newton | Steps 4–6 | `find_position_and_bias`, `gauss_newton` |
| §4 Attacking GPS | Step 7 | `spoof_measurements` |
| §5 Arbiter, gate, cross-check | Steps 8–11 | `gate_ok`, `count_refused`, `first_disagreement`, then your own experiments |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` is written **before** you run the step. It is never marked
> right or wrong; being wrong and finding out why is the point.

## Step 1 — NAVERA's rules

In the **⌨️ Terminal** (prompt `student@navera:~/lessons/01-welcome$`), search the arbiter's settings
in your NAVERA copy, or open
[estimator_params.yaml](file:navera/navera_estimator/navera_estimator/config/estimator_params.yaml):

```bash
grep -n "max_speed_mps\|gps_jump_margin_m\|gps_timeout_s" ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml
```

> [!TASK]
> Write `V_MAX_MPS`, `MARGIN_M` and `GPS_TIMEOUT_S` in `answers.py` (numbers, no quotes).

## Step 2 — Residuals

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
</details>

## Step 3 — Brute force

**TODO 3** `find_position`: the grid search of lesson §3, in 2-D (the docstring gives the grid).

```bash
python3 where_am_i.py clean
```

<details><summary>Stuck? Hints</summary>

1. `best` and `best_m` start as `None`, **before** both loops; the inner loop sits inside the outer one.
2. x always 0.0 or 10.0? A `return` or a `best = None` sits inside a loop.
</details>

## Step 4 — A clock 1 µs ahead

> [!TASK]
> **Predict** (`PREDICT_CLOCK`): with pseudoranges 0.3 km too long, where does `find_position` land, and
> what is its minimum mismatch?

```bash
python3 where_am_i.py clock
```

Write `CLOCK_ERROR_M` (part 1). Before you open the box below, try to explain why it is far less than
300 m.

<details><summary>Why about 140 m and not 300 m?</summary>
You are <b>inside</b> the beacon triangle: moving away from one beacon brings you closer to the others,
so a uniform +0.3 km on all three ranges mostly cancels. The continuous least-squares optimum is about
115 m away; the 0.1 km grid can only reach (3.1, 4.1), 141 m away. Outside the triangle it would not
cancel so well ("Going further").
</details>

**TODO 4** `find_position_and_bias`: the bias becomes a third unknown, searched on the docstring's grid.
Return three numbers. Run `clock` again: part 2 must find the true position and b = 0.3 km.

<details><summary>Stuck? Hints</summary>

1. A third loop inside the other two; same integer trick as `x = i / 10`, for 21 biases 0.00 … 1.00.
2. Give the bias to `mismatch` as its 4th argument; otherwise the bias found is always 0.
3. `((3.0, 4.0), 0.3)` is a point and a number: return three numbers.
</details>

> [!TASK]
> `EXPLAIN_CLOCK`: why does adding the bias as an unknown repair the solution?

## Step 5 — Count the unknowns

> [!TASK]
> **Predict** (`PREDICT_TWO`): with beacon C out of range, how many `(x, y, bias)` fit almost
> perfectly?

```bash
python3 where_am_i.py two
```

Each blue dot in `out/two.png` fits, with its own bias; a finer grid would give a continuous curve.
Which curve? Take two dots: compute (distance to A − distance to B) for each, with your `distance`. What
stays constant? Which curve is the set of points whose distances to two fixed points differ by a
constant?

> [!TASK]
> `EXPLAIN_TWO` (unknowns vs measurements; satellites needed by real GPS) and `CURVE` (one word).

## Step 6 — Gauss–Newton

**TODO 5** `gauss_newton(beacons, measured, guess, steps)`: lesson §3. At each step build `H` (one row
`[uₓ, u_y, 1]` per beacon) and `r` (measured − predicted), solve, update.

🧰 numpy in three lines:

```python
import numpy as np
H = np.array([[1.0, 0.0], [0.0, 2.0], [1.0, 1.0]]);  r = np.array([1.0, 2.0, 2.0])
delta, *_ = np.linalg.lstsq(H, r, rcond=None)        # least-squares solution of H · delta ≈ r
```

Check your first step by hand against the lesson's worked table (guess (4, 4), b = 0), then:

```bash
python3 where_am_i.py gn
```

<details><summary>Stuck? Hints</summary>

1. Inside the step loop: two empty lists `H` and `r`, one row each per beacon, then one `lstsq`.
2. Sign check: `uₓ = (x − beacon_x) / d`; the residual is measured − (d + b).
3. Jumping away instead of converging? You add `−Δ`, or your residual has the opposite sign.
</details>

> [!TASK]
> `GN_STEPS`: steps until the mismatch is below 1e-6. `EXPLAIN_GN`: why is it so much faster than brute
> force, and what could make it fail?

## Step 7 — Be the spoofer

**TODO 6** `spoof_measurements(beacons, fake_position, bias)`: the pseudoranges a receiver at the fake
position would measure, one per beacon, in a list (`values = []`, then `values.append(…)`).

> [!TASK]
> **Predict** (`PREDICT_SPOOF`): you are at (3, 4); the spoofer fakes (7, 2) on all three beacons. What
> does your Gauss–Newton find, with what mismatch?

```bash
python3 where_am_i.py spoof
```

> [!TASK]
> `EXPLAIN_SPOOF`: why is the mismatch 0 at the fake position, and what does it mean for a receiver?

Now a fourth beacon D = (10, 10) is added. The spoofer overpowers A, B and C, but D's real signal still
reaches you.

> [!TASK]
> **Predict** (`PREDICT_PARTIAL`): what changes in the solution and in the mismatch?

```bash
python3 where_am_i.py partial
```

> [!TASK]
> `EXPLAIN_PARTIAL`: why can a receiver with a spare measurement notice a partial spoof, and why does that
> not help against a full one?

<details><summary>Read after Step 7: what real receivers do with this</summary>
A full spoof is <b>consistent</b> (computed for one point), so the residual is zero and a simple receiver
has no alarm. A partial spoof leaves a residual that no single point can remove: with more satellites
than unknowns, receivers check exactly this (receiver autonomous integrity monitoring, RAIM). Better
receivers add other partial defences: signal power monitoring, several antennas to see where signals
come from, signed navigation messages (Galileo OSNMA). Each has limits. A sensor that does not use radio
at all (a camera, the stars) is not fooled by a radio attack: NAVERA's approach.
</details>

## Step 8 — The jump gate

Positions are now in metres. **TODO 7** `gate_ok` (lesson §5): True if accepted. 🧰 `return a <= b`
already returns True or False; with an `if`, every path needs a `return`.

**TODO 8** `count_refused`: the least guided function. Redo the lesson's 7-row table by hand first, then
make your code do exactly that (its docstring example is that table: 5).

```bash
python3 where_am_i.py test
```

<details><summary>Stuck? Hints</summary>

1. What must you remember from one fix to the next? Create those variables before the loop.
2. 4 instead of 5: `elapsed` does not restart after an accept, or starts one step too high. 2: you
   compare with the previous fix instead of the last trusted one, or you count the accepted fixes.
   6 or 7: you update `elapsed` after the test, or you also restart it after a refusal.
</details>

> [!TASK]
> **Predict** (`PREDICT_GATE`) for NAVERA's settings, one fix per second: A) a 300 m jump that stays;
> B) a drag of 20 m per second for a minute. Then run, and write `JUMP_REFUSED` and `DRIFT_REFUSED`.

```bash
python3 where_am_i.py gate
```

## Step 9 — Be the arbiter

No code. It is 12:00:10. The last GPS fix arrived at 12:00:08 with σ 35 m (few satellites visible), and
GPS has been the active source. Day vision is fresh with σ 30 m; night vision is fresh too.

> [!TASK]
> `ARBITER_SOURCE` and `ARBITER_STATE`. Careful: priority, not precision.

## Step 10 — The detective

[flight.csv](file:./flight.csv) is a **simulated** survey flight (one row per second): the GPS
position, and the day-vision position with its σ when vision has a match (empty cells over the sea).
Somewhere in it, a spoofer is at work. **TODO 9** `first_disagreement`: NAVERA's cross-check on the log
(lesson §5: GPS farther from vision than 5 σ + 50 m).

> [!TASK]
> **Predict** (`PREDICT_FLIGHT`): will the jump gate catch this spoofer? Will the cross-check? When?

```bash
python3 where_am_i.py flight
```

> [!TASK]
> Write `FLIGHT_REFUSED` and `CAUGHT_AT_S`. Open `out/flight.png`. `EXPLAIN_FLIGHT`: when did the spoof
> really start, how fast does it drag, and why was it caught so late? (NAVERA also requires the
> disagreement to last 3 s; mission 27 adds that.)

## Step 11 — Attacker vs defender

Now write your own experiments with your functions (a short script or `python3` in the terminal). A
drag list of `n` m/s for 60 s is `[(n * t, 0) for t in range(61)]`.

**Attacker.** With NAVERA's defaults and one fix per second, find `STEALTH_SPEED_MPS`, the highest
whole-number drag speed that is never refused, and `REFUSED_ONE_FASTER`, how many of the 60 fixes are
refused at 1 m/s more. Look at that second number: what does the gate do to a drag that is just too
fast?

**Defender.** NAVERA's `max_speed_mps` is set per vehicle. Our survey drone flies at 15 m/s. With
`v_max = 15`, run your `count_refused` on the honest part of the flight (the GPS fixes before the spoof
started, which you found in Step 10) for several margins. Find `DEFENDER_MARGIN_M`, the smallest whole
margin with **zero** refused honest fixes (look at the multipath spikes in `out/flight.png`), and
`DEFENDER_STEALTH_MPS`, the attacker's best speed against your setting.

> [!TASK]
> Write the four numbers and `EXPLAIN_TRADEOFF`: what did tightening the gate gain, what does a smaller
> margin cost on real GPS, and what can the gate still never stop?

## Step 12 — Check, then look back

Press **✔ Check my work**: it also tests your functions on beacons and numbers they have never seen.
Then, without the lesson: could you explain to a friend, in three sentences, how twenty ships ended up
at an airport, and what NAVERA would and would not have done about it?

## Going further (optional)

- **A real receiver in 3-D.** [gnss_fix.py](file:./gnss_fix.py) is your Gauss–Newton in 3-D with 8
  satellites near Sousse. Set `USE_SATELLITES` to 6, 5, 4, 3: why is the residual exactly 0 at 4? Watch
  PDOP grow.
- **Geometry.** Move beacon C to (10, 10) and redo Step 4. Does the clock error hurt more or less outside
  the triangle? Relate it to the valley of lesson §2 and to `(HᵀH)⁻¹`.
- **A bad start.** Give `gauss_newton` the guess (−20, −20, 0), or a beacon set where all beacons lie on a
  line. What happens, and why (hint: rank of H)?
