#!/usr/bin/env python3
"""Integration test: every way a client can plug a GPS, fed with simulated streams.

  1. u-blox UBX on a serial port (pseudo-terminal, as a passive tap on the TX wire of a GPS
     ArduPilot set to UBX at 230400): NAV-PVT -> a fix with the receiver's own accuracy
     (DIAGONAL_KNOWN), its velocity and UTC; the same receiver's NMEA is not published twice;
     dead reckoning only is invalid; a corrupted frame publishes nothing; a silent port is
     listened to at another baud (auto baud); NOTHING is written to the receiver.
  2. NMEA over TCP (gps_node url tcp:): fixes, then exit code 1 when the server goes away.
  3. UBX over UDP (gps.launch.py url:=udp:, as the boot service runs it): fixes.
  4. DroneCAN (dronecan_gps_node on a pydronecan virtual bus, mcast:): the Here3-like node's
     Fix2 is used, the autopilot node's re-broadcast (it commands ESCs) never; the node sends
     nothing on the bus unless node id allocation is turned on.

Needs a sourced ROS 2 workspace (gps_pkg built) and pydronecan for part 4. Exit code 0 = pass.
"""
import json
import os
import pty
import select
import signal
import socket
import struct
import subprocess
import sys
import termios
import threading
import time
import tty

import rclpy
from navera_msgs.msg import PositionEstimate
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import TimeReference
from geometry_msgs.msg import TwistStamped

from navera_common.gnss import NAV, NAV_PVT, ubx_frame

failures = []


def check(cond, what):
    if not cond:
        failures.append(what)
        print("FAIL", what)


def nav_pvt(fix_type=3, flags=0x01, h_acc_mm=1500, lat=35.7340010, lon=10.5758485):
    p = struct.pack("<IHBBBBBBIiBBBBiiiiIIiiiiiIIH", 123456000, 2026, 10, 22, 14, 16, 21, 0x07, 30, 250_000_000,
                    fix_type, flags, 0, 12, round(lon * 1e7), round(lat * 1e7), 127400, 95300, h_acc_mm, 2500,
                    1000, -2000, 300, 2236, 0, 500, 0, 120) + bytes(14)
    return ubx_frame(NAV, NAV_PVT, p)


def nmea(body):
    c = 0
    for ch in body.encode():
        c ^= ch
    return f"${body}*{c:02X}\r\n".encode()


GGA = nmea("GNGGA,141621.00,3544.04006,N,01034.55091,E,1,12,0.72,95.3,M,32.1,M,,")


class Listener:
    def __init__(self):
        self.node = Node("gps_sources_test")
        self.est, self.time, self.vel = [], [], []
        self.node.create_subscription(PositionEstimate, "/navera/estimate/gps", self.est.append, 50)
        self.node.create_subscription(TimeReference, "/navera/sensors/gnss_time", self.time.append, 50)
        self.node.create_subscription(TwistStamped, "/navera/sensors/gps_vel", self.vel.append, 50)
        self.ex = SingleThreadedExecutor()
        self.ex.add_node(self.node)
        self.th = threading.Thread(target=self.ex.spin, daemon=True)
        self.th.start()

    def wait_publisher(self, timeout=25.0):
        end = time.time() + timeout
        while self.node.count_publishers("/navera/estimate/gps") == 0 and time.time() < end:
            time.sleep(0.2)
        time.sleep(1.0)
        return self.node.count_publishers("/navera/estimate/gps") > 0

    def wait_gone(self, timeout=10.0):
        end = time.time() + timeout
        while self.node.count_publishers("/navera/estimate/gps") and time.time() < end:
            time.sleep(0.2)

    def close(self):
        self.ex.shutdown()
        self.th.join(timeout=5)
        self.node.destroy_node()


