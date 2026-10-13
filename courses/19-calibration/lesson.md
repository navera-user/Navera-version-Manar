# Lens calibration: fisheye models and Zhang's method

![The real Insta360 top lens on NAVERA's bench: the fisheye picture (top) and the same picture straightened into an ideal pinhole view 111° wide (bottom). Look at the screen's lower edge and the window frame](assets/before_after_small.jpg)

> [!NOTE] Mission brief
> **6 October 2026, NAVERA's bench.** NAVERA's camera, the top lens of an Insta360 ONE R, was calibrated from
> 38 photos of a chessboard shown on a computer screen: **8 numbers** in a small file, reprojection error
> 0.525 px. Those 8 numbers turn every pixel into a direction in space; without them, map matching is
> impossible.
>
> Now load that file on the wrong picture. Suppose the camera is switched to 1280 × 720 and simply scales its
> picture, while the file still describes 1920 × 540. Nothing crashes. But the pixel in the middle of the
> picture is believed to look **27.7°** away from where it really looks: from 150 m, about **79 m** on the
> ground, on every frame. This is why NAVERA's live camera **refuses** a calibration made at another
> resolution or with another camera. And a second puzzle: this lens sees about **166°** across, yet NAVERA
> straightens only the central **111°**. Why throw a third of the view away?
>
> **Session 1 — Lens modeller:** you write the fisheye lens model, find where it stops being valid, and choose
> the width of the straight view with numbers. **Session 2 — Calibrator:** you calibrate the real lens from
> 36 real views, test the result on views it never saw, and find out why your numbers are not the bench's.
> Each session ends with a badge.
>
> **Start now:** open the 🛠️ **Lab** tab, do **Step 0** (two minutes, no code), then come back here for §1.

**Objectives.** After this mission you can:

1. **implement** the equidistant fisheye model with its polynomial (Kannala–Brandt, as OpenCV uses it), and
   find the angle of a pixel;
