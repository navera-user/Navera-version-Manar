#!/usr/bin/env python3
"""The autopilot's FIRST GPS as NAVERA's GPS, against ArduPilot SITL (wiring C: the client's
GPS stays on the autopilot as GPS1, NAVERA feeds it as GPS2).

Not part of run_tests.sh (needs an ArduPilot build). Usage, from the workspace root:

    python3 navera_tools/tests/sitl_gps1_monitor.py [~/ardupilot]

ArduCopter SITL (instance 6): GPS_TYPE 1 (its simulated receiver), GPS_TYPE2 14 (MAVLink: where
NAVERA's GPS_INPUT goes), MAVLink on SERIAL1 = tcp 5822. Checks:
  1. discovery finds the autopilot over TCP and chooses NAVERA_GPS_SOURCE=vehicle_gps1;
  2. vehicle_link (read_gps1) publishes /navera/vehicle/gps1 at the SITL home position;
  3. GPS_TYPE set to 14 (now NAVERA would feed GPS1): vehicle_link stops publishing it
     (NAVERA never reads its own output back), and discovery no longer chooses it.
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
from pymavlink import mavutil
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import NavSatFix

from navera_common.discovery import autopilot_streams, decide, probe_mavlink_url

INSTANCE = 6
GCS = f"tcp:127.0.0.1:{5760 + 10 * INSTANCE}"
LINK = f"tcp:127.0.0.1:{5762 + 10 * INSTANCE}"
HOME = (35.8256, 10.6385)


def main(ardupilot):
    work = tempfile.mkdtemp(prefix="navera_gps1_")
    with open(os.path.join(work, "extra.parm"), "w") as f:
        f.write("SERIAL1_PROTOCOL 2\nGPS_TYPE 1\nGPS_TYPE2 14\nFS_GCS_ENABLE 0\nLOG_BACKEND_TYPE 0\n")
    dp = os.path.join(ardupilot, "Tools/autotest/default_params/copter.parm")
    sitl = subprocess.Popen([os.path.join(ardupilot, "build/sitl/bin/arducopter"), "--model", "quad",
                             "--home", f"{HOME[0]},{HOME[1]},10,0", "--defaults", f"{dp},{work}/extra.parm",
                             f"-I{INSTANCE}", "-w"], cwd=work, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT, start_new_session=True)
    link, failures = None, []
    try:
        gcs = mavutil.mavlink_connection(GCS, source_system=255)
        if gcs.wait_heartbeat(timeout=40) is None:
            print("FAIL no heartbeat from SITL")
            return 1
        gcs.mav.request_data_stream_send(gcs.target_system, gcs.target_component,
                                         mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)
        end = time.time() + 90
        while time.time() < end:
            m = gcs.recv_match(type="GPS_RAW_INT", blocking=True, timeout=1)
            if m is not None and m.fix_type >= 3:
                break
        ap = probe_mavlink_url(LINK)                      # the TCP probe discovery runs
        if not ap:
            print("FAIL the autopilot was not found over TCP")
            return 1
        st = autopilot_streams(LINK)
        d = decide({"network": [ap], "autopilot_streams": st}, {})
        print("1. " + next(r for r in d["report"] if r.startswith("GPS")))
        if d["settings"].get("NAVERA_GPS_SOURCE") != "vehicle_gps1":
            failures.append(f"discovery chose {d['settings'].get('NAVERA_GPS_SOURCE')}, expected vehicle_gps1")
        os.environ.setdefault("ROS_DOMAIN_ID", "86")
        link = subprocess.Popen(["ros2", "run", "navera_output", "vehicle_link_node.py", "--ros-args",
                                 "-p", f"mavlink_url:={LINK}", "-p", "relay_port:=0", "-p", "read_gps1:=true"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True)
        rclpy.init()
        node = rclpy.create_node("gps1_test")
        got = []
        node.create_subscription(NavSatFix, "/navera/vehicle/gps1", lambda m: got.append((time.time(), m)),
                                 qos_profile_sensor_data)
        ex = SingleThreadedExecutor()
        ex.add_node(node)
        threading.Thread(target=ex.spin, daemon=True).start()
        end = time.time() + 40
        while not got and time.time() < end:
            time.sleep(0.5)
        if not got:
            failures.append("vehicle_link published no /navera/vehicle/gps1")
        else:
            m = got[-1][1]
            err = math.hypot((m.latitude - HOME[0]) * 111320, (m.longitude - HOME[1]) * 111320 * math.cos(
                math.radians(HOME[0])))
            print(f"2. /navera/vehicle/gps1: {m.latitude:.6f}, {m.longitude:.6f} ({err:.1f} m from home), "
                  f"covariance type {m.position_covariance_type}")
            if err > 20:
                failures.append(f"GPS1 {err:.0f} m from the SITL home")
        gcs.mav.param_set_send(gcs.target_system, gcs.target_component, b"GPS_TYPE", 14,
                               mavutil.mavlink.MAV_PARAM_TYPE_INT8)
        t_set = time.time()
        time.sleep(35)                                     # the change is announced, else re-read in 30 s
        late = [t for t, _ in got if t > t_set + 33]
        last = max((t for t, _ in got), default=0) - t_set
        print(f"3. GPS_TYPE=14: last /navera/vehicle/gps1 {last:.1f} s after the change; "
              f"{len(late)} message(s) in the last 2 s")
        if late:
            failures.append("vehicle_link kept publishing GPS1 after it became NAVERA's own (type 14)")
        os.killpg(link.pid, signal.SIGINT)                 # SITL's TCP port takes one client
        link.wait(timeout=10)
        d14 = decide({"network": [ap], "autopilot_streams": autopilot_streams(LINK)}, {})
        line = next(r for r in d14["report"] if r.startswith("GPS"))
        print("   " + line)
        if d14["settings"].get("NAVERA_GPS_SOURCE") != "none" or "NAVERA's own output" not in line:
            failures.append(f"with GPS_TYPE=14 discovery chose {d14['settings'].get('NAVERA_GPS_SOURCE')} ({line})")
        ex.shutdown()
        node.destroy_node()
        rclpy.shutdown()
    finally:
        for p in (link, sitl):
            if p is not None and p.poll() is None:
                os.killpg(p.pid, signal.SIGINT if p is link else signal.SIGTERM)
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, signal.SIGKILL)
    for f in failures:
        print("FAIL", f)
    print("sitl_gps1_monitor:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/ardupilot")))
