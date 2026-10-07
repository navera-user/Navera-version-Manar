# Counting your steps with a camera: visual odometry

A drone has lost its GPS over the edge of Sousse. Until now, NAVERA's day vision found it on the
satellite map every second or two (lesson 22). Then the drone flies over a building site: the map
photo was taken years ago, the ground has changed, and **no match is accepted for 30 seconds**.
At 15 m/s, that is 450 m flown "blind". Where is the drone now?

Close your eyes and walk across your classroom. You can still say roughly where you are: you
**count your steps** and you know which way you turned. That is **odometry** (from Greek *hodos*,
the way, and *metron*, measure). A car counts the turns of its wheels. A drone has no wheels — but
it has a camera looking at the ground. If it can measure how far the ground moved between two photos,
it can count its "steps" with its eyes. That is **visual odometry** (VO).

In this lesson you will learn how it works, why it is never perfect, and how NAVERA uses it **only
between two map fixes**.

## Two photos, one step

A camera looking straight down takes a photo every second. If the drone moves 20 m between two
photos and each photo covers 160 m × 120 m of ground, the two photos show **mostly the same ground**:
they **overlap**. The houses of photo 1 are still in photo 2 — only a bit lower, a bit to the side.

![The drone flies north-east: the ground in its photo slides south-west](assets/slide.svg)

The key idea fits in one sentence:

> **The ground slides in the picture the opposite way to the drone.**

Think of looking out of a train window: the trees rush backwards while you go forwards. If the drone
flies north (towards the top of a north-up photo), the houses slide **down** the picture; if it flies
east (right), they slide **left**.

So visual odometry has three small jobs:

1. measure the **shift** of the picture between two photos, in pixels: `(dx, dy)`;
2. turn pixels into meters with the **meters per pixel** of the camera (lesson 17);
3. turn "the ground slid left and down" into "the drone moved east and north", and **add** this
   step to the position.

## Measuring the slide: phase correlation

How do you measure how much a picture slid? A simple (but slow) way: put photo 2 on top of photo 1,
then try every possible shift — 1 px right, 2 px right, 1 px up… — and for each shift measure how
well the two pictures agree. The best shift is the slide.

OpenCV does exactly this, but smartly, with a trick called **phase correlation**. It uses the
**Fourier transform** (a mathematical tool that describes a picture as a sum of waves) to test
**all shifts at once**, in a few milliseconds. You don't need the maths: you need to know what goes
in and what comes out.

```python
(dx, dy), response = cv2.phaseCorrelate(a, b, window)
```

| What | Meaning |
|---|---|
| `a`, `b` | the previous and the current photo, in grey, as `float32` numbers (lesson 8) |
| `window` | a **Hanning window**: a mask that fades the picture to black near its edges, so the borders (which never match) do not confuse the result |
| `dx`, `dy` | how many pixels the content of `b` moved compared to `a`: `dx > 0` means **right**, `dy > 0` means **down** (the image y axis points down!) |
| `response` | how sure it is, from 0 to 1. Two photos of the same textured ground give a high response; two photos of the sea give a very low one |

Phase correlation is very precise — a fraction of a pixel — but it only measures a **slide**
(a translation). If the picture is also turned or zoomed between the two photos, it gets confused.
That is why NAVERA first turns and scales the previous photo to match the new one, using the heading
change from the IMU and the height change (see "In NAVERA" below).

> [!NOTE]
> Another way to measure the motion is with the **features** of lessons 20 and 21: find keypoints
> in both photos, match them, and fit a transformation with RANSAC (`cv2.estimateAffinePartial2D`).
> It also measures rotation and scale, and works with less overlap, but it is slower. Both are
> good tools; NAVERA uses phase correlation for odometry because it is fast and the IMU already
> knows the rotation.

## From pixels to meters

The camera's **meters per pixel** come from lesson 17. A camera at height *h* with a horizontal
field of view *hfov* sees a strip of ground

  footprint width = 2 × h × tan(hfov / 2)

