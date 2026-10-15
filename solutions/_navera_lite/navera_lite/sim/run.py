"""navera_lite/sim/run.py — fly one scenario headless: the world (sim/world.py) with NAVERA Lite's judge, guard,
messenger and the autopilot's filter, and write my_runs/<name>.csv + my_runs/<name>_events.log (the columns of
world.COLUMNS, one row every 0.2 s of mission time). Part of NAVERA Lite, the course's teaching stack (mission 31).
Written for the course; it is not NAVERA code.

    python3 -m navera_lite.sim.run campaign/jam.json              # the course's parts (this folder's navera_lite)
    python3 -m navera_lite.sim.run campaign/jam.json --mine       # YOUR parts from your earlier lesson folders
    options: --out DIR (default my_runs, or my_runs/mine with --mine)   --quiet (no event list)

--mine flies, each one if you finished it (else the course's, and the run says so): your judge
(../29-arbiter/navera_lite/arbiter.py), your guard (../30-spoofing/navera_lite/spoof.py), your Kalman filter as the
autopilot's (../28-kalman/navera_lite/kalman.py), and with vision "mine" your trained weights
(../21-features/my_desc.pt by day, ../25-thermal-night/my_homography.pt at night). Your mission-31 decoder
(navera_lite/output.py: parse_frames, decode_gps_input) ALWAYS reads the autopilot's link.
"""
import csv
import importlib.util
import inspect
import json
import math
import os
import sys

from navera_lite import output, vehicle
from navera_lite.sim import world as W

# @part 31
DATA = os.environ.get("NAVERA_LITE_SIM_DATA", "/data/academy/31-simulator")
# @part 31
MINE = {"arbiter": os.path.join("..", "29-arbiter", "navera_lite", "arbiter.py"),
        "spoof": os.path.join("..", "30-spoofing", "navera_lite", "spoof.py"),
        "kalman": os.path.join("..", "28-kalman", "navera_lite", "kalman.py"),
        "day weights": os.path.join("..", "21-features", "my_desc.pt"),
        "night weights": os.path.join("..", "25-thermal-night", "my_homography.pt")}
# @part 31
REF_WEIGHTS = {"day weights": "ref_desc.pt", "night weights": "ref_homography.pt"}
# @part 31
STUB_MARKS = ("# TODO: write your code " + "above", "NotImplementedError(" + '"TODO')     # runner_kit's marks


# @part 31
def unfinished(mod, names):
    """The functions/methods of a module that are still TODO stubs (their source holds a stub mark)."""
    out = []
    for name in names:
        obj = mod
        for part in name.split("."):
            obj = getattr(obj, part, None)
        if obj is None:
            out.append(name + " (missing)")
            continue
        try:
            src = inspect.getsource(obj)
        except (OSError, TypeError):
            continue
        if any(m in src for m in STUB_MARKS):
            out.append(name)
    return out


# @part 31
def restore(name, old):
    """Put back the module that was in sys.modules[name] (or none)."""
    if old is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = old


# @part 31
def load_mine(part, path, needs):
    """Your module `part` from another lesson folder, put in sys.modules as navera_lite.<part> — or None and why."""
    if not os.path.exists(path):
        return None, f"{path} not found"
    name = "navera_lite." + part
    keep = sys.modules.get(name)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:                                     # noqa: BLE001 — one plain sentence
        restore(name, keep)
        return None, f"{path} cannot be loaded ({type(e).__name__}: {e})"
    todo = unfinished(mod, needs)
    if todo:
        restore(name, keep)
        return None, f"{path} still has TODO stubs: {', '.join(todo)}"
    return mod, path


# @part 31
def parts(mine, vision_kind):
    """The modules and weights this flight uses, and a report line per part ('yours' / 'course')."""
    import importlib
    report = {}
    mods = {}
    needs = {"arbiter": ["candidates", "track_since", "pick", "Arbiter.receive", "Arbiter.step"],
             "spoof": ["chi2_threshold_2d", "innovation", "SpoofGuard.on_reference", "SpoofGuard.on_gps"],
             "kalman": ["cv_model", "kf_predict", "kf_update"]}
    for part in ("arbiter", "spoof", "kalman"):
        mod, why = (None, "")
        if mine:
            mod, why = load_mine(part, MINE[part], needs[part])
        if mod is None:
            mod = importlib.import_module("navera_lite." + part)
            report[part] = "course" + (f" — {why}" if mine else "")
        else:
            report[part] = f"yours ({why})"
        mods[part] = mod
    weights = {}
    if vision_kind == "mine":
        for key in ("day weights", "night weights"):
            p = MINE[key] if mine and os.path.exists(MINE[key]) else REF_WEIGHTS[key]
            if mine and p == REF_WEIGHTS[key]:
                report[key] = f"course ({MINE[key]} not found)"
            else:
                report[key] = ("yours (" + p + ")") if mine else "course (" + p + ")"
            weights[key] = p
    return mods, weights, report


