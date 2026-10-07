import math
import os
import re
import time

from academy_check import Background, Checker, load_student, need, sh, wait_for_messages

c = Checker()
R = 6_371_000.0
NAVERA_YAML = os.path.expanduser("~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml")
SOUSSE, MONASTIR = (35.8250, 10.5950), (35.78, 10.86)


def dist_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1.0, a)))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    return math.degrees(math.atan2(math.sin(dl) * math.cos(p2),
                                   math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl))) % 360


def stamp(m):
    return m.header.stamp.sec + m.header.stamp.nanosec * 1e-9


def node_mod():
    return load_student("fake_gps_node.py")


def ans(name):
    (v,) = need(load_student("answers.py"), name)
    c.ok(v is not None, f"{name} has no answer yet")
    return v


def load_yaml(path):
    import yaml
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        c.ok(False, f"{path} is missing")
    except yaml.YAMLError as e:
        c.ok(False, f"{os.path.basename(path)} is not valid YAML: {str(e)[:300]}")


@c.test("fake_gps_node.py, my_navera.launch.py and answers.py load",
        hint="Run `python3 fake_gps_node.py` and `python3 answers.py`, and read the error (line number!).")
def _():
    need(node_mod(), "make_descriptor", "check_settings", "FakeGps", "SPECS")
    need(load_student("my_navera.launch.py"), "generate_launch_description", "fake_gps")
    load_student("answers.py")


@c.test("TODO 1 — make_descriptor(): description, read_only and a floating-point range",
        hint="ParameterDescriptor(description=..., read_only=...); if lo is not None: "
             "floating_point_range=[FloatingPointRange(from_value=lo, to_value=hi, step=0.0)].")
def _():
    (f,) = need(node_mod(), "make_descriptor")
    d = f("ground speed, m/s", 0.0, 60.0, False)
    c.eq(d.description, "ground speed, m/s", "description")
    c.eq(d.read_only, False, "read_only")
    c.ok(len(d.floating_point_range) == 1, "floating_point_range should hold one FloatingPointRange")
    r = d.floating_point_range[0]
    c.eq((r.from_value, r.to_value), (0.0, 60.0), "(from_value, to_value)")
    d = f("kind of vehicle", None, None, True)
    c.ok(d.read_only is True and len(d.floating_point_range) == 0, "no range when lo is None, and read_only kept")


@c.test("TODO 2a — check_settings(): the vehicle / speed rule, with the exact messages",
        hint="Unknown vehicle → \"unknown vehicle 'tank' (car, drone or boat)\"; too fast → "
             "\"speed 20.0 m/s too fast for a boat (max 15.0)\" (one decimal); otherwise \"\".")
def _():
    (f,) = need(node_mod(), "check_settings")
    c.eq(f("car", 12.0), "", "check_settings('car', 12.0)")
    c.eq(f("boat", 15.0), "", "check_settings('boat', 15.0) (the maximum is allowed)")
    c.eq(f("boat", 20.0), "speed 20.0 m/s too fast for a boat (max 15.0)", "check_settings('boat', 20.0)")
    c.eq(f("tank", 1.0), "unknown vehicle 'tank' (car, drone or boat)", "check_settings('tank', 1.0)")


LIVE = {}


@c.test("live — descriptors and the validation callback refuse bad changes, accept good ones",
        hint="TODO 1 makes rate_hz read-only and speed_mps limited to [0, 60]. TODO 2b: combine the new values "
             "(p.name, p.value) with the current ones and return SetParametersResult(successful=..., reason=...).")
