# Lab 19 — Model, straighten and calibrate the real Insta360 lens

**Goal:** write the lens part of NAVERA Lite (`navera_lite/fisheye.py`): the fisheye model, where it is valid,
how wide a straight view should be, the straightening; then calibrate the real lens from 36 real views, test
the result on views it never saw, write a calibration file with NAVERA Lite's tool, and compare it with the
bench's.
**Time:** 4 h to 5 h 30 in two sessions (a strong programmer: about 3 h 30; up to 6 h 30 if numpy is new to you).
**Fast track:** if you know numpy and OpenCV, write the TODOs from the docstrings without the 🧰 and "Stuck?"
boxes, then do "Going further" (*Zhang by hand*) and write `ZHANG_FX` in `answers.py`.

`python3 run_lens.py test` (session 1) and `python3 calibrate_lab.py test` (session 2) name the **symptom** of a
wrong result and the hint to open: try to find the mistake yourself first, then open that hint.

Your files (📝 Code tab): [navera_lite/fisheye.py](file:./navera_lite/fisheye.py) (**your code**: eight
functions, `TODO 1–8`), [answers.py](file:./answers.py), [report.md](file:./report.md), and two tools you only
run: [run_lens.py](file:./run_lens.py) (session 1) and [calibrate_lab.py](file:./calibrate_lab.py) (session 2).

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §1–§2 pinhole vs fisheye, the model | Steps 1–2 | `fisheye_project` |
| §3 where the model is valid | Step 3 | `theta_from_theta_d` |
| §5 how wide | Step 4 | `stretch_at` |
| §4 straightening | Step 5 | `undistort` |
| §6, §8 calibration with OpenCV | Steps 6–7 | `board_points`, `calibrate_fisheye` |
| §7 reprojection error, hold-out | Steps 8–10 | `reprojection_rms`, `holdout_rms` |
| all | Steps 11–12 | the calibration tool, the memo |

The data, in `/data/academy/19-calibration/`, are **real**: 36 frames of NAVERA's Insta360 ONE R recorded during
the bench calibration of 6 October 2026 (top lens only, 1920 × 540; the chessboard is shown on a computer screen),
and the bench's calibration file `insta360_top.yaml`. No camera is needed.

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is never
> marked right or wrong. Each function's docstring says its goal and gives one example with its result; the
> runners' `test` mode tries every example. The lesson shows how; the code is yours.

## Session 1 — Lens modeller (about 2 h 30)

## Step 0 — Pinhole or fisheye?

No code. Two cameras have the same f = 600 px: a pinhole (r = f·tan θ) and an ideal fisheye (r = f·θ).

> [!TASK]
> **Predict** (`PREDICT_EDGE` in `answers.py`): a ray at 80° and a ray at 40° from the optical axis. For **each**
> camera, how many times farther from the image centre does the 80° ray land than the 40° ray? Save the file
> (`Ctrl+S`). Then read lesson §1–§2.

## Step 1 — Look at the data

```bash
ls /data/academy/19-calibration /data/academy/19-calibration/views
```

```bash
cat /data/academy/19-calibration/insta360_top.yaml
```

Find the model, the picture size, the 9 numbers of `camera_matrix` (K, row by row), the 4 numbers of
`distortion` (k1…k4), `rms_px`, `views`, `out_hfov_deg` and `crop`. Then open
[navera_lite/fisheye.py](file:./navera_lite/fisheye.py): read the conventions at the top and the given
`load_calibration()` (it turns the file into K, D and the size) and `theta_d_of()` (the lens polynomial).

```bash
cp /data/academy/19-calibration/views/f0216.jpg .
```

Open [f0216.jpg](file:./f0216.jpg): the screen's edges and the window frame are curved; in the room they are
straight. Note the picture size the calibration is for: it must match the camera's picture exactly.

## Step 2 — The fisheye projection (TODO 1)

**TODO 1** `fisheye_project(X_cam, K, D)`: lesson §2, the five steps and the worked example, for **N points at
once**.

<details><summary>🧰 numpy: work on whole columns, and protect one division</summary>

