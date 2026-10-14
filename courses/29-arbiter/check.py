import contextlib
import io
import json
import math
import os
import re
import tempfile
import time

from academy_check import (Background, CheckFailed, Checker, explained, hidden, is_stub, load_student, need,
                           predicted, publishers_ok, run)

c = Checker()

# ---------------------------------------------------------------- expected values
# Unseen situations and the course reference's answers: courses/29-arbiter/hidden/cases.json, written by
# solutions/29-arbiter/make_hidden.py with the reference judge (check.py never runs the reference).
CASES = json.loads(hidden("cases.json"))
DEFAULTS = {"gps_timeout_s": 3.0, "day_timeout_s": 5.0, "night_timeout_s": 5.0, "celestial_timeout_s": 45.0,
            "future_tolerance_s": 0.5, "fix_max_sigma_m": 25.0, "min_stated_sigma_m": 0.01,
            "switch_holdoff_s": 2.0, "tick_hz": 5.0, "max_speed_mps": 100.0, "gps_jump_margin_m": 50.0,
            "vehicle": "drone"}
CLOCK0, TICK = 1000.0, 0.2
# the race (datasets/29-arbiter/race.csv), course reference (make_dataset.py): samples and switches
RACE_SAMPLES = [(0.5, "STARTING", None, "no position received yet"), (2.0, "FIX", "gps", "gps: σ 3.0 m"),
                (5.0, "FIX", "gps", "gps: σ 3.0 m"), (9.5, "FIX", "gps", "gps: σ 3.0 m"),
                (12.0, "DEGRADED", "day", "day: σ 30.0 m > 25.0 m"), (15.0, "DEGRADED", "day", "day: σ 30.0 m > 25.0 m"),
                (16.5, "DEGRADED", "gps", "gps: σ 40.0 m > 25.0 m"), (18.5, "DEGRADED", "day", "day: σ 30.0 m > 25.0 m"),
                (21.0, "DEGRADED", "day", "day: σ 30.0 m > 25.0 m"), (27.0, "DEGRADED", "night", "night: σ unknown"),
                (30.5, "NO_FIX", None, "no usable source (gps: no position; last fix refused: jump 5045 m > 350 m in "
                 "3.0 s; day: stale (8.9 s > 5.0 s); night: stale (7.4 s > 5.0 s); celestial: refused: from the "
                 "future (60.0 s ahead))")]
RACE_SWITCHES = [(1.0, None, "gps"), (11.2, "gps", "day"), (16.0, "day", "gps"), (17.5, "gps", "day"),
                 (26.6, "day", "night"), (28.2, "night", None)]
SWITCH_TOL_S = 0.35
# experiment.py with a correct judge (seeded, the same for everybody): hold-off → (switches/min, share, unused s)
HOLD = {0.0: (31.1, 0.624, 0.0), 0.5: (24.5, 0.4983, 75.4), 1.0: (20.3, 0.3937, 138.2),
        2.0: (12.1, 0.2427, 228.8), 4.0: (4.4, 0.0993, 314.8), 8.0: (0.8, 0.034, 354.0)}
FUSION = {"claimed_sigma_m": 2.4807, "true_sigma_m": 2.6576, "spoofed_fused_m": 1476.92}
V0_FLAP_SWITCHES = 29          # judge_lab.py play flapping.csv --v0: "changes of winner: 29"
REPORT_HEADS = ["## 1. The hold-off", "## 2. The freshness window", "## 3. Selection or fusion",
                "## 4. The door, the race and your design"]


