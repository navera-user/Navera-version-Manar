# Lab 22 — Find the drone on the map

**Goal:** write the whole day-vision chain — scale, search patch, matching, RANSAC, gates, latitude and
longitude — then measure its error on 13 drone photos whose true position is known exactly.
**Time:** about 1 h 30.

You work in two files: [locate.py](file:./locate.py) (one photo) and [evaluate.py](file:./evaluate.py)
(all the photos). [navmap.py](file:./navmap.py) holds the map helpers of lesson 7 (`map_patch`,
`latlon_to_pixel`, `pixel_to_latlon`, `m_per_px`, `haversine_m`): use them, don't change them.

## Step 1 — Meet the photos

The dataset is in `/data/academy/22-locate-on-map/`. List the photos:

```bash
ls /data/academy/22-locate-on-map/photos
```

and read the truth table:

```bash
column -s, -t /data/academy/22-locate-on-map/truth.csv
```

Each row gives the true centre of the photo (`true_lat`, `true_lon`), the height (`altitude_m`), the
lens (`hfov_deg`), the heading of the photo's top (`heading_deg`), where the photo comes from
(`source`) and the **prior** your code receives (`prior_lat`, `prior_lon`), a few hundred meters from
the truth, with the search radius `search_m` = 300 m.

Copy the overview picture here so you can open it in the editor:

```bash
cp /data/academy/22-locate-on-map/overview.jpg .
```

Open [overview.jpg](file:./overview.jpg). How were these "drone photos" made? By the script
`/data/academy/22-locate-on-map/make_dataset.py`: it cuts a piece of map around a known point, turns
it by the heading, scales it to what the camera would see from that height (lesson 17), then blurs
it, changes its brightness and adds noise and JPEG artefacts. Because we chose the point, we know the
**exact** truth — something a real flight log never gives so easily.

| Photos | Source | What to expect |
|---|---|---|
| p01–p08 | cut from **the map itself** (city, port, olives, farms, hills…) | easy: the same picture as the map |
| p09, p10 | **2022** imagery of Kalâa Kebira (another date, other shadows) | harder |
| p11 | **2017** imagery of the same town | much harder |
| p12 | open sea | nothing to match: the right answer is "no fix" |
| p13 | the prior is **1.2 km** off: the true place is not in the searched map | "no fix" too |

## Step 2 — Run the demo

```bash
python3 locate.py
```

It says `Not written yet: TODO 1 (photo_m_per_px)`. Normal: let's write it.

## Step 3 — The photo's scale (TODO 1)

> [!TASK]
> In `locate.py`, write `photo_m_per_px(width_px, altitude_m, hfov_deg)`: the footprint width
> `2 × altitude × tan(hfov / 2)` divided by the width in pixels. The angle is in **degrees**.

