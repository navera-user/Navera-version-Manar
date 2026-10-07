# Lab 23 — Visual odometry over NAVERA's Sousse map

**Goal:** write phase correlation with numpy's FFT and compare it with OpenCV, turn image shifts into
metres east/north, follow a drone through 80 frames, measure the drift and explain it with a
random-walk model, bound it with map fixes (a Kalman update), and run NAVERA's own `FrameOdometry`
and `VisionNavigator` on the same flight.
**Time:** about 3 hours.

Your files:

| File | What you do there |
|---|---|
| [vo.py](file:./vo.py) | TODOs 1–8: the odometry chain, the fusion, NAVERA's odometry |
| [drift_sim.py](file:./drift_sim.py) | TODOs 9–10: Monte Carlo of drift, growth exponent |
| [navera_nav.py](file:./navera_nav.py) | TODO 11: NAVERA's odometry gate, then the flight through `VisionNavigator` |
| [report.md](file:./report.md) | your short written analysis (graded) |

The programs write their measurements into `results.json`; the check reads it and compares your
report with it. Code below the line `# ---- you don't need to change anything below this line ----`
loads data and draws plots: read it, but you do not need to change it.

## Step 1 — Meet the flight

The dataset is a **synthetic flight**: 80 frames cut from NAVERA's satellite map (Sousse, Tunisia)
along a 1.58 km arc at about 114 m, one frame per second, 20 m apart. Because we made it, the truth is
exact.

```bash
ls /data/academy/23-visual-odometry
```

```bash
cat /data/academy/23-visual-odometry/info.json
```

`info.json` gives what the drone *believes*: the **barometer** height 110.8 m, a 70° camera, 320 px
wide frames, "north-up according to the IMU". `truth.csv` gives the true position of each frame in
metres east/north of frame 0 — use it **only to grade** your odometry, never to compute it.

```bash
head -4 /data/academy/23-visual-odometry/truth.csv
```

Now look at the frames:

```bash
python3 vo.py sheet
```

Open **frames.png** (file list on the left). Ten frames per row, in flight order. Consecutive frames
show nearly the same ground, slightly moved: that motion is what you will measure.

> [!NOTE]
> Like a real drone, the flight has defects you are **not told about**: each frame has its own
> brightness, blur, noise and JPEG artefacts, and two small systematic errors are hidden in the
> sensors. You will find them with your measurements in Step 6.

## Step 2 — Metres per pixel (TODO 1)

> [!TASK]
> **TODO 1.** In `vo.py`, complete `frame_m_per_px(altitude_m, hfov_deg, width_px)`:
> `2 h tan(HFOV/2) / W`.

```bash
python3 -c "import vo; print(vo.frame_m_per_px(110.8, 70, 320))"
```

Expected: `0.48489…`. If you see `-1.5…` or a huge number, you gave degrees to `math.tan`.

## Step 3 — Phase correlation with numpy (TODO 2)

> [!TASK]
> **TODO 2.** Complete `phase_correlation(a, b)` → `(dx, dy, response)`, following the six comments
> in the function and section 2 of the lesson: Hanning window, `np.fft.fft2`, normalised cross-power
> spectrum `Fb · conj(Fa) / |…|`, `np.fft.ifft2` (real part), peak with `np.argmax` +
> `np.unravel_index`, parabola sub-pixel refinement in x and y, negative shifts for indices above
> W/2 or H/2. `response` is the peak value.

Test it on a frame rolled by a known amount (5 px down, 7 px left):

```bash
python3 -c "import vo, cv2, numpy as np; a = vo.to_grey_float(cv2.imread(vo.DATA + '/frames/frame_030.jpg')); print(vo.phase_correlation(a, np.roll(a, (5, -7), axis=(0, 1))))"
```

You should see about `(-7.0, 5.0, 0.95)`. If you get `(313.0, 5.0, …)` you forgot the negative
shifts; if the response is tiny (≈ 0.0001) you forgot to normalise. Now two unrelated noise images:

```bash
python3 -c "import vo, numpy as np; r = np.random.default_rng(1); print(vo.phase_correlation(r.normal(size=(240, 320)), r.normal(size=(240, 320))))"
```

A random shift with a response near 0.02: no common motion, no peak. This is what the sea looks like
to visual odometry.

## Step 4 — Your FFT against OpenCV (TODO 3)

> [!TASK]
> **TODO 3.** Complete `frame_shift(prev, cur, method="numpy")`: convert both frames with
> `to_grey_float()`; `"numpy"` returns `dx, dy` of your `phase_correlation`; `"opencv"` uses
> `cv2.createHanningWindow((width, height), cv2.CV_32F)` and `cv2.phaseCorrelate(a, b, window)`;
> any other method raises `ValueError`.

```bash
python3 vo.py pair 10
```

