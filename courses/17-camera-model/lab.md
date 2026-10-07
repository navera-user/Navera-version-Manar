# Lab 17 — Measure the world with a camera

**Goal:** implement the pinhole camera model (K, projection, back-projection onto the ground,
footprint, GSD, map zoom, error propagation), verify it against NAVERA's own code, use it on three
synthetic drone photos, and write a short analysis.
**Time:** about 3 hours.

| File | What you do with it |
|---|---|
| [camera_math.py](file:./camera_math.py) | the model — **TODO 1 to 6** |
| [measure_pad.py](file:./measure_pad.py) | measure a landing pad in the photos — **TODO 7** |
| [compare_with_navera.py](file:./compare_with_navera.py) | compares your functions with NAVERA's (nothing to change) |
| [experiments.py](file:./experiments.py) | runs all experiments, writes `results.json` and two charts (nothing to change) |
| [report.md](file:./report.md) | your key numbers and analysis — graded |

The photos in `/data/academy/17-camera-model/` are made from NAVERA's satellite map, which covers
**Sousse, Tunisia** (NAVERA's test area). They are what an ideal camera would see over flat ground,
so we know the exact truth. Numerical scenarios in this lab use places at different latitudes (Reykjavik, Sousse)
and a generic mountain range.

## Step 1 — Run the starter and read the conventions

```bash
python3 camera_math.py
```

Every line says `TODO not done yet`. Read the comment block at the top of
[camera_math.py](file:./camera_math.py) (world ENU with the origin on the ground under the drone,
camera axes OpenCV, `R_wc` maps camera → world), then scroll below the line
`you don't need to change anything below` and read `camera_rotation()`: it builds R_wc from
heading, pitch and roll exactly like NAVERA (lesson 16).

> [!TIP]
> Test small pieces in the Python shell: type `python3`, then for example
> `from camera_math import *` and `camera_rotation(0, 0, 0)`. Leave with `exit()`. After you edit
> the file, restart the shell — Python does not reload a module by itself.

## Step 2 — Intrinsics (TODO 1)

> [!TASK]
> **TODO 1:** write `focal_px(hfov_deg, width_px)`, `intrinsic_matrix(hfov_deg, width_px, height_px)`
> (a 3×3 **numpy array of floats**, principal point at the image centre, fx = fy, skew 0) and
> `fov_deg(f_px, size_px)` (the inverse relation, in degrees).

Run `python3 camera_math.py` again. You should see `focal length f 659.790 px`, `vertical FOV
44.511 deg` and

```
  K =
    [[659.8   0.  960. ]
     [  0.  659.8 270. ]
     [  0.    0.    1. ]]
```

659.8 px is the fx ≈ 660 px found by the real calibration of NAVERA's Insta360 (lesson 18).

## Step 3 — Projection (TODO 2)

> [!TASK]
> **TODO 2:** write `project(K, R_wc, C, X)`: the pixel (u, v) of the world point X, as a numpy
> array of 2 floats, or `None` if X is behind the camera. Use lesson sections 1–2: first move X
> into the camera frame (read the `R_wc` convention at the top of the file), then apply K.

Convert inputs with `np.asarray(X, float)` so that lists work too. Run the program: the line
`pixel of the ground point (30 m E, 45 m N)` must be `[576. 126.]` — worked example 1 of the lesson.

> [!WARNING]
> `R_wc @ v` and `R_wc.T @ v` are different rotations. With a nadir camera and heading 0 both give
> the same result for some points (the matrix is symmetric!), so a mistake can hide. The check
> uses a tilted camera too.

## Step 4 — Back-projection onto the ground (TODO 3)

> [!TASK]
> **TODO 3:** write `ground_point(K, R_wc, C, u, v)`: the **[east, north]** (m) where the ray of
> pixel (u, v) hits the ground z = 0, or `None` if the ray does not go down. This is lesson
> section 3: the ray direction in the world, then the ray–plane intersection.

To undo K you need its inverse: numpy has `np.linalg.inv` and `np.linalg.solve`. Run the
program: pixel (0, 0) of the nadir camera at 150 m is at `[-150. 84.38]` (north-west corner), and
the tilted camera (heading 30°, pitch −12°, roll 4°) sees at its image centre `[-25.23 -22.25]`.

> [!QUESTION]
> The drone heads 30° (north-north-east) and pitches nose down. Why is the image centre
> **south-west** of the drone? Draw the side view of lesson section 3 before you answer.

A good test of TODO 2 and 3 together: project a ground point, back-project the pixel, and you must
get the point back. Try it in the Python shell:

```python
from camera_math import *
K = intrinsic_matrix(90, 960, 540); R = camera_rotation(30, -12, 4); C = [0, 0, 150]
uv = project(K, R, C, [38, -92, 0]); print(uv, ground_point(K, R, C, *uv))
```

## Step 5 — Footprint and area (TODO 4)

> [!TASK]
> **TODO 4:** write `footprint_polygon(K, R_wc, C, width_px, height_px)` (the 4 corners
> (0,0), (w,0), (w,h), (0,h) on the ground, a (4, 2) array, `None` if one corner sees the sky) and
> `polygon_area(pts)` with the shoelace formula of lesson section 4.

Run the program: the tilted footprint area is about **56 669 m²**. A quick test of the shoelace
formula: a 4 × 3 rectangle must give 12, in both vertex orders (that is why there is an `abs`).

## Step 6 — GSD and map zoom (TODO 5)

> [!TASK]
> **TODO 5:** write `meters_per_pixel(height_m, hfov_deg, width_px)` (nadir GSD, lesson
> section 5), `map_m_per_px(lat_deg, zoom)` (lesson section 6 and lesson 07) and
> `best_zoom(height_m, hfov_deg, width_px, lat_deg, zooms=range(13, 20))`: the zoom **number**
> (int) from `zooms` whose map resolution is closest **in ratio** to the photo's
> (the smallest `abs(math.log(map_mpp / photo_mpp))`).

Expected: GSD 0.227 m/px at 150 m, zoom 17 is 0.521 m/px in Reykjavik and 0.968 m/px in Sousse, the
best zoom at 300 m over Reykjavik is 17 (over Sousse it is 18). An ordinary loop that keeps the best value is fine.

## Step 7 — Measurements and errors (TODO 6)

> [!TASK]
> **TODO 6:** write `height_from_object(size_m, size_px, f_px)` (the pinhole model of section 2,
> solved for the height), `fitted_scale(h_believed_m, h_true_m)` (the scale a map match would
> measure, section 7) and `tilt_position_error(height_m, tilt_deg, dtilt_deg)`: how far the
> ground point of the optical axis moves when the tilt is wrong by δθ (section 7 — compute it
> exactly, with and without the error, not with the linear approximation).

Expected: 120 m for a 12 m pad seen as 48 px with f = 480; scale 1.333 when NAVERA believes 150 m
and the drone is at 200 m; 2.708 m of ground error for 1° of tilt error at 150 m and 10° tilt.

## Step 8 — Compare with NAVERA

```bash
python3 compare_with_navera.py
```

This script imports **your** functions and NAVERA's (`navera_common.camera_model`,
`day_pkg.local_matcher`) and compares them: GSD, map resolution, K of `CameraModel.ideal()`, and —
the strongest test — it projects the point under the drone with **your** `project()` through
NAVERA's `nadir_homography()`: for any attitude, the straightened image must put that point exactly
at the image centre (480, 270). It also checks that your `ground_point()` of the image centre is
h·tan(tilt) away, with NAVERA's `tilt_deg()`. Every line must start with ✔ and the last line must
say `ALL MATCH`.

