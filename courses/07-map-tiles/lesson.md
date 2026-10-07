# Map projections and tiles: Web Mercator, the tile pyramid and MBTiles

A drone flying over **Muscat** at 300 m takes a photo every second. To find where it is without GPS,
NAVERA must compare that photo with the satellite map of the area — not the whole map, but the few
map squares around its last known position, read **now**. NAVERA's map of its test area is one file
of more than a million small pictures. You cannot search a million pictures for every photo; you
must **compute** which ones you need from a latitude and a longitude, and read only those.

Every web map works this way: the world is flattened with the **Web Mercator** projection, cut into
a **pyramid of 256 × 256 tiles**, and each tile has an address z/x/y that is a simple function of
(lat, lon). In this lesson you derive the projection, compute scales for Omani latitudes, open the
map file (an **SQLite** database) yourself, and meet a real NAVERA bug that cost 175 m per fix.

> [!NOTE]
> **The data.** NAVERA's satellite map, `/data/map.mbtiles`, covers the region of **Sousse,
> Tunisia** — NAVERA's test map, because NAVERA is developed there. There is **no satellite
> imagery of Oman** in the academy. All formulas work everywhere, so you will compute scales,
> zooms and tile numbers for Oman, and read real pictures only for Sousse.

## 1. Why a projection, and why Mercator?

A **map projection** is a function (φ, λ) → (x, y) from the curved Earth to a plane. No projection
keeps everything: a sphere cannot be flattened without stretching. You must choose what to keep:

- **conformal** projections keep **angles and shapes locally** (a small circle stays a circle);
- **equal-area** projections keep **areas**;
- none keeps all distances.

For image matching, shapes matter most: a roundabout in the photo must be round on the map, a
right-angled building corner must stay 90°, north must stay "up". So web maps chose a conformal
projection: **Mercator** (Gerardus Mercator, 1569).

### Deriving the Mercator formula

Take a small patch on a sphere of radius R at latitude φ: its north–south side is R·dφ and its
east–west side is R·cos φ·dλ (the parallel is a circle of radius R cos φ). Mercator decides that
meridians are vertical, equally spaced lines: **x = R·λ**. The east–west side on the map is then
R·dλ, so east–west is stretched by a factor **1/cos φ**.

To keep the shape, north–south must be stretched by the **same** factor:

```
dy = R·dφ / cos φ        →        y(φ) = R ∫₀^φ dθ / cos θ = R · ln tan(π/4 + φ/2)
```

![Mercator stretches north–south exactly as much as east–west](assets/mercator.svg)

The integral of sec θ has several equal forms, which you will meet in different code:

```
ln tan(π/4 + φ/2)  =  ln(tan φ + sec φ)  =  asinh(tan φ)
```

