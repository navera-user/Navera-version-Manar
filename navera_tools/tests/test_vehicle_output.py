#!/usr/bin/env python3
"""Integration test: sensor_sim GPS -> estimator -> vehicle_output -> "autopilot".

The test plays the autopilot: it reads the NMEA stream from a pseudo-terminal
and MAVLink GPS_INPUT from UDP. While GPS is simulated the output must be a fix
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

import pynmea2
from pymavlink import mavutil

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
    try:
        # 1) GPS simulated: expect fixes near the simulated circle (Sousse).
        deadline, fixes = time.time() + 30, []
        while time.time() < deadline and len(fixes) < 5:
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
    finally:
        for p in procs + [sim]:
            if p.poll() is None:
                stop(p)
        mav_in.close()

    for f in failures:
        print("FAIL", f)
    print("vehicle_output:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
