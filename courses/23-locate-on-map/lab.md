# Lab 23 — Find the tile, then the metre

**Goal:** locate 80 drone photos on the map of Sousse. Run a pretrained network (DINOv2) as a finder and measure it
against two baselines that use no picture; train your own finder and compare; then turn the best candidates into
exact latitudes and longitudes with OpenCV, decide when the finder is worth running, and evaluate your whole chain.
**Time:** 5 h 30 to 8 h in two sessions (more if PyTorch is still new; GPU trainings wait for a free slot).
**Fast track:** write the TODOs from their docstrings without the 🧰 and "Stuck?" boxes, then do "Going further".

Your files (📝 Code tab): [navera_lite/retrieval.py](file:./navera_lite/retrieval.py) (**your code**: TODO 1, 2, 4,
5), [navera_lite/locate.py](file:./navera_lite/locate.py) (**your code**: TODO 3, 6, 7, 8, 9),
[answers.py](file:./answers.py), and the ready-made runner [run_locate.py](file:./run_locate.py) (you don't edit it).
`python3 run_locate.py test` tries every docstring example and names the symptom of a wrong result.

The data is in `/data/academy/23-locate-on-map/` (read only): 80 photos of 640 × 480 pixels drawn from the
OpenStreetMap map of Sousse, Tunisia (NAVERA's test area; map data © OpenStreetMap contributors) with camera effects,
made by us so that we know the exact truth; `photos.csv` (height, heading, field of view, terrain, and a prior of
σ 200 m for each photo), `truth.csv`, and the DINOv2 embeddings of the 2 208 map tiles of the test area. DINOv2's
code and weights (Meta AI, Apache-2.0) are in `/data/models/dinov2/`.

| Lesson | Lab | You write |
|---|---|---|
| §1 two scales | Step 0 | (a prediction) |
| §3 DINOv2's input | Steps 1–2 | `preprocess` |
| §2, §4 cosine, honest numbers | Steps 3–6 | `rank`, `evaluate` |
| §6 your network | Steps 7–10 | `TileNet`, `info_nce` |
| (cost) | Step 11 | (a decision) |
| §5 the circle | Step 12 | `search_radius` |
| §7 the gates | Step 13 | `place` |
| §8 when to retrieve | Step 14 | `locate` |
| §9 the budget | Steps 15–16 | `budget` |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is never marked
> right or wrong; being wrong and finding out why is the point.

## Session 1 — Finder (3 h to 4 h 30)

## Step 0 — Look

```bash
python3 run_locate.py look
```

Open `out/look.png`: a photo, the same photo turned north-up at the map's scale, and the 9 map tiles around it.

> [!TASK]
> Find the photo on the tiles by eye. **Predict** (`PREDICT_LOOK`): how many tiles does it cover? Will a method that
> compares the view with **whole tiles** find the right one, and how far from the truth can the right tile's centre be?
> Save (`Ctrl+S`), then read lesson Part A.

## Step 1 — DINOv2's input (TODO 1)

Open [navera_lite/retrieval.py](file:./navera_lite/retrieval.py). Each `TODO` keeps its docstring and ends with
`return None   # TODO…`: replace that line with your code. The given functions (`north_up`, `load_dino`,
`embed_dino`, `TileIndex`, …) are for you to read and use.

**TODO 1** `preprocess(views, size=224)`: lesson §3.

<details><summary>🧰 numpy for pictures</summary>

```python
import numpy as np, cv2
img = np.zeros((4, 6, 3), np.uint8); img[..., 2] = 255         # a 4 × 6 picture, pure red in OpenCV's BGR
small = cv2.resize(img, (3, 2), interpolation=cv2.INTER_AREA)  # (width, height) → shape (2, 3, 3)
img[:, :, ::-1][0, 0]                                           # array([255, 0, 0]): the channels reversed
(np.array([[1.0, 2.0, 3.0]]) - np.array([1.0, 1.0, 1.0])) / np.array([1.0, 2.0, 4.0])   # per-channel: [[0, 0.5, 0.5]]
np.zeros((2, 3, 5)).transpose(2, 0, 1).shape                    # (5, 2, 3): the last axis moved to the front
torch.from_numpy(np.zeros((2, 2), np.float32))                  # a tensor that shares the numpy array's memory
```
</details>

```bash
python3 run_locate.py test
```

The TODO 1 line must be ✔ (the others are later TODOs).

<details><summary>Stuck? Hints, one at a time</summary>

1. For each picture: resize to size × size (`cv2.INTER_AREA`), reverse the channels, divide by 255, subtract the mean
   and divide by the std (both in RED, GREEN, BLUE order), move the channels to the front. Then stack and make a
   float32 tensor.
2. "Red ended up in channel 2": you kept BGR. Reverse the last axis (`[:, :, ::-1]`) before normalising.
3. Values of hundreds: the /255 is missing (or comes after the normalisation).
4. Shape (2, 224, 224, 3): the channels must come first, `.transpose(2, 0, 1)` per picture.
5. `TypeError: expected np.ndarray (got …)` or a float64 tensor: make the array `np.float32` before
   `torch.from_numpy`.
</details>

## Step 2 — Embed the photos with DINOv2

> [!TASK]
> First count (`N_PATCHES`): how many 14 × 14 patches does DINOv2 cut from a 224 × 224 picture?

```bash
python3 run_locate.py embed
```

It embeds 4 map tiles with **your** `preprocess` and compares them with the course's index (made with a correct
preprocessing): a wrong input is refused here. Then it embeds the 80 photos' north-up views and saves
`out/dino_queries.npy`. On the GPU: a few seconds (the runner may first wait for a free GPU slot); on the CPU about
2 s per photo.

## Step 3 — Ranking and honest numbers (TODO 2, TODO 3)

**TODO 2** `rank(q, E)` (retrieval.py): lesson §2. **TODO 3** `evaluate(errors_m, wrong_m=50.0)` (locate.py): lesson
§4, with `np.percentile` (linear).

<details><summary>🧰 Sorting and lengths with numpy</summary>

```python
a = np.array([[3.0, 4.0], [1.0, 0.0]])
np.linalg.norm(a, axis=1)                   # array([5., 1.]): the length of each ROW
np.argsort(np.array([0.2, 0.9, 0.5]))       # array([0, 2, 1]): the indices that sort, SMALLEST first
np.argsort(-np.array([0.2, 0.9, 0.5]), kind="stable")   # array([1, 2, 0]): largest first, ties keep their order
[e for e in [3.0, None, 1.0] if e is not None]          # [3.0, 1.0]
```
</details>

```bash
python3 run_locate.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. rank: one dot product per row (`E @ q`), divided by each row's length and by q's length; then the order, largest
   first.
2. "Those are dot products": a cosine divides by BOTH lengths (lesson §2).
3. "The order is the least similar first": `np.argsort` sorts from small to large.
4. evaluate: keep the errors that are not None; availability = kept / all; percentiles of the kept ones only.
5. "p90 = 80 is the nearest sample": write `np.percentile(acc, 90)` (linear), not a sorted index.
6. `ValueError` for an empty list must be raised **before** you divide by its length.
</details>

## Step 4 — Retrieval against the baselines

Read lesson §4 first. Each photo has a prior of σ 200 m: the search circle is 600 m (18 tiles or so). For each photo
the runner asks DINOv2's index for the best tile in the circle (`TileIndex.search`, with your `rank`) and measures the
distance from that tile's centre to the truth, with your `evaluate`.

> [!TASK]
> **Predict** (`PREDICT_DINO`): NAVERA's DINOv2 beat "stay at the prior" by only 38 m on real frames. Here the photos
> are drawn in the map's own style. Will DINOv2 do better or worse than that, relative to the baseline? Why?

```bash
python3 run_locate.py retrieve
```

Open `out/retrieval_dino_csv.png` (the share of photos with an error ≤ x, for each method).

> [!TASK]
> Write `MED_DINO`, `MED_PRIOR`, `MED_RANDOM`, `MED_BEST` (metres, no decimals) and `EXPLAIN_BASELINE`: did DINOv2 beat
> staying at the prior, and by how much compared with the random tile? Why is even the best tile of the circle not
> 0 m away? Look at the p90 column too.

## Step 5 — A worse prior

```bash
python3 run_locate.py retrieve --sigma 800
```

The same photos, with priors of σ 800 m (the drone has flown a long time without a fix): the circle is 1 500 m wide
(about 115 tiles).

> [!TASK]
> Write `MED_DINO_800`, `MED_PRIOR_800` and `EXPLAIN_SIGMA`: when is retrieval worth running, and when is the prior
> already as good? (Lesson §5: how do the two baselines grow with σ?)

## Step 6 — Where and why it fails

Both runs print the median by terrain and two ranges of similarity: when the top tile **is** the best tile of the
circle, and when it is not.

> [!TASK]
> Write `WORST_TERRAIN` (`"textured"`, `"sparse"` or `"sea"`) and `EXPLAIN_SCORE`: can the similarity of the top tile
> tell you that it is the wrong tile? What does that mean for a drone that must never trust a wrong position? Copy a
> sea photo into your folder (`cp /data/academy/23-locate-on-map/photos/p01.jpg out/`) and look at it.

<details><summary>Read this after Step 6: what NAVERA found</summary>
The same overlap: NAVERA's good matches scored 0.942–0.974, its bad ones 0.823–0.972. A similarity tells "how alike",
not "how sure". Over the sea every tile is alike: the ranking is noise. Retrieval can only propose; something
independent must accept or refuse (session 2's gates).
</details>

## Step 7 — Training pairs from the map

Read lesson §6. Your network learns from pairs made from the map itself: no photo, no label to buy.

```bash
python3 run_locate.py pairs
```

```bash
python3 run_locate.py pairs --no-augment
```

Open `out/pairs.png` and `out/pairs_plain.png`: top row = 8 map tiles (anchors), bottom row = a view of a place
inside each one. Read `make_pairs` in retrieval.py.

> [!TASK]
> `EXPLAIN_PAIRS`: why is a view NOT centred on its tile, and what are the black corners, the blur and the clouds for?

## Step 8 — Your network (TODO 4)

**TODO 4** `TileNet`: read the **rule** in its docstring. Before you code, trace the shapes on paper: (N, 3, 64, 64)
→ after conv1 and its pooling → … → after conv4 → after the global average pooling → after fc. Then count the
parameters by hand, block by block (lesson §6's worked example).

> [!TASK]
> Write `N_PARAMS` (weights and biases, all five layers), then code `__init__` and `forward`.

<details><summary>🧰 PyTorch: a mean over some axes</summary>

```python
x = torch.arange(24.0).reshape(1, 2, 3, 4)     # 1 sample, 2 maps of 3 × 4
x.mean(dim=(2, 3))                               # tensor([[ 5.5, 17.5]]): one mean per map → shape (1, 2)
F.max_pool2d(torch.zeros(1, 2, 8, 8), 2).shape   # torch.Size([1, 2, 4, 4])
```
</details>

```bash
python3 run_locate.py test
```

The TODO 4 line must say "sizes follow the rule".

<details><summary>Stuck? Hints, one at a time</summary>

1. `__init__`: `super().__init__()` first; then the four `nn.Conv2d(in, out, 3, padding=1)` (in of each = out of the
   one before) and `nn.Linear(?, DIM)`. What arrives at fc is one number per map of conv4.
2. `forward`: four times "conv, `F.relu`, `F.max_pool2d(…, 2)`", then the mean over the width and height, then fc, then
   `F.normalize(…, dim=1)`.
3. `mat1 and mat2 shapes cannot be multiplied (2x2048 and 128x128)`: you flattened (128 · 4 · 4 = 2 048) instead of
   averaging.
4. Your count is 256 864: the biases are missing; a 3 × 3 filter on c_in maps has 9 · c_in weights plus 1 bias.
</details>

## Step 9 — The loss, then train (TODO 5)

**TODO 5** `info_nce(za, zp, tau=0.1)`: lesson §6. No loop, no `.item()`, no numpy.

<details><summary>🧰 PyTorch: a classification loss</summary>

```python
logits = torch.tensor([[2.0, 0.0, 0.0], [0.0, 0.0, 1.0]])   # 2 rows (samples), 3 possible answers each
right = torch.tensor([0, 2])                                  # the right answer of each row (whole numbers)
F.cross_entropy(logits, right)                                # tensor(0.3955): the mean over the rows of −log(softmax)
torch.arange(4)                                               # tensor([0, 1, 2, 3])
a @ b.T                                                       # (B, D) @ (D, B) → (B, B): every dot product
```
</details>

```bash
python3 run_locate.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Three things: the matrix of every similarity za[i]·zp[j]; divided by tau; and for row i the right answer i.
2. `F.cross_entropy` does the softmax, the −log and the mean for you: what are its two arguments here?
3. 0.5981 instead of 0.5130 on the docstring example: the division by tau is missing.
4. `Expected all tensors to be on the same device`: make the right answers on the device of za (`device=za.device`).
</details>

Then train (about 3 minutes on the GPU, longer if the runner waits for a free slot):

```bash
python3 run_locate.py train
```

It makes 8 000 training pairs (north of the map) and 1 024 validation pairs (south), trains your TileNet with your
`info_nce` (the given `train_tilenet`), saves `my_tiles.pt`, its log `logs/my_tiles.pt.json` (with the weights'
fingerprint), the curves `out/train_my_tiles.png`, and measures retrieval with it on the 80 lab photos at σ 400 m.
Use the GPU: the runner waits for one of the class's three GPU slots (each training takes about 3 minutes, so the
wait is short). This network is too heavy for the CPU: a reduced CPU run took 40 minutes and gave a network that does
not reach the check's bar. Training runs in its own process: do not start a second training (or `embed`, `speed`)
at the same time, your sandbox's memory would not hold both.