def quiet(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def judge(*names):
    """The student's arbiter module, after checking the named TODOs are written."""
    m = quiet("navera_lite.arbiter")
    for f in need(m, *names):
        if is_stub(f):
            raise CheckFailed(f"{f.__name__}() is not written yet (it is still the TODO stub in navera_lite/arbiter.py)")
    return m


def arbiter_class(*methods):
    m = quiet("navera_lite.arbiter")
    (A,) = need(m, "Arbiter")
    for meth in methods or ("receive", "step"):
        if is_stub(getattr(A, meth)):
            todo = 4 if meth == "receive" else 5
            raise CheckFailed(f"Arbiter.{meth}() is not written yet (TODO {todo} in navera_lite/arbiter.py)")
    return m


def answers():
    return quiet("answers.py")


TIPS = [("KeyError", " — since[...] of a source that is not in since? track_since (TODO 2) must give every candidate "
                     "its instant before pick() reads it; or a cfg key misspelt (the names of navera_lite.yaml)"),
        ("'NoneType' object is not iterable", " — one of your functions returned None where a list or a pair was "
                                              "expected: is that TODO written?"),
        ("'NoneType' object has no attribute", " — a TODO returns None (not written yet?), or self.latest.get() of a "
                                               "source that sent nothing"),
        ("unhashable", " — the dict keys are the source names (\"gps\", …), not an Estimate or a list")]


def go(fn, *args, **kw):
    """run() with one more sentence for this mission's common errors."""
    try:
        return run(fn, *args, **kw)
    except CheckFailed as e:
        msg = str(e)
        for key, tip in TIPS:
            if key in msg:
                raise CheckFailed(msg + tip)
        raise


def cfg(over=None):
    d = dict(DEFAULTS)
    d.update(over or {})
    return d


def make_est(m_est, s):
    return m_est.Estimate(s["source"], s["lat"], s["lon"], s["stamp_s"], cov=tuple(s["cov"]), cov_type=s["cov_type"],
                          valid=s["valid"])


def describe(s):
    """An estimate spec in a few words, for the messages."""
    if not s["valid"]:
        what = "says no position"
    elif not (math.isfinite(s["lat"]) and math.isfinite(s["lon"])):
        what = "a NaN position"
    elif s["cov_type"] == 0:
        what = "σ unknown"
    else:
        what = f"σ {math.sqrt(s['cov'][0]):g} m"
    return f"{s['source']} stamped {s['stamp_s']:g} ({what})"


def norm(text):
    return re.sub(r"[0-9.]+", "#", text or "")


def drive(m_arb, m_est, rows, until, c_):
    """The checker's own clock (as judge_lab.simulate and the ROS node): on each arrival receive() then step();
    between arrivals step() every 0.2 s. Returns ([t, state, source, reason] per decision, switches)."""
    a = m_arb.Arbiter(c_)
    out, i, k = [], 0, 0
    while True:
        tk = round(k * TICK, 6)
        if i < len(rows) and rows[i]["t_s"] <= tk + 1e-9:
            r = rows[i]
            t, now = r["t_s"], CLOCK0 + r["t_s"]
            cov = (r["a"], r["b"], 0.0, r["b"], r["c"], 0.0, 0.0, 0.0, 0.0)
            e = m_est.Estimate(r["source"], r["lat"], r["lon"], now - r["delay_s"], cov=cov, cov_type=r["cov_type"],
                               valid=bool(r["valid"]))
            a.receive(e, now)
            d = a.step(now)
            i += 1
        elif tk <= until + 1e-9:
            t = tk
            d = a.step(CLOCK0 + tk)
            k += 1
        else:
            sw = [[round(s[0] - CLOCK0, 6), s[1], s[2]] for s in a.switches]
            return out, sw
        if d is None:
            raise CheckFailed("Arbiter.step() returned None (TODO 5)")
        out.append([t, d.state, d.source, d.reason])


def summary(out):
    res, last = [], None
    for t, state, src, reason in out:
        if (state, src) != last:
            res.append([t, state, src, reason])
            last = (state, src)
    return res


def compare_scenario(sc, label):
    m_arb = arbiter_class()
    m_est = quiet("navera_lite.estimate")
    out, sw = go(drive, m_arb, m_est, sc["rows"], sc["until"], cfg(), seconds=90)
    mine = summary(out)
    want = sc["summary"]
    for k, w in enumerate(want):
        g = mine[k] if k < len(mine) else None
        if g is None or (g[1], g[2]) != (w[1], w[2]) or abs(g[0] - w[0]) > 1e-6:
            yours = "nothing more" if g is None else f"{g[1]} {g[2] or ''} ({g[3]}) at t = {g[0]:.1f} s"
            before = mine[k - 1] if 0 < k <= len(mine) else None
            raise CheckFailed(f"{label}: your judge's change n°{k + 1} is {yours}; the reference's change n°{k + 1} "
                              "is another decision or comes at another moment."
                              + (f" Until then both said {before[1]} {before[2] or ''} (since t = {before[0]:.1f} s)."
                                 if before else "")
                              + " Replay a similar case with `python3 judge_lab.py play` and explain each change.")
        if w[1] in ("FIX", "DEGRADED") and g[3] != w[3]:
            raise CheckFailed(f"{label}: at t = {g[0]:.1f} s your reason is {g[3]!r}: it must be "
                              f"\"<source>: <classify's words>\", e.g. \"gps: σ 3.0 m\" (TODO 5)")
    if len(mine) > len(want):
        g = mine[len(want)]
        raise CheckFailed(f"{label}: your judge changes once more than it should: {g[1]} {g[2] or ''} ({g[3]}) at "
                          f"t = {g[0]:.1f} s")
    if [[round(x[0], 6), x[1], x[2]] for x in sw] != [[round(x[0], 6), x[1], x[2]] for x in sc["switches"]]:
        raise CheckFailed(f"{label}: the decisions are right, but self.switches is not the list of every change of "
                          f"winner (now_s, old, new): yours has {len(sw)} entr(ies), e.g. {sw[:2]!r} (TODO 5)")


# ================================================================================================ session 1
@c.test("TODO 1 — candidates() on situations it has never seen",
        hint="Lesson §2: a source competes when its stored estimate is eligible (estimate.eligible, with THESE "
             "settings) — and the list is in priority order (estimate.SOURCES), whatever the dict's order.")
def _():
    m = judge("candidates")
    m_est = quiet("navera_lite.estimate")
    for case in CASES["candidates"]:
        latest = {s["source"]: make_est(m_est, s) for s in case["latest"]}
        got = go(m.candidates, latest, case["now"], cfg(case["cfg"]))
        if not isinstance(got, (list, tuple)):
            raise CheckFailed(f"candidates() must return a list of source names, got {got!r}")
        if list(got) != case["want"]:
            what = "; ".join(describe(s) for s in case["latest"])
            extra = f" (settings changed: {case['cfg']})" if case["cfg"] else ""
            raise CheckFailed(f"at now = {case['now']:g} s with {what}{extra}: you returned {list(got)!r}. Which of "
                              "them does estimate.eligible() accept, and in which order must they be?")


@c.test("TODO 2 — track_since() remembers only an unbroken eligibility",
        hint="Lesson §4 🧰: a candidate already in since keeps its instant, a new one gets now_s, every other source "
             "is forgotten. Return a new dict.")
def _():
    m = judge("track_since")
    for case in CASES["track_since"]:
        got = go(m.track_since, dict(case["since"]), list(case["cands"]), case["now"])
        if not isinstance(got, dict):
            raise CheckFailed(f"track_since() must return a dict source → time, got {got!r}")
        if got != case["want"]:
            raise CheckFailed(f"track_since({case['since']!r}, {case['cands']!r}, {case['now']:g}) returned {got!r}: "
                              "which sources must stay, which instants must be kept, which are new?")


@c.test("TODO 3 — pick(): priority with a hold-off, on unseen cases",
        hint="Lesson §4: a source replaces the current winner only after switch_holdoff_s of unbroken eligibility "
             "(≥, boundary included); a lost winner is replaced at once by the first candidate; read the hold-off "
             "from cfg (one case uses 3.0 s, one 0.0 s).")
def _():
    m = judge("pick")
    for case in CASES["pick"]:
        got = go(m.pick, list(case["cands"]), case["current"], dict(case["since"]), case["now"], cfg(case["cfg"]))
        if got != case["want"]:
            h = cfg(case["cfg"])["switch_holdoff_s"]
            raise CheckFailed(f"pick({case['cands']!r}, current={case['current']!r}, since={case['since']!r}, "
                              f"now={case['now']:g}) with a hold-off of {h:g} s returned {got!r}. Who has waited "
                              "long enough, and is the current winner still a candidate?")


@c.test("TODO 4 — receive(): the door refuses what it must and stores the rest",
        hint="The docstring lists the refusals in their order: unknown source, stamp in the future (beyond "
             "future_tolerance_s), not newer than the stored fix (old news), a GPS jump (self.gate). A refused fix is "
             "never stored; refused[source] remembers a future or jump refusal until a fix of that source is stored.")
def _():
    m = arbiter_class("receive")
    m_est = quiet("navera_lite.estimate")
    keys = {"from the future": "future", "old news": "old news", "jump": "jump", "unknown source": "unknown"}
    for seq in CASES["receive"]:
        a = m.Arbiter(cfg(seq["cfg"]))
        for k, ((s, now), want) in enumerate(zip(seq["steps"], seq["want"])):
            got = go(a.receive, make_est(m_est, s), now)
            if not (isinstance(got, (tuple, list)) and len(got) == 2 and isinstance(got[0], bool)):
                raise CheckFailed(f"receive() must return a pair (stored, why) like (False, \"old news\"), got {got!r}")
            label = f"\"{seq['name']}\", fix n°{k + 1} ({describe(s)}, now {now:g})"
            if got[0] != want["stored"]:
                raise CheckFailed(f"{label}: you returned {tuple(got)!r} — it must be "
                                  f"{'stored' if want['stored'] else 'refused'}")
            kw = next((v for k_, v in keys.items() if want["why"].startswith(k_)), "stored")
            if kw not in str(got[1]).lower():
                raise CheckFailed(f"{label}: the reason {got[1]!r} must say \"{kw}\" (the docstring's words)")
            latest = {name: e.stamp_s for name, e in dict(a.latest).items()}
            if latest != want["latest"]:
                raise CheckFailed(f"{label}: after it, self.latest holds the stamps {latest!r} — a refused fix must "
                                  "not be stored, a stored one replaces the older one of its source")
            if sorted(dict(a.refused)) != want["refused"]:
                raise CheckFailed(f"{label}: after it, self.refused has the sources {sorted(dict(a.refused))!r}, "
                                  f"it should have {want['refused']!r}")


@c.test("TODO 4 — a fix from the future never comes back (2 unseen scenarios)",
        hint="Lesson §3: refuse a fix stamped in the future AT THE DOOR, before it is stored and before the jump gate "
             "sees it — stored, it sets the order (honest fixes become \"old news\") and wins when the clock "
             "reaches its stamp; given to the gate, it becomes the trusted fix.")
def _():
    for sc in CASES["scenarios"]:
        if sc["name"] in ("b", "c"):
            label = {"b": "GPS dies after one fix stamped 15 s ahead (celestial only afterwards)",
                     "c": "a vehicle at 25 m/s, honest GPS on, ONE GPS fix stamped 12 s ahead and 600 m off"}[sc["name"]]
            compare_scenario(sc, label)


@c.test("TODO 5 — step(): states, reasons and the switch log",
        hint="The docstring's table: STARTING only before anything arrives (a refused fix counts as arrived), NO_FIX "
             "with no_fix_reason(), else classify() of estimate.stated_sigma(); every change of winner, None "
             "included, goes to self.switches as (now_s, old, new).")
def _():
    m = arbiter_class()
    m_est = quiet("navera_lite.estimate")
    for seq in CASES["step"]:
        a = m.Arbiter(cfg(seq["cfg"]))
        got = []
        for op in seq["ops"]:
            if op[0] == "r":
                go(a.receive, make_est(m_est, op[1]), op[2])
            else:
                d = go(a.step, op[1])
                if d is None:
                    raise CheckFailed("step() returned None: it must return a Decision (TODO 5)")
                got.append((op[1], d.state, d.source, d.reason, d.switched, d.sigma_m))
        for (t, state, src, reason, sw, sig), w in zip(got, seq["want"]["decisions"]):
            label = f"\"{seq['name']}\", step at t = {t:g}"
            if (state, src) != (w["state"], w["source"]):
                if state == "STARTING" or w["state"] == "STARTING":
                    raise CheckFailed(f"{label}: you decided {state}. STARTING means nothing received yet: nothing "
                                      "stored AND nothing refused (a refused fix has arrived)")
                raise CheckFailed(f"{label}: you decided {state} on {src!r}. Which rule of the docstring's table "
                                  "applies, and does a source wait for the hold-off here?")
            if w["state"] in ("FIX", "DEGRADED", "STARTING") and reason != w["reason"]:
                raise CheckFailed(f"{label}: the reason {reason!r} is not the docstring's wording")
            if w["state"] == "NO_FIX" and norm(reason) != norm(w["reason"]):
                raise CheckFailed(f"{label}: NO_FIX's reason must be no_fix_reason(sources), got {reason!r}")
            if bool(sw) != w["switched"]:
                raise CheckFailed(f"{label}: switched is {sw!r}: True only when the winner changed at this step")
            if (sig is None) != (w["sigma_m"] is None) or (sig is not None and abs(sig - w["sigma_m"]) > 1e-6):
                raise CheckFailed(f"{label}: sigma_m is {sig!r}: the σ the winner states (estimate.stated_sigma)")
        sws = [list(x) for x in a.switches]
        if [[round(x[0], 6), x[1], x[2]] for x in sws] != [[round(x[0], 6), x[1], x[2]] for x in seq["want"]["switches"]]:
            raise CheckFailed(f"\"{seq['name']}\": self.switches is {sws!r} — every change of winner as "
                              "(now_s, old, new), None included")


@c.test("TODOs 1–5 — your judge on an unseen 36 s flight",
        hint="A flapping GPS, a day vision that states 18 m, a GPS at σ 30 m, a 1 km jump, night and celestial "
             "fixes: replay your own variants with `python3 judge_lab.py play FILE` until each change is explained.")
def _():
    sc = next(s for s in CASES["scenarios"] if s["name"] == "a")
    compare_scenario(sc, "the unseen flight")


@c.test("Step 0 — arbiter v0 on a flapping GPS",
        hint="Run `python3 judge_lab.py play /data/academy/29-arbiter/flapping.csv --v0` and copy the number after "
             "\"changes of winner:\". PREDICT_FLAP is your guess before the run.")
def _():
    a = answers()
    predicted("PREDICT_FLAP", getattr(a, "PREDICT_FLAP", ""))
    v = getattr(a, "V0_FLAP_SWITCHES", None)
    if isinstance(v, bool) or not isinstance(v, int):
        raise CheckFailed(f"V0_FLAP_SWITCHES should be a whole number without quotes, got {v!r}")
    if v != V0_FLAP_SWITCHES:
        raise CheckFailed(f"V0_FLAP_SWITCHES = {v}: that is not what judge_lab.py prints for arbiter v0 (--v0) on "
                          "flapping.csv — copy the number after \"changes of winner:\"")


@c.test("Step 5 — the door left open",
        hint="Predict first, then run `python3 judge_lab.py play /data/academy/29-arbiter/lockout.csv --open-door` "
             "and explain both effects: what happened to the honest fixes, and why an old position came back as FIX.")
def _():
    a = answers()
    predicted("PREDICT_LOCKOUT", getattr(a, "PREDICT_LOCKOUT", ""))
    explained("EXPLAIN_LOCKOUT", getattr(a, "EXPLAIN_LOCKOUT", ""),
              ([r"old news", r"older", r"newer", r"drop", r"ignor", r"refus", r"locked", r"lock", r"order", r"thrown",
                r"discard", r"rejected", r"blocked"], "what happened to the honest GPS fixes (and why)"),
              ([r"came back", r"come back", r"revi", r"again", r"clock", r"reach", r"catch", r"no longer", r"30 ?s",
                r"32", r"stamp", r"stale position", r"old position", r"400", r"430", r"behind", r"jump"],
               "why an old position became FIX later"),
              min_words=15)


# ================================================================================================ session 2
@c.test("Step 6 — live: your arbiter_node on a scenario it has never seen",
        hint="Stop every node of the lab first (`kill -INT $(jobs -p)`). The check starts YOUR arbiter_node (default "
             "settings) and plays a hidden scenario with replay_node; it compares the order of your judge's states.")
def _():
    arbiter_class()
    publishers_ok("/navera_lite/status", expected=0)
    publishers_ok("/navera_lite/fix/gps", expected=0)
    import rclpy
    from diagnostic_msgs.msg import DiagnosticStatus
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    live = CASES["live"]
    fd, path = tempfile.mkstemp(suffix=".csv", prefix="probe_", dir=os.getcwd())
    got = []
    try:
        with os.fdopen(fd, "w") as f:
            f.write("t_s,source,lat,lon,a,b,c,cov_type,valid,delay_s\n")
            for r in live["rows"]:
                f.write(f"{r['t_s']},{r['source']},{r['lat']!r},{r['lon']!r},{r['a']},{r['b']},{r['c']},"
                        f"{r['cov_type']},{r['valid']},{r['delay_s']}\n")
        with Background("python3 -m navera_lite.ros.arbiter_node", settle=2.5) as arb:
            started_here = not rclpy.ok()
            if started_here:
                rclpy.init()
            node = rclpy.create_node("academy_checker")
            qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, history=HistoryPolicy.KEEP_LAST, depth=10,
                             durability=DurabilityPolicy.TRANSIENT_LOCAL)
            node.create_subscription(DiagnosticStatus, "/navera_lite/status", got.append, qos)
            try:
                with Background(f"python3 -m navera_lite.ros.replay_node --ros-args -p file:={path} -p loop:=false "
                                "-p imu_hz:=0.0", settle=0.5):
                    end = time.time() + 3.5 + live["rows"][-1]["t_s"] + 7.0
                    while time.time() < end:
                        rclpy.spin_once(node, timeout_sec=0.1)
                        if got and {kv.key: kv.value for kv in got[-1].values}.get("state") == "NO_FIX" and \
                                len({kv.value for m in got for kv in m.values if kv.key == "source"}) >= 3:
                            break
                        if arb.p.poll() is not None:
                            break
            finally:
                node.destroy_node()
                if started_here and rclpy.ok():
                    rclpy.shutdown()
            if arb.p.poll() is not None:
                out = arb.p.stdout.read()
                raise CheckFailed("your arbiter_node stopped during the check:\n" + out[-900:])
    finally:
        os.remove(path)
    if not got:
        raise CheckFailed("no status from your arbiter_node in the check: start it yourself as in Step 6 and read "
                          "its first lines")
    seq, last = [], None
    for m in got:
        v = {kv.key: kv.value for kv in m.values}
        key = (v.get("state"), v.get("source") or None)
        if key != last:
            seq.append((key, m.message))
            last = key
    want = [(w[1], w[2]) for w in live["summary"]]
    mine = [k for k, _ in seq]
    if mine != want:
        k = next((i for i, (x, y) in enumerate(zip(mine, want)) if x != y), min(len(mine), len(want)))
        yours = f"{mine[k][0]} on {mine[k][1]!r} ({seq[k][1]})" if k < len(mine) else "nothing more"
        raise CheckFailed(f"live, change n°{k + 1} of your judge was {yours}; before it: "
                          + " → ".join(f"{s} {src or ''}".strip() for s, src in mine[:k])
                          + ". Does `python3 judge_lab.py test` pass? (The hidden scenario: GPS, day vision stating "
                            "20 m, GPS lost and back, a celestial fix stamped 30 s ahead.)")
    if "future" not in seq[-1][1]:
        raise CheckFailed(f"live, your last NO_FIX says {seq[-1][1]!r}: it should also say that the celestial fix "
                          "was refused as from the future (self.refused, TODO 4)")