def run(*args):
    return subprocess.Popen(["ros2", "run", "gps_pkg", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)


def stop(proc):
    """Ctrl-C to the node's process group (as a launch would); never leave one behind."""
    if proc.poll() is not None:
        return
    os.killpg(proc.pid, signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        failures.append(f"{proc.args[3]} did not stop on SIGINT within 10 s")
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()


def part_ubx_serial(ls):
    master, slave = pty.openpty()
    tty.setraw(slave)
    name = os.ttyname(slave)
    os.close(slave)
    proc = run("gps_node.py", "--ros-args", "-p", f"serial_port:={name}", "-p", "baud_rate:=230400")
    written = []
    done = threading.Event()

    def watch():                                  # what gps_node sends to the "receiver"
        while not done.is_set():
            if select.select([master], [], [], 0.1)[0]:
                try:
                    written.append(os.read(master, 256))
                except OSError:
                    time.sleep(0.1)
    threading.Thread(target=watch, daemon=True).start()
    try:
        check(ls.wait_publisher(), "ubx serial: gps_node did not start")
        # nothing valid for 5 s: it listens at another baud (a local setting: nothing sent)
        time.sleep(6.0)
        speed = termios.tcgetattr(master)[5]
        check(speed != termios.B230400, "ubx serial: still at 230400 after 6 s of silence (auto baud)")
        n0 = len(ls.est)
        for _ in range(5):                        # a 5 Hz receiver, NMEA + UBX on one port
            os.write(master, nav_pvt() + GGA)
            time.sleep(0.2)
        time.sleep(1.0)
        new = ls.est[n0:]
        check(len(new) == 5, f"ubx serial: {len(new)} estimates for 5 NAV-PVT (+5 GGA not to be repeated)")
        check(all(m.model_id == "ubx_nav_pvt" and m.valid for m in new), "ubx serial: not all valid NAV-PVT fixes")
        if new:
            m = new[-1]
            check(m.position_covariance_type == PositionEstimate.COVARIANCE_TYPE_DIAGONAL_KNOWN
                  and abs(m.position_covariance[0] - 2.25) < 1e-9, "ubx serial: covariance is not hAcc^2")
            check(abs(m.altitude - 127.4) < 1e-6, f"ubx serial: altitude {m.altitude} (ellipsoid 127.4)")
            check(json.loads(m.details_json).get("num_sats") == 12, "ubx serial: satellites missing")
        check(len(ls.time) >= 5 and ls.time[-1].time_ref.sec == 1792678581, "ubx serial: no GNSS time")
        check(len(ls.vel) >= 5 and abs(ls.vel[-1].twist.linear.x + 2.0) < 1e-6, "ubx serial: no ENU velocity")
        n0 = len(ls.est)
        os.write(master, nav_pvt(fix_type=1, flags=0))           # dead reckoning only
        bad = bytearray(nav_pvt())
        bad[40] ^= 1
        os.write(master, bytes(bad))                              # corrupted: nothing
        time.sleep(1.0)
        new = ls.est[n0:]
        check(len(new) == 1 and not new[0].valid and "dead reckoning" in new[0].reason,
              f"ubx serial: DR-only / corrupted frame gave {[(m.valid, m.reason) for m in new]}")
        check(b"".join(written) == b"", f"ubx serial: gps_node wrote {b''.join(written)[:40]!r} to the receiver")
    finally:
        done.set()
        stop(proc)
        os.close(master)
        ls.wait_gone()


def part_tcp(ls):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    proc = run("gps_node.py", "--ros-args", "-p", f"url:=tcp:127.0.0.1:{port}")
    srv.settimeout(20)
    try:
        conn, _ = srv.accept()
    except socket.timeout:
        check(False, "tcp: gps_node never connected")
        stop(proc)
        return
    check(ls.wait_publisher(), "tcp: gps_node did not start")
    n0 = len(ls.est)
    for _ in range(3):
        conn.sendall(GGA)
        time.sleep(0.3)
    time.sleep(1.0)
    new = ls.est[n0:]
    check(len(new) == 3 and all(m.valid and m.model_id == "nmea_gga" for m in new),
          f"tcp: {len(new)} NMEA fixes, expected 3 valid")
    conn.close()
    srv.close()
    try:
        code = proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        stop(proc)
        code = None
    check(code == 1, f"tcp: exit code {code} when the server went away, expected 1")
    ls.wait_gone()


def part_udp(ls):
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    # through the launch file the boot service uses (navera_boot_gps.sh, NAVERA_GPS_SOURCE=network)
    proc = subprocess.Popen(["ros2", "launch", "gps_pkg", "gps.launch.py", f"url:=udp:127.0.0.1:{port}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        check(ls.wait_publisher(), "udp: gps_node did not start")
        tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        n0 = len(ls.est)
        for _ in range(3):
            tx.sendto(nav_pvt(), ("127.0.0.1", port))
            time.sleep(0.3)
        tx.close()
        time.sleep(1.0)
        new = ls.est[n0:]
        check(len(new) == 3 and all(m.valid for m in new), f"udp: {len(new)} UBX fixes, expected 3 valid")
    finally:
        stop(proc)
        ls.wait_gone()


def part_dronecan(ls):
    try:
        import dronecan
    except ImportError:
        check(False, "dronecan: pydronecan is not installed (pip install --user dronecan)")
        return
    bus = f"mcast:{20 + os.getpid() % 200}"           # a virtual bus of its own
    here3, fc, spy = (dronecan.make_node(bus, node_id=124), dronecan.make_node(bus, node_id=10),
                      dronecan.make_node(bus))
    heard = set()
    spy.add_transfer_hook(lambda t: heard.add(t.source_node_id))
    halt = threading.Event()

    def bus_traffic():
        good = dronecan.uavcan.equipment.gnss.Fix2(latitude_deg_1e8=3573400100, longitude_deg_1e8=1057584850,
                                                   height_ellipsoid_mm=127400, height_msl_mm=95300, status=3,
                                                   sats_used=14, covariance=[2.25, 2.25, 6.25, 0.04, 0.04, 0.04],
                                                   gnss_time_standard=2)
        good.gnss_timestamp.usec = 1792678581250000
        other = dronecan.uavcan.equipment.gnss.Fix2(latitude_deg_1e8=100000000, longitude_deg_1e8=100000000,
                                                    status=3, sats_used=20)
        while not halt.is_set():
            here3.broadcast(good)
            fc.broadcast(dronecan.uavcan.equipment.esc.RawCommand(cmd=[0, 0, 0, 0]))
            fc.broadcast(other)                                   # the autopilot's own GPS, re-broadcast
            for n in (here3, fc, spy):
                n.spin(0.1)
    th = threading.Thread(target=bus_traffic, daemon=True)
    th.start()
    try:
        for allocate in (False, True):
            proc = run("dronecan_gps_node.py", "--ros-args", "-p", f"can_interface:={bus}",
                       "-p", f"allocate_node_ids:={'true' if allocate else 'false'}")
            try:
                check(ls.wait_publisher(), "dronecan: the node did not start")
                heard.clear()
                n0 = len(ls.est)
                time.sleep(6.0)                          # it listens 2 s before choosing a node
                new = ls.est[n0:]
                nodes = {json.loads(m.details_json).get("node_id") for m in new}
                check(len(new) >= 3 and nodes == {124},
                      f"dronecan: fixes from nodes {nodes} ({len(new)}), expected 124")
                check(all(m.valid and m.position_covariance_type == PositionEstimate.COVARIANCE_TYPE_DIAGONAL_KNOWN
                          and abs(m.position_covariance[0] - 2.25) < 1e-3 for m in new), "dronecan: fix or accuracy")
                others = heard - {124, 10}
                if allocate:
                    check(125 in others, f"dronecan allocate: NAVERA's node 125 not heard ({others})")
                else:
                    check(not others, f"dronecan passive: something transmitted from nodes {others}")
            finally:
                stop(proc)
                ls.wait_gone()
    finally:
        halt.set()
        th.join(3)
        for n in (here3, fc, spy):
            n.close()
        import multiprocessing
        for p in multiprocessing.active_children():          # the virtual bus's I/O processes
            p.kill()


def main():
    rclpy.init()
    ls = Listener()
    try:
        for part in (part_ubx_serial, part_tcp, part_udp, part_dronecan):
            part(ls)
    finally:
        ls.close()
        rclpy.shutdown()
    print("gps_sources:", "PASS" if not failures else f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
