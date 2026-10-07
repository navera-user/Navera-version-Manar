# Lab 26 — Measure the spread, draw the circles, fuse two sources

**Goal:** write the basic statistics yourself, use them on 300 fixes of a receiver standing still,
draw the 1σ / 2σ / 3σ circles, show that a weighted average beats both of its inputs, and build a
covariance that NAVERA's real arbiter accepts.
**Time:** about 1 h.

Your files: [uncertainty.py](file:./uncertainty.py) (the maths, TODO 1–6),
[analyse.py](file:./analyse.py) (the analysis, TODO 7–9), [answers.py](file:./answers.py) (quiz).

The data, in `/data/academy/26-uncertainty/` (read only), is **simulated** (made by
`make_dataset.py` in the same folder): a receiver standing still at NAVERA's GPS test site in
M'saken, measured 300 times by a GPS (σ ≈ 2 m) and by a vision source (σ 6–8 m, with **3 wrong
matches**), plus two independent sources A and B side by side.

## Step 1 — Look at the data

```bash
ls /data/academy/26-uncertainty/
```

```bash
head -5 /data/academy/26-uncertainty/gps_fixes.csv
```

Each line is a time and a position. The receiver did not move, yet the positions change in the 5th
or 6th decimal: that is the noise. (Lesson 6: 0.00001° of latitude ≈ 1.1 m.)

## Step 2 — Mean, median, standard deviation (TODO 1–3)

Open [uncertainty.py](file:./uncertainty.py) and complete `mean`, `median` and `std`. Then run the
demo with the ten dice throws of the course:

```bash
python3 uncertainty.py
```

You should read `mean 3.8`, `median 4.0` (or `4`), and `std 1.66…`.

> [!TIP]
> For `median`, `s = sorted(values)`, `n = len(s)`, `mid = n // 2` (`//` divides and drops the
> decimals). With 10 values the two middle ones are `s[4]` and `s[5]`, i.e. `s[mid - 1]` and `s[mid]`.
> For `std`, reuse your own `mean()`.

## Step 3 — Share within a circle, and the weighted average (TODO 4–5)

`share_within(errors, radius)` returns the **fraction** of errors that are `<= radius` (0.5 means half).

`fuse(x1, s1, x2, s2)` is the formula of the course: weights `1/s²`, the weighted average, and the new
σ `1 / sqrt(w1 + w2)`. Return both: `return x, s`.

```bash
python3 uncertainty.py
```

The demo fuses 100 m (σ 10) and 110 m (σ 5): you should get `(108.0, 4.47…)`.

> [!TASK]
> Complete TODO 1 to 5 in `uncertainty.py`. "Done" means `python3 uncertainty.py` prints the values
> above, and checks 1–5 are green when you press **✔ Check my work**.

## Step 4 — The analysis (TODO 7–9)

[analyse.py](file:./analyse.py) loads the three files, converts each fix to metres east / north of the
truth (`to_local_m`, lesson 6), and uses **your** functions. Run it once now:

```bash
python3 analyse.py
```

It already prints the GPS and vision statistics. Look at the vision line: **mean 10.2 m but median
8.3 m** — three wrong matches out of 300 moved the mean, not the median.

Now complete:

- **TODO 7** — the share of GPS fixes inside the 1σ, 2σ and 3σ circles: `share_within(dist, k * sigma)`.
- **TODO 8** — for each row of `two_sources.csv`, fuse A and B **on each axis separately** (east with
  east, north with north), then append the distance `math.hypot(fused_east, fused_north)`.
- **TODO 9** — draw the three circles on the plot:
  `ax.add_patch(plt.Circle((0, 0), k * sigma, fill=False, color=color, lw=2, label=label))`.

```bash
python3 analyse.py
```

Then open [error_circles.png](file:./error_circles.png) in the editor.

> [!QUESTION]
> The GPS gives 39 % / 89 % / 97 % inside 1σ / 2σ / 3σ, a perfect Gaussian 39 / 86 / 99 %. Close, but
> not identical. Look at the course and at the dataset description: what in this simulated GPS is not
> pure, independent noise?

<details><summary>Answer</summary>
Its error wanders slowly (a "random walk" that drifts and comes back, like a real receiver): successive
fixes are not independent, and 300 fixes cover only a few "wanders". Real errors are never perfectly
Gaussian — which is why the honesty test looks at several circles, not one.
</details>

> [!TASK]
> Complete TODO 7–9 and run `python3 analyse.py`. "Done" means `results.json` and
> `error_circles.png` exist, the share inside each circle is right, and the **fused** median error is
> smaller than both A's and B's. Press **✔ Check my work**.

## Step 5 — A covariance the real arbiter accepts (TODO 6)

Complete `make_covariance(sigma_east, sigma_north, sigma_up=None)`: the 9 numbers of
`position_covariance` (variances on the diagonal, everything else 0) and the type
(`COVARIANCE_TYPE_DIAGONAL_KNOWN`), or nine zeros and `COVARIANCE_TYPE_UNKNOWN` when a σ is `None`.

Below the line, `estimate_message()` puts your covariance into a real `navera_msgs/PositionEstimate`.
Ask NAVERA's own arbiter what it thinks of it — its `_sane()` and `_stated_sigma()` are plain
functions you can call:

```bash
python3 -c "from uncertainty import estimate_message as m; from navera_estimator.nodes.estimator_node import EstimatorNode as E; x = m(35.734, 10.576, 3.0, 4.0); print(list(x.position_covariance), E._sane(x), E._stated_sigma(x))"
```

You should see your 9 numbers, `True` (it is a real covariance) and `4.0` (the arbiter keeps the
**larger** horizontal σ — the cautious choice). Try `None, None` instead of `3.0, 4.0`: the arbiter
reads `None` — "uncertainty unknown" → DEGRADED.

> [!TASK]
> Complete TODO 6. "Done" means the real arbiter accepts your covariance (check 7). Then answer the
> quiz in [answers.py](file:./answers.py) and press **✔ Check my work**.

## Going further (optional)

- **Break it on purpose.** In the `python3 -c` command above, build the message, then set
  `x.position_covariance[1] = 5.0` (no longer symmetric) or a negative variance, and call `E._sane(x)`
  again. What does the arbiter say? Why would a filter downstream break on it?
- **Draw the ellipse.** With numpy, `numpy.cov([east, north])` gives the 2 × 2 covariance of the GPS
  fixes. Its `numpy.linalg.eigh` gives the axes of the 1σ ellipse (square roots of the eigenvalues)
  and their directions. Draw it on `error_circles.png` with `matplotlib.patches.Ellipse`.
- **Fusion with an outlier.** Fuse the GPS fixes with the vision fixes (stated σ 2 m and 8 m). Look at
  rows 41, 157 and 233 (the wrong matches): how far do they pull the fused position? Would you fuse
  without checking first?
