import math
import os
import time

from academy_check import Background, Checker, load_student, need, sh, wait_for_messages

c = Checker()
R = 6_371_000.0
NAVERA_YAML = os.path.expanduser("~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml")
WANT_YAML = {"topic": "/fake_gps/fix", "rate_hz": 1.0, "start_lat": 35.83, "start_lon": 10.59,
             "speed_mps": 8.0, "heading_deg": 90.0, "sigma_m": 3.0}


def dist_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1.0, a)))


def stamp(m):
    return m.header.stamp.sec + m.header.stamp.nanosec * 1e-9


def rate_of(msgs):
    return (len(msgs) - 1) / (stamp(msgs[-1]) - stamp(msgs[0])) if len(msgs) > 1 and stamp(msgs[-1]) > stamp(msgs[0]) else 0


def speed_of(msgs):
    a, b = msgs[0], msgs[-1]
    return dist_m(a.latitude, a.longitude, b.latitude, b.longitude) / max(1e-6, stamp(b) - stamp(a))


def collect(cmd, topic, count, timeout=15, extra=None):
    """Run cmd, collect `count` NavSatFix on topic; extra(bg) runs while it is alive."""
    from sensor_msgs.msg import NavSatFix
    with Background(cmd, settle=2.5) as bg:
        first = wait_for_messages(topic, NavSatFix, count=1, timeout=timeout)
        msgs = wait_for_messages(topic, NavSatFix, count=count, timeout=timeout) if first else []
        more = extra(bg) if (extra and msgs) else None
    if len(msgs) < 3:
        out = bg.output()
        c.ok(False, f"only {len(msgs)} messages on {topic} with `{cmd}`." +
             (f" The node printed:\n{out[-600:]}" if out.strip() else ""))
    return msgs, more


def load_yaml(path):
    import yaml
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        c.ok(False, f"{path} is missing")
    except yaml.YAMLError as e:
        c.ok(False, f"{os.path.basename(path)} is not valid YAML: {str(e)[:300]}")


@c.test("fake_gps_params.py loads", hint="Run `python3 fake_gps_params.py` and read the error.")
def _():
    need(load_student("fake_gps_params.py"), "FakeGps")


@c.test("TODO 1 — the node's settings are parameters (topic, rate_hz, start_lat, start_lon)",
        hint="declare_parameter(name, default) for each setting, then get_parameter(name).value. Try "
             "`python3 fake_gps_params.py --ros-args -p rate_hz:=4.0 -p topic:=/test/fix`.")
def _():
    msgs, _ = collect("python3 fake_gps_params.py --ros-args -p topic:=/check/fix -p rate_hz:=4.0 "
                      "-p start_lat:=36.0 -p start_lon:=10.0", "/check/fix", count=9)
    c.near(rate_of(msgs), 4.0, 0.5, "the rate with -p rate_hz:=4.0")
    c.ok(dist_m(msgs[0].latitude, msgs[0].longitude, 36.0, 10.0) < 200,
         f"with -p start_lat:=36.0 -p start_lon:=10.0 the first fix is at "
         f"({msgs[0].latitude:.5f}, {msgs[0].longitude:.5f})")


@c.test("TODO 1/2 — the defaults stay the same, and `ros2 param set` changes the speed while it runs",
        hint="Defaults: rate_hz 2.0, speed_mps 5.0… TODO 2: read speed_mps with get_parameter() INSIDE on_timer, "
             "not only in __init__.")
def _():
    def change(bg):
        code, out = sh("ros2 param get /fake_gps rate_hz", timeout=20)
        before = wait_for_messages("/fake_gps/fix", __import__("sensor_msgs.msg", fromlist=["NavSatFix"]).NavSatFix,
                                   count=4, timeout=6)
        sh("ros2 param set /fake_gps speed_mps 20.0", timeout=20)
        time.sleep(1.0)
        after = wait_for_messages("/fake_gps/fix", __import__("sensor_msgs.msg", fromlist=["NavSatFix"]).NavSatFix,
                                  count=5, timeout=6)
        return out, before, after
    msgs, (got, before, after) = collect("python3 fake_gps_params.py", "/fake_gps/fix", count=4, extra=change)
    c.ok("2.0" in got, f"`ros2 param get /fake_gps rate_hz` said: {got.strip()[:200]!r} — expected 2.0")
    c.near(rate_of(msgs), 2.0, 0.3, "the default rate")
    c.ok(dist_m(msgs[0].latitude, msgs[0].longitude, 35.8256, 10.6084) < 300, "the default start is not Sousse")
    c.near(speed_of(before), 5.0, 0.6, "the default speed (m/s)")
    c.ok(len(after) >= 3, "too few messages after `ros2 param set`")
    c.near(speed_of(after), 20.0, 2.5, "the speed after `ros2 param set /fake_gps speed_mps 20.0`")


@c.test("TODO 3 — my_gps.yaml holds the settings of the lab",
        hint="fake_gps: → ros__parameters: → one `name: value` per line, indented with spaces. "
             "Values: rate 1.0, start 35.8300 / 10.5900, speed 8.0, heading 90.0, sigma 3.0.")
