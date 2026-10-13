# Lab 18 — Measure the world with a camera

**Goal:** write the camera part of NAVERA Lite (`navera_lite/camera.py`), use it to measure heights and
positions in three drone photos, find out what wrong heights and wrong attitudes cost, straighten a tilted
photo, check everything against OpenCV, and write a short memo.
**Time:** 3 h to 4 h 30 (a strong programmer: about 2 h 30; more if numpy matrices are new to you).
**Fast track:** if you know numpy, write the TODOs from the docstrings without the 🧰 boxes and the "Stuck?" boxes;
then do "Going further" (*Sloped ground*, *A scale gate in numbers*) and write the results under *Going further*
in `answers.py`; your teacher reads them.

`python3 run_camera.py test` names the **symptom** of a wrong result and the hint to open ("Lab Step 2, hint 4"):
try to find the mistake yourself first, then open that hint.

Your files (📝 Code tab): [navera_lite/camera.py](file:./navera_lite/camera.py) (**your code**: eight
functions, `TODO 1–8`), [measure_pad.py](file:./measure_pad.py) (**your code**: `TODO A`, `TODO B`, `TODO C`),
[answers.py](file:./answers.py), [report.md](file:./report.md), and two ready-made tools you only run:
[run_camera.py](file:./run_camera.py) (runs your functions on the lab's situations and draws them) and
[compare_with_opencv.py](file:./compare_with_opencv.py) (an independent check with OpenCV).

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §1–§2 frames, pinhole, K | Steps 1–2 | `focal_px`, `K_from_hfov`, `project` |
| §3 back-projection | Step 3 | `backproject_ground` |
| §4 GSD, measuring | Step 4 | `gsd`, `pad_size_px`, `height_from_size` |
| §3 back-projection on a real photo, §5 | Step 5 | `pad_centre_px` |
| §4 footprint | Step 6 | `footprint` |
| §5 height → scale | Step 7 | (no new code) |
| §6 attitude → position | Step 8 | `tilt_position_error`, the attacker |
| §7 straightening | Steps 9–10 | `nadir_homography`; the OpenCV check |
| all | Step 11 | the memo |

The photos, in `/data/academy/18-camera-model/`, are synthetic: what an ideal camera (960 × 540 px, HFOV 90°)
would see over flat ground, rendered from OpenStreetMap data of Sousse, Tunisia (NAVERA's test area; map
data © OpenStreetMap contributors). We built them, so we know the exact truth.

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is
> never marked right or wrong. Each function's docstring says its goal and gives one example with its
> result; `python3 run_camera.py test` tries every example. The lesson shows how; the code is yours.

## Session 1 — Measurer (about 2 h; 2 h 30 if numpy is new to you)

## Step 0 — Ahead or behind?

No code. A drone flies north, 200 m above flat ground. Its camera is screwed under the body, looking straight
down. To accelerate, the drone pitches **15° nose down**.

> [!TASK]
> **Predict** (`PREDICT_TILT` in `answers.py`): does the centre of the photo now show the ground **ahead** of
> the drone or **behind** it, and how many metres from the point under the drone? Save the file (`Ctrl+S`).
> Then read lesson §1–§3.

## Step 1 — The intrinsic matrix (TODO 1, TODO 2)

Open [navera_lite/camera.py](file:./navera_lite/camera.py). The top holds the conventions, the mount
`R_BODY_NADIR_CAM` and four finished helpers (`camera_rotation`, `camera_rotation_hpr`, `off_nadir_deg`,
`warp_point`): read `camera_rotation_hpr`, you will use it all along. Each `TODO` function keeps its
docstring and ends with `return None   # TODO…`: replace that line with your code.

<details><summary>🧰 numpy: a matrix is an array of rows</summary>

```python
import numpy as np
M = np.array([[2.0, 0.0, 5.0],
              [0.0, 3.0, 7.0],
              [0.0, 0.0, 1.0]])    # 3 rows; write 2.0, not 2, so the array holds floats
M[0, 2]                            # 5.0 — row 0, column 2
M.shape                            # (3, 3)
v = np.array([1.0, 1.0, 1.0])
M @ v                              # array([ 7., 10.,  1.]) — matrix × vector
M.T                                # the transpose: rows become columns
```
</details>

**TODO 1** `focal_px(hfov_deg, width_px)`: lesson §2, "Field of view". **TODO 2** `K_from_hfov(hfov_deg,
width_px, height_px)`: K of lesson §2, with `focal_px` and the principal point at the image centre.

```bash
python3 run_camera.py test
```

The TODO 1 and TODO 2 lines must be ✔ (the others are later TODOs).

> [!TASK]
> With your `focal_px` (a `python3 -c "…"` line), the **vertical** field of view of NAVERA's straightened
> Insta360 view, 1920 × 540 px, HFOV 111°: write `VFOV_INSTA_DEG` (two decimals).

<details><summary>Stuck? Hints, one at a time</summary>

1. The right half of the image, w/2 pixels, is seen under HFOV/2: tan(HFOV/2) = (w/2) / f.
2. −99.9 instead of 1 108.5: `math.tan` got degrees — `math.tan(math.radians(hfov_deg) / 2)`. 369.5: you used
   the whole angle, not half of it.
3. K wrong with (640, 360) in the bottom row: the principal point goes in the last **column**, `K[0, 2]` and
   `K[1, 2]`; the bottom row is `[0, 0, 1]`.
4. `python3 -c "from navera_lite.camera import focal_px; import math; f = focal_px(111, 1920); print(2 * math.degrees(math.atan(270 / f)))"`
   uses the height 540 px through its half, 270.
</details>

## Step 2 — Projection (TODO 3)

**TODO 3** `project(K, R_wc, C, X)`: lesson §2 and worked example 1. First move X into the camera frame (read
the `R_wc` convention at the top of the file), return `None` when the depth is ≤ 0, then apply K and divide.

<details><summary>🧰 numpy: lists in, arrays out</summary>

```python
X = [30, 45, 0]                    # a student, or a test, may pass a list
a = np.asarray(X, dtype=float)     # array([30., 45.,  0.]) — now it subtracts and multiplies
a - np.asarray([0, 0, 150], dtype=float)   # array([  30.,   45., -150.])
b = np.array([2.0, 4.0, 2.0])
b[0] / b[2], b[1] / b[2]           # (1.0, 2.0) — divide by the last number
np.array([1.0, 2.0])               # return two numbers as an array
```
</details>

```bash
python3 run_camera.py test
```

```bash
python3 run_camera.py project
```

`project` prints the pixels of the foot and the top of a 30 m mast, and draws `out/grid.png`: a 20 m ground grid
seen by a level camera and by the same camera 20° nose down. Look where the point under the drone goes.

> [!TASK]
> Write `MAST_LEAN_PX`, the distance in pixels between the mast's top and foot in the image, and
> `EXPLAIN_MAST`: why does the top appear farther from the image centre than the foot, and what does that
> mean for a camera model that assumes flat ground? Then check your idea in lesson §3's box "Read this after
> lab Step 2".

<details><summary>Stuck? Hints, one at a time</summary>

1. Follow worked example 1 line by line: X − C, then into camera axes, then u and v. Make every input an
   array first (🧰 above).
2. `None` for a point in front of the camera: your depth test fired. The depth is the z of R_wcᵀ · (X − C) — C
   is subtracted BEFORE rotating; without it a ground point has depth 0.
3. [576, 318] instead of [576, 222]: north is UP the image (the camera's y points down): keep the sign of Y.
4. [819.4, 451.7] instead of [738.3, 262.3] on the tilted line: you used `R_wc @ …`; world → camera needs
   `R_wc.T @ …`. The level camera, nose north, cannot show this mistake: its R_wc is symmetric.
5. [480, 270] for the point above the camera: the depth test is missing (depth ≤ 0 → `None`).
6. Last hint, the answer line for the camera frame: `X_cam = R_wc.T @ (X - C)`.
7. MAST_LEAN_PX: the top moves in u **and** v — √(Δu² + Δv²).
</details>

## Step 3 — Back-projection (TODO 4)

**TODO 4** `backproject_ground(K, R_wc, C, u, v)`: lesson §3 and worked example 2.

<details><summary>🧰 numpy: K⁻¹ · b without writing the inverse</summary>

```python
A = np.array([[2.0, 0.0], [0.0, 4.0]])
b = np.array([6.0, 8.0])
np.linalg.solve(A, b)              # array([3., 2.]) — the x with A @ x = b, i.e. A⁻¹ · b
np.linalg.inv(A) @ b               # the same, with the inverse written out
```
</details>

```bash
python3 run_camera.py test
```

```bash
python3 run_camera.py centre
```

`centre` prints where the image centre lands for a nose-down pitch from 0° to 25° at 200 m, then a round
trip on 200 random points: ground → `project` → `backproject_ground` must give the point back.

> [!TASK]
> Write `CENTRE_BEHIND_M` (pitch −15°: the distance from the point under the drone, positive) and
> `EXPLAIN_TILT`: why does a nose-down drone's camera look behind it? Compare with your `PREDICT_TILT`.

> [!TASK]
> Now a case the runner does not print. Guess the quadrant first (north-east, south-west…), then compute it with
> **your** `backproject_ground` (a `python3 -c "…"` line or a small file): the ground point of the image centre
> (480, 270) for a camera 200 m up, heading 40°, pitch −15°, **roll +10°** (`camera_rotation_hpr(40, -15, 10)`,
> K from your `K_from_hfov(90, 960, 540)`). Write `CENTRE_ROLL_E_M` and `CENTRE_ROLL_N_M` (one decimal), and
> `EXPLAIN_T`: why does `project` need `R_wc.T`, while `backproject_ground` uses `R_wc` itself?

<details><summary>Stuck? Hints, one at a time</summary>

1. Two parts, as in worked example 2: the ray's direction in world axes (K⁻¹ then R_wc, 🧰 above); then the
   point where it meets z = 0. If the direction does not go down (its z ≥ 0), return `None`.
2. λ = −C_z / d_z, X = C + λ·d, return `np.array([X[0], X[1]])`. Make C an array first.
3. [−6.99, 21.31] instead of [−16.82, −14.83] on the tilted line: you used `R_wc.T @`; the ray goes camera →
   world with `R_wc @`.
4. [−16.82, −14.83] on the "50 m east and 20 m south" line: the ray starts at C — add C's east and north too.
5. A number instead of `None` for the ray towards the sky: test `d[2]` before you divide.
6. Last hint, the answer line for the direction: `d = R_wc @ np.linalg.solve(K, [u, v, 1.0])`.
</details>

## Step 4 — How high was the camera? (TODO 5, TODO A, TODO C)

**TODO 5** `gsd(h_m, hfov_deg, width_px)`: lesson §4. Then copy the photos into your folder and look at them:

```bash
cp /data/academy/18-camera-model/photo_A.png /data/academy/18-camera-model/photo_B.png /data/academy/18-camera-model/photo_T.png .
```

Open [photo_A.png](file:./photo_A.png) and [photo_B.png](file:./photo_B.png): both straight down, image top
= north, height unknown. Each shows a 12 m × 12 m orange landing pad. In
[measure_pad.py](file:./measure_pad.py), `orange_mask(img)` is given: a boolean array, True on the pad's
orange pixels.

<details><summary>🧰 numpy: where is a mask True?</summary>

```python
m = np.array([[False, True,  False],
              [False, True,  True ]])
rows, cols = np.nonzero(m)         # rows = array([0, 1, 1]), cols = array([1, 1, 2]) — ROWS FIRST
cols.min(), cols.max()             # (1, 2)
rows.mean()                        # 0.666…
len(cols) == 0                     # True when nothing is True: test it before .min()
```
</details>

**TODO A** `pad_size_px(img)`: the number of **columns** from the leftmost to the rightmost orange pixel,
both included. **TODO C** `height_from_size(f_px, size_m, n_px)`: lesson §4, "Measuring with a known object" —
`measure_pad.py` uses it to turn the pad's width into a height.

> [!TASK]
> **Predict** (`PREDICT_PAD`): which photo, A or B, will give the more precise height, and why? Then run:

```bash
python3 run_camera.py test
```

```bash
python3 measure_pad.py
```

It prints each pad's width, the height your `height_from_size` gives, and the heights for one pixel more and
less. Open `out/mask_photo_A.png` to see what the mask found. (Photo T's line needs TODO B:
Step 5.)

> [!TASK]
> Write `HEIGHT_A_M`, `HEIGHT_B_M` (one decimal), `HEIGHT_B_RANGE_M` (photo B: largest − smallest height of the
> ±1 px range) and `EXPLAIN_PIXEL`: why is one photo's height so much less precise than the other's?

<details><summary>Stuck? Hints, one at a time</summary>

1. 0.337 instead of 0.2083 for `gsd`: `math.tan` got degrees. 0.104: you used half the footprint — the whole
   width is 2·h·tan(HFOV/2).
2. `rows, cols = np.nonzero(orange_mask(img))`; no orange pixel → `return None`.
3. 10 instead of 11 on the test image: "both included" — add 1. 3 instead of 11: you counted rows (np.nonzero
   gives rows first).
4. Return an `int`: `int(cols.max() - cols.min() + 1)`.
5. TODO C: 3.33 or 0.48 instead of 300 for (1000, 12, 40)? One pixel covers size_m / n_px metres of ground, and
   at nadir that GSD is h / f: solve for h.
</details>

## Step 5 — Where is the pad? (TODO B)

Open [photo_T.png](file:./photo_T.png): the same camera 170 m above the ground, heading 40°, pitch −14° (nose
down), roll +5° (right wing down), as `TILTED` in measure_pad.py says. **TODO B** `pad_centre_px(img)`:
(u, v) = (mean column, mean row) of the orange pixels.

```bash
python3 run_camera.py test
```

```bash
python3 measure_pad.py
```

The last line back-projects the pad's centre with your `backproject_ground` and the real attitude.

> [!TASK]
> Write `PAD_T_E_M` and `PAD_T_N_M` (the pad, east and north of the point under the drone). Then two
> computations of your own, with your `backproject_ground` on the same pixel (copy it from the printout; a small
> file `what_if.py` is easiest):
> 1. `LEVEL_ERROR_M`: the old "straight down" assumption — the same pixel, but a level camera
>    (`camera_rotation_hpr(40)`): how far is that point from the pad?
> 2. `HEIGHT_SHIFT_M`: the right attitude, but a height of 150 m instead of 170 m: how far does the pad move?
>    Compare with 20/170 of the pad's distance from the point under the drone: why exactly that?
>    (`EXPLAIN_HEIGHT_SHIFT`)
>
> Then `EXPLAIN_LEVEL`: what did the level assumption get wrong, and what does a matcher need to avoid it?

<details><summary>Stuck? Hints, one at a time</summary>

1. The same `np.nonzero` as TODO A; `float(cols.mean())`, `float(rows.mean())`.
2. (3.0, 14.33) instead of (14.33, 3.0) on the test image, or measure_pad.py says the pixel is outside the image:
   (u, v) = (**column**, row) — np.nonzero gives rows first.
3. Your pad lands NORTH of the drone in photo T? The drone is nose down, so its camera looks back (the nose
   points 40°, the camera towards 220°): check the tilted `backproject_ground` lines of `run_camera.py test`.
4. `what_if.py`: `from navera_lite.camera import *`, `import numpy as np`; K from `K_from_hfov(90, 960, 540)`;
   two calls to `backproject_ground(K, R, [0, 0, h], u, v)`; the distance is `np.hypot(*(a - b))`.
</details>

> [!TIP] 🏅 End of session 1 — Measurer
> Press **✔ Check my work**. When checks 1–7 pass (TODO 1–5, A–C and Steps 0–5; the others are session 2), you
> earn the **Measurer** badge. If the class session ends here, stop here.

## Session 2 — Straightener (about 2 h)

Read lesson §4 (footprint) to §7 first.

## Step 6 — Footprints (TODO 6)

**TODO 6** `footprint(K, R_wc, C, width_px, height_px)`: lesson §4; reuse your `backproject_ground` for the four
corners, in the docstring's order.

> [!TASK]
> **Predict** (`PREDICT_AREA`): the lab camera at 150 m, nose north. At 30° nose down, how many times the
> nadir footprint's area will it cover? (The lesson's table gives 1.77 for a narrower camera: will a 90° camera
> give more or less?)

```bash
python3 run_camera.py test
```

```bash
python3 run_camera.py footprint
```

Open `out/footprint.png` (dots: the image centre; squares: the corner (0, 0)).

> [!TASK]
> Write `AREA_RATIO_30` (area at −30° / area at 0°, two decimals) and `EXPLAIN_FOOTPRINT`: why is the footprint
> a trapezoid whose far side is the wide one?

<details><summary>Stuck? Hints</summary>

1. A loop over the four corners `((0, 0), (width_px, 0), (width_px, height_px), (0, height_px))`; if one gives
   `None`, return `None`; else `np.array(list_of_points)`, shape (4, 2).
2. The corners in another order (the ✘ line shows [−100, −56.25] second): top-left, top-RIGHT, bottom-right,
   bottom-left — the image's own order, clockwise on screen.
</details>

## Step 7 — A wrong height is a wrong scale (no new code)

A drone takes off from a valley whose floor is 120 m above sea level. It flies at 520 m above sea level (GPS)
over a plateau whose ground is 280 m above sea level. Its day vision has no rangefinder and uses
"GPS altitude − take-off ground" as the height above the ground.

> [!TASK]
> With your `gsd` (or lesson §5 directly):
> 1. `SCALE_PLATEAU`: the scale a correct match would fit, true GSD / predicted GSD (two decimals);
> 2. `VERDICT_PLATEAU`: `"accepted"` or `"refused"` by a ±15 % scale gate;
> 3. `HEIGHT_FROM_SCALE_M`: elsewhere, the predicted height is 300 m and a match fits a scale of 1.08. What
>    height does it measure?

<details><summary>Stuck? Hints</summary>

1. Predicted height = 520 − 120 m; true height = 520 − 280 m.
2. 1.67: upside down — the drone is lower than predicted, so the photo shows less ground than expected: s < 1.
3. The gate accepts 0.85 ≤ s ≤ 1.15. h_true = h_predicted × s.
</details>

## Step 8 — The attacker: what an attitude error costs (TODO 7)

**TODO 7** `tilt_position_error(h_m, tilt_deg, dtilt_deg)`: lesson §6, the exact difference (not the
small-angle formula).

```bash
python3 run_camera.py test
```

```bash
python3 run_camera.py tilt
```

Open `out/tilt_error.png`. Now play the attacker. You can bias the drone's attitude (a badly mounted camera, a
vibrating IMU, a forged attitude message). Day vision states its positions at σ = 30 m. The drone flies at
250 m with its camera tilted 8° from vertical.

