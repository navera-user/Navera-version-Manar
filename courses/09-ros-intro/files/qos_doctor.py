"""qos_doctor.py — runs YOUR incompatible_policies() (navera_lite/ros/qos.py, TODO 1) on examples, then on the
live graph.

    python3 qos_doctor.py test                 your function on the docstring's examples and a few more (Step 8)
    python3 qos_doctor.py /navera_lite/imu     who publishes and who subscribes on a topic, with the QoS each
                                               one offers or requests, and YOUR verdict for every pair (Step 9)

The live mode asks ROS 2 the same question as `ros2 topic info -v`: start the nodes first (in THIS terminal,
with &), wait until they have logged that they started, then run it.
"""
import sys
import time

import runner_kit as rk

# ---- you don't need to change anything in this file (but you can read it!) ----

try:
    import rclpy
except ImportError:
    sys.exit("rclpy cannot be imported: ROS 2 is not sourced in this terminal (run `source /opt/ros/humble/setup.bash`).")

q = rk.load_student("navera_lite.ros.qos")


def _words(qos):
    """Reliability and durability: the two policies TODO 1 looks at."""
    return f"{qos.reliability.name}, {qos.durability.name}"


POLICIES = ("RELIABILITY", "DURABILITY")


def verdict(offered, requested):
    """(text, ok): the student's incompatible_policies() on one pair as "connect" / "NO CONNECTION (…)", or one plain
    sentence about what went wrong."""
    v, err = rk.call(q, "incompatible_policies", offered, requested)
    if err:
        return err, False
    if not isinstance(v, (list, tuple)) or not all(isinstance(x, str) for x in v):
        return (f"incompatible_policies() must return a list of words like [\"RELIABILITY\"] (or [] when they connect), "
                f"but it returned {v!r} (a {type(v).__name__})"), False
    odd = [x for x in v if x not in POLICIES]
    if odd:
        return (f"incompatible_policies() returned {list(v)!r}: use the names ROS prints, \"RELIABILITY\" and "
                "\"DURABILITY\" (capitals; the policy's name, not its value like \"RELIABLE\")"), False
    return ("connect" if not v else "NO CONNECTION (" + ", ".join(v) + ")"), True


def test():
    """The docstring's examples, and a few more pairs from the lesson's §5 tables."""
    cases = [("FIX_QOS → FIX_QOS", q.FIX_QOS, q.FIX_QOS, []),
             ("SENSOR_QOS → FIX_QOS   (docstring)", q.SENSOR_QOS, q.FIX_QOS, ["RELIABILITY"]),
             ("FIX_QOS → SENSOR_QOS   (docstring)", q.FIX_QOS, q.SENSOR_QOS, []),
             ("STATUS_QOS → STATUS_QOS", q.STATUS_QOS, q.STATUS_QOS, []),
             ("FIX_QOS → STATUS_QOS", q.FIX_QOS, q.STATUS_QOS, ["DURABILITY"]),
             ("SENSOR_QOS → STATUS_QOS", q.SENSOR_QOS, q.STATUS_QOS, ["RELIABILITY", "DURABILITY"])]
    print("offered → requested                    yours                         lesson §5")
    good, never_no, early = 0, True, False
    for label, off, req, want in cases:
        text, ok = verdict(off, req)
        if not ok:
            print(f"✘ {label:<36} {text}")
            never_no = False
            continue
        never_no = never_no and text == "connect"
        expect = "connect" if not want else "NO CONNECTION (" + ", ".join(want) + ")"
        mark = "✔" if text == expect else "✘"
        got_names = set(text[len("NO CONNECTION ("):-1].split(", ")) if text.startswith("NO CONNECTION (") else set()
        early = early or (mark == "✘" and len(want) > 1 and got_names < set(want))
        good += mark == "✔"
        print(f"{mark} {label:<36} {text:<29} {expect}")
    if early:
        print("\n  ✘ only one name where both policies fail: did you return after the first one? bad = [], append each "
              "name, return bad at the end")
    print(f"\n{good}/{len(cases)} as in the lesson's tables." +
          ("" if good == len(cases) or early else "  Which policy does each ✘ line differ on? Read the tables of lesson §5 "
                                          "again: who OFFERS (the first profile), who REQUESTS (the second)?"))
    if never_no:
        print("Your function never finds an incompatible policy: do you compare with the constants "
              "(ReliabilityPolicy.BEST_EFFORT), not with text like \"BEST_EFFORT\"? (Step 8, 🧰 box and hints)")
    print("The check uses other profiles (other depths, the four combinations of both policies).")


def live(topic):
    if not topic.startswith("/"):
        topic = "/" + topic
    rclpy.init()
    node = rclpy.create_node("qos_doctor")
    pubs, subs, end = [], [], time.monotonic() + 3.0
    while time.monotonic() < end:                       # discovery takes a moment: ask a few times
        rclpy.spin_once(node, timeout_sec=0.2)
        pubs = node.get_publishers_info_by_topic(topic)
        subs = node.get_subscriptions_info_by_topic(topic)
    types = sorted({e.topic_type for e in pubs + subs})
    node.destroy_node()
    rclpy.shutdown()
    if not pubs and not subs:
        sys.exit(f"Nobody publishes or subscribes on {topic} (yet). Is the node running in THIS terminal (`jobs`)? "
                 "Is the name right (`ros2 topic list`)? Did its log say it started? Try again.")
    print(f"Topic {topic} ({', '.join(types)}): {len(pubs)} publisher(s), {len(subs)} subscriber(s)")
    name = lambda e: (e.node_namespace.rstrip("/") + "/" + e.node_name)
    for e in pubs:
        print(f"  publisher   {name(e):<18} offers    {_words(e.qos_profile)}")
    for e in subs:
        print(f"  subscriber  {name(e):<18} requests  {_words(e.qos_profile)}")
    print("  (history and depth are not listed: discovery does not share them, they never decide a connection)")
    if not pubs or not subs:
        print("\nNo pair to judge: a connection needs a publisher AND a subscriber.")
        return
    print("\nYour incompatible_policies() says:")
    for p in pubs:
        for s in subs:
            text, _ = verdict(p.qos_profile, s.qos_profile)
            print(f"  {name(p)} → {name(s):<18} {text}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    if sys.argv[1] == "test":
        test()
    else:
        live(sys.argv[1])
