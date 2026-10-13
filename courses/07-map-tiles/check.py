import contextlib
import io
import math
import os
import re
import shutil
import sqlite3
import tempfile

from academy_check import CheckFailed, Checker, explained, is_stub, load_student, need, predicted, run

c = Checker()
SMALL = "/data/academy/07-map-tiles/sousse_small.mbtiles"   # 88 tiles of the course's OpenStreetMap map
JPEG = b"\xff\xd8\xff"


def tiles():
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student("navera_lite.tiles", fresh=True)


def functions(*names):
    mod = tiles()
    fns = need(mod, *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/tiles.py)")
    return fns


def answers(*names):
    with contextlib.redirect_stdout(io.StringIO()):
        return need(load_student("answers.py", fresh=True), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def num(v, what):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    if isinstance(v, (tuple, list)):
        raise CheckFailed(f"{what} should return one number, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return one number, got {v!r}")


def pair(v, what):
    if v is None:
        raise CheckFailed(f"{what} returned None — does every path end with `return`?")
    try:
        vals = [float(x) for x in v]
    except (TypeError, ValueError):
        raise CheckFailed(f"{what} should return two numbers, got {v!r}")
    if len(vals) != 2:
        raise CheckFailed(f"{what} should return two numbers, got {len(vals)}: {v!r}")
    return vals


TIPS = [("math domain error", " — math.log got a number ≤ 0: a latitude in DEGREES went into math.tan (lesson §1)"),
        ("unable to open database", " — open the map with sqlite3.connect('file:' + path + '?mode=ro', uri=True)"),
        ("Incorrect number of bindings", " — three ? in the SQL, three values in the tuple (lesson §5)"),
        ("'NoneType' object is not subscriptable", " — a query that finds nothing gives None: test `row is None` "
                                                   "before row[0]")]


def go(fn, *args, **kw):
    """run() with one more sentence for this mission's common errors."""
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        for key, tip in TIPS:
            if key in msg:
                raise CheckFailed(msg + tip)
        raise


def small_db():
    """The checker's own read-only connection to the small map (data, not student code)."""
    if not os.path.exists(SMALL):
        c.skip(f"the small map {SMALL} is not mounted — ask your teacher")
    return sqlite3.connect("file:" + SMALL + "?mode=ro", uri=True)


def ref_tile(db, z, x, y):
    row = db.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                     (z, x, 2 ** z - 1 - y)).fetchone()
    return None if row is None else bytes(row[0])


# ======================================================================== session 1 — Cartographer
@c.test("TODO 1: mercator_y() on unseen latitudes, north and south",
        hint="Lesson §1: the formula on the unit sphere, with φ in RADIANS; ln is math.log (not math.log10). It is 0 on "
             "the equator, π at MAX_LAT, and mercator_y(−φ) = −mercator_y(φ).")
def _():
    (f,) = functions("mercator_y")
    v0 = num(go(f, 0.0), "mercator_y(0.0)")
    if abs(v0 - -4.2897288) < 1e-5:
        raise CheckFailed("mercator_y(0.0) gives −4.289729: math.radians was applied to π/4 as well — π/4 is already in "
                          "radians, convert only the latitude")
    v = num(go(f, -22.9068), "mercator_y(-22.9068)")
    if abs(v - 1.0793546) < 1e-5 or abs(v) > 3.2:
        raise CheckFailed(f"mercator_y(−22.9068) gives {v:.6f}: the latitude went into math.tan in DEGREES — "
                          "convert with math.radians first")
    if abs(v - -0.4108961 / math.log(10)) < 1e-5:
        raise CheckFailed("mercator_y(−22.9068) is ln(…)/ln(10): you used math.log10 — ln, the natural logarithm, is "
                          "math.log")
    c.near(v, -0.4108961, 1e-6, "mercator_y(−22.9068) (Rio de Janeiro)")
    c.near(num(go(f, 60.0), "mercator_y(60)"), 1.3169579, 1e-6, "mercator_y(60.0)")
    c.near(num(go(f, 89.0), "mercator_y(89)"), 4.7413488, 1e-6, "mercator_y(89.0) (beyond the web map, still defined)")
    c.near(num(go(f, -60.0), "mercator_y(-60)"), -1.3169579, 1e-6, "mercator_y(−60.0)")


@c.test("TODO 2: tile_xy() gives fractional tile coordinates on unseen places and zooms",
        hint="Lesson §2: x is a direct proportion of the longitude; y uses your mercator_y and counts rows from the "
             "NORTH. Return the two fractional numbers (no floor, no int).")
def _():
    (f,) = functions("tile_xy")
    x, y = pair(go(f, -1.2921, 36.8219, 15), "tile_xy(Nairobi, 15)")
    c.near(x, 19735.611164, 1e-5, "x of Nairobi at zoom 15")
    if abs(y - (32768 - 16501.619783)) < 1e-3:
        raise CheckFailed("y of Nairobi is mirrored: XYZ rows count from the NORTH — y = (1 − mercator_y/π)/2·n")
    c.ok(abs(y - round(y)) > 1e-9 or abs(x - round(x)) > 1e-9,
         "tile_xy returned whole numbers: return the FRACTIONAL coordinates (the tile is their floor)")
    c.near(y, 16501.619783, 1e-5, "y of Nairobi at zoom 15")
    x, y = pair(go(f, 35.6762, 139.6503, 12), "tile_xy(Tokyo, 12)")
    c.near(x, 3636.91008, 1e-5, "x of Tokyo at zoom 12")
    c.near(y, 1612.985257, 1e-5, "y of Tokyo at zoom 12")
    x, y = pair(go(f, -41.2865, 174.7762, 16), "tile_xy(Wellington, 16)")
    c.near(y, 41034.106019, 1e-5, "y of Wellington at zoom 16 (south of the equator: y > n/2)")
    c.near(pair(go(f, 10.0, -180.0, 3), "tile_xy")[0], 0.0, 1e-9, "x at longitude −180")


