"""run_tiles.py — runs YOUR functions of navera_lite/tiles.py on the lab's situations, and draws them.

    python3 run_tiles.py test                      each function on its docstring example
    python3 run_tiles.py explore                   look inside the map file: schema, size, metadata   (Step 1)
    python3 run_tiles.py explore "SELECT ..."      run your own SQL on the map (read only)            (Step 1)
    python3 run_tiles.py sousse                    the Ribat of Sousse at every zoom of the map         (Step 3)
    python3 run_tiles.py world                     pixel and tile sizes from the equator to the Arctic  (Step 4)
    python3 run_tiles.py tile LAT LON Z            read one tile with your read_tile()                  (Step 5)
    python3 run_tiles.py guard                     impossible tile addresses: does read_tile refuse them? (Step 6)
    python3 run_tiles.py mosaic LAT LON Z          tiles around a point, the point, its tile's corner   (Step 7)
                         [--radius R] [--out FILE.png]                     and centre
    python3 run_tiles.py corner                    the corner bug, measured in metres                   (Step 7)
    python3 run_tiles.py coverage                  what the map file really covers, against its metadata (Step 8)

Every mode reads the course map (/data/map.mbtiles); add --map FILE to read another MBTiles file, e.g.
--map /data/academy/07-map-tiles/sousse_small.mbtiles. Pictures are saved in out/ — click them in the
file list of the 📝 Code tab. Map data © OpenStreetMap contributors.
"""
import math
import os
import sqlite3
import sys

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

t = rk.load_student("navera_lite.tiles")
g = rk.load_student("navera_lite.geo")
_kit_hint = rk._hint


def _hint(e):
    """This mission's extra sentence for the errors students meet most."""
    s = str(e)
    if isinstance(e, ValueError) and "math domain error" in s:
        return (" — math.log() got a number ≤ 0: a latitude in DEGREES went into math.tan, which takes RADIANS "
                "(lesson §1: convert with math.radians first)")
    if "unable to open database" in s:
        return " — the path is wrong, or the URI is not 'file:' + path + '?mode=ro' with uri=True (lesson §5)"
    if "readonly database" in s:
        return " — good: the map is read only. Your code must not try to write to it."
    if "Incorrect number of bindings" in s:
        return " — the number of ? in the SQL text must equal the number of values in the tuple (lesson §5)"
    if "'NoneType' object is not subscriptable" in s or "cannot unpack non-iterable NoneType" in s:
        return " — a function you call returned None: is its TODO written, and does every path end with `return`?"
    return _kit_hint(e)


rk._hint = _hint

RIBAT = (35.8277, 10.6388)             # the Ribat of Sousse, a square fort of the 8th century
KANTAOUI = (35.8930, 10.5965)          # Port El Kantaoui marina, 8 km north of Sousse
PLACES = [("Lagos", 6.4541, 3.3947),
          ("Mexico City", 19.4326, -99.1332), ("Cape Town", -33.9249, 18.4241), ("Sousse", *RIBAT),
          ("London", 51.5007, -0.1246), ("Anchorage", 61.2181, -149.9003), ("Reykjavik", 64.1417, -21.9266),
          ("Longyearbyen", 78.2232, 15.6267)]


def map_path(args):
    """--map FILE from the command line (removed from args), else the course map."""
    if "--map" in args:
        i = args.index("--map")
        if i + 1 >= len(args):
            sys.exit("--map needs a file name, e.g. --map /data/academy/07-map-tiles/sousse_small.mbtiles")
        path = args[i + 1]
        del args[i:i + 2]
    else:
        path = t.MAP_PATH
    if not os.path.exists(path):
        sys.exit(f"map file not found: {path} — ask your teacher (or try "
                 "--map /data/academy/07-map-tiles/sousse_small.mbtiles)")
    return path


def ro(path):
    """The runner's own read-only connection (Step 1 comes before your open_map)."""
    return sqlite3.connect("file:" + os.path.abspath(path) + "?mode=ro", uri=True)


def fmt(v, nd=1):
    return f"{v:,.{nd}f}".replace(",", " ")


