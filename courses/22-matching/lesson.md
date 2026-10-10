# Matching and geometry: ratio test, DLT and RANSAC

> [!NOTE] In short
> - When GPS is jammed, NAVERA must find which frame keypoints match which map keypoints, and how
>   the frame lies on the map.
> - The **ratio test** keeps a match only when the best map descriptor is clearly better than the
>   second best.
> - The **DLT** computes a homography from point pairs, and **RANSAC** finds the right one even
>   when many pairs are wrong.
> - **Trust gates** (inliers, rotation, scale, spread, prediction) stop NAVERA from believing a
>   wrong place.
> - In the lab you write your own DLT and RANSAC with NumPy, compare them with OpenCV, and apply
>   NAVERA's trust gates.
> - NAVERA's `LocalMatcher.locate()` uses the same ratio test (0.8) and RANSAC.

⏱ Core reading ~16 min · optional deep-dives marked *Going further*.

A survey drone flies along a coast at 300 m. Ships and aircraft in the Baltic Sea and the eastern
Mediterranean regularly report **GNSS interference**, and today the drone's GPS receiver
shows nonsense. The camera still works. NAVERA has the satellite map on board, and lesson 21 gave
you keypoints and descriptors in both the camera frame and the map. Two questions remain:

1. **Correspondence:** which keypoint of the frame is the same ground point as which keypoint of the map?
2. **Geometry:** given those pairs — many of them wrong — what is the exact transformation that lays
   the frame onto the map, and how sure are we that it is right?

This lesson answers both with three classic tools: the **ratio test** (Lowe, 2004), the **Direct
Linear Transform** (DLT) for a **homography**, and **RANSAC** (Fischler and Bolles, 1981). You will
implement the DLT and RANSAC yourself with numpy, compare them with OpenCV, and then apply the
**trust gates** that NAVERA uses before it believes a position.

> [!NOTE]
> NAVERA's test map covers **Sousse, Tunisia**, where NAVERA is developed. The lab pictures are cut
> from that map. The maths is the same over Cape Town, Singapore or Reykjavik — only the map changes.

## 1. Nearest neighbours in descriptor space

A SIFT descriptor is a vector **d** ∈ ℝ¹²⁸ (lesson 21). Two descriptors are compared with the
Euclidean (**L2**) distance:

```
dist(a, b) = ‖a − b‖₂ = sqrt( Σₖ (aₖ − bₖ)² ),   k = 1 … 128
```

(ORB's binary descriptors use the **Hamming distance** instead — the number of differing bits —
which you wrote in lesson 21.) For each frame descriptor **q**, the **nearest neighbour** (NN) is the
map descriptor with the smallest distance. A **brute-force matcher** computes all distances:

```python
matcher = cv2.BFMatcher(cv2.NORM_L2)               # cv2.NORM_HAMMING for ORB
pairs = matcher.knnMatch(desc_frame, desc_map, k=2)  # the 2 nearest neighbours of each frame descriptor
```

Each element of `pairs` is a list `[best, second]` of `cv2.DMatch` objects with `queryIdx` (index in
the frame), `trainIdx` (index in the map) and `distance`.

<details class="further"><summary>Going further (optional) — The cost of brute-force matching, and why NAVERA uses the GPU</summary>

**Cost.** NAVERA matches up to 1500 frame descriptors against the map tiles of its search circle —
often 20 000–50 000 descriptors. That is 1500 × 30 000 = 4.5 × 10⁷ distances of 128 dimensions,
about 6 × 10⁹ multiply-adds per frame. This is why `LocalMatcher._knn2` computes them on the GPU
with `torch.cdist`, in blocks of 20 000 map descriptors to bound the memory.

</details>

## 2. The ratio test

The nearest neighbour always exists — even for a frame keypoint that is **not** on the map (a moved
car, a new building) or one that looks like many others (one palm tree in a plantation, one
container in a port). A threshold on the distance itself does not work well: distances vary a lot
between textures.

Lowe's idea: compare the best distance **d₁** with the second best **d₂**. Keep the match only if

```
d₁ < r · d₂          (r = 0.8 in NAVERA and in this lab)
```

![The ratio test](assets/ratio_test.svg)

If the keypoint is distinctive, the correct match is much closer than any other candidate, so
d₁/d₂ is small. If it is ambiguous, d₁ ≈ d₂. On his test images Lowe found that r = 0.8 removed
about 90 % of the false matches while losing less than 5 % of the correct ones.

