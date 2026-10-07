# Images are just numbers

NAVERA's day camera looks straight down and sends photo after photo. You see roofs, streets, a
football pitch. The computer sees none of that: a photo of 1536 × 730 pixels is, for it,
**3 363 840 numbers**. To find
where the drone is, NAVERA must find which piece of the satellite map (lesson 7) "looks like" those
numbers — and the map is another big table of numbers, taken by another camera, on another day, from
much higher, with north at the top.

Before a computer can compare two pictures, they must be made **comparable**: same orientation, same
scale, similar brightness. In this lesson you learn what an image really is, the basic operations on
it, and why NAVERA applies them before every match.

## Pixels: a table of numbers

Zoom far into any digital photo and you see small squares of one colour each: the **pixels**
("picture elements"). A **grey** (black-and-white) image is simply a **table**: one number per pixel,
its brightness.

- 0 is black, 255 is white, 128 a middle grey.
- Why 255? Each pixel is stored in one **byte**, and a byte can hold 256 different values (0 to 255).
  In Python this type is called **uint8** ("unsigned integer, 8 bits").

![A grey image is a table of numbers; a colour image is three tables](assets/pixels.svg)

Positions in an image are counted like the map tiles of lesson 7: the origin (0, 0) is the **top-left**
corner, **x** grows to the right (columns), **y** grows **downwards** (rows).

In Python, images are **numpy arrays** — numpy is the library for big tables of numbers. Two things to
remember:

- `img.shape` gives `(height, width)`: **rows first**, then columns.
- `img[y, x]` is the pixel at row `y`, column `x` — again **y first**. `img[2, 3]` in the picture above
  is 160.

### Colour: three tables

A colour pixel mixes three lights: **red, green and blue**. A colour image is therefore three tables
stacked, called **channels**, and its shape is `(height, width, 3)`.

> [!WARNING]
> OpenCV, the image library NAVERA uses, stores the channels in the order **Blue, Green, Red** (BGR),
> not RGB. `img[y, x]` gives `[blue, green, red]`. Pure red is `[0, 0, 255]`. Forget it and your red
> roofs come out blue.

| `[B, G, R]` | Colour |
|---|---|
| `[0, 0, 0]` | black |
| `[255, 255, 255]` | white |
| `[0, 0, 255]` | red |
| `[0, 255, 255]` | yellow (green + red light) |
| `[30, 105, 140]` | a sandy roof of Sousse |

The aerial test frames you will use in the lab are 1536 × 730 pixels × 3 channels = 3 363 840 numbers
(3.4 MB).
On the disk, the JPEG format squeezes it to a few hundred kilobytes by throwing away details the eye
does not notice.

### From colour to grey

To turn a colour pixel into one grey value, you take a **weighted average** of its three channels:

grey = 0.299 × R + 0.587 × G + 0.114 × B

Green counts most because our eyes are most sensitive to it. In OpenCV:
`cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)`.

Vision navigation almost always works in **grey**. The colours of a satellite map and of a drone
camera never match (different sensors, seasons, hours of the day), but the **shapes** — roads, walls,
shadows — stay the same. Grey also means 3 times fewer numbers to process, and a thermal (night)
camera only gives grey anyway.

## Operations on an image

Because an image is an array, many operations are just a line of numpy. The others are one call to
**OpenCV** (`import cv2`).

### Crop and flip: slicing

To **crop** (cut out a rectangle) you take some rows and some columns with a **slice** — you met slices
on lists in lesson 4:

```python
part = img[100:400, 600:1000]        # rows 100..399, columns 600..999  -> 300 x 400 pixels
```

Again: rows (y) first! `img[y0:y1, x0:x1]`. To **flip** left–right, read the columns backwards:
`img[:, ::-1]`.

### Rotate

Turning an image by any angle needs to compute, for each new pixel, where it comes from in the old
image. OpenCV does it in two steps: build a **rotation matrix** (a small table of 6 numbers that
describes the turn), then apply it with `warpAffine`:

```python
h, w = img.shape[:2]
M = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, 1.0)   # centre, angle, scale
turned = cv2.warpAffine(img, M, (w, h))                        # size of the result: (WIDTH, HEIGHT)
```

In OpenCV a **positive angle turns counter-clockwise** (anticlockwise). The result keeps the same size,
so the corners of the old image are cut off and the new corners are filled with black.

### Resize (scale)

