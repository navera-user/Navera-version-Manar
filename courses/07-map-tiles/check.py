import hashlib
import os
import re

from academy_check import Checker, load_student, need, sh

c = Checker()

SMALL = "/data/academy/07-map-tiles/sousse_small.mbtiles"   # a few tiles of the real map
SOUSSE = (35.8277, 10.6388)
MONASTIR = (35.7795, 10.8320)


def lab():
    return load_student("tiles_lab.py")


def pair(v, what):
    c.ok(v is not None, f"{what} returned None — the TODO is not done yet")
    c.ok(isinstance(v, (tuple, list)) and len(v) == 2, f"{what} should return two numbers; got {v!r}")
    return v[0], v[1]


@c.test("tile_xy() gives the fractional tile position of the Ribat of Sousse at zoom 17",
        hint="x = (lon + 180) / 360 × 2**z. For y, copy the Mercator formula of the course carefully "
             "(math.log, math.tan and math.cos of the latitude in RADIANS).")
def _():
    (tile_xy,) = need(lab(), "tile_xy")
    x, y = pair(tile_xy(*SOUSSE, 17), "tile_xy()")
    c.near(x, 69409.46887, tol=1e-4, what="x")
    c.near(y, 51547.56050, tol=1e-4, what="y")


@c.test("tile_xy(): at zoom 1 the point (0°, 0°) is the corner shared by the 4 tiles",
        hint="At zoom z there are n = 2**z tiles across. Latitude 0 and longitude 0 are in the middle: n / 2.")
def _():
    (tile_xy,) = need(lab(), "tile_xy")
    x, y = pair(tile_xy(0.0, 0.0, 1), "tile_xy()")
    c.near(x, 1.0, tol=1e-9, what="x")
    c.near(y, 1.0, tol=1e-9, what="y")
    x, y = pair(tile_xy(0.0, -180.0, 3), "tile_xy()")
    c.near(x, 0.0, tol=1e-9, what="x at longitude -180")


@c.test("latlon_to_tile() gives whole tile numbers (Sousse at zoom 13, 17, 19; Monastir at 17)",
        hint="Call tile_xy() and keep the whole part of each number: int(math.floor(x)). Return a pair of ints.")
def _():
    (f,) = need(lab(), "latlon_to_tile")
    for (lat, lon), z, want in [(SOUSSE, 13, (4338, 3221)), (SOUSSE, 17, (69409, 51547)),
                                (SOUSSE, 19, (277637, 206190)), (MONASTIR, 17, (69479, 51569))]:
        got = pair(f(lat, lon, z), "latlon_to_tile()")
        c.ok(all(isinstance(v, int) for v in got), f"tile numbers must be int, got {got!r}")
        c.eq(tuple(got), want, what=f"latlon_to_tile({lat}, {lon}, {z})")


@c.test("tile_to_latlon() gives the north-west corner of tile 17/69388/51536 (the value NAVERA's test uses)",
        hint="lon = x / n × 360 − 180 ; lat = degrees(atan(sinh(π × (1 − 2 × y / n)))) with n = 2**z.")
def _():
    (f,) = need(lab(), "tile_to_latlon")
    lat, lon = pair(f(69388, 51536, 17), "tile_to_latlon()")
    c.near(lat, 35.8534396195918, tol=1e-9, what="latitude")
    c.near(lon, 10.579833984375, tol=1e-9, what="longitude")


@c.test("a point is inside its tile: south-east of the tile's NW corner, north-west of the next one",
        hint="tile_to_latlon(x, y) is the top-left corner; tile_to_latlon(x + 1, y + 1) is the bottom-right one.")
def _():
    to_tile, to_ll = need(lab(), "latlon_to_tile", "tile_to_latlon")
    for (lat, lon) in (SOUSSE, MONASTIR, (35.70123, 10.45678)):
        for z in (13, 16, 19):
            x, y = pair(to_tile(lat, lon, z), "latlon_to_tile()")
            n_lat, w_lon = pair(to_ll(x, y, z), "tile_to_latlon()")
            s_lat, e_lon = pair(to_ll(x + 1, y + 1, z), "tile_to_latlon()")
            c.ok(s_lat <= lat <= n_lat and w_lon <= lon <= e_lon,
                 f"({lat}, {lon}) is not inside its own tile at zoom {z}")


@c.test("meters_per_pixel(): 156 543 m at zoom 0 on the equator, ≈ 0.968 m at Sousse zoom 17",
        hint="EQUATOR_M / 2**z / 256 is the size on the equator; multiply by cos(latitude in radians).")
def _():
    (f,) = need(lab(), "meters_per_pixel")
    v = f(0.0, 0)
    c.ok(v is not None, "meters_per_pixel() returned None — the TODO is not done yet")
    c.near(v, 156543.034, tol=0.01, what="meters_per_pixel(0, 0)")
    c.near(f(SOUSSE[0], 17), 0.968339, tol=1e-5, what="meters_per_pixel(Sousse, 17)")
    c.near(f(SOUSSE[0], 18), f(SOUSSE[0], 17) / 2, tol=1e-9, what="zoom 18 (it should be half of zoom 17)")


