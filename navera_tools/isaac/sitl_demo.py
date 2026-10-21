#!/usr/bin/env python3
"""Closed-loop demo: ArduPilot SITL flies an AUTO mission over the Isaac Sim scene; after the GPS
cut it flies ONLY on NAVERA's vision positions (GPS_INPUT from navera_output). SIMULATION.

    python3 navera_tools/isaac/sitl_demo.py --master udpin:127.0.0.1:14550 --results DIR
        [--vehicle copter] [--alt 250] [--radius 500] [--speed 8] [--cut-after 15]

Started by run_closed_loop.sh after SITL (GPS_TYPE 14, SIM_GPS_DISABLE 1: its only position is
NAVERA's GPS_INPUT) and MAVProxy (map + console). This script:
  * streams the simulator's TRUTH (SIM_STATE, 50 Hz) + the autopilot's EKF position
    (GLOBAL_POSITION_INT) as UDP JSON to Isaac Sim (--isaac-port: places the vehicle and its
    camera) and to the NAVERA link (--link-port: IMU, baro, GPS, truth), t = s since its t0;
  * flies: mission upload (take-off to --alt above home, a diamond of --radius around the scene
    centre at --speed, back to the first corner, RTL), AUTO, arm;
  * cuts the GPS --cut-after s after the vehicle reaches its altitude: the "gps" flag in the
    packets turns false and the link stops the receiver; NAVERA's output is then vision only;
  * records the autopilot's texts and modes (sitl_events.jsonl) and ends --hold-home s after the
    vehicle is back over home in RTL (RTL_ALT_FINAL keeps it at altitude: day vision needs
    height — closed-loop test 2 lost its fixes below ~150 m during the landing and drifted
    ~500 m), or when it has landed and disarmed, or at --timeout.
"""
import argparse
import json
import math
import os
import socket
import sys
import time

from pymavlink import mavutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from flight_profile import GeoRef  # noqa: E402

