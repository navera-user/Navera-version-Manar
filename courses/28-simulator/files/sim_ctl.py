#!/usr/bin/env python3
"""sim_ctl.py — talk to the NAVERA mission simulator from the terminal.

The simulator (navera_tools/run_sim.sh) has a web page on port 8190; this script uses the
same HTTP API the page uses (/api/state, /api/mission, /api/fault, /api/stop).

    python3 sim_ctl.py status                     one line: phase, NAVERA's state, errors
    python3 sim_ctl.py mission                    a drone mission over Sousse (simulated vision, target profile)
    python3 sim_ctl.py mission --vision measured  ... with the former day vision's error profile (~440 m, unknown sigma)
    python3 sim_ctl.py fault gps jammed           inject a fault: gps ok|jammed|spoof_jump|spoof_drift|off,
                                                  camera ok|failed
    python3 sim_ctl.py record --seconds 300       write one line per second to flight.csv and the
                                                  simulator's events to events.log (Ctrl+C to stop early)
    python3 sim_ctl.py stop                       stop the mission (the simulator keeps running)
    python3 sim_ctl.py campaign scenario.json     a scripted fault-injection run: mission, faults at fixed
                                                  times after "enroute", recording; writes <name>.csv
                                                  and <name>_events.log, then stops the mission

A scenario file (JSON) — times are seconds after the drone starts flying to the destination:
    {"name": "drift_target", "vision": "target",
     "faults": [[30, "gps", "spoof_drift"], [120, "gps", "ok"]],
     "tail_s": 40}
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8190"
START = [35.8256, 10.6385]          # the simulator's default start point (Sousse)
DEST = [35.8050, 10.6010]           # ~4 km south-west, inland, inside the onboard map
COLUMNS = ["t_s", "phase", "gps_mode", "navera_state", "navera_source", "navera_lat", "navera_lon",
           "navera_err_m", "truth_lat", "truth_lon", "truth_alt_m", "truth_speed_mps", "ap_mode",
           "ap_err_m", "reason", "camera"]


def call(path, body=None, timeout=10):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(URL + path, data=data, method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error")
        except Exception:
            msg = str(e)
        sys.exit(f"the simulator refused: {msg}")
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        sys.exit(f"cannot reach the simulator on {URL} ({e}). Is navera_tools/run_sim.sh running "
                 f"(and did you take the simulator in the Hardware menu)?")


def row(st, t):
    nav, tr, ap = st.get("navera") or {}, st.get("truth") or {}, st.get("autopilot") or {}
    fresh = nav.get("fresh")
    f = lambda v, d=1: "" if v is None else f"{v:.{d}f}"          # noqa: E731
    return {"t_s": f(t), "phase": st.get("phase", ""), "gps_mode": (st.get("gps") or {}).get("mode", ""),
            "navera_state": nav.get("state", ""), "navera_source": nav.get("source", ""),
            "navera_lat": f(nav.get("lat") if fresh else None, 7), "navera_lon": f(nav.get("lon") if fresh else None, 7),
            "navera_err_m": f(nav.get("err_m")), "truth_lat": f(tr.get("lat"), 7), "truth_lon": f(tr.get("lon"), 7),
            "truth_alt_m": f(tr.get("alt")), "truth_speed_mps": f(tr.get("speed")), "ap_mode": ap.get("mode", ""),
            "ap_err_m": f(ap.get("err_m")), "reason": nav.get("reason", ""),
            "camera": (st.get("faults") or {}).get("camera", "")}


def status():
    st = call("/api/state")
    r = row(st, 0.0)
    print(f"phase {r['phase']} ({st.get('detail', '')})\n"
          f"GPS receiver: {r['gps_mode']} | NAVERA: {r['navera_state']} {r['navera_source']} "
          f"error {r['navera_err_m'] or '—'} m | autopilot: {r['ap_mode']} error {r['ap_err_m'] or '—'} m\n"
          f"reason: {r['reason']}")


def record(seconds, out, events_out):
    print(f"recording to {out} and {events_out} for {seconds} s (Ctrl+C to stop)…")
    seen = set()
    t0 = time.time()
    with open(out, "w", newline="") as f, open(events_out, "a") as ev:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        try:
            while time.time() - t0 < seconds:
                st = call("/api/state")
                t = time.time() - t0
                w.writerow(row(st, t))
                f.flush()
                for e in st.get("events", []):
                    key = (e.get("clock"), e.get("text"))
                    if key not in seen:
                        seen.add(key)
                        ev.write(f"{e.get('clock')} [{e.get('level')}] {e.get('text')}\n")
                ev.flush()
                if int(t) % 10 == 0:
                    r = row(st, t)
                    print(f"  t={t:5.0f} s  {r['phase']:9s} GPS {r['gps_mode']:11s} NAVERA {r['navera_state']:9s} "
                          f"{r['navera_source']:11s} err {r['navera_err_m'] or '—':>6s} m")
                time.sleep(max(0.0, 1.0 - (time.time() - t0 - t)))
        except KeyboardInterrupt:
            pass
    print(f"saved {out} and {events_out}")


def mission(vision="target", start=START, dest=DEST, speed=15.0, alt=150.0):
    call("/api/mission", dict(vehicle="drone", start=list(start), dest=list(dest), vision="profile",
                              profile=vision, light="day", speed=speed, alt=alt,
                              forward_degraded=vision == "measured", degraded_sigma_m=500.0,
                              max_speed_mps=30.0, camera_mount="gimbal"))


FAULT_VALUES = {"gps": ("ok", "jammed", "spoof_jump", "spoof_drift", "off"), "camera": ("ok", "failed")}


def load_scenario(path):
    """Read and check a scenario file. Every mistake is found HERE, before anything is sent to the
    simulator (the simulator is shared by the class: a half-started mission must never be left flying)."""
    try:
        with open(path) as f:
            sc = json.load(f)
    except FileNotFoundError:
        sys.exit(f"scenario file not found: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"{path} is not valid JSON: {e}")
    if not isinstance(sc, dict):
        sys.exit(f"{path}: the scenario must be a JSON object {{...}}")
    name = sc.get("name")
    if not isinstance(name, str) or not name or any(ch in name for ch in "/\\") or name.startswith("."):
        sys.exit(f'{path}: "name" must be a simple file name like "my_run" (no "/")')
    if sc.get("vision", "target") not in ("target", "measured"):
        sys.exit(f'{path}: "vision" must be "target" or "measured", not {sc.get("vision")!r}')
    faults = sc.get("faults", [])
    if not isinstance(faults, list):
        sys.exit(f'{path}: "faults" must be a list like [[30, "gps", "jammed"], [70, "gps", "ok"]]')
    for i, fl in enumerate(faults):
        if not (isinstance(fl, list) and len(fl) == 3 and isinstance(fl[0], (int, float))
                and not isinstance(fl[0], bool) and fl[0] >= 0):
            sys.exit(f"{path}: fault {i} = {fl!r} must be [seconds >= 0, what, value]")
        if fl[1] not in FAULT_VALUES or fl[2] not in FAULT_VALUES[fl[1]]:
            sys.exit(f"{path}: fault {i} = {fl!r}: allowed are "
                     + "; ".join(f"{k}: {'|'.join(v)}" for k, v in FAULT_VALUES.items()))
    for key, default in (("tail_s", 40), ("max_s", 900)):
        v = sc.get(key, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            sys.exit(f'{path}: "{key}" must be a positive number of seconds, not {v!r}')
    sc["faults"] = sorted(faults, key=lambda fl: fl[0])
    return sc


def safe_stop():
    """Best effort: faults back to ok and mission stopped. Never exits, never raises."""
    for path, body in (("/api/fault", {"gps": "ok", "camera": "ok"}), ("/api/stop", {})):
        try:
            req = urllib.request.Request(URL + path, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).read()
        except Exception as e:                       # noqa: BLE001 — we are already cleaning up
            print(f"  (warning: {path} failed during clean-up: {e})", file=sys.stderr)


def campaign(path, out_dir="."):
    """Run one scripted scenario: the same mission, the same faults at the same times, every time."""
    # 1. check everything BEFORE touching the shared simulator
    sc = load_scenario(path)
    name, faults = sc["name"], sc["faults"]
    call("/api/state")                                       # reachable? (read only: changes nothing)
    try:
        os.makedirs(out_dir, exist_ok=True)                  # --out-dir my_runs works on the first run
    except OSError as e:
        sys.exit(f"cannot create the output folder {out_dir!r}: {e}")
    csv_path = os.path.join(out_dir, f"{name}.csv")
    ev_path = os.path.join(out_dir, f"{name}_events.log")
    try:                                                     # open (= test) both files before flying
        f = open(csv_path, "w", newline="")
        ev = open(ev_path, "w")
    except OSError as e:
        sys.exit(f"cannot write the output files in {out_dir!r}: {e}")
    # 2. from here on, ANY error (or Ctrl+C) still resets the faults and stops the mission
    with f, ev:
        try:
            call("/api/fault", {"gps": "ok", "camera": "ok"})          # a clean start
            mission(sc.get("vision", "target"))
            print(f"{name}: mission sent; faults {faults} (s after en route)")
            seen, t0, t_enroute, k = set(), time.time(), None, 0
            end_after = (faults[-1][0] if faults else 0) + float(sc.get("tail_s", 40))
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            while time.time() - t0 < float(sc.get("max_s", 900)):
                st = call("/api/state")
                t = time.time() - t0
                w.writerow(row(st, t))
                f.flush()
                for e in st.get("events", []):
                    key = (e.get("clock"), e.get("text"))
                    if key not in seen:
                        seen.add(key)
                        ev.write(f"{e.get('clock')} [{e.get('level')}] {e.get('text')}\n")
                ev.flush()
                if t_enroute is None and st.get("phase") == "enroute":
                    t_enroute = t
                    print(f"  en route at t = {t:.0f} s")
                if t_enroute is not None:
                    while k < len(faults) and t - t_enroute >= faults[k][0]:
                        call("/api/fault", {faults[k][1]: faults[k][2]})
                        print(f"  t = {t:.0f} s: fault {faults[k][1]} -> {faults[k][2]}")
                        # the exact instant: the CSV row that first shows it comes up to 1 s later
                        ev.write(f"{time.strftime('%H:%M:%S')} [inject] t_s={time.time() - t0:.1f} "
                                 f"{faults[k][1]} -> {faults[k][2]}\n")
                        k += 1
                    if t - t_enroute >= end_after or st.get("phase") in ("arrived", "error", "idle"):
                        break
                time.sleep(max(0.0, 1.0 - (time.time() - t0 - t)))
        except KeyboardInterrupt:
            print("  stopped by Ctrl+C")
        finally:                                             # also runs on errors and sys.exit()
            safe_stop()
            print(f"mission stopped; saved {csv_path} and {ev_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    m = sub.add_parser("mission")
    m.add_argument("--start", default=",".join(map(str, START)))
    m.add_argument("--dest", default=",".join(map(str, DEST)))
    m.add_argument("--vision", choices=("target", "measured"), default="target")
    m.add_argument("--speed", type=float, default=15.0, help="cruise speed m/s")
    m.add_argument("--alt", type=float, default=150.0)
    fa = sub.add_parser("fault")
    fa.add_argument("what", choices=("gps", "camera"))
    fa.add_argument("value")
    r = sub.add_parser("record")
    r.add_argument("--seconds", type=float, default=300.0)
    r.add_argument("--out", default="flight.csv")
    r.add_argument("--events", default="events.log")
    sub.add_parser("stop")
    cp = sub.add_parser("campaign")
    cp.add_argument("scenario")
    cp.add_argument("--out-dir", default=".")
    a = ap.parse_args()
    if a.cmd == "status":
        status()
    elif a.cmd == "mission":
        try:
            start = [float(v) for v in a.start.split(",")]
            dest = [float(v) for v in a.dest.split(",")]
            assert len(start) == 2 and len(dest) == 2
        except (ValueError, AssertionError):
            sys.exit("--start and --dest must be 'lat,lon' in degrees, e.g. 35.8256,10.6385")
        mission(a.vision, start, dest, a.speed, a.alt)
        print("mission sent: the autopilot starts, aligns on NAVERA's GPS (30–60 s), arms and takes off.\n"
              "Follow it with:  python3 sim_ctl.py status")
    elif a.cmd == "fault":
        if a.value not in FAULT_VALUES[a.what]:
            sys.exit(f"{a.what} accepts: {'|'.join(FAULT_VALUES[a.what])}")
        call("/api/fault", {a.what: a.value})
        print(f"fault injected: {a.what} -> {a.value}")
    elif a.cmd == "record":
        record(a.seconds, a.out, a.events)
    elif a.cmd == "stop":
        call("/api/stop", {})
        print("mission stopped")
    elif a.cmd == "campaign":
        campaign(a.scenario, a.out_dir)


if __name__ == "__main__":
    main()
