# Lab 8 — Images as arrays: dtypes, filters, warps, and a photo made comparable with the map

**Goal:** implement the core image operations yourself with numpy — safe uint8 conversion, grey,
histogram, normalisation and equalisation, a true 2-D convolution, Gaussian and Sobel kernels, the
rotation–scale matrix and a bilinear affine warp — verify each one against OpenCV, then use them to
bring a drone photo to the map's orientation and scale, and measure how sensitive the comparison is.
**Time:** about 3 hours.

| File | Role |
|---|---|
| [images_lab.py](file:./images_lab.py) | **your work**: eleven functions marked `TODO` (plus `flip_horizontal`, done as an example) |
| `explore.py` | prints a real frame as numbers (ready) |
| `demo.py` | runs your functions on a real frame, saves `out/*.png`, prints dtype and range (ready) |
| `like_map.py` | compares the map with the photo before/after your `make_like_map()` (ready) |
| `analysis.py` | your filters against OpenCV, contrast methods, heading and scale sweeps → `results.json` (ready) |
| [report.md](file:./report.md) | **your work**: the written analysis |

Data (read-only): 31 real aerial frames in `/data/navera_data/camera_pkg/camera_pkg/data/day/`
(1536 × 730, used only as pictures), and in `/data/academy/08-images/`: `map_patch.png` (512 × 512,
zoom 17, north up, Port El Kantaoui marina in NAVERA's Sousse test map), `drone_photo.jpg` (a
**simulated** photo of the same place: heading 35°, 0.6 m/px, darker, warmer, blurred, noisy) and
`info.json` (its exact parameters). Every picture a script saves appears in the file list: click it.

## Step 1 — A photo is an array

```bash
python3 explore.py
```

Read: `ndarray of uint8`, shape `(730, 1536, 3)`, the BGR values of two pixels, the range of each
channel, and an 8 × 8 block of grey values. Open `frame.png` and `centre_8x8_zoomed.png`.

Now see the uint8 arithmetic of the course with your own eyes:

```bash
python3 -c "import numpy as np; a = np.array([250, 100], np.uint8); print(a + 10, a * 2, a / 2, (a / 2).dtype)"
```

`[  4 110] [244 200] [125.  50.] float64`: wrap-around, then a silent change of dtype.

## Step 2 — Safe conversion and grey (TODO 1 and TODO 2)

**TODO 1** `to_uint8(a)`: round (`np.rint`), clip to 0..255, then `.astype(np.uint8)` — in this order.
**TODO 2** `to_gray(img)`: if `img.ndim == 2` return it; else compute Y = 0.299 R + 0.587 G + 0.114 B
**yourself** in float32 (remember: channel 0 is blue) and return `to_uint8(...)`.

```bash
python3 -c "import numpy as np; from images_lab import to_uint8; print(to_uint8(np.array([-5.6, 0.4, 99.5, 254.6, 300.0])))"
```

Expected `[  0   0 100 255 255]`. Then compare your grey with OpenCV's on the simulated photo:

```bash
python3 -c "import cv2, numpy as np; from images_lab import to_gray; p = cv2.imread('/data/academy/08-images/drone_photo.jpg'); print(np.abs(to_gray(p).astype(int) - cv2.cvtColor(p, cv2.COLOR_BGR2GRAY)).max())"
```

The maximum difference must be 0 or 1 (rounding).

> [!TASK]
> **TODO 1–2 done** means: `to_uint8()` rounds, clips before converting and returns uint8; `to_gray()`
> gives 29, 150, 76 for pure blue, green, red, equals `cv2.cvtColor` to ± 1 and returns a grey
> picture unchanged.

## Step 3 — Histogram, normalisation, equalisation (TODO 3, 4, 5)

- **TODO 3** `histogram(gray)`: `np.bincount(gray.ravel(), minlength=256)`.
- **TODO 4** `normalise(gray)`: min–max stretch in float, then **`to_uint8()`** — the course explains
  why. A uniform picture (max = min) is returned unchanged.
