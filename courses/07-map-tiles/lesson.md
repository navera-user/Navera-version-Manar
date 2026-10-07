# How the world is cut into map tiles

NAVERA flies with a satellite map of the whole Sousse region on board: from Hergla to Monastir,
from the sea to the olive groves inland. On the box it is one file of **10 GB** — more than a million
small pictures. When the camera takes a photo, NAVERA must compare it with the right piece of map,
**now**, many times per minute. It cannot load 10 GB each time; it cannot even search through a
million pictures one by one.

The trick is old and simple: cut the world into a **grid of squares** with a clear numbering rule, so
that from a latitude and a longitude you can **compute** the number of the square you need, and read
only that one. Every web map (the one in your phone too) works like that. In this lesson you learn the
rule and you read NAVERA's map yourself.

## Step 1 — flatten the Earth: Web Mercator

A map is flat, the Earth is round. You cannot flatten an orange peel without stretching or tearing
it, so every flat map stretches something. Web maps all use the same stretching, called
**Web Mercator**:

- the meridians become **vertical straight lines**, evenly spaced: longitude becomes the **x** axis;
- the parallels become **horizontal straight lines**, but they are pulled further and further apart
  as you go towards the poles: latitude becomes the **y** axis, stretched.

The stretch is chosen so that **shapes stay right** locally: a round roundabout stays round, a square
building stays square, north stays up. That is exactly what we want to compare a photo with a map.
The price: **sizes** are wrong far from the equator (on a world map Greenland looks as big as Africa;
it is 14 times smaller), and the poles cannot be drawn at all — the map stops at 85.05° north and south.

> [!NOTE]
> The stretch at a latitude is 1 / cos(latitude) — the same cosine as in lesson 6! At Sousse
> (35.8°) things on the map look 1.23 times bigger than at the equator. We will need this in a moment.

## Step 2 — cut the square into tiles: zoom levels

After flattening, the whole world is a **square**. Now:

- at **zoom 0**, the whole world is **one tile**, a picture of 256 × 256 pixels;
- at **zoom 1**, the square is cut into 2 × 2 = 4 tiles, each again 256 × 256 pixels (so twice more detail);
- at **zoom 2**, 4 × 4 = 16 tiles;
- at **zoom z**, 2^z × 2^z tiles.

![Zoom levels: each tile is cut into four at the next level](assets/zoom_pyramid.svg)

Each tile has an address of three numbers, written **z / x / y**:

- **z**: the zoom level;
- **x**: the column, from 0 at longitude −180° (the far west), growing to the **east**;
- **y**: the row, from 0 at the **top** (the far north), growing to the **south**.

This numbering is called **XYZ** (or "slippy map" tiles). NAVERA's map holds zoom 13 to zoom 19:

| Zoom | Tiles across the world | 1 pixel at the equator | 1 pixel at Sousse | 1 tile at Sousse |
|---|---|---|---|---|
| 13 | 8 192 | 19.1 m | 15.5 m | 3.97 km |
| 15 | 32 768 | 4.78 m | 3.87 m | 992 m |
| 17 | 131 072 | 1.19 m | 0.97 m | 248 m |
| 18 | 262 144 | 0.60 m | 0.48 m | 124 m |
| 19 | 524 288 | 0.30 m | 0.24 m | 62 m |

Each zoom level has **4 times** more tiles than the previous one, and each pixel is **half** the size.
That is why zoom 19 alone has 865 375 tiles in NAVERA's file, while zoom 13 has only 240.

## Step 3 — from latitude/longitude to a tile number

Let **n = 2^z** be the number of tiles across.

**x** is easy, because longitudes are evenly spaced. Longitude goes from −180 to +180 (a range of 360);
shift it to 0…360 and take the fraction:

```
x = (lon + 180) / 360 × n
```

**y** follows the Mercator stretch. You don't need to understand where it comes from; just copy it
carefully (it uses the latitude in **radians**, `ln` is `math.log`):

```
y = (1 − ln(tan(lat) + 1 / cos(lat)) / π) / 2 × n
```

For the Ribat of Sousse (35.8277, 10.6388) at zoom 17 this gives **x = 69409.47, y = 51547.56**.

- The **whole parts** (69409, 51547) are the tile: the Ribat is in tile **17 / 69409 / 51547**.
- The **fractions** (0.47, 0.56) say where it is *inside* the tile: 0.47 × 256 = pixel 120 from the
  left, 0.56 × 256 = pixel 143 from the top.

Check in your head: Sousse is a bit east of the middle of the world (x slightly above n / 2 = 65 536)
and north of the equator (y below n / 2). ✔

## Step 4 — and back: from a tile to latitude/longitude

The opposite formulas give the **north-west corner** (top-left) of tile x, y:

```
lon = x / n × 360 − 180
lat = atan(sinh(π × (1 − 2 × y / n)))      (in radians → convert to degrees)
```

