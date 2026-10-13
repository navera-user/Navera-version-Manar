#!/usr/bin/env python3
"""lite_lint.py — the release gate that keeps NAVERA's code out of the course.

    tools/lite_lint.py 06-coordinates            # courses/<id>/, solutions/<id>/, datasets/<id>/
    tools/lite_lint.py --all                     # every mission + courses/_lib + solutions/_navera_lite
    tools/lite_lint.py --path some/dir file.py   # any files or folders
    tools/lite_lint.py --base ~/navera-academy/base ...   # the NAVERA snapshot to compare with (read only)

Two rules (reviews/fledgling-design.md §1.4 and §7.1; NAVERA Lite = the design's "Fledgling"):
1. No identifier of the real product: package, node and message names, NAVERA's folders and data paths
   (BANNED below). The words "navera", "NAVERA" and "navera_lite" are allowed: lessons describe the
   product in words and numbers.
2. No copy of NAVERA's text: no 6 consecutive non-trivial lines (whitespace-normalised) identical to a
   file of NAVERA's base snapshot. Imports, blank lines, lone brackets and public ROS boilerplate are
   trivial (they are not NAVERA's work).

Exit code 0 when clean, 1 with one line per finding: `path:line: message`. Only reads files.
"""
import argparse
import hashlib
import os
import re
import sys

ACADEMY = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BASE = os.path.expanduser("~/navera-academy/base")     # NAVERA at one commit, read only
WINDOW = 6

BANNED = [(re.compile(p), what) for p, what in [
    (r"\bnavera_common\b", "NAVERA package name navera_common"),
    (r"\bnavera_estimator\b", "NAVERA package name navera_estimator"),
    (r"\bnavera_msgs\b", "NAVERA message package navera_msgs"),
    (r"\bnavera_tools\b", "NAVERA folder navera_tools"),
    (r"\bestimator_node\b", "NAVERA node name estimator_node"),
    (r"\bPositionEstimate\b", "NAVERA message PositionEstimate"),
    (r"\bNavStatus\b", "NAVERA message NavStatus"),
    (r"\bcn_pkg\b", "NAVERA package cn_pkg"),
    (r"\bday_pkg\b", "NAVERA package day_pkg"),
    (r"\bgps_pkg\b", "NAVERA package gps_pkg"),
    (r"\bimu_pkg\b", "NAVERA package imu_pkg"),
    (r"\bcamera_pkg\b", "NAVERA package camera_pkg"),
    (r"\bnight_pkg\b", "NAVERA package night_pkg"),
    (r"\bnavera_output\b", "NAVERA package navera_output"),
    (r"\brtc_pkg\b", "NAVERA package rtc_pkg"),
    (r"\bsimulation_web\b", "NAVERA package simulation_web"),
    (r"\b(vehicle_output_node|vehicle_link_node|ros_gps_node|rtc_node|navera_web_bridge|navera_stellar_bridge"
     r"|cn_subscriber|day_subscriber|night_subscriber)\b", "a NAVERA executable name"),
    (r"\b(EstimatorNode|LocalMatcher|VisionNavigator|FrameOdometry|MBTilesReader)\b", "a NAVERA class name"),
    (r"~/navera(?![\w-])", "the NAVERA copy ~/navera"),
    (r"/data/navera_data", "NAVERA's data folder /data/navera_data"),
    (r"file:navera/", "a file:navera/ link (NAVERA's code)"),
    (r"(?<![\w~.-])/navera/(?!academy)", "a NAVERA topic or path /navera/…"),
]]

TEXT_EXT = {".py", ".md", ".txt", ".yaml", ".yml", ".json", ".sh", ".xml", ".cfg", ".msg", ".srv",
            ".launch", ".html", ".js", ".css", ".svg", ".csv", ".ini", ".toml", ".service", ".env",
            ".cpp", ".hpp", ".c", ".h", ".cmake", ".example", ".patch", ".diff", ".log", ".nmea", ""}
SKIP_DIRS = {".git", "__pycache__", "build", "install", "log", ".pytest_cache", "node_modules"}
MAX_BYTES = 5_000_000
BOILERPLATE = {
    'if __name__ == "__main__":', "if __name__ == '__main__':", "main()", "rclpy.init(args=args)",
    "rclpy.init()", "rclpy.spin(node)", "rclpy.shutdown()", "node.destroy_node()", "def main(args=None):",
    "def main():", "try:", "except KeyboardInterrupt:", "pass", "else:", "finally:", "return", "break",
    "continue", '"""', "'''", "```", "```bash", "```python", "</details>", "---", "/**:", "ros__parameters:",
}


