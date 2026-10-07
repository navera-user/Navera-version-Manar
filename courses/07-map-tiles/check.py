import hashlib
import json
import math
import os
import re

from academy_check import Checker, load_student, need, sh

c = Checker()

SMALL = "/data/academy/07-map-tiles/sousse_small.mbtiles"   # 88 tiles copied from the real map
SOUSSE = (35.8277, 10.6388)        # Ribat of Sousse
MONASTIR = (35.7795, 10.8320)      # Monastir marina
SINGAPORE = (1.2834, 103.8607)     # Marina Bay Sands
REYKJAVIK = (64.1417, -21.9266)    # Hallgrimskirkja


def lab():
    return load_student("tiles_lab.py")


def pair(v, what):
    c.ok(v is not None, f"{what} returned None — the TODO is not done yet")
    c.ok(isinstance(v, (tuple, list)) and len(v) == 2, f"{what} should return two numbers; got {v!r}")
    return v[0], v[1]


def num(v, what):
    c.ok(v is not None, f"{what} returned None — the TODO is not done yet")
    return v


@c.test("mercator_y(): 0 at the equator, 0.670562 at Sousse, π at 85.0511°, odd in latitude",
        hint="ln(tan(π/4 + φ/2)) with φ in RADIANS: math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)). "
             "'math domain error' means tan(...) was ≤ 0: usually degrees used as radians.")
def _():
    (f,) = need(lab(), "mercator_y")
    c.near(num(f(0.0), "mercator_y()"), 0.0, tol=1e-12, what="mercator_y(0)")
    c.near(f(SOUSSE[0]), 0.67056242035, tol=1e-9, what="mercator_y(35.8277)")
    c.near(f(85.0511287798), math.pi, tol=1e-8, what="mercator_y(85.0511287798)")
    c.near(f(-51.5007), -f(51.5007), tol=1e-12, what="mercator_y(-51.5007) (it should be -mercator_y(51.5007))")


@c.test("inverse_mercator_y() undoes mercator_y() (to 10⁻¹⁰ degree) and returns degrees",
        hint="φ = 2·atan(exp(y)) − π/2 (or atan(sinh(y))), then math.degrees().")
def _():
    f, g = need(lab(), "mercator_y", "inverse_mercator_y")
    c.near(num(g(math.pi), "inverse_mercator_y()"), 85.0511287798, tol=1e-8, what="inverse_mercator_y(π)")
    for lat in (-60.0, -33.9249, 0.0, 1.2834, 35.8277, 64.1417, 80.0):
        c.near(g(f(lat)), lat, tol=1e-10, what=f"inverse_mercator_y(mercator_y({lat}))")


@c.test("tile_xy(): the Ribat of Sousse at zoom 17, the point (0°, 0°) at zoom 1, longitude −180°",
        hint="n = 2**z; x = (lon + 180) / 360 · n (a direct proportion); y = (1 − mercator_y(lat) / π) / 2 · n.")
def _():
    (f,) = need(lab(), "tile_xy")
    x, y = pair(f(*SOUSSE, 17), "tile_xy()")
    c.near(x, 69409.46887, tol=1e-4, what="x of the Ribat at zoom 17")
    c.near(y, 51547.56050, tol=1e-4, what="y of the Ribat at zoom 17 (y grows to the SOUTH)")
    x, y = pair(f(0.0, 0.0, 1), "tile_xy()")
    c.near(x, 1.0, tol=1e-9, what="x of (0°, 0°) at zoom 1")
    c.near(y, 1.0, tol=1e-9, what="y of (0°, 0°) at zoom 1")
    c.near(pair(f(0.0, -180.0, 3), "tile_xy()")[0], 0.0, tol=1e-9, what="x at longitude -180")


@c.test("latlon_to_tile(): whole tile numbers for Sousse (z13, 17, 19), Monastir, Singapore and Cape Town",
        hint="int(math.floor(x)) and int(math.floor(y)) of tile_xy(). Return a pair of int.")