**Worked example.** Frame keypoint A: d₁ = 100, d₂ = 300 → 100 < 0.8 × 300 = 240 → keep. Keypoint B:
d₁ = 200, d₂ = 210 → 200 > 168 → drop. Keypoint C has only one candidate (empty map nearby) → we
cannot judge → drop.

The ratio r is a trade-off. In the lab, on a 2022 photo matched against today's map, r = 0.6 keeps 2
matches (too few for any model), r = 0.8 keeps 37 of which about half are correct, and r = 1.0 (no
test) keeps all 2000 nearest neighbours of which almost none are correct — and RANSAC then finds a
**wrong** answer. The ratio test does not look at geometry; that is the job of the next sections.

## 3. Transformations and their degrees of freedom

We write image points in **homogeneous coordinates**: (x, y) becomes x = (x, y, 1)ᵀ, and any
(X, Y, W) with W ≠ 0 means the point (X/W, Y/W). A planar transformation is then a 3 × 3 matrix:

```
| X |   | h00 h01 h02 | | x |            u = X / W = (h00 x + h01 y + h02) / (h20 x + h21 y + h22)
| Y | = | h10 h11 h12 | | y |    →
| W |   | h20 h21 h22 | | 1 |            v = Y / W = (h10 x + h11 y + h12) / (h20 x + h21 y + h22)
```

Multiplying H by any non-zero number gives the same mapping, so H has 9 − 1 = **8 degrees of
freedom (DOF)**. The family of models, from the most constrained to the most general:

| Model | Matrix form | DOF | Minimal sample s | Keeps |
|---|---|---|---|---|
| translation | [I t; 0 1] | 2 | 1 pair | everything |
| Euclidean (rigid) | [R t; 0 1] | 3 | 2 pairs | lengths, angles |
| **similarity** | [sR t; 0 1] | 4 | 2 pairs | angles, ratios of lengths |
| affine | [A t; 0 1] | 6 | 3 pairs | parallel lines |
| **homography** | full H | 8 | 4 pairs | straight lines |

Each pair (x, y) ↔ (u, v) gives two equations, so the minimal sample is ⌈DOF / 2⌉ pairs.

![A homography lays the drone view onto the map](assets/homography.svg)

<details class="further"><summary>Going further (optional) — When is a homography the right model?</summary>

**When is a homography the right model?** Exactly when the scene is a **plane** (or the camera only
rotates). Seen from 300 m, flat coastal ground (like Sousse) is nearly a plane: a 20 m building is 7 % of the
height, so its roof is displaced in the image, but most of the frame follows a homography. For a
camera looking **straight down** (after NAVERA straightens the frame with the IMU, lessons 16–19),
the homography reduces to a **similarity**: rotation θ, scale s, shift (tx, ty), with h20 = h21 = 0.

</details>

## 4. The Direct Linear Transform (DLT)

Multiply the equation for u by its denominator and move everything to one side:

```
u (h20 x + h21 y + h22) − (h00 x + h01 y + h02) = 0
v (h20 x + h21 y + h22) − (h10 x + h11 y + h12) = 0
```

These are **linear** in the nine unknowns h = (h00, h01, h02, h10, h11, h12, h20, h21, h22)ᵀ. Each
pair gives two rows of a matrix A:

```
[ −x  −y  −1   0   0   0   u·x  u·y  u ]
[  0   0   0  −x  −y  −1   v·x  v·y  v ]
```

With N pairs, A is 2N × 9 and we want **A h = 0**. The trivial solution h = 0 is excluded by asking
‖h‖ = 1. With noisy points there is no exact solution, so we minimise ‖A h‖ subject to ‖h‖ = 1. The
answer is the **right singular vector of A for its smallest singular value**: with the singular
value decomposition A = U Σ Vᵀ, it is the **last row of Vᵀ**:

```python
_, _, Vt = np.linalg.svd(A)
H = Vt[-1].reshape(3, 3)
H = H / H[2, 2]          # the usual scale: H[2, 2] = 1
```

<details class="further"><summary>Going further (optional) — Why the smallest singular vector? (an SVD primer)</summary>