(NAVERA's `local_matcher.py` writes `math.log(math.tan(r) + 1.0 / math.cos(r))`.) The inverse is the
**Gudermannian function**:

```
φ = 2·atan(e^y) − π/2  =  atan(sinh y)            (y on the unit sphere, φ in radians)
```

The **scale factor** is k = 1/cos φ: at Salalah (17.0°) k = 1.046, at Muscat (23.6°) 1.091, at
Sousse (35.8°) 1.233, at 60° it is 2. Areas are scaled by k², which is why Greenland looks as big as
Africa on a web map although it is 14 times smaller. At the pole k is infinite: y → ∞.

**Web Mercator** cuts the map at the latitude where y = π (on the unit sphere), which makes the
world an exact square: φ_max = atan(sinh π) = **85.0511°**. Nothing north or south of that exists in
a web map.

> [!WARNING]
> **`ValueError: math domain error`** means you gave a function a value outside its domain — here
> `math.log()` of a number ≤ 0. Forget `math.radians()` and Salalah (17.0194) gives
> tan(π/4 + 8.51) = −0.13: `math.log` fails with this error. Muscat (23.5839) gives tan(…) = +0.011:
> no error at all, just y = −4.5 instead of 0.42 and a tile row outside the map. A crash
> is the lucky case. Always convert with `math.radians()` first.

### Web Mercator is not quite Mercator

Web Mercator (EPSG:3857) applies the **sphere** formula above, with R = a = 6 378 137 m, directly to
**WGS84 ellipsoidal** latitudes. The true Mercator of the ellipsoid (EPSG:3395) has an extra term:

```
y_3395 = a·[ln tan(π/4 + φ/2) − e·atanh(e·sin φ)]
```

At Muscat the two disagree by **a·e·atanh(e sin φ) ≈ 17.1 km** in y. Mixing tiles or coordinates from
the two systems is a classic bug (a whole city shifted north). Web Mercator is also not perfectly
conformal: at Muscat its north–south scale differs from its east–west scale by about 0.5 %
(N/M = 1.0057) — the same 0.5 % you met with the radii M and N in lesson 6. For matching photos,
this is negligible; for surveying, Web Mercator is the wrong tool.

## 2. The tile pyramid

After projection, the world (up to ±85.05°) is a square. Cut it:

- **zoom 0**: the whole world is one tile of 256 × 256 pixels;
- **zoom 1**: 2 × 2 tiles; **zoom z**: n = 2^z tiles in each direction, 4^z tiles in total.

![Zoom levels: each tile is cut into four at the next level](assets/zoom_pyramid.svg)

A tile's address is **z / x / y**: x counts columns from 0 at λ = −180° towards the **east**, y counts
rows from 0 at the **north** edge (85.05° N) towards the **south**. This is the **XYZ** or
"slippy map" convention. In fractional tile coordinates:

```
x = (λ + 180) / 360 · n                          (direct proportion: λ from −180..180 to 0..n)
y = (1 − ln tan(π/4 + φ/2) / π) / 2 · n          (φ in radians)
```

The **whole parts** are the tile; the **fractional parts** times 256 are the pixel inside it.
Multiplying by 256 directly gives **global pixel coordinates**: the pixel (0, 0) is the north-west
corner of the world, and at zoom 17 the world is 2^17 · 256 = 33 554 432 pixels wide.

**Worked example — the Sultan Qaboos Grand Mosque, Muscat (23.5839°, 58.3875°), zoom 17.**
n = 131 072. x = (58.3875 + 180)/360 · 131 072 = **86 794.24**. ln tan(π/4 + φ/2) = 0.423758, so
y = (1 − 0.423758/π)/2 · 131 072 = **56 696.09**. The mosque is in tile **17 / 86794 / 56696**, at pixel
(0.24 · 256, 0.09 · 256) ≈ (61, 23) inside it. Sanity check: Muscat is east of Greenwich (x > n/2 =
65 536) and north of the equator (y < n/2). ✔

**Inverse — tile to lat/lon.** For any (fractional) x, y:

```
λ = x / n · 360 − 180
φ = Gudermannian(π · (1 − 2y / n))
```

With whole x, y you get the tile's **north-west corner**; with x + 0.5, y + 0.5 its **centre**.
Python note: use `int(math.floor(x))` for the tile number. `int()` truncates towards zero, which is
the same for positive numbers but wrong for negative offsets (for example a pixel at −0.3 in a
mosaic is in the tile to the left, not in tile 0).

## 3. How big is a pixel?

The equator, 2πa = 40 075 016.7 m (`EQUATOR_M`), is cut into 2^z · 256 pixels. Away from the
equator, the map is stretched by 1/cos φ, so a pixel covers less ground:

```
meters per pixel = 2πa · cos φ / (256 · 2^z) = 156 543.03 · cos φ / 2^z
```

| Zoom | Salalah (17.0°) | Muscat (23.6°) | Khasab (26.2°) | Sousse (35.8°) |
|---|---|---|---|---|
| 13 | 18.27 m | 17.51 m | 17.15 m | 15.49 m |
| 15 | 4.568 m | 4.378 m | 4.287 m | 3.873 m |
| 17 | 1.142 m | 1.095 m | 1.072 m | 0.968 m |
| 19 | 0.286 m | 0.274 m | 0.268 m | 0.242 m |

So the "same" zoom-17 map is 18 % coarser in Salalah than in Sousse. A zoom-17 tile is 292 m wide in
Salalah, 280 m in Muscat and 248 m in Sousse. (Precisely, this formula is the east–west pixel size;
north–south, Web Mercator's pixel at Muscat is 0.5 % smaller, as explained above.)

**Choosing a zoom.** A downward camera at height H with horizontal field of view α and W pixels
across sees ground pixels of size GSD = 2H·tan(α/2)/W (the **ground sample distance**; lesson 8).
NAVERA scales the photo to the map's meters per pixel before matching. Shrinking a photo is safe;
enlarging it invents nothing but blur. So a simple rule is: take the **highest zoom whose pixel is
still at least the camera's GSD**:

```
z = floor( log2( 156 543.03 · cos φ / GSD ) )
```

For a camera with α = 84° and W = 1536 px at 300 m over Muscat, GSD = 0.352 m and z = 18. NAVERA's map
file carries its own table, `altitude_zoom_map`, which chooses a coarser zoom (17 at 300 m): coarser
tiles are faster to match and less sensitive to small changes on the ground. You will compare both
in the lab.

## 4. XYZ rows and TMS rows

The tile file format comes from an older standard, **TMS** (Tile Map Service), that numbers rows
from the **south**. Columns are identical; rows are flipped:

```
tms_row = (2^z − 1) − y
```

![XYZ rows count from the north, TMS rows from the south](assets/xyz_vs_tms.svg)

The Ribat of Sousse is in XYZ tile 17/69409/51547, stored as tile_row 131 071 − 51 547 = 79 524.
Forget the flip and you read the tile at the mirror latitude, about 35.8° **south** — in the ocean,
where NAVERA's file has nothing.

## 5. Inside an MBTiles file

**MBTiles** stores a whole tile pyramid in **one SQLite database file**. **SQLite** is a database
engine that keeps tables, indexes and everything else in a single ordinary file, organised in fixed
**pages** (4096 bytes here); Python reads it with the standard module `sqlite3`. NAVERA's map
contains two tables:

```sql
CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT)
CREATE TABLE tiles (zoom_level INTEGER NOT NULL, tile_column INTEGER NOT NULL,
                    tile_row INTEGER NOT NULL, tile_data BLOB NOT NULL,
                    PRIMARY KEY (zoom_level, tile_column, tile_row))
```

A **BLOB** is raw bytes — here the content of a JPEG file, which always starts with the bytes
`FF D8 FF`. The **primary key** creates an **index**: a B-tree sorted by (zoom, column, row). Finding
one tile among 1.15 million is a search in a tree of depth 3–4, i.e. a few page reads, not a scan
of the table. (NAVERA's file also has an extra index, `tile_index`, on the same three columns: it duplicates the
primary key's index and changes nothing for you — `explore_db.py` will list it.) SQLite tells you
which strategy it uses:

```sql
EXPLAIN QUERY PLAN SELECT tile_data FROM tiles WHERE zoom_level=17 AND tile_column=69409 AND tile_row=79524
-- SEARCH tiles USING INDEX sqlite_autoindex_tiles_1 (zoom_level=? AND tile_column=? AND tile_row=?)
```

**SQL in five words.** `SELECT` columns `FROM` a table `WHERE` a condition; `COUNT(*)` with
`GROUP BY zoom_level` counts rows per zoom; `length(tile_data)` is the size of a BLOB in bytes. In
Python, never paste numbers into the SQL text; write `?` **placeholders** and pass the values as a
tuple — `sqlite3` inserts them safely and the same query plan is reused.

**Read-only.** The map is shared by the whole class and by the product. Always open it with a URI:
`sqlite3.connect("file:/data/map.mbtiles?mode=ro", uri=True)`. `uri=True` tells Python to parse the
`?mode=ro` option instead of treating it as part of the file name; a read-only connection cannot
modify the file, even by mistake.

**Metadata is not a measurement.** NAVERA's map says, in its own metadata, `bounds 10.3,35.55,
10.9,36.1`, `minzoom 13`, `maxzoom 19`, `altitude_zoom_map {...}` and `estimated_size_mb 36467`.
The file on disk is **10 286 944 256 bytes = 10.29 GB** (2 511 461 pages × 4096 bytes). The
"estimated size" is a number written by the tool that created the file, and it is wrong by a factor
of 3.5. An engineer measures (`os.path.getsize`, `PRAGMA page_count`) and does not trust a label.

| Zoom | 13 | 14 | 15 | 16 | 17 | 18 | 19 |
|---|---|---|---|---|---|---|---|
| Tiles in NAVERA's map | 240 | 928 | 3 528 | 13 750 | 54 312 | 216 810 | 865 375 |

Each level has about 4 times more tiles than the previous one; zoom 19 alone holds 75 % of the tiles.

## 6. Mosaics and pixel ↔ lat/lon

One tile is small (280 m at zoom 17 in Muscat), and the drone may be near its edge. NAVERA always
works on a **mosaic**: the (2r + 1)² tiles around the position, glued into one picture. If the
mosaic's top-left tile is (x0, y0), a point and a pixel are related by:

```
px = (x_frac − x0) · 256          py = (y_frac − y0) · 256
lat, lon = tile_to_latlon(x0 + px/256, y0 + py/256, z)
```

![Pixels of a mosaic, and the corner bug](assets/mosaic_pixels.svg)

These two lines are what turns "the photo centre matched pixel (412.6, 377.1) of the mosaic" into
a latitude and a longitude — the output of day vision.

### A real bug: corner or centre?

The day-vision dataset of NAVERA stores, for each zoom-17 tile, the latitude and longitude of its
**north-west corner** (the value `tile_to_latlon(x, y)` returns). For a while, when a camera photo
matched a tile, NAVERA published that corner as the drone's position. But the photo matched the
**whole** tile, so the right answer is its **centre**. Every fix was off by half the tile diagonal,
towards the north-west: **175 m** at zoom 17 in Sousse. In Muscat, where zoom-17 tiles are larger,
the same bug would cost 198 m. The fix adds 0.5 to x and y; a unit test keeps it fixed.

## 🐦 How birds do it

Homing pigeons released far from their loft first rely on compass mechanisms (the sun, the Earth's
magnetic field). Close to home, they also use what they see. In the early 2000s, Tim Guilford, Dora
Biro and colleagues at Oxford fitted small GPS loggers to homing pigeons and released them many
times from the same sites. Each bird gradually developed its **own route**, then repeated it very
precisely, flight after flight. Many of these routes followed linear features visible from the air —
roads, railways, rivers, hedgerows. In 2004 another team (Hans-Peter Lipp and colleagues, Zurich)
reported pigeons that followed motorways and even changed direction at motorway junctions.

In tile language: a bird at high altitude sees only large structures, a coastline or a mountain
ridge — a **low zoom**. Lower down it resolves single roads and buildings — a **high zoom**. And it does
not carry "the world" in memory, only the area it has flown over, in most detail near home — exactly
how NAVERA prepares a mission: only the tiles along the route, at the zoom levels it needs. Navi, our
swallow, uses the same pyramid when she returns to the same nest: first the coast, then the town,
then the roof.

## In NAVERA

**Reading tiles — `simulation_web/simulation_web/web_common.py`**
([open it](file:navera/simulation_web/simulation_web/web_common.py)), class `MBTilesReader`, used by the
operator view and by the simulator's camera:

```python
def get(self, z: int, x: int, y: int) -> Optional[bytes]:
    """Tile bytes for XYZ coordinates (already bounds-checked), or None."""
    ...
            if self._conn is None:
                uri = "file:" + quote(self.path) + "?mode=ro"
                self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            row = self._conn.execute(
                "SELECT tile_data FROM tiles "
                "WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                (z, x, (2 ** z - 1) - y),
            ).fetchone()
    ...
    return bytes(row[0]) if row else None
```

Read-only URI, placeholders, the TMS flip and `None` for a missing tile. (`quote()` escapes special
characters in the path; the real method also holds a lock, because several web requests may read at
the same time.)

**Tile geometry — `day_pkg/day_pkg/local_matcher.py`**
([open it](file:navera/day_pkg/day_pkg/local_matcher.py)):

```python
EQUATOR_M = 40075016.7

def tile_xy(lat, lon, z):
    """Fractional XYZ tile coordinates of (lat, lon) at zoom z."""
    n = 2 ** z
    r = math.radians(lat)
    return (lon + 180.0) / 360.0 * n, (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n

def tile_px_to_latlon(px, py, z):
    """(lat, lon) of a global tile-pixel position (256 px per tile) at zoom z."""
    n = 2 ** z
    x, y = px / 256.0, py / 256.0
    return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n)))), x / n * 360.0 - 180.0

