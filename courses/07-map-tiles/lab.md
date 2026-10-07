# Lab 7 — Read NAVERA's map, tile by tile

**Goal:** compute tile numbers from latitude/longitude and back, read real tiles out of NAVERA's
10 GB map with SQL, save them as pictures, and glue a 3 × 3 mosaic around any place with the place
marked on it.
**Time:** about 1 h 15.

Your file is [tiles_lab.py](file:./tiles_lab.py): six functions with a `# TODO`. The scripts
`explore_db.py`, `get_tile.py`, `mosaic.py` and `compare_navera.py` are ready and use your functions.
Answers to the quiz go in [answers.py](file:./answers.py).

Two maps are available, both read-only:

| Path | What |
|---|---|
| `/data/map.mbtiles` | NAVERA's real map: Sousse region, zoom 13–19, 1.15 million tiles, 10 GB |
| `/data/academy/07-map-tiles/sousse_small.mbtiles` | 88 tiles copied from it (around the Ribat of Sousse and Monastir marina), 2 MB — used by **✔ Check my work** |

## Step 1 — Look inside the map

```bash
python3 explore_db.py
```

The first run can take up to 20 seconds (it counts a million rows on a disk). You see the two tables,
the **metadata** and the number of tiles per zoom level. Find the line `altitude_zoom_map`: it is a
small dictionary "flying height in meters → zoom level".

Now ask your own SQL question. This one lists the tiles of zoom 13 (`LIMIT 5` = only the first 5 rows):

```bash
python3 explore_db.py "SELECT zoom_level, tile_column, tile_row, length(tile_data) FROM tiles WHERE zoom_level = 13 LIMIT 5"
```

`length(tile_data)` is the size of each picture in bytes. A tile of open sea can be tiny (under
1 000 bytes — a uniform picture compresses very well), a tile of city is much bigger.

> [!TASK]
> Answer **Q1** (the zoom for 300 m) and **Q2** (the number of zoom-17 tiles) in `answers.py`.

## Step 2 — tile_xy(): latitude/longitude → fractional tile position

Open [tiles_lab.py](file:./tiles_lab.py). Write **TODO 1**, `tile_xy(lat, lon, z)`, with the two formulas
of the course (step 3). Return `x, y` — both with their decimals.

> [!TIP]
> The Python names: `math.log` (ln), `math.tan`, `math.cos`, `math.pi`, `math.radians`. Remember: the
> latitude must be in radians *inside* `tan` and `cos`. `2 ** z` is "2 to the power z".

Try it in the interactive Python (`python3`, then):

```python
from tiles_lab import tile_xy
tile_xy(35.8277, 10.6388, 17)
```

You should get `(69409.46887…, 51547.56049…)`. Try zoom 1 at latitude 0, longitude 0: you should get
exactly `(1.0, 1.0)` — the corner shared by the 4 tiles of zoom 1.

## Step 3 — latlon_to_tile() and tile_to_latlon()

**TODO 2** `latlon_to_tile(lat, lon, z)`: call your `tile_xy()` and keep only the whole parts. Use
`int(math.floor(x))` (for positive numbers `int(x)` alone gives the same; `floor` is correct everywhere).

**TODO 3** `tile_to_latlon(x, y, z)`: the north-west corner of a tile (course, step 4). Return
`lat, lon` in **degrees** (`math.degrees` at the end).

```bash
python3 tiles_lab.py
```

The table shows the Ribat's tile at each zoom. Look at the numbers: from one zoom to the next, x and y
are (about) **doubled** — each tile was cut into 2 × 2.

