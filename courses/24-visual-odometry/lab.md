# Lab 24 — An odometer from two frames, and a navigator that knows when it lies

**Goal:** write phase correlation with numpy's FFT and measure it against OpenCV; turn pixel shifts into metres east and
north and follow a drone along a 90-second flight over Sousse; find the two hidden causes of its drift; race six
odometers, one of them with the descriptor you trained in mission 21; then simulate drift, choose when to refuse a
step, and bound the error with map fixes.
**Time:** 4 h 30 to 6 h in two sessions (a strong programmer: about 3 h 30).
**Fast track:** if you know numpy's FFT, write the TODOs from the docstrings without the 🧰 and "Stuck?" boxes, then do
"Going further" and put the results in `LOOK_BACK`.

Your files (📝 Code tab): [navera_lite/vo.py](file:./navera_lite/vo.py) (**your code**: TODO 1–5, 7, 8),
[drift_sim.py](file:./drift_sim.py) (**your code**: TODO 6), [answers.py](file:./answers.py), [report.md](file:./report.md),
and the ready-made runner [run_vo.py](file:./run_vo.py) (runs your functions on the flight and draws them; you don't
edit it). `python3 run_vo.py test` tries every docstring example and names the symptom of a wrong result.

The data is in `/data/academy/24-visual-odometry/` (read only): a synthetic flight drawn from OpenStreetMap data of
Sousse, Tunisia (NAVERA's test area; map data © OpenStreetMap contributors), made by us so that we know the exact
truth, and 40 frame pairs. Like a real drone, the flight has defects you are **not told about**.

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a calculation by hand |
| §2–§3 phase correlation | Steps 1–2 | `phase_shift` |
| §5–§6 metres, dead reckoning | Steps 3–4 | `px_to_en`, `integrate` |
| §4 turns, keypoints | Step 5 | `median_shift` |
| §7 random walk and bias | Step 6 | `drift_sigma`, `simulate_drift` |
| §9 threshold | Step 7 | (a decision) |
| §8–§9 blend, gate | Steps 8–9 | `blend`, `vo_gate` |
| all | Step 10 | the report |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is never marked
> right or wrong; being wrong and finding out why is the point.

## Session 1 — Odometer (about 2 h 30 to 3 h)

## Step 0 — The flight, by hand

No code yet. Look at the flight:

```bash
python3 run_vo.py look
```

Open `out/flight_sheet.png` (click it in the file tree; ⟳ refreshes the tree). Every 6th frame of 90, one per second.
The top of each frame points to the drone's heading. Then read what the drone measured:

```bash
head -4 /data/academy/24-visual-odometry/flight.csv
```

```bash
cat /data/academy/24-visual-odometry/info.json
```

The drone flies at 20 m/s, one frame per second, so 20 m between frames.

> [!TASK]
> With frame 1's barometer height, the camera's HFOV and width from `info.json`, compute **by hand** (a calculator or
> one `python3 -c` line) how many pixels the ground slides between two frames: `SLIDE_PX`. Then **predict**
> (`PREDICT_SEA`): over open water, what will phase correlation say? Save `answers.py` (`Ctrl+S`), then read lesson
> Part A (§1–§6).

## Step 1 — Phase correlation (TODO 1)

Open [navera_lite/vo.py](file:./navera_lite/vo.py). Each TODO function keeps its docstring and ends with
`return None   # TODO…`: replace that line with your code. The finished functions (`to_gray32`, `derotate`,
`opencv_shift`, `keypoint_matches`) are for you to read and use.

**TODO 1** `phase_shift(a, b)`: the eight steps of lesson §3. This is the biggest function of the lab: write it in
small pieces and print as you go.

<details><summary>🧰 numpy's FFT and the peak of an array</summary>

```python
import numpy as np
x = np.array([[1.0, 2.0], [3.0, 4.0]])
F = np.fft.fft2(x)                    # complex (2, 2): F[0, 0] = 10 (the sum)
np.real(np.fft.ifft2(F))              # back to x (the imaginary parts are ~1e-16)
np.conj(1 + 2j), np.abs(3 + 4j)       # (1-2j), 5.0
np.outer([1, 2], [10, 20, 30])        # (2, 3): [[10, 20, 30], [20, 40, 60]]
z = np.array([[0, 7, 1], [9, 2, 3]])
k = np.argmax(z)                      # 3: the flat index of 9
np.unravel_index(k, z.shape)          # (1, 0): row 1, column 0  →  (y, x)!
7 % 3, -1 % 3                         # 1, 2 — the neighbour of index 0 on the left is the last one
```
</details>

```bash
python3 run_vo.py test
```

The TODO 1 line must be ✔ (the others are later TODOs). Then one real step of the flight, frames 9 → 10:

```bash
python3 run_vo.py pair 10
```

It prints your (dx, dy, response) and OpenCV's, and saves `out/pair_10.png`: frame 9, frame 10, and frame 9 moved by
**your** shift subtracted from frame 10. Flat grey = your shift is right.

<details><summary>Stuck? Hints, one at a time</summary>

1. Start with `h, w = a.shape`, the float arrays `a = np.asarray(a, dtype=float)` (same for b), and the window
   `np.outer(np.hanning(h), np.hanning(w))`. Then steps 2–4 of §3 give the surface r; print `r.shape` (it must be (h, w)).
2. The peak: `py, px = np.unravel_index(np.argmax(r), r.shape)` — row first.
3. `75` instead of `−5` (or `310` on a frame): an index past the middle is a negative shift (`dx -= w`).
4. `(2, −5)` instead of `(−5, 2)`: x and y swapped. `(5, −2)`: every sign reversed — it is `B * np.conj(A)`.
5. A response far above 1 (or near 0.0001): divide R by `np.abs(R) + 1e-12` before `ifft2`.
6. Sub-pixel: a small helper `def vertex(cm, c0, cp):` that returns the δ of §3 (0 if the denominator is 0), called once
   with `r[py, (px - 1) % w], r[py, px], r[py, (px + 1) % w]` and once with the neighbours in the column. Add it to
   px and py **before** the negative-shift rule.
</details>

## Step 2 — Your FFT against OpenCV

```bash
python3 run_vo.py compare
```

It runs your `phase_shift` and OpenCV's `phaseCorrelate` on the 51 steps of the first leg (frames 0–51, over the city),
each previous frame first turned by the IMU's heading change (`derotate`), and prints how far apart the two shifts are,
both responses, and the time per step.

> [!TASK]
> Write `MEAN_DIFF_PX` (three decimals) and `EXPLAIN_SUBPIXEL`: where does that small difference come from, and what do
> both methods agree on?

<details><summary>Stuck? Hints</summary>

1. A difference above 1 px on some step: your phase_shift is wrong there. Run `pair` with that step's number and look
   at the right panel.
2. The explanation: lesson §3, "OpenCV".
</details>

## Step 3 — From pixels to metres, and the track (TODO 2, TODO 3)

**TODO 2** `px_to_en(dx, dy, m_per_px, heading_deg)`: lesson §5. Check on paper first: (dx, dy) = (−10, 0) px at
0.5 m/px, heading 0 → the drone moved 5 m east.

**TODO 3** `integrate(steps, start=(0.0, 0.0))`: lesson §6. Return a numpy array of n + 1 rows.

<details><summary>🧰 Running sums in numpy</summary>

```python
s = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
np.cumsum(s, axis=0)          # [[1, 2], [4, 6], [9, 12]]: running sums down the rows
np.zeros((4, 2))              # 4 rows of (0, 0)
np.vstack([[[10.0, 0.0]], s]) # a row on top: shape (4, 2)
```
</details>

```bash
python3 run_vo.py test
```

```bash
python3 run_vo.py pair 10
```

Now `pair` also prints the drone's motion east/north next to the truth.

<details><summary>Stuck? Hints, one at a time</summary>

1. TODO 2: two lines for right and forward, `th = math.radians(heading_deg)`, then the two formulas of §5. Return a tuple
   of two floats.
2. `(−5.0, 0.0)` instead of `(5.0, 0.0)` on the docstring example: the sign of forward — the ground slid DOWN, the
   drone flew forward.
3. `(0.0, 5.0)`: east and north swapped, or the heading not used.
4. TODO 3: 4 rows for 4 steps? Row 0 is the start. The track ignores `start`? Add start to every running sum.
</details>

## Step 4 — The first leg: drift, and its two causes

```bash
python3 run_vo.py leg
```

Dead reckoning along the first leg with your three functions, the barometer's height and the IMU's heading. Open
`out/leg.png`: your track (red) against the truth (black), and the error frame by frame.

The runner also fits **one scale and one rotation** that turn your steps into the true ones (lesson §6, last paragraph):
"the truth is k × your step length", and "your steps point … ° clockwise / anticlockwise of the true ones".

> [!TASK]
> Write `DRIFT_BARO` (m per 100 m), `SCALE_RATIO` (k) and `HEADING_ERROR_DEG`. Your steps are too short by the factor k:
> which height would make them right? Write it as `TRUE_ALT_M` (the barometer said about 116.4 m), then run
> `python3 run_vo.py leg --altitude H` with your H and write `DRIFT_TRUE_ALT`. Then correct the heading too:
> `python3 run_vo.py leg --altitude H --heading-offset D`, where D is the correction (think about its sign), and write
> `DRIFT_BOTH`. Finally `EXPLAIN_BIAS`: the two causes, and why they make the error grow with every step.

<details><summary>Stuck? Hints</summary>

1. g ∝ h (lesson §6): if every step must be k times longer, the height must be k times larger.
2. The drift barely moves with `--heading-offset 2`? It got worse: your steps point clockwise of the truth, so the IMU
   heading is too large — subtract.
3. DRIFT_BOTH is below 0.3 m per 100 m when both corrections are right.
</details>

> [!QUESTION]
> The error after 1 km is about 47 m and it never comes back down by itself. What kind of information, in a real flight
> without truth, could reveal the height and heading errors? (Lesson §8 has one answer.)

## Step 5 — Six odometers (TODO 4)

**TODO 4** `median_shift(p1, p2, tol_px=1.0)`: lesson §4. The votes are `p2 − p1`.

<details><summary>🧰 Medians and distances in numpy</summary>

```python
d = np.array([[3.0, 1.0], [3.2, 0.8], [40.0, -9.0]])
np.median(d[:, 0]), np.median(d[:, 1])        # 3.2, 0.8 — per column
np.hypot(d[:, 0] - 3.0, d[:, 1] - 1.0)        # [0., 0.283, 38.3]: the distance of each vote to (3, 1)
(np.hypot(d[:, 0] - 3.0, d[:, 1] - 1.0) <= 1.0).sum()   # 2 votes within 1 px
np.asarray([(1, 2)], dtype=float).reshape(-1, 2)        # a list of points as an (N, 2) array
```
</details>

```bash
python3 run_vo.py test
```

Now the race. The runner measures six odometers on 40 frame pairs from another part of the city and from the sea, in
five groups: straight flight, and turns of 4°, 12° and 30° between the two frames, and open sea. For each pair the
true shift is known. The six: your `phase_shift` as it is; your `phase_shift` after `derotate` with the IMU's heading
change; OpenCV after `derotate`; ORB keypoints + your `median_shift` after `derotate`; **your PatchNet** descriptor
(mission 21) + your `median_shift` after `derotate`; and ORB keypoints with OpenCV's fit of a turn and a shift, without
the IMU.

The runner uses `my_desc.pt` from this folder, else your mission 21 file `../21-features/my_desc.pt`, else the course's
`ref_desc.pt`; it prints which. (The GPU is shared by the class: if no slot is free within 30 s, it runs on the CPU,
slower — about a minute.)

> [!TASK]
> **Predict** (`PREDICT_RACE`): on straight pairs, which odometer will be the most precise, and how many times slower
> than your phase correlation will the learned descriptor be?

```bash
python3 run_vo.py odometers
```

Open `out/odometers.png` too.

> [!TASK]
> Write `OK_PHASE_TURN4` and `OK_ORB_FIT_TURN30` (pairs right, of 8) and `EXPLAIN_ODOMETERS`: why does phase
> correlation need the IMU; what do keypoints, and your learned descriptor, cost; what can no method do?

<details><summary>Read this after you ran `odometers`: a fair race?</summary>
All the methods measured the same pairs against the same truth. Your network was trained to match <b>map</b> patches
with <b>drone photo</b> patches; here it matches two frames of the same camera one second apart, an easier job, so it
is precise, but it pays a forward pass of a CNN on hundreds of patches per frame. For consecutive frames of a camera
whose turn the IMU knows, phase correlation is as precise and much cheaper: that is why NAVERA uses it for odometry, and
keeps learned features for the hard job of matching a frame with the map (missions 22–23). Over the sea, no method has
anything to follow.
</details>

<details><summary>Stuck? Hints (TODO 4)</summary>

1. Three parts: the votes `d = p2 - p1` (as float arrays of shape (N, 2)); the medians of `d[:, 0]` and `d[:, 1]`; the
   count of votes within `tol_px` (≤) of that median point.
2. The docstring example gives (−14.67, −1.0, …): that is the mean. Use `np.median`.
3. With no match at all, return `(None, None, 0)` before anything else (`np.median` of an empty array is `nan`).
</details>

> [!TIP] 🏅 End of session 1 — Odometer
> Press **✔ Check my work**. When checks 1–7 pass (TODO 1–4, your odometer on an unseen flight, Steps 0–5), you earn the
> **Odometer** badge. If the class session ends here, stop here, and read lesson Part B before session 2.

## Session 2 — Navigator (about 2 h to 2 h 30)

## Step 6 — Drift, simulated (TODO 5, TODO 6)

**TODO 5** `drift_sigma(n, sigma_step_m, bias_m)` in `vo.py`: lesson §7. It must work on a number and on a numpy array
of n's (use `np.sqrt`).

**TODO 6** `simulate_drift(n_steps, sigma_m, bias_m, trials=2000, seed=0)` in [drift_sim.py](file:./drift_sim.py): the
Monte Carlo of lesson §7, in one axis.

<details><summary>🧰 Random numbers, sums along an axis, RMS</summary>

```python
rng = np.random.default_rng(7)           # the same seed → the same numbers, every run
x = rng.normal(0.0, 2.0, size=(3, 5))    # 3 rows × 5 columns, mean 0, standard deviation 2
np.cumsum(x, axis=1)                     # running sums ALONG each row
np.mean(x ** 2, axis=0)                  # the mean of the squares DOWN each column: 5 numbers
np.sqrt(np.mean(np.array([3.0, -4.0]) ** 2))   # RMS of [3, −4] = 3.54
```
</details>

```bash
python3 run_vo.py test
```

> [!TASK]
> **Predict** (`PREDICT_GROWTH`): on log-log axes, what will the "both" curve (σ = 0.5 m and a bias of 0.1 m) look like?

```bash
python3 drift_sim.py
```

Open `out/drift.png`: your simulation (solid) against your formula (dashed), for random errors only, a bias only, and
both.

> [!TASK]
> Write `EXPONENT_RANDOM`, `EXPONENT_BIAS` (two decimals) and `N_CROSS`: with σ = 0.5 m and a bias of 0.1 m, after how
> many steps is the bias part as large as the random part? (By hand, from lesson §7; check it on the plot.)

<details><summary>Stuck? Hints, one at a time</summary>

1. TODO 5: one line with `np.sqrt`; then `float(...)` if the result is a single number (the docstring wants a float
   for a number).
2. `drift_sigma(25, 1.0, 0.0)` gives 25, or `drift_sigma(25, 1.0, 0.2)` gives 10: σ's do not add, variances do (n·σ²
   and n²·bias²), then one square root.