@c.test("read_tile() returns the right JPEG for tile 17/69409/51547 (the Ribat of Sousse)",
        hint="The file stores tile_row = 2**z − 1 − y (TMS). SELECT tile_data FROM tiles WHERE zoom_level=? "
             "AND tile_column=? AND tile_row=?, and return bytes(row[0]).")
def _():
    (f,) = need(lab(), "read_tile")
    data = f(SMALL, 17, 69409, 51547)
    c.ok(data is not None, "read_tile() returned None for a tile that is in the file "
                           "(TODO not done, or the row is not flipped)")
    c.ok(isinstance(data, (bytes, bytearray, memoryview)), f"read_tile() should return bytes, got {type(data).__name__}")
    data = bytes(data)
    c.ok(data[:3] == b"\xff\xd8\xff", "these bytes are not a JPEG picture")
    c.eq(hashlib.md5(data).hexdigest(), "270e09c03dd62649227d2c37500973c4", what="the tile's fingerprint (md5)")


@c.test("read_tile() works at other zooms (19 and 13) too",
        hint="2**z − 1 − y depends on the zoom: use the z you received, not a fixed 17.")
def _():
    (f,) = need(lab(), "read_tile")
    for (z, x, y), md5 in [((19, 277637, 206190), "bd51161cc482d75e13e9cca612336df0"),
                           ((13, 4338, 3221), "a1b0ebd6d727e5becea3ed768b4bebc1")]:
        data = f(SMALL, z, x, y)
        c.ok(data is not None, f"read_tile() returned None for tile {z}/{x}/{y}")
        c.eq(hashlib.md5(bytes(data)).hexdigest(), md5, what=f"fingerprint of tile {z}/{x}/{y}")


@c.test("read_tile() returns None for a tile that is not in the file, and opens it read-only",
        hint="fetchone() gives None when no row matches. Open with sqlite3.connect('file:' + path + '?mode=ro', uri=True).")
def _():
    (f,) = need(lab(), "read_tile")
    c.ok(f(SMALL, 17, 1, 1) is None, "read_tile() should return None when the tile does not exist")
    src = open("tiles_lab.py").read()
    c.ok(re.search(r"mode\s*=\s*ro", src) is not None,
         "I can't find mode=ro in tiles_lab.py: the shared map must be opened read-only")


@c.test("pixel_in_mosaic() puts the Ribat of Sousse at pixel ≈ (376.0, 399.5) of its zoom-17 mosaic",
        hint="(fractional x − (x − 1)) × 256, and the same for y — use tile_xy() and latlon_to_tile().")
def _():
    (f,) = need(lab(), "pixel_in_mosaic")
    px, py = pair(f(*SOUSSE, 17), "pixel_in_mosaic()")
    c.near(px, 376.031, tol=0.05, what="px")
    c.near(py, 399.487, tol=0.05, what="py")
    px, py = pair(f(*MONASTIR, 17), "pixel_in_mosaic()")
    c.near(px, 463.576, tol=0.05, what="px for Monastir marina")
    c.near(py, 306.841, tol=0.05, what="py for Monastir marina")


@c.test("mosaic.py builds a 768 × 768 mosaic.png",
        hint="Run the command of step 7 in the terminal and read the error, if any.")
def _():
    if os.path.exists("mosaic.png"):
        os.rename("mosaic.png", "mosaic_yours.png")
    try:
        code, out = sh(f"python3 mosaic.py 35.7795 10.8320 17 --map {SMALL}", timeout=60)
        c.ok(code == 0, "mosaic.py stopped with an error:\n" + out[-600:])
        import cv2
        img = cv2.imread("mosaic.png")
        c.ok(img is not None, "mosaic.png is missing or is not a picture")
        c.eq(img.shape, (768, 768, 3), what="the size of mosaic.png")
        c.ok(float(img[300:400, 300:400].std()) > 10, "the middle of the mosaic is empty: no tile was read")
    finally:
        if os.path.exists("mosaic_yours.png"):
            os.replace("mosaic_yours.png", "mosaic.png")


QUIZ = {"Q1": (17, "Run `python3 explore_db.py` and read the line altitude_zoom_map."),
        "Q2": (54312, "Run `python3 explore_db.py` and look at the count of tiles per zoom level."),
        "Q3": (79524, "tile_row = 2**17 − 1 − 51547. Compute it in Python.")}

for q, (good, hint) in QUIZ.items():
    @c.test(f"quiz {q}", hint=hint)
    def _(q=q, good=good):
        (v,) = need(load_student("answers.py"), q)
        try:
            v = int(float(v))
        except (TypeError, ValueError):
            c.ok(False, f"{q} should be a number, got {v!r}")
        c.ok(v != 0, f"{q} has no answer yet")
        c.ok(v == good, f"{q} = {v} is not the right answer")

c.run()
