# Lab 20 — Corners, scale and descriptors, measured

**Goal:** implement the Harris detector from its maths, find the characteristic scale of a blob, compare
your Harris with OpenCV's ORB and SIFT on pictures with a known transform (repeatability), measure binary
descriptor distances, score the "matchability" of different terrains, and write a short report.
**Time:** 2½ – 3 hours.

Your pictures are in `/data/academy/20-features/` (read only). They are cut from **NAVERA's satellite
map of Sousse, Tunisia** (the only map NAVERA has today):

| File | What it is |
|---|---|
| `terrain_city.jpg`, `terrain_olives.jpg`, `terrain_farms.jpg`, `terrain_hills.jpg`, `terrain_coast_water.jpg`, `terrain_sea.jpg` | 512 × 512 map patches, zoom 17 (≈ 0.97 m/px, ≈ 500 m of ground) |
| `terrain.csv` | one line per patch: file, terrain, lat, lon, zoom, m_per_px, description |
| `pair_*.jpg` + `pairs.json` | synthetic 640 × 480 "drone photos" of some patches — turned, closer (made from the zoom 18–19 map) — with the **exact** 3 × 3 transform `H` from the patch to the photo |
| `drone_city.jpg`, `drone_city_blurry_dark.jpg` | a drone view of the medina, clear and very blurred/dark |
| `real_aerial_frame.jpeg` | a real aerial photo of a Sousse district (picture only: the position in its flight log is **wrong**) |

Your code goes in [features.py](file:./features.py) (TODOs 0–8). Helper programs: `peek.py`,
`scale_demo.py`, `clahe_demo.py`, `measure.py`, `my_spot.py` — read them, do not change them.

## Step 1 — Look at the data

```bash
ls -l /data/academy/20-features/
```

```bash
python3 -c "import json; [print(p['name'], p['scale'], p['heading_deg'], p['what']) for p in json.load(open('/data/academy/20-features/pairs.json'))]"
```

Open `terrain_city.jpg` and `pair_city_zoom4.jpg` in the editor (📝 Code → open file → paste the path).
The second one shows the north-west part of the first, 3.9 times closer.

> [!QUESTION]
> Before measuring: which terrain do you expect to have the most keypoints, and which the fewest? Which
> detector do you expect to suffer most from the ×3.9 zoom? Write your guesses down.

## Step 2 — Gradients (TODO 1)

Run the demo once:

```bash
python3 features.py
```

It prints `(TODO 1 is not done yet)`. Open [features.py](file:./features.py).