3. TODO 6: the errors of all flights at once: `bias_m + rng.normal(0.0, sigma_m, size=(trials, n_steps))`; the
   accumulated errors along the steps; the RMS over the trials.
4. All the RMS values equal to the bias: the errors were not accumulated (np.cumsum along axis 1). An RMS near 0 with
   σ = 1: the mean of signed errors — square first.
</details>

## Step 7 — When to trust a step

```bash
python3 run_vo.py responses
```

It measures every step of the **whole** flight (89 steps: city, coast, the turn over the sea, back over the coast and
the city) and marks each step **right** or **wrong** against the truth. It prints the lowest responses of the right
steps and all the wrong ones, and draws `out/responses.png`. Look at frames 60 and 84 too
(`out/flight_sheet.png`, or open `/data/academy/24-visual-odometry/flight/frame_084.jpg`).

> [!TASK]
> Write `SEA_MAX_RESPONSE` (the highest response of a wrong step over the water) and choose **your threshold**
> `MIN_RESPONSE`: steps below it will be refused. It must refuse every wrong step over the water and keep every right
> step. Then `EXPLAIN_THRESHOLD`: why are the steps over the water weak, and what kind of wrong step does a threshold
> miss? (Was your `PREDICT_SEA` right?)

<details><summary>Stuck? Hints</summary>

