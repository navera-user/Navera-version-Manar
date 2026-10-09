# Lab 22 — From a photo to latitude and longitude, with an error budget

**Goal:** build the complete day-vision localisation chain (scale, search patch, matching, RANSAC
similarity, gates, centre → lat/lon), measure two error sources experimentally (wrong height,
tilted camera), evaluate your pipeline and NAVERA's own `LocalMatcher` on the same 13 photos, and
write a short engineering report.
**Time:** 3 h 30 – 4 h for this lab (about 4 h 45 for the whole mission with the lesson).

| File | What you do in it |
|---|---|
| [locate.py](file:./locate.py) | TODOs 1–4: the chain for one photo |
| [budget.py](file:./budget.py) | TODOs 5–8: error-budget formulas, then two experiments |
| [evaluate.py](file:./evaluate.py) | TODOs 9–11: error, percentile, summary; runs both pipelines on all photos |
| [report.md](file:./report.md) | TODO 12: your written analysis (graded) |
| [navmap.py](file:./navmap.py) | map helpers of lesson 7 (`map_patch`, `latlon_to_pixel`, `pixel_to_latlon`, `m_per_px`, `haversine_m`): use, don't change |

The constants at the top of `locate.py` are NAVERA's values: `Z = 17`, `RATIO = 0.8`,
`MIN_INLIERS = 8`, `SCALE_TOL = 0.15`, `RANSAC_PX = 6.0`.

## Step 1 — Meet the data

All the data comes from NAVERA's test map, which covers **Sousse, Tunisia**. List the photos:

```bash
ls /data/academy/22-locate-on-map/photos
```

and read the truth table:

```bash
column -s, -t /data/academy/22-locate-on-map/truth.csv
```

Each row gives the true centre of the photo (`true_lat`, `true_lon`), the height above the ground
(`altitude_m`), the lens (`hfov_deg`), the heading of the photo's top (`heading_deg`), where the
photo comes from (`source`), and the **prior** your code receives (`prior_lat`, `prior_lon`) with
the search radius `search_m` = 300 m. Copy the overview picture here and open it in the editor:

```bash
cp /data/academy/22-locate-on-map/overview.jpg .
```

Then open [overview.jpg](file:./overview.jpg).

How were these photos made? `/data/academy/22-locate-on-map/make_dataset.py` cuts a piece of map
around a chosen point, turns it by the heading, scales it to the camera's GSD, then blurs it,
changes its exposure, adds noise and JPEG artefacts. Because we chose the point, the truth is
**exact** — a real flight log never gives that.

| Photos | Source | What to expect |
|---|---|---|
| p01–p08 | cut from **the map itself** (medina, port, olives, farms, hills…) | easy: the same imagery as the map |
| p09, p10 | **2022** imagery of Kalâa Kebira (another date, other shadows) | harder |
| p11 | **2017** imagery of the same town | much harder |
| p12 | open sea | nothing to match: the right answer is "no fix" |
| p13 | the prior is **1.2 km** off: the true place is not in the searched map | "no fix" too |

> [!QUESTION]
> Before you code: for p13, what is the smallest `search_m` for which the true position is inside
> the search circle? What would that cost in patch area compared with 300 m (course, section 3)?

## Step 2 — Run the demo

```bash
python3 locate.py
```

It says `Not written yet: TODO 1 (photo_m_per_px)`. Normal: the chain is yours to write.

## Step 3 — GSD of the photo (TODO 1)

> [!TASK]
> In `locate.py`, write `photo_m_per_px(width_px, altitude_m, hfov_deg)`: the footprint width
> `2 · h · tan(hfov / 2)` divided by the width in pixels. The angle is in **degrees**.

Test it with the course's example:

```bash
python3 -c "from locate import photo_m_per_px; print(photo_m_per_px(640, 200, 75))"
```

You should see `0.4795…`. A negative or huge number means you forgot `math.radians`.

## Step 4 — The search patch (TODO 2)

> [!TASK]
> Write `build_search_patch(prior_lat, prior_lon, search_m, margin_m, z=Z)`. It returns
> `(patch, (x0, y0), mpp)`: the map square centred on the prior with half-width
> `ceil((search_m + margin_m) / mpp)` pixels, its top-left corner in **global** pixels, and the
> metres per map pixel.

Try it around the old town of Sousse and save the patch:

```bash
python3 -c "import cv2; from locate import build_search_patch; p, o, m = build_search_patch(35.8256, 10.6370, 300, 200); print(p.shape, o, m); cv2.imwrite('patch.png', p)"
```

Expected: `(1034, 1034, 3) (17768139, 13195900) 0.968…` — 500 m / 0.968 m = 516.3, rounded up
to 517 pixels on each side. Open [patch.png](file:./patch.png): the walled medina and the port.