## Step 9 — Measure the photos (TODO 7)

Copy two photos into your folder to look at them:

```bash
cp /data/academy/17-camera-model/photo_A.png /data/academy/17-camera-model/photo_T.png .
```

Open [photo_A.png](file:./photo_A.png) (nadir, height unknown) and [photo_T.png](file:./photo_T.png)
(tilted: 150 m, heading 30°, pitch −12°, roll +4°). Each has a 12 m × 12 m orange pad on the ground.
In [measure_pad.py](file:./measure_pad.py), `orange_mask(img)` already returns a boolean array,
True on the pad's orange pixels.

> [!TASK]
> **TODO 7:** write `pad_size_px(img)` — the number of columns from the leftmost to the rightmost
> orange pixel, both included, as an int — and `pad_centre_px(img)` — `(u, v)` = (mean column,
> mean row) of the orange pixels. Both return `None` when no pixel is orange.

```bash
python3 measure_pad.py
```

You should see heights near 120 m (A) and 213 m (B, truth 210 m) with their ±1 px range, and the
pad of photo T at about **37.6 m east, −91.8 m north** of the point under the drone (the truth is
38.0, −92.0). Remember: numpy gives positions as (row, column), but a pixel is
`(u, v) = (column, row)` — swapping them is the classic bug here. Open `mask_photo_A.png` to see what the mask found.

## Step 10 — Run all experiments

```bash
python3 experiments.py
```

It writes `results.json` and two charts. It also runs your `measure_pad.py` again, so the
lines about photo A, B and T appear a second time — that is normal. Open [footprint.png](file:./footprint.png): the four
footprints at 150 m for pitch 0°, −10°, −20°, −30°, with their image-centre points. Open
[scale.png](file:./scale.png): the Insta360 GSD against height, with the map zoom levels of Reykjavik
(solid) and Sousse (dotted). Where the blue line crosses a zoom line, the photo has exactly that
map's resolution.

## Step 11 — Write the report

> [!TASK]
> Fill in [report.md](file:./report.md):
> - the **Key numbers** table, rows A to M — one number per row (most are in `results.json`;
>   D is a positive distance; for **M**, read `_scale_tol()` in the lesson: when does 2·σh/h become
>   larger than 0.15?);
> - the four analysis sections (**Tilt**, **Reykjavik and Sousse**, **Measuring the height with an
>   object**, **Height uncertainty**), each at least 40 words, with your own explanation and
>   numbers. Delete the TODO lines.

Then press **✔ Check my work**. The check runs your functions on new inputs, runs
`measure_pad.py` and `compare_with_navera.py`, reads `results.json` and checks the report.

## Going further (optional)

1. **Heading from the image.** NAVERA's `heading_of_image_up_deg(R)` gives the azimuth of the image's
   top on the ground. Compute it yourself: project two pixels of the image's centre column with
   `ground_point()` and take `atan2(ΔE, ΔN)`. Compare for photo T.
2. **Straighten photo T.** Build NAVERA's homography with
   `from navera_common.camera_model import nadir_homography`, warp photo T with
   `cv2.warpPerspective(img, H, (960, 540))` and save the result. Is the pad now square? Where is
   the point under the drone?
3. **Uncertainty by simulation.** Draw 10 000 random heights h ~ N(300, 30²) m and tilts
   θ ~ N(10°, 1°²) and compute the ground position of the image centre for each. Compare the
   standard deviation with the linear estimate √((tan θ · σh)² + (h σθ / cos²θ)²).
4. **Oblique GSD.** Check numerically that at the image centre of a camera tilted by θ, one pixel
   covers h/(f cos θ) across and h/(f cos² θ) along the tilt (back-project pixels (480, 270) and
   (481, 270), then (480, 271)).
