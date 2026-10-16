"""NAVERA Sim Lite — what the Jetson serves (the simulation itself runs in each student's browser).

  code(name, src)      the NAVERA Lite files the browser flies: the student's own parts ("mine", each replaced by
                       the course's copy when missing or unfinished) or the course's ("course")
  script / save        the student's flight script, kept outside their NAVERA copy (a reset keeps it)
  tile(z, x, y)        OpenStreetMap tiles from the map file; missing low zooms are built from
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
MAPS = [(config.OSM_MAP, 19)]      # OpenStreetMap only (licence): © OpenStreetMap contributors
CACHE = os.path.join(config.ACADEMY, "state", "tilecache")
_db = threading.local()


# ---------------------------------------------------------------- the code the browser flies: NAVERA Lite
# Sim Lite flies the student's own NAVERA Lite (owner decisions 2026-10-15): it ALWAYS opens and flies for every
# student, but never ships a later mission's solution to the browser. For each part:
#   1. the student's own copy (from the lesson folder where they write it) if it compiles, has no TODO stub left,
#      and every course part it imports may be sent;
#   2. else the course's FINISHED copy, only if the student has PASSED the missions whose TODOs it holds
#      (staff and students given NAVERA access: always);
#   3. else a simple teaching stand-in (server/simlite_standins: arbiter v0's naive judge, mission 09's position
#      contract, a pass-through instead of the Kalman filter), or nothing (no spoofing guard).
COURSE_FILES = ("31-simulator", "files")             # the course's copies: finished up to mission 30, 31 = starter
STANDINS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simlite_standins", "navera_lite")
# part → (missions whose TODOs it holds, course parts it imports, where the student writes it, stand-in?)
PARTS = {
    "geo.py": (("06-coordinates",), (), None, False),
    "estimate.py": (("12-position-message",), ("geo.py",), None, True),
    "guard.py": ((), ("geo.py",), None, False),
    "uncertainty.py": (("27-uncertainty",), ("estimate.py",), None, False),
    "arbiter.py": (("29-arbiter",), ("estimate.py", "geo.py", "guard.py"), "29-arbiter", True),
    "spoof.py": (("30-spoofing",), ("estimate.py", "geo.py", "guard.py", "uncertainty.py"), "30-spoofing", False),
    "kalman.py": (("28-kalman",), ("uncertainty.py",), "28-kalman", True),
}
ALWAYS = ("__init__.py", "output.py", "sim/__init__.py", "sim/sensors.py", "sim/world.py")   # given or stubs only
STUB_MARKS = ("# TODO: replace this line with your code", "# TODO: write your code above", 'NotImplementedError("TODO')
YAML_FROM = ("33-final-project", "31-simulator", "30-spoofing", "29-arbiter")


def _course_dir():
    return os.path.join(config.COURSES, *COURSE_FILES)


def _read(path):
    if os.path.getsize(path) > MAX_FILE:
        raise ValueError("too big")
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _mine(name, lesson, part, needs_done=True):
    """The student's own copy of a part, or (None, why)."""
    path = os.path.join(workspaces.lesson_dir(name, lesson), "navera_lite", part)
    rel = f"lessons/{lesson}/navera_lite/{part}"
    if not os.path.isfile(path):
        return None, f"{rel} not found"
    try:
        text = _read(path)
    except (OSError, ValueError) as e:
        return None, f"{rel} cannot be read ({e})"
    try:
        compile(text, rel, "exec")
    except SyntaxError as e:
        return None, f"{rel} line {e.lineno}: {e.msg}"
    if needs_done and any(m in text for m in STUB_MARKS):
        return None, f"{rel} still has TODO stubs"
    return text, rel


def _function_text(text, fn):
    """The source of a top-level function in a file's text ('' if absent)."""
    i = text.find(f"\ndef {fn}(")
    if i < 0:
        return ""
    j = text.find("\ndef ", i + 1)
    k = text.find("\n# @part", i + 1)
    ends = [x for x in (j, k) if x > 0]
    return text[i:min(ends)] if ends else text[i:]


def _decoder_written(text):
    """True when parse_frames and decode_gps_input (mission 31 TODOs 1–2) hold no stub marker."""
    return all(_function_text(text, fn) and not any(m in _function_text(text, fn) for m in STUB_MARKS)
               for fn in ("parse_frames", "decode_gps_input"))


