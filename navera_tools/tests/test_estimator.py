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
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node

GPS, DAY = PositionEstimate.SOURCE_GPS, PositionEstimate.SOURCE_DAY_VISION


def main():
    # max_speed 500 m/s: a 2 km offset becomes "reachable" after ~4 s, so the
    # patient-spoofer case below runs in seconds.
    proc = subprocess.Popen(["ros2", "run", "navera_estimator", "estimator_node.py",
                             "--ros-args", "-p", "max_speed_mps:=500.0"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rclpy.init()
    n = Node("estimator_test")
    pub = {GPS: n.create_publisher(PositionEstimate, "/navera/estimate/gps", 10),
           DAY: n.create_publisher(PositionEstimate, "/navera/estimate/day", 10)}
    positions, statuses = [], []
    n.create_subscription(PositionEstimate, "/navera/position", positions.append, 10)
    n.create_subscription(NavStatus, "/navera/nav_status", statuses.append, 10)
    executor = SingleThreadedExecutor()
    executor.add_node(n)
    spinner = threading.Thread(target=executor.spin, daemon=True)
    spinner.start()
    # Wait for the estimator to be up (cold starts after a build can be slow),
    # instead of a fixed sleep.
    deadline = time.time() + 20.0
    while not statuses and time.time() < deadline:
        time.sleep(0.2)
    if not statuses:
        print("FAIL estimator did not start within 20 s")
        return 1
    time.sleep(1.0)

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

    settle()
    # Patient spoofer: GPS jumps 2 km and STAYS there while day vision (stated
    # 15 m accuracy) sees the vehicle at A. Reachability alone would accept the
    # spoof after ~4 s here; the independent source must keep it out, then
    # re-admit the true GPS as soon as it agrees again.
    est(GPS)
    time.sleep(0.5)
    t0 = time.time()
    while time.time() - t0 < 7.0:
        est(GPS, lat=35.848)                               # ~2 km north
        est(DAY, var=15.0 ** 2)
        time.sleep(0.5)
    if statuses[-1].active_source == GPS:
        failures.append(f"patient 2 km spoof accepted after 7 s: {statuses[-1].reason}")
    if statuses[-1].active_source != DAY:
        failures.append(f"day vision did not take over during the spoof: {statuses[-1].reason}")
    for _ in range(8):                                     # true GPS back, holdoff 2 s
        est(GPS)
        est(DAY, var=15.0 ** 2)
        time.sleep(0.5)
    if statuses[-1].active_source != GPS or statuses[-1].state != NavStatus.STATE_FIX:
        failures.append(f"true GPS not re-accepted when vision agrees: {statuses[-1].reason}")

    proc.terminate()
    proc.wait(timeout=10)
    # Stop spinning before tearing ROS down: shutting the context down under a
    # spinning thread aborts the interpreter (exit 134) intermittently.
    executor.shutdown()
    spinner.join(timeout=5)
    n.destroy_node()
    rclpy.shutdown()
    for f in failures:
        print("FAIL", f)
    print("estimator:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