> [!TASK]
> **Predict** (`PREDICT_ATTACK`): how large a tilt error (degrees) moves the centre point by 30 m?
> Then find it with your function: the smallest positive `dtilt_deg` with `tilt_position_error(250, 8, d)` ≥
> 30 m, two decimals (`ATTACK_DTILT_DEG`); the same at a tilt of 35° (`ATTACK_DTILT_35_DEG`). Write
> `EXPLAIN_ATTACK`: why does a tilted camera need a better attitude than a level one?

<details><summary>🧰 Python: search a number with a loop</summary>

```python
x = 0.0
while x * x < 2.0:                 # the first x (step 0.001) whose square reaches 2
    x = x + 0.001
print(round(x, 3))                 # 1.415 — the step sets the precision
```

Put a few lines like these in a file `attack.py` (start it with `from navera_lite.camera import
tilt_position_error`) and run `python3 attack.py`. Bisection (halve an interval that contains the answer) is
faster, but a small step is enough here.
</details>

<details><summary>Stuck? Hints</summary>

1. 1.799 instead of 1.805 in the test: that is h·δθ/cos²θ, the small-angle formula; 1.745: h·δθ. The docstring
   wants h·tan(θ + δθ) − h·tan θ, then `abs(…)`. A huge number (22 660): degrees inside `math.tan` — convert
   with `math.radians` first.