> [!TASK]
> Write `MED_MINE_400` (the last line of `train`). Then measure DINOv2 on the same priors:

```bash
python3 run_locate.py retrieve --sigma 400
```

```bash
python3 run_locate.py retrieve --sigma 400 --finder mine
```

> [!TASK]
> Write `MED_DINO_400`. Compare the two tables and the two plots.

## Step 10 — One experiment

A network learns what its data shows it. Choose **one** setting, predict, train `exp.pt`, and compare with
`my_tiles.pt`:

| Flag | What changes |
|---|---|
| `--no-augment` | views without turn, scale, light, blur, clouds or black corners |
| `--shift 0` | every view centred exactly on its tile |
| `--n-train 2000` | a quarter of the pairs |
| `--tau 0.5` | a softer softmax |

> [!TASK]
> **Predict** (`PREDICT_EXPERIMENT`): which flag, and what will happen to the median at σ 400 m? Then train, e.g.:

```bash
python3 run_locate.py train --no-augment --out exp.pt
```

> [!TASK]
> Write `EXP_MEDIAN` (its last line) and `EXPLAIN_EXPERIMENT`: what changed, by how much, and why? Keep the other
> settings as they were: the check compares `logs/exp.pt.json` with `logs/my_tiles.pt.json` and accepts exactly one
> change.