Both methods should give about `dx = +15.7, dy = +36.9` px. (The camera-motion line stays empty until
TODO 4.) Open **pair_10.png**: find a building that moved between the two frames — does it move the way
dx, dy say? Now compare on all 79 pairs:

```bash
python3 vo.py compare
```

Expected: a mean difference below 0.4 px (about 0.17 px), and OpenCV 2–3 times faster. The integer
peak is the same; the sub-pixel methods differ (parabola vs centroid). This writes the
`fft_vs_opencv` part of `results.json`.

## Step 5 — From pixels to east/north (TODO 4)

> [!TASK]
> **TODO 4.** Complete `shift_to_east_north(dx, dy, m_per_px, heading_deg=0.0)`: first `right` and
> `forward` in metres (the ground moves the other way; y points down), then the rotation by the
> heading θ (lesson, section 3).

Check two cases on paper first: (dx, dy) = (−10, 0) px at 0.5 m/px, θ = 0 → (5, 0) m east;
(0, +10) px, θ = 90° → (5, 0) m (forward is east).

```bash
python3 vo.py pair 10
```

Now the camera-motion line should read about east −7.6 m, north +17.9 m against the truth −7.3,
+18.6. NAVERA's frames are usually **heading-up** (the top of the image is where the drone flies), not
north-up. This command turns frames 10 and 11 heading-up with the true heading (337.6°), measures the
shift and converts it with your heading rotation:

```bash
python3 vo.py heading 10
```

The ground now slides almost straight **down** (dx ≈ 0.5, dy ≈ 40 px: the drone flies forward), and
with θ = 337.6° your function gives the same east/north as in the north-up case. If east has the
wrong sign here but not before, your rotation matrix is transposed.

## Step 6 — Integrate and measure the drift (TODOs 5, 6)

> [!TASK]
> **TODO 5.** `integrate(steps, start)`: the running sum, n steps → n + 1 points.
>
> **TODO 6.** `drift_per_100m(track, truth)`: 100 × (distance between the last points) / (length of
> the true path, the sum of the true step lengths).

```bash
python3 vo.py
```

Expected: `final error 54.3 m … drift 3.43 m per 100 m` (fusion is TODO 7: it says "not done yet").
Open **vo_track.png** (red: your odometry, black: the truth) and **vo_error.png**. The shape of the
track is right; it slowly slides away.

Now the first hidden defect. The barometer says 110.8 m, but the drone really flew at 114.25 m:

```bash
python3 vo.py --altitude 114.25
```

The drift drops to about 2.6 m per 100 m: the barometer made every step 3 % too short (a scale bias).
What is left is mostly the second hidden defect: the IMU heading is about **2° off**, so every step is
turned (sin 2° ≈ 0.035). Both are **biases**; no better pixel measurement removes them.

> [!QUESTION]
> The error at the end is 54 m after 1580 m. Will it ever come back down by itself? What kind of
> information could correct the 2° heading error?

## Step 7 — Drift as a random walk (TODOs 9, 10)

Is the error growth on the flight "√n" or "n"? Simulate both.

> [!TASK]
> **TODO 9.** In `drift_sim.py`, `simulate_drift(n_steps, sigma, bias, trials, seed)`: per-step error
> vectors `ex = bias + N(0, σ)`, `ey = N(0, σ)` for `trials` flights (`np.random.default_rng(seed)`,
> arrays of shape `(trials, n_steps)`), cumulative sums along the steps, and the RMS of |error| over
> the trials → an array of length `n_steps`.
>
> **TODO 10.** `growth_exponent(rms)`: the slope p of `log(rms)` against `log(n)`, n = 1…len(rms)
> (`np.polyfit(..., 1)`).

```bash
python3 drift_sim.py
```

Expected: after 100 steps about 7.07 m (= σ√(2n)) for random errors and 10.00 m (= b·n) for the bias;
exponents 0.50 and 1.00. Open **drift_sim.png**: two straight lines of different slopes on a log-log
plot, and the dashed "both" curve that follows the random line first and the bias line later.

## Step 8 — Fusion with map fixes (TODO 7)

`map_fixes.csv` gives a map-matched position (lesson 22) every 10 frames (200 m): the truth plus about
4 m of noise.

```bash
cat /data/academy/23-visual-odometry/map_fixes.csv
```

> [!TASK]
> **TODO 7.** `fuse_with_fixes(steps, fixes, fix_sigma=4.0, k=0.1, c=1.0, start, start_sigma=0.0)` →
> `(track, sigmas)`. After step i (counting from 1): position += step, σ += k·|step| + c. If `i in
> fixes`: K = σ² / (σ² + fix_sigma²), position += K (fix − position), σ = √((1 − K) σ²). Both lists
> have `len(steps) + 1` entries (the start included).

Small test first — 4 steps of 10 m east, a fix at (0, 0) after step 2:

```bash
python3 -c "import vo; t, s = vo.fuse_with_fixes([(10, 0)] * 4, {2: (0, 0)}); print(t); print([round(x, 2) for x in s])"
```

Expected track `(0,0) (10,0) (10,0) (20,0) (30,0)` and sigmas `0, 2, 2.83, 4.83, 6.83`: at step 2,
σ = 4 m equals the fix's 4 m, so K = 0.5 and the position goes half-way (from 20 to 10). Now the
whole flight:

```bash
python3 vo.py
```

Expected: `worst 10.3 m` with fixes (against 54 m), and the stated 2σ covering the true error on
about 99 % of the frames. In **vo_error.png** the blue curve is a saw-tooth, the dashed line the
stated 2σ.

## Step 9 — NAVERA's own code on the same flight (TODOs 8, 11)

Your NAVERA copy is in `~/navera`. Open
[frame_odometry.py](file:navera/day_pkg/day_pkg/frame_odometry.py) and
[vision_nav.py](file:navera/day_pkg/day_pkg/vision_nav.py) beside this lab.

> [!TASK]
> **TODO 8.** `navera_steps(frames, m_per_px)` → `(steps, refused)`: create one
> `FrameOdometry()` and call `step(frame, 0.0, m_per_px, float(t))` for frame t = 0, 1, 2…
> (heading 0: north-up frames; t in seconds). The first call only stores the frame. Each later call
> returns `(east, north, dt, quality)` or `None` (refused): keep `(east, north)`, and for a refused
> step repeat the previous accepted step (constant velocity) and count it.

```bash
python3 vo.py navera
```

Expected: 0 refused, a drift of about 3.57 m per 100 m — close to yours. NAVERA works on a half-size,
high-passed image; your full-size version is a little better here.

> [!TASK]
> **TODO 11.** In `navera_nav.py`, `vo_gate(v_vo, v_ref, vel_sigma)`: True when the VO velocity
> agrees with the velocity measured by the map fixes — the same rule as `VisionNavigator.odometry()`.

```bash
python3 navera_nav.py
```

It flies the flight through `VisionNavigator` twice: GPS for 4 frames, then your VO as velocity
measurements, **A** with the map fixes, **B** with none. It prints NAVERA's mode (measured /
propagated / unavailable), the stated σ and the true error, and checks that your gate takes the same
decisions as NAVERA's (76 of 76). Read scenario B: σ grows faster and faster (the ½·a·dt² term) and
NAVERA says **unavailable** from frame 29, when σ passes `max_sigma_m` = 300 m.

> [!QUESTION]
> In B the error of `VisionNavigator` reaches ~150 m before it stops, but your integrated odometry was
> only about 24 m off at frame 28. Look at `predict()`: how does it use the velocity, and why does that hurt
> on a curved path flown without a heading?

## Step 10 — Write the report

> [!TASK]
> Fill in [report.md](file:./report.md): five sections, 2–5 sentences each, every `...` replaced.
> The check looks for your measured numbers (from the outputs or `results.json`): the drift with the
> barometer and with the true height, the random-walk exponent, the worst error with map fixes and the
> frame where scenario B becomes unavailable. At least 250 words.

```bash
cat results.json
```

## Step 11 — Check your work

Press **✔ Check my work**. The check tests every function on small exact cases, runs your odometry on
the whole flight, and compares `results.json` and `report.md`. If the `results.json` check fails, run
again, in this order: `python3 vo.py compare`, `python3 vo.py`, `python3 vo.py --altitude 114.25`,
`python3 vo.py navera`, `python3 drift_sim.py`, `python3 navera_nav.py`.

## Going further (optional)

- **A better sub-pixel peak.** The parabola is biased towards integer positions. Implement the
  estimator of Foroosh et al. (2002) for phase correlation — with c₊ > c₋: δ = c₊ / (c₊ ± c₀), keeping
  the solution in [0, 1] — and measure the error on shifts of 0.25, 0.5, 0.75 px (make exact sub-pixel
  shifts by shifting a 4× upscaled image by 1, 2, 3 px and downscaling with `cv2.INTER_AREA`).
- **Estimate the heading bias from the fixes.** Between two map fixes compare the direction of your
  odometry with the direction from fix to fix. Average the angle, turn every step back by it, and see
  the drift fall. With the scale ratio of the same two vectors you also get the height error — this is
  how a navigation system calibrates itself on-line.
- **Honest or over-confident?** Rerun `fuse_with_fixes` with k = 0.02 and k = 0.3 (edit `main()`).
  What happens to the 2σ coverage? Which k would you choose if a wrong σ made the autopilot trust a bad
  position?
- **Rotation too.** Turn frame 11 by 5° before correlating it with frame 10 and watch the response
  drop. Read about the Fourier–Mellin transform (phase correlation in log-polar coordinates) that
  measures rotation and scale.