> [!NOTE]
> **Why the smallest singular vector? (a short primer)** The **SVD** writes any matrix as
> A = U Σ Vᵀ, where U and V are rotation-like matrices (their columns are orthonormal: length 1,
> perpendicular to each other) and Σ is diagonal with the **singular values** σ₁ ≥ σ₂ ≥ … ≥ σ₉ ≥ 0.
>
> 1. Rotations do not change lengths. So ‖A h‖ = ‖U Σ Vᵀ h‖ = ‖Σ z‖ with **z = Vᵀ h**, and
>    ‖z‖ = ‖h‖ = 1.
> 2. ‖Σ z‖² = σ₁² z₁² + σ₂² z₂² + … + σ₉² z₉², with z₁² + … + z₉² = 1. This is a weighted average
>    of the σᵢ². It is smallest when all the weight is on the smallest one: z = (0, …, 0, 1).
> 3. Back to h: h = V z = the **last column of V** = the last row of Vᵀ. The minimum value of
>    ‖A h‖ is σ₉. With 4 exact pairs σ₉ = 0 (an exact solution); with noise σ₉ is small but not 0.
>
> Example: if Σ = diag(5, 2, 0.1), the unit vector z that makes ‖Σ z‖ smallest is (0, 0, 1),
> giving 0.1; any mix such as z = (0.6, 0, 0.8) gives √(25·0.36 + 0.01·0.64) ≈ 3.0.

</details>

With exactly 4 pairs (no 3 on a line), A is 8 × 9, has a one-dimensional null space, and H is
exact. With more pairs the DLT is a least-squares fit of the **algebraic** error ‖A h‖ — not exactly
the pixel error, but close when the data are **well conditioned** (small rounding errors in A only
cause small changes in h — see the next part).

### Normalisation (Hartley, 1997)

The entries of A mix 1, x, and products like u·x. In patch pixels (0 to 800) the products reach
6 × 10⁵. NAVERA's map points are in **global tile pixels** at zoom 17–18: about 1.8 × 10⁷ (zoom 17) to
3.55 × 10⁷ (zoom 18) in Sousse.
Then u·x ≈ 2 × 10¹⁰ while some columns are −1: the matrix is badly **conditioned** (the ratio of its
largest to smallest singular value is huge) and rounding errors destroy the smallest singular vector.

![Hartley normalisation](assets/dlt_normalise.svg)

The fix is to normalise each point set with a similarity T: move the centroid to the origin and
scale so that the mean distance to it is √2:

```
c = mean of the points,   d = mean ‖pᵢ − c‖,   s = √2 / d
T = | s  0  −s·cx |
    | 0  s  −s·cy |
    | 0  0    1   |
```

Run the DLT on the normalised points (T_src·x ↔ T_dst·u) to get Hn, then undo the normalisation:

```
H = T_dst⁻¹ · Hn · T_src
```

<details class="further"><summary>Going further (optional) — What experiments.py measures: raw against normalised coordinates</summary>

What the lab's `experiments.py` measures (8 random pairs with 1 px noise, 200 trials, error averaged
over a grid of 63 image points; a quicker test in lab Step 4 gives about 1.9 / 39 px — same conclusion):

| Map coordinates | cond(A) raw | cond(A) normalised | median error raw | median error normalised |
|---|---|---|---|---|
| patch pixels (0–800) | 1.1 × 10⁸ | 571 | 1.36 px | 1.35 px |
| global tile pixels (~3.55 × 10⁷) | 8.5 × 10¹⁷ | 571 | 25.3 px | 1.35 px |

</details>

Normalisation is cheap and never hurts. Always do it.

## 5. RANSAC

Least squares has a **breakdown point** of 0 % (the breakdown point is the fraction of wrong data
a method can survive before its answer becomes meaningless): one single outlier, far enough away,
can move the fit anywhere. After the ratio test, 10–90 % of the pairs can still be wrong. **RANSAC** (RANdom SAmple
Consensus) is robust:

1. Draw a **minimal sample** of s pairs at random (s = 4 for a homography).
2. Fit the model to it (your DLT).
3. Count the **inliers**: pairs whose **reprojection error** ‖H(xᵢ) − uᵢ‖ is below a threshold t.
4. Keep the model with the most inliers. Repeat N times.
5. **Refit** the model on all the inliers of the best one.

![RANSAC on a line](assets/ransac_line.svg)

### How many samples?

Let w be the inlier ratio. A sample of s pairs is all inliers with probability wˢ. After N samples,
the probability that **none** was clean is (1 − wˢ)ᴺ. We want this to be at most 1 − p, where p is the
required confidence:

```
(1 − wˢ)ᴺ ≤ 1 − p     ⇒     N = ⌈ log(1 − p) / log(1 − wˢ) ⌉
```

**Worked example**, p = 0.99, w = 0.5:

```
s = 4 (homography):  wˢ = 0.0625,  N = log(0.01) / log(0.9375) = −4.605 / −0.06454 = 71.4  →  72
s = 2 (similarity):  wˢ = 0.25,    N = log(0.01) / log(0.75)   = −4.605 / −0.2877  = 16.01 →  17
```

![RANSAC iterations](assets/ransac_iterations.svg)

N grows roughly like 1/wˢ: with w = 0.3 the homography already needs 567 samples, a similarity 49.
This is one reason NAVERA fits a similarity (`cv2.estimateAffinePartial2D`, s = 2): fewer samples,
and a 4-DOF model is much harder to fit by accident to a group of wrong pairs than an 8-DOF one.

w is unknown in advance. **Adaptive RANSAC** starts with a large N and, each time it finds a model
with more inliers, recomputes N with w = inliers / pairs. On the city pair of the lab (w ≈ 0.95)
it stops after a handful of samples.

<details class="further"><summary>Going further (optional) — The inlier threshold: where t ≈ 2.45 σ comes from</summary>

If the true matches have Gaussian position noise σ in each axis, the squared reprojection error
divided by σ² is (ex/σ)² + (ey/σ)²: a sum of **two squared standard normal numbers**. The
distribution of such a sum has a name, **χ² ("chi-squared") with 2 degrees of freedom**; tables
give its percentiles, and its 95 % point is 5.99. (Lesson 27 explains χ² properly; here you only
need this one number.) Accepting 95 % of the true inliers therefore needs t² = 5.99 σ², so
**t ≈ 2.45 σ**. Keypoints are located to 1–2 px, so t = 3–6 px is
typical. NAVERA uses `ransac_px = 6.0` in map pixels at zoom 17 (≈ 0.97 m), i.e. about 6 m on the
ground. Too small a threshold drops good pairs; too large lets wrong pairs vote.

</details>

> [!TIP]
> OpenCV's `cv2.findHomography(src, dst, cv2.RANSAC, 5.0)` does the same thing as your RANSAC and
> then **refines** H by non-linear least squares on the pixel error (Levenberg–Marquardt). Your
> refit minimises the algebraic error only: the results are very close but not identical.

## 6. Reading the motion out of H

For the similarity part, take the 2 × 2 block A = H[:2, :2] (after dividing H by H[2, 2]). For a pure
similarity A = s·R(θ):

```
A = | s cos θ   −s sin θ |
    | s sin θ    s cos θ |
```

NAVERA reads θ and s from the **first column** — the image of the unit x vector:

```
θ = atan2(A[1,0], A[0,0])          s = sqrt(A[0,0]² + A[1,0]²)
```

A more robust reading, which also tells you how far A is from a similarity, uses the SVD
A = U Σ Vᵀ (the **polar decomposition**):

```
R = U Vᵀ   (the closest rotation)     θ = atan2(R[1,0], R[0,0])
s = sqrt(|det A|)                      anisotropy = σ₁ / σ₂   (1.0 for a pure similarity)
perspective = ‖(h20, h21)‖             (0 for a straight-down view)
```

**Worked example.** H = [[0.6928, −0.4, 120], [0.4, 0.6928, 40], [0, 0, 1]].
s = sqrt(0.6928² + 0.4²) = sqrt(0.48 + 0.16) = 0.800; θ = atan2(0.4, 0.6928) = 30.0°; det A = 0.64,
so √det = 0.800 as well, and the anisotropy is 1. The frame centre (240, 180) lands at
(0.6928·240 − 0.4·180 + 120, 0.4·240 + 0.6928·180 + 40) = (214.3, 260.7) on the map.

In image coordinates **y points down**, so a positive θ turns **clockwise** on the screen. Use
`math.atan2(y, x)` (not `atan(y / x)`, which loses the quadrant) and convert with `math.degrees`.

## 7. Trust gates

The number of inliers is a much better confidence measure than any "similarity score": NAVERA's
former retrieval method gave scores of 0.95–0.98 to right and wrong places alike. But the inlier
count alone is not enough either: in the lab, the no-ratio-test match of the 2022 photo has 11
inliers and is 364 px wrong. NAVERA therefore applies **geometric gates** that a wrong place almost
never passes:

![Trust gates](assets/trust_gates.svg)