## Step 5 — Ratio test (TODO 3)

`match_features()` already computes SIFT in both images (≤ 1 500 keypoints in the photo, no limit in
the patch). You add the ratio test of lesson 21.

> [!TASK]
> Replace `good = []` by the ratio test: `knnMatch(d1, d2, k=2)`, keep `p[0]` when the pair has two
> elements and `p[0].distance < RATIO * p[1].distance`.

## Step 6 — Similarity, gates, position (TODO 4)

Read the comments of TODO 4 in `locate()` and sections 4–6 of the course. You fit the similarity
with `cv2.estimateAffinePartial2D(..., method=cv2.RANSAC, ...)`, read `s` and `θ` from the first
column of `A`, apply the two gates, and carry the centre to latitude/longitude.

> [!TASK]
> Complete `locate()` so that it returns `accepted=True` with `lat`, `lon`, `inliers`, `scale` and
> `rotation_deg` for a good match, and `accepted=False`, `lat=None` and a `reason` otherwise.

Run the demo on photo p01:

```bash
python3 locate.py
```

Expect about 950 inliers, scale `1.0`, rotation `30.0` (the heading of the photo) and an error
well under a metre, in 1–3 s. Open [locate_demo.png](file:./locate_demo.png): blue = prior and
search circle, green = truth, red = your answer and the photo outline. Now the hard cases. The sea:

```bash
python3 locate.py p12_sea
```

It must say `accepted: False` — calm water has no keypoints. The lost drone:

```bash
python3 locate.py p13_lost
```

The true place is outside the patch; whatever RANSAC fits there must be refused by the gates. And a
photo from another year:

```bash
python3 locate.py p09_kalaa22
```

Only 15–20 inliers instead of hundreds: roofs repainted, shadows elsewhere, cars moved. Just enough.

> [!QUESTION]
> For p13, write down the inliers and the scale your code printed. Which gate refused it? Would
> the other gate alone have been enough?

## Step 7 — The error budget (TODOs 5–8)

Open [budget.py](file:./budget.py). Four small formulas from section 7 of the course:

> [!TASK]
> - **TODO 5** `expected_scale(h_true, h_assumed)` — the scale RANSAC fits when the photo was
>   resized with the wrong height.
> - **TODO 6** `tilt_offset_m(height_m, tilt_deg)` — `h · tan θ`.
> - **TODO 7** `tilt_homography(width, height, hfov_deg, tilt_deg)` — `H = K R K⁻¹`, with the focal
>   length in pixels `f = (width / 2) / tan(hfov / 2)`, `K = [[f, 0, w/2], [0, f, h/2], [0, 0, 1]]`
>   and `R` the rotation by `tilt_deg` about the x axis. A pure rotation of the camera around its
>   lens moves every image point by this homography (lesson 21): it lets you make a "tilted" photo
>   from a straight-down one.
> - **TODO 8** `rss(terms)` and `error_budget(...)` — the four terms in metres (tilt, matcher =
>   pixels × map metres per pixel, lag = speed × lag, map) and `total_m` = their RSS.

Quick tests (the formulas are in the course, §2 and §7a — the course has no 5° example, so the expected values are given just below):

```bash
python3 -c "from budget import *; print(expected_scale(200, 160), tilt_offset_m(200, 5), rss([3, 4]))"
```

You should see `1.25 17.49… 5.0`. Then run the two experiments with **your** `locate()`:

```bash
python3 budget.py
```

It takes about 30 s. Part 1 locates photo p01 with heights from 0.7 × to 1.3 × the truth; part 2
re-renders p01 as if the camera were pitched by 0°, 2°, 5° and 10°, and locates it while believing
it looks straight down. It writes `budget.json` and [tilted_photo.png](file:./tilted_photo.png)
(the 10° photo: notice the trapezoid of black borders). Compare the fitted scale with the expected
one, and the measured error with `h · tan θ`.

> [!QUESTION]
> With a wrong height the error stays under a metre when the photo is accepted. With a tilt it
> grows steadily. Why is one an **availability** problem and the other an **accuracy** problem?

## Step 8 — Evaluate both pipelines (TODOs 9–11)

> [!TASK]
> In `evaluate.py`, write:
> - **TODO 9** `error_m(res, lat_key, lon_key, row)` — `None` for a refused photo, else the haversine
>   distance to the truth. The keys differ: your `locate()` says `"lat"`, NAVERA says `"predicted_lat"`.
> - **TODO 10** `percentile(values, q)` — linear interpolation, like `np.percentile` (course, section 8).
> - **TODO 11** `summarise(errors)` — `n`, `accepted`, `availability`, `median_m`, `p90_m`, `worst_m`,
>   `wrong_accepted` (error > 50 m).

