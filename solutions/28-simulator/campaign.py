#!/usr/bin/env python3
"""campaign.py — turn a fault-injection campaign into measurements and PASS / FAIL verdicts (Part C).

    python3 campaign.py                       analyse /data/academy/28-simulator/campaign/*.csv
                                              (+ your own runs in ./my_runs/ if any), print the
                                              table, write results.json
    python3 campaign.py --flight F.csv        analyse one flight only

Each flight CSV has one row per second (written by `sim_ctl.py record` / `sim_ctl.py campaign`):
    t_s, phase, gps_mode, navera_state, navera_source, navera_lat, navera_lon, [navera_err_m],
    truth_lat, truth_lon, truth_alt_m, truth_speed_mps, ap_mode, [ap_err_m], reason, [camera]
Columns in [] are missing in some flights. Empty cells mean "no value".
"""
import csv
import glob
import json
import math
import os
import sys

import numpy as np

CAMPAIGN = "/data/academy/28-simulator/campaign"
NUMBERS = ("t_s", "navera_lat", "navera_lon", "navera_err_m", "truth_lat", "truth_lon",
           "truth_alt_m", "truth_speed_mps", "ap_err_m")
POSITION_STATES = ("FIX", "DEGRADED")
SPOOF_LIMIT_M = 100.0         # a GPS used by NAVERA with an error above this = spoof leakage
R_EARTH = 6371000.0


def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres (lesson 06)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def load_flight(path):
    """Rows as dicts: NUMBERS columns as float (None when empty or missing), the other columns
    as text; a missing 'camera' column means 'ok'."""
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            for k in NUMBERS:
                v = r.get(k)
                r[k] = float(v) if v not in (None, "") else None
            r["camera"] = r.get("camera") or "ok"
            rows.append(r)
    return rows


def nav_error(r):
    """NAVERA's horizontal error in this row (m), from the coordinates; None if a position is missing."""
    if None in (r["navera_lat"], r["navera_lon"], r["truth_lat"], r["truth_lon"]):
        return None
    return haversine_m(r["navera_lat"], r["navera_lon"], r["truth_lat"], r["truth_lon"])


def fault_intervals(rows, column, normal="ok"):
    """[(t_start, t_end, value), ...] for every run of rows where row[column] != normal.
    t_end is the t_s of the first row back to normal (or of the last row if it never comes back)."""
    out = []
    start, value = None, None
    for r in rows:
        v = r[column]
        if start is None and v != normal:
            start, value = r["t_s"], v
        elif start is not None and v != value:
            out.append((start, r["t_s"], value))
            start, value = (r["t_s"], v) if v != normal else (None, None)
    if start is not None:
        out.append((start, rows[-1]["t_s"], value))
    return out


def first_time(rows, condition, after):
    """t_s of the first row with t_s >= after for which condition(row) is True, or None."""
    for r in rows:
        if r["t_s"] >= after and condition(r):
            return r["t_s"]
    return None


def switch_latency(rows, t0):
    """Seconds from t0 to the first row where NAVERA's source is not GPS. None if never."""
    t = first_time(rows, lambda r: r["navera_source"] != "GPS", t0)
    return None if t is None else t - t0


def recovery_latency(rows, t1):
    """Seconds from t1 to the first row where NAVERA uses GPS again. None if never."""
    t = first_time(rows, lambda r: r["navera_source"] == "GPS", t1)
    return None if t is None else t - t1


def availability(rows, t0, t1):
    """Fraction of the rows with t0 <= t_s < t1 that have a NAVERA position (state FIX or DEGRADED
    and a latitude). None if there is no such row."""
    sel = [r for r in rows if t0 <= r["t_s"] < t1]
    if not sel:
        return None
    ok = sum(1 for r in sel if r["navera_state"] in POSITION_STATES and r["navera_lat"] is not None)
    return ok / len(sel)


def error_stats(rows, t0, t1):
    """(median, 95th percentile, max) of nav_error over rows with t0 <= t_s < t1 (None values skipped),
    with numpy's default (linear) percentile. (None, None, None) if no error."""
    e = [x for x in (nav_error(r) for r in rows if t0 <= r["t_s"] < t1) if x is not None]
    if not e:
        return None, None, None
    return float(np.percentile(e, 50)), float(np.percentile(e, 95)), float(max(e))


