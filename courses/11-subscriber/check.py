import contextlib
import io
import math
import os
import re
import tempfile
import time

from academy_check import (Background, CheckFailed, Checker, explained, load_student, need, predicted,
                           publishers_ok, run, sh)

c = Checker()


def quiet(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def trip():
    return quiet("navera_lite.ros.trip_node")


def estimate_cls():
    (E,) = need(quiet("navera_lite.estimate"), "Estimate")
    return E


def answers(*names):
    return need(quiet("answers.py"), *names)


def number(v, name):
    if isinstance(v, bool) or isinstance(v, str) or v is None:
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def verdict(v, what):
    """update() must return a pair (bool, str)."""
    if v is None:
        raise CheckFailed(f"{what} returned None — update() is not written yet (TODO 1), or one of its paths has no "
                          "`return`")
    if not (isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], bool) and isinstance(v[1], str)):
        raise CheckFailed(f"{what} returned {v!r} — update() must return a pair (True or False, \"reason\")")
    return v


# ======================================================================== Session 1 — TODO 1–3 (no ROS)
QUITO = [(100.0, -0.2201, -78.5123), (101.0, -0.220037, -78.5122191), (103.5, -0.2195604, -78.5120302),
         (104.0, -0.2194705, -78.5119313)]
QUITO_DISTANCE_M = 83.2693


@c.test("TODO 1: update() accepts good fixes, remembers them and adds the distance",
        hint="Lesson §3 and the docstring: the first good fix is (True, \"first fix\"), the next ones (True, \"ok\"); "
             "append (stamp_s, lat, lon) to self.fixes and add the haversine distance from the previous accepted fix.")
def _():
    m, E = trip(), estimate_cls()
    (TC,) = need(m, "TripComputer")
    tc = TC()
    want = [(True, "first fix"), (True, "ok"), (True, "ok"), (True, "ok")]
    for (t, lat, lon), w in zip(QUITO, want):
        got = verdict(run(tc.update, E("gps", lat, lon, t)), f"update() of a good fix at t = {t}")
        c.ok(got == w, f"a good fix near Quito at t = {t} s gave {got}, expected {w}")
    fixes = list(tc.fixes)
    c.ok(len(fixes) == 4, f"self.fixes holds {len(fixes)} fixes after 4 good ones — append each accepted fix")
    last = tuple(fixes[-1]) if fixes else None
    c.ok(last is not None and len(last) == 3 and abs(last[0] - 104.0) < 1e-9 and abs(last[1] - QUITO[-1][1]) < 1e-9,
         f"the last element of self.fixes is {last!r}, expected (stamp_s, lat, lon) of the newest fix")
    c.near(tc.distance_m, QUITO_DISTANCE_M, 0.05, "self.distance_m after 4 good fixes near Quito")


REYKJAVIK_LON = -21.9426
REFUSALS = [  # (stamp, lat, lon, valid) → expected verdict; TripComputer(max_speed_mps=20.0, margin_m=10.0)
    ((50.0, 64.1466, REYKJAVIK_LON, True), (True, "first fix")),
    ((52.0, 64.1470047, REYKJAVIK_LON, True), (True, "ok")),            # 45 m in 2 s: gate 50 m
    ((53.0, 64.149298, REYKJAVIK_LON, True), (False, "jump")),          # 255 m from the last accepted in 1 s
    ((54.0, 64.1493879, REYKJAVIK_LON, True), (False, "jump")),         # 10 m from the REFUSED fix, 265 m from the accepted
    ((54.0, 64.1474454, REYKJAVIK_LON, True), (True, "ok")),            # 49 m in 2 s from the accepted fix
    ((54.0, 64.1474904, REYKJAVIK_LON, True), (False, "old fix")),      # SAME stamp as the last accepted: not newer
    ((53.5, 64.1473195, REYKJAVIK_LON, True), (False, "old fix")),      # late and 14 m behind: not a jump
    ((55.0, math.nan, REYKJAVIK_LON, False), (False, "no position")),   # both bad: the first rule wins
    ((56.0, 0.0, 0.0, True), (False, "bad position")),                  # Null Island
    ((56.0, 64.1476, math.inf, True), (False, "bad position")),
    ((56.0, 64.1477152, REYKJAVIK_LON, True), (True, "ok")),            # 30 m in 2 s
]
WHY_WRONG = {
    3: "the gate must measure from the last ACCEPTED fix, not from the refused one (and a refused fix is never "
       "appended to self.fixes)",
    4: "\"old fix\" compares with the last ACCEPTED fix's stamp (54.0 was refused, so 52.0 counts)",
    5: "a fix with the SAME stamp as the last accepted one is not newer: \"old fix\" (<=, not <)",
    6: "a late fix behind the vehicle is \"old fix\": test the stamp BEFORE the gate (lesson §3)",
    7: "when several rules are broken, the FIRST one in lesson §3's order gives the reason",
}