- **TODO 5** `equalise(gray)`: CDF with `np.cumsum`, `cdf_min` = the first non-zero value
  (`cdf[np.nonzero(cdf)[0][0]]`), a lookup table `lut` of 256 uint8 values, then `lut[gray]` — numpy
  replaces every pixel value v by `lut[v]` in one operation.

```bash
python3 demo.py
```

Each line shows shape, **dtype**, min and max. Open `out/dark_gray.png` (a dull version of the frame:
only 89 grey values used), `out/dark_normalised.png`, `out/dark_equalised.png`, `out/dark_clahe.png`
and `out/histogram.png` (blue: before; red: after equalisation). The last lines of `demo.py` show the
OpenCV error you get when CLAHE receives a float64 picture: now you know what it means.

> [!TASK]
> **TODO 3–5 done** means: 256 counts summing to the pixel count; `normalise()` returns uint8 with
> [[50, 100], [150, 50]] → [[0, 128], [255, 0]]; `equalise()` equals `cv2.equalizeHist` to ± 1.

## Step 4 — Convolution, Gaussian and Sobel (TODO 6, 7, 8)

- **TODO 6** `convolve2d(img, kernel)`: a **true** convolution (flip the kernel with `[::-1, ::-1]`),
  same output size, border `np.pad(..., mode="reflect")`, result float32. Loop over the k × k
  kernel entries only, and add whole shifted slices of the padded image: numpy does the pixels.
- **TODO 7** `gaussian_kernel(k, sigma)`: 1-D Gaussian, normalised, `np.outer(g, g)`; OpenCV's rule
  when `sigma <= 0`.
- **TODO 8** `sobel(gray)`: returns `(gx, gy)` equal to `cv2.Sobel(gray, cv2.CV_32F, 1, 0)` and
  `(0, 1)`. OpenCV correlates; your function convolves. Which kernel must you pass?

Test against OpenCV:

```bash
python3 -c "import cv2, numpy as np; from images_lab import *; g = to_gray(cv2.imread('/data/academy/08-images/drone_photo.jpg')); k = gaussian_kernel(7, 1.5); print(np.abs(convolve2d(g, k) - cv2.GaussianBlur(g.astype(np.float32), (7, 7), 1.5)).max()); print(np.abs(sobel(g)[0] - cv2.Sobel(g, cv2.CV_32F, 1, 0)).max())"
```

Both numbers must be tiny (below 0.001). If the second is large (hundreds), look at the sign of your
gx on a picture that gets brighter to the right.

```bash
python3 demo.py
```

Open `out/blur_own.png` (your 7 × 7 Gaussian) and `out/sobel_magnitude.png` (√(gx² + gy²)/4): every
building outline and road edge is bright.

> [!TASK]
> **TODO 6–8 done** means: the identity kernel returns the picture, a kernel with a 1 left of the centre
> gives out[y, x] = img[y, x + 1] (true convolution), the border is "reflect 101", a random 5 × 5
> kernel matches `cv2.filter2D` with the flipped kernel; your Gaussian kernels equal
> `cv2.getGaussianKernel`; your Sobel equals `cv2.Sobel`. All float32.

## Step 5 — The affine matrix and the warp (TODO 9 and TODO 10)

- **TODO 9** `rotation_scale_matrix(cx, cy, angle_deg, scale)`: the 2 × 3 matrix of the course
  (`np.radians`, `np.cos`, `np.sin`), float64.
- **TODO 10** `warp_affine(gray, M, out_w, out_h)`: inverse mapping and bilinear interpolation, as in
  the course figure. `np.mgrid[0:out_h, 0:out_w]` gives two arrays v, u with the row and column of
  every output pixel; compute x and y for all of them at once with A⁻¹; `np.floor` → integer arrays
  `x0`, `y0`; read the 4 neighbours with the helper `_get(gray, ys, xs)` (it returns 0 outside). The
  result is float32.

```bash
python3 -c "import cv2, numpy as np; from images_lab import *; print(rotation_scale_matrix(320, 240, -35, 0.6201)); print(cv2.getRotationMatrix2D((320, 240), -35, 0.6201))"
```

The two matrices must be identical. Then `python3 demo.py` and open `out/rotated_30_half.png`: the
frame turned 30° **counter-clockwise** and halved about its centre, black outside.

