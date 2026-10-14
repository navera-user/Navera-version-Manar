# Lab 26 — A position from the stars

**Goal:** write NAVERA Lite's star part (`navera_lite/stars.py`): the clock of the sky, where a star stands,
latitude from Polaris, a star detector in OpenCV, the camera's direction from the IMU, the two roots and the
prior that chooses. Then fly it on six night photos taken at five places and measure what the IMU's attitude
costs.
**Time:** 4 h to 6 h (session 1: 1 h 30–2 h, session 2: 2 h 30–4 h; the detector and the two roots take the
longest if numpy or trigonometry is rusty); a strong programmer who knows numpy and OpenCV: about 3 h.
**Fast track:** if you know numpy and OpenCV well, skip the 🧰 boxes and the "Stuck?" boxes; do "Going
further" at the end.

Your files (📝 Code tab): [navera_lite/stars.py](file:./navera_lite/stars.py) (**your code**: `TODO 1–9`),
[answers.py](file:./answers.py), [report.md](file:./report.md), and a tool you only run:
[run_stars.py](file:./run_stars.py). `navera_lite/imu.py` (your mission 17, finished) gives `q_true_north` and
`declination_deg`; `navera_lite/camera.py` (18) and `rotations.py` (16) are finished too.

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §1 the sky's clock | Steps 1–2 | `julian_date`, `gmst_deg` (TODO 1–2) |
| §2 altitude and azimuth | Step 3 | `altaz` (TODO 3) |
| §3 Polaris | Step 4 | `lat_from_polaris` (TODO 4) |
| §4 star detection | Step 5 | `detect_stars` (TODO 5, OpenCV) |
| §5 plate solving | Step 6 | (given solver: you measure) |
| §6 two frames, two roots | Steps 7–8 | `boresight_altaz`, `both_roots`, `choose` (TODO 6–8) |
| §7 error budget | Step 9 | `error_km` (TODO 9) |
| all | Step 10 | the star-fix memo |

> [!NOTE]
> **The data** (`/data/academy/26-stars/`, described in its README): a public star catalogue (the HYG database v4.1 by D. Nash / astronexus, CC BY-SA 4.0 — share-alike: a copy or change of it must keep the same licence; 8 920 stars
> brighter than magnitude 6.5, J2000), and six **synthetic** night photos from NAVERA Lite's star camera
> (1280 × 960, 60° wide, its axis leaning 20° towards the drone's nose), rendered for the course with exact
> truth. `photos.json` gives, for each photo, the UTC time, the IMU chip's attitude at the exposure (magnetic
> north, with BNO085-class errors), a prior and the truth.
>
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step; it is never
> marked right or wrong. `python3 run_stars.py test` tries every docstring example (and a few traps). Angles
> are in degrees at every interface.

## Session 1 — Stargazer (about 1 h 30; 2 h if spherical trigonometry is new)

## Step 0 — The sky's clock

No code, no lesson yet.

> [!TASK]
> **Predict** (`PREDICT_SIDEREAL` in `answers.py`): tonight a bright star is due south at exactly 21:00. At
> what time will it be due south tomorrow night: 21:00, a little earlier, or a little later? Write one reason.
> Save the file (`Ctrl+S`). Then read lesson §1–§3.

## Step 1 — The star catalogue

```bash
python3 run_stars.py look
```

It counts the stars by magnitude (smaller = brighter) and lists the brightest. Later, the plate solver
(Step 6) votes only with stars brighter than magnitude 4.5. How many are there? Count them yourself.

<details><summary>🧰 numpy: count with a mask</summary>

```python
import numpy as np
m = np.array([1.2, 4.6, 3.0, 4.5, 5.9])
m <= 4.5                        # array([ True, False,  True,  True, False])
int((m <= 4.5).sum())           # 3 — True counts as 1
```
In the terminal: `python3 -c 'from navera_lite.stars import load_catalogue; cat = load_catalogue(); print(…)'`,
with the count of `cat["vmag"] <= 4.5` in place of `…`. Mind the quotes: **single quotes outside**, double
quotes inside (double inside double ends the command early).
</details>

> [!TASK]
> Write `N_VOTE_STARS`: the number of catalogue stars with `vmag ≤ 4.5`.

## Step 2 — The clock of the sky (TODO 1, TODO 2)

Open the 📝 Code tab, then `navera_lite/stars.py`. Read the conventions at the top. Each `TODO` function keeps
its docstring and ends with `return None   # TODO…`: replace that line with your code.