`cv2.resize(img, (new_width, new_height))` makes an image bigger or smaller. Notice the order:
**(width, height)** — the opposite of `img.shape`! A classic bug. When shrinking, several old pixels
become one new pixel: `interpolation=cv2.INTER_AREA` averages them properly. When enlarging,
`cv2.INTER_LINEAR` blends neighbours smoothly.

### Brightness and contrast

Each pixel can be changed with a simple rule:

new = old × **contrast** + **brightness**

A brightness of +50 makes everything lighter; a contrast of 2 makes darks darker and lights lighter.

> [!WARNING]
> **The uint8 trap.** A uint8 cannot hold more than 255. In numpy, `np.uint8(250) + np.uint8(10)` gives
> **4**, not 260 and not 255: the value "wraps around" like a car's odometer. A white sky becomes
> black! Always compute in **float** (`img.astype(np.float32)`), then **clip** to 0…255
> (`np.clip`), then convert back with `.astype(np.uint8)`.

**Normalising** chooses the contrast and brightness automatically: the darkest pixel becomes 0 and the
brightest 255:

new = (old − min) / (max − min) × 255

A dull, dark photo then uses the whole range of greys, like the map does. (NAVERA uses a cleverer
version called **CLAHE**, which does this region by region, so a shadow in one corner does not darken
the whole picture.)

### Blur

**Blurring** replaces each pixel by an average of itself and its neighbours. The **Gaussian blur**
gives more weight to the closest neighbours; the window size `k` (3, 5, 7… always odd so that it has a
centre) sets how far it reaches. Blur removes **noise** (the random speckle of a camera sensor) and
tiny details that the other picture may not have — a satellite map at 1 m per pixel never shows the
cracks a low-flying drone sees.

`cv2.GaussianBlur(img, (k, k), 0)` — the 0 lets OpenCV choose the strength from `k`.

### Edges

An **edge** is a place where the brightness changes quickly: the side of a road, the wall of a
building, the shoreline. The **Canny** edge detector (named after its inventor, John Canny) finds them
and draws them as thin white lines on black:

```python
e = cv2.Canny(grey_blurred, 50, 150)        # two thresholds: low and high
```

A change stronger than the **high** threshold is surely an edge; one between **low** and **high** is
kept only if it continues a sure edge. Canny is usually applied to a slightly **blurred** grey image,
otherwise every grain of noise becomes an "edge".

Edges are interesting for navigation because they **do not care about brightness**: a road is a road
in the morning and in the evening. Lesson 20 goes further with **features** — small, distinctive
patterns that NAVERA actually matches.

## Why the photo must look like the map

Put a drone photo next to the map of the same place: a human sees it is the same place; a computer
comparing numbers sees almost nothing in common. Four differences must be removed:

| Difference | Why it happens | The fix |
|---|---|---|
| **Orientation** | the map has north up; the photo's top points where the drone flies (its **heading**) | rotate the photo by the heading |
| **Scale** | a map pixel is 0.97 m (zoom 17 at Sousse); a photo pixel depends on the height and the camera | resize the photo |
| **Brightness / colours** | another camera, another day, sun, haze | grey + normalise |
| **Detail and noise** | the drone sees more detail and sensor noise | a little blur |

![The four steps that make a drone photo comparable with the map](assets/like_map.svg)

### Which way to rotate?

The **heading** is the direction of the image top, as a bearing (lesson 6): clockwise from north.
If the heading is 35°, the photo's top points 35° east of north, so north appears 35° **to the left**
of the top (counter-clockwise). To bring north back to the top we turn the photo **clockwise** by
35° — in OpenCV, an angle of **−35**.

### How much to scale?

The ground size of a camera pixel (its **ground resolution**, in meters per pixel) comes from the
height and the camera's **field of view** (the angle it sees, from its left edge to its right edge):

ground width seen = 2 × height × tan(field of view / 2)

meters per pixel = ground width seen / image width in pixels

For example, a camera with an 84° field of view, 300 m above the ground, sees 2 × 300 × tan(42°) ≈
540 m; with 1536 pixels across, that is 0.35 m per pixel. The map has 0.97 m per pixel, so the photo
must be shrunk by **0.35 / 0.97 ≈ 0.36**. In general:

scale factor = photo meters per pixel / map meters per pixel

## In NAVERA

**Night vision prepares every thermal frame exactly like this** — `night_pkg/night_pkg/nodes/night_localizer.py`,
function `normalize_query()` ([open it](file:navera/night_pkg/night_pkg/nodes/night_localizer.py)):

