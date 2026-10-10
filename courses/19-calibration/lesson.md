# Lens calibration: fisheye models and Zhang's method

> [!NOTE] In short
> - A wide lens bends straight lines. A **distortion model** (Brown–Conrady or fisheye) describes this bending with a few numbers.
> - **Calibration** finds these numbers from many photos of a chessboard (Zhang's method, done by OpenCV).
> - The **reprojection error** (RMS) says how well the model fits — but only where the board was seen.
> - **Straightening** turns the fisheye picture into the picture of a perfect pinhole camera; NAVERA keeps a 111° view.
> - In the lab you write the fisheye model by hand, calibrate the real Insta360 lens from 36 views, and compare with NAVERA's tool.

A survey drone flies along a straight coast road at 150 m. The GPS signal is jammed,
and NAVERA must find the drone's position by matching the camera picture with a satellite map. The
road is perfectly straight on the map. In the camera picture it is **curved**, like a reflection in
a spoon. A curved road will never match a straight one.

The camera is not broken. NAVERA's camera on the bench is an **Insta360 ONE R** with its 360°
module, and its top lens sees about **166°** from left to right. A lens that wide must bend light,
and the bending must be **measured** before the picture can be used to measure the world. This
measurement is called **calibration**. In this lesson you will:

- write the mathematical model of a fisheye lens (the one OpenCV and NAVERA use),
- understand how Zhang's method recovers that model from photos of a flat chessboard,
- judge a calibration with the reprojection error — and see why one number is not enough,
- straighten the picture, and compute exactly why NAVERA keeps only the central **111°**.

Everything uses the **real** calibration of NAVERA's real camera, made on the bench on
6 October 2026. (NAVERA is developed in Sousse, Tunisia: its test map and recordings come from
there; the other places in this course are examples from around the world.)

## 1. From the ideal pinhole to a real lens

Lesson 18 built the **pinhole camera**. A point with camera coordinates (X, Y, Z) — x to the right,
y down, z along the **optical axis** — is first divided by its depth:

```
a = X / Z          b = Y / Z            (normalised image coordinates)
u = fx · a + cx    v = fy · b + cy      (pixels;  K = [[fx, 0, cx], [0, fy, cy], [0, 0, 1]])
```

Call **θ** (theta) the angle between the incoming ray and the optical axis, and **r** the distance
of the normalised point from the centre. Then

```
r = sqrt(a² + b²) = tan θ          so, in pixels:   r_px = f · tan θ
```

The pinhole has one beautiful property: **straight lines in the world stay straight in the image**
(the projection is linear in homogeneous coordinates). Homographies (lesson 22) depend on it.

But look at tan θ as θ grows:

| θ | 30° | 45° | 60° | 70° | 80° | 85° | 90° |
|---|---|---|---|---|---|---|---|
| tan θ | 0.58 | 1.00 | 1.73 | 2.75 | 5.67 | 11.4 | ∞ |

A ray at 83° from the axis (the edge of the Insta360) would land 8.1 f from the centre. A pinhole
camera can **never** see 180°, and even 120° needs a huge sensor.

![Pinhole versus fisheye: how rays reach the sensor](assets/rays.svg)

## 2. Distortion models

**Distortion** is the difference between where a real lens puts a ray and where the ideal pinhole
would put it. Two families of models are used in practice.

### 2.1 Brown–Conrady: a pinhole plus small corrections

For normal lenses (up to ~100°), the **Brown–Conrady model** keeps the pinhole and adds a polynomial
correction in the normalised plane. With r² = a² + b²:

```
a_d = a·(1 + k1 r² + k2 r⁴ + k3 r⁶) + 2 p1 a b + p2 (r² + 2a²)
b_d = b·(1 + k1 r² + k2 r⁴ + k3 r⁶) + p1 (r² + 2b²) + 2 p2 a b
u = fx · a_d + cx      v = fy · b_d + cy
```

- k1, k2, k3 are **radial** terms: they move points along the radius. k1 < 0 gives **barrel**
  distortion (straight lines bulge outwards), k1 > 0 gives **pincushion** distortion.
- p1, p2 are **tangential** terms: they model a lens that is slightly tilted or off-centre relative
  to the sensor.

OpenCV stores them as `dist = [k1, k2, p1, p2, k3]` (`cv2.calibrateCamera`, `cv2.undistort`). The
weakness is visible in the formula: everything starts from r = tan θ, which goes to infinity at 90°.
No polynomial correction can bring a ray at 90° back onto the sensor.

### 2.2 Fisheye: start from the angle, not from tan θ

A **fisheye lens** uses strongly curved glass so that the distance on the sensor grows with the
**angle**, not with its tangent. Several ideal projections exist: equisolid (r = 2f sin(θ/2)),
stereographic (r = 2f tan(θ/2)), and the simplest, the **equidistant** projection:

```
r_px = f · θ          (θ in radians)
```

A ray at 83° (1.449 rad) lands 1.449 f from the centre instead of 8.1 f. Real lenses are close to,
but not exactly, one of these. OpenCV's fisheye module (the **Kannala–Brandt** model) adds an odd
polynomial in θ to the equidistant projection:

```
θ_d = θ · (1 + k1 θ² + k2 θ⁴ + k3 θ⁶ + k4 θ⁸)
```

With k1 = … = k4 = 0 this is exactly r = f θ. Note that these k's are **not** the Brown–Conrady k's:
same letters, different model. For the fisheye model OpenCV stores `D = [k1, k2, k3, k4]`.

![A grid seen straight, and the same grid through a fisheye lens](assets/barrel.svg)

### 2.3 The full fisheye projection, step by step

This is what `cv2.fisheye.projectPoints` computes (no skew), and what you will write in the lab
(`project_fisheye`):

```
1. normalise          a = X/Z,   b = Y/Z,   r = sqrt(a² + b²)
2. angle              θ = atan(r)
3. lens polynomial    θ_d = θ (1 + k1 θ² + k2 θ⁴ + k3 θ⁶ + k4 θ⁸)
4. rescale            a' = (θ_d / r) · a,   b' = (θ_d / r) · b     (if r = 0: a' = a, b' = b)
5. apply K            u = fx · a' + cx,     v = fy · b' + cy
```

**Worked example** with the real Insta360 calibration (fx = 660.48, fy = 721.40, cx = 937.06,
cy = 317.66, k1 = 0.2319, k2 = −0.4170, k3 = 0.5338, k4 = −0.2386). A point at
X = (1.0, 0.5, 2.0) m in the camera frame:

```
a = 0.5,  b = 0.25,  r = 0.5590
θ = atan(0.5590) = 0.5097 rad (29.2°)
θ_d = 0.5097 · (1 + 0.2319·0.2598 − 0.4170·0.0675 + 0.5338·0.0175 − 0.2386·0.0046) = 0.5303
θ_d / r = 0.9487   →   a' = 0.4743,  b' = 0.2372
u = 660.48 · 0.4743 + 937.06 = 1250.35 px
v = 721.40 · 0.2372 + 317.66 =  488.75 px
```

An ideal pinhole with the same K would give (1267.3, 498.0): already **19 px** away (√(16.95² + 9.25²) = 19.3 px) at only 29° off
the axis. At 150 m above the ground, one pixel of NAVERA's straightened picture covers about 0.23 m,
so ignoring the distortion would move this point by about 4.4 m on the ground — and much more near
the edges.

> [!WARNING]
> Common errors: `math.atan` works in **radians**; `np.arctan2(b, a)` is not the same as
> `np.arctan(r)`; and dividing by r on the optical axis (r = 0) gives `nan` — the limit of θ_d / r is 1.

## 3. Calibration: what is unknown, and how many equations

A calibration estimates the **intrinsic** parameters, which belong to the camera:

- fisheye model: fx, fy, cx, cy and k1…k4 (8 numbers; OpenCV can also estimate a skew, NAVERA fixes it to 0),
- Brown–Conrady: fx, fy, cx, cy and k1, k2, p1, p2, k3 (9 numbers).

But each photo of the board is taken from an unknown place, so each view also adds 6 **extrinsic**
parameters: a rotation R_i (3 numbers, stored as a **Rodrigues vector** `rvec`: a 3-D vector whose direction is the rotation axis and whose length is the rotation angle in radians; `cv2.Rodrigues(rvec)` turns it into the 3 × 3 matrix R) and a translation t_i
(3 numbers, `tvec`). With N views of a 9 × 6 board:

```
unknowns  = 8 + 6 N
equations = 54 corners × 2 coordinates × N = 108 N
```

Even one view gives more equations than unknowns, yet one view is not enough: the equations are
**not independent**. For example, a board seen face-on cannot separate "long focal length, board
far away" from "short focal length, board near". We need views that make the unknowns observable:
tilted boards, boards near the edges and corners of the image (where distortion is largest), at
different distances.

### 3.1 Zhang's method (2000)

> [!NOTE]
> This section is **for reading**: it explains what happens inside OpenCV. The lab uses OpenCV's
> calibration functions and does not ask you to write Zhang's closed form (it is a "Going further"
> challenge).