# @part 31
def corridor():
    """corridor.json of the dataset (its frame and route)."""
    p = os.path.join(DATA, "corridor", "corridor.json")
    try:
        with open(p) as f:
            return json.load(f)
    except OSError:
        sys.exit(f"{p} is missing: the simulator's corridor data is not mounted (tell your teacher)")


# @part 31
def settings_for(sc):
    from navera_lite import settings
    try:
        cfg = settings.load("navera_lite.yaml") if os.path.exists("navera_lite.yaml") else dict(settings.DEFAULTS)
    except (OSError, ValueError) as e:
        sys.exit(f"navera_lite.yaml cannot be read: {e}")
    v = sc.get("vehicle", "drone")
    cfg["vehicle"] = v
    cfg["max_speed_mps"] = float(sc.get("max_speed_mps") or vehicle.VEHICLES.get(v, 30.0))
    return cfg


# @part 31
def reader(out_mod):
    """The autopilot's side of the link, with YOUR parse_frames and decode_gps_input: bytes → decoded GPS_INPUTs
    (only frames whose checksum is right)."""
    def read(data):
        msgs = []
        for fr in out_mod.parse_frames(data) or []:
            if fr.get("msgid") == out_mod.GPS_INPUT_ID and fr.get("crc_ok") is True:
                msgs.append(out_mod.decode_gps_input(fr["payload"]))
        return msgs
    return read


# @part 31
def check_scenario(sc):
    """A scenario (my_scenario.json) checked: every mistake is reported in words, nothing is guessed."""
    if not isinstance(sc, dict):
        raise ValueError('the file must be one object: {"name": …, "vision": …, "faults": […], "duration_s": …}')
    name = sc.get("name", "")
    if not isinstance(name, str) or not name or not all(c.isalnum() or c in "-_" for c in name):
        raise ValueError('"name" must be a text of letters, digits, - and _, for example "my_run"')
    if sc.get("vision", "target") not in ("target", "measured", "mine", "profile"):
        raise ValueError(f'"vision" must be "target", "measured", "mine" or "profile", not {sc.get("vision")!r}')
    if sc.get("vehicle", "drone") not in W.VEHICLES:
        raise ValueError(f'"vehicle" must be one of {sorted(W.VEHICLES)}')
    if sc.get("light", "day") not in W.FAULTS["light"]:
        raise ValueError('"light" must be "day" or "night"')
    faults = sc.get("faults", [])
    if not isinstance(faults, list):
        raise ValueError('"faults" must be a list like [[30, "gps", "jammed"], [70, "gps", "ok"]]')
    for f in faults:
        if (not isinstance(f, list) or len(f) != 3 or isinstance(f[0], bool) or not isinstance(f[0], (int, float))
                or f[0] < 0 or f[1] not in W.FAULTS or f[2] not in W.FAULTS[f[1]]):
            raise ValueError(f"fault {json.dumps(f)}: use [seconds ≥ 0, sensor, mode] with "
                             + "; ".join(f"{k}: {'|'.join(v)}" for k, v in W.FAULTS.items()))
    d = sc.get("duration_s", 120)
    if isinstance(d, bool) or not isinstance(d, (int, float)) or not 0 < d <= 600:
        raise ValueError('"duration_s" must be a number of seconds, 0 < duration ≤ 600')
    return sc