> [!TASK]
> **TODO 1.** `image_gradients(grey)` returns `(Ix, Iy)` as `float32` arrays of the picture's shape:
> `cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)` for `Ix`, `(…, 0, 1, …)` for `Iy`, both divided by
> `SOBEL_NORM` (= 8, see the lesson's worked example). Convert the picture with
> `grey.astype(np.float32)` first.

Run `python3 features.py` again: the line `TODO 1  ramp I = 3x: Ix = 3.00` must show 3.00 and 0.00.

> [!WARNING]
> If you get `Ix = 0` on half of a test, you probably used an 8-bit output depth: negative gradients were
> cut to 0. Use `cv2.CV_32F`.

## Step 3 — Harris (TODOs 2 and 3)

> [!TASK]
> **TODO 2.** `harris_response(grey, sigma=1.5, k=0.05)`: compute `Ix·Ix`, `Iy·Iy`, `Ix·Iy` (element-wise,
> numpy `*`), smooth each with `cv2.GaussianBlur(product, (0, 0), sigma)` → `Sxx, Syy, Sxy`, and return
> `R = Sxx·Syy − Sxy² − k·(Sxx + Syy)²` as `float32`. No Python loops.
>
> **TODO 3.** `harris_corners(grey, n=500, sigma=1.5, k=0.05, nms_radius=4, rel_threshold=0.01)`:
> 1. `R = harris_response(...)`;
> 2. local maxima: `R == cv2.dilate(R, np.ones((2*nms_radius+1,)*2, np.uint8))`;
> 3. and `R > rel_threshold * R.max()`;
> 4. `ys, xs = np.nonzero(mask)` (rows first!), sort by `R[ys, xs]` decreasing, keep `n`;
> 5. return a `float32` array of shape `(m, 2)` with columns **x, y**.

```bash
python3 features.py
```

Open `harris_city.png`: the 300 strongest corners are yellow crosses.

> [!QUESTION]
> Are the crosses on roof corners, on straight walls, inside flat courtyards? Compare with the table
> "flat / edge / corner" of the lesson. Then check your understanding of the sign of R with the
> self-check question 1 of the lesson.

Compare your `R` with OpenCV's (which uses a box window instead of a Gaussian):

```bash
python3 -c "import cv2, numpy as np; from features import *; g = cv2.imread(DATA + '/terrain_city.jpg', 0); r = harris_response(g); o = cv2.cornerHarris(g.astype(np.float32), 5, 3, 0.05); print('correlation', np.corrcoef(r.ravel(), o.ravel())[0, 1])"
```

You should see a correlation above 0.9. The values differ by a constant factor (OpenCV does not divide
the Sobel output by 8, and averages with a 5 × 5 box): only the **shape** of R matters for detection.

## Step 4 — Characteristic scale (TODO 4)

> [!TASK]
> **TODO 4.** `characteristic_scale(grey, x, y, sigmas)`: for each `s` in `sigmas`, blur the float32
> picture (`cv2.GaussianBlur(g, (0, 0), s)`), take `cv2.Laplacian(blurred, cv2.CV_32F, ksize=1)`, read its
> value at row `y`, column `x`, multiply by `s**2`, take the absolute value. Return the `s` with the largest
> value (a float).

```bash
python3 scale_demo.py
```

The table must show `sigma*` close to `r/sqrt2` for r = 4, 8, 16. Open `scale_curves.png`: your σ* for
radii 3 to 20 px lies on the straight line r/√2 — the measured scale is **proportional** to the size of the
blob. Doubling the radius doubles σ*. This is the principle of SIFT's scale selection. (The small steps come
from the list of σ values tried, 8 % apart.)

## Step 5 — OpenCV's ORB and SIFT (TODOs 5 and 0)

> [!TASK]
> **TODO 5.** `detect_keypoints(img, method="ORB", max_points=10000)`: grey picture if `img.ndim == 3`
> (`cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)`), then `cv2.ORB_create(nfeatures=max_points)` or
> `cv2.SIFT_create(nfeatures=max_points)`, `raise ValueError(...)` for any other name, then
> `kps, des = detector.detectAndCompute(grey, None)`; return `list(kps), des`.

```bash
python3 features.py
```

Open `keypoints_city.png`: each circle is a keypoint, its radius the keypoint's `size` (scale), the line its
`angle`. Now look inside the descriptors:

```bash
python3 peek.py
```

> [!TASK]
> **TODO 0.** At the top of `features.py`, set `ORB_BYTES` and `SIFT_LENGTH` to the length of **one**
> descriptor (the second number of `descriptor array shape`). Note also the `dtype` of each.

## Step 6 — Hamming distance (TODO 6)

> [!TASK]
> **TODO 6.** `hamming(a, b)`: the number of different bits between two `uint8` descriptors:
> `np.bitwise_xor`, then `np.unpackbits`, then the sum. Return a Python `int`.

Test it against OpenCV:

```bash
python3 -c "import numpy as np, cv2; from features import hamming; a = np.array([0b10110000], np.uint8); b = np.array([0b10010001], np.uint8); print(hamming(a, b), cv2.norm(a, b, cv2.NORM_HAMMING))"
```

