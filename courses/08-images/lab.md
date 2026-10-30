# Lab 8 — Make a drone photo comparable with the map

**Goal:** write the image part of NAVERA Lite (`navera_lite/image.py`): safe dtype conversions, a true 2-D
convolution, the affine matrix, a bilinear warp, and `like_map`, which turns a drone photo north-up at the
map's scale. Check each one against OpenCV, then use them to find how wrong the drone's compass was, and
write a short engineering note.
**Time:** 3 to 5 h (a strong programmer: about 3 h; 5 h if numpy is new to you).
**Fast track:** if you know numpy, skip the 🧰 boxes and the "Stuck?" boxes; do "Going further" at the end.

Your files (📝 Code tab): [navera_lite/image.py](file:./navera_lite/image.py) (**your code**: seven
functions, `TODO 1–7`, with numpy and math only: OpenCV is the reference you compare with, never called
inside image.py; `to_gray`, `histogram`, `gaussian_kernel`, `sobel` and `pixel_or_zero` are given),
[answers.py](file:./answers.py), [report.md](file:./report.md), and one ready-made tool you only run:
[run_images.py](file:./run_images.py) (runs your functions on the lab's pictures and saves what they make
in `out/`). Data, read only, in `/data/academy/08-images/`: `real_frame.jpg` (a real aerial frame from
NAVERA's day-camera test data), `thermal16.png` (a synthetic 16-bit thermal-like frame), `map_patch.png` and
`drone_photo.jpg` (both drawn from OpenStreetMap data by the same renderer — © OpenStreetMap contributors),
`info.json`.

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §1 arrays | Step 1 | (look) |
| §2 dtypes | Step 2 | `to_uint8`, `to_float01`, `normalise` |
| §4 convolution | Steps 3–4 | by hand, then `convolve2d` |
| §5 the affine matrix | Step 5 | by hand, then `affine_matrix` |
| §6 resampling | Step 6 | `warp_affine` |
| §7 photo → map | Steps 7–9 | a hand trace, `like_map`; heading and scale sweeps; the note |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is
> never marked right or wrong. Each function's docstring says its goal and gives an example with its
> result; `python3 run_images.py test` tries every example. The lesson shows how; the code is yours.

## Session 1 — Darkroom (about 1 h 45; 2 h 30 if numpy is new to you)

## Step 0 — A 16-bit frame meets a byte

No code. `thermal16.png` is a 16-bit frame (uint16) whose values run from about 7 150 (cold) to 8 430 (warm).
Someone displays it with a plain `t.astype(np.uint8)`. NAVERA's LOC-24 was this family of bug: 16-bit thermal
converted to 8 bits without scaling, which saturates or blanks the scene. Here you meet its worst form.

> [!TASK]
> **Predict** (`PREDICT_CAST` in `answers.py`): what will that picture look like? Save the file (`Ctrl+S`).
> Then read lesson §1–§2 (about 25 min).

## Step 1 — A photo is an array

```bash
python3 run_images.py explore
```

Read the type, dtype and shape, the [blue, green, red] values of two pixels, the range of each channel, and
an 8 × 8 block of grey values. Open `out/frame_half.png` and `out/frame_8x8_zoomed.png`: the red square of
the first is the second, pixel by pixel. Then see the uint8 arithmetic of lesson §2 with your own eyes:

```bash
python3 -c "import numpy as np; a = np.array([250, 100], np.uint8); print(a + 10, a * 2, a / 2, (a / 2).dtype)"
```

## Step 2 — Safe conversions (TODO 1, TODO 2, TODO 3)

Open the 📝 Code tab, then `navera_lite/image.py`. Each `TODO` function keeps its docstring and ends with
`return None   # TODO…`: replace that line with your code.

<details><summary>🧰 numpy: clip, rint, iinfo, kinds of dtype</summary>

```python
x = np.array([-2.0, 3.5, 4.5, 400.0])
np.rint(x)                          # [-2.,  4.,  4., 400.]  nearest integer (a half goes to the even one)
np.clip(x, 0, 255)                  # [  0.,  3.5, 4.5, 255.]  limits, still float
np.iinfo(np.uint8).max              # 255     np.iinfo(a.dtype).max works on any integer array's dtype
np.issubdtype(np.uint16, np.integer), np.issubdtype(np.float32, np.floating)   # True True
np.issubdtype(np.bool_, np.integer) # False: a bool array is not an integer image
g = np.array([[3, 9]], np.uint16); g.min(), g.max()   # 3 9   (numpy scalars of dtype uint16!)
np.zeros((2, 3), np.uint8)          # a uint8 array of zeros, shape (2, 3)
```
</details>

**TODO 1** `to_uint8(a)`: lesson §2, the rule in the box. **TODO 2** `to_float01(a)`: integers divided by
the largest value of their own dtype; floats only converted; anything else `raise ValueError("…")`.
**TODO 3** `normalise(gray)`: the min–max stretch of §2, computed in float, finished with your `to_uint8`.

```bash
python3 run_images.py test
```

The TODO 1, 2 and 3 lines must be ✔ (the others are later TODOs).

<details><summary>Stuck? Hints, one at a time</summary>

1. Each of the three is 2 to 6 lines. Work in float64 or float32 from the first line:
   `np.asarray(a, dtype=np.float64)`.
2. `[0, 0, 100, 255, 44]`: 300 wrapped to 44 — clip before converting. `[0, 0, 99, 254, 255]`: `astype`
   truncated 254.6 to 254 — `np.rint` first. Right numbers but dtype float64: the last step is
   `.astype(np.uint8)`.
3. to_float01 gives `[0, 51.4, 257]` for uint16: you divided by 255 for every dtype. Use
   `np.iinfo(a.dtype).max`, inside `if np.issubdtype(a.dtype, np.integer):`.
4. normalise gives a warning `invalid value encountered in divide`, or nan: the uniform picture has
   max = min. Test it **before** dividing and return `np.zeros(shape, np.uint8)`. Values that are wrong only
   for uint16 input: you computed in uint16 (`(g − lo) * 255` overflows) — convert to float first.
</details>

Now the thermal frame, cast naively and with your `normalise`:

```bash
python3 run_images.py cast
```

Open `out/thermal_naive.png` and `out/thermal_normalised.png`, and compare with your `PREDICT_CAST`.

> [!TASK]
> `NAIVE_COLDEST` and `NAIVE_HOTTEST`: what `.astype(np.uint8)` makes of the coldest and of the hottest pixel
> of `thermal16.png`. This prints the frame's coldest and hottest counts; then apply lesson §2's rule to each
> (by hand, or with `np.array([…], np.uint16).astype(np.uint8)`). `EXPLAIN_CAST`: why these two values, and
> why your `normalise` does not have the problem.

```bash
python3 -c "import cv2; t = cv2.imread('/data/academy/08-images/thermal16.png', cv2.IMREAD_UNCHANGED); print(t.dtype, t.min(), t.max())"
```

Careful: the darkest and brightest pixels of the cast **picture** are not what the coldest and hottest
**pixels** became. Then open "Read this after lab Step 2" at the end of lesson §2.

## Step 3 — Convolution by hand

Read lesson §4 first (about 20 min). Then do its worked example again on new numbers, with pencil and paper.

> [!TASK]
> `HAND_BLUR`: [2, 2, 2, 8, 8, 8] convolved with [1, 2, 1]/4, border reflect 101 (six numbers).
> `HAND_DERIV`: [2, 2, 2, 8, 8, 8] convolved (true convolution) with [1, 0, −1].

<details><summary>Stuck? Hints</summary>

1. Write the padded signal first: reflect 101 adds one value at each end, … c b | a b c …. Here
   [**2**, 2, 2, 2, 8, 8, 8, **8**].
2. With the flip, the kernel [1, 0, −1] gives out(x) = img(x + 1) − img(x − 1). Every sign reversed? That is
   the correlation.
3. A first value of 1.5 means you padded with 0.
</details>

## Step 4 — The convolution in code (TODO 4)

<details><summary>🧰 np.pad and shifted slices</summary>

```python
a = np.array([[1, 2, 3], [4, 5, 6]])
np.pad(a, ((0, 0), (1, 1)), mode="reflect")   # [[2, 1, 2, 3, 2], [5, 4, 5, 6, 5]]  … c b | a b c …
np.pad(a, ((1, 1), (0, 0)), mode="edge")      # repeats the edge row: not OpenCV's default
p = np.pad(a, ((0, 0), (1, 1)), mode="reflect")
p[:, 0:3], p[:, 2:5]                          # two slices of a's own size (2, 3): shifted left / right
k = np.array([[1, 2], [3, 4]]); k[::-1, ::-1] # [[4, 3], [2, 1]]: turned by 180°
out = np.zeros((2, 3)); out += 0.5 * p[:, 0:3]   # add a weighted slice to the result
```
</details>

**TODO 4** `convolve2d(img, k)`: pad by (rows // 2, columns // 2) with reflect, flip the kernel, then one
loop over the kernel's entries that adds `weight × slice` (lesson §4). An even-sized kernel has no centre:
`raise ValueError("…")`. Return float32.

```bash
python3 run_images.py test
```

> [!TASK]
> **Predict** (`PREDICT_SPEED`) before the next command: your convolution is plain numpy, OpenCV's is
> optimised C. How many times slower will yours be on the 1536 × 730 frame?

```bash
python3 run_images.py filters
```

The largest differences with OpenCV must be tiny (below 0.001). Open `out/blur.png` and `out/edges.png`
(the gradient magnitude √(gx² + gy²) × 4 of your `sobel`): every roof outline and kerb is bright.

> [!TASK]
> `EXPLAIN_FLIP`: what would a correlation (no flip) give with [1, 0, −1] in Step 3, and why does the flip
> change nothing for the Gaussian?

<details><summary>Stuck? Hints</summary>

1. `test` says "every sign is reversed": you forgot `k[::-1, ::-1]` — that is a correlation. `filters` says
   the same: "your gx is exactly MINUS OpenCV's".
2. "the border repeats the edge pixel" or "is filled with zeros": `mode="reflect"` is the only np.pad mode
   that matches OpenCV's default (reflect 101). `mode="symmetric"` repeats the edge pixel too.
3. A shape smaller than the image: you did not pad, or padded on one side only. Pad by `k.shape[0] // 2` rows
   at the top **and** bottom, `k.shape[1] // 2` columns left **and** right.
4. In the loop, the slice for kernel entry (i, j) is `p[i:i + H, j:j + W]` with (H, W) the image's shape.
</details>

> [!TIP] 🏅 End of session 1 — Darkroom
> Press **✔ Check my work**. When checks 1–6 pass (TODO 1–4, Steps 0–4), you earn the **Darkroom** badge.
> If the class session ends here, stop here.

## Session 2 — Map matcher (about 2 h; 2 h 45 if numpy is new to you)

Read lesson §5–§7 first.

## Step 5 — The affine matrix (TODO 5)

> [!TASK]
> By hand first (lesson §5 worked example, new numbers): `CORNER_UV`, where the pixel (0, 0) goes with
> `affine_matrix(-90.0, 0.5, (40.0, 30.0))`.

**TODO 5** `affine_matrix(angle_deg, scale, centre)`: the matrix of lesson §5, as a float64 numpy array of
shape (2, 3). Mind the argument order: the angle first.

```bash
python3 run_images.py test
```

<details><summary>Stuck? Hints</summary>

1. `math.cos` and `math.sin` take radians: `math.radians(angle_deg)`. `centre` is a pair: `cx, cy = centre`.
2. `test` says "b has the wrong sign": your matrix turns clockwise. The top row is [a, b, …], the bottom row
   [−b, a, …].
3. "the last column is 0": you turned about (0, 0). tx = (1 − a)·cx − b·cy, ty = b·cx + (1 − a)·cy.
4. CORNER_UV (25, 50): you used +90°. (0, 0): you forgot the centre.
</details>

## Step 6 — The warp (TODO 6)

<details><summary>🧰 every pixel at once: np.mgrid, floor, integer indexing</summary>

```python
v, u = np.mgrid[0:2, 0:3].astype(np.float64)      # row and column of every pixel of a 2 × 3 result
x = 0.5 * u + 0.25                                # a formula on whole arrays: one value per pixel
x0 = np.floor(x).astype(np.int64)                 # integer part, as integers (indices must be int)
fx = x - x0                                       # the fraction, 0 <= fx < 1
A = np.array([[2.0, 0.0], [0.0, 4.0]]); np.linalg.inv(A)   # [[0.5, 0. ], [0. , 0.25]]
img = np.array([[5, 6], [7, 8]])
pixel_or_zero(img, np.array([0, 1, 2]), np.array([1, 0, 0]))   # [6., 7., 0.]: (2, 0) is outside → 0
```
</details>

**TODO 6** `warp_affine(img, M, size)`: lesson §6. `size` is (width, height), OpenCV's order; the result has
`height` rows. For every destination pixel, the source point by A⁻¹; then the bilinear blend of its four
neighbours, read with `pixel_or_zero`. Return float32.

```bash
python3 run_images.py test
```

```bash
python3 run_images.py warp
```

`warp` compares your matrix with `cv2.getRotationMatrix2D` and your warp of the real frame with
`cv2.warpAffine` (mean difference below 0.25 grey level; OpenCV rounds its weights a little). Open
`out/rotated.png`: the frame turned 30° counter-clockwise and halved, black outside.

<details><summary>Stuck? Hints</summary>

1. Five parts: `a_inv = np.linalg.inv(M[:, :2])`; the grid `v, u` of the result; the source `x`, `y` of
   every pixel (subtract t first, then multiply by a_inv, written out entry by entry); `x0`, `fx`, `y0`,
   `fy`; the blend.
2. `test` says "the picture moved the wrong way" or "you multiplied by A, not by its INVERSE", or `warp`
   shows a mean difference of tens of grey levels (with a ⚠ line): the source of (u, v) is A⁻¹·((u, v) − t),
   so subtract t FIRST ("you subtracted t after multiplying" means the order is wrong).
   Did you call `np.linalg.inv(M[:, :2])` and use **that** in the two lines for x and y?
3. "no blending": a missing weight or `np.rint` instead of `np.floor`. The four reads are `(y0, x0)`,
   `(y0, x0 + 1)`, `(y0 + 1, x0)`, `(y0 + 1, x0 + 1)` — rows first.
4. `IndexError: arrays used as indices must be of integer…`: `np.floor(x).astype(np.int64)`. Shape
   (width, height) instead of (height, width): `np.mgrid[0:height, 0:width]`.
</details>

## Step 7 — The photo made like the map (TODO 7)

**TODO 7** `like_map(photo, heading_deg, gsd_photo_m, gsd_map_m)`: the least guided function. Its docstring
gives the exact result; lesson §7 gives the steps and a worked example.

> [!TASK]
> **By hand first** (`LIKE_TRACE`): for the lab's photo (640 × 480, 0.60 m/px, map 0.967527 m/px), the tuple
> `(s, side, dx, dy)` with s to 3 decimals and (dx, dy) = c_out − c_in, the column you add to M. Then write
> `like_map` with your own functions.

<details><summary>Check your trace (open after you wrote it)</summary>
s = 0.60 / 0.967527 = 0.6201 → 0.620; side = round(800 × 0.6201) = 496; c_in = (319.5, 239.5);
c_out = (247.5, 247.5); (dx, dy) = (−72, +8).
</details>

```bash
python3 run_images.py test
```

The three TODO 7 lines check the size (s and side), the centre (a dot at the photo's centre must land at the
result's centre) and the direction of the turn (a mark at the top of a photo whose top looks east must land
east).

> [!TASK]
> **Predict** (`PREDICT_NCC`) before running `like`: roughly what NCC will the raw photo give against the map,
> and your `like_map` at the compass heading? Then run it, open `out/like_map.png` (the map, the raw photo, your
> result), and write `NCC_COMPASS`, the like_map value it prints (three decimals).

```bash
python3 run_images.py like
```

<details><summary>Stuck? Hints</summary>

1. Order: `to_gray` → `normalise` → s and side → `affine_matrix` → shift the last column → `warp_affine` →
   `to_uint8`.
2. "the photo's top mark lands WEST" (heading 90°): you turned by +heading; the angle is −heading (lesson §7
   figure).
3. "the photo's centre lands at (28.69, 28.38)" or "(28.22, 27.84)" (other numbers, e.g. swapped, if your turn is
   also wrong) instead of (28.50, 28.50): half a pixel
   off — the centres are ((w − 1)/2, (h − 1)/2) and ((side − 1)/2, (side − 1)/2), not w/2. A centre far off: you did not add (c_out − c_in) to `M[0, 2]` and `M[1, 2]`.
4. Shape (58, 58) expected, yours smaller: side = round(hypot(w, h) · s), `math.hypot`. A dark, flat result
   in `like`: you normalised after the warp.
</details>

## Step 8 — How good was the compass?

`info.json` gives the heading the drone's compass (its IMU) reported: `heading_imu_deg`, the "compass heading". Compasses are not perfect. If you give
`like_map` other headings, the one whose result looks most like the map (highest NCC) is the best estimate
of the true heading. `python3 run_images.py sweep` tries 10° either side of the compass heading in steps of
0.5°; `python3 run_images.py sweep FROM TO STEP` tries your own range.

> [!TASK]
> **Predict** (`PREDICT_SWEEP`): where will the NCC peak, and how fast will it fall on each side? Is a 4°
> heading error worse than a 4 % scale error?

```bash
python3 run_images.py sweep
```

Open `out/sweep.png`. Then refine around your peak with a step of 0.1°: `python3 run_images.py sweep FROM TO 0.1`,
with FROM and TO 2° either side of your peak. For example, for a peak at 28.5°:

```bash
python3 run_images.py sweep 26.5 30.5 0.1
```

(Fine sweeps print the NCC with 4 decimals, so neighbouring headings do not tie.)

> [!TASK]
> `BEST_HEADING_DEG` (the heading of the highest NCC, to 0.1°), `COMPASS_ERROR_DEG` (true − compass, with its sign),
> `HEADING_TOL_DEG` (how many degrees either side of the best heading the NCC stays at 0.9 or more), and
> `EXPLAIN_SWEEP`: what does this say about the heading accuracy a pixel comparison needs, and what could a
> system do when its compass is not that good?

## Step 8b — Heading or scale?

The scale comes from the height above ground and the lens (mission 18); it is never exact either. Sweep the
photo's m/px at your best heading (this line reads `BEST_HEADING_DEG` from your `answers.py`; default range
0.54 to 0.66 m/px, step 0.005):

```bash
python3 run_images.py scale $(python3 -c "import answers; print(answers.BEST_HEADING_DEG)")
```

> [!TASK]
> `SCALE_TOL_PCT`: how many % either side of the best m/px the NCC stays at 0.9 or more (half the width of that
> zone, divided by 0.60). `EXPLAIN_SCALE`: which costs more here, a 5 % scale error or a 5° heading error, and
> which sensor sets each?

<details><summary>Read this after you wrote EXPLAIN_SWEEP and EXPLAIN_SCALE</summary>
A few degrees of heading error turn a near-perfect match into a mediocre one: the photo covers 384 m × 288 m,
and 4° moves its edges by 10–17 m (17 m at the corners). Pixel comparison is <b>not rotation-invariant</b>, so a system that uses it
needs a good heading (NAVERA's night vision takes it from the frame's data or the IMU) or a search over
headings like your sweep (more time, and more chances of a wrong match). The other way is a method that
estimates the rotation itself: NAVERA's day vision matches features and fits rotation, scale and
translation, and only checks that the scale agrees with the altitude. Features are mission 21.
Your peak NCC is high because this "photo" is a render of the same OpenStreetMap data as the map; a real photo
against a satellite map peaks much lower. The sweep's grid also limits your answer: the true value can lie
between two grid points.
</details>

## Step 9 — The engineering note

Write [report.md](file:./report.md) (150–400 words, your own words, keep the three headings): the thermal
cast, your filters against OpenCV, and the photo → map numbers with what they mean. Quote your numbers.

> [!TASK]
> report.md has the three headings, at least 150 words, and quotes the naive cast value (Step 2), the NCC
> with the compass heading and at the best heading, the best heading, and the ± tolerance (Step 8).
> Write a tolerance as ±0.8° or +/-0.8 deg (your own number, of course); both work.

## Step 10 — Check, then look back

Press **✔ Check my work**: it tests your functions on values, kernels and photos they have never seen. When
every check passes, you earn the **Map matcher** badge. Then look back, without the lesson:

1. Explain to a colleague in three sentences why a 16-bit frame must not be cast to 8 bits, and what to do
   instead.
2. Which of your predictions was the most wrong? What did you assume?
3. `like_map` resamples the photo once. Why is that better than turning it, then scaling it, in two warps?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **Separable convolution.** A Gaussian kernel is the outer product of a 1-D kernel with itself. Write
  `convolve_separable(img, g1d)` (rows, then columns) and time it against your `convolve2d` for k = 3, 7, 15,
  31. Which grows like k, which like k²?
- **Aliasing.** `like_map` shrinks the photo by 0.62 without blurring first. Blur it with
  `gaussian_kernel(5, 0.5 / 0.62)` before the warp and rerun the sweep: does the best NCC change?
- **Edges against edges.** Compare the Sobel magnitudes of your prepared photo and of the map instead of the
  grey levels. Is the peak of the heading sweep sharper or wider?
