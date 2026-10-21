#!/usr/bin/env python3
"""F7 in ArduPilot SITL: can NAVERA's vision position ever corrupt the vehicle's height?

Not part of run_tests.sh (needs an ArduPilot build, about 4 min per run). Usage, from the
workspace root:

    nice -n 19 python3 navera_tools/tests/sitl_f7_height.py [--vehicle copter|plane|rover]
                       [--ardupilot ~/ardupilot] [--runs recommended,posz_gps] [--keep] [--instance N]

ArduCopter (or ArduPlane / Rover, --vehicle) SITL runs with no simulated GPS (SIM_GPS_DISABLE 1)
and NAVERA's recommended parameters (docs/ARDUPILOT_INTEGRATION.md §3: GPS_TYPE 14, EK3_SRC1_VELXY 0, EK3_SRC1_VELZ 0,
EK3_SRC1_POSZ 1 = barometer). This script plays NAVERA: it builds every GPS_INPUT with
navera_output.mavlink_out.gps_input_fields(), exactly as vehicle_output_node sends it, from the
simulator's true position (SIM_STATE) plus noise:

    gps        KIND_FIX, true altitude: origin, arming, take-off and hover (Copter: 40 m, GUIDED;
               Plane: AUTO take-off then loiter at 60 m; Rover: armed, standing in HOLD)
    vision     KIND_ESTIMATED (GPS off, 0 satellites, ±15 m), exactly as sent: no altitude,
               IGNORE_ALT set
    garbage_z  as vision, but the (ignored) alt field on the wire = truth + 5000 m
    The next phases inject on the wire what mavlink_out never sends for vision (a height
    with IGNORE_ALT cleared), i.e. the worst case: a wrong height that reaches the
    autopilot anyway (a NAVERA bug, or a spoofed GNSS height passed through):
    wrong_z    altitude 200 m below the truth
    jumps      altitude jumping truth ±300 m every 2 s
    drift      slow spoof: position and altitude both pulled 90 m (1 m/s), north and up
    hold       drift held at 90 m

The second run (posz_gps) is identical with EK3_SRC1_POSZ 3 (GPS height), the setting the
docs forbid, to prove the check is sensitive. Since F28 NAVERA states a vision velocity
accuracy (> 1.5 m/s: "unknown" 30 m/s here), and EKF3 then stops using the GPS height by
itself (gpsAccuracyGoodForAltitude false; SITL 2026-10-21: posz_gps stayed on the barometer):
the control run therefore sends the pre-F28 velocity fields (flagged ignored) to stay
sensitive. The dataflash log (XKF1 PD, BARO Alt, SIM Alt, GPS Alt, XKF3 IPD, XKF4 SH) is
analysed per phase. Exit code 0 = the recommended run keeps
height on the barometer, its horizontal position follows the vision spoof, and the posz_gps
run's height does not follow the barometer.
"""
import argparse
import glob
import json
import math
import os
import random
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone

from pymavlink import mavutil
from pymavlink.DFReader import DFReader_binary

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sitl_vehicles as sv                                                # noqa: E402

WS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for _pkg in ("navera_output", "navera_common"):
    sys.path.insert(0, os.path.join(WS, _pkg))
from navera_output import mavlink_out                                    # noqa: E402
from navera_output.policy import KIND_ESTIMATED, KIND_FIX, Config, Output  # noqa: E402

HOME = sv.HOME                               # lat, lon, ground altitude AMSL (m)
TAKEOFF_M = {"copter": 40.0, "plane": 60.0, "rover": 0.0}
RATE_HZ = 5.0
VISION_SIGMA_M = 15.0                        # stated accuracy (NAVERA target)
VISION_NOISE_M = 3.0                         # actual noise added to the truth

NAVERA_PARAMS = sv.NAVERA_PARAMS             # docs/ARDUPILOT_INTEGRATION.md §3
VEHICLE_PARAMS = {
    "copter": {"FS_EKF_ACTION": 0},          # observe the estimate, do not land on it
    "plane": {"TKOFF_ALT": 50},
    "rover": {},
}
RUNS = {"recommended": {}, "posz_gps": {"EK3_SRC1_POSZ": 3}}

# (name, seconds) after take-off; the GPS_INPUT for each is built in vision_output()
PHASES = [("vision", 20), ("garbage_z", 10), ("wrong_z", 15), ("jumps", 16), ("drift", 90), ("hold", 10)]
DRIFT_MPS = 1.0
DRIFT_MAX_M = 90.0


def offset_ll(lat, lon, dn, de):
    return lat + dn / 111319.5, lon + de / (111319.5 * math.cos(math.radians(lat)))