@c.test("TODO 1: update() refuses bad fixes with the first rule broken, and a refusal changes nothing",
        hint="The four rules in order: no position, bad position, old fix (vs the last ACCEPTED stamp), jump (mission 01's "
             "gate from the last ACCEPTED fix, with the time between the stamps). A refused fix only adds to self.refused "
             "and sets self.last_refusal.")
def _():
    m, E = trip(), estimate_cls()
    (TC,) = need(m, "TripComputer")
    tc = TC(max_speed_mps=20.0, margin_m=10.0)
    for i, ((t, lat, lon, valid), want) in enumerate(REFUSALS):
        got = verdict(run(tc.update, E("gps", lat, lon, t, valid=valid)), "update()")
        if got != want:
            why = WHY_WRONG.get(i, "compare with the docstring's rules")
            raise CheckFailed(f"fix {i + 1} of an unseen sequence (stamp {t}, lat {lat}, valid {valid}, "
                              f"v_max 20 m/s, margin 10 m) gave {got}, expected {want} — {why}")
    c.eq(len(list(tc.fixes)), 4, "the number of fixes remembered after 4 good and 7 bad ones")
    c.eq(tc.refused, 7, "self.refused")
    c.eq(tc.last_refusal, "bad position", "self.last_refusal")
    c.near(tc.distance_m, 124.0, 0.05, "self.distance_m (refused fixes must add nothing)")


SYDNEY = [(0.0, -33.8688, 151.2093), (2.0, -33.868755, 151.2095166), (3.5, -33.8686381, 151.2096358),
          (7.0, -33.8683324, 151.2097332), (8.0, -33.8682334, 151.2097007)]


@c.test("TODO 2: speed_window() measures the chord inside the window, on unseen fixes",
        hint="Lesson §4: keep the fixes whose time is ≥ newest − window_s (the boundary is included); the speed is the "
             "haversine distance from the OLDEST kept fix to the newest, divided by the time between them; fewer than 2 "
             "kept → None.")
def _():
    (sw,) = need(trip(), "speed_window")
    fixes = [tuple(f) for f in SYDNEY]
    for w, want in ((5.0, 10.0884), (6.0, 10.0731), (100.0, 9.1327)):
        got = run(sw, fixes, w)
        if got is None:
            raise CheckFailed(f"speed_window(5 fixes near Sydney, {w}) returned None — is TODO 2 written? At least 2 fixes "
                              "are in this window")
        extra = (" — the fix exactly window_s before the newest must be kept (≥, not >)" if w == 6.0 and
                 isinstance(got, (int, float)) and abs(got - 10.0884) < 1e-3 else "")
        try:
            c.near(got, want, 0.002, f"speed_window(5 irregular fixes near Sydney, {w})")
        except CheckFailed as e:
            raise CheckFailed(str(e) + extra)
    got = run(sw, fixes, 0.5)
    c.ok(got is None, f"speed_window(..., 0.5) returned {got!r}: only one fix is inside a 0.5 s window, so None")
    got = run(sw, fixes[:1], 5.0)
    c.ok(got is None, f"speed_window(one fix, 5.0) returned {got!r}, expected None")
    c.ok(fixes == [tuple(f) for f in SYDNEY], "speed_window() changed the list it was given — it must only read it")


@c.test("TODO 3: Watchdog.silent() before any message, at the threshold and after a new kick",
        hint="Lesson §5: True before the first kick (nothing ever came); True only when MORE than silence_s seconds "
             "passed since the last kick (>, not >=).")
def _():
    (W,) = need(trip(), "Watchdog")
    w = W(2.5)
    got = run(w.silent, 100.0)
    c.ok(got is not None, "Watchdog.silent() returned None — TODO 3 is not written yet")
    c.ok(got is True, f"Watchdog(2.5).silent(100.0) before any kick returned {got!r}, expected True (nothing ever came)")
    w.kick(100.0)
    for now, want in ((102.5, False), (102.6, True)):
        got = run(w.silent, now)
        c.ok(got is want, f"after kick(100.0), silent({now}) returned {got!r}, expected {want}")
    w.kick(103.0)
    got = run(w.silent, 104.0)
    c.ok(got is False, f"after a new kick(103.0), silent(104.0) returned {got!r}, expected False")


