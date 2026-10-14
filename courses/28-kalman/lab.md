# Lab 28 — A Kalman filter that stays honest

**Goal:** write NAVERA Lite's Kalman part (`navera_lite/kalman.py`): the constant-velocity model, the predict and
update steps, a height filter that must give exactly the course's reference numbers, an honesty test, and a 2-D
tracker with a gate. Then fly the tracker through a jam and six wrong fixes, and tune it.
**Time:** 4 h 30 (up to 6 h if numpy is rusty) plus 1 h 30 of reading (session 1: 2–2 h 30, session 2: 2 h 30–3 h
30; the matrix shapes and the tracker loop take the longest); a strong programmer who knows numpy: about 3 h.
**Fast track:** if you know numpy well, skip the 🧰 boxes and the "Stuck?" boxes; do "Going further" at the end.

Your files (📝 Code tab): [navera_lite/kalman.py](file:./navera_lite/kalman.py) (**your code**: TODO 1–5 and 7),
[band_sim.py](file:./band_sim.py) (**your code**: TODO 6), [answers.py](file:./answers.py),
[report.md](file:./report.md), and a tool you only run: [run_kalman.py](file:./run_kalman.py).

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §2 F, Q and the prediction | Step 1 | `cv_model`, `kf_predict` (TODO 1–2) |
| §3 the update | Step 2 | `kf_update` (TODO 3), a hand trace |
| §4 q, R and the race | Steps 3–4 | `Height1D.update` (TODO 4) |
| §6 NEES | Step 5 | `nees` (TODO 5), `nees_band` (TODO 6, band_sim.py) |
| §5 tracker and gate | Steps 6–7 | `run_filter` (TODO 7) |
| (session 2: read §5–§7 first; Step 5 uses §6, then Steps 6–7 use §5) | | |
| §7 tuning | Step 8 | (you measure) |
| all | Step 9 | the filter memo |

> [!NOTE]
> **The data** (`/data/academy/28-kalman/`, described in its README) is **simulated** for the course: heights
> from three sources with the truth, the course's reference output for those heights, and a 6-minute flight with
> one position fix per second (σ 5 m), a 40-second jam and a few wrong fixes, with the truth.
>
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step; it is never
> marked right or wrong. `python3 run_kalman.py test` tries every docstring example (and a few traps). Arrays:
> states are numpy vectors, covariances numpy matrices; a one-number measurement is still an array (`[106.0]`).

## Session 1 — Height keeper (2 h to 2 h 30)

## Step 0 — How fast does "I don't know" grow?

No code, no lesson yet.

> [!TASK]
> **Predict** (`PREDICT_GROW` in `answers.py`): a drone flies east at 12 m/s. Its navigation knows its position
> to σ 3 m and its velocity to σ 1 m/s. Then the GPS is jammed for 40 s. It carries on with its last
> velocity, but the drone's real velocity keeps changing a little (gusts, small random accelerations of about
> 0.5 m/s²).
> After 40 s, is the σ of its position about 3 + 1 × 40 = 43 m, clearly less, or clearly more? Write one reason.
> Save the file (`Ctrl+S`). Then read lesson §1–§4.

## Step 1 — The model and the prediction (TODO 1, TODO 2)

Open the 📝 Code tab, then `navera_lite/kalman.py`. Read the conventions at the top. Each `TODO` function keeps
its docstring and ends with `return None   # TODO…`: replace that line with your code.

**TODO 1** `cv_model(dt, q, dims=2)`: lesson §2, "Where Q comes from", and the 🧰 box (outer and Kronecker
products). **TODO 2** `kf_predict(x, P, F, Q)`: lesson §2, two lines. Convert the inputs first, so that lists
work too:

<details><summary>🧰 numpy: one line to convert several inputs, and the matrix product</summary>

```python
import numpy as np
a, b = (np.asarray(v, dtype=float) for v in ([1, 2], [[1, 0], [0, 2]]))
b @ a          # array([1., 4.]) — matrix × vector
b @ b.T        # the transpose with .T (a numpy array only: a list has no .T)
b * b          # NOT a matrix product: element by element
```
</details>

```bash
python3 run_kalman.py test
```

The lines of TODO 1 and 2 must be ✔ (the other TODOs show "not written yet").