def tile_of(lat, lon, z):
    """Whole tile numbers from YOUR tile_xy."""
    x, y = rk.need_ok(t, "tile_xy", lat, lon, z, n=2)
    return math.floor(x), math.floor(y)


# ------------------------------------------------------------------ test
def close(got, want, tol):
    if isinstance(want, (tuple, list)):
        try:
            vals = [float(v) for v in got]
        except (TypeError, ValueError):
            return False
        return len(vals) == len(want) and all(abs(a - b) <= tol for a, b in zip(vals, want))
    try:
        return abs(float(got) - want) <= tol
    except (TypeError, ValueError):
        return False


def show(v):
    if isinstance(v, (tuple, list)):
        try:
            return "(" + ", ".join(f"{float(x):.6f}" for x in v) + ")"
        except (TypeError, ValueError):
            return repr(v)
    if isinstance(v, bytes):
        return f"{len(v)} bytes starting with {v[:3]!r}"
    return f"{v:.6f}" if isinstance(v, float) else repr(v)


def fmt_args(args):
    return "(" + ", ".join(repr(a) for a in args) + ")"


def test():
    small = t.SMALL_MAP
    cases = [  # TODO, function, arguments, docstring result, tolerance, note when wrong
        (1, "mercator_y", (0.0,), 0.0, 1e-12, None),
        (1, "mercator_y", (51.5007,), 1.052085, 1e-6,
         "1.052085 for London. 1.775599 or 'math domain error': math.tan got DEGREES — math.radians first"),
        (1, "mercator_y", (t.MAX_LAT,), math.pi, 1e-6, None),
        (2, "tile_xy", (1.2834, 103.8607, 17), (103350.53, 65068.69), 0.01,
         "x is a direct proportion of the longitude; y uses mercator_y and counts rows from the NORTH (lesson §2)"),
        (2, "tile_xy", (0.0, 0.0, 1), (1.0, 1.0), 1e-9, None),
        (3, "tile_to_latlon", (0, 0, 0), (85.051129, -180.0), 1e-6,
         "the north-west corner of the world: lesson §2 'The way back', latitude in DEGREES"),
        (3, "tile_to_latlon", (103350.5, 65068.5, 17), (1.283920, 103.860626), 1e-6, None),
        (4, "m_per_px", (0.0, 0), 156543.03, 0.01, None),
        (4, "m_per_px", (1.2834, 17), 1.1940, 1e-4, "cos of the latitude in RADIANS; 256 · 2**z pixels (lesson §3)"),
        (5, "best_zoom", (0.352, 1.2834), 18, 0, None),
        (5, "best_zoom", (100.0, 1.2834), 13, 0, "keep the zoom inside [zmin, zmax]: 13 is the coarsest the map holds"),
        (5, "best_zoom", (0.0, 35.8), ValueError, None, None),
        (7, "read_tile", None, None, None, None),
        (8, "latlon_to_pixel", (1.2834, 103.8607, 17, 103349, 65067), (390.88, 432.45), 0.01, None),
        (9, "pixel_to_latlon", (128.0, 128.0, 17, 103350, 65068), (1.283920, 103.860626), 1e-6, None),
        (10, "tiles_in_circle", (35.8277, 10.6388, 300.0, 17),
         [(69408, 51547), (69409, 51546), (69409, 51547), (69409, 51548), (69410, 51547)], None, None),
    ]
    done = total = 0
    unwritten = set()
    for k, fn, args, want, tol, note in cases:
        if fn in unwritten:
            total += 1
            continue
        if fn == "read_tile":                                   # TODO 6 + 7 together, on the small map
            total += 3
            db, err = rk.call(t, "open_map", small)
            if err:
                print(f"✘ TODO  6  {err}")
                continue
            print(f"✔ TODO  6  open_map  ->  {type(db).__name__} (writing through it must fail: Step 5 tests that)")
            done += 1
            got, err = rk.call(t, "read_tile", db, 17, 69409, 51547)
            if err:
                if "NoneType" in err and "subscriptable" in err:
                    err = ("read_tile(): fetchone() returned None — no row for this address. Is the TMS row flipped "
                           "(lesson §4)? And test `row is None` before `row[0]`.")
                print(f"✘ TODO  7  {err}")
                continue
            ok = isinstance(got, bytes) and got[:3] == b"\xff\xd8\xff"
            print(f"{'✔' if ok else '✘'} TODO  7  read_tile(db, 17, 69409, 51547)  ->  {show(got)}" + (
                "" if ok else ("   (None: the Ribat IS in the map — is the TMS row flipped? lesson §4)" if got is None
                               else "   (the docstring says JPEG bytes starting with b'\\xff\\xd8\\xff')")))
            missing = None
            try:
                missing = t.read_tile(db, 17, 103350, 65068)
            except Exception as e:                              # noqa: BLE001 — shown to the student
                missing = e
            ok2 = missing is None
            print(f"{'✔' if ok2 else '✘'} TODO  7  read_tile(db, 17, 103350, 65068)  ->  {missing!r}" + (
                "" if ok2 else "   (Singapore is not in the map: return None when no row comes back)"))
            done += ok + ok2
            continue
        total += 1
        if want is ValueError:
            try:
                got = getattr(t, fn)(*args)
            except ValueError:
                print(f"✔ TODO {k:2d}  {fn}{fmt_args(args)}  ->  ValueError")
                done += 1
            except Exception as e:                              # noqa: BLE001 — shown to the student
                print(f"✘ TODO {k:2d}  {fn}{fmt_args(args)}  ->  {type(e).__name__}: {e}   (the docstring asks for "
                      "ValueError when gsd_m ≤ 0: check it first)")
            else:
                if rk.is_stub(getattr(t, fn)):
                    continue
                print(f"✘ TODO {k:2d}  {fn}{fmt_args(args)}  ->  {got!r}   (the docstring asks for ValueError when "
                      "gsd_m ≤ 0: check it first)")
            continue
        got, err = rk.call(t, fn, *args)
        if err:
            if "not written yet" in err:
                unwritten.add(fn)
            print(f"✘ TODO {k:2d}  {err}")
            continue
        if fn == "best_zoom":
            ok = isinstance(got, int) and not isinstance(got, bool) and got == want
            if got == want and not isinstance(got, int):
                note = f"the value is right but it is a {type(got).__name__}: return int(...)"
        elif fn == "tiles_in_circle":
            try:
                got_l = [tuple(int(v) for v in p) for p in got]
            except (TypeError, ValueError):
                got_l = None
            ok = got_l == want
            if not ok and got_l is not None and sorted(got_l) == want:
                note = "the right tiles in another order: return sorted(…)"
            elif not ok and got_l is not None and len(got_l) < len(want):
                note = f"{len(got_l)} tile(s) instead of 5: the circle reaches into the neighbour tiles (lab hint 4)"
        else:
            ok = close(got, want, tol)
        if not ok and fn == "mercator_y" and close(got, 0.456915, 1e-5):
            note = "0.456915: you used math.log10 — ln, the natural logarithm, is math.log"
        if not ok and fn == "tile_to_latlon" and close(got, (math.radians(85.051129), -180.0), 1e-3):
            note = "the latitude is in RADIANS: wrap it in math.degrees(…)"
        if not ok and fn == "tile_xy" and isinstance(got, (tuple, list)) and len(got) == 2 and close(got[0], 103350.53, 0.01):
            note = "x is right, y is not: y counts rows from the NORTH (lesson §2); is your mercator_y ✔ above?"
        why = f"   ({note})" if note else f"   (the docstring says {show(want)})"
        shown = show(got) if fn != "tiles_in_circle" else repr(got)
        print(f"{'✔' if ok else '✘'} TODO {k:2d}  {fn}{fmt_args(args)}  ->  {shown}" + ("" if ok else why))
        done += ok
    print(f"\n{done} of {total} example lines give the docstring's result.")