@c.test("TODO 3: tile_to_latlon() — corners, centres, fractional tiles, and the inverse of tile_xy",
        hint="Lesson §2 'The way back': undo tile_xy; the latitude in DEGREES. No int() inside: x + 0.5 must give the "
             "centre.")
def _():
    to_ll, to_xy = functions("tile_to_latlon", "tile_xy")
    lat, lon = pair(go(to_ll, 19293.25, 12345.75, 15), "tile_to_latlon(19293.25, 12345.75, 15)")
    if abs(lat - math.radians(40.499181)) < 1e-4:
        raise CheckFailed("the latitude is in RADIANS: wrap it in math.degrees(…)")
    if abs(lon - 31.959228) < 1e-5 or abs(lat - 40.505446) < 1e-5:
        raise CheckFailed("tile_to_latlon ignores the fractional part (int() or floor inside?): it must accept "
                          "x + 0.5, y + 0.5")
    c.near(lat, 40.4991809, 1e-7, "latitude of (19293.25, 12345.75) at zoom 15")
    c.near(lon, 31.9619751, 1e-7, "longitude of (19293.25, 12345.75) at zoom 15")
    lat, lon = pair(go(to_ll, 2047, 1023, 11), "tile_to_latlon(2047, 1023, 11)")
    c.near(lat, 0.1757810, 1e-7, "latitude of the NW corner of 11/2047/1023")
    c.near(lon, 179.8242188, 1e-7, "longitude of the NW corner of 11/2047/1023")
    for la, lo, z in [(-33.9249, 18.4241, 14), (64.8378, -147.7164, 18), (-54.8019, -68.3030, 13)]:
        x, y = pair(go(to_xy, la, lo, z), "tile_xy")
        back = pair(go(to_ll, x, y, z), "tile_to_latlon")
        c.ok(math.dist(back, (la, lo)) < 1e-9, f"tile_to_latlon(tile_xy({la}, {lo}, {z})) gives {back}, not the point")
        n_lat, w_lon = pair(go(to_ll, math.floor(x), math.floor(y), z), "tile_to_latlon")
        s_lat, e_lon = pair(go(to_ll, math.floor(x) + 1, math.floor(y) + 1, z), "tile_to_latlon")
        c.ok(s_lat <= la <= n_lat and w_lon <= lo <= e_lon, f"({la}, {lo}) is not inside its own tile at zoom {z}")


@c.test("TODO 4: m_per_px() at unseen latitudes and zooms",
        hint="Lesson §3: the equator cut into 256·2**z pixels, shrunk by cos(latitude) — radians inside cos. Each zoom "
             "level halves it.")
def _():
    (f,) = functions("m_per_px")
    v = num(go(f, -1.2921, 16), "m_per_px(-1.2921, 16)")
    if abs(v - 8694.6239) < 0.01 or abs(v - 75880.354) < 0.01:
        raise CheckFailed(f"m_per_px(Nairobi, 16) gives {v:,.1f}: ^ in Python is XOR (2 ^ 16 = 18), not a power — "
                          "write 2 ** z")
    if abs(v - 2.3880498 * 256) < 1:
        raise CheckFailed("m_per_px is 256 times too large: a tile has TILE_PX = 256 pixels per side")
    if abs(v - 0.6571263) < 1e-4:
        raise CheckFailed("m_per_px(Nairobi, 16) gives 0.657126: math.cos got the latitude in DEGREES — math.radians")
    c.near(v, 2.3880498, 1e-6, "m_per_px(Nairobi, 16)")
    v = num(go(f, 60.1699, 18), "m_per_px(60.1699, 18)")
    c.ok(v > 0, f"m_per_px(60.1699, 18) = {v:.4f} < 0: math.cos got DEGREES")
    c.near(v, 0.2970473, 1e-6, "m_per_px(Helsinki, 18)")
    c.near(num(go(f, -54.8019, 13), "m_per_px"), 11.0146755, 1e-5, "m_per_px(Ushuaia, 13)")


@c.test("TODO 5: best_zoom() — the highest zoom whose pixel is ≥ the GSD, an int, clamped, ValueError for GSD ≤ 0",
        hint="Lesson §3 and its 🧰 box: round DOWN, then keep the zoom inside [zmin, zmax]; return an int; refuse "
             "gsd_m ≤ 0 first with ValueError.")