> [!TASK]
> Finish **TODO 1**, **TODO 2** and **TODO 3**. Done means: the Ribat of Sousse is in tile
> 17/69409/51547, the north-west corner of tile 17/69388/51536 is (35.8534396195918, 10.579833984375)
> (the value of NAVERA's own test), and every point lies inside the tile you compute for it.

## Step 4 — meters_per_pixel()

**TODO 4** `meters_per_pixel(lat, z)`: course, step 5. Use the constants `EQUATOR_M` and `TILE_PX`
of the file.

```bash
python3 tiles_lab.py
```

The last two columns fill in: at zoom 17 a pixel is 0.968 m and a tile is 248 m wide; at zoom 19 the
tile is only 62 m wide — about the size of the Ribat itself.

> [!TASK]
> Finish **TODO 4**. Done means: 156 543 m per pixel at zoom 0 on the equator, ≈ 0.968 m at Sousse,
> zoom 17, and exactly half of that at zoom 18.

## Step 5 — read_tile(): your first SQL in Python

**TODO 5** `read_tile(db_path, z, x, y)` must:

1. open the file **read-only**: `conn = sqlite3.connect("file:" + db_path + "?mode=ro", uri=True)`;
2. run the `SELECT` of the course with **placeholders**:
   `conn.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?", (z, x, row))`
   where `row` is the **TMS row** `(2 ** z - 1) - y`;
3. take the first answer with `.fetchone()`: it is `None` when no tile matches, otherwise a tuple
   whose first element is the picture;
4. close the connection (`conn.close()`) and return `bytes(...)` of the picture, or `None`.

> [!WARNING]
> Never build the SQL by gluing numbers into the text (`"... zoom_level=" + str(z)`). The `?`
> placeholders are the safe way: `sqlite3` inserts the values itself. And never forget `mode=ro` —
> the check looks for it.

```bash
python3 get_tile.py 35.8277 10.6388 19
```

It prints the tile, its TMS row, its corner and its size, then saves `tile_19_277637_206190.png`. Click
it in the file list: you see the Ribat of Sousse from above, 62 m × 62 m. Try a few other places of the
lesson 6 table, and other zooms (13 to 19).

> [!QUESTION]
> Try `python3 get_tile.py 35.8277 10.6388 12`. Why does it say the tile is not in the map? Look at
> `minzoom` in the metadata.

> [!TASK]
> Finish **TODO 5** and answer **Q3** (the TMS row of y = 51547 at zoom 17). Done means: `read_tile()`
> returns the right JPEG bytes at zoom 13, 17 and 19, returns `None` for a missing tile, and opens the
> file with `mode=ro`.

## Step 6 — compare with NAVERA

```bash
python3 compare_navera.py
```

It puts your `tile_xy()` and `meters_per_pixel()` next to NAVERA's (`day_pkg/local_matcher.py`), your
corner next to `prepare_area.tile_nw()`, and reads the same tile with your `read_tile()` and with
NAVERA's `MBTilesReader`. Everything must be identical — including the bytes of the picture.

Notice the line **centre**: `prepare_area.tile_center()` gives a point half a tile south-east of the
corner. This is the difference that caused the 175 m bug of the course.

## Step 7 — a mosaic around any place

One tile is small. NAVERA always looks at the tiles **around** the position too: the drone may be near
the edge of its tile. `build_mosaic()` (already written, below the line in `tiles_lab.py`) reads the
3 × 3 tiles around a point and glues them into one 768 × 768 picture, then marks the point. It needs
one last function from you.

**TODO 6** `pixel_in_mosaic(lat, lon, z)`: where is the point in that mosaic, in pixels? The mosaic's
top-left tile is `(x − 1, y − 1)`. So the point is `(fractional x − (x − 1))` tiles from the left edge,
which you multiply by 256 to get pixels — same for y.

```bash
python3 mosaic.py 35.8277 10.6388 17
```

Open `mosaic.png`: the red circle must sit **on the Ribat** (the square fort in the medina, just south
of the big road), white lines show the tile borders, and a scale bar shows 200 m. If the circle is
somewhere else, your `pixel_in_mosaic()` is wrong; if the picture is upside-down in pieces, check your
TMS row.

Now Monastir marina, and a wider view at zoom 15:

```bash
python3 mosaic.py 35.7795 10.8320 17
```

```bash
python3 mosaic.py 35.7795 10.8320 15
```

> [!TASK]
> Finish **TODO 6**. Done means: the Ribat of Sousse is at pixel ≈ (376.0, 399.5) of its zoom-17
> mosaic, and `mosaic.py` produces a 768 × 768 `mosaic.png`.

Press **✔ Check my work**.

## Going further (optional)

- **Your street.** Is your home or school inside the map's `bounds` (10.3–10.9 east, 35.55–36.1 north)?
  If yes, make its mosaic at zoom 19. If not, `build_mosaic` leaves dark grey squares: those tiles are
  not in the file.
- **The edge of the map.** Make a mosaic of a point just outside the bounds, e.g. `35.56 10.31` at zoom
  13. Which tiles are missing? What should NAVERA do when the drone flies off its map?
- **Size of the map.** With SQL, compute the total size of all zoom-19 pictures:
  `SELECT SUM(length(tile_data)) FROM tiles WHERE zoom_level = 19` (it takes a while). What share of the
  10 GB is zoom 19? Why would someone choose not to carry zoom 19 on a drone?
