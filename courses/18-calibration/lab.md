# Lab 18 — Straighten the real Insta360 picture

**Goal:** load the real calibration of NAVERA's Insta360 camera, straighten a real fisheye
picture with it, **measure** that the lines became straight, compare with NAVERA's own code, and
calibrate the lens yourself from real chessboard photos.
**Time:** about 1 h 15.

You will work in [fisheye.py](file:./fisheye.py) (5 TODOs) and [answers.py](file:./answers.py).

> [!NOTE]
> The pictures in this lab are **real**: they were taken by the Insta360's top lens on the bench,
> during the calibration of 6 October 2026. Only the top half of each frame is given (the half
> NAVERA uses). No camera is needed for this lab.

## Step 1 — Look at the data

```bash
ls -l /data/academy/18-calibration /data/academy/18-calibration/views
```

You see the calibration file `insta360_top.yaml` and 14 photos of a chessboard shown on a
computer screen. Print the calibration file:

```bash
cat /data/academy/18-calibration/insta360_top.yaml
```

Find in it: the model (`fisheye`), the picture size (1920 × 540), the 9 numbers of
`camera_matrix`, the 4 numbers of `distortion`, the quality `rms_px` and the number of `views`.
At the end, `crop` says the calibration is for the top half, and `latency_s` is the camera delay
(lesson 19).

Copy one photo into your lesson folder so you can open it in the editor:

```bash
cp /data/academy/18-calibration/views/f0208.jpg .
```

Open [f0208.jpg](file:./f0208.jpg). Look at the long edges of the screen and at the window: they
are curved. In real life they are straight.

## Step 2 — Read the calibration (TODO 1)

In `fisheye.py`, write `load_calibration(path)`. It returns three things:

- `K`: the camera matrix, a 3 × 3 numpy array (the 9 numbers of `camera_matrix`, row by row);
- `D`: a numpy array of the 4 distortion numbers;
- `size`: the tuple `(width, height)`.

```python
import yaml
with open(path) as f:
    d = yaml.safe_load(f)          # d is now a Python dictionary
print(d["image_width"])            # 1920
```

> [!TASK]
> Write `load_calibration()` (TODO 1). `K[0, 0]` must be fx = 660.48…, `K[1, 2]` cy = 317.66…,
> and `size` = `(1920, 540)`.

## Step 3 — How wide does the lens see? (TODO 5)

Write `fisheye_fov_deg(K, size)` with the simple fisheye rule of the course,
**angle (radians) = distance from the centre (pixels) / focal length (pixels)**:

- the left edge of the picture is `cx` pixels left of the centre → angle `cx / fx`;
- the right edge is `(w - 1 - cx)` pixels to the right → angle `(w - 1 - cx) / fx`;
- the horizontal field of view is the sum of the two, converted with `math.degrees()`;
- the same vertically, with `cy`, `fy` and `h`.

Return `(hfov, vfov)` in degrees.

> [!TASK]
> Write `fisheye_fov_deg()` (TODO 5). For the Insta360 it gives about **166.5°** × **42.8°**.

## Step 4 — The perfect camera and the straightening (TODOs 2 and 3)

**TODO 2** — `straight_camera_matrix(hfov_deg, size)` builds the K of the perfect pinhole camera
we want to imitate:

> f = (w / 2) / tan(hfov / 2)    and    K_new = [[f, 0, w/2], [0, f, h/2], [0, 0, 1]]

Example to check by hand: for 90° and a 1000 × 500 picture, tan(45°) = 1, so f = 500.

**TODO 3** — `undistort(img, K, D, K_new)` builds the straight picture in two OpenCV calls:

```python
map1, map2 = cv2.fisheye.initUndistortRectifyMap(K, D, np.eye(3), K_new, (w, h), cv2.CV_16SC2)
flat = cv2.remap(img, map1, map2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
```

The first call computes the **map** (for each new pixel: where to fetch it in the fisheye
picture). `np.eye(3)` means "don't turn the camera". The second applies the map. `(w, h)` is
`(img.shape[1], img.shape[0])` — careful, numpy gives the height first.

> [!TASK]
> Write `straight_camera_matrix()` (TODO 2) and `undistort()` (TODO 3). The check compares your
> straight picture with the one NAVERA's code makes: they must be the same.

## Step 5 — Measure the straightness (TODO 4) and run

"It looks straighter" is not engineering. Let's **measure**. The program finds the 9 × 6 inner
corners of the chessboard (`find_corners()`, already written). Each row of 9 corners and each
column of 6 corners should lie on a straight line. Your `line_bend_px(points)` says how far they
are from it:

1. find the best straight line through all the points:
   `vx, vy, x0, y0 = cv2.fitLine(points.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()`
   gives a point `(x0, y0)` on the line and its direction `(vx, vy)`;
