# Lab 7 — Web Mercator, tiles and NAVERA's map file

**Goal:** implement the Web Mercator tile mathematics (projection, tile numbers, inverse, scale,
zoom choice, mosaic pixels), read real tiles out of NAVERA's 10 GB MBTiles file with SQL, verify
everything against NAVERA's own code, then compute scales for cities around the world and write a short report.
**Time:** about 3 hours.

| File | Role |
|---|---|
| [tiles_lab.py](file:./tiles_lab.py) | **your work**: ten functions marked `TODO` |
| `explore_db.py` | looks inside an MBTiles file, or runs your SQL (ready) |
| `get_tile.py`, `mosaic.py` | read one tile / build a mosaic with your functions (ready) |
| `compare_navera.py` | your functions against NAVERA's (ready) |
| `analysis.py` | world scales, map facts, corner bug → `results.json` (ready) |
| [report.md](file:./report.md), [answers.py](file:./answers.py) | **your work**: report and quiz |

Two maps, both read-only:

| Path | What |
|---|---|
| `/data/map.mbtiles` | NAVERA's test map: Sousse region, Tunisia, zoom 13–19, 1.15 million tiles |
| `/data/academy/07-map-tiles/sousse_small.mbtiles` | 88 tiles copied from it (Ribat of Sousse, Monastir marina), 2 MB — used by **✔ Check my work** |

NAVERA's test map covers Sousse, Tunisia. The other cities of this lab (Singapore, Reykjavik…) are used
for computations only: there is no imagery of them.

## Step 1 — Look inside the map

```bash
python3 explore_db.py
```

The first run can take about 20 s (it counts more than a million index entries on disk). Read the
output from the top: the **schema** (the two `CREATE TABLE` statements and the automatic index of
the primary key), the **pages** (page count × page size, and the size reported by the file system —
compare them), the **metadata**, and the number of tiles per zoom. Note the line
`estimated_size_mb` and compare it with the measured size.

Ask SQLite how it finds one tile:

```bash
python3 explore_db.py "EXPLAIN QUERY PLAN SELECT tile_data FROM tiles WHERE zoom_level=17 AND tile_column=69409 AND tile_row=79524"
```

`SEARCH ... USING INDEX` means a B-tree search, not a scan. Now measure the average tile size at
the three lowest zooms (this reads ~4700 pictures, a few seconds):

```bash
python3 explore_db.py "SELECT zoom_level, COUNT(*), AVG(length(tile_data)) FROM tiles WHERE zoom_level <= 15 GROUP BY zoom_level"
```

> [!TASK]
> Answer **Q1** (the zoom that `altitude_zoom_map` gives for 300 m) and **Q2** (the number of zoom-17
> tiles) in [answers.py](file:./answers.py).

## Step 2 — The Mercator ordinate (TODO 1 and TODO 2)

Open [tiles_lab.py](file:./tiles_lab.py). **TODO 1** `mercator_y(lat)`: ln tan(π/4 + φ/2) with φ in
radians (`math.log`, `math.tan`, `math.pi`, `math.radians`). **TODO 2** `inverse_mercator_y(y)`:
2·atan(eʸ) − π/2 (`math.exp`, `math.atan`), returned in **degrees**.

```bash
python3 -c "from tiles_lab import *; print(mercator_y(51.5007), inverse_mercator_y(mercator_y(51.5007)), mercator_y(MAX_LAT))"
```

Expected: 1.0520853127, 51.5007 (to ~10⁻¹⁴) and π = 3.14159… — the latitude where Web Mercator stops.

> [!WARNING]
> `ValueError: math domain error` here means `math.log()` received a number ≤ 0: you passed degrees
> where radians were expected (see the course). Fix the unit, do not "protect" the log.

## Step 3 — Tile numbers and their inverse (TODO 3, 4, 5)

