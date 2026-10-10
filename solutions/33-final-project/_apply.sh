#!/bin/bash
# The example project (idea 1): branch, change + test (example_project.patch), commit, patch, measurement.
set -e
L=$PWD
cd ~/navera
git checkout -q -f work && git branch -q -D project/min-satellites 2>/dev/null || true
git checkout -q -b project/min-satellites base
git apply "$L/example_project.patch"
git add gps_pkg/gps_pkg/nodes/gps_node.py gps_pkg/test/test_gga_validation.py
git -c user.name="Example Student" -c user.email="student@example.com" commit -q \
    -m "gps: refuse GGA fixes computed from fewer than 4 satellites"
git diff base > "$L/my_project.patch"
cd "$L" && python3 measure_project.py