@c.test("Step 6 — the race, live: my_run.json",
        hint="Restart your arbiter_node, then `python3 play_scenario.py` (about 40 s) until 11 of 11 decisions and "
             "every switch match; it writes my_run.json. EXPLAIN_WAIT: why day vision at t = 15.0 s?")
def _():
    if not os.path.exists("my_run.json"):
        raise CheckFailed("my_run.json does not exist yet: run the live race (Step 6, `python3 play_scenario.py`)")
    try:
        with open("my_run.json") as f:
            run_ = json.load(f)
    except (OSError, ValueError) as e:
        raise CheckFailed(f"my_run.json cannot be read ({e}): run the race again")
    if not isinstance(run_, dict) or run_.get("mode") != "live":
        raise CheckFailed("my_run.json is not a LIVE race: run `python3 play_scenario.py` with your arbiter_node "
                          "running (the --offline race does not write it)")
    st = run_.get("statuses")
    ok_rows = isinstance(st, list) and len(st) >= 100 and all(
        isinstance(x, list) and len(x) == 4 and isinstance(x[0], (int, float)) for x in st)
    if not ok_rows or any(b[0] < a_[0] for a_, b in zip(st, st[1:])):
        raise CheckFailed("my_run.json has no usable list of statuses: run the live race again (do not edit the file)")
    good = 0
    for t, state, src, reason in RACE_SAMPLES:
        mine = [x for x in st if x[0] <= t]
        if mine and (mine[-1][1], mine[-1][2], norm(mine[-1][3])) == (state, src, norm(reason)):
            good += 1
    sw, prev = [], None
    for t, _, src, _ in st:
        if src != prev:
            sw.append((t, prev, src))
            prev = src
    sw_ok = len(sw) == len(RACE_SWITCHES) and all(a_[1:] == b[1:] and abs(a_[0] - b[0]) <= SWITCH_TOL_S
                                                  for a_, b in zip(sw, RACE_SWITCHES))
    if good < len(RACE_SAMPLES) or not sw_ok:
        raise CheckFailed(f"your live race: {good} of {len(RACE_SAMPLES)} decisions identical, switches "
                          f"{'match' if sw_ok else 'differ'}. Fix the first ✘ that play_scenario.py shows, restart "
                          "your arbiter_node and play again.")
    explained("EXPLAIN_WAIT", getattr(answers(), "EXPLAIN_WAIT", ""),
              ([r"hold", r"hysteres", r"wait", r"2 ?s", r"two seconds", r"since", r"not long enough", r"too recent",
                r"just came back", r"only 1 ?s", r"1 ?s"], "the hold-off (how long the GPS has been back)"))