1. The wrong steps form two groups: very low responses (over the water) and a few high ones. Which steps are the high
   ones, and what is in those frames?
2. Your threshold lies between the highest response of the first group and the lowest response of a right step.
</details>

## Step 8 — Blend and gate (TODO 7, TODO 8)

**TODO 7** `blend(x1, v1, x2, v2)`: lesson §8. It must also work element by element on numpy arrays (east and north at
once): use plain arithmetic, no `math`.

**TODO 8** `vo_gate(v_vo, v_ref, sigma_mps, k=3.0)`: lesson §9. The least guided TODO: work the lesson's worked example
by hand first, then write it. Return `True` or `False`.

```bash
python3 run_vo.py test
```

<details><summary>Stuck? Hints</summary>

1. blend gives (11.5, 2.25) instead of (14.5, 2.25): the weights are swapped — each estimate is weighted by the OTHER
   one's variance.
2. vo_gate: compare the two vectors, not their lengths: (−20, 0) and (20, 0) have the same speed.
3. Exactly k·σ apart is accepted (≤).
</details>

## Step 9 — The whole flight

The runner now flies the whole flight four times, adding one defence each time: **A** every step as measured;
**B** + your threshold; **C** + your gate (the expected velocity is the last accepted step turned by the IMU's heading
change; a refused step is replaced by it); **D** + the seven map fixes of `map_fixes.csv` (none over the sea), blended
with your `blend`, the stated σ grown with your `drift_sigma`.