**TODO 1** `julian_date(y, mo, d, h=0, mi=0, s=0.0)`: lesson §1, the recipe. **TODO 2** `gmst_deg(jd)`: the
IAU formula of §1, written with numpy operations so that it also works on an array of dates.

<details><summary>🧰 Python: whole-number parts, and the remainder of a division</summary>

```python
import math
math.floor(7.9), math.floor(-0.5)     # (7, -1) — rounds DOWN, also below zero
365.7 % 360.0, -10.0 % 360.0          # (5.7, 350.0) — always in [0, 360)
```
</details>

```bash
python3 run_stars.py test
```

The lines of TODO 1 and 2 must be ✔ (the other TODOs show "not written yet").

```bash
python3 run_stars.py clock
```

**Before running it**, predict `TRANSIT_SHIFT_S` from lesson §1 (one line of arithmetic) and write it in
`answers.py`: the run only confirms it. `clock` prints Julian dates and sidereal times, finds when Vega crosses
the meridian of Sousse on two nights in a row (with your two functions), and shows how far precession has moved
three stars since J2000.

> [!TASK]
> Check your `TRANSIT_SHIFT_S` against the run (seconds earlier the next night). `VEGA_SHIFT_ARCMIN`: how far
> precession moved Vega (in ′). `VEGA_SHIFT_KM`: that angle as a distance on the Earth (lesson §7: 1′ = 1.852 km).
> `EXPLAIN_SIDEREAL`: why does the sky's clock gain on yours, and why does it matter for a star fix? And: Polaris'
> **right ascension** moved 8.8°, but Polaris moved only 9.1′ on the sky. Why? (One degree of ra is cos δ
> degrees on the sky.)

<details><summary>Stuck? Hints, one at a time</summary>

1. `julian_date`: four lines of the lesson's recipe. Start with the January/February rule, then A, B, then
   the sum. The time of day is `(h + mi / 60 + s / 3600) / 24` days.
2. ✘ "0.5 day short": the hours are not added. ✘ "13 days off": B is missing. ✘ "Jan/Feb": the year must be
   decreased by one AND the month increased by 12, before A is computed.
3. `gmst_deg`: `d = np.asarray(jd, dtype=float) - 2451545.0`, `T = d / 36525.0`, the formula, then `% 360.0`.
   Return a float for one date (`float(g)`) and the array for an array.
4. ✘ a number in the millions: the `% 360.0` is missing. ✘ 22.45: you divided by 15 (hours); the function
   returns degrees.
</details>

## Step 3 — Where is that star? (TODO 3)

**TODO 3** `altaz(ra_deg, dec_deg, lat, lon, gst_deg)`: lesson §2. H = gst + lon − ra, then the two formulas.
ra and dec may be arrays (the runner sends 1 637 stars at once).

<details><summary>🧰 numpy: one formula for a whole array</summary>

```python
ra = np.array([10.0, 200.0])
np.sin(np.radians(ra))                 # array([ 0.1736, -0.3420]) — math.sin would fail on an array
np.degrees(np.arctan2([1.0, -1.0], [0.0, 0.0])) % 360.0     # array([ 90., 270.])
np.ndim(np.float64(3.0)), np.ndim(ra)  # (0, 1) — 0 for a single number
```
</details>

```bash
python3 run_stars.py test
```

Then the sky over **Cape Town** on 20 October 2026, 20:00 UTC (22:00 local time).

