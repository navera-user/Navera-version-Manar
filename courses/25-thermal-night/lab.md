# Lab 25 — Night watch, then night navigator

**Goal:** audit a night dataset, compute what a thermal camera covers, prepare night frames and find them with NCC,
guard the fixes with the motion gate; then make your own training pairs from the map, build and train a small
homography network, measure it against NCC in five conditions, sabotage it as LOC-6 did, and fly a night flight.
**Time:** 4 h 30 to 6 h in two sessions (a strong programmer: about 3 h 30). The full training takes under a minute
on the GPU.
**Fast track:** if you know numpy, OpenCV and PyTorch, write the TODOs from the docstrings without the 🧰 and
"Stuck?" boxes, then do "Going further".

Your files (📝 Code tab): [navera_lite/night.py](file:./navera_lite/night.py) (**your code**: TODO 1–6),
[navera_lite/homography_net.py](file:./navera_lite/homography_net.py) (**your code**: TODO 7–11),
[answers.py](file:./answers.py), [report.md](file:./report.md), and the ready-made runner
[run_night.py](file:./run_night.py) (runs your functions on the lab's data and draws them; you don't edit it).
`python3 run_night.py test` tries every docstring example and names the symptom of a wrong result.

The data is in `/data/academy/25-thermal-night/` (read only): squares of ground drawn from OpenStreetMap data of
Sousse, Tunisia (NAVERA's test area; map data © OpenStreetMap contributors), each as a day aerial view and as
thermal-like "temperature" pictures, made by us so that the truth is exact; a simulated night flight; and NAVERA's
night and day replay frames, copied as data.

| Lesson | Lab | You write |
|---|---|---|
| §1 thermal | Steps 0, 2 | (no code) |
| §2 NCC | Steps 1, 6 | `ncc`, `ncc_locate` |
| §3 footprint, coverage | Steps 3–4 | `footprint_m`, `coverage` |
| §4 preparing | Step 5 | `prepare` |
| §5 motion gate | Step 7 | `motion_gate` |
| §6, §8 corners, pairs | Step 8 | `cut_pair` |
| §7 the network | Steps 9–10 | `to_input`, `HomographyNet` |
| §6, §8 H, training | Steps 11–12 | `offsets_to_H`, `train` |
| §9 measuring, limits | Steps 13–15 | (experiments) |
| all | Step 16 | the report |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is never
> marked right or wrong; being wrong and finding out why is the point.

## Session 1 — Night watch (about 2 h 30)

## Step 0 — Look

No code.

```bash
python3 run_night.py look
```

Open `out/look.png` (click it in the file tree; ⟳ to refresh). A is the day aerial view a drone carries as its
reference; B, C, D are the same ground as a thermal-like camera would see it at night, at noon and at dawn
(bright = warm).

> [!TASK]
> **Predict** (`PREDICT_LOOK`): which of B, C, D will be easiest to match with A by comparing pixels, which hardest,
> and why? Save the file (`Ctrl+S`). Then read lesson Part A (§1–§5).

## Step 1 — NCC (TODO 1)

Open [navera_lite/night.py](file:./navera_lite/night.py). Each `TODO` function keeps its docstring and ends with
`return None   # TODO…`: replace that line with your code. The given parts (`min_altitude`, the constants) are for
you to read and use.

**TODO 1** `ncc(a, b)`: lesson §2. Work in float64: uint8 arithmetic wraps around (200 + 100 = 44).

<details><summary>🧰 numpy: means, sums and floats</summary>

```python
import numpy as np
x = np.asarray([[1, 2], [3, 4]], dtype=np.float64)    # a float copy (uint8 would overflow)
x.mean(), (x * x).sum()                                # 2.5, 30.0 — over all the pixels
float(np.float64(0.5))                                 # 0.5 as a Python float
```
</details>

```bash
python3 run_night.py test
```

The three `ncc` lines must be ✔ (the others are later TODOs).

<details><summary>Stuck? Hints, one at a time</summary>

1. Three lines of numpy: subtract each picture's mean; the sum of the products; the square root of the product of the
   two sums of squares. Then the ratio.
2. You get 0.999… or 0.98 instead of 1.0 on the first case: you did not subtract the means (or only one of them).
3. `nan` or `RuntimeWarning: invalid value` on the uniform case: the denominator is 0 — test it (`if den == 0:` or
   `< 1e-12`) and return 0.0 first.
4. `|NCC| > 1`: you divided by the sum of squares, not by its square root.
</details>

## Step 2 — The data auditor (no new code)

NAVERA's replay data has a set of 30 "night" frames and a set of 30 day frames
(`ls /data/academy/25-thermal-night/replay/`). Each set carries labels (`night_labels.csv`, `day_labels.csv`).

> [!TASK]
> **Predict** (`PREDICT_AUDIT`): if the night frames are real thermal pictures, about what NCC do you expect between a
> night frame and the day frame of the same place (lesson §1–§2)?

```bash
python3 run_night.py audit
```

It compares every night frame with every day frame using your `ncc` (on reduced copies) and prints, for each night
frame, the day frame with the best NCC, the best and the second-best score, and the mean brightness. Open
`out/audit.png` (night frame 1, contrast stretched, above its best day match). Compare the labels too:
`head -3 /data/academy/25-thermal-night/replay/*_labels.csv`.

> [!TASK]
> Write `TWIN_OF_NIGHT_01` (a frame number), `AUDIT_BEST_NCC` (the median best NCC, two decimals) and
> `EXPLAIN_AUDIT`: what are the "night" frames really? Give two clues (look at the scores, the shadows, the labels).

<details><summary>Stuck? Hints</summary>

1. The first line of the table: night frame 1, its best day frame, the NCC.
2. Clues: how high is the best NCC compared with the second best and with your prediction? Are there sun shadows in
   `out/audit.png`? Does the place in night frame 1's label match the place of its best day frame's label?
</details>

## Step 3 — Footprint and coverage (TODO 2, TODO 3)

**TODO 2** `footprint_m(alt_m, hfov_deg, vfov_deg)`: lesson §3, the two formulas. **TODO 3**
`coverage(width_m, height_m, heading_deg, ref_m)`: the share of the square covered by the turned rectangle. Choose
your method:

<details><summary>🧰 Method A — a grid of sample points (simple)</summary>

Put a fine grid of points over the square (e.g. 400 × 400), turn each point into the rectangle's own axes, and count
those inside. Pieces you need:

```python
n = 4
s = (np.arange(n) + 0.5) / n * 10.0 - 5.0      # 4 centres of cells over [−5, 5]: [-3.75, -1.25, 1.25, 3.75]
X, Y = np.meshgrid(s, s)                       # two (4, 4) arrays: every (x, y) of the grid
inside = (np.abs(X) <= 2.0) & (np.abs(Y) <= 4.0)
inside.mean()                                  # 0.25: the share of True (here 1 column pair of 4 … in x, all 4 in y)
```
To express a point (x, y) in axes turned by an angle a: u = x·cos a + y·sin a, v = −x·sin a + y·cos a (the sign of a
does not change the area).
</details>

<details><summary>🧰 Method B — exact polygon overlap with OpenCV</summary>

```python
import cv2
sq  = np.float32([[0, 0], [2, 0], [2, 2], [0, 2]])
tri = np.float32([[1, 1], [3, 1], [1, 3]])
area, pts = cv2.intersectConvexConvex(sq, tri)   # 0.5: the area of the overlap (and its corners)
```
The four corners of the turned rectangle (centred on 0): turn (±w/2, ±h/2) by the heading with the matrix
[[cos a, −sin a], [sin a, cos a]] — in order around the rectangle.
</details>

```bash
python3 run_night.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. `footprint_m`: `2 * alt_m * math.tan(math.radians(hfov_deg) / 2)`, and the same with vfov_deg.
2. footprint_m gives (324.0, −1281.1) or other strange numbers: `math.tan` takes radians.
3. coverage gives 1.0 on the docstring example: the rectangle reaches w/2 and h/2 on each side of its centre — compare
   |u| with width_m / 2 and |v| with height_m / 2, not with the full sizes.
4. 0.75 at 0° but 0.78 at 90°: the heading must be turned into radians (`math.radians(heading_deg)`).
</details>

## Step 4 — Coverage and minimum height (no new code)

> [!TASK]
> **Predict** (`PREDICT_FIRST_CAM`): NAVERA's simulator first had a thermal camera of 56.7° × 48°, and its simulated
> drone flies at most 400 m. Could it ever give a night fix (85 % coverage of the 496 m square)?

```bash
python3 run_night.py coverage
```

It prints the lesson camera's coverage at five heights and four headings, then the minimum height of three cameras
(the given `min_altitude`, a bisection with your two functions).

> [!TASK]
> Write `COV_350_30` (three decimals), `MIN_ALT_FIRST_0`, `MIN_ALT_FIRST_45` (whole metres) and `EXPLAIN_COVERAGE`:
> why does 45° need more height than 0°, and what does that mean for the first camera on a drone limited to 400 m?

## Step 5 — Preparing night frames (TODO 4)

**TODO 4** `prepare(frame, alt_m, hfov_deg, vfov_deg, heading_deg, map_m_per_px, out_px, need=MIN_COVERAGE)`:
lesson §4. First the coverage (your two functions, with the square's side out_px · map_m_per_px), then the warp.

<details><summary>🧰 One affine warp with OpenCV</summary>

```python
M = np.float32([[0.5, 0.0, 10.0],          # x_out = 0.5·x_in + 0·y_in + 10
                [0.0, 0.5, 20.0]])         # y_out = 0·x_in + 0.5·y_in + 20
out = cv2.warpAffine(img, M, (64, 64), flags=cv2.INTER_AREA, borderValue=0)   # (width, height) of the output
```
M sends INPUT pixel coordinates to OUTPUT coordinates. For "scale by s then turn": the 2 × 2 part is the product of
the turn and the scale; then choose the last column so that the input centre lands on the output centre
(c_out = A · c_in + t, so t = c_out − A · c_in).
</details>

<details><summary>🧰 Which way to turn (picture coordinates, y down)</summary>

The frame's top points at heading_deg (clockwise from north). In the north-up output, the frame's "up" direction
(0, −1) must become (sin h, −cos h), and its "right" direction (1, 0) must become (cos h, sin h). The matrix whose
columns are these two vectors is the turn.
</details>

```bash
python3 run_night.py test
```

```bash
python3 run_night.py prepare
```

It prepares the 12 frames of a simulated night flight (640 × 512, 75° × 63°) at the reference's 7.75 m per pixel and
draws three of them next to the day reference at their true place: `out/prepared.png`. The roads and field edges of
your prepared frame should line up with the reference's, north up.

> [!TASK]
> Write `REFUSED_FRAME`: the frame `prepare` refused.

<details><summary>Stuck? Hints, one at a time</summary>

1. Plan: `fw, fh = footprint_m(...)`; `cov = coverage(fw, fh, heading_deg, out_px * map_m_per_px)`; if cov < need,
   return (None, cov, a sentence with "fly higher"); else the warp, and return (patch, cov, "ok").
2. Scale: one output pixel is map_m_per_px metres, one frame pixel is fw / w metres along x (and fh / h along y): the
   frame grows by (fw / w) / map_m_per_px.
3. The patch is upside down or mirrored in `out/prepared.png`: check the turn with the 🧰 box: frame "up" → (sin h, −cos h).
4. The test says the centre pixel is not 200: the centre must go to ((out_px − 1)/2, (out_px − 1)/2) — compute t
   with c_in = ((w − 1)/2, (h − 1)/2).
</details>

## Step 6 — Template matching with NCC (TODO 5)

**TODO 5** `ncc_locate(template, search)`: lesson §2, "Template matching".

<details><summary>🧰 cv2.matchTemplate</summary>

```python
search = np.random.default_rng(0).integers(0, 255, (20, 30)).astype(np.uint8)
tpl = search[5:12, 8:17]                                   # 7 rows × 9 columns, top-left at x = 8, y = 5
r = cv2.matchTemplate(search, tpl, cv2.TM_CCOEFF_NORMED)   # (20 − 7 + 1, 30 − 9 + 1) = (14, 22) scores
lo, hi, lo_xy, hi_xy = cv2.minMaxLoc(r)                    # hi ≈ 1.0, hi_xy = (8, 5): (x, y) of the TOP-LEFT corner
```
</details>

```bash
python3 run_night.py test
```

> [!TASK]
> **Predict** (`PREDICT_NCC`): the runner will search the thermal patch's centre in the reference in five
> conditions: day vs day (the same kind of picture), night, the night picture inverted (255 − x), noon, dawn. In
> which will NCC find the right place, in which not, and why?

```bash
python3 run_night.py ncc
```

Open `out/ncc.png`.

> [!TASK]
> Write `NCC_GOOD_SAME`, `NCC_GOOD_NIGHT`, `NCC_GOOD_INVERTED` (shares 0–1, two decimals) and `EXPLAIN_NCC`: why does
> NCC work day vs day but not at night, and why does inverting the night picture not fix it?

<details><summary>Stuck? Hints, one at a time</summary>

1. `cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)`, then `cv2.minMaxLoc`: the 2nd value is the best
   score, the 4th the (x, y) of the best top-left corner.
2. The test says (3.0, 1.0, 1.0): that is the top-left corner. The template's centre is at
   x + (tw − 1)/2; the search area's centre at (sw − 1)/2.
3. (−1.0, 1.0, …) or (1.0, 1.0, …): a sign — dy > 0 means DOWN, like the picture's y.
</details>

<details><summary>Read this after you ran `ncc`: what the table says</summary>
Day vs day, NCC is almost perfect: the same kind of picture up to noise and gain. At night the brightness order of
the materials changes (lesson §1): roads reverse, trees do not, so no gain and no offset map one picture onto the
other; NCC's best place is then often wrong. Inverting helps where the night is a negative of the day (roads, soil),
and hurts where it is not (trees, water). Dawn has almost no contrast: the camera's automatic gain stretches noise.
</details>

## Step 7 — The motion gate (TODO 6)

**TODO 6** `motion_gate(anchor, t_anchor_s, fix, t_s, v_max_mps=V_MAX_MPS, margin_m=GATE_MARGIN_M)`: lesson §5. The
distance is `haversine_m` (mission 06), already imported at the top of night.py. Build the reason with an f-string;
`f"{238.4:.0f}"` gives `'238'`.

```bash
python3 run_night.py test
```

```bash
python3 run_night.py gate
```

A night matcher's fixes on another flight (25 m/s, one every 2 s, no usable frame between 18 and 32 s) go through
your gate; the runner moves the anchor only when your gate accepts.

> [!TASK]
> Write `GATE_REFUSED` (the times, in seconds, of the refused fixes, as a list) and `EXPLAIN_GATE`: why was the fix
> at 8 s refused, why was the one at 32 s accepted, and what happened after it?

<details><summary>Stuck? Hints, one at a time</summary>

1. Three cases: no anchor → (True, "first fix"); jump > reach → (False, "implausible jump … m in … s (max … m)");
   otherwise (True, "ok"). dt = max(0.0, t_s − t_anchor_s).
2. The test expects a refusal at t = 1.0 and you accept: is reach = v_max_mps × dt + margin_m (not v × t_s)? Do you
   use the ARGUMENTS v_max_mps and margin_m (the check changes them)?
3. `haversine_m(anchor[0], anchor[1], fix[0], fix[1])`: latitude first.
</details>

<details><summary>Read this after you ran `gate`: the lock-in</summary>
The fix at 32 s was wrong by about 300 m, but after 14 s without an accepted fix the reach was 450 m: it passed and
became the anchor. Every correct fix after it was then "too far" from that wrong anchor and refused, and the reach
grows by only 30 m/s while the true distance stays about 300 m too large for several frames. A gate that only
compares with its own last decision can lock onto a wrong anchor; NAVERA compares night fixes with the arbiter's
output (the prior) and other sources too (missions 29–30).
</details>

> [!TIP] 🏅 End of session 1 — Night watch
> Press **✔ Check my work**. When checks 1–9 pass (TODO 1–6 and Steps 0–7; the others are session 2), you earn the
> **Night watch** badge. If the class session ends here, stop here, and read lesson Part B before session 2.

## Session 2 — Night navigator (about 2 h 30 to 3 h)

## Step 8 — Making training pairs (TODO 7)

Open [navera_lite/homography_net.py](file:./navera_lite/homography_net.py) and read its first lines (the patch
coordinates and the 4-point label), then `thermal_camera` and `random_pair`: they draw the random numbers and call
your function.

**TODO 7** `cut_pair(ref_scene, thermal_scene, corner_xy, offsets)`: lesson §8, steps 2–4.

<details><summary>🧰 A perspective warp from four corners</summary>

```python
src = np.float32([[10, 10], [50, 12], [52, 48], [8, 50]])   # 4 points of a picture (a quadrilateral)
dst = np.float32([[0, 0], [39, 0], [39, 39], [0, 39]])        # where they must go: the corners of a 40 px square
H = cv2.getPerspectiveTransform(src, dst)                     # the 3 × 3 matrix: src[k] → dst[k]
out = cv2.warpPerspective(img, H, (40, 40))                    # the picture inside src, as a 40 × 40 square
```
Both arrays must be float32, shape (4, 2), in the same corner order.
</details>

```bash
python3 run_night.py test
```

```bash
python3 run_night.py pairs
```

Open `out/pairs.png`: eight pairs, the green outline marks the true place of the thermal patch's corners in the
reference patch.

> [!TASK]
> `EXPLAIN_CORNERS`: what do the 8 numbers of a label mean, and why does the network predict corners rather than the
> 9 entries of H?

<details><summary>Stuck? Hints, one at a time</summary>

1. The square's corners in the scene: `SQUARE + (x0, y0)`; the thermal corners: those + `offsets.reshape(4, 2)`.
2. Two `getPerspectiveTransform`s to `SQUARE` (one from the square, one from the thermal corners), two
   `warpPerspective`s of size (PATCH_PX, PATCH_PX).
3. The test says the thermal patch moved LEFT: you warped from SQUARE to the corners (the inverse), or subtracted the
   offsets.
4. `error: (-215:Assertion failed) src.checkVector(2, CV_32F) == 4`: the points must be `np.float32`, shape (4, 2).
</details>

## Step 9 — The network's input (TODO 8)

**TODO 8** `to_input(pairs, device="cpu")`: lesson §7, "Input normalisation". Torch operations only.

<details><summary>🧰 Statistics per channel in PyTorch</summary>

```python
x = torch.arange(16.0).reshape(1, 2, 2, 4)        # 1 pair, 2 channels of 2 × 4
x.mean(dim=(2, 3), keepdim=True)                  # shape (1, 2, 1, 1): tensor([[[[ 3.5]], [[11.5]]]])
x.std(dim=(2, 3), keepdim=True)                   # each channel's std, same shape (broadcasts against x)
torch.as_tensor(np.zeros((2, 2), np.uint8)).float()   # numpy uint8 → float32 tensor
```
</details>

```bash
python3 run_night.py test
```

> [!TASK]
> `EXPLAIN_NORM`: why is each channel of each pair normalised on its own, and what does the "+ 1.0" protect?

<details><summary>Stuck? Hints</summary>

1. Accept both numpy and tensors: `x = pairs if torch.is_tensor(pairs) else torch.as_tensor(np.asarray(pairs))`, then
   `.to(device).float()`.
2. −1.16 instead of −0.84 on the test: you divided by the std alone — the docstring says (std + 1.0).
</details>

## Step 10 — The network (TODO 9)

> [!TASK]
> **Predict** (`PREDICT_PARAMS`): which layer holds most of the 192 600 parameters? Then count `fc1`'s parameters by
> hand (lesson §7 does `conv3`): `N_PARAMS_FC1`.

**TODO 9** `HomographyNet`: `__init__` (the six layers of the docstring's table, **with those names**: the check
and Sim Lite load your weights into them) and `forward` (the table in order). Mission 21's PatchNet is the same
kind of code; one new piece:

<details><summary>🧰 A loop over layers</summary>

```python
for conv in (self.conv1, self.conv2):      # a tuple of layers: the same three operations for each
    x = F.max_pool2d(F.relu(conv(x)), 2)