# ------------------------------------------------------------------ explore (Step 1)
def explore(args):
    path = map_path(args)
    db = ro(path)
    if args:
        try:
            cur = db.execute(args[0])
        except sqlite3.Error as e:
            sys.exit(f"SQLite refused this query: {e}")
        if cur.description is None:
            print("(no rows)")
            return
        print(" | ".join(d[0] for d in cur.description))
        for n, row in enumerate(cur):
            if n == 50:
                print("... (only the first 50 rows are shown)")
                break
            print(" | ".join(f"<{len(v)} bytes>" if isinstance(v, bytes) else str(v) for v in row))
        return
    print(f"File: {path}")
    print("\nSchema (the CREATE statements kept in sqlite_master):")
    for kind, name, sql in db.execute("SELECT type, name, sql FROM sqlite_master"):
        print(f"  {kind:<6} {name:<26} {' '.join((sql or '(automatic: made by the PRIMARY KEY)').split())}")
    page_size = db.execute("PRAGMA page_size").fetchone()[0]
    page_count = db.execute("PRAGMA page_count").fetchone()[0]
    print(f"\nSQLite pages: {page_count} pages × {page_size} bytes = {page_count * page_size} bytes")
    print(f"os.path.getsize:  {os.path.getsize(path)} bytes = {os.path.getsize(path) / 1e6:.1f} MB")
    print("\nmetadata (name = value):")
    for name, value in db.execute("SELECT name, value FROM metadata"):
        print(f"  {name:<18} {value}")
    print("\ntiles per zoom level:")
    for z, count in db.execute("SELECT zoom_level, COUNT(*) FROM tiles GROUP BY zoom_level ORDER BY zoom_level"):
        print(f"  zoom {z:>2}: {count:>7} tiles")


