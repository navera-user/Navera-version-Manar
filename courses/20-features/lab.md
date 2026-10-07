# Lab 20 — Keypoints on the map

**Goal:** detect keypoints with ORB and SIFT, look at their "fingerprints", count them on six kinds
of ground, and write a function that tells how *matchable* a picture is.
**Time:** about 1 hour.

Your pictures are in `/data/academy/20-features/` (read only):

| File | What it is |
|---|---|
| `terrain_city.jpg`, `terrain_olives.jpg`, `terrain_farms.jpg`, `terrain_hills.jpg`, `terrain_coast_water.jpg`, `terrain_sea.jpg` | 512 × 512 patches of the satellite map, zoom 17 (≈ 0.97 m per pixel, ≈ 500 m of ground) |
| `terrain.csv` | one line per patch: file, terrain, lat, lon, zoom, m_per_px, description |
| `drone_city.jpg` | a synthetic drone photo of the medina: turned 35°, another scale, slightly blurred |
| `drone_city_blurry_dark.jpg` | the same photo, very blurred and dark (dusk, shaking camera) |
| `real_aerial_frame.jpeg` | a real aerial photo of a Sousse district (a picture only: the position written in its flight log is **wrong**) |

Your code goes in [features.py](file:./features.py). It has 6 TODOs.

## Step 1 — Look at the pictures

In the terminal, list the dataset:

```bash
ls -l /data/academy/20-features/
```

```bash
cat /data/academy/20-features/terrain.csv
```

Open a few pictures in the editor to see them (the editor shows images): click
**📝 Code**, then open `/data/academy/20-features/terrain_city.jpg` — or simply copy one here:

```bash
cp /data/academy/20-features/terrain_olives.jpg /data/academy/20-features/drone_city.jpg .
```

> [!QUESTION]
> Before measuring anything: which of the six terrains do you think has the most keypoints? The fewest?
> Write your guess down; you will check it in Step 4.

## Step 2 — Detect keypoints (TODO 1)

Run the demo once to see where you start:

```bash
python3 features.py
```

It says `(TODO 1 is not done yet)`. Open [features.py](file:./features.py) and find `detect_keypoints`.

> [!TASK]
> **TODO 1.** Write `detect_keypoints(img, method="ORB", max_points=10000)`:
> 1. If `img` has 3 dimensions (`img.ndim == 3`), convert it to grey with
>    `cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)`; otherwise use it as it is.
> 2. Create the detector: `cv2.ORB_create(nfeatures=max_points)` when `method == "ORB"`,
>    `cv2.SIFT_create(nfeatures=max_points)` when `method == "SIFT"`, and
>    `raise ValueError("...")` for any other name.
> 3. `keypoints, descriptors = detector.detectAndCompute(grey, None)` and return
>    `list(keypoints), descriptors`.

Run the demo again:

```bash
python3 features.py
```

You should see several thousand ORB keypoints and a descriptor array of shape `(N, 32)`. The demo
saved **`keypoints_city.png`** with the 300 strongest ones: open it in the editor. Each circle is a
keypoint; its size is the keypoint's `size`, the line its `angle`.

> [!QUESTION]
> Where are the circles? On roofs, on street corners, in courtyards? Are there any on the big
> straight road on the left?

## Step 3 — Look inside a fingerprint (TODO 6)

The small program `peek.py` uses your `detect_keypoints` and prints the descriptor of the first
keypoint, for ORB and for SIFT:

```bash
python3 peek.py
```

Read the lines `descriptor array shape (…, …)`. The first number is the number of keypoints, the
second the length of **one** descriptor. ORB also shows its descriptor as bits (0 and 1).

> [!TASK]
> **TODO 6.** At the top of `features.py`, set `ORB_BYTES` and `SIFT_LENGTH` to the descriptor lengths
> you just read.

## Step 4 — Count keypoints per terrain (TODOs 2 and 3)

> [!TASK]
> **TODO 2.** `count_keypoints(path, method="SIFT")`: read the picture with `cv2.imread(path)` and
> return how many keypoints `detect_keypoints` finds in it.
>
> **TODO 3.** `keypoints_per_terrain(method="SIFT")`: read `terrain.csv` with `csv.DictReader`
> (lesson 4) and return a dictionary `{terrain: number of keypoints}`, e.g. `{"city": 6600, ...}`.
> The picture of each row is `os.path.join(DATA, row["file"])`.

