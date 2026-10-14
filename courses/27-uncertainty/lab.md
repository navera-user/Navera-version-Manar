# Lab 27 — Ellipses, gates and fusion

**Goal:** write NAVERA Lite's uncertainty part (`navera_lite/uncertainty.py`): a covariance from a cloud of
fixes, its ellipse, the distance of a surprise in sigmas, J P Jᵀ, the χ² gate, information fusion, and the
honest way to publish the result. You discover the χ² law by simulation, judge six fixes after a GPS outage,
attack your own gate, and measure on a 400 s drive when fusion helps and when it hurts.
**Time:** 3 h to 4 h 30 (session 1: 1 h 30–2 h, session 2: 1 h 30–2 h 30; the ellipse and the radar take the
longest if matrices are rusty). A strong programmer who knows numpy: about 2 h 30.
**Fast track:** if you know numpy well, skip the 🧰 boxes and the "Stuck?" boxes; do "Going further" at the end.

Your files (📝 Code tab): [navera_lite/uncertainty.py](file:./navera_lite/uncertainty.py) (**your code**:
TODO 1–3 and 5–9), [chi2_sim.py](file:./chi2_sim.py) (TODO 4), [answers.py](file:./answers.py),
[report.md](file:./report.md), and a tool you only run: [run_uncertainty.py](file:./run_uncertainty.py).
`navera_lite/estimate.py` (mission 12's part, finished: the course's reference) gives `is_covariance`,
`stated_sigma` and `classify`: read them, use them, do not change them.

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §1 one cloud, one matrix · §2 the ellipse | Steps 1–2 | `sample_cov`, `ellipse` (TODO 1–2) |
| §3 Mahalanobis and χ² | Step 3 | `mahalanobis2` (TODO 3), `d2_samples` (TODO 4) |
| §4 J P Jᵀ | Step 4 | `propagate`, `polar_to_en` (TODO 5–6) |
| §5 the gate | Steps 5–6 | `gate` (TODO 7), judge and attacker |
| §6 fusion | Step 7 | `fuse` (TODO 8) |
| §7 publishing | Step 8 | `make_covariance` (TODO 9) |
| all | Step 9 | the memo |

> [!NOTE]
> **The data** (`/data/academy/27-uncertainty/`, described in its README) is **synthetic**, made for the course:
> 600 fixes of a receiver standing still on a harbour quay, a predicted position after a GPS outage with six
> candidate fixes, and a 400 s drive with GPS and day-vision fixes and the truth. Positions are metres east and
> north (ENU).
>
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step; it is never
> marked right or wrong. `python3 run_uncertainty.py test` tries every docstring example and a few traps.
> Matrices are numpy arrays; `A @ B` is the matrix product, `A.T` the transpose.

## Session 1 — Ellipse maker (about 1 h 30; 2 h if matrices are new)

## Step 0 — Three metres

No code, no lesson yet.

> [!TASK]
> **Predict** (`PREDICT_INSIDE` in `answers.py`): a GPS states σ = 3 m, the same east and north, errors
> independent. Out of 100 fixes, how many are within 3 m of the truth? One number and one reason. Save
> (`Ctrl+S`). Then read lesson §1–§2.

## Step 1 — Look at the data

```bash
python3 run_uncertainty.py look
```

```bash
head -4 /data/academy/27-uncertainty/static_fixes.csv
```

`static_fixes.csv` is the error of each fix from the surveyed point, one fix every 10 s (so that consecutive
errors are nearly independent).

## Step 2 — The cloud becomes a matrix and an ellipse (TODO 1, TODO 2)

Open `navera_lite/uncertainty.py`. Read the conventions at the top and the given functions (`chi2_threshold`,
`p_inside`, `ellipse_outline`). Each TODO keeps its docstring and ends with `return None   # TODO…`: replace
that line with your code.

**TODO 1** `sample_cov(points)`: lesson §1. **TODO 2** `ellipse(P, k=1.0)`: lesson §2 and its 🧰 box.

<details><summary>🧰 numpy: a mean per column, a matrix product, a transpose</summary>

```python
import numpy as np
x = np.array([[1.0, 2.0], [3.0, 6.0], [5.0, 4.0]])     # 3 rows (points), 2 columns (east, north)
x.shape                  # (3, 2)
x.mean(axis=0)           # array([3., 4.]) — the mean of each COLUMN (axis=0 runs down the rows)
d = x - x.mean(axis=0)   # subtracts (3, 4) from every row
d.T @ d                  # (2, 3) @ (3, 2) → a 2 × 2 matrix: the sums of products of the columns
```
`np.asarray(points, dtype=float)` turns a list of pairs into such an array.
</details>

