# Lab 22 — From pairs to a trusted match, then your network as a matcher

**Goal:** write NAVERA Lite's matcher: the ratio test, a similarity and a homography (your own DLT), RANSAC and the
trust gates, measured against the truth and against OpenCV; then match with your own network from mission 21,
**decide** its threshold and when to use it from your measurements, and write the matcher's policy.
**Time:** 5 h to 6 h 30 in two sessions (a strong programmer: about 4 h). Nothing is trained today: every run takes
seconds (the slowest, `envelope`, about a minute).
**Fast track:** if you know least squares and RANSAC, write the TODOs from the docstrings without the 🧰 and "Stuck?"
boxes, then do "Going further".

Your files (📝 Code tab): [navera_lite/match.py](file:./navera_lite/match.py) (**your code**: TODO 1–6),
[navera_lite/learned_match.py](file:./navera_lite/learned_match.py) (**your code**: TODO 7–9),
[answers.py](file:./answers.py), [report.md](file:./report.md), and the ready-made runner
[run_match.py](file:./run_match.py) (runs your functions on the lab's pictures, measures them against the truth and
draws them; you don't edit it). `python3 run_match.py test` tries every docstring example and names the symptom of a
wrong result.

The pictures are in `/data/academy/22-matching/` (read only): map patches and drone photos drawn from OpenStreetMap
data of Sousse, Tunisia (NAVERA's test area; map data © OpenStreetMap contributors), made by us so that we know the
exact truth: `pairs.json` gives, for each photo, the true 3 × 3 matrix from a map pixel to a photo pixel.

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §1 ratio test | Step 1 | `ratio_test` |
| §2 similarity | Step 2 | `fit_similarity` |
| §3 homography, DLT | Step 3 | `dlt_homography` |
| §4 RANSAC | Steps 4–5 | `ransac_iterations`, `ransac` |
| §5 gates | Step 6 | `gates` |
| §6 a learned matcher | Steps 7–8 | `learned_pairs` |
| §7 a threshold | Step 9 | `ratio_curve` + a DECISION |
| §8 envelope, policy | Steps 10–11 | a DECISION + `match_photo` |
| all | Step 12 | the report |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is never
> marked right or wrong. The **DECISIONS** of session 2 are different: they are yours to choose, and the check
> measures them on scenes you never saw.

## Session 1 — Geometer (about 2 h 45)

## Step 0 — Look before you match

No code. Copy the pictures into a folder you can open:

```bash
python3 run_match.py look
```

Click the maps and photos in `look/` (⟳ to refresh). Eight pairs: a city, the same city with a tilted camera, olive
groves (sharp, then shaken by the drone), a harbour, the open sea, a photo taken somewhere else than the drone
believes (`wrong_place`), and a photo taken lower than the altimeter says (`hills`).

> [!TASK]
> **Predict** (`PREDICT_HARDEST`): which pair will be the hardest to match **correctly**, and why? Save (`Ctrl+S`).
> Then read lesson Part A (§1–§5).

## Step 1 — The ratio test (TODO 1)

Open [navera_lite/match.py](file:./navera_lite/match.py). Each `TODO` function keeps its docstring and ends with
`return None   # TODO…`: replace that line with your code. The finished functions (`distance_matrix`,
`similarity_matrix`, `normalise_points`, `fit_model`, `ransac_similarity`) are for you to read and use.

**TODO 1** `ratio_test(dist, ratio=0.8)`: lesson §1. No Python loop is needed over the rows.

<details><summary>🧰 The two smallest values of each row</summary>

```python
d = np.array([[5.0, 1.0, 3.0], [2.0, 9.0, 4.0]])
o = np.argsort(d, axis=1)          # [[1, 2, 0], [0, 2, 1]]: the columns of each row, smallest first
rows = np.arange(len(d))           # [0, 1]
d[rows, o[:, 0]]                   # [1.0, 2.0]: each row's smallest value
d[rows, o[:, 1]]                   # [3.0, 4.0]: each row's second smallest
keep = np.array([True, False])
rows[keep], o[keep, 0]             # [0] and [1]: the kept rows and their best columns
np.column_stack([[0], [1]])        # [[0, 1]]: two columns side by side → shape (K, 2)
```
</details>

```bash
python3 run_match.py test
```

The TODO 1 line must be ✔. Then on the city pair:

```bash
python3 run_match.py ratio
```

It pairs every SIFT point of the map with its nearest photo point, counts the right ones (the truth knows), then
applies your ratio test with 0.6, 0.7, 0.8 and 0.9. Open `out/ratio_city.png`.

> [!TASK]
> Write `PRECISION_NONE`, `KEPT_08`, `PRECISION_08` (from the table) and `EXPLAIN_RATIO`: why does comparing with the
> SECOND-nearest throw out wrong pairs?

<details><summary>Stuck? Hints, one at a time</summary>

1. Sort each row (`np.argsort(dist, axis=1)`), read the best and the second distance of every row, compare
   `best < ratio * second`, and keep the rows where it is True with their best column.
2. Every row kept, even the ties? You compared with `<=`, or with the largest distance: the test is strict, against
   the **second** smallest.
3. `IndexError` with one column: when `dist.shape[1] < 2`, return `np.zeros((0, 2), dtype=int)` first.
4. The right rows but the wrong columns: j is the column of the **smallest** distance, `o[:, 0]`.
</details>

## Step 2 — The similarity (TODO 2)

**TODO 2** `fit_similarity(src, dst)`: lesson §2 — its 🧰 box (a, b instead of s, θ) and the two rows per pair.

<details><summary>🧰 Building a system with two rows per point</summary>

```python
p = np.array([[1.0, 2.0], [3.0, 4.0]])          # two points (x, y)
n = len(p)
A = np.zeros((2 * n, 3))
A[0::2] = np.column_stack([p[:, 0], np.ones(n), np.zeros(n)])   # rows 0, 2, 4…: [x, 1, 0]
A[1::2] = np.column_stack([p[:, 1], np.zeros(n), np.ones(n)])   # rows 1, 3, 5…: [y, 0, 1]
b = np.array([[10.0, 20.0], [30.0, 40.0]]).reshape(-1)          # [10, 20, 30, 40]: x then y of each point
x, *_ = np.linalg.lstsq(A, b, rcond=None)                        # least squares (mission 01)
math.hypot(3.0, 4.0), math.degrees(math.atan2(1.0, 1.0))         # 5.0 and 45.0
```
</details>

```bash
python3 run_match.py test
```

<details><summary>Stuck? Hints, one at a time</summary>

1. Unknowns [a, b, tx, ty]; for each pair the rows [x1, −y1, 1, 0] (= x2) and [y1, x1, 0, 1] (= y2); `lstsq`; then
   s = hypot(a, b), θ = degrees(atan2(b, a)).
2. θ = −90 instead of 90 on the docstring example: a sign in your rows; compare them with the model of lesson §2.
3. θ = 1.5708: radians — `math.degrees`.
4. The ValueError cases: check `len(src) < 2` and "all the src points are the same" (`np.allclose(src, src[0])`)
   **before** solving; `raise ValueError("…")`.
</details>

## Step 3 — The homography: your DLT (TODO 3)

**TODO 3** `dlt_homography(src, dst)`: lesson §3. Normalise with the given `normalise_points`, two rows of A per pair,
the SVD, undo the normalisations, divide by H[2, 2].

<details><summary>🧰 Pairs of points, and the SVD</summary>

```python
for (x, y), (u, v) in zip([[1, 2], [3, 4]], [[5, 6], [7, 8]]):   # walks the two lists side by side
    print(x, y, u, v)                                            # 1 2 5 6, then 3 4 7 8
A = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
U, S, Vt = np.linalg.svd(A)        # S: singular values, largest first; Vt: (3, 3), one unit vector per row
h = Vt[-1]                         # the unit vector that makes ‖A·h‖ smallest
np.abs(A @ h).max() < 1e-12        # True: here A·h = 0 exactly (2 equations, 3 unknowns)
h.reshape(3, 1).shape, np.linalg.inv(np.eye(3))  # reshape a vector; invert a 3 × 3 matrix
```
</details>

```bash
python3 run_match.py test
```

Then fit both models to the pairs the truth calls right, on the sharp city photo and on the tilted one, and compare
with OpenCV:

```bash
python3 run_match.py fit
```

> [!TASK]
> Write `RESID_SIM_TILT`, `RESID_H_TILT` (the median residuals on city_tilt) and `EXPLAIN_DOF`: why can the similarity
> not fit the tilted photo, and what does the homography cost?

<details><summary>Stuck? Hints, one at a time</summary>

1. `sn, T1 = normalise_points(src)`, the same for dst (T2); the rows of lesson §3 with the NORMALISED coordinates;
   `Vt[-1].reshape(3, 3)` is Hn; then `H = np.linalg.inv(T2) @ Hn @ T1`; `return H / H[2, 2]`.
2. The transposed matrix on the docstring example: `reshape(3, 3)` reads row by row — check the order of your 9
   columns (h1 h2 h3 for u, h4 h5 h6 for v, h7 h8 h9 for the bottom row).
3. Exact on the docstring example but the check says "badly scaled": you built A from the raw points, not from `sn`
   and `dn`, or you forgot to undo T1 and T2.
4. Fewer than 4 pairs: `raise ValueError(…)` first.
</details>

## Step 4 — How many samples? (TODO 4)

> [!TASK]
> **Predict** (`PREDICT_ITERS`): with w = 0.2 and p = 0.99, how many samples does a homography need? A guess, before
> you write the code.

**TODO 4** `ransac_iterations(p=0.99, w=0.5, s=2)`: lesson §4's formula, rounded UP, an `int`; w = 1 → 1; w ≤ 0 or
w > 1 → ValueError.

```bash
python3 run_match.py test
```

```bash
python3 run_match.py iters
```

> [!TASK]
> Write `ITERS_SIM_W02` and `ITERS_H_W02` (the w = 0.2 row).

<details><summary>Stuck? Hints</summary>

1. `math.log(1 - p) / math.log(1 - w ** s)`, then `int(math.ceil(…))`.
2. 16 instead of 17 on the docstring example: you rounded down (`int()` alone cuts the decimals).
3. `ZeroDivisionError` or `math domain error` with w = 1: 1 − wˢ = 0 — return 1 before the formula.
</details>

## Step 5 — RANSAC (TODO 5)

**TODO 5** `ransac(src, dst, kind="similarity", thr_px=6.0, iters=100, rng=None)`: the least guided function. Its
docstring lists the rules every RANSAC of the course follows. First, **on paper**: what happens once before the loop,
what happens in each iteration (four things), and what happens after the loop. Then trace by hand the docstring's
example for two iterations: which samples could give 8 inliers, which could give fewer?

<details><summary>🧰 Random samples and boolean masks</summary>

```python
rng = np.random.default_rng(1)
idx = rng.choice(10, 2, replace=False)    # e.g. [4 9]: 2 different indices among 0..9 (rng.choice(n, s, replace=False))
src = np.arange(20.0).reshape(10, 2)
src[idx]                                   # the 2 rows of the sample
err = np.array([0.5, 7.0, 2.0])
inl = err <= 3.0                           # [True, False, True]: a boolean mask
inl.sum(), src[:3][inl]                    # 2, and the rows where the mask is True
best = None
if best is None or inl.sum() > best.sum(): # remember the best mask so far
    best = inl
np.zeros(5, dtype=bool)                    # five False
```
</details>

```bash
python3 run_match.py test
```

```bash
python3 run_match.py ransac
```

It runs your RANSAC on the tilted city pair, first with the number of samples your `ransac_iterations` asks for
(with the share w of right pairs measured from the truth), then with 500 samples, and OpenCV's for comparison.
Open `out/ransac_city_tilt.png`.

> [!TASK]
> Write `CENTRE_ERR_SIM_TILT` and `CENTRE_ERR_H_TILT` (the **500-sample** rows: how far from the truth the model puts
> the photo's centre, in metres).

<details><summary>Read this after you ran `ransac`: the first two rows</summary>
With w = 0.91 the formula asks for 3 and 4 samples, and the homography found only 5 inliers, 82 m off. The formula
promises that one sample is <b>clean</b> (no wrong pair) with probability p; it does not promise that a clean sample is
a <b>good</b> one. Four right pairs bunched together, each with a pixel of noise, give a homography that is wrong
everywhere else. That is why real systems use a margin (NAVERA: up to 5 000 iterations) and refit on all the inliers.
The similarity, with 2 points, is far less sensitive.
</details>

<details><summary>Stuck? Hints, one at a time</summary>

1. Before the loop: `n_min = MIN_SAMPLE[kind]`, a default rng, `best = None`; if there are fewer than `n_min` pairs,
   return `(None, np.zeros(len(src), dtype=bool))`.
2. Each iteration: a sample `idx = rng.choice(len(src), n_min, replace=False)`; `M = fit_model(kind, src[idx],
   dst[idx])`; `None` → `continue` (it still counted); distances between `warp_points(M, src)` and `dst`; the mask
   `err <= thr_px`; keep it if it has MORE inliers than the best so far.
3. After the loop: no best → (None, all False); else `fit_model(kind, src[best], dst[best])` and return it with `best`.
4. The check says "with iters = 1 … the inliers are …": draw the sample with exactly
   `rng.choice(len(src), n_min, replace=False)`, once per iteration, before anything else uses the rng.
5. The inliers are right but the check says M is not the refit: you returned the best SAMPLE's model.
</details>

## Step 6 — The gates (TODO 6)

> [!TASK]
> **Predict** (`PREDICT_GATES`): which of the eight pairs will your gates refuse, and with which reason?

**TODO 6** `gates(fit, inlier_pts, shape, predicted_scale, min_inliers=6, scale_tol=0.15, min_spread=0.25)`: lesson §5,
in the docstring's order. The given `spread` (mission 21) measures the coverage.

```bash
python3 run_match.py test
```

```bash
python3 run_match.py gates
```

Every pair goes through SIFT, your ratio test, your RANSAC and your gates. The column "prototype" is NAVERA's first
rule (≥ 12 inliers, no scale check).

> [!TASK]
> Write `REASON_WRONG_PLACE`, `REASON_HILLS` (your gates' exact words), `PROTOTYPE_WRONG` (the pair the prototype
> accepts at another place) and `EXPLAIN_GATES`: what does the scale gate cost (look at `hills`), and why does NAVERA
> keep it anyway?

<details><summary>Read this after you ran `gates`: wrong altitude</summary>
<code>hills</code> is a right match refused: the photo was taken lower than the altimeter says, so its scale is 40 % off.
NAVERA's report (3 October 2026) measured the same with its SIFT matcher on real aerial frames: with the altitude 40 % wrong (hills), 0 of
33 frames were accepted, until an altitude-uncertainty window (trying several heights) brought it to 27 of 33. A gate
that refuses right matches costs availability; one that accepts a wrong place costs the drone.
</details>

<details><summary>Stuck? Hints</summary>

1. Four `if`s in the docstring's order, each returning `(False, "…")`; at the end `return True, "ok"`.
2. The scale test: `abs(fit[0] / predicted_scale - 1) > scale_tol`.
3. The spread: `spread(inlier_pts, shape, grid=(4, 2), min_per_cell=3) < min_spread`.
4. "fit None (even with few points: the first gate)": test `fit is None` before counting the points.
</details>

> [!TIP] 🏅 End of session 1 — Geometer
> Press **✔ Check my work**. When checks 1–7 pass (TODO 1–6 and Steps 0–6; the others are session 2), you earn the
> **Geometer** badge. If the class session ends here, stop here, and read lesson Part B before session 2.

## Session 2 — Learned matcher (about 2 h 30 to 3 h 30)

## Step 7 — Bring your network

Mission 21 saved your trained network in `~/lessons/21-features/my_desc.pt`. This copies it here, or the course's
network (`ref_desc.pt`, in this folder) if yours is missing:

```bash
test -f ../21-features/my_desc.pt && cp ../21-features/my_desc.pt my_desc.pt || cp ref_desc.pt my_desc.pt
```

```bash
ls -l my_desc.pt
```

About 360 kB of numbers: the 88 896 weights of your PatchNet. The runner and the check load it with
`learned_desc.load_weights` (weights only, never code).

## Step 8 — Your network as a matcher (TODO 7)

Open [navera_lite/learned_match.py](file:./navera_lite/learned_match.py). Read the given functions first: `upright`,
`keypoints`, `patches_at`, and `sift_pairs` (the same job with SIFT: your model for TODO 7).

**TODO 7** `learned_pairs(map_gray, photo_gray, heading_deg, zoom, model, ratio=0.8, max_dist=None)`: lesson §6.
`learned_desc.describe(model, patches)` gives the descriptors.

```bash
python3 run_match.py learned
```

It runs SIFT and your network on the shaken olive grove, and saves `out/learned_olives_shaken.png` and
`out/upright_olives_shaken.png` (the photo as your network sees it). Try `python3 run_match.py learned city` too.

> [!TASK]
> Write `PAIRS_SIFT_SHAKEN` and `PAIRS_LEARNED_SHAKEN` (the "pairs" column).

<details><summary>Stuck? Hints, one at a time</summary>

1. `up, valid, A = upright(photo_gray, heading_deg, zoom)`; `p1 = keypoints(map_gray)`; `p2 = keypoints(up,
   valid=valid)`; the descriptors of `patches_at(map_gray, p1)` and `patches_at(up, p2)`.
2. `d = distance_matrix(d1, d2)`; `m = ratio_test(d, ratio)`; with `max_dist`, keep the rows of m where
   `d[m[:, 0], m[:, 1]] < max_dist`.
3. Pairs found but almost all wrong in the table? The photo points are still in the upright picture:
   `warp_points(np.linalg.inv(A), p2[m[:, 1]])`.
4. Return `(p1[m[:, 0]], …)` as float arrays; with fewer than 2 keypoints on one side, two `np.zeros((0, 2))`.
</details>

## Step 9 — DECISION: your network's threshold (TODO 8)

**TODO 8** `ratio_curve(best, second, correct, ratios)`: lesson §7, the table that decides.

```bash
python3 run_match.py test
```

```bash
python3 run_match.py curve
```

On 12 pairs with the truth (other photos than the check's), it prints three tables: SIFT with the ratio test, your
network with the ratio test, and your network with a distance cut alone (a distance cut is a ratio test against 1:
`ratio_curve(best, 1, …)`). Open `out/curve.png`.

> [!TASK]
> **DECISION.** Choose your network's rule: `LEARNED_RATIO` and `LEARNED_MAX_DIST` (`None` for no distance cut, or a
> number). Write `EXPLAIN_THRESHOLD`: justify it with **your** numbers (precision, right pairs kept) and compare it with
> SIFT's 0.8. The check applies your rule, with your network, to unseen photos: it must keep a clean set (precision ≥
> 0.85) without throwing away most of the right pairs (at least half of what a loose 0.95 finds).

<details><summary>Stuck? Hints</summary>

1. ratio_curve: for each t, `kept = best < t * second` (arrays), `right = kept & correct`; append a dict with the two
   counts as `int` and the precision (`None` when nothing is kept).
2. Deciding: in the table, where does the precision start to fall fast? What does one more step of the ratio buy in
   right pairs, and cost in wrong ones? (lesson §7's worked example)
</details>

## Step 10 — DECISION: where can your network be trusted?

Your network was trained on photo patches turned by at most ±20° and scaled by 0.8–1.25, with blur and noise.

> [!TASK]
> **Predict** (`PREDICT_ENVELOPE`): up to what error of the heading prior will it still match? Will it beat SIFT
> anywhere?

```bash
python3 run_match.py envelope
```

About a minute. Three tables, each cell "inliers verdict": A, the heading prior wrong by 0–90°; B, the zoom prior wrong
by ×1.0–1.45 (a wrong altitude); C, blur and shake. `ok` means accepted by your gates AND right.

> [!TASK]
> **DECISION.** `HEADING_LIMIT_DEG`: your matcher will use the network only when the heading prior's σ is at most this.
> Write `EXPLAIN_ENVELOPE`: where does your network beat SIFT, where does it fail, and what in its training explains
> both?

## Step 11 — Your matcher's policy (TODO 9)

**TODO 9** `match_photo(map_gray, photo_gray, prior, model, cfg)`: lesson §8. Your policy: which matcher first, when
the other, and the gates for each attempt. `cfg` holds your decisions (the runner and the check build it from
`answers.py`). The docstring says what to return.

```bash
python3 run_match.py mission
```

Ten scenes: sharp and shaken, heading known or not, the sea, another place, a wrong altitude. Each line: your answer,
the method, the gates' reason, and the verdict from the truth: **right**, **refused** or **WRONG**.

> [!TASK]
> `mission` shows no WRONG and you understand every refusal. Write `EXPLAIN_POLICY`. The check runs your policy on 13
> unseen scenes: zero wrong positions, at least 7 right.

<details><summary>Stuck? Hints, one at a time</summary>

1. A list of methods to try: `["sift"]`, plus `"learned"` when `prior["heading_deg"] is not None` and
   `prior["heading_sigma_deg"] <= cfg["heading_limit_deg"]` (or the other order: your decision — measure both).
2. For each: the pairs (`sift_pairs(map_gray, photo_gray, SIFT_RATIO)` or your `learned_pairs(…, cfg["learned_ratio"],
   cfg["learned_max_dist"])`), then `fit, inl = ransac_similarity(src, dst, RANSAC_PX, RANSAC_ITERS,
   np.random.default_rng(0))`, then `gates(fit, dst[inl], photo_gray.shape, prior["zoom"])`.
3. Accepted → return the dict at once; otherwise remember it and try the next; after the loop, return the last one with
   `"ok": False` and `"fit": None`.
4. A WRONG line: some attempt was accepted without your gates, or with the wrong `predicted_scale` (it is the prior's
   zoom).
</details>

## Step 12 — The report

Write [report.md](file:./report.md) (200–500 words, your own words, keep the four headings): pairs and models, RANSAC
and the gates, your network as a matcher, your policy. Quote your numbers.

> [!TASK]
> report.md has the four headings, 200–500 words, and quotes your `KEPT_08`, `RESID_H_TILT`, `LEARNED_RATIO` and
> `HEADING_LIMIT_DEG`.

## Step 13 — Check, then look back

Press **✔ Check my work** (about 2 minutes: it runs your matcher with your network on many unseen photos). It tests
your functions on unseen numbers, measures your threshold and your policy on photos you never saw, and loads your
`my_desc.pt` safely (numbers only). When every check passes, you earn the **Matchmaker** badge. Then look back,
without the lesson:

1. Explain to a colleague, in three sentences, why NAVERA's prototype accepted a position 1 097 m off, and what fixed it.
2. Which of your predictions was the most wrong? What did you assume?
3. Your network beat SIFT on shaken olive groves. What would you need to measure before flying it instead of SIFT on a
   real drone?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **Learned first?** Swap the order of your policy (network first when the heading is good). Count right, refused and
  WRONG on `mission`, and the inliers of the accepted matches. Which order would you fly, and why?
- **The homography in RANSAC.** Run `ransac` on `city_tilt` with your homography and the number of samples of the w = 0.2 row of `iters`: how long
  does it take compared with OpenCV's `findHomography`? Where does the time go?
- **A rotation-proof network.** In mission 21's `train`, turn the photo patches by a random multiple of 90°
  (`torch.rot90`) and train again. Copy the new weights here and run `envelope`: did table A change? What did it cost in
  table C?
- **Mutual matching.** Keep a pair only if j's nearest map point is also i (a cross-check). Does it fix the many-to-one
  pairs of `wrong_place` before the gates do?