def _():
    (f,) = functions("best_zoom")
    for args, want in [((0.5, -1.2921), 18), ((0.25, 60.1699), 18), ((3.0, -54.8019), 14), ((0.05, 0.0), 19),
                       ((50.0, 30.0), 13), ((1.0, -33.9), 16), ((3.0, -54.8019, 15, 17), 15)]:
        z = go(f, *args)
        c.ok(z is not None, f"best_zoom{args} returned None")
        c.ok(isinstance(z, int) and not isinstance(z, bool), f"best_zoom{args} should be an int, got {z!r}")
        if args == (0.5, -1.2921) and z == 19:
            raise CheckFailed("best_zoom(0.5, Nairobi) gives 19: you rounded (or rounded up); the map must not be "
                              "finer than the photo — round DOWN with math.floor")
        if args == (0.5, -1.2921) and z == 13:
            wide = go(f, 0.5, -1.2921, 0, 30)
            if wide is not None and wide <= 0:
                raise CheckFailed("best_zoom(0.5, Nairobi) gives 13 because the ratio is upside down (a negative zoom, "
                                  "clamped): 2^z = (m/px at zoom 0) / GSD, so log2(m0 / gsd_m)")
            raise CheckFailed("best_zoom(0.5, Nairobi) gives 13 (= floor of ln): the zoom rule uses log₂ — math.log2, "
                              "not math.log")
        if args == (3.0, -54.8019) and z == 15:
            raise CheckFailed("best_zoom(3.0, Ushuaia) gives 15 (log2 = 14.88): you rounded to the nearest; the rule "
                              "rounds DOWN with math.floor")
        if args == (50.0, 30.0) and z == 11:
            raise CheckFailed("best_zoom(50.0, 30.0) gives 11: clamp the result to [zmin, zmax] = [13, 19]")
        c.eq(z, want, what=f"best_zoom{args}")
    for bad in (0.0, -0.3):
        try:
            got = f(bad, 35.8)
        except ValueError:
            continue
        except Exception as e:
            raise CheckFailed(f"best_zoom({bad}, 35.8) raised {type(e).__name__}: {e} — the docstring asks for "
                              "ValueError when gsd_m ≤ 0 (check it first)")
        raise CheckFailed(f"best_zoom({bad}, 35.8) returned {got!r}: raise ValueError when gsd_m ≤ 0")


@c.test("Steps 0–3: the map in numbers — prediction, big tiles, why high zooms are small, a zoom-18 tile",
        hint="Step 1: your own SQL with COUNT(*), WHERE zoom_level = … AND length(tile_data) > …. EXPLAIN_TILE_SIZE: what "
             "JPEG compresses well. KANTAOUI_TILE_Z18: whole parts of your tile_xy, written (x, y). "
             "EXPLAIN_SHARED_CORNER: even and odd tile numbers.")
def _():
    p, big, why, kt, sc = answers("PREDICT_TILES", "BIG_TILES_Z17", "EXPLAIN_TILE_SIZE", "KANTAOUI_TILE_Z18",
                                  "EXPLAIN_SHARED_CORNER")
    predicted("PREDICT_TILES", p)
    big = number(big, "BIG_TILES_Z17")
    c.ok(big != 12444, "BIG_TILES_Z17 is the number of ALL zoom-17 tiles: add the size condition, "
                       "length(tile_data) > 10000")
    c.ok(big == 1491, f"BIG_TILES_Z17 = {big:g} is not the count of zoom-17 tiles larger than 10 000 bytes — check "
                      "zoom_level = 17, length(tile_data) > 10000 (bytes, no spaces) and COUNT(*)")
    explained("EXPLAIN_TILE_SIZE", why,
              ((r"compress", r"jpe?g"), "what the file format does"),
              ((r"detail", r"uniform", r"plain", r"flat", r"simple", r"few", r"less", r"edge", r"same colou?r"),
               "what a high-zoom tile shows"))
    vals = pair(kt, "KANTAOUI_TILE_Z18")
    if vals[0] == 138788.0 and vals[1] == 2 ** 18 - 1 - 103036.0:
        raise CheckFailed("KANTAOUI_TILE_Z18 has the TMS row: write the XYZ (x, y) of tile_xy here")
    c.ok(vals == [138788.0, 103036.0], f"KANTAOUI_TILE_Z18 = {kt!r} is not the zoom-18 tile of Port El Kantaoui — "
                                        "the whole parts (math.floor) of your tile_xy(35.8930, 10.5965, 18)")
    explained("EXPLAIN_SHARED_CORNER", sc,
              ((r"even", r"odd", r"top.?left", r"first", r"child", r"quarter", r"parent", r"double", r"2 ?[x×*]"),
               "how a tile's children are numbered"),
              ((r"corner", r"north.?west", r"\bnw\b", r"same", r"share"), "which child keeps the corner"), min_words=6)


@c.test("Step 4: choosing a zoom — your rule at 1000 m, the highest height for zoom 19, why the map is coarser",
        hint="Lesson §3: the GSD of the lab's camera (tan in RADIANS), then your best_zoom over Sousse. "
             "ALT_MAX_Z19_SOUSSE_M: the height where the GSD equals the zoom-19 pixel at Sousse. EXPLAIN_ZOOM: which "
             "is coarser, and what that saves.")
def _():
    p, bz, alt, why = answers("PREDICT_ZOOM", "BEST_ZOOM_SOUSSE_1000", "ALT_MAX_Z19_SOUSSE_M", "EXPLAIN_ZOOM")
    predicted("PREDICT_ZOOM", p)
    bz = number(bz, "BEST_ZOOM_SOUSSE_1000")
    if bz == 15:
        raise CheckFailed("BEST_ZOOM_SOUSSE_1000 = 15 is the map's table; the question asks what YOUR best_zoom gives")
    c.ok(bz == 16, f"BEST_ZOOM_SOUSSE_1000 = {bz:g} is not what best_zoom gives for the lab's camera (84°, 1536 px) at "
                   "1000 m over Sousse — GSD = 2·H·tan(42°)/1536 with math.radians, then best_zoom(gsd, 35.8277)")
    alt = number(alt, "ALT_MAX_Z19_SOUSSE_M")
    if abs(alt - 150) < 1 or abs(alt - 200) < 1:
        raise CheckFailed("ALT_MAX_Z19_SOUSSE_M is the map table's height: compute where YOUR rule stops giving 19 "
                          "(GSD = m_per_px(35.8277, 19))")
    if abs(alt - 81.1) < 1:
        raise CheckFailed("ALT_MAX_Z19_SOUSSE_M about 81 m: tan got DEGREES — math.tan(math.radians(42))")
    if abs(alt - 207.0) < 0.05:
        raise CheckFailed("ALT_MAX_Z19_SOUSSE_M = 207: that is the first height where best_zoom is NOT 19 — give the last "
                          "height where it is, to one decimal (algebra: GSD = zoom-19 pixel)")
    c.near(alt, 206.5, 0.3, "ALT_MAX_Z19_SOUSSE_M (m)")
    explained("EXPLAIN_ZOOM", why,
              ((r"coarse", r"table", r"lower", r"one level", r"less detail", r"bigger pixel"), "which one is coarser"),
              ((r"fast", r"speed", r"time", r"fewer", r"less tiles", r"number of tiles", r"compute", r"cheap"),
               "what a coarser zoom saves"),
              ((r"detail", r"robust", r"chang", r"noise", r"shrink", r"never enlarg", r"blur", r"small"),
               "why less detail can be better"))