Both numbers must be 2 (the lesson's worked example).

## Step 7 — Repeatability (TODO 7)

> [!TASK]
> **TODO 7.** `project(points, H)`: add a column of ones to the `(N, 2)` points, multiply by `H.T`, divide
> the first two columns by the third; return `(N, 2)`.
> `repeatability(pts_a, pts_b, H, shape_b, eps=3.0)`: project the A points, keep those inside B
> (`0 ≤ x < w` and `0 ≤ y < h`), find the nearest B point of each with `scipy.spatial.cKDTree(pts_b).query(...)`
> and return the share within `eps`. Return `0.0` when no A point falls inside.

Test it on one pair, Harris against Harris:

```bash
python3 -c "import cv2, json, numpy as np; from features import *; p = json.load(open(DATA + '/pairs.json'))[0]; a = cv2.imread(DATA + '/' + p['map'], 0); b = cv2.imread(DATA + '/' + p['photo'], 0); print(p['name'], repeatability(harris_corners(a, 1000), harris_corners(b, 1000), np.array(p['H']), b.shape))"
```

You should get about 0.6 for `city_rot35`.

## Step 8 — Spread and matchability (TODO 8), CLAHE

> [!TASK]
> **TODO 8.** `spread(keypoints, shape, grid=(4, 4), min_per_cell=3)`: `grid = (columns, rows)`; the cell
> of a keypoint at `x, y = kp.pt` is column `int(x / w * columns)` and row `int(y / h * rows)`, both kept
> inside the grid. Count per cell (`np.zeros((rows, columns), int)`), return the share of cells with at
> least `min_per_cell`. `matchability(img, enough=300)`: ORB keypoints with `max_points=500`, return
> `min(1, n / enough) * spread(keypoints, img.shape)`.

```bash
python3 features.py
```

The last lines list the matchability of six pictures: about 1 for the city, the olives and the clear drone
photo, 0 for the water and the blurry dark photo. Now see what contrast stretching does:

```bash
python3 clahe_demo.py
```

```bash
python3 clahe_demo.py terrain_coast_water.jpg
```

Open `clahe_demo.png` after each run (left: original, right: CLAHE). On the dark drone photo the city comes
back. On the water the new keypoints sit on ripples and seagrass shadows — will they be there on the next
satellite picture?

## Step 9 — Measure everything and write the report

`measure.py` runs your functions on all the pairs and terrains and saves `results.json`:

```bash
python3 measure.py
```

It prints a table of repeatability (Harris / ORB / SIFT / chance) for each pair, the ORB Hamming medians,
the SIFT counts per terrain and the matchability scores. Open `results.json` too.

> [!TASK]
> **Report.** Open [report.md](file:./report.md) and replace each TODO with at least 40 words of your own:
>
> 1. **Scale** — quote the `city_zoom4` repeatability of Harris and SIFT (from your results.json, e.g.
>    `0.32` or `32 %`), and of `city_rot35`; explain the difference with the lesson's ideas; compare with
>    the chance level.
> 2. **Descriptors** — quote both Hamming medians (same point, random) and explain the random value.
> 3. **Terrain** — which terrains are easy or hopeless, with numbers; why the olive grove is a trap; what
>    CLAHE did on water.
> 4. **Oman** — discuss at least two Omani places (Batinah coast, Muscat, Hajar mountains, Wahiba Sands,
>    the sea off Masirah, Barr Al Hikman…): what would the camera see, what would SIFT and the
>    matchability score do?
>
> The check verifies the four headings, the word counts, the quoted numbers and the Omani places — and it
> recomputes one repeatability value with your code, so run `measure.py` again after any change.

## Step 10 — Check your work

Press **✔ Check my work**. There are 14 checks: each TODO is tested on synthetic cases with known answers
(a ramp, a white square, disks, random bytes) and on the dataset, then `results.json` and `report.md`.
Read the hint of any red line, fix, save, check again.

## Going further (optional)

- **A fairer tolerance.** A fixed ε = 3 px punishes keypoints detected at a coarse scale. Change a copy of
  `repeatability` so that ε grows with the keypoint's `size` (for example `ε = max(3, 0.5·size)`). Does ORB
  catch up with SIFT?
- **Your own spot.** `my_spot.py` cuts a patch of the real map anywhere around Sousse and scores it:

  ```bash
  python3 my_spot.py 35.8256 10.6370
  ```

  Try the port, the beach, the salt lake (sebkha) south of Sousse, the motorway. Which places would you
  avoid if you had to navigate by camera?
- **Repetition detector.** For each SIFT descriptor of the olive grove, compute the distance to its nearest
  *other* descriptor in the same picture (`cv2.BFMatcher().knnMatch(des, des, k=2)`, take the second
  neighbour). Compare the median with the city's. A small value means "I have a twin" — the problem the
  **ratio test** of lesson 21 solves.
- **The real frame.** Count the SIFT keypoints of `real_aerial_frame.jpeg` per 10 000 pixels and compare
  with the map patches. Is a real camera frame more or less textured than the satellite map?
