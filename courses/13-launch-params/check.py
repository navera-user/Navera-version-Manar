import contextlib
import io
import json
import math
import re
import time

import yaml

from academy_check import (Background, CheckFailed, Checker, explained, is_stub, load_student, need, predicted,
                           publishers_ok, run, sh, topic_publishers, wait_for_messages)

c = Checker()

# ---------------------------------------------------------------- expected values (course reference, 2026-10-13)
VEHICLES = {"drone": 30.0, "plane": 100.0, "boat": 20.0, "robot": 10.0}
LIMITS = {"rate_hz": (0.1, 50.0), "speed_mps": (0.0, 100.0), "heading_deg": (0.0, 360.0), "sigma_m": (0.0, 1000.0)}
# check_settings on unseen settings: the key that starts each expected sentence, in order
SETTINGS_CASES = [
    ({}, []),
    ({"vehicle": "robot", "max_speed_mps": 10.0}, []),
    ({"vehicle": "plane", "max_speed_mps": 99.5}, ["max_speed_mps"]),
    ({"tick_hz": 0.0, "day_timeout_s": -1.0}, ["day_timeout_s", "tick_hz"]),
    ({"fix_max_sigma_m": 0.005}, ["fix_max_sigma_m"]),
    ({"min_stated_sigma_m": -0.1}, ["min_stated_sigma_m"]),
    ({"celestial_timeout_s": 45, "gps_jump_margin_m": True}, ["celestial_timeout_s", "gps_jump_margin_m"]),
    ({"vehicle": "car", "max_speed_mps": 5.0}, ["vehicle"]),
    ({"vehicle": "boat", "max_speed_mps": "fast"}, ["max_speed_mps"]),
    ({"min_stated_sigma_m": -0.1, "fix_max_sigma_m": -0.2}, ["min_stated_sigma_m", "fix_max_sigma_m"]),
    ({"night_timeout_s": 0, "vehicle": "boat", "max_speed_mps": 12.0, "fix_max_sigma_m": 0.01},
     ["night_timeout_s", "night_timeout_s", "fix_max_sigma_m", "max_speed_mps"]),
]
N_INTEGRATOR = 4
PRECEDENCE = {"SPEED_DEFAULT": 10.0, "SPEED_FILE": 18.0, "SPEED_FILE_THEN_P": 18.0, "SPEED_P_THEN_FILE": 18.0,
              "SPEED_TWO_FILES": 25.0, "SPEED_F": 30.0}
MY_GPS = {"/**": {"rate_hz": 1.0, "sigma_m": 3.0},
          "/drone/fake_gps": {"vehicle": "drone", "speed_mps": 18.0, "heading_deg": 90.0},
          "/boat/fake_gps": {"vehicle": "boat", "speed_mps": 6.0, "heading_deg": 45.0, "start_lat": 35.78,
                             "start_lon": 10.86}}
START = (35.8256, 10.6084)
MARK = "CHK13JSON "

# ---------------------------------------------------------------- scripts run in the STUDENT's process (sh):
# they only report what the student's code does; every comparison is made here.
NODE_SCRIPT = r'''
import json, sys
import rclpy
from rclpy.parameter import Parameter
plan = json.loads(sys.argv[1])
res = []
for sc in plan:
    out = {"ops": []}
    rclpy.init(args=["--ros-args"] + sc["args"])
    node = None
    try:
        from navera_lite.ros import gps_node as g
        node = g.CheckedGps()
        out["started"] = True
    except Exception as e:
        out["started"] = False
        out["error"] = f"{type(e).__name__}: {e}"
    if node is not None:
        for op in sc["ops"]:
            try:
                if op[0] == "get":
                    out["ops"].append(node.get_parameter(op[1]).value)
                elif op[0] == "describe":
                    d = node.describe_parameter(op[1])
                    out["ops"].append({"read_only": d.read_only, "description": d.description,
                                       "range": [[r.from_value, r.to_value] for r in d.floating_point_range]})
                else:
                    ps = [Parameter(n, value=v) for n, v in op[1]]
                    r = node.set_parameters_atomically(ps)
                    out["ops"].append({"ok": bool(r.successful), "reason": r.reason})
            except Exception as e:
                out["ops"].append({"error": f"{type(e).__name__}: {e}"})
        node.destroy_node()
    rclpy.shutdown()
    res.append(out)
print("CHK13JSON " + json.dumps(res))
'''

