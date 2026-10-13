"""latched_probe.py — a late listener of the judge's status: does it get the last status at once, even when it starts
long after the judge published it?

    python3 latched_probe.py          listen for 5 s, then say whether a status arrived
    python3 latched_probe.py 10       listen for 10 s

Lab Step 11, TODO 2: write the subscription (topic, message type, QoS) and the callback. Lesson §5 and lab Step 7
(B1–B3) tell you which QoS a LATE subscriber of a latched topic must request.
"""
import sys
import time

import rclpy
from rclpy.node import Node

TOPIC = "navera_lite/status"        # relative name: /navera_lite/status when the node has no namespace


class LatchedProbe(Node):
    """Prints the reason (msg.message) of the first status it receives, and remembers it in self.first."""

    def __init__(self):
        super().__init__("latched_probe")
        self.first = None              # the text of the first status received, None until then
        # TODO 2: subscribe to TOPIC (type: DiagnosticStatus from diagnostic_msgs.msg) with a QoS that also
        #         delivers the status kept for late subscribers, and with self.on_status as the callback.

    def on_status(self, msg):
        # TODO 2: the first time only, keep msg.message in self.first and print it like this:
        #         print(f"first status: {msg.message}", flush=True)
        pass


# ---- you don't need to change anything below this line ----
def main():
    try:
        seconds = float(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else 5.0
    except ValueError:
        sys.exit(f"usage: python3 latched_probe.py [seconds] — {sys.argv[1]!r} is not a number of seconds")
    rclpy.init()
    node = LatchedProbe()
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < seconds:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    if node.first is None:
        print(f"no status received in {seconds:.1f} s on {node.resolve_topic_name(TOPIC)}", flush=True)
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