2. the distance of a point `(x, y)` to that line is `|(x - x0) * vy - (y - y0) * vx|`;
3. return the **largest** distance, as a `float`.

> [!TIP]
> Why not `np.polyfit` (y = a·x + b)? Because a chessboard **column** is almost vertical: x hardly
> changes, and y = a·x + b cannot describe a vertical line. `cv2.fitLine` works in every direction.

> [!TASK]
> Write `line_bend_px()` (TODO 4). Then run the program:

```bash
python3 fisheye.py
```

You should see the field of view, f = 659.8 px for 111°, and a line like
`most bent chessboard line: before 6.5 px, after 1.2 px`. Open
[before_after.jpg](file:./before_after.jpg): top, the fisheye picture; bottom, the straight one.
The red lines join the first and last corner of each row: before, the corners sag away from them;
after, they sit on them. Notice the **black borders** at the bottom: directions the lens never saw.

> [!QUESTION]
> Why is the result 1.2 px and not exactly 0? Think of the RMS error of the calibration (0.5 px),
> the corner detection, and the slightly curved screen.

## Step 6 — Compare with NAVERA's code

Your NAVERA copy has the code that straightens every frame on the drone. This small program
(nothing to change) asks NAVERA's `CameraModel` to straighten the same photo and compares:

```bash
python3 compare_navera.py
```

You should read `max_out_hfov_deg = 110.94 deg` (the 111° rule of the course: 2 atan(960/660.5)),
a focal length of the straight picture equal to fx = 660.5 px, and a mean difference of
**0.00**: your code and NAVERA's make the very same picture. Open
[navera_vs_mine.jpg](file:./navera_vs_mine.jpg) if you like. The NAVERA code is in
[camera_model.py](file:navera/navera_common/navera_common/camera_model.py) — find `undistort()`
and `max_out_hfov_deg()`.

## Step 7 — Where is the calibration valid?

```bash
python3 lens_curve.py
```

Open [lens_curve.png](file:./lens_curve.png). It draws, for each angle of an incoming ray, how
far from the centre it lands:

- blue, the pinhole `f × tan(angle)`: it explodes towards 90°;
- dashed, the ideal fisheye `f × angle`: a straight line;
- green, the real calibration with k1…k4. It follows the lens where the board was seen (up to
  about 52° from the axis), then **turns back down** after 67°. A real lens never does that: it is
  the polynomial guessing where it has no data.

The grey line is the left edge of the picture (937 px): the green curve never reaches it. The
calibration simply cannot describe the extreme edges — another reason why NAVERA keeps 111°.

## Step 8 — Calibrate the lens yourself

The 14 photos are enough for a small calibration. Run NAVERA's real tool on them (it takes about
half a minute):

```bash
python3 ~/navera/navera_tools/calibrate_camera.py --images /data/academy/18-calibration/views --board 9x6 --square-mm 32.94 --out my_calib.yaml
```

- `--board 9x6`: the inner corners, 9 columns × 6 rows;
- `--square-mm 32.94`: the side of one square, as displayed on the screen;
- the model is `fisheye` by default.

It prints `board found` for each photo, then something like
`fisheye calibration from 13 views: RMS 0.57 px (usable)`. (One view was refused by OpenCV as
badly conditioned and dropped — the tool does that automatically.) Compare:

```bash
cat my_calib.yaml
```

> [!TASK]
> Produce `my_calib.yaml` in your lesson folder. Its fx (first number of `camera_matrix`) should be
> within 3 % of the bench's 660.5 px, with an RMS below 1 px.

> [!QUESTION]
> Your fx is about 664 px, the bench file says 660.5 px. Which one would you trust more, and why?
> (Hint: how many views did each use?)

## Step 9 — Quiz

> [!TASK]
> Answer the three questions in [answers.py](file:./answers.py).

Press **✔ Check my work**.

## Going further (optional)

- **Wider is not better.** In `fisheye.py`, change `HFOV = 111.0` to `HFOV = 150.0` (near the top) and run
  again. Look at the centre of the chessboard in `before_after.jpg`: how much smaller is it? Compute
  the new f and compare with 660.
- **Fewer views.** Calibrate from only 8 photos (the tool needs at least 8):
  `mkdir -p few && cp /data/academy/18-calibration/views/f00*.jpg /data/academy/18-calibration/views/f0111.jpg few/`,
  then the Step 8 command with `--images few --out few.yaml`. How much do fx and the RMS change?
  What does that teach about collecting views?
- **Your own calibration at work.** In `fisheye.py`, change `CALIB_FILE` to `"my_calib.yaml"` and run
  it again. Is the straightened chessboard as straight as with the bench file?