```
</details>

```bash
python3 run_night.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. `super().__init__()` first; then `self.conv1 = nn.Conv2d(2, 16, 3, padding=1)` and the five others from the table.
2. `forward`: four times "conv, ReLU, 2 × 2 max-pooling", `x.flatten(1)`, `fc1`, ReLU, `fc2`. No ReLU after fc2.
3. `mat1 and mat2 shapes cannot be multiplied (3x4096 and 1024x128)`: one pooling is missing.
4. Parameters wrong: a layer without its bias, another kernel size, or padding missing.
</details>

## Step 11 — From corners to H, and training (TODO 10, TODO 11)

**TODO 10** `offsets_to_H(offsets, side=PATCH_PX)`: lesson §6 (the 🧰 box of Step 8 has the OpenCV call).

**TODO 11** `train(model, train_x, train_y, val_x, val_y, …)`: the least guided function. Mission 21's `train` had
the same plan; what changes: the loss (mean squared error against offsets / RHO_PX), and the data stays on the CPU:
each **batch** goes through your `to_input` to the device. Write the plan on paper first: once, every epoch, every
batch, after each epoch.

<details><summary>🧰 The mean squared error, and a batch to the GPU</summary>

```python
import torch.nn.functional as F
F.mse_loss(torch.tensor([0.5, -0.5]), torch.tensor([0.25, 0.0]))   # tensor(0.1562) = mean of 0.0625 and 0.25
idx = order[0:4]                                                    # 4 random indices (a CPU tensor)
xb = to_input(train_x[idx], device); yb = train_y[idx].to(device) / RHO_PX
```
</details>