@c.test("TODO A — holdoff_metrics() on ticks it has never seen",
        hint="Lab Step 7: count the ticks where the winner differs from the tick before (None counts), the share of "
             "ticks won by \"gps\", and 0.2 s per tick where GPS was eligible but did not win.")
def _():
    m = quiet("experiment.py")
    (f,) = need(m, "holdoff_metrics")
    if is_stub(f):
        raise CheckFailed("holdoff_metrics() is not written yet (TODO A in experiment.py)")
    for case in CASES["holdoff_metrics"]:
        got = go(f, [tuple(t) for t in case["ticks"]], case["duration_s"])
        if not isinstance(got, dict):
            raise CheckFailed(f"holdoff_metrics() must return a dict, got {got!r}")
        for key, want in case["want"].items():
            if key not in got:
                raise CheckFailed(f"the dict has no key {key!r} (the docstring's three keys)")
            try:
                v = float(got[key])
            except (TypeError, ValueError):
                raise CheckFailed(f"{key} must be a number, got {got[key]!r}")
            if abs(v - want) > 1e-6 * max(1.0, abs(want)):
                raise CheckFailed(f"on {len(case['ticks'])} unseen ticks ({case['duration_s']:g} s), {key} = {v:.6g} "
                                  "is not right — check it by hand on the docstring's 4-tick example first")