wide; divide by the image width in pixels and you have the ground size of one pixel. Our drone flies
at about 114 m with a 70° camera and 320 px wide photos: 2 × 114 × tan(35°) / 320 ≈ **0.50 m per
pixel**.

Now the signs. The photos are **north-up**: the top of the picture points north (NAVERA turns every
photo that way using the heading measured by the IMU, lesson 16). Then:

| The ground in the picture slid… | so the drone moved… | in numbers |
|---|---|---|
| left (`dx < 0`) | **east** | east = −dx × m_per_px |
| right (`dx > 0`) | west | |
| down (`dy > 0`) | **north** | north = +dy × m_per_px |
| up (`dy < 0`) | south | |

Example: the ground slid `dx = −10` px and `dy = +40` px, at 0.5 m per pixel. The drone moved
5 m east and 20 m north.

## Adding up the steps

One step tells you how far the drone moved in one second. To know **where** it is, you start from a
known position and add the steps one after the other:

```
position[0] = start
position[1] = position[0] + step[0]
position[2] = position[1] + step[1]
...
```

The list of positions is the **track**. Sailors did exactly this for centuries with a compass, a
clock and a log line to measure the speed: they called it **dead reckoning**.

![Visual odometry, one photo after the other](assets/chain.svg)

## Drift: why counting steps always goes wrong in the end

Walk across the classroom blindfolded, then open your eyes: you are close, but not exactly where you
thought. And the longer you walk, the farther off you are. Every step adds a small error, and
**the errors add up — they never cancel by themselves**. This growing error is called **drift**.
You met it in lesson 16: integrating a gyroscope gives a heading that slowly drifts away. Visual
odometry drifts too, for the same reason: it **integrates** (adds up) small measurements.

Where do the small errors come from?

| Cause | What it does | Example |
|---|---|---|
| **wrong height** | every step is too short or too long by the same percentage | the barometer says 110.8 m, the truth is 114.25 m: every step is 3 % too short → 3 m of error per 100 m |
| **wrong heading** | every step is turned a little | a 2° compass error moves you sideways by sin 2° ≈ 0.035 → 3.5 m per 100 m |
| **noise, blur, light changes** | each shift is off by a fraction of a pixel, randomly | small; random errors partly cancel |
| **bad frames** | a cloud, the sea, a blurry photo: no shift can be measured | the step is missing, or wrong |

The first two are **systematic** errors: the same mistake at every step, so the error grows in
proportion to the distance. That is why engineers measure odometry in **meters of error per 100 m
flown** (or "percent of the distance"). A good visual odometry drifts a few meters per 100 m — fine
for 200 m, useless for 20 km.

> [!QUESTION]
> A drone drifts 3 m per 100 m. How far off is it after 1.5 km? After 50 km?

<details><summary>Answer</summary>About 45 m after 1.5 km, and about 1.5 km after 50 km —
no longer useful to land on a parcel locker.</details>

## The cure: a map fix now and then

Visual odometry tells you **how you moved**, not **where you are**. Map matching (lesson 22) tells
you where you are, with an error of a few meters that **does not grow** — but it fails sometimes
(changed ground, uniform terrain, a bad frame).

So NAVERA uses both, like a hiker who counts steps between the signposts:

- when the map gives a **fix** (a matched position), the position **is** that fix: the drift is
  thrown away and the counting starts again from there;
- between two fixes, visual odometry carries the position forward, step by step, and the
  uncertainty grows with the distance.

![The error with odometry alone, and with a map fix now and then](assets/drift.svg)

The error then looks like a **saw**: it grows a little, falls back at each fix, grows again. Its worst
value depends on how long the drone flies between two fixes — not on the length of the whole flight.
In the lab you will measure both curves on a synthetic flight over Sousse.

## When visual odometry cannot work

Visual odometry needs **fixed, textured ground** that both photos share:

- **over the sea** there is nothing fixed to follow: the waves move and look all alike, the response
  stays low and the result must not be used;
