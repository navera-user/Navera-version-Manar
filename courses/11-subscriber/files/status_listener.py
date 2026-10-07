#!/usr/bin/env python3
"""status_listener.py — listen to NAVERA's arbiter and say, in words, what it decided.

It subscribes to /navera/nav_status (navera_msgs/NavStatus, 5 times per second) and logs a line
ONLY when the decision (the state or the active source) changes. When GPS goes silent and the
arbiter falls to NO_FIX, it also logs how long GPS had been silent.

    python3 status_listener.py       (with NAVERA's estimator running)
"""
import rclpy
from navera_msgs.msg import NavStatus, SourceHealth
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

TOPIC = "/navera/nav_status"


def state_name(state):
    """The name of a NavStatus state number: "INITIALIZING", "NO_FIX", "FIX" or "DEGRADED"."""
    # TODO 5: return the right name for each of the 4 states, using the constants of the message
    #         (NavStatus.STATE_INITIALIZING, NavStatus.STATE_NO_FIX, ...) — never the bare numbers.
    #         For any other number, return f"UNKNOWN STATE {state}".
    return "?"


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


def to_s(stamp):
    """A builtin_interfaces/Time in seconds (float)."""
    return stamp.sec + stamp.nanosec * 1e-9


def gps_silence_s(msg):
    """How long GPS has been silent when this status was computed: header.stamp minus the
    last_seen of the GPS entry of msg.sources. None if GPS was never heard (last_seen is 0)."""
    # TODO 6: find the entry of msg.sources whose .source == SourceHealth.SOURCE_GPS; if its
    #         last_seen is zero (never heard) or there is none, return None; else return
    #         to_s(msg.header.stamp) - to_s(entry.last_seen).
    return None


class StatusListener(Node):
    def __init__(self):
        super().__init__("status_listener")
        self.last_key = None            # (state, active_source) of the last line logged
        # TODO 7a: subscribe to NavStatus on TOPIC (depth 10) with the callback self.on_status
        self.get_logger().info(f"listening to {TOPIC}")

    def on_status(self, msg):
        # TODO 7b: when (msg.state, msg.active_source) differs from self.last_key:
        #            - log describe(msg)
        #            - if the new state is NO_FIX and gps_silence_s(msg) is not None, also log
        #              exactly:  GPS silent for 3.12 s      (two decimals)
        #            - store the new key in self.last_key
        #          Otherwise do nothing: NAVERA publishes 5 statuses per second.
        pass


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
