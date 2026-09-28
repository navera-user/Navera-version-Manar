"""ArduPilot SITL: start it, fly it, read what it knows.

The SITL autopilot runs with its GPS input set to MAVLink (GPS_TYPE 14): the
only position it receives is NAVERA's vehicle output (GPS_INPUT on SERIAL1).
Its own simulated GPS is disabled. This link (SERIAL0) is the ground station:
it reads the simulator's TRUE state (SIM_STATE) and the autopilot's own belief
(GLOBAL_POSITION_INT from its EKF), and sends mode / arm / goto commands.
"""
import math
import os
import signal
import subprocess
import threading
import time

from pymavlink import mavutil

VEHICLES = {
    # key: (binary, model, extra default files, speed param, speed scale)
    "drone": ("arducopter", "quad", ["copter.parm"], "WPNAV_SPEED", 100.0),
    "boat": ("ardurover", "motorboat", ["rover.parm", "motorboat.parm"], "WP_SPEED", 1.0),
    "robot": ("ardurover", "rover", ["rover.parm"], "WP_SPEED", 1.0),
}
GCS_URL = "tcp:127.0.0.1:5760"            # SERIAL0
NAVERA_URL = "tcp:127.0.0.1:5762"         # SERIAL1: NAVERA's GPS_INPUT
EKF_POS_OK = 0x10                          # EKF_POS_HORIZ_ABS