- **TODO 3** `tile_xy(lat, lon, z)`: x is a direct proportion of the longitude; y uses your
  `mercator_y()`. Return the two **fractional** numbers.
- **TODO 4** `latlon_to_tile()`: `int(math.floor(...))` of both.
- **TODO 5** `tile_to_latlon(x, y, z)`: longitude from x; latitude with `inverse_mercator_y()` of
  π·(1 − 2y/n). It must work for fractional x, y (centre = x + 0.5, y + 0.5).

```bash
python3 tiles_lab.py
```

The table shows the Ribat of Sousse at every zoom of NAVERA's map: from one zoom to the next, x and y
double (each tile is cut into 2 × 2). Now the worked example of the course, Marina Bay Sands in Singapore:

```bash
python3 -c "from tiles_lab import *; print(tile_xy(1.2834, 103.8607, 17), latlon_to_tile(1.2834, 103.8607, 17))"
```

You must find (103350.53…, 65068.69…) and tile (103350, 65068).

> [!TASK]
> **TODO 1–5 done** means: `mercator_y(35.8277)` = 0.670562, `mercator_y(85.0511287798)` = π, the
> inverse is exact; the Ribat is in 17/69409/51547; Singapore in 17/103350/65068; the NW corner of
> 17/69388/51536 is (35.8534396195918, 10.579833984375) — the value of NAVERA's unit test; every point
> lies inside the tile you compute for it.

## Step 4 — Scale and zoom (TODO 6 and TODO 7)

**TODO 6** `meters_per_pixel(lat, z)` with `EQUATOR_M` and `TILE_PX`. **TODO 7** `zoom_for_gsd(lat,
gsd_m, zmin, zmax)`: `math.floor(math.log2(...))`, then clamp with `max(zmin, min(zmax, z))`, and
return an `int`.

```bash
python3 -c "from tiles_lab import *; print(meters_per_pixel(1.2834, 17), meters_per_pixel(64.1417, 17), zoom_for_gsd(1.2834, 0.352, 13, 19))"
```

Expected: 1.1940 m (Singapore), 0.5209 m (Reykjavik), zoom 18.

> [!TASK]
> **TODO 6–7 done** means: 156 543.03 m/px at zoom 0 on the equator, Singapore 1.1940 and Reykjavik
> 0.5209 m/px at zoom 17, zoom 18 exactly half of zoom 17; `zoom_for_gsd()` returns the right integer zoom,
> clamped to [zmin, zmax].

## Step 5 — Read a tile with SQL (TODO 8)

**TODO 8** `read_tile(db_path, z, x, y)`:

1. `conn = sqlite3.connect("file:" + db_path + "?mode=ro", uri=True)` — read-only;
2. `conn.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?", (z, x, row))`
   with `row = (2 ** z - 1) - y` (the TMS row);
3. `.fetchone()` → `None` if no tile, else a tuple whose element 0 is the JPEG;
4. `conn.close()`, then return `bytes(...)` or `None`.

```bash
python3 get_tile.py 35.8277 10.6388 19
```

Open `tile_19_277637_206190.png`: the Ribat of Sousse seen from above, 62 m wide. Now ask for Singapore:

```bash
python3 get_tile.py 1.2834 103.8607 17
```

The tile number is computed, but `read_tile()` returns `None`: NAVERA's map has no tile of Singapore.

> [!TASK]
> **TODO 8 done** means: `read_tile()` returns the exact JPEG bytes (checked by md5) of three tiles at
> zoom 13, 17 and 19, `None` for a missing tile, and the file is opened with `mode=ro`. Answer **Q3**
> (the TMS row of y = 51547 at zoom 17).

## Step 6 — Mosaic pixels (TODO 9 and TODO 10)

**TODO 9** `latlon_to_pixel(lat, lon, z, x0, y0)` and **TODO 10** `pixel_to_latlon(px, py, z, x0, y0)`:
the two formulas of section 6 of the course.

```bash
python3 mosaic.py 35.8277 10.6388 17
```

