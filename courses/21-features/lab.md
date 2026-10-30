# Lab 21 — Scout the ground, build a detector, train a descriptor

**Goal:** rank terrains by eye, then by measurement; write the Harris detector of NAVERA Lite from its maths and
measure it against OpenCV's ORB and SIFT; compare binary descriptors; then build, train and test your own neural
network that describes ground patches, and measure it against OpenCV.
**Time:** two sessions, lab 3 h 30 (a strong programmer) to 6 h (new to PyTorch, which is expected); with the
lesson, the mission takes 5 h to 8 h. A training run takes 15 s to about a minute on the GPU (longer when classmates
share it; if three are already training, the runner waits for its turn) and about 11 minutes on the Jetson's CPU
(add about 30 minutes in all).
**Fast track:** if you know numpy and PyTorch, write the TODOs from the docstrings without the 🧰 and "Stuck?" boxes,
then do "Going further" and write the results in `LOOK_BACK`.

Your files (📝 Code tab): [navera_lite/features.py](file:./navera_lite/features.py) (**your code**: TODO 1–6),
[navera_lite/learned_desc.py](file:./navera_lite/learned_desc.py) (**your code**: TODO 7–9),
[answers.py](file:./answers.py), and the ready-made runner
[run_features.py](file:./run_features.py) (runs your functions on the lab's pictures and draws them; you don't edit
it). `python3 run_features.py test` tries every docstring example and names the symptom of a wrong result.