@c.test("TODO B — true_sigma() on values it has never seen",
        hint="Lesson §7: take fuse()'s weights, then √(w1²σ1² + w2²σ2² + 2·w1·w2·ρ·σ1·σ2).")
def _():
    m = quiet("experiment.py")
    (f,) = need(m, "true_sigma")
    if is_stub(f):
        raise CheckFailed("true_sigma() is not written yet (TODO B in experiment.py)")
    for case in CASES["true_sigma"]:
        got = go(f, *case["args"])
        c.near(got, case["want"], 1e-6, what=f"true_sigma{tuple(case['args'])}")


@c.test("Steps 7–8 — results.json from your experiment",
        hint="Run `python3 experiment.py` after your judge and TODO A/B are right: it writes results.json. PREDICT_HOLDOFF "
             "is your guess before the run; EXPLAIN_HOLDOFF names what the hold-off buys AND what it costs.")
def _():
    if not os.path.exists("results.json"):
        raise CheckFailed("results.json does not exist yet: run `python3 experiment.py` (Step 7)")
    try:
        with open("results.json") as f:
            res = json.load(f)
    except (OSError, ValueError) as e:
        raise CheckFailed(f"results.json cannot be read ({e}): run python3 experiment.py again")
    rows = {float(r.get("holdoff_s", -1)): r for r in res.get("holdoff", []) if isinstance(r, dict)}
    for h, (spm, share, unused) in HOLD.items():
        r = rows.get(h)
        if r is None:
            raise CheckFailed(f"results.json has no row for a hold-off of {h:g} s: run python3 experiment.py again")
        for key, want, tol in (("switches_per_min", spm, 0.01), ("gps_share", share, 0.001), ("gps_unused_s", unused, 0.05)):
            v = r.get(key)
            if not isinstance(v, (int, float)) or abs(v - want) > tol:
                raise CheckFailed(f"results.json, hold-off {h:g} s: {key} = {v!r} is not what a correct judge gives "
                                  "on these seeded events. Run `python3 judge_lab.py test` and check TODO A, then run "
                                  "experiment.py again.")
    fu = res.get("fusion") or {}
    for key, want in FUSION.items():
        v = fu.get(key)
        if not isinstance(v, (int, float)) or abs(v - want) > 0.01:
            raise CheckFailed(f"results.json, fusion: {key} = {v!r} is not right (TODO B), run experiment.py again")
    a = answers()
    predicted("PREDICT_HOLDOFF", getattr(a, "PREDICT_HOLDOFF", ""))
    explained("EXPLAIN_HOLDOFF", getattr(a, "EXPLAIN_HOLDOFF", ""),
              ([r"fewer", r"less", r"stab", r"zig", r"chatter", r"flicker", r"switch", r"chang", r"calm", r"steady"],
               "what the hold-off buys (fewer changes of winner)"),
              ([r"unused", r"not used", r"lost", r"wast", r"cost", r"good gps", r"later", r"delay", r"miss", r"ignor",
                r"less gps", r"share"], "what it costs (good GPS left unused)"),
              min_words=15)


