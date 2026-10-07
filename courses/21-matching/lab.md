# Lab 21 — Your own DLT and RANSAC, against OpenCV and NAVERA

**Goal:** implement the homography pipeline yourself (homogeneous coordinates, Hartley
normalisation, DLT with the SVD, the RANSAC sample formula, adaptive RANSAC, decomposition of H),
use it to lay synthetic drone views onto the satellite map, compare it with `cv2.findHomography`,
apply NAVERA's trust gates, and write a short analysis of your measurements.
**Time:** 2.5–3 h.

Your files:

| File | What you do |
|---|---|
| [geometry.py](file:./geometry.py) | TODO 1–6: the maths, numpy only |
| [matching.py](file:./matching.py) | TODO 7–9: ratio test, matching two pictures, trust gates |
| `experiments.py` | given: runs the measurements and writes `results.json` |
| [analysis.md](file:./analysis.md) | your written analysis (5 sections) |

The pictures are in `/data/academy/21-matching/` (read only). They are cut from NAVERA's test map,
which covers Sousse, Tunisia.

## Step 1 — The data

```bash
ls -l /data/academy/21-matching
```

```bash
python3 -c "import json; t = json.load(open('/data/academy/21-matching/truth.json')); [print(k, v['rotation_deg'], v['scale'], v['centre'], v['view_source']) for k, v in t.items() if k != 'line']"
```

There are four pairs. `patch_<name>.jpg` is an 800 × 800 piece of the map at zoom 18 (≈ 0.48 m per
pixel); `view_<name>.jpg` is a 480 × 360 synthetic drone view of a place inside it, turned, scaled,
blurred, with another brightness and noise. `truth.json` gives the true rotation, scale (patch
pixels per view pixel) and the patch pixel of the view centre.

| Pair | Content | Difficulty |
|---|---|---|
| `city` | Sousse medina, 30°, scale 0.8 | easy |
| `olives` | olive grove, −60°, scale 1.2 | repetitive texture |
| `otherdate` | a **2022** image matched against today's map, 120°, scale 1.5 | hard: other shadows, new buildings |
| `sea` | open water | impossible — must be refused |

## Step 2 — Homogeneous coordinates (TODO 1)

Run the self-test of `geometry.py`. Every TODO prints a line when it works:

```bash
python3 geometry.py
```

> [!TASK]
> **TODO 1a** `apply_homography(H, pts)`: (N, 2) points → (N, 2) points. Add a column of ones
> (`np.hstack`), multiply by `H.T`, divide the first two columns by the third.
> **TODO 1b** `reprojection_errors(H, src, dst)`: the (N,) array of ‖H(srcᵢ) − dstᵢ‖.

> [!WARNING]
> Common error: forgetting the division by W. With h20 = h21 = 0 it does not show (W = 1), so the
> check uses an H with perspective terms.

## Step 3 — Hartley normalisation (TODO 2)

> [!TASK]
> **TODO 2** `normalise_points(pts)` returns `(pts_n, T)`: the centroid moved to (0, 0), the mean
> distance to it equal to √2, and the 3 × 3 matrix T that does the same thing (course, section 4).

```bash
python3 geometry.py
```

You should see `centroid [0. 0.], mean distance 1.4142`.

## Step 4 — The DLT (TODO 3)

> [!TASK]
> **TODO 3a** `build_dlt_matrix(src, dst)`: the 2N × 9 matrix A, two rows per pair, exactly as in
> the course.
> **TODO 3b** `dlt_homography(src, dst, normalise=True)`: normalise both sets (when asked), build A,
> `np.linalg.svd(A)`, take the last row of Vᵀ, reshape to 3 × 3, de-normalise with
> `np.linalg.inv(T_dst) @ Hn @ T_src`, divide by `H[2, 2]`. Fewer than 4 pairs → `ValueError`.

```bash
python3 geometry.py
```

The DLT on the true inliers must give almost exactly `H_true`. Compare with OpenCV's own DLT
(method `0` = plain least squares, no RANSAC) on the noise-free inliers:

```bash
python3 -c "import cv2, numpy as np, geometry as g; s, d, H, m = g.synthetic_pairs(outlier_ratio=0.0); np.set_printoptions(precision=5, suppress=True); print('mine\n', g.dlt_homography(s, d)); print('opencv\n', cv2.findHomography(s, d, 0)[0])"
```

