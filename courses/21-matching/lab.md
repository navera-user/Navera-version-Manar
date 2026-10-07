# Lab 21 — Lay a drone view onto the map

**Goal:** write RANSAC for a line, the ratio test, and a complete matcher that finds how a drone
view is turned, zoomed and placed on a piece of the satellite map — and decides whether to trust it.
**Time:** about 1 h 15.

You work in two files: [ransac_line.py](file:./ransac_line.py) (the warm-up) and
[matching.py](file:./matching.py) (the real thing). The pictures are in `/data/academy/21-matching/`.

## Step 1 — Meet the four pairs

```bash
ls /data/academy/21-matching
```

There are four **pairs**. In each, `patch_<name>.jpg` is a piece of the satellite map (zoom 18,
800 × 800 px, about 0.48 m per pixel) and `view_<name>.jpg` a synthetic "drone view" (480 × 360 px)
of a place inside it — turned, zoomed, blurred, with another brightness, like a real camera would
see it. Because we made them ourselves, we know the exact answer: it is in `truth.json`.

| Pair | What it is | Difficulty |
|---|---|---|
| `city` | Sousse medina, turned 30°, scale 0.8 | easy: thousands of corners |
| `olives` | an olive grove, turned −60°, scale 1.2 | repeated trees: the ratio test matters |
| `otherdate` | a photo from **2022** matched against today's map, turned 120°, scale 1.5 | hard: shadows, new buildings |
| `sea` | open water | impossible — and the matcher must say so |

Copy two pictures into your folder to look at them in the editor:

```bash
cp /data/academy/21-matching/view_otherdate.jpg /data/academy/21-matching/patch_otherdate.jpg .
```

Open `view_otherdate.jpg` and `patch_otherdate.jpg` in the **📝 Code** tab. Can you find the view
on the map by eye? (Hint: turn your head a third of a turn.) Not easy — let's teach the computer.

## Step 2 — Warm-up: RANSAC on a line

Run the warm-up program:

```bash
python3 ransac_line.py
```

It reads 100 points from `points.csv`: 70 lie on the line y = 0.6 x + 12, 30 are random outliers.
The program prints the **least-squares** line through all the points — about y = 0.49 x + 20.3, far
from the truth: the outliers pulled it. Open `line_fit.png` to see it.

Now open [ransac_line.py](file:./ransac_line.py) and find `fit_line_ransac`. The loop that picks
two random points is written for you. Inside it:

- **TODO 1a**: compute the line through points `i` and `j`:
  `slope = (y[j] − y[i]) / (x[j] − x[i])` and `intercept = y[i] − slope × x[i]`.
- **TODO 1b**: `mask` — with numpy, a whole array at once: `np.abs(y - (slope * x + intercept)) < threshold`
  gives `True` for every point close to the line.
- **TODO 1c**: `mask.sum()` counts the `True` values. If it beats `best_count`, remember this mask.
- **TODO 1d**: after the loop, refit with `least_squares_line(pts[best_mask])` and return
  `slope, intercept, best_mask`.

> [!TASK]
> Complete `fit_line_ransac()` in `ransac_line.py`. **Done** when `python3 ransac_line.py` prints a
> RANSAC line close to **y = 0.6 x + 12** with about 70 inliers, and `line_fit.png` shows the outliers
> as red crosses.

```bash
python3 ransac_line.py
```

You should see something like `RANSAC : y = 0.593 x + 12.24 (73 inliers, 27 outliers)`. (A few of
the random outliers happen to fall close to the line: they count as inliers, and that is fine.)

## Step 3 — The ratio test

Open [matching.py](file:./matching.py). At the bottom (below the line) there is `features(img)`:
the SIFT keypoints and descriptors of lesson 20. At the top, `ratio_test(knn_pairs, ratio)`
receives what `BFMatcher.knnMatch(..., k=2)` returns: a list of `[best, second]` pairs.

> [!TASK]
> **TODO 2** — in `ratio_test()`, add `best` to the list `good` only when
> `best.distance < ratio * second.distance`. Use the `ratio` argument, not a fixed 0.8.

Try your function with several ratios on the city pair (one long line — just press ▶ Run):

```bash
python3 -c "import cv2, matching as m; v, p = m.load_pair('city'); _, a = m.features(v); _, b = m.features(p); pairs = cv2.BFMatcher(cv2.NORM_L2).knnMatch(a, b, k=2); print(len(pairs), 'photo keypoints'); [print('ratio', r, '->', len(m.ratio_test(pairs, r)), 'matches kept') for r in (0.6, 0.7, 0.8, 0.9, 1.0)]"
```

With ratio 0.8 about **250** of the 2000 photo keypoints survive. Ratio 1.0 keeps everything
(including all the liars); 0.6 keeps only the most distinctive ones.

## Step 4 — Find the homography

Now the main function, `match_views(view, patch)`. The features and `knnMatch` are already there.
Three small TODOs:

- **TODO 3a**: `good = ratio_test(pairs, ratio)`.
- **TODO 3b**: the (x, y) position of each good match, in the view and on the patch. For a match
  `m`, the view keypoint is `kv[m.queryIdx]` and the patch keypoint `kp[m.trainIdx]`; `.pt` is its
  (x, y). OpenCV wants an array of shape (N, 1, 2):
  `src = np.float32([kv[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)` — write `dst` the same way.
