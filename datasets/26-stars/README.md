# Mission 26 data

- `bright_stars.csv` — 8 404 stars brighter than magnitude 6.5: catalogue number `hr`, Bayer/Flamsteed name
  `bayer`, a `common` name for about 50 bright stars, position `ra_deg`, `dec_deg` (equinox and epoch J2000)
  and visual magnitude `vmag` (smaller = brighter).
- `photos/night_01.png … night_06.png` — synthetic photos from NAVERA Lite's star camera (1280 × 960 pixels,
  8-bit grey, 60° wide, ideal lens), at night, at six places.
- `photos.json` — for each photo: the UTC time, the IMU chip's attitude at the exposure (quaternion
  x, y, z, w; its north is MAGNETIC north), a prior position (the operating area), and the truth (true
  position and attitude, for measuring errors). Also the camera's K matrix and its mounting.
- `photo01_stars.csv`, `photo02_stars.csv` — where the catalogue stars fall in `night_01.png` and `night_02.png`
  (pixels, with their magnitude).

The photos are rendered for the course from the catalogue; they are not real sky photos.

## Source and licence of the catalogue

`bright_stars.csv` is a subset (columns and stars brighter than 6.5 kept, common names added) of
**The Bright Star Catalogue, 5th Revised Edition (Preliminary Version)**, D. Hoffleit and W. H. Warren Jr.,
Astronomical Data Center, NSSDC/ADC, 1991 — CDS catalogue V/50,
https://cdsarc.cds.unistra.fr/viz-bin/cat/V/50. Neither the CDS ReadMe nor the Harvard readme of the catalogue
states a licence; an earlier documentation file of the machine-readable catalogue describes it as public domain.
It is distributed freely by CDS, which asks users to acknowledge it, and is shared here for teaching with this
citation: "This research has made use of the VizieR catalogue access tool, CDS, Strasbourg, France."
