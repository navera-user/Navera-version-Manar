# Lab 23 — Visual odometry on a flight over Sousse

**Goal:** follow a drone through 80 photos using only the slide of the ground between them, measure
how fast the error grows, then add map fixes and watch the error fall back.
**Time:** about 1 hour.

Everything happens in [vo.py](file:./vo.py). It has six small TODOs; the part below the line
`# ---- you don't need to change anything below this line ----` loads the data, runs your functions
on the whole flight and draws the plots.

## Step 1 — Meet the flight

The dataset is a **synthetic flight**: 80 photos cut from the satellite map along a curved path of
1.6 km over the west of Sousse (houses, olive trees, sand, a motorway). Because we made it, we know
the **exact truth** for every photo. Look at the files:

```bash
ls /data/academy/23-visual-odometry
```

```bash
cat /data/academy/23-visual-odometry/info.json
```

`info.json` says the camera is at **110.8 m** (what the barometer says), has a **70°** field of view
and takes **320 px** wide photos, one per second.

```bash
head -5 /data/academy/23-visual-odometry/truth.csv
```

`truth.csv` gives, for each photo, where the drone really was, in meters **east** and **north** of the
first photo (and as lat/lon). You will only use it to **grade** your odometry, never to compute it —
a real drone has no truth file!

Now look at the photos themselves:

```bash
python3 vo.py sheet
```

Open **frames.png** in the editor (file list on the left). Ten photos per row, in flight order. Look
at photos 0 and 1, 1 and 2…: they show almost the same ground, slightly slid. That slide is what you
are going to measure.

> [!NOTE]
> To be realistic, the photos have small defects you are **not told about**, like on a real drone:
> different brightness, a bit of blur and noise, and an IMU whose heading is slightly off. You will
> discover their effect in Step 6.

## Step 2 — Meters per pixel (TODO 1)

> [!TASK]
> Complete `frame_m_per_px(altitude_m, hfov_deg, width_px)`: the footprint width
> `2 × altitude × tan(hfov / 2)` divided by the width in pixels (lesson 17).

`math.tan` works in **radians**: use `math.radians(hfov_deg / 2)`. Test it:

```bash
python3 -c "import vo; print(vo.frame_m_per_px(110.8, 70, 320))"
```

You should see about `0.4849`: each pixel of the photo is a bit less than half a meter of ground.

## Step 3 — Measure the slide (TODO 2)

> [!TASK]
> Complete `frame_shift(prev, cur)` so that it returns `(dx, dy)`, the slide of the ground in pixels
> from `prev` to `cur`, with **phase correlation**.

Follow the three comments in the function:

1. `a = to_grey_float(prev)` and `b = to_grey_float(cur)` (the helper is below the line);
2. a Hanning window of the same size: `cv2.createHanningWindow((width, height), cv2.CV_32F)` — careful,
   OpenCV wants **(width, height)**, and a numpy picture's shape is **(height, width)**:
   `a.shape[1]` is the width;
3. `(dx, dy), response = cv2.phaseCorrelate(a, b, window)` and return `dx, dy`.

Keep the order `(prev, cur)`: swapping them would flip every sign.

## Step 4 — From pixels to meters, with the right signs (TODO 3)

> [!TASK]
> Complete `pixels_to_meters(dx, dy, m_per_px)` so that it returns `(east, north)`, the movement
> of the **drone** in meters.

Use the table of the course: the ground slides the **opposite** way to the drone, and the image y axis
points **down**. Check yourself with two tiny examples on paper before you code:

- ground slid 10 px **left** (`dx = -10`), 0.5 m/px → the drone went **5 m east**: `(5.0, 0.0)`;
- ground slid 10 px **down** (`dy = +10`) → the drone went **5 m north**: `(0.0, 5.0)`.

Now look at one real step:

```bash
python3 vo.py pair 10
```

You should see a slide of about `dx = +15.7 px, dy = +36.9 px` and a drone movement of about
7.6 m **west** (negative east) and 17.9 m **north** — close to what the truth says. Open
**pair_10.png** and find a house that moved between the two photos: does it move the way `dx`, `dy`
say?

> [!TIP]
> If your east/north have the wrong sign compared to the truth, the problem is in TODO 3, not in
> TODO 2: phase correlation measures the *ground*, you want the *drone*.

