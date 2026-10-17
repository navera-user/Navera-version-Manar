#!/usr/bin/env python3
"""One-screen digest of the newest field test, for the remote operator (read-only).

    python3 -m navera_tools.field.watch [folder]

Prints: is the server alive, disk space, session state, how old the last frame / phone reading
are, stars, solve rate, error against the phone's GPS, and the reasons frames were not solved.
"""
import collections
import json
import math
import os
import shutil
import subprocess
import sys
import time

ROOT = os.environ.get("NAVERA_FIELD_DIR", os.path.expanduser("~/navera-field"))


def read_jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue            # a half-written last line
                if isinstance(d, dict):
                    out.append(d)
    except OSError:
        pass
    return out


def newest(root):
    dirs = [os.path.join(root, d) for d in os.listdir(root) if os.path.isfile(os.path.join(root, d, "session.json"))] \
        if os.path.isdir(root) else []
    return max(dirs, key=os.path.getmtime) if dirs else None


def age(t):
    return "never" if not t else f"{time.time() - t:.0f}s ago"


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else newest(ROOT)
    srv = subprocess.run(["pgrep", "-f", "navera_tools/field/server.py"], capture_output=True).returncode == 0
    free = shutil.disk_usage(ROOT if os.path.isdir(ROOT) else "/").free / 1e9
    print(f"server: {'RUNNING' if srv else 'NOT RUNNING'}   disk free: {free:.1f} GB")
    cam = os.path.exists("/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0")
    print(f"camera device: {'present' if cam else 'MISSING'}")
    if not d:
        print("no test folder yet")
        return
    print(f"test: {os.path.basename(d)}")
    frames, phone, events = (read_jsonl(os.path.join(d, n)) for n in ("frames.jsonl", "phone.jsonl", "events.jsonl"))
    print(f"frames {len(frames)}   phone readings {len(phone)}   events {len(events)}")
    if phone:
        p = phone[-1]
        print(f"phone last: {age(p.get('t'))}  gps acc {p.get('acc')} m  off-vertical {p.get('off_vertical_deg')} deg")
    if frames:
        last = frames[-1]
        print(f"last frame: {age(last.get('t'))}  sky={last.get('sky')} confirmed={last.get('confirmed')} "
              f"solved={last.get('solved')} why={last.get('why')}")
        tail = frames[-60:]
        solved = [f for f in tail if f.get("solved")]
        print(f"last {len(tail)} frames: solved {len(solved)}   median stars "
              f"{sorted(f.get('confirmed') or 0 for f in tail)[len(tail) // 2]}")
        errs = sorted(f["err_km_live"] for f in frames if isinstance(f.get("err_km_live"), (int, float))
                      and math.isfinite(f["err_km_live"]))
        if errs:
            print(f"error vs phone GPS (all {len(errs)} solved): median {errs[len(errs) // 2]:.1f} km, max {errs[-1]:.1f} km")
        why = collections.Counter((f.get("why") or "ok").split("(")[0].strip() for f in tail if not f.get("solved"))
        if why:
            print("not solved because: " + "; ".join(f"{k} x{v}" for k, v in why.most_common(5)))
    for e in events[-6:]:
        print("event:", {k: v for k, v in e.items() if k != "t"})
    r = os.path.join(d, "report.md")
    if os.path.exists(r):
        print(f"report.md present ({age(os.path.getmtime(r))})")


if __name__ == "__main__":
    main()
