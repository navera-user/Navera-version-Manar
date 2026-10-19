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


def usb_360_present():
    """The Insta360 in USB 'Android' mode on the bus (read from sysfs: the device is not opened)."""
    base = "/sys/bus/usb/devices"
    try:
        for n in os.listdir(base):
            try:
                with open(os.path.join(base, n, "idVendor")) as f:
                    if f.read().strip().lower() == "2e1a":
                        return True
            except OSError:
                continue
    except OSError:
        pass
    return False


def verdict_360(f):
    """USE / IGNORE (why) for one solved 360 frame: what the operator may believe."""
    if f.get("stopped_but_phone_moving"):
        return "IGNORE: camera said stopped but the phone GPS says moving"
    if not f.get("stopped"):
        return "IGNORE: taken while moving ('up' may hold the car's acceleration)"
    return "USE"


def print_360(frames):
    """The 360 digest: trusted (stopped) fixes apart from flagged (moving) ones, the last fix's verdict, IMU health."""
    f360 = [f for f in frames if f.get("mode") == "360"]
    solved = [f for f in f360 if f.get("solved")]
    use = [f for f in solved if verdict_360(f) == "USE"]
    ign = [f for f in solved if verdict_360(f) != "USE"]

    def errs(rows):
        e = sorted(f["err_km_live"] for f in rows if isinstance(f.get("err_km_live"), (int, float)))
        return f"median {e[len(e) // 2]:.0f} km, max {e[-1]:.0f} km (n={len(e)})" if e else "no error yet"
    print(f"360: {len(f360)} frames, {sum(1 for f in f360 if f.get('stopped'))} judged stopped; fixes: "
          f"{len(use)} USE, {len(ign)} IGNORE")
    print(f"  USE (stopped) error vs phone: {errs(use)}")
    print(f"  IGNORE (moving)  error vs phone: {errs(ign)}")
    fooled = sum(1 for f in solved if f.get("stopped_but_phone_moving"))
    if fooled:
        print(f"  WARNING: {fooled} fix(es) called stopped while the phone moved - the stillness test was fooled")
    if solved:
        last = solved[-1]
        print(f"  last fix: {age(last.get('t'))}  {verdict_360(last)}  sigma {last.get('sigma_km')} km  "
              f"err {last.get('err_km_live')} km  matched {last.get('matched')}  phone speed {last.get('phone_speed_mps')} m/s")
    if use:
        print(f"  last USE fix: {age(use[-1].get('t'))}")
    nosens = sum(1 for f in f360[-60:] if "no camera sensor data" in str(f.get("why") or ""))
    if nosens:
        print(f"  WARNING: {nosens} of the last {len(f360[-60:])} frames had no camera IMU data (stream restarting?)")
    ss = sorted(f["solve_s"] for f in f360 if isinstance(f.get("solve_s"), (int, float)))
    if ss:
        print(f"  solve time: median {ss[len(ss) // 2]:.1f} s, max {ss[-1]:.1f} s")


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else newest(ROOT)
    srv = subprocess.run(["pgrep", "-f", "navera_tools/field/server.py"], capture_output=True).returncode == 0
    free = shutil.disk_usage(ROOT if os.path.isdir(ROOT) else "/").free / 1e9
    print(f"server: {'RUNNING' if srv else 'NOT RUNNING'}   disk free: {free:.1f} GB")
    cam = os.path.exists("/dev/v4l/by-id/usb-Amba_Insta360_One_R-video-index0")
    print(f"camera device: webcam mode {'present' if cam else 'absent'}, USB 360 mode (2e1a) "
          f"{'present' if usb_360_present() else 'absent'}")
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
    if any(f.get("mode") == "360" for f in frames):
        print_360(frames)
    for e in events[-6:]:
        print("event:", {k: v for k, v in e.items() if k != "t"})
    r = os.path.join(d, "report.md")
    if os.path.exists(r):
        print(f"report.md present ({age(os.path.getmtime(r))})")


if __name__ == "__main__":
    main()