Then run the evaluation:

```bash
python3 evaluate.py
```

It takes about 1 min 30 s: for each of the 13 photos it runs **your** pipeline and NAVERA's
`LocalMatcher`, imported from your NAVERA copy (`~/navera/day_pkg/day_pkg/local_matcher.py`), on the
CPU, with the map tiles saved in the dataset (`images/tile_17_x_y.jpg`, NAVERA's layout). It prints
both results side by side and writes `results.csv`, `results.json` and [errors.png](file:./errors.png).

With a correct solution you should get, for your pipeline, about 10/13 accepted, a median of about
0.3 m and 0 wrong; for `LocalMatcher`, fewer accepted photos with similar errors. Look carefully at
p09 and p10: your pipeline accepts them, NAVERA refuses them (2–5 inliers). Find the reason in the
course ("In NAVERA") — it is a design trade-off, not a bug.

> [!WARNING]
> Is NAVERA's day vision accurate to 30 cm? **No.** Photos p01–p08 are cut from the very imagery you
> match against. The inlier count collapsing on 2022 and 2017 imagery is the real lesson. Real
> flights add lens distortion, haze, blur, tilt and an imperfect height.

## Step 9 — Write the report (TODO 12)

> [!TASK]
> Fill in [report.md](file:./report.md): keep the four headings, replace every `TODO` line, about
> 300 words or more. The check verifies that you quote **your** numbers: your result as `a/13`,
> NAVERA's as `b/13`, your measured error for the 5° tilt and the worked-case total (Bangkok) from `budget.json`
> (one decimal is enough), and that no `TODO` is left.

To print the numbers you need:

```bash
python3 -c "import json; d = json.load(open('results.json')); print(d['student']); print(d['navera'])"
```

```bash
python3 -c "import json; b = json.load(open('budget.json')); print(b['tilt_sweep']); print(b['worked_case'])"
```

## Step 10 — Check your work

Press **✔ Check my work**. It tests every function with known values, runs your `locate()` on the
13 photos (about a minute), and reads `budget.json`, `results.json` and `report.md`. Read the hint of
any red line, fix, re-run the program that writes the file, and check again.

## Going further (optional)

1. **Remove the gates.** Make a copy without the scale gate and with a minimum of 3 inliers:

   ```bash
   sed 's/^MIN_INLIERS = 8 /MIN_INLIERS = 3 /; s/^SCALE_TOL = 0.15 /SCALE_TOL = 100 /' locate.py > locate_nogate.py
   ```

   then locate the 2017 photo and the lost drone with it:

   ```bash
   python3 locate_nogate.py p11_kalaa17
   ```

   ```bash
   python3 locate_nogate.py p13_lost
   ```

   The 2017 photo is now "accepted" with 3 inliers, a scale of about 3.6 and an error of about
   150 m; p13 is still refused, but only because RANSAC found 2 inliers. This is the "prototype, no
   scale check" row of the course.
2. **No height at all.** NAVERA's `locate_any_height()` tries a ladder of heights and measures the
   height from the fitted scale (`h = h_tried × s`). Run it on p01 with no height given:

   ```bash
   python3 -c "import sys, os, cv2; sys.path.insert(0, os.path.expanduser('~/navera/day_pkg')); from day_pkg.local_matcher import LocalMatcher; m = LocalMatcher('/data/academy/22-locate-on-map/images', device='cpu'); r = m.locate_any_height(cv2.imread('/data/academy/22-locate-on-map/photos/p01_medina.jpg'), (35.824881, 10.638330), 300, 75, min_alt_m=60, max_alt_m=600); print(r['accepted'], r.get('altitude_m'), r['heights_tried'], r['inliers'])"
   ```

   (OpenCV may print `WARN … can't open/read file` for map tiles outside the dataset: harmless.)
   The true height is 200 m. How close is the measured one? Why does this search need 15 inliers
   instead of 8?
3. **A bigger search.** Call your `locate()` on p13 with `search_m=1000`. Does it find the drone?
   How long does it take compared with 300 m? Try 1 500 m: in the sandbox (about 1.8 GB of memory)
   the program will probably be **killed** — the patch is 3 500 pixels wide with hundreds of
   thousands of keypoints. This is why NAVERA caches at most 300 features per tile and caps its
   search radius at 1 500 m.
4. **Tidal flats.** Using only formulas: a drone 150 m above the mudflats of the Wadden Sea
   (Netherlands/Germany) with a 90° camera. What is its GSD, the zoom-17 GSD at latitude 53.4°, and the resize factor? Would you
   expect enough features on wet, uniform mudflats (lesson 20)? What does that mean for the
   availability of day vision on a coastal survey there?
