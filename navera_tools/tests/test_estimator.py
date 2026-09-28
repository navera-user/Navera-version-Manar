#!/usr/bin/env python3
"""Integration test: navera_estimator driven by scripted source estimates.

Checks: one estimate is published once; a future stamp is refused; a NaN
position marked valid is refused; a flapping GPS does not zig-zag the output;
losing GPS falls back to day vision immediately; a sudden GPS jump (spoofing)
is refused and GPS is re-accepted once it is plausible again; a large stated
uncertainty is DEGRADED, not FIX. Needs a sourced ROS 2
workspace. Exit code 0 = pass.
"""
import math
import subprocess
import sys
import threading
import time

import rclpy
from navera_msgs.msg import NavStatus, PositionEstimate
from rclpy.duration import Duration
from rclpy.node import Node

GPS, DAY = PositionEstimate.SOURCE_GPS, PositionEstimate.SOURCE_DAY_VISION


def main():
    proc = subprocess.Popen(["ros2", "run", "navera_estimator", "estimator_node.py"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rclpy.init()
    n = Node("estimator_test")
    pub = {GPS: n.create_publisher(PositionEstimate, "/navera/estimate/gps", 10),
           DAY: n.create_publisher(PositionEstimate, "/navera/estimate/day", 10)}
    positions, statuses = [], []
    n.create_subscription(PositionEstimate, "/navera/position", positions.append, 10)
    n.create_subscription(NavStatus, "/navera/nav_status", statuses.append, 10)
    threading.Thread(target=rclpy.spin, args=(n,), daemon=True).start()
    time.sleep(4.0)

    def est(src, lat=35.83, lon=10.64, valid=True, ahead_s=0.0, known_cov=True, var=4.0):
        m = PositionEstimate()
        m.header.stamp = (n.get_clock().now() + Duration(seconds=ahead_s)).to_msg()
        m.latitude, m.longitude, m.altitude = lat, lon, math.nan
        if known_cov:
            m.position_covariance = [var, 0.0, 0.0, 0.0, var, 0.0, 0.0, 0.0, 4 * var]
            m.position_covariance_type = PositionEstimate.COVARIANCE_TYPE_APPROXIMATED
        m.source, m.mode, m.valid = src, PositionEstimate.MODE_MEASURED, valid
        pub[src].publish(m)

    def settle():
        time.sleep(3.6)                   # > gps/day timeout (3 s): back to NO_FIX

    failures = []

    positions.clear()
    est(GPS)
    time.sleep(2.5)
    if len(positions) != 1:
        failures.append(f"one estimate published {len(positions)} times")
    if statuses[-1].state != NavStatus.STATE_FIX:
        failures.append("valid GPS with known covariance is not FIX")
    settle()

    est(GPS, ahead_s=60.0)
    time.sleep(1.0)
    if statuses[-1].state != NavStatus.STATE_NO_FIX or "future" not in statuses[-1].reason:
        failures.append(f"future stamp accepted: {statuses[-1].reason}")
    settle()

    est(GPS, lat=math.nan)
    time.sleep(1.0)
    if statuses[-1].state != NavStatus.STATE_NO_FIX:
        failures.append("NaN position marked valid was accepted")
    settle()

    statuses.clear()
    t0, k = time.time(), 0
    while time.time() - t0 < 8.0:
        est(GPS, valid=(k % 2 == 0))
        if k % 2 == 0:
            est(DAY, lat=35.834, lon=10.645, known_cov=False)
        k += 1
        time.sleep(0.5)
    srcs = [s.active_source for s in statuses]
    switches = sum(1 for a, b in zip(srcs, srcs[1:]) if a != b)
    if switches > 2:
        failures.append(f"flapping GPS switched the source {switches} times")

    statuses.clear()
    est(DAY, lat=35.834, lon=10.645, known_cov=False)       # GPS silent now
    time.sleep(1.0)
    if statuses[-1].active_source != DAY or statuses[-1].state != NavStatus.STATE_DEGRADED:
        failures.append("day vision did not take over as DEGRADED after GPS loss")

    settle()
    est(GPS, var=40.0 ** 2)                                # HDOP ~20: sigma 40 m
    time.sleep(1.0)
    if statuses[-1].state != NavStatus.STATE_DEGRADED:
        failures.append("GPS with 40 m sigma reported as FIX")

    settle()
    # Spoofing: GPS at A, then a sudden 5 km jump 1 s later, then back at A.
    est(GPS)
    time.sleep(1.0)
    est(GPS, lat=35.875)                                   # ~5 km north, 1 s later
    time.sleep(0.6)
    if statuses[-1].state != NavStatus.STATE_NO_FIX or "spoofing" not in statuses[-1].reason:
        failures.append(f"5 km GPS jump was not refused: {statuses[-1].reason}")
    est(GPS)                                               # plausible again
    time.sleep(0.6)
    if statuses[-1].state != NavStatus.STATE_FIX:
        failures.append("GPS not re-accepted once plausible again")

    proc.terminate()
    proc.wait(timeout=10)
    rclpy.shutdown()
    for f in failures:
        print("FAIL", f)
    print("estimator:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