- **uniform ground** (sand, a big field, a snow-white roof) gives a weak, unreliable peak;
- **too fast or too low**: if two photos overlap by less than about half, there is not enough
  common ground;
- **turns**: if the picture turns between two photos and nobody corrects it, phase correlation is lost.

That is why the **response** matters: a careful program uses a step only when it is sure.

## 🐦 How birds do it

Counting your own motion to know where you are is called **path integration** — dead reckoning.
Animals do it, and it has the same weakness as visual odometry: small errors add up.

You met it in lesson 6: the famous experiment of the Dutch scientist **A. C. Perdeck**,
published in 1958. Look at it again with visual odometry in mind. Every autumn, starlings from around the Baltic fly south-west across the
Netherlands to spend the winter in Belgium, northern France and southern England. Perdeck caught
thousands of them in the Netherlands, put a ring on each one, carried them by plane to
**Switzerland** and released them there. Rings found later told where they had gone.

- The **young** starlings, on their first migration, simply kept flying **south-west**, the same
  direction and roughly the same distance as before. They ended up in **Spain and southern France**
  — the wrong place. They had only a "compass and distance" program, like pure dead reckoning.
- The **adults** corrected: many flew **north-west**, back towards their usual wintering areas.
  They had something the young ones did not: a **map** learned from experience.

That is visual odometry versus a map fix. Counting steps alone can take you far, but if something
moves you (wind, a wrong start, a bad step), nothing brings you back. A map fix now and then resets
the error to zero. Navi, a young swallow on her first trip, would do well to grow up into an "adult"
navigator — and so does NAVERA, which mixes both.

## In NAVERA

### `day_pkg/day_pkg/frame_odometry.py` — the visual odometry

Open [frame_odometry.py](file:navera/day_pkg/day_pkg/frame_odometry.py). It is only 56 lines and you
can now read all of it. The heart of `FrameOdometry.step()`:

```python
# the previous frame turned into this one's orientation and scale (heading change, height change)
dturn = (hdg - phdg + 180.0) % 360.0 - 180.0
R = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), dturn, pmpp / m_per_px)
pg = cv2.warpAffine(pg, R, (w, h), flags=cv2.INTER_LINEAR)
...
(dx, dy), resp = cv2.phaseCorrelate(a, b, self._win)
if resp < self.min_response or abs(dx) > w / 3 or abs(dy) > h / 3:
    return None
mpp = m_per_px / self.scale
right, fwd = -dx * mpp, dy * mpp                  # the ground moved the other way
th = math.radians(hdg)
de = fwd * math.sin(th) + right * math.cos(th)
dn = fwd * math.cos(th) - right * math.sin(th)
```

You will recognise every line:

- the previous photo is first **turned by the heading change** measured by the IMU and **scaled by
  the height change**, so that only a slide remains;
- `cv2.phaseCorrelate` with a Hanning window (`self._win`), exactly as in your lab;
- a step is refused when the **response is below `min_response` (0.08)** — over open water — or
  when the slide is more than a third of the picture;
- `right, fwd = -dx * mpp, dy * mpp`: the same sign rule as yours ("the ground moved the other way");
- NAVERA's photos are not always north-up (the top of the photo points where the drone flies), so the
  last two lines turn (right, forward) into (east, north) with the heading, using sin and cos —
  with a heading of 0° (photo top = north) they give back exactly your rule.

### `day_pkg/day_pkg/nodes/day_subscriber.py` — between two map fixes

When a frame gives no map match, the day node calls `_dead_reckon()`. If visual odometry measured
this frame's step, the last position (the **anchor**) is moved by it, and the stated uncertainty
grows:

```python
de, dn, dt, q = vo
lat, lon = _move((self._anchor_lat, self._anchor_lon), de, dn)
sigma = self._dr_sigma + 0.1 * math.hypot(de, dn) + 1.0
if sigma <= self.dr_max_sigma_m:
    ...
    self._emit_fix(now, seq_id, lat, lon, meta, status, "dead_reckon", ...)
```