## Step 5 — Add up the steps and measure the drift (TODO 4 and TODO 5)

> [!TASK]
> Complete `integrate(steps, start)`: a list that starts with `start` and adds each `(east, north)`
> step to the last position. With `n` steps the track has `n + 1` points.

> [!TASK]
> Complete `drift_per_100m(track, truth)`: the distance between the **last** point of your track and
> the **last** true point, divided by the distance **flown** along the truth (the sum of the lengths
> of the true steps, `math.hypot`), times 100.

Then run the whole flight:

```bash
python3 vo.py
```

It measures the 79 steps between the 80 photos, adds them up and prints something like:

```
visual odometry only : final error   55.5 m, worst   55.5 m, drift 3.52 m per 100 m
with_map_fixes(): TODO 6 not done yet — the plots show odometry only
```

Open **vo_track.png**: the black line is the truth, the red one is where your odometry thinks the
drone is. The shape is right, but the red track slowly slides away. Open **vo_error.png**: the error
grows almost in a straight line with the distance — that is **drift**.

> [!QUESTION]
> The error at the end is about 55 m after 1580 m flown. Is it ever going to come back down by itself?

<details><summary>Answer</summary>No. Nothing in odometry knows where the drone really is; each step
only adds to the error. It can only be removed by an absolute position — a map fix.</details>

## Step 6 — Where does the drift come from?

Remember the hidden defects. The barometer says 110.8 m, but the drone really flew at **114.25 m**.
Run the flight again, giving it the true height:

```bash
python3 vo.py --altitude 114.25
```

The drift drops from about 3.5 to about 2.6 m per 100 m: the wrong height made every step about 3 %
too short. The rest comes mainly from the IMU heading being about **2° off**: every step is turned
a little (sin 2° ≈ 0.035, so about 3.5 m sideways per 100 m when the path is straight). Two small,
**systematic** errors — and no amount of careful pixel measurement can remove them.

## Step 7 — Reset the drift with map fixes (TODO 6)

In NAVERA, odometry only bridges the gaps between **map fixes** (lesson 22). The file
`map_fixes.csv` gives a map-matched position every 10 photos (every 200 m) — the true position plus
about 4 m of error, like a real map match:

```bash
cat /data/academy/23-visual-odometry/map_fixes.csv
```

> [!TASK]
> Complete `with_map_fixes(steps, fixes, start)`: like `integrate()`, but after adding step number
> `i`, if `i` is a key of the dictionary `fixes`, the position **becomes** `fixes[i]`; the next steps
> continue from there.

For example `with_map_fixes([(10, 0)] * 4, {2: (0, 0)})` gives
`[(0, 0), (10, 0), (0, 0), (10, 0), (20, 0)]`. Run the flight again:

```bash
python3 vo.py
```

Now you should read about `final error 6.9 m, worst 10.6 m` with fixes. Open **vo_error.png** again:
the blue curve is a **saw** — it grows for 10 photos, falls back at each fix (dotted orange lines),
grows again. Its worst value no longer depends on the length of the flight, only on the distance
between two fixes. This is exactly why NAVERA's day node resets its anchor and its uncertainty at
every accepted map match (`_dead_reckon()` and the code after an accepted match in
`day_subscriber.py`).

## Step 8 — Check your work

Press **✔ Check my work**. It tests each function with small examples, then runs your functions on
the whole flight and compares with the measured reference values (final error about 55 m, drift about
3.5 m per 100 m, worst error with fixes under a third of the odometry-only one).

## Going further (optional)

- **The response.** Change `frame_shift` to print the `response` of phase correlation. Which photos
  give the lowest value? Look at them in frames.png: what kind of ground is it? NAVERA refuses a step
  below 0.08 (`min_response` in `frame_odometry.py`).
- **Fewer fixes.** In `main()` (below the line) keep only every second fix:
  `fixes = {k: v for k, v in fixes.items() if k % 20 == 0}`. How does the worst error change?
  How far apart can the fixes be if the drone must stay within 30 m?
- **Learn the heading bias.** The map fixes also tell you something about the drift itself: compare
  the direction of your odometry between two fixes with the direction between the fixes. Estimate the
  2° heading error, turn every step back by it (east, north → rotate with sin/cos) and see the drift
  drop. Real navigation systems do this kind of on-the-fly calibration all the time.
