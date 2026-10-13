"""run_lab13.py — try your mission-13 code without starting ROS nodes by hand.

    python3 run_lab13.py test                       each TODO on its docstring example
    python3 run_lab13.py settings navera_lite.yaml  check_settings() on a settings file (TODO 4)
    python3 run_lab13.py launch                     what your launch file WOULD start (TODO 5), nothing runs
    python3 run_lab13.py launch use_boat:=false gps_source:=boat      the same, with launch arguments

Written for the course; it is not NAVERA code.
"""
# ---- you don't need to change anything in this file (but you can read it!) ----
import sys

import runner_kit as rk

OK, BAD = "✔", "✘"


def show(ok, text):
    print(f"  {OK if ok else BAD} {text}")
    return ok


# ------------------------------------------------------------------------------------------- TODO 1
def test_descriptor(g):
    print("TODO 1  make_descriptor()")
    d, err = rk.call(g, "make_descriptor", "speed_mps", 10.0)
    if err:
        return show(False, err)
    if type(d).__name__ != "ParameterDescriptor":
        return show(False, f"make_descriptor() must return a ParameterDescriptor, it returned {d!r}")
    r = list(d.floating_point_range)
    good = show(len(r) == 1 and (r[0].from_value, r[0].to_value) == (0.0, 100.0) and not d.read_only,
                f"speed_mps: range {[(x.from_value, x.to_value) for x in r]}, read_only {d.read_only}"
                "   (the docstring's table says what it should be)")
    d, err = rk.call(g, "make_descriptor", "rate_hz", 1.0)
    if err:
        return show(False, err)
    good &= show(bool(d.read_only), f"rate_hz: read_only {d.read_only}")
    d, err = rk.call(g, "make_descriptor", "vehicle", "drone")
    if err:
        return show(False, err)
    good &= show(not d.floating_point_range and not d.read_only and bool(d.description),
                 f"vehicle: range {list(d.floating_point_range)}, read_only {d.read_only}, "
                 f"description {d.description!r}")
    return good


# ------------------------------------------------------------------------------------------ TODO 2-3
def test_node(g):
    print("TODO 2  CheckedGps.declare_all()   and   TODO 3  CheckedGps.on_set_parameters()")
    import rclpy
    from rclpy.parameter import Parameter
    rclpy.init(args=["--ros-args", "-r", "__node:=run_lab13_gps", "-p", "vehicle:=boat"])
    node = None
    try:
        try:
            node = g.CheckedGps()
        except NotImplementedError:
            return show(False, "CheckedGps.declare_all() is not written yet (TODO 2)")
        except Exception as e:
            return show(False, f"the node did not start: {type(e).__name__}: {e} — look at declare_all() "
                               "(TODO 2), and at on_set_parameters() if the error comes from there")
        ok = show(node.get_parameter("vehicle").value == "boat" and node.get_parameter("speed_mps").value == 10.0,
                  f"started: vehicle {node.get_parameter('vehicle').value!r}, speed_mps "
                  f"{node.get_parameter('speed_mps').value}")
        desc = node.describe_parameter("rate_hz")
        ok &= show(bool(desc.read_only), f"rate_hz is declared read-only: {desc.read_only}")
        res = node.set_parameters([Parameter("rate_hz", value=5.0)])[0]
        ok &= show(not res.successful, f"set rate_hz 5.0 → successful={res.successful}")
        for params, want in (([Parameter("speed_mps", value=25.0)], False),
                             ([Parameter("speed_mps", value=15.0)], True),
                             ([Parameter("vehicle", value="car")], False)):
            what = ", ".join(f"{p.name} {p.value!r}" for p in params)
            try:
                r = node.on_set_parameters(params)
            except NotImplementedError:
                return show(False, "on_set_parameters() is not written yet (TODO 3)")
            except Exception as e:
                return show(False, f"on_set_parameters() stopped with {type(e).__name__}: {e} (on: {what})")
            if r is None:
                return show(False, "on_set_parameters() returned None: return a SetParametersResult")
            if type(r).__name__ != "SetParametersResult":
                return show(False, f"on_set_parameters() must return a SetParametersResult, it returned {r!r}")
            ok &= show(r.successful == want, f"boat, current speed 10.0, change {what} → successful={r.successful}"
                                             + (f", reason {r.reason!r}" if r.reason else ""))
        return ok
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


# ------------------------------------------------------------------------------------------- TODO 4
def test_settings(s):
    print("TODO 4  check_settings()")
    p, err = rk.call(s, "check_settings", dict(s.DEFAULTS))
    if err:
        return show(False, err)
    if not isinstance(p, list):
        return show(False, f"check_settings() must return a list of sentences, it returned {p!r}")
    good = show(p == [], f"the default settings → {p}   (they break no rule)")
    p, err = rk.call(s, "check_settings", dict(s.DEFAULTS, gps_timeout_s=3))
    if err:
        return show(False, err)
    good &= show(isinstance(p, list) and len(p) == 1, f"gps_timeout_s=3 (an int) → {p}")
    return good