So each step **adds 10 % of its length plus 1 m** to the uncertainty (σ, "sigma") — a careful
guess, larger than the 3–4 m per 100 m you will measure, because real flights are worse than a
synthetic one. These positions are published as **PROPAGATED** (dead-reckoned), never as measured.
Dead-reckoning stops after `max_dead_reckon_s` (**120 s**) or when the uncertainty passes
`dead_reckon_max_sigma_m` (**500 m**): then NAVERA says "no position" rather than a wrong one.
When a map match is accepted again, the anchor jumps to it and `_dr_sigma` is reset to the match's
own small sigma: **the drift is thrown away at each map fix**.

### `day_pkg/day_pkg/vision_nav.py` — the search follows the uncertainty

[vision_nav.py](file:navera/day_pkg/day_pkg/vision_nav.py) holds the rules between matches
(`VisionNavigator`). `odometry()` turns each visual-odometry step into a **measured velocity**;
`predict()` carries the last fix along that velocity and grows its sigma with time; `search()`
makes the next map search circle **3 sigma** wide (never less than 80 m, never more than 1500 m).
A lost drone is searched for in a wider circle — and as soon as a match is found, the circle
shrinks again.

### What has been measured

From `docs/VALIDATION_STATUS.md`, for day vision carrying its position along the measured track when
no frame matches (**simulator only**, mission simulator with GPS jammed): on a land route the error
stayed at a **median of 10 m, max 33 m**, with no autopilot failsafe; across the bay, the position
was carried **90 s over the sea stating ±300 m, with a true error of at most 146 m**. Those
numbers are for carrying the position along the velocity measured before the gap; the frame-to-frame
odometry of `frame_odometry.py` was added after (bench campaign of 2026-10-06), and no separate
figure for it is listed yet. None of this has been measured on a real flight.

## Words to remember

| Word | Meaning |
|---|---|
| **odometry** | measuring your own movement step by step (wheels, steps, camera) |
| **visual odometry (VO)** | odometry from the slide of the ground between consecutive photos |
| **overlap** | the part of the ground two photos both show |
| **phase correlation** | a fast way to find the slide between two pictures, testing all shifts at once |
| **Hanning window** | a mask that fades the picture near its edges before phase correlation |
| **response** | how sure phase correlation is (0–1); low over the sea |
| **track** | the list of positions, one per photo |
| **dead reckoning** | carrying a position forward from known movements, without seeing where you are |
| **drift** | the error of dead reckoning, growing with time / distance |
| **systematic error** | the same mistake at every step (wrong height, wrong heading): it adds up |
| **map fix** | an absolute position from the map (lesson 22); it resets the drift |
| **PROPAGATED** | NAVERA's label for a dead-reckoned (not measured) position |

## Check what you learned

<details><summary>1. The ground slides UP in a north-up photo. Which way did the drone go?</summary>
South. The ground slides the opposite way to the drone; up in the picture is north, so the drone went south.
</details>

<details><summary>2. Why does the error of visual odometry keep growing, even if each step is measured well?</summary>
Because the position is a <b>sum</b> of steps: every small error is added to the previous ones and
nothing removes it. Systematic errors (a wrong height, a wrong heading) grow in proportion to the
distance flown.
</details>

<details><summary>3. The barometer reads 5 % too low. What happens to the track?</summary>
The meters per pixel are 5 % too small, so every step is 5 % too short: the track has the right shape
but falls short — about 5 m of error per 100 m flown.
</details>

<details><summary>4. Why can't visual odometry work over the open sea?</summary>
There is nothing fixed and textured to follow: the waves move and all look alike. Phase correlation
gives a low response, and NAVERA (`min_response` 0.08) does not use the result.
</details>

<details><summary>5. What does NAVERA do with the drift when a map match is accepted again?</summary>
It throws it away: the anchor jumps to the matched position and the uncertainty is reset to the
match's own sigma. Visual odometry only bridges the gaps between map fixes.
</details>

Now open the **🛠️ Lab** tab.
