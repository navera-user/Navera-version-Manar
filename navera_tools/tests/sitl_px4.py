#!/usr/bin/env python3
"""PX4 SITL: an AUTO mission flown GPS-denied on NAVERA's positions, sent as MAVLink HIL_GPS.

Not part of run_tests.sh (needs a PX4 SITL build; ~6 min of real time per scenario). Usage, from
the workspace root, after colcon build (the NAVERA nodes run from install/):

    nice -n 19 python3 navera_tools/tests/sitl_px4.py --px4 ~/px4_sitl/PX4-Autopilot
        [--scenarios nominal,navera_stop,output_restart,no_hil_param,px4_defaults] [--sigma 30]
        [--instance 3]
        [--out DIR] [--set K=V,...]

PX4 v1.15 SIH quadrotor (build/px4_sitl_default, headless, real time) with NO simulated GPS
(SENS_EN_GPSSIM 0) and NAVERA's recommended parameters (docs/PX4_INTEGRATION.md §2: MAV_USEHILGPS
1, EKF2_GPS_CTRL 1, EKF2_HGT_REF 0, EKF2_GPS_CHECK 240, EKF2_NOAID_NOISE, COM_POS_FS_EPH), set at
boot through a px4-rc.params hook. Its ONLY horizontal position is NAVERA's output. The chain is
the product's own, as navera-discover sets it up for PX4:

    NAVERA emulation (this script: /navera/position, /navera/nav_status, /navera/sensors/gps_vel)
      -> vehicle_output_node (real node: policy, bridge, reacquire, mavlink_message auto)
      -> udpout:127.0.0.1:<relay> -> vehicle_link_node (real node: owns the PX4 link, relays)
      -> PX4 (onboard MAVLink port) -> EKF2

The NAVERA emulation: GPS = the simulator's truth (HIL_STATE_QUATERNION of the SIH display link)
+ 0.7 m noise at 5 Hz, stated 1.5 m, 12 satellites, with the receiver velocity; day vision after
the GPS loss = one photo a second, describing the truth at its exposure, published --latency later
(uniform), its error REPLAYED in order from the real UAV-VisLoc results (sitl_closed_loop.py: pool
"good", median ~16 m), stated max(--sigma, the matcher's sigma), from 5 m above the take-off
point (during the GPS phase too: the arbiter prefers GPS); state FIX on GPS, DEGRADED on vision,
NO_FIX when nothing is current (3 s).

Mission (relative to home): takeoff 80 m, 4 legs (300 / 400 / 400 / 400 m), RTL + land, cruise
8 m/s. GPS is lost when waypoint 1 is reached and never returns. Scenarios:

  nominal         vision as replayed to the landing
  navera_stop     NAVERA stops publishing 90 s after the loss (the arbiter silent: "no fix"):
                  PX4's own failsafe must act
  output_restart  vehicle_output_node killed (SIGKILL) 60 s after the loss, restarted 10 s later
                  (navera-output.service RestartSec): how PX4 lives through the gap, and recovers
  px4_defaults    nominal with PX4's defaults for COM_POS_FS_EPH (5), EKF2_NOAID_NOISE (10) and
                  EKF2_GPS_V_GATE (5): what the recommended values change
  no_hil_param    MAV_USEHILGPS 0 (the integrator forgot it): PX4 must refuse to arm (no position)

Measured: EKF position error vs truth (GLOBAL_POSITION_INT vs HIL_STATE_QUATERNION), its stated
eph (ESTIMATOR_STATUS pos_horiz_accuracy), mode changes, failsafe / EKF messages (STATUSTEXT),
waypoints reached, landing point vs home. Results: <out>/<scenario>.json + a table on stdout.
SIMULATION only.
"""
import argparse
import glob
import json
import math
import os
import random
import signal
import subprocess
import sys
import tempfile
import threading
import time

from pymavlink import mavutil

WS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

