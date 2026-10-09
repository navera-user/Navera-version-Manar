import os
import re

from academy_check import Background, Checker, load_student, need, sh, wait_for_messages

c = Checker()
DOMAIN = int(os.environ.get("ROS_DOMAIN_ID", "0") or 0)
BASE_PORT = 7400 + 250 * DOMAIN


def ans(name):
    (v,) = need(load_student("answers.py"), name)
    return v


def answered(name):
    v = ans(name)
    c.ok(v is not None and not (isinstance(v, (str, list)) and len(v) == 0), f"{name} has no answer yet")
    return v


def is_bool(name, want):
    v = answered(name)
    c.ok(isinstance(v, bool), f"{name} should be True or False (no quotes), got {v!r}")
    c.ok(v is want, f"{name} = {v!r} does not match what ROS does — run the experiment again and look carefully")


def topics(v, name):
    c.ok(isinstance(v, (list, tuple)), f"{name} should be a list like [\"/a\", \"/b\"], got {v!r}")
    c.ok(len(v) > 0, f"{name} is still empty")
    return {str(t).strip() for t in v} - {"/parameter_events", "/rosout"}


@c.test("answers.py loads", hint="Run `python3 answers.py`: it must print nothing and show no error. "
                                   "A missing quote, bracket or comma is the usual reason.")
def _():
    load_student("answers.py")


@c.test("Step 1 — your domain and its discovery port",
        hint="echo $ROS_DOMAIN_ID, then the formula of the course: 7400 + 250 × domain (a number, no quotes).")
def _():
    v = answered("MY_DOMAIN_ID")
    c.eq(str(v).strip(), str(DOMAIN), "MY_DOMAIN_ID")
    c.eq(answered("DISCOVERY_PORT"), BASE_PORT, "DISCOVERY_PORT")


@c.test("Step 2 — DDS_PORTS: the UDP ports of your domain",
        hint="Run the `ss -uln | awk …` command of step 2 while the talker runs and copy the numbers. "
             "They all lie between your discovery port and the next domain's.")
def _():
    v = answered("DDS_PORTS")
    c.ok(isinstance(v, (list, tuple)) and all(isinstance(p, int) for p in v),
         f"DDS_PORTS should be a list of whole numbers, got {v!r}")
    bad = [p for p in v if not BASE_PORT <= p < BASE_PORT + 250]
    c.ok(not bad, f"these ports are not in your domain's range {BASE_PORT}…{BASE_PORT + 249}: {bad}")
    c.ok(BASE_PORT in v, f"your discovery port {BASE_PORT} is missing")
    c.ok(any(p >= BASE_PORT + 10 for p in v), "no participant port (discovery port + 10 + 2p) in the list")


@c.test("Step 3 — chatter.txt holds one message saved from /chatter",
        hint="With the talker running: `ros2 topic echo --once /chatter > chatter.txt` in the lab folder.")
def _():
    c.file_exists("chatter.txt")
    txt = open("chatter.txt", encoding="utf-8", errors="replace").read()
    c.ok("data:" in txt and "Hello World" in txt,
         "chatter.txt should contain a line like  data: 'Hello World: 12'  — got:\n" + txt[:300])


RUN = {}


def live_talker():
    """Start a talker, measure it, and read its QoS with `ros2 topic info -v` (done once)."""
    if "msgs" not in RUN:
        from std_msgs.msg import String
        RUN["msgs"], RUN["info"] = [], ""
        with Background("ros2 run demo_nodes_py talker", settle=2.0):
            if wait_for_messages("/chatter", String, count=1, timeout=15):
                RUN["msgs"] = wait_for_messages("/chatter", String, count=2, timeout=6)
            RUN["info"] = sh("ros2 topic info -v /chatter --no-daemon --spin-time 3", timeout=30)[1]
    c.ok(len(RUN["msgs"]) >= 1, "the check could not receive its own talker's messages — tell your teacher")
    return RUN


@c.test("Step 2 — CHATTER_TYPE and the talker's QoS (the check runs a talker to compare)",
        hint="Copy the `Type:` line and, under the PUBLISHER's `QoS profile:`, the words after "
             "`Reliability:` and `Durability:` of `ros2 topic info -v /chatter`.")
