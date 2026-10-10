#!/bin/bash
# The solution does what the student does: play the three attacks to the REAL arbiter,
# read the two offsets of real_drift.txt into detection.py and report.md, run the experiment.
set -e
for s in jump drift jamspoof; do python3 spoof_real.py $s > /dev/null; done
python3 - <<'PY'
import re
lines = [l for l in open("real_drift.txt") if l.startswith("t=")]
off = lambda key: re.search(r"GPS\s+(\d+) m off", next(l for l in lines if key in l)).group(1)
d, r = off("IN DOUBT"), off("drifting away")
s = open("detection.py").read()
s = re.sub(r"REAL_DRIFT_OFFSET_AT_DOUBT_M = [0-9.]+", f"REAL_DRIFT_OFFSET_AT_DOUBT_M = {d}.0", s)
s = re.sub(r"REAL_DRIFT_OFFSET_AT_REFUSAL_M = [0-9.]+", f"REAL_DRIFT_OFFSET_AT_REFUSAL_M = {r}.0", s)
open("detection.py", "w").write(s)
t = open("report.md").read().replace("{DOUBT}", d).replace("{REFUSED}", r)
open("report.md", "w").write(t)
PY
python3 detection.py > /dev/null 2>&1