def _norm(line):
    return " ".join(line.split())


def trivial(n):
    """A normalised line that says nothing of its author."""
    if len(n) < 6 or n in BOILERPLATE:
        return True
    if n.startswith("import ") or (n.startswith("from ") and " import " in n):
        return True
    if re.fullmatch(r"[#\s\-=*_|:{}\[\]().,;'\"`<>/]*", n):     # separators, brackets, table rules
        return True
    return False


def _lines(path):
    try:
        if os.path.getsize(path) > MAX_BYTES:
            return None
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", "replace").splitlines()


def _walk(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for dp, dns, fns in os.walk(p):
            dns[:] = sorted(d for d in dns if d not in SKIP_DIRS)
            for fn in sorted(fns):
                if os.path.splitext(fn)[1].lower() in TEXT_EXT:
                    yield os.path.join(dp, fn)


def _windows(lines):
    """(hash, first line number) of every WINDOW consecutive non-trivial lines."""
    kept = [(i + 1, n) for i, n in ((i, _norm(l)) for i, l in enumerate(lines)) if not trivial(n)]
    for k in range(len(kept) - WINDOW + 1):
        chunk = "\n".join(n for _, n in kept[k:k + WINDOW])
        yield hashlib.sha1(chunk.encode()).hexdigest(), kept[k][0]


_index = {}


def base_index(base=BASE):
    """hash → "file:line" for every 6-line window of NAVERA's base (built once per run)."""
    if base in _index:
        return _index[base]
    idx = {}
    if os.path.isdir(base):
        for f in _walk([base]):
            lines = _lines(f)
            if lines:
                for h, ln in _windows(lines):
                    idx.setdefault(h, f"{os.path.relpath(f, base)}:{ln}")
    _index[base] = idx
    return idx


def lint_paths(paths, base=BASE):
    """[(path, line, message)] for every finding in these files/folders."""
    out = []
    idx = base_index(base)
    for f in _walk(paths):
        lines = _lines(f)
        if lines is None:
            continue
        for i, line in enumerate(lines, 1):
            for rx, what in BANNED:
                if rx.search(line):
                    out.append((f, i, f"banned identifier: {what}"))
        if idx:
            last = -2
            for k, (h, ln) in enumerate(_windows(lines)):
                if h in idx:
                    if k != last + 1:            # one finding per run of overlapping windows
                        out.append((f, ln, f"{WINDOW}+ lines identical to NAVERA's base/{idx[h]} — write it yourself"))
                    last = k
    return out


def mission_paths(lid, root=ACADEMY):
    return [p for p in (os.path.join(root, "courses", lid), os.path.join(root, "solutions", lid),
                        os.path.join(root, "datasets", lid)) if os.path.exists(p)]


def all_paths(root=ACADEMY):
    ps = [os.path.join(root, "courses", "_lib"), os.path.join(root, "solutions", "_navera_lite")]
    cdir = os.path.join(root, "courses")
    for d in sorted(os.listdir(cdir)):
        if os.path.isfile(os.path.join(cdir, d, "meta.json")):
            ps += mission_paths(d, root)
    return [p for p in ps if os.path.exists(p)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("lessons", nargs="*", help="mission ids, e.g. 06-coordinates")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--path", nargs="+", default=[])
    ap.add_argument("--base", default=BASE)
    a = ap.parse_args(argv)
    paths = list(a.path)
    for lid in a.lessons:
        mp = mission_paths(lid)
        if not mp:
            sys.exit(f"no mission {lid}")
        paths += mp
    if a.all:
        paths += all_paths()
    if not paths:
        ap.error("give mission ids, --all or --path")
    if not os.path.isdir(a.base):
        print(f"warning: {a.base} not found: the copy check is skipped", file=sys.stderr)
    found = lint_paths(paths, a.base)
    for f, ln, msg in found:
        print(f"{os.path.relpath(f)}:{ln}: {msg}")
    n = len(list(_walk(paths)))
    print(f"lite_lint: {n} files, {len(found)} finding(s)" + (" — clean" if not found else ""))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