@c.test("Step 0: the polling bug, counted (polling.py)",
        hint="Run the three commands of Step 0 and copy the DROPPED and DOUBLED counts; EXPLAIN_POLLING: jitter, and "
             "why on arrival sends each position once.")
def _():
    p, d5, u5, u10, ex = answers("PREDICT_POLL", "DROPPED_5HZ", "DOUBLED_5HZ", "DOUBLED_10HZ", "EXPLAIN_POLLING")
    predicted("PREDICT_POLL", p)
    for name, v, want in (("DROPPED_5HZ", d5, 30), ("DOUBLED_5HZ", u5, 30), ("DOUBLED_10HZ", u10, 301)):
        c.ok(number(v, name) == want, f"{name} = {v} is not what `python3 polling.py` prints"
                                     + (" with --poll-hz 10" if name == "DOUBLED_10HZ" else " with the defaults"))
    explained("EXPLAIN_POLLING", ex,
              ([r"jitter", r"late", r"early", r"irregular", r"not exact", r"vary", r"varies", r"clock", r"phase"],
               "what the jitter does (a late position misses its tick)"),
              ([r"arriv", r"callback", r"once", r"each position", r"every position"],
               "why forwarding on arrival sends each position exactly once"))


@c.test("Step 4: the noisy drive — noise and delay of your speed (run_trip.py drive)",
        hint="Run `python3 run_trip.py drive` after `python3 run_trip.py test` is all ✔, and copy its numbers. "
             "EXPLAIN_WINDOW: what the 10 s window buys (noise) and what it costs (delay).")
def _():
    p, i_std, w_std, parked, lag, ex = answers("PREDICT_NOISE", "INSTANT_STD_MPS", "WINDOW_STD_MPS",
                                               "PARKED_INSTANT_MPS", "LAG_S", "EXPLAIN_WINDOW")
    predicted("PREDICT_NOISE", p)
    for name, v, want, tol in (("INSTANT_STD_MPS", i_std, 4.11, 0.02), ("WINDOW_STD_MPS", w_std, 0.40, 0.011),
                               ("PARKED_INSTANT_MPS", parked, 5.51, 0.02), ("LAG_S", lag, 9.0, 0.01)):
        x = number(v, name)
        c.ok(abs(x - want) <= tol, f"{name} = {x} is not what `python3 run_trip.py drive` prints with a correct "
                                   "trip computer — run it again after `python3 run_trip.py test` is all ✔")
    explained("EXPLAIN_WINDOW", ex,
              ([r"nois", r"std", r"spread", r"smooth", r"averag", r"precis", r"stable", r"jump"], "what the window buys (less noise)"),
              ([r"delay", r"lag", r"late", r"slow", r"behind", r"react", r"takes? (about )?\d", r"past"], "what it costs (a delay)"))


# ======================================================================== Session 2 — on the wire
NODE = "python3 -m navera_lite.ros.trip_node"
TODO_MSG = {"TODO 4": "TripNode.listen() is still the TODO 4 stub", "TODO 5": "TripNode.on_fix() is still the TODO 5 stub"}


def start_trip():
    """Background trip node, with a plain sentence when it dies at start."""
    bg = Background(NODE, settle=2.5)
    try:
        bg.__enter__()
    except CheckFailed as e:
        s = str(e)
        for k, v in TODO_MSG.items():
            if k in s:
                raise CheckFailed(f"your trip node stops at start: {v}")
        last = [line for line in s.splitlines() if line.strip()][-1:] or ["?"]
        raise CheckFailed(f"your trip node stops at start: {last[0].strip()} — run `{NODE}` to see the whole error")
    return bg


def no_leftovers():
    for topic in ("/navera_lite/trip", "/navera_lite/fix/gps"):
        publishers_ok(topic, expected=0, tries=1)


@c.test("TODO 4: the trip node subscribes to navera_lite/fix/gps",
        hint="Lesson §1: self.sub = self.create_subscription(<type>, \"navera_lite/fix/gps\", self.on_fix, FIX_QOS) — the "
             "callback without parentheses. Check with `ros2 node info /trip`.")