GPS_SIGMA_M, GPS_NOISE_M = 1.5, 0.7
RESTART_S = 10.0                 # navera-output.service RestartSec
ALT_M, SPEED = 80.0, 8.0
LEGS = ((300.0, 0.0), (300.0, 400.0), (-100.0, 400.0), (-100.0, 0.0))    # north, east from home (m)

PX4_PARAMS = {
    "SENS_EN_GPSSIM": 0,          # no simulated receiver: NAVERA is the only GPS
    "MAV_USEHILGPS": 1,           # PX4 reads HIL_GPS (from its own system id) as a GPS
    "EKF2_GPS_CTRL": 1,           # lon/lat only: HIL_GPS's velocity is always "valid", no height
    "EKF2_HGT_REF": 0,            # barometer
    "EKF2_GPS_CHECK": 240,        # 245 without NSATS (bit 0) and EPH (bit 2): vision has neither
    "EKF2_NOAID_NOISE": 50.0,     # else a stated 30 m is fused as 10 m (gps_control.cpp)
    "EKF2_GPS_V_GATE": 100.0,     # the unfused HIL_GPS velocity (vd 0 in a climb) must not trip the
                                  # commander's post-takeoff navigation test (estimatorCheck.cpp)
    "COM_POS_FS_EPH": 25.0,       # position invalid above 2.5 x this = 62 m (default 5 -> 12.5 m)
    "COM_VEL_FS_EVH": 3.0,        # velocity invalid above 7.5 m/s (default 1 -> 2.5 m/s)
    "MPC_XY_CRUISE": SPEED,
    "NAV_ACC_RAD": 25.0,          # waypoint acceptance > the vision position noise (default 10 m)
    "MIS_DIST_1WP": 0.0,
    "NAV_DLL_ACT": 0, "COM_DL_LOSS_T": 60, "NAV_RCL_ACT": 0, "COM_RCL_EXCEPT": 4, "COM_RC_IN_MODE": 4,
    "COM_ARM_WO_GPS": 1,
}


def ne(lat, lon, lat0, lon0):
    """(north, east) m of (lat, lon) from (lat0, lon0), flat earth."""
    return (math.radians(lat - lat0) * 6371000.0,
            math.radians(lon - lon0) * 6371000.0 * math.cos(math.radians(lat0)))


def offset(lat, lon, n, e):
    return (lat + math.degrees(n / 6371000.0),
            lon + math.degrees(e / (6371000.0 * math.cos(math.radians(lat)))))


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else None


class Truth:
    """The simulator's truth (HIL_STATE_QUATERNION on the SIH display link, sent to 19410 + instance),
    latest + history."""

    def __init__(self, port):
        self.m = mavutil.mavlink_connection(f"udpin:127.0.0.1:{port}", source_system=250)
        self.last = None
        self.hist = []
        self.stop = False
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self.stop:
            msg = self.m.recv_match(type="HIL_STATE_QUATERNION", blocking=True, timeout=0.5)
            if msg is None:
                continue
            s = (time.time(), msg.lat * 1e-7, msg.lon * 1e-7, msg.alt * 1e-3, msg.vx * 0.01, msg.vy * 0.01)
            self.last = s
            self.hist.append(s)
            if len(self.hist) > 3000:
                del self.hist[:1000]


