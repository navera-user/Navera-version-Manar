import contextlib
import io
import re

from academy_check import (Background, CheckFailed, Checker, explained, is_stub, load_student, need, predicted,
                           sh)

c = Checker()

# ---------------------------------------------------------------- expected values (measured on the course reference,
# solutions/09-ros-intro/TEACHER.md "Answer key"; sandbox runs of 2026-10-13)
SUBSCRIBES = {"/navera_lite/fix/gps", "/navera_lite/fix/day", "/navera_lite/fix/night", "/navera_lite/fix/celestial",
              "/navera_lite/imu"}
PUBLISHES = {"/navera_lite/position", "/navera_lite/status"}
YAML_KEYS = {"gps_timeout_s", "day_timeout_s", "night_timeout_s", "celestial_timeout_s", "future_tolerance_s",
             "fix_max_sigma_m", "min_stated_sigma_m", "switch_holdoff_s", "tick_hz", "max_speed_mps",
             "gps_jump_margin_m", "vehicle"}
EXTRA_PARAMS = {"use_eligible", "use_sim_time"}   # declared by ArbiterV0 / by every rclpy node
HZ_RANGE = (5.2, 8.0)           # measured 5.4–7.5 Hz: 5 Hz tick + one decision per arriving fix (1–1.5 fixes/s)
GATE_RANGE = (930.0, 970.0)     # 100 m/s × 9.0 s + 50 m = 950 m (stamps jitter by a few hundredths of a second)
QOS_SEEN = {"BE_PUB_RELIABLE_SUB_RECEIVED": False, "BE_PUB_BE_SUB_RECEIVED": True, "LATE_TL_RELIABLE_RECEIVED": True,
            "LATE_VOLATILE_RECEIVED": False, "LATE_TL_BEST_EFFORT_RECEIVED": False}
IMU = "/navera_lite/imu"
IMU_PUB = ("ros2 topic pub -r 10 " + IMU + " sensor_msgs/msg/Imu \"{header: {frame_id: check}}\" "
           "--qos-reliability RELIABILITY --qos-durability volatile")


def quiet(name):
    with contextlib.redirect_stdout(io.StringIO()):
        return load_student(name, fresh=True)


def answers(*names):
    return need(quiet("answers.py"), *names)


