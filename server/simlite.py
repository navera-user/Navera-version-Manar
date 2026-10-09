"""NAVERA Sim Lite — what the Jetson serves (the simulation itself runs in each student's browser).

  code(name, src)      the student's NAVERA files the browser runs: navera_common, the estimator,
                       navera_msgs/*.msg — from their own copy ("mine") or the base ("original")
  script / save        the student's flight script, kept outside their NAVERA copy (a reset keeps it)
  tile(z, x, y)        satellite map tiles from the map file; missing low zooms are built from
                       the zoom-17 tiles once and cached
"""
import glob
import io
import os
import sqlite3
import threading

import config
import workspaces

MAX_FILE = 400_000
MAPS = [("~/navera_data_map.mbtiles", 19), ("~/.navera_sim/world_tiles.mbtiles", 17),
        (os.path.join(config.ACADEMY, "datasets", "07-map-tiles", "sousse_small.mbtiles"), 19)]
CACHE = os.path.join(config.ACADEMY, "state", "tilecache")
_db = threading.local()


def _root(name, src, allow_original):
    if src == "mine":
        nav = os.path.join(workspaces.student_home(name), "navera")
        if os.path.isdir(nav):
            return nav, "mine"
    if not allow_original:          # students only ever fly their own copy, never the original's code
        raise FileNotFoundError("your NAVERA copy is missing — press ♻️ Reset my NAVERA copy in the user menu")
    return config.BASE, "original"


def code(name, src, allow_original=False):
    root, origin = _root(name, src, allow_original)
    files = {}
    for f in sorted(glob.glob(os.path.join(root, "navera_common", "navera_common", "*.py"))):
        files["navera_common/" + os.path.basename(f)] = f
    files["navera_estimator/nodes/estimator_node.py"] = os.path.join(
        root, "navera_estimator", "navera_estimator", "nodes", "estimator_node.py")
    for f in sorted(glob.glob(os.path.join(root, "navera_msgs", "msg", "*.msg"))):
        files["navera_msgs/msg/" + os.path.basename(f)] = f
    out, missing = {}, []
    for rel, path in files.items():
        try:
            if os.path.getsize(path) > MAX_FILE:
                missing.append(rel + " (too big)")
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                out[rel] = fh.read()
        except OSError:
            missing.append(rel)
    return {"origin": origin, "files": out, "missing": missing}


DEFAULT_SCRIPT = '''# Your flight script — runs in your browser with the simulation.
# sim.goto(place, speed=…), sim.jam_gps(), sim.spoof_gps("jump"|"drift"), sim.restore_gps(),
# sim.camera_fail(), sim.night(), sim.set_speed(m/s), sim.log(text)
# Read: sim.t, sim.truth, sim.navera.source / .state / .error_m / .position
#   (before NAVERA's first position: .position is None and .error_m is inf)

def on_start(sim):
    sim.log("flying the route set in the Flight tab")
    # sim.goto("Monastir", speed=15)   # or send the vehicle somewhere else from your script

warned = False

def on_tick(sim, t):
    global warned
    if t == 60:
        sim.jam_gps()                 # what does NAVERA do without GPS?
    if sim.navera.position is None:   # no position from NAVERA yet: nothing to judge
        return
    if sim.navera.error_m > 400 and not warned:
        sim.log(f"error above 400 m at T+{t} s, source: {sim.navera.source}")
        warned = True
'''


# the default before 2026-10-09: it logged "error above 400 m" at T+0.1 s (no position yet = error inf)
_OLD_DEFAULT = DEFAULT_SCRIPT.replace(
    "#   (before NAVERA's first position: .position is None and .error_m is inf)\n", "").replace(
    "    if sim.navera.position is None:   # no position from NAVERA yet: nothing to judge\n        return\n", "")


def _script_path(name):
    return os.path.join(config.STUDENTS, name, "simlite", "flight.py")


def _request_data():
    """GET args / JSON body of the current request (the routes in app.py only pass the user name)."""
    try:
        from flask import has_request_context, request
        if has_request_context():
            return request.args, (request.get_json(silent=True) or {})
    except ImportError:
        pass
    return {}, {}


def _current(name):
    try:
        with open(_script_path(name)) as f:
            text = f.read()
    except OSError:
        return DEFAULT_SCRIPT
    return DEFAULT_SCRIPT if text == _OLD_DEFAULT else text     # the old default, never edited: the fixed one


def script(name):
    """The student's flight script; ?default=1 gives the default one (the "Restore default" button)."""
    args, _ = _request_data()
    if str(args.get("default", "")) == "1":
        return DEFAULT_SCRIPT
    return _current(name)


CONFLICT = "this flight script was changed in another tab or window since you opened it"