| Gate | Where | Value | Why |
|---|---|---|---|
| inliers | `LocalMatcher.min_inliers` | ≥ 8 (≥ 15 when the height is searched) | a few pairs agree by chance |
| rotation | `locate(heading_deg=…)` | ±20° from the IMU heading | a wrong place rarely fits at the right rotation |
| scale | `scale_tol` | ±15 % of the scale predicted from height + field of view | the strongest gate (see *How much did the gates matter?* in "In NAVERA") |
| spread | `VisionNavigator.update` | if < 30 inliers, they must cover ≥ 25 % of a 4 × 2 grid | inliers on one strip (a shoreline, a road) leave scale and rotation badly determined |
| prediction | `VisionNavigator.update` | within 3 σ of the position carried along the velocity (unless ≥ 100 inliers) | a sudden jump needs a second agreeing fix |

An accepted fix gets a 1-σ uncertainty from its inlier count (`fix_sigma_m`): 4, 8, 15 or 25 map
pixels for ≥ 100, ≥ 50, ≥ 20 or fewer inliers — at 0.97 m per pixel, from about 4 m to 24 m.

## 🐦 How birds do it

In 2004 Dora Biro, Jessica Meade and Tim Guilford (University of Oxford) put small GPS loggers on
homing pigeons and released them many times from the same sites. Each bird developed its **own
personal route** home (different from the routes of the other birds) and followed it faithfully, flight after flight, often along roads,
rivers and field edges. The best explanation is **visual pilotage**: the bird matches what it sees
with remembered landmarks along the route.

Notice the logic. One white house could be any white house: a single landmark is the ratio-test
problem of section 2. What tells the pigeon "I am on my route" is a **configuration** of several
landmarks in the right relative positions — the consensus of section 5. The same holds for a bird
following a coast on migration, such as the Atlantic coast of Morocco: a coastline alone is a long, featureless line (the spread
problem of section 7); a coastline **plus** a headland, a river mouth and a town is a fix. Navi the swallow would say it simply: trust the pattern, not the
single clue.

## In NAVERA

The core of `LocalMatcher.locate()` in
[local_matcher.py](file:navera/day_pkg/day_pkg/local_matcher.py) (shortened):

```python
idx, val = self._knn2(dq, dm)                      # 2 NN per frame descriptor (GPU when available)
ok = val[:, 0] < self.ratio * val[:, 1]            # ratio test, ratio = 0.8
qi = np.nonzero(ok)[0]
src = np.float32([kq[i].pt for i in qi])           # frame points (already scaled to map resolution)
dst = pm[idx[qi, 0]].astype(np.float32)            # map points, in GLOBAL tile pixels (~3.5e7)
A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=self.ransac_px,
                                     maxIters=5000, confidence=0.999)
n_in = int(inl.sum())
scale = math.hypot(A[0, 0], A[1, 0])               # 1.0 when the altitude prediction is right
px, py = A @ np.array([q.shape[1] / 2.0, q.shape[0] / 2.0, 1.0])   # frame centre on the map
...
if n_in < self.min_inliers:            res["reason"] = f"{n_in} geometric inliers (min ...)"
elif heading_deg is not None and ...:  res["reason"] = "fitted rotation ... ≠ heading ...: wrong place"
elif abs(scale - 1.0) > tol:           res["reason"] = "fitted scale ... ≠ 1 expected from the altitude: wrong place"
else:                                  res["accepted"] = True
```

Note three details. The frame is **pre-scaled** with the height so that the expected scale is
exactly 1. The model is a **similarity** (s = 2), not a homography. And `dst` is in global tile
pixels: OpenCV normalises internally, which is exactly why your DLT must too.

<details class="further"><summary>Going further (optional) — How much did the gates matter? (bench results)</summary>

How much did the gates matter? `docs/VALIDATION_STATUS.md` (benchmark of 2026-10-01, measured on the
Jetson with 33 aerial frames from another source and date than the map, search within 600 m):

| Variant | Accepted | Error of accepted | Wrong (> 50 m) accepted |
|---|---|---|---|
| prototype, no scale check, ≥ 12 inliers | 10/33 | median 4 m, worst 1097 m | 1 |
| + scale check (frame scale known) | 21/33 | median 4 m, worst 5 m | 0 |
| + frame pre-scaled, map features per tile, margin 300 m | 32/33 | median 4 m, worst 9 m | 0 |
| product module (`LocalMatcher`, ≥ 6 inliers in that bench run — the default is now 8, as in the table above —, GPU matching) | 30/33 | median 4 m, worst 5 m | 0 |

