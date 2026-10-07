import os
from academy_check import Background, Checker, load_student, need, wait_for_messages

c = Checker()


def ans(name):
    (v,) = need(load_student("answers.py"), name)
    return v


def num_eq(name, want):
    v = ans(name)
    c.ok(v is not None and str(v).strip() != "", f"{name} has no answer yet")
    c.ok(str(v).strip() == str(want), f"{name} = {v!r} is not right")


def topics(v, name):
    c.ok(isinstance(v, (list, tuple)), f"{name} should be a list like [\"/a\", \"/b\"], got {v!r}")
    c.ok(len(v) > 0, f"{name} is still empty")
    return {str(t).strip() for t in v} - {"/parameter_events", "/rosout"}


@c.test("answers.py loads", hint="Run `python3 answers.py`: it must print nothing and show no error. "
                                   "A missing quote or bracket is the usual reason.")
def _():
    load_student("answers.py")


@c.test("Step 1 — MY_DOMAIN_ID is your ROS domain",
        hint="Run `echo $ROS_DOMAIN_ID` and write the number without quotes.")
def _():
    v = ans("MY_DOMAIN_ID")
    c.ok(v is not None, "MY_DOMAIN_ID is still None")
    c.eq(str(v).strip(), os.environ.get("ROS_DOMAIN_ID", "?"), "MY_DOMAIN_ID")


@c.test("Step 5 — chatter.txt holds one message saved from /chatter",
        hint="With the talker running, run `ros2 topic echo --once /chatter > chatter.txt` "
             "in the lab folder, then open chatter.txt.")
def _():
    c.file_exists("chatter.txt")
    txt = open("chatter.txt", encoding="utf-8", errors="replace").read()
    c.ok("data:" in txt and "Hello World" in txt,
         "chatter.txt should contain a line like  data: 'Hello World: 12'  — got:\n" + txt[:300])


RUN = {}


def live_talker():
    """Start a talker ourselves and measure what ROS really says (done once)."""
    if "msgs" not in RUN:
        from std_msgs.msg import String
        RUN["msgs"], RUN["times"] = [], []
        with Background("ros2 run demo_nodes_py talker", settle=2.0):
            first = wait_for_messages("/chatter", String, count=1, timeout=15)
            if first:
                RUN["msgs"] = wait_for_messages("/chatter", String, count=4, timeout=8)
    c.ok(len(RUN["msgs"]) >= 2, "the check could not receive the talker's messages — tell your teacher "
                                "(the demo talker did not run in your sandbox)")


@c.test("Step 3 — CHATTER_TYPE is the type of /chatter (the check runs a talker to compare)",
        hint="Look at the line `Type:` printed by `ros2 topic info /chatter`. Copy it exactly: "
             "package/msg/Name.")
def _():
    v = str(ans("CHATTER_TYPE")).strip()
    c.ok(v != "", "CHATTER_TYPE is still empty")
    live_talker()
    from std_msgs.msg import String
    real = String.__module__.split(".")[0] + "/msg/" + String.__name__
    c.eq(v, real, "CHATTER_TYPE")


@c.test("Step 3 — TALKER_HZ is the talker's rate",
        hint="Run `ros2 topic hz /chatter`, wait for `average rate:`, then stop it with Ctrl+C.")
def _():
    v = ans("TALKER_HZ")
    c.ok(v is not None, "TALKER_HZ is still None")
    c.near(v, 1.0, 0.2, "TALKER_HZ")


@c.test("Step 4 — CHATTER_SUBSCRIBERS: one listener running",
        hint="With exactly one listener running, `ros2 topic info /chatter` shows `Subscription count:`.")
def _():
    num_eq("CHATTER_SUBSCRIBERS", 1)


@c.test("Step 6 — MODE_REPLAYED in PositionEstimate",
        hint="Run `ros2 interface show navera_msgs/msg/PositionEstimate` and find the line `uint8 MODE_REPLAYED=…`.")
def _():
    from navera_msgs.msg import PositionEstimate
    num_eq("MODE_REPLAYED", PositionEstimate.MODE_REPLAYED)


@c.test("Step 6 — STATE_FIX in NavStatus",
        hint="Run `ros2 interface show navera_msgs/msg/NavStatus` and find `uint8 STATE_FIX=…`.")
def _():
    from navera_msgs.msg import NavStatus
    num_eq("STATE_FIX", NavStatus.STATE_FIX)


@c.test("Step 7 — the estimator's subscriptions",
        hint="`ros2 node info /estimator_node` lists them under `Subscribers:` — there are 5 "
             "(4 estimates and the IMU). Copy each topic name with its leading /.")
def _():
    got = topics(ans("ESTIMATOR_SUBSCRIBES"), "ESTIMATOR_SUBSCRIBES")
    want = {"/navera/estimate/gps", "/navera/estimate/day", "/navera/estimate/night",
            "/navera/estimate/cn", "/navera/sensors/imu"}
    missing, extra = want - got, got - want
    c.ok(not missing and not extra,
         (f"missing: {sorted(missing)}" if missing else "") + ("  " if missing and extra else "") +
         (f"not a subscription of the estimator: {sorted(extra)}" if extra else ""))


@c.test("Step 7 — the estimator's two NAVERA outputs",
        hint="Under `Publishers:` in `ros2 node info /estimator_node`, keep the two topics that start with /navera.")
def _():
    got = topics(ans("ESTIMATOR_PUBLISHES"), "ESTIMATOR_PUBLISHES")
    c.eq(sorted(got), ["/navera/nav_status", "/navera/position"], "ESTIMATOR_PUBLISHES (sorted)")


@c.test("Step 7 — FIRST_STATE: what the arbiter says before any source speaks",
        hint="Read the `state:` line of `ros2 topic echo --once /navera/nav_status` while only the estimator "
             "runs, then compare it with the STATE_… constants of NavStatus.")
def _():
    from navera_msgs.msg import NavStatus
    num_eq("FIRST_STATE", NavStatus.STATE_INITIALIZING)


QUIZ = {"Q1": ("b", "Publish/subscribe: the publisher never knows who listens."),
        "Q2": ("a", "Read the part about ROS_DOMAIN_ID again."),
        "Q3": ("b", "Read the part 'Messages' of the course again.")}
for q, (good, hint) in QUIZ.items():
    @c.test(f"quiz {q}", hint=hint)
    def _(q=q, good=good):
        v = str(ans(q)).strip().lower().strip(")")
        c.ok(v != "", f"{q} has no answer yet")
        c.ok(v == good, f"{q} = \"{v}\" is not the right answer")

c.run()
