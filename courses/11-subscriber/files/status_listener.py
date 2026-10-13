"""status_listener.py — listen to the judge (arbiter v0) and say, in words, what it decided.

A second subscriber WITH MEMORY. It subscribes to two topics:
  navera_lite/status    the judge's decision (DiagnosticStatus, 5 or more a second, latched)
  navera_lite/fix/gps   the GPS fixes, only to remember the stamp of the last one
and prints a line ONLY when the decision (state, source) changes. When the judge falls to NO_FIX, it also
prints how long the GPS had been silent: the time of that status minus the stamp of the last GPS fix
(each value is also added to out/silence.json).

    python3 status_listener.py          (with arbiter v0 running; Ctrl+C to stop)
"""
import json
import os

from diagnostic_msgs.msg import DiagnosticStatus
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix

from navera_lite.ros.convert import stamp_to_s, status_values
from navera_lite.ros.qos import FIX_QOS, STATUS_QOS
from navera_lite.ros.runner import run_node

# ---- you don't need to change anything in this file (but you can read it!) ----


def log_value(path, value):
    """Append one measurement to a JSON list in out/ (the check compares your answers with it)."""
    try:
        with open(path) as f:
            values = json.load(f)
    except (OSError, ValueError):
        values = []
    values.append(value)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(values, f)


class StatusListener(Node):
    def __init__(self):
        super().__init__("status_listener")
        self.last_key = None          # memory 1: (state, source) of the last line printed
        self.last_gps_stamp = None    # memory 2: the stamp (s) of the newest GPS fix heard
        self.status_sub = self.create_subscription(DiagnosticStatus, "navera_lite/status", self.on_status,
                                                   STATUS_QOS)
        self.gps_sub = self.create_subscription(NavSatFix, "navera_lite/fix/gps", self.on_gps, FIX_QOS)
        self.get_logger().info(f"listening to {self.resolve_topic_name('navera_lite/status')}")

    def now_s(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def on_gps(self, msg):
        self.last_gps_stamp = stamp_to_s(msg.header.stamp)

    def on_status(self, msg):
        values = status_values(msg)
        key = (values.get("state", "?"), values.get("source", ""))
        if key == self.last_key:
            return                    # nothing new: stay quiet
        self.last_key = key
        self.get_logger().info(f"{key[0]} | source: {key[1] or 'none'} | {msg.message}")
        if key[0] == "NO_FIX":
            if self.last_gps_stamp is None:
                self.get_logger().info("GPS silent: not measured (no GPS fix heard since the last NO_FIX — "
                                       "let the GPS run 5 s after FIX before you stop it)")
            else:
                silent = self.now_s() - self.last_gps_stamp
                self.get_logger().info(f"GPS silent for {silent:.2f} s (since the stamp of its last fix)")
                log_value("out/silence.json", round(silent, 2))
            self.last_gps_stamp = None    # each measurement needs fixes heard in THIS run of the GPS


def main(args=None):
    run_node(StatusListener, args)


if __name__ == "__main__":
    main()