LAUNCH_SCRIPT = r'''
import json, sys
from launch import LaunchContext, LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch.utilities import perform_substitutions
from navera_lite.ros.navera_lite_launch import generate_launch_description
res = []
for args in json.loads(sys.argv[1]):
    out = {"declared": [], "procs": [], "other": []}
    try:
        ld = generate_launch_description()
        if not isinstance(ld, LaunchDescription):
            out["error"] = f"generate_launch_description() returned {ld!r}, not a LaunchDescription"
            res.append(out)
            continue
        ctx = LaunchContext()
        for e in ld.entities:
            if isinstance(e, DeclareLaunchArgument):
                out["declared"].append(e.name)
                d = perform_substitutions(ctx, e.default_value) if e.default_value is not None else None
                ctx.launch_configurations[e.name] = args.get(e.name, d)
        for e in ld.entities:
            if isinstance(e, DeclareLaunchArgument):
                continue
            if not isinstance(e, ExecuteProcess):
                out["other"].append(type(e).__name__)
                continue
            started = e.condition is None or e.condition.evaluate(ctx)
            out["procs"].append({"started": started, "cmd": [perform_substitutions(ctx, p) for p in e.cmd]})
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    res.append(out)
print("CHK13JSON " + json.dumps(res))
'''


def student_json(script, plan, what, timeout=90):
    code, out = sh(f"python3 - {quote(json.dumps(plan))} <<'CHK13PY'\n{script}\nCHK13PY", timeout=timeout)
    for line in out.splitlines():
        if line.startswith(MARK):
            return json.loads(line[len(MARK):])
    last = [l for l in out.strip().splitlines() if l.strip()][-3:]
    raise CheckFailed(f"{what} could not run: " + (" / ".join(last) or f"exit code {code}"))


def quote(s):
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ---------------------------------------------------------------- helpers
def quiet(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def written(mod, *names):
    fns = need(mod, *names)
    for f in fns:
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub)")
    return fns