```bash
python3 run_night.py test
```

A quick run first (seconds):

```bash
python3 run_night.py train --n-train 3000 --epochs 3 --out quick.pt
```

The training loss should go down from about 0.21. Then the real training (about 30–60 s on the GPU; if the class's
three GPU slots are busy the runner waits, then uses the CPU; on the CPU use `--device cpu --n-train 3000 --epochs 6`,
about 11 minutes on a busy Jetson, for a weaker network that still passes the check):

```bash
python3 run_night.py train
```

It prints one line per epoch, saves your weights in `my_homography.pt`, the curves in `out/loss_my_homography.png`,
and the median errors on the validation pairs.

> [!TASK]
> Write `VAL_CENTRE_PX` (two decimals, the median centre error of the last line).

<details><summary>Stuck? Hints, one at a time</summary>

1. Once: `torch.Generator().manual_seed(seed)`, `torch.optim.Adam(model.parameters(), lr=lr)`, `history = []`.
   Every epoch: `model.train()`, `order = torch.randperm(n, generator=g)`, then the batches.
2. Every batch: `idx = order[start:start + batch]`; the loss of `model(to_input(train_x[idx], device))` against
   `train_y[idx].to(device) / RHO_PX`; then `opt.zero_grad()`, `loss.backward()`, `opt.step()`; keep `loss.item()`.