> [!TASK]
> **TODO 9–10 done** means: `rotation_scale_matrix()` equals `cv2.getRotationMatrix2D` for four sets
> of parameters; `warp_affine()` with the identity returns the picture, matches `cv2.warpAffine`
> (mean difference below 0.25 grey level), and gives 0 outside the source.

## Step 6 — Make the drone photo look like the map (TODO 11)

**TODO 11** `make_like_map(photo, heading_deg, photo_m_per_px, map_m_per_px, method)`:

1. `to_gray()`;
2. contrast: `normalise()` (default), `equalise()`, or CLAHE (`cv2.createCLAHE(clipLimit=2.0,
   tileGridSize=(8, 8)).apply(g)` — needs uint8) — **before** the warp, so that the black corners the
   rotation adds do not count as "the darkest pixel";
3. one matrix: `rotation_scale_matrix(w / 2, h / 2, angle, s)` — which angle (sign!) and which s?
4. shift the last column so the photo centre lands at the centre of the round(w·s) × round(h·s) output
   (worked example in the course);
5. `warp_affine()`, then **`to_uint8()`** — the result is a picture.

```bash
python3 like_map.py
```

The raw photo scores a similarity near 0.06 with the map; your prepared photo must score above 0.9
with a mean difference below 25. Open `comparison.png` (map | raw | normalise | equalise | CLAHE):
the marina's pontoons must line up.

> [!TIP]
> If the check says **only** that the dtype is wrong, your geometry is fine: add `to_uint8()`. If the
> similarity is near 0 or negative, the photo is turned the wrong way (+35 instead of −35, i.e. 70°
> from north). If the size is wrong, check s = photo_m_per_px / map_m_per_px.

> [!TASK]
> **TODO 11 done** means: a grey **uint8** picture of about 397 × 298 px whose 160 × 160 middle matches
> the map with similarity > 0.9 and a mean difference < 25 from the normalised map.

## Step 7 — Analysis and report

```bash
python3 analysis.py
```

It writes `results.json` and `analysis.png`: the dtype of each of your functions' outputs, your
convolution, Sobel and warp against OpenCV (maximum and mean differences, time), the similarity and
difference with the map for the raw photo and the three contrast methods, and two **sweeps**: the
similarity when `make_like_map()` is given a heading from 0° to 70°, and a photo m/px from 0.50 to 0.70.
Open `analysis.png`.

Write [report.md](file:./report.md) (150–400 words, your own words, three headings):

- **## Convolution** — how close your filters and warp are to OpenCV (numbers), why a true
  convolution flips the kernel and what that does to Sobel, the speed difference.
- **## Preprocessing** — similarity and difference for raw, normalise, equalise and CLAHE; why
  equalise can keep a high similarity but a larger difference; which dtype each step must return.
- **## Geometry** — the best heading and best photo m/px of the sweeps against `info.json`, the range of
  headings with similarity above 0.5, and what that means for the heading and altitude accuracy
  NAVERA needs before a pixel comparison.

> [!TASK]
> `python3 analysis.py` runs (the check runs it again) and `report.md` has the headings
> `## Convolution`, `## Preprocessing`, `## Geometry`, at least 150 words, and quotes the raw
> similarity (≈ 0.06), the similarity after normalise (≈ 0.975), the best heading (35) and the best
> photo m/px (0.60). Then press **✔ Check my work**.

## Going further (optional)

- **Separable convolution.** Write `convolve_separable(img, g1d)` (rows, then columns) and time it
  against your `convolve2d()` for k = 3, 7, 15, 31. Plot the times against k: which grows like k, which
  like k²?
- **Aliasing.** Shrink a real frame by 0.25 with your `warp_affine()` with and without a Gaussian blur
  of σ = 0.5/0.25 = 2 first. Compare both with `cv2.resize(..., interpolation=cv2.INTER_AREA)` using
  `difference()`. Look at roof tiles and road markings.
- **Edges against edges.** Compute Canny edges of the map patch and of your prepared photo
  (`cv2.Canny` needs uint8) and their similarity. Is it more or less sensitive to the heading than the
  grey-level similarity? Run the heading sweep on edges.
