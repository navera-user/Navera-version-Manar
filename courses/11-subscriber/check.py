import json
import math
import re
import statistics
import time

from academy_check import Background, Checker, load_student, need, wait_for_messages

c = Checker()
M_PER_DEG = 2 * math.pi * 6_371_000.0 / 360
# noise_study.py with a correct Tracker (fixed seed): reference values
NOISE_REF = {"sigma_0m": {"distance_m": 715.47, "instant_mean_mps": 5.987, "window_mean_mps": 5.922,
                          "window_std_mps": 0.325},
             "sigma_3m": {"distance_m": 1501.17, "distance_ratio": 2.094, "instant_mean_mps": 12.562,
                          "instant_std_mps": 6.134, "window_mean_mps": 5.991, "window_std_mps": 1.003}}


def listener():
    return load_student("gps_listener.py")


def tracker():
    (T,) = need(listener(), "Tracker")
    return T()


@c.test("gps_listener.py, executor_demo.py and status_listener.py load without errors",
        hint="Run `python3 -c \"import gps_listener, executor_demo, status_listener\"` and read the error.")
def _():
    need(listener(), "Tracker", "GpsListener", "NO_FIX", "NOT_FINITE", "NULL_ISLAND", "NOT_NEWER")
    need(load_student("executor_demo.py"), "Demo", "make_executor")
    need(load_student("status_listener.py"), "state_name", "describe", "gps_silence_s", "StatusListener")


@c.test("TODO 1 — check() refuses no fix, NaN/inf, Null Island and old fixes, in that order",
        hint="status < 0 → NO_FIX; math.isfinite on lat, lon AND t → NOT_FINITE; (0.0, 0.0) → NULL_ISLAND; "
             "t <= the last accepted fix's t → NOT_NEWER; else \"\".")
def _():
    m = listener()
    t = m.Tracker()
    c.eq(t.check(35.8, 10.6, 10.0), "", "check(a good fix)")
    c.eq(t.check(35.8, 10.6, 10.0, -1), m.NO_FIX, "check(status -1)")
    c.eq(t.check(float("nan"), 10.6, 10.0), m.NOT_FINITE, "check(NaN latitude)")
    c.eq(t.check(35.8, 10.6, float("inf")), m.NOT_FINITE, "check(infinite time)")
    c.eq(t.check(0.0, 0.0, 10.0), m.NULL_ISLAND, "check(0.0, 0.0)")
    c.eq(t.check(0.0, 0.0, 10.0, -1), m.NO_FIX, "check(0, 0 AND no fix) — the first reason wins")
    t.last = (35.8, 10.6, 10.0)
    c.eq(t.check(35.8, 10.6, 10.0), m.NOT_NEWER, "check(same time as the last fix)")
    c.eq(t.check(35.8, 10.6, 9.5), m.NOT_NEWER, "check(older than the last fix)")
    c.eq(t.check(35.8, 10.6, 10.5), "", "check(newer than the last fix)")


@c.test("TODO 2 — update(): count, distance and instantaneous speed",
        hint="First fix: count 1, distance 0, return None. Next: step = haversine_m(previous, new), "
             "distance += step, speed = step / dt; remember the fix in self.last.")
def _():
    t = tracker()
    v = t.update(35.828, 10.64, 100.0)
    c.ok(v is None, f"update() returned {v!r} for the first fix — no speed yet, return None")
    c.eq(t.count, 1, "count after one fix")
    v = t.update(35.828 + 100 / M_PER_DEG, 10.64, 110.0)
    c.near(v, 10.0, 0.05, "speed returned by the second update()")
    c.near(t.speed_mps, 10.0, 0.05, "self.speed_mps")
    c.near(t.distance_m, 100.0, 0.5, "self.distance_m")
    c.ok(t.last is not None and abs(t.last[2] - 110.0) < 1e-9, f"self.last should be the new fix, got {t.last!r}")


@c.test("TODO 2 — window speed over the history, and rejected fixes change nothing",
        hint="Append (lat, lon, t) to self.history (a deque of `window` fixes); window speed = haversine(oldest, "
             "newest) / (t_newest − t_oldest). A rejected fix must return None before touching the state.")
