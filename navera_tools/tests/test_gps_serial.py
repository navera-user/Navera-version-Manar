#!/usr/bin/env python3
"""Integration test: gps_node fed through a pseudo-terminal (no GPS hardware).

Checks checksum enforcement, fix-quality filtering, ellipsoidal altitude, the
unknown-HDOP case, and that the node exits with code 1 when the port vanishes
(so systemd restarts it). Needs a sourced ROS 2 workspace. Exit code 0 = pass.
"""
import math
import os
import pty
import subprocess
import sys
import threading
import time

import rclpy
from navera_msgs.msg import PositionEstimate
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node


def nmea(body):
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"${body}*{cs:02X}\r\n"


GGA = "GPGGA,123519,3549.7320,N,01038.4000,E,{q},08,{hdop},10.0,M,33.0,M,,"
CASES = [
    # (name, line, expectation: None = nothing published, else dict of checks)
    ("valid fix", nmea(GGA.format(q=1, hdop="0.9")),
     {"valid": True, "alt": 43.0, "cov_type": PositionEstimate.COVARIANCE_TYPE_APPROXIMATED}),
    ("no checksum", "$" + GGA.format(q=1, hdop="0.9") + "\r\n", None),
    ("bad checksum", nmea(GGA.format(q=1, hdop="0.9"))[:-4] + "00\r\n", None),
    ("receiver dead-reckoning (q=6)", nmea(GGA.format(q=6, hdop="0.9")), {"valid": False}),
    ("no HDOP", nmea(GGA.format(q=1, hdop="")),
     {"valid": True, "cov_type": PositionEstimate.COVARIANCE_TYPE_UNKNOWN}),
]


def main():
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        ["ros2", "run", "gps_pkg", "gps_node.py", "--ros-args",
         "-p", f"serial_port:={os.ttyname(slave)}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rclpy.init()
    node = Node("gps_serial_test")
    got = []
    node.create_subscription(PositionEstimate, "/navera/estimate/gps", got.append, 10)
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    spinner = threading.Thread(target=executor.spin, daemon=True)
    spinner.start()
    # Wait until gps_node's publisher is discovered (instead of a fixed sleep).
    deadline = time.time() + 20.0
    while node.count_publishers("/navera/estimate/gps") == 0 and time.time() < deadline:
        time.sleep(0.2)
    if node.count_publishers("/navera/estimate/gps") == 0:
        print("FAIL gps_node did not start within 20 s")
        return 1
    time.sleep(1.0)

    failures = []
    for name, line, expect in CASES:
        before = len(got)
        os.write(master, line.encode())
        time.sleep(1.0)
        new = got[before:]
        if expect is None:
            if new:
                failures.append(f"{name}: published {len(new)} message(s), expected none")
            continue
        if len(new) != 1:
            failures.append(f"{name}: {len(new)} message(s), expected 1")
            continue
        m = new[0]
        if m.valid != expect["valid"]:
            failures.append(f"{name}: valid={m.valid}")
        if "alt" in expect and not math.isclose(m.altitude, expect["alt"], abs_tol=1e-6):
            failures.append(f"{name}: altitude {m.altitude}")
        if "cov_type" in expect and m.position_covariance_type != expect["cov_type"]:
            failures.append(f"{name}: covariance type {m.position_covariance_type}")
        if not m.valid and not math.isnan(m.latitude):
            failures.append(f"{name}: invalid estimate carries a position")

    os.close(master)                                   # unplug the "cable"
    try:
        code = proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        code = None
    if code != 1:
        failures.append(f"port loss: exit code {code}, expected 1")
    # Stop spinning before tearing ROS down: shutting the context down under a
    # spinning thread aborts the interpreter (exit 134) intermittently.
    executor.shutdown()
    spinner.join(timeout=5)
    node.destroy_node()
    rclpy.shutdown()

    for f in failures:
        print("FAIL", f)
    print("gps_serial:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