class Navera:
    """NAVERA's arbiter output as the real nodes publish it, from the truth (rclpy node)."""

    def __init__(self, truth, sigma, latency, seed):
        import rclpy
        from geometry_msgs.msg import TwistStamped
        from navera_msgs.msg import NavStatus, PositionEstimate
        self.rclpy, self.NavStatus = rclpy, NavStatus
        self.PositionEstimate, self.TwistStamped = PositionEstimate, TwistStamped
        rclpy.init()
        self.node = rclpy.create_node("navera_px4_sitl_emulation")
        self.pub_pos = self.node.create_publisher(PositionEstimate, "/navera/position", 10)
        self.pub_st = self.node.create_publisher(NavStatus, "/navera/nav_status", 10)
        self.pub_vel = self.node.create_publisher(TwistStamped, "/navera/sensors/gps_vel", 10)
        self.truth, self.sigma, self.latency = truth, sigma, latency
        self.rng = random.Random(seed)
        from sitl_closed_loop import VisionErrors
        self.vision = VisionErrors("good", self.rng)
        self.gps_on, self.silent = True, False
        self.ground = math.inf           # the take-off altitude (truth MSL), set at the first truth
        self.last_rx = {}                # source -> wall time of its last position
        self.pending = []                # (publish at, msg)
        self.n_day = self.n_day_ok = 0
        self.day_err = []
        self.stop = False
        threading.Thread(target=self._run, daemon=True).start()

    def _stamp(self, t):
        from builtin_interfaces.msg import Time
        return Time(sec=int(t), nanosec=int((t % 1.0) * 1e9))

    def _pos(self, source, lat, lon, alt, sigma, t_meas, details):
        m = self.PositionEstimate()
        m.header.stamp = self._stamp(time.time())
        m.header.frame_id = "map"
        m.latitude, m.longitude, m.altitude = lat, lon, alt
        v = sigma * sigma
        m.position_covariance = [v, 0.0, 0.0, 0.0, v, 0.0, 0.0, 0.0, 4.0 if source == 1 else 0.0]
        m.position_covariance_type = 2
        m.source, m.mode, m.valid, m.confidence = source, 0, True, 1.0
        m.sensor_stamp = self._stamp(t_meas)
        m.producer = "sitl_px4"
        m.frame_index = -1
        m.details_json = json.dumps(details)
        return m

    def _run(self):
        next_gps = next_photo = time.time()
        while not self.stop:
            now = time.time()
            tr = self.truth.last
            if tr is not None and not math.isfinite(self.ground):
                self.ground = tr[3]
            if tr is None or self.silent:
                time.sleep(0.05)
                continue
            if self.gps_on and now >= next_gps:
                next_gps = now + 0.2
                n, e = self.rng.gauss(0, GPS_NOISE_M), self.rng.gauss(0, GPS_NOISE_M)
                lat, lon = offset(tr[1], tr[2], n, e)
                self.pub_pos.publish(self._pos(1, lat, lon, tr[3], GPS_SIGMA_M, now,
                                               {"num_sats": 12, "geo_sep_m": 0.0}))
                v = self.TwistStamped()
                v.header.stamp = self._stamp(now)
                v.twist.linear.x, v.twist.linear.y = tr[5], tr[4]          # ENU: east, north
                self.pub_vel.publish(v)
                self.last_rx[1] = now
            if now >= next_photo and tr[3] - self.ground > 5.0:       # the day pipeline: always, once airborne
                next_photo = now + 1.0
                f = self.vision.next()
                self.n_day += 0 if self.gps_on else 1
                if f is not None:
                    self.n_day_ok += 0 if self.gps_on else 1
                    e_err, n_err, msig = f
                    lat, lon = offset(tr[1], tr[2], n_err, e_err)
                    if not self.gps_on:
                        self.day_err.append(math.hypot(n_err, e_err))
                    msg = self._pos(2, lat, lon, math.nan, max(self.sigma, msig), now, {})
                    self.pending.append((now + self.rng.uniform(*self.latency), msg))
            for item in [p for p in self.pending if p[0] <= now]:
                self.pending.remove(item)
                self.pub_pos.publish(item[1])
                self.last_rx[2] = now
            st = self.NavStatus()
            st.header.stamp = self._stamp(now)
            if self.gps_on and now - self.last_rx.get(1, 0) <= 3.0:
                st.state, st.active_source = 2, 1
            elif now - self.last_rx.get(2, 0) <= 3.0:
                st.state, st.active_source = 3, 2
            else:
                st.state, st.active_source = 1, 0
            st.reason = "sitl_px4 emulation"
            self.pub_st.publish(st)
            time.sleep(0.05)

    def close(self):
        self.stop = True
        time.sleep(0.2)
        self.node.destroy_node()
        self.rclpy.try_shutdown()