def _():
    (T,) = need(listener(), "Tracker")
    t = T(window=3)
    for i in range(5):                                   # 4 steps of 50 m north, 5 s apart
        t.update(35.828 + i * 50 / M_PER_DEG, 10.64, 5.0 * i)
    c.near(t.distance_m, 200.0, 1.0, "distance after 4 steps of 50 m")
    c.near(t.window_speed_mps, 10.0, 0.05, "window speed (3 fixes: 100 m in 10 s)")
    c.eq(len(t.history), 3, "len(history) with window=3")
    before = (t.count, t.distance_m, t.last)
    for bad in ((0.0, 0.0, 99.0, 0), (35.9, 10.6, 1.0, 0), (35.9, 10.6, 99.0, -1), (math.nan, 10.6, 99.0, 0)):
        c.ok(t.update(*bad) is None, f"update{bad} should be rejected and return None")
    c.eq((t.count, t.distance_m, t.last), before, "the state after 4 rejected fixes")
    c.eq(sum(t.rejected.values()), 4, "the total of self.rejected")


def results():
    try:
        return json.load(open("results.json"))
    except FileNotFoundError:
        c.ok(False, "results.json does not exist yet — run `python3 noise_study.py`")
    except ValueError as e:
        c.ok(False, f"results.json is not valid JSON: {e}")


@c.test("Step 3 — results.json: the noise study, run with your Tracker",
        hint="Run `python3 noise_study.py` after TODO 1 and 2. The seed is fixed: a correct Tracker gives "
             "exactly the course's numbers (distance ratio ≈ 2.09 with 3 m of noise).")
def _():
    r = (results() or {}).get("noise")
    c.ok(isinstance(r, dict) and "sigma_3m" in r, "results.json has no `noise` section — run python3 noise_study.py")
    for case, ref in NOISE_REF.items():
        for k, want in ref.items():
            got = r[case].get(k)
            c.ok(isinstance(got, (int, float)), f"noise.{case}.{k} is missing or not a number: {got!r}")
            c.near(got, want, max(0.01, 0.01 * abs(want)), f"noise.{case}.{k}")


LINE = re.compile(r"fix (\d+): distance ([\d.]+) m, speed ([\d.?]+) m/s, window ([\d.?]+) m/s")
REJ = re.compile(r"rejected \(([a-z ]+)\), (\d+) so far")
RUN = {}


def run_listener(faults):
    key = "faults" if faults else "plain"
    if key not in RUN:
        player = "python3 -u gps_track_player.py" + (" --ros-args -p faults:=true" if faults else "")
        with Background(player, settle=2.0):
            with Background("python3 -u gps_listener.py", settle=2.0) as bg:
                time.sleep(9 if not faults else 11)
        out = bg.output()
        RUN[key] = (out, LINE.findall(out), REJ.findall(out))
    out, lines, rej = RUN[key]
    if len(lines) < 4:
        c.ok(False, f"{len(lines)} lines like `fix 12: distance 66.0 m, speed 6.0 m/s, window 6.0 m/s`." +
             (f" Your node printed:\n{out[-600:]}" if out.strip() else " Your node printed nothing."))
    return lines, rej, out


@c.test("TODO 3 — gps_listener.py receives the player's fixes and logs one line per fix",
        hint="Course section 1: 3a subscribes to TOPIC with the sensor-data QoS profile named in the TODO "
             "and on_fix as callback. 3b (section 3, 'Which time?'): the time comes from the message's stamp, not "
             "the clock. Ask the tracker's check() for the reason BEFORE update() (update() returns None for a rejection and "
             "for the first fix alike), then log one line in exactly the format given in the TODO comment.")
def _():
    run_listener(False)


@c.test("live — the logged speeds and distance match the player's 6 m/s",
        hint="t must come from msg.header.stamp (sec + nanosec·1e-9), not from time.time(); add each step to "
             "the distance.")
def _():
    lines, _, _ = run_listener(False)
    speeds = [float(s) for _, _, s, _ in lines if s != "?"]
    c.ok(len(speeds) >= 3, "not enough speeds logged (only '?')")
    c.near(statistics.median(speeds), 6.0, 0.6, "the median instantaneous speed (m/s)")
    wins = [float(w) for _, _, _, w in lines if w != "?"]
    c.near(statistics.median(wins), 6.0, 0.6, "the median window speed (m/s)")
    (n0, d0, _, _), (n1, d1, _, _) = lines[0], lines[-1]
    c.ok(int(n1) > int(n0), "the fix numbers do not grow")
    c.near((float(d1) - float(d0)) / (int(n1) - int(n0)), 3.0, 0.4, "distance gained per fix (m)")


