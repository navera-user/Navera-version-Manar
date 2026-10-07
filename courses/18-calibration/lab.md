# Lab 18 — Model, calibrate and straighten the real Insta360 lens

**Goal:** write the fisheye lens model by hand and check it against OpenCV, straighten a real frame
and measure the result, calibrate the lens yourself from 36 real chessboard views, test the
calibration (stability, hold-out, other model), reproduce it with NAVERA's own tool, and write a
short engineering report.
**Time:** about 3 hours.

| File | What you do |
|---|---|
| [fisheye_model.py](file:./fisheye_model.py) | Part A — TODOs 1–7: the lens model and the straightening |
| [calibrate_lab.py](file:./calibrate_lab.py) | Part B — TODOs 8–10: your own calibration |
| [report.md](file:./report.md) | Part C — your analysis (5 sections) |
| [answers.py](file:./answers.py) | 3 quiz questions |

> [!NOTE]
> All pictures are **real**: top-lens frames of the Insta360 ONE R recorded during the bench
> calibration of 6 October 2026, with the chessboard shown on a computer screen. Only the top half of
> each frame is given (the half NAVERA uses; the bottom lens filmed the room and is never shared).
> No camera is needed.

## Step 1 — Look at the data (5 min)

```bash
ls /data/academy/18-calibration /data/academy/18-calibration/views | head -50
```

You see the bench calibration `insta360_top.yaml`, 36 views `fNNNN.jpg` (1920 × 540) and
`corners_ref.npz` (the corners, used by the grader). Print the calibration:

```bash
cat /data/academy/18-calibration/insta360_top.yaml
```

Find the model, the size, the 9 numbers of `camera_matrix` (K row by row), the 4 numbers of
`distortion` (k1…k4), `rms_px`, `views`, `out_hfov_deg` and `crop`. Copy one view and open it:

```bash
cp /data/academy/18-calibration/views/f0208.jpg .
```

Open [f0208.jpg](file:./f0208.jpg). The screen's edges, the window frame and the chessboard rows are
curved. In the real room they are straight.

## Step 2 — Read the calibration and project points (TODOs 1 and 2, 25 min)

**TODO 1** — `load_calibration(path)` returns `K` (3 × 3 float array), `D` (4 floats) and
`size = (width, height)`. `yaml.safe_load()` gives a Python dictionary.

**TODO 2** — `project_fisheye(X_cam, K, D)`: the five steps of section 2.3 of the course, for an
array of N points at once (numpy works on whole columns: `X[:, 0] / X[:, 2]`). Return an (N, 2) array.
Use `np.where` to avoid the division by r = 0 on the optical axis.

Test it on the worked example of the course:

```bash
python3 -c "import numpy as np, fisheye_model as m; K, D, s = m.load_calibration(m.CALIB_FILE); print(m.project_fisheye(np.array([[1.0, 0.5, 2.0], [0.0, 0.0, 5.0]]), K, D))"
```

You must see about `[[1250.35 488.75] [937.06 317.66]]` (the second point is on the axis: it lands
on the principal point). `nan` in the second row means you divided by r = 0.

> [!TASK]
> TODOs 1 and 2. The grader compares your `project_fisheye()` with `cv2.fisheye.projectPoints` on 42
> points: the largest difference must be below 10⁻⁶ px.

## Step 3 — Where is the model valid? (TODO 3, 20 min)

`theta_d_of(theta, D)` (given) computes θ_d = θ (1 + k1 θ² + … + k4 θ⁸). **TODO 3** —
`theta_from_theta_d(theta_d, D)` inverts it: given θ_d (the distance from the principal point divided
by f), find θ. The polynomial rises, reaches a maximum, then falls (course, section 6), so:

1. find where the rising part ends (evaluate `theta_d_of` on a fine grid of [0, π/2] and find the
   first index where `np.diff` is ≤ 0);
2. if θ_d is negative or above the maximum: return `float("nan")`;
3. otherwise solve θ_d_of(θ) = θ_d on the rising part. **Bisection** is safe: keep an interval
   [lo, hi] that contains the root and halve it 60–80 times.

Test it:

```bash
python3 -c "import fisheye_model as m; K, D, s = m.load_calibration(m.CALIB_FILE); print([m.theta_from_theta_d(t, D) for t in (0.0, 0.5303, 1.249, 1.30)])"
```

Expected: about `[0.0, 0.5097, 1.17…, nan]` — 0.5097 rad is the 29.2° of the worked example.

> [!TASK]
> TODO 3. Round trips θ → θ_d → θ must give θ back (to 10⁻⁵ rad), and θ_d = 1.30 and the image edge
> (cx / fx = 1.419) must give `nan`.

## Step 4 — Reprojection error, straightening, straightness (TODOs 4–7, 40 min)