```bash
python3 features.py
```

The demo prints a little bar chart, from the most textured terrain to the least. Compare it with your
guess from Step 1. Try ORB too:

```bash
python3 -c "from features import *; print(keypoints_per_terrain('ORB'))"
```

> [!QUESTION]
> The olive grove has almost as many keypoints as the city. Look at `terrain_olives.jpg` again:
> why might it still be harder to match than the city? (Hint: the course, "repetitive texture".)

## Step 5 — Blur, darkness and CLAHE

The program `clahe_demo.py` counts the SIFT keypoints of a picture before and after CLAHE (with
NAVERA's settings) and saves both side by side in `clahe_demo.png`:

```bash
python3 clahe_demo.py
```

The blurry, dark drone photo goes from a few dozen keypoints to several hundred. Open
`clahe_demo.png`: on the right, the city appears again. Now the coast:

```bash
python3 clahe_demo.py terrain_coast_water.jpg
```

Many more keypoints too… but look at where they are: on seagrass shadows and ripples of the water.
Would you find them again on a satellite picture taken another day? This is why "more keypoints" is
not always better.

## Step 6 — Spread and matchability (TODOs 4 and 5)

Now the most useful function of the lab: a score that says *before matching* whether a picture is
worth trying.

> [!TASK]
> **TODO 4.** `spread(keypoints, shape, grid=(4, 4), min_per_cell=3)`: cut the picture into
> `columns × rows` cells (`grid = (columns, rows)`, `shape = img.shape`, so `h, w = shape[:2]`).
> For each keypoint `x, y = kp.pt`, its cell is column `int(x / w * columns)` and row
> `int(y / h * rows)` — keep both inside the grid (`min(columns - 1, ...)`). Count the keypoints in
> each cell (a numpy array `np.zeros((rows, columns), int)` is handy), then return the share of cells
> holding at least `min_per_cell` keypoints: a number from 0 to 1.
>
> **TODO 5.** `matchability(img, enough=300)`: detect ORB keypoints with `max_points=500` and return
> `min(1, n / enough) * spread(keypoints, img.shape)` where `n` is the number of keypoints.

Run the demo:

```bash
python3 features.py
```

The end of the output lists the matchability of six pictures. You should get about 1 for the city,
the olives and the clear drone photo, and 0 for the water and the blurry dark photo.

> [!TIP]
> Test a "half and half" picture in Python: `a = city.copy(); a[:, 256:] = sea[:, 256:]`. It has
> plenty of keypoints, but only on one half: your score should be about 0.5. The check tests exactly this.

## Step 7 — Check your work

Press **✔ Check my work**. It tests every TODO with the pictures of the dataset, the half city /
half sea picture, and `keypoints_city.png`. Read the hint of any red line, fix, save, check again.

## Going further (optional)

- **Your own spot.** `my_spot.py` cuts a patch of the real map (`/data/map.mbtiles`, with the
  `navmap.py` helper of lesson 7) anywhere around Sousse and scores it:

  ```bash
  python3 my_spot.py 35.8256 10.6370
  ```

  Try the port, the beach, the salt lake (sebkha) south of Sousse, the A1 motorway… Which places
  would you avoid flying over if you had to navigate by camera?
- **The real photo.** Count the SIFT keypoints of `/data/academy/20-features/real_aerial_frame.jpeg`.
  `count_keypoints` stops at 10 000 (the `max_points` limit), so call
  `detect_keypoints(img, "SIFT", max_points=100000)` directly. The real frame has many more pixels
  (1536 × 730) than a map patch: is it fair to compare raw counts? Compute keypoints *per 10 000
  pixels* instead.
- **Repetition detector.** For each keypoint of the olive grove, find the distance from its SIFT
  descriptor to the *closest other* descriptor of the same picture
  (`cv2.BFMatcher().knnMatch(des, des, k=2)`, use the second neighbour). Compare the median of these
  distances with the city's. A small distance means "I have a twin": that is repetitive texture, and
  it is exactly what the **ratio test** of the next lesson is about.