3. After the batches: `model.eval()`, `with torch.no_grad():` the loss of each validation batch; the row
   `{"epoch": e, "train_loss": mean, "val_loss": mean}`; append; `if log: log(row)`.
4. The loss stays at about 0.21 (as good as answering 0): `opt.step()` or `zero_grad()` missing, or the targets
   are not divided by RHO_PX; `Expected all tensors to be on the same device`: `.to(device)` on the targets.
5. offsets_to_H gives [[1, 0, −2], [0, 1, 1], …]: the inverse — from the square to the square + offsets.
</details>

## Step 12 — Overfitting, live

> [!TASK]
> **Predict** (`PREDICT_OVERFIT`): with 2 000 pairs from only 6 places and 30 epochs, what will the training loss
> and the validation loss do? Then run (it does not overwrite `my_homography.pt`):

```bash
python3 run_night.py train --scenes 6 --n-train 2000 --epochs 30 --out overfit.pt
```

Open `out/loss_overfit.png` next to `out/loss_my_homography.png`.

> [!TASK]
> `EXPLAIN_OVERFIT`: what did the two losses do with 6 places, and why? At which epoch would you have stopped?

## Step 13 — Learned vs NCC, in five conditions

```bash
python3 run_night.py compare
```

It measures, on validation places, the median centre error and the share within 3 px for: the prior alone, NCC (your
`ncc_locate`), an untrained network (random weights) and yours, at night, at dawn, at noon, over the coast, and with
a prior wrong by up to 26 px (more than the ρ = 16 px of training). Open `out/compare.png`.