**TODO 4** — `reprojection_rms(obj_pts, img_pts_list, rvecs, tvecs, K, D)`. For each view, turn the
Rodrigues vector into a matrix (`R, _ = cv2.Rodrigues(rvec)`), move the board points into the camera
frame (X_cam = R X + t, i.e. `obj.reshape(-1, 3) @ R.T + t.reshape(1, 3)`), project them with **your**
`project_fisheye()`, and compare with the detected corners (`seen.reshape(-1, 2)`). Return the RMS
over all corners and the list of per-view RMS. (It is used in Part B.)

**TODO 5** — `straight_camera_matrix(hfov_deg, size)`: f = (w/2) / tan(hfov/2), principal point at
(w/2, h/2). Check by hand: 90° on a 1000 × 500 image gives f = 500.

**TODO 6** — `undistort(img, K, D, K_new)`: `cv2.fisheye.initUndistortRectifyMap` with R = `np.eye(3)`,
the new camera `K_new`, the size `(w, h)` and `cv2.CV_16SC2`; then `cv2.remap` with
`cv2.INTER_LINEAR` and `borderMode=cv2.BORDER_CONSTANT`.

**TODO 7** — `line_bend_px(points)`: the straightness of a row of corners. `cv2.fitLine(points as
float32, cv2.DIST_L2, 0, 0.01, 0.01).ravel()` gives `(vx, vy, x0, y0)`; the distance of (x, y) to that
line is |(x − x0)·vy − (y − y0)·vx|. Return the **largest** distance as a float.

> [!TIP]
> Why not `np.polyfit` (y = a·x + b)? A chessboard **column** is almost vertical: x hardly changes,
> and y = a·x + b cannot describe a vertical line. `cv2.fitLine` fits in every direction.

Now run Part A:

```bash
python3 fisheye_model.py
```

You should see: your projection equal to OpenCV's (difference ~10⁻¹³ px), the worked example, the
ideal field of view 166.5° × 42.8°, the curve peak at 67.4° / 825 px, the left edge "not describable",
f = 659.8 px for 111°, a line like `most bent chessboard line: before 6.52 px, after 1.17 px`, and the
trade-off table of the course. Open [before_after.jpg](file:./before_after.jpg): the red lines join the
first and last corner of each row — before, the corners sag away from them; after, they sit on them.
The black areas are directions the lens never saw.

> [!QUESTION]
> Why is the "after" value 1.2 px and not 0? Think of the RMS of the calibration (0.5 px), of the
> corner detector, and of a computer screen that is not perfectly flat.

> [!TASK]
> TODOs 4–7, then run `fisheye_model.py`: it writes the `model` part of `results.json` and
> `before_after.jpg`. The grader also checks that your straightened picture is NAVERA's picture.

## Step 5 — Compare with NAVERA's code (5 min)

```bash
python3 compare_navera.py
```

NAVERA's `CameraModel` straightens the same frame. You should read `max_out_hfov_deg() = 110.94 deg`,
the 111° asked in the file **capped** to 110.94°, `K_out` focal length 660.48 px (= fx), and a mean
difference of 0.000: your code and NAVERA's give the same picture. The three test points show
NAVERA's `undistort_points()`: the fisheye pixel (200, 100), near the top-left corner, lands at
(−125.5, −23.5) — outside the 111° straight picture. That part of the lens is what the crop gives up. Find `max_out_hfov_deg()` and
`undistort()` in [camera_model.py](file:navera/navera_common/navera_common/camera_model.py).

## Step 6 — Calibrate the lens yourself (TODOs 8–10, 40 min)

Open [calibrate_lab.py](file:./calibrate_lab.py).

**TODO 8** — `board_points(cols, rows, square_m)`: the 3D corners in the board frame, Z = 0 (Zhang),
as a (54, 1, 3) float64 array, row by row with the column index changing fastest. Corner 1 is at
(s, 0, 0) and corner 9 at (0, s, 0) for s = 0.03294 m.

**TODO 9** — `calibrate_fisheye(obj, views, size)`: one call of `cv2.fisheye.calibrate` with one copy
of `obj` per view, K = `np.eye(3)`, D = `np.zeros((4, 1))`, the flags
`CALIB_RECOMPUTE_EXTRINSIC | CALIB_CHECK_COND | CALIB_FIX_SKEW` and the criteria written in the TODO.
Do **not** catch `cv2.error`: the given `calibrate_robust()` needs it to drop refused views.

**TODO 10** — `calibrate_pinhole(obj, views, size)`: the Brown–Conrady model with
`cv2.calibrateCamera(obj_list, views, size, None, None)`. Convert everything to `np.float32` first —
this is the bug of NAVERA's `--model pinhole` (course, "In NAVERA").

Run it (the corner detection takes about 1 minute the first time, then it is cached in
`corners.npz`; the whole script takes about 2 minutes):

```bash
python3 calibrate_lab.py
```

Read the output carefully:

1. **Your calibration**: views used and refused, fx, fy, cx, cy, D, and the RMS computed by OpenCV
   **and** by your `reprojection_rms()` — they must be equal. The worst and best views. The farthest
   corner angle in the views used and in all views: compare them — which views did OpenCV refuse?
