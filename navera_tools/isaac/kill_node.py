#!/usr/bin/env python3
"""SIGKILL the python process(es) running a ROS node script, inside the container (SIMULATION tests).

    python3 kill_node.py day_subscriber.py

Only a process whose script argument (argv[1]) ends with /<name> is killed: the interpreter running the
node itself, not the `ros2 run` launcher above it (whose argv has the bare name) nor this script (the
name is never its argv[1]). Prints the PIDs killed; exit 1 when none.
"""
import os
import signal
import sys


def victims(name: str):
    out = []
    for d in os.listdir("/proc"):
        if not d.isdigit() or int(d) == os.getpid():
            continue
        try:
            argv = open(f"/proc/{d}/cmdline", "rb").read().split(b"\0")
        except OSError:
            continue
        if len(argv) > 1 and argv[1].decode(errors="replace").endswith("/" + name):
            out.append(int(d))
    return out


def main():
    pids = victims(sys.argv[1])
    for p in pids:
        try:
            os.kill(p, signal.SIGKILL)
        except OSError:
            pass
    print(" ".join(map(str, pids)))
    return 0 if pids else 1


if __name__ == "__main__":
    sys.exit(main())