Now see why normalisation matters: 50 sets of 8 noisy pairs (1 px), with the map side moved to
global tile pixels (+3.55 × 10⁷, like NAVERA's map points), with and without normalisation:

```bash
python3 -c "import numpy as np, geometry as g; P = [g.synthetic_pairs(n=8, outlier_ratio=0.0, noise_px=1.0, seed=k) for k in range(50)]; grid = np.array([[0, 0], [640, 0], [640, 480], [0, 480], [320, 240]]); [print('normalise =', n, '  median error over 50 trials:', round(float(np.median([g.reprojection_errors(g.dlt_homography(s, d + 3.55e7, normalise=n), grid, g.apply_homography(H, grid) + 3.55e7).mean() for s, d, H, m in P])), 2), 'px') for n in (True, False)]"
```

Expected: about 2 px normalised, about 40 px raw.

> [!QUESTION]
> Look at the columns of A for a point near 3.55 × 10⁷: what is the ratio between the largest and
> the smallest entries? What does that do to the SVD in 64-bit floating point (≈ 16 significant digits)?

## Step 5 — How many samples? (TODO 4)

> [!TASK]
> **TODO 4** `ransac_iterations(p, w, s)` = ⌈log(1 − p) / log(1 − wˢ)⌉ as an `int`. w = 1 → 1;
> w ≤ 0 or p outside (0, 1) → `ValueError`.

```bash
python3 geometry.py
```

You should get N = 5, 17, 72, 567 for w = 0.9, 0.7, 0.5, 0.3 (s = 4, p = 0.99). Check one by hand
with the worked example of the course.

## Step 6 — RANSAC (TODO 5)

> [!TASK]
> **TODO 5** `ransac_homography(src, dst, threshold=5.0, p=0.999, max_iters=5000, seed=0)` returns
> `(H, mask)`. Use `rng = np.random.default_rng(seed)` and `rng.choice(n, 4, replace=False)`; skip
> degenerate samples with the given `_degenerate()`; after each better model, set the number of
> samples still needed to `ransac_iterations(p, inliers / n, 4)` (adaptive); stop at `max_iters`.
> Refit on all the inliers at the end and recompute the mask. Fewer than 4 pairs → `(None, mask)`.

```bash
python3 geometry.py
```

Expected: `RANSAC: 141 inliers, 141 of them true inliers` on 200 pairs with 59 outliers.

> [!TIP]
> If your RANSAC is slow, print the number of samples it ran. With 30 % outliers the adaptive N
> should drop to a few dozen after the first good sample.

## Step 7 — Rotation and scale (TODO 6)

> [!TASK]
> **TODO 6** `similarity_params(H)` returns a dict with `rotation_deg`, `scale`, `anisotropy`,
> `perspective`, `tx`, `ty` — the SVD (polar) reading of section 6 of the course.

```bash
python3 geometry.py
```

You should read rotation ≈ 35° and scale ≈ 1.2.

## Step 8 — The ratio test on real pictures (TODO 7)

> [!TASK]
> **TODO 7** in `matching.py`: `ratio_test(knn_pairs, ratio)` keeps `best` when
> `best.distance < ratio * second.distance`.

See the trade-off on the city pair (one long line — press ▶ Run):

```bash
python3 -c "import cv2, matching as m; v, p = m.load_pair('city'); _, a = m.features(v); _, b = m.features(p); pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(a, b, k=2); print(len(pairs), 'view keypoints'); [print('ratio', r, '->', len(m.ratio_test(pairs, r)), 'matches kept') for r in (0.6, 0.7, 0.8, 0.9, 1.0)]"
```

## Step 9 — Lay the views onto the map (TODO 8)

> [!TASK]
> **TODO 8** `match_views(view, patch, ratio=0.8, method="opencv", threshold=5.0)`:
> 8a the good matches; 8b `src`, `dst` as (N, 2) `float32` arrays (store them in `details`);
> 8c `"opencv"` → `cv2.findHomography(src.reshape(-1, 1, 2), dst.reshape(-1, 1, 2), cv2.RANSAC, threshold)`,
> `"mine"` → `geometry.ransac_homography(src, dst, threshold)`, anything else → `ValueError`.
> Store a **boolean** (N,) mask in `details["mask"]`; return `(H, number of inliers, details)`.

> [!WARNING]
> OpenCV returns its mask as an (N, 1) array of `uint8` 0/1. `mask.ravel().astype(bool)` makes it
> the (N,) boolean array the rest of the code expects. OpenCV also wants `float32` (or `float64`)
> points — a list of tuples or an `int` array gives an error about the input type.

```bash
python3 matching.py
```

For every pair you get one line for OpenCV and one for your RANSAC: good matches, inliers, time,
rotation, scale and the centre error against the truth. On the city and the olives both should be
within 0.1° and 0.5 px; open `overlay_city.png` (the view laid onto the map with H: the streets
must continue without a seam) and `matches_otherdate.png` (the inlier pairs).

> [!QUESTION]
> On `olives` your RANSAC finds more inliers than OpenCV (341 against 327). Both refit on their
> inliers; OpenCV then refines H on the pixel error. Why can a different final H accept or reject
> a few borderline pairs at a 5 px threshold?

## Step 10 — Trust gates (TODO 9)

> [!TASK]
> **TODO 9** `trust(H, src_inliers, view_shape, expected_scale, expected_rotation_deg=None, ...)`
> returns `(ok, reason)`. Refuse, in this order: no H; fewer than `min_inliers` (8); rotation further
> than `rotation_tol_deg` (20°) from the expected one (wrap the difference to −180…180); scale outside
> ±`scale_tol` (15 %) of the expected one; fewer than 30 inliers **and** `inlier_spread()` below
> `min_spread` (0.25). The reasons must contain the words `homography`, `inliers`, `rotation`,
> `scale`, `spread`. Use `geometry.similarity_params(H)`.

```bash
python3 matching.py otherdate
```

In the demo the expected rotation and scale come from `truth.json`. In NAVERA they come from the IMU
heading and from the height and the camera's field of view (lesson 17).

## Step 11 — Measure and write the analysis

```bash
python3 experiments.py
```

It takes about 30 s and saves `results.json`: the N table, a Monte Carlo test of the N formula,
the normalisation experiment, OpenCV vs yours on the four pairs (with your trust gates), and a sweep
of the ratio from 0.6 to 1.0 on `otherdate`.

> [!TASK]
> Fill in [analysis.md](file:./analysis.md): five sections (**Ratio test**, **Normalisation**,
> **RANSAC iterations**, **OpenCV vs mine**, **Trust gates**), each at least 40 words of your own,
> using the numbers of your `results.json`. The section *RANSAC iterations* must quote N for
> p = 0.99, w = 0.5 with s = 4 and s = 2. Delete the `>` prompt lines.

## Step 12 — The same in NAVERA

```bash
grep -n "ratio\|RANSAC\|min_inliers\|scale_tol\|heading_tol\|def inlier_spread\|def fix_sigma_m" ~/navera/day_pkg/day_pkg/local_matcher.py
```

```bash
grep -n "min_spread\|gate_k\|strong_inliers" ~/navera/day_pkg/day_pkg/vision_nav.py
```

Open [local_matcher.py](file:navera/day_pkg/day_pkg/local_matcher.py) and read `locate()` from
`idx, val = self._knn2(dq, dm)` to the end. Find: the ratio 0.8, the similarity model with
`ransacReprojThreshold=self.ransac_px` (6 px), `maxIters=5000`, `confidence=0.999`, the three
refusals, and `fix_sigma_m`. Which of your gates live in `vision_nav.py` instead?

## Step 13 — Check your work

Press **✔ Check my work**. It tests every function on hand-made cases (exact matrices, a pair at
global coordinates, 30 % outliers), runs your matcher on the real pairs, and reads `results.json`
and `analysis.md`. The whole check takes about 20 s.

## Going further (optional)

- **Similarity RANSAC.** Write `ransac_similarity(src, dst)`: a similarity from 2 pairs has a
  closed form (treat points as complex numbers: z' = a·z + b, with a = (u₁ − u₂)/(z₁ − z₂)). Compare
  the number of samples and the inliers with your homography RANSAC on `otherdate`, and with
  `cv2.estimateAffinePartial2D`.
- **Better RANSAC.** Try `cv2.findHomography(src, dst, cv2.USAC_MAGSAC, 5.0)` on `otherdate` and
  `olives`. MAGSAC++ does not need a hard threshold. Does it change the inliers or the centre error?
- **Threshold study.** Run your RANSAC on `synthetic_pairs(noise_px=2.0)` with thresholds 1, 2, 5, 10,
  20 px. Plot (matplotlib, save a PNG) the share of true inliers found and the H error. Where is
  2.45 σ on your plot?
- **Your own pair.** `navmap.py` (lesson 7's helpers) is here: cut a patch with
  `navmap.map_patch(lat, lon, 18, 800, 800)`, make a view with `cv2.getRotationMatrix2D` +
  `cv2.warpAffine`, and test your matcher on farms (35.9389, 10.4590) or hills (35.80, 10.3711).