2. **Stability**: fx from random subsets of 8, 12, 20 and 30 views. How does the spread change?
3. **Hold-out**: calibration on 28 views, error measured on the 8 others.
4. **Brown–Conrady** on the same views: its RMS, its fx, its hold-out error.

> [!TASK]
> TODOs 8–10, then run `calibrate_lab.py`: it writes the `calibration` part of `results.json`. The
> grader checks your functions on 12 real views, your RMS against OpenCV's, the subset experiment
> (fx must be more stable with 30 views than with 8), the hold-out and the Brown–Conrady fit.

## Step 7 — Calibrate with NAVERA's own tool (5 min)

Run NAVERA's real calibration tool on the same folder:

```bash
python3 ~/navera/navera_tools/calibrate_camera.py --images /data/academy/18-calibration/views --board 9x6 --square-mm 32.94 --out my_calib.yaml
```

- `--board 9x6`: the inner corners, 9 columns × 6 rows; `--square-mm 32.94`: the side of one square.
- The model is `fisheye` by default. The views are already the top halves, so no `--crop` is needed
  here. For a live calibration of the full 1920 × 1080 picture you would add `--crop top`, so that the
  file records the crop that `live_camera.py` checks.

It prints `board found` for each view, then a line like
`fisheye calibration from 34 views: RMS 0.506 px (usable); NAVERA will publish a 110.2 deg wide …`.

```bash
cat my_calib.yaml
```

Compare `camera_matrix[0]` (fx) and `rms_px` with your `results.json`. Same detector, same flags, same
views, same order: you should find the **same** numbers. Compare also with the bench file (fx 660.5 px
from 38 views). Is the difference larger or smaller than the spread you measured in Step 6?

> [!TASK]
> Produce `my_calib.yaml` in your lesson folder. Its fx must agree with your own calibration within
> 1 px and with the bench within 3 %, with an RMS below 1 px.

## Step 8 — Draw the lens curves (10 min)

```bash
python3 lens_curve.py
```

Open [lens_curve.png](file:./lens_curve.png): the distance r from the principal point as a function of
the ray angle θ, for the ideal pinhole (f tan θ), the ideal fisheye (f θ), the bench calibration, your
fisheye calibration and your Brown–Conrady fit. The grey zone starts at the farthest corner used by
your calibration. Answer for yourself:

- Up to which angle do all the calibrated curves agree? Why there?
- What happens to the Brown–Conrady curve beyond that angle, and why (look at its formula)?
- Your fisheye calibration and the bench one turn back down at different angles. Which one is "right"?

## Step 9 — Report and quiz (30 min)

Fill [report.md](file:./report.md): keep the five `## ` headings, write at least 40 words under each,
in full sentences, with **your** numbers.

1. **My calibration** — fx, fy, cx, cy, RMS, views detected / used / refused; comparison with the
   bench file and with `my_calib.yaml`.
2. **Stability and hold-out** — std of fx with 8 and 30 views; train vs test RMS; what they mean.
3. **Fisheye or Brown–Conrady** — both RMS, both hold-out errors, why they are similar, where the
   models differ (use `lens_curve.png`), which one NAVERA must use and why.
4. **The 111° crop** — f_new at 111°, 150° and 166°, centre detail kept, edge stretch, ground sampling
   distance at 150 m.
5. **Recommendation** — 3–5 concrete rules for calibrating a new NAVERA unit before a field test (for
   example in a workshop in Muscat).

Then answer the three questions in [answers.py](file:./answers.py).

> [!TASK]
> `report.md` with the five sections (≥ 40 words each); section 1 must quote your fx (± 1 px) and
> section 4 the focal length of a 150° straight view. Quiz answered.

Press **✔ Check my work**.

## Going further (optional)

- **Zhang's closed form, by hand.** Take 5 views from `corners.npz`, convert the corners to ideal
  pinhole pixels with `cv2.fisheye.undistortPoints(..., P=K)` (your calibration), estimate one
  homography per view with `cv2.findHomography(board_xy, pixels)`, build the 2 equations per view on
  b = (B11, B12, B22, B13, B23, B33), solve V b = 0 with `np.linalg.svd`, and recover fx, fy, cx, cy
  (Zhang 2000, appendix B). How close is the closed form to the refined K?
- **Fewer parameters.** Add `cv2.fisheye.CALIB_FIX_K3 | cv2.fisheye.CALIB_FIX_K4` to your flags and
  run again. How do the RMS, the hold-out error and the curve beyond 45° change? Is a simpler model
  better here?
- **Your calibration at work.** In `fisheye_model.py`, set `CALIB_FILE = "my_calib.yaml"` and run it.
  Is the straightened chessboard as straight as with the bench file? Then try `HFOV = 150.0` and look
  at how small the chessboard becomes in `before_after.jpg`.