Test it (the course's example):

```bash
python3 -c "from locate import photo_m_per_px; print(photo_m_per_px(640, 200, 75))"
```

You should see `0.4795…`. If you see a negative or huge number, you forgot `math.radians`.

## Step 4 — Cut the map around the prior (TODO 2)

> [!TASK]
> Write `build_search_patch(prior_lat, prior_lon, search_m, margin_m, z=Z)`. It returns
> `(patch, (x0, y0), mpp)`: the map piece centred on the prior, of half-width `search_m + margin_m`
> meters, its top-left corner in global pixels, and the meters per map pixel.

Try it around the old town of Sousse and save the patch:

```bash
python3 -c "import cv2; from locate import build_search_patch; p, o, m = build_search_patch(35.8256, 10.6370, 300, 200); print(p.shape, o, m); cv2.imwrite('patch.png', p)"
```

Expected: `(1034, 1034, 3) (17768139, 13195900) 0.968…`. 500 m / 0.968 m per pixel = 516.3, rounded
up to 517 pixels on each side of the centre. The corner's numbers are big because they are **global**
pixels: counted from the corner of the whole world map at zoom 17 (lesson 7). Open [patch.png](file:./patch.png): the walled medina with the port on the right.

## Step 5 — Matches with the ratio test (TODO 3)

`match_features()` already computes SIFT keypoints in both pictures (up to 1 500 in the photo, no limit
in the map piece, which is much bigger). You add the **ratio test** of lesson 21.

> [!TASK]
> In `match_features()`, replace `good = []` by the ratio test: `knnMatch(d1, d2, k=2)`, and keep
> `p[0]` when `p[0].distance < RATIO * p[1].distance`.

Without the test you would keep all 1 500 photo keypoints, most of them matched to a random look-alike.

## Step 6 — Fit, gates, position (TODO 4)

Now the heart of the chain. Read the comments of TODO 4 in `locate()` and the course section
"Step 5 — From the photo centre to latitude and longitude". In short:

1. `cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, …)` → the matrix `A` and the inliers;
2. read the **scale** and the **rotation** from `A`, count the inliers;
3. the **gates**: at least `MIN_INLIERS` inliers, and `|scale − 1| ≤ SCALE_TOL`; otherwise return the
   result with `accepted=False` and a clear `reason`;
4. the photo centre through `A`, plus `(x0, y0)`, through `navmap.pixel_to_latlon`.

> [!TASK]
> Complete `locate()` so that it returns `accepted=True` with `lat`, `lon`, `inliers`, `scale` and
> `rotation_deg` for a good match, and `accepted=False`, `lat=None` and a `reason` otherwise.

Run the demo on the first photo:

```bash
python3 locate.py
```

You should see about 950 inliers, a scale of `1.0`, a rotation of `30.0` (the photo's heading!) and an
error well under a meter. It takes one or two seconds: SIFT on a 1 000 × 1 000 map piece is real work.
Open [locate_demo.png](file:./locate_demo.png): the blue circle is the search area around the prior
(blue cross), the green ring is the truth, the red outline is where your code placed the photo.

Now the hard ones. The sea:

```bash
python3 locate.py p12_sea
```

It must say `accepted: False` — there is not a single keypoint on calm water. The lost drone:

```bash
python3 locate.py p13_lost
```

The true place is outside the map piece, so RANSAC can only find nonsense: the gates must refuse it.
And a photo from another year:

```bash
python3 locate.py p09_kalaa22
```

Only a handful of inliers this time (around 15–20 instead of hundreds): roofs were repainted, shadows
fall elsewhere, cars moved. It is still enough — just.

> [!QUESTION]
> In `p13_lost`, what would happen without the gates? Look at the inliers and scale your code
> printed, and imagine the autopilot receiving that position.

## Step 7 — Measure honestly (TODO 5 and 6)

> [!TASK]
> In `evaluate.py`, write `error_m(res, row)` (`None` for a refused photo, else the haversine distance
> to the truth in meters) and `median(values)` (`None` for an empty list). Then run the evaluation:

```bash
python3 evaluate.py
```

It locates all 13 photos (about 30 seconds), prints a table, and writes `results.csv` and
[errors.png](file:./errors.png). With a correct solution you should get:

- p01–p08 (cut from the map): all accepted, hundreds of inliers, errors **under half a meter**;
- p09–p10 (2022 imagery): accepted with 15–20 inliers, about 1 m off;
- p11 (2017), p12 (sea), p13 (lost): **no fix**;
- in total 10/13 accepted, a median error of about 0.2–0.3 m, and **no wrong position**.

Now be critical. Is NAVERA's day vision accurate to 30 cm? **No.** Photos p01–p08 are cut from the
very picture we match against: of course they match. Look at how the inlier count collapses when the
photo comes from another date (p09–p11): that, not the 0.3 m, is the lesson. Real flights add a lens,
haze, a tilted camera and an imprecise height. That is why `docs/VALIDATION_STATUS.md` quotes NAVERA's
bench result on real aerial frames from another source (median 4 m, 32/33 within 9 m) and marks the
simulator's ~1 m as **optimistic**: its camera, like our p01–p08, is cut from the map's own imagery.

## Step 8 — Check your work

Press **✔ Check my work**. The check runs your `locate()` on every photo (it takes about a minute), and
tests `photo_m_per_px`, the patch, the ratio test, the rotation and scale, the refusals and your
`results.csv`.

## Going further (optional)

1. **NAVERA's own matcher on your photos.** `compare_navera.py` imports `LocalMatcher` from
   your NAVERA copy (`~/navera/day_pkg/day_pkg/local_matcher.py`) and runs it, on the CPU, on the same
   13 photos, with the map tiles saved in the dataset (`images/tile_17_x_y.jpg`, NAVERA's layout):

   ```bash
   python3 compare_navera.py
   ```

   Compare its table with yours. On these photos NAVERA's SIFT matcher accepts the 8 map-cut photos
   with the same sub-meter error, but **refuses** the 2022 photos (2–5 inliers). Why? It keeps only 300
   keypoints per map tile (to stay fast in flight), you kept them all. Speed against sensitivity is a
   real engineering trade-off; on the Jetson, NAVERA's default is the learned matcher (DISK + LightGlue)
   precisely because it does better on such cross-date photos.
2. **Remove a gate.** Make a copy without the scale gate and with a minimum of 3 inliers:

   ```bash
   sed 's/^MIN_INLIERS = 8 /MIN_INLIERS = 3 /; s/^SCALE_TOL = 0.15 /SCALE_TOL = 100 /' locate.py > locate_nogate.py
   ```

   then locate the 2017 photo with it:

   ```bash
   python3 locate_nogate.py p11_kalaa17
   ```

   Look at the scale it accepts, and at the error. This is exactly the "prototype, no scale check" row
   of the course.
3. **A bigger search.** The prior of `p13_lost` is 1.2 km off. Write a small script that calls
   `locate()` on that photo with `search_m=1000` (the square map piece then reaches the true place).
   Does it find the drone? How long does it take compared with `search_m=300`? Try 1500 too: in your
   sandbox (1.8 GB of memory) the program is probably **killed** — the map piece is 3 500 pixels wide
   and holds hundreds of thousands of keypoints. Time, memory and the risk of look-alikes all grow
   with the search area: that is why NAVERA caps its search circle at 1 500 m and keeps only 300
   keypoints per tile.