## Step 11 — Cost

```bash
python3 run_locate.py speed
```

> [!TASK]
> Write `MS_DINO`, `MS_MINE` and `EXPLAIN_CHOICE`: which finder would you fly on the drone's Jetson, next to the
> camera, the IMU and the rest of the stack? Accuracy (Steps 4–9) **and** cost.

> [!TIP] 🏅 End of session 1 — Finder
> Press **✔ Check my work**. When checks 1–8 pass, you earn the **Finder** badge. If the class session ends here,
> stop here and read lesson Part B before session 2.

## Session 2 — Locator (2 h 30 to 3 h 30)

## Step 12 — The search circle (TODO 6)

Open [navera_lite/locate.py](file:./navera_lite/locate.py). **TODO 6** `search_radius(sigma_m, k=3.0, r_min_m=80.0,
r_max_m=1500.0)`: lesson §5.

```bash
python3 run_locate.py test
```

<details><summary>Stuck? Hints</summary>

1. k·σ first, then the floor, then the ceiling: `min(max(…), …)`.
2. 360 for σ = 120 but 30 for σ = 10: the floor r_min_m is missing. `math.isfinite` tells a NaN or an infinity.
</details>

## Step 13 — The gates and the centre (TODO 7)

**TODO 7** `place(A, n_inliers, view_shape, x0, y0, z=17, min_inliers=6, scale_tol=0.15)`: lesson §7. Do the
worked example of §7 on paper first.

