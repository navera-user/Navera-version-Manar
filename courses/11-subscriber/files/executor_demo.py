#!/usr/bin/env python3
"""executor_demo.py — a slow callback and a timer: who waits for whom?

The node has two callbacks:
  * a 10 Hz timer (a "control loop" that must run on time), which measures the gaps between its calls;
  * a subscription to /fake_gps/fix whose callback takes 0.3 s ("heavy processing", e.g. image matching).

    python3 executor_demo.py single     one thread: callbacks run one after the other
    python3 executor_demo.py multi      two threads + two callback groups (TODO 4)

Run it while gps_track_player.py publishes. After DURATION_S it prints the statistics and writes
executor_<mode>.json.
"""
import json
import sys
import time

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import NavSatFix

PERIOD_S = 0.1          # the timer: 10 Hz
WORK_S = 0.3            # time spent in each fix callback
DURATION_S = 8.0


class Demo(Node):
    def __init__(self, separate_groups):
        super().__init__("executor_demo")
        timer_group = None          # None = the node's default group (one MutuallyExclusive group for all)
        fix_group = None
        # TODO 4a: when separate_groups is True, give the timer and the subscription EACH its own
        #          MutuallyExclusiveCallbackGroup(), so that a second thread may run one while the
        #          other is busy.
        self.create_timer(PERIOD_S, self.on_timer, callback_group=timer_group)
        self.create_subscription(NavSatFix, "/fake_gps/fix", self.on_fix, qos_profile_sensor_data,
                                 callback_group=fix_group)
        self.ticks = []             # monotonic times of the timer calls
        self.fixes = 0

    def on_timer(self):
        self.ticks.append(time.monotonic())

    def on_fix(self, msg):
        self.fixes += 1
        time.sleep(WORK_S)          # pretend to work hard (sleep releases Python's GIL)


def make_executor(mode):
    """The executor for the mode: 'single' -> SingleThreadedExecutor, 'multi' -> MultiThreadedExecutor."""
    # TODO 4b: return MultiThreadedExecutor(num_threads=2) for "multi".
    return SingleThreadedExecutor()


# ---- you don't need to change anything below this line ----
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "single"
    if mode not in ("single", "multi"):
        sys.exit("usage: python3 executor_demo.py single|multi")
    rclpy.init()
    node = Demo(separate_groups=(mode == "multi"))
    ex = make_executor(mode)
    ex.add_node(node)
    end = time.monotonic() + DURATION_S
    try:
        while time.monotonic() < end:
            ex.spin_once(timeout_sec=0.05)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    gaps = [b - a for a, b in zip(node.ticks[:-1], node.ticks[1:])]
    res = {"mode": mode, "executor": type(ex).__name__, "fixes": node.fixes, "ticks": len(node.ticks),
           "expected_ticks": int(DURATION_S / PERIOD_S),
           "max_gap_ms": 1000 * max(gaps) if gaps else None,
           "mean_gap_ms": 1000 * sum(gaps) / len(gaps) if gaps else None}
    print(json.dumps(res, indent=2))
    with open(f"executor_{mode}.json", "w") as f:
        json.dump(res, f, indent=2)
    time.sleep(WORK_S + 0.1)                  # let a callback still running finish
    ex.shutdown(timeout_sec=2.0)
    if rclpy.ok():
        rclpy.shutdown()                      # also destroys the node


if __name__ == "__main__":
    main()