<details><summary>🧰 Two ways to the eigenvalues: by hand, or numpy</summary>

The lesson's formulas use `math.hypot`, `math.atan2` and `math.degrees`. Or let numpy do it:
```python
vals, vecs = np.linalg.eigh(np.array([[4.0, 1.0], [1.0, 2.0]]))
vals          # array([1.586, 4.414]) — ASCENDING: the largest is LAST
vecs[:, 1]    # the eigenvector of vals[1] is the COLUMN 1, not the row
```
Either way, your angle must end in (−90°, 90°], and a tiny negative λ from rounding (−1e-15) must count as 0:
`max(lam, 0.0)` before the square root.
</details>

```bash
python3 run_uncertainty.py test
```

The lines of TODO 1 and 2 must be ✔ (the others say "not written yet").

```bash
python3 run_uncertainty.py cloud
```

Open `out/cloud.png`: the 600 fixes, your 1-, 2- and 3-sigma ellipses, and the circle of the judge's σ
(mission 12's √max(a, c)).

> [!TASK]
> Write `ELLIPSE_A_M`, `ELLIPSE_B_M`, `ELLIPSE_ANGLE_DEG` (the 1-sigma ellipse) and `JUDGE_SIGMA_M` (the judge's
> σ). Which way does the long axis point, as a compass direction (lesson §2: the angle is from east towards
> north)?

<details><summary>Stuck? Hints, one at a time</summary>

1. `sample_cov`: four lines — the array, a check (fewer than 2 rows → `raise ValueError(...)`), the deviations,
   then `d.T @ d / (N − 1)` with N = the number of rows (`x.shape[0]`).
2. ✘ "you divided by N": the lesson divides by N − 1 (as `np.cov` does). ✘ "the mean point is not subtracted":
   the deviations are `x - x.mean(axis=0)`, not the points themselves.
3. `ellipse`: read a, b, c from P (`P[0][0]`, `P[0][1]`, `P[1][1]`), then the 🧰 formulas of lesson §2; return
   `(k * math.sqrt(lam1), k * math.sqrt(lam2), angle)`.
4. ✘ "the right line, but the angle must be in (−90, 90]": an eigenvector may point either way along its axis
   (south-west instead of north-east): add or remove 180°. ✘ "a round error": with a circle any direction is "the
   long axis"; the convention is 0.0 (½·atan2(0, 0) gives it for free). ✘ "those are variances (m²)": the
   semi-axes are √λ.
5. ✘ "math domain error" (or nan) for "errors on one line (ρ = 1)": λ₂ came out as −1e-15. `max(lam2, 0.0)`.
</details>

## Step 3 — Distances in sigmas, and the χ² law (TODO 3, TODO 4)

Read lesson §3. **TODO 3** `mahalanobis2(r, S)` in `navera_lite/uncertainty.py`. **TODO 4** `d2_samples(n,
seed=0)` in `chi2_sim.py`: the simulation of lesson §3, two lines of numpy.

<details><summary>🧰 numpy: solve instead of invert, and random numbers</summary>

```python
S = np.array([[4.0, 1.0], [1.0, 2.0]])
r = np.array([1.0, 3.0])
w = np.linalg.solve(S, r)     # the w with S @ w = r, i.e. S⁻¹ r — without computing S⁻¹ (faster, safer)
r @ w                          # the dot product of two vectors: one number
rng = np.random.default_rng(7)         # ONE generator, seeded: the same numbers at every run
z = rng.standard_normal((5, 3))        # a 5 × 3 table of standard normal numbers (mean 0, σ 1)
(z ** 2).sum(axis=1)                   # 5 numbers: the sum of squares of each ROW
```
</details>

```bash
python3 run_uncertainty.py test
```

> [!TASK]
> **Predict** (`PREDICT_CIRCLE`): the judge's circle (radius = the judge's σ of Step 2) and the 1-sigma ellipse
> — which one will hold more of the 600 fixes, and why? Then:

```bash
python3 run_uncertainty.py cloud
```

```bash
python3 chi2_sim.py
```

Open `out/chi2.png`.

