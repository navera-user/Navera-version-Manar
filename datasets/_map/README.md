# `_map/` — the OpenStreetMap map of Sousse (NAVERA Academy)

Our own map of Sousse, rendered from OpenStreetMap data. It replaces the ESRI satellite MBTiles
in the course (we may not redistribute ESRI imagery, and bulk downloading tile.openstreetmap.org
is forbidden — so we render the tiles ourselves from the Geofabrik extract).

| Output | Path | Size |
|---|---|---|
| Map tiles z13–19, JPEG q88, TMS rows | `~/academy-data/osm_sousse.mbtiles` | 980 MB, 264 585 tiles |
| Exact source PBF (+ `.sha256`, `.md5`) | `~/academy-data/osm/tunisia-2026-10-12.osm.pbf` | 84 MB |
| Bbox extract (ODbL "data on request") | `~/academy-data/osm/sousse-bbox-2026-10-12.osm.pbf` | 3 MB |
| Render database (EPSG:3857, used by `render_view`) | `~/academy-data/osm/sousse_osm.sqlite` | 10 MB |
| Build record (PBF date, sha256, timings) | `~/academy-data/osm/build_state.json`, `~/academy-data/osm_sousse.build.json` | |
| Previews | `~/academy-data/previews/` | |

Area: lat 35.70–35.97, lon 10.47–10.75 (Hergla → Sousse → Monastir airport, inland to M'saken).
Per zoom: z13 63, z14 224, z15 832, z16 3 162, z17 12 444, z18 49 572, z19 198 288 tiles.

## Files here

- `make_map.sh` — the entry point: installs the tools into a private dir if missing, sets
  `PYTHONPATH`/`PROJ_DATA`, runs `make_map.py`.
- `make_map.py` — steps `download extract convert style render previews verify` (all by default).
- `osmdata.py` — bbox extract (pyosmium) and OSM → SQLite conversion (classes, sea polygons
  from `natural=coastline`, deterministic roof colours from the OSM id, R-tree indexes).
- `style_map.py` — generates the Mapnik styles below + `patterns/*.png`. Edit the style here, not the XML.
- `style_map.xml` — the cartographic style (tiles and `render_view(style="map")`).
- `style_pseudo_*.xml` — layers of the pseudo-satellite style.
- `render_view.py` — synthetic downward camera views (see below).

## Rebuild

```bash
cd ~/navera-academy-v2/datasets/_map
./make_map.sh                    # everything: ~3 min on the Jetson (6 cores)
./make_map.sh style render previews verify      # after a style change: ~1 min
OSM_PBF=/path/to/tunisia-YYYY-MM-DD.osm.pbf ./make_map.sh   # rebuild from a kept PBF
```

Measured on 2026-10-13 (Jetson, 6 cores, 7 GB): download 10 s, extract 108 s, convert 14 s,
render 45 s (264 585 tiles, 8×8 metatiles, 6 processes), verify 3 s.
`OSM_OUT` changes the output dir (default `~/academy-data`), `OSM_WORKERS` the process count.

Tools: mapnik 4.3.2, osmium (pyosmium) 4.3.1, shapely 2.1.2, installed with
`pip install --no-deps --target ~/osmrender/pylib ...` (194 MB). Never into the shared user site:
`--no-deps` keeps the system numpy 1.26 (must stay < 2). Gotchas: the map srs must be
`epsg:3857`; `PROJ_DATA` must point to `pylib/mapnik/share/proj`; Mapnik reads the
pre-projected SQLite (OGR on raw .osm is ~150× slower).

## Licence and attribution — duties

- OSM data is © OpenStreetMap contributors, licensed **ODbL 1.0**. Our tiles and views are a
  *Produced Work*: we may use and sell the course with them, but **every place that shows the map
  must show "© OpenStreetMap contributors" linked to https://www.openstreetmap.org/copyright**
  (map viewers, mission pages, dashboards, datasets README, exported images in slides).
- The MBTiles carries it in `metadata`: `attribution` (plain text), `attribution_url`,
  `attribution_html` (the link), `license` = "Map data ODbL (OpenStreetMap); rendered tiles:
  produced work", `source` (PBF file, data timestamp, sha256), `osm_data_date`, `osm_pbf_sha256`.
  `render_view(..., return_meta=True)` returns `meta['attribution']` too.
- The SQLite database and the PBF extract are a *Derivative Database* of OSM: if we give them to
  anyone (students included), they are ODbL too. If someone asks for the data behind the
  produced work, we hand over `sousse-bbox-<date>.osm.pbf` (that is why it is kept) — and
  `osmdata.py` documents the transformation.

## `render_view` — synthetic camera views

```python
import sys, os
sys.path.insert(0, os.path.expanduser('~/navera-academy-v2/datasets/_map'))
from render_view import render_view          # adds ~/osmrender/pylib and PROJ_DATA itself
img = render_view(35.8277, 10.6388, heading_deg=30, alt_m=300, out_px=512, seed=1,
                  style='pseudo', effects='medium')                # numpy BGR uint8
img, meta = render_view(..., return_meta=True)  # true pose, effects drawn, corner lat/lon, homography
```

- `alt_m` or `ground_size_m` (nadir footprint width), `fov_deg` (default 60), `out_px` int or (w, h).
- `style='map'`: same XML and per-zoom rules as the tiles. `style='pseudo'`: procedural textures per
  land class, fixed in world coordinates (the same place looks the same whatever the seed or
  view); roof colour per building from its OSM id; offset shadows (sun in the south-east);
  tree crowns (olive grid in orchards); sea waves; procedural rural parcels and a synthetic
  urban fabric where OSM has no data (Sousse has only ~10 k buildings in OSM). It is a drawing,
  not imagery — and it does not resemble the map style (ORB finds ~0–10 inliers between them).
- `effects`: `'light' | 'medium' | 'strong'` (random, from `seed`) or a dict with `pitch_deg,
  roll_deg, yaw_err_deg, scale_err, blur, motion_blur, noise, gamma, color, brightness, illum,
  vignette, jpeg, clouds, occlusion` (see the module docstring).
- Speed (512 px): pseudo ≈ 1.0–1.2 s, map ≈ 0.2 s per view. One Mapnik map per process (cached).
- Env: `NAVERA_OSM_PYLIB` (default `~/osmrender/pylib`), `NAVERA_OSM_DB`
  (default `~/academy-data/osm/sousse_osm.sqlite`).
- Demo: `PYTHONPATH= python3 render_view.py <outdir>` writes sample views.

ORB check (3000 features, 512 px, see `~/academy-data/previews/orb_comparison.txt`): pseudo views
give ~2 500–3 000 keypoints everywhere (map style: 1–2 300, almost none in the countryside); a
pseudo view with `effects='medium'` still matches the clean one with 75–1 100 RANSAC inliers.

## Pixel-centre convention (important for vision missions)
`render_view` puts the requested (lat, lon) at pixel (w/2, h/2) — the corner-based convention — while the course
(mission 08 `like_map`, OpenCV-style) uses the pixel CENTRE (w−1)/2, (h−1)/2. The difference is half a pixel and
it rotates with the heading. Mission 08 compensates by rendering one extra pixel each way and cropping the first
row and column (solutions/08-images/make_dataset.py). A constant ≈0.2 map-pixel offset remains inside render_view.
Missions 21–25: do the same, or state the convention you use. Mission 18's photos are unaffected (no sub-pixel
truth is graded there).
