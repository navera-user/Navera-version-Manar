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


def _root(name, src):
    if src == "mine":
        nav = os.path.join(workspaces.student_home(name), "navera")
        if os.path.isdir(nav):
            return nav, "mine"
    return config.BASE, "original"


def code(name, src):
    root, origin = _root(name, src)
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

def on_start(sim):
    sim.log("flying the route set in the Flight tab")
    # sim.goto("Monastir", speed=15)   # or send the vehicle somewhere else from your script

warned = False

def on_tick(sim, t):
    global warned
    if t == 60:
        sim.jam_gps()                 # what does NAVERA do without GPS?
    if sim.navera.error_m > 400 and not warned:
        sim.log(f"error above 400 m at T+{t} s, source: {sim.navera.source}")
        warned = True
'''


def _script_path(name):
    return os.path.join(config.STUDENTS, name, "simlite", "flight.py")


def script(name):
    try:
        with open(_script_path(name)) as f:
            return f.read()
    except OSError:
        return DEFAULT_SCRIPT


def save_script(name, text):
    if len(text) > MAX_FILE:
        raise ValueError(f"the script is too long ({len(text) // 1000} kB, the limit is {MAX_FILE // 1000} kB): nothing was saved")
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


def bounds():
    """[south, west, north, east] of each map file (from its metadata, else from its tiles): the page asks
    the Jetson only for tiles inside these; everywhere else the online imagery is enough."""
    import math
    out = []
    for path, _ in maps():
        if path not in _bounds_cache:
            b = None
            try:
                meta = dict(_conn(path).execute("SELECT name, value FROM metadata").fetchall())
                if meta.get("bounds"):
                    w, s_, e, n = (float(v) for v in meta["bounds"].split(","))
                    b = [s_, w, n, e]
                else:
                    z, x0, x1, r0, r1 = _conn(path).execute(
                        "SELECT zoom_level, MIN(tile_column), MAX(tile_column), MIN(tile_row), MAX(tile_row) FROM tiles "
                        "GROUP BY zoom_level ORDER BY zoom_level DESC LIMIT 1").fetchone()
                    lon = lambda x: x / 2 ** z * 360 - 180                                         # noqa: E731
                    lat = lambda r: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (2 ** z - r) / 2 ** z))))  # noqa: E731
                    b = [lat(r0), lon(x0), lat(r1 + 1), lon(x1 + 1)]
            except Exception:
                b = None
            _bounds_cache[path] = b
        if _bounds_cache[path]:
            out.append(_bounds_cache[path])
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
    data = _compose(z, x, y, depth)
    os.makedirs(os.path.dirname(c), exist_ok=True)
    with open(c, "wb") as f:
        f.write(data or b"")
    return data