> [!TASK]
> Write `NET_NIGHT_PX`, `NCC_NIGHT_PX`, `NET_NOON_PX` (one decimal) and `EXPLAIN_LEARNED`: why does your network win
> at night but not at noon or at dawn? What would you need before trusting it on a real drone?

<details><summary>Read this after you ran `compare`: is that a good result?</summary>
At night your network roughly halves the prior's error and beats NCC by far; at noon and dawn it is no better than
the prior, or worse: it learned the night's relation between materials and nothing else, and it says so with the
same confidence. A one-pass network like this one is coarse (the original HomographyNet's corner error was also about
a third of ρ); NAVERA's STHN refines its corners in several steps. And everything here is a drawing of the map:
real thermal frames, with their own surprises, are the test that counts.
</details>

## Step 14 — Sabotage: LOC-6 in your hands

> [!TASK]
> **Predict** (`PREDICT_STRICT`): the runner saves your weights again under names that start with `module.` (as a
> script that wraps the network would) and loads them with `strict=False` (lesson §9). What median error will this
> network have at night: near your trained network's, near the prior's (about 9.5 px), or much worse? Why?

```bash
python3 run_night.py sabotage
```

> [!TASK]
> Write `MISSING_KEYS` and `EXPLAIN_STRICT`: why is `strict=False` dangerous, and what did NAVERA change after LOC-6
> (lesson, In NAVERA)?