```python
footprint_w = 2.0 * altitude_m * math.tan(math.radians(hfov_deg) / 2.0)
gsd_cam = footprint_w / w                 # camera meters per pixel
gsd_map = ground_resolution_m(lat, zoom)  # map meters per pixel
scale = gsd_cam / gsd_map
...
    # The image top points along the heading, i.e. the camera image is the
    # north-up view turned counter-clockwise by the heading (OpenCV: positive
    # angle = counter-clockwise on screen). Turning it back clockwise by the
    # heading (negative angle) brings north to the top.
    M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), -float(heading_deg), 1.0)
    ...
    img_bgr = cv2.warpAffine(img_bgr, M, (diag, diag), flags=cv2.INTER_LINEAR)
...
interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
img = cv2.resize(img_bgr, (nw, nh), interpolation=interp)
```

Ground resolution, the scale factor, a rotation by **minus** the heading, and `INTER_AREA` to shrink:
everything from this lesson. (NAVERA makes the rotated canvas as big as the diagonal, `diag`, so no
corner of the photo is cut off.) If the altitude or the field of view is unknown, the function refuses
to guess and returns a reason instead — a frame at the wrong scale would give a wrong position.

**Day vision** — `day_pkg/day_pkg/local_matcher.py`, method `locate()`
([open it](file:navera/day_pkg/day_pkg/local_matcher.py)):

```python
grey = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
mpp_map = map_m_per_px(prior[0], self.z)
s = frame_m_per_px / mpp_map                     # frame pixels → map pixels
...
q = self.clahe.apply(cv2.resize(grey, None, fx=s, fy=s,
                                interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR))
```

Grey, scale to the map's meters per pixel (`map_m_per_px` is your `meters_per_pixel` of lesson 7),
then CLAHE for the contrast. Here the rotation is not done on the picture: the feature matching of
lesson 21 finds it by itself, and NAVERA checks it against the measured heading.

The ground resolution formula lives in `navera_common/navera_common/camera_model.py`:
`ground_m_per_px(altitude_agl_m, hfov_deg, width_px)`.

## New words

| Word | Meaning |
|---|---|
| **pixel** | one small square of an image, with one value (grey) or three (colour) |
| **uint8 / byte** | a whole number from 0 to 255, stored in 8 bits — the usual pixel type |
| **numpy array** | Python's table of numbers; an image is one. `shape` = (height, width[, channels]) |
| **channel** | one of the three tables of a colour image; OpenCV order: Blue, Green, Red |
| **grey image** | one channel: brightness only |
| **crop** | cut out a rectangle: `img[y0:y1, x0:x1]` |
| **interpolation** | how new pixel values are computed when rotating or resizing |
| **contrast / brightness** | multiply / add to every pixel value |
| **normalise** | stretch the values so they go from 0 to 255 |
| **blur (Gaussian)** | average each pixel with its neighbours; removes noise and fine detail |
| **edge, Canny** | where brightness changes quickly; the classic algorithm to find edges |
| **heading** | direction of the image top (or the vehicle's nose), clockwise from north |
| **ground resolution** | meters on the ground per pixel (m/px) |
| **field of view** | the angle a camera sees, edge to edge |

## Check what you learned

<details><summary>1. An image has shape (480, 640, 3). How wide is it, and how many numbers does it hold?</summary>
640 pixels wide (and 480 high — rows come first), with 3 channels: 480 × 640 × 3 = 921 600 numbers.
</details>

<details><summary>2. A program adds 20 to every pixel of a uint8 image and the white clouds become black. Why?</summary>
uint8 wraps around above 255: 250 + 20 = 270 becomes 14. Compute in float, clip to 0…255, convert back.
</details>

<details><summary>3. The drone flies with heading 90° (towards the east). How must its photo be turned to have north up?</summary>
The photo's top points east, so north is on its left. Turn it 90° clockwise: rotate by −90 in OpenCV.
</details>

<details><summary>4. A photo has 0.5 m per pixel and the map 1 m per pixel. Bigger or smaller, and by how much?</summary>
Smaller: scale factor 0.5 / 1 = 0.5 — half the width and half the height, so that one pixel = 1 m in both.
</details>

<details><summary>5. Why does NAVERA compare pictures in grey and not in colour?</summary>
Colours change with the camera, the season and the light, but shapes do not. Grey keeps the shapes,
removes most of the colour differences, and has 3 times fewer numbers.
</details>

Now open the **🛠️ Lab** tab.
