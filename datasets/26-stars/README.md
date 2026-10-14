# Mission 26 data

- `bright_stars.csv` — 8 920 stars brighter than magnitude 6.5: HYG id `id`, Hipparcos number `hip`, Yale/HR number
  `hr` (when it has one), Bayer/Flamsteed name `bayer`, a `common` name for about 55 bright stars, position `ra_deg`,
  `dec_deg` (equinox and epoch J2000) and visual magnitude `vmag` (smaller = brighter).
- `photos/night_01.png … night_06.png` — synthetic photos from NAVERA Lite's star camera (1280 × 960 pixels,
  8-bit grey, 60° wide, ideal lens), at night, at six places.
- `photos.json` — for each photo: the UTC time, the IMU chip's attitude at the exposure (quaternion
  x, y, z, w; its north is MAGNETIC north), a prior position (the operating area), and the truth (true
  position and attitude, for measuring errors). Also the camera's K matrix and its mounting.
- `photo01_stars.csv`, `photo02_stars.csv` — where the catalogue stars fall in `night_01.png` and `night_02.png`
  (pixels, with their magnitude).

The photos are rendered for the course from the catalogue; they are not real sky photos.

## Source and licence of the catalogue

`bright_stars.csv` is derived from the **HYG star database v4.1** by David Nash (astronexus),
https://github.com/astronexus/HYG-Database, licensed under the Creative Commons Attribution-ShareAlike 4.0
International licence (CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/). HYG combines the Hipparcos,
Yale Bright Star and Gliese catalogues. Changes made for the course: only stars brighter than magnitude 6.5 kept
(the Sun removed), right ascension converted from hours to degrees, columns reduced, a `bayer` and a `common`
column added. This subset is shared under the same licence, CC BY-SA 4.0.

Attribution: "HYG star database v4.1, David Nash / astronexus, CC BY-SA 4.0 (subset)."