def save_script(name, text, base=None, force=None):
    """Saved only if the file is still the one the page loaded (`base` in the request body): two tabs
    must not silently overwrite each other. `force` (after the student confirmed) saves anyway."""
    if len(text) > MAX_FILE:
        raise ValueError(f"the script is too long ({len(text) // 1000} kB, the limit is {MAX_FILE // 1000} kB): nothing was saved")
    _, body = _request_data()
    base = body.get("base") if base is None else base
    force = bool(body.get("force")) if force is None else force
    if isinstance(base, str) and not force:
        now = _current(name)
        if now != base and now != text:
            raise ValueError(CONFLICT + ": nothing was saved")
    p = _script_path(name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w") as f:
        f.write(text[:MAX_FILE])
    os.replace(tmp, p)


# ---------------------------------------------------------------- lesson files (mission 28: scenario in, flight out)
import json
import re

_NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _lesson(name, lesson_id):
    if not lesson_id or "/" in lesson_id or lesson_id.startswith(".") \
            or not os.path.isdir(os.path.join(config.COURSES, lesson_id)):
        raise ValueError("unknown lesson")
    return workspaces.lesson_dir(name, lesson_id)


FAULTS = {"gps": ("ok", "jammed", "spoof_jump", "spoof_drift", "off"), "camera": ("ok", "failed")}


def scenario(name, lesson_id):
    """my_scenario.json, checked like sim_ctl.py checks it: every mistake is reported, nothing is guessed."""
    with open(os.path.join(_lesson(name, lesson_id), "my_scenario.json")) as f:
        sc = json.load(f)
    if not isinstance(sc, dict):
        raise ValueError('the file must be one object: {"name": …, "vision": …, "faults": […], "tail_s": …}')
    if not isinstance(sc.get("name", "my_run"), str) or not sc.get("name", "my_run").strip():
        raise ValueError('"name" must be a text, for example "my_run"')
    if sc.get("vision", "target") not in ("target", "measured"):
        raise ValueError(f'"vision" must be "target" or "measured", not {sc.get("vision")!r}')
    faults = sc.get("faults", [])
    if not isinstance(faults, list):
        raise ValueError('"faults" must be a list like [[30, "gps", "jammed"], [70, "gps", "ok"]]')
    for f in faults:
        if (not isinstance(f, list) or len(f) != 3 or not isinstance(f[0], (int, float)) or isinstance(f[0], bool)
                or f[0] < 0 or f[1] not in FAULTS or f[2] not in FAULTS[f[1]]):
            raise ValueError(f'fault {json.dumps(f)}: use [seconds, "gps", "ok|jammed|spoof_jump|spoof_drift|off"] '
                             'or [seconds, "camera", "ok|failed"]')
    tail = sc.get("tail_s", 40)
    if not isinstance(tail, (int, float)) or isinstance(tail, bool) or tail < 0:
        raise ValueError('"tail_s" must be a number of seconds')
    return sc


def save_flight(name, lesson_id, run, csv_text, events_text):
    """my_runs/<run>.csv (+ _events.log) in the student's lesson folder: what sim_ctl.py writes."""
    if not _NAME.match(run or ""):
        raise ValueError("the run name may use letters, digits, - and _ only")
    d = os.path.join(_lesson(name, lesson_id), "my_runs")
    os.makedirs(d, exist_ok=True)
    for fn, text in ((f"{run}.csv", csv_text), (f"{run}_events.log", events_text)):
        tmp = os.path.join(d, fn + ".tmp")
        with open(tmp, "w") as f:
            f.write(text[:5_000_000])
        os.replace(tmp, os.path.join(d, fn))
    return f"my_runs/{run}.csv"


# ---------------------------------------------------------------- map tiles
def maps():
    """Every map file present, best first: each tile is taken from the first one that has it."""
    out = []
    for path, native in MAPS:
        p = os.path.realpath(os.path.expanduser(path))
        if os.path.exists(p):
            out.append((p, native))
    return out


_bounds_cache = {}
CELL_SHIFT = 4          # coverage cells: 16 x 16 tiles of the deepest zoom (zoom 13 for a zoom-17 map, ~4 km)


def _tile_lat(z, ty):
    """Latitude of the top edge of XYZ tile row ty."""
    import math
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / 2 ** z))))