> [!TASK]
> **By hand first** (`PREDICT_ACHERNAR`): Achernar has δ ≈ −57.1° (of date). How high does it stand at its
> highest, seen from Cape Town (φ = −33.92°; lesson §2's ✏️ check has the rule)? Tonight's table will show a
> lower altitude: from its azimuth, is Achernar before or after its transit? Then:

```bash
python3 run_stars.py sky capetown
```

Open `out/sky_capetown.png` (centre = zenith, north up, east to the RIGHT as on a map; a star chart held
over your head shows east on the left). You may also try `sousse`, `reykjavik`, `quito`, `sydney`.

> [!TASK]
> Write `ACHERNAR_ALT_DEG` and `ACHERNAR_AZ_DEG` (Cape Town, from the table). Where is Polaris for Cape Town?

<details><summary>Stuck? Hints</summary>

1. Convert everything to radians: `ra, dec = np.radians(…)`, `phi = np.radians(lat)`, and
   `H = np.radians(gst_deg + lon) - ra`.
2. `alt = np.degrees(np.arcsin(…))`; `az = np.degrees(np.arctan2(num, den)) % 360.0`, with num and den from
   the lesson, in that order.
3. ✘ "the azimuth goes the wrong way round" or "measured from south": compare your num and den with lesson §2.
   ✘ "the longitude has the wrong sign": LST = gst + lon (east positive), H = LST − ra.
4. ✘ "only length-1 arrays can be converted": a `math.` function got an array: use `np.`.
   ✘ "the azimuth is negative": `% 360.0` at the end of the azimuth line.
5. Return `(float(alt), float(az))` for one star; the arrays themselves for arrays (`np.ndim(alt) == 0` tells
   them apart).
</details>

## Step 4 — Latitude from Polaris (TODO 4)

**TODO 4** `lat_from_polaris(alt_deg, ha_deg=None, p_deg=POLARIS_P_DEG)`: lesson §3.

```bash
python3 run_stars.py test
```

`polaris` measures Polaris every 30 minutes through one night from Reykjavik, London, Sousse and Singapore
(with your `altaz`, as a perfect sextant would, without refraction), and finds the latitude both ways.

> [!TASK]
> **Predict** (`PREDICT_POLARIS`): with the hour-angle correction, which of the four places will keep the
> largest latitude error, and why? Then:

```bash
python3 run_stars.py polaris
```

> [!TASK]
> Write `NAIVE_MAX_ERR_KM` and `CORRECTED_MAX_ERR_KM`: the largest error of each column (all places).
> `EXPLAIN_POLARIS`: why is the naive error about that size, what does the correction remove, and why is the
> corrected error largest where it is?

<details><summary>Stuck? Hints</summary>

1. Two cases: `ha_deg is None` → the altitude itself; otherwise the lesson's formula.
2. ✘ "the correction has the wrong sign": at H = 0 Polaris is ABOVE the pole, so the pole (your latitude) is
   lower than Polaris. ✘ "cos got degrees": `math.cos(math.radians(ha_deg))`.
</details>

> [!TIP] 🏅 End of session 1 — Stargazer
> Press **✔ Check my work**. When the checks of TODO 1–4 and Steps 1–4 pass (checks 1–6; the others are
> session 2), you earn the **Stargazer** badge. If the class session ends here, stop here.

## Session 2 — Star navigator (2 h 30–4 h; the longer end if OpenCV or trigonometry is new)

Read lesson §4–§7 first.

## Step 5 — Find the stars (TODO 5)

**TODO 5** `detect_stars(gray, k_sigma=5.0, min_area=3, max_area=150)`: lesson §4, the five steps and its 🧰
box. Your first OpenCV detector: background, robust σ, threshold, groups, sizes, weighted centres, sorted.

> [!TASK]
> **Predict** (`PREDICT_DETECT`): photo 1 holds 121 catalogue stars brighter than magnitude 5.0, and 40 hot
> pixels. How many of the 121 will your detector find, and how many hot pixels will it report as stars? Why?

```bash
python3 run_stars.py test
```

```bash
python3 run_stars.py detect
```

Open `out/detect_01.png` (circles = your stars; the right panel zooms on the brightest, + = your centre). Then
photo 2, which has a glowing corner and an aircraft trail (the runner counts the stars found in the corner
and the detections that are not stars):

```bash
python3 run_stars.py detect 2
```

> [!TASK]
> Write `N_STARS_01` (how many stars your detector finds in photo 1) and `CENTROID_RMS_PX` (the RMS centre
> error against the truth). `EXPLAIN_CENTROID`: why weight the centre by brightness, and why do the size limits
> and the local background matter (photo 2)?

<details><summary>Stuck? Hints, one at a time</summary>

1. The shape: `g = np.asarray(gray, dtype=np.uint8)`; `bg = cv2.medianBlur(g, 21)`; `resid = g.astype(float) -
   bg` (float first!); `sigma` = the robust σ of `resid` (🧰 box); `mask = resid > k_sigma * sigma`.
2. `n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)`. Label 0 is
   the background: skip it. `stats[i, cv2.CC_STAT_AREA]` is the size of object i.
3. For the weighted centre of every object at once: `w = np.where(labels > 0, resid, 0.0)`;
   `rows, cols = np.indices(g.shape)`; `np.bincount(labels.ravel(), weights=…)` gives per-object sums of `w`,
   `w * cols` and `w * rows`. Centre = sum(w·col) / sum(w). (A loop over the objects with `labels == i` also
   works; it is slower.)
4. Keep the objects with `min_area ≤ area ≤ max_area`, stack `(u, v)` = (column, row), sort with
   `np.argsort(-flux)`. No object → `np.zeros((0, 2)), np.zeros(0)`.
5. ✘ "(4.0, 4.0) is the plain centre": you used the centroids of `connectedComponentsWithStats`; weight by
   `resid`. ✘ "u and v are swapped": u is the column. ✘ "the hot pixel was kept": the size limits.
   ✘ the runner says "sort the stars BRIGHTEST FIRST": `np.argsort(-flux)`.
6. **Thousands of detections** on photo 1, or ✘ "on a grey, noisy sky"? You subtracted two uint8 arrays:
   19 − 20 = 255 on uint8. Write `g.astype(float) - bg`.
7. Photo 2 loses the stars of the bright corner, or `detect` reports a few detections far from every star? Your
   background is not local (a fixed threshold?) or the trail is kept (max_area).
</details>

## Step 6 — Which stars are these?

The given `plate_solve` (lesson §5) identifies your detections and finds where the image centre points.

> [!TASK]
> **Predict** (`PREDICT_PIXEL`): the camera is 60° wide on 1 280 pixels, so one pixel is 60°/1280 = 2.81′ on
> average. Is one pixel at the image **centre** 2.81′, more, or less? Use K: f = 640 / tan 30° = 1108.5 px.
> Then:

```bash
python3 run_stars.py solve
```

Open `out/solve_01.png`: the green circles are identified stars, the red + the image centre.

> [!TASK]
> Write `SOLVE_RMS_ARCSEC` (the fit residual) and `PIXEL_ARCMIN` (one pixel at the image centre, printed). Was
> your prediction right? Why do the pixels near the edge cover less sky?

## Step 7 — Where does the camera point? (TODO 6)

**TODO 6** `boresight_altaz(q_body, cam_axis_body=CAM_AXIS_BODY)`: lesson §6, first paragraph. Rotate the
camera's axis into the world (ENU) frame with mission 16's `q_rotate` (imported at the top of stars.py); its
altitude is the angle above the horizon (from the Up part), its azimuth is clockwise from north (East and North
parts: which one goes first in atan2?).

```bash
python3 run_stars.py test
```

<details><summary>Stuck? Hints</summary>

1. `v = np.asarray(q_rotate(q_body, cam_axis_body), dtype=float)`, then normalise it.
2. `alt = math.degrees(math.asin(v[2]))`; azimuth = `math.degrees(math.atan2(v[0], v[1])) % 360.0` (east, north:
   a heading).
3. ✘ "measured from EAST": you wrote atan2(north, east). ✘ "you rotated (0, 0, 1)": rotate `cam_axis_body`.
</details>

## Step 8 — Two roots, one prior (TODO 7, TODO 8)

**TODO 7** `both_roots(alt_deg, az_deg, ra_deg, dec_deg, gst_deg)`: lesson §6, the general case.

> [!TASK]
> **Before you code**, trace the docstring example by hand (lesson §6's table shows the method with other
> numbers): a = 37.13°, A = 295.02°. Write `TRACE_PSI_DEG`: ψ in degrees (ψ = atan2(q, p): q first).

**TODO 8** `choose(roots, prior_lat, prior_lon, max_sep_deg=5.0)`: lesson §6, "Choosing". The given
`sep_deg(lat1, lon1, lat2, lon2)` measures the angle between two places (on the sphere, so it is right across
the 180° meridian and near the poles).

```bash
python3 run_stars.py test
```

<details><summary>Stuck? Hints for TODO 7</summary>

1. Radians: `a, A, dec = math.radians(…)`; `p = math.sin(a)`, `q = math.cos(a) * math.cos(A)`,
   `R = math.hypot(p, q)`, `psi = math.atan2(q, p)`.
2. If `abs(math.sin(dec)) > R` there is no solution: return `[]`. Else `x = math.asin(math.sin(dec) / R)`.
3. Loop over `x` and `math.pi - x`: φ = that − ψ, wrapped to [−π, π); skip it if |φ| > π/2. Then H with
   `math.atan2(…)` (lesson §6), and λ = α + H − gst in degrees, wrapped to [−180, 180):
   `(lon + 180.0) % 360.0 - 180.0`.
4. ✘ "only one root": both x and 180° − x. Keep the asin root first.
5. Your roots have the right latitudes but wrong longitudes? Check the sign in λ = α + H − gst, and H's atan2
   (num = −cos a · sin A).
</details>

```bash
python3 run_stars.py fix
```

For each photo: your detections, the plate solve, the chip's attitude turned to true north (`q_true_north` with
the WMM declination at the prior), your boresight, your two roots and your choice, and the error against the
truth. Open `out/fix_imu.png`.