STARTED = []                             # every process started: stopped at exit, whatever happens


def start(cmd, log, env=None, cwd=None):
    p = subprocess.Popen(cmd, stdout=open(log, "a"), stderr=subprocess.STDOUT, start_new_session=True,
                         env=env, cwd=cwd)
    STARTED.append(p)
    return p


def stop_all(*_):
    for p in STARTED:
        stop(p)


def stop(p, sig=signal.SIGTERM):
    if p is None or p.poll() is not None:
        return
    try:
        os.killpg(p.pid, sig)
        p.wait(timeout=10)
    except Exception:                                 # noqa: BLE001
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def ros_node(exe, params, log):
    args = ["ros2", "run", "navera_output", exe, "--ros-args"]
    for k, v in params.items():
        args += ["-p", f"{k}:={v}"]
    return start(args, log)


def upload_mission(m, home):
    items = [(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, home[0], home[1], ALT_M)]
    for n, e in LEGS:
        la, lo = offset(home[0], home[1], n, e)
        items.append((mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, la, lo, ALT_M))
    items.append((mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH, 0, 0, 0))
    m.mav.mission_count_send(m.target_system, m.target_component, len(items), 0)
    sent = set()
    t_end = time.time() + 20
    while time.time() < t_end:
        r = m.recv_match(type=["MISSION_REQUEST_INT", "MISSION_REQUEST", "MISSION_ACK"], blocking=True, timeout=1)
        if r is None:
            continue
        if r.get_type() == "MISSION_ACK":
            if r.type != 0 or len(sent) != len(items):
                print(f"    mission ack {r.type} after {len(sent)}/{len(items)} items", flush=True)
                if not sent:
                    continue                  # an ack of something earlier
            return r.type == 0 and len(sent) == len(items)
        cmd, la, lo, alt = items[r.seq]
        frame = (mavutil.mavlink.MAV_FRAME_MISSION if cmd == mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH
                 else mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT)    # PX4: RTL only in the mission frame
        m.mav.mission_item_int_send(m.target_system, m.target_component, r.seq, frame, cmd, 0, 1,
                                    0, 0, 0, float("nan"), int(la * 1e7), int(lo * 1e7), alt, 0)
        sent.add(r.seq)
    return False