The pictures are in `/data/academy/21-features/` (read only): map patches and drone photos drawn from OpenStreetMap
data of Sousse, Tunisia (NAVERA's test area; map data © OpenStreetMap contributors), made by us so that we know the
exact truth, plus two real aerial frames from NAVERA's day-camera test data and 14 336 pairs of patches.

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a ranking |
| §1 gradients | Step 1 | `gradients` |
| §2 structure tensor, Harris | Steps 2–3 | `structure_tensor`, `eigen2`, `harris` |
| §3–§4 scale, repeatability | Step 4 | `repeatability` |
| §6 texture, matchability | Step 5 | (no new code) |
| §5 descriptors | Step 6 | `hamming` |
| §7 the data, tensors and layers | Steps 7–8 | `PatchNet` (sizes from a rule) |
| §8 loss, gradient descent | Steps 9–10 | `triplet_loss`, `train` |
| §9 validation, overfitting | Steps 11–12 | (looking inside, comparing) |
| §7–§9 | Step 13 | your own experiment |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is never
> marked right or wrong; being wrong and finding out why is the point.

## Session 1 — Scout & detector (about 2 h 30 to 3 h 30 with Part A)

## Step 0 — The scout

No code. You are the scout of a survey team: before the drone flies, you say where its camera will find its way.
Open the six map patches (they are also the picture at the top of the lesson):

```bash
mkdir -p look && cp /data/academy/21-features/terrain_*.png look/
```

Click them in the file tree (⟳ to refresh). Each is about 500 m × 500 m of ground: city, olives, fields, saltpans,
coast, sea.

> [!TASK]
> **Predict** (`PREDICT_RANK`): rank the six from the most keypoints to the fewest, and say which one you would
> trust most to be found again on a map. Save the file (`Ctrl+S`). Then read lesson Part A (§1–§6).

## Step 1 — Gradients (TODO 1)

Open [navera_lite/features.py](file:./navera_lite/features.py). Each `TODO` function keeps its docstring and ends
with `return None   # TODO…`: replace that line with your code. The finished functions (`harris_corners`, `detect`,
`clahe`, `warp_points`, `spread`, `matchability`) are for you to read and use.

**TODO 1** `gradients(gray)`: lesson §1, with OpenCV.

<details><summary>🧰 OpenCV's Sobel</summary>

```python
import cv2, numpy as np
img = np.array([[0, 0, 10, 10]] * 3, np.uint8)
cv2.Sobel(img, cv2.CV_32F, 1, 0, ksize=3)     # float32 result; (1, 0) = derivative in x, (0, 1) = in y
# row 1 → [0., 40., 40., 0.]: the raw sums (a step of 10, Sobel weights 1 2 1 → 40). Divide by 8 for the course rule.
```
</details>

```bash
python3 run_features.py test
```

The TODO 1 line must be ✔ (the others are later TODOs).

<details><summary>Stuck? Hints, one at a time</summary>

1. Two calls to `cv2.Sobel`, one with (1, 0), one with (0, 1); both with `cv2.CV_32F` and `ksize=3`.
2. [0, 24, 24, 24, 24, 0] instead of [0, 3, 3, 3, 3, 0]: the raw sums are 8 times the slope — divide by 8.
3. Negative gradients missing (all values ≥ 0), or a uint8 result: the output depth must be `cv2.CV_32F`, not `-1`.
4. The order of the result: `return gx, gy` (x first).
</details>

## Step 2 — The structure tensor and its eigenvalues (TODO 2, TODO 3)

**TODO 2** `structure_tensor(gx, gy, sigma=1.5)`: lesson §2, "In code". **TODO 3** `eigen2(sxx, syy, sxy)`: the 🧰
formula of lesson §2; it must work on plain numbers and on whole arrays (use `np.sqrt`, not `math.sqrt`).

<details><summary>🧰 A Gaussian window with OpenCV</summary>

```python
a = np.zeros((7, 7), np.float32); a[3, 3] = 1.0
b = cv2.GaussianBlur(a, (0, 0), 1.5)     # (0, 0): OpenCV chooses the kernel size from sigma = 1.5
b.sum()                                   # ≈ 1.0 — a weighted average: the weights sum to 1
```
</details>

```bash
python3 run_features.py test
```

```bash
python3 run_features.py house
```

`house` prints Sxx, Syy, Sxy at three points of `house.png` (a synthetic top view of one house: an L-shaped roof with
a courtyard, a garden wall, a water tank, a road; `cp /data/academy/21-features/house.png look/` to see it).

> [!TASK]
> With your `eigen2` (a `python3 -c "…"` line or a small file) and the Harris formula (k = 0.04), classify each point:
> `KIND_1`, `KIND_2`, `KIND_3` (`"flat"`, `"edge"` or `"corner"`), write `R_POINT_3` (no decimals), and `EXPLAIN_EIGEN`:
> what do the two eigenvalues say about a window, and why does Harris not compute them?

<details><summary>Stuck? Hints, one at a time</summary>

1. TODO 2: three products `gx * gx`, `gy * gy`, `gx * gy`, each blurred with `cv2.GaussianBlur(…, (0, 0), sigma)`;
   return the three (sxx, syy, sxy).
2. eigen2(5, 5, 3) gives (6.73, 3.27): under the root you wrote sxy, not sxy². eigen2(400, 0, 0) gives
   (600, −200): it is ((a − c)/2)², not (a − c)².
3. (2, 8) instead of (8, 2): l1 is the larger one — the "+" root first.
4. `TypeError: only size-1 arrays` or `only length-1 arrays`: `math.sqrt` cannot take an array, `np.sqrt` can.
5. `python3 -c "from navera_lite.features import eigen2; print(eigen2(103.1, 103.3, 57.2))"`
</details>

## Step 3 — Harris (TODO 4)

**TODO 4** `harris(gray, k=0.04, sigma=1.5)`: lesson §2, with your TODO 1 and TODO 2. No Python loop over pixels:
numpy works on the whole arrays at once.

```bash
python3 run_features.py test
```

```bash
python3 run_features.py house
```

Open `out/house_corners.png`: the 12 strongest corners (red crosses), found by the given `harris_corners` with your
`harris`. Are they on roof corners, on the wall, on the water tank? Then the city:

```bash
python3 run_features.py corners
```

Open `out/harris_city.png`.

<details><summary>Stuck? Hints, one at a time</summary>

1. R > 0 everywhere, even on the sides of the square? Check the sign: det − k·trace², det = Sxx·Syy − Sxy².
2. `harris_corners` finds nothing on the house: is your R a 2-D array of the picture's shape?
3. Use the parameters: `structure_tensor(gx, gy, sigma)`, and `k` in the formula — the check changes them.
</details>

## Step 4 — Repeatability (TODO 5)

**TODO 5** `repeatability(pts1, pts2, H, shape2, tol_px=3.0)`: lesson §4. Project with the given `warp_points(H,
pts1)`, keep the projections inside picture 2, and find for each the nearest point of picture 2.

<details><summary>🧰 Nearest neighbours with numpy broadcasting</summary>

```python
p = np.array([[0.0, 0.0], [10.0, 0.0]])            # 2 points
q = np.array([[1.0, 0.0], [10.0, 5.0], [9.0, 1.0]]) # 3 points
d = np.hypot(p[:, None, 0] - q[None, :, 0], p[:, None, 1] - q[None, :, 1])   # (2, 3): every distance
d.min(axis=1)                                        # [1.0, 1.414…]: each p's nearest q
(d.min(axis=1) <= 1.2).mean()                        # 0.5: the share of True
```
(`p[:, None, 0]` has shape (2, 1) and `q[None, :, 0]` shape (1, 3): numpy repeats them into (2, 3).)
</details>

> [!TASK]
> **Predict** (`PREDICT_ZOOM`): in a photo **4 times closer** than the map, which detector, Harris, ORB or SIFT, will
> find the fewest of its map points again, and why?

```bash
python3 run_features.py test
```

```bash
python3 run_features.py repeat
```

It measures Harris (yours), ORB and SIFT with 1 000 points each on six photo pairs, and the chance level. Open
`out/repeat.png`.

> [!TASK]
> Write `REP_HARRIS_ROT35`, `REP_HARRIS_ZOOM4`, `REP_SIFT_ZOOM4` and `CHANCE` (two decimals), `WORST_ZOOM4` (the
> worst detector on `city_zoom4`: `"harris"`, `"orb"` or `"sift"`), and `EXPLAIN_SCALE`: why does Harris survive the
> 35° turn but not the 4× zoom, while SIFT survives both?

<details><summary>Read this after you ran `repeat`: what the table says</summary>

- **Harris and the turn:** R depends only on the eigenvalues, so a turn changes nothing. **Harris and the zoom:** its
  window is fixed (1.5 px); 4 times closer it finds the photo's small details (windows, low walls, cars) that the map
  does not have at its pixel size.
- **SIFT** picks a scale per point, so it finds the same structures at both sizes. Why is it *below* Harris after the
  plain 35° turn? Most of its 1 000 strongest points are its finest blobs, the most sensitive to the photo's noise,
  blur and JPEG (measured on this pair: its smallest keypoints repeat 0.69, its mid-size ones 0.84), while Harris's
  corners sit on the drawing's sharp roof corners.
- **ORB at 4×: at chance** (0.07, chance 0.08): its map points are found no more often than random points. Its
  pyramid has 8 levels, 1.2 apart (1.2⁷ ≈ 3.6×): a 4× zoom is beyond what it can bridge from the map side. Harris and
  SIFT stay far above chance on every pair (the map is a clean drawing).
- Repeatable positions are necessary, not sufficient: Harris gives no scale and no direction, so it has no descriptor
  that could be compared across a 4× zoom.
</details>

<details><summary>Stuck? Hints, one at a time</summary>

1. Three parts: `p = warp_points(H, pts1)`; a boolean mask "inside" with `0 ≤ x ≤ w − 1` and `0 ≤ y ≤ h − 1`
   (`h, w = shape2[:2]`); then the 🧰 distances from the inside points to `pts2`.
2. 1/3 instead of 0.5 on the docstring example: (50, 50) is outside the 20 × 20 picture 2 — keep only the inside
   points before you divide.
3. `ValueError: zero-size array` or `nan`: no point inside, or `pts2` empty — return 0.0 first.
4. 0.0 when you expect 0.5: compare with `<= tol_px`, and take the minimum over picture 2's points (axis=1).
</details>

## Step 5 — The scout's terrains (no new code)

```bash
python3 run_features.py terrain
```

It counts SIFT keypoints (with OpenCV's default contrast threshold 0.04, and with NAVERA's 0.02), and computes the
given `matchability` of every terrain, of two drone views of the city (clear, and at dusk with motion blur) and of
the two real frames. Then CLAHE on the dark photo. Open `out/terrains.png` and `out/clahe_dark.png`.

> [!TASK]
> Write `MOST_KEYPOINTS` (a terrain name: `"city"`, `"olives"`…), `SIFT_FIELDS`, `DARK_SIFT_BEFORE`,
> `DARK_SIFT_AFTER` (whole numbers) and `EXPLAIN_TERRAIN`: which terrain fooled your Step 0 ranking, and why do many
> keypoints not mean easy matching? Look at `real_coast.jpg` too (copy it into `look/`): the real sea is not empty.
> Will its keypoints be on the map?

<details><summary>Stuck? Hints</summary>

1. The numbers are in the first column of the table (`SIFT`), not the `SIFT 0.02` one.
2. "Fooled": compare your `PREDICT_RANK` with the SIFT column and the red circles of `out/terrains.png`; then think of lesson §6's three traps and Step 4's
   `olives_rot35_zoom` line (ORB).
</details>

> [!TIP] 🏅 End of session 1 — Corner hunter
> Press **✔ Check my work**. When checks 1–7 pass (TODO 1–5 and Steps 0–5; the others are session 2), you earn the
> **Corner hunter** badge. If the class session ends here, stop here, and read lesson Part B before session 2.

## Session 2 — Learner (about 2 h 30 to 4 h 30 with Part B)

## Step 6 — Binary descriptors (TODO 6)

**TODO 6** `hamming(d1, d2)`: lesson §5 and its 🧰 box. Return a Python `int` (`int(...)`).

```bash
python3 run_features.py test
```

```bash
python3 run_features.py hamming
```

It pairs the ORB keypoints of the map patch and of the photo turned by 35° whose positions match under H, and
compares their descriptors with your `hamming`; then random pairs. Open `out/hamming.png`.

> [!TASK]
> Write `HAMMING_SAME`, `HAMMING_RANDOM` and `EXPLAIN_HAMMING`: why is the random median close to 128, and what does
> the gap between the two allow a matcher to do?

<details><summary>Stuck? Hints</summary>

1. `np.bitwise_xor(a, b)` then `np.unpackbits(…)` then `.sum()`; make both uint8 first (`np.asarray(d, np.uint8)`).
2. 6 instead of 2: you counted the bits that are EQUAL — count the ones of the XOR.
</details>

## Step 7 — Look at the training data

Before building a network, look at what it will learn from:

```bash
python3 run_features.py patches
```

Open `out/patches.png`: 8 training pairs (top: the map patch, middle: the same ground in a drone photo, turned up to
20°, scaled, tilted, blurred, darker or brighter, noisier) and 8 photo patches of other places (bottom): the kind of
impostor the loss must push away. Each patch is 32 × 32 px, about 30 m of ground.

> [!TASK]
> **Predict** (`PREDICT_HARD`): which of the 8 pairs will be hardest for a descriptor to recognise, and why? Which
> impostor of the bottom row looks most like one of the pairs?

## Step 8 — The network (TODO 7)

Open [navera_lite/learned_desc.py](file:./navera_lite/learned_desc.py). Read `to_tensor` first: it turns uint8 patches
into the network's input. Then read the **rule** in `PatchNet`'s docstring: it gives the names, the first block and
how the sizes change from block to block; the other sizes are yours to derive.

> [!TASK]
> **Predict** (`PREDICT_PARAMS`): how many numbers will PatchNet learn, roughly? Write it **before** you work them out.

**On paper first**, like lesson §7's ✏️ check: follow one 1 × 32 × 32 patch through the three blocks (maps × height ×
width after each), then the number that `flatten` gives: that is fc's input size. Then the parameters of each layer
(lesson §7's worked example) and their sum: `N_PARAMS`.

**TODO 7** `PatchNet`: write `__init__` (four layers, with the docstring's **names**: your weights are loaded into
them by the check, mission 22 and Sim Lite) and `forward` (the blocks in order, then fc, then length 1).

<details><summary>🧰 PyTorch: functions without parameters</summary>

```python
import torch, torch.nn.functional as F
x = torch.randn(5, 8, 6, 6)          # 5 samples, 8 maps of 6 × 6
F.relu(x).min()                       # ≥ 0: negatives set to 0
F.max_pool2d(x, 2).shape              # torch.Size([5, 8, 3, 3]): half the width and height
x.flatten(1).shape                    # torch.Size([5, 288]): each sample's maps in one row (8 · 6 · 6)
F.normalize(torch.tensor([[3.0, 4.0]]), dim=1)   # tensor([[0.6, 0.8]]): each row divided by its length
```
</details>

```bash
python3 run_features.py test
```

The TODO 7 line must say the layers `['conv1', 'conv2', 'conv3', 'fc']`, output (2, 64), row lengths 1.0 and "sizes
follow the rule" (it does not tell you the number of parameters: that is your `N_PARAMS`).

<details><summary>Stuck? Hints, one at a time</summary>

1. `__init__`: first `super().__init__()`, then `self.conv1 = nn.Conv2d(1, 16, 3, padding=1)`; conv2 takes conv1's
   maps and doubles them; conv3 the same.
2. `forward`: three times "conv, `F.relu`, `F.max_pool2d(…, 2)`", then `x.flatten(1)`, then `self.fc`, then
   `F.normalize(…, dim=1)`; return it.
3. `mat1 and mat2 shapes cannot be multiplied (2xA and BxC)`: A numbers per patch reached fc, but it was built for B.
   Trace the shapes on paper again: each block halves 32 → 16 → 8 → 4. `(2x256 …)` or another odd size: `padding=1`
   is missing in a conv (each 3 × 3 conv without padding shrinks the picture by 2).
4. "sizes do NOT follow the rule": a layer without its bias, another kernel size, or a wrong number of maps.
5. `cannot assign module before Module.__init__() call`: `super().__init__()` must come first.
</details>

## Step 9 — The loss (TODO 8)

**TODO 8** `triplet_loss(da, dp, margin=0.5)`: lesson §8. Work on the whole batch at once with tensors: no loop, no
`.item()`, no numpy (the loss must keep its gradient).

<details><summary>🧰 PyTorch: all the distances of a batch, and the diagonal</summary>

```python
a = torch.tensor([[0.0, 0.0], [1.0, 0.0]]); b = torch.tensor([[0.0, 1.0], [1.0, 1.0], [3.0, 0.0]])
d = torch.cdist(a, b)                 # (2, 3): d[i, j] = ‖a[i] − b[j]‖ → [[1.0, 1.414, 3.0], [1.414, 1.0, 2.0]]
d.diagonal()                          # tensor([1., 1.]): d[0, 0], d[1, 1]
mask = torch.eye(2, 3, dtype=torch.bool)               # True on the diagonal
d.masked_fill(mask, float("inf")).min(dim=1).values    # tensor([1.414, 1.414]): each row's smallest OFF the diagonal
torch.clamp(torch.tensor([-0.2, 0.3]), min=0)          # tensor([0.0, 0.3]) — max(0, x); F.relu(x) is the same
```
</details>

```bash
python3 run_features.py test
```

If the computer has a GPU, `test` also runs your loss there (the training will).

<details><summary>Stuck? Hints, one at a time</summary>

1. Three quantities for the whole batch: every distance anchor ↔ photo (one matrix), each anchor's distance to ITS
   photo, each anchor's distance to the closest OTHER photo. The 🧰 box has one tool for each.
2. 0.2620 instead of 0.7620 (exactly 0.5 too small): the margin is missing.
3. 0.5000 on the second line: the diagonal was not left out, so d_neg = d_pos and each loss is exactly the margin.
4. `element 0 of tensors does not require grad`: somewhere you left PyTorch (`.item()`, `float()`, numpy, or
   `torch.tensor(...)` of a result).
5. "triplet_loss (GPU)" fails with a device or mask message: a tensor you create (the mask) is on the CPU while the
   distances are on the GPU — create it on the data's device: `torch.eye(len(da), dtype=torch.bool, device=da.device)`.
6. The formula per anchor is max(0, margin + d_pos − d_neg): which 🧰 line gives max(0, ·) for a whole vector?
</details>

## Step 10 — Train it (TODO 9)

**TODO 9** `train(model, train_a, train_p, val_a, val_p, …)`: the least guided function. The docstring is the
specification, including the exact order of the pairs (so that the check can compare your run with its own). First
write, on paper, the plan: what happens once, what happens every epoch, what happens every batch, and what happens
after each epoch to measure the validation loss (without learning: `model.eval()` and `with torch.no_grad():`, in
batches of `batch`, lesson §9 says why). Then code it.

<details><summary>🧰 PyTorch: an optimiser, a random order, and no gradients</summary>

```python
opt = torch.optim.Adam(model.parameters(), lr=1e-3)    # once, before the epochs
g = torch.Generator().manual_seed(0)                   # once, before the epochs
order = torch.randperm(10, generator=g)                # tensor([4, 1, 7, …]): 0..9 shuffled, the same every run
order[0:4], order[4:8], order[8:12]                    # batches of 4 (the last one has only 2)
x[order[0:4]]                                          # those 4 samples of a tensor x
with torch.no_grad():                                  # inside: no gradients are recorded (faster, no learning)
    v = model(x[:4])
loss.item()                                            # a 1-number tensor as a Python float (for the history)
```
(On the GPU, move the order to the data: `order.to(train_a.device)`.)
</details>

A quick run on 512 pairs first (it writes `quick.pt`; a 512-pair network scores about 0.79, below the check's 0.85):

```bash
python3 run_features.py train --n-train 512 --epochs 3 --out quick.pt
```

The training loss should go down. Then the real training, which writes `my_desc.pt` and its log
`logs/my_desc.pt.json` (15 s to about a minute on the GPU; on the CPU add `--device cpu --n-train 4096 --epochs 4`: about
11 minutes on the Jetson's CPU, score about 0.93):

```bash
python3 run_features.py train
```

It prints one line per epoch, saves the curves in `out/loss_my_desc.png`, and the matching score on the validation
pairs. The check measures `my_desc.pt` on pairs you never see, and checks that its fingerprint is the one in
`logs/my_desc.pt.json`: a weights file trained by someone else, or retrained without the runner, does not pass.
If you change `train` after this run (for example after a ✘ of check 11), run `python3 run_features.py train` again:
Steps 11 and 13 compare other runs with this one.

> [!TASK]
> Write `VAL_SCORE_FULL` (three decimals, from the last line).

<details><summary>Stuck? Hints, one at a time</summary>

1. Once: an Adam optimiser on `model.parameters()` with `lr`, ONE seeded `torch.Generator`, an empty `history`.
   Every epoch: `model.train()`, a new `torch.randperm(n, generator=g)`, then ALL the batches of that order.
2. Every batch: `idx = order[start:start + batch]` (skip it if it has fewer than 2 pairs), the loss on
   `model(train_a[idx])` and `model(train_p[idx])`, then the three lines of lesson §8. Keep `loss.item()` in a list.
3. After the batches: `model.eval()`, `with torch.no_grad():` the loss of each validation batch of `batch` pairs (not
   all 2 048 at once: each anchor would then face 2 047 impostors instead of 255, and the loss would not be
   comparable); the row `{"epoch": e, "train_loss": mean, "val_loss": mean}` with Python floats; `history.append(row)`;
   `if log is not None: log(row)`. Epochs are numbered from 1.
4. The training loss moves strangely or the check says your first epoch differs from the specification: is
   `opt.zero_grad()` called before EVERY `backward()` (otherwise the gradients of all earlier batches pile up)? Is a
   new `randperm` drawn each epoch from the SAME generator? Does the loop cover every batch, not only the first?
5. `Expected all tensors to be on the same device`: `order = torch.randperm(...).to(train_a.device)`.
6. `Killed` with no other message, or "out of memory": the computer ran out of memory (classmates are training too).
   Run the command again in a minute, or add `--device cpu --n-train 4096 --epochs 4`.
</details>

## Step 11 — What did it learn? Filters, and overfitting

Every training starts from the same random weights (`--seed`, 0 by default), so the runner can rebuild your
network's start and compare it with the end.

> [!TASK]
> **Predict** (`PREDICT_FILTERS`): which of the four layers will training change the most, and which the least? Will
> conv1's trained 3 × 3 filters look like mission 08's Sobel kernel?

```bash
python3 run_features.py filters
```

It prints how far each layer moved from its start (‖after − before‖ / ‖before‖) and draws conv1's 16 filters before
training, after, and the difference, on one colour scale (`out/filters.png`).

> [!TASK]
> `EXPLAIN_FILTERS`: which layer moved the most and which the least (the printed numbers)? Do conv1's filters look
> different after training? Say honestly what you see. Many random 3 × 3 filters already have a bright side and a dark
> side: why can the network keep almost random first filters and still score so well? Where did it do most of its
> learning?

Now overfitting, live.

> [!TASK]
> **Predict** (`PREDICT_OVERFIT`): with only 300 training pairs and 30 epochs, what will the training loss and the
> validation loss do? Then run (it does not touch `my_desc.pt`):

```bash
python3 run_features.py train --n-train 300 --epochs 30 --out overfit.pt
```

Open `out/loss_overfit.png` next to `out/loss_my_desc.png` (same scale).

> [!TASK]
> `EXPLAIN_OVERFIT`: what happened to the two losses with 300 pairs, and why? (The validation loss may only stop
> falling and stay flat: that is already overfitting, the gap between the two curves is what matters.) At which epoch
> would you have stopped?

## Step 12 — Learned vs OpenCV, and the failures

```bash
python3 run_features.py compare
```

It measures the matching score (lesson §9) on the 2 048 validation pairs for raw pixels, ORB, SIFT, an untrained
PatchNet (random weights) and yours, and saves `out/compare.png` and `out/failures.png`: map patches your network
matched to the wrong photo patch (left: the map, middle: its true photo, right: the one it chose).

> [!TASK]
> Write `SCORE_ORB`, `SCORE_SIFT`, `SCORE_UNTRAINED`, `SCORE_LEARNED` (three decimals), then
> `EXPLAIN_BASELINES`: raw pixels score almost as well as ORB: what does that say about these pairs? And why does an
> untrained network, which sees the same pixels, score *below* raw pixels?
> `EXPLAIN_LEARNED`: why does your network win here, what do its failures have in common, and what would you need to
> measure before trusting it on a real drone?

<details><summary>Read this after you ran `compare`: a fair comparison?</summary>
The descriptors are compared on the same patches, at the same place, nearly upright: the photo patches keep a heading
error of up to ±20° (a matcher turns the photo north-up from the drone's heading first, as mission 08's like_map did),
and ORB and SIFT are computed without their own orientation, like an upright matcher. SIFT was given its best patch
size, chosen on these same validation pairs (8 px of 8, 12, 16, 24, 32): that favours SIFT, so the comparison is
conservative. ORB and SIFT were designed for any picture; your network was trained for <b>this</b> kind of pair: drawn
map views with this blur, these turns and this noise. It wins on its home ground. A real camera brings other light,
seasons, shadows, 3-D buildings and a lens: the honest next step is a test set of real frames.
</details>

## Step 13 — Your experiment

You know the recipe; now change ONE thing and measure what it does. Choose one row, and use one of its values (the
check knows what they give; other values are welcome in Going further):

| `EXPERIMENT` | What you change | Command |
|---|---|---|
| `"margin"` | the triplet margin, 0.5 → 0.2 or 1.0 | `python3 run_features.py train --margin 1.0 --out exp.pt` |
| `"batch"` | the batch size, 256 → 64 or 1 024 (fewer or more impostors per batch) | `… train --batch 64 --out exp.pt` |
| `"pairs"` | the number of training pairs, → 1 024 | `… train --n-train 1024 --out exp.pt` |
| `"negatives"` | every impostor of the batch instead of the hardest one (the course's variant of the loss) | `… train --negatives all --out exp.pt` |
| `"freeze"` | only fc learns: the three conv blocks keep their random start | `… train --train fc --out exp.pt` |

On the CPU, add the same `--device cpu --n-train 4096 --epochs 4` as for `my_desc.pt` (for `"pairs"`, write
`--n-train 1024` instead of 4096): the experiment must differ from your `my_desc.pt` run in that ONE setting, epochs
included.

How large is a difference that means something? The same recipe with another random start:

```bash
python3 run_features.py train --seed 1 --out seed1.pt
```

The difference between `seed1.pt`'s score and `my_desc.pt`'s is your run-to-run noise. (On the CPU, skip this run:
the course measured the noise of the GPU recipe at about ±0.004, scores 0.955–0.963.)

> [!NOTE]
> Compare **scores**, not losses. With another margin or with `--negatives all`, the loss is another function: its
> numbers are not comparable at all. With another `batch` the loss changes meaning too: 64 pairs per batch means 63
> impostors instead of 255, so the hardest one is easier and the loss is smaller **without the network being any
> better** (lesson §9). Look at the loss curves' shape only for `batch` and `pairs`.

> [!TASK]
> Write `EXPERIMENT` and `PREDICT_EXPERIMENT` (will the validation score go up, down or stay the same, and why?)
> **before** you run your command. Then write `EXP_SCORE` (three decimals, the last line of the run) and
> `EXPLAIN_EXPERIMENT`: how did the **score** change compared with `my_desc.pt`, is that larger than your run-to-run
> noise, and what does it tell you about that setting?

## Step 14 — Check, then look back

Press **✔ Check my work**. It tests your functions on pictures and numbers they have never seen, trains a tiny network
with your `train` and compares it with the specification, loads your `my_desc.pt` safely (numbers only), checks its
fingerprint against `logs/my_desc.pt.json`, and measures it on 1 024 patch pairs from places you never saw: it must
reach a matching score of 0.85. When every check passes, you earn the **Learner** badge. Then look back, without the
lesson:

1. Explain to a colleague, in three sentences, why Ingenuity's camera lost its way and what NAVERA does about it.
2. Which of your predictions was the most wrong? What did you assume?
3. Your network beat SIFT on drawn views. What data would you collect to know whether it beats SIFT on a real drone?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **Your own scale test.** Make a fifth pair: `cv2.resize` a terrain patch by 3 (`fx=3, fy=3`, linear) and measure
  Harris and SIFT repeatability. Careful with the pixel centres: x' = 3x + 1, so H = [[3, 0, 1], [0, 3, 1], [0, 0, 1]].
- **Hardest negatives on both sides.** In a copy of `triplet_loss`, also use the hardest impostor among the anchors
  (`torch.cdist(da, da)`, diagonal left out). Does the validation score improve?
- **Rotation.** Turn each validation photo patch by 90° (`np.rot90`) and compare again: which descriptor breaks? Why
  would ORB with its own orientation not break? Then add a random `torch.rot90` to the photo patches in a copy of your
  `train`: does augmentation buy the invariance?
- **A second experiment.** Try another row of Step 13's table, other values (margin 0.05 or 2.0, batch 16, 300
  pairs), or two epochs instead of eight.
- **Fly your own parts.** Mission 22 loads `my_desc.pt` from this folder: keep it.
