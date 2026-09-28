#!/usr/bin/env python3
"""Validation against ArduPilot SITL: does a real autopilot accept NAVERA's output?

Not part of run_tests.sh (needs an ArduPilot build). Usage, from the workspace root:

    NAVERA_ALLOW_SIM=1 python3 navera_tools/tests/sitl_ardupilot.py [~/ardupilot] [mavlink|nmea|all]

For each mode, ArduCopter SITL runs with its GPS configured as that input
(MAVLink GPS_INPUT: GPS_TYPE 14; NMEA: GPS_TYPE 5 on SERIAL3). The chain is:

    sensor_sim (GPS) -> navera_estimator -> vehicle_output -> ArduCopter SITL

The autopilot's own GPS_RAW_INT is read back. While GPS is simulated it must
report a fix at the simulated position; after the GPS stops it must lose the
fix within a few seconds. Exit code 0 = pass.
"""
import math
import os
import pty
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

from pymavlink import mavutil

SIM_LAT, SIM_LON = 35.8288, 10.6360          # sensor_sim circle centre (r = 800 m)


def start(cmd, env=None, cwd=None, log=None):
    return subprocess.Popen(cmd, stdout=log or subprocess.DEVNULL, stderr=subprocess.STDOUT,
                            start_new_session=True, env=env, cwd=cwd)


def stop(p):
    if p is None or p.poll() is not None:
        return
    try:
        os.killpg(p.pid, signal.SIGTERM)
        p.wait(timeout=10)
    except Exception:
        os.killpg(p.pid, signal.SIGKILL)


def linked_ptys():
    """Two pseudo-terminal paths joined by a byte bridge (a null-modem cable)."""
    m1, s1 = pty.openpty()
    m2, s2 = pty.openpty()
    for fd in (s1, s2):                       # raw mode: no echo, no line editing
        import tty
        tty.setraw(fd)

    def pump(a, b):
        while True:
            try:
                data = os.read(a, 4096)
                if not data:
                    return
                os.write(b, data)
            except OSError:
                return
    for a, b in ((m1, m2), (m2, m1)):
        threading.Thread(target=pump, args=(a, b), daemon=True).start()
    return os.ttyname(s1), os.ttyname(s2)


def gps_state(mav, seconds):
    """Last GPS_RAW_INT seen within `seconds` (fix_type, lat, lon) or None."""
    last, end = None, time.time() + seconds
    while time.time() < end:
        m = mav.recv_match(type="GPS_RAW_INT", blocking=True, timeout=1)
        if m is not None:
            last = (m.fix_type, m.lat / 1e7, m.lon / 1e7, m.satellites_visible)
    return last


def run(mode, ardupilot, log_dir):
    failures = []
    params = os.path.join(log_dir, f"navera_{mode}.parm")
    with open(params, "w") as f:
        if mode == "mavlink":
            f.write("GPS_TYPE 14\n")
        else:
            f.write("GPS_TYPE 5\nSERIAL3_PROTOCOL 5\nSERIAL3_BAUD 9\n")    # 9 = 9600
        f.write("SIM_GPS_DISABLE 1\nGPS_AUTO_CONFIG 0\n")
    defaults = os.path.join(ardupilot, "Tools/autotest/default_params/copter.parm")
    cmd = [os.path.join(ardupilot, "build/sitl/bin/arducopter"), "--model", "quad",
           "--home", f"{SIM_LAT},{SIM_LON},10,0", "--defaults", f"{defaults},{params}", "-I0"]
    out_params = ["-p", "rate_hz:=5.0"]
    if mode == "nmea":
        a, b = linked_ptys()
        cmd += [f"--serial3=uart:{a}:9600"]
        out_params += ["-p", f"nmea_port:={b}", "-p", "nmea_baud:=9600"]
    else:
        out_params += ["-p", "mavlink_url:=tcp:127.0.0.1:5762"]

    sitl = start(cmd, cwd=log_dir, log=open(os.path.join(log_dir, f"sitl_{mode}.log"), "w"))
    time.sleep(8)
    mav = mavutil.mavlink_connection("tcp:127.0.0.1:5760", source_system=250)
    mav.wait_heartbeat(timeout=30)
    mav.mav.request_data_stream_send(mav.target_system, mav.target_component,
                                     mavutil.mavlink.MAV_DATA_STREAM_ALL, 5, 1)
    env = dict(os.environ, NAVERA_ALLOW_SIM="1")
    est = start(["ros2", "run", "navera_estimator", "estimator_node.py"])
    out = start(["ros2", "run", "navera_output", "vehicle_output_node.py", "--ros-args"] + out_params,
                log=open(os.path.join(log_dir, f"output_{mode}.log"), "w"))
    sim = start([sys.executable, "navera_tools/sensor_sim.py"], env=env)
    try:
        # With NAVERA feeding it, the autopilot must report a 3D fix near the sim position.
        st, end = None, time.time() + 45
        while time.time() < end:
            st = gps_state(mav, 3)
            if st and st[0] >= 3 and math.hypot(st[1] - SIM_LAT, st[2] - SIM_LON) < 0.02:
                break
        print(f"  [{mode}] autopilot GPS while NAVERA has GPS: {st}")
        if not (st and st[0] >= 3 and math.hypot(st[1] - SIM_LAT, st[2] - SIM_LON) < 0.02):
            failures.append(f"{mode}: autopilot did not get a 3D fix at the NAVERA position: {st}")

        stop(sim)                                   # GPS lost at NAVERA
        st, end = None, time.time() + 20
        while time.time() < end:
            st = gps_state(mav, 2)
            if st and st[0] <= 1:
                break
        print(f"  [{mode}] autopilot GPS after NAVERA lost GPS: {st}")
        if not (st and st[0] <= 1):
            failures.append(f"{mode}: autopilot kept a fix after NAVERA reported no fix: {st}")
    finally:
        for p in (sim, out, est, sitl):
            stop(p)
        mav.close()
    return failures


def main():
    ardupilot = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/ardupilot")
    modes = ["mavlink", "nmea"] if (len(sys.argv) < 3 or sys.argv[2] == "all") else [sys.argv[2]]
    log_dir = tempfile.mkdtemp(prefix="navera_sitl_")
    failures = []
    for mode in modes:
        failures += run(mode, ardupilot, log_dir)
    for f in failures:
        print("FAIL", f)
    print("sitl_ardupilot:", "PASS" if not failures else f"{len(failures)} failure(s)",
          f"(logs: {log_dir})")
    if not failures:
        shutil.rmtree(log_dir, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