def _():
    (f,) = need(lab(), "latlon_to_tile")
    for (lat, lon), z, want in [(SOUSSE, 13, (4338, 3221)), (SOUSSE, 17, (69409, 51547)),
                                (SOUSSE, 19, (277637, 206190)), (MONASTIR, 17, (69479, 51569)),
                                (SINGAPORE, 17, (103350, 65068)), (REYKJAVIK, 17, (57552, 34838)), ((-33.9, 18.4), 15, (18058, 19667))]:
        got = pair(f(lat, lon, z), "latlon_to_tile()")
        c.ok(all(isinstance(v, int) for v in got), f"tile numbers must be int, got {got!r}")
        c.eq(tuple(got), want, what=f"latlon_to_tile({lat}, {lon}, {z})")


@c.test("tile_to_latlon(): NW corner of 17/69388/51536 = NAVERA's test value; x+0.5, y+0.5 is the centre",
        hint="lon = x / n · 360 − 180; lat = inverse_mercator_y(π · (1 − 2·y / n)). It must accept "
             "fractional x, y too (no int() inside).")
def _():
    f, to_tile = need(lab(), "tile_to_latlon", "latlon_to_tile")
    lat, lon = pair(f(69388, 51536, 17), "tile_to_latlon()")
    c.near(lat, 35.8534396195918, tol=1e-9, what="latitude of the NW corner")
    c.near(lon, 10.579833984375, tol=1e-9, what="longitude of the NW corner")
    lat, lon = pair(f(69409.5, 51547.5, 17), "tile_to_latlon()")
    c.near(lat, 35.8278347177, tol=1e-9, what="latitude of the centre of tile 17/69409/51547")
    for (la, lo) in (SOUSSE, SINGAPORE, REYKJAVIK, (-33.9249, 18.4241)):
        for z in (13, 16, 19):
            x, y = pair(to_tile(la, lo, z), "latlon_to_tile()")
            n_lat, w_lon = pair(f(x, y, z), "tile_to_latlon()")
            s_lat, e_lon = pair(f(x + 1, y + 1, z), "tile_to_latlon()")
            c.ok(s_lat <= la <= n_lat and w_lon <= lo <= e_lon, f"({la}, {lo}) is not inside its own tile at zoom {z}")


@c.test("meters_per_pixel(): 156 543.03 m at zoom 0 on the equator; Singapore 1.1940, Reykjavik 0.5209 m at zoom 17",
        hint="EQUATOR_M · cos(lat in radians) / 2**z / TILE_PX. Each zoom level halves it.")
def _():
    (f,) = need(lab(), "meters_per_pixel")
    c.near(num(f(0.0, 0), "meters_per_pixel()"), 156543.034, tol=0.01, what="meters_per_pixel(0, 0)")
    c.near(f(SINGAPORE[0], 17), 1.19402896, tol=1e-6, what="meters_per_pixel(Singapore, 17)")
    c.near(f(REYKJAVIK[0], 17), 0.52090279, tol=1e-6, what="meters_per_pixel(Reykjavik, 17)")
    c.near(f(SOUSSE[0], 18), f(SOUSSE[0], 17) / 2, tol=1e-12, what="zoom 18 at Sousse (half of zoom 17)")


@c.test("zoom_for_gsd(): the highest zoom whose pixel is still ≥ the camera's, clamped to [zmin, zmax]",
        hint="z = floor(log2(meters_per_pixel(lat, 0) / gsd_m)) — math.log2 and math.floor — then "
             "max(zmin, min(zmax, z)). Return an int.")