@c.test("live — with `faults:=true` the bad fixes are rejected and logged, and the speed stays right",
        hint="The faulty player sends a no-fix (NaN), a (0, 0) and a late duplicate every 6 s. Log "
             "`rejected (<reason>), <n> so far` for them, and do not let them change distance or speed.")
def _():
    lines, rej, out = run_listener(True)
    reasons = {r for r, _ in rej}
    for want in ("no fix", "null island", "not newer"):
        c.ok(want in reasons, f"no line `rejected ({want}), … so far` in your node's output:\n{out[-500:]}")
    speeds = [float(s) for _, _, s, _ in lines if s != "?"]
    c.ok(speeds and max(speeds) < 12.0, f"a bad fix reached the speed: max logged speed {max(speeds or [0]):.1f} m/s")


EXE = {}


def run_executor(mode):
    if mode not in EXE:
        with Background("python3 -u gps_track_player.py", settle=2.0):
            with Background(f"python3 -u executor_demo.py {mode}", settle=1.0) as bg:
                end = time.time() + 14
                while time.time() < end and bg.p.poll() is None:
                    time.sleep(0.3)
        try:
            EXE[mode] = json.load(open(f"executor_{mode}.json"))
        except (OSError, ValueError):
            EXE[mode] = None
        EXE[mode + "_out"] = bg.output()
    c.ok(EXE[mode] is not None, f"`python3 executor_demo.py {mode}` wrote no executor_{mode}.json:\n"
         + EXE[mode + "_out"][-500:])
    return EXE[mode]


@c.test("TODO 4 — with two callback groups and a MultiThreadedExecutor the timer runs on time",
        hint="Course section 2 (executors): 4a gives the timer and the subscription each their OWN mutually exclusive "
             "callback group; 4b makes make_executor('multi') return an executor with two threads, so both groups "
             "can run at the same time.")
def _():
    single = run_executor("single")
    c.ok(single["fixes"] >= 5 and single["max_gap_ms"] > 200,
         f"single: fixes {single['fixes']}, max gap {single['max_gap_ms']:.0f} ms — expected a gap > 200 ms")
    multi = run_executor("multi")
    c.eq(multi["executor"], "MultiThreadedExecutor", "the executor used for 'multi'")
    c.ok(multi["fixes"] >= 5, f"multi: only {multi['fixes']} fixes processed — is the player running?")
    c.ok(multi["max_gap_ms"] < 180 and multi["ticks"] >= 0.85 * multi["expected_ticks"],
         f"multi: {multi['ticks']} ticks of {multi['expected_ticks']}, max gap {multi['max_gap_ms']:.0f} ms — "
         "the timer still waits for the slow callback (are the two callbacks in two different groups?)")


@c.test("TODO 5 — state_name() names the 4 states",
        hint="A dict {NavStatus.STATE_INITIALIZING: \"INITIALIZING\", …} and dict.get(state, default).")
def _():
    from navera_msgs.msg import NavStatus
    (f,) = need(load_student("status_listener.py"), "state_name")
    for n, want in ((NavStatus.STATE_INITIALIZING, "INITIALIZING"), (NavStatus.STATE_NO_FIX, "NO_FIX"),
                    (NavStatus.STATE_FIX, "FIX"), (NavStatus.STATE_DEGRADED, "DEGRADED")):
        c.eq(f(n), want, f"state_name({n})")
    c.eq(f(42), "UNKNOWN STATE 42", "state_name(42)")


@c.test("TODO 6 — gps_silence_s(): header.stamp − last_seen of the GPS entry",
        hint="Loop over msg.sources, keep the one with source == SourceHealth.SOURCE_GPS; last_seen 0 means "
             "never heard (None). Use to_s() for both stamps.")