# ------------------------------------------------------------------ sousse (Step 3)
def sousse(args):
    lat, lon = RIBAT
    print(f"The Ribat of Sousse ({lat}, {lon}), with your tile_xy and tile_to_latlon:\n")
    print(f"{'zoom':>4} {'x (fractional)':>16} {'y (fractional)':>16}   {'tile':>16}   {'NW corner of the tile':>24}")
    for z in range(13, 20):
        x, y = rk.need_ok(t, "tile_xy", lat, lon, z, n=2)
        corner = rk.need_ok(t, "tile_to_latlon", math.floor(x), math.floor(y), z, n=2)
        print(f"{z:>4} {x:16.4f} {y:16.4f}   {f'{math.floor(x)}/{math.floor(y)}':>16}   "
              f"({corner[0]:.6f}, {corner[1]:.6f})")
    back = rk.need_ok(t, "tile_to_latlon", *t.tile_xy(lat, lon, 17), 17, n=2)
    print(f"\ntile_to_latlon(tile_xy(Ribat, 17)) = ({back[0]:.10f}, {back[1]:.10f})   (it must give the Ribat back)")
    print("From one zoom to the next, what happens to x and y? (Step 3 asks.)")


# ------------------------------------------------------------------ world (Step 4)
def world(args):
    print(f"{'place':<14}{'lat':>9}{'mercator_y':>12}{'1/cos φ':>9}{'m/px z13':>10}{'m/px z17':>10}"
          f"{'tile z17 (m)':>14}")
    for name, lat, lon in PLACES:
        y = rk.need_ok(t, "mercator_y", lat, kind=float)
        m13 = rk.need_ok(t, "m_per_px", lat, 13, kind=float)
        m17 = rk.need_ok(t, "m_per_px", lat, 17, kind=float)
        print(f"{name:<14}{lat:9.4f}{y:12.6f}{1 / math.cos(math.radians(lat)):9.3f}{m13:10.3f}{m17:10.4f}"
              f"{m17 * t.TILE_PX:14.1f}")
    m0 = rk.need_ok(t, "m_per_px", 0.0, 0, kind=float)
    if abs(m0 - 156543.03) > 0.1:
        print(f"\n⚠ m_per_px(0, 0) = {m0:.2f}: it should be 156 543.03 m (the equator cut into 256 pixels)")


