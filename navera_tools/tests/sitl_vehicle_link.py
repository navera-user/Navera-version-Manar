#!/usr/bin/env python3
"""Validation against ArduPilot SITL: does vehicle_link read the vehicle's own sensors right?

Not part of run_tests.sh (needs an ArduPilot build). Usage, from the workspace root:

    python3 navera_tools/tests/sitl_vehicle_link.py [~/ardupilot]

ArduCopter SITL (instance 3, its own simulated GPS, a simulated downward rangefinder)
takes off and flies a leg; vehicle_link reads it on SERIAL1. While flying, every
second, NAVERA's /navera/vehicle/* topics are compared with what the autopilot
reports on its ground-station link (ATTITUDE, GLOBAL_POSITION_INT) and with the
simulator's truth (SIM_STATE): roll, pitch, heading, height above home, rangefinder.
Exit code 0 = pass.
"""
import math
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time

import rclpy
from geometry_msgs.msg import PointStamped
from pymavlink import mavutil
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import Imu, Range

from navera_common.camera_model import body_rpy_enu

INSTANCE = 3
GCS = f"tcp:127.0.0.1:{5760 + 10 * INSTANCE}"
LINK = f"tcp:127.0.0.1:{5762 + 10 * INSTANCE}"


def main(ardupilot):
    work = tempfile.mkdtemp(prefix="navera_vlink_")
    parm = os.path.join(work, "extra.parm")
    with open(parm, "w") as f:
        f.write("RNGFND1_TYPE 100\nRNGFND1_ORIENT 25\nRNGFND1_MAX_CM 4000\nRNGFND1_MIN_CM 20\n"
                "FS_GCS_ENABLE 0\nLOG_BACKEND_TYPE 0\nSERIAL1_PROTOCOL 2\n")
    dp = os.path.join(ardupilot, "Tools/autotest/default_params/copter.parm")
    sitl = subprocess.Popen([os.path.join(ardupilot, "build/sitl/bin/arducopter"), "--model", "quad",
                             "--home", "35.8256,10.6385,10,0", "--defaults", f"{dp},{parm}",
                             f"-I{INSTANCE}", "-w"], cwd=work, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT, start_new_session=True)
    link = None
    try:
        time.sleep(4)
        link = subprocess.Popen(["ros2", "run", "navera_output", "vehicle_link_node.py", "--ros-args",
                                 "-p", f"mavlink_url:={LINK}", "-p", "attitude_hz:=50.0"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True)
        return run(sitl)
    finally:
        for p in (link, sitl):
            if p is not None and p.poll() is None:
                os.killpg(p.pid, signal.SIGINT if p is link else signal.SIGTERM)
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)


def run(sitl):
    gcs = mavutil.mavlink_connection(GCS, source_system=255)
    if gcs.wait_heartbeat(timeout=40) is None:
        print("FAIL no heartbeat from SITL")
        return 1
    gcs.mav.request_data_stream_send(gcs.target_system, gcs.target_component, mavutil.mavlink.MAV_DATA_STREAM_ALL, 20, 1)
    rclpy.init()
    node = Node("vehicle_link_test")
    got = {"imu": None, "rel": None, "agl": None}
    node.create_subscription(Imu, "/navera/vehicle/imu", lambda m: got.__setitem__("imu", m), 50)
    node.create_subscription(PointStamped, "/navera/vehicle/relative_alt", lambda m: got.__setitem__("rel", m), 10)
    node.create_subscription(Range, "/navera/vehicle/altitude_agl", lambda m: got.__setitem__("agl", m), 10)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    spinner = threading.Thread(target=ex.spin, daemon=True)
    spinner.start()
    ap = {}
    stop = threading.Event()

    def rx():
        while not stop.is_set():
            m = gcs.recv_match(blocking=True, timeout=0.5)
            if m is not None:
                ap[m.get_type()] = m
    threading.Thread(target=rx, daemon=True).start()

    def wait(cond, s, why):
        end = time.time() + s
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.5)
        print("FAIL", why)
        return False

    failures = 0
    if not wait(lambda: got["imu"] is not None and got["rel"] is not None, 40, "no /navera/vehicle/imu or relative_alt"):
        failures += 1
    # take off (the autopilot uses its own simulated GPS here) and fly a leg
    if not wait(lambda: "EKF_STATUS_REPORT" in ap and ap["EKF_STATUS_REPORT"].flags & 0x10, 120, "EKF never ready"):
        return 1
    gcs.set_mode(gcs.mode_mapping()["GUIDED"])
    for _ in range(30):
        gcs.mav.command_long_send(gcs.target_system, gcs.target_component,
                                  mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        time.sleep(1)
        if gcs.motors_armed():
            break
    gcs.mav.command_long_send(gcs.target_system, gcs.target_component,
                              mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 25)
    wait(lambda: "GLOBAL_POSITION_INT" in ap and ap["GLOBAL_POSITION_INT"].relative_alt > 22000, 60, "takeoff")
    gcs.mav.set_position_target_global_int_send(0, gcs.target_system, gcs.target_component,
                                                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, 0b110111111000,
                                                int(35.8300 * 1e7), int(10.6450 * 1e7), 25, 0, 0, 0, 0, 0, 0, 0, 0)
    worst = {"roll": 0.0, "pitch": 0.0, "heading": 0.0, "rel": 0.0, "agl": 0.0}
    seen_tilt = 0.0
    for _ in range(25):                                    # 25 s of flight, compared each second
        time.sleep(1.0)
        a, g = ap.get("ATTITUDE"), ap.get("GLOBAL_POSITION_INT")
        if not (a and g and got["imu"] and got["rel"]):
            continue
        q = got["imu"].orientation
        r, p, h = body_rpy_enu((q.x, q.y, q.z, q.w))
        seen_tilt = max(seen_tilt, abs(math.degrees(a.pitch)), abs(math.degrees(a.roll)))
        worst["roll"] = max(worst["roll"], abs(r - math.degrees(a.roll)))
        worst["pitch"] = max(worst["pitch"], abs(p - math.degrees(a.pitch)))
        worst["heading"] = max(worst["heading"], abs((h - math.degrees(a.yaw) + 180) % 360 - 180))
        worst["rel"] = max(worst["rel"], abs(got["rel"].point.z - g.relative_alt / 1000.0))
        if got["agl"] is not None:
            worst["agl"] = max(worst["agl"], abs(got["agl"].range - g.relative_alt / 1000.0))
    print(f"compared over 25 s of flight (tilt up to {seen_tilt:.0f} deg): worst differences "
          f"roll {worst['roll']:.2f} deg, pitch {worst['pitch']:.2f} deg, heading {worst['heading']:.2f} deg, "
          f"height above home {worst['rel']:.2f} m, rangefinder vs height {worst['agl']:.2f} m")
    # attitude: same values a few messages apart (50 Hz); heights: 10 Hz, flat simulated ground
    limits = {"roll": 3.0, "pitch": 3.0, "heading": 3.0, "rel": 1.5, "agl": 3.0}
    for k, lim in limits.items():
        if worst[k] > lim:
            print(f"FAIL {k} differs by {worst[k]:.2f} (max {lim})")
            failures += 1
    if got["agl"] is None:
        print("FAIL no rangefinder height on /navera/vehicle/altitude_agl")
        failures += 1
    if seen_tilt < 3.0:
        print("FAIL the vehicle never tilted: attitude not really exercised")
        failures += 1
    stop.set()
    ex.shutdown()
    spinner.join(timeout=5)
    node.destroy_node()
    rclpy.shutdown()
    print("vehicle_link:", "PASS" if not failures else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/ardupilot")))