```bash
python3 run_kalman.py grow
```

`grow` runs your two functions on the drone of Step 0: 40 predictions of one second, q = 0.3 m²/s⁴. Open
`out/grow.png`.

> [!TASK]
> Write `SIGMA_40S_M` (σ of the position after 40 s, from the run). `EXPLAIN_GROW`: compare with your prediction:
> why does σ grow faster than a straight line? Name the two things that add up (lesson §2's ✏️ check helps). (What
> would σ be with q = 0, the velocity error alone? √(3² + (1·40)²) = 40.1 m: a straight line. Only q bends it.)

<details><summary>Stuck? Hints, one at a time</summary>

1. `cv_model`: one axis first: F1 (2 × 2) and g = [dt²/2, dt] as numpy arrays, Q1 = q·g gᵀ (🧰 box: outer
   product). Then copy the one-axis model onto `dims` axes with the Kronecker product (🧰 box), for F1 and Q1.
2. ✘ "the state order": with `np.kron(np.eye(dims), F1)` the state would be [e, v_e, n, v_n]. The course's order
   is [e, n, v_e, v_n]: F1 first.
3. ✘ "Q = q·[[dt³/3, dt²/2], …]": that is another model (continuous noise). This course: Q = q·g gᵀ.
4. `kf_predict`: the two formulas of lesson §2, with `@` and `.T`, after converting the four inputs (🧰 box above).
5. ✘ "F @ P @ F": the transpose is missing. ✘ "Q is not added". ✘ "P is not moved by F".
</details>

## Step 2 — The update (TODO 3), by hand first

> [!TASK]
> **By hand, before coding** (lesson §3 has the method with other numbers): a height filter predicts
> x⁻ = [120 m, 0 m/s] with P⁻ = [[16, 4], [4, 2]]. A barometer reads 126 m with σ 2 m. Compute S, K (two
> numbers), the new state and P[0][0]. Write `TRACE_HEIGHT_M`, `TRACE_CLIMB_MPS` and `TRACE_SIGMA_M` (σ of the
> height after the update).

**TODO 3** `kf_update(x, P, z, H, R)`: lesson §3, the five lines, and the NIS (`nu @ np.linalg.solve(S, nu)`, a
float). The 🧰 box of lesson §3 shows `solve`, `inv` and the shapes.

```bash
python3 run_kalman.py test
```

```bash
python3 run_kalman.py step
```

`step` runs your `kf_update` on the numbers of your hand trace. If they differ, find out who is wrong.

<details><summary>Stuck? Hints, one at a time</summary>

1. Convert x, P, z, H, R with `np.asarray(…, dtype=float)`. Shapes: x (2,), P (2, 2), z (1,), H (1, 2), R (1, 1).
2. Translate lesson §3 line by line: ν, S, K, the new x, the new P. S⁻¹ is `np.linalg.inv(S)`; I is
   `np.eye(len(x))`; every product is `@`.
3. The NIS in one line: `nis = float(nu @ np.linalg.solve(S, nu))`.
4. ✘ "nis divides by R only" or "by P only": S = H P Hᵀ + R contains both. ✘ "nis is a square root": NIS is a d².
5. ✘ "matmul: Input operand … has a mismatch": print the shapes; H must be 2-D (`[[1.0, 0.0]]`), not `[1.0, 0.0]`.
</details>

## Step 3 — The race (TODO 4)

**TODO 4** `Height1D.update(self, t, h, sigma)`: lesson §4, "The race", and the docstring's rules. It is a
**method**: the filter keeps its state in `self.x`, `self.P` and `self.t` between calls (they are `None` before
the first height). Use your three functions: `cv_model(dt, self.climb_accel ** 2, dims=1)`, `kf_predict`,
`kf_update`.

<details><summary>🧰 Python: a method that keeps state between calls</summary>

```python
class Counter:
    def __init__(self):
        self.n = None              # nothing seen yet
    def add(self, k):
        if self.n is None:         # the first call starts the count
            self.n = k
        else:
            self.n = self.n + k    # later calls change what the object remembers
        return self.n
c = Counter(); c.add(5); c.add(2)  # 5, then 7: c.n is 7
```
</details>

