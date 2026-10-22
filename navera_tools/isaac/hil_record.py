#!/usr/bin/env python3
"""Hardware in the loop, box side: record what the REAL NAVERA box does in a simulated flight.

    python3 navera_tools/isaac/hil_record.py --ros-args -p results:=DIR -p pc_offset_s:=0.004 \
        -p truth_port:=15531 -p lat0:=35.8685 -p lon0:=35.8685 -p z_ref:=39.0 -p pc_host:=192.168.1.192

Runs on the box (hil_flight.sh starts it) on the staged stack's ROS domain. It joins NAVERA's
answers to the simulator's truth (sitl_demo.py streams SIM_STATE to this box over UDP) and
writes the same files as the Isaac container record (isaac_link.py), so summarise.py reads them:

  position.csv  every /navera/position vs the truth at its sensor stamp
  day.csv       every /navera/estimate/day (+ the error at the TRUE exposure, joined later by
                hil_summarise.py from the PC's stream.csv)
  proc.csv      frame_meta -> frame_done (live camera hands over -> day pipeline acks), ms
  events.jsonl  day_status;  ekf.csv  the autopilot's EKF vs the truth;  gps_cut  the cut time

and what only the box can tell (hil_*.csv):
  hil_meta.csv    per frame: grab stamp, frame_meta receipt (live camera time), usable
  hil_pos.csv     per /navera/position: receipt, header stamp, sensor stamp (all box clock)
  hil_out.csv     per /navera/fix (what the output gave the autopilot, the same decision as its
                  GPS_INPUT): receipt, fix (1) / no fix (0), stated sigma — the gaps the autopilot saw
  hil_rx.csv      per second and topic: messages, largest gap (vehicle IMU over MAVLink, GPS over
                  the network, the truth stream, position)
  hil_truth_rx.csv  per truth packet: PC send time - box receipt (network delay + clock offset)
  hil_sys.csv     tegrastats each second: RAM, swap, CPU per core, GPU, temperatures, power
  hil_units.csv   every 2 s per staged unit: memory, CPU time, restarts, main PID, state
  hil_ping.csv    round trip to the PC each second (TCP connect to rtt_port: no ICMP through its firewall)
  truth.csv       the truth as received (t, lat, lon, alt, height above home)

Times: the box's clock; truth times are the PC's (t = PC wall - t0). pc_offset_s = PC clock -
box clock (measured by hil_flight.sh before the flight) converts. SIMULATION truth, real box.
"""
import json
import math
import os
import re
import socket
import subprocess
import sys
import threading
import time

import rclpy
from navera_msgs.msg import NavStatus, PositionEstimate
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu, NavSatFix
from std_msgs.msg import Int32, String

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from flight_profile import GeoRef, LiveFeed  # noqa: E402

SRC = {0: "unknown", 1: "gps", 2: "day", 3: "night", 4: "celestial", 5: "inertial", 6: "fused"}
MODE = {0: "measured", 1: "propagated", 2: "held", 3: "replayed"}
STATE = {0: "initializing", 1: "no_fix", 2: "fix", 3: "degraded"}


def stamp_s(st) -> float:
    return st.sec + st.nanosec * 1e-9


def parse_tegrastats(line: str) -> dict:
    """One tegrastats line -> numbers (RAM / swap MB, CPU % per core, GPU %, temperatures C, mW)."""
    d = {}
    m = re.search(r"RAM (\d+)/(\d+)MB", line)
    if m:
        d["ram_mb"], d["ram_total_mb"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"SWAP (\d+)/(\d+)MB", line)
    if m:
        d["swap_mb"] = int(m.group(1))
    m = re.search(r"CPU \[([^\]]*)\]", line)
    if m:
        cores = [int(c.split("%")[0]) for c in m.group(1).split(",") if "%" in c]
        if cores:
            d["cpu_avg"], d["cpu_max"] = round(sum(cores) / len(cores), 1), max(cores)
    m = re.search(r"GR3D_FREQ (\d+)%", line)
    if m:
        d["gpu"] = int(m.group(1))
    for name in ("cpu", "gpu", "tj", "soc0", "soc1", "soc2"):
        m = re.search(rf"\b{name}@(-?[\d.]+)C", line)
        if m:
            d[f"t_{name}"] = float(m.group(1))
    m = re.search(r"VDD_IN (\d+)mW", line)
    if m:
        d["vdd_in_mw"] = int(m.group(1))
    return d


class Rx:
    """Per-second message count and largest inter-arrival gap of one topic."""

    def __init__(self):
        self.last, self.n, self.gap = None, 0, 0.0

    def hit(self, now: float):
        if self.last is not None:
            self.gap = max(self.gap, now - self.last)
        self.last, self.n = now, self.n + 1

    def take(self):
        r = (self.n, self.gap)
        self.n, self.gap = 0, 0.0
        return r