# ======================================================================== session 2 — Tile hunter
@c.test("TODO 6: open_map() opens the map READ-ONLY, and refuses a missing file",
        hint="Lesson §5 and its 🧰 box: a read-only URI, with uri=True; path None → MAP_PATH; a missing file → "
             "FileNotFoundError, tested before SQLite sees the path.")
def _():
    small_db()
    (f,) = functions("open_map")
    tmp = tempfile.mkdtemp(prefix="check07_")
    try:
        copy = os.path.join(tmp, "copy.mbtiles")
        shutil.copy(SMALL, copy)
        os.chmod(copy, 0o666)
        before = open(copy, "rb").read()
        db = go(f, copy)
        c.ok(db is not None, "open_map returned None: return the connection")
        n = db.execute("SELECT COUNT(*) FROM tiles").fetchone()
        c.ok(tuple(n) == (88,), f"through your connection the small map has {n!r} tiles, not (88,)")
        try:
            db.execute("CREATE TABLE written_by_check (a)")
            db.commit()
        except Exception as e:                                           # noqa: BLE001
            c.ok("readonly" in str(e) or "read-only" in str(e) or "read only" in str(e),
                 f"writing failed, but not because the database is read-only: {e}")
        else:
            raise CheckFailed("open_map gives a connection that can WRITE: the map must be opened with "
                              "'file:' + path + '?mode=ro' and uri=True")
        finally:
            with contextlib.suppress(Exception):
                db.close()
        c.ok(open(copy, "rb").read() == before, "the map file changed after open_map: it must be read-only")
        if os.path.exists("/data/map.mbtiles"):
            try:
                d0 = run(f, seconds=20)
            except CheckFailed as e:
                raise CheckFailed(f"open_map() with no path: {str(e).split(' — ')[0]} — None must become MAP_PATH BEFORE "
                                  "os.path.exists (map_patch, which later missions use, calls open_map() like this)")
            c.ok(d0 is not None, "open_map() with no path returned None: open MAP_PATH")
            n0 = d0.execute("SELECT COUNT(*) FROM tiles WHERE zoom_level = 13").fetchone()
            c.ok(tuple(n0)[0] > 0, "open_map() with no path did not open the course map (MAP_PATH)")
        missing = os.path.join(tmp, "no_such_map.mbtiles")
        try:
            f(missing)
        except FileNotFoundError:
            pass
        except Exception as e:                                           # noqa: BLE001
            raise CheckFailed(f"open_map(a missing file) raised {type(e).__name__}: {e} — raise FileNotFoundError "
                              "(test os.path.exists first)")
        else:
            raise CheckFailed("open_map(a missing file) did not raise FileNotFoundError")
        c.ok(not os.path.exists(missing), "open_map created a new empty file for a missing path: test "
                                          "os.path.exists first and raise FileNotFoundError")
        src = open("navera_lite/tiles.py", encoding="utf-8").read()
        m = re.search(r"^def open_map\(.*?(?=^def |^# @part|^# TODO|\Z)", src, re.S | re.M)
        body = re.sub(r'""".*?"""|#[^\n]*', "", m.group(0) if m else "", flags=re.S)
        c.ok(re.search(r"uri\s*=\s*True", body) is not None,
             "open_map: pass uri=True to sqlite3.connect — this computer's SQLite reads '?mode=ro' even without it, "
             "others take the whole text as a file name and create a new writable file (lesson §5)")
        c.ok("mode=ro" in body, "open_map: the URI must say mode=ro (lesson §5)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@c.test("TODO 7: read_tile() returns the right JPEG bytes of unseen tiles, None for absent tiles",
        hint="Lesson §4–§5: the file stores TMS rows; three ? and a tuple of values in the same order; no row → None, "
             "otherwise the bytes of the BLOB.")