> [!TASK]
> **Predict** (`PREDICT_GATE`): which stage will have the largest worst error, and will stage D's 2σ cover the true
> error more or less than 86 % of the time?

```bash
python3 run_vo.py fuse
```

Open `out/fuse.png`: the four tracks, then D's true error with its stated 2σ, and C's error without fixes.

> [!TASK]
> Write `GATE_REFUSED`, `WORST_NO_FIX` (stage C), `WORST_FUSED` (stage D), `COVERAGE` (stage D) and `EXPLAIN_FUSION`:
> what does a fix do to the error, where is the worst error, and is the stated σ honest?

> [!QUESTION]
> Try `python3 run_vo.py fuse --bias 1.0` (and other values). Which bias makes the coverage close to 86 %? What does
> that say about the 0.7 m you were given, compared with what you measured in Step 4?

## Step 10 — The report

Write [report.md](file:./report.md) (200–450 words, your own words, keep the four headings): the odometer (your FFT
against OpenCV), the drift (its two causes and how you found them), the six odometers, and the navigator (threshold,
gate, fixes, honesty of σ). Quote your numbers.

> [!TASK]
> report.md has the four headings, at least 200 words, and quotes your `DRIFT_BARO`, `OK_PHASE_TURN4`, `WORST_FUSED`
> and `COVERAGE`.