# @part 31
def fly(sc, mine=False, quiet=True, keep_frames=False):
    """Fly one scenario (a dict) and return the World (rows, events, outcome(), parts report in .parts)."""
    check_scenario(sc)
    todo = unfinished(output, ["parse_frames", "decode_gps_input"])
    if todo:
        raise RuntimeError("the autopilot reads the link with YOUR navera_lite/output.py, and "
                           + " and ".join(todo) + " " + ("is" if len(todo) == 1 else "are")
                           + " still a TODO: write TODO 1 and TODO 2 first (lab Steps 1–2)")
    kind = sc.get("vision", "target")
    mods, weights, report = parts(mine, kind)
    cfg = settings_for(sc)
    judge = mods["arbiter"].Arbiter(cfg)
    if sc.get("guard", True):
        judge = mods["spoof"].GuardedArbiter(judge, mods["spoof"].SpoofGuard(cfg))
    else:
        report["spoof"] = "none (guard switched off by the scenario)"
    c = corridor()
    frame = W.LocalFrame(c["centre_lat"], c["centre_lon"])
    route = (tuple(c["route"]["start_en"]), tuple(c["route"]["dest_en"]))
    if kind == "mine":
        from navera_lite.sim.vision import NetworkVision
        stated = {}
        try:
            with open("my_vision_profile.json") as f:
                prof = json.load(f)
            stated = {k: prof[k]["stated_sigma_m"] for k in ("day", "night")
                      if isinstance(prof.get(k), dict) and prof[k].get("stated_sigma_m")}
        except (OSError, ValueError):
            pass
        vision = NetworkVision(DATA, weights["day weights"], weights["night weights"], stated)
        report["stated σ"] = (", ".join(f"{k} {v:g} m" for k, v in stated.items()) + " (my_vision_profile.json)"
                              if stated else "day 15 m, night 25 m (the target profile's: no my_vision_profile.json)")
    elif kind == "profile":
        path = sc.get("vision_profile", "my_vision_profile.json")
        try:
            with open(path) as f:
                prof = json.load(f)
        except (OSError, ValueError) as e:
            raise RuntimeError(f"vision 'profile' reads {path}: {e} (make it with `python3 vision_check.py`)")
        vision = W.ProfileVision("profile", prof)
    else:
        vision = W.ProfileVision(kind)
    w = W.World(sc, judge, output, mods["kalman"], vision, frame, route)
    w.parts = report
    w.run(reader(output))
    if not keep_frames:
        w.sent_frames = []
    return w


# @part 31
def write(w, out_dir):
    """my_runs/<name>.csv and <name>_events.log. Returns the CSV path."""
    os.makedirs(out_dir, exist_ok=True)
    name = w.sc["name"]
    path = os.path.join(out_dir, name + ".csv")
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, W.COLUMNS)
        wr.writeheader()
        wr.writerows(w.rows)
    with open(os.path.join(out_dir, name + "_events.log"), "w") as f:
        f.write(f"# scenario: {json.dumps(w.sc)}\n")
        for k, v in w.parts.items():
            f.write(f"# part {k}: {v}\n")
        for t, m, text in w.events:
            f.write(f"{'' if m is None else f'{m:7.1f}':>7}  {text}\n")
        f.write(f"# outcome: {json.dumps(w.outcome())}\n")
    return path


# @part 31
def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0].startswith("-"):
        sys.exit(__doc__.split("\n\n")[1])
    mine = "--mine" in args
    out_dir = os.path.join("my_runs", "mine") if mine else "my_runs"
    if "--out" in args:
        i = args.index("--out")
        if i + 1 >= len(args):
            sys.exit("--out needs a folder name")
        out_dir = args[i + 1]
    try:
        with open(args[0]) as f:
            sc = json.load(f)
    except OSError:
        sys.exit(f"{args[0]}: no such file")
    except ValueError as e:
        sys.exit(f"{args[0]} is not valid JSON: {e} (look at commas and quotes near that line)")
    try:
        w = fly(sc, mine=mine)
    except (ValueError, RuntimeError) as e:
        sys.exit(f"{args[0]}: {e}")
    except Exception as e:                                       # noqa: BLE001 — one plain sentence, with the place
        import traceback
        frames = traceback.extract_tb(e.__traceback__)
        deep = frames[-1] if frames else None
        where = f" ({os.path.relpath(deep.filename)}, line {deep.lineno}, in {deep.name})" if deep else ""
        sys.exit(f"the flight stopped: {type(e).__name__}: {e}{where} — if that file is one of YOUR parts, fix it "
                 "there (or fly without --mine)")
    path = write(w, out_dir)
    print(f"Scenario {sc['name']} ({w.vehicle}, vision {sc.get('vision', 'target')}, {w.faults['light']}):")
    for k, v in w.parts.items():
        print(f"  {k:14s} {v}")
    if "--quiet" not in args:
        for t, m, text in w.events:
            print(f"  {'' if m is None else f'{m:6.1f} s':>8}  {text}")
    o = w.outcome()
    errs = [float(r["lite_err_m"]) for r in w.rows if r["lite_err_m"]]
    ap = [float(r["ap_err_m"]) for r in w.rows if r["ap_err_m"]]
    print(f"  end at {w.mission_t:.1f} s: autopilot {o['ap_mode']}, {o['miss_m']:.0f} m from the destination; "
          f"largest error NAVERA Lite {max(errs) if errs else math.nan:.0f} m, autopilot "
          f"{max(ap) if ap else math.nan:.0f} m")
    print(f"  wrote {path} and {path[:-4]}_events.log ({len(w.rows)} rows)")


if __name__ == "__main__":
    main()
