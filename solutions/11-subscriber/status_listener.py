#!/usr/bin/env python3
"""status_listener.py — listen to NAVERA's arbiter and say, in words, what it decided.

It subscribes to /navera/nav_status (navera_msgs/NavStatus, 5 times per second) and prints
a line ONLY when the decision (the state or the active source) changes — not 5 lines per second.

    python3 status_listener.py       (with NAVERA's estimator running)
"""
import rclpy
from navera_msgs.msg import NavStatus
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

TOPIC = "/navera/nav_status"


def state_name(state):
    """The name of a NavStatus state number: "INITIALIZING", "NO_FIX", "FIX" or "DEGRADED"."""
    names = {
        NavStatus.STATE_INITIALIZING: "INITIALIZING",
        NavStatus.STATE_NO_FIX: "NO_FIX",
        NavStatus.STATE_FIX: "FIX",
        NavStatus.STATE_DEGRADED: "DEGRADED",
    }
    return names.get(state, f"UNKNOWN STATE {state}")


SOURCE_NAMES = {
    NavStatus.SOURCE_UNKNOWN: "none",
    NavStatus.SOURCE_GPS: "GPS",
    NavStatus.SOURCE_DAY_VISION: "day vision",
    NavStatus.SOURCE_NIGHT_VISION: "night vision",
    NavStatus.SOURCE_CELESTIAL: "celestial",
}


def describe(msg):
    """One line of text for a NavStatus message, e.g.  "FIX | source: GPS | GPS fix"."""
    source = SOURCE_NAMES.get(msg.active_source, str(msg.active_source))
    return f"{state_name(msg.state)} | source: {source} | {msg.reason}"


class StatusListener(Node):
    def __init__(self):
        super().__init__("status_listener")
        self.last_key = None            # (state, active_source) of the last line printed
        self.create_subscription(NavStatus, TOPIC, self.on_status, 10)
        self.get_logger().info(f"listening to {TOPIC}")

    def on_status(self, msg):
        key = (msg.state, msg.active_source)
        if key != self.last_key:
            self.get_logger().info(describe(msg))
            self.last_key = key


# ---- you don't need to change anything below this line ----
def main():
    rclpy.init()
    node = StatusListener()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