def run(a, scenario, out_dir):
    work = tempfile.mkdtemp(prefix=f"px4_{scenario}_", dir=a.workdir)
    os.makedirs(os.path.join(work, "hook"))
    params = dict(PX4_PARAMS, **a.set)
    if scenario == "no_hil_param":
        params["MAV_USEHILGPS"] = 0
    if scenario == "px4_defaults":
        params.update(COM_POS_FS_EPH=5.0, EKF2_NOAID_NOISE=10.0, EKF2_GPS_V_GATE=5.0)
    with open(os.path.join(work, "hook", "px4-rc.params"), "w") as f:
        f.write("#!/bin/sh\n" + "".join(f"param set {k} {v}\n" for k, v in params.items()))
    build = os.path.join(a.px4, "build", "px4_sitl_default")
    # the GCS link without its 50 Hz streams (a Python script reading them all would lag behind PX4)
    with open(os.path.join(build, "etc", "init.d-posix", "px4-rc.mavlink")) as f:
        rc = [ln for ln in f if not (ln.startswith("mavlink stream") and "udp_gcs_port_local" in ln)]
    rc.insert(rc.index(next(ln for ln in rc if "API/Offboard" in ln)),
              "mavlink stream -r 10 -s GLOBAL_POSITION_INT -u $udp_gcs_port_local\n")
    with open(os.path.join(work, "hook", "px4-rc.mavlink"), "w") as f:
        f.writelines(rc)
    env = dict(os.environ, PATH=os.path.join(work, "hook") + ":" + os.environ["PATH"],
               PX4_SIM_MODEL="sihsim_quadx", PX4_SIMULATOR="sihsim")
    i = a.instance
    # PX4's ports for instance i: GCS link 18570+i (answers whoever speaks), onboard link sends to
    # 14540+i, the SIH display link to 19410+i
    gcs_port, onboard_remote, sih_remote, relay = 18570 + i, 14540 + i, 19410 + i, a.relay_port
    procs = {}
    res = dict(scenario=scenario, params=params, sigma=a.sigma, events=[], statustext=[], modes=[])
    t0 = time.time()

    def ev(what):
        t = time.time() - t0
        res["events"].append((round(t, 1), what))
        print(f"  [{scenario} {t:6.1f}] {what}", flush=True)

    procs["px4"] = start([os.path.join(build, "bin", "px4"), "-d", "-i", str(i), "-w", os.path.join(work, "wd"),
                          os.path.join(build, "etc")], os.path.join(work, "px4.log"), env=env)
    gcs = mavutil.mavlink_connection(f"udpout:127.0.0.1:{gcs_port}", source_system=255)
    hb = None
    for _ in range(60):
        gcs.mav.heartbeat_send(6, 8, 0, 0, 0)
        hb = gcs.recv_match(type="HEARTBEAT", blocking=True, timeout=1)
        if hb is not None and hb.autopilot == mavutil.mavlink.MAV_AUTOPILOT_PX4:
            break
    if hb is None:
        ev("PX4 did not start")
        return res
    sysid = gcs.target_system
    ev(f"PX4 up (system {sysid})")
    truth = Truth(sih_remote)
    log_dir = os.path.join(work, "ros")
    os.makedirs(log_dir)
    procs["link"] = ros_node("vehicle_link_node.py", {"mavlink_url": f"udpin:127.0.0.1:{onboard_remote}",
                                                      "source_system": sysid, "relay_port": relay},
                             os.path.join(log_dir, "vehicle_link.log"))
    out_params = {"mavlink_url": f"udpout:127.0.0.1:{relay}", "mavlink_message": "auto",
                  "mavlink_system_id": sysid, "forward_degraded": "true", "degraded_sigma_m": float(a.sigma),
                  "max_speed_mps": 15.0}
    procs["output"] = ros_node("vehicle_output_node.py", out_params, os.path.join(log_dir, "vehicle_output.log"))
    nav = Navera(truth, a.sigma, a.latency, a.seed)
    for mid, hz in ((230, 2), (245, 2), (33, 10), (24, 2)):         # ESTIMATOR_STATUS, EXT_SYS_STATE, GPOS, GPS_RAW
        gcs.mav.command_long_send(sysid, 1, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, mid, 1e6 / hz,
                                  0, 0, 0, 0, 0)
    home = None
    reached, mode, armed, landed_state = set(), None, False, None
    phase, t_cut, t_event_done, t_restart = "start", None, False, None
    t_cut_boot = last_boot = None
    t_end = time.time() + a.timeout
    armed_once = False
    last_hb = 0.0
    last_text = {}
    while time.time() < t_end:
        if time.time() - last_hb > 1.0:
            gcs.mav.heartbeat_send(6, 8, 0, 0, 0)
            last_hb = time.time()
        msgs = []
        while True:                      # drain: the script must never lag behind PX4
            mm = gcs.recv_match(blocking=False)
            if mm is None:
                break
            msgs.append(mm)
        if not msgs:
            time.sleep(0.02)
        now = time.time()
        for msg in msgs:
            typ = msg.get_type()
            if typ == "HEARTBEAT" and msg.get_srcSystem() == sysid and msg.autopilot == 12:
                md = mavutil.mode_string_v10(msg)
                if md != mode:
                    mode = md
                    res["modes"].append((round(now - t0, 1), md))
                    ev(f"mode {md}")
                armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                armed_once |= armed
            elif typ == "STATUSTEXT":
                res["statustext"].append((round(now - t0, 1), msg.severity, msg.text))
                shown = last_text.get(msg.text, -99)
                if (msg.severity <= 4 or "ailsafe" in msg.text or "GPS" in msg.text) and now - shown > 20 \
                        and len(msg.text.strip()) > 2:
                    last_text[msg.text] = now
                    ev(f"PX4: {msg.text.strip()}")
            elif typ == "MISSION_ITEM_REACHED" and msg.seq not in reached:
                reached.add(msg.seq)
                ev(f"waypoint {msg.seq} reached")
                if msg.seq == 1 and t_cut is None:
                    nav.gps_on, t_cut, t_cut_boot, phase = False, now, last_boot, "denied"
                    ev("GPS LOST: NAVERA on day vision only from now on")
            elif typ == "EXTENDED_SYS_STATE":
                landed_state = msg.landed_state
            elif typ == "GLOBAL_POSITION_INT":
                last_boot = msg.time_boot_ms * 1e-3
            elif typ == "HOME_POSITION":
                home = (msg.latitude * 1e-7, msg.longitude * 1e-7)
        # the flight script
        if home is None and phase == "start":
            if not hasattr(run, "_asked") or now - run._asked > 2:
                gcs.mav.command_long_send(sysid, 1, mavutil.mavlink.MAV_CMD_GET_HOME_POSITION, 0, 0, 0, 0, 0, 0, 0, 0)
                run._asked = now
            if now - t0 > 120 and scenario == "no_hil_param":
                ev("no home position after 120 s (PX4 has no position): expected without MAV_USEHILGPS")
                break
            continue
        if phase == "start":
            ev(f"home {home[0]:.6f},{home[1]:.6f}: uploading the mission")
            if not upload_mission(gcs, home):
                ev("mission upload failed")
                break
            phase = "arming"
            t_arm, t_try = now, 0.0
            continue
        if phase == "arming":
            if not armed and now - t_arm < 90:
                if now - t_try >= 3.0:
                    t_try = now
                    gcs.mav.command_long_send(sysid, 1, mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0, 1, 4, 4, 0, 0, 0, 0)
                    gcs.mav.command_long_send(sysid, 1, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0,
                                              0, 0, 0)
                continue
            if not armed:
                ev("could not arm in 90 s")
                break
            phase = "gps"
            ev("armed, AUTO.MISSION")
            continue
        if t_cut is not None and not t_event_done:
            dt = now - t_cut
            if scenario == "navera_stop" and dt >= 90:
                nav.silent = True
                t_event_done = True
                ev("NAVERA STOPS (no /navera/position, no nav_status): output -> no fix")
            elif scenario == "output_restart" and dt >= 60 and t_restart is None:
                stop(procs["output"], signal.SIGKILL)
                t_restart = now
                ev("vehicle_output_node KILLED (SIGKILL)")
            if t_restart is not None and now - t_restart >= RESTART_S:
                procs["output"] = ros_node("vehicle_output_node.py", out_params,
                                           os.path.join(log_dir, "vehicle_output.log"))
                t_event_done = True
                ev("vehicle_output_node restarted")
        if armed_once and not armed and phase != "start":
            ev("disarmed (landed)")
            break
    res.update(waypoints_reached=sorted(reached), armed_once=armed_once, final_mode=mode,
               landed_state=landed_state, minutes=round((time.time() - t0) / 60, 1),
               vision=dict(photos=nav.n_day, accepted=nav.n_day_ok,
                           err_med=q(nav.day_err, 0.5), err_p90=q(nav.day_err, 0.9)))
    res["t_cut_boot_s"] = t_cut_boot
    nav.close()
    truth.stop = True
    for k in ("output", "link", "px4"):
        stop(procs.get(k))
    with open(os.path.join(out_dir, f"{scenario}.json"), "w") as f:
        json.dump(res, f, indent=1)
    for name in ("vehicle_output.log", "vehicle_link.log"):
        try:
            with open(os.path.join(log_dir, name)) as src:
                with open(os.path.join(out_dir, f"{scenario}_{name}"), "w") as dst:
                    dst.write(src.read())
        except OSError:
            pass
    ulogs = sorted(glob.glob(os.path.join(work, "wd", "log", "*", "*.ulg")))
    if ulogs:
        res["ulog"] = ulogs[-1]
        try:
            res.update(analyse_ulog(ulogs[-1], t_cut_boot))
        except Exception as e:                        # noqa: BLE001
            res["ulog_error"] = repr(e)
    with open(os.path.join(out_dir, f"{scenario}.json"), "w") as f:
        json.dump(res, f, indent=1)
    return res