- **TODO 3c**: `H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)`.
  `mask` holds a 1 for every inlier: the function already returns `int(mask.sum())`.

> [!TASK]
> Complete **TODO 3** in `match_views()`. **Done** when `python3 matching.py city` prints about
> 250 good matches and more than 200 RANSAC inliers.

```bash
python3 matching.py city
```

## Step 5 — Rotation, scale and the drone's position

The matrix H alone is just 9 numbers. Let's read it (the course, section 5).

> [!TASK]
> **TODO 4a** — `rotation_and_scale(H)`: return `(rotation_deg, scale)` from the first column of the
> 2 × 2 block: `math.degrees(math.atan2(H[1, 0], H[0, 0]))` and `math.hypot(H[0, 0], H[1, 0])`.
> **TODO 4b** — `where_is_centre(H, view)`: carry the view centre `(w / 2, h / 2)` through H with
> `cv2.perspectiveTransform` (input shape (1, 1, 2)) and return `(x, y)` as two floats.

Run all four pairs:

```bash
python3 matching.py
```

For each pair, compare your rotation, scale and centre with the truth printed next to them. On the
city and the olives you should be within 0.1° and 0.1 %, and the centre within a pixel —
on the map that is **half a metre**. Then open `overlay_city.png`: the program used your H to lay
the view (orange outline) onto the map. If H is right, the streets of the view continue the streets
of the map, without a seam.

Now look at `otherdate`: only about **37** good matches and **19** inliers — against 241 for the
city. The picture is from 2022: other shadows, other cars, a few new buildings. The answer is still
right (about 119° instead of 120°, scale 1.51), but with much less margin. And the `sea` pair: no
keypoints at all, so no homography — the program says so instead of inventing a position.

> [!QUESTION]
> The olive grove gave **more** inliers (327) than the city (241), although olive trees all look
> alike. How can that be? Two clues: the trees are not *exactly* alike (rows, paths, gaps and field
> edges make many of them distinctive — the ratio test removed the truly ambiguous ones), and the
> city view is zoomed **in** (scale 0.8): it shows less ground than the olive view (scale 1.2), so
> there is less of the map to share keypoints with.

## Step 6 — Trust, and a picture of the inliers

> [!TASK]
> **TODO 5** — `trust(H, inliers, expected_scale, min_inliers=8, scale_tol=0.15)`: return `False`
> when there is no H, when there are fewer than `min_inliers` inliers, or when
> `abs(scale / expected_scale - 1)` is bigger than `scale_tol`; otherwise `True`. These are NAVERA's
> own rules (8 inliers, ± 15 %).
> **TODO 6** — `draw_inlier_matches(view, patch, details, path)`: keep the matches of
> `details["good"]` whose `details["mask"]` value is `True`, draw them with `cv2.drawMatches`, save
> the picture with `cv2.imwrite(path, img)` and return `path`. (Use
> `flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS` so that only the matched keypoints appear.)

```bash
python3 matching.py
```

Open `matches_city.png` and `matches_otherdate.png`. Every green line joins a view keypoint to the
map keypoint RANSAC agreed with. On the city, a dense bundle of parallel-looking lines; on the
2022 photo, a thin handful. **That number of lines is your confidence.**

In the demo, the expected scale given to `trust()` comes from `truth.json`. In NAVERA it comes from
the height and the camera's field of view (lesson 17) — no cheating there.

## Step 7 — Find it in NAVERA

The same steps in the real product:

```bash
grep -n "ratio\|RANSAC\|min_inliers\|scale_tol" ~/navera/day_pkg/day_pkg/local_matcher.py
```

Find, in `LocalMatcher.__init__`, the default values `ratio=0.8`, `ransac_px=6.0`, `min_inliers=8`
and `scale_tol=0.15`; in `locate()`, the ratio test, `cv2.estimateAffinePartial2D(... cv2.RANSAC ...)`
and the three refusals. Open [local_matcher.py](file:navera/day_pkg/day_pkg/local_matcher.py) and
read `locate()` from the line `idx, val = self._knn2(dq, dm)` to the end: you can now understand
every line.

## Step 8 — Check your work

Press **✔ Check my work**. The check runs your functions on the four pairs and on a few hand-made
cases (a clear match and an ambiguous one for the ratio test, a matrix with a known rotation). If
something is red, read the hint, fix, save and check again.

## Going further (optional)

- **Stricter or looser.** In `match_views()`, try `ratio=0.9` and `ratio=0.6` on the `otherdate`
  pair (`python3 matching.py otherdate`). How do the good matches and the inliers change? Is the
  answer still right? Put 0.8 back afterwards.
- **NAVERA's model.** Replace `cv2.findHomography(src, dst, cv2.RANSAC, 5.0)` by
  `cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=6.0)` (it returns
  a 2 × 3 matrix: add the row `[0, 0, 1]` with `np.vstack` to make it 3 × 3). Compare the inliers on
  `otherdate`. Which model needs fewer pairs per RANSAC try?
- **Your own pair.** `navmap.py` (lesson 7's helpers) is in your folder:
  `navmap.map_patch(lat, lon, 18, 800, 800)` returns a piece of the map. Cut a view from it with
  `cv2.getRotationMatrix2D` + `cv2.warpAffine`, turn it by an angle of your choice, and check that
  your matcher finds that angle. Try a place on the farms (35.9389, 10.4590) or the hills
  (35.80, 10.3711).