def _():
    ref = small_db()
    op, rd = functions("open_map", "read_tile")
    db = go(op, SMALL)
    for z, x, y, what in [(17, 69393, 51518, "Port El Kantaoui, zoom 17"), (19, 277638, 206191, "a corner of the Ribat "
                          "block, zoom 19"), (13, 4339, 3222, "zoom 13")]:
        got = go(rd, db, z, x, y)
        if got is None:
            raise CheckFailed(f"read_tile(db, {z}, {x}, {y}) returned None, but the small map has this tile ({what}): "
                              "is the TMS row 2**z − 1 − y, and are the values in the order of the ? ?")
        c.ok(isinstance(got, bytes), f"read_tile should return bytes, got a {type(got).__name__}: bytes(row[0])")
        c.ok(got[:3] == JPEG, f"tile {z}/{x}/{y} does not start with the JPEG bytes FF D8 FF: {got[:8]!r}")
        if got in (ref_tile(ref, z, x, y - 1), ref_tile(ref, z, x, y + 1)):
            raise CheckFailed(f"read_tile(db, {z}, {x}, {y}) returned the NEIGHBOUR tile, one row north or south "
                              f"({what}): the TMS row is (2**z − 1) − y — the − 1 matters (lesson §4)")
        c.ok(got == ref_tile(ref, z, x, y), f"read_tile(db, {z}, {x}, {y}) returned other bytes than the tile "
                                            f"{z}/{x}/{y} ({what}) — the TMS row?")
    for z, x, y in [(17, 103350, 65068), (17, 69420, 51547), (16, 34704, 25774 + 40)]:
        got = go(rd, db, z, x, y)
        c.ok(got is None, f"read_tile(db, {z}, {x}, {y}) should be None (no such tile in the small map), got "
                          f"{type(got).__name__}")


@c.test("TODO 7: read_tile() refuses impossible addresses with ValueError — z first, quickly — and uses ? placeholders",
        hint="The docstring's rules, at the top of read_tile, before any computation: whole numbers (NumPy integers "
             "too), z in range BEFORE 2**z, then x and y; otherwise ValueError. The SQL text has three ? and no number.")
def _():
    small_db()
    op, rd = functions("open_map", "read_tile")
    db = go(op, SMALL)
    for args, what in [((31, 0, 0), "zoom 31"), ((17, 69409, -2), "a negative row"),
                       ((15, 2 ** 15, 12886), "column 2**15 at zoom 15"), ((17, "69409", 51547), "a column given as text"),
                       ((17, 69409.0, 51547), "a column given as a float"), ((True, 0, 0), "True as a zoom")]:
        try:
            got = run(rd, db, *args, seconds=10)
        except CheckFailed as e:
            msg = str(e)
            if "ValueError" in msg:
                continue
            raise CheckFailed(f"read_tile(db, {', '.join(map(repr, args))}) — {what}: {msg.split(' — ')[0]} — the "
                              "docstring asks for ValueError (check the address yourself, first)")
        raise CheckFailed(f"read_tile(db, {', '.join(map(repr, args))}) — {what}: returned {repr(got)[:40]} instead of "
                          "raising ValueError")
    import numpy as np
    try:
        got = run(rd, db, np.int64(17), np.int32(69409), np.int64(51547), seconds=10)
    except CheckFailed as e:
        raise CheckFailed(f"read_tile(db, np.int64(17), np.int32(69409), np.int64(51547)): {str(e).split(' — ')[0]} — "
                          "NumPy integers are whole numbers too (later missions compute tiles with NumPy): accept "
                          "numbers.Integral, refuse bool, float and text")
    if got is None:
        raise CheckFailed("read_tile(db, np.int64(17), np.int32(69409), np.int64(51547)) returned None: sqlite3 sends "
                          "NumPy integers as 8 raw bytes, so the query finds nothing — convert z, x, y with int() RIGHT "
                          "AFTER the whole-number test, before any arithmetic (2 ** np.int64(17) and n − 1 − y are "
                          "NumPy integers too; lab Step 5, 🧰 box)")
    c.ok(isinstance(got, bytes) and got[:3] == JPEG, "read_tile with NumPy integers should return the Ribat's JPEG bytes")
    import time
    t0 = time.perf_counter()
    try:
        got = run(rd, db, 10 ** 9, 0, 0, seconds=2)
    except CheckFailed as e:
        msg = str(e)
        if "ValueError" not in msg:
            if "finish" in msg or "seconds" in msg or "time" in msg.lower():
                raise CheckFailed("read_tile(db, 10**9, 0, 0) did not answer within 2 s: you build 2**z before "
                                  "checking z (NAVERA's WEB-4, lesson §5)")
            raise CheckFailed(f"read_tile(db, 10**9, 0, 0): {msg} — raise ValueError for z > 30, before 2**z")
    else:
        raise CheckFailed(f"read_tile(db, 10**9, 0, 0) returned {got!r} instead of raising ValueError")
    took = time.perf_counter() - t0
    c.ok(took < 0.5, f"read_tile(db, 10**9, 0, 0) raised ValueError but took {took:.1f} s: you build 2**z before "
                     "checking z (NAVERA's WEB-4, lesson §5)")
    src = open("navera_lite/tiles.py", encoding="utf-8").read()
    m = re.search(r"^def read_tile\(.*?(?=^def |^# @part|^# TODO|\Z)", src, re.S | re.M)
    body = re.sub(r'""".*?"""|#[^\n]*', "", m.group(0) if m else "", flags=re.S)
    first_pow = re.search(r"2\s*\*\*\s*\(?\s*(int\()?\s*z\b|1\s*<<\s*\(?\s*(int\()?\s*z\b|pow\(\s*2\s*,\s*z\b", body)
    z_check = re.search(r"\b3[01]\b|(?<![<>])[<>]=?\s*z\b|\bz\s*[<>]=?(?![<>])", body)   # any comparison on z
    c.ok(first_pow is None or (z_check is not None and z_check.start() < first_pow.start()),
         "read_tile computes 2**z (or 1 << z) before comparing z with its limit (0 ≤ z ≤ 30): check z first — even 1 << z builds a "
         "125 MB number for z = 10**9 (WEB-4, lesson §5)")
    c.ok(body.count("?") >= 3, "read_tile's SQL should have three ? placeholders (lesson §5)")
    c.ok(not re.search(r"f[\"'][^\"']*SELECT|\.format\(|%\s*\(|SELECT[^\"']*[\"']\s*\+", body, re.I),
         "read_tile builds its SQL text from pieces (f-string, + or .format): use ? placeholders and a tuple of "
         "values (lesson §5)")