def _():
    (f,) = need(lab(), "zoom_for_gsd")
    for args, want in [((0.0, 1.0), 17), ((SINGAPORE[0], 0.352, 13, 19), 18), ((SINGAPORE[0], 0.7, 13, 19), 17),
                       ((SINGAPORE[0], 100.0, 13, 19), 13), ((SINGAPORE[0], 0.01, 13, 19), 19), ((REYKJAVIK[0], 2.3), 14),
                       ((REYKJAVIK[0], 0.352, 13, 19), 17)]:
        z = num(f(*args), "zoom_for_gsd()")
        c.ok(isinstance(z, int), f"zoom_for_gsd{args} should be an int, got {z!r}")
        c.eq(z, want, what=f"zoom_for_gsd{args}")


@c.test("read_tile() returns the right JPEG for 17/69409/51547 (the Ribat), 19/277637/206190 and 13/4338/3221",
        hint="The file stores tile_row = 2**z − 1 − y (TMS). SELECT tile_data FROM tiles WHERE zoom_level=? "
             "AND tile_column=? AND tile_row=? with the tuple (z, x, row); return bytes(row[0]).")
def _():
    (f,) = need(lab(), "read_tile")
    for (z, x, y), md5 in [((17, 69409, 51547), "270e09c03dd62649227d2c37500973c4"),
                           ((19, 277637, 206190), "bd51161cc482d75e13e9cca612336df0"),
                           ((13, 4338, 3221), "a1b0ebd6d727e5becea3ed768b4bebc1")]:
        data = f(SMALL, z, x, y)
        c.ok(data is not None, f"read_tile() returned None for tile {z}/{x}/{y}, which is in the file "
                               "(TODO not done, or the row is not flipped)")
        c.ok(isinstance(data, (bytes, bytearray, memoryview)), f"read_tile() should return bytes, got {type(data).__name__}")
        data = bytes(data)
        c.ok(data[:3] == b"\xff\xd8\xff", "these bytes are not a JPEG picture")
        c.eq(hashlib.md5(data).hexdigest(), md5, what=f"the fingerprint (md5) of tile {z}/{x}/{y}")


@c.test("read_tile() returns None for a missing tile and opens the file read-only",
        hint="fetchone() gives None when no row matches. Open with sqlite3.connect('file:' + path + '?mode=ro', uri=True).")
def _():
    (f,) = need(lab(), "read_tile")
    c.ok(f(SMALL, 17, 69409, 51547) is not None, "read_tile() returned None for a tile that exists (TODO 8 not done yet)")
    c.ok(f(SMALL, 17, 1, 1) is None, "read_tile() should return None when the tile does not exist")
    src = "\n".join(l.split("#")[0] for l in open("tiles_lab.py").read().splitlines())
    c.ok(re.search(r"mode\s*=\s*ro", src) is not None,
         "I can't find mode=ro in tiles_lab.py: the shared map must be opened read-only")


@c.test("latlon_to_pixel() / pixel_to_latlon(): the Ribat at (376.03, 399.49) of its mosaic; exact inverse; = NAVERA",
        hint="px = (fractional x − x0) · TILE_PX, py = (fractional y − y0) · TILE_PX. Back: "
             "tile_to_latlon(x0 + px / TILE_PX, y0 + py / TILE_PX, z).")
def _():
    to_px, to_ll = need(lab(), "latlon_to_pixel", "pixel_to_latlon")
    px, py = pair(to_px(*SOUSSE, 17, 69408, 51546), "latlon_to_pixel()")
    c.near(px, 376.031, tol=0.01, what="px of the Ribat (top-left tile 69408, 51546)")
    c.near(py, 399.487, tol=0.01, what="py of the Ribat")
    lat, lon = pair(to_ll(px, py, 17, 69408, 51546), "pixel_to_latlon()")
    c.near(lat, SOUSSE[0], tol=1e-10, what="latitude after pixel -> lat/lon")
    c.near(lon, SOUSSE[1], tol=1e-10, what="longitude after pixel -> lat/lon")
    lat, lon = pair(to_ll(100.25, 37.5, 17, 69409, 51547), "pixel_to_latlon()")
    c.near(lat, 35.8286219481, tol=1e-9, what="latitude of pixel (100.25, 37.5) of tile 17/69409/51547")
    c.near(lon, 10.6385877728, tol=1e-9, what="longitude of that pixel")