def answers(*names):
    return need(quiet("answers.py"), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def boolean(v, name):
    if not isinstance(v, bool):
        raise CheckFailed(f"{name} should be True or False (no quotes), got {v!r}")
    return v


def state(v, name, allowed=("FIX", "DEGRADED", "NO_FIX", "STARTING")):
    if not isinstance(v, str) or v.strip().upper().replace(" ", "_") not in allowed:
        raise CheckFailed(f"{name} should be one of {', '.join(allowed)} (in quotes), got {v!r}")
    return v.strip().upper().replace(" ", "_")


def read_yaml(path):
    try:
        with open(path) as f:
            text = f.read()
    except FileNotFoundError:
        raise CheckFailed(f"there is no file {path} in your lesson folder yet")
    if "\t" in text:
        raise CheckFailed(f"{path} contains a TAB: YAML indentation must be spaces")
    try:
        return yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        raise CheckFailed(f"{path} is not valid YAML: {str(e).splitlines()[0]}")


def block(doc, key, path):
    sec = doc.get(key) if isinstance(doc, dict) else None
    if sec is None and isinstance(doc, dict) and key.startswith("/") and key != "/**":
        sec = doc.get(key[1:])               # ROS reads `boat/fake_gps:` as `/boat/fake_gps`
    if not isinstance(sec, dict) or not isinstance(sec.get("ros__parameters"), dict):
        raise CheckFailed(f"{path} has no section `{key}:` with `ros__parameters:` under it")
    return sec["ros__parameters"]


# ================================================================ Session 1 — Guard the knobs
@c.test("TODO 1: make_descriptor() gives the right limits for every parameter",
        hint="The docstring's table: a range for rate_hz, speed_mps, heading_deg and sigma_m only, read_only for "
             "rate_hz only, and a description for all. floating_point_range is a LIST holding one range.")
def _():
    (make,) = written(quiet("navera_lite.ros.gps_node"), "make_descriptor")
    for name, value in (("heading_deg", 90.0), ("sigma_m", 3.0), ("rate_hz", 1.0), ("speed_mps", 10.0),
                        ("start_lat", 35.8256), ("stamp_offset_s", 0.0), ("vehicle", "drone")):
        d = run(make, name, value)
        if type(d).__name__ != "ParameterDescriptor":
            raise CheckFailed(f"make_descriptor({name!r}, …) returned {d!r}, not a ParameterDescriptor")
        c.ok(isinstance(d.description, str) and d.description.strip(), f"make_descriptor({name!r}, …) has no description")
        got = [(r.from_value, r.to_value) for r in d.floating_point_range]
        want = [LIMITS[name]] if name in LIMITS else []
        c.ok(got == want, f"make_descriptor({name!r}, …): floating_point_range is {got}, "
                          + ("but this parameter should have no range" if not want else "not the docstring's limits"))
        c.ok(bool(d.read_only) == (name == "rate_hz"),
             f"make_descriptor({name!r}, …): read_only is {d.read_only}" + (" — only rate_hz is read-only" if d.read_only else ""))


@c.test("TODO 2: CheckedGps declares guarded parameters (the node really refuses impossible values)",
        hint="declare_parameter(name, value, make_descriptor(name, value)) for each entry of DEFAULTS, set self.lat "
             "and self.lon as in FakeGps.declare_all, and register the callback AFTER the loop (lab Step 2 hints).")
def _():
    (cls,) = need(quiet("navera_lite.ros.gps_node"), "CheckedGps")
    if is_stub(cls.declare_all):
        raise CheckFailed("CheckedGps.declare_all() is not written yet (TODO 2)")
    plan = [{"args": ["-r", "__node:=chk13_gps", "-p", "heading_deg:=270.0", "-p", "start_lat:=-33.9"],
             "ops": [["get", "heading_deg"], ["describe", "sigma_m"], ["describe", "rate_hz"],
                     ["set", [["rate_hz", 2.0]]], ["set", [["sigma_m", 1500.0]]], ["set", [["heading_deg", 400.0]]]]},
            {"args": ["-r", "__node:=chk13_gps", "-p", "sigma_m:=2000.0"], "ops": []}]
    r = student_json(NODE_SCRIPT, plan, "your node")
    sc = r[0]
    c.ok(sc["started"], f"CheckedGps did not start: {sc.get('error')}")
    get, d_sigma, d_rate, s_rate, s_sigma, s_head = sc["ops"]
    c.ok(not (isinstance(get, dict) and "error" in get) and get == 270.0,
         f"started with -p heading_deg:=270.0 the node holds {get!r}: does declare_all read the start values?")
    c.ok(isinstance(d_sigma, dict) and d_sigma.get("range") == [list(LIMITS["sigma_m"])],
         f"`ros2 param describe` would show sigma_m as {d_sigma}: the descriptor is not used in declare_parameter")
    c.ok(isinstance(d_rate, dict) and d_rate.get("read_only"), "rate_hz is not declared read-only")
    c.ok(isinstance(s_rate, dict) and s_rate.get("ok") is False, f"setting rate_hz while running gave {s_rate}: it must be refused")
    c.ok(isinstance(s_sigma, dict) and s_sigma.get("ok") is False, "sigma_m 1500.0 was accepted while running")
    c.ok(isinstance(s_head, dict) and s_head.get("ok") is False, "heading_deg 400.0 was accepted while running")
    c.ok(not r[1]["started"], "the node started with -p sigma_m:=2000.0: the range must also act at start")


@c.test("TODO 3: on_set_parameters() refuses a speed the vehicle cannot fly, with new AND current values",
        hint="Lesson §2: new = {p.name: p.value for p in params}; vehicle and speed each = the new value if present, "
             "else self.get_parameter(…).value; unknown vehicle first; return SetParametersResult(successful=…, reason=…).")
def _():
    (cls,) = need(quiet("navera_lite.ros.gps_node"), "CheckedGps")
    for m in ("declare_all", "on_set_parameters"):
        if is_stub(getattr(cls, m)):
            raise CheckFailed(f"CheckedGps.{m}() is not written yet")
    plan = [{"args": ["-r", "__node:=chk13_gps", "-p", "vehicle:=robot", "-p", "speed_mps:=8.0"],
             "ops": [["set", [["speed_mps", 12.0]]], ["set", [["speed_mps", 9.5]]], ["set", [["vehicle", "plane"]]],
                     ["set", [["speed_mps", 95.0]]], ["set", [["vehicle", "boat"]]], ["set", [["vehicle", "tank"]]],
                     ["get", "speed_mps"], ["get", "vehicle"]]},
            {"args": ["-r", "__node:=chk13_gps", "-p", "vehicle:=robot", "-p", "speed_mps:=8.0"],
             "ops": [["set", [["vehicle", "plane"], ["speed_mps", 60.0]]],
                     ["set", [["speed_mps", 15.0], ["vehicle", "robot"]]], ["get", "speed_mps"]]}]
    r = student_json(NODE_SCRIPT, plan, "your node")
    for sc in r:
        c.ok(sc["started"], f"CheckedGps did not start: {sc.get('error')}")
        for o in sc["ops"]:
            if isinstance(o, dict) and "error" in o:
                raise CheckFailed(f"a parameter change crashed inside your callback: {o['error']}")
            if isinstance(o, dict) and "invalid type" in o.get("reason", ""):
                raise CheckFailed("ROS says 'Callback returned an invalid type': return a SetParametersResult")
    a = r[0]["ops"]
    c.ok(a[0]["ok"] is False, "a robot (10 m/s) was allowed speed_mps 12.0")
    c.ok("10" in a[0]["reason"], f"the reason for refusing 12.0 on a robot does not name the limit: {a[0]['reason']!r}")
    c.ok(a[1]["ok"] is True, f"a robot was refused speed_mps 9.5: {a[1]['reason']!r}")
    c.ok(a[2]["ok"] is True and a[3]["ok"] is True, "robot → plane, then 95.0 m/s, was refused: a plane flies 100 m/s")
    c.ok(a[4]["ok"] is False, "changing the vehicle to a boat while the speed is 95.0 was accepted: the CURRENT "
                              "speed matters when only the vehicle changes")
    c.ok(a[5]["ok"] is False, "vehicle 'tank' was accepted: a vehicle that is not in VEHICLES must be refused")
    c.ok(a[6] == 95.0 and a[7] == "plane", f"after the refused changes the node holds {a[7]!r} at {a[6]!r}")
    b = r[1]["ops"]
    c.ok(b[0]["ok"] is True, "vehicle plane AND speed 60.0 in one change was refused: use the NEW vehicle when it is "
                             "in params")
    c.ok(b[1]["ok"] is False and b[2] == 60.0, "speed 15.0 AND vehicle robot in one change was accepted: use the NEW "
                                               "values of both")


@c.test("TODO 4: check_settings() finds every broken rule, in order, on unseen settings",
        hint="One sentence per broken rule, starting with the key, in the docstring's order (types, then > 0, then "
             "the σ pair, then the vehicle and its speed). An int where the default is a float is a problem, a bool "
             "too; a rule that needs a number skips a value that is not one.")
def _():
    s = quiet("navera_lite.settings")
    (check, defaults) = need(s, "check_settings", "DEFAULTS")
    if is_stub(check):
        raise CheckFailed("check_settings() is not written yet (TODO 4)")
    for change, want in SETTINGS_CASES:
        got = run(check, dict(defaults, **change))
        what = f"check_settings(DEFAULTS with {change})" if change else "check_settings(DEFAULTS)"
        if not isinstance(got, list) or not all(isinstance(x, str) for x in got):
            raise CheckFailed(f"{what} returned {got!r}: return a list of sentences (strings)")
        keys = [x.split()[0] if x.split() else "" for x in got]
        if len(got) != len(want):
            raise CheckFailed(f"{what} returned {len(got)} problem(s): {got}" + (
                " — these settings break no rule" if not want else f" — expected sentences about: {want}"))
        c.ok(keys == want, f"{what} returned {got}: expected sentences about {want}, in this order (each sentence "
                           "starts with its key; the docstring numbers the rules)")
        for x in got:
            m = re.search(r"write (\S+)\.0, not", x)
            c.ok(not m or re.fullmatch(r"[+-]?\d+", m.group(1)), f"{what}: {x!r} — 'write ….0' only fits a whole "
                 "number; any other value gets \"must be a float, got …\" (rule 1 of the docstring)")


@c.test("Step 0: the integer trap and the silent `ros2 param set`",
        hint="Lab Step 0: read the reply of `ros2 param set` and the judge's message AFTER it. Lesson §2, 'Read once'.")
def _():
    p, ps, ok, st, ex = answers("PREDICT_INT", "PREDICT_SET", "SET_REPORTED_OK", "STATE_AFTER_SET", "EXPLAIN_SILENT")
    predicted("PREDICT_INT", p)
    predicted("PREDICT_SET", ps)
    c.ok(boolean(ok, "SET_REPORTED_OK") is True, "SET_REPORTED_OK: what did `ros2 param set` print?")
    c.ok(state(st, "STATE_AFTER_SET") == "FIX", "STATE_AFTER_SET is not what the judge said after the set")
    explained("EXPLAIN_SILENT", ex, ([r"once", r"start", r"init", r"restart", r"begin"], "when the judge reads its settings"),
              ([r"stor", r"saved", r"value", r"read", r"use"], "the stored value versus the value it uses"))


@c.test("Steps 2–3: which guard refused what, and the attacker's start",
        hint="Lab Steps 2 and 3: run each command and write what really happened (True / False, and the number "
             "`ros2 param get` prints). Lesson §2 table.")
def _():
    p, r5, s500, s150, b25, att, ex = answers("PREDICT_GUARDS", "RATE_SET_OK", "SPEED_500_OK", "START_150_RUNS",
                                              "BOAT_25_OK", "ATTACK_SPEED", "EXPLAIN_GUARDS")
    predicted("PREDICT_GUARDS", p)
    for name, v in (("RATE_SET_OK", r5), ("SPEED_500_OK", s500), ("START_150_RUNS", s150), ("BOAT_25_OK", b25)):
        c.ok(boolean(v, name) is False, f"{name} is not what your node did")
    c.ok(abs(number(att, "ATTACK_SPEED") - 25.0) < 1e-6, "ATTACK_SPEED is not what `ros2 param get` showed")
    explained("EXPLAIN_GUARDS", ex, ([r"start", r"declar", r"launch", r"begin"], "that the bad value came at start"),
              ([r"callback", r"on_set", r"regist"], "why the callback did not see it"))


@c.test("Step 4: an integrator's settings file, checked",
        hint="`python3 run_lab13.py settings integrator.yaml` with your finished TODO 4.")
def _():
    (n,) = answers("N_INTEGRATOR_PROBLEMS")
    c.ok(number(n, "N_INTEGRATOR_PROBLEMS") == N_INTEGRATOR, "N_INTEGRATOR_PROBLEMS is not what a correct "
                                                             "check_settings finds in integrator.yaml")


# ================================================================ Session 2 — One command
@c.test("Step 5: my_gps.yaml — /** first, then the drone and the boat, all values typed right",
        hint="Lab Step 5: three sections named /**, /drone/fake_gps and /boat/fake_gps (full names, first slash), each "
             "with ros__parameters:; decimals with a dot, text in quotes.")
def _():
    doc = read_yaml("my_gps.yaml")
    keys = list(doc.keys()) if isinstance(doc, dict) else []
    c.ok(keys, "my_gps.yaml has no section yet (lab Step 5)")
    c.ok(keys[:1] == ["/**"], f"the first section of my_gps.yaml is {keys[:1]}: put /** first (lesson §3)")
    c.ok(not ({"fake_gps", "/fake_gps"} & set(keys)), "my_gps.yaml has a section `fake_gps:`: it means /fake_gps, "
                                                     "which matches neither /drone/fake_gps nor /boat/fake_gps")
    for sec, values in MY_GPS.items():
        got = block(doc, sec, "my_gps.yaml")
        for k, v in values.items():
            if k not in got:
                raise CheckFailed(f"my_gps.yaml: `{sec}` has no {k}")
            g = got[k]
            if isinstance(v, float):
                if not isinstance(g, float):
                    raise CheckFailed(f"my_gps.yaml: {sec} {k} is {g!r}, not a decimal number (write {v}, with a dot)")
                c.ok(abs(g - v) < 1e-6, f"my_gps.yaml: {sec} {k} is {g}, not the lab's value")
            else:
                c.ok(g == v, f"my_gps.yaml: {sec} {k} is {g!r}, not the lab's value")
    plan = [{"args": ["-r", "__ns:=/boat", "--params-file", "my_gps.yaml"],
             "ops": [["get", "vehicle"], ["get", "start_lat"], ["get", "speed_mps"]]}]
    r = student_json(NODE_SCRIPT, plan, "the boat with my_gps.yaml")[0]
    c.ok(r["started"], f"the boat did not start with my_gps.yaml: {r.get('error')}")
    c.ok(r["ops"] == ["boat", 35.78, 6.0], f"the node /boat/fake_gps started with my_gps.yaml holds vehicle, start_lat, "
                                         f"speed_mps = {r['ops']}: does a section name match it?")


@c.test("Step 6: precedence, measured",
        hint="Lab Step 6: write the value `ros2 param get` printed for each command. Lesson §3: -p writes the /** row.")
def _():
    vals = answers("PREDICT_PRECEDENCE", *PRECEDENCE, "EXPLAIN_PRECEDENCE")
    predicted("PREDICT_PRECEDENCE", vals[0])
    for (name, want), v in zip(PRECEDENCE.items(), vals[1:-1]):
        c.ok(abs(number(v, name) - want) < 1e-6, f"{name} is not what `ros2 param get` gives for that command")
    explained("EXPLAIN_PRECEDENCE", vals[-1], ([r"/\*\*", r"row", r"wildcard", r"every node", r"section"], "where -p writes"),
              ([r"same", r"overwr", r"replac", r"fast", r"own"], "why fast.yaml won"))


@c.test("TODO 5: the launch file describes two receivers and one judge (checked without starting it)",
        hint="Lab Step 7 and its hints; `python3 run_lab13.py launch …` shows the commands your file builds.")
def _():
    lf = quiet("navera_lite.ros.navera_lite_launch")
    written(lf, "generate_launch_description")
    combos = [{}, {"gps_source": "boat"}, {"use_boat": "false", "gps_source": "boat"}, {"gps_source": "robot"}]
    res = student_json(LAUNCH_SCRIPT, combos, "your launch file")
    for args, r in zip(combos, res):
        if "error" in r:
            raise CheckFailed(f"with {args or 'no arguments'}: {r['error']}")
    c.ok(sorted(res[0]["declared"]) == ["gps_source", "use_boat"],
         f"declared launch arguments: {res[0]['declared']} (expected use_boat and gps_source)")
    c.ok(len(res[0]["procs"]) == 3 and not res[0]["other"],
         f"{len(res[0]['procs'])} process(es) built with fl_node, other actions {res[0]['other']}: expected 3 fl_node")

    def find(r, module, ns):
        for p in r["procs"]:
            cmd = p["cmd"]
            if f"navera_lite.ros.{module}" in cmd and ((f"__ns:=/{ns}" in cmd) if ns else
                                                       not any(x.startswith("__ns:=") for x in cmd)):
                return p
        raise CheckFailed(f"your launch file starts no {module} "
                          + (f"in the namespace /{ns}" if ns else "without a namespace"))

    for ns, params in (("drone", ["vehicle:=drone", "speed_mps:=12.0"]),
                       ("boat", ["vehicle:=boat", "speed_mps:=5.0", "heading_deg:=0.0"])):
        p = find(res[0], "gps_node", ns)
        c.ok("__node:=fake_gps" in p["cmd"], f"the {ns}'s receiver is not named fake_gps")
        for x in params:
            if x not in p["cmd"]:
                name = x.split(":=")[0]
                given = [y for y in p["cmd"] if y.startswith(name + ":=")]
                raise CheckFailed(f"the {ns}'s receiver gets {given or 'no ' + name}, expected {x}"
                                  + (" — write a float (with .0)" if given and "." not in given[0] else ""))
        c.ok(p["started"], f"the {ns}'s receiver does not start with the default arguments")
    judge = find(res[0], "arbiter_v0", None)
    c.ok("__node:=arbiter" in judge["cmd"], "the judge is not named arbiter")
    pf = [judge["cmd"][i + 1] for i, x in enumerate(judge["cmd"][:-1]) if x == "--params-file"]
    for args, r in zip(combos, res):
        src = args.get("gps_source", "drone")
        j = find(r, "arbiter_v0", None)
        c.ok(f"vehicle:={src}" in j["cmd"], f"with {args or 'no arguments'} the judge gets "
             f"{[x for x in j['cmd'] if x.startswith('vehicle:=')] or 'no vehicle'}, expected vehicle:={src} "
             "(the value of gps_source, a substitution in params)")
    c.ok(len(pf) == 1 and pf[0].endswith("/navera_lite.yaml"), f"the judge's params file is {pf}, expected navera_lite.yaml")
    for args, r in zip(combos, res):
        src = args.get("gps_source", "drone")
        j = find(r, "arbiter_v0", None)
        want = f"navera_lite/fix/gps:=/{src}/navera_lite/fix/gps"
        c.ok(want in j["cmd"], f"with {args or 'no arguments'} the judge's remaps are "
                               f"{[x for x in j['cmd'] if ':=' in x and not x.startswith('__')]}, expected {want}")
        boat = find(r, "gps_node", "boat")
        c.ok(boat["started"] == (args.get("use_boat", "true") == "true"),
             f"with {args or 'no arguments'} the boat's receiver " + ("does not start" if not boat["started"] else "still starts"))


@c.test("Step 7 + Step 9: the launch file runs — three nodes, the judge follows the boat, DEGRADED at 2 m",
        hint="Run `jobs` and stop every node of the earlier steps first (`kill -INT $(jobs -p)`). The judge must subscribe to /boat/navera_lite/fix/gps with "
             "gps_source:=boat; navera_lite.yaml must hold fix_max_sigma_m: 2.0 (lab Step 9).")
def _():
    from diagnostic_msgs.msg import DiagnosticStatus
    from sensor_msgs.msg import NavSatFix
    lf = quiet("navera_lite.ros.navera_lite_launch")
    written(lf, "generate_launch_description")
    publishers_ok(expected=0)
    with Background("ros2 launch navera_lite/ros/navera_lite_launch.py gps_source:=boat", settle=3.0) as bg:
        nodes = ""
        for _ in range(4):
            nodes = sh("timeout 15 ros2 node list --no-daemon --spin-time 3", timeout=25)[1]
            if all(n in nodes for n in ("/arbiter", "/boat/fake_gps", "/drone/fake_gps")):
                break
            time.sleep(1.0)
        for n in ("/arbiter", "/boat/fake_gps", "/drone/fake_gps"):
            c.ok(n in nodes.split(), f"`ros2 node list` does not show {n} while your launch runs: {nodes.split()}")
        subs = []
        for _ in range(4):
            info = sh("timeout 15 ros2 topic info -v /boat/navera_lite/fix/gps --no-daemon --spin-time 3", timeout=25)[1]
            subs = re.findall(r"Node name: (\S+)\s*\nNode namespace: (\S+)\s*\nTopic type: \S+\s*\nEndpoint type: "
                              r"SUBSCRIPTION", info)
            if ("arbiter", "/") in subs:
                break
        c.ok(("arbiter", "/") in subs, "with gps_source:=boat the judge does not subscribe to /boat/navera_lite/fix/gps "
                                       f"(subscribers: {subs or 'none'})")
        msgs = []
        end = time.time() + 12
        while time.time() < end:
            msgs += wait_for_messages("/navera_lite/status", DiagnosticStatus, count=1, timeout=3.0)
            if msgs and msgs[-1].message.startswith("gps:"):
                break
        c.ok(msgs, "no message on /navera_lite/status in 12 s")
        last = msgs[-1]
        c.ok(last.message.startswith("gps:"), f"the judge says {last.message!r}: it does not receive the boat's GPS")
        c.ok("> 2.0 m" in last.message and last.level == DiagnosticStatus.WARN,
             f"the judge says {last.message!r}: with fix_max_sigma_m 2.0 in navera_lite.yaml it should be DEGRADED")
        judges = max((topic_publishers("/navera_lite/status")[0] or 0) for _ in range(2))
        c.ok(judges <= 1, f"{judges} nodes publish on /navera_lite/status: a judge from an earlier step still runs — "
                          "run `jobs`, then `kill -INT $(jobs -p)`, and check again")
        pos = wait_for_messages("/navera_lite/position", NavSatFix, count=3, timeout=8.0)
        c.ok(len(pos) >= 2, "the judge published no positions")
        c.ok(all(abs(p.longitude - START[1]) < 1e-6 for p in pos) and pos[-1].latitude > START[0],
             "the judge's positions are not the boat's (north from the start, longitude constant)")
    out = bg.output()
    c.ok("Traceback" not in out, "a process of your launch printed a Python traceback: " + out[out.find("Traceback"):][:300])


@c.test("Step 7: the judge with no boat", hint="Lab Step 7, the last launch: read the level and the message. Lesson §4.")
def _():
    p, st, ex = answers("PREDICT_NO_BOAT", "NO_BOAT_STATE", "EXPLAIN_REMAP")
    predicted("PREDICT_NO_BOAT", p)
    c.ok(state(st, "NO_BOAT_STATE") == "STARTING", "NO_BOAT_STATE is not what the judge showed")
    explained("EXPLAIN_REMAP", ex, ([r"publish", r"nobody", r"no one", r"no node", r"nothing", r"topic"], "why it receives nothing"),
              ([r"crash", r"error", r"silen", r"warn", r"alarm", r"notic"], "why the silence is dangerous"))


@c.test("Step 8: the plane — R-1 reproduced and repaired",
        hint="Lab Step 8: plane.yaml = navera_lite.yaml with vehicle \"plane\" and, at the end, max_speed_mps: 100.0.")
def _():
    doc = read_yaml("plane.yaml")
    b = block(doc, "/**", "plane.yaml")
    c.ok(b.get("vehicle") == "plane", f"plane.yaml: vehicle is {b.get('vehicle')!r}")
    v = b.get("max_speed_mps")
    c.ok(isinstance(v, float) and v >= VEHICLES["plane"], f"plane.yaml: max_speed_mps is {v!r}; a plane needs a float "
                                                           ">= 100.0 (lab Step 8, the repair)")
    p, s30, s100, ex = answers("PREDICT_PLANE", "PLANE_STATE_30", "PLANE_STATE_100", "EXPLAIN_R1")
    predicted("PREDICT_PLANE", p)
    c.ok(state(s30, "PLANE_STATE_30") == "NO_FIX", "PLANE_STATE_30 is not what the judge said after 10 s")
    c.ok(state(s100, "PLANE_STATE_100") == "FIX", "PLANE_STATE_100 is not what the judge said")
    explained("EXPLAIN_R1", ex, ([r"jump", r"gate"], "what refused the fixes"),
              ([r"check_settings", r"start", r"before", r"settings", r"take-?off"], "what would have caught it earlier"))


@c.test("Step 9: one setting changed, and only one",
        hint="Lab Step 9: copy navera_lite.yaml to navera_lite.yaml.orig FIRST, then set fix_max_sigma_m: 2.0 (a float).")
def _():
    new = block(read_yaml("navera_lite.yaml"), "/**", "navera_lite.yaml")
    old = block(read_yaml("navera_lite.yaml.orig"), "/**", "navera_lite.yaml.orig")
    v = new.get("fix_max_sigma_m")
    c.ok(isinstance(v, float) and abs(v - 2.0) < 1e-9, f"navera_lite.yaml: fix_max_sigma_m is {v!r}, expected 2.0")
    c.ok(old.get("fix_max_sigma_m") == 25.0, "navera_lite.yaml.orig is not the original (fix_max_sigma_m 25.0)")
    diff = sorted(k for k in set(new) | set(old) if new.get(k) != old.get(k))
    c.ok(diff == ["fix_max_sigma_m"], f"navera_lite.yaml and its .orig differ in {diff}: only fix_max_sigma_m may change")
    ps, st, msg = answers("PREDICT_SIGMA", "SIGMA_STATE", "SIGMA_MESSAGE")
    predicted("PREDICT_SIGMA", ps)
    c.ok(state(st, "SIGMA_STATE") == "DEGRADED", "SIGMA_STATE is not what the judge said")
    c.ok(isinstance(msg, str) and "3.0" in msg and "2.0" in msg, f"SIGMA_MESSAGE {msg!r} is not the judge's message")


@c.test("Step 10: report.md — three headings, your words and your numbers",
        hint="Keep the headings ## Precedence, ## Guards, ## One setting per vehicle; at least 40 words under each, "
             "with your measured values.")
def _():
    try:
        text = open("report.md").read()
    except FileNotFoundError:
        raise CheckFailed("report.md is missing")
    parts = re.split(r"^##\s+", text, flags=re.M)
    secs = {p.splitlines()[0].strip().lower(): p for p in parts[1:] if p.strip()}
    for h in ("precedence", "guards", "one setting per vehicle"):
        if h not in secs:
            raise CheckFailed(f"report.md has no heading `## {h.capitalize()}`")
        body = re.sub(r"\(.*?\)", " ", secs[h].split("\n", 1)[1] if "\n" in secs[h] else "", flags=re.S)
        n = len(re.findall(r"[A-Za-zÀ-ÿ']{2,}", body))
        c.ok(n >= 40, f"report.md, {h}: {n} words of yours (the brackets of the template do not count), 40 needed")
        c.ok(re.search(r"\d", body), f"report.md, {h}: quote at least one of your measured values")


c.milestone("knob_guard", "TODO 1:", "TODO 2:", "TODO 3:", "TODO 4:", "Step 0:", "Steps 2–3:", "Step 4:",
            label="Knob guard")
c.milestone("integrator", "TODO", "Step", label="Integrator")

c.run()
