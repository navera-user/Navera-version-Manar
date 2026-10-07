# Lab 17 — Measure the world with a camera

**Goal:** write the camera formulas NAVERA uses (focal length, footprint, meters per pixel, map
scale, tilt), check them against NAVERA's own code, and find the height of a drone from one of its
photos.
**Time:** about 1 hour.

Your files:

| File | What you do with it |
|---|---|
| [camera_math.py](file:./camera_math.py) | the formulas — **TODO 1 to 4** |
| [measure_pad.py](file:./measure_pad.py) | measure a landing pad in two photos — **TODO 5** |
| [compare_with_navera.py](file:./compare_with_navera.py) | compares your formulas with NAVERA's (nothing to change) |
| [plot_scale.py](file:./plot_scale.py) | draws a chart (nothing to change) |
| [answers.py](file:./answers.py) | three quiz questions |

## Step 1 — Run the starter

```bash
python3 camera_math.py
```

Every line says `TODO not done yet`. The program already knows what to print: you only have to write
the formulas inside the functions.

> [!TIP]
> Python's `math.tan()` and `math.cos()` want the angle in **radians**. Always write
> `math.tan(math.radians(angle_deg))`. Forgetting this is the number-one bug of this lab:
> `math.tan(45)` is 1.62, not 1!

## Step 2 — Focal length, footprint, meters per pixel

Open [camera_math.py](file:./camera_math.py). Each function has its formula in its docstring
(the text between `"""`). For example, the footprint:

```python
def footprint(height_m, hfov_deg):
    return 2.0 * height_m * math.tan(math.radians(hfov_deg) / 2.0)
```

> [!TASK]
> **TODO 1:** write `focal_px(hfov_deg, width_px)`, `footprint(height_m, hfov_deg)` and
> `meters_per_pixel(height_m, hfov_deg, width_px)` (use `footprint()` inside it). Save, run
> `python3 camera_math.py` again.

You should now see the Insta360 lines filled in:

```
  focal length                                   659.790 px
  footprint at 50 m                              145.501 m
  ...
  meters per pixel at 150 m                      0.227 m/px
```

659.8 px: that is the **fx ≈ 660** that the real calibration of NAVERA's Insta360 found (lesson 18).
An ideal lens of 111° on 1920 pixels has exactly that focal length — this is why NAVERA caps the
straightened view at 111°.

## Step 3 — Height from a known object

If you know the real size of something on the ground, the pinhole rule tells you the height:
`size_px / f = size_m / h`.

> [!TASK]
> **TODO 2:** write `height_from_object(size_m, size_px, hfov_deg, width_px)`. Use your
> `focal_px()`. A 12 m pad seen as 48 px by a 960 px, 90° camera must give **120 m**.

Run `python3 camera_math.py` again and check the line "height when a 12 m pad is 48 px".

## Step 4 — Map zoom and scale

Now connect the camera to the map of lesson 7. The map's meters per pixel at zoom `z` is
`40075016.7 · cos(latitude) / 2**z / 256`.

> [!TASK]
> **TODO 3:** write
> - `map_meters_per_pixel(lat_deg, zoom)`,
> - `scale_factor(...)` = photo meters per pixel / map meters per pixel (the resize NAVERA applies),
> - `best_zoom(...)`: try every zoom in `zooms`, and return the one where
>   `abs(math.log(map_mpp / photo_mpp))` is the smallest. Return the **zoom number** (an int).

Why the `log`? A map twice too fine and a map twice too coarse are equally bad.
`log(2)` and `log(1/2)` have the same size (0.69), so `abs(log(ratio))` treats them the same.

A loop that keeps the best value looks like this:

```python
best, best_err = None, None
for z in zooms:
    err = ...                      # how far this zoom is
    if best_err is None or err < best_err:
        best, best_err = z, err
return best
```

Run the program: at 300 m the best zoom is **18**, and the scale for the zoom-17 map is **0.469**.

Then draw the picture of it all:

```bash
python3 plot_scale.py
```

Open [scale.png](file:./scale.png) in the editor. The blue line is the photo's meters per pixel; the
grey dashed lines are the map zoom levels. Where the blue line crosses a grey line, the photo and
that zoom have the same resolution.

> [!QUESTION]
> NAVERA's prepared map area uses zoom 17 (0.97 m/px). At what height does the Insta360 view have
> the same resolution? Read it on the chart, then compute it: h = 0.97 · 1920 / (2 · tan 55.5°).
> (About 640 m. Lower, NAVERA shrinks the photo; higher, it enlarges it.)