def code(name, src="mine", passed=(), full=False):
    """{"origin", "files": {"navera_lite/<part>": text, "navera_lite.yaml": text}, "parts": {part: where it comes
    from and why}, "profile": my_vision_profile.json or None, "missing": []}. Never fails for a student.
    passed: the mission ids the student has passed; full: may receive every course part (staff, NAVERA access)."""
    passed = set(passed)
    course = full and src == "course"
    own = src == "mine"                                # "safe": never the student's files (after an error)
    allowed = {}                                       # part → the course's finished copy may be sent

    def ok(part):
        if part not in allowed:
            todo, deps, _, _ = PARTS[part]
            allowed[part] = (full or all(m in passed for m in todo)) and all(ok(d) for d in deps)
        return allowed[part]

    base = os.path.join(_course_dir(), "navera_lite")
    files, parts, missing = {}, {}, []

    def put(part, path):
        try:
            files["navera_lite/" + part] = _read(path)
            return True
        except (OSError, ValueError):
            missing.append(part)
            return False

    for part in ALWAYS:
        if part == "output.py" and own:
            text, why = _mine(name, "31-simulator", part, needs_done=False)
            if text is not None:
                files["navera_lite/" + part] = text
                parts["output"] = (f"yours ({why})" if _decoder_written(text) else
                                   f"the course's starter ({why}: your decoder is not written yet: direct link)")
                continue
            parts["output"] = "the course's starter (encoder given; your decoder is not written: direct link)"
        put(part, os.path.join(base, part))
    chosen = {}
    for part in ("arbiter.py", "spoof.py", "kalman.py"):          # the student's parts first
        todo, deps, lesson, standin = PARTS[part]
        label, why = part[:-3], ""
        if own and lesson:
            text, why = _mine(name, lesson, part)
            if text is not None and all(ok(d) for d in deps):
                files["navera_lite/" + part] = text
                chosen[part] = "yours"
                parts[label] = f"yours ({why})"
                continue
            if text is not None:
                why = f"{why}: it needs course parts of missions you have not passed yet"
        if ok(part):
            chosen[part] = "course"
            parts[label] = "the course's finished part" + (f" ({why})" if why else "")
        elif standin:
            chosen[part] = "standin"
            parts[label] = {"arbiter": "stand-in: arbiter v0's naive rules (mission 29 not passed yet)",
                            "kalman": "stand-in: no filter, positions passed through (mission 28 not passed yet)"}[label] \
                + (f" — {why}" if why else "")
        else:
            chosen[part] = "none"
            parts[label] = "none: no spoofing guard (mission 30 not passed yet)" + (f" — {why}" if why else "")
    # the course parts they import: finished when allowed, else the stand-in position contract
    need = {"estimate.py"}                                          # the world itself uses the Estimate
    todo = [p for p, how in chosen.items() if how in ("yours", "course")]
    while todo:
        for d in PARTS[todo.pop()][1]:
            if d not in need:
                need.add(d)
                todo.append(d)                                         # the world itself uses the Estimate
    for part in sorted(need):
        if ok(part):
            put(part, os.path.join(base, part))
        elif PARTS[part][3]:
            put(part, os.path.join(STANDINS, part))
    for part, how in chosen.items():
        if how == "course":
            put(part, os.path.join(base, part))
        elif how == "standin":
            put(part, os.path.join(STANDINS, part))
    if not ok("estimate.py"):
        parts["estimate"] = "stand-in: mission 09's position contract (mission 12 not passed yet)"
    yaml_text, yaml_from = None, "the course's"
    if own:
        for lesson in YAML_FROM:
            p = os.path.join(workspaces.lesson_dir(name, lesson), "navera_lite.yaml")
            if os.path.isfile(p):
                try:
                    yaml_text = _read(p)
                except (OSError, ValueError):
                    continue
                try:
                    same = yaml_text == _read(os.path.join(config.COURSES, lesson, "files", "navera_lite.yaml"))
                except (OSError, ValueError):
                    same = False
                yaml_from = (f"the course's (lessons/{lesson}/navera_lite.yaml, unchanged)" if same
                             else f"yours (lessons/{lesson}/navera_lite.yaml)")
                break
    if yaml_text is None:
        try:
            yaml_text = _read(os.path.join(_course_dir(), "navera_lite.yaml"))
        except (OSError, ValueError):
            yaml_text = ""
    files["navera_lite.yaml"] = yaml_text
    parts["settings"] = yaml_from
    profile = None
    if own:
        p = os.path.join(workspaces.lesson_dir(name, "31-simulator"), "my_vision_profile.json")
        try:
            prof = json.loads(_read(p))
            if isinstance(prof, dict) and all(isinstance(prof.get(k), dict) and "sigma_m" in prof[k]
                                              for k in ("day", "night")):
                profile = {k: {"sigma_m": float(prof[k]["sigma_m"]), "stated_sigma_m": prof[k].get("stated_sigma_m"),
                               "fail": float(prof[k].get("fail", 0.0))} for k in ("day", "night")}
        except (OSError, ValueError, TypeError):
            pass
    parts["vision profile"] = ("yours (lessons/31-simulator/my_vision_profile.json)" if profile
                               else "none yet (mission 31, lab Step 11): 'My networks' flies the target profile")
    return {"origin": "course" if course else src, "files": files, "parts": parts, "profile": profile,
            "missing": missing, "full": bool(full)}


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


