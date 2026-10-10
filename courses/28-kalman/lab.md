# Lab 28 — Ellipses, gates and a Kalman filter that agrees with NAVERA

**Goal:** implement the uncertainty toolbox of the course (sample covariance, error ellipse, J P Jᵀ,
Mahalanobis gate, information fusion), build a 2-D constant-velocity Kalman filter with a
chi-square gate, test its honesty with NEES, prove that your 1-D filter is NAVERA's real height
filter, and write a short report with your measured numbers.
**Time:** about 4 h for this lab (about 5 h for the whole mission with the lesson).

Your files:

| File | What you do |
|---|---|
| [uncertainty.py](file:./uncertainty.py) | TODO 1–7: the maths of sections 1–5 |
| [kalman.py](file:./kalman.py) | TODO 8–12: the Kalman filter of section 6 |
| [race_navera.py](file:./race_navera.py) | TODO 13: your filter against NAVERA's `VisionNavigator` |
| [analyse.py](file:./analyse.py) | TODO 14–15: gating counts and NEES; it writes `results.json` and three PNGs |
| [report.md](file:./report.md) | your written analysis (4 sections) |

The data in `/data/academy/28-kalman/` is **simulated** (`make_dataset.py` in the same folder
makes it): a receiver standing still in Sousse harbour with a correlated error, a 6-minute drone flight
from Monastir along the coast with a 40 s GPS outage and 6 wrong fixes, and 104 height measurements from three
sources. NAVERA's own recorded data is from Sousse, Tunisia; the simulated scenario of this lab is placed in the same test area.

> [!TIP]
> Every function has a docstring with the exact formula and return type. Read it first. All vectors
> are 1-D numpy arrays and matrices 2-D arrays: `A @ B` is the matrix product, `A.T` the transpose,
> `np.linalg.solve(S, r)` computes `S⁻¹ r` without inverting S. A frequent error:
> `ValueError: matmul: Input operand 1 has a mismatch in its core dimension` — you multiplied a
> (2, 2) by a (4,) vector; print the `.shape` of both.

## Step 1 — Look at the data

```bash
ls -l /data/academy/28-kalman/
```

```bash
head -4 /data/academy/28-kalman/static_fixes.csv /data/academy/28-kalman/track.csv /data/academy/28-kalman/heights.csv
```

`static_fixes.csv` is the error (m) of each fix from the surveyed point. In `track.csv`, `z_e, z_n`
are empty during the outage (t = 150–189 s) and `outlier = 1` marks the wrong fixes — the filter
must **not** read that column (it would be cheating); only the analysis uses it to score the gate.

## Step 2 — Covariance and ellipse (TODO 1–2)

In [uncertainty.py](file:./uncertainty.py), complete `sample_cov(points)` (divide by N − 1) and
`error_ellipse(P, k)` with `numpy.linalg.eigh`. Careful with three details:

1. `eigh` returns the eigenvalues in **ascending** order, and the eigenvectors in the **columns**
   (`vecs[:, 1]` belongs to `vals[1]`).
2. The angle uses `math.atan2(north, east)` and is brought into (−90°, 90°]: an axis has no arrow.
3. The demo matrix of the course, `[[12, 5], [5, 6]]`, must give a = 3.85 m, b = 1.78 m, θ = 29.5°.

```bash
python3 uncertainty.py
```

## Step 3 — Propagation, gate and fusion (TODO 3–6)

- **TODO 3** `chi2_threshold(p, dof)`: `chi2.ppf` from `scipy.stats` (already imported).
- **TODO 4** `propagate(J, P)` and `polar_to_en(...)`: the radar example of the course. Expected:
  east, north = (1732.05, 1000.00) m and the covariance `[[94.9, −121.1], [−121.1, 234.7]]`.
- **TODO 5** `mahalanobis2(r, S)` and `chi2_gate(r, S, p)`. The demo prints d² = 8.17 for (6, −2).
- **TODO 6** `fuse(x1, P1, x2, P2)`, information form. It must accept scalars (`fuse(100, 100, 110, 25)`
  → 108, 20) and 2-D arrays.

```bash
python3 uncertainty.py
```

> [!TASK]
> Complete TODO 1 to 6 in `uncertainty.py`. "Done" means the demo prints the values above and checks
> 1–5 are green.

## Step 4 — A covariance NAVERA's arbiter accepts (TODO 7)

`make_covariance(P2, sigma_up)` builds the 9 numbers of `PositionEstimate.position_covariance` from a
2 × 2 horizontal covariance, and the covariance **type**: 3 (KNOWN) when there is a correlation term,
2 (DIAGONAL_KNOWN) when not, and 0 (UNKNOWN) with nine zeros when `P2` is `None`. Return Python
floats: a ROS `float64[9]` field refuses numpy values and integers (`9.0`, not `9`).

Then ask NAVERA's real arbiter — its `_sane()` and `_stated_sigma()` are static methods you can call:

```bash
python3 -c "from uncertainty import estimate_message as m; from navera_estimator.nodes.estimator_node import EstimatorNode as E; x = m(35.76, 10.81, [[12.0, 5.0], [5.0, 6.0]]); print(list(x.position_covariance), x.position_covariance_type, E._sane(x), E._stated_sigma(x))"
```

You should see your 9 numbers, type `3`, `True` and `3.464…` (√12). Compare with a = 3.85 m from
Step 2: you will discuss this difference in the report.

> [!TASK]
> Complete TODO 7. "Done" means checks 6 and 7 are green: the real arbiter accepts your correlated
> covariance and reads "uncertainty unknown" for `None`.

## Step 5 — The Kalman filter (TODO 8–12)

In [kalman.py](file:./kalman.py):