def _():
    if not LIVE:
        with Background("python3 -u fake_gps_node.py", settle=3.0):
            wait_for_messages("/fake_gps/fix", __import__("sensor_msgs.msg", fromlist=["NavSatFix"]).NavSatFix, 1, 10)
            for k, cmd in (("describe", "ros2 param describe /fake_gps speed_mps"),
                           ("rate", "ros2 param set /fake_gps rate_hz 5.0"),
                           ("s500", "ros2 param set /fake_gps speed_mps 500.0"),
                           ("s45", "ros2 param set /fake_gps speed_mps 45.0"),
                           ("drone", "ros2 param set /fake_gps vehicle drone"),
                           ("s45d", "ros2 param set /fake_gps speed_mps 25.0")):
                LIVE[k] = sh(cmd, timeout=25)[1]
    c.ok("Max value: 60.0" in LIVE["describe"], "`ros2 param describe /fake_gps speed_mps` shows no range:\n" + LIVE["describe"][-300:])
    c.ok("read-only" in LIVE["rate"], f"rate_hz should be read-only, `ros2 param set` said: {LIVE['rate'].strip()[:200]}")
    c.ok("out of range" in LIVE["s500"], f"speed 500 should be out of range, got: {LIVE['s500'].strip()[:200]}")
    c.ok("too fast for a car" in LIVE["s45"], f"speed 45 for a car should be refused by your callback, got: {LIVE['s45'].strip()[:200]}")
    c.ok("successful" in LIVE["drone"] and "successful" in LIVE["s45d"],
         f"vehicle drone then speed 25.0 should both be accepted, got: {LIVE['drone'].strip()[:100]} / {LIVE['s45d'].strip()[:100]}")


@c.test("TODO 3 — my_gps.yaml: /** first, then the car and the boat",
        hint="/**: rate_hz 1.0, sigma_m 3.0 — FIRST. /car/fake_gps: car, 35.8250 / 10.5950, 12.0, 90.0. "
             "/boat/fake_gps: boat, 35.7800 / 10.8600, 5.0, 45.0. Decimals with a dot, text in quotes.")
def _():
    d = load_yaml("my_gps.yaml")
    c.ok(isinstance(d, dict), "my_gps.yaml should be a mapping of node names")
    keys = list(d)
    c.ok(keys and keys[0] == "/**", f"the first section must be /** (the last match wins), got {keys}")
    want = {"/**": {"rate_hz": 1.0, "sigma_m": 3.0},
            "/car/fake_gps": {"vehicle": "car", "start_lat": 35.825, "start_lon": 10.595, "speed_mps": 12.0, "heading_deg": 90.0},
            "/boat/fake_gps": {"vehicle": "boat", "start_lat": 35.78, "start_lon": 10.86, "speed_mps": 5.0, "heading_deg": 45.0}}
    for sect, vals in want.items():
        p = (d.get(sect) or {}).get("ros__parameters")
        c.ok(isinstance(p, dict), f"section {sect} → ros__parameters is missing (two underscores, indented)")
        for k, v in vals.items():
            c.ok(k in p, f"{sect}: `{k}` is missing")
            if isinstance(v, float):
                c.ok(isinstance(p[k], float), f"{sect}: {k}: {p[k]!r} — write a decimal number with a dot")
                c.near(p[k], v, 1e-6, f"{sect}: {k}")
            else:
                c.eq(p[k], v, f"{sect}: {k}")


@c.test("live — the boat from the file: /boat/fix at 1 Hz, from off Monastir, 5 m/s towards the north-east",
        hint="python3 fake_gps_node.py --ros-args -r __ns:=/boat -r /fake_gps/fix:=fix --params-file my_gps.yaml")
def _():
    from sensor_msgs.msg import NavSatFix
    with Background("python3 -u fake_gps_node.py --ros-args -r __ns:=/boat -r /fake_gps/fix:=fix "
                    "--params-file my_gps.yaml", settle=3.0) as bg:
        msgs = wait_for_messages("/boat/fix", NavSatFix, count=1, timeout=10) and \
            wait_for_messages("/boat/fix", NavSatFix, count=6, timeout=9)
    msgs = msgs or []
    c.ok(len(msgs) >= 4, f"only {len(msgs)} messages on /boat/fix." + (f" The node printed:\n{bg.output()[-400:]}"))
    dt = stamp(msgs[-1]) - stamp(msgs[0])
    c.near((len(msgs) - 1) / dt, 1.0, 0.15, "the boat's rate (Hz)")
    c.ok(dist_m(msgs[0].latitude, msgs[0].longitude, *MONASTIR) < 100, "the boat does not start off Monastir")
    a, b = msgs[0], msgs[-1]
    c.near(dist_m(a.latitude, a.longitude, b.latitude, b.longitude) / dt, 5.0, 0.5, "the boat's speed (m/s)")
    c.near(bearing_deg(a.latitude, a.longitude, b.latitude, b.longitude), 45.0, 5.0, "the boat's direction (°)")