2. Your loop: `d` from 0 in steps of 0.001 while `tilt_position_error(250, 8, d) < 30`.
3. About 6.84°: that is atan(30/250), a **level** camera; the camera here is tilted 8°.
</details>

## Step 9 — Straighten photo T (TODO 8)

**TODO 8** `nadir_homography(K, R_wc, R_wv)`: the least guided function. The docstring defines it; lesson §7
follows one pixel in words. Your work is the trace, on paper, before any code: a pixel x of the real photo —
which matrix turns it into a ray in the real camera's axes, which one into world axes, which one into the level
camera's axes, and which one back into a pixel? Write the four as one product, in the order they act (the first
one acts on x, so it stands on the right). Check on paper: with R_wv = R_wc you must get the identity.

> [!TASK]
> **Predict** (`PREDICT_STRAIGHT`): in a level, north-up view at the same place, how many pixels wide will the
> pad be, and at which pixel do you expect its centre? (Use Step 5's position and the GSD at 170 m.)

```bash
python3 run_camera.py test
```

```bash
python3 run_camera.py straighten
```

It warps photo T with your homography into the view of a level camera, image top north (`cv2.warpPerspective`),
saves `out/straight_T.png`, says where the point under the drone went, and measures the pad with your TODO A
and B. Open the picture.

> [!TASK]
> Write `STRAIGHT_PAD_PX` (the pad's width in the straightened view), `STRAIGHT_PAD_E_M` and `STRAIGHT_PAD_N_M`:
> the pad's position measured in the straightened view (east = (u − 480) × GSD, north = −(v − 270) × GSD, with
> your `gsd(170, 90, 960)`), one decimal. Do they agree with Step 5? Then `EXPLAIN_STRAIGHT`: why can one
> 3 × 3 matrix straighten the whole photo without knowing any depth?

<details><summary>Stuck? Hints</summary>

1. The four matrices, right to left: K⁻¹ (pixel → ray), R_wc (camera → world), R_wv transposed (world → level
   camera), K (ray → pixel). `np.linalg.inv(K)` gives K⁻¹.
2. The test says H[2, 2] = 1.024: right matrix, not scaled — divide it by `H[2, 2]`.
3. [[1.398, −0.502, 61.1], …]: the rotations are swapped (R_wv not transposed, R_wc transposed).
4. [[0.654, 0.620, −7.98], …]: that is the INVERSE, level view → tilted view. Read your product from the right:
   the first matrix must take a pixel of the REAL photo into the real camera's ray.
5. A black or mirrored straight_T.png: run the test first; a wrong homography sends the photo out of the frame.
6. STRAIGHT_PAD_N_M positive: v grows DOWN the image, so north = −(v − 270) × GSD.
</details>

## Step 10 — An independent check: OpenCV

Your code passes its own examples, but you wrote both. OpenCV, the vision library of most robots, computes the
same things its own way: `cv2.projectPoints` (with the rotation as a Rodrigues vector), normalised rays from
`cv2.undistortPoints`, a homography fitted by `cv2.findHomography` to 50 pixel pairs, and its own warp.

```bash
python3 compare_with_opencv.py
```

> [!TASK]
> Every line starts with ✔ and the last line says `ALL MATCH`. A ✘ line names the function to fix.

## Step 11 — The memo

Write [report.md](file:./report.md) (120–350 words, your own words, keep the three headings): what the tilt
did to photo T and what an attitude error costs, the heights you measured and what a wrong height does to a
match, and what straightening did and needs. Quote your numbers with their units.

> [!TASK]
> report.md has the three headings, at least 120 words, and quotes the heights of photos A and B, how far off
> the level assumption was, and the pad's width in the straightened view.

## Step 12 — Check, then look back

Press **✔ Check my work**: it tests your functions on cameras, attitudes and images they have never seen. When
every check passes, you earn the **Straightener** badge. Then look back, without the lesson:

1. Explain to a colleague, in three sentences, why NAVERA's bench error went from 28 m to about 1 m.
2. Which of your predictions was the most wrong? What did you assume?
3. Straightening needs the attitude; measuring metres needs the height. Which of the two would you trust less
   on a drone over hills, and why?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **Oblique GSD.** Check the optional box of lesson §4: back-project pixels (480, 270), (481, 270) and
  (480, 271) of the lab camera at 150 m, 20° nose down. Do you get h/(f cos θ) across and h/(f cos² θ) along?
- **Sloped ground.** `backproject_ground` assumes the plane z = 0. Write `backproject_plane(K, R_wc, C, u, v, n,
  c)` for any plane n·X = c (λ = (c − n·C)/(n·d)), and measure how far photo T's pad moves if the ground
  under it rises 5 % towards the north.
- **A scale gate in numbers.** Draw 10 000 heights h ~ N(300, 30²) m (`np.random.default_rng(1).normal`). What
  share of correct matches would a ±15 % gate refuse? With 2σ/h instead of 15 %?
- **Heading up, not north up.** Straighten photo T with `R_wv = camera_rotation_hpr(40)` (NAVERA keeps the
  heading). Where is the pad now, and what must the matcher still do before comparing with the map?
- **Fly your own rotations.** Swap the course's `rotations.py` for your own from mission 16 (keep a backup) and
  run the OpenCV check again (its part 0 builds the rotations with OpenCV alone, so a wrong convention fails): `cp navera_lite/rotations.py rotations_course.py && cp ../16-rotations/navera_lite/rotations.py navera_lite/`.