> [!TASK]
> Write `MEDIAN_FIX_KM` (the median error) and `NO_FIX_PHOTO` (the photo number that gives no position). Then
> with a perfect IMU:

```bash
python3 run_stars.py fix truth
```

> [!TASK]
> Write `PERFECT_MAX_KM` (the largest error with the true attitude).

> [!NOTE] Why 0.2 km here and 5.5–6.5 km in NAVERA?
> These photos are **synthetic**: they were drawn with the same sky model your code uses (precession, GMST, an
> ideal pinhole), without refraction, aberration, nutation or lens distortion. So with a perfect attitude only
> your centroids are left: 0.2 km. That tests your **code**, not the sky. A real system adds (camera 55–66° high):
> refraction 0.8–1.3 km (3 km at 30°), aberration ≤ 0.6 km, nutation ≤ 0.5 km, the clock 0.46 km per second, and
> above all its plate solver's own error. NAVERA's astrometry.net fit is 2.9′ at the centre, i.e. 5.4 km: most of
> its 5.5–6.5 km. Next to the IMU's 50–120 km, all of this is still small. (Going further measures refraction.)

> [!TASK]
> **Predict** (`PREDICT_MAGNETIC`): if the declination is forgotten (about +3.3° near Sousse, camera about 66° high),
> how many km does photo 1's fix move? Use lesson §7's rule. Then:

```bash
python3 run_stars.py fix magnetic
```

```bash
python3 run_stars.py fix oneroot
```

`oneroot` does what NAVERA's first code did: it keeps only the asin root and no prior check.

> [!TASK]
> Write `MAGNETIC_MOVE_01_KM` (how far photo 1's fix **moved** from `fix`: compare it with your prediction),
> `MAGNETIC_ERR_01_KM` (photo 1's error to the truth, declination forgotten) and `ONE_ROOT_ERR_03_KM` (photo 3,
> one root). `EXPLAIN_ROOTS`: why can one direction give two places, why is the asin root wrong for photo 3,
> and why does photo 6 give no position? `EXPLAIN_NORTH`: the move against your prediction, and why the
> **error** is larger still (which two things add up)? Why do photos 3–5 then give no position at all? (Photo 1's
> move is about 1.3 × the rule, photo 2's about the rule: lesson §7's box explains why — read it after Step 9.)

## Step 9 — The error budget (TODO 9)

**TODO 9** `error_km(tilt_deg, heading_deg=0.0, alt_deg=90.0)`: the least guided TODO. Lesson §7 has the rule;
the docstring has an example: do it by hand first, then code it.

```bash
python3 run_stars.py test
```

`budget` disturbs photo 1's true attitude 2 000 times with BNO085-class errors (σ 0.3° on roll, 0.3° on pitch,
1.5° on heading), runs your fix each time, and compares with your `error_km`.

> [!TASK]
> **Predict** (`PREDICT_BUDGET`): will the measured RMS error be close to your formula, above it, or below it?
> And the median? Then:

```bash
python3 run_stars.py budget
```

Open `out/budget.png`.

> [!TASK]
> Write `FORMULA_KM`, `MC_RMS_KM` and `MC_MEDIAN_KM` from the run. **Your role: the integrator who mounts the
> star camera.** A mounting error is a fixed tilt (a bias), not noise. With a perfect IMU, how large may it be so
> that the fix stays within 55 km? Write `MOUNT_BIAS_MAX_DEG` (degrees, 3 decimals). `EXPLAIN_BUDGET`: which error term dominates for
> photo 1, why the median is smaller than the RMS, and why the formula and the simulation differ.

<details><summary>Stuck? Hints</summary>

1. One line: `KM_PER_DEG` × the square root of tilt² + (heading × cos(alt))², with alt in radians inside cos.
2. ✘ "added": independent errors combine as √(a² + b²). ✘ "not multiplied by cos": the heading term.
3. `MOUNT_BIAS_MAX_DEG`: with no heading error, error_km(t) = 55 km: solve for t.
</details>