> [!TASK]
> Write `INSIDE_1SIGMA_PCT` (fixes inside the 1-sigma ellipse, `cloud`), `CIRCLE_1_PCT` (inside the judge's
> circle, k = 1) and `SIM_P95` (the d² that 95 % of your simulated errors stay below, `chi2_sim.py`).
> `EXPLAIN_CHI2`: why does the 1-sigma ellipse hold about 39 % on a map when ±1σ holds 68 % on one axis, and
> why is the 95 % threshold near 6 and not 4?

<details><summary>Stuck? Hints, one at a time</summary>

1. `mahalanobis2`: make r a float array, `np.linalg.solve(S, r)`, then a dot product. Return `float(...)`.
2. ✘ "that is rᵀ S r": you multiplied by S; d² uses S⁻¹. ✘ "that is d": you took the square root; the function
   returns d².
3. ✘ "you divided by the diagonal only": `r[0]**2/S[0][0] + r[1]**2/S[1][1]` forgets b; `np.linalg.solve` uses
   the whole matrix.
4. `d2_samples`: one generator from the seed, an n × 2 table of standard normal numbers, the sum of the squares
   of each row.
5. ✘ "uniform numbers (rng.random)?": `rng.random` draws between 0 and 1; you need `rng.standard_normal`.
   ✘ "that is the distance d": no square root. ✘ "(x + y)² is not x² + y²": square each number, then add.
   ✘ "two runs with the same seed give different numbers": create `rng` inside the function, from `seed`.
</details>

## Step 4 — Carrying a covariance through a function (TODO 5, TODO 6)

Read lesson §4. **TODO 5** `propagate(J, P)`, one line. **TODO 6** `polar_to_en(r_m, bearing_deg, sigma_r_m,
sigma_bearing_deg)`: the radar worked example of §4, written once for any input, using your `propagate`.

<details><summary>🧰 numpy: a diagonal matrix, and returning two things</summary>

```python
np.diag([4.0, 9.0])               # array([[4., 0.], [0., 9.]])
np.array([[1.0, 2.0], [3.0, 4.0]]) # a 2 × 2 matrix written row by row: [row 0, row 1]
def two():
    return np.array([1.0, 2.0]), np.eye(2)    # a tuple (vector, matrix): unpack with v, M = two()
```
</details>

```bash
python3 run_uncertainty.py test
```

The runner simulates a radar at 3 000 m, bearing 300°, σ 8 m and 1°: it draws 20 000 noisy (range, bearing)
pairs, turns each into (east, north), and compares their `sample_cov` with your J P Jᵀ.

> [!TASK]
> **Predict** (`PREDICT_RADAR`), by hand from lesson §4: the long semi-axis a of the J P Jᵀ ellipse, in metres.
> Then run it, and write `RADAR_A_M` (J P Jᵀ) and `MC_A_M` (the 20 000 draws):

```bash
python3 run_uncertainty.py radar
```

> [!TASK]
> **Predict** (`PREDICT_WIDE`): with a bearing σ of 10° (a radio direction finder), what share of the draws
> will fall inside the 95 % ellipse of J P Jᵀ? Then run it, open `out/radar_wide.png`, and write
> `WIDE_INSIDE_PCT`. `EXPLAIN_RADAR`: why is the ellipse long across the line of sight, and why does J P Jᵀ fail
> with 10°?

```bash
python3 run_uncertainty.py radar wide
```

<details><summary>Stuck? Hints, one at a time</summary>

1. `propagate`: `J @ P @ J.T`, after `np.asarray(…, dtype=float)` on both.
2. `polar_to_en`: β and σβ in radians (`math.radians`), en from sin and cos, J as in lesson §4 (row 0 = the
   derivatives of east, row 1 = of north), P_polar = `np.diag([σr², σβ²])`, then your `propagate`.
3. ✘ "57² = 3 283 times too large": σβ is still in degrees. ✘ "east and north are swapped": a bearing is
   clockwise from NORTH, so east = r sin β, north = r cos β.
4. ✘ "two shapes do not fit in a matrix product" in the 1 × 2 case: J P J (no transpose) cannot work when J is
   not square.
</details>

> [!TIP] 🏅 End of session 1 — Ellipse maker
> Press **✔ Check my work**. When the checks of TODO 1–6 and Steps 0–4 pass, you earn the **Ellipse maker**
> badge. If the class session ends here, stop here.

## Session 2 — Gatekeeper (1 h 30–2 h 30)

Read lesson §5–§7 first.

## Step 5 — The judge: six fixes after a GPS outage (TODO 7)