@c.test("mosaic.py builds a 768 × 768 mosaic (the checker's own test: Monastir marina, zoom 17, small map)",
        hint="Run `python3 mosaic.py 35.7795 10.8320 17 --map /data/academy/07-map-tiles/sousse_small.mbtiles` "
             "and read the error, if any.")
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


RES = {}


@c.test("results.json (from python3 analysis.py): world scales, zoom by altitude, corner bug, map file facts",
        hint="Run `python3 analysis.py` after your last change (it takes ~20 s). If the numbers are wrong while "
             "the function checks pass, run it again.")
def _():
    c.ok(os.path.exists("results.json"), "results.json is missing: run python3 analysis.py")
    RES.update(json.load(open("results.json")))
    rows = {r["place"]: r for r in RES.get("world", [])}
    c.ok("Singapore" in rows and "Reykjavik" in rows,
         "results.json has no 'world' table with Singapore and Reykjavik: run the current analysis.py")
    c.near(rows["Singapore"]["m_per_px_z17"], 1.1940, tol=1e-4, what="m_per_px_z17 of Singapore")
    c.near(rows["Reykjavik"]["m_per_px_z17"], 0.5209, tol=1e-4, what="m_per_px_z17 of Reykjavik")
    c.eq(RES.get("singapore_zoom_by_altitude"), {"150": 19, "200": 19, "300": 18, "500": 18, "1000": 17,
                                                 "1500": 16, "2000": 16}, what="singapore_zoom_by_altitude")
    c.near(RES.get("corner_bug_m", {}).get("Singapore", 0), 215.9, tol=0.2, what="corner_bug_m for Singapore")
    c.near(RES.get("corner_bug_m", {}).get("Reykjavik", 0), 94.2, tol=0.2, what="corner_bug_m for Reykjavik")
    c.near(RES.get("corner_bug_m", {}).get("Sousse (NAVERA test map)", 0), 175.1, tol=0.2, what="corner_bug_m for Sousse")
    m = RES.get("map", {})
    c.eq(m.get("file_bytes"), 10286944256, what="map.file_bytes")
    c.eq(m.get("total_tiles"), 1154943, what="map.total_tiles")


def numbers(text):
    flat = re.sub(r"(?<=\d)[ ,  ](?=\d{3}\b)", "", text)
    return [float(v) for v in re.findall(r"\d+(?:\.\d+)?", flat)]


@c.test("report.md: three sections, at least 150 words, and the key numbers quoted",
        hint="Headings '## World scales', '## The map file', '## The corner bug'. Quote the zoom-17 m/px of Singapore "
             "and Reykjavik, the real file size in GB and the metadata estimate in MB, and the corner error at Singapore in m.")
def _():
    c.file_exists("report.md")
    text = re.sub(r"<!--.*?-->", "", open("report.md", encoding="utf-8").read(), flags=re.S)
    for h in ("## World scales", "## The map file", "## The corner bug"):
        c.ok(re.search(r"^" + re.escape(h), text, re.M | re.I) is not None, f"report.md has no '{h}' heading")
    words = re.findall(r"[A-Za-z]{2,}", text)
    c.ok(len(words) >= 150, f"report.md has only {len(words)} words of your own (at least 150 expected)")
    found = numbers(text)
    for want, tol, name in [(1.194, 0.006, "Singapore's m/px at zoom 17 (≈ 1.19)"), (0.521, 0.006, "Reykjavik's m/px at zoom 17 (≈ 0.52)"),
                            (10.29, 0.02, "the real file size in GB (≈ 10.29)"), (36467, 0.5, "the metadata estimate (36467 MB)"),
                            (215.9, 1.0, "the corner error at Singapore (≈ 216 m)")]:
        c.ok(any(abs(v - want) <= tol for v in found), f"report.md does not quote {name}")


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