@c.test("Steps 5–6: the TMS row of your zoom-18 tile, and why the address checks and the placeholders matter",
        hint="Lesson §4: the TMS row of your KANTAOUI_TILE_Z18; compare sizes as lab Step 5 says. EXPLAIN_GUARD: what "
             "a huge z does to 2**z, and what a ? does with a value.")
def _():
    row, why = answers("TMS_ROW_KANTAOUI_Z18", "EXPLAIN_GUARD")
    row = number(row, "TMS_ROW_KANTAOUI_Z18")
    c.ok(row != 103036, "TMS_ROW_KANTAOUI_Z18 = 103036 is the XYZ row: the file counts rows from the south")
    if row in (159106, 159108):
        raise CheckFailed("TMS_ROW_KANTAOUI_Z18 is one off: lesson §4's flip is (2**z − 1) − y — compare the tile sizes "
                          "as lab Step 5 shows, a neighbour tile has another size")
    c.ok(row == 159107, f"TMS_ROW_KANTAOUI_Z18 = {row:g} is not the row stored for your zoom-18 tile (lesson §4)")
    explained("EXPLAIN_GUARD", why,
              ((r"huge", r"big", r"large", r"memory", r"slow", r"time", r"hang", r"freez", r"block", r"stall", r"second",
                r"denial", r"dos\b"), "what 2**z costs for a huge z"),
              ((r"placeholder", r"\?", r"parameter", r"bound", r"value"), "what a placeholder does"),
              ((r"sql", r"query", r"text", r"code", r"command", r"inject"), "what a value must never become"))


@c.test("TODO 8: latlon_to_pixel() — where a point is in a mosaic, on unseen points",
        hint="Lesson §6: tile coordinates relative to the mosaic's TOP-LEFT tile, in pixels.")
def _():
    (f,) = functions("latlon_to_pixel")
    px, py = pair(go(f, -1.2921, 36.8219, 15, 19733, 16502), "latlon_to_pixel")
    if px % 256 == 0 and py % 256 == 0:
        raise CheckFailed(f"latlon_to_pixel gives ({px:g}, {py:g}): whole tiles only — use the FRACTIONAL tile_xy, not "
                          "math.floor/int of it")
    if abs(px - 2.611164) < 1e-4:
        raise CheckFailed("latlon_to_pixel gives tile units: multiply by TILE_PX (256)")
    c.near(px, 668.458098, 1e-4, "px of Nairobi in a mosaic starting at tile (19733, 16502)")
    c.near(py, -97.335470, 1e-4, "py (negative: the point is above the mosaic's top edge)")
    px, py = pair(go(f, 35.8930, 10.5965, 17, 69392.5, 51517.25), "latlon_to_pixel")
    c.near(px, 401.385244, 1e-4, "px with a fractional top-left (69392.5, 51517.25)")
    c.near(py, 249.557249, 1e-4, "py with a fractional top-left")


@c.test("TODO 9: pixel_to_latlon() — the exact inverse, also for negative and fractional pixels",
        hint="Lesson §6: undo latlon_to_pixel step by step — pixels back to tile units, then add the mosaic's top-left "
             "tile; your tile_to_latlon does the rest.")
def _():
    to_ll, to_px = functions("pixel_to_latlon", "latlon_to_pixel")
    lat, lon = pair(go(to_ll, 300.5, -40.25, 16, 64512, 41000), "pixel_to_latlon")
    if abs(lat - -40.9789) < 1e-3:
        raise CheckFailed("pixel_to_latlon adds pixels to tile numbers: divide px and py by TILE_PX (256) first")
    c.near(lat, -41.1449193, 1e-7, "latitude of pixel (300.5, −40.25)")
    c.near(lon, 174.3814480, 1e-7, "longitude of pixel (300.5, −40.25)")
    lat, lon = pair(go(to_ll, 1000.0, 77.0, 18, 138700, 103000), "pixel_to_latlon")
    c.near(lat, 35.9332062, 1e-7, "latitude of pixel (1000, 77) at zoom 18")
    c.near(lon, 10.4808283, 1e-7, "longitude of pixel (1000, 77) at zoom 18")
    for la, lo, z, x0, y0 in [(64.8378, -147.7164, 17, 13760, 32001), (-33.9249, 18.4241, 19, 288970, 314714)]:
        p = pair(go(to_px, la, lo, z, x0, y0), "latlon_to_pixel")
        back = pair(go(to_ll, *p, z, x0, y0), "pixel_to_latlon")
        c.ok(math.dist(back, (la, lo)) < 1e-9, f"lat/lon → pixel → lat/lon round trip near ({la}, {lo}) gives {back} "
                                               "(this uses your latlon_to_pixel too: if the TODO 8 check fails, fix it "
                                               "first)")


@c.test("map_patch() works with your functions: a picture of the small map that matches the tiles pixel for pixel",
        hint="map_patch (given) uses your tile_xy, open_map and read_tile: if a check above fails, fix it first.")