def _():
    v = str(answered("CHATTER_TYPE")).strip()
    info = live_talker()["info"]
    m = re.search(r"Type:\s*(\S+)", info)
    c.ok(m is not None, "the check could not read `ros2 topic info -v /chatter`:\n" + info[-400:])
    c.eq(v, m.group(1), "CHATTER_TYPE")
    pub = info.split("Endpoint type: PUBLISHER", 1)[-1]
    rel = re.search(r"Reliability:\s*(\w+)", pub).group(1)
    dur = re.search(r"Durability:\s*(\w+)", pub).group(1)
    c.eq(str(answered("CHATTER_RELIABILITY")).strip().upper(), rel, "CHATTER_RELIABILITY")
    c.eq(str(answered("CHATTER_DURABILITY")).strip().upper(), dur, "CHATTER_DURABILITY")


@c.test("Step 2 — TALKER_HZ and CHATTER_MSG_BYTES",
        hint="`ros2 topic hz /chatter` → average rate; `ros2 topic bw /chatter` → `Message size mean` in B. "
             "The course computes it: 4 + 4 + characters + 1, padded to a multiple of 4.")
def _():
    c.near(answered("TALKER_HZ"), 1.0, 0.2, "TALKER_HZ")
    c.near(answered("CHATTER_MSG_BYTES"), 24, 4, "CHATTER_MSG_BYTES")


@c.test("Step 3 — CHATTER_SUBSCRIBERS with one listener",
        hint="With exactly one listener (and no echo), `ros2 topic info /chatter` shows `Subscription count:`.")
def _():
    c.eq(answered("CHATTER_SUBSCRIBERS"), 1, "CHATTER_SUBSCRIBERS")


@c.test("Step 4 — another domain does not see your topics",
        hint="Participants only discover participants of the same ROS_DOMAIN_ID.")
def _():
    is_bool("OTHER_DOMAIN_SEES_CHATTER", False)


@c.test("Step 5 — the four QoS experiments",
        hint="Offered must be ≥ requested: RELIABLE requested from a BEST_EFFORT publisher → no match; "
             "a late VOLATILE subscriber gets nothing old; a late TRANSIENT_LOCAL one gets the stored message.")
def _():
    is_bool("BE_PUB_RELIABLE_SUB_RECEIVED", False)
    is_bool("BE_PUB_BE_SUB_RECEIVED", True)
    is_bool("LATCHED_TRANSIENT_RECEIVED", True)
    is_bool("LATCHED_VOLATILE_RECEIVED", False)


@c.test("Step 6 — the service and the action",
        hint="Call add_two_ints with a = your domain and b = 1000; copy the action's final `sequence` "
             "as a list, e.g. [0, 1, 1, …].")
def _():
    c.eq(answered("SERVICE_SUM"), DOMAIN + 1000, "SERVICE_SUM")
    c.eq(list(answered("FIBONACCI_8")), [0, 1, 1, 2, 3, 5, 8, 13, 21], "FIBONACCI_8")


@c.test("Step 7 — MODE_REPLAYED and STATE_FIX",
        hint="`ros2 interface show …` and find the lines `uint8 MODE_REPLAYED=…` and `uint8 STATE_FIX=…`.")
def _():
    from navera_msgs.msg import NavStatus, PositionEstimate
    c.eq(answered("MODE_REPLAYED"), PositionEstimate.MODE_REPLAYED, "MODE_REPLAYED")
    c.eq(answered("STATE_FIX"), NavStatus.STATE_FIX, "STATE_FIX")


EST = {}


def live_estimator():
    """Run NAVERA's estimator once: its node info, a few statuses."""
    if "info" not in EST:
        from navera_msgs.msg import NavStatus
        EST["info"], EST["msgs"] = "", []
        with Background("ros2 run navera_estimator estimator_node.py", settle=2.5):
            EST["msgs"] = wait_for_messages("/navera/nav_status", NavStatus, count=6, timeout=10)
            EST["info"] = sh("ros2 node info /estimator_node --no-daemon --spin-time 3", timeout=30)[1]
    c.ok(EST["msgs"], "the check could not run NAVERA's estimator — tell your teacher")
    return EST


def section(info, title):
    m = re.search(title + r":\n(.*?)(?:\n  [A-Z][a-zA-Z ]+:|\Z)", info, re.S)
    return {line.split(":")[0].strip() for line in (m.group(1).splitlines() if m else []) if line.strip()}


@c.test("Step 8 — the estimator's subscriptions and publications (the check runs it to compare)",
        hint="`ros2 node info /estimator_node`: copy the topic names under `Subscribers:` (5) and the two "
             "`/navera/…` names under `Publishers:`, each with its leading /.")