NAV_STATES = {0: "MANUAL", 1: "ALTCTL", 2: "POSCTL", 3: "AUTO_MISSION", 4: "AUTO_LOITER", 5: "AUTO_RTL",
              10: "ACRO", 12: "DESCEND", 14: "OFFBOARD", 15: "STAB", 17: "AUTO_TAKEOFF", 18: "AUTO_LAND"}


def _stats(x):
    import numpy as np
    return dict(median=round(float(np.median(x)), 1), p90=round(float(np.percentile(x, 90)), 1),
                max=round(float(np.max(x)), 1))


def analyse_ulog(path, t_cut_boot):
    """From PX4's own log: EKF position error vs the simulator's truth after the GPS loss, its stated
    eph, how long the position was invalid, the navigation states, the landing point.
    """
    import numpy as np
    from pyulog import ULog
    u = ULog(path, ["vehicle_global_position", "vehicle_global_position_groundtruth", "vehicle_local_position",
                    "vehicle_status", "failsafe_flags", "vehicle_land_detected", "vehicle_local_position_groundtruth"])
    d = {x.name: x.data for x in u.data_list if x.multi_id == 0}
    gp, gt = d["vehicle_global_position"], d["vehicle_global_position_groundtruth"]
    t0 = u.start_timestamp
    out = {}
    tg = gt["timestamp"]
    idx = np.clip(np.searchsorted(tg, gp["timestamp"]), 0, len(tg) - 1)
    dn = np.radians(gp["lat"] - gt["lat"][idx]) * 6371000.0
    de = np.radians(gp["lon"] - gt["lon"][idx]) * 6371000.0 * np.cos(np.radians(gt["lat"][idx]))
    err = np.hypot(dn, de)
    tb = (gp["timestamp"] - 0) * 1e-6               # PX4 boot time, s (as GLOBAL_POSITION_INT)
    lp, ff, vs = d["vehicle_local_position"], d["failsafe_flags"], d["vehicle_status"]
    ld = d.get("vehicle_land_detected")
    t_end = math.inf                                  # the first touchdown after the GPS loss
    if t_cut_boot is not None and ld is not None:
        landed = (ld["timestamp"] * 1e-6 > t_cut_boot) & ld["landed"].astype(bool)
        if landed.any():
            t_end = float(ld["timestamp"][landed][0] * 1e-6)
    out["touchdown_after_cut_s"] = (round(t_end - t_cut_boot, 1) if math.isfinite(t_end) and t_cut_boot is not None
                                    else None)
    if t_cut_boot is not None:
        m = (tb >= t_cut_boot) & (tb < t_end)
        if m.any():
            e = err[m]
            out["ekf_err_denied_m"] = dict(_stats(e), n=int(m.sum()))
            out["denied_s"] = round(float(tb[m][-1] - t_cut_boot), 1)
        ml = (lp["timestamp"] * 1e-6 >= t_cut_boot) & (lp["timestamp"] * 1e-6 < t_end)
        if ml.any():
            eph = lp["eph"][ml]
            out["ekf_eph_denied_m"] = _stats(eph)
        mf = (ff["timestamp"] * 1e-6 >= t_cut_boot) & (ff["timestamp"] * 1e-6 < t_end)
        if mf.any():
            inv = ff["local_position_invalid"][mf].astype(bool) | ff["global_position_invalid"][mf].astype(bool)
            tt = ff["timestamp"][mf] * 1e-6
            out["position_invalid_after_cut_s"] = round(float(np.sum(np.diff(tt)[inv[:-1]])), 1) if len(tt) > 1 else 0.0
        rtl = (vs["timestamp"] * 1e-6 > t_cut_boot) & (vs["nav_state"] == 5)
        t_rtl = float(vs["timestamp"][rtl][0] * 1e-6) if rtl.any() else t_end
        mm = (tb >= t_cut_boot) & (tb < t_rtl)        # the GPS-denied mission legs, before RTL
        if mm.any():
            out["ekf_err_legs_m"] = _stats(err[mm])
        mr = (tb >= t_rtl) & (tb < t_end)             # RTL: the way home, the descent, the landing
        if mr.any():
            out["ekf_err_rtl_land_m"] = _stats(err[mr])
        mg = tb < t_cut_boot
        if mg.any():
            out["ekf_err_gps_m"] = dict(median=round(float(np.median(err[mg])), 2), max=round(float(err[mg].max()), 2))
    states, last = [], None
    for t, s in zip(vs["timestamp"], vs["nav_state"]):
        if s != last:
            states.append((round((int(t) - int(t0)) * 1e-6, 1), NAV_STATES.get(int(s), int(s))))
            last = s
    out["nav_states"] = states
    lg = d["vehicle_local_position_groundtruth"]
    out["final_truth_from_home_m"] = round(float(np.hypot(lg["x"][-1], lg["y"][-1])), 1)
    return out


