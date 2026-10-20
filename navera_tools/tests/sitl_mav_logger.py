#!/usr/bin/env python3
"""Logs the SITL autopilot's own belief (EKF position/height, baro, EKF status) to JSON lines.

    python3 navera_tools/tests/sitl_mav_logger.py OUT.jsonl [tcp:127.0.0.1:5763]

SERIAL2 of ArduPilot SITL (the simulator's own links use 5760 / 5762). Read-only except for
the telemetry stream-rate request. SIMULATED runs only.
"""
import json
import sys
import time

from pymavlink import mavutil

url = sys.argv[2] if len(sys.argv) > 2 else "tcp:127.0.0.1:5763"


def connect():
    """SITL restarts with every mission: (re)connect, and ask for the telemetry streams."""
    while True:
        try:
            m = mavutil.mavlink_connection(url)
            if m.wait_heartbeat(timeout=10):
                m.mav.request_data_stream_send(m.target_system, m.target_component,
                                               mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1)
                return m
            m.close()
        except OSError:
            pass
        time.sleep(2)


KEEP = {"GLOBAL_POSITION_INT": ("lat", "lon", "alt", "relative_alt", "vx", "vy", "vz"),
        "LOCAL_POSITION_NED": ("x", "y", "z", "vx", "vy", "vz"),
        "VFR_HUD": ("alt", "climb", "groundspeed", "throttle"),
        "EKF_STATUS_REPORT": ("flags", "velocity_variance", "pos_horiz_variance", "pos_vert_variance",
                              "terrain_alt_variance"),
        "SCALED_PRESSURE": ("press_abs",), "GPS_RAW_INT": ("fix_type", "lat", "lon", "alt", "eph", "epv", "vel"),
        "HEARTBEAT": ("custom_mode",), "NAV_CONTROLLER_OUTPUT": ("alt_error", "wp_dist"),
        "POSITION_TARGET_GLOBAL_INT": ("lat_int", "lon_int", "alt"),
        "ATTITUDE": ("roll", "pitch", "yaw"), "AHRS2": ("roll", "pitch", "yaw", "altitude"),
        "SIMSTATE": ("roll", "pitch", "yaw", "xacc", "yacc", "zacc", "lat", "lng")}
with open(sys.argv[1], "w", buffering=1) as f:
    m = connect()
    quiet_since = time.time()
    while True:
        msg = m.recv_match(blocking=True, timeout=2)
        if msg is None:
            if time.time() - quiet_since > 10:        # the link died (SITL restarted)
                m.close()
                m = connect()
                quiet_since = time.time()
            continue
        quiet_since = time.time()
        if msg.get_type() not in KEEP:
            continue
        d = {k: getattr(msg, k, None) for k in KEEP[msg.get_type()]}
        d.update(t=msg.get_type(), wall=round(time.time(), 3))
        f.write(json.dumps(d) + "\n")