```bash
python3 run_locate.py test
```

```bash
python3 run_locate.py local p02
```

It runs the given `local_match` (like_map, CLAHE, SIFT, ratio test, RANSAC similarity, your `place`) on photo p02
around a prior of σ 50 m.

> [!TASK]
> Write `LOCAL_ERR_P02` (metres, one decimal). Try `local p01` (a sea photo) and `local p02 --sigma 400`: read the
> reasons.

<details><summary>Stuck? Hints, one at a time</summary>

1. Gate 1, then gate 2, each returning `(None, None, reason)` with the docstring's words; then the centre.
2. The scale is the length of A's first column: `math.hypot(A[0][0], A[1][0])`.
3. The centre ((w − 1)/2, (h − 1)/2, 1) times A gives (u, v) in OpenCV's patch pixels; then
   `pixel_to_latlon(u + 0.5, v + 0.5, z, x0, y0)`.
4. Off by about half a metre: the + 0.5 is missing. `view_shape` may have 3 numbers: `h, w = view_shape[:2]`.
</details>

## Step 14 — The chain, and your rule (TODO 8)

**TODO 8** `locate(photo, meta, prior, finder, cfg=DEFAULTS)`: lesson §8. The least guided TODO: the docstring is the
specification. On paper first: what is computed once; what happens when the radius is small; what happens when it is
large (the finder is called once, then up to k fine steps); what is checked at the very end.

