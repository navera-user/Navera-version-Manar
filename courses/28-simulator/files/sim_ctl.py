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
"""
import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request

URL = "http://127.0.0.1:8190"
START = [35.8256, 10.6385]          # the simulator's default start point (Sousse)
DEST = [35.8050, 10.6010]           # ~4 km south-west, inland, inside the onboard map
COLUMNS = ["t_s", "phase", "gps_mode", "navera_state", "navera_source", "navera_lat", "navera_lon",
           "navera_err_m", "truth_lat", "truth_lon", "truth_alt_m", "truth_speed_mps", "ap_mode",
           "ap_err_m", "reason"]


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
            "ap_err_m": f(ap.get("err_m")), "reason": nav.get("reason", "")}


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
    a = ap.parse_args()
    if a.cmd == "status":
        status()
    elif a.cmd == "mission":
        start = [float(v) for v in a.start.split(",")]
        dest = [float(v) for v in a.dest.split(",")]
        call("/api/mission", dict(vehicle="drone", start=start, dest=dest, vision="profile", profile=a.vision,
                                  light="day", speed=a.speed, alt=a.alt, forward_degraded=a.vision == "measured",
                                  degraded_sigma_m=500.0, max_speed_mps=30.0, camera_mount="gimbal"))
        print("mission sent: the autopilot starts, aligns on NAVERA's GPS (30–60 s), arms and takes off.\n"
              "Follow it with:  python3 sim_ctl.py status")
    elif a.cmd == "fault":
        call("/api/fault", {a.what: a.value})
        print(f"fault injected: {a.what} -> {a.value}")
    elif a.cmd == "record":
        record(a.seconds, a.out, a.events)
    elif a.cmd == "stop":
        call("/api/stop", {})
        print("mission stopped")


if __name__ == "__main__":
    main()