class HilRecord(Node):
    def __init__(self):
        super().__init__("hil_record")
        dyn = ParameterDescriptor(dynamic_typing=True)
        p = lambda n, d: self.declare_parameter(n, d, dyn).value       # noqa: E731
        self.results = os.path.expanduser(str(p("results", "/tmp/hil")))
        self.offset = float(p("pc_offset_s", 0.0))
        self.pc_host = str(p("pc_host", ""))
        self.rtt_port = int(p("rtt_port", 10117))
        self.unit_prefix = str(p("unit_prefix", "navera-stage-"))
        self.geo = GeoRef(float(p("lat0", 35.8685)), float(p("lon0", 10.5352)))
        os.makedirs(self.results, exist_ok=True)
        self.feed = LiveFeed(int(p("truth_port", 15531)), self.geo, float(p("z_ref", 0.0)), host="0.0.0.0")
        self.t0 = None
        self.gps_cut = None
        self.gps_state = "on"
        self._last_ekf = None
        self.lock = threading.Lock()
        f = lambda n, hdr: self._csv(n, hdr)                                   # noqa: E731
        self.pos_f = f("position.csv", "t,lat,lon,source,mode,valid,sigma_m,truth_lat,truth_lon,err_m,gps")
        self.day_f = f("day.csv", "t,frame,lat,lon,mode,valid,sigma_m,err_m,err_frame_m,t_exposure,proc_ms,reason")
        self.proc_f = f("proc.csv", "t,frame,proc_ms")
        self.ekf_f = f("ekf.csv", "t,ekf_lat,ekf_lon,truth_lat,truth_lon,err_m,gps")
        self.meta_f = f("hil_meta.csv", "frame,grab_box,meta_rx_box,usable,reason")
        self.hpos_f = f("hil_pos.csv", "rx_box,header_box,sensor_box,source,mode,valid,frame")
        self.hday_f = f("hil_day.csv", "rx_box,sensor_box,frame,valid,mode")
        self.rx_f = f("hil_rx.csv", "box,topic,n,max_gap_ms")
        self.trx_f = f("hil_truth_rx.csv", "rx_box,sent_pc,delta_ms")
        self.truth_f = f("truth.csv", "t,lat,lon,alt,rel")
        self.sys_f = f("hil_sys.csv", "box,ram_mb,swap_mb,cpu_avg,cpu_max,gpu,t_cpu,t_gpu,t_tj,vdd_in_mw")
        self.units_f = f("hil_units.csv", "box,unit,state,mem_mb,cpu_s,restarts,pid")
        self.ping_f = f("hil_ping.csv", "box,rtt_ms")
        self.out_f = f("hil_out.csv", "rx_box,fix,sigma_m")
        self.events = open(os.path.join(self.results, "events.jsonl"), "a")
        self.meta_t = {}       # frame -> box receipt of frame_meta
        self.proc_ms = {}
        self.rx = {k: Rx() for k in ("vehicle_imu", "gps_est", "truth", "position", "day")}
        self.live = {}
        self.create_subscription(PositionEstimate, "/navera/position", self._on_pos, 50)
        self.create_subscription(PositionEstimate, "/navera/estimate/day", self._on_day, 10)
        self.create_subscription(NavSatFix, "/navera/fix", self._on_fix, 50)
        self.create_subscription(PositionEstimate, "/navera/estimate/gps", self._on_gps, 10)
        self.create_subscription(NavStatus, "/navera/nav_status", self._on_nav, 10)
        self.create_subscription(String, "/day/day_status", self._on_status, 10)
        self.create_subscription(String, "/day/frame_meta", self._on_meta, 10)
        self.create_subscription(Int32, "/day/frame_done", self._on_done, 10)
        self.create_subscription(Imu, "/navera/vehicle/imu", lambda m: self.rx["vehicle_imu"].hit(time.time()),
                                 qos_profile_sensor_data)
        for target in (self._truth_loop, self._rx_loop, self._tegra_loop, self._units_loop, self._ping_loop):
            threading.Thread(target=target, daemon=True).start()
        self.get_logger().info(f"HIL record -> {self.results}, PC offset {self.offset * 1000:.1f} ms")

    def _on_fix(self, m):
        ok = m.status.status >= 0 and math.isfinite(m.latitude)
        sig = math.sqrt(m.position_covariance[0]) if ok and m.position_covariance[0] > 0 else float("nan")
        self._w(self.out_f, f"{time.time():.4f},{int(ok)},{sig:.1f}")

    def _csv(self, name, header):
        fh = open(os.path.join(self.results, name), "a")
        if fh.tell() == 0:
            fh.write(header + "\n")
            fh.flush()
        return fh

    @staticmethod
    def _w(fh, line):
        fh.write(line + "\n")
        fh.flush()

    # ── truth ────────────────────────────────────────────────────────────
    def t_of(self, box_s: float) -> float:
        """Box time -> the flight's t (PC clock, s since sitl_demo's t0)."""
        return box_s + self.offset - (self.t0 or 0.0)

    def _truth_loop(self):
        while rclpy.ok():
            with self.lock:
                n = self.feed.poll()
            d = self.feed.last
            if n and d:
                now = time.time()
                self.rx["truth"].hit(now)
                if self.t0 is None and d.get("t0"):
                    self.t0 = float(d["t0"])
                    with open(os.path.join(self.results, "hil_t0.json"), "w") as fh:
                        json.dump(dict(t0_pc=self.t0, pc_offset_s=self.offset), fh)
                if d.get("t") is not None and d.get("lat") is not None:
                    self._w(self.truth_f, f"{d['t']:.4f},{d['lat']:.8f},{d['lon']:.8f},{d['alt']:.2f},"
                                          f"{d.get('rel', 0.0):.2f}")
                if d.get("t") is not None and self.t0:
                    self._w(self.trx_f, f"{now:.4f},{self.t0 + d['t']:.4f},{1000 * (now + self.offset - self.t0 - d['t']):.1f}")
                if not d.get("gps", True) and self.gps_cut is None:
                    self.gps_cut = float(d["t"])
                    self.gps_state = "cut"
                    with open(os.path.join(self.results, "gps_cut"), "w") as fh:
                        fh.write(f"{self.gps_cut:.2f}")
                    self.get_logger().info(f"GPS CUT at t={self.gps_cut:.1f} s")
                ekf = d.get("ekf")
                if ekf and ekf != self._last_ekf and self.feed.ready():
                    self._last_ekf = ekf
                    err, tl, tn = self._err(ekf[0], ekf[1], d["t"])
                    self._w(self.ekf_f, f"{d['t']:.3f},{ekf[0]:.7f},{ekf[1]:.7f},{tl:.7f},{tn:.7f},{err:.2f},"
                                        f"{'on' if d.get('gps', True) else 'cut'}")
                if d.get("done") and not os.path.exists(os.path.join(self.results, "flight_done")):
                    with open(os.path.join(self.results, "flight_done"), "w") as fh:
                        fh.write(f"{d.get('t', 0)}")
            time.sleep(0.01)

    def _err(self, lat, lon, t):
        with self.lock:
            if not self.feed.ready():
                return float("nan"), 0.0, 0.0
            st = self.feed.state(max(t, 0.0))
        tl, tn = self.geo.to_latlon(st.e, st.n)
        e1, n1 = self.geo.to_en(lat, lon)
        return math.hypot(e1 - st.e, n1 - st.n), tl, tn

    @staticmethod
    def _sigma(m):
        return math.sqrt(m.position_covariance[0]) if m.position_covariance[0] > 0 else float("nan")

    # ── NAVERA ───────────────────────────────────────────────────────────
    def _on_pos(self, m):
        now = time.time()
        self.rx["position"].hit(now)
        ts = m.sensor_stamp if m.sensor_stamp.sec else m.header.stamp
        t = self.t_of(stamp_s(ts))
        err, tl, tn = self._err(m.latitude, m.longitude, t) if m.valid else (float("nan"), 0, 0)
        self._w(self.pos_f, f"{t:.3f},{m.latitude:.7f},{m.longitude:.7f},{SRC.get(m.source, m.source)},"
                            f"{MODE.get(m.mode, m.mode)},{int(m.valid)},{self._sigma(m):.1f},{tl:.7f},{tn:.7f},"
                            f"{err:.2f},{self.gps_state}")
        self._w(self.hpos_f, f"{now:.4f},{stamp_s(m.header.stamp):.4f},{stamp_s(ts):.4f},{SRC.get(m.source, m.source)},"
                             f"{MODE.get(m.mode, m.mode)},{int(m.valid)},{m.frame_index}")

    def _on_gps(self, m):
        self.rx["gps_est"].hit(time.time())

    def _on_day(self, m):
        now = time.time()
        self.rx["day"].hit(now)
        t = self.t_of(stamp_s(m.sensor_stamp))
        err = self._err(m.latitude, m.longitude, t)[0] if m.valid else float("nan")
        # err_frame_m / t_exposure: joined by hil_summarise.py (the PC's stream.csv)
        self._w(self.day_f, f"{t:.3f},{m.frame_index},{m.latitude:.7f},{m.longitude:.7f},{MODE.get(m.mode, m.mode)},"
                            f"{int(m.valid)},{self._sigma(m):.1f},{err:.2f},nan,nan,"
                            f"{self.proc_ms.get(m.frame_index, float('nan')):.0f},\"{m.reason[:80]}\"")
        self._w(self.hday_f, f"{now:.4f},{stamp_s(m.sensor_stamp):.4f},{m.frame_index},{int(m.valid)},"
                             f"{MODE.get(m.mode, m.mode)}")

    def _on_nav(self, m):
        self.live["state"] = STATE.get(m.state, "?")

    def _on_status(self, m):
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        t = self.t_of(time.time())
        self.events.write(json.dumps(dict(t=round(t, 3), day_status=d)) + "\n")
        self.events.flush()

    def _on_meta(self, m):
        now = time.time()
        try:
            d = json.loads(m.data)
        except ValueError:
            return
        fid = int(d.get("frame_id", -1))
        self.meta_t[fid] = now
        grab = int(d.get("image_stamp_ns", 0)) * 1e-9 + float(d.get("capture_latency_s", 0.0) or 0.0)
        self._w(self.meta_f, f"{fid},{grab:.4f},{now:.4f},{int(bool(d.get('usable', True)))},"
                             f"\"{str(d.get('reason', ''))[:60]}\"")

    def _on_done(self, m):
        mt = self.meta_t.get(m.data)
        if mt:
            self.proc_ms[m.data] = 1000.0 * (time.time() - mt)
            self._w(self.proc_f, f"{self.t_of(time.time()):.3f},{m.data},{self.proc_ms[m.data]:.0f}")

    # ── the box ──────────────────────────────────────────────────────────
    def _rx_loop(self):
        while rclpy.ok():
            time.sleep(1.0)
            now = time.time()
            for k, r in self.rx.items():
                n, gap = r.take()
                self._w(self.rx_f, f"{now:.1f},{k},{n},{1000 * gap:.0f}")

    def _tegra_loop(self):
        try:
            proc = subprocess.Popen(["tegrastats", "--interval", "1000"], stdout=subprocess.PIPE, text=True)
        except OSError as e:
            self.get_logger().warn(f"tegrastats unavailable: {e}")
            return
        for line in proc.stdout:
            d = parse_tegrastats(line)
            self._w(self.sys_f, f"{time.time():.1f}," + ",".join(
                str(d.get(k, "")) for k in ("ram_mb", "swap_mb", "cpu_avg", "cpu_max", "gpu", "t_cpu", "t_gpu",
                                            "t_tj", "vdd_in_mw")))

    def _units_loop(self):
        while rclpy.ok():
            out = subprocess.run(["systemctl", "--user", "list-units", "--no-legend", "--plain",
                                  f"{self.unit_prefix}*"], capture_output=True, text=True).stdout
            units = [ln.split()[0] for ln in out.splitlines() if ln.strip()]
            now = time.time()
            for u in units:
                r = subprocess.run(["systemctl", "--user", "show", u, "-p", "ActiveState", "-p", "MemoryCurrent",
                                    "-p", "CPUUsageNSec", "-p", "NRestarts", "-p", "MainPID"],
                                   capture_output=True, text=True).stdout
                kv = dict(ln.split("=", 1) for ln in r.splitlines() if "=" in ln)
                mem, cpu = kv.get("MemoryCurrent", ""), kv.get("CPUUsageNSec", "")
                mem_mb = f"{int(mem) / 1e6:.0f}" if mem.isdigit() else ""
                cpu_s = f"{int(cpu) / 1e9:.1f}" if cpu.isdigit() else ""
                self._w(self.units_f, f"{now:.1f},{u},{kv.get('ActiveState', '')},{mem_mb},{cpu_s},"
                                      f"{kv.get('NRestarts', '')},{kv.get('MainPID', '')}")
            time.sleep(2.0)

    def _ping_loop(self):
        """Round trip to the PC each second: a TCP connect to its NMEA port (the PC's firewall
        drops ICMP echo), i.e. SYN -> SYN-ACK through the same network path as the sensors."""
        if not self.pc_host:
            return
        while rclpy.ok():
            t = time.time()
            try:
                with socket.create_connection((self.pc_host, self.rtt_port), timeout=2.0):
                    rtt = time.time() - t
                self._w(self.ping_f, f"{t:.1f},{1000 * rtt:.2f}")
            except OSError:
                self._w(self.ping_f, f"{t:.1f},nan")
            time.sleep(max(0.0, 1.0 - (time.time() - t)))


def main():
    rclpy.init()
    node = HilRecord()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, rclpy.executors.ExternalShutdownException):
        pass


if __name__ == "__main__":
    main()
