"""Shared helpers for the ArduPilot SITL scripts that play NAVERA (sitl_f7_height.py,
sitl_closed_loop.py): start one SITL vehicle (Copter, Plane, Rover) with no simulated GPS, a
MAVLink link that tracks the simulator's truth (SIM_STATE) and the autopilot's clock, mission
upload, and the vehicle-specific way to get it moving.

Not a test itself. Needs an ArduPilot build (build/sitl/bin/arducopter, arduplane, ardurover).
"""
import math
import os
import signal
import subprocess
import time
from collections import deque

from pymavlink import mavutil

HOME = (35.8288, 10.6360, 300.0)             # lat, lon, ground altitude AMSL (m)

# binary, SITL model, default parameter file (as Tools/autotest/pysim/vehicleinfo.py)
VEHICLES = {
    "copter": ("arducopter", "quad", "Tools/autotest/default_params/copter.parm"),
    "plane": ("arduplane", "plane", "Tools/autotest/models/plane.parm"),
    "rover": ("ardurover", "rover", "Tools/autotest/default_params/rover.parm"),
}

# NAVERA's recommended parameters (docs/ARDUPILOT_INTEGRATION.md §3), no simulated GPS
NAVERA_PARAMS = {
    "GPS_TYPE": 14, "GPS_AUTO_CONFIG": 0, "SERIAL1_PROTOCOL": 2,
    "EK3_SRC1_POSXY": 3, "EK3_SRC1_VELXY": 0, "EK3_SRC1_VELZ": 0, "EK3_SRC1_POSZ": 1,
    "EK3_OGN_HGT_MASK": 0,
    "SIM_GPS_DISABLE": 1,                    # the only GPS is NAVERA's GPS_INPUT
    # every arming check except "logging": on a loaded Jetson at nice 19 the SITL log thread
    # misses its 5 s heartbeat ("AP_Logger: stuck thread") though the log is written
    "ARMING_CHECK": ((1 << 21) - 2) & ~(1 << 10),
}

MODE_NUMBERS = {
    "copter": {"STABILIZE": 0, "AUTO": 3, "GUIDED": 4, "LOITER": 5, "RTL": 6, "LAND": 9},
    "plane": {"MANUAL": 0, "CIRCLE": 1, "AUTO": 10, "RTL": 11, "LOITER": 12, "TAKEOFF": 13, "GUIDED": 15},
    "rover": {"MANUAL": 0, "HOLD": 4, "AUTO": 10, "RTL": 11, "GUIDED": 15},
}


def run(cmd, cwd, log):
    """A process at nice 19 in its own session (killed as a group by stop())."""
    return subprocess.Popen(["nice", "-n", "19"] + cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)


def stop(p):
    """Kill the process group started by run() (by its recorded PID)."""
    if p is None or p.poll() is not None:
        return
    try:
        os.killpg(p.pid, signal.SIGTERM)
        p.wait(timeout=10)
    except Exception:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def start_sitl(vehicle, ardupilot, work, params, instance=0, speedup=1.0, home=HOME):
    """Start the SITL vehicle in `work` with the defaults + params. Returns (Popen, tcp port)."""
    os.makedirs(work, exist_ok=True)
    parm = os.path.join(work, "navera.parm")
    with open(parm, "w") as f:
        f.writelines(f"{k} {v}\n" for k, v in params.items())
    binary, model, defaults = VEHICLES[vehicle]
    cmd = [os.path.join(ardupilot, "build/sitl/bin", binary), "--model", model,
           "--home", f"{home[0]},{home[1]},{home[2]},0",
           "--defaults", f"{os.path.join(ardupilot, defaults)},{parm}", f"-I{instance}"]
    if speedup != 1.0:
        cmd += ["--speedup", f"{speedup:g}"]
    p = run(cmd, work, open(os.path.join(work, "sitl.log"), "w"))
    return p, 5760 + 10 * instance


def offset_ll(lat, lon, dn, de):
    """lat, lon moved dn metres north and de metres east (flat earth, short distances)."""
    return lat + dn / 111319.5, lon + de / (111319.5 * math.cos(math.radians(lat)))


def ne_from(lat0, lon0, lat, lon):
    """(north, east) metres of lat, lon from lat0, lon0."""
    return (lat - lat0) * 111319.5, (lon - lon0) * 111319.5 * math.cos(math.radians(lat0))