def settings(path):
    s = rk.load_student("navera_lite.settings")
    try:
        cfg = s.load(path)
    except FileNotFoundError:
        sys.exit(f"there is no file {path} in this folder")
    except ValueError as e:
        sys.exit(f"load() refused the file: {e}")
    except Exception as e:
        sys.exit(f"{path} is not a valid settings file: {type(e).__name__}: {e}")
    p, err = rk.call(s, "check_settings", cfg)
    if err:
        sys.exit(err)
    if not isinstance(p, list):
        sys.exit(f"check_settings() must return a list of sentences, it returned {p!r}")
    print(f"{path}: vehicle {cfg.get('vehicle')!r}, max_speed_mps {cfg.get('max_speed_mps')!r}")
    if not p:
        print("  no problem found")
    for line in p:
        print(f"  ✘ {line}")
    print(f"{len(p)} problem(s)")


# ------------------------------------------------------------------------------------------- TODO 5
def plan(args):
    """[(name, started, command)] of the student's launch file with these launch arguments."""
    from launch import LaunchContext, LaunchDescription
    from launch.actions import DeclareLaunchArgument, ExecuteProcess
    from launch.utilities import perform_substitutions
    lf = rk.load_student("navera_lite.ros.navera_lite_launch")
    ld, err = rk.call(lf, "generate_launch_description")
    if err:
        sys.exit(err)
    if not isinstance(ld, LaunchDescription):
        sys.exit(f"generate_launch_description() must return a LaunchDescription, it returned {ld!r}")
    ctx = LaunchContext()
    declared = []
    for e in ld.entities:
        if isinstance(e, DeclareLaunchArgument):
            declared.append(e.name)
            default = perform_substitutions(ctx, e.default_value) if e.default_value is not None else None
            ctx.launch_configurations[e.name] = args.get(e.name, default)
    unknown = sorted(set(args) - set(declared))
    if unknown:
        print(f"note: your launch file declares no argument {', '.join(unknown)} (ros2 launch would ignore it)")
    out = []
    for e in ld.entities:
        if isinstance(e, DeclareLaunchArgument):
            continue
        if not isinstance(e, ExecuteProcess):
            out.append((type(e).__name__, None, "(not a process: this runner does not show it)"))
            continue
        try:
            started = e.condition is None or e.condition.evaluate(ctx)
            cmd = [perform_substitutions(ctx, part) for part in e.cmd]
            name = perform_substitutions(ctx, e.name) if e.name else "?"
        except Exception as ex:
            sys.exit(f"a launch value could not be computed: {type(ex).__name__}: {ex} — is every launch "
                     "argument you use declared with DeclareLaunchArgument?")
        out.append((name, started, " ".join(c.replace(sys.executable, "python3") for c in cmd)))
    return declared, out


def launch(argv):
    args = {}
    for a in argv:
        if ":=" not in a:
            sys.exit(f"launch arguments are written name:=value, got {a!r}")
        k, v = a.split(":=", 1)
        args[k] = v
    declared, out = plan(args)
    print(f"launch arguments declared: {', '.join(declared) or 'none'}   given: {args or 'none'}")
    for name, started, cmd in out:
        mark = "·" if started is None else ("▶ starts " if started else "✘ skipped")
        print(f"\n{mark} {name}\n    {cmd}")
    print("\nNothing was started. To run it: ros2 launch navera_lite/ros/navera_lite_launch.py "
          + " ".join(argv))


def test_launch():
    print("TODO 5  generate_launch_description()")
    declared, out = plan({})
    procs = [o for o in out if o[1] is not None]
    ok = show(sorted(declared) == ["gps_source", "use_boat"], f"launch arguments: {declared}")
    ok &= show(len(procs) == 3, f"{len(procs)} process(es): {', '.join(o[0] for o in procs)}   "
                                "(`python3 run_lab13.py launch` shows their commands)")
    return ok


def test():
    g = rk.load_student("navera_lite.ros.gps_node")
    s = rk.load_student("navera_lite.settings")
    results = [test_descriptor(g)]
    print()
    results.append(test_node(g))
    print()
    results.append(test_settings(s))
    print()
    if rk.is_stub(rk.load_student("navera_lite.ros.navera_lite_launch").generate_launch_description):
        results.append(show(False, "TODO 5 generate_launch_description() is not written yet"))
    else:
        results.append(test_launch())
    print(f"\n{sum(bool(r) for r in results)}/{len(results)} TODO groups pass their examples. "
          "(✔ Check my work tests them on other cases too.)")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "test":
        test()
    elif mode == "settings" and len(sys.argv) == 3:
        settings(sys.argv[2])
    elif mode == "launch":
        launch(sys.argv[2:])
    else:
        sys.exit(__doc__)