def _():
    info = live_estimator()["info"]
    want_sub = section(info, "Subscribers") - {"/parameter_events", "/rosout"}
    want_pub = {t for t in section(info, "Publishers") if t.startswith("/navera")}
    c.ok(len(want_sub) == 5 and len(want_pub) == 2, "the check could not read the node info:\n" + info[-500:])
    got = topics(ans("ESTIMATOR_SUBSCRIBES"), "ESTIMATOR_SUBSCRIBES")
    missing, extra = want_sub - got, got - want_sub
    c.ok(not missing and not extra, (f"missing: {sorted(missing)} " if missing else "") +
         (f"not a subscription of the estimator: {sorted(extra)}" if extra else ""))
    c.eq(sorted(topics(ans("ESTIMATOR_PUBLISHES"), "ESTIMATOR_PUBLISHES")), sorted(want_pub), "ESTIMATOR_PUBLISHES (sorted)")


@c.test("Step 8 — FIRST_STATE, NAV_STATUS_HZ and FIX_MAX_SIGMA_M",
        hint="FIRST_STATE is the NUMBER printed after `state:` by `ros2 topic echo --once /navera/nav_status` "
             "(the constants are in NavStatus.msg: 0 = STATE_INITIALIZING, 1 = STATE_NO_FIX…); "
             "`ros2 topic hz` gives about 5; the service call returns double_value=25.0.")
def _():
    from navera_msgs.msg import NavStatus
    st = live_estimator()["msgs"][-1]
    fs = answered("FIRST_STATE")
    if isinstance(fs, str):          # a name is accepted too: "INITIALIZING" or "STATE_INITIALIZING"
        names = {k[len("STATE_"):]: getattr(NavStatus, k) for k in dir(NavStatus)
                 if k.startswith("STATE_") and isinstance(getattr(NavStatus, k), int)}
        key = fs.strip().upper()
        key = key[len("STATE_"):] if key.startswith("STATE_") else key
        c.ok(key in names, f"FIRST_STATE = {fs!r} is not a state name — write the number printed after `state:`, without quotes")
        fs = names[key]
    c.ok(isinstance(fs, int) and not isinstance(fs, bool),
         f"FIRST_STATE should be the number printed after `state:` (no quotes), got {fs!r}")
    c.eq(fs, st.state, "FIRST_STATE (the number after `state:`)")
    c.ok(st.state == NavStatus.STATE_INITIALIZING, "unexpected estimator state — tell your teacher")
    c.near(answered("NAV_STATUS_HZ"), 5.0, 0.7, "NAV_STATUS_HZ")
    c.near(answered("FIX_MAX_SIGMA_M"), 25.0, 1e-6, "FIX_MAX_SIGMA_M")


@c.test("quiz Q1–Q3", hint="Q1 and Q3: the QoS compatibility tables of the course. Q2: the discovery port formula of the course, with your domain number.")
def _():
    for q, good in (("Q1", "c"), ("Q2", "b"), ("Q3", "a")):
        v = str(ans(q)).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f"{q} = \"{v}\" is not the right answer")


@c.test("report.md — three sections of analysis, with your measurements",
        hint="Keep the headings ## Discovery, ## QoS, ## NAVERA; at least 40 words each, in your own words. "
             "Discovery must give your discovery port; QoS must name RELIABLE, BEST_EFFORT, TRANSIENT_LOCAL "
             "and VOLATILE and paste the warning; NAVERA must mention /navera/nav_status.")
def _():
    c.file_exists("report.md")
    txt = open("report.md", encoding="utf-8", errors="replace").read()
    parts = {}
    for title in ("Discovery", "QoS", "NAVERA"):
        m = re.search(r"^##\s*" + title + r"\s*$(.*?)(?=^##\s|\Z)", txt, re.M | re.S)
        c.ok(m is not None, f"the heading `## {title}` is missing")
        body = re.sub(r"^\*(?=\S)[^*]+?\*\s*$", "", m.group(1), flags=re.M | re.S)                    # the template's italic prompts
        words = len(re.findall(r"[A-Za-z0-9_/]+", body))
        c.ok(words >= 40, f"section {title} has {words} words of yours — write at least 40")
        parts[title] = body
    c.ok(str(BASE_PORT) in parts["Discovery"], f"the Discovery section does not give your discovery port ({BASE_PORT})")
    up = parts["QoS"].upper()
    for w in ("RELIABLE", "BEST_EFFORT", "TRANSIENT_LOCAL", "VOLATILE"):
        c.ok(w in up, f"the QoS section does not use the word {w}")
    c.ok("incompatible" in parts["QoS"].lower(), "paste the `incompatible QoS` warning line in the QoS section")
    c.ok("/navera/nav_status" in parts["NAVERA"], "the NAVERA section does not mention /navera/nav_status")


c.run()