## Step 15 — Fly the night

```bash
python3 run_night.py fly
```

The night flight end to end: each frame is prepared (your `prepare`), the reference patch is cut around the prior,
your network predicts the corners, your `offsets_to_H` and the given `centre_shift` give the correction, and your
motion gate checks the fix. Errors against the true positions, with NCC for comparison.

> [!TASK]
> Write `FLY_MEDIAN_M` (the last line).

## Step 16 — The report

Write [report.md](file:./report.md) (200–500 words, your own words, keep the four headings): the auditor, geometry
and NCC, the learned homography, limits and honesty. Quote your numbers.

> [!TASK]
> report.md has the four headings, at least 200 words, and quotes your `AUDIT_BEST_NCC`, your `MIN_ALT_FIRST_0`, your
> `NCC_GOOD_NIGHT` and your `NET_NIGHT_PX`.

## Step 17 — Check, then look back

Press **✔ Check my work**. It tests your functions on numbers and pictures they have never seen, loads your
`my_homography.pt` safely (numbers only, strictly) and measures it on 512 night pairs from places you never saw: the
median centre error must be 6.5 px or less (the prior alone: about 9.5; a full GPU training: about 3.5). When every
check passes, you earn the **Night navigator** badge. Then look back, without the lesson:

1. Explain to a colleague, in three sentences, what LOC-6 was and why no test caught it for weeks.
2. Which of your predictions was the most wrong? What did you assume?
3. Your network was trained on drawings. What data would you collect to know whether it works on a real thermal
   camera over Sousse?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **Two passes.** Warp the thermal patch with your first H (so it is almost aligned), run the network again, and
  compose the two homographies. Does the night error fall? (This is the idea behind STHN's refinement.)
- **Train for dawn and noon too.** Copy `train_pairs` into your own script and mix night, noon and dawn pairs from
  the training places (`scenes_train.npz` has night only: use `scenes_val.npz`'s first half for training and its
  second half for validation). What happens to the night error?
- **NCC on edges.** Replace both patches by their gradient magnitude (mission 08's Sobel) before `ncc_locate`. Does
  it survive the night better? Why could it?
- **Fly your own parts.** Sim Lite (mission 31) can load `my_homography.pt` for night flights: keep it.