def _():
    no_leftovers()
    bg = start_trip()
    try:
        out = ""
        for _ in range(3):
            code, out = sh("timeout 20 ros2 node info /trip --no-daemon --spin-time 2", timeout=30)
            if "Subscribers:" in out:
                break
        subs = out.split("Subscribers:", 1)[1].split("Publishers:", 1)[0] if "Subscribers:" in out else ""
        c.ok("Subscribers:" in out, "`ros2 node info /trip` did not find your node — is it named \"trip\"? (it is, unless "
                                     "you changed __init__)")
        c.ok("/navera_lite/fix/gps: sensor_msgs/msg/NavSatFix" in subs,
             "your trip node does not subscribe to /navera_lite/fix/gps with the type NavSatFix. It subscribes to: "
             + (", ".join(s.strip() for s in subs.splitlines() if s.strip() and "parameter_events" not in s) or "nothing"))
    finally:
        bg.__exit__(None, None, None)


def scenario_csv():
    """An unseen scenario (inputs only; the expected outputs stay in this file): Reykjavik, 8 m north per row."""
    lat0, lon0, m_per_deg = 64.1466, -21.9426, 111194.93
    lines = ["t_s,source,lat,lon,a,b,c,cov_type,valid,delay_s"]
    for k in range(14):
        north, east, valid, delay = 8.0 * k, 0.0, 1, 0.0
        if k == 3:
            east = 2000.0                                  # jump
        if k == 6:
            valid = 0                                      # no position
        if k == 9:
            north, delay = 40.0, 2.0                       # measured 2 s earlier: old fix
        lat = lat0 + north / m_per_deg
        lon = lon0 + east / (m_per_deg * math.cos(math.radians(lat0)))
        lat_s = "nan" if k == 12 else f"{lat:.7f}"         # bad position
        lines.append(f"{float(k):.1f},gps,{lat_s},{lon:.7f},4.0,0.0,4.0,1,{valid},{delay}")
    return "\n".join(lines) + "\n"


def evidence(path, step):
    """The measurements a given tool logged in out/ (read as JSON, never executed)."""
    import json
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        raise CheckFailed(f"{path} is missing: it is written when you run {step}. Run that step, then copy its numbers")
    if not isinstance(data, list):
        raise CheckFailed(f"{path} is damaged: delete it and run {step} again")
    return data


def values(msg):
    return {kv.key: kv.value for kv in msg.values}


def collect(topic, until, timeout):
    """Messages of `topic` (DiagnosticStatus) until until(list) is True or timeout; returns the list."""
    import rclpy
    from diagnostic_msgs.msg import DiagnosticStatus
    from rclpy.qos import qos_profile_sensor_data
    started = not rclpy.ok()
    if started:
        rclpy.init()
    node = rclpy.create_node("academy_checker_trip")
    got = []
    node.create_subscription(DiagnosticStatus, topic, got.append, qos_profile_sensor_data)
    end = time.time() + timeout
    try:
        while time.time() < end and not until(got):
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.destroy_node()
        if started:
            rclpy.shutdown()
    return got


@c.test("TODO 5: on the wire, the trip node judges unseen fixes and notices when they stop",
        hint="Lesson §1 and §5: in on_fix, kick the watchdog with self.now_s(), give self.computer.update() an Estimate "
             "(convert.from_navsatfix(msg, source=\"gps\", ...)), and log a warning when it is refused.")