The scale gate removed the only wrong fix (1097 m). The document is honest about the limits: these
are not frames from NAVERA's own camera, and positions are stated at ±30 m until that is measured.

</details>

## Glossary

| Term | Meaning |
|---|---|
| **nearest neighbour (NN)** | the map descriptor at the smallest distance from a frame descriptor |
| **L2 / Hamming distance** | Euclidean distance (SIFT) / number of differing bits (ORB) |
| **ratio test** | keep a match only if d₁ < r·d₂ (Lowe); removes ambiguous matches |
| **homogeneous coordinates** | (x, y) written as (x, y, 1); (X, Y, W) means (X/W, Y/W) |
| **homography** | 3 × 3 projective map between two planes; 8 degrees of freedom |
| **similarity** | rotation + uniform scale + translation; 4 degrees of freedom |
| **degrees of freedom (DOF)** | the number of independent parameters of a model |
| **DLT** | Direct Linear Transform: solve A h = 0 with the SVD |
| **SVD** | A = U Σ Vᵀ; the last row of Vᵀ minimises ‖A h‖ with ‖h‖ = 1 |
| **χ² with 2 degrees of freedom** | the distribution of a sum of two squared standard normal numbers; its 95 % point is 5.99 (lesson 27) |
| **breakdown point** | the fraction of wrong data a method survives before its answer becomes meaningless |
| **condition number** | σ_max / σ_min of a matrix; large = sensitive to rounding and noise |
| **Hartley normalisation** | centroid to 0, mean distance √2, before the DLT |
| **RANSAC** | fit minimal random samples, keep the model with most inliers, refit |
| **inlier / outlier** | a pair that agrees / disagrees with the model within the threshold |
| **reprojection error** | ‖H(x) − u‖ in pixels |
| **inlier ratio w** | inliers / all pairs; decides how many RANSAC samples are needed |
| **trust gate** | a geometric test a fix must pass before it is believed |

## Check what you learned

<details><summary>1. A match has d₁ = 180 and d₂ = 200. Does it pass the ratio test with r = 0.8? With r = 0.95?</summary>
0.8 × 200 = 160 < 180: dropped. 0.95 × 200 = 190 > 180: kept. A higher r keeps more matches,
including more ambiguous ones.
</details>

<details><summary>2. Why is the minimal sample 4 pairs for a homography and 2 for a similarity?</summary>
A homography has 8 DOF (9 entries minus the overall scale), a similarity 4 (θ, s, tx, ty). Each
pair gives 2 equations (u and v), so 8/2 = 4 and 4/2 = 2 pairs.
</details>

<details><summary>3. Why is h the last row of Vᵀ, and why must you divide H by H[2, 2]?</summary>
Minimising ‖A h‖ with ‖h‖ = 1 gives the right singular vector of the smallest singular value; numpy
sorts singular values in decreasing order, so it is the last row of Vᵀ. That vector has norm 1, not
H[2, 2] = 1; dividing fixes the arbitrary scale so that H is comparable with OpenCV's.
</details>

<details><summary>4. With w = 0.3, p = 0.99, how many RANSAC samples does a homography need? A similarity?</summary>
Homography: log(0.01) / log(1 − 0.3⁴) = −4.605 / log(0.9919) = 567. Similarity:
−4.605 / log(0.91) = 48.8 → 49. A 4-DOF model needs about 11 times fewer samples.
</details>

<details><summary>5. A fit has 250 inliers, rotation as the IMU says, but scale 1.45 when 1.0 is expected. Accept?</summary>
No. The scale is predicted from the height and the field of view; 45 % off means a wrong place (or
a badly wrong height). NAVERA refuses it: "fitted scale 1.45 ≠ 1 expected from the altitude: wrong
place". (When the height itself is uncertain, `locate_any_height` searches several heights instead.)
</details>

<details><summary>6. Your DLT works on patch pixels but gives 25 px errors on global tile pixels. What is wrong?</summary>
You skipped (or mis-applied) the Hartley normalisation: at coordinates near 3.5 × 10⁷ the matrix A
has a condition number around 10¹⁸ and the smallest singular vector is destroyed by rounding.
Normalise both sets and de-normalise with H = T_dst⁻¹ Hn T_src.
</details>

Now open the **🛠️ Lab** tab.
