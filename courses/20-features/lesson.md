# Finding interesting points

A drone flies 300 m above Sousse. Its GPS has just been jammed. Its camera still works: it sees
roofs, streets, a roundabout. On board, NAVERA has the satellite map of the whole region. The
question of this module is simple to say and hard to do: **where on the map is this photo?**

You could try to slide the photo over the map pixel by pixel and compare colours. That fails
quickly: the photo was taken on another day, under another sun, with another camera, turned and
at another size. The colours never agree exactly.

So engineers do what *you* do when you recognise a place from the sky: you don't compare every
grain of sand, you look for a few **remarkable details** — the corner of a big building, a
crossroads, a round fountain — and you check that they sit in the same arrangement on the map.
Those remarkable details are called **keypoints**. Finding them is the first step of day vision,
and the subject of this lesson.

![Flat, edge and corner](assets/corner_edge_flat.svg)

## 1. What makes a point "interesting"?

Look at a small square window of a picture — say 10 × 10 pixels — and imagine you move it a little.

| Where the window is | What happens when you move it | Can you find this exact place again? |
|---|---|---|
| On **flat** ground (a field, calm water) | Nothing changes, whichever way you move | No: every place looks the same |
| On an **edge** (the side of a road) | Moving *across* the edge changes the picture, moving *along* it does not | Only half: you know you are on the edge, not *where* on it |
| On a **corner** (the corner of a roof) | Every move changes the picture | **Yes**: one exact place |

That is the whole idea of a **corner detector**: it measures, for every pixel, how much the picture
changes when you move a little in each direction. Where the picture changes in *all* directions,
it marks a keypoint.

Corners are not the only interesting shapes. A small round thing — a tree seen from above, a
water tank, a roundabout — is also easy to find again. Such a spot that is darker or brighter
than everything around it is called a **blob**. Some detectors look for corners, others for blobs:

- **ORB** (*Oriented FAST and Rotated BRIEF*, 2011) looks for **corners**. It is very fast and free
  to use.
- **SIFT** (*Scale-Invariant Feature Transform*, 1999) looks for **blobs** of every size. It is
  slower but very robust. It is the one NAVERA uses on the CPU.

Both are already in OpenCV (lesson 8): you will use them in two lines.

### A keypoint is more than a position

When OpenCV finds a keypoint, it gives you a `cv2.KeyPoint` object with:

| Field | Meaning | Example |
|---|---|---|
| `pt` | its position `(x, y)` in pixels | `(419.0, 109.0)` |
| `size` | the size of the detail it found, in pixels | `31.0` |
| `angle` | the main direction of the light/dark change around it, in degrees | `26` |
| `response` | how strong it is (the detector keeps the strongest) | `0.0012` |

The **size** and the **angle** are what make keypoints useful for a drone. A drone flying higher
sees the same roof smaller; a drone flying east instead of north sees it turned. If the detector
measures the size and the angle of each detail, it can describe the detail *as if* it were always
seen at the same size and pointing the same way. We say the keypoint is **scale invariant**
(it does not care about the zoom) and **rotation invariant** (it does not care about the turn).

> [!NOTE]
> "Invariant" means "does not change". A rotation-invariant description of a roof corner is the
> same whether the photo is turned by 0°, 35° or 180°.

## 2. The descriptor: a fingerprint for each keypoint

Finding keypoints is not enough. In the next lesson you will take a keypoint of the drone photo
and look for **the same** keypoint on the map. To compare them, each keypoint needs a short
summary of what its neighbourhood looks like: its **descriptor**. Think of it as a **fingerprint**:
two photos of the same place give *almost* the same fingerprint; two different places give very
different ones.