```python
P = np.array([[1.0, 2.0, 4.0],
              [3.0, 0.0, 2.0]])           # 2 points, one per row
x = P[:, 0] / P[:, 2]                     # array([0.25, 1.5 ]) — column 0 divided by column 2, row by row
np.hypot(x, P[:, 1])                      # √(x² + y²), element by element
s = np.ones_like(x)                       # array([1., 1.])
ok = x > 0.5                              # array([False,  True]) — a mask
s[ok] = 3.0 / x[ok]                       # divide ONLY where the mask is True; elsewhere s stays 1
np.stack([x, s], axis=1)                  # shape (2, 2): one row per point
```
</details>

```bash
python3 run_lens.py test
```

The TODO 1 lines must be ✔ (the others are later TODOs). Then compare your model with OpenCV's on 1000
directions, and look at the picture it draws:

```bash
python3 run_lens.py project
```

> [!TASK]
> With your `fisheye_project` and the bench calibration (a `python3 -c "…"` line or a small file), the pixel of
> X_c = (−1.6, 0.4, 1.4) m: `STEP2_U`, `STEP2_V`; then `PINHOLE_GAP_PX`, its distance to the ideal pinhole pixel
> (fx·a + cx, fy·b + cy) with the same K. Compare with the 19.3 px of the lesson's example.

<details><summary>🧰 a small file to compute with your part</summary>

```python
# try_it.py — run it with: python3 try_it.py
import numpy as np
from navera_lite.fisheye import load_calibration, fisheye_project
cal = load_calibration("/data/academy/19-calibration/insta360_top.yaml")
K, D = cal["K"], cal["D"]
print(fisheye_project(np.array([[1.0, 0.5, 2.0]]), K, D))      # the lesson's worked example
```
</details>

<details><summary>Stuck? Hints, one at a time</summary>

1. θ is the angle from the **axis**: `np.arctan(r)`, with r = √(a² + b²). Not `np.arctan2(b, a)` (that is the
   direction in the image).
2. [[1267.30, 498.01]] is the ideal pinhole and [[1238.19, 482.11]] the ideal fisheye: the lens polynomial
   `theta_d_of(theta, D)` (given) is missing.
3. a and b are multiplied by θ_d / r, the same number for both.
4. v uses fy = `K[1, 1]` and cy = `K[1, 2]`, u uses `K[0, 0]` and `K[0, 2]`.
5. Return one row per point: `np.stack([u, v], axis=1)`, shape (N, 2).
6. `nan` for the point on the axis: start a scale array at 1 (`np.ones_like(r)`) and divide θ_d by r only where
   r > 1e-12 (🧰 above). `np.where(r > 0, θ_d / r, 1)` also works, but numpy still computes 0/0 first and prints a
   RuntimeWarning: harmless; the mask avoids it.