Zhengyou Zhang's idea is to use a **planar** target and put the world frame on it, so every corner
has Z = 0. For a pinhole camera, the projection of the board then becomes a 3 × 3 **homography**:

```
s · [u, v, 1]ᵀ = K [r1  r2  r3  t] [X, Y, 0, 1]ᵀ = K [r1  r2  t] [X, Y, 1]ᵀ = H [X, Y, 1]ᵀ
```

where r1, r2 are the first two columns of R and s is an unknown scale. Each view gives one H
(8 numbers up to scale), which can be estimated from the corners by the **DLT** method (lesson 22).
Write H = [h1 h2 h3]. Since H = λ K [r1 r2 t], we have r1 = K⁻¹h1/λ and r2 = K⁻¹h2/λ. The columns of a
rotation are orthogonal and have the same length, so:

```
h1ᵀ B h2 = 0
h1ᵀ B h1 = h2ᵀ B h2           with   B = K⁻ᵀ K⁻¹  (symmetric)
```

These two equations are **linear** in the 6 entries of B. One view gives 2 equations; B has 5 degrees
of freedom (6 entries, up to scale), so **3 views** are enough to solve for B with an SVD, then K is
recovered from B (a Cholesky factorisation), then each pose (R_i, t_i) from H_i and K.

This closed-form solution ignores distortion and is sensitive to noise. It is only the **starting
point** of a **non-linear least-squares** refinement (Levenberg–Marquardt) of everything together:

```
minimise   Σ_i Σ_j ‖ u_ij − π(K, D, R_i, t_i, X_j) ‖²
```

where u_ij is the detected corner j in view i, and π is the full projection of section 2 (with
distortion). `cv2.calibrateCamera` follows this recipe. `cv2.fisheye.calibrate` uses the same idea
for the fisheye model: an initial guess with the ideal equidistant lens, one homography per view on
normalised points, then a joint refinement of K, D and the poses.

![Zhang's method in five steps](assets/zhang.svg)

### 3.2 Finding the corners

Calibration is only as good as its corners. OpenCV's `cv2.findChessboardCornersSB` finds the
**inner corners** (where four squares meet) with sub-pixel accuracy, often better than 0.1 px. NAVERA
calls it with `CALIB_CB_EXHAUSTIVE | CALIB_CB_ACCURACY` (slow but robust: about 1.5 s per
1920 × 540 view on the Jetson). The 9 × 6 corners come back row by row, the column index changing
fastest — the 3D points you give OpenCV must be in the **same order**.

## 4. The reprojection error

After the refinement, every corner is projected again with the estimated parameters and compared
with where it was detected. The **reprojection error** of one corner is the distance in pixels; the
summary number is the **RMS** (root mean square) over all M corners of all views:

```
RMS = sqrt( (1/M) · Σ ‖ u_detected − u_projected ‖² )
```

The Insta360 top-lens calibration reports **RMS = 0.525 px**. `calibrate_camera.py` calls below
0.5 px "good" and below 1 px "usable".

What the RMS **does** tell you: the model explains the corners it was fitted on to about half a pixel.
Large values mean bad corners (motion blur, a board that is not flat), a wrong board size, or a wrong
model.

What the RMS **does not** tell you:

1. **It is a training error.** The parameters were tuned on those very corners. The honest test is a
   **hold-out**: calibrate on some views, then measure the error on views the calibration never saw.
   You will do it in the lab.
2. **It says nothing where no corner was seen.** If all corners lie within 45° of the axis, the model
   can be anything beyond 45° and the RMS will still be small.
3. **It does not measure stability.** Two calibrations with RMS 0.5 px can disagree on fx by several
   percent if the views are few or similar. In the lab you will calibrate random subsets of the real
   views and measure the spread of fx.

> [!NOTE]
> OpenCV's fisheye calibration can refuse a view: with the flag `CALIB_CHECK_COND` it raises
> *"CALIB_CHECK_COND - Ill-conditioned matrix for input array 5"* when the pose of view 5 cannot be
> estimated reliably. NAVERA's tool then drops that view and tries again. Note which views get
> dropped: often the most extreme ones — exactly those that teach the model about the edges.

## 5. The OpenCV fisheye API

| Function | What it does |
|---|---|
| `cv2.fisheye.calibrate(obj, img, size, K, D, flags=…, criteria=…)` | Zhang-style calibration. Returns `rms, K, D, rvecs, tvecs` |
| `cv2.fisheye.projectPoints(X, rvec, tvec, K, D)` | 3D points → distorted pixels (section 2.3) |
| `cv2.fisheye.undistortPoints(pts, K, D, R=…, P=…)` | distorted pixels → normalised points (or pixels of a new camera P) |
| `cv2.fisheye.initUndistortRectifyMap(K, D, R, K_new, size, m1type)` | the per-pixel look-up table for straightening |
| `cv2.remap(img, map1, map2, cv2.INTER_LINEAR)` | applies the table to an image |
| `cv2.fisheye.undistortImage(img, K, D, Knew=…)` | both steps in one call (slow if repeated) |

Useful flags of `cv2.fisheye.calibrate`:

- `CALIB_RECOMPUTE_EXTRINSIC` — re-estimate every board pose at each iteration (recommended);
- `CALIB_CHECK_COND` — refuse ill-conditioned views (see the note above);
- `CALIB_FIX_SKEW` — force K[0, 1] = 0 (modern sensors have square pixel grids);
- `CALIB_USE_INTRINSIC_GUESS`, `CALIB_FIX_K1` … `CALIB_FIX_K4`, `CALIB_FIX_PRINCIPAL_POINT` — to
  start from or freeze some parameters.

Formats that trip everyone:

- object points: an array (N, 1, 3) per view; image points: (N, 1, 2) per view; `size` is
  **(width, height)** while numpy's `img.shape` is (height, width, 3);
- `cv2.fisheye.calibrate` accepts float64; `cv2.calibrateCamera` wants **float32** and fails with
  *"objectPoints should contain vector of vectors of points of type Point3f"* otherwise;
- D has 4 values for the fisheye model and 5 for Brown–Conrady: do not mix them.

## 6. The real Insta360 calibration

The Insta360 picture is 1920 × 1080 pixels made of **two halves**: the top half (1920 × 540) comes
from the top lens, the bottom half from the bottom lens (lesson 20). NAVERA uses only the top half.
It was calibrated on the bench with a chessboard shown on a computer screen (9 × 6 inner corners,
squares of 32.94 mm), from **38 views**:

| Parameter | Value | Meaning |
|---|---|---|
| fx, fy | 660.5 px, 721.4 px | focal lengths (horizontal, vertical) |
| cx, cy | 937.1 px, 317.7 px | principal point (the image centre would be 960, 270) |
| k1 … k4 | 0.232, −0.417, 0.534, −0.239 | fisheye polynomial |
| RMS | 0.525 px | reprojection error on the 38 views |
| crop | [0, 0, 1920, 540] | the calibration is for the top half only |

Why is fy ≠ fx? The camera squeezes its lens picture to fit the 1920 × 540 half, so one pixel does
not cover the same angle across and up-down. The calibration discovers this by itself.

With the ideal rule θ = r / f, the left edge (937 px from the centre) is at 937 / 660.5 = 1.419 rad
= 81°, the right edge (982 px) at 85°: about **166.5° × 42.8°**. But the calibrated polynomial tells a
different story. θ_d(θ) rises until θ = **67.4°**, where θ_d = 1.249 rad, i.e. **825 px** from the
centre, and then turns back down. The left edge (937 px) is never reached: the model **cannot
describe** the outer ~110 px on each side. This is not a property of the glass — a real lens never
"turns back" — it is a polynomial extrapolating beyond the data: the corners used for calibration
lie within about 52° of the axis. In the lab you will invert θ_d(θ) and return `nan` where no
answer exists.

## 7. Straightening (undistortion) and rectification

To straighten a picture, we choose a **new, ideal pinhole camera** K_new and build the image it
would have taken from the same place. For each pixel (u, v) of the new image:

```
1. its ray in the new camera:      [a, b, 1] = K_new⁻¹ [u, v, 1]
2. optional rotation R:            ray' = Rᵀ · ray    (R = identity: no rotation)
3. where the fisheye put that ray: (u_f, v_f) = fisheye projection (section 2.3)
4. copy the colour there, with bilinear interpolation
```

This is the **inverse mapping**: we go from each output pixel back to the input, so every output
pixel gets exactly one value and there are no holes. `cv2.fisheye.initUndistortRectifyMap` computes
(u_f, v_f) for every output pixel once — a "map" of 1920 × 540 entries — and `cv2.remap` applies it to
each frame in a few milliseconds. NAVERA builds the map once at start and reuses it. Pixels whose ray
the lens never saw become **black**.

When R is not the identity, the same function **rectifies**: it simulates a rotated camera. Stereo
cameras use it to make two images row-aligned; NAVERA uses the same idea (a rotation computed from
the IMU attitude) to turn a tilted view into a straight-down view (`nadir_homography` in `camera_model.py`).

## 8. How wide should the straight picture be? The 166° → 111° trade-off

For a straight picture w pixels wide with horizontal field of view H:

```
f_new = (w / 2) / tan(H / 2)
```

Near the centre, both the lens and the new camera put a small angle δθ at a distance f · δθ. So the
ratio **f_new / fx** is the share of the lens' centre resolution (pixels per degree) the straight
picture keeps. At an angle θ from the centre, the pinhole picture needs dr/dθ = f_new / cos²θ pixels per
radian: the edges are **stretched** by 1 / cos²(H/2) — new pixels interpolated from few real ones.

| Straight view H | f_new (w = 1920) | centre detail kept (f_new / 660.5) | edge stretch 1/cos²(H/2) |
|---|---|---|---|
| 111° | 659.8 px | 99.9 % | 3.1 |
| 150° | 257.2 px | 38.9 % | 14.9 |
| 166° | 117.9 px | 17.8 % | 67.3 |

Showing the whole 166° as a pinhole image would throw away more than 80 % of the centre's detail —
the part that matters most for map matching — to display hugely stretched edges that the
calibration does not even describe. NAVERA's rule is **never make f_new shorter than fx**:

```
H_max = 2 · atan( (w/2) / fx ) = 2 · atan(960 / 660.5) = 110.94°
```

That is the **111°** in the calibration file (`out_hfov_deg: 111.0`, capped to 110.94° by the code).
Vertically, the same f_new gives 2 · atan(270 / 660.5) = 44.5°. At 150 m above the ground, the
straightened picture covers 2 · 150 · tan(55.5°) = 436 m across, i.e. **0.23 m per pixel**.

![The centre detail kept as a function of the straight view's width](assets/crop.svg)

![The real Insta360 top lens before and after straightening, with the 9 × 6 corners found](assets/before_after_small.jpg)

## 🐦 How birds do it

Look at a rock dove — the feral pigeon of every city square, from London to Cape Town. Its eyes are on the **sides** of
the head. Together they cover more than 300° around the bird, with only a narrow zone in front seen
by both eyes and a small blind sector behind. That is a bird with two built-in fisheye lenses:
perfect to spot a falcon coming from almost any direction.

The falcons themselves made a cleverer choice, the same one as NAVERA. A falcon's eye has **two
foveae** — small regions packed with photoreceptors. The deep central fovea looks sideways and gives
some of the sharpest vision in the animal world for distant targets; a second, shallower fovea looks forward, where
the two eyes overlap, for judging distance during the final attack. The rest of the retina still
sees a wide field, but at lower resolution. Owls, like the Eurasian eagle-owl of rocky cliffs,
went further towards "narrow and precise": their tube-shaped eyes face forward, the visual field is
about 200° with roughly 50° seen by both eyes, and the eyes barely move — so the owl turns its whole
head, up to about 270°.

Navi the swallow sits in between: a wide view to stay safe while she hunts insects over the
fields, plus a sharp zone to aim. Nature has no single best lens: **wide** to see everything, or
**sharp** to measure well. NAVERA makes the falcon's trade-off: the Insta360 sees 166°, but for
measuring, NAVERA keeps the central 111° at full resolution.

## In NAVERA

**Calibrating.** The tool is [navera_tools/calibrate_camera.py](file:navera/navera_tools/calibrate_camera.py).
It takes photos live from the camera (`--device`) or from a folder (`--images`), finds the corners and
runs the fisheye calibration, dropping refused views:

```python
def board_points(cols, rows, square_m):
    obj = np.zeros((rows * cols, 1, 3), np.float64)
    obj[:, 0, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_m
    return obj
...
        flags = (cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_CHECK_COND |
                 cv2.fisheye.CALIB_FIX_SKEW)
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-9)
        # CALIB_CHECK_COND refuses ill-conditioned views: drop them one by one
        while True:
            try:
                rms, K, D, _, _ = cv2.fisheye.calibrate(obj, views, (w, h), K, D, flags=flags, criteria=crit)
                break
            except cv2.error as e:
                ...                                   # find "input array N", remove view N, retry
```

It writes the YAML file you will read in the lab: `model`, `image_width`, `image_height`,
`camera_matrix` (9 numbers, row by row), `distortion`, `rms_px`, `views`, `out_hfov_deg`, `crop` and,
measured later, `latency_s` (lesson 20).

> [!NOTE]
> **Known issue (Release 0.x):** `calibrate_camera.py --model pinhole` passes float64 points to
> `cv2.calibrateCamera` and stops with the "Point3f" error of section 5. The default `--model fisheye`
> — the one used for the Insta360 — is not affected. In the lab, your own `calibrate_pinhole()` must
> avoid this bug.

**Using it.** [navera_common/camera_model.py](file:navera/navera_common/navera_common/camera_model.py)
turns the file into a `CameraModel`. The 111° rule and the straightening:

```python
    def max_out_hfov_deg(self) -> float:
        """The widest undistorted view keeping the lens' own resolution at the centre."""
        return math.degrees(2.0 * math.atan((self.size[0] / 2.0) / self.K[0, 0]))

    def undistort(self, img: np.ndarray) -> np.ndarray:
        ...
        if self._maps is None:                      # built once, then reused for every frame
            if self.model == "fisheye":
                self._maps = cv2.fisheye.initUndistortRectifyMap(
                    self.K, self.D[:4], np.eye(3), self.K_out, self.size, cv2.CV_16SC2)
            ...
        return cv2.remap(img, *self._maps, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
```

In the constructor, `out_hfov_deg = min(out_hfov_deg, self.max_out_hfov_deg())` and
`K_out = [[f, 0, w/2], [0, f, h/2], [0, 0, 1]]` with f = (w/2) / tan(out_hfov/2) — your `f_new`.

**Safety checks.** [camera_pkg/nodes/live_camera.py](file:navera/camera_pkg/camera_pkg/nodes/live_camera.py)
(`_camera_model`) refuses a calibration that does not match the camera:

- another **picture size** ("calibration … is for 1920x540, the camera gives …") — K is in pixels of one size;
- another **crop** (the whole picture instead of the top half) — `crop` must match `NAVERA_CAMERA_CROP`;
- another **camera** — when calibrated live, the file stores the USB identity `camera_id`.

A wrong calibration does not crash anything: it silently shifts every match by metres. NAVERA prefers
to stop with a clear message.

## Glossary

| Word | Meaning |
|---|---|
| **intrinsic parameters** | the camera's own numbers: fx, fy, cx, cy and the distortion coefficients |
| **extrinsic parameters** | the pose of the board in one view: rotation (rvec) and translation (tvec) |
| **Rodrigues vector** | a rotation stored as 3 numbers: direction = rotation axis, length = angle (radians) |
| **distortion** | the difference between the real image and an ideal pinhole image |
| **Brown–Conrady model** | pinhole + radial (k1, k2, k3) and tangential (p1, p2) corrections in r = tan θ |
| **radial / tangential distortion** | displacement along the radius / perpendicular to it (lens tilted or off-centre) |
| **barrel / pincushion** | straight lines bulge outwards / inwards |
| **equidistant projection** | the ideal fisheye: r = f θ |
| **Kannala–Brandt (OpenCV fisheye) model** | θ_d = θ (1 + k1 θ² + k2 θ⁴ + k3 θ⁶ + k4 θ⁸), r = f θ_d |
| **homography** | a 3 × 3 matrix mapping one plane to another (here: board → image) |
| **Zhang's method** | calibration from ≥ 3 views of a plane: homographies, closed form for K, then non-linear refinement |
| **Levenberg–Marquardt (LM)** | the iterative non-linear least-squares method used for the refinement |
| **reprojection error, RMS** | distance between detected and re-projected corners; RMS = sqrt(mean of squared distances) |
| **hold-out test** | measuring the error on data not used for fitting |
| **ill-conditioned** | a problem where small changes of the data cause large changes of the solution |
| **undistortion / rectification** | rebuilding the image of an ideal (and optionally rotated) pinhole camera |
| **inverse mapping, remap** | for each output pixel, fetch the colour at its source in the input |

## Check what you learned

<details><summary>1. Why can no Brown–Conrady model describe a 180° lens, while the fisheye model can?</summary>
Brown–Conrady starts from r = tan θ, which is infinite at θ = 90°: a ray at 90° or more has no finite
normalised coordinate to correct. The fisheye model starts from θ itself (r = f θ_d(θ)), which stays
finite at 90° and beyond.
</details>

<details><summary>2. In Zhang's method, why is the board's plane chosen as Z = 0, and how many views are needed for K?</summary>
With Z = 0 the third column of R disappears and the board-to-image mapping becomes a homography
H = K [r1 r2 t]. Each H gives two linear equations on B = K⁻ᵀK⁻¹ (orthogonality and equal length of r1,
r2). B has 5 degrees of freedom, so at least 3 views are needed (more in practice, against noise).
</details>

<details><summary>3. Project the point (0, 0, 5) m with the Insta360 calibration. What happens in the formula?</summary>
a = b = 0 and r = 0, so θ = 0 and θ_d / r is 0/0. The limit is 1, so (a', b') = (0, 0) and the pixel is
the principal point (cx, cy) = (937.06, 317.66). Code that divides by r without care returns nan.
</details>

<details><summary>4. A calibration has RMS 0.3 px from 8 views; another has RMS 0.5 px from 35 views spread over the whole image. Which do you trust more?</summary>
The second. A low RMS on few views is a training error on little data: the parameters can be far from
the truth (fx can vary by tens of pixels between 8-view calibrations) and nothing constrains the image
edges. Many well-spread views make the parameters stable and the model valid over a larger angle.
</details>

<details><summary>5. Why is NAVERA's straightened Insta360 view 111° wide and not 150°?</summary>
f_new = 960 / tan(H/2). At 111°, f_new ≈ fx = 660 px: the centre keeps all its detail. At 150°,
f_new = 257 px: the centre loses 61 % of its pixels per degree, and the edges are stretched 15 times —
in a region where the calibration is not even measured.
</details>

<details><summary>6. The calibration file was made from the full 1920 × 1080 picture, but NAVERA runs with NAVERA_CAMERA_CROP=top. What does live_camera.py do, and why?</summary>
It refuses to start: the size (1920 × 540 vs 1920 × 1080) and the crop do not match. K is expressed in
the pixels of one specific image: cy for the full picture is not cy for the top half, and the full
picture contains a second lens with a different model.
</details>

Now open the **🛠️ Lab** tab.