## Step 11 — Check, then look back

Press **✔ Check my work**. It tests your functions on numbers and frames they have never seen (another place, another
height, a turn) and reads your answers and report. When every check passes, you earn the **Navigator** badge. Then look
back, without the lesson:

1. Explain to a colleague, in three sentences, what went wrong on Ingenuity's sixth flight and which of your defences
   would, or would not, have helped.
2. Which of your predictions was the most wrong? What did you assume?
3. Your odometer drifted 4.6 m per 100 m with the barometer. Name two sensors or measurements that would reduce it,
   and what each one fixes.

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **Calibrate on the fly.** Between two map fixes, compare the direction and the length of your odometry with the
  fix-to-fix vector: their ratio is the scale error, their angle the heading error. Correct the steps after each fix and
  measure the new worst error.
- **A better sub-pixel peak.** The parabola is biased towards whole pixels. Measure its error on exact sub-pixel shifts
  (shift a picture with the Fourier shift theorem, as the check does) and compare with OpenCV's centroid.
- **NAVERA's high-pass.** Subtract a blurred copy from each frame before `phase_shift`
  (`g - cv2.GaussianBlur(g, (0, 0), 8)`). What happens to the responses over the city, over the sea, and on the
  overlay frames?
- **Fly your own parts.** `cp ../21-features/navera_lite/learned_desc.py navera_lite/` uses your own mission 21 code.