# ---------------------------------------------------------------- lesson files (mission 31: scenario in, flight out)
import json
import re

_NAME = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _lesson(name, lesson_id):
    if not lesson_id or "/" in lesson_id or lesson_id.startswith(".") \
            or not os.path.isdir(os.path.join(config.COURSES, lesson_id)):
        raise ValueError("unknown lesson")
    return workspaces.lesson_dir(name, lesson_id)


FAULTS = {"gps": ("ok", "jammed", "off", "spoof_jump", "spoof_drift"), "camera": ("ok", "blackout", "late", "delayed"),
          "imu": ("ok", "bias", "off"), "light": ("day", "night")}       # = navera_lite/sim/world.py FAULTS (mission 31)
VEHICLES = ("drone", "plane", "boat", "robot")


def scenario(name, lesson_id):
    """my_scenario.json, checked like navera_lite/sim/run.py checks it: every mistake is reported, nothing is guessed."""
    with open(os.path.join(_lesson(name, lesson_id), "my_scenario.json")) as f:
        sc = json.load(f)
    if not isinstance(sc, dict):
        raise ValueError('the file must be one object: {"name": …, "vision": …, "faults": […], "duration_s": …}')
    nm = sc.get("name", "")
    if not isinstance(nm, str) or not _NAME.match(nm):
        raise ValueError('"name" must be a text of letters, digits, - and _, for example "my_run"')
    if sc.get("vision", "target") not in ("target", "measured", "mine", "profile"):
        raise ValueError(f'"vision" must be "target", "measured", "mine" or "profile", not {sc.get("vision")!r}')
    if sc.get("vehicle", "drone") not in VEHICLES:
        raise ValueError(f'"vehicle" must be one of {", ".join(VEHICLES)}')
    if sc.get("light", "day") not in FAULTS["light"]:
        raise ValueError('"light" must be "day" or "night"')
    faults = sc.get("faults", [])
    if not isinstance(faults, list):
        raise ValueError('"faults" must be a list like [[30, "gps", "jammed"], [70, "gps", "ok"]]')
    for f in faults:
        if (not isinstance(f, list) or len(f) != 3 or not isinstance(f[0], (int, float)) or isinstance(f[0], bool)
                or f[0] < 0 or f[1] not in FAULTS or f[2] not in FAULTS[f[1]]):
            raise ValueError(f"fault {json.dumps(f)}: use [seconds ≥ 0, sensor, mode] with "
                             + "; ".join(f"{k}: {'|'.join(v)}" for k, v in FAULTS.items()))
    d = sc.get("duration_s", 120)
    if not isinstance(d, (int, float)) or isinstance(d, bool) or not 0 < d <= 600:
        raise ValueError('"duration_s" must be a number of seconds, 0 < duration ≤ 600')
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
        return None          # an incomplete square would paint dark holes over the map underneath
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