class Autopilot:
    def __init__(self, ardupilot_dir, work_dir, log):
        self.dir = os.path.expanduser(ardupilot_dir)
        self.work = work_dir
        self.log = log                     # callable(level, text)
        self.proc = None
        self.mav = None
        self.vehicle = None
        self._stop = threading.Event()
        self._thread = None
        self.lock = threading.Lock()
        self.reset_state()

    def reset_state(self):
        # Truth from the physics (SIM_STATE), never from the autopilot's estimate:
        # (lat, lon, alt above start m, heading deg, ground speed m/s, course deg,
        #  v_north, v_east, v_down m/s, alt MSL m)
        self.truth = None
        self.home_alt = None
        self.belief = None         # (lat, lon) from the EKF
        self.gps_raw = None        # (fix_type, lat, lon, sats, eph_m)
        self.mode = "—"
        self.armed = False
        self.ekf_flags = 0
        self.last_hb = 0.0
        self.attitude = (0.0, 0.0, 0.0)
        self.gyro = (0.0, 0.0, 0.0)

    # ---------- process ----------
    def start(self, vehicle, lat, lon, heading=0.0):
        self.stop()
        self.reset_state()
        binary, model, defaults, _, _ = VEHICLES[vehicle]
        self.vehicle = vehicle
        dp = os.path.join(self.dir, "Tools/autotest/default_params")
        params = os.path.join(self.work, "navera_sim.parm")
        with open(params, "w") as f:
            f.write("GPS_TYPE 14\nSIM_GPS_DISABLE 1\nGPS_AUTO_CONFIG 0\n"
                    "SERIAL1_PROTOCOL 2\n"
                    # GCS failsafe off: the simulator is the only ground station
                    "FS_GCS_ENABLE 0\n"
                    # no onboard flight log: SITL's logger thread stalls under load
                    # and then blocks arming ("Logging failed")
                    "LOG_BACKEND_TYPE 0\n"
                    # NAVERA integration (navera_output/README.md): position only
                    # from NAVERA; velocity from the autopilot's own IMU
                    "EK3_SRC1_VELXY 0\nEK3_SRC1_VELZ 0\n")
            if vehicle == "drone":
                f.write("ANGLE_MAX 4500\n")      # 30 deg caps the SITL quad at ~10 m/s
        files = ",".join([os.path.join(dp, d) for d in defaults] + [params])
        cmd = [os.path.join(self.dir, "build/sitl/bin", binary), "--model", model,
               "--home", f"{lat},{lon},10,{heading}", "--defaults", files, "-I0", "-w"]
        self.proc = subprocess.Popen(cmd, cwd=self.work, stdout=open(os.path.join(self.work, "sitl.log"), "w"),
                                     stderr=subprocess.STDOUT, start_new_session=True)
        self.log("info", f"autopilot: ArduPilot SITL {binary} ({model}) started")

    def connect(self, timeout=40.0):
        end = time.time() + timeout
        while time.time() < end:
            if self.proc is None or self.proc.poll() is not None:
                raise RuntimeError("SITL exited — see sitl.log")
            try:
                self.mav = mavutil.mavlink_connection(GCS_URL, source_system=255, autoreconnect=True)
                if self.mav.wait_heartbeat(timeout=5):
                    break
            except Exception:
                time.sleep(1)
        else:
            raise RuntimeError("no heartbeat from SITL")
        self.mav.mav.request_data_stream_send(self.mav.target_system, self.mav.target_component,
                                              mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
        self._cmd(mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 108, 50000)    # SIM_STATE 20 Hz
        self._stop.clear()
        self._thread = threading.Thread(target=self._rx, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None
        if self.mav:
            try:
                self.mav.close()
            except Exception:
                pass
        self.mav = None
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
                self.proc.wait(timeout=5)
            except Exception:
                os.killpg(self.proc.pid, signal.SIGKILL)
        self.proc = None

    # ---------- telemetry ----------
    def _rx(self):
        while not self._stop.is_set():
            try:
                m = self.mav.recv_match(blocking=True, timeout=0.5)
            except Exception:
                time.sleep(0.2)
                continue
            if m is None:
                continue
            t = m.get_type()
            with self.lock:
                if t == "SIM_STATE":
                    if self.home_alt is None:
                        self.home_alt = m.alt
                    spd = math.hypot(m.vn, m.ve)
                    course = math.degrees(math.atan2(m.ve, m.vn)) % 360 if spd > 0.3 else \
                        math.degrees(m.yaw) % 360
                    self.truth = (m.lat_int / 1e7, m.lon_int / 1e7, m.alt - self.home_alt,
                                  math.degrees(m.yaw) % 360, spd, course, m.vn, m.ve, m.vd, m.alt)
                    self.attitude = (m.roll, m.pitch, m.yaw)
                    self.gyro = (m.xgyro, m.ygyro, m.zgyro)
                elif t == "GLOBAL_POSITION_INT":
                    self.belief = (m.lat / 1e7, m.lon / 1e7)
                elif t == "GPS_RAW_INT":
                    self.gps_raw = (m.fix_type, m.lat / 1e7, m.lon / 1e7, m.satellites_visible,
                                    m.eph / 100.0 if m.eph not in (0, 65535) else math.nan)
                elif t == "HEARTBEAT" and m.get_srcSystem() == self.mav.target_system \
                        and m.type != mavutil.mavlink.MAV_TYPE_GCS:
                    self.mode = self.mav.flightmode
                    self.armed = bool(m.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    self.last_hb = time.monotonic()
                elif t == "EKF_STATUS_REPORT":
                    self.ekf_flags = m.flags
            if t == "STATUSTEXT":
                txt = m.text.strip()
                if txt and not txt.startswith(("PreArm: Waiting", "Field Elevation")):
                    self.log("warn" if m.severity <= 4 else "info", f"autopilot: {txt}")

    def snapshot(self):
        with self.lock:
            return dict(truth=self.truth, belief=self.belief, gps_raw=self.gps_raw,
                        mode=self.mode, armed=self.armed,
                        ekf_pos_ok=bool(self.ekf_flags & EKF_POS_OK),
                        link=time.monotonic() - self.last_hb < 3.0 if self.last_hb else False,
                        attitude=self.attitude, gyro=self.gyro)

    # ---------- commands ----------
    def _cmd(self, command, *p):
        p = list(p) + [0] * (7 - len(p))
        self.mav.mav.command_long_send(self.mav.target_system, self.mav.target_component,
                                       command, 0, *p)

    def set_param(self, name, value):
        self.mav.mav.param_set_send(self.mav.target_system, self.mav.target_component,
                                    name.encode(), float(value),
                                    mavutil.mavlink.MAV_PARAM_TYPE_REAL32)

    def set_mode(self, name):
        mapping = self.mav.mode_mapping() or {}
        if name not in mapping:
            raise RuntimeError(f"mode {name} unknown")
        self.mav.set_mode(mapping[name])

    def arm(self):
        self._cmd(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)

    def takeoff(self, alt):
        self._cmd(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, alt)

    def goto(self, lat, lon, alt):
        self.mav.mav.set_position_target_global_int_send(
            0, self.mav.target_system, self.mav.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, 0b110111111000,
            int(lat * 1e7), int(lon * 1e7), alt, 0, 0, 0, 0, 0, 0, 0, 0)

    def set_speed(self, mps):
        _, _, _, pname, scale = VEHICLES[self.vehicle]
        self.set_param(pname, mps * scale)
        self._cmd(mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED, 1, mps, -1)