@c.test("Step 9 — report.md",
        hint="Keep the four ## headings of report.md; at least 40 words in each section and 250 in total; in sections "
             "1–3, at least two numbers that are in YOUR results.json (as experiment.py printed them).")
def _():
    if not os.path.exists("report.md"):
        raise CheckFailed("report.md is missing")
    text = open("report.md", encoding="utf-8").read()
    try:
        res = json.load(open("results.json"))
    except (OSError, ValueError):
        raise CheckFailed("results.json is needed first (Step 7): the report quotes its numbers")
    pos = []
    for head in REPORT_HEADS:
        i = text.find(head)
        if i < 0:
            raise CheckFailed(f"report.md: the heading {head!r} is missing (keep the template's headings)")
        pos.append(i)
    pos.append(len(text))
    nums = set()

    def add(x, digits):
        for d in digits:
            nums.add(f"{x:.{d}f}")
    for r in res.get("holdoff", []):
        add(r["switches_per_min"], (1, 2))
        add(r["gps_unused_s"], (0, 1))
        add(100 * r["gps_share"], (0, 1))
        add(r["gps_share"], (2, 3))
    for r in res.get("freshness", []):
        add(100 * r["availability"], (0, 1))
        add(r["max_error_m"], (0,))
        nums.add(str(r["dropouts"]))
    fu = res.get("fusion", {})
    for k in ("claimed_sigma_m", "true_sigma_m", "spoofed_fused_m", "weight_gps"):
        if isinstance(fu.get(k), (int, float)):
            add(fu[k], (1, 2, 3))
    total = 0
    for k, head in enumerate(REPORT_HEADS):
        body = text[pos[k] + len(head):pos[k + 1]]
        body_words = [w for w in re.findall(r"[A-Za-zÀ-ÿ']{2,}", re.sub(r"<!--.*?-->", "", body, flags=re.S))]
        total += len(body_words)
        if len(body_words) < 40:
            raise CheckFailed(f"report.md, section {head!r}: {len(body_words)} words — write at least 40 (the "
                              "template's comments do not count)")
        if k < 3:
            found = {n for n in re.findall(r"\d+(?:\.\d+)?", re.sub(r"<!--.*?-->", "", body, flags=re.S)) if n in nums}
            if len(found) < 2:
                raise CheckFailed(f"report.md, section {head!r}: quote at least two of YOUR numbers from results.json "
                                  "(as experiment.py printed them)")
    if total < 250:
        raise CheckFailed(f"report.md has {total} words in its four sections: write at least 250")


c.milestone("session1", "TODO 1", "TODO 2", "TODO 3", "TODO 4", "TODO 5", "TODOs", "Step 0", "Step 5",
            label="Fair judge")
c.milestone("session2", "TODO", "Step", label="Steady hand")
c.run()