`sinh` and `atan` are two more calculator buttons (`math.sinh`, `math.atan`); together they undo the
`ln(tan + 1/cos)` of step 3. To get the **centre** of a tile, use x + 0.5 and y + 0.5.

> [!WARNING]
> **Corner or centre?** This tiny detail caused a real bug in NAVERA. The day-vision dataset stores,
> for every tile, the latitude/longitude of its **north-west corner**. For a while, when the camera
> matched a tile, NAVERA published that corner as the drone's position — but the photo's centre is the
> tile's **centre**. Every position was wrong by half a tile: about **175 m** towards the north-west at
> zoom 17. The fix and a test that keeps it fixed are in the code (see "In NAVERA" below).

## Step 5 — how big is a pixel?

The equator is 40 075 017 m long. At zoom z it is cut into n tiles of 256 pixels, so on the equator
one pixel covers 40 075 017 / n / 256 meters. Away from the equator the map is stretched by
1 / cos(latitude), so a pixel covers **less** ground:

```
meters per pixel = 40 075 017 × cos(lat) / 2^z / 256
```

At Sousse, zoom 17: 40 075 017 × 0.811 / 131 072 / 256 ≈ **0.968 m**. A car (4 m) is 4 pixels long.

This number is essential for vision navigation: to compare a camera photo with the map, NAVERA must
first make both pictures have the **same meters per pixel** (lesson 8). It is also why the map file
recommends a zoom for each flying height (`altitude_zoom_map` in its metadata): the higher the drone,
the more ground each camera pixel covers, and the lower the zoom that matches it.

## Step 6 — the MBTiles file

How do you store a million tiles? Not as a million files (slow to copy, hard to manage), but in **one
file**: an **MBTiles** file. Inside, it is an **SQLite database**.

A **database** is a program that stores tables — think of the CSV files of lesson 4, but with millions of
rows and an index to find one row instantly. **SQLite** keeps a whole database in one ordinary file;
Python can read it with the built-in module `sqlite3`. An MBTiles file has two tables:

**`metadata`** — two columns, `name` and `value`: what the map is.

| name | value (NAVERA's map) |
|---|---|
| name | Sousse Governorate Satellite |
| format | jpg |
| bounds | 10.3,35.55,10.9,36.1 (west, south, east, north) |
| minzoom / maxzoom | 13 / 19 |
| altitude_zoom_map | which zoom to use at which flying height |

**`tiles`** — one row per tile:

| zoom_level | tile_column | tile_row | tile_data |
|---|---|---|---|
| 17 | 69409 | 79524 | (27 295 bytes of JPEG picture) |

To ask a database for something you use **SQL**, a little language made of English-like sentences:

```sql
SELECT tile_data FROM tiles WHERE zoom_level = 17 AND tile_column = 69409 AND tile_row = 79524
```

"Give me the column `tile_data` from the table `tiles`, for the row where zoom is 17, and column is…".

### The upside-down rows (TMS)

Look again at the table above: the Ribat's tile is y = **51547**, but its `tile_row` is **79524**. The
MBTiles format comes from an older standard called **TMS**, which counts rows **from the south**
(from the bottom), while XYZ counts from the north (the top). Columns are the same. To convert:

```
tile_row = (2^z − 1) − y
```

At zoom 17: 131 071 − 51 547 = 79 524. ✔

![XYZ rows count from the north, TMS rows from the south](assets/xyz_vs_tms.svg)

Forget the flip and you read the tile at the mirror latitude, about 35.8° **south** — in the middle of
the ocean, where NAVERA's file has nothing.

> [!WARNING]
> NAVERA's map is shared by the whole class and by the product itself. Always open it **read-only**:
> `sqlite3.connect("file:/data/map.mbtiles?mode=ro", uri=True)`. The `file:…?mode=ro` form is called a
> **URI**; `uri=True` tells Python to read the `mode=ro` part ("read only") instead of treating it as a
> file name. A read-only connection cannot change or damage the file, even by mistake.

The `tile_data` is the picture itself, as **bytes** (the content of a `.jpg` file). Every JPEG starts
with the bytes `FF D8 FF` — a handy way to check you got a picture and not garbage. OpenCV can
**decode** those bytes into pixels (lesson 8 is about pixels).

## 🐦 How birds do it

A homing pigeon released far from home flies back to its loft. Far away, it relies mostly on its
compasses (the sun, the magnetic field). Close to home, it uses something else: **what it sees**.

In the early 2000s, scientists at Oxford (Tim Guilford, Dora Biro and their colleagues) fixed tiny GPS
loggers on homing pigeons and released them again and again from the same places. Each pigeon
slowly developed its **own favourite route** home and then followed it flight after flight, very
precisely. Many of those routes ran along roads, railways, rivers and field edges — lines that are
easy to see from above. Some even seemed to follow a main road and change direction at its
junctions, like a driver who knows the way.

Think of it in tiles. From high up, a bird sees only big shapes — a coast, a river, a mountain range:
that is a **low zoom level**. Lower down, it sees single roads, roofs and trees: a **high zoom level**.
And a pigeon does not "carry" the whole world in its head — only the area it has flown over, and the
area around home best of all.

Navi does the same when she comes back from Africa: first the shape of the Tunisian coast, then the
town, then the farm, then the barn door.

NAVERA's map file works the same way: only the region of the mission, cut into tiles, at the zoom
levels it needs — and the right tile picked in an instant from a latitude and a longitude.

## In NAVERA

**Reading tiles — `simulation_web/simulation_web/web_common.py`**
([open it](file:navera/simulation_web/simulation_web/web_common.py)). The operator view and the
simulator's camera read the map with `MBTilesReader`:

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

Read-only URI, the SQL sentence, the TMS flip `(2 ** z - 1) - y`, and `None` when the tile is missing:
everything you will write in the lab. (`quote()` protects file names with spaces; the `?` in the SQL
are placeholders that `sqlite3` fills safely with the values of the tuple.) It also keeps the
connection open between calls and uses a lock, because several web requests can arrive at once.

**Tile geometry — `day_pkg/day_pkg/local_matcher.py`**
([open it](file:navera/day_pkg/day_pkg/local_matcher.py)). Day vision needs the same three formulas:

```python
EQUATOR_M = 40075016.7

def tile_xy(lat, lon, z):
    """Fractional XYZ tile coordinates of (lat, lon) at zoom z."""
    n = 2 ** z
    r = math.radians(lat)
    return (lon + 180.0) / 360.0 * n, (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n

def map_m_per_px(lat, z):
    return EQUATOR_M * math.cos(math.radians(lat)) / 2 ** z / 256.0
```

**The corner bug and its test — `day_pkg/day_pkg/nodes/day_localizer.py` and
`day_pkg/test/test_tile_geometry.py`.** The function `tile_center_latlon()` turns a tile name such as
`tile_17_69388_51536.jpg` into the tile's **centre**, with `x + 0.5` and `y + 0.5`. Its docstring tells
the story: *"publishing that [corner] as the position biases every fix by half a tile (~175 m at z17,
to the NW)"*. The test checks the north-west corner of that tile is (35.8534396195918, 10.579833984375)
— your lab's `tile_to_latlon()` must give exactly the same numbers.