def number(v, name):
    if v is None:
        raise CheckFailed(f"{name} is still empty (None) — write the number you found, without quotes")
    if isinstance(v, bool) or isinstance(v, str):
        raise CheckFailed(f"{name} should be a number without quotes, got {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise CheckFailed(f"{name} should be a number, got {v!r}")


def boolean(v, name):
    if not isinstance(v, bool):
        raise CheckFailed(f"{name} should be True or False (capital letter, no quotes), got {v!r}")
    return v


def word(v, name):
    if not isinstance(v, str) or not v.strip():
        raise CheckFailed(f"{name} is still empty — one word between quotes")
    return v.strip().strip("'\"").upper()


def topic_set(v, name):
    if not isinstance(v, (list, tuple)) or not all(isinstance(t, str) for t in v):
        raise CheckFailed(f'{name} should be a list of topic names in quotes, like ["/a/b", "/c"], got {v!r}')
    if not v:
        raise CheckFailed(f"{name} is still empty")
    got = {t.strip() for t in v} - {"/parameter_events", "/rosout"}
    bare = [t for t in got if not t.startswith("/")]
    if bare:
        raise CheckFailed(f"{name}: write the full names as `ros2 node info` prints them, starting with / "
                          f"(e.g. {'/' + bare[0]!r})")
    return got


# ---------------------------------------------------------------- session 1: map the graph
@c.test("answers.py loads", hint="Run `python3 answers.py`: it must print nothing and show no error. A missing quote, "
                                 "bracket or comma is the usual reason; True/False take a capital letter.")
def _():
    quiet("answers.py")


@c.test("Steps 0–1: your first guess, and running a node from a package",
        hint="Step 1: run `python3 navera_lite/ros/arbiter_v0.py` once, on purpose, and read the LAST line of the error: "
             "its first word is the error's name. Lab 🧰 \"packages and python3 -m\" explains it.")
def _():
    pred, err = answers("PREDICT_SILENT", "MODULE_ERROR")
    predicted("PREDICT_SILENT", pred)
    w = word(err, "MODULE_ERROR")
    c.ok("MODULENOTFOUND" in w, f"MODULE_ERROR = {err!r} is not the error Python prints when the file is run by its "
                                 "path (read the last line of the traceback)")


@c.test("Step 2: what /arbiter subscribes to and publishes, its parameters, and the discovery lag",
        hint="`ros2 node info /arbiter` (if it says \"Unable to find node\", wait and run it again). Copy the "
             "topic names under Subscribers: and Publishers:, leave out /parameter_events and /rosout. "
             "EXTRA_PARAMS: compare `ros2 param list /arbiter` with the keys of navera_lite.yaml. EXPLAIN_LAG: lesson §4.")
def _():
    pred, subs, pubs, extra_p, lag = answers("PREDICT_SUBSCRIBES", "ARBITER_SUBSCRIBES", "ARBITER_PUBLISHES",
                                             "EXTRA_PARAMS", "EXPLAIN_LAG")
    predicted("PREDICT_SUBSCRIBES", pred)
    s = topic_set(subs, "ARBITER_SUBSCRIBES")
    if s == PUBLISHES or s & PUBLISHES:
        raise CheckFailed("ARBITER_SUBSCRIBES holds a topic the arbiter PUBLISHES: read the Subscribers: part of "
                          "`ros2 node info` only")
    missing, extra = SUBSCRIBES - s, s - SUBSCRIBES
    c.ok(not missing, f"ARBITER_SUBSCRIBES misses {len(missing)} topic(s): count the lines under Subscribers: again "
                      "(the four fix topics and one more)")
    c.ok(not extra, f"ARBITER_SUBSCRIBES has topic(s) the arbiter does not subscribe to: {sorted(extra)}")
    p = topic_set(pubs, "ARBITER_PUBLISHES")
    c.ok(p == PUBLISHES, f"ARBITER_PUBLISHES = {sorted(p)} is not what `ros2 node info /arbiter` lists under "
                         "Publishers: (without /parameter_events and /rosout)")
    if not isinstance(extra_p, (list, tuple)) or not all(isinstance(x, str) for x in extra_p) or not extra_p:
        raise CheckFailed(f'EXTRA_PARAMS should be a list of parameter names in quotes, like ["a", "b"], got {extra_p!r}')
    e = {x.strip().lstrip("/").split(":")[0].strip() for x in extra_p}
    in_yaml = e & YAML_KEYS
    c.ok(not in_yaml, f"EXTRA_PARAMS: {sorted(in_yaml)} IS in navera_lite.yaml — list only the parameters that are not")
    c.ok(e == EXTRA_PARAMS, f"EXTRA_PARAMS = {sorted(e)}: `ros2 param list /arbiter` shows {len(EXTRA_PARAMS)} names "
                            "that are not keys of navera_lite.yaml — one is declared in ArbiterV0.__init__, one by every node")
    explained("EXPLAIN_LAG", lag, ((r"discover", r"announc", r"find each other", r"daemon", r"cache"), "discovery"),
              ((r"wait", r"again", r"twice", r"second", r"retr", r"repeat", r"later"), "what to do about it"))


@c.test("Step 3: two constants, read from the message definitions",
        hint="`ros2 interface show sensor_msgs/msg/NavSatFix`: lines with = are constants (NavSatStatus is nested "
             "inside). For DEGRADED_LEVEL: in navera_lite/ros/convert.py, LEVELS says which DiagnosticStatus constant "
             "DEGRADED uses; `ros2 interface show diagnostic_msgs/msg/DiagnosticStatus` gives its number; Step 4's "
             "`--field level` watch shows it live during the GPS gap.")
def _():
    nofix, level = answers("STATUS_NO_FIX", "DEGRADED_LEVEL")
    c.ok(number(nofix, "STATUS_NO_FIX") == -1, f"STATUS_NO_FIX = {nofix!r} is not the value of that constant "
                                                "(watch the sign)")
    lv = number(level, "DEGRADED_LEVEL")
    known = {0: "OK, the level of FIX", 2: "ERROR, the level of NO_FIX", 3: "STALE, the level of STARTING (the \\x03 you saw)"}
    c.ok(lv not in known, f"DEGRADED_LEVEL = {level!r} is {known.get(lv, '')}: follow the chain for DEGRADED — "
                          "LEVELS[\"DEGRADED\"] → which constant → which number; Step 4's level watch shows it")
    c.ok(lv == 1, f"DEGRADED_LEVEL = {level!r} — which constant does LEVELS give DEGRADED, and what number does "
                  "DiagnosticStatus define for it?")


@c.test("Step 4: the status rate and the jump gate, measured on the live judge",
        hint="Start the arbiter BEFORE the replay (Step 4 order). STATUS_HZ: the `average rate:` of "
             "`ros2 topic hz /navera_lite/status`. GATE_ALLOWED_M: `grep refused arbiter.log | head -1`, the number "
             "after `>`. Explain both from what the code does (lesson §3) and from mission 01's gate.")
def _():
    pred, hz, why_hz, allowed, why_gate = answers("PREDICT_HZ", "STATUS_HZ", "EXPLAIN_HZ", "GATE_ALLOWED_M",
                                                  "EXPLAIN_GATE")
    predicted("PREDICT_HZ", pred)
    h = number(hz, "STATUS_HZ")
    if h == 5.0:
        raise CheckFailed("STATUS_HZ = 5.0 is tick_hz, the setting — write the rate `ros2 topic hz` MEASURED")
    c.ok(HZ_RANGE[0] <= h <= HZ_RANGE[1], f"STATUS_HZ = {hz!r} is not a rate `ros2 topic hz` gives for the status "
                                          "with the replay running")
    low = str(why_hz).lower()
    if re.search(r"jitter|imprecis|inaccura|not exact|twice|duplicat|resend|retransmi", low) and \
            not re.search(r"on_fix|arriv|fix", low):
        raise CheckFailed("EXPLAIN_HZ: the timer is not imprecise — look at who else calls self.step() in ArbiterV0")
    explained("EXPLAIN_HZ", why_hz, ((r"tick", r"timer", r"5 ?hz", r"five", r"\b5\b", r"0\.2"), "the regular tick"),
              ((r"arriv", r"each fix", r"every fix", r"new fix", r"receiv\w* (a |each |every |new )?(\w+ )?fix", r"on_fix",
                r"when a fix"),
               "the extra decisions when a fix arrives"))
    a = number(allowed, "GATE_ALLOWED_M")
    if a == 150:
        raise CheckFailed("GATE_ALLOWED_M = 150 is the gate after 1 s: read the FIRST `refused` line of arbiter.log "
                          "(started before the replay), not a later one")
    c.ok(GATE_RANGE[0] <= a <= GATE_RANGE[1], f"GATE_ALLOWED_M = {allowed!r} is not the allowed distance of the first "
                                              "refused fix (did you start the arbiter before the replay?)")
    explained("EXPLAIN_GATE", why_gate,
              ((r"elapsed", r"last trusted", r"last (gps|good|accepted)", r"\b9(\.0)? ?s", r"nine", r"gap",
                r"no gps", r"silent", r"\b1[129]\b"), "WHY the elapsed time is 9 s (the last trusted fix, the GPS gap)"),
              ((r"100", r"speed", r"v_max", r"m/s", r"50", r"margin"), "the gate's speed and margin"))


@c.test("Step 5: two judges on one topic",
        hint="With the second arbiter running: `ros2 topic info /navera_lite/status` → Publisher count. Explain "
             "with the lesson's §1 (decoupling: a subscriber does not know who publishes).")
def _():
    n, why = answers("STATUS_PUBLISHERS", "EXPLAIN_TWO_JUDGES")
    c.ok(number(n, "STATUS_PUBLISHERS") == 2, f"STATUS_PUBLISHERS = {n!r} is not the publisher count with two "
                                              "arbiters running")
    if re.search(r"forbid|should not (allow|be allowed)|missing", str(why).lower()):
        raise CheckFailed("EXPLAIN_TWO_JUDGES: ROS does not forbid it, on purpose — lesson §1, decoupling: why is it "
                          "allowed?")
    explained("EXPLAIN_TWO_JUDGES", why,
              ((r"decoupl", r"(does not|doesn't|don't|do not|cannot|can't|never) know", r"anyone", r"anybody", r"any node",
                r"no (central|server|owner|check)"), "why ROS lets two nodes publish on one topic"),
              ((r"two answer", r"conflict", r"contradict", r"which", r"mix", r"wrong", r"differ", r"both", r"confus",
                r"interleav", r"alternat", r"cannot tell", r"can't tell"), "what a subscriber of the status then gets"))


@c.test("Step 6: another domain is another world",
        hint="`ROS_DOMAIN_ID=$((ROS_DOMAIN_ID + 1)) ros2 topic list --no-daemon --spin-time 3`: is /navera_lite/status "
             "in the list? EXPLAIN_ISOLATION: lesson §4, NAVERA's WEB-12, and the two settings that limit discovery.")
def _():
    sees, why = answers("OTHER_DOMAIN_SEES_STATUS", "EXPLAIN_ISOLATION")
    c.ok(boolean(sees, "OTHER_DOMAIN_SEES_STATUS") is False,
         "OTHER_DOMAIN_SEES_STATUS = True: run the command again and look for /navera_lite/status itself "
         "(/parameter_events and /rosout belong to the ros2 command's own node)")
    explained("EXPLAIN_ISOLATION", why,
              ((r"hijack", r"same network", r"wi-?fi", r"another (computer|machine|simulator|robot)", r"simulat", r"fake",
                r"publish", r"inject", r"attack", r"outside"), "what could go wrong"),
              ((r"domain",), "the domain"), ((r"localhost", r"loopback", r"127\.0\.0\.1", r"local"), "the localhost-only setting"))


# ---------------------------------------------------------------- session 2: the silent listener
@c.test("Step 7: offered vs requested, five experiments",
        hint="Run the five commands of Step 7 in order, each in the same terminal as its publisher, and write what "
             "you SAW (True = at least one message printed). The warning line ends with `Last incompatible policy: …`.")
def _():
    pred, pol = answers("PREDICT_QOS", "INCOMPATIBLE_POLICY")
    predicted("PREDICT_QOS", pred)
    vals = answers(*QOS_SEEN)
    wrong = [n for n, v in zip(QOS_SEEN, vals) if boolean(v, n) is not QOS_SEEN[n]]
    c.ok(not wrong, f"{len(wrong)} of the five observations do not match what ROS does: {', '.join(wrong)}. Run "
                    "those experiments again and wait the full timeout (a late subscriber may need 2 s to match)")
    c.ok("RELIABILITY" in word(pol, "INCOMPATIBLE_POLICY"),
         f"INCOMPATIBLE_POLICY = {pol!r} is not the policy named in the warning")


def todo_fn():
    q = quiet("navera_lite.ros.qos")
    (fn,) = need(q, "incompatible_policies")
    if is_stub(fn):
        raise CheckFailed("incompatible_policies() is not written yet (it is still the TODO stub in navera_lite/ros/qos.py)")
    return fn


# incompatible_policies() takes rclpy QoSProfile objects, which cannot be passed to the student's process: a small
# script builds the profiles THERE (inputs only, no expected value) and prints the student's answers; judged here.
PROBE = r"""
import json, sys, traceback
sys.path.insert(0, ".")
from rclpy.qos import DurabilityPolicy as D, HistoryPolicy as H, QoSProfile, ReliabilityPolicy as R
from navera_lite.ros import qos
out = []
for (ro, do, ho, no), (rr, dr, hr, nr) in json.loads(sys.argv[1]):
    off = QoSProfile(reliability=R[ro], durability=D[do], history=H[ho], depth=no)
    req = QoSProfile(reliability=R[rr], durability=D[dr], history=H[hr], depth=nr)
    try:
        v = qos.incompatible_policies(off, req)
        if isinstance(v, (list, tuple)) and all(isinstance(x, str) for x in v):
            out.append(["ok", list(v)])
        else:
            out.append(["type", repr(v)[:60], type(v).__name__])
    except Exception as e:
        tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename.endswith("qos.py")]
        out.append(["err", f"{type(e).__name__}: {e}" + (f" (navera_lite/ros/qos.py line {tb[-1].lineno})" if tb else "")])
print("PROBE_RESULT " + json.dumps(out))
"""
COMBOS = [(r, d) for r in ("RELIABLE", "BEST_EFFORT") for d in ("TRANSIENT_LOCAL", "VOLATILE")]
DEPTH = {("RELIABLE", "TRANSIENT_LOCAL"): 1, ("RELIABLE", "VOLATILE"): 7, ("BEST_EFFORT", "TRANSIENT_LOCAL"): 3,
         ("BEST_EFFORT", "VOLATILE"): 20}
PAIRS = [((ro, do, "KEEP_LAST", DEPTH[(ro, do)]), (rr, dr, "KEEP_LAST", DEPTH[(rr, dr)]))
         for ro, do in COMBOS for rr, dr in COMBOS]
WANT = [(["RELIABILITY"] if (o[0] == "BEST_EFFORT" and r[0] == "RELIABLE") else []) +
        (["DURABILITY"] if (o[1] == "VOLATILE" and r[1] == "TRANSIENT_LOCAL") else []) for o, r in PAIRS]
DEPTH_PAIRS = [(("RELIABLE", "TRANSIENT_LOCAL", "KEEP_LAST", 1), ("BEST_EFFORT", "VOLATILE", "KEEP_LAST", 50)),
               (("RELIABLE", "VOLATILE", "KEEP_ALL", 1), ("BEST_EFFORT", "VOLATILE", "KEEP_LAST", 50)),
               (("BEST_EFFORT", "VOLATILE", "KEEP_LAST", 100), ("BEST_EFFORT", "VOLATILE", "KEEP_LAST", 1))]
NAMES = ("RELIABILITY", "DURABILITY")


def probe(pairs):
    """The student's incompatible_policies() on each pair (run in the student's own Python): a list of lists."""
    import json
    import shlex
    todo_fn()                                            # a stub gives a clear message first
    code, out = sh(f"timeout 40 python3 -c {shlex.quote(PROBE)} {shlex.quote(json.dumps(pairs))}", timeout=60)
    line = next((l for l in reversed(out.splitlines()) if l.startswith("PROBE_RESULT ")), None)
    if line is None:
        tail = "\n".join(out.strip().splitlines()[-5:])
        raise CheckFailed("navera_lite/ros/qos.py could not be run with test profiles. The end of the error:\n" + tail)
    got = []
    for item in json.loads(line[len("PROBE_RESULT "):]):
        if item[0] == "err":
            raise CheckFailed(f"incompatible_policies() stopped with {item[1]}")
        if item[0] == "type":
            raise CheckFailed(f"incompatible_policies() must return a list of words like [\"RELIABILITY\"] (or [] when "
                              f"they connect), got {item[1]} (a {item[2]})")
        odd = [x for x in item[1] if x not in NAMES]
        if odd:
            raise CheckFailed(f"incompatible_policies() returned {item[1]!r}: use the policy names ROS prints in its WARN "
                              "line, \"RELIABILITY\" and \"DURABILITY\" (capitals; the policy, not its value like "
                              "\"RELIABLE\")")
        if len(set(item[1])) != len(item[1]):
            raise CheckFailed(f"incompatible_policies() returned {item[1]!r}: each policy at most once")
        got.append(item[1])
    return got


def label(pair):
    (ro, do, _, _), (rr, dr, _, _) = pair
    return f"offered {ro}+{do}, requested {rr}+{dr}"


@c.test("TODO 1: incompatible_policies() judges every pair of reliability and durability",
        hint="Lesson §5, the two tables: the first argument is what the publisher OFFERS, the second what the "
             "subscriber REQUESTS. Each table has one ✘ cell; each ✘ adds its policy's name to the list. Depth and "
             "history never decide. `python3 qos_doctor.py test` shows the docstring's examples.")
def _():
    got = probe(PAIRS)
    yes = [not g for g in got]                       # True = "they connect"
    want = [not w for w in WANT]
    bad = [(p, y) for p, y, w in zip(PAIRS, yes, want) if y != w]
    if bad:
        says_yes = [p for p, y in bad if y]
        says_no = [p for p, y in bad if not y]
        dur_hole = lambda p: p[1][1] == "TRANSIENT_LOCAL" and p[0][1] == "VOLATILE"
        rel_hole = lambda p: p[1][0] == "RELIABLE" and p[0][0] == "BEST_EFFORT"
        if says_yes and not says_no and all(dur_hole(p) for p in says_yes):
            why = "a VOLATILE offer cannot serve a TRANSIENT_LOCAL request: does your code look at durability?"
        elif says_yes and not says_no and all(rel_hole(p) for p in says_yes):
            why = "a BEST_EFFORT offer cannot serve a RELIABLE request: does your code look at reliability?"
        elif says_yes and not says_no and len(says_yes) == 7:
            why = ("it never finds an incompatible policy: do you compare with the constants "
                   "(ReliabilityPolicy.BEST_EFFORT), not with text like \"BEST_EFFORT\"? (print(offered.reliability))")
        elif says_yes and not says_no:
            why = ("it accepts pairs where only ONE policy fails: test the two policies separately, each one alone is "
                   "enough to refuse")
        elif says_no and not says_yes and len(says_no) == 9:
            why = ("it never says connect: when neither ✘ cell applies, return an empty list []")
        elif says_no and not says_yes:
            why = ("these pairs DO connect: an offer STRONGER than the request is fine (RELIABLE serves BEST_EFFORT, "
                   "TRANSIENT_LOCAL serves VOLATILE) — do you demand equal policies, or compare depths?")
        else:
            why = ("some pairs are refused that connect, and some accepted that do not: are the two arguments swapped "
                   "(the FIRST one is the publisher's offer)?")
        p, y = bad[0]
        raise CheckFailed(f"{len(bad)} of 16 pairs are judged wrong, e.g. {label(p)} → you say "
                          f"{'connect' if y else 'no connection'} — {why}")
    wrong_name = [(p, g, w) for p, g, w in zip(PAIRS, got, WANT) if sorted(g) != sorted(w)]
    if wrong_name:
        p, g, w = wrong_name[0]
        if set(g) < set(w):
            raise CheckFailed(f"{label(p)} → you say {g!r}: here BOTH policies fail — did you return after the first "
                              "one? Use bad = [], append each failing name, return bad at the end")
        raise CheckFailed(f"{len(wrong_name)} pairs name the wrong policy, e.g. {label(p)} → you say {g!r} — which "
                          "of the two tables has the ✘ for that pair? (When BOTH fail, the list has both names.)")


@c.test("TODO 1: incompatible_policies() ignores history and depth",
        hint="Only reliability and durability decide a connection (lesson §5): a subscriber that keeps 50 messages "
             "can listen to a publisher that keeps 1.")
def _():
    a, b, d = probe(DEPTH_PAIRS)
    c.ok(a == [], f"a publisher keeping 1 message (RELIABLE, TRANSIENT_LOCAL) and a subscriber asking for 50 "
                  f"(BEST_EFFORT, VOLATILE): you say {a!r} — depth must not decide")
    c.ok(b == [], f"a KEEP_ALL publisher and a KEEP_LAST subscriber: you say {b!r} — history must not decide")
    c.ok(d == [], f"two BEST_EFFORT + VOLATILE endpoints with depths 100 and 1: you say {d!r} — depth must not decide")


def listener_count(rel):
    """Run the student's imu_listener.py against a check-owned IMU publisher; returns (count, output)."""
    with Background(IMU_PUB.replace("RELIABILITY", rel), settle=2.0):
        code, out = sh("timeout 40 python3 imu_listener.py 7", timeout=60)
    m = re.search(r"heard (\d+) IMU messages", out)
    if not m:
        tail = "\n".join(out.strip().splitlines()[-6:])
        raise CheckFailed("imu_listener.py did not print its `heard N IMU messages` line. Run "
                          f"`python3 imu_listener.py` yourself; its output ended with:\n{tail}")
    return int(m.group(1)), out


@c.test("Step 10: the repaired imu_listener.py hears a BEST_EFFORT IMU and a RELIABLE one",
        hint="Lab Steps 9–10: the plain number 10 asks for the default profile, which is RELIABLE. Request "
             "BEST_EFFORT instead (a profile from navera_lite/ros/qos.py, or rclpy's qos_profile_sensor_data): it "
             "accepts both kinds of publishers. Change the subscriber only, never the given profiles.")
def _():
    code, out = sh("timeout 30 python3 -c \"from navera_lite.ros import qos; "
                   "print('|'.join(qos.describe(p) for p in (qos.FIX_QOS, qos.SENSOR_QOS, qos.STATUS_QOS)))\"", timeout=40)
    want = "RELIABLE, VOLATILE, KEEP_LAST 10|BEST_EFFORT, VOLATILE, KEEP_LAST 5|RELIABLE, TRANSIENT_LOCAL, KEEP_LAST 1"
    c.ok(want in out, "the given profiles FIX_QOS, SENSOR_QOS or STATUS_QOS of navera_lite/ros/qos.py were changed: put "
                      "them back (the replay and the arbiter use them) and repair the listener instead")
    n, out = listener_count("best_effort")
    if n == 0 and "incompatible" in out.lower():
        pol = re.search(r"Last incompatible policy: (\w+)", out)
        pol = pol.group(1) if pol else "?"
        raise CheckFailed("imu_listener.py still hears nothing from a BEST_EFFORT + VOLATILE publisher (like the "
                          "replay's IMU, or a vehicle's driver), and ROS says why: \"offering incompatible QoS … "
                          f"Last incompatible policy: {pol}\". What does your subscription request for that policy?")
    c.ok(n >= 10, f"imu_listener.py heard {n} messages in 7 s from a BEST_EFFORT publisher at 10 Hz: it should hear "
                  "most of them")
    n, out = listener_count("reliable")
    c.ok(n >= 10, f"with a RELIABLE publisher imu_listener.py heard {n} messages in 7 s — does your listener request "
                  "something a RELIABLE + VOLATILE publisher cannot give (TRANSIENT_LOCAL?)")


@c.test("TODO 2: latched_probe.py gets the kept status as a LATE subscriber",
        hint="Lab Step 11: a late subscriber of a latched topic must request TRANSIENT_LOCAL, and (Step 7, B3) RELIABLE "
             "too: STATUS_QOS of navera_lite/ros/qos.py is exactly that. Print the first status with "
             "print(f\"first status: {msg.message}\", flush=True).")
def _():
    import random
    token = f"check {random.randint(10000, 99999)}"
    pub = ("ros2 topic pub --once -w 0 --keep-alive 60 --qos-depth 1 --qos-durability transient_local "
           "--qos-reliability reliable /navera_lite/status diagnostic_msgs/msg/DiagnosticStatus "
           f"\"{{message: '{token}'}}\"")
    with Background(pub, settle=4.0):
        code, out = sh("timeout 40 python3 latched_probe.py 7", timeout=60)
    if "Traceback" in out and "first status" not in out:
        tail = "\n".join(out.strip().splitlines()[-4:])
        raise CheckFailed(f"latched_probe.py stopped with an error. The end of its output:\n{tail}")
    if f"first status: {token}" in out:
        return
    if "first status:" in out:
        raise CheckFailed("latched_probe.py printed a status, but not the one the check published — print msg.message "
                          "of the message you receive")
    pol = re.search(r"Last incompatible policy: (\w+)", out)
    if pol:
        raise CheckFailed(f"latched_probe.py heard nothing, and ROS says why: \"incompatible QoS … {pol.group(1)}\"")
    raise CheckFailed("latched_probe.py heard nothing from a publisher that published ONCE before it started: as a late "
                      "subscriber it must ask for the kept message — what does it request (durability AND reliability, "
                      "lab Step 7 B1–B3)? Is the callback given to create_subscription, and does it print?")


@c.test("Steps 9–10: what the listener requested, and why the repair belongs in the subscriber",
        hint="LISTENER_REQUESTS: `python3 qos_doctor.py /navera_lite/imu` or `ros2 topic info -v` while the broken "
             "listener runs. EXPLAIN_TEN: what does create_subscription do with a plain number (lesson §5)? "
             "EXPLAIN_REPAIR: who owns the IMU driver, and what does a BEST_EFFORT request accept?")
def _():
    req, ten, why = answers("LISTENER_REQUESTS", "EXPLAIN_TEN", "EXPLAIN_REPAIR")
    w = word(req, "LISTENER_REQUESTS")
    c.ok(w == "RELIABLE", f"LISTENER_REQUESTS = {req!r} is not the reliability the broken listener requests")
    explained("EXPLAIN_TEN", ten, ((r"default",), "the default profile"),
              ((r"depth", r"queue", r"keep_last", r"history", r"how many"), "what the number itself sets (only ...)"))
    if re.search(r"10 (is|means) (the )?(code|value|number)? ?(of )?reliable", str(ten).lower()):
        raise CheckFailed("EXPLAIN_TEN: 10 is not a code for RELIABLE — what does a plain number set, and where does "
                          "RELIABLE come from (lesson §5)?")
    if re.search(r"(chang|set|modif|edit)\w* (the |its )?(publisher|sensor_qos|replay)", str(why).lower()):
        raise CheckFailed("EXPLAIN_REPAIR: the publisher was not changed (and must not be): say what the SUBSCRIPTION "
                          "requests now")
    explained("EXPLAIN_REPAIR", why,
              ((r"best.?effort", r"sensor_qos", r"sensor data", r"qos_profile_sensor_data"), "what the listener requests now"),
              ((r"driver", r"(not|n't) (ours|mine|yours|our|my)", r"someone else", r"somebody else", r"other people",
                r"integrator", r"vehicle", r"cannot change", r"can't change", r"don't control", r"do not control",
                r"any publisher", r"every publisher", r"accepts", r"both kinds", r"both (best|reliable)"),
               "why the subscriber is the right place (who owns the publisher, or what a BEST_EFFORT request accepts)"))


# Session 1 (Steps 0–6) earns "Cartographer"; the whole mission earns "QoS detective".
c.milestone("cartographer", "answers.py loads", "Steps 0–1:", "Step 2:", "Step 3:", "Step 4:", "Step 5:", "Step 6:",
            label="Session 1 complete: Cartographer badge earned (the ✘ lines left, if any, are session 2)")
c.milestone("qos-detective", "answers", "Step", "TODO",
            label="Mission complete: Cartographer and QoS detective badges earned")

c.run()