**TODO 7** `gate(r, S, p=0.99)`: lesson §5. The number of degrees of freedom is the length of r.

```bash
python3 run_uncertainty.py test
```

```bash
cat /data/academy/27-uncertainty/judge.json
```

The drone flew 40 s on visual odometry along a track at bearing 120°; `P_pred` is its predicted covariance,
GPS states σ 3 m. Six candidate fixes, A–F, each one a separate situation.

> [!TASK]
> **Predict** (`PREDICT_JUDGE`): from the numbers only (no running yet), which of A–F will a 99 % gate accept?
> Then:

```bash
python3 run_uncertainty.py judge
```

Open `out/judge.png`. The column "never-grown" is a predictor that kept σ 5 m for the whole outage; "circle"
is a rule that accepts any fix within 160 m.

> [!TASK]
> Write `D2_A` (fix A's d²) and `N_ACCEPT_99` (how many fixes your 99 % gate accepts). Suppose the truth is A
> (odometry drifted along the track) and B is a spoofer. `EXPLAIN_JUDGE`: why is E refused although it is
> nearer than A? What would the never-grown predictor and the 160 m circle each do here, and what happens to
> the never-grown predictor on the next fixes?

<details><summary>Stuck? Hints</summary>

1. `gate`: r as a float array, its d² (your TODO 3), the threshold from the given `chi2_threshold(p, len(r))`,
   and `bool(d2 <= threshold)`.
2. ✘ "a 2-D r uses 2 degrees of freedom": you used dof = 1 (6.63). ✘ "did you compare d (6), not d², with the
   threshold?": every fix passes, even D. ✘ (Check my work) "not 3 sigma (9)": the threshold comes from
   `chi2_threshold`, not from k = 3. ✘ "a bool": return `bool(…)`, not the number.
</details>

## Step 6 — The attacker

You are now the spoofer. Where can a fake fix go without being refused? The runner moves a fake fix away from
the prediction every 5°, and finds by bisection the largest offset your gate accepts.

```bash
python3 run_uncertainty.py attack
```

> [!TASK]
> Write `ATTACK_MAX_M` and `ATTACK_MIN_M` (the longest and shortest accepted offsets). `EXPLAIN_ATTACK`: which
> direction does the attacker choose, why, and which formula of lesson §5 gives these two numbers? What would
> make the attacker's room smaller, and what would that cost the defender?

## Step 7 — Fusing GPS with day vision (TODO 8)

**TODO 8** `fuse(x1, P1, x2, P2)`: lesson §6.

<details><summary>🧰 numpy: the inverse of a matrix</summary>

```python
A = np.array([[4.0, 1.0], [1.0, 2.0]])
Ai = np.linalg.inv(A)          # array([[ 0.2857, -0.1429], [-0.1429,  0.5714]])
A @ Ai                         # the identity (to rounding)
1 / A                          # NOT the inverse: it divides each NUMBER (and fails on a 0)
```
</details>

```bash
python3 run_uncertainty.py test
```

The drive (`fusion.csv`): open sky, a street canyon at 40° from east (t 120–279 s, GPS long along the street),
open sky again. Vision states σ 15 m and is honest — except a few wrong map matches, hundreds of metres off.
The runner compares five policies: GPS alone, vision alone, fuse every pair, gate then fuse (your 99 % gate on
vision − GPS, with S = P_gps + P_vision), and the same when vision **states 5 m** (a liar).

> [!TASK]
> **Predict** (`PREDICT_FUSE`): will "fuse every pair" have a smaller or larger RMS error than GPS alone? Why?
> Then:

```bash
python3 run_uncertainty.py fuse
```

Open `out/fuse.png`.

> [!TASK]
> Write `RMS_GPS_M`, `RMS_ALL_M` (fuse every pair), `RMS_GATED_M` (gate, then fuse), `COVER_GATED_PCT` and
> `COVER_LIAR_PCT` (the coverage of "gate, then fuse" and of its liar version), and `LIAR_REFUSED` (good vision
> fixes the gate refused when vision states 5 m). `EXPLAIN_FUSE`: why can fusing everything be worse than GPS
> alone although its p95 is better, and what does the liar do to the coverage and to the gate?

<details><summary>Stuck? Hints, one at a time</summary>

1. Three lines: the two informations `np.linalg.inv(P1)`, `np.linalg.inv(P2)` (after `np.asarray`), the fused
   P, then the fused x. x1 and x2 as float arrays.
2. ✘ "P is the SUM of the informations": P is the inverse of that sum.
3. ✘ "x moves towards the WORSE estimate": x = P (P1⁻¹ x1 + P2⁻¹ x2) — each x with its OWN information.
4. ✘ "is the inverse a matrix inverse (np.linalg.inv), not 1 / P?": `1 / P` divides each number; it is right
   only for diagonal matrices, which is why the docstring example passes.
</details>

## Step 8 — Publishing it honestly (TODO 9)

**TODO 9** `make_covariance(P2, sigma_up_m=None)`: lesson §7 and its table. This one has the least help: the
docstring gives the rules, the lesson the table. **Trace it by hand first:** P2 = [[16, −4], [−4, 9]], no up σ.
Which 9 numbers, which type? Then P2 = [[16, −4], [−3, 9]] with sigma_up_m = 2.0?

<details><summary>🧰 Python: plain floats, and an error with a reason</summary>

```python
import numpy as np
v = np.float64(2.5) * 2
type(v), type(float(v))           # numpy.float64, float — the contract wants Python floats (mission 12)
ok, why = (False, "not symmetric")
if not ok:
    raise ValueError(f"P2 is not a covariance: {why}")
```
`from navera_lite.estimate import is_covariance` is already at the top of uncertainty.py.
</details>

```bash
python3 run_uncertainty.py test
```

```bash
python3 run_uncertainty.py publish
```

The runner takes one second in the street canyon, publishes GPS alone and the gated fusion through your
`make_covariance`, and asks mission 12's judge what it reads. Then it counts, over the whole drive, the
seconds where GPS alone is shown **FIX** while the long axis of its ellipse is longer than 25 m.

> [!TASK]
> Write `STATED_SIGMA_M` (the judge's σ for GPS alone at that second), `WORST_SIGMA_M` (the long semi-axis of
> its ellipse) and `FALSE_FIX_S` (the count). `EXPLAIN_PUBLISH`: why do the two numbers differ, how large can the
> difference get, and what would you change in the judge or in the source?

<details><summary>Stuck? Hints</summary>

1. None first: nine `0.0` and `COV_UNKNOWN`. Otherwise read a, the two east-north terms (P2[0][1] AND P2[1][0],
   each at its own place: index 1 and index 3), c; the up variance and the type from the docstring's rules.
2. Build the list, ask `is_covariance(cov9)`, raise if it says no, else return `(cov9, kind)`.
3. ✘ "never publish it": an impossible matrix was published — ask `is_covariance`. ✘ (Check my work) "copied
   from BOTH places": you put P2[0][1] at index 1 AND 3, so an asymmetric P2 looks symmetric and is published.
4. ✘ "the up variance is a guess, so APPROXIMATED": no up σ given → type 1. ✘ "not a Python float": `float(x)`.
</details>

## Step 9 — A memo for the autopilot integrator

An integrator connects NAVERA Lite to an autopilot and asks: "what does your σ mean, when do you refuse a
position, and why not average all your sources?" Open [report.md](file:./report.md) and answer under its three
headings, 150 to 350 words, in your own words, with **your** numbers (units!): at least the coverage and RMS of
"gate, then fuse", and the 39 % of a 1-sigma ellipse.

> [!TASK]
> Write `report.md` (three headings unchanged). Then press **✔ Check my work**: all checks should be green.

## Step 10 — Look back (not graded)

Write `LOOK_BACK` in `answers.py`: 1. The mission brief's drone landed after 45 s when vision said ±300 m and
lasted 91 s with ±500 m. Using §5, give one way a too-small σ can make an autopilot's filter give up. 2. Which
of your nine functions would you test first in a real flight log, and with what data?

## Going further (optional)

- **The tilted judge.** Write `honest_sigma(cov9)` that returns √λ₁ of the horizontal block, and rerun Step 8's
  count with it. How many of the false FIX seconds disappear? What would you lose?
- **Gate ROC.** Run "gate, then fuse" with p in 0.9, 0.95, 0.99, 0.999 (copy `run_policy` from
  `run_uncertainty.py` into your own script) and plot wrong matches accepted against good fixes refused.
- **Correlated sources.** Make vision's error a copy of GPS's error plus noise (ρ = 0.5) and measure the
  coverage of your `fuse`. Mission 29 does this properly.
- **Fly your own mission 12.** `cp ../12-position-message/navera_lite/estimate.py navera_lite/` and run
  `python3 -m pytest navera_lite/tests -q`, then `python3 run_uncertainty.py publish`.