COPTER_MODES = {0: "STABILIZE", 3: "AUTO", 4: "GUIDED", 5: "LOITER", 6: "RTL", 9: "LAND", 2: "ALT_HOLD"}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--master", default="udpin:127.0.0.1:14550")
    ap.add_argument("--results", required=True)
    ap.add_argument("--vehicle", default="copter", choices=("copter", "plane"))
    ap.add_argument("--lat0", type=float, default=35.8685)
    ap.add_argument("--lon0", type=float, default=10.5352)
    ap.add_argument("--alt", type=float, default=250.0, help="m above home")
    ap.add_argument("--radius", type=float, default=500.0)
    ap.add_argument("--speed", type=float, default=8.0)
    ap.add_argument("--cut-after", type=float, default=15.0, help="s after reaching the altitude")
    ap.add_argument("--isaac-port", type=int, default=15500)
    ap.add_argument("--link-port", type=int, default=15501)
    ap.add_argument("--timeout", type=float, default=1200.0)
    ap.add_argument("--hold-home", type=float, default=45.0, help="s over home (RTL) before the demo ends")
    ap.add_argument("--arm-after-file", default="", help="arm only once this file exists (Isaac Sim rendering)")
    a = ap.parse_args()
    os.makedirs(a.results, exist_ok=True)
    geo = GeoRef(a.lat0, a.lon0)
    ev = open(os.path.join(a.results, "sitl_events.jsonl"), "a")
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    m = mavutil.mavlink_connection(a.master, source_system=245)
    m.wait_heartbeat(timeout=120)
    ts, tc = m.target_system, m.target_component
    t0 = time.time()
    json.dump(dict(t0_wall=t0, vehicle=a.vehicle, lat0=a.lat0, lon0=a.lon0, alt=a.alt, radius=a.radius,
                   speed=a.speed, cut_after=a.cut_after), open(os.path.join(a.results, "sitl_session.json"), "w"))

    def log(kind, **kw):
        d = dict(t=round(time.time() - t0, 2), kind=kind, **kw)
        ev.write(json.dumps(d) + "\n")
        ev.flush()
        print(f"[{d['t']:7.1f}] {kind} {kw}", flush=True)

    for msgid, hz in ((mavutil.mavlink.MAVLINK_MSG_ID_SIM_STATE, 50), (mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT, 10),
                      (mavutil.mavlink.MAVLINK_MSG_ID_EKF_STATUS_REPORT, 2), (mavutil.mavlink.MAVLINK_MSG_ID_HOME_POSITION, 1)):
        m.mav.command_long_send(ts, tc, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, msgid, int(1e6 / hz),
                                0, 0, 0, 0, 0)

    state = dict(gps=True, done=False, phase="boot", mode="?", armed=False, ekf=None, home=None, rel=0.0)
    flown = dict(mission_sent=False, armed_at=None, at_alt=None, cut_at=None, landed_at=None, was_armed=False,
                 rtl_at=None, home_at=None)
    wps = []

    def send(d):
        data = json.dumps(d).encode()
        for port in (a.isaac_port, a.link_port):
            out.sendto(data, ("127.0.0.1", port))

    def upload():
        rel = mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
        home = state["home"]
        items = [(mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, home[0], home[1], 0.0)]
        items.append((mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, home[0], home[1], a.alt))
        for k in range(5):                                  # a diamond, back to its first corner
            th = math.radians(90 * k)
            wps.append(geo.to_latlon(a.radius * math.cos(th), a.radius * math.sin(th)))
            items.append((mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, wps[-1][0], wps[-1][1], a.alt))
        items.append((mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH, 0, 0, 0))
        m.mav.mission_count_send(ts, tc, len(items))
        deadline = time.time() + 30
        sent = set()
        while len(sent) < len(items) and time.time() < deadline:
            r = m.recv_match(type=["MISSION_REQUEST", "MISSION_REQUEST_INT"], blocking=True, timeout=2)
            if r is None:
                continue
            cmd, lat, lon, alt = items[r.seq]
            m.mav.mission_item_int_send(ts, tc, r.seq, rel, cmd, 0, 1, 0, 0, 0, 0, int(lat * 1e7), int(lon * 1e7), alt)
            sent.add(r.seq)
        log("mission", items=len(items), waypoints=[[round(p[0], 6), round(p[1], 6)] for p in wps])

    last_try = last_home = 0.0
    while True:
        now = time.time()
        t = now - t0
        msg = m.recv_match(blocking=True, timeout=0.5)
        if msg is not None:
            typ = msg.get_type()
            if typ == "SIM_STATE":
                # SIM_STATE position: lat_int/lon_int (degE7) when present — ArduPilot 4.5.7 also
                # fills lat/lon with degE7 in float32 (~1 m steps), other versions with degrees
                if getattr(msg, "lat_int", 0):
                    lat, lon = msg.lat_int / 1e7, msg.lon_int / 1e7
                else:
                    lat = msg.lat / 1e7 if abs(msg.lat) > 1000 else msg.lat
                    lon = msg.lon / 1e7 if abs(msg.lon) > 1000 else msg.lon
                send(dict(t=round(t, 4), t0=t0, vehicle=a.vehicle, lat=lat, lon=lon, alt=msg.alt,
                          rel=state["rel"], vn=msg.vn, ve=msg.ve, vd=msg.vd,
                          roll=math.degrees(msg.roll), pitch=math.degrees(msg.pitch),
                          hdg=math.degrees(msg.yaw) % 360.0, p=msg.xgyro, q=-msg.ygyro, r=-msg.zgyro,
                          ekf=state["ekf"], gps=state["gps"], done=state["done"], phase=state["phase"],
                          mode=state["mode"], armed=state["armed"], home=state["home"]))
            elif typ == "GLOBAL_POSITION_INT":
                if msg.lat:
                    state["ekf"] = [msg.lat / 1e7, msg.lon / 1e7, msg.alt / 1000.0]
                state["rel"] = msg.relative_alt / 1000.0
            elif typ == "HOME_POSITION" and state["home"] is None:
                state["home"] = [msg.latitude / 1e7, msg.longitude / 1e7, msg.altitude / 1000.0]
                log("home", home=state["home"])
            elif typ == "HEARTBEAT" and msg.get_srcSystem() == ts and msg.type != mavutil.mavlink.MAV_TYPE_GCS:
                mode = COPTER_MODES.get(msg.custom_mode, str(msg.custom_mode)) if a.vehicle == "copter" \
                    else str(msg.custom_mode)
                armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                if mode != state["mode"] or armed != state["armed"]:
                    log("mode", mode=mode, armed=armed)
                state["mode"], state["armed"] = mode, armed
            elif typ == "STATUSTEXT":
                log("text", text=msg.text)
                if "RTL" in msg.text and flown["rtl_at"] is None and flown["cut_at"] is not None:
                    flown["rtl_at"] = time.time() - t0
                    state["phase"] = "RTL on NAVERA vision"
            elif typ == "EKF_STATUS_REPORT":
                state["ekf_flags"] = msg.flags
        # ── the flight sequence ──
        if state["home"] is None and now - last_home > 2.0:      # ArduPilot sends it on request
            last_home = now
            m.mav.command_long_send(ts, tc, mavutil.mavlink.MAV_CMD_GET_HOME_POSITION, 0, 0, 0, 0, 0, 0, 0, 0)
        if not flown["mission_sent"] and state["home"] is not None and state.get("ekf_flags", 0) & 0x10:
            upload()
            flown["mission_sent"] = True
            state["phase"] = "arming"
        if flown["mission_sent"] and not state["armed"] and not flown["was_armed"] and now - last_try > 3 \
                and (not a.arm_after_file or os.path.exists(a.arm_after_file)):
            last_try = now
            m.set_mode("AUTO")
            m.mav.command_long_send(ts, tc, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        if state["armed"] and not flown["was_armed"]:
            flown["was_armed"], flown["armed_at"] = True, t
            state["phase"] = "climb (GPS)"
        if flown["was_armed"] and flown["at_alt"] is None and state["rel"] > 0.95 * a.alt:
            flown["at_alt"] = t
            state["phase"] = "mission (GPS)"
            log("at_altitude", rel=state["rel"])
        if flown["at_alt"] is not None and state["gps"] and t > flown["at_alt"] + a.cut_after:
            state["gps"], flown["cut_at"] = False, t
            state["phase"] = "mission (GPS CUT: NAVERA vision only)"
            log("gps_cut", t_cut=t)
        if flown["rtl_at"] is not None and flown["home_at"] is None and state["ekf"] and state["home"]:
            d = math.hypot((state["ekf"][0] - state["home"][0]) * 111320.0,
                           (state["ekf"][1] - state["home"][1]) * 111320.0 * math.cos(math.radians(state["home"][0])))
            if d < 30.0:
                flown["home_at"] = t
                state["phase"] = "over home (RTL, holding at altitude)"
                log("home_reached", ekf_dist_m=round(d, 1))
        if flown["home_at"] is not None and t > flown["home_at"] + a.hold_home and not state["done"]:
            flown["landed_at"] = flown["landed_at"] or t
        if flown["was_armed"] and not state["armed"] and flown["landed_at"] is None:
            flown["landed_at"] = t
            state["phase"] = "landed"
            log("landed")
        if (flown["landed_at"] is not None and t > flown["landed_at"] + 5) or t > a.timeout:
            state["done"] = True
            for _ in range(20):
                send(dict(t=round(time.time() - t0, 4), t0=t0, vehicle=a.vehicle, done=True, gps=state["gps"],
                          phase=state["phase"]))
                time.sleep(0.05)
            log("done", flown={k: (round(v, 1) if isinstance(v, float) else v) for k, v in flown.items()})
            json.dump(dict(flown, wps=wps), open(os.path.join(a.results, "sitl_flown.json"), "w"))
            return


if __name__ == "__main__":
    main()