def _file_boxes(path):
    """Where one map file has imagery, as [south, west, north, east] boxes. A file that states its
    bounds (a prepared map of one region) is one box; a file of scattered tiles (downloaded along
    flights) is described cell by cell — one box around them would cover half of Europe and make
    the page ask the Jetson for thousands of tiles that do not exist."""
    c = _conn(path)
    meta = dict(c.execute("SELECT name, value FROM metadata").fetchall())
    if meta.get("bounds"):
        w, s_, e, n = (float(v) for v in meta["bounds"].split(","))
        return [[s_, w, n, e]]
    (z,) = c.execute("SELECT MAX(zoom_level) FROM tiles").fetchone()
    if z is None:
        return []
    sh = min(CELL_SHIFT, z)
    cz = z - sh
    rows = {}
    for cx, cr in c.execute(f"SELECT DISTINCT tile_column >> {sh}, tile_row >> {sh} FROM tiles WHERE zoom_level=?", (z,)):
        rows.setdefault((1 << cz) - 1 - cr, []).append(cx)         # TMS row -> XYZ row
    out = []
    for cy, xs in rows.items():                                  # a run of neighbouring cells = one box
        xs.sort()
        start = prev = xs[0]
        for x in xs[1:] + [None]:
            if x is not None and x == prev + 1:
                prev = x
                continue
            out.append([round(_tile_lat(cz, cy + 1), 5), round(start / 2 ** cz * 360 - 180, 5),
                        round(_tile_lat(cz, cy), 5), round((prev + 1) / 2 ** cz * 360 - 180, 5)])
            if x is not None:
                start = prev = x
    return out


def bounds():
    """[south, west, north, east] boxes where the map files have imagery. The page asks the Jetson for
    tiles inside them only (elsewhere the online imagery is enough), and Sim Lite's day vision works
    inside them only: real NAVERA day vision needs this prepared onboard map."""
    out = []
    for path, _ in maps():
        if path not in _bounds_cache:
            try:
                _bounds_cache[path] = _file_boxes(path)
            except Exception:
                _bounds_cache[path] = []
        out.extend(_bounds_cache[path])
    return out


def map_file():
    m = maps()
    return (m[0][0], max(n for _, n in m)) if m else (None, 0)


def _conn(path):
    conns = getattr(_db, "conns", None)
    if conns is None:
        conns = _db.conns = {}
    if path not in conns:
        conns[path] = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    return conns[path]


def _raw(path, z, x, y):
    row = (1 << z) - 1 - y                       # MBTiles rows are TMS (y flipped)
    r = _conn(path).execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                            (z, x, row)).fetchone()
    return r[0] if r else None


def _compose(z, x, y, depth):
    """A tile built from its four children (for zooms the map file does not hold)."""
    from PIL import Image
    kids = [(dx, dy, tile(z + 1, 2 * x + dx, 2 * y + dy, depth - 1)) for dx in (0, 1) for dy in (0, 1)]
    if not all(k[2] for k in kids):
        return None          # an incomplete square would paint dark holes over the satellite imagery underneath
    canvas = Image.new("RGB", (512, 512), (18, 40, 66))
    for dx, dy, data in kids:
        if data:
            canvas.paste(Image.open(io.BytesIO(data)).convert("RGB").resize((256, 256)), (dx * 256, dy * 256))
    buf = io.BytesIO()
    canvas.resize((256, 256), Image.LANCZOS).save(buf, "JPEG", quality=82)
    return buf.getvalue()


_buildable = {}


def _can_build(files, z, x, y, depth):
    """Cheap (index-only) check before building a tile from its children: some map file must hold ALL
    the tiles under it at one deeper zoom. Most squares outside the map's area fail here at once,
    instead of each being built (and found incomplete) on the Jetson."""
    key = (z, x, y, depth)
    if key in _buildable:
        return _buildable[key]
    ok = False
    for path, native in files:
        for k in range(1, depth + 1):
            zz = z + k
            if zz > native:
                break
            n = 1 << k
            r0 = (1 << zz) - (y + 1) * n                          # TMS rows of the square
            got = _conn(path).execute(
                "SELECT COUNT(*) FROM tiles WHERE zoom_level=? AND tile_column BETWEEN ? AND ? AND tile_row BETWEEN ? AND ?",
                (zz, x * n, x * n + n - 1, r0, r0 + n - 1)).fetchone()[0]
            if got >= n * n:
                ok = True
                break
        if ok:
            break
    if len(_buildable) > 200_000:
        _buildable.clear()
    _buildable[key] = ok
    return ok


def tile(z, x, y, depth=4):
    files = maps()
    if not files or not (0 <= z <= 19) or not (0 <= x < (1 << z)) or not (0 <= y < (1 << z)):
        return None
    for path, _ in files:
        data = _raw(path, z, x, y)
        if data:
            return data
    if depth <= 0 or z >= max(n for _, n in files):
        return None
    key = "+".join(os.path.basename(p) for p, _ in files)
    c = os.path.join(CACHE, key, str(z), str(x), f"{y}.jpg")
    if os.path.exists(c):
        with open(c, "rb") as f:
            return f.read() or None
    if not _can_build(files, z, x, y, depth):
        return None                              # nothing to build here (remembered in memory, nothing written)
    data = _compose(z, x, y, depth)
    os.makedirs(os.path.dirname(c), exist_ok=True)
    with open(c, "wb") as f:
        f.write(data or b"")
    return data
