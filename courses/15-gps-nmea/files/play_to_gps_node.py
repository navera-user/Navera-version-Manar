"""Feed an NMEA log to NAVERA's REAL GPS driver, as if a GPS receiver were plugged in.

    python3 play_to_gps_node.py                (the Sousse drive, about 40 seconds)
    python3 play_to_gps_node.py other.nmea

How it works: a "pseudo-terminal" is a fake serial port. We start NAVERA's gps_node
(ros2 run gps_pkg gps_node.py) on it, write the log into it line by line, and count
the messages gps_node publishes on /navera/estimate/gps (navera_msgs/PositionEstimate):
valid ones (a usable fix) and invalid ones (no fix, or a fix NAVERA does not trust).
The same trick is used by NAVERA's own test navera_tools/tests/test_gps_serial.py.
The counts are saved in gps_node_counts.json (the check reads them).
"""
import json
import math
import os
import pty
import signal
import subprocess
import sys
import threading
import time
import tty

import rclpy
from navera_msgs.msg import PositionEstimate
from rclpy.executors import SingleThreadedExecutor

PATH = sys.argv[1] if len(sys.argv) > 1 else "/data/academy/15-gps-nmea/sousse_drive.nmea"
PAUSE_S = 0.004                     # between two lines: the 1069 s drive plays in ~25 s


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def main():
    with open(PATH, "rb") as f:
        lines = f.read().splitlines()          # raw bytes: a damaged byte stays damaged
    master, slave = pty.openpty()
    tty.setraw(slave)
    port = os.ttyname(slave)
    print(f"fake serial port: {port}")
    node_proc = subprocess.Popen(["ros2", "run", "gps_pkg", "gps_node.py", "--ros-args",
                                  "-p", f"serial_port:={port}", "--log-level", "warn"],
                                 start_new_session=True)
    rclpy.init()
    node = rclpy.create_node("nmea_player")
    got = []
    node.create_subscription(PositionEstimate, "/navera/estimate/gps", got.append, 50)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    stop = threading.Event()

    def spin():
        while not stop.is_set():
            ex.spin_once(timeout_sec=0.1)
    spinner = threading.Thread(target=spin)
    spinner.start()
    try:
        t_end = time.time() + 20.0                       # wait until gps_node is up and connected
        while node.count_publishers("/navera/estimate/gps") == 0:
            if node_proc.poll() is not None or time.time() > t_end:
                sys.exit("gps_node did not start — is your NAVERA copy built? (lesson 9)")
            time.sleep(0.2)
        time.sleep(1.0)
        print(f"playing {len(lines)} lines of {PATH} into gps_node…")
        for i, ln in enumerate(lines):
            os.write(master, ln + b"\r\n")
            time.sleep(PAUSE_S)
            if i % 1000 == 0:
                print(f"  line {i:4d}: {len(got)} estimates received so far")
        time.sleep(1.5)
    finally:
        os.killpg(node_proc.pid, signal.SIGINT)
        try:
            node_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(node_proc.pid, signal.SIGKILL)
        stop.set()
        spinner.join()
        node.destroy_node()
        rclpy.try_shutdown()
    valid = [m for m in got if m.valid]
    invalid = [m for m in got if not m.valid]
    reasons = {}
    for m in invalid:
        reasons[m.reason] = reasons.get(m.reason, 0) + 1
    print(f"\ngps_node published {len(got)} PositionEstimate messages:")
    print(f"  valid (usable fix): {len(valid)}")
    print(f"  invalid           : {len(invalid)}")
    for r, n in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"      {n:3d} x  {r}")
    jump, at = 0.0, None                 # largest distance between two consecutive valid fixes
    for a, b in zip(valid, valid[1:]):
        d = haversine_m(a.latitude, a.longitude, b.latitude, b.longitude)
        if d > jump:
            jump, at = d, (b.latitude, b.longitude)
    if at:
        print(f"largest jump between two consecutive valid fixes: {jump / 1000:.1f} km "
              f"(to lat {at[0]:.5f}, lon {at[1]:.5f})")
    with open("gps_node_counts.json", "w") as f:
        json.dump({"log": PATH, "published": len(got), "valid": len(valid), "invalid": len(invalid),
                   "reasons": reasons, "max_jump_m": round(jump, 1)}, f, indent=2, ensure_ascii=False)
    print("saved gps_node_counts.json")
    if valid:
        m = valid[0]
        print(f"first valid fix: lat {m.latitude:.6f}, lon {m.longitude:.6f}, "
              f"altitude {m.altitude:.1f} m (ellipsoid), sigma {m.position_covariance[0] ** 0.5:.2f} m, "
              f"details {m.details_json}")


if __name__ == "__main__":
    main()