## Step 10 — The star-fix memo

Write [report.md](file:./report.md) (150–350 words, your own words, keep the three headings): how the sky's
clock and your formulas place a star; how a photo and the IMU become a position (detection, plate solve, two
roots, the prior); how good the fix is and what limits it. Quote your numbers with their units.

> [!TASK]
> report.md has the three headings, 150–350 words, and quotes the median fix error with the IMU (km), the
> largest error with a perfect attitude (km), and the cost of one degree of attitude (km).

## Step 11 — Check, then look back

Press **✔ Check my work**: it tests your functions on dates, stars, images, attitudes and roots it has never
seen. When every check passes, you earn the **Star navigator** badge. Then look back, without the lesson:

1. Explain to a colleague, in three sentences, how a star photo and an IMU give a position.
2. Which of your predictions was the most wrong? What did you assume?
3. NAVERA calls the celestial fix "coarse". After this lab, what would you use it for, and what not?

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **The unweighted centre.** Change `detect_stars` to use the plain centres of `connectedComponentsWithStats`
  (keep a copy of yours!) and run `detect` again. How much worse is the RMS, and how much does `fix truth` change?
- **The fold.** Run `budget` on photos 3, 4 and 6 (`python3 run_stars.py budget 3`, …). Compute each
  boresight's hour angle H = GMST + λ − α. Which photo is worst, and why is it not the one nearest the pole?
  Read lesson §7's box after Step 9.
- **Refraction, measured.** The air lifts every star (Bennett's rule: about 1′ × cot(alt + 7.31/(alt + 4.4))).
  So the stars at the image centre truly stand R lower than where the camera points: the plate solve's direction
  is R below the IMU's altitude. A fix that ignores it is off by that angle. `python3 run_stars.py fix truth refraction` puts it in. How many km for photo 1
  (66° high) and photo 3 (55°)? Worth correcting next to a 50 km IMU error? Next to a levelled camera with a
  0.05° attitude (5.6 km)?
- **The whole rotation (about 20 lines).** `plate_solve` also returns `R_eq_cam` (camera → sky). Write
  `fix_zenith(sol, q, gst)`: the vertical in the body frame `up_body = q_rotate(q_conj(q), (0, 0, 1))`, into the
  camera frame and onto the sky `z = sol["R_eq_cam"] @ R_BODY_STAR_CAM.T @ up_body`, `ra, dec = vec_to_radec(z)`,
  then lat = dec, lon = ra − gst wrapped (lesson §6, last paragraph). Write it in a new file `zenith.py` next to
  `run_stars.py`: `from navera_lite.rotations import q_conj, q_rotate`, `from navera_lite.stars import
  R_BODY_STAR_CAM, vec_to_radec, sep_deg, KM_PER_DEG`, `import run_stars as rs`; then for n in 1–6:
  `_, p, _, _, _, jd, sol, _ = rs.solve_photo(n)`, `q = p["chip_q"]`, `gst = rs.gst_of(jd)`, and compare your
  (lat, lon) with `p["truth"]["lat"], p["truth"]["lon"]` (`sep_deg(…) * KM_PER_DEG`). Run `python3 zenith.py`
  with the chip's attitude **as delivered** (magnetic!). Which photos improve? Does photo 6 give a position now? Does the
  declination still matter, and why? (Reference: errors 38–56 km, photo 6 included.)
- **The stretch factor (maths).** Moving the observer by (dφ north, dλ east) turns the local frame by
  ω = (−dφ, dλ cos φ, dλ sin φ) (ENU). A heading error is ω = (0, 0, Δ). The star stays put if the difference is
  parallel to the star's direction s. Solve for dφ, dλ and show that the move is Δ cos a cos φ / |s_U cos φ −
  s_N sin φ|, i.e. Δ cos a · cos φ / (cos δ |cos H|). Check it on photo 1 (about 59 km per degree of heading).
  Then repeat with a tilt about the horizontal axis along the camera's azimuth, ω = ε·(sin A, cos A, 0): what
  changes? (Photo 1: ×1.19 = sin 66° × 1.30.)
- **A zenith camera.** Change `CAM_AXIS_BODY` to (0, 0, 1) for a test of the easy case of lesson §6: does the
  heading still matter?
- **Fly your own parts.** This mission ships the course's `imu.py`. Copy yours over it
  (`cp ../17-imu/navera_lite/imu.py navera_lite/`) and run `python3 run_stars.py fix`.