> [!TASK]
> **Predict** (`PREDICT_SWEEP`): below which search radius is the fine step alone good enough?

```bash
python3 run_locate.py sweep
```

It runs your `locate` on the first 20 photos for σ = 50, 100, 200 and 400 m, each twice: with retrieval switched off
("fine only") and always on ("retrieval", with your `my_tiles.pt` as the finder). About 5 minutes: read lesson §9
meanwhile.

> [!TASK]
> Decide `DIRECT_MAX_R_M` (metres): up to this radius your stack searches with the fine step alone; above it, retrieval
> chooses where to look. Write `EXPLAIN_DECISION`: quote the sweep (positions given, wrong ones, seconds per photo).
> `run` (Step 16) and Sim Lite use your value.

<details><summary>Stuck? Hints, one at a time</summary>

1. `r = search_radius(sigma, cfg["k_sigma"], cfg["r_min_m"], cfg["r_max_m"])`, then one `if`.
2. Small radius: one `local_match(photo, meta, prior_lat, prior_lon, r, cfg)`; the finder is not called.
3. Large radius: the view comes from `north_up` with `gsd(...)` (camera.py) and `m_per_px(prior_lat, cfg["z"])`; call
   the finder ONCE; try `local_match` around each candidate's (lat, lon) = (cand[2], cand[3]) with `cfg["tile_r_m"]`;
   stop at the first accepted one.
4. At the end, if there is a position: its distance to the prior (`haversine_m`) above r → refuse it.
5. The sweep stops with "called the finder … times": once per photo in retrieval mode, never in "fine only" mode.
</details>

## Step 15 — The error budget (TODO 9)

**TODO 9** `budget(terms)`: lesson §9.

```bash
python3 run_locate.py test
```

```bash
python3 run_locate.py budget
```

> [!TASK]
> Write `BUDGET_TOTAL` (two decimals).

## Step 16 — The whole chain

```bash
python3 run_locate.py run
```

Your `locate` with your rule on the 80 photos (σ 200 m priors, finder `my_tiles.pt`). Then run `budget` again: it
prints your measured median and p90 next to the budget.

> [!TASK]
> Write `FINAL_AVAIL`, `FINAL_MEDIAN`, `FINAL_P90`, `FINAL_WRONG`, and `EXPLAIN_REFUSED`: pick one refused photo from
> the table, say which gate refused it and why refusing was right.

## Step 17 — Check, then look back

Press **✔ Check my work**. It tests your functions on inputs they have never seen, loads your `my_tiles.pt` safely
(numbers only) and measures it on 40 photos you never saw, and runs your `locate` on hidden photos with its own
finder. When every check passes, you earn the **Locator** badge. Then look back, without the lesson:

1. Explain to a colleague, in three sentences, why NAVERA's DINOv2 barely beat staying put, and what the AI is good
   for after all.
2. Which prediction was the most wrong? What did you assume?
3. Your TileNet was trained and tested on drawn maps. What would you collect to know whether it works on real photos?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **Top k.** `locate` reads `cfg["top_k"]`. In a small script of your own, call it on photos p01–p20 with
  `dict(DEFAULTS, top_k=1)` and `dict(DEFAULTS, top_k=10)` (σ 400 m priors, as `sweep` makes them). More positions, or
  more wrong ones? How much slower?
- **Flatten vs average.** Make a copy of TileNet that flattens instead of averaging (Linear(2048, 128)), train it with
  `train_tilenet` and compare the median at σ 400 m. (Your `my_tiles.pt` must stay the averaging one.)
- **Height ladder.** NAVERA tries several heights when the height is unknown. Run `local_match` with the height
  multiplied by 0.8, 1.0 and 1.25 on a photo and look at the fitted scales.
- **Fly your own parts.** Sim Lite (31) can load `my_tiles.pt`: keep it.
