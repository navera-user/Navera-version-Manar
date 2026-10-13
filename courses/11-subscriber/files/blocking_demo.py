"""blocking_demo.py — one slow callback and one timer in the same node: who waits for whom?

The node "blocking_demo" has two callbacks:
  * a 10 Hz timer (think: a control loop that must run on time); it measures the gaps between its calls;
  * a subscription to navera_lite/fix/gps whose callback works for WORK seconds (think: image matching).

    python3 blocking_demo.py single                one thread (what rclpy.spin() gives you)
    python3 blocking_demo.py multi                 two threads, timer and subscription in two callback groups
    python3 blocking_demo.py shared                two threads, but both callbacks in the node's default group
    python3 blocking_demo.py single --work 0.1     a lighter callback

Start a GPS first, in the background in this terminal (5 fixes a second):
    python3 -m navera_lite.ros.gps_node --ros-args -p rate_hz:=5.0 > gps.log 2>&1 &
It runs for 10 s, then prints what happened.
"""
import argparse
import json
import os
import time

import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor, SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix

from navera_lite.ros.convert import stamp_to_s
from navera_lite.ros.qos import FIX_QOS

# ---- you don't need to change anything in this file (but you can read it!) ----

PERIOD_S = 0.1          # the timer: 10 Hz
DURATION_S = 10.0


class Demo(Node):
    def __init__(self, work_s, own_groups):
        super().__init__("blocking_demo")
        self.work_s = work_s
        timer_group = fix_group = None         # None = the node's default group: one mutually exclusive group
        if own_groups:
            timer_group = MutuallyExclusiveCallbackGroup()
            fix_group = MutuallyExclusiveCallbackGroup()
        self.create_timer(PERIOD_S, self.on_timer, callback_group=timer_group)
        self.sub = self.create_subscription(NavSatFix, "navera_lite/fix/gps", self.on_fix, FIX_QOS,
                                            callback_group=fix_group)
        self.ticks = []            # when the timer really ran (monotonic clock, s)
        self.ages = []             # how old each fix was when its callback started (s)
        self.stamps = []

    def now_s(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def on_timer(self):
        self.ticks.append(time.monotonic())

    def on_fix(self, msg):
        self.ages.append(self.now_s() - stamp_to_s(msg.header.stamp))
        self.stamps.append(stamp_to_s(msg.header.stamp))
        time.sleep(self.work_s)              # "heavy work" (sleep lets other threads run)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("single", "multi", "shared"))
    ap.add_argument("--work", type=float, default=0.3, help="seconds of work per fix (default 0.3)")
    a = ap.parse_args()
    rclpy.init()
    node = Demo(a.work, own_groups=(a.mode == "multi"))
    ex = SingleThreadedExecutor() if a.mode == "single" else MultiThreadedExecutor(num_threads=2)
    ex.add_node(node)
    print(f"mode {a.mode}: {type(ex).__name__}, "
          f"{'two callback groups' if a.mode == 'multi' else 'one (default) callback group'}, "
          f"work {a.work:g} s per fix. Listening for {DURATION_S:g} s…")
    start = time.monotonic()
    try:
        while time.monotonic() < start + DURATION_S:
            ex.spin_once(timeout_sec=0.05)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    gaps = [b - a for a, b in zip(node.ticks, node.ticks[1:])]
    ages = node.ages
    span = (node.stamps[-1] - node.stamps[0]) if len(node.stamps) > 1 else 0.0
    if not ages:
        print("\nNo fix arrived. Is the GPS running (`python3 -m navera_lite.ros.gps_node --ros-args -p "
              "rate_hz:=5.0 > gps.log 2>&1 &` in THIS terminal, in the background; `jobs` shows it)? Wait 2 s after "
              "starting it, then try again.")
    else:
        print(f"\n  timer ticks        {len(node.ticks):3d} of {int(DURATION_S / PERIOD_S)}")
        print(f"  longest timer gap  {1000 * max(gaps):5.0f} ms   (it should be {1000 * PERIOD_S:.0f} ms)")
        steps = [b - a for a, b in zip(node.stamps, node.stamps[1:])]
        period = sorted(steps)[len(steps) // 2] if steps else 0.0
        skipped = sum(max(0, round(s / period) - 1) for s in steps) if period > 0 else 0
        print(f"  fixes handled      {len(ages):3d}   (their stamps span {span:.1f} s; {skipped} fixes in between "
              "were never handled)")
        print(f"  age of a fix when its callback started: first {ages[0]:.2f} s, last {ages[-1]:.2f} s, "
              f"max {max(ages):.2f} s")
        record = {"mode": a.mode, "work_s": a.work, "ticks": len(node.ticks),
                  "gap_ms": round(1000 * max(gaps)) if gaps else None, "max_age_s": round(max(ages), 2),
                  "time": time.strftime("%H:%M:%S")}
        try:
            with open("out/blocking.json") as f:
                runs = json.load(f)
        except (OSError, ValueError):
            runs = []
        os.makedirs("out", exist_ok=True)
        with open("out/blocking.json", "w") as f:
            json.dump(runs + [record], f, indent=1)
        print("  (this run was added to out/blocking.json)")
    time.sleep(a.work + 0.1)                  # let a callback still running finish
    ex.shutdown(timeout_sec=2.0)
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