def _():
    no_leftovers()
    fd, path = tempfile.mkstemp(suffix=".csv", prefix="scenario_", dir=".")
    with os.fdopen(fd, "w") as f:
        f.write(scenario_csv())
    bg = start_trip()
    try:
        replay = Background(f"python3 -m navera_lite.ros.replay_node --ros-args -p file:={path} -p loop:=false "
                            "-p rate:=2.0 -p start_delay_s:=3.0 -p imu_hz:=0.0", settle=0.5)
        with replay:
            def done(msgs):
                return any(values(m).get("fixes") == "10" and values(m).get("refused") == "4" for m in msgs) \
                    or bg.p.poll() is not None
            msgs = collect("/navera_lite/trip", done, 20.0)
            if bg.p.poll() is not None:
                out = bg.p.stdout.read()
                for k, v in TODO_MSG.items():
                    if k in out:
                        raise CheckFailed(f"your trip node died when the first fix arrived: {v}")
                last = [line for line in out.splitlines() if line.strip()][-1:] or ["?"]
                extra = (" — update() wants an Estimate: convert the message with from_navsatfix(msg, source=\"gps\", "
                         "now_s=...) first" if "'NavSatFix' object has no attribute" in out else "")
                raise CheckFailed(f"your trip node died during the scenario: {last[0].strip()}{extra}")
            c.ok(msgs, "no message on /navera_lite/trip in 20 s — does your node still start the 1 Hz timer?")
            seen = values(msgs[-1])
            talking = [values(m) for m in msgs if values(m).get("fixes") not in (None, "0")]
            c.ok(talking, f"your trip node accepted no fix of the scenario (last values: {seen}) — is on_fix written, "
                          "and does it give the fix to self.computer.update()?")
            c.ok(any(v.get("silent") == "false" for v in talking),
                 "the trip node said silent: true while fixes were coming — on_fix must kick the watchdog with self.now_s()")
            final = seen
            c.ok(final.get("fixes") == "10" and final.get("refused") == "4",
                 f"after an unseen scenario of 14 fixes (4 bad ones) your node says fixes {final.get('fixes')}, "
                 f"refused {final.get('refused')}, expected other numbers — fix checks 1–2 (update) first; if they pass, "
                 "does on_fix give update() the message's stamp (from_navsatfix), not the arrival time?")
            c.eq(final.get("last_refusal"), "bad position", "last_refusal at the end of the unseen scenario")
            c.near(float(final.get("distance_m", "nan") or "nan"), 104.0, 0.5, "distance_m of the unseen scenario")
            later = collect("/navera_lite/trip", lambda ms: any(values(m).get("silent") == "true" for m in ms), 8.0)
            c.ok(any(values(m).get("silent") == "true" for m in later),
                 "8 s after the last fix your trip node still does not say silent: true — is Watchdog.silent() right, "
                 "and does on_fix kick it with self.now_s()?")
    finally:
        bg.__exit__(None, None, None)
        with contextlib.suppress(OSError):
            os.remove(path)
    log = bg.output()
    warned = [line for line in log.splitlines() if "WARN" in line and
              any(r in line for r in ("jump", "old fix", "no position", "bad position"))]
    c.ok(len(warned) >= 4, f"your node refused 4 fixes but logged {len(warned)} warning(s) with the reason: on_fix must "
                           "self.get_logger().warn(...) with the reason each time update() refuses a fix")


@c.test("Step 6: bad_fixes.csv through your trip node — the numbers",
        hint="Run Step 6 (a fresh trip node, then the replay with -p loop:=false) and copy fixes, refused, last_refusal and "
             "distance_m from `ros2 topic echo /navera_lite/trip … --once`.")
def _():
    p, n, r, last, dist = answers("PREDICT_TRIP", "TRIP_FIXES", "TRIP_REFUSED", "TRIP_LAST_REFUSAL", "TRIP_DISTANCE_M")
    predicted("PREDICT_TRIP", p)
    c.ok(number(n, "TRIP_FIXES") == 16 and number(r, "TRIP_REFUSED") == 4,
         f"TRIP_FIXES = {n} and TRIP_REFUSED = {r} are not what a correct trip node shows at the end of bad_fixes.csv "
         "(start a FRESH trip node before the replay, and use -p loop:=false)")
    c.ok(isinstance(last, str) and last.strip().lower() == "old fix",
         f"TRIP_LAST_REFUSAL = {last!r} is not the last reason of the scenario (copy it with quotes)")
    c.ok(abs(number(dist, "TRIP_DISTANCE_M") - 190.0) <= 1.0, f"TRIP_DISTANCE_M = {dist} is not what the node shows")


@c.test("Step 7: the blocking callback, measured (blocking_demo.py)",
        hint="Run single and multi with the GPS at 5 Hz and copy the longest timer gaps and the max age of the multi run. "
             "EXPLAIN_BLOCKING: threads, callback groups, and why the fixes still pile up.")
