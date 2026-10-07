import math
import re
import statistics
import time

from academy_check import Background, Checker, load_student, need, wait_for_messages

c = Checker()
M_PER_DEG = 2 * math.pi * 6_371_000.0 / 360


def tracker():
    (T,) = need(load_student("gps_listener.py"), "Tracker")
    return T()


@c.test("gps_listener.py and status_listener.py load without errors",
        hint="Run `python3 -c \"import gps_listener, status_listener\"` and read the error.")
def _():
    need(load_student("gps_listener.py"), "Tracker", "GpsListener", "haversine_m")
    need(load_student("status_listener.py"), "state_name", "describe", "StatusListener")


@c.test("TODO 1 — the first fix: count 1, distance 0, speed None",
        hint="On the first call there is no previous fix (self.last is None): add 1 to count, "
             "remember the fix in self.last, and return None.")
def _():
    t = tracker()
    v = t.update(35.8, 10.6, 100.0)
    c.ok(v is None, f"update() returned {v!r} for the first fix — there is no speed yet, return None")
    c.eq(t.count, 1, "count after one fix")
    c.near(t.distance_m, 0.0, 1e-9, "distance_m after one fix")
    c.ok(t.last is not None, "self.last is still None after a fix — store (lat, lon, t) in it")


@c.test("TODO 1 — a second fix 100 m north, 10 s later: speed 10 m/s, distance 100 m",
        hint="step = haversine_m(previous lat, previous lon, lat, lon); dt = t - previous t; speed = step / dt. "
             "Do not forget to ADD step to self.distance_m.")
def _():
    t = tracker()
    t.update(35.8, 10.6, 100.0)
    v = t.update(35.8 + 100 / M_PER_DEG, 10.6, 110.0)
    c.near(v, 10.0, 0.05, "speed returned by update()")
    c.near(t.speed_mps, 10.0, 0.05, "self.speed_mps")
    c.near(t.distance_m, 100.0, 0.5, "self.distance_m")
    c.eq(t.count, 2, "count")


@c.test("TODO 1 — the distance adds up over many fixes, and two fixes with the same time don't crash",
        hint="self.last must be updated at EVERY call. When dt is 0 (two fixes with the same stamp), "
             "do not divide: the speed is None.")
def _():
    t = tracker()
    for i in range(4):                        # 3 steps of 50 m east, 5 s apart
        t.update(0.0001, 10.0 + i * 50 / M_PER_DEG, 5.0 * i)
    c.near(t.distance_m, 150.0, 1.0, "distance after 3 steps of 50 m")
    c.near(t.speed_mps, 10.0, 0.1, "speed after the last step")
    v = t.update(0.0001, 10.0 + 4 * 50 / M_PER_DEG, 15.0)       # same time as the previous fix
    c.ok(v is None, f"with dt = 0 the speed must be None, got {v!r}")
    c.near(t.distance_m, 200.0, 1.0, "distance after a 4th step")


@c.test("TODO 4 — state_name() names the 4 states",
        hint="A dict {NavStatus.STATE_INITIALIZING: \"INITIALIZING\", ...} and dict.get(state, default) is "
             "one tidy way.")
def _():
    from navera_msgs.msg import NavStatus
    (f,) = need(load_student("status_listener.py"), "state_name")
    for n, want in ((NavStatus.STATE_INITIALIZING, "INITIALIZING"), (NavStatus.STATE_NO_FIX, "NO_FIX"),
                    (NavStatus.STATE_FIX, "FIX"), (NavStatus.STATE_DEGRADED, "DEGRADED")):
        c.eq(f(n), want, f"state_name({n})")
    c.ok("UNKNOWN" in str(f(42)), f"state_name(42) should say UNKNOWN STATE, got {f(42)!r}")


@c.test("describe() writes state, source and reason",
        hint="describe() is given: it works as soon as state_name() does.")
def _():
    from navera_msgs.msg import NavStatus
    (f,) = need(load_student("status_listener.py"), "describe")
    m = NavStatus(state=NavStatus.STATE_FIX, active_source=NavStatus.SOURCE_GPS, reason="GPS fix")
    c.eq(f(m), "FIX | source: GPS | GPS fix", "describe(a FIX from GPS)")


