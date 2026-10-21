#!/usr/bin/env python3
"""Headless fault campaign on the NAVERA mission simulator (ArduPilot SITL in the loop).

Drives a RUNNING simulator (navera_tools/run_sim.sh, control server on :8190) over its
JSON API only: no browser, no ROS. For every scenario it starts a drone mission on a
prepared map area, injects faults at fixed times after the drone reaches cruise, and
samples the state at ~1 Hz into a CSV (truth vs. NAVERA output vs. autopilot belief).
Truth is the simulator's SIM_STATE (never the autopilot's own estimate).

    python3 navera_tools/tests/sitl_fault_campaign.py --list
    python3 navera_tools/tests/sitl_fault_campaign.py --out DIR S1_gps_cut_default S2_gps_cut_fwd
    python3 navera_tools/tests/sitl_fault_campaign.py --out DIR all

Per scenario: DIR/<name>.csv, DIR/<name>_events.json, and one line in DIR/summary.json.
SIMULATED data only. Run it on a test machine; never on a box installed on a vehicle.
"""
import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
import urllib.request

API = os.environ.get("NAVERA_SIM_API", "http://127.0.0.1:8190/api")

# A route whose map area was prepared beforehand (areas are keyed by the exact route).
# ~7.4 km, 8 min at 15 m/s.
ROUTE_START = [35.852048261234444, 10.572280883789064]
ROUTE_DEST = [35.82365922190618, 10.647811889648438]
SPEED = 15.0
ALT = 150.0
# seconds after "enroute" at which a scenario is stopped, whatever happens
MAX_AFTER_CRUISE_S = 560

# (time after cruise start in s, fault dict) lists. mission = extra keys for the mission request.
SCENARIOS = {
    "S1_gps_cut_default": dict(
        desc="GPS cut at +60 s, default settings (forward_degraded off) - F2",
        mission={}, faults=[(60, {"gps": "jammed"})]),
    "S2_gps_cut_forward_degraded": dict(
        desc="GPS cut at +60 s, forward_degraded on - F1",
        mission={"forward_degraded": True}, faults=[(60, {"gps": "jammed"})]),
    "S3_camera_dies_gps_ok": dict(
        desc="camera fails at +60 s, GPS healthy all along",
        mission={}, faults=[(60, {"camera": "failed"})]),
    "S4_camera_dies_recovers_gps_ok": dict(
        desc="camera fails at +60 s, recovers at +150 s, GPS healthy all along",
        mission={}, faults=[(60, {"camera": "failed"}), (150, {"camera": "ok"})]),
    "S4b_gps_cut_camera_dies_recovers": dict(
        desc="GPS cut at +60 s (forward_degraded on), camera fails +120 s, recovers +210 s",
        mission={"forward_degraded": True},
        faults=[(60, {"gps": "jammed"}), (120, {"camera": "failed"}), (210, {"camera": "ok"})]),
    "S5_imu_fault_gps_ok": dict(
        desc="IMU fails at +60 s, GPS healthy all along",
        mission={}, faults=[(60, {"imu": "failed"})]),
    "S5b_gps_cut_imu_fault": dict(
        desc="GPS cut at +60 s (forward_degraded on), IMU fails at +120 s",
        mission={"forward_degraded": True},
        faults=[(60, {"gps": "jammed"}), (120, {"imu": "failed"})]),
    "S6_gps_back_forward_degraded": dict(
        desc="GPS cut at +60 s (forward_degraded on), GPS back at +150 s: clean hand-over?",
        mission={"forward_degraded": True},
        faults=[(60, {"gps": "jammed"}), (150, {"gps": "ok"})]),
    "S6b_gps_back_default": dict(
        desc="GPS cut at +60 s (default settings), GPS back at +150 s",
        mission={}, faults=[(60, {"gps": "jammed"}), (150, {"gps": "ok"})]),
    # --- added for the degraded-forwarding fixes (2026-10-15) ---
    "S2c_gps_cut_forward_sigma50": dict(
        desc="as S2 with the declared accuracy at 50 m instead of the simulator's 500 m floor",
        mission={"forward_degraded": True, "degraded_sigma_m": 50.0}, faults=[(60, {"gps": "jammed"})]),
    "S8_gap_stall_6s": dict(
        desc="GPS cut at +60 s (forward_degraded on); the day pipeline is frozen 6 s at +85 s (a NO FIX gap like "
             "the 5 s one of S6; synthetic: SIGSTOP/SIGCONT of the day node)",
        mission={"forward_degraded": True}, faults=[(60, {"gps": "jammed"}), (85, {"stall_day_s": 6})],
        max_s=190),
    "S9_gap_stall_15s": dict(
        desc="as S8 with a 15 s freeze: longer than a bridge may honestly be",
        mission={"forward_degraded": True}, faults=[(60, {"gps": "jammed"}), (85, {"stall_day_s": 15})],
        max_s=190),
    "S10_gap_stall_10s": dict(
        desc="as S8 with a 10 s freeze: the longest gap the bridge covers",
        mission={"forward_degraded": True}, faults=[(60, {"gps": "jammed"}), (85, {"stall_day_s": 10})],
        max_s=190),
    # --- closed loop with the real day pipeline, same stated accuracy as sitl_closed_loop.py (2026-10-21) ---
    "S11_gps_cut_forward_sigma30": dict(
        desc="GPS cut at +60 s, forward_degraded on, declared accuracy 30 m (the 30 m floor, as the error-model "
             "runs of sitl_closed_loop.py)",
        mission={"forward_degraded": True, "degraded_sigma_m": 30.0}, faults=[(60, {"gps": "jammed"})]),
}
ORDER = list(SCENARIOS)