- **TODO 8** `cv_model(dt, q, dims)`: F and Q of the course, with `np.kron(F1, np.eye(dims))`.
- **TODO 9** `kf_predict`, **TODO 10** `kf_update` (return `x, P, nu, S`), **TODO 11** `nees`.

```bash
python3 kalman.py
```

The demo is the worked example of the course: after the barometer update you must read
`x = [82.56 0.812]` and `P = [[1.92 0.609] [0.609 3.176]]`.

- **TODO 12** `run_filter(times, zs, sigma_z, q, gate_p)`: the loop. Follow the docstring
  **exactly** (start state, start covariance, one entry per time, `accepted` is `None` when there is
  no measurement), because the check compares your numbers with the reference.

> [!TASK]
> Complete TODO 8 to 12. "Done" means checks 8–11 are green: one step by hand matches the course,
> and on the coastal track your gated filter refuses the 6 outliers, makes exactly 3 false alarms,
> reaches an RMSE of 4.48 m on the measured steps, and its σ grows to about 92 m at the end of the
> outage.

## Step 6 — Race NAVERA's height filter (TODO 13)

NAVERA's day-vision navigator keeps the height above ground in a Kalman filter written with plain
lists (`~/navera/day_pkg/day_pkg/vision_nav.py`, `_height_predict` / `_height_update`). Look at it:

```bash
grep -n "_height_predict" -A 24 ~/navera/day_pkg/day_pkg/vision_nav.py
```

Complete `student_heights(rows)` in [race_navera.py](file:./race_navera.py) with **your** `cv_model`
(`dims=1`), `kf_predict` and `kf_update`, with the same model and start as NAVERA (in the docstring),
then run the race:

```bash
python3 race_navera.py
```

The script feeds the same 104 heights to both filters. You want `SAME FILTER`: a largest
difference below 10⁻⁶ m (floating-point rounding only). If you see differences of a few metres,
check your start covariance and that `dt` is the time between consecutive rows.

> [!TASK]
> Complete TODO 13. "Done" means `python3 race_navera.py` prints `SAME FILTER` and writes `race.json`
> (check 12).

## Step 7 — The analysis (TODO 14–15)

[analyse.py](file:./analyse.py) uses all your functions. Complete:

- **TODO 14**: from `gated["accepted"]` and the `outlier` column, count `caught` (outliers refused)
  and `false_alarms` (good fixes refused). `accepted` is `True`, `False` or `None` — compare with
  `is False`.
- **TODO 15**: the mean NEES of the gated filter and its 95 % band
  `[chi2_threshold(0.025, 2N) / N, chi2_threshold(0.975, 2N) / N]`.

```bash
python3 analyse.py
```

Then open the three pictures in the editor and look at them carefully:
[ellipse.png](file:./ellipse.png) (do the 39 / 95 / 99 % ellipses contain what they should?),
[track.png](file:./track.png) (where are the outliers? what happens to the 3σ ellipse in the gap?),
[nees.png](file:./nees.png) (where does the NEES leave the band, and why?).

> [!QUESTION]
> Look at the `q sweep` line. With q = 0.003 the RMSE is more than 2 km. The truth did not change, the
> measurements did not change: what happened at the end of the 40 s gap? Look at the gate.

<details><summary>Answer</summary>
With a tiny q the filter believes the drone flies in a perfectly straight line, so its P stays small
during the outage while the real drone turns. When the fixes come back, d² is enormous: the gate
refuses them, P stays small, and every later fix is refused too. The filter is lost for good —
an overconfident filter plus a gate is a trap. This is why process noise must be measured, not
guessed small "to make the output smooth".
</details>

> [!TASK]
> Complete TODO 14–15 and run `python3 analyse.py` with `Q_FILTER = 0.3` and `GATE_P = 0.99`.
> "Done" means `results.json` and the three PNG files exist and the values are right (checks 13–14).

## Step 8 — Your report

Open [report.md](file:./report.md) and replace each TODO paragraph with your analysis: at least
40 words per section, the numbers it asks for (from **your** `results.json` — 2 decimals is fine),
and your reasoning. To read the numbers:

```bash
python3 -m json.tool results.json
```

```bash
cat race.json
```

For section 4 you need two numbers you compute yourself: the probability of NAVERA's 3-sigma vision
gate for a round 2-D error, `1 − exp(−9/2)`, and the σ that `_stated_sigma()` reads for the harbour
covariance (`static.navera_stated_sigma_m` in `results.json`), compared with the semi-major axis a.

```bash
python3 -c "import math; print(100 * (1 - math.exp(-4.5)))"
```

> [!TASK]
> Write `report.md` (four sections, headings unchanged, no TODO left). The check verifies the
> structure, the length and that each section quotes the right numbers. Press **✔ Check my work**:
> all 15 checks should be green.

## Going further (optional)

- **ROC of the gate.** Run `run_filter` with `gate_p` in `[0.9, 0.95, 0.99, 0.999, 0.99999]` and plot
  false alarms against missed outliers. Which p would you choose for a drone that cannot afford to
  follow a spoofed fix? Lesson 30 does this properly.
- **Mis-stated R.** Run the filter with `sigma_z = 2.0` and `sigma_z = 15.0` while the real noise is
  5 m. Predict first what happens to the mean NEES, then measure it.
- **The tilted-ellipse fix.** Write a function that returns `sqrt(largest eigenvalue)` of the
  horizontal block of a `PositionEstimate` covariance, and compare it with `_stated_sigma()` for the
  radar covariance of Step 3. In which situations would NAVERA's choice give a FIX that should be
  DEGRADED (σ ≤ 25 m on the diagonal, > 25 m along the long axis)?
- **Joseph form.** Replace `P = (I − K H) P` by `(I − KH) P (I − KH)ᵀ + K R Kᵀ` and check that the
  result is the same here. Why do flight-grade filters prefer it?