LINE = re.compile(r"fix (\d+): distance ([\d.]+) m, speed ([\d.?]+) m/s")
RUN = {}


def run_listener():
    if "lines" not in RUN:
        RUN["lines"] = []
        with Background("python3 -u gps_track_player.py", settle=2.0):
            with Background("python3 -u gps_listener.py", settle=2.0) as bg:
                time.sleep(9)
        RUN["out"] = bg.output()
        RUN["lines"] = LINE.findall(RUN["out"])
    if len(RUN["lines"]) < 4:
        out = RUN["out"]
        c.ok(False, f"{len(RUN['lines'])} lines like `fix 12: distance 66.0 m, speed 6.0 m/s` in 9 s." +
             (f" Your node printed:\n{out[-600:]}" if out.strip() else " Your node printed nothing."))
    return RUN["lines"]


@c.test("TODO 2/3 — gps_listener.py receives the track player's fixes and logs one line per fix",
        hint="TODO 2: self.create_subscription(message type, topic, callback, 10). TODO 3: log the line "
             "with self.get_logger().info(...) in exactly the format shown in the TODO.")
def _():
    run_listener()


@c.test("the speeds you log match the player's 6 m/s",
        hint="t must come from the message's header.stamp (sec + nanosec * 1e-9), not from time.time().")
def _():
    lines = run_listener()
    speeds = [float(s) for _, _, s in lines if s != "?"]
    c.ok(len(speeds) >= 3, "not enough speeds logged (only '?')")
    c.near(statistics.median(speeds), 6.0, 0.6, "the median logged speed (m/s)")


@c.test("the distance you log grows by 3 m per fix (6 m/s x 0.5 s)",
        hint="Add each step to self.distance_m; the first fix counts as distance 0.")
def _():
    lines = run_listener()
    n0, d0, _ = lines[0]
    n1, d1, _ = lines[-1]
    fixes = int(n1) - int(n0)
    c.ok(fixes > 0, "the fix numbers do not grow")
    c.near((float(d1) - float(d0)) / fixes, 3.0, 0.4, "distance gained per fix (m)")


NAV = {}


def run_navera():
    """track player -> ros_gps_node -> NAVERA estimator -> your status_listener; then the GPS stops."""
    if "out" not in NAV:
        from navera_msgs.msg import NavStatus
        NAV["out"], NAV["fix"] = "", False
        with Background("ros2 run navera_estimator estimator_node.py", settle=2.0), \
                Background("ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/fake_gps/fix", settle=1.0), \
                Background("python3 -u status_listener.py", settle=2.0) as bg:
            with Background("python3 -u gps_track_player.py", settle=1.0):
                end = time.time() + 20
                while time.time() < end and not NAV["fix"]:
                    msgs = wait_for_messages("/navera/nav_status", NavStatus, count=1, timeout=2)
                    NAV["fix"] = any(m.state == NavStatus.STATE_FIX for m in msgs)
                time.sleep(3)                  # a few seconds of FIX
            time.sleep(6)                      # the GPS has stopped: > gps_timeout_s (3 s)
        NAV["out"] = bg.output()
    c.ok(NAV["fix"], "NAVERA never reached FIX with the track player's GPS — tell your teacher")
    return NAV["out"]


@c.test("TODO 5 — status_listener.py hears NAVERA say FIX from GPS",
        hint="TODO 5: subscribe to NavStatus on TOPIC with self.on_status. TODO 6 must log describe(msg).")
def _():
    out = run_navera()
    c.ok("FIX | source: GPS" in out,
         "no line `FIX | source: GPS | GPS fix` in your node's output:\n" + out[-600:])


@c.test("TODO 6 — it prints only when the decision changes, and sees NO_FIX when the GPS stops",
        hint="Compare (msg.state, msg.active_source) with self.last_key; print and store it only when "
             "they differ. NAVERA publishes 5 status messages per second: 5 lines per second is too many.")
def _():
    out = run_navera()
    n_fix = out.count("FIX | source: GPS")
    c.ok(n_fix <= 3, f"`FIX | source: GPS` was printed {n_fix} times in a few seconds — print only on change")
    c.ok("NO_FIX" in out and "stale" in out,
         "after the GPS stopped, no line with NO_FIX and the reason `GPS: stale (...)`:\n" + out[-600:])


c.run()