**Preparing a mission area — `day_pkg/day_pkg/prepare_area.py`** extracts from the MBTiles map the
zoom-17 tiles along a planned route (`tile_nw()`, `tile_center()`), so the drone carries only the
tiles it may need.

## New words

| Word | Meaning |
|---|---|
| **Web Mercator** | the way web maps flatten the Earth: north up, shapes kept, sizes stretched towards the poles |
| **tile** | one 256 × 256 pixel square picture of the map |
| **zoom level (z)** | how many times the world square was cut in 4: 2^z × 2^z tiles |
| **XYZ (slippy map)** | numbering of tiles: x to the east, y to the **south**, from the top-left |
| **TMS** | older numbering where rows count from the **south**: row = 2^z − 1 − y |
| **meters per pixel** | the ground size of one pixel (also called ground resolution) |
| **MBTiles** | a single file holding all the tiles of a map, in an SQLite database |
| **SQLite / database** | a program (and file) that stores tables and finds rows fast |
| **SQL** | the language to ask a database: `SELECT … FROM … WHERE …` |
| **URI, mode=ro** | a way to open a file with options; `mode=ro` = read only |
| **JPEG** | a compressed picture format; its bytes start with FF D8 FF |

## Check what you learned

<details><summary>1. At zoom 18, how many tiles are there across the world, and how many in total?</summary>
2^18 = 262 144 across, and 262 144 × 262 144 ≈ 68.7 billion in total. That is why a map only stores the
tiles of its region.
</details>

<details><summary>2. You go from zoom 17 to zoom 18. What happens to the meters per pixel?</summary>
It is divided by 2: each tile is cut into 4 (2 × 2), each new tile still has 256 × 256 pixels.
At Sousse: 0.968 m → 0.484 m.
</details>

<details><summary>3. Tile 17/69409/51547 — is tile 17/69410/51547 east or west of it? And 17/69409/51548?</summary>
69410 is one column further east. 51548 is one row further <b>south</b> (XYZ rows grow to the south).
</details>

<details><summary>4. Why does the MBTiles query use tile_row = 2^z − 1 − y?</summary>
MBTiles follows the TMS convention, where rows are counted from the south, while XYZ (used by NAVERA
and web maps) counts from the north. The formula flips the row number.
</details>

<details><summary>5. Day vision matched a photo to a tile and published the tile's north-west corner. What is wrong?</summary>
The photo's centre is at the tile's centre, half a tile south-east of the corner: about 175 m of error at
zoom 17. Use x + 0.5, y + 0.5.
</details>

Now open the **🛠️ Lab** tab.