def _():
    import numpy as np
    ref = small_db()
    mod = tiles()
    (mp,) = need(mod, "map_patch")
    for fn in ("tile_xy", "open_map", "read_tile"):
        if is_stub(getattr(mod, fn)):
            raise CheckFailed(f"map_patch needs your {fn}(): write its TODO first")
    lat, lon, z, w, h = 35.8930, 10.5965, 17, 300, 200
    got = go(mp, lat, lon, z, w, h, SMALL)
    got = np.asarray(got)
    c.ok(got.shape == (h, w, 3), f"map_patch returned shape {got.shape}, expected {(h, w, 3)}")
    import cv2
    n = 2 ** z
    gx = (lon + 180.0) / 360.0 * n * 256
    gy = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n * 256
    left, top = math.floor(gx) - w // 2, math.floor(gy) - h // 2
    want = np.full((h, w, 3), 40, np.uint8)
    for ty in range(top // 256, (top + h - 1) // 256 + 1):
        for tx in range(left // 256, (left + w - 1) // 256 + 1):
            data = ref_tile(ref, z, tx, ty)
            if data is None:
                continue
            tile = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            ox, oy = tx * 256 - left, ty * 256 - top
            a0, a1, b0, b1 = max(0, ox), min(w, ox + 256), max(0, oy), min(h, oy + 256)
            want[b0:b1, a0:a1] = tile[b0 - oy:b1 - oy, a0 - ox:a1 - ox]
    diff = float(np.abs(got.astype(int) - want.astype(int)).mean())
    c.ok(diff < 0.5, f"the patch around Port El Kantaoui differs from the map's tiles (mean difference {diff:.1f} "
                     "grey levels): tile numbers or the TMS row are off")


@c.test("TODO 10: tiles_in_circle() — every tile whose centre is within the radius, on unseen places",
        hint="The docstring: tiles whose CENTRE is within r_m by geo.haversine_m; look far enough around the point's tile "
             "(how many tile widths does r_m reach?); a sorted list of (x, y); ValueError for r_m < 0.")
def _():
    (f,) = functions("tiles_in_circle")
    for args, n, first in [((-33.9249, 18.4241, 600.0, 17), 16, (72242, 78678)),
                           ((-33.9249, 18.4241, 500.0, 17), 12, (72242, 78679)),
                           ((78.2232, 15.6267, 300.0, 17), 69, (71221, 18144)),
                           ((35.8277, 10.6388, 1000.0, 16), 13, (34703, 25772)),
                           ((35.8930, 10.5965, 130.0, 17), 1, (69394, 51518))]:
        import time
        t0 = time.perf_counter()
        try:
            got = run(f, *args, seconds=20)
        except CheckFailed as e:
            if "did not finish" in str(e):
                raise CheckFailed(f"tiles_in_circle{args} did not finish in 20 s: far too many tiles scanned — is your "
                                  "half-width in TILES? The tile width in metres is m_per_px(lat, z) × TILE_PX "
                                  "(m_per_px alone is one pixel)")
            raise
        if time.perf_counter() - t0 > 3.0:
            raise CheckFailed(f"tiles_in_circle{args} took {time.perf_counter() - t0:.0f} s: far too many "
                              "tiles scanned — is your half-width in TILES? The tile width in metres is "
                              "m_per_px(lat, z) × TILE_PX (m_per_px alone is one pixel)")
        try:
            tl = [tuple(int(v) for v in p) for p in got]
        except (TypeError, ValueError):
            raise CheckFailed(f"tiles_in_circle{args} should return a list of (x, y), got {got!r}"[:300])
        if sorted(tl) == tl and len(tl) < n:
            raise CheckFailed(f"tiles_in_circle{args} finds {len(tl)} tiles, too few: the search square around the "
                              "point's tile is too small for this radius — how many tile widths does r_m reach, and how "
                              "close can a tile k columns away come? (lab Step 7, hint 5 and EXPLAIN_MARGIN)")
        c.ok(sorted(tl) == tl, f"tiles_in_circle{args}: the list is not sorted — return sorted(…)")
        c.ok(len(set(tl)) == len(tl), f"tiles_in_circle{args}: a tile appears twice")
        c.ok(len(tl) == n and tl[0] == first, f"tiles_in_circle{args} gives {len(tl)} tiles — not the tiles whose "
                                              "CENTRE is within the radius (centre = x + 0.5, y + 0.5; distance "
                                              "with geo.haversine_m)")
    c.ok(go(f, 35.8930, 10.5965, 0.0, 17) == [], "tiles_in_circle with r_m = 0 should be [] (no centre is exactly "
                                                  "on the point)")
    try:
        f(35.8, 10.6, -5.0, 17)
    except ValueError:
        pass
    except Exception as e:                                               # noqa: BLE001
        raise CheckFailed(f"tiles_in_circle with r_m = −5 raised {type(e).__name__}: the docstring asks for ValueError")
    else:
        raise CheckFailed("tiles_in_circle with r_m = −5 should raise ValueError")


@c.test("Steps 7–8: the corner bug and the fix, the search circle, the map's real coverage and growth",
        hint="Step 7: Quito's corner → centre with your functions and geo.haversine_m; your tiles_in_circle at "
             "Reykjavik; EXPLAIN_MARGIN: the (k − ½)·w question. Step 8: your SQL (MIN(tile_column) at zoom 13) and tile_to_latlon. The EXPLAIN items: tile "
             "size and latitude; the matched pixel; whole tiles; tiles on the edge.")
def _():
    p, cq, why, fix, ncirc, west, wb, gr, mg = answers("PREDICT_CORNER", "CORNER_QUITO_M", "EXPLAIN_CORNER",
                                                       "EXPLAIN_FIX", "CIRCLE_TILES_REYKJAVIK", "COVER_WEST_Z13_DEG",
                                                       "EXPLAIN_BOUNDS", "EXPLAIN_GROWTH", "EXPLAIN_MARGIN")
    predicted("PREDICT_CORNER", p)
    cq = number(cq, "CORNER_QUITO_M")
    if abs(cq - 305.7) < 0.5:
        raise CheckFailed("CORNER_QUITO_M = 305.7 is the tile WIDTH; the bug is the corner → centre distance")
    if abs(cq - 216.2) < 0.05:
        raise CheckFailed("CORNER_QUITO_M = 216.2 is the flat width/√2; measure corner → centre with geo.haversine_m, "
                          "as the tool does")
    c.ok(abs(cq - 215.95) <= 0.08, f"CORNER_QUITO_M = {cq:g} m is not the corner → centre distance of Quito's zoom-17 "
                                    "tile — the tile from tile_xy(−0.1807, −78.4678, 17), its corner and its centre")
    explained("EXPLAIN_CORNER", why,
              ((r"equator", r"latitude", r"cos", r"stretch", r"mercator", r"scale"), "what changes with latitude"),
              ((r"tile", r"pixel", r"cover", r"larger", r"bigger", r"wider", r"ground", r"diagonal"),
               "what that does to the tile"))
    explained("EXPLAIN_FIX", fix,
              ((r"half", r"diagonal", r"175", r"corner", r"edge", r"up to"), "how far the centre can still be"),
              ((r"pixel", r"\bu\b", r"\(u", r"match", r"pixel_to_latlon", r"where the photo"), "what to publish instead"))
    ncirc = number(ncirc, "CIRCLE_TILES_REYKJAVIK")
    c.ok(ncirc != 21, "CIRCLE_TILES_REYKJAVIK = 21 is the Ribat's count: call your tiles_in_circle at Reykjavik "
                      "(64.1417, −21.9266)")
    c.ok(ncirc == 62, f"CIRCLE_TILES_REYKJAVIK = {ncirc:g} is not what tiles_in_circle(64.1417, −21.9266, 600.0, 17) "
                      "gives with a correct TODO 10 (if the TODO 10 check fails, fix it first)")
    explained("EXPLAIN_MARGIN", mg,
              ((r"half", r"½", r"0\.5", r"ceil", r"round(ed|ing)? up", r"k ?[-−] ?1/2", r"r_?m ?/ ?w", r"tile width"),
               "how far a tile k columns away can be"),
              ((r"north", r"latitude", r"\brow", r"smaller", r"cos", r"shrink", r"large", r"km", r"size"),
               "why a margin can matter"))
    west = number(west, "COVER_WEST_Z13_DEG")
    c.ok(abs(west - 10.47) > 0.002, "COVER_WEST_Z13_DEG = 10.47 is the metadata; compute what the zoom-13 tiles cover")
    if abs(west - 10.5029) < 0.001:
        raise CheckFailed("COVER_WEST_Z13_DEG: you took the EAST edge of the westernmost tile — its west edge is its "
                          "north-west corner's longitude")
    c.ok(abs(west - 10.459) <= 0.0006, f"COVER_WEST_Z13_DEG = {west:g} is not the west edge of the zoom-13 tiles — "
                                        "MIN(tile_column) at zoom 13, then the longitude of that tile's west side")
    explained("EXPLAIN_BOUNDS", wb,
              ((r"tile", r"grid", r"whole", r"snap", r"square"), "what the file stores"),
              ((r"larg", r"big", r"wide", r"km", r"coarse", r"zoom", r"size", r"small"), "why more at zoom 13"))
    explained("EXPLAIN_GROWTH", gr,
              ((r"edge", r"border", r"boundar", r"outside", r"partly", r"cut", r"bounds"), "the tiles at the edge"),
              ((r"child", r"4", r"four", r"share", r"fraction", r"proportion", r"low zoom", r"few"),
               "why it matters more at low zooms"))


@c.test("report.md: the map memo — three sections, ≥ 150 words, the key numbers",
        hint="Keep the three headings of the template. Quote, with units: the zoom-17 pixel size near the equator and in "
             "Reykjavik, the zoom your rule chooses at 1000 m, the number of tiles or the file size, and the corner "
             "errors in Sousse and Quito (lab Step 9 lists them).")
def _():
    c.file_exists("report.md")
    text = open("report.md", encoding="utf-8").read()
    for h in ("## Scales and zooms", "## The map file", "## The corner bug"):
        c.ok(re.search(r"^" + re.escape(h), text, re.M | re.I) is not None, f"report.md has no '{h}' heading")
    body = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    words = re.findall(r"[A-Za-zÀ-ÿ']{2,}", body)
    c.ok(len(words) >= 150, f"report.md has {len(words)} words of your own (at least 150 expected)")
    flat = re.sub(r"(?<=\d)[ ,  ](?=\d{3}\b)", "", body)
    for pat, what in [(r"\b1\.19\d*", "the zoom-17 pixel size near the equator (Quito or Singapore)"),
                      (r"\b0\.52\d*", "the zoom-17 pixel size in Reykjavik"),
                      (r"\b(zoom|z)\s?16\b", "the zoom your rule chooses at 1000 m, written 'zoom NN'"),
                      (r"\b(264585|198288|12444|979\.?\d*|980)\b", "the number of tiles or the size of the file"),
                      (r"\b175(\.\d+)?\b", "the corner error in Sousse"),
                      (r"\b21[56](\.\d+)?\b", "the corner error in Quito")]:
        c.ok(re.search(pat, flat, re.I) is not None, f"report.md does not quote {what}")


c.milestone("cartographer", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "TODO 5:", "Steps 0–3:", "Step 4:",
            label="Session 1 complete: Cartographer badge earned (the ✘ lines left, if any, are session 2)")
c.milestone("tile_hunter", "TODO", "Step", "map_patch", "report",
            label="Mission complete: Cartographer and Tile hunter badges earned")

c.run()