@c.test("answers.py — runtime changes and the four precedence measurements",
        hint="Steps 2–5: what `ros2 param set` answered, and `ros2 param get /car/fake_gps rate_hz` in the four runs. "
             "Remember: command-line items are applied in the order they are written.")
def _():
    for k, v in (("RATE_SET_ACCEPTED", False), ("SPEED_500_ACCEPTED", False), ("BOAT_FAST_ACCEPTED", False)):
        got = ans(k)
        c.ok(got is v, f"{k} = {got!r} — run the command of the lab again and read the answer")
    for k, v in (("RATE_CODE_DEFAULT", 2.0), ("RATE_FROM_FILE", 1.0), ("RATE_FILE_THEN_P", 4.0), ("RATE_P_THEN_FILE", 1.0)):
        c.near(ans(k), v, 1e-9, k)


LAUNCH = {}


def launch(args=""):
    if args not in LAUNCH:
        from navera_msgs.msg import NavStatus, PositionEstimate
        res = {"nodes": "", "status": [], "pos": [], "out": ""}
        try:
            with Background(f"ros2 launch ./my_navera.launch.py {args}", settle=5.0) as bg:
                end = time.time() + 15
                while time.time() < end:
                    res["status"] = wait_for_messages("/navera/nav_status", NavStatus, count=2, timeout=3)
                    if res["status"] and res["status"][-1].active_source == NavStatus.SOURCE_GPS:
                        break
                res["pos"] = wait_for_messages("/navera/position", PositionEstimate, count=1, timeout=4)
                res["nodes"] = sh("ros2 node list --no-daemon --spin-time 3", timeout=25)[1]
            res["out"] = bg.output()
        except Exception as e:                     # the launch stopped right away
            res["out"] = str(e)
        LAUNCH[args] = res
    r = LAUNCH[args]
    c.ok(r["status"], f"no /navera/nav_status with `ros2 launch ./my_navera.launch.py {args}`: did it include NAVERA's "
                      "estimator.launch.py (TODO 7)? Output:\n" + r["out"][-800:])
    return r


@c.test("TODO 4–8 — `ros2 launch ./my_navera.launch.py`: car, boat, bridge and arbiter, NAVERA follows the car",
        hint="Read the launch output: one [bracketed] line per process. Are the four actions (and the arguments) in "
             "the LaunchDescription list? Does ros_gps say `GPS from /car/fix`?")
def _():
    from navera_msgs.msg import NavStatus
    r = launch()
    for n in ("/car/fake_gps", "/boat/fake_gps", "/ros_gps", "/estimator_node"):
        c.ok(n in r["nodes"], f"node {n} is missing from `ros2 node list`:\n{r['nodes']}")
    c.ok("GPS from /car/fix" in r["out"], "ros_gps does not listen to /car/fix (TODO 6)")
    c.ok(r["status"][-1].active_source == NavStatus.SOURCE_GPS, f"NAVERA does not use the GPS: {r['status'][-1].reason!r}")
    c.ok(r["pos"] and dist_m(r["pos"][0].latitude, r["pos"][0].longitude, *SOUSSE) < 2000,
         "no /navera/position near the car in Sousse")


@c.test("TODO 7 — the included estimator.launch.py receives gps_timeout_s := 2.0",
        hint="IncludeLaunchDescription(PythonLaunchDescriptionSource(path), launch_arguments={\"gps_timeout_s\": "
             "\"2.0\"}.items()). The arbiter logs its windows when it starts: look for gps_timeout=2.0s.")
def _():
    r = launch()
    c.ok("gps_timeout=2.0s" in r["out"], "the arbiter did not start with gps_timeout=2.0s:\n" +
         "\n".join(l for l in r["out"].splitlines() if "estimator up" in l)[-300:])


