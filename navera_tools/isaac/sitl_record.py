#!/usr/bin/env python3
"""Fly a circuit with ArduPilot SITL (real autopilot, real flight dynamics, wind and turbulence)
and record the flown trajectory for the Isaac Sim flight (flight_profile.Trajectory).

    python3 navera_tools/isaac/sitl_record.py --vehicle plane|copter --lat 35.8685 --lon 10.5352 \
        --dem ~/.navera_sim/isaac/kalaa/dem --out traj_plane.csv [--height 500] [--radius 900]
        [--speed 25] [--wind 7 --wind-dir 290 --turb 2] [--record 480] [--instance 8] [--speedup 8]

The autopilot (ArduPilot's own SITL build, $NAVERA_ARDUPILOT or ~/ardupilot) takes off from
the circuit's east point (home elevation from the DEM), climbs to --height above home and
circles the centre: a plane with NAV_LOITER_TURNS of --radius, a quadcopter through 36
waypoints on the circle. Wind, gusts and turbulence are ArduPilot's (SIM_WIND_*). Its normal
simulated GPS is used — this only records how the vehicle flies; NAVERA is not in the loop.

Recorded at 50 Hz of simulated time (ATTITUDE + GLOBAL_POSITION_INT): t (s), lat, lon,
alt_msl (m), rel_alt (m), vn, ve, vd (m/s), roll, pitch, heading (deg; heading clockwise from
north), p, q, r (body rates FLU, rad/s). The header line `# station_t=<s>` marks when the
vehicle is on the circuit at height (the Isaac flight starts there).

A separate SITL instance (-I, ports 5760 + 10 I) and its own working directory: it never
touches another simulator. Stops SITL at the end.
"""
import argparse
import math
import os
import subprocess
import sys
import tempfile
import time

from pymavlink import mavutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from flight_profile import GeoRef  # noqa: E402
from scene_dem import Dem  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--vehicle", choices=("plane", "copter"), required=True)
    ap.add_argument("--lat", type=float, required=True, help="circuit centre")
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--dem", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--height", type=float, default=500.0, help="m above home")
    ap.add_argument("--radius", type=float, default=900.0)
    ap.add_argument("--speed", type=float, default=25.0, help="m/s (plane airspeed / copter WP speed)")
    ap.add_argument("--wind", type=float, default=7.0)
    ap.add_argument("--wind-dir", type=float, default=290.0)
    ap.add_argument("--turb", type=float, default=2.0)
    ap.add_argument("--record", type=float, default=480.0, help="s on the circuit to record")
    ap.add_argument("--instance", type=int, default=8)
    ap.add_argument("--speedup", type=float, default=8.0)
    a = ap.parse_args()

    apdir = os.path.expanduser(os.environ.get("NAVERA_ARDUPILOT", "~/ardupilot"))
    geo = GeoRef(a.lat, a.lon)
    home = geo.to_latlon(a.radius, 0.0)
    home_alt = Dem(a.dem).height(*home)
    if a.vehicle == "plane":
        binary, model = "arduplane", "plane"
        defaults = [os.path.join(apdir, "Tools/autotest/models/plane.parm")]
    else:
        binary, model = "arducopter", "quad"
        defaults = [os.path.join(apdir, "Tools/autotest/default_params/copter.parm")]
    work = tempfile.mkdtemp(prefix=f"isaac_sitl_{a.vehicle}_")
    cmd = [os.path.join(apdir, "build/sitl/bin", binary), "--model", model,
           "--home", f"{home[0]:.7f},{home[1]:.7f},{home_alt:.1f},0", "--defaults", ",".join(defaults),
           f"-I{a.instance}", "--speedup", str(a.speedup)]
    print("SITL:", " ".join(cmd), flush=True)
    proc = subprocess.Popen(cmd, cwd=work, stdout=open(os.path.join(work, "sitl.log"), "w"),
                            stderr=subprocess.STDOUT)
    try:
        record(a, proc, home, home_alt, geo)
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