# ------------------------------------------------------------------ tile (Step 5)
def tile(args):
    path = map_path(args)
    if len(args) != 3:
        sys.exit("usage: python3 run_tiles.py tile LAT LON ZOOM      e.g. python3 run_tiles.py tile 35.8277 10.6388 19")
    lat, lon, z = float(args[0]), float(args[1]), int(args[2])
    x, y = tile_of(lat, lon, z)
    print(f"({lat}, {lon}) is in tile {z}/{x}/{y} (XYZ numbering; the file stores another row number, lesson §4).")
    db = rk.need_ok(t, "open_map", path)
    data, err = rk.call(t, "read_tile", db, z, x, y)
    if err and "returned None" in err:
        print("read_tile() returned None: the map has no such tile (the course map covers Sousse only, "
              "zoom 13–19). That is the right answer for a place outside the map.")
        return
    if err:
        sys.exit(err)
    if not isinstance(data, bytes):
        sys.exit(f"read_tile() must return bytes (or None), it returned a {type(data).__name__}: return bytes(row[0])")
    print(f"read {len(data)} bytes, starting with {data[:3]!r}  (a JPEG file always starts with b'\\xff\\xd8\\xff')")
    import cv2
    img = t.decode_tile(data)
    big = cv2.resize(img, (512, 512), interpolation=cv2.INTER_NEAREST)
    t.stamp_attribution(big)
    os.makedirs("out", exist_ok=True)
    out = f"out/tile_{z}_{x}_{y}.png"
    cv2.imwrite(out, big)
    mpp = rk.need_ok(t, "m_per_px", lat, z, kind=float)
    print(f"the tile is {t.TILE_PX * mpp:.0f} m wide ({mpp:.3f} m per pixel); shown twice its size")
    rk.saved(out)


# ------------------------------------------------------------------ guard (Step 6)
GUARD_CASES = [("zoom 31 (the map stops at 19; tile numbers would not fit)", "31, 0, 0"),
               ("a negative column", "17, -1, 51547"),
               ("row 2**17 at zoom 17 (rows go from 0 to 2**17 - 1)", "17, 69409, 2 ** 17"),
               ("a row given as text", "17, 69409, '51547'"),
               ("a zoom of one billion (lesson §5: check z BEFORE computing 2**z)", "10 ** 9, 0, 0")]


def guard(args):
    """Each case runs in its own Python process and is timed: a function that builds 2**(10**9) first takes
    several seconds (and 125 MB) before it answers; one that checks z first answers at once."""
    import subprocess
    small = t.SMALL_MAP
    for fn in ("open_map", "read_tile"):
        if rk.is_stub(getattr(t, fn)):
            sys.exit(f"{fn}() is not written yet: write TODO 6 and TODO 7 first (lab Step 5)")
    print("read_tile() must raise ValueError, quickly, for every impossible address:\n")
    good = 0
    for what, call in GUARD_CASES:
        code = ("import sys, time; sys.path.insert(0, '.'); from navera_lite import tiles as t\n"
                f"db = t.open_map({small!r})\n"
                "t0 = time.perf_counter()\n"
                "try:\n"
                f"    r = t.read_tile(db, {call})\n"
                "    print('RETURNED', round(time.perf_counter() - t0, 2), repr(r)[:60])\n"
                "except ValueError as e:\n"
                "    print('VALUEERROR', round(time.perf_counter() - t0, 2), e)\n"
                "except Exception as e:\n"
                "    print('OTHER', round(time.perf_counter() - t0, 2), type(e).__name__, e)\n")
        try:
            out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=15)
            line = (out.stdout.strip().splitlines() or [out.stderr.strip().splitlines()[-1] if out.stderr.strip()
                                                          else "no output"])[-1]
        except subprocess.TimeoutExpired:
            line = "TIMEOUT"
        kind, _, rest = line.partition(" ")
        secs, _, msg = rest.partition(" ")
        try:
            secs = float(secs)
        except ValueError:
            secs, msg = 0.0, rest
        slow = secs > 0.5
        if kind == "VALUEERROR" and not slow:
            good += 1
            print(f"✔ read_tile(db, {call}) — {what}\n     ValueError: {msg}")
        elif kind == "VALUEERROR":
            print(f"✘ read_tile(db, {call}) — {what}\n     ValueError, but it took {secs:.1f} s: you build 2**z "
                  "before checking z (NAVERA's WEB-4, lesson §5)")
        elif line == "TIMEOUT":
            print(f"✘ read_tile(db, {call}) — {what}\n     still running after 15 s: you build 2**z before "
                  "checking z (NAVERA's WEB-4, lesson §5)")
        elif kind == "RETURNED":
            print(f"✘ read_tile(db, {call}) — {what}\n     it returned {msg} instead of raising ValueError")
        elif kind == "OTHER":
            print(f"✘ read_tile(db, {call}) — {what}\n     {msg} (the docstring asks for ValueError)")
        else:
            print(f"✘ read_tile(db, {call}) — {what}\n     {line}")
    print(f"\n{good} of {len(GUARD_CASES)} impossible addresses refused with ValueError.")


