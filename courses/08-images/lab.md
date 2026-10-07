# Lab 8 — Pictures as numbers

**Goal:** look at a real aerial photo as numbers, write the basic image operations (grey, crop, rotate,
resize, brightness, normalise, blur, edges), then use them to make a drone photo comparable with the
satellite map — exactly what NAVERA does before a match.
**Time:** about 1 h 15.

Your file is [images_lab.py](file:./images_lab.py). The scripts `explore.py`, `demo.py` and
`like_map.py` are ready and use your functions. Every picture they save appears in the file list:
**click it** and the editor shows it.

The pictures:

| Path | What |
|---|---|
| `/data/navera_data/camera_pkg/camera_pkg/data/day/frame_*.jpeg` | 31 real aerial photos, 1536 × 730. We use them only as pictures (the positions in their log are not reliable). |
| `/data/academy/08-images/map_patch.png` | 512 × 512 of NAVERA's map (zoom 17, north up) around Port El Kantaoui marina |
| `/data/academy/08-images/drone_photo.jpg` | a **simulated** drone photo of the same place: heading 35°, 0.6 m per pixel, darker, warmer, a bit blurred and noisy |
| `/data/academy/08-images/info.json` | the exact parameters of the simulated photo |

> [!NOTE]
> Why a simulated photo? Because we know **exactly** its heading, its scale and its centre, so the
> computer can tell you whether your processing is right. It was made from the zoom-18 tiles of the map
> (a different, sharper picture than the zoom-17 map patch), turned, scaled and degraded like a real
> camera would. The script that made it is `/data/academy/08-images/make_dataset.py`.

## Step 1 — A photo is a table of numbers

```bash
python3 explore.py
```

Read the output: the type is `ndarray of uint8`, the shape `(730, 1536, 3)` — 730 rows, 1536 columns,
3 channels. Then the values of two pixels as `[blue, green, red]`, the minimum, maximum and mean of each
channel, and an 8 × 8 block of grey values from the middle of the photo.

Open **frame.png** (the photo) and **centre_8x8_zoomed.png** (those 64 numbers, each drawn as a big
square). Find, in the table of numbers, the darkest and the brightest of the 64 squares.

Try another frame:

```bash
python3 explore.py /data/navera_data/camera_pkg/camera_pkg/data/day/frame_0020.jpeg
```

## Step 2 — Grey and crop

Open [images_lab.py](file:./images_lab.py). The first function, `flip_horizontal()`, is **already
written** as an example: one slice, `img[:, ::-1]` — all rows, columns backwards.

- **TODO 1** `to_gray(img)`: if `img.ndim == 2` the image is already grey, return it; otherwise use
  `cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)`.
- **TODO 2** `crop(img, x, y, w, h)`: one slice. Rows first!
- **TODO 3** `crop_center(img, w, h)`: compute the top-left corner so that the rectangle is in the
  middle, then call your `crop()`. Use `//` (whole division): pixel positions must be whole numbers.

Test as you go in the interactive Python (`python3`):

```python
import numpy as np
from images_lab import crop, crop_center
a = np.arange(48).reshape(6, 8)
print(a)
print(crop(a, 2, 1, 3, 4))
```

You should see the 4 rows × 3 columns block that starts at row 1, column 2 (values 10, 11, 12 on its
first line). Then run the demo:

```bash
python3 demo.py
```

