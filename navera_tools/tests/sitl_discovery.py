#!/usr/bin/env python3
"""Discovery against ArduPilot SITL: does NAVERA find an autopilot by itself and choose it?

Not part of run_tests.sh (needs an ArduPilot build). Usage, from the workspace root:

    python3 navera_tools/tests/sitl_discovery.py [~/ardupilot]

ArduCopter SITL (instance 4) with a second GPS and a downward rangefinder, MAVLink on its
SERIAL1 (tcp 5802 — given to discovery as NAVERA_DISCOVER_MAVLINK, as a serial port would
be found by scanning). Discovery must find it, learn that it streams attitude and a second
GPS, and choose: attitude from the vehicle, GPS from the vehicle's second GPS, NAVERA's
output relayed through vehicle_link. Then vehicle_link on that link must relay a packet
sent to its local relay port: a REQUEST_MESSAGE(AUTOPILOT_VERSION) answered by the
autopilot proves it arrived. Exit code 0 = pass.
"""
import json
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
from std_msgs.msg import String

from navera_common.discovery import decide, discover

INSTANCE = 4
GCS = f"tcp:127.0.0.1:{5760 + 10 * INSTANCE}"
LINK = f"tcp:127.0.0.1:{5762 + 10 * INSTANCE}"


def main(ardupilot):
    work = tempfile.mkdtemp(prefix="navera_disc_")
    with open(os.path.join(work, "extra.parm"), "w") as f:
        f.write("SERIAL1_PROTOCOL 2\nGPS_TYPE2 1\nSIM_GPS2_DISABLE 0\nRNGFND1_TYPE 100\nRNGFND1_ORIENT 25\n"
                "RNGFND1_MAX_CM 4000\nFS_GCS_ENABLE 0\nLOG_BACKEND_TYPE 0\n")
    dp = os.path.join(ardupilot, "Tools/autotest/default_params/copter.parm")
    sitl = subprocess.Popen([os.path.join(ardupilot, "build/sitl/bin/arducopter"), "--model", "quad",
                             "--home", "35.8256,10.6385,10,0", "--defaults", f"{dp},{work}/extra.parm",
                             f"-I{INSTANCE}", "-w"], cwd=work, stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT, start_new_session=True)
    link = None
    failures = []
    try:
        gcs = mavutil.mavlink_connection(GCS, source_system=255)
        if gcs.wait_heartbeat(timeout=40) is None:
            print("FAIL no heartbeat from SITL")
            return 1
        gcs.mav.request_data_stream_send(gcs.target_system, gcs.target_component,
                                         mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)
        # the second GPS needs a fix before discovery can see it streaming
        end = time.time() + 90
        while time.time() < end:
            m = gcs.recv_match(type="GPS2_RAW", blocking=True, timeout=1)
            if m is not None and m.fix_type >= 3:
                break
        env = dict(os.environ, NAVERA_DISCOVER_MAVLINK=LINK, ROS_DOMAIN_ID="78")
        t0 = time.time()
        found = discover(env, ros_wait_s=1.0)
        d = decide(found, {"ROS_DOMAIN_ID": "78"})
        print(f"discovery ({time.time() - t0:.0f} s):\n  " + "\n  ".join(d["report"]))
        s = d["settings"]
        checks = [(s.get("NAVERA_SENSOR_SOURCE") == "vehicle", f"attitude source {s.get('NAVERA_SENSOR_SOURCE')}"),
                  (s.get("NAVERA_GPS_SOURCE") == "vehicle", f"GPS source {s.get('NAVERA_GPS_SOURCE')}"),
                  (s.get("NAVERA_VEHICLE_MAVLINK_URL") == LINK, f"vehicle link {s.get('NAVERA_VEHICLE_MAVLINK_URL')}"),
                  (s.get("NAVERA_MAVLINK_URL") == "udpout:127.0.0.1:14650", f"output {s.get('NAVERA_MAVLINK_URL')}")]
        failures += [why for ok, why in checks if not ok]
        # the second GPS switched to type 14 (MAVLink-fed: NAVERA's own GPS_INPUT would feed
        # it) must never be taken as the vehicle's GPS — a loop
        gcs.mav.param_set_send(gcs.target_system, gcs.target_component, b"GPS_TYPE2", 14,
                               mavutil.mavlink.MAV_PARAM_TYPE_INT8)
        time.sleep(2)
        from navera_common.discovery import autopilot_streams
        d14 = decide({"network": [x for x in found["network"] if x.get("url") == LINK],
                      "autopilot_streams": autopilot_streams(LINK)}, {"ROS_DOMAIN_ID": "78"})
        print("  with GPS_TYPE2=14: " + next(r for r in d14["report"] if r.startswith("GPS")))
        # never the second GPS NAVERA feeds; its first GPS (type 1, a real receiver) is now the
        # vehicle's GPS (wiring C, sitl_gps1_monitor.py)
        if d14["settings"].get("NAVERA_GPS_SOURCE") not in ("none", "vehicle_gps1"):
            failures.append(f"a MAVLink-fed second GPS was taken: {d14['settings'].get('NAVERA_GPS_SOURCE')}")
        # relay: through vehicle_link, which owns the link discovery chose
        os.environ["ROS_DOMAIN_ID"] = "78"
        link = subprocess.Popen(["ros2", "run", "navera_output", "vehicle_link_node.py", "--ros-args",
                                 "-p", f"mavlink_url:={s.get('NAVERA_VEHICLE_MAVLINK_URL', LINK)}",
                                 "-p", "relay_port:=14650"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True)
        rclpy.init()
        node = rclpy.create_node("discovery_test")
        st = {}
        node.create_subscription(String, "/navera/vehicle/status", lambda m: st.update(json.loads(m.data)), 10)
        ex = SingleThreadedExecutor()
        ex.add_node(node)
        threading.Thread(target=ex.spin, daemon=True).start()
        end = time.time() + 30
        while not st.get("link") and time.time() < end:
            time.sleep(0.5)
        nav = mavutil.mavlink_connection("udpout:127.0.0.1:14650", source_system=1, source_component=191)
        answered = False
        end = time.time() + 15
        while time.time() < end and not answered:
            nav.mav.command_long_send(1, 1, mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0, 148, 0, 0, 0, 0, 0, 0)
            time.sleep(1.2)
            answered = "AUTOPILOT_VERSION" in (st.get("rates_hz") or {})
        print(f"vehicle_link: link {st.get('link')}, relayed {st.get('relayed_packets')} packet(s), "
              f"autopilot answered: {answered}")
        if not st.get("link"):
            failures.append("vehicle_link did not connect to the discovered link")
        if not answered:
            failures.append("a packet sent to the relay port did not reach the autopilot")
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
    print("sitl_discovery:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/ardupilot")))