class Navera(sv.Link):
    """The GPS_INPUT stream, built with navera_output.mavlink_out from the simulator's truth."""

    def __init__(self, port, seed=7):
        super().__init__(port)
        self.rng = random.Random(seed)
        self.last_send = 0.0

    def tick(self, make):
        """Pump messages; send the GPS_INPUT fields make(*truth) at RATE_HZ."""
        self.pump(0.05)
        if self.truth is not None and time.time() - self.last_send >= 1.0 / RATE_HZ:
            self.mav.mav.gps_input_send(**make(*self.truth))
            self.last_send = time.time()


def gps_output(lat, lon, alt):
    """NAVERA passing a healthy GPS through (KIND_FIX, true altitude)."""
    out = Output(KIND_FIX, "fix", lat=lat, lon=lon, alt_ellipsoid_m=alt, geoid_sep_m=0.0,
                 sigma_h_m=1.0, sigma_v_m=2.0, satellites=12, gnss=True)
    return mavlink_out.gps_input_fields(out, datetime.now(timezone.utc))


def vision_output(rng, phase, t, lat, lon, alt, legacy_vel=False):
    """What reaches the autopilot in `phase`, t s into it: (GPS_INPUT fields, Output)."""
    lat, lon = offset_ll(lat, lon, rng.gauss(0, VISION_NOISE_M), rng.gauss(0, VISION_NOISE_M))
    wire_z = None                            # None: as mavlink_out built it
    if phase in ("drift", "hold"):
        d = min(DRIFT_MAX_M, DRIFT_MPS * t) if phase == "drift" else DRIFT_MAX_M
        lat, lon = offset_ll(lat, lon, d, 0.0)
        wire_z = alt + d
    elif phase == "wrong_z":
        wire_z = alt - 200.0
    elif phase == "jumps":
        wire_z = alt + (300.0 if int(t // 2) % 2 == 0 else -300.0)
    # the vision position as NAVERA's policy builds it (KIND_ESTIMATED, non-GNSS, 0 sats);
    # a producer-attached height is included to show mavlink_out drops it
    out = Output(KIND_ESTIMATED, "estimated", lat=lat, lon=lon,
                 alt_ellipsoid_m=wire_z if wire_z is not None else alt, geoid_sep_m=0.0,
                 sigma_h_m=VISION_SIGMA_M, satellites=0, gnss=False,
                 vel_sigma_mps=Config.max_speed_mps)        # horizontal velocity stated (unknown), never vertical
    f = mavlink_out.gps_input_fields(out, datetime.now(timezone.utc))
    assert f["ignore_flags"] & mavlink_out.IGNORE_ALT and f["alt"] == 0.0, "vision height sent"
    assert f["ignore_flags"] & mavlink_out.IGNORE_VEL_VERT, "vertical velocity sent"
    if legacy_vel:                           # the control run: velocity flagged ignored (pre-F28)
        f.update(vn=0.0, ve=0.0, speed_accuracy=0.0)
        f["ignore_flags"] |= mavlink_out.IGNORE_VEL_HORIZ | mavlink_out.IGNORE_SPEED_ACCURACY
    if phase == "garbage_z":
        f["alt"] = alt + 5000.0              # flag still set
    elif wire_z is not None:                 # injected: height presented as valid
        f["alt"] = float(wire_z)
        f["ignore_flags"] &= ~mavlink_out.IGNORE_ALT
    return f


def get_moving(vehicle, nav, mav, gps, run_until, name):
    """Arm on the passed-through GPS and reach the hover / loiter height (Rover: stand still)."""
    if vehicle == "plane":
        lat, lon = offset_ll(HOME[0], HOME[1], 400.0, 0.0)
        items = [sv.mission_item(0, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, HOME[0], HOME[1], 0),
                 sv.mission_item(1, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, HOME[0], HOME[1], 50.0, p1=15.0),
                 sv.mission_item(2, mavutil.mavlink.MAV_CMD_NAV_LOITER_UNLIM, lat, lon, TAKEOFF_M["plane"])]
        sv.upload_mission(nav, items, lambda: nav.tick(gps))
    mode = {"copter": "GUIDED", "plane": "AUTO", "rover": "HOLD"}[vehicle]
    nav.set_mode(vehicle, mode)
    end = time.time() + 90
    while not nav.armed():                     # pre-arm checks pass a few s after the origin
        if time.time() > end:
            raise RuntimeError(f"{name}: could not arm")
        nav.set_mode(vehicle, mode)
        nav.arm()
        t_try = time.time() + 3
        while time.time() < t_try:
            nav.tick(gps)
    if vehicle == "copter":
        nav.command(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, TAKEOFF_M["copter"])
    if vehicle != "rover":
        margin = 2.0 if vehicle == "copter" else 10.0      # Plane: take-off ends at 50 m, then climbs
        run_until(gps, lambda: nav.truth and nav.truth[2] - HOME[2] > TAKEOFF_M[vehicle] - margin,
                  120, "take-off")
    end = time.time() + (25 if vehicle == "plane" else 8)
    while time.time() < end:
        nav.tick(gps)


def fly(vehicle, name, extra, ardupilot, work, instance=0):
    """One SITL run. Returns (dataflash log path, {phase: (start_ms, end_ms)})."""
    params = dict(NAVERA_PARAMS, **VEHICLE_PARAMS[vehicle], **extra)
    sitl, port = sv.start_sitl(vehicle, ardupilot, work, params, instance=instance)
    phases = {}
    try:
        time.sleep(4)
        nav = Navera(port)
        mav = nav.mav
        nav.request({mavutil.mavlink.MAVLINK_MSG_ID_SIM_STATE: 10,
                     mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT: 5,
                     mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE: 10})
        gps = gps_output

        def run_until(make, cond, timeout, what):
            end = time.time() + timeout
            while time.time() < end:
                nav.tick(make)
                if cond():
                    return
            raise RuntimeError(f"{name}: timed out waiting for {what}")

        t0 = nav.boot_ms
        run_until(gps, lambda: any("origin set" in t for _, t in nav.texts), 90, "EKF origin from GPS")
        phases["gps"] = [t0 or nav.boot_ms, None]
        get_moving(vehicle, nav, mav, gps, run_until, name)
        phases["gps"][1] = nav.boot_ms
        for ph, dur in PHASES:
            print(f"  [{vehicle} {name}] phase {ph} ({dur} s)")
            phases[ph] = [nav.boot_ms, None]
            p0 = time.time()
            end = p0 + dur
            while time.time() < end:
                nav.tick(lambda la, lo, al: vision_output(nav.rng, ph, time.time() - p0, la, lo, al,
                                                          legacy_vel=name == "posz_gps"))
            phases[ph][1] = nav.boot_ms
        mav.close()
    finally:
        sv.stop(sitl)
    logs = sorted(glob.glob(os.path.join(work, "logs", "*.BIN")), key=os.path.getmtime)
    if not logs:
        raise RuntimeError(f"{name}: no dataflash log in {work}/logs")
    return logs[-1], phases


def ned_from(lat0, lon0, lat, lon):
    return ((lat - lat0) * 111319.5, (lon - lon0) * 111319.5 * math.cos(math.radians(lat0)))


def analyse(log, phases):
    """Per phase: EKF height vs barometer and vs truth, what GPS altitude ArduPilot received,
    height innovation / test ratio, and EKF horizontal position minus truth."""
    rows = {k: [] for k in ("XKF1", "BARO", "SIM", "GPS", "XKF3", "XKF4", "ORGN")}
    df = DFReader_binary(log, zero_time_base=True)
    while True:
        m = df.recv_match(type=list(rows))
        if m is None:
            break
        t = m.get_type()
        if t in ("XKF1", "XKF3", "XKF4") and m.C != 0:
            continue
        if t == "BARO" and m.I != 0:
            continue
        if t == "GPS" and getattr(m, "I", 0) != 0:
            continue
        rows[t].append(m)
    org = next((m for m in rows["ORGN"] if m.Type == 0), None)
    if org is None:
        raise RuntimeError("no EKF origin (ORGN) in the log")
    lat0, lon0 = org.Lat, org.Lng

    def near(series, tus):
        lo, hi = 0, len(series) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if series[mid].TimeUS < tus:
                lo = mid + 1
            else:
                hi = mid
        return series[lo]

    baro0 = None
    res = {}
    for ph, (a, b) in phases.items():
        a_us, b_us = a * 1000, b * 1000
        k1 = [m for m in rows["XKF1"] if a_us <= m.TimeUS <= b_us]
        if not k1:
            continue
        dz_baro, dz_true, dn, de = [], [], [], []
        for m in k1[::5]:
            br, sm = near(rows["BARO"], m.TimeUS), near(rows["SIM"], m.TimeUS)
            if baro0 is None:
                baro0 = br.Alt + m.PD                  # baro reading at EKF height 0
            ekf_h = -m.PD
            dz_baro.append(ekf_h - (br.Alt - baro0))
            dz_true.append(ekf_h - (sm.Alt - org.Alt))
            tn, te = ned_from(lat0, lon0, sm.Lat, sm.Lng)
            dn.append(m.PN - tn)
            de.append(m.PE - te)
        gps = [m.Alt for m in rows["GPS"] if a_us <= m.TimeUS <= b_us and m.Status >= 3]
        x3 = [m.IPD for m in rows["XKF3"] if a_us <= m.TimeUS <= b_us]
        x4 = [m.SH for m in rows["XKF4"] if a_us <= m.TimeUS <= b_us]
        last = k1[-1]
        sm = near(rows["SIM"], last.TimeUS)
        res[ph] = dict(
            ekf_minus_baro_max=max(abs(x) for x in dz_baro),
            ekf_minus_truth_max=max(abs(x) for x in dz_true),
            ekf_height_end=-last.PD, true_height_end=sm.Alt - org.Alt,
            gps_alt_received=(min(gps) - org.Alt, max(gps) - org.Alt) if gps else None,
            ipd_max=max(abs(x) for x in x3) if x3 else None,
            sh_max=max(x4) if x4 else None,
            horiz_err_n_end=dn[-1], horiz_err_e_end=de[-1],
            horiz_err_max=max(math.hypot(x, y) for x, y in zip(dn, de)))
    return res


def report(name, res):
    print(f"\n== {name} ==  (heights relative to the EKF origin, m)")
    print(f"{'phase':10} {'|EKF-baro|max':>13} {'|EKF-true|max':>13} {'EKF h end':>9} {'true h end':>10} "
          f"{'GPS alt rcvd':>17} {'|IPD|max':>8} {'SH max':>6} {'EKF-true N end':>14} {'horiz err max':>13}")
    for ph, r in res.items():
        g = r["gps_alt_received"]
        g = f"{g[0]:+7.0f}..{g[1]:+7.0f}" if g else "-"
        print(f"{ph:10} {r['ekf_minus_baro_max']:13.1f} {r['ekf_minus_truth_max']:13.1f} "
              f"{r['ekf_height_end']:9.1f} {r['true_height_end']:10.1f} {g:>17} "
              f"{(r['ipd_max'] or 0):8.1f} {(r['sh_max'] or 0):6.2f} {r['horiz_err_n_end']:14.1f} "
              f"{r['horiz_err_max']:13.1f}")


def verdict(results):
    fails = []
    rec = results.get("recommended")
    if rec:
        vis = [p for p in rec if p != "gps"]
        worst = max(rec[p]["ekf_minus_baro_max"] for p in vis)
        if worst > 3.0:
            fails.append(f"recommended: EKF height left the barometer by {worst:.1f} m")
        worst_t = max(rec[p]["ekf_minus_truth_max"] for p in vis)
        if worst_t > 5.0:
            fails.append(f"recommended: EKF height off the truth by {worst_t:.1f} m")
        if "hold" in rec and rec["hold"]["horiz_err_n_end"] < 0.7 * DRIFT_MAX_M:
            fails.append("recommended: horizontal position did not follow the vision spoof "
                         f"({rec['hold']['horiz_err_n_end']:.0f} m of {DRIFT_MAX_M:.0f} m)")
    pz = results.get("posz_gps")
    if pz:
        worst = max(pz[p]["ekf_minus_baro_max"] for p in pz if p != "gps")
        if worst < 20.0:
            fails.append(f"posz_gps: height stayed on the barometer ({worst:.1f} m): test not sensitive")
    return fails


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vehicle", choices=sorted(sv.VEHICLES), default="copter")
    ap.add_argument("--instance", type=int, default=0, help="SITL instance (TCP port 5760 + 10 N)")
    ap.add_argument("--ardupilot", default="~/ardupilot")
    ap.add_argument("--runs", default="recommended,posz_gps")
    ap.add_argument("--keep", action="store_true", help="keep the logs even on PASS")
    ap.add_argument("--analyse", nargs=2, metavar=("LOG", "PHASES_JSON"), help="only analyse a kept run")
    a = ap.parse_args()
    results = {}
    if a.analyse:
        with open(a.analyse[1]) as f:
            ph = json.load(f)
        name = os.path.basename(os.path.dirname(os.path.dirname(a.analyse[0]))) or "run"
        results[name] = analyse(a.analyse[0], ph)
        report(name, results[name])
        return 0
    ardupilot = os.path.expanduser(a.ardupilot)
    out = tempfile.mkdtemp(prefix=f"navera_f7_{a.vehicle}_")
    for name in a.runs.split(","):
        work = os.path.join(out, name)
        print(f"[{name}] SITL in {work}")
        log, phases = fly(a.vehicle, name, RUNS[name], ardupilot, work, a.instance)
        with open(os.path.join(work, "phases.json"), "w") as f:
            json.dump(phases, f)
        results[name] = analyse(log, phases)
        report(name, results[name])
    with open(os.path.join(out, "results.json"), "w") as f:
        json.dump(results, f, indent=1)
    fails = verdict(results)
    for f in fails:
        print("FAIL", f)
    print(f"sitl_f7_height ({a.vehicle}):", "PASS" if not fails else f"{len(fails)} failure(s)", f"(logs: {out})")
    if not fails and not a.keep:
        shutil.rmtree(out, ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