def record(a, proc, home, home_alt, geo):
    port = 5760 + 10 * a.instance
    m = None
    for _ in range(60):
        try:
            m = mavutil.mavlink_connection(f"tcp:127.0.0.1:{port}", source_system=255)
            break
        except Exception:                      # noqa: BLE001 — SITL still starting
            time.sleep(1)
    m.wait_heartbeat(timeout=60)
    ts, tc = m.target_system, m.target_component

    def pset(name, value):
        m.mav.param_set_send(ts, tc, name.encode(), float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
        time.sleep(0.05)

    params = dict(SIM_WIND_SPD=a.wind, SIM_WIND_DIR=a.wind_dir, SIM_WIND_TURB=a.turb, ARMING_CHECK=0)
    if a.vehicle == "plane":
        params.update(AIRSPEED_CRUISE=a.speed, TRIM_ARSPD_CM=a.speed * 100, ROLL_LIMIT_DEG=45,
                      TKOFF_THR_MINACC=0, RTL_AUTOLAND=0)
    else:
        params.update(WPNAV_SPEED=a.speed * 100, WPNAV_SPEED_UP=600, WPNAV_ACCEL=250, AUTO_OPTIONS=3, ANGLE_MAX=3500)
    for k, v in params.items():
        pset(k, v)
    for msgid in (mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE, mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT):
        m.mav.command_long_send(ts, tc, mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, msgid, 20000, 0, 0, 0, 0, 0)

    # mission: home, takeoff, circuit
    rel = mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
    items = [(mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, home[0], home[1], 0.0, (0, 0, 0, 0))]
    if a.vehicle == "plane":
        items.append((mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, home[0], home[1], 80.0, (15, 0, 0, 0)))
        c = geo.to_latlon(0.0, 0.0)
        items.append((mavutil.mavlink.MAV_CMD_NAV_LOITER_TURNS, c[0], c[1], a.height, (50, 0, -a.radius, 1)))
    else:
        items.append((mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, home[0], home[1], a.height, (0, 0, 0, 0)))
        for k in range(36):
            th = 2 * math.pi * k / 36
            p = geo.to_latlon(a.radius * math.cos(th), a.radius * math.sin(th))
            items.append((mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, p[0], p[1], a.height, (0, 0, 0, 0)))
        items.append((mavutil.mavlink.MAV_CMD_DO_JUMP, 0, 0, 0, (3, 50, 0, 0)))
    m.mav.mission_count_send(ts, tc, len(items))
    sent = set()
    t_end = time.time() + 60
    while len(sent) < len(items) and time.time() < t_end:
        r = m.recv_match(type=["MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"], blocking=True, timeout=5)
        if r is None:
            continue
        if r.get_type() == "MISSION_ACK":
            break
        cmd, lat, lon, alt, (p1, p2, p3, p4) = items[r.seq]
        m.mav.mission_item_int_send(ts, tc, r.seq, rel, cmd, 0, 1, p1, p2, p3, p4,
                                    int(lat * 1e7), int(lon * 1e7), alt)
        sent.add(r.seq)
    print(f"mission: {len(items)} items uploaded", flush=True)

    # wait for a 3-D fix and the EKF, then AUTO + arm
    t0 = time.time()
    while time.time() - t0 < 120:
        g = m.recv_match(type="GPS_RAW_INT", blocking=True, timeout=5)
        if g is not None and g.fix_type >= 3 and time.time() - t0 > 20 / a.speedup * 4:
            break
    armed = False
    for _ in range(60):
        m.set_mode("AUTO")
        m.mav.command_long_send(ts, tc, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 21196, 0, 0, 0, 0, 0)
        hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
        if hb is not None and hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
            armed = True
            break
        time.sleep(1)
    if not armed:
        raise SystemExit("SITL did not arm (see its log)")
    print("armed, AUTO", flush=True)

    rows, pos, station_t = [], None, None
    while proc.poll() is None:
        msg = m.recv_match(type=["ATTITUDE", "GLOBAL_POSITION_INT", "STATUSTEXT"], blocking=True, timeout=10)
        if msg is None:
            continue
        typ = msg.get_type()
        if typ == "STATUSTEXT":
            print("SITL:", msg.text, flush=True)
            continue
        if typ == "GLOBAL_POSITION_INT":
            pos = msg
            continue
        if pos is None:
            continue
        t = msg.time_boot_ms / 1000.0
        lat, lon = pos.lat / 1e7, pos.lon / 1e7
        e, n = geo.to_en(lat, lon)
        rel_alt = pos.relative_alt / 1000.0
        if station_t is None and rel_alt > 0.95 * a.height and abs(math.hypot(e, n) - a.radius) < 120:
            station_t = t
            print(f"on station at t={t:.1f} s", flush=True)
        rows.append((t, lat, lon, pos.alt / 1000.0, rel_alt, pos.vx / 100.0, pos.vy / 100.0, pos.vz / 100.0,
                     math.degrees(msg.roll), math.degrees(msg.pitch), math.degrees(msg.yaw) % 360.0,
                     msg.rollspeed, -msg.pitchspeed, -msg.yawspeed))
        if station_t is not None and t - station_t > a.record:
            break
    if station_t is None:
        raise SystemExit("the vehicle never reached the circuit at height")
    with open(a.out, "w") as f:
        f.write(f"# station_t={station_t:.3f} vehicle={a.vehicle} home={home[0]:.7f},{home[1]:.7f},{home_alt:.1f} "
                f"wind={a.wind}@{a.wind_dir} turb={a.turb} speed={a.speed} radius={a.radius} height={a.height}\n")
        f.write("t,lat,lon,alt_msl,rel_alt,vn,ve,vd,roll,pitch,heading,p,q,r\n")
        last = -1.0
        for r in rows:
            if r[0] <= last:
                continue
            last = r[0]
            f.write(",".join(f"{v:.7f}" if i in (1, 2) else f"{v:.4f}" for i, v in enumerate(r)) + "\n")
    print(f"{len(rows)} samples -> {a.out}", flush=True)


if __name__ == "__main__":
    main()