def map_m_per_px(lat, z):
    return EQUATOR_M * math.cos(math.radians(lat)) / 2 ** z / 256.0
```

`tile_px_to_latlon` is your `pixel_to_latlon` with x0 = y0 = 0 (global pixels).

**The corner bug and its test — `day_pkg/day_pkg/nodes/day_localizer.py`, `tile_center_latlon()`**:

```python
    The dataset CSV stores each tile's NORTH-WEST CORNER (the value
    tile_to_latlon(x, y) returns), not its centre: publishing that as the
    position biases every fix by half a tile (~175 m at z17, to the NW).
    ...
    lon = (x + 0.5) / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5) / n))))
```

`day_pkg/test/test_tile_geometry.py` checks that the NW corner of tile 17/69388/51536 is
(35.8534396195918, 10.579833984375) and that the centre is 175 ± 1 m away — your functions must
reproduce these numbers. **`day_pkg/day_pkg/prepare_area.py`** (`tile_nw()`, `tile_center()`)
extracts the zoom-17 tiles along a planned route, so the drone carries only what it needs.

## Glossary

| Term | Meaning |
|---|---|
| **map projection** | a function (φ, λ) → (x, y) from the Earth to a plane |
| **conformal** | keeps angles and local shapes (Mercator is conformal on the sphere) |
| **scale factor k** | map length / ground length; Mercator: k = 1/cos φ |
| **Web Mercator (EPSG:3857)** | spherical Mercator applied to WGS84 latitudes, cut at ±85.0511° |
| **ordinate** | the y coordinate of a point (here, y on the map); x is the abscissa |
| **Gudermannian** | φ = atan(sinh y), the inverse of the Mercator ordinate |
| **tile pyramid** | the world cut into 4^z tiles of 256 × 256 px at each zoom z |
| **XYZ / TMS** | tile numbering with rows from the north / from the south; row = 2^z − 1 − y |
| **global pixel** | tile coordinate × 256; (0, 0) is the world's NW corner |
| **ground sample distance (GSD)** | ground size of one camera pixel |
| **MBTiles** | a tile pyramid stored in one SQLite file (tables metadata and tiles) |
| **SQLite, page** | a database engine in one file; the file is made of fixed-size pages |
| **index, B-tree** | sorted search structure that finds one row in a few reads |
| **BLOB** | a column holding raw bytes (here, a JPEG file) |
| **placeholder `?`** | a slot in an SQL query, filled safely by sqlite3 with a value |
| **URI, mode=ro** | `file:...?mode=ro` opens the database read-only |

## Check what you learned

<details><summary>1. Derive the scale factor of Mercator and say why it must be the same north–south and east–west.</summary>
x = Rλ makes the east–west map length R·dλ for a ground length R cos φ dλ: scale 1/cos φ. A conformal
map must scale all directions equally at a point, so dy = R dφ / cos φ, which integrates to
R ln tan(π/4 + φ/2).
</details>

<details><summary>2. At zoom 17, how wide is a tile in Salalah and in Sousse, and why is Salalah's larger?</summary>
256 × 156 543.03 · cos φ / 2^17: 292 m in Salalah, 248 m in Sousse. Closer to the equator, cos φ is
larger, the Mercator stretch smaller, so one pixel covers more ground.
</details>

<details><summary>3. The tile 17/86794/56696 contains the Grand Mosque. Which tile_row do you query in the MBTiles file?</summary>
131 071 − 56 696 = 74 375 (TMS rows count from the south).
</details>

<details><summary>4. Your code computes math.log(math.tan(math.pi / 4 + 17.0194 / 2)) and crashes with "math domain error". Why?</summary>
17.0194 is in degrees but used as radians: tan(π/4 + 8.51 rad) = −0.13 is negative, and the log of a
negative number is undefined. Use math.radians(17.0194). (With Muscat's 23.5839 the same mistake does
not crash — it silently gives a wrong tile.)
</details>

<details><summary>5. The metadata says 36467 MB, the file system says 10.29 GB. Which do you report, and how do you check it?</summary>
The measurement: os.path.getsize (or PRAGMA page_count × page_size). Metadata is free text written by
a tool and can be wrong.
</details>

<details><summary>6. Why does the corner bug cost more meters in Muscat than in Sousse, at the same zoom?</summary>
The error is half the tile diagonal. Tiles cover more ground at lower latitude (cos φ larger): 280 m
in Muscat against 248 m in Sousse, so 198 m against 175 m.
</details>

Now open the **🛠️ Lab** tab.
