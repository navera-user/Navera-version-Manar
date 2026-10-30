#!/bin/bash
# bisect_test.sh — reference solution of TODO 4 (lab Step 7).
# 0 = good, 1 = bad, 125 = this commit cannot be tested.
n=$(python3 ~/lessons/05-git/probe_gate.py) || exit 125
if [ "$n" = "5" ]; then
    exit 0
fi
exit 1