def spoof_leak_s(rows, t0, t1, limit=SPOOF_LIMIT_M):
    """Seconds (= rows) with t0 <= t_s < t1 where NAVERA used GPS while its error exceeded `limit`."""
    n = 0
    for r in rows:
        if t0 <= r["t_s"] < t1 and r["navera_source"] == "GPS":
            e = nav_error(r)
            if e is not None and e > limit:
                n += 1
    return n


def gps_err_max(rows, t0, t1):
    """Largest nav_error among rows with t0 <= t_s < t1 where NAVERA's source is GPS (None if none):
    how far a spoofed GPS dragged NAVERA before it was refused."""
    e = [nav_error(r) for r in rows if t0 <= r["t_s"] < t1 and r["navera_source"] == "GPS"]
    e = [x for x in e if x is not None]
    return max(e) if e else None


def autopilot_modes(rows, t0, t1):
    """Sorted list of the distinct ap_mode values in rows with t0 <= t_s < t1 (empty / '—' skipped)."""
    return sorted({r["ap_mode"] for r in rows if t0 <= r["t_s"] < t1 and r["ap_mode"] not in ("", "—")})


# The requirements of the campaign: (id, applies to fault, text, measured key, test)
REQUIREMENTS = [
    ("R1", "jammed", "NAVERA leaves a jammed GPS within 1 s", "switch_s", lambda v: v is not None and v <= 1.0),
    ("R2", "off", "NAVERA leaves a silent GPS within 4 s (3 s timeout + 1 s)", "switch_s",
     lambda v: v is not None and v <= 4.0),
    ("R3", "*gps", "NAVERA uses GPS again within 5 s after it is good again", "recovery_s",
     lambda v: v is not None and v <= 5.0),
    ("R4", "*gps+camera", "a position is available >= 95 % of the time while the camera works", "availability",
     lambda v: v is not None and v >= 0.95),
    ("R5", "*spoof", "no second with NAVERA on a GPS more than 100 m wrong", "spoof_leak_s", lambda v: v == 0),
    ("R6", "failed", "camera lost while GPS is down: NO FIX within 6 s and the autopilot fails safe (LAND)",
     "nofix_s", None),
    ("R7", "spoof_drift", "a slow GPS drift is refused before it drags NAVERA 150 m away", "gps_err_max_m",
     lambda v: v is not None and v <= 150.0),
]


# ---- you don't need to change anything below this line (but you can read it!) ----

def analyse_flight(rows):
    """One dict per injected fault (GPS faults first, then camera faults)."""
    cam = fault_intervals(rows, "camera")
    out = []
    for t0, t1, kind in fault_intervals(rows, "gps_mode"):
        p50, p95, mx = error_stats(rows, t0, t1)
        out.append(dict(column="gps_mode", fault=kind, t0=t0, t1=t1, duration_s=round(t1 - t0, 1),
                        camera_ok=not any(c0 < t1 and c1 > t0 for c0, c1, _ in cam),
                        switch_s=_r(switch_latency(rows, t0)), recovery_s=_r(recovery_latency(rows, t1)),
                        availability=_r(availability(rows, t0, t1), 3),
                        err_p50_m=_r(p50), err_p95_m=_r(p95), err_max_m=_r(mx),
                        spoof_leak_s=spoof_leak_s(rows, t0, t1), gps_err_max_m=_r(gps_err_max(rows, t0, t1)),
                        ap_err_max_m=_r(_ap_err_max(rows, t0, t1 + 10.0)),
                        ap_modes=autopilot_modes(rows, t0, t1 + 10.0)))
    for t0, t1, kind in cam:
        t_nofix = first_time(rows, lambda r: r["navera_state"] == "NO FIX", t0)
        out.append(dict(column="camera", fault=kind, t0=t0, t1=t1, duration_s=round(t1 - t0, 1),
                        availability=_r(availability(rows, t0, t1), 3),
                        nofix_s=_r(None if t_nofix is None or t_nofix >= t1 else t_nofix - t0),
                        ap_modes=autopilot_modes(rows, t0, t1 + 10.0)))
    return out


