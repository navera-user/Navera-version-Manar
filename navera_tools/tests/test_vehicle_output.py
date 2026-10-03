#!/usr/bin/env python3
"""Integration test: sensor_sim GPS -> estimator -> vehicle_output -> "autopilot".

The test plays the autopilot: it reads the NMEA stream from a pseudo-terminal,
MAVLink GPS_INPUT from UDP and the ROS NavSatFix on /navera/fix. While GPS is simulated the output must be a fix
at the simulated position; once GPS stops, the output must become "no fix"
(never the last position repeated). Exit code 0 = pass.
"""
import math
import os
import pty
import signal
import subprocess
import sys
import time

import threading

import pynmea2
import rclpy
from pymavlink import mavutil
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import NavSatFix, NavSatStatus

UDP_PORT = 14577


def start(cmd, env=None):
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True, env=env)


def stop(p):
    try:
        os.killpg(p.pid, signal.SIGTERM)
        p.wait(timeout=10)
    except Exception:
        os.killpg(p.pid, signal.SIGKILL)


def drain(master, mav):
    """Discard what is already buffered (the pty and the UDP socket keep old
    messages): only output produced from now on is evaluated."""
    os.set_blocking(master, False)
    try:
        while os.read(master, 65536):
            pass
    except BlockingIOError:
        pass
    while mav.recv_match(blocking=False) is not None:
        pass


def read_gga(master, seconds):
    """Parsed GGA sentences received during `seconds`."""
    out, buf, end = [], b"", time.time() + seconds
    os.set_blocking(master, False)
    while time.time() < end:
        try:
            buf += os.read(master, 4096)
        except BlockingIOError:
            time.sleep(0.05)
            continue
        *lines, buf = buf.split(b"\n")
        for ln in lines:
            s = ln.decode("ascii", "replace").strip()
            if s.startswith("$GPGGA"):
                out.append(pynmea2.parse(s, check=True))
    return out


def main():
    failures = []
    master, slave = pty.openpty()
    env = dict(os.environ, NAVERA_ALLOW_SIM="1")
    mav_in = mavutil.mavlink_connection(f"udpin:127.0.0.1:{UDP_PORT}")
    procs = [start(["ros2", "run", "navera_estimator", "estimator_node.py"]),
             start(["ros2", "run", "navera_output", "vehicle_output_node.py", "--ros-args",
                    "-p", f"nmea_port:={os.ttyname(slave)}",
                    "-p", f"mavlink_url:=udpout:127.0.0.1:{UDP_PORT}"])]
    sim = start([sys.executable, "navera_tools/sensor_sim.py"], env=env)
    rclpy.init()
    node = Node("vehicle_output_test")
    ros_fix = []
    node.create_subscription(NavSatFix, "/navera/fix", ros_fix.append, 50)
    ex = SingleThreadedExecutor()
    ex.add_node(node)
    spinner = threading.Thread(target=ex.spin, daemon=True)
    spinner.start()
    try:
        # 1) GPS simulated: expect fixes near the simulated circle (Sousse).
        # (and a ROS fix: on an idle machine 5 NMEA fixes come before ROS has matched
        # this test's /navera/fix subscription — the phase must not end before it)
        deadline, fixes = time.time() + 30, []
        while time.time() < deadline and (len(fixes) < 5 or not any(
                f.status.status == NavSatStatus.STATUS_FIX for f in ros_fix)):
            fixes += [g for g in read_gga(master, 1.0) if g.gps_qual == 1]
        if len(fixes) < 5:
            failures.append(f"only {len(fixes)} NMEA fixes while GPS was simulated")
        elif not all(abs(g.latitude - 35.8288) < 0.02 and abs(g.longitude - 10.636) < 0.02
                     for g in fixes):
            failures.append("NMEA fix not at the simulated position")
        drain(master, mav_in)
        m = mav_in.recv_match(type="GPS_INPUT", blocking=True, timeout=5)
        if m is None or m.fix_type not in (2, 3) or abs(m.lat / 1e7 - 35.8288) > 0.02:
            failures.append(f"MAVLink GPS_INPUT fix wrong: {m}")
        good = [f for f in ros_fix if f.status.status == NavSatStatus.STATUS_FIX]
        if not good:
            failures.append("no ROS fix on /navera/fix while GPS was simulated")
        elif abs(good[-1].latitude - 35.8288) > 0.02 or \
                good[-1].position_covariance_type == NavSatFix.COVARIANCE_TYPE_UNKNOWN:
            failures.append(f"ROS fix wrong: {good[-1].latitude} cov type {good[-1].position_covariance_type}")

        # 2) GPS stops: within a few seconds the output must be "no fix".
        stop(sim)
        time.sleep(5.0)
        drain(master, mav_in)
        after = read_gga(master, 2.0)
        if not after or any(g.gps_qual != 0 or g.lat for g in after):
            failures.append(f"after GPS loss: {[(g.gps_qual, g.lat) for g in after][:3]}")
        drain(master, mav_in)
        m = mav_in.recv_match(type="GPS_INPUT", blocking=True, timeout=3)
        if m is None or m.fix_type != 1 or m.lat != 0:
            failures.append(f"after GPS loss MAVLink still reports a position: {m}")
        last = ros_fix[-1] if ros_fix else None
        if last is None or last.status.status != NavSatStatus.STATUS_NO_FIX or not math.isnan(last.latitude):
            failures.append("after GPS loss the ROS output still reports a position")
    finally:
        for p in procs + [sim]:
            if p.poll() is None:
                stop(p)
        mav_in.close()
        ex.shutdown()
        spinner.join(timeout=5)
        node.destroy_node()
        rclpy.shutdown()

    for f in failures:
        print("FAIL", f)
    print("vehicle_output:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
