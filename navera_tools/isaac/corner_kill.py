#!/usr/bin/env python3
"""Kill day_subscriber alone as the vehicle reaches a waypoint corner (SIMULATION, open3 problem 1).

    python3 corner_kill.py ~/navera_results/NAME [--after 40] [--dist 25] [--container navera_isaac]

Runs on the PC beside run_closed_loop.sh: waits for the GPS cut, reads the mission's waypoints
(sitl_events.jsonl), follows the truth in position.csv, and once --after s past the cut, when the
vehicle is within --dist m of a corner and closing on it, SIGKILLs the day node in the container
(kill_node.py; the container's loop respawns it 1 s later, as the product's launch does). Writes
day_kill_wall (wall clock) and corner_kill.json (time after the cut, the corner, the distance).
"""
import argparse
import json
import math
import os
import subprocess
import time


def _dist(a, b):
    k = math.cos(math.radians(a[0]))
    return math.hypot((a[0] - b[0]) * 111320.0, (a[1] - b[1]) * 111320.0 * k)


def _last_truth(path):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 4096))
            lines = f.read().decode(errors="replace").strip().splitlines()
    except OSError:
        return None
    for line in reversed(lines[1:]):
        c = line.split(",")
        try:
            return float(c[0]), (float(c[7]), float(c[8]))
        except (IndexError, ValueError):
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("res")
    ap.add_argument("--after", type=float, default=40.0)
    ap.add_argument("--dist", type=float, default=25.0)
    ap.add_argument("--container", default="navera_isaac")
    ap.add_argument("--timeout", type=float, default=3600.0)
    a = ap.parse_args()
    t_end = time.time() + a.timeout
    cut = wps = None
    while time.time() < t_end and (cut is None or wps is None):
        try:
            cut = float(open(os.path.join(a.res, "gps_cut")).read())
        except (OSError, ValueError):
            pass
        try:
            for line in open(os.path.join(a.res, "sitl_events.jsonl")):
                d = json.loads(line)
                if d.get("kind") == "mission":
                    wps = [tuple(p) for p in d["waypoints"]]
        except (OSError, ValueError):
            pass
        time.sleep(1.0)
    prev = {}
    while time.time() < t_end:
        tr = _last_truth(os.path.join(a.res, "position.csv"))
        if tr is not None and tr[0] - cut >= a.after:
            for i, w in enumerate(wps):
                d = _dist(tr[1], w)
                closing = i in prev and d < prev[i]
                prev[i] = d
                if d <= a.dist and closing:
                    tw = time.time()
                    r = subprocess.run(["docker", "exec", a.container, "python3",
                                        "/ws/src/navera/navera_tools/isaac/kill_node.py", "day_subscriber.py"],
                                       capture_output=True, text=True)
                    open(os.path.join(a.res, "day_kill_wall"), "w").write(f"{tw:.3f}\n")
                    json.dump({"t_after_cut_s": round(tr[0] - cut, 2), "t_rel": tr[0], "corner": i, "waypoint": w,
                               "dist_m": round(d, 1), "pids": r.stdout.strip(), "rc": r.returncode},
                              open(os.path.join(a.res, "corner_kill.json"), "w"))
                    print(f"killed at {tr[0] - cut:.1f} s after the cut, {d:.0f} m before corner {i}: {r.stdout.strip()}",
                          flush=True)
                    return 0
        time.sleep(0.2)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