```bash
python3 run_kalman.py test
```

```bash
python3 run_kalman.py race
```

`race` runs your `Height1D` (climb_accel 0.5) on the 131 heights of `heights.csv` and compares every output with
`reference_heights.csv`. Open `out/race.png`. You win when the largest difference is below 10⁻⁶ m: **SAME
FILTER**.

> [!TASK]
> Win the race. Then write `RACE_RMSE_RAW_M` and `RACE_RMSE_FILTER_M` (the RMS errors of the raw heights and of
> your filter against the truth, printed by `race`).

<details><summary>Stuck? Hints, one at a time</summary>

1. Order: (1) ignore a height that is not > 0 — return the current `(height, σ)` or None; (2) the first usable
   height starts the filter; (3) otherwise refuse a time before `self.t`, predict over `t - self.t`, update; (4)
   remember `self.t = t`; return `float(self.x[0]), math.sqrt(self.P[0, 0])`.
2. Start values: `self.x = np.array([h, 0.0])`, `self.P = np.diag([sigma ** 2, 4.0])`.
3. The update: `self.x, self.P, _ = kf_update(x, P, [h], [[1.0, 0.0]], [[sigma ** 2]])`.
4. "the two filters differ" (by 0.4 to 1.8 m somewhere in the flight): q = `self.climb_accel ** 2` (0.25), not 0.5;
   R = σ², not σ; the start climb variance is 4.0, not 0 and not σ².
5. A crash at the first "no reading" row, or a difference from that row on: a height of 0.0 changes nothing (no
   prediction either) and `self.t` stays the time of the last usable height.
6. ✘ "returned a σ of 9.0": that is P[0][0], the variance; return its square root.
</details>

## Step 4 — What q means

The race used σ_a = 0.5 m/s², the value in NAVERA's code. Is it the best value for these heights?

> [!TASK]
> **Predict** (`PREDICT_Q`): with climb_accel 0.05 m/s² and with 5 m/s², which will have the larger RMS error over
> the whole flight? Will either of them do **worse** than the raw heights (`RACE_RMSE_RAW_M`)? Why? Then:

```bash
python3 run_kalman.py heights 0.05
```

```bash
python3 run_kalman.py heights 5
```

```bash
python3 run_kalman.py heights 0.5
```

Open the three `out/heights_….png`.

> [!TASK]
> Write `RMSE_CA_005_M` and `RMSE_CA_5_M` (whole flight). `EXPLAIN_Q`: what goes wrong with each, where in the
> flight (climb, descent or level), and why does the smallest value state the smallest σ while being the most wrong?

> [!TIP] 🏅 End of session 1 — Height keeper
> Press **✔ Check my work**. When the checks of TODO 1–4 and Steps 1–4 pass (checks 1–6; the others are
> session 2), you earn the **Height keeper** badge. If the class session ends here, stop here. Read lesson
> §5–§7 before session 2.

## Session 2 — Tracker (2 h 30 to 3 h 30)

## Step 5 — Is it honest? (TODO 5, TODO 6)

**TODO 5** `nees(err, P)`: lesson §6, one line (the same algebra as the NIS of TODO 3).

**TODO 6** `nees_band(n_dim, n_steps, trials=4000, p=0.95, seed=0)` in **band_sim.py**: lesson §6, "How close to
2 is clearly?". Simulate `trials` honest flights in one go with a 3-D array of standard normal numbers, square,
sum over the dimensions, average over the steps, and cut the ends with `np.percentile`.

<details><summary>🧰 numpy: random numbers in a 3-D array, sums along an axis, percentiles</summary>

```python
import numpy as np
rng = np.random.default_rng(0)
a = rng.standard_normal((3, 4, 2))     # 3 × 4 × 2 numbers from N(0, 1)
a.sum(axis=2).shape                    # (3, 4): summed over the LAST axis
a.sum(axis=2).mean(axis=1).shape       # (3,): then averaged over the middle one
np.percentile([1, 2, 3, 4, 5], [10, 90])   # array([1.4, 4.6])
```
</details>

> [!TASK]
> **Predict** (`PREDICT_BAND`): an honest 2-D filter flies 361 s. Its mean NEES is near 2. Between which two
> numbers will it fall in 95 % of such flights? (One step: 0.05 to 7.38, lesson §6. And 361 steps?) Then:

```bash
python3 run_kalman.py test
```

```bash
python3 band_sim.py
```

Open `out/band.png`. (The first row, one step, uses only 4 000 flights: expect about 0.05–7.4, a few % off the
exact χ² values.)

> [!TASK]
> Write `BAND_LOW` and `BAND_HIGH` (n = 2, N = 361, p = 0.95, two decimals).

<details><summary>Stuck? Hints, one at a time</summary>

1. `nees`: `float(err @ np.linalg.solve(P, err))` after converting both inputs. ✘ "37.0": the inverse is missing.
2. `nees_band`: `rng = np.random.default_rng(seed)`; `x = rng.standard_normal((trials, n_steps, n_dim))`.
3. Square, then sum over the LAST axis (the dimensions): one NEES per step, shape (trials, n_steps). Then average
   over the steps: one mean per flight, shape (trials,).
4. Cut c = 100 (1 − p) / 2 percent at each end: `np.percentile` with two percentages. Return two floats.
5. ✘ a band near 722: you summed over the steps instead of averaging. ✘ a band around 1: you averaged over the
   dimensions too (the NEES of one step is a SUM over the n dimensions).
</details>

## Step 6 — The tracker (TODO 7)

**TODO 7** `run_filter(times, zs, sigma_z, q, gate_p=None, v0_sigma=20.0)`: lesson §5, "The tracker" and "The
gate". The least guided TODO: the docstring states the contract and has an example.

> [!TASK]
> **Before you code**, trace the docstring example by hand for the first two times: what are x and P after k = 0,
> and after k = 1 (no fix)? (Only the top-left numbers of P: P[0][0] after k = 1 is 25 + 400 + 0.25 = 425.25.
> Why those three terms?) No answer to write: the trace is your plan.

```bash
python3 run_kalman.py test
```

<details><summary>🧰 Python: walking two lists together, and a dict of lists</summary>

```python
times = [0.0, 1.0, 2.0]; zs = [(0, 0), None, (30, 0)]
for k, (t, z) in enumerate(zip(times, zs)):   # k = 0, 1, 2; t and z from the same position
    print(k, t, z, times[k] - times[k - 1] if k > 0 else None)
out = {"x": [], "d2": []}
out["x"].append(np.array([1.0, 2.0]).copy())   # .copy(): later changes to the array do not change the stored one
out["d2"].append(None)
```
</details>

<details><summary>Stuck? Hints, one at a time</summary>

1. Before the loop: H (2 × 4: an identity on the left, zeros on the right — `np.hstack` puts two arrays side by
   side), R, the gate's threshold (or None without a gate), and a dict of four empty lists.
2. Loop over the times with `enumerate(zip(times, zs))`. k = 0 is the start (docstring). At every other k:
   predict first, always, over the real time step.
3. With a fix, one call to your kf_update gives the candidate state AND its d2: keep the candidate only when there
   is no gate or the d2 passes it.
4. Append to the four lists at EVERY time (start, fix used, fix refused, no fix): `x.copy()`, `P.copy()`, the d2,
   the decision.
5. ✘ "the prediction was skipped at a time with no fix": predict at EVERY time. ✘ "d2 compares with P only": use
   the nis of kf_update (S contains R). ✘ "a refused fix moved x": keep the prediction.
</details>

```bash
python3 run_kalman.py track 0.3
```

The flight, no gate, q = 0.3. Open `out/track_0.3.png` (left: the map; right: the true error and the stated σ,
linear up to 10 m, then logarithmic).

> [!TASK]
> Write `NEES_NO_GATE` (mean NEES), `SIGMA_END_JAM_M` (σ east at the end of the jam) and `ERR_END_JAM_M` (the
> true 2-D error |x − truth| at the end of the jam). Is the stated σ honest during the jam? Compare like with like:
> the 2-D error with the 2-D σ √(σe² + σn²) that `track` also prints, not with σ east.

## Step 7 — The gate

> [!TASK]
> **Predict** (`PREDICT_GATE`): with a 99 % gate, how many of the 6 wrong fixes will be refused, and how many of the
> 315 good ones? What will happen to the mean NEES? Then:

```bash
python3 run_kalman.py track 0.3 0.99
```

> [!TASK]
> Write `NEES_GATE`, `WRONG_REFUSED`, `GOOD_REFUSED` and `D2_AFTER_JAM` (d² of the first fix after the jam).
> `EXPLAIN_GATE`: why did a few good fixes get refused (is the number about what a 99 % gate should refuse?), and
> why did the wrong fixes raise the NEES so much without the gate?
>
> **Your role: the judge.** With your `SIGMA_END_JAM_M`, a fix (σ 5 m) arrives 150 m north of the prediction at
> the end of the jam. Compute its d² by hand (lesson §5's ✏️ check): `JUDGE_D2`, and `JUDGE_ACCEPT` (True or
> False) for the 99 % gate.

## Step 8 — The tuner

```bash
python3 run_kalman.py sweep
```

The same flight with the 99 % gate and seven values of q, from 0.01 to 10. The verdict uses your NEES band. A value
just outside the band (1.74) is a weak verdict, and lesson §6 says why the band is narrower than reality; q = 0.3
wins because it is honest AND the most accurate.

> [!TASK]
> Write `Q_BEST`: the value of q you would fly (lesson §7's rule: honest first, then the smallest error).
> `EXPLAIN_TUNE`: what happened to q = 0.01 and 0.03 after the jam (why, step by step), and why is q = 0.1 not
> chosen although its error is close to the best? And is q = 1 (1.74) clearly dishonest, or only just outside a
> band that lesson §6 says is too narrow?

```bash
python3 run_kalman.py track 0.03 0.99
```

Open `out/track_0.03_gate0.99.png` and see the lock-out.

## Step 9 — The filter memo

Write [report.md](file:./report.md) (150–350 words, your own words, keep the three headings): what your filter
does in each step; what q and R mean and how you chose q; what the gate and the NEES test protect against.
Quote your numbers with their units.

> [!TASK]
> report.md has the three headings, 150–350 words, and quotes the race's RMS errors (m), the mean NEES with the
> gate and your band, and the q you chose.

## Step 10 — Check, then look back

Press **✔ Check my work**: it tests your functions on models, heights, flights and errors it has never seen.
When every check passes, you earn the **Tracker** badge. Then look back, without the lesson:

1. Explain to a colleague, in three sentences, how a measurement of height changes a climb rate.
2. Which of your predictions was the most wrong? What did you assume?
3. NAVERA states an accuracy with every position it sends. After this lab, what would you check before trusting
   that number in a filter of your own?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **One big step.** In `grow`, the 40 s are predicted in 40 steps of 1 s. Predict them in ONE step of 40 s (a
  three-line script: `from navera_lite.kalman import cv_model, kf_predict`). σ after 40 s? Why is it so much
  larger? Which one describes a drone whose accelerations change every second?
- **NIS in flight.** Without the truth, the NIS of the accepted fixes should average 2 (slightly less, about 1.9,
  behind a 99 % gate, which cuts off the tail). Compute it from
  `run_filter(...)["d2"]` for q = 0.03, 0.3 and 3 (with the gate). Does it tell the same story as NEES?
- **The real band.** Re-simulate 100 flights of the lab's model (truth: `cv_model(1.0, 0.3)` with one random
  acceleration of variance 0.3 per axis and second; fixes with σ 5 m; no fix from 150 to 189 s) and run your
  tracker with q = 0.3 and the 99 % gate on each. The 2.5 % and 97.5 % points of the mean NEES? Compare with your
  band from `band_sim.py`. (Reference: about 1.6–2.6.)
- **The Joseph form.** Write the update with P = (I − KH) P⁻ (I − KH)ᵀ + K R Kᵀ in a copy of your function and
  compare on the flight: largest difference in P? Why do long-running filters prefer it?
- **A height gate.** NAVERA's height filter has no gate. Add a wrong height (200 m at t = 70 s) to a copy of the
  data and run `Height1D`. How far is the filter pulled, and for how long? What gate would you add?
- **Fly your own parts.** Mission 24's `blend` is the 1-D update. Check it: `blend(x⁻, P⁻, z, R)` against your
  `kf_update` with H = [[1]] on three cases of your choice.