def verdicts(fault):
    """[(req_id, text, measured, 'PASS' | 'FAIL')] for the requirements that apply to this fault."""
    out = []
    for rid, applies, text, key, test in REQUIREMENTS:
        k = fault["fault"]
        ok_scope = (applies == k or (applies == "*gps" and fault["column"] == "gps_mode")
                    or (applies == "*gps+camera" and fault["column"] == "gps_mode" and fault.get("camera_ok"))
                    or (applies == "*spoof" and k.startswith("spoof")))
        if not ok_scope:
            continue
        v = fault.get(key)
        if rid == "R6":
            passed = v is not None and v <= 6.0 and "LAND" in fault["ap_modes"]
        else:
            passed = test(v)
        out.append((rid, text, v, "PASS" if passed else "FAIL"))
    return out


def _ap_err_max(rows, t0, t1):
    e = [r["ap_err_m"] for r in rows if t0 <= r["t_s"] < t1 and r["ap_err_m"] is not None]
    return max(e) if e else None


def _r(v, nd=1):
    return None if v is None else round(float(v), nd)


def flights():
    paths = sorted(glob.glob(os.path.join(CAMPAIGN, "*.csv"))) + sorted(glob.glob("my_runs/*.csv"))
    return {("my_runs/" if p.startswith("my_runs") else "") + os.path.basename(p)[:-4]: p for p in paths}


def campaign_results():
    res = {}
    n_pass = n_fail = 0
    for name, path in flights().items():
        rows = load_flight(path)
        faults = analyse_flight(rows) or []
        for f in faults:
            f["verdicts"] = [list(v) for v in (verdicts(f) or [])]
            n_pass += sum(1 for v in f["verdicts"] if v[3] == "PASS")
            n_fail += sum(1 for v in f["verdicts"] if v[3] == "FAIL")
        res[name] = faults
    return res, n_pass, n_fail


def print_table(res):
    print(f"{'flight':22s} {'fault':12s} {'t0':>6s} {'dur':>5s} {'switch':>6s} {'recov':>6s} {'avail':>6s} "
          f"{'p50':>6s} {'p95':>6s} {'leak':>4s}  autopilot")
    for name, faults in res.items():
        for f in faults:
            g = lambda k: "—" if f.get(k) is None else f"{f[k]:g}"      # noqa: E731
            print(f"{name:22s} {f['fault']:12s} {f['t0']:6.1f} {f['duration_s']:5.0f} {g('switch_s'):>6s} "
                  f"{g('recovery_s'):>6s} {g('availability'):>6s} {g('err_p50_m'):>6s} {g('err_p95_m'):>6s} "
                  f"{g('spoof_leak_s'):>4s}  {','.join(f['ap_modes'])}")
            for rid, text, v, verdict in f.get("verdicts", []):
                print(f"{'':22s}   {verdict:4s} {rid} {text} (measured: {v})")


def main():
    if "--flight" in sys.argv:
        rows = load_flight(sys.argv[sys.argv.index("--flight") + 1])
        for f in analyse_flight(rows) or []:
            print(f)
        return
    res, n_pass, n_fail = campaign_results()
    print_table(res)
    out = {"campaign": res, "requirements_pass": n_pass, "requirements_fail": n_fail}
    try:
        import mavlink_lab
        with open(mavlink_lab.STREAM, "rb") as f:
            out["mavlink"] = mavlink_lab.summarize(mavlink_lab.parse_frames(f.read()))
    except Exception as e:
        print("(mavlink part not ready:", e, ")")
    try:
        import sensor_models
        out["models"] = sensor_models.model_results()
    except Exception as e:
        print("(models part not ready:", e, ")")
    with open("results.json", "w") as f:
        json.dump(out, f, indent=1)
    print(f"\n{n_pass} PASS, {n_fail} FAIL — saved results.json")


if __name__ == "__main__":
    main()