class Link:
    """MAVLink to the SITL vehicle: the simulator's truth, the autopilot's clock, its texts."""

    WATCH = ("MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK", "MISSION_ITEM_REACHED",
             "COMMAND_ACK", "PARAM_VALUE")

    def __init__(self, port, verbose=True):
        self.mav = mavutil.mavlink_connection(f"tcp:127.0.0.1:{port}", source_system=250)
        self.mav.wait_heartbeat(timeout=60)
        self.truth = None                    # (lat, lon, alt AMSL) of the simulated vehicle
        self.truth_ms = 0                    # autopilot boot time of that truth
        self.boot_ms = 0
        self._boot_wall = time.time()        # wall-clock instant boot_ms last advanced
        self.speedup = 1.0
        self.texts = []                      # (boot_ms, text)
        self.inbox = deque(maxlen=200)       # mission / command protocol messages
        self.last = {}                       # last message of each type
        self.verbose = verbose
        self.on_message = None               # optional callback(msg)

    def request(self, rates):
        """MAV_CMD_SET_MESSAGE_INTERVAL for {message id: Hz}."""
        for msg_id, hz in rates.items():
            self.mav.mav.command_long_send(self.mav.target_system, self.mav.target_component,
                                           mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                                           msg_id, 1e6 / hz, 0, 0, 0, 0, 0)

    @property
    def t(self):
        """Autopilot time, s (the simulation's clock: follows --speedup and a slow host), extrapolated
        between its messages by the wall clock (at most 0.1 s)."""
        t = self.boot_ms / 1000.0 + min(0.1, (time.time() - self._boot_wall) * self.speedup)
        self._t_last = max(t, getattr(self, "_t_last", 0.0))          # never backwards
        return self._t_last

    def pump(self, timeout=0.05):
        end = time.time() + timeout
        while True:
            m = self.mav.recv_match(blocking=True, timeout=max(0.0, end - time.time()))
            if m is None:
                return
            t = m.get_type()
            if t == "BAD_DATA":
                continue
            if hasattr(m, "time_boot_ms") and m.time_boot_ms > self.boot_ms:
                self.boot_ms = m.time_boot_ms
                self._boot_wall = time.time()
            self.last[t] = m
            if t == "SIM_STATE":
                self.truth = (m.lat_int / 1e7, m.lon_int / 1e7, m.alt) if getattr(m, "lat_int", 0) \
                    else (m.lat, m.lon, m.alt)
                self.truth_ms = self.boot_ms
            elif t == "STATUSTEXT":
                self.texts.append((self.boot_ms, m.text))
                if self.verbose:
                    print(f"    ap {self.boot_ms / 1000:7.1f}: {m.text}")
            elif t in self.WATCH:
                self.inbox.append(m)
            if self.on_message is not None:
                self.on_message(m)

    def take(self, types):
        """The oldest queued protocol message of one of `types`, or None."""
        for i, m in enumerate(self.inbox):
            if m.get_type() in types:
                del self.inbox[i]
                return m
        return None

    def mode_name(self):
        hb = self.last.get("HEARTBEAT")
        return mavutil.mode_string_v10(hb) if hb is not None else "?"

    def set_mode(self, vehicle, name):
        self.mav.mav.set_mode_send(self.mav.target_system, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                                   MODE_NUMBERS[vehicle][name])

    def armed(self):
        hb = self.last.get("HEARTBEAT")
        return bool(hb and hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)

    def arm(self):
        self.mav.mav.command_long_send(self.mav.target_system, self.mav.target_component,
                                       mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)

    def command(self, cmd, *p):
        p = list(p) + [0] * (7 - len(p))
        self.mav.mav.command_long_send(self.mav.target_system, self.mav.target_component, cmd, 0, *p)

    def set_param(self, name, value):
        self.mav.mav.param_set_send(self.mav.target_system, self.mav.target_component, name.encode(),
                                    float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)


def mission_item(seq, cmd, lat=0.0, lon=0.0, alt=0.0, p1=0.0, p2=0.0, p3=0.0, p4=0.0):
    """One MISSION_ITEM_INT (relative altitude frame)."""
    return dict(seq=seq, frame=mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, command=cmd,
                current=0, autocontinue=1, param1=p1, param2=p2, param3=p3, param4=p4,
                x=int(round(lat * 1e7)), y=int(round(lon * 1e7)), z=float(alt))


def upload_mission(link, items, idle, timeout=30.0):
    """Upload items (item 0 = home placeholder) while calling idle() between messages."""
    mav = link.mav
    link.inbox.clear()
    mav.mav.mission_count_send(mav.target_system, mav.target_component, len(items),
                               mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
    end = time.time() + timeout
    while time.time() < end:
        idle()
        m = link.take(("MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"))
        if m is None:
            continue
        if m.get_type() == "MISSION_ACK":
            if m.type != 0:
                raise RuntimeError(f"mission refused (MISSION_ACK {m.type})")
            return
        it = dict(items[m.seq])
        mav.mav.mission_item_int_send(mav.target_system, mav.target_component, it.pop("seq"),
                                      it.pop("frame"), it.pop("command"), it.pop("current"),
                                      it.pop("autocontinue"), it["param1"], it["param2"], it["param3"],
                                      it["param4"], it["x"], it["y"], it["z"],
                                      mavutil.mavlink.MAV_MISSION_TYPE_MISSION)
    raise RuntimeError("mission upload timed out")