def parse_set(s):
    out = {}
    for kv in filter(None, (s or "").split(",")):
        k, v = kv.split("=")
        out[k.strip()] = float(v) if "." in v else int(v)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--px4", default=os.path.expanduser("~/px4_sitl/PX4-Autopilot"))
    ap.add_argument("--scenarios", default="nominal,navera_stop,output_restart,no_hil_param,px4_defaults")
    ap.add_argument("--sigma", type=float, default=30.0)
    ap.add_argument("--latency", default="0.3,1.0")
    ap.add_argument("--instance", type=int, default=3)
    ap.add_argument("--relay-port", type=int, default=14663)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--timeout", type=float, default=900.0)
    ap.add_argument("--set", default="")
    ap.add_argument("--out", default=os.path.expanduser("~/.navera_sim/px4_sitl"))
    ap.add_argument("--workdir", default=os.path.expanduser("~/px4_sitl/runs"))
    ap.add_argument("--pyulog-path", default=os.path.expanduser("~/px4_sitl/pydeps"),
                    help="where pyulog is installed when not on the Python path (pip install --target)")
    a = ap.parse_args()
    sys.path.append(a.pyulog_path)
    a.latency = tuple(float(x) for x in a.latency.split(","))
    a.set = parse_set(a.set)
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.workdir, exist_ok=True)
    import atexit
    atexit.register(stop_all)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(1))
    os.environ.setdefault("ROS_DOMAIN_ID", "93")
    os.environ["ROS_LOCALHOST_ONLY"] = "1"
    rows = []
    for sc in a.scenarios.split(","):
        print(f"== {sc}", flush=True)
        r = run(a, sc, a.out)
        rows.append(r)
        e = r.get("ekf_err_denied_m") or {}
        print(f"   {sc}: waypoints {r.get('waypoints_reached')} final mode {r.get('final_mode')} "
              f"EKF err denied med/p90/max {e.get('median')}/{e.get('p90')}/{e.get('max')} m "
              f"eph {r.get('ekf_eph_denied_m')} denied {r.get('denied_s')} s, "
              f"landed {r.get('final_truth_from_home_m')} m from home", flush=True)
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump([{k: v for k, v in r.items() if k != "samples"} for r in rows], f, indent=1)


if __name__ == "__main__":
    main()
