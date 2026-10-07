# Lab 17 report — the camera as a measuring instrument

Name:

## Key numbers

Write ONE number in each empty cell of the "value" column (digits only, a dot for decimals, a
minus sign if needed; no units). Most of them are in `results.json` after
`python3 experiments.py`; some you compute yourself.

| id | quantity | value |
|---|---|---|
| A | focal length of NAVERA's straightened Insta360 view, 111° on 1920 px (px) |  |
| B | vertical field of view of that view, 540 px high (deg) |  |
| C | footprint area of the lab camera at 150 m, pitch −20° (m²) |  |
| D | ground distance from the point under the drone to the image-centre point, pitch −20° (m) |  |
| E | height where the Insta360 view has the GSD of the zoom-17 map over Muscat (m) |  |
| F | the same height over Sousse (m) |  |
| G | height of photo B measured from the pad (m) |  |
| H | photo B: lowest height if the pad width is wrong by ±1 px (m) |  |
| I | photo B: highest height if the pad width is wrong by ±1 px (m) |  |
| J | photo T: the pad is this far EAST of the point under the drone (m) |  |
| K | photo T: the pad is this far NORTH of the point under the drone (m) |  |
| L | fitted scale in the Jebel Akhdar scenario |  |
| M | relative height uncertainty σh/h (%) above which NAVERA widens its 15 % scale gate |  |

## 1. Tilt

TODO: Where does the centre of the picture land when the drone pitches nose down, in front of
or behind the drone, and why? How do the footprint's shape and area change from 0° to −30°?
What does that mean for a match that assumes "the drone is at the image centre"? (40 words or more)

## 2. Muscat and Sousse

TODO: Why does the same zoom level have a different m/px in Muscat and in Sousse? Which zoom
would you prepare for a 300 m flight over Muscat, and is it the same for Sousse? (40 words or more)

## 3. Measuring the height with an object

TODO: Compare your heights for photos A and B with the truth (120 m and 210 m). Why is B less
precise? What does that tell you about measuring the height from the whole photo matched
to the map instead of from one object? (40 words or more)

## 4. Height uncertainty

TODO: Explain the Jebel Akhdar result (L): what scale does the matcher see, would NAVERA accept
the match, and which height source would have avoided the problem? Explain how you found M.
(40 words or more)