def _():
    p, g1, g2, age, ex = answers("PREDICT_BLOCKING", "GAP_SINGLE_MS", "GAP_MULTI_MS", "AGE_MULTI_S", "EXPLAIN_BLOCKING")
    predicted("PREDICT_BLOCKING", p)
    g1, g2, age = number(g1, "GAP_SINGLE_MS"), number(g2, "GAP_MULTI_MS"), number(age, "AGE_MULTI_S")
    c.ok(250 <= g1 <= 900, f"GAP_SINGLE_MS = {g1:g} ms is not a gap the single run can give with 0.3 s of work per "
                            "fix — was the GPS running at 5 Hz, and is it in milliseconds?")
    c.ok(90 <= g2 <= 200, f"GAP_MULTI_MS = {g2:g} ms: the multi run keeps the 10 Hz timer close to 100 ms — copy the "
                           "`longest timer gap` of `python3 blocking_demo.py multi`")
    c.ok(1.3 <= age <= 2.7, f"AGE_MULTI_S = {age:g} s is not the `max` age of the multi run (GPS at 5 Hz, in seconds)")
    runs = evidence("out/blocking.json", "Step 7 (blocking_demo.py)")
    single = [r for r in runs if r.get("mode") == "single" and r.get("work_s") == 0.3 and r.get("gap_ms") is not None]
    multi = [r for r in runs if r.get("mode") == "multi" and r.get("work_s") == 0.3 and r.get("gap_ms") is not None]
    c.ok(any(abs(r["gap_ms"] - g1) <= 1 for r in single),
         f"GAP_SINGLE_MS = {g1:g} is not the longest gap of one of your `single` runs (out/blocking.json lists them)")
    c.ok(any(abs(r["gap_ms"] - g2) <= 1 and abs(r["max_age_s"] - age) <= 0.011 for r in multi),
         f"GAP_MULTI_MS = {g2:g} and AGE_MULTI_S = {age:g} are not the numbers of one of your `multi` runs "
         "(out/blocking.json lists them)")
    explained("EXPLAIN_BLOCKING", ex,
              ([r"thread"], "the threads"),
              ([r"group", r"exclusive"], "the callback groups"),
              ([r"queue", r"old", r"\bage", r"overload", r"faster than", r"ρ", r"rho", r"utili[sz]ation", r"0\.3",
                r"0\.2", r"pile", r"can.?t keep up", r"cannot keep up", r"too slow"],
               "why the fixes still pile up (0.3 s of work every 0.2 s)"))


@c.test("Step 8: the judge notices a silent GPS — your measurements",
        hint="With arbiter_v0, status_listener.py and the GPS running, stop the GPS (Ctrl+C) and copy the `GPS silent for "
             "… s` values (at least 2) into SILENCE_S as a list of numbers. EXPLAIN_SILENCE: the 3 s timeout, the 5 Hz "
             "tick, and your node's 1 Hz timer.")
def _():
    p, vals, ex = answers("PREDICT_SILENCE", "SILENCE_S", "EXPLAIN_SILENCE")
    predicted("PREDICT_SILENCE", p)
    c.ok(isinstance(vals, (list, tuple)) and len(vals) >= 2,
         f"SILENCE_S = {vals!r}: write a list of at least 2 numbers, like [7.25, 7.31] (your values)")
    xs = [number(v, "each value of SILENCE_S") for v in vals]
    c.ok(xs[:2] != [7.25, 7.31], "SILENCE_S still holds the example values: write YOUR measurements")
    big = [x for x in xs if x > 5]
    c.ok(not big, f"{big}: a value above 5 s means the listener measured from an old fix (the GPS was stopped too soon "
                  "after FIX) — run that cycle again, letting the GPS run 5 s after FIX")
    logged = evidence("out/silence.json", "Step 8 (status_listener.py)")
    missing = [x for x in xs if not any(isinstance(v, (int, float)) and abs(v - x) <= 0.006 for v in logged)]
    c.ok(not missing, f"{missing} were not printed by your status_listener.py runs (out/silence.json lists what it "
                      "measured): copy YOUR values")
    bad = [x for x in xs if not 2.95 <= x <= 3.7]
    c.ok(not bad, f"{bad} cannot be a `GPS silent for … s` value of status_listener.py with arbiter v0 "
                  "(gps_timeout_s 3.0) — copy the numbers it printed")
    explained("EXPLAIN_SILENCE", ex,
              ([r"timer", r"tick", r"5 ?hz", r"0\.2", r"five times"], "the judge's 5 Hz tick"),
              ([r"3(\.0)? ?s", r"timeout", r"stale", r"three seconds", r"gps_timeout"], "the 3 s timeout"),
              ([r"1 ?hz", r"once a second", r"every second", r"one second", r"\b1(\.0)? ?s\b", r"slower", r"once per second"],
               "why your trip node is later (its watchdog is checked once a second)"))


c.milestone("trip-computer", "TODO 1:", "TODO 2:", "TODO 3:", "Step 0:", "Step 4:",
            label="Session 1 done: Trip computer badge earned")
c.milestone("watchdog", "TODO", "Step", label="Mission complete: Trip computer and Watchdog badges earned")
c.run()
