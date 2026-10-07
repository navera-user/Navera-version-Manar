# Lab 17 report — the camera as a measuring instrument

Name: teacher solution

## Key numbers

| id | quantity | value |
|---|---|---|
| A | focal length of NAVERA's straightened Insta360 view, 111° on 1920 px (px) | 659.79 |
| B | vertical field of view of that view, 540 px high (deg) | 44.51 |
| C | footprint area of the lab camera at 150 m, pitch −20° (m²) | 66466.1 |
| D | ground distance from the point under the drone to the image-centre point, pitch −20° (m) | 54.6 |
| E | height where the Insta360 view has the GSD of the zoom-17 map over Reykjavik (m) | 343.6 |
| F | the same height over Sousse (m) | 638.9 |
| G | height of photo B measured from the pad (m) | 213.3 |
| H | photo B: lowest height if the pad width is wrong by ±1 px (m) | 205.7 |
| I | photo B: highest height if the pad width is wrong by ±1 px (m) | 221.5 |
| J | photo T: the pad is this far EAST of the point under the drone (m) | 37.6 |
| K | photo T: the pad is this far NORTH of the point under the drone (m) | -91.8 |
| L | fitted scale in the mountain scenario | 0.1667 |
| M | relative height uncertainty σh/h (%) above which NAVERA widens its 15 % scale gate | 7.5 |

## 1. Tilt

When the drone pitches nose down, its belly (and the fixed camera) turns towards the back, so the
image centre lands behind the drone: 26.4 m at −10°, 54.6 m at −20°, 86.6 m at −30° (h·tan θ).
The footprint becomes a trapezoid whose far (back) edge is much wider than the near edge; the area
grows from 50 625 m² to 97 405 m². A match that puts the drone at the image centre would be wrong
by tens of metres, so NAVERA straightens the frame first.

## 2. Reykjavik and Sousse

Web Mercator keeps 256 px per tile at every latitude but the ground circle at latitude φ is
shorter by cos φ, so one pixel covers 0.52 m at zoom 17 over Reykjavik (64.2° N) and 0.97 m over
Sousse (35.8° N). At 300 m the Insta360 GSD is 0.45 m/px. Over Reykjavik the closest map is zoom 17
(0.52 m/px), but over Sousse it is zoom 18 (0.48 m/px), so the same flight needs a different map
tile set at each place: the zoom must be chosen with the latitude.

## 3. Measuring the height with an object

Photo A gives 120 m (truth 120 m); photo B gives 213 m (truth 210 m, +1.6 %). The pad in B is only
27 px wide and a pixel count has an error of about one pixel, which is 3.7 % of 27 px, so B can be
anywhere from 206 to 222 m. Height precision grows with the size of the object in pixels; the
whole photo matched to the map spans hundreds of pixels, so its scale gives a far better height.

## 4. Height uncertainty

GPS altitude minus the take-off ground in the valley says 1800 m, but the plateau is 1500 m higher, so
the true height is 300 m and the photo shows 6 times less ground: the matcher would need a scale
of 0.17. The 15 % gate (or even the 35 % maximum) refuses it, and the right place is lost. A
rangefinder, or the height measured by earlier matches, avoids this. NAVERA's gate is
max(0.15, 2σh/h), so it widens when 2σh/h > 0.15, that is σh/h > 7.5 %.