Open `mosaic.png`: the red circle must sit on the Ribat (the square fort in the medina), the yellow
mark is the NW corner of its tile and the green mark the tile's centre — the 175 m of the corner bug,
visible on the ground. The program also converts the red pixel back to lat/lon: it must give the
input again. Then a larger view (5 × 5 tiles at zoom 15) of Monastir marina, written to **another
file** with `--out` so that your `mosaic.png` of the Ribat stays as it is:

```bash
python3 mosaic.py 35.7795 10.8320 15 --radius 2 --out mosaic_monastir.png
```

Open `mosaic_monastir.png`: 1280 × 1280 pixels, the marina in the middle.

> [!TASK]
> **TODO 9–10 done** means: the Ribat is at pixel (376.03, 399.49) of the mosaic whose top-left tile
> is (69408, 51546); pixel → lat/lon is the exact inverse; pixel (100.25, 37.5) of tile 17/69409/51547
> gives NAVERA's value; `mosaic.py` writes a 768 × 768 `mosaic.png` (radius 1 = 3 × 3 tiles).
> The checker builds its **own** test mosaic (Monastir marina, zoom 17, from the small map) and then
> puts your `mosaic.png` back: you do not need to prepare a particular picture.

## Step 7 — Compare with NAVERA

```bash
python3 compare_navera.py
```

Every pair of numbers must be identical: your `tile_xy` and `meters_per_pixel` against
`local_matcher`; your corner and centre against `prepare_area.tile_nw/tile_center` and the bug fix
`tile_center_latlon`; your `pixel_to_latlon` against `tile_px_to_latlon`; and the bytes read by your
`read_tile` against the simulator's `MBTilesReader`.

## Step 8 — Analysis and report

```bash
python3 analysis.py
```

It prints and saves to `results.json`: for eight places (seven cities on six continents, plus Sousse) the zoom-17
pixel and tile size, the scale factor 1/cos φ, the EPSG:3857 − EPSG:3395 offset, and the zoom your
`zoom_for_gsd()` picks for an example camera (84°, 1536 px, 300 m); the zoom by flying height over
Singapore next to the map's own `altitude_zoom_map`; the corner-bug size in Sousse, Singapore and
Reykjavik; the
pixel round-trip error; and the map-file facts.

Write [report.md](file:./report.md) (150–400 words, your own words, three headings):

- **## World scales** — zoom-17 m/px in Singapore and Reykjavik and why they differ; your zoom rule against
  `altitude_zoom_map`: which would you use, and why?
- **## The map file** — the real size in GB, the metadata's `estimated_size_mb`, which you trust and
  why; how a tile is found among a million (index, query plan).
- **## The corner bug** — what was wrong, 175 m in Sousse, how much in Singapore, and why different.

> [!TASK]
> `results.json` exists and is right (the check verifies it), and `report.md` has the three headings,
> at least 150 words, and quotes: Singapore's and Reykjavik's zoom-17 m/px, the real size in GB, the
> 36467 MB estimate, and the corner error in Singapore in meters. Then press **✔ Check my work**.

## Going further (optional)

- **The true ellipsoidal Mercator.** Write `mercator_y_3395(lat)` and plot, for 0–60°, the
  difference with Web Mercator in meters and in zoom-17 pixels. At which latitude does the offset
  exceed one zoom-0 tile?
- **Quadkeys.** Some map servers address tiles with one string (Bing "quadkeys"): each zoom level adds
  one digit 0–3 from the bits of x and y. Write `quadkey(x, y, z)` and its inverse, and check that a
  tile's quadkey is a prefix of its children's.
- **Size of a mission.** With SQL, compute the bytes of all zoom-17 tiles inside a 5 km corridor
  around a route of your choice in the map (use `prepare_area.py` as a model). How much storage would
  the same corridor need at zoom 19? Why would NAVERA not carry zoom 19 for a long route?