## Step 5 — Tilt

> [!TASK]
> **TODO 4:** write `tilt_shift_m(height_m, tilt_deg)` = h · tan(tilt) and
> `tilted_extent(height_m, fov_deg, tilt_deg)` which returns a **tuple** `(near, far)`:
> `near = h·tan(tilt − fov/2)`, `far = h·tan(tilt + fov/2)`, and `far = math.inf` when
> `tilt + fov/2 >= 90`.

Run `python3 camera_math.py`: a 10° tilt at 150 m moves the centre of the picture by **26.4 m**, and
at 100 m with a 60° field of view and a 20° tilt the picture covers the ground from 17.6 m behind
to 119.2 m in front — almost 7 times more ground in front than behind.

Try it yourself in the Python shell (type `python3`, then the lines, then `exit()`):

```python
from camera_math import tilted_extent
for tilt in (0, 10, 20, 40, 59, 60):
    print(tilt, tilted_extent(100, 60, tilt))
```

At a tilt of 60°, the top edge of the picture looks at the horizon.

## Step 6 — Compare with NAVERA

Your copy of NAVERA (`~/navera`) has the same formulas, in `navera_common/camera_model.py` and
`day_pkg/local_matcher.py`. This script imports both yours and NAVERA's and compares them:

```bash
python3 compare_with_navera.py
```

Every line should start with ✔ and the last line should say `ALL MATCH`. If a line says ✘, the
numbers next to it show what you got and what NAVERA gets — find the difference in your formula.

Want to see NAVERA's code? Open
[camera_model.py](file:navera/navera_common/navera_common/camera_model.py) and search (`Ctrl+F`)
for `ground_m_per_px`, then [local_matcher.py](file:navera/day_pkg/day_pkg/local_matcher.py) and
search for `map_m_per_px`.

## Step 7 — How high was the drone?

In `/data/academy/17-camera-model/` there are two photos taken by a straight-down camera
(960 px wide, 90° field of view) above the old town of Sousse. Each shows an orange landing pad
**12 m × 12 m**. Look at one:

```bash
cp /data/academy/17-camera-model/photo_A.png .
```

and open [photo_A.png](file:./photo_A.png) in the editor.

> [!NOTE]
> These photos are made from the satellite map (as if a perfect camera flew there) and the orange
> pad was painted on them, so we know the exact truth. Real photos also need lesson 18 (the lens)
> and lesson 16 (the tilt) first.

Open [measure_pad.py](file:./measure_pad.py). The function `orange_mask(img)` already gives a
**mask**: an array of True/False, True where the pixel is orange (you met masks in lesson 8).

> [!TASK]
> **TODO 5:** write `pad_size_px(img)`: the number of columns from the leftmost to the rightmost
> orange pixel, both included. `rows, cols = np.nonzero(mask)` gives the row and column of every
> True pixel. Return `None` if there is no orange pixel.

```bash
python3 measure_pad.py
```

You should see something like:

```
photo_A.png: the 12 m pad is 48 px wide -> the drone was at 120 m
photo_B.png: the 12 m pad is 27 px wide -> the drone was at 213 m
```

Photo B was really taken at 210 m. Why 213? The pad is about 27.4 px wide, but a pixel count is a
whole number: 1 px of error on a 27 px object is almost 4 % of height. **Big objects measure
heights better** — that is why NAVERA measures the height from the scale of the *whole* photo
matched to the map, not from one small object.

Open `mask_photo_A.png` to see what the mask found.

## Step 8 — Quiz and check

Answer the three questions in [answers.py](file:./answers.py), then press **✔ Check my work**.

## Going further (optional)

1. **Your phone.** Find your phone camera's horizontal field of view (often 65–75°). Stand 3 m from
   a door (about 0.9 m wide), take a photo, measure the door's width in pixels and compute the
   distance with `height_from_object()`. How close do you get?
2. **The height that matches.** Write `height_for_zoom(zoom, lat, hfov_deg, width_px)` that returns
   the height at which the photo has exactly the map's meters per pixel. Check it with the chart.
3. **The 45° limit.** NAVERA refuses frames tilted more than 45°. With the Insta360 view
   (111°, so 55.5° each side), what does `tilted_extent(150, 111, 45)` give? Why does straightening
   such a frame make little sense?