It applies every function to a real photo and saves the results in **out/**. Functions still to do
print `TODO`. Open `out/gray.png`, `out/crop.png` and `out/crop_center.png`.

> [!TASK]
> Finish **TODO 1**, **TODO 2** and **TODO 3**. Done means: pure blue, green, red pixels become grey
> values 29, 150, 76; a grey image comes back unchanged; `crop()` and `crop_center()` cut exactly the
> right pixels.

## Step 3 — Rotate and resize

- **TODO 4** `rotate(img, angle_deg)`: counter-clockwise for positive angles, around the centre, same
  size — the two lines of the course (`getRotationMatrix2D`, `warpAffine`).
- **TODO 5** `scale(img, factor)`: compute the new width and height (`round(...)`, then `int(...)`), and
  call `cv2.resize(img, (new_w, new_h), interpolation=...)` — `cv2.INTER_AREA` when the factor is below
  1, `cv2.INTER_LINEAR` otherwise.

```bash
python3 demo.py
```

Open `out/rotated_30.png`: the photo turned 30° **counter-clockwise**, with black corners. Open
`out/half_size.png` and compare its shape (printed by the demo) with the original.

> [!TASK]
> Finish **TODO 4** and **TODO 5**. Done means: `rotate(img, 0)` changes nothing, `rotate(img, 90)` moves
> a dot from the right of the centre to above it, the size never changes; `scale()` gives (30, 50) for a
> 60 × 100 picture and 0.5, and keeps the 3 colour channels.

## Step 4 — Brightness, contrast, normalise

First, see the uint8 trap with your own eyes, in `python3`:

```python
import numpy as np
a = np.array([250, 100], dtype=np.uint8)
print(a + 10)
print(np.clip(a.astype(np.float32) + 10, 0, 255).astype(np.uint8))
```

The first line gives `[  4 110]` — 250 + 10 = 4! The second gives the right `[255 110]`.

- **TODO 6** `adjust(img, contrast, brightness)`: float, multiply, add, clip, back to uint8.
- **TODO 7** `normalise(img)`: `img.min()`, `img.max()`, then the formula of the course. If max equals
  min (a uniform picture), return the picture unchanged — dividing by zero would be a disaster.

```bash
python3 demo.py
```

Compare `out/dark.png` (a dull, dark version the demo makes) with `out/dark_normalised.png`: the
details come back. Look at `out/brighter.png` and `out/more_contrast.png` too.

> [!TASK]
> Finish **TODO 6** and **TODO 7**. Done means: 250 + 10 gives 255 (not 4), negative results give 0, the
> result is uint8; `normalise()` sends the darkest pixel to 0 and the brightest to 255.

## Step 5 — Blur and edges

- **TODO 8** `blur(img, k)`: `cv2.GaussianBlur(img, (k, k), 0)`.
- **TODO 9** `edges(img, low=50, high=150)`: grey → blur with k = 5 → `cv2.Canny(..., low, high)`.
  Use your own `to_gray()` and `blur()`.

```bash
python3 demo.py
```

Open `out/blur_15.png` (a strong blur: the cars disappear, the streets stay) and `out/edges.png`: the
outline of every building and street, in white on black. No more `TODO` should be printed.

> [!QUESTION]
> In `python3`, compare `edges(img, 20, 60)` and `edges(img, 100, 300)` on the photo: type
> `import cv2`, `from images_lab import edges`, `img = cv2.imread("frame.png")`, then save each result
> with `cv2.imwrite("e1.png", edges(img, 20, 60))` (and `e2.png`). Which thresholds keep only the
> strong outlines? Which picture would be easier to compare with a map?

> [!TASK]
> Finish **TODO 8** and **TODO 9**. Done means: a uniform picture is not changed by blur, a dot spreads
> (more with k = 5 than with k = 3); `edges()` finds the border between a black and a white half and
> nothing in a uniform picture; `python3 demo.py` runs with no `TODO` and no `ERROR`.

## Step 6 — Make the drone photo look like the map

Open `/data/academy/08-images/drone_photo.jpg` and `/data/academy/08-images/map_patch.png` side by side
(in the terminal: `cp /data/academy/08-images/*.png /data/academy/08-images/*.jpg .` copies them into
your lesson folder so you can click them). Same place? Hard to say: the photo is turned, bigger,
darker, warmer.

```bash
python3 like_map.py
```

With the TODO still open, it stops and asks for TODO 10. Write it:

**TODO 10** `make_like_map(photo, heading_deg, photo_m_per_px, map_m_per_px)` — the four steps of the
course, using **your** functions:

1. `to_gray()`;
2. `normalise()` — before rotating, so the black corners do not count as "the darkest pixel";
3. `rotate()` — by how much, and in which direction, to bring north to the top? (heading 35°,
   counter-clockwise for positive angles…);
4. `scale()` — by which factor? The photo has 0.6 m per pixel, the map 0.968.

```bash
python3 like_map.py
```

It compares the 160 × 160 middle of the map with (a) the photo as it is and (b) your prepared photo,
with two scores:

- **difference** — the average gap between the two pictures' pixels: 0 = identical;
- **similarity** — the **correlation**, from −1 to 1: 1 means the same pattern of light and dark,
  0 means unrelated. It ignores brightness and contrast.

The raw photo should score a similarity near 0. Your prepared photo should score **above 0.9**, with a
difference **below 25**. Open `comparison.png`: map | photo as it is | your prepared photo. The
pontoons of the marina must line up.

> [!TIP]
> Similarity near 0 or negative? Your rotation is probably the wrong way round (+35 instead of −35):
> the photo is then turned 70° away from north. Similarity good but difference above 25? You forgot to
> normalise. Size wrong? Check the scale factor.

> [!TASK]
> Finish **TODO 10**. Done means: the result is a grey picture of about 397 × 298 pixels (the map's
> scale), its middle matches the map with a similarity above 0.9 and a difference below 25.

Press **✔ Check my work**.

> [!NOTE]
> Real photos are much harder than this simulated one: the map is often 2 or 3 years older than the
> flight, with other shadows, other cars, new buildings. That is why NAVERA does not compare whole
> pictures pixel by pixel but looks for **features** — small, distinctive patterns — and matches them
> (lessons 20 and 21). The preparation you wrote today is still the first step.

## Going further (optional)

- **Wrong heading.** In `python3`, run your `make_like_map()` with heading 30 and 40 instead of 35 and
  compute the `similarity()` of the middles (copy the lines from `like_map.py`). How fast does it drop?
  This is why NAVERA needs the heading from its IMU (lesson 16).
- **Wrong height.** A wrong altitude gives a wrong scale. Try `photo_m_per_px` = 0.5 and 0.7. NAVERA's
  day vision accepts a match only when the scale it measures agrees with the altitude (read the
  docstring at the top of `~/navera/day_pkg/day_pkg/local_matcher.py`).
- **Edges against edges.** Compute `edges()` of the map patch and of your prepared photo and save them
  side by side with `np.hstack`. Do the outlines match?