2. **measure** a reprojection error and **say where** a calibration is valid (and where it only extrapolates);
3. **calibrate** a camera from chessboard views (Zhang's idea, done by OpenCV) and **test** it on views it
   never saw;
4. **justify** the width of a straightened view (NAVERA's 111°) with numbers.

**You need:** the pinhole model, K and f = (w/2) / tan(HFOV/2) (mission 18), a pose as R and t (missions 16 and
18), numpy arrays (mission 04). ⏱ Reading: about 75 minutes with the ✏️ checks, pencil and calculator. Lab:
4 h to 5 h 30, in two sessions.

**Before you start** — answer without looking (if you miss two, reread mission 18, §2 and §7):

<details><summary>1. A camera sees 90° across 1 000 px. What is its focal length f in pixels?</summary>
f = (w/2) / tan(HFOV/2) = 500 / tan 45° = <b>500 px</b>.
</details>

<details><summary>2. With K (f = 800, centre (640, 360)), which pixel shows the camera-frame point X_c = (20, −10, 100)?</summary>
u = 800 · 20/100 + 640 = <b>800</b>, v = 800 · (−10)/100 + 360 = <b>280</b>.
</details>

<details><summary>3. In mission 18 you straightened a tilted view with H = K·R_wvᵀ·R_wc·K⁻¹. Which matrix turns a pixel into a ray?</summary>
K⁻¹: [u, v, 1] → ((u − cx)/f, (v − cy)/f, 1). It undoes the shift, then the scale.
</details>

<details><summary>Workspace and words (open if you need them)</summary>

Your files are in `~/lessons/19-calibration/`; the part of NAVERA Lite you write is
[navera_lite/fisheye.py](file:./navera_lite/fisheye.py).

| Word | Meaning | Français |
|---|---|---|
| **distortion** | the difference between where a real lens puts a ray and where an ideal pinhole would | distorsion |
| **fisheye lens** | a very wide lens whose image distance grows with the ray's angle, not its tangent | objectif fisheye (hypergone) |
| **equidistant projection** | the ideal fisheye: r = f·θ | projection équidistante |
| **calibration** | measuring a camera's own numbers (K and the distortion) from photos | étalonnage (calibration) |
| **intrinsic / extrinsic parameters** | the camera's own numbers / the pose of the board in one photo | paramètres intrinsèques / extrinsèques |
| **chessboard corner** | an inner point where four squares meet | coin intérieur du damier |
| **reprojection error, RMS** | distance between a detected corner and the model's prediction; root mean square of those | erreur de reprojection, moyenne quadratique |
| **hold-out test** | measuring the error on data the fit never saw | test sur données réservées |
| **ill-conditioned** | a problem where tiny changes of the data change the answer a lot | mal conditionné |
| **straightening (undistortion)** | rebuilding the picture an ideal pinhole camera would take | redressement (correction de distorsion) |
| **extrapolation** | using a fitted model outside the range of its data | extrapolation |
</details>

## 1. A pinhole cannot see 166°

In mission 18, a point at angle **θ** (theta) from the **optical axis** lands at a distance r from the
principal point:

```
pinhole:   r = f · tan θ          (r and f in pixels)
```

This works well for narrow and normal lenses, and it keeps straight lines straight. But tan θ explodes as θ
grows:

| θ | 30° | 45° | 55.5° | 70° | 80° | 83° | 90° |
|---|---|---|---|---|---|---|---|
| tan θ | 0.58 | 1.00 | 1.46 | 2.75 | 5.67 | 8.14 | ∞ |

**Worked example.** The Insta360 top lens sees about 83° to each side of its axis. A pinhole picture whose
edge is at 55.5° has its edge at 1.46 f from the centre; to reach 83° it would need 8.14 f: the edge of a
166° pinhole view lies 8.14 / 1.46 = **5.6 times** farther out. At 90° it would need an infinite sensor. A
pinhole picture of 166° is possible on paper, but almost all its pixels would be spent on the edges.

![Pinhole versus fisheye: how rays reach the sensor](assets/rays.svg)

> [!QUESTION] ✏️ Check
> A pinhole camera with f = 600 px. How far from the principal point do rays at 30°, 60° and 80° land? How
> wide must the sensor be (in pixels) to show ±80°?

<details><summary>Answer</summary>
600·tan 30° = <b>346 px</b>, 600·tan 60° = <b>1 039 px</b>, 600·tan 80° = <b>3 403 px</b>. A ±80° view needs
about 6 800 px across: ten times wider than for ±30°, for the same detail at the centre.
</details>

## 2. The fisheye model

A **fisheye lens** uses strongly curved glass so that the distance on the sensor grows with the **angle**
itself. The simplest ideal is the **equidistant projection**:

```
ideal fisheye:   r = f · θ          (θ in radians)
```

At 83° (1.449 rad), r = 1.449 f instead of 8.14 f. Straight lines become curves: the price of a wide view.

![A grid seen straight, and the same grid through a fisheye lens](assets/barrel.svg)

No real lens is exactly equidistant. OpenCV's fisheye model (the **Kannala–Brandt** model, used by NAVERA and by
NAVERA Lite) bends the ideal with a short polynomial of θ:

```
θ_d = θ · (1 + k1·θ² + k2·θ⁴ + k3·θ⁶ + k4·θ⁸)          D = [k1, k2, k3, k4]
```

θ_d is the angle the *ideal* fisheye would need to put the point where the real lens puts it. With all four
k = 0, θ_d = θ and we are back to r = f·θ.

> [!TIP] 🧰 A polynomial in θ
> θ·(1 + k1θ² + k2θ⁴ + …) = θ + k1θ³ + k2θ⁵ + …: only **odd** powers. Close to the axis (small θ) the higher
> powers are tiny, so θ_d ≈ θ: every lens behaves like the ideal near its centre. The k's only matter far from
> the axis. (This is the same idea as a Taylor series: a smooth curve written as a sum of powers, each one
> mattering at larger θ.) With k1 = 0.2, θ = 0.1 rad: 0.1 + 0.2·0.001 = 0.1002; at θ = 1.0 rad: 1.2.

**The projection, step by step.** A point X_c = (X, Y, Z) in the camera frame (mission 18: x right, y down, z
along the axis):

```
1. normalise          a = X / Z,    b = Y / Z,    r = √(a² + b²)        (r = tan θ: the pinhole's radius)
2. angle              θ = atan(r)                                       (from the axis, radians)
3. lens polynomial    θ_d = θ · (1 + k1θ² + k2θ⁴ + k3θ⁶ + k4θ⁸)
4. rescale            a' = (θ_d / r) · a,    b' = (θ_d / r) · b
5. apply K            u = fx · a' + cx,      v = fy · b' + cy
```

Step 4 keeps the **direction** of the point in the image (a and b scaled by the same number) and changes only
its **distance** from the centre, from r to θ_d. Two focal lengths fx and fy appear because this camera's
pixels do not cover the same angle across and up-down (§8).

**Worked example**, with the real bench calibration (fx = 660.48, fy = 721.40, cx = 937.06, cy = 317.66;
k1 = 0.2319, k2 = −0.4170, k3 = 0.5338, k4 = −0.2386). The point X_c = (1.0, 0.5, 2.0) m:

```
a = 0.5,  b = 0.25,  r = 0.5590
θ   = atan(0.5590) = 0.5097 rad (29.2°)
θ_d = 0.5097 · (1 + 0.2319·0.2598 − 0.4170·0.0675 + 0.5338·0.0175 − 0.2386·0.0046) = 0.5303
θ_d / r = 0.9487   →   a' = 0.4743,  b' = 0.2372
u = 660.48 · 0.4743 + 937.06 = 1250.35 px        v = 721.40 · 0.2372 + 317.66 = 488.75 px
```

An ideal pinhole with the same K puts the point at (1267.30, 498.01): already **19.3 px** away, only 29° off
the axis. Farther out the gap grows fast (lab Step 2).

> [!WARNING]
> On the optical axis (a = b = 0), r = 0 and θ_d / r is 0/0: numpy gives `nan`. The limit of θ_d / r is 1
> (θ_d ≈ θ ≈ r near the axis), so the point lands on (cx, cy). Also: θ is the angle **from the axis**,
> atan(r) — not the direction in the image, atan2(b, a).

> [!QUESTION] ✏️ Check
> With the bench calibration, a ray at θ = 0.8 rad. Compute θ_d, then how far from the principal point
> (in px, along a row) it lands. Compare with an ideal fisheye and with a pinhole of the same fx.

<details><summary>Answer</summary>
θ² = 0.64: θ_d = 0.8·(1 + 0.2319·0.64 − 0.4170·0.4096 + 0.5338·0.2621 − 0.2386·0.1678) = <b>0.862</b>, so
r = 660.48 · 0.862 = <b>569 px</b>. Ideal fisheye: 660.48 · 0.8 = 528 px. Pinhole: 660.48·tan 0.8 = 680 px.
The real lens sits between the two.
</details>

## 3. Where is the model valid?

Map matching needs the opposite direction: **which ray does a pixel see?** Undo step 5, then step 4:

```
a' = (u − cx) / fx,    b' = (v − cy) / fy,    θ_d = √(a'² + b'²)      then solve θ_d(θ) = θ_d for θ
```

There is no formula for the last step: θ_d(θ) is a 9th-degree polynomial. But it is easy to solve
numerically, *if* the curve rises.

> [!TIP] 🧰 Bisection
> To solve g(θ) = target on an interval [lo, hi] where g rises and g(lo) ≤ target ≤ g(hi): take the middle m;
> if g(m) < target the answer is in [m, hi], else in [lo, m]. Each step halves the interval: after 60 steps
> it is 2⁻⁶⁰ of the start, far below any useful precision.
> ```python
> lo, hi = 0.0, 2.0                  # solve x**3 = 5 on [0, 2]
> for _ in range(60):
>     m = (lo + hi) / 2
>     if m ** 3 < 5: lo = m
>     else: hi = m
> print(lo)                          # 1.7099759466766968
> ```

Draw the bench calibration's curve r = fx·θ_d(θ) (lab Step 3 does it): it rises, reaches **825 px at θ = 67.4°**,
then **turns back down**. A real lens never does that: a ray farther from the axis never lands closer to the
centre. The polynomial does it because nothing told it otherwise: look where the calibration views put their
corners.

![Every corner of the 36 calibration views on the 1920 × 540 picture, with rings of constant angle. Nothing lies beyond about 52°](assets/coverage.png)

The corners stop at about **52°** from the axis. Beyond that, the polynomial is **extrapolating**: four
numbers fitted on 0–52° say nothing reliable about 70°. Two consequences:

- the picture's left edge is 937 px from the principal point and its right edge 983 px; both are above the
  curve's top (825 px): **no angle** of the model gives them. The calibration cannot describe the outer
  110 px on the left and 160 px on the right, although the lens obviously sees something there;
- between 52° and 67.4° the model gives an answer, but an untested one.

**Worked example.** Which ray does pixel (300, 200) see? a' = (300 − 937.06)/660.48 = −0.9645, b' =
(200 − 317.66)/721.40 = −0.1631, θ_d = 0.9782; bisection on the rising part gives θ = 0.894 rad = **51.2°**.
That pixel is at the edge of the data: trust it, but not much farther.

> [!QUESTION] ✏️ Check
> Pixel (100, 270) of the bench picture. Compute θ_d. Can the model give its angle?

<details><summary>Answer</summary>
a' = (100 − 937.06)/660.48 = −1.267, b' = (270 − 317.66)/721.40 = −0.066, θ_d = <b>1.269</b>. The curve's top is
θ_d = 825/660.48 = 1.249 < 1.269: <b>no angle</b> of the rising part gives it. The honest answer is "not
describable" (`nan`), not a number from the falling part.
</details>

## 4. Straightening a fisheye picture

Day vision compares the camera with a map. A straight-down **pinhole** picture of flat ground is a scaled,
turned copy of the map (mission 18): straight roads stay straight. A fisheye picture is not. So NAVERA first turns the fisheye picture into the picture an **ideal pinhole camera K_new** at
the same place would take. For each pixel (u, v) of the **new** picture:

```
1. its ray in the new camera:        [a, b, 1] = K_new⁻¹ · [u, v, 1]          (mission 18, §3)
2. where the fisheye puts that ray:  (u_f, v_f) = fisheye projection of (a, b, 1)   (§2)
3. copy the colour found at (u_f, v_f), interpolated between the 4 nearest pixels (bilinear)
```

This is **inverse mapping**: we start from each output pixel and fetch its colour, so every output pixel gets
exactly one value and there are no holes. Steps 1–2 do not depend on the picture, only on K, D and K_new: OpenCV
computes them once for all pixels (`cv2.fisheye.initUndistortRectifyMap`, a "map" of 1920 × 540 source
positions), then `cv2.remap` applies the map to each frame in a few milliseconds. An output pixel whose source
falls outside the fisheye picture has no colour: it is filled **black** (a constant border).

The 111° straight view of the Insta360 (K_new = `K_from_hfov(111, 1920, 540)` from mission 18, f = 659.79 px)
takes its colours from fisheye columns ≈ 230 to ≈ 1645 only: the outer ~230 px on each side of the lens
picture are not used. Its bottom rows are black: cy = 317.7, so the lens' axis points below the middle of the
picture, and the straight view, centred on its own middle, looks lower than the lens sees.

> [!QUESTION] ✏️ Check
> Why does straightening build its map from the **output** pixels backwards, instead of sending each fisheye
> pixel forwards to its place in the straight picture?

<details><summary>Answer</summary>
Forwards, the stretched parts of the output would receive no pixel at all (holes) and the squeezed parts several
(overwrites). Backwards, every output pixel asks for exactly one colour. It also needs only the forward lens
model of §2, which has a formula; the forwards route would need the inverse of §3 for every pixel.
</details>

## 5. How wide should the straight view be?

A straight view w pixels wide with a field of view H has (mission 18)

```
f_new = (w/2) / tan(H/2)
```

Choose H and you choose f_new. Two numbers judge the choice:

- **At the centre**, the straight view has f_new pixels per radian, the lens has fx. The ratio **f_new / fx** is
  the share of the lens' centre detail the straight view keeps: below 1, real detail is thrown away.
- **Away from the centre**, a pinhole picture spends f_new / cos²θ pixels per radian (the derivative of
  f_new·tan θ), while the lens records only fx·θ_d′(θ), with the derivative of the polynomial:

```
θ_d′(θ) = 1 + 3k1θ² + 5k2θ⁴ + 7k3θ⁶ + 9k4θ⁸          stretch(θ) = (f_new / cos²θ) / (fx · θ_d′(θ))
```

The **stretch** is the number of straight-view pixels made from one lens pixel, along a radius. Above 1, the
extra pixels are **invented** by interpolation: they cost memory and matching time and add no detail. Where
θ_d′ ≤ 0 (past the curve's top), the model is not valid and the stretch has no meaning.

**Worked example** (111° view, f_new = 659.79 px, bench calibration) at θ = 30° = 0.5236 rad:
θ_d′ = 1 + 3·0.2319·0.2742 − 5·0.4170·0.0752 + 7·0.5338·0.0206 − 9·0.2386·0.0057 = 1.099;
stretch = (659.79 / 0.75) / (660.48 · 1.099) = 879.7 / 725.8 = **1.21**. A pure 1/cos² estimate would say 1.33:
the real lens spreads its pixels a little more at 30° than the ideal fisheye, so less is invented.

| Straight view H | f_new (w = 1920) | centre detail kept f_new / fx | stretch at 30° | the view's edge (H/2) |
|---|---|---|---|---|
| 111° | 659.8 px | 99.9 % | 1.21 | 55.5°: lab Step 4 |
| 150° | 257.2 px | 38.9 % | 0.47 | 75°: not valid (> 67.4°) |
| 166° | 117.9 px | 17.8 % | 0.22 | 83°: not valid |

A 150° view would throw away 61 % of the centre's detail, the part that matters most for matching, to show
edges the calibration does not even describe. NAVERA's rule is **never make f_new shorter than fx**:

```
H_max = 2 · atan((w/2) / fx) = 2 · atan(960 / 660.48) = 110.94°
```

That is the **111°** in the bench file (`out_hfov_deg: 111.0`, which the code caps to 110.94°). Its vertical field
of view is 2·atan(270 / 659.79) = 44.5°, and from 150 m it covers 436 m across, 0.227 m per pixel (mission 18).

![The centre detail kept as a function of the straight view's width](assets/crop.svg)

> [!QUESTION] ✏️ Check
> Another camera: fx = 800 px, pictures 1 280 px wide. Following NAVERA's rule, what is the widest straight view?

<details><summary>Answer</summary>
H_max = 2·atan(640 / 800) = <b>77.3°</b>. A longer focal length (more pixels per degree) gives a narrower view
for the same width.
</details>

> [!WARNING] Common wrong ideas (session 1)
> - "Straightening adds detail." It only resamples: above a stretch of 1 the new pixels are interpolated.
> - "The fisheye's k1…k4 are the same as Brown–Conrady's k1, k2." Same letters, another model (§8).
> - "If the model gives an angle, it is right." Past the last corners (here ~52°) it extrapolates; past 67.4° it
>   even answers from the falling part of the curve.
> - "A wider straight view is always better for navigation." It covers more ground but each metre gets fewer
>   pixels at the centre, and its edges are stretched and unmeasured.
> - "The black parts of the straightened picture are a bug." They are directions the lens picture does not
>   contain; filling them with a repeated border colour would create false features.

## 6. Calibration: finding K and D from photos

Everything above assumed we know fx, fy, cx, cy and k1…k4. **Calibration** measures them. The idea: photograph
an object whose geometry is known exactly (a chessboard: 9 × 6 inner corners, squares of 32.94 mm), many
times, from different positions, and find the numbers that best predict where its corners appear.

**What is unknown.** The 8 **intrinsic** parameters (fx, fy, cx, cy, k1…k4; the skew, a slanted pixel grid, is
fixed to 0 on modern sensors), plus, for every photo, where the board was: its **pose**, a rotation (3 numbers,
a **Rodrigues vector** `rvec`: direction = rotation axis, length = angle in radians; `cv2.Rodrigues` turns it
into the 3 × 3 matrix R) and a translation `tvec` (3 numbers, metres). These 6 per view are **extrinsic**
parameters: they say nothing about the camera, but they must be found too. With N views of 54 corners:

```
unknowns  = 8 + 6·N                  equations = 54 corners × 2 coordinates × N = 108·N
```

Even N = 1 gives more equations than unknowns, yet one view is never enough: the equations are not
independent. A board seen face-on cannot separate "long focal length, board far away" from "short focal length,
board close". Tilted boards, boards near the picture's edges and at several distances make the unknowns
**observable**.

**Zhang's idea (2000).** Put the board's own frame on the board, so every corner has Z = 0. For a pinhole camera
the board-to-picture mapping then becomes a 3 × 3 **homography** H_i per view. Because the columns of a rotation
are perpendicular and of equal length, each H_i gives **two equations on K alone**; K has 5 unknowns
(fx, fy, cx, cy and the skew), so 3 views fix a first K, without any initial guess. That first guess
(distortion set to 0) is then **refined**: an iterative least-squares method (Levenberg–Marquardt) moves K, D and
every pose together to make the predicted corners match the detected ones:

```
minimise   Σ over views i, corners j   ‖ u_ij − project(K, D, rvec_i, tvec_i, X_j) ‖²
```

where X_j is corner j on the board (Z = 0), u_ij where it was detected in view i, and `project` the model of §2
after the pose (X_c = R_i·X_j + t_i). OpenCV's `cv2.fisheye.calibrate` follows this recipe for the fisheye model.

![Zhang's method in five steps](assets/zhang.svg)

<details class="further"><summary>Optional: the two equations of Zhang's closed form</summary>
With the board at Z = 0, s·[u, v, 1]ᵀ = K [r1 r2 r3 t] [X, Y, 0, 1]ᵀ = K [r1 r2 t] [X, Y, 1]ᵀ = H [X, Y, 1]ᵀ.
Write H = [h1 h2 h3] = λ K [r1 r2 t]: then r1 = K⁻¹h1/λ and r2 = K⁻¹h2/λ. Perpendicular columns of equal length
give h1ᵀ B h2 = 0 and h1ᵀ B h1 = h2ᵀ B h2, with B = K⁻ᵀK⁻¹ symmetric: two equations, <b>linear</b> in the 6 entries
of B. Stack them for N ≥ 3 views, solve V·b = 0 with an SVD, and recover K from B (a Cholesky factorisation),
then each pose from H_i and K. The lab's "Going further" asks you to do it.
</details>

> [!QUESTION] ✏️ Check
> 20 views of a 9 × 6 board, fisheye model with no skew. How many unknowns, how many equations? Why does
> a camera fixed on a tripod, photographing one board placed in one spot 20 times, still calibrate badly?

<details><summary>Answer</summary>
8 + 6·20 = <b>128</b> unknowns, 108·20 = <b>2 160</b> equations. Twenty identical views are one view twenty times:
the same poses, the same corners, no new angle. Nothing separates f from the distance, and nothing at the
picture's edges constrains k1…k4.
</details>

## 7. The reprojection error, and what it does not tell you

After the fit, every corner is projected again with the calibration and its view's pose, and compared with
where it was detected. One corner's **reprojection error** is the distance between the two (pixels). The
summary is the **RMS** (root mean square) over all M corners of all views:

```
RMS = √( (1/M) · Σ ‖u_detected − u_projected‖² )
```

> [!TIP] 🧰 RMS
> Square, average, square root, in that order. Three errors (0.3, 0.4), (0, 1) and (0.6, 0.8) px have lengths
> 0.5, 1 and 1: their squares 0.25, 1, 1, mean 0.75, RMS = √0.75 = **0.87 px**. The RMS weighs big errors more
> than the plain mean (0.83). Over several views, square **every corner**, then average them all: the mean of
> the per-view RMS values is not the RMS.

The bench calibration says **RMS 0.525 px**: the model explains the corners it was fitted on to about half a
pixel. Large values mean blurred corners, a board that is not flat, a wrong board size or the wrong model. Three
things it does **not** say:

1. **It is a training error.** The parameters were tuned on those corners. The honest test is a **hold-out**:
   calibrate on some views, measure on views the calibration never saw. For an unseen view, the board's pose is
   unknown: find it first, with K and D held fixed (undo the lens with `cv2.fisheye.undistortPoints`, which gives
   ideal pinhole rays, then find the pose with `cv2.solvePnP` and K = identity), then measure as above.
2. **It says nothing where no corner was seen** (§3): an RMS of 0.5 px from corners within 52° says nothing at 60°.
3. **It does not measure stability.** fx and the board's distance can trade against each other: a 1.5 % larger fx
   with every board 1.5 % farther away predicts almost the same corners. Two calibrations with the same RMS
   can disagree on fx by several pixels. In the lab you measure that spread.

> [!QUESTION] ✏️ Check
> Calibration A: RMS 0.30 px from 8 views, all near the picture's centre. Calibration B: RMS 0.50 px from 35
> views spread over the picture. Which do you trust for a 111° straight view, and why?

<details><summary>Answer</summary>
<b>B</b>. A's small RMS is a training error on little data: its parameters are unstable (fx can move by tens of
pixels between 8-view calibrations), and nothing constrains its edges, where the 111° view reaches 55.5°. B's
corners cover more angles and its parameters are pinned down by more views.
</details>

## 8. Calibrating with OpenCV

**Corners.** `cv2.findChessboardCornersSB(grey, (9, 6), flags)` finds the 54 inner corners with sub-pixel
accuracy, **row by row, the column index changing fastest**. The 3-D board points you give OpenCV must be in the
same order: (0, 0, 0), (s, 0, 0), …, (8s, 0, 0), then (0, s, 0)… with s = 0.03294 m, as an array of shape
(54, 1, 3).

**The fisheye calibration.**

```python
rms, K, D, rvecs, tvecs = cv2.fisheye.calibrate(object_points, image_points, (width, height), K0, D0,
                                                flags=flags, criteria=criteria)
```

`object_points` and `image_points` are **lists** with one array per view ((54, 1, 3) and (54, 1, 2), float64);
K0 = the identity and D0 = four zeros are the starting values; `criteria` says when to stop the refinement.
The flags you need:

| Flag | Meaning |
|---|---|
| `cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC` | re-estimate every board pose at each step of the refinement (recommended) |
| `cv2.fisheye.CALIB_CHECK_COND` | refuse a view whose pose cannot be estimated reliably (ill-conditioned) |
| `cv2.fisheye.CALIB_FIX_SKEW` | keep K[0, 1] = 0 |
| `cv2.fisheye.CALIB_FIX_K3`, `…_FIX_K4`, `…_USE_INTRINSIC_GUESS` | freeze some numbers, or start from a given K |

Flags are combined with `|`. With `CALIB_CHECK_COND`, a refused view stops the whole call with an error that names
it: *"CALIB_CHECK_COND - Ill-conditioned matrix for input array 17"*. The usual reply (NAVERA's tool does it, and
NAVERA Lite's given `calibrate_robust()`) is to remove that view and calibrate again. Write down **which** views
get refused: often the most extreme ones, exactly those that would teach the model about the edges.

**Formats that trip everyone.** The size is **(width, height)**, while `img.shape` is (height, width, 3).
D has 4 numbers in the fisheye model.

**The other model: Brown–Conrady.** OpenCV's ordinary calibration (`cv2.calibrateCamera`) keeps the pinhole
r = tan θ and corrects it with a polynomial in r: a_d = a·(1 + k1r² + k2r⁴ + k3r⁶) plus two "tangential" terms
p1, p2 for a lens slightly tilted against the sensor; D = [k1, k2, p1, p2, k3]. It wants **float32** points
(otherwise: *"objectPoints should contain vector of vectors of points of type Point3f"*). Its weakness is in the
formula: it starts from tan θ, which is infinite at 90°, so no correction can describe a lens that sees beyond
90°. Within 45° of the axis, though, it can fit as well as the fisheye model: the lab measures it.

> [!WARNING] Common wrong ideas (session 2)
> - "A low RMS means an accurate camera." It means the model fits the corners it was given, where they were.
> - "More parameters are always better." Each extra number can bend the curve where no corner was seen.
> - "One calibration is the truth." Calibrate twice from different views and fx moves; know by how much.
> - "A calibration is a property of the lens." It belongs to one lens, at one resolution, with one crop: K is
>   in pixels of one specific picture.
> - "Catch the error and carry on." A refused view must be removed, not ignored silently inside the function.

## In NAVERA

NAVERA's calibration tool takes chessboard photos from a folder or live from the camera, finds the corners, runs
OpenCV's fisheye calibration with the three flags of §8, drops the views OpenCV refuses one at a time, and writes
a small YAML file: the model, the picture size, K (9 numbers), D (4 numbers), the RMS, the number of views, the
straight view's width, the **crop** (the Insta360 picture is two lenses one above the other; NAVERA uses the top
half, 1920 × 540) and, for a USB camera calibrated live, the camera's identity. The bench file of 6 October 2026:
fisheye model, 38 views, RMS 0.525 px, fx 660.5 px, fy 721.4 px, out_hfov_deg 111.

The live camera (ARCHITECTURE §5, in words) straightens every frame with that file before day vision sees it, and
**refuses** a file made at another resolution or, for a USB camera, with another camera, rather than run with
wrong rays. It builds the straightening map once, then remaps each frame, and publishes a straight view at most
as wide as f_new ≥ fx allows (110.94° for this lens). NAVERA is Release 0.2, field validation pending: its day
vision is "not yet measured with NAVERA's camera" (VALIDATION_STATUS, 2026-10-03), and the edges of the 111° view
(55.5°) lie beyond the corners the bench session recorded (about 52°): one more open problem.

## In NAVERA Lite

The same ideas live in [navera_lite/fisheye.py](file:./navera_lite/fisheye.py), the part you write today:

| You write | It does | Lesson |
|---|---|---|
| `fisheye_project` | camera-frame points → fisheye pixels | §2 |
| `theta_from_theta_d` | the ray angle of a pixel, or `nan` where the model is not valid | §3 |
| `stretch_at` | straight-view pixels per lens pixel at an angle | §5 |
| `undistort` | the straightened picture | §4 |
| `board_points`, `calibrate_fisheye` | the board's corners, one OpenCV calibration | §6, §8 |
| `reprojection_rms`, `holdout_rms` | the training error, and the honest error on unseen views | §7 |

Given: `load_calibration`, `save_calibration`, `theta_d_of`, `find_corners`, `calibrate_robust`, and the
command-line tool `python3 -m navera_lite.tools.calibrate`, which uses your `board_points` and
`calibrate_fisheye` to write a calibration file like NAVERA's. From mission 18 you reuse `camera.K_from_hfov`.
Mission 20 puts the straightened picture on the live camera, with its timing.

## 🐦 How birds do it

A **woodcock** has eyes so far back on its head that it sees almost 360° around, and even above: two natural
fisheye lenses, perfect to spot a predator while its bill probes the soil. **Falcons** make NAVERA's other choice:
a wide field at modest resolution, plus a deep central **fovea** packed with receptors where the detail is
needed to measure. And the brain calibrates its eyes: when scientists fitted young barn owls with prism
spectacles that shifted their view sideways, the owls' brains slowly re-learned where things are. A calibration
belongs to one set of optics.

## Summary

1. A pinhole puts a ray at f·tan θ and cannot reach 90°; a fisheye puts it at f·θ_d(θ), with
   θ_d = θ(1 + k1θ² + k2θ⁴ + k3θ⁶ + k4θ⁸) (OpenCV, NAVERA). On the axis, θ_d / r → 1.
2. A calibration is only measured where its corners were (here up to ~52°); past the curve's top (67.4°, 825 px)
   it cannot describe a pixel at all.
3. Straightening fetches, for every pixel of an ideal pinhole view K_new, the fisheye pixel that saw the same ray
   (a map built once, then remap); directions the lens picture lacks stay black.
4. A straight view w wide with f_new < fx throws away centre detail; NAVERA's rule f_new ≥ fx gives
   2·atan(960 / 660.48) = 110.94° ≈ 111°. Its edges are still stretched (more pixels than the lens recorded there).
5. Zhang: a flat board gives one homography per view and two equations on K per view; the refinement fits K, D
   and every pose together. The RMS is a training error: test on unseen views, and measure how much fx moves.

**Next mission:** the straightened picture goes live. Frames arrive late and the drone turns while they travel:
you measure the camera's delay and take the attitude at the right instant.

## Check yourself

Answer without scrolling up.

<details><summary>1. Write the five steps from a camera-frame point to a fisheye pixel. Which step needs care on the axis?</summary>
a = X/Z, b = Y/Z, r = √(a² + b²); θ = atan r; θ_d = θ(1 + k1θ² + …); a' = (θ_d/r)·a, b' = (θ_d/r)·b; u = fx·a' + cx,
v = fy·b' + cy. Step 4: at r = 0 use θ_d/r = 1.
</details>

<details><summary>2. Why can the bench calibration not give the angle of the picture's left-edge pixels?</summary>
Their θ_d (937/660.5 = 1.42) is above the top of the polynomial's rising part (1.249, at 67.4°): no angle gives
it. The polynomial was fitted on corners within ~52° and bends back where it has no data.
</details>

<details><summary>3. Your calibration has train RMS 0.47 px and hold-out RMS 0.57 px. Is it broken?</summary>
No. A hold-out error a little above the training error is normal: the training error is optimistic because the
parameters were tuned on those corners. The hold-out number is the honest accuracy, within the angles tested.
</details>

<details><summary>4. A partner sets the Insta360 to 1280 × 720 and keeps the bench file. What goes wrong, and what does NAVERA do?</summary>
K is in pixels of the 1920 × 540 top half: every ray is wrong (27.7° at the image centre in the brief's example,
about 79 m on the ground from 150 m). NAVERA's live camera refuses a file made at another resolution; the camera
must be calibrated again at the new size.
</details>

<details><summary>5. (Mission 18) A level camera at 150 m with an attitude 1° wrong. How far is the centre point off on the ground?</summary>
150 · tan 1° = 2.6 m.
</details>

Now open the **🛠️ Lab** tab.