def get(path, timeout=10):
    with urllib.request.urlopen(f"{API}/{path}", timeout=timeout) as r:
        return json.load(r)


def post(action, body, timeout=20):
    req = urllib.request.Request(f"{API}/{action}", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:           # the server answers 400/500 with a JSON body
        return json.loads(e.read() or b"{}")


def stall_day(seconds):
    """Freeze the day localizer for `seconds` (SIGSTOP / SIGCONT of its python process): its
    estimate goes stale and the arbiter says NO FIX, like a pipeline that stops answering."""
    import signal
    import subprocess
    import threading
    pids = [int(p) for p in subprocess.run(["pgrep", "-f", "lib/day_pkg/day_subscriber.py"], capture_output=True,
                                           text=True).stdout.split()]
    for p in pids:
        os.kill(p, signal.SIGSTOP)
    for p in pids:
        threading.Timer(seconds, lambda p=p: os.kill(p, signal.SIGCONT)).start()
    return {"stalled_pids": pids, "seconds": seconds}


def state():
    for _ in range(5):
        try:
            return get("state")
        except Exception:                          # noqa: BLE001
            time.sleep(1.0)
    return None


def hav(a, b):
    r = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


COLS = ["t_s", "wall", "phase", "ap_mode", "armed", "ekf_ok", "gps_fault", "cam_fault", "imu_fault",
        "truth_lat", "truth_lon", "truth_alt", "truth_speed",
        "nav_state", "nav_source", "nav_fresh", "nav_lat", "nav_lon", "nav_err_m",
        "ap_belief_err_m", "ap_fix_type", "ap_sats", "dist_to_dest_m"]


def row_from(d, t_s):
    tr, n, ap, f = d.get("truth"), d.get("navera") or {}, d.get("autopilot") or {}, d.get("faults") or {}
    return dict(
        t_s=round(t_s, 1), wall=round(time.time(), 1), phase=d.get("phase"), ap_mode=ap.get("mode"),
        armed=ap.get("armed"), ekf_ok=ap.get("ekf_ok"), gps_fault=f.get("gps"), cam_fault=f.get("camera"),
        imu_fault=f.get("imu"),
        truth_lat=tr and tr["lat"], truth_lon=tr and tr["lon"], truth_alt=tr and tr["alt"],
        truth_speed=tr and tr["speed"],
        nav_state=n.get("state"), nav_source=n.get("source"), nav_fresh=n.get("fresh"),
        nav_lat=n.get("lat"), nav_lon=n.get("lon"),
        nav_err_m=n.get("err_m") if n.get("fresh") else None,
        ap_belief_err_m=ap.get("err_m"), ap_fix_type=ap.get("fix_type"), ap_sats=ap.get("sats"),
        dist_to_dest_m=ap.get("dist_to_dest_m"))


def stats(v):
    v = sorted(x for x in v if x is not None)
    if not v:
        return None
    return dict(n=len(v), median=round(statistics.median(v), 1), p90=round(v[int(.9 * (len(v) - 1))], 1),
                max=round(v[-1], 1), last=None)


def wait_idle(timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = state()
        if d and d["phase"] in ("idle", "error"):
            return True
        time.sleep(2)
    return False


def run(name, outdir):
    sc = SCENARIOS[name]
    print(f"\n=== {name}: {sc['desc']}", flush=True)
    d = state()
    if d is None:
        raise SystemExit("simulator not reachable on " + API)
    post("stop", {})
    wait_idle(30)
    post("fault", {"gps": "ok", "camera": "ok", "imu": "ok", "light": "day"})
    time.sleep(2)
    body = dict(vehicle="drone", start=ROUTE_START, dest=ROUTE_DEST, speed=SPEED, alt=ALT,
                vision="real", light="day", max_speed_mps=30, profile="measured")
    body.update(sc["mission"])
    r = post("mission", body)
    print("mission:", r, flush=True)
    summary = dict(name=name, desc=sc["desc"], mission=body, faults=sc["faults"], started=time.time())
    if not r.get("ok"):
        summary["outcome"] = "harness: mission refused: " + str(r.get("error"))
        return summary
    t0 = time.time()
    while True:
        d = state()
        if d and d["phase"] == "enroute":
            break
        if d and d["phase"] == "error" or time.time() - t0 > 480:
            summary["outcome"] = f"harness: did not reach cruise ({d and d['phase']}: {d and d['detail']})"
            post("stop", {})
            return summary
        time.sleep(3)
    summary["takeoff_to_cruise_s"] = round(time.time() - t0)
    tc = time.time()
    path = os.path.join(outdir, name + ".csv")
    rows, pending, injected = [], sorted(sc["faults"], key=lambda x: x[0]), []
    end_reason, landed_at, arrived_at, last_events = None, None, None, []
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, COLS)
        w.writeheader()
        while True:
            t = time.time() - tc
            while pending and t >= pending[0][0]:
                at, fl = pending.pop(0)
                rr = stall_day(fl.pop("stall_day_s")) if "stall_day_s" in fl else post("fault", fl)
                injected.append(dict(t_s=round(t, 1), fault=fl, reply=rr))
                print(f"  +{t:5.0f}s inject {fl} -> {rr}", flush=True)
            d = state()
            if d is None:
                end_reason = "harness: simulator stopped answering"
                break
            row = row_from(d, t)
            rows.append(row)
            w.writerow(row)
            fh.flush()
            last_events = d.get("events", last_events)
            if int(t) % 30 == 0 and (len(rows) < 2 or int(rows[-2]["t_s"]) != int(t)):
                print(f"  +{t:5.0f}s phase={row['phase']} mode={row['ap_mode']} nav={row['nav_state']}/"
                      f"{row['nav_source']} err={row['nav_err_m'] and round(row['nav_err_m'])} "
                      f"ap_err={row['ap_belief_err_m'] and round(row['ap_belief_err_m'])} "
                      f"alt={row['truth_alt'] and round(row['truth_alt'])}", flush=True)
            if d["phase"] == "error":
                end_reason = "sim phase error: " + str(d["detail"])
                break
            if d["phase"] == "arrived" and arrived_at is None:
                arrived_at = t
            if arrived_at is not None and t - arrived_at > 20:
                end_reason = "arrived"
                break
            on_ground = row["truth_alt"] is not None and row["truth_alt"] < 1.5
            if row["armed"] is False and t > 20 and on_ground:
                landed_at = landed_at or t
                if t - landed_at > 15:
                    end_reason = "landed and disarmed"
                    break
            if t > sc.get("max_s", MAX_AFTER_CRUISE_S):
                end_reason = "time limit"
                break
            time.sleep(max(0.0, 1.0 - ((time.time() - tc) - t)))
    json.dump(last_events, open(os.path.join(outdir, name + "_events.json"), "w"), indent=1)
    try:
        d = state()
        summary["vision_stats"] = (d or {}).get("vision", {}).get("stats")
    except Exception:                                  # noqa: BLE001
        pass
    # ---- analysis ----
    t_first_fault = sc["faults"][0][0]
    summary.update(end_reason=end_reason, duration_after_cruise_s=round(rows[-1]["t_s"]), injected=injected)
    nav_all = [r["nav_err_m"] for r in rows]
    summary["nav_err_all"] = stats(nav_all)
    after = [r for r in rows if r["t_s"] >= t_first_fault]
    summary["nav_err_after_first_fault"] = stats([r["nav_err_m"] for r in after])
    summary["nav_no_position_s_after_first_fault"] = sum(1 for r in after if r["nav_err_m"] is None)
    summary["ap_belief_err_after_first_fault"] = stats([r["ap_belief_err_m"] for r in after])
    for key in ("nav_err_after_first_fault",):
        if summary[key]:
            vv = [r["nav_err_m"] for r in after if r["nav_err_m"] is not None]
            summary[key]["last"] = round(vv[-1], 1)
    # autopilot reaction: first sample where the mode left GUIDED while armed
    fs = next((r for r in rows if r["armed"] and r["ap_mode"] not in ("GUIDED", "—", None) and r["t_s"] > 5), None)
    summary["autopilot_left_guided"] = fs and dict(t_s=fs["t_s"], mode=fs["ap_mode"],
                                                  after_first_fault_s=round(fs["t_s"] - t_first_fault, 1))
    modes = []
    for r in rows:
        if not modes or modes[-1][1] != r["ap_mode"]:
            modes.append((r["t_s"], r["ap_mode"]))
    summary["mode_changes"] = modes
    states = []
    for r in rows:
        k = (r["nav_state"], r["nav_source"])
        if not states or states[-1][1:] != k:
            states.append((r["t_s"],) + k)
    summary["nav_state_changes"] = states
    last = rows[-1]
    summary["final"] = dict(t_s=last["t_s"], phase=last["phase"], ap_mode=last["ap_mode"], armed=last["armed"],
                            truth_alt=last["truth_alt"], dist_to_dest_m=last["dist_to_dest_m"],
                            nav_state=last["nav_state"], nav_err_m=last["nav_err_m"])
    # position jumps of the NAVERA output not explained by the truth movement (1 s steps)
    jumps = []
    for a, b in zip(rows, rows[1:]):
        if None in (a["nav_lat"], b["nav_lat"], a["truth_lat"], b["truth_lat"]) or not (a["nav_fresh"] and b["nav_fresh"]):
            continue
        dt = b["t_s"] - a["t_s"]
        if not 0.3 < dt < 3:
            continue
        step = hav((a["nav_lat"], a["nav_lon"]), (b["nav_lat"], b["nav_lon"]))
        mv = hav((a["truth_lat"], a["truth_lon"]), (b["truth_lat"], b["truth_lon"]))
        jumps.append((abs(step - mv), b["t_s"], b["nav_source"], round(step), round(mv)))
    jumps.sort(reverse=True)
    summary["largest_nav_jumps_m"] = [dict(excess_m=round(j[0]), t_s=j[1], source=j[2], nav_step_m=j[3], truth_step_m=j[4])
                                      for j in jumps[:5]]
    # after a GPS return: error in the 10 s windows around it, and time until NAVERA reports FIX again
    back = [t for t, f in sc["faults"] if f.get("gps") == "ok"]
    if back:
        tb = back[0]
        win = lambda lo, hi: stats([r["nav_err_m"] for r in rows if lo <= r["t_s"] < hi])
        summary["gps_back"] = dict(
            t_s=tb, nav_err_prev_10s=win(tb - 10, tb), nav_err_next_30s=win(tb, tb + 30),
            nav_err_after_30s=win(tb + 30, 1e9),
            first_fix_after_s=next((round(r["t_s"] - tb, 1) for r in rows if r["t_s"] >= tb and r["nav_state"] == "FIX"
                                    and r["nav_source"] == "GPS"), None))
    json.dump(summary, open(os.path.join(outdir, name + "_summary.json"), "w"), indent=1, default=str)
    print("  end:", end_reason, "| final:", summary["final"], flush=True)
    post("fault", {"gps": "ok", "camera": "ok", "imu": "ok"})
    post("stop", {})
    wait_idle(60)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scenarios", nargs="*", help="scenario names, or 'all'")
    ap.add_argument("--out", default=os.path.expanduser("~/.navera_sim/faults_2026-10-15"))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.scenarios:
        for k, v in SCENARIOS.items():
            print(f"{k:36s} {v['desc']}")
        return
    names = ORDER if a.scenarios == ["all"] else a.scenarios
    for n in names:
        if n not in SCENARIOS:
            sys.exit("unknown scenario " + n)
    os.makedirs(a.out, exist_ok=True)
    allsum = {}
    sp = os.path.join(a.out, "summary.json")
    if os.path.exists(sp):
        allsum = json.load(open(sp))
    for n in names:
        try:
            allsum[n] = run(n, a.out)
        except Exception as e:                         # noqa: BLE001
            allsum[n] = dict(name=n, outcome=f"harness exception: {e!r}")
            print("EXCEPTION", repr(e), flush=True)
        json.dump(allsum, open(sp, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