@c.test("launch arguments — with_boat:=false starts no boat; gps_source:=boat makes NAVERA follow the boat",
        hint="TODO 5: DeclareLaunchArgument(\"with_boat\", default_value=\"true\") and (\"gps_source\", \"car\"). "
             "TODO 8: condition=IfCondition(LaunchConfiguration(\"with_boat\")) on the boat.")
def _():
    r = launch("with_boat:=false")
    c.ok("/car/fake_gps" in r["nodes"] and "/boat/fake_gps" not in r["nodes"],
         f"with_boat:=false — node list:\n{r['nodes']}")
    r = launch("gps_source:=boat")
    c.ok("GPS from /boat/fix" in r["out"], "with gps_source:=boat, ros_gps does not listen to /boat/fix")
    c.ok(r["pos"] and dist_m(r["pos"][0].latitude, r["pos"][0].longitude, *MONASTIR) < 2000,
         "with gps_source:=boat, /navera/position is not near the boat off Monastir")


@c.test("NAVERA copy — fix_max_sigma_m is 2.0 and gps_timeout_s is back to 3.0; the order trap measured",
        hint="Edit ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml (keep the indentation); "
             "`git -C ~/navera diff` must show only fix_max_sigma_m. Answers: plain launch 3.0, ros2 run with the "
             "YAML 1.0, your launch 2.0.")
def _():
    d = load_yaml(NAVERA_YAML)
    try:
        p = d["estimator_node"]["ros__parameters"]
    except (KeyError, TypeError):
        c.ok(False, "the file's structure is broken: estimator_node → ros__parameters → … (see `git -C ~/navera diff`)")
    c.near(p.get("fix_max_sigma_m"), 2.0, 1e-9, "fix_max_sigma_m in your NAVERA copy")
    c.near(p.get("gps_timeout_s"), 3.0, 1e-9, "gps_timeout_s in your NAVERA copy (put it back to 3.0)")
    for k, v in (("GPS_TIMEOUT_YAML_1_PLAIN_LAUNCH", 3.0), ("GPS_TIMEOUT_YAML_1_RUN", 1.0), ("GPS_TIMEOUT_MY_LAUNCH", 2.0)):
        c.near(ans(k), v, 1e-9, k)


@c.test("live — with fix_max_sigma_m = 2.0, the launched arbiter says DEGRADED: GPS 3 m > 2 m",
        hint="Your launch includes NAVERA's estimator.launch.py, which loads estimator_params.yaml; the fake "
             "receivers state sigma_m 3.0.")
def _():
    from navera_msgs.msg import NavStatus
    st = launch()["status"][-1]
    c.ok(st.state == NavStatus.STATE_DEGRADED and "uncertainty 3 m > 2 m" in st.reason,
         f"state {st.state}, reason {st.reason!r} — expected DEGRADED, `GPS fix, uncertainty 3 m > 2 m`")


@c.test("report.md — Precedence, Validation and NAVERA, with your measurements",
        hint="Keep the three headings, at least 40 words each. Validation must quote a refusal message "
             "(e.g. `too fast for a`); NAVERA must quote the three gps_timeout_s values and `3 m > 2 m`.")
def _():
    c.file_exists("report.md")
    txt = open("report.md", encoding="utf-8", errors="replace").read()
    secs = {}
    for title in ("Precedence", "Validation", "NAVERA"):
        m = re.search(r"^##\s*" + title + r"\s*$(.*?)(?=^##\s|\Z)", txt, re.M | re.S)
        c.ok(m is not None, f"the heading `## {title}` is missing")
        body = re.sub(r"^\*(?=\S)[^*]+?\*\s*$", "", m.group(1), flags=re.M | re.S)
        words = len(re.findall(r"[A-Za-z0-9_.]+", body))
        c.ok(words >= 40, f"section {title} has {words} words of yours — write at least 40")
        secs[title] = body
    c.ok("too fast for a" in secs["Validation"] or "read-only" in secs["Validation"],
         "the Validation section quotes no refusal message")
    c.ok(all(x in secs["NAVERA"] for x in ("3.0", "1.0", "2.0")) and "3 m > 2 m" in secs["NAVERA"],
         "the NAVERA section must quote 3.0, 1.0, 2.0 and `3 m > 2 m`")


c.run()