# ------------------------------------------------------------------ mosaic (Step 7)
def mosaic(args):
    path = map_path(args)
    radius, out = 1, "out/mosaic.png"
    for flag in ("--radius", "--out"):
        if flag in args:
            i = args.index(flag)
            if i + 1 >= len(args):
                sys.exit(f"{flag} needs a value")
            if flag == "--radius":
                radius = int(args[i + 1])
            else:
                out = args[i + 1]
            del args[i:i + 2]
    if len(args) != 3:
        sys.exit("usage: python3 run_tiles.py mosaic LAT LON ZOOM [--radius R] [--out FILE.png]")
    lat, lon, z = float(args[0]), float(args[1]), int(args[2])
    import cv2
    import numpy as np
    tx, ty = tile_of(lat, lon, z)
    x0, y0, k = tx - radius, ty - radius, 2 * radius + 1
    db = rk.need_ok(t, "open_map", path)
    img = np.full((k * t.TILE_PX, k * t.TILE_PX, 3), t.MISSING_GREY, np.uint8)
    missing = 0
    for row in range(k):
        for col in range(k):
            data, err = rk.call(t, "read_tile", db, z, x0 + col, y0 + row)
            if err and "returned None" not in err:
                sys.exit(err)
            if data is None:
                missing += 1
                continue
            img[row * t.TILE_PX:(row + 1) * t.TILE_PX, col * t.TILE_PX:(col + 1) * t.TILE_PX] = t.decode_tile(data)
    for i in range(1, k):                                            # thin white lines between tiles
        img[i * t.TILE_PX, :] = 255
        img[:, i * t.TILE_PX] = 255

    def mark(la, lo, colour, r):
        px, py = rk.need_ok(t, "latlon_to_pixel", la, lo, z, x0, y0, n=2)
        p = (int(round(px)), int(round(py)))
        cv2.circle(img, p, r, colour, 2)
        cv2.line(img, (p[0] - r - 8, p[1]), (p[0] + r + 8, p[1]), colour, 1)
        cv2.line(img, (p[0], p[1] - r - 8), (p[0], p[1] + r + 8), colour, 1)
        return px, py

    nw = rk.need_ok(t, "tile_to_latlon", tx, ty, z, n=2)
    centre = rk.need_ok(t, "tile_to_latlon", tx + 0.5, ty + 0.5, z, n=2)
    mark(*nw, (0, 200, 255), 6)                                      # yellow: NW corner of the point's tile
    mark(*centre, (40, 170, 40), 6)                                  # green: centre of the point's tile
    px, py = mark(lat, lon, (0, 0, 230), 12)                         # red: the point
    back = rk.need_ok(t, "pixel_to_latlon", px, py, z, x0, y0, n=2)
    mpp = rk.need_ok(t, "m_per_px", lat, z, kind=float)
    size = img.shape[1]
    length_m = next(L for L in (5000, 2000, 1000, 500, 200, 100, 50, 20, 10, 5) if L / mpp <= 0.4 * size)
    bar = int(round(length_m / mpp))
    cv2.rectangle(img, (10, size - 36), (30 + bar, size - 8), (255, 255, 255), -1)
    cv2.line(img, (20, size - 16), (20 + bar, size - 16), (0, 0, 0), 3)
    cv2.putText(img, f"{length_m} m", (22, size - 22), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
    t.stamp_attribution(img)
    if os.path.dirname(out):
        os.makedirs(os.path.dirname(out), exist_ok=True)
    cv2.imwrite(out, img)
    print(f"top-left tile ({x0}, {y0}), the point's tile ({tx}, {ty}); the point is at pixel ({px:.2f}, {py:.2f})")
    print(f"pixel -> lat/lon with your pixel_to_latlon gives back ({back[0]:.8f}, {back[1]:.8f})")
    if abs(back[0] - lat) > 1e-7 or abs(back[1] - lon) > 1e-7:
        print("⚠ that is not the point you gave: pixel_to_latlon must be the exact inverse of latlon_to_pixel")
    print(f"the mosaic is {k} × {k} tiles, {size} × {size} px, {size * mpp:.0f} m wide ({mpp:.3f} m per pixel)"
          + (f"; {missing} tile(s) not in the map (grey)" if missing else ""))
    print("red = the point, yellow = north-west corner of its tile, green = centre of its tile")
    rk.saved(out)


# ------------------------------------------------------------------ corner (Step 7)
def corner(args):
    print("The corner bug: a photo that matches a whole zoom-17 tile was published at the tile's NW corner.")
    print("Distance from the NW corner to the centre of the tile that holds each place (your tile functions,")
    print("distance with geo.haversine_m):\n")
    print(f"{'place':<14}{'lat':>9}{'tile z17':>18}{'tile width (m)':>16}{'corner -> centre (m)':>22}")
    for name, lat, lon in PLACES:
        x, y = tile_of(lat, lon, 17)
        nw = rk.need_ok(t, "tile_to_latlon", x, y, 17, n=2)
        c = rk.need_ok(t, "tile_to_latlon", x + 0.5, y + 0.5, 17, n=2)
        w = t.TILE_PX * rk.need_ok(t, "m_per_px", lat, 17, kind=float)
        d = g.haversine_m(*nw, *c)
        print(f"{name:<14}{lat:9.4f}{f'{x}/{y}':>18}{w:16.1f}{d:22.1f}")


# ------------------------------------------------------------------ coverage (Step 8)
def coverage(args):
    path = map_path(args)
    db = ro(path)
    meta = dict(db.execute("SELECT name, value FROM metadata"))
    print(f"metadata 'bounds' (west, south, east, north): {meta.get('bounds')}")
    print("What the tiles really cover, zoom by zoom (edges from YOUR tile_to_latlon):\n")
    print(f"{'zoom':>4}{'tiles':>9}{'columns':>16}{'rows (XYZ)':>16}{'west':>10}{'east':>10}{'south':>10}{'north':>10}")
    for z, x1, x2, r1, r2, n in db.execute("SELECT zoom_level, MIN(tile_column), MAX(tile_column), MIN(tile_row), "
                                           "MAX(tile_row), COUNT(*) FROM tiles GROUP BY zoom_level ORDER BY zoom_level"):
        if z < 15:
            print(f"{z:>4}{n:>9}   (zoom 13–14: Step 8 asks you to compute these edges yourself)")
            continue
        y1, y2 = 2 ** z - 1 - r2, 2 ** z - 1 - r1                       # TMS rows -> XYZ rows
        north, west = rk.need_ok(t, "tile_to_latlon", x1, y1, z, n=2)
        south, east = rk.need_ok(t, "tile_to_latlon", x2 + 1, y2 + 1, z, n=2)
        print(f"{z:>4}{n:>9}{f'{x1}–{x2}':>16}{f'{y1}–{y2}':>16}{west:10.4f}{east:10.4f}{south:10.4f}{north:10.4f}")


MODES = {"test": test, "explore": explore, "sousse": sousse, "world": world, "tile": tile, "mosaic": mosaic,
         "corner": corner, "coverage": coverage, "guard": guard}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in MODES:
        print(__doc__)
        sys.exit(1)
    mode, rest = sys.argv[1], sys.argv[2:]
    MODES[mode]() if mode == "test" else MODES[mode](rest)