7. "list indices must be integers" or "tuple indices": X_cam can be a plain list (the docstring's example is one):
   start with `X = np.asarray(X_cam, dtype=float)`.
</details>

## Step 3 — Where is the model valid? (TODO 2)

Read lesson §3 first.

**TODO 2** `theta_from_theta_d(theta_d, D)`: lesson §3 and the 🧰 bisection box below. Plan it on paper first:
(1) where does the rising part of θ_d(θ) end on [0, π/2]? (evaluate `theta_d_of` on a fine grid, e.g. 20 001
points, and find the first place where it stops increasing: `np.diff`); (2) which θ_d have no answer?
(3) bisection on the rising part.

<details><summary>🧰 Bisection</summary>

To solve g(θ) = target where g rises on [lo, hi]: take the middle m; if g(m) < target the answer is in [m, hi], else in
[lo, m]. Each step halves the interval; 60 steps are far more than enough.

```python
lo, hi = 0.0, 2.0                  # solve x**3 = 5 on [0, 2]
for _ in range(60):
    m = (lo + hi) / 2
    if m ** 3 < 5: lo = m
    else: hi = m
print(lo)                          # 1.7099759466766968
```
</details>

<details><summary>🧰 numpy: where does an array stop rising?</summary>

```python
y = np.array([0.0, 1.0, 3.0, 4.0, 3.5, 2.0])
np.diff(y)                                # array([ 1. ,  2. ,  1. , -0.5, -1.5]) — y[i+1] − y[i]
np.nonzero(np.diff(y) <= 0)[0]            # array([3, 4]) — y stops rising after index 3
# an EMPTY result (no index at all)? The array rises everywhere: its top is its last value (a lens like that exists)
y[3]                                      # 4.0 — the top
```
</details>

```bash
python3 run_lens.py test
```

```bash
python3 run_lens.py curve
```

Open `out/lens_curve.png`: the pinhole, the ideal fisheye and the bench calibration.

> [!TASK]
> With **your** `theta_from_theta_d`: the angle from the optical axis of pixel (1500, 100) of the bench picture,
> in degrees (`PIXEL_ANGLE_DEG`; lesson §3 shows the way back from a pixel to θ_d). Then `EXPLAIN_TURN_BACK`:
> why does the calibrated curve turn back down after 67.4°, when a real lens never does? (lesson §3, the
> corners' picture)

<details><summary>Stuck? Hints, one at a time</summary>

1. Bisection needs an interval where the function **rises**: [0, θ_top], with θ_top where the grid values stop
   increasing.
2. θ_d = 1.2 has two angles: θ ≈ 1.083 rad (62.0°) on the rising part and θ ≈ 1.249 rad (71.5°) on the falling
   part. Return the rising one: search only in [0, θ_top].
3. θ_d above the top value (or negative): `return float("nan")` before any search. Never type the top of this
   lens (1.249) into your code: find it with the grid, so the function works for any lens (the check uses others).
4. A result near 29.2 instead of 0.5097: you returned degrees; the function returns radians.
5. PIXEL_ANGLE_DEG: a' = (u − cx)/fx and b' = (v − cy)/fy use **different** focal lengths; θ_d = √(a'² + b'²);
   then `math.degrees(theta_from_theta_d(...))`. 48.3°? You used fx for both. 51.8°? That is θ_d in degrees: the
   polynomial is not inverted.
</details>

## Step 4 — How wide should the straight view be? (TODO 3)

Read lesson §5 first.

You are the **trade-off engineer**: the drone's straight view must keep detail for map matching and cover as
much ground as possible.

**TODO 3** `stretch_at(theta_deg, f_new_px, K, D)`: lesson §5, the stretch, with the derivative θ_d′(θ) of the
lens polynomial. Return `nan` where the model is not valid (θ_d′ ≤ 0) and at or beyond 90°.

<details><summary>🧰 the derivative of a polynomial</summary>

The derivative of c·θⁿ is n·c·θⁿ⁻¹. So θ·(1 + k1θ²) = θ + k1θ³ has the derivative 1 + 3k1θ². Example:
k1 = 0.2, θ = 0.5: θ + k1θ³ = 0.525 and its derivative 1 + 3·0.2·0.25 = 1.15.
</details>

> [!TASK]
> **Predict** (`PREDICT_STRETCH`): at the left and right edges of the 111° straight view, how many straight-view
> pixels are made from one lens pixel? Then run:

```bash
python3 run_lens.py test
```

```bash
python3 run_lens.py stretch
```

Open `out/stretch.png`.

> [!TASK]
> Write `STRETCH_EDGE_111`, `H_MAX_DEG` (lesson §5, NAVERA's rule f_new ≥ fx, two decimals) and
> `H_MAX_PARTNER_DEG`: the same rule for a partner's camera with fx = 540 px and pictures 1920 px wide. Then
> `EXPLAIN_FOV`: as the trade-off engineer, why 111° and not 150°? Quote two numbers from the table.

<details><summary>Stuck? Hints, one at a time</summary>

1. Degrees in, radians inside: `t = math.radians(theta_deg)`. A result near 0 or negative: θ is still in degrees.
2. 1.702 instead of 1.474 for (40°, 659.79): you used fx alone below the line; the lens' pixels per radian at θ
   are fx·θ_d′(θ).
3. 1.602: that is θ_d/θ (an average), not the derivative 1 + 3k1θ² + 5k2θ⁴ + 7k3θ⁶ + 9k4θ⁸. 0.679: upside down
   (straight pixels per radian on top).
4. `nan` cases: `if not 0 <= t < math.pi / 2` and `if slope <= 0`: `return float("nan")`.
</details>

## Step 5 — Straighten a real view (TODO 4)

Read lesson §4 first.

**TODO 4** `undistort(img, K, D, K_new)`: lesson §4 and §8 — the map once, then remap. No rotation
(`np.eye(3)`), map type `cv2.CV_16SC2`, bilinear interpolation, a constant (black) border.

<details><summary>🧰 OpenCV: the two calls</summary>

```python
m1, m2 = cv2.fisheye.initUndistortRectifyMap(K, D, R, K_new, (width, height), cv2.CV_16SC2)
out = cv2.remap(img, m1, m2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
```
R is the rotation of the new camera (none here); `(width, height)` is the size of the NEW picture.
</details>

```bash
python3 run_lens.py test
```

```bash
python3 run_lens.py straighten
```

Open `out/before_after.jpg`: the red lines join each row's first and last corner. Before, the corners sag away
from them; after, they sit on them. Try another view too: `python3 run_lens.py straighten f0323`.

> [!TASK]
> Write `BEND_BEFORE_PX` and `BEND_AFTER_PX` (f0216, two decimals), and `EXPLAIN_RESIDUAL`: why is the "after"
> value not 0? (Think of the calibration's RMS, the corner detector and a screen that is not perfectly flat.)

<details><summary>Stuck? Hints, one at a time</summary>

1. The two calls of the 🧰 box, with R = `np.eye(3)` and the NEW camera `K_new`.
2. Wrong shape, or an OpenCV size error: the size is `(w, h)` with `h, w = img.shape[:2]`.
3. The centre of the straight view takes its colour from (cx, cy) of the fisheye picture: if not, check K_new
   (the 4th argument) and the rotation (identity).
4. A coloured bottom row where black is expected: the border mode must be `cv2.BORDER_CONSTANT`
   (`BORDER_REPLICATE` or `BORDER_REFLECT` invent colours where the lens saw nothing).
</details>

> [!TIP] 🏅 End of session 1 — Lens modeller
> Press **✔ Check my work**. When checks 1–6 pass (TODO 1–4 and Steps 0–5; the others are session 2), you earn
> the **Lens modeller** badge. If the class session ends here, stop here.

## Session 2 — Calibrator (about 2 h 30)

Read lesson §6–§8 first.

## Step 6 — The board (TODO 5)

**TODO 5** `board_points(cols, rows, square_m)`: lesson §8, "Corners": the board is the plane Z = 0, in the
detector's order, shape (cols·rows, 1, 3), float64. Fast track: one line with `np.mgrid` (or `np.meshgrid`) and
`reshape`.

```bash
python3 calibrate_lab.py test
```

Then find the corners in the 36 real views (about 30 s; the result is cached in `corners.npz`):

```bash
python3 calibrate_lab.py detect
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Two loops, rows outside, columns inside: the point of row r, column c is (c·s, r·s, 0).
2. If the ROW index changes fastest in your list ([[0, 0, 0], [0, 0.5, 0], [0.5, 0, 0], …]): swap the loops. If the
   order is right but x and y are swapped ([[0, 0, 0], [0, 0.5, 0], [0, 1.0, 0], [0.5, 0, 0], …] for 3 × 2): x is
   the COLUMN (c·s), y the ROW (r·s) — swap the values, not the loops.
3. Start from `np.zeros((rows * cols, 1, 3))` and fill `obj[i, 0, 0]` and `obj[i, 0, 1]`; zeros are float64.
</details>

## Step 7 — Calibrate (TODO 6) — and the detective

**TODO 6** `calibrate_fisheye(obj, views, size)`: lesson §8, the call, with the three flags the docstring describes,
`CRITERIA` (given at the top of the file), K0 = identity, D0 = four zeros (placeholders: lesson §8). **Do not** catch
`cv2.error`: the given `calibrate_robust()` reads the refused view's number in it.

| Flag | Meaning |
|---|---|
| `cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC` | re-estimate every board pose at each step of the refinement |
| `cv2.fisheye.CALIB_CHECK_COND` | refuse a view whose pose cannot be estimated reliably (ill-conditioned) |
| `cv2.fisheye.CALIB_FIX_SKEW` | keep K[0, 1] = 0 |
| `cv2.fisheye.CALIB_FIX_K3`, `…_FIX_K4` | freeze some k's (not today; "Going further") |
| `cv2.fisheye.CALIB_USE_INTRINSIC_GUESS` | start from your K0 instead of the picture's size (not today) |

Flags are combined with `|`.

> [!TASK]
> **Predict** (`PREDICT_FX`): will your fx be the bench's 660.5 px? Then:

```bash
python3 calibrate_lab.py test
```

```bash
python3 calibrate_lab.py calibrate
```

It calibrates with all the views, dropping those OpenCV refuses, prints fx, fy, cx, cy, D, the RMS, and one line
per view: its RMS (once TODO 7 is done), its farthest corner from the axis and the board's columns in the picture.

> [!TASK]
> Write `MY_FX`, `MY_RMS`, `VIEWS_USED`, `REFUSED_VIEWS` and `FARTHEST_USED_DEG`. You are now the **detective**:
> compare the refused views' lines with the others (and look at them: `cp /data/academy/19-calibration/views/f0208.jpg .`).
> `EXPLAIN_REFUSED`: what do the refused views have in common, and why can OpenCV not estimate their pose
> reliably? What does refusing them cost the calibration? Compare `FARTHEST_USED_DEG` with the 52° of lesson §3:
> where were the corners between 43° and 52°, and what does your calibration now know about the edges of the 111°
> view (55.5°)?

<details><summary>Read this after you wrote EXPLAIN_REFUSED</summary>
f0023 and f0208 reach farthest to the right (44.6° and 51.8°), where no other view has corners. In that part of the
picture the lens model is still poorly known while OpenCV estimates the poses, and nothing else ties those two poses
down, so their equations are nearly dependent (ill-conditioned): tiny corner errors would swing the pose a lot.
OpenCV drops them, and with them every corner beyond 43°.
</details>

<details><summary>Stuck? Hints, one at a time</summary>

1. `cv2.fisheye.calibrate([obj] * len(views), views, size, np.eye(3), np.zeros((4, 1)), flags=…, criteria=CRITERIA)`
   returns five things: return them as they come.
2. Flags are combined with `|`: the three of the table above that recompute the poses, check the conditioning
   and fix the skew.
3. The test says the skew K[0, 1] ≠ 0: the "fix skew" flag is missing. calibrate_robust refuses nothing and the
   RMS looks fine? `CALIB_CHECK_COND` is missing.
4. "returned None" from calibrate_robust: a `try/except` inside your function swallowed the error — remove it.
</details>

## Step 8 — The reprojection error (TODO 7)

**TODO 7** `reprojection_rms(obj, views, rvecs, tvecs, K, D)`: lesson §7. For each view: R from the Rodrigues
vector (`cv2.Rodrigues(rvec)[0]`), the board corners in the camera frame X_c = R·X + t, **your**
`fisheye_project`, then the errors against the detected corners. Return the RMS over all corners and the list of
per-view RMS values.

<details><summary>🧰 numpy: R·X for many points at once</summary>

```python
O = np.array([[1.0, 0.0, 0.0],
              [0.0, 2.0, 0.0]])          # 2 points, one per row
R = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
t = np.array([[0.0], [0.0], [5.0]])      # OpenCV gives a (3, 1) column
O @ R.T + t.reshape(1, 3)                # array([[ 0., 1., 5.], [-2., 0., 5.]]) — each row is R·X + t
```
</details>

```bash
python3 calibrate_lab.py test
```

```bash
python3 calibrate_lab.py calibrate
```

Your RMS must now equal OpenCV's (to 10⁻⁶ px), and every view has its own RMS.

> [!TASK]
> Write `WORST_VIEW`: the used view with the largest RMS.

<details><summary>Stuck? Hints, one at a time</summary>

1. `O = np.asarray(obj, dtype=float).reshape(-1, 3)` and `np.asarray(view).reshape(-1, 2)`: OpenCV's (N, 1, 3)
   and (N, 1, 2) arrays become (N, 3) and (N, 2).
2. Use `O @ R.T`, not `O @ R`: the 🧰 box applies R to each row.
3. 0.7 instead of 0.5 in the test: a distance is √(du² + dv²), not du + dv. 0.25: take the square root.
4. 0.5 instead of 0.7071: you averaged the per-view RMS values. Collect the squared errors of **all** corners
   (a list, then `np.concatenate`), average them, then the square root.
</details>

## Step 9 — How stable is fx?

```bash
python3 calibrate_lab.py stability
```

It calibrates random subsets of 8, 12, 20 and 30 views, 10 times each, with your functions (about 30 s), and prints
the mean, std, min and max of fx for each size.

> [!TASK]
> **Before you run it, predict** (`PREDICT_STD`): the std of fx, in px, with 8 views and with 30 views. Then run it,
> write `FX_STD_8` and `FX_STD_30`, and `EXPLAIN_STABILITY`: what do these spreads say about a calibration with
> "RMS 0.5 px", and about how many views to take? Keep the 30-view min and max in mind for Step 11.

## Step 10 — The honest test (TODO 8)

**TODO 8** `holdout_rms(obj, test_views, K, D)`: the least guided function. Lesson §7, point 1, says what is
missing for an unseen view and which two OpenCV calls find it; the docstring says what to return. Plan on paper:
what does each call need and give, and which of **your** functions finishes the job?

```bash
python3 calibrate_lab.py test
```

```bash
python3 calibrate_lab.py holdout
```

It keeps 8 fixed test views, calibrates on the 28 others (OpenCV refuses some of them: the runner says how many
were used), tests with your `holdout_rms`, then does the same with the Brown–Conrady model (given). Then compare
the three models where it matters, the angle each one gives to the same pixel:

```bash
python3 calibrate_lab.py curves
```

Open `out/my_curves.png`: along the principal point's row, the angle each model gives to a pixel, against the
pixel's distance from the principal point. Grey: beyond the farthest corner your calibration used.

> [!NOTE]
> Brown–Conrady's fx (≈ 740–750 px) is not comparable with the fisheye's (≈ 670 px): another formula, so another
> meaning of fx, with its own principal point and its own board distances (lesson §7, point 3). That is also why,
> inside the data, its angles differ from the fisheye's by up to about 3.5° (more on the left, where its principal
> point is shifted; it does not give 0° at your principal point) while both predict the same corners: each model
> places the boards differently. Look at what happens beyond the grey line, near the picture's edges.

> [!TASK]
> Write `TRAIN_RMS`, `TEST_RMS`, `BC_TEST_RMS` (three decimals), and `REASON_BC`: the lesson says a fisheye lens
> needs the fisheye model, yet Brown–Conrady does as well on the hold-out. Why is there no contradiction? (Where
> are the test corners? Where do the curves part, and what does Brown–Conrady do near the picture's edge?)

<details><summary>Stuck? Hints, one at a time</summary>

1. For each test view: `cv2.fisheye.undistortPoints(view, K, D)` gives the corners as ideal pinhole rays
   (normalised coordinates).
2. `cv2.solvePnP` finds the board's pose from those rays, with K = identity and no distortion, because the rays are
   already normalised. It returns three things: `ok, rvec, tvec`.
3. Collect the rvecs and tvecs, then your `reprojection_rms(obj, test_views, rvecs, tvecs, K, D)` does the rest.
4. About 13 px instead of about half a pixel? You ran solvePnP on the raw fisheye pixels with K and no distortion: the
   pose is wrong. Undo the lens first (hint 1).
</details>

## Step 11 — Your calibration file, made by a tool

NAVERA Lite's calibration tool does what NAVERA's does (lesson, "In NAVERA"), with **your** `board_points` and
`calibrate_fisheye`:

> [!TASK]
> **Before** you run the tool, compute from your `MY_FX` the `out_hfov_deg` it will write (lesson §5, NAVERA's
> rule; two decimals): `CLI_HFOV_DEG`. Then run it and check.

```bash
python3 -m navera_lite.tools.calibrate --images /data/academy/19-calibration/views --board 9x6 --square-mm 32.94 --out my_calib.yaml
```

- `--board 9x6`: the inner corners, 9 columns × 6 rows; `--square-mm 32.94`: one square's side.
- The views are already the top halves. For full two-lens pictures you would add `--crop top`, and the file
  would record the crop, as NAVERA's does.

```bash
cat my_calib.yaml
```

Same detector, same flags, same views: its fx should be yours, and its `out_hfov_deg` your `CLI_HFOV_DEG`. Now
three facts disagree with the bench file: your fx is not 660.5 px, the file's `out_hfov_deg` is not 111, and
(Step 10) Brown–Conrady was as good as the fisheye model. You explained the third in `REASON_BC`. Three facts help
with the first: (1) the course's 36 views are 36 of the bench session's 39: three were left out of the dataset, two
of them because a person's face is visible; (2) in Step 9, none of your 30-view subsets came near 660.5 px: compare
their min and max with 660.5; (3) your calibration and the bench's both say RMS ≈ 0.5 px.

> [!TASK]
> Write `REASON_FX` (two reasons why your fx is not the bench's) and `REASON_HFOV` (why your file says
> `CLI_HFOV_DEG` and not 111°: lesson §5).

<details><summary>Read this after you wrote REASON_FX</summary>
Measured on the host from the original bench frames: the 36 course views give fx 670.2 px before any JPEG re-save
and with no view refused. The JPEG re-save moves the corners by about 0.01 px. Refusing f0023 and f0208 together
changes fx by only 0.02 px, but only because they cancel: without f0023 alone fx is 667.6 px, without f0208 alone
672.6 px. The 10 px come from the three views the dataset left out: which views you take moves fx more than the
RMS can show, and fx trades against the boards' distance at the same RMS (lesson §7, point 3).
</details>

## Step 12 — The memo, then look back

Fill [report.md](file:./report.md) (150–400 words, your own words, keep the three headings): what the lens model
says and how wide the straight view should be; your calibration and how far you trust it; and your
**recommendation** for calibrating a new NAVERA unit before a field test (for example in a partner's workshop in
Singapore): 3–5 concrete rules, from your numbers.

> [!TASK]
> report.md has the three headings and at least 150 words, and quotes the widest straight view (Step 4), your fx
> and your hold-out (test) RMS (Steps 7 and 10).

Press **✔ Check my work**: it tests your functions on lenses, views and pictures they have never seen. When every
check passes, you earn the **Calibrator** badge. Then look back, without the lesson:

1. Explain to a colleague in three sentences why NAVERA throws away a third of its lens' view.
2. Which of your predictions was the most wrong? What did you assume?
3. The bench views reach 52° from the axis, but the corners your calibration kept stop at 43°; the 111° view needs
   55.5°. What would you change in the photo session?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **Zhang by hand.** Take 5 views from `corners.npz`, turn their corners into ideal pinhole pixels with
  `cv2.fisheye.undistortPoints(view, K, D, P=K)` (your calibration), fit one homography per view with
  `cv2.findHomography(board_xy, pixels)`, build the two equations per view of the box below on
  b = (B11, B12, B22, B13, B23, B33), solve V·b = 0 with `np.linalg.svd`, and recover fx, fy, cx, cy (Zhang 2000,
  appendix B). How close is `ZHANG_FX` to your refined fx? Expect a surprise. Then print the third column of each
  view's R (`cv2.Rodrigues(rvec)[0][:, 2]`, the board's normal) from your calibration: what do the normals have in
  common? Zhang (2000, §3.3) explains why that breaks the closed form, while the joint refinement (which starts from
  the picture's size, lesson §6) still converges. Check your code on made-up views with varied orientations (as
  `calibrate_lab.py test` makes them): it should recover their fx.

  <details><summary>The two equations of Zhang's closed form</summary>

With the board at Z = 0, s·[u, v, 1]ᵀ = K [r1 r2 r3 t] [X, Y, 0, 1]ᵀ = K [r1 r2 t] [X, Y, 1]ᵀ = H [X, Y, 1]ᵀ.
Write H = [h1 h2 h3] = λ K [r1 r2 t]: then r1 = K⁻¹h1/λ and r2 = K⁻¹h2/λ. Perpendicular columns of equal length
give h1ᵀ B h2 = 0 and h1ᵀ B h1 = h2ᵀ B h2, with B = K⁻ᵀK⁻¹ symmetric: two equations, <b>linear</b> in the 6 entries
of B. Stack them for N ≥ 3 views, solve V·b = 0 with an SVD, and recover K from B (a Cholesky factorisation),
then each pose from H_i and K.
  </details>

- **Fewer numbers.** Add `cv2.fisheye.CALIB_FIX_K3 | cv2.fisheye.CALIB_FIX_K4` to your flags (keep a copy of your
  function first). How do the RMS, the hold-out error and the curve beyond 45° change? Does the curve still turn
  back?
- **Your calibration at work.** Straighten f0216 with `out/my_fisheye.yaml` instead of the bench file, at
  the width your `my_calib.yaml` says. Is the chessboard as straight?
- **Fly your own camera part.** Swap in your mission-18 `camera.py` (keep a backup) and run `python3 run_lens.py
  stretch` again: `cp navera_lite/camera.py camera_course.py && cp ../18-camera-model/navera_lite/camera.py navera_lite/`.
