# Lab 7 — Tiles, the map file and a 175 m bug

**Goal:** write NAVERA Lite's map part (`navera_lite/tiles.py`), use it to explore the course's map file of
Sousse, choose zooms for a camera, read tiles safely, build mosaics, reproduce NAVERA's corner bug (LOC-1)
and measure it around the world, then write a short map memo.
**Time:** 3 h 30 to 4 h 30 (a strong programmer: about 2 h 45; 4 h 30 or more if SQL and logarithms are new to you).
**Fast track:** if you know SQL and numpy, skip the 🧰 boxes and the "Stuck?" boxes; do "Going further".

Your files (📝 Code tab): [navera_lite/tiles.py](file:./navera_lite/tiles.py) (**your code**: ten functions,
`TODO 1–10`), [answers.py](file:./answers.py), [report.md](file:./report.md), and one ready-made tool you only
run: [run_tiles.py](file:./run_tiles.py) (runs your functions on the lab's situations and draws them).
`navera_lite/geo.py` is mission 06's part, finished.

Two maps, both read-only. Both are drawn from OpenStreetMap data: **© OpenStreetMap contributors**.

| Path | What |
|---|---|
| `/data/map.mbtiles` | the course map: Sousse region, Tunisia, zooms 13–19 (≈ 1 GB) |
| `/data/academy/07-map-tiles/sousse_small.mbtiles` | 88 tiles copied from it (the Ribat of Sousse, Port El Kantaoui marina), 1.3 MB |

| Lesson | Lab | You write |
|---|---|---|
| (nothing to read first) | Step 0 | a prediction |
| §5 (the 🧰 SQL box) | Step 1 | SQL queries, two answers |
| §1–§2 Mercator, tile numbers | Steps 2–3 | `mercator_y`, `tile_xy`, `tile_to_latlon` |
| §3 pixel size, zoom | Step 4 | `m_per_px`, `best_zoom`; zoom choice |
| §4–§5 TMS, MBTiles | Steps 5–6 | `open_map`, `read_tile`; impossible addresses |
| §6 mosaics, the corner bug | Step 7 | `latlon_to_pixel`, `pixel_to_latlon`, `tiles_in_circle`; LOC-1 measured |
| §5 metadata | Steps 8–9 | coverage, tile growth; the map memo |

> [!NOTE]
> **Predict, then run.** Each `PREDICT_…` in `answers.py` is written **before** you run the step. It is
> never marked right or wrong. Each function's docstring says its goal and gives one example with its
> result; `python3 run_tiles.py test` tries every example. The lesson shows how; the code is yours.

## Session 1 — Cartographer (about 1 h 30; 2 h if SQL is new to you)

## Step 0 — How big is the map?

No code. The course map covers about 25 km × 30 km around Sousse. A zoom-19 tile there is 62 m wide.

> [!TASK]
> **Predict** (`PREDICT_TILES` in `answers.py`): how many zoom-19 tiles does the map hold? Save the file
> (`Ctrl+S`). Then read lesson §5's 🧰 box (two minutes) and come back.

## Step 1 — Look inside the map

```bash
python3 run_tiles.py explore
```

Read the output from the top: the **schema** (the two `CREATE TABLE` statements, the indexes made by the two
PRIMARY KEYs (`sqlite_autoindex_…`) and one more, `tile_index`, on exactly the same three columns as the tiles
key: it is never used and only costs disk space, a small mistake of the tool that made the file), the
**pages** (page count × page size, against the size the file system reports), the **metadata**, and the
tiles per zoom. Compare the count at zoom 19 with your prediction (an area needs width × height tiles).

Now ask SQLite how it finds one tile:

```bash
python3 run_tiles.py explore "EXPLAIN QUERY PLAN SELECT tile_data FROM tiles WHERE zoom_level=17 AND tile_column=69409 AND tile_row=79524"
```

`SEARCH … USING INDEX` means a B-tree search, not a scan of 264 585 rows. Then measure the average size of a
tile per zoom (it reads every tile of zooms 13–16, about 4 000 tiles: under a second):

```bash
python3 run_tiles.py explore "SELECT zoom_level, COUNT(*), AVG(length(tile_data)) FROM tiles WHERE zoom_level <= 16 GROUP BY zoom_level"
```

Every tile is 256 × 256 pixels, yet the files get smaller as the zoom grows. (`length(tile_data)` is a tile's size in bytes;
`tile_data > 10000` would compare the bytes themselves and count every tile.)

> [!TASK]
> Write your own SQL (lesson §5 🧰: `COUNT(*)`, `length(tile_data)`, `WHERE … AND …`):
> 1. `BIG_TILES_Z17`: how many zoom-17 tiles are larger than 10 000 bytes?
> 2. `EXPLAIN_TILE_SIZE`: why are the tiles of higher zooms smaller files? (Think of what JPEG compresses
>    well, and of what a zoom-19 tile of Sousse shows; look at the pictures of lesson §2.)
>
> Also note, for Step 4, which zoom the metadata's `altitude_zoom_map` gives for 300 m and for 1 000 m
> (`{"2000": 13, …}` reads "at 2000 m, zoom 13").

<details><summary>Stuck? Hints</summary>

1. The first query of this step has the shape you need: `SELECT COUNT(*) FROM tiles WHERE … AND …`, in double
   quotes after `explore`.
2. `SQLite refused this query: no such column`: check the column names in the schema (`zoom_level`,
   `tile_column`, `tile_row`, `tile_data`). Put the whole query in double quotes, as shown.
</details>

## Step 2 — The Mercator ordinate and tile numbers (TODO 1, TODO 2)

Open the 📝 Code tab, then `navera_lite/tiles.py`. The top holds the constants (`TILE_PX`, `EQUATOR_M`,
`MAX_LAT`, `MAP_PATH`…). Each `TODO` function keeps its docstring and ends with `return None   # TODO…`:
replace that line with your code.

**TODO 1** `mercator_y(lat)`: lesson §1, on the unit sphere (R = 1). **TODO 2** `tile_xy(lat, lon, z)`:
lesson §2; use your `mercator_y`. Return the two **fractional** numbers.

```bash
python3 run_tiles.py test
```

The TODO 1 and TODO 2 lines must be ✔ (the others are later TODOs).

<details><summary>Stuck? Hints, one at a time</summary>

1. `math.log` (ln, the natural logarithm — not `math.log10`), `math.tan`, `math.pi`, `math.radians`. Only the
   latitude is in degrees.
2. `mercator_y(51.5007)` gives 1.775599 instead of 1.052085: the latitude went into `math.tan` in degrees.
   `math domain error`: the same, or the `/2` on φ is missing. 0.456915: `math.log10` — ln is `math.log`.
3. tile_xy gives y = 66 003.31 instead of 65 068.69 for Singapore: you counted rows from the south — look at
   the sign in lesson §2. y = 64 067.90: you forgot to divide mercator_y by π.
4. Check x alone first on the second example: (0°, 0°) at zoom 1 is the middle of a 2 × 2 world, x = 1.
</details>

## Step 3 — Back to latitude and longitude (TODO 3)

**TODO 3** `tile_to_latlon(x, y, z)`: the inverse of §2 (the formula is in "The way back"). It must work for
fractional x, y: no `int()` inside.

```bash
python3 run_tiles.py test
```

```bash
python3 run_tiles.py sousse
```

The table shows the Ribat at every zoom of the map and checks your inverse. Look at x and y from one zoom to
the next, and at the corner column.

> [!TASK]
> 1. With your `tile_xy` (a `python3 -c "…"` line), the zoom-18 tile of Port El Kantaoui marina (35.8930,
>    10.5965): write `KANTAOUI_TILE_Z18` as `(x, y)`, two whole numbers.
> 2. `EXPLAIN_SHARED_CORNER`: in the table, zooms 14 and 15 give the Ribat's tile the same north-west corner,
>    zooms 13 and 14 do not. Why? (Look at whether the tile numbers are even or odd.)

<details><summary>Stuck? Hints</summary>

1. `python3 -c "from navera_lite.tiles import tile_xy; print(tile_xy(35.8930, 10.5965, 18))"` prints the
   fractional coordinates; the tile is their whole part (`math.floor`).
2. (85.051129, −180.0) expected, you get (1.484422, −180.0): the latitude is in radians, `math.degrees(…)`.
3. Right longitude, wrong latitude: compare your brackets with lesson §2, "The way back", term by term.
4. Shared corners: a zoom-z tile is cut into 2 × 2 children at zoom z + 1. Which child has the same
   north-west corner as its parent?
</details>

## Step 4 — Pixel size and zoom (TODO 4, TODO 5)

**TODO 4** `m_per_px(lat, z)`: lesson §3, with `EQUATOR_M` and `TILE_PX`. **TODO 5**
`best_zoom(gsd_m, lat, zmin=13, zmax=19)`: the rule of §3 (🧰 log₂ and clamping); return an `int`, and raise
`ValueError` when `gsd_m ≤ 0`.

```bash
python3 run_tiles.py test
```

```bash
python3 run_tiles.py world
```

The table runs your functions from Lagos to Longyearbyen (Svalbard, 78° N); it does not use a camera. For
the tasks below, the lab's camera is the one of lesson §3's worked example: field of view 84°, 1 536 pixels
across. `math.tan` takes radians: `math.tan(math.radians(42))`.

> [!TASK]
> **Predict** (`PREDICT_ZOOM`) before you call `best_zoom`: at 1 000 m over Sousse, will your rule choose a
> finer or a coarser zoom than the map's `altitude_zoom_map` (Step 1), and by how many levels?

> [!TASK]
> With your functions (a `python3 -c "…"` line or a short script):
> 1. `BEST_ZOOM_SOUSSE_1000`: `best_zoom` for the lab's camera at 1 000 m over Sousse (35.8277°).
> 2. `ALT_MAX_Z19_SOUSSE_M`: the highest flying height (m, one decimal) at which `best_zoom` still gives 19
>    over Sousse. Find it with algebra (when is the GSD equal to the zoom-19 pixel?). A loop of 1 m steps finds
>    the first height that is NOT 19 (207 m): the answer is the last one that is, to one decimal.
> 3. `EXPLAIN_ZOOM`: compare your rule with the map's table at 300 m and at 1 000 m. Which one is coarser, and
>    why can that be a good choice for matching photos with the map? (Think of the number of tiles and of
>    small details.)

<details><summary>Stuck? Hints</summary>

1. `m_per_px(1.2834, 17)` gives 0.3385: `math.cos` got degrees. 305.67: the 256 pixels of a tile are missing.
2. best_zoom(0.352, 1.2834) gives 19: you rounded (`round`) or rounded up (`math.ceil`); the rule rounds
   DOWN, `math.floor`. 10 for the 100 m case: the result is not kept inside [zmin, zmax] (🧰 box). 13 for
   Singapore: you used `math.log` (ln); the zoom rule needs `math.log2` (log₂).
3. ✘ "it is a float": `np.floor` or `math.log2` alone give floats; `math.floor` gives an int. Wrap the
   final result in `int(…)` to be safe.
4. GSD = 2·H·tan(42°)/1536 (radians inside tan!). Zoom 15 at 1 000 m, the same as the map's table: tan got
   DEGREES. For item 2: when is the GSD exactly the zoom-19 pixel at Sousse? Solve that for H.
</details>

> [!TIP] 🏅 End of session 1 — Cartographer
> Press **✔ Check my work**. When the checks of TODO 1–5 and Steps 1–4 pass, you earn the **Cartographer**
> badge. If the class session ends here, stop here.

## Session 2 — Tile hunter (about 1 h 45)

Read lesson §4–§6 first.

## Step 5 — Read a tile (TODO 6, TODO 7)

**TODO 6** `open_map(path=None)`: lesson §5 and its 🧰 box. `None` means `MAP_PATH`; raise
`FileNotFoundError` when the file does not exist (`os.path.exists`): SQLite would otherwise create an empty
database or give an unclear error.

**TODO 7** `read_tile(db, z, x, y)`: in this order — check the address (the docstring's rules, **z first**,
`raise ValueError("…")`), compute the TMS row (§4), ask for the tile with three `?` placeholders,
return `None` when no row comes back, otherwise the BLOB as `bytes`.

<details><summary>🧰 Python: checking an argument and raising</summary>

```python
import numbers
def scale(v):
    # numbers.Integral = any whole number: int, and NumPy's int64/int32 (later missions compute tiles with
    # NumPy); not a float, not a text. True is an int in Python: refuse bool explicitly.
    if isinstance(v, bool) or not isinstance(v, numbers.Integral):
        raise ValueError(f"v must be a whole number, got {v!r}")
    if not 0 <= v <= 10:                                 # a chained comparison
        raise ValueError(f"v must be in [0, 10], got {v}")
    return 2 ** v
scale(3)       # 8          scale(np.int64(3)) also gives 8;  scale(3.0) raises ValueError
# sqlite3 does not know NumPy integers: it sends np.int64(17) as 8 raw bytes, and the query silently finds
# nothing. After the checks, convert:  z, x, y = int(z), int(x), int(y)
scale("3")     # ValueError: v must be a whole number, got '3'
```
</details>

```bash
python3 run_tiles.py test
```

```bash
python3 run_tiles.py tile 35.8277 10.6388 19
```

Open `out/tile_19_277637_206190.png`: the Ribat seen from above, 62 m wide — a square fort with a courtyard in
the middle. Streets or a park instead: your TMS row is one off (hint 5). Now a place that is not in the
map:

```bash
python3 run_tiles.py tile 1.2834 103.8607 17
```

The tile number is computed, but `read_tile` must return `None`: the course map has no tile of Singapore.

> [!TASK]
> Write `TMS_ROW_KANTAOUI_Z18`: the `tile_row` stored in the file for your `KANTAOUI_TILE_Z18`. Then check it
> against a known fact: the zoom-18 tile of Port El Kantaoui marina is **9 767 bytes** long.
> `python3 run_tiles.py explore "SELECT length(tile_data) FROM tiles WHERE zoom_level=18 AND tile_column=X AND tile_row=ROW"`
> (your numbers in place of X and ROW) must print 9767. Another size is a neighbour tile: being one off in the
> row number is the classic mistake (a neighbour also returns a row, so "one row came back" proves nothing).

<details><summary>Stuck? Hints</summary>

1. The connect line is in lesson §5's 🧰 box; with the path in a variable, build the text with `quote(path)`
   (already imported at the top of tiles.py). Keep `uri=True`: without it some SQLite builds read the whole text as a file name, `?mode=ro` included.
2. read_tile returns `None` for the Ribat: the TMS flip is missing (you asked for row y, the file has
   2^z − 1 − y), or the order of the values in the tuple is not the order of the `?`.
3. `Incorrect number of bindings`: three `?`, three values in the tuple.
4. `TypeError: 'NoneType' object is not subscriptable`: `fetchone()` found no row (wrong TMS row?) and you
   wrote `row[0]` before checking `row is None`.
5. A size other than 9 767 (your row is 159 108?), or a Ribat picture without the fort: (2^z − 1) − y, the
   − 1 matters.
6. `run_tiles.py test` says NumPy integers give None: sqlite3 sends `np.int64` as 8 raw bytes; after your checks
   convert with `int()` (🧰 box).
</details>

## Step 6 — Impossible addresses

A tile server receives z/x/y from the outside world (lesson §5, NAVERA's WEB-4). Your `read_tile` is the place
that refuses impossible addresses. The tool below calls it with five of them, each in its own Python process,
and times each answer (a check of z is instant; building 2**z for a billion takes seconds):

```bash
python3 run_tiles.py guard
```

All five must say ✔ `ValueError`, quickly. "took 6.4 s" or "still running" means your function built 2**z before
checking z. `1 << z` is fast enough to pass this timer (0.02 s) but still builds a 125 MB number: ✔ Check my work
also reads the order of your code.

> [!TASK]
> `EXPLAIN_GUARD`: why must z be checked before 2**z is computed, and why are z, x, y passed as `?` values
> instead of being written into the SQL text?

<details><summary>Stuck? Hints</summary>

1. "a row given as text — TypeError '<=' not supported between instances of 'int' and 'str'": the
   `isinstance(…, numbers.Integral)` test is missing or comes after the range test — a text "51547" is not a
   tile number.
2. "OverflowError" or "TypeError" instead of ValueError: do the checks yourself at the top of the function,
   before any computation, and `raise ValueError(...)`.
</details>

## Step 7 — Mosaics, the corner bug and the search circle (TODO 8, 9, 10)

**TODO 8** `latlon_to_pixel(lat, lon, z, x0, y0)` and **TODO 9** `pixel_to_latlon(px, py, z, x0, y0)`:
lesson §6 (TODO 9 is its ✏️ check: write the way back yourself).

```bash
python3 run_tiles.py test
```

```bash
python3 run_tiles.py mosaic 35.8277 10.6388 17
```

Open `out/mosaic.png`: the red circle must sit on the Ribat (the square fort with a courtyard), yellow is the
north-west corner of its tile, green the tile's centre. Yellow-to-green is the corner bug on the ground. The
tool also converts the red pixel back: it must give the point again.

> [!TASK]
> **Predict** (`PREDICT_CORNER`) before the next run: at which latitude is the zoom-17 corner bug exactly
> **half** of its size on the equator? And at which latitude is it exactly **100 m**? (The table will show
> whether you are right: look between the two places that bracket your answer.)

```bash
python3 run_tiles.py corner
```

> [!TASK]
> 1. `CORNER_QUITO_M`: Quito (−0.1807, −78.4678) is not in the tool's table. Compute its corner bug yourself,
>    the way the tool does (your tile functions and `geo.haversine_m` from the corner to the centre of Quito's
>    zoom-17 tile), with a `python3 -c "…"` line or a short script. The tool measures on the sphere of mission
>    06, so it differs from tile width/√2 by about 0.1 %.
> 2. `EXPLAIN_CORNER`: why is the same bug larger near the equator?
> 3. `EXPLAIN_FIX`: NAVERA's fix publishes the tile's CENTRE. That is exact only when the photo's centre falls
>    on the tile's centre. How far off can it still be, and what would be the right position to publish if the
>    matcher tells you which pixel (u, v) of the tile the photo's centre fell on?

**TODO 10** `tiles_in_circle(lat, lon, r_m, z)`, the least guided function of the mission: NAVERA's day vision
compares a photo only with the tiles within 600 m of its last position (lesson "In NAVERA"). Read the
docstring twice. Before coding, answer on paper: around which tile do you search, and how many tiles on each
side must you look at so that no tile whose centre is within r_m is missed? (`m_per_px` gives the size of a
tile in metres.)

```bash
python3 run_tiles.py test
```

> [!TASK]
> With your `tiles_in_circle`: how many zoom-17 tiles does a 600 m search compare at the Ribat (NAVERA says
> about 21), and `CIRCLE_TILES_REYKJAVIK`: how many at Reykjavik (64.1417, −21.9266), same radius and zoom?
> Why so many more?

> [!TASK]
> `EXPLAIN_MARGIN`: a tile k columns away has its centre at least (k − ½)·w from the point (w = the tile width in
> metres). How many tiles on each side does that ask you to look at for a radius r_m? Why might one extra tile of
> margin still be wise? (Think of how a tile's size in metres changes from row to row, and of large radii.)

<details><summary>Stuck? Hints</summary>

1. latlon_to_pixel gives (1.53, 1.69) instead of (390.88, 432.45): multiply by `TILE_PX`.
2. pixel_to_latlon(128.0, 128.0, 17, 103350, 65068) gives a longitude near 104.21 (about 39 km off):
   pixels and tile numbers are not the same unit.
3. The mosaic's red circle is not on the fort but the yellow and green marks look right: latlon_to_pixel
   subtracted the wrong tile (x0, y0 is the TOP-LEFT tile of the mosaic, not the point's tile). If the whole
   map looks shifted by exactly one tile (the fort 256 px below the red circle) and TODO 8 is ✔ in `test`, it is
   not latlon_to_pixel: your read_tile reads the neighbouring row (TMS flip, Step 5 hint 5).
4. TODO 10 returns 1 tile at the Ribat for 300 m instead of 5: you looked at the point's tile only; a 248 m
   tile means the circle reaches into its neighbours. A list that is right but in another order: `sorted(…)`.
5. TODO 10, how far to look: how close to the point can the centre of a tile k columns away be, at the least?
   Write it with the tile width w, then ask which k can still be within r_m.
</details>

## Step 8 — Metadata against measurement

```bash
python3 run_tiles.py coverage
```

It compares the metadata's `bounds` with the rectangle the tiles really cover at zooms 15–19 (from the
smallest and largest column and row, with your `tile_to_latlon`).

Zooms 13 and 14 are left for you:

> [!TASK]
> 1. `COVER_WEST_Z13_DEG`: with SQL find the smallest `tile_column` at zoom 13 (`MIN(tile_column)`), then
>    convert it with your `tile_to_latlon` (which corner of that tile gives the west edge?). The `coverage` table
>    gives zooms 15–19 only: compare your edge with theirs.
> 2. `EXPLAIN_BOUNDS`: the metadata says the map starts at 10.47° E. Why do the zoom-13 tiles reach further
>    west, and why do the edges match 10.47° almost exactly from zoom 15 on?
> 3. `EXPLAIN_GROWTH`: from Step 1, the tiles per zoom grow by 3.56, 3.71, 3.80, 3.94, 3.98 and 4.00. Each tile
>    has 4 children, so why not exactly 4 at low zooms? (Think of the tiles on the edge of the area.)

## Step 9 — The map memo

Write [report.md](file:./report.md) (150–400 words, your own words, keep the three headings) for an engineer
who will use this map in a navigation stack. Quote your numbers with their units.

> [!TASK]
> report.md has the three headings, at least 150 words, and quotes: the zoom-17 pixel size in Quito (or
> Singapore) and in Reykjavik, the zoom your rule chooses at 1 000 m over Sousse, the number of tiles or the
> size of the file, and the corner error in Sousse and in Quito.

## Step 10 — Check, then look back

Press **✔ Check my work**: it tests your functions on places and tiles they have never seen. When every
check passes, you earn the **Tile hunter** badge. Then look back, without the lesson:

1. Explain LOC-1 to a colleague in three sentences, with the number.
2. Which of your predictions was the most wrong? What did you assume?
3. Name one place in this lab where a wrong unit would give no error at all, only a wrong answer.

Write your answers in `LOOK_BACK` in `answers.py` if you want your teacher to read them (not graded).

## Going further (optional)

- **The true ellipsoidal Mercator.** Write `mercator_y_3395(lat)` (lesson §1, optional box) and plot the
  difference with Web Mercator in metres for 0–80°. At which latitude does it exceed one zoom-17 tile?
- **Quadkeys.** Some map services address a tile with one string: each zoom adds a digit 0–3 made of one bit
  of x and one of y. Write `quadkey(x, y, z)` and its inverse; check that a tile's quadkey starts with its
  parent's.
- **A map for Reykjavik.** How many zoom-17 tiles would a 10 km × 10 km area at Reykjavik need, and how many
  MB with Step 1's average tile sizes? Compare with the same area at Sousse.
- **map_patch.** Read `map_patch` in `tiles.py` (given) and use it with `patch_origin` and your
  `pixel_to_latlon` to find the (lat, lon) of the top-left pixel of a 640 × 480 patch around the Ribat.
- **Fly your own geo.** `cp ../06-coordinates/navera_lite/geo.py navera_lite/` and rerun every step: does
  anything change?