def _():
    from builtin_interfaces.msg import Time
    from navera_msgs.msg import NavStatus, SourceHealth
    (f,) = need(load_student("status_listener.py"), "gps_silence_s")
    m = NavStatus()
    m.header.stamp = Time(sec=200, nanosec=100_000_000)
    m.sources = [SourceHealth(source=SourceHealth.SOURCE_DAY_VISION, last_seen=Time(sec=150)),
                 SourceHealth(source=SourceHealth.SOURCE_GPS, last_seen=Time(sec=196, nanosec=900_000_000))]
    c.near(f(m), 3.2, 1e-6, "gps_silence_s (GPS last seen 3.2 s before)")
    m.sources = [SourceHealth(source=SourceHealth.SOURCE_GPS, last_seen=Time())]
    c.ok(f(m) is None, "gps_silence_s should be None when GPS was never heard (last_seen = 0)")
    m.sources = []
    c.ok(f(m) is None, "gps_silence_s should be None when there is no GPS entry")


NAV = {}


def run_navera():
    """player -> ros_gps_node -> NAVERA estimator -> your status_listener; then the player stops."""
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
            time.sleep(6)                      # the GNSS has stopped: > gps_timeout_s (3 s)
        NAV["out"] = bg.output()
    c.ok(NAV["fix"], "NAVERA never reached FIX with the player's GNSS — tell your teacher")
    return NAV["out"]


@c.test("TODO 7 — status_listener.py hears NAVERA say FIX from GPS, once, not 5 times per second",
        hint="7a: subscribe to NavStatus on TOPIC with self.on_status. 7b: compare (state, active_source) with "
             "self.last_key and log describe(msg) only when it changed.")
def _():
    out = run_navera()
    n_fix = out.count("FIX | source: GPS")
    c.ok(n_fix >= 1, "no line `FIX | source: GPS | GPS fix` in your node's output:\n" + out[-600:])
    c.ok(n_fix <= 2, f"`FIX | source: GPS` was printed {n_fix} times in a few seconds — log only on change")


@c.test("TODO 7 — when the GNSS stops: NO_FIX, and `GPS silent for X s` with X ≈ gps_timeout_s",
        hint="Course section 5 (detecting silence): when the (state, source) key changes and the new state is NO_FIX, use gps_silence_s() "
             "and the exact message format of the TODO comment. X should be close to the arbiter's GPS timeout "
             "(see its parameters), give or take one tick.")
def _():
    out = run_navera()
    c.ok("NO_FIX" in out and "stale" in out,
         "after the GNSS stopped, no line with NO_FIX and `GPS: stale (...)`:\n" + out[-600:])
    m = re.findall(r"GPS silent for ([\d.]+) s", out)
    c.ok(m, "no line `GPS silent for X.XX s` after NO_FIX:\n" + out[-500:])
    c.ok(2.9 <= float(m[-1]) <= 3.6, f"GPS silent for {m[-1]} s — expected between 3.0 and about 3.2 s (the window plus at most one tick)")


@c.test("report.md — Noise, Executors and NAVERA, with your numbers",
        hint="Keep the three headings, at least 40 words each. Noise must quote your 3 m distance ratio "
             "(e.g. 2.09); Executors must quote your single-thread max gap in ms; NAVERA must quote a "
             "silence value (3.xx s).")
def _():
    c.file_exists("report.md")
    txt = open("report.md", encoding="utf-8", errors="replace").read()
    secs = {}
    for title in ("Noise", "Executors", "NAVERA"):
        m = re.search(r"^##\s*" + title + r"\s*$(.*?)(?=^##\s|\Z)", txt, re.M | re.S)
        c.ok(m is not None, f"the heading `## {title}` is missing")
        body = re.sub(r"^\*(?=\S)[^*]+?\*\s*$", "", m.group(1), flags=re.M | re.S)
        words = len(re.findall(r"[A-Za-z0-9_.]+", body))
        c.ok(words >= 40, f"section {title} has {words} words of yours — write at least 40")
        secs[title] = body
    nums = lambda s: [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]
    c.ok(any(abs(x - 2.09) < 0.02 for x in nums(secs["Noise"])), "the Noise section does not quote the distance ratio (≈ 2.09)")
    c.ok(any(x >= 200 for x in nums(secs["Executors"])), "the Executors section does not quote the single-thread max gap (ms)")
    c.ok(any(2.9 <= x <= 3.6 for x in nums(secs["NAVERA"])), "the NAVERA section does not quote a measured silence (3.xx s)")


c.run()