def _():
    d = load_yaml("my_gps.yaml")
    c.ok(isinstance(d, dict) and "fake_gps" in d, "the first line must be `fake_gps:` (the node name)")
    p = (d["fake_gps"] or {}).get("ros__parameters")
    c.ok(isinstance(p, dict), "under fake_gps: you need `ros__parameters:` (two underscores), indented")
    for k, v in WANT_YAML.items():
        c.ok(k in p, f"`{k}` is missing in my_gps.yaml")
        if isinstance(v, float):
            c.ok(isinstance(p[k], float), f"{k}: {p[k]!r} — write it as a decimal number with a dot (e.g. {v})")
            c.near(p[k], v, 1e-6, k)
        else:
            c.eq(p[k], v, k)


@c.test("my_gps.yaml is used: 1 fix per second, from 35.83 / 10.59, 8 m/s towards the east",
        hint="Try `python3 fake_gps_params.py --ros-args --params-file my_gps.yaml` and watch "
             "`ros2 topic echo /fake_gps/fix --field longitude`.")
def _():
    msgs, _ = collect("python3 fake_gps_params.py --ros-args --params-file my_gps.yaml", "/fake_gps/fix",
                      count=5, timeout=12)
    c.near(rate_of(msgs), 1.0, 0.2, "the rate")
    c.ok(dist_m(msgs[0].latitude, msgs[0].longitude, 35.83, 10.59) < 200, "the first fix is not near 35.83 / 10.59")
    c.near(speed_of(msgs), 8.0, 1.0, "the speed (m/s)")
    c.ok(msgs[-1].longitude > msgs[0].longitude and abs(msgs[-1].latitude - msgs[0].latitude) < 1e-5,
         "the vehicle should go due east (longitude grows, latitude stays)")


@c.test("NAVERA copy — fix_max_sigma_m changed to 2.0 in estimator_params.yaml",
        hint="Edit ~/navera/navera_estimator/navera_estimator/config/estimator_params.yaml: the line "
             "`fix_max_sigma_m: 25.0` becomes `fix_max_sigma_m: 2.0`. Keep the indentation.")
def _():
    d = load_yaml(NAVERA_YAML)
    try:
        v = d["estimator_node"]["ros__parameters"]["fix_max_sigma_m"]
    except (KeyError, TypeError):
        c.ok(False, "the file's structure is broken: estimator_node → ros__parameters → fix_max_sigma_m. "
                    "`git -C ~/navera diff` shows what you changed.")
    c.near(v, 2.0, 1e-6, "fix_max_sigma_m in your NAVERA copy")


LAUNCH = {}


def run_launch():
    if "status" not in LAUNCH:
        from navera_msgs.msg import NavStatus
        from sensor_msgs.msg import NavSatFix
        LAUNCH["status"], LAUNCH["fixes"], LAUNCH["param"], LAUNCH["out"] = [], [], "", ""
        try:
            with Background("ros2 launch ./my_navera.launch.py", settle=4.0) as bg:
                LAUNCH["fixes"] = wait_for_messages("/fake_gps/fix", NavSatFix, count=3, timeout=15)
                end = time.time() + 15
                while time.time() < end:
                    LAUNCH["status"] = wait_for_messages("/navera/nav_status", NavStatus, count=3, timeout=3)
                    if LAUNCH["status"] and LAUNCH["status"][-1].active_source == NavStatus.SOURCE_GPS:
                        break
                LAUNCH["param"] = sh("ros2 param get /estimator_node fix_max_sigma_m", timeout=20)[1]
            LAUNCH["out"] = bg.output()
        except Exception as e:            # the launch stopped right away
            LAUNCH["out"] = str(e)
    if not LAUNCH["status"]:
        c.ok(False, "no /navera/nav_status: the launch did not start NAVERA's estimator. Output:\n" + LAUNCH["out"][-800:])
    return LAUNCH


@c.test("TODO 4–7 — `ros2 launch ./my_navera.launch.py` starts the fake GPS (with my_gps.yaml), the bridge "
        "and NAVERA's arbiter", hint="Run the launch yourself and read its output: each node prints a line "
             "with its name in [brackets]. Did you put the three actions in the LaunchDescription list?")
def _():
    from navera_msgs.msg import NavStatus
    L = run_launch()
    c.ok(len(L["fixes"]) >= 2, "no messages on /fake_gps/fix during the launch (TODO 4)")
    c.near(rate_of(L["fixes"]), 1.0, 0.25, "the fake GPS rate in the launch (from my_gps.yaml)")
    st = L["status"][-1]
    c.ok(st.active_source == NavStatus.SOURCE_GPS,
         f"NAVERA does not use the GPS (state {st.state}, reason {st.reason!r}) — is ros_gps listening to "
         f"/fake_gps/fix? (TODO 5)")


@c.test("the launched arbiter uses your NAVERA setting: GPS with 3 m is now DEGRADED",
        hint="The launch must include NAVERA's estimator.launch.py (which loads estimator_params.yaml), and "
             "fix_max_sigma_m must be 2.0 in that file.")
def _():
    from navera_msgs.msg import NavStatus
    L = run_launch()
    st = L["status"][-1]
    c.ok("2.0" in L["param"], f"`ros2 param get /estimator_node fix_max_sigma_m` said {L['param'].strip()!r}")
    c.ok(st.state == NavStatus.STATE_DEGRADED and "uncertainty 3 m > 2 m" in st.reason,
         f"state {st.state}, reason {st.reason!r} — expected DEGRADED, `GPS fix, uncertainty 3 m > 2 m`")


c.run()