![A descriptor is a fingerprint of the keypoint's neighbourhood](assets/descriptor.svg)

- A **SIFT descriptor** is a list of **128 numbers**. SIFT cuts the neighbourhood (turned to the
  keypoint's angle, scaled to its size) into 4 × 4 small cells, and in each cell it counts how much
  the brightness changes in 8 directions: 4 × 4 × 8 = 128.
- An **ORB descriptor** is **256 yes/no answers** (bits), packed into **32 bytes**. Each bit
  answers one tiny question like "is the pixel here brighter than the pixel there?", always for
  the same 256 pairs of pixels around the keypoint.

OpenCV returns all the descriptors of a picture as one numpy array: **one row per keypoint**. With
1000 SIFT keypoints you get an array of shape `(1000, 128)`. In the lab you will measure the length
of an ORB row yourself.

> [!TIP]
> Bits are much faster to compare than 128 numbers: ORB is the choice for small computers that must
> be quick. SIFT descriptors are more precise: NAVERA uses SIFT, and a GPU learned method (lesson 22)
> when the GPU is free.

## 3. Using them in OpenCV

Here is the whole thing, for a picture `img` read with `cv2.imread`:

```python
import cv2
grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)          # detectors work on brightness only
orb = cv2.ORB_create(nfeatures=1000)                  # keep at most the 1000 strongest
keypoints, descriptors = orb.detectAndCompute(grey, None)
print(len(keypoints), descriptors.shape)              # e.g. 1000 (1000, 32)
```

For SIFT, replace the detector by `cv2.SIFT_create(nfeatures=1000)`. The `None` is a *mask*: you
could give a black-and-white picture to say "only look here".

To **see** the keypoints, OpenCV draws them for you:

```python
drawn = cv2.drawKeypoints(img, keypoints, None, color=(0, 0, 255),
                          flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS)
cv2.imwrite("keypoints.png", drawn)
```

With the "rich" flag every keypoint is a circle as big as its `size`, with a line showing its
`angle`.

## 4. Texture: why a city is easy and the sea is not

A picture with many corners and blobs, spread everywhere, has a lot of **texture**. Texture is what
makes a place recognisable. Here are the SIFT keypoints of six 512 × 512 patches of the Sousse map
(zoom 17, so about 500 m × 500 m of ground each) — you will measure them yourself in the lab:

![Keypoints per terrain](assets/terrain_counts.svg)

- **City**: every roof has four corners, every street two edges, every courtyard is a blob. Thousands
  of keypoints, everywhere.
- **Olive groves**: thousands of blobs too (each tree is one)… but the trees all look alike and stand
  in regular rows. A tree here has nearly the same fingerprint as a tree 50 m further. Many keypoints
  is not the same as many *different* keypoints: we call this **repetitive texture**, and it can
  fool a matcher.
- **Farm fields and dry hills**: fewer keypoints, mostly on the roads, hedges and ravines between
  smooth areas.
- **Water**: the sea is nearly one flat colour. Close to the coast a few patches of seagrass give a
  handful of keypoints — but water moves, waves change, and those patches are not where they were on
  the day the satellite took the map.

Three more enemies of texture come from the camera, not the ground: **blur** (the drone shakes or
moves fast), **darkness** (dusk, a cloud shadow) and **haze**. All three wash out the small changes
of brightness that detectors look for. In the lab, a blurry, dark version of the same city photo
drops from thousands of keypoints to almost none.

### Making the most of a dull picture: CLAHE

When a picture is dark or low-contrast, you can **stretch its contrast** before detecting keypoints.
A clever way is **CLAHE** (*Contrast Limited Adaptive Histogram Equalisation*): it cuts the picture
into small tiles (8 × 8 of them) and stretches the contrast of each tile separately, but *limits*
how much (the "clip limit") so that noise is not blown up too much.

```python
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
boosted = clahe.apply(grey)
```

CLAHE brings back keypoints in a dull picture. But be careful: on water it also "finds" texture in
tiny ripples and noise — keypoints that will never be found again on the map. More keypoints only
help if they belong to things that **stay put**.

## 5. Measuring "matchability"

Before spending time trying to match a photo, it is useful to ask: *is this photo even worth
trying?* Two things matter:

1. **How many** keypoints there are. With 10 keypoints, even a perfect matcher has little to work
   with.
2. **How spread** they are. If all the keypoints sit on one road at the edge of the photo, the
   position along that road is badly known, and a small error in one point turns the whole fit.
   Keypoints all over the photo pin it down from every side.

A simple way to measure the spread: cut the picture into a grid (say 4 × 4 = 16 cells) and count
the share of cells that hold at least a few keypoints. All cells full → spread 1. Keypoints in one
corner → spread 1/16.

In the lab you will combine the two into one score between 0 and 1:

```
matchability = min(1, number of keypoints / 300)  ×  spread
```

A city photo scores near 1, the open sea 0, and a photo that is half city, half sea about 0.5.

## In NAVERA

Open [local_matcher.py](file:navera/day_pkg/day_pkg/local_matcher.py) in your NAVERA copy. This is
NAVERA's day-vision matcher (the default since 2026-10-01). Its class `TileFeatures` computes the
keypoints of every map tile, once, and keeps them in memory:

```python
class TileFeatures:
    """SIFT features of the map tiles of an area, computed lazily and cached."""
    PAD = 48                          # border taken from the neighbours

    def __init__(self, images_dir, zoom=17, per_tile=300, cache_tiles=3000):
        ...
        self.sift = cv2.SIFT_create(nfeatures=per_tile, contrastThreshold=0.02)
        self.clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
```

You can recognise everything from this lesson:

- **SIFT**, at most **300 keypoints per 256 × 256 map tile** (`per_tile`), at **zoom 17**.
- `contrastThreshold=0.02` — lower than OpenCV's default (0.04), so that SIFT also keeps weaker
  blobs: satellite pictures are often pale.
- **CLAHE** with clip limit 2 and 8 × 8 tiles, applied before detection (look at `_compute`:
  `self.sift.detectAndCompute(self.clahe.apply(big), None)`).
- `PAD = 48`: each tile is cut with a 48-pixel border taken from its neighbours, so that a roof cut
  in half by the tile border is still seen whole.

The camera frame gets the same treatment in `LocalMatcher.locate()` (up to 1500 keypoints). If it
has fewer than 10, NAVERA gives up on that frame at once, with this reason:

```python
kq, dq = self.sift.detectAndCompute(q, None)
if dq is None or len(kq) < 10:
    res.update(reason="too few features in the frame (uniform ground, blur, darkness)")
```

Uniform ground, blur, darkness: the three enemies of texture you just met. And NAVERA's own
`inlier_spread()` function, in the same file, measures the spread of the matched points on a
4 × 2 grid — exactly the idea of your matchability score. In `vision_nav.py`, a fix with fewer than
50 matched points spread over less than a quarter of the frame is rejected.

What happens over water and uniform land is written honestly in `docs/VALIDATION_STATUS.md`. In a
simulated flight over uniform terrain near Gabès, with the former whole-tile method, the conclusion
was **"Day vision is unreliable over uniform terrain (desert, sea)"** (median error 351 m). Local
keypoint matching did much better on the same simulated flight (147 matches in a row, none
rejected) — but the document warns that this simulated camera is cut from the map's own pictures,
which is optimistic. Over the sea, however, there is simply nothing to match: NAVERA
then carries its last position along the measured track (dead-reckoning). In the simulator it was
carried 90 s over the bay stating ±300 m, with a true error of at most 146 m. You will meet this
again in lesson 23.

## Words you learned

| Word | Meaning |
|---|---|
| **keypoint** (feature) | a small, remarkable spot of a picture that can be found again: a corner or a blob |
| **corner** | a point where the picture changes in every direction |
| **blob** | a small spot darker or brighter than its surroundings (a tree, a tank) |
| **descriptor** | a short list of numbers describing a keypoint's neighbourhood: its "fingerprint" |
| **ORB** | a fast corner detector with binary descriptors (256 bits = 32 bytes) |
| **SIFT** | a robust blob detector with 128-number descriptors; NAVERA uses it |
| **scale / rotation invariant** | gives the same description whatever the zoom / the turn of the photo |
| **texture** | the amount of detail in a picture; lots of texture = lots of keypoints |
| **repetitive texture** | many details that all look alike (rows of olive trees): easy to confuse |
| **CLAHE** | a local contrast boost, used before detection to help dull pictures |
| **spread** | how well keypoints cover the whole picture (share of grid cells used) |

## Check what you learned

<details><summary>1. Why is a point on the straight edge of a road a poor keypoint?</summary>
Because sliding along the edge does not change what you see: you can tell you are on the edge,
but not <i>where</i> along it. A corner changes in every direction, so it marks one exact place.
</details>

<details><summary>2. The descriptor array of a picture has shape (742, 128). What do you know?</summary>
742 keypoints were found, and each has a 128-number descriptor: it was made by SIFT (ORB rows
are 32 bytes long).
</details>

<details><summary>3. An olive grove gives thousands of keypoints. Why can it still be hard to match?</summary>
The trees all look alike and stand in regular rows: many keypoints have nearly the same
fingerprint, so a tree of the photo can be matched to the wrong tree of the map. This is
repetitive texture.
</details>

<details><summary>4. Why does NAVERA give up on a frame with fewer than 10 keypoints instead of trying anyway?</summary>
With so few points no reliable fit is possible, and a wrong position is worse than no position.
The frame is reported as "too few features (uniform ground, blur, darkness)" and NAVERA continues
with dead-reckoning.
</details>

<details><summary>5. CLAHE turns 68 keypoints into 878 on a picture of the sea near the coast. Is the picture now easy to match?</summary>
No. CLAHE stretched the contrast of ripples, seagrass and noise. Those details move or change and
are not on the map in the same place. More keypoints only help when they belong to things that stay put.
</details>

Now open the **🛠️ Lab** tab.
