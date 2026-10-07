#!/bin/bash
# the solution runs the real comparison (Step 7) and the experiments (Step 8), like the student
set -e
python3 compare_real.py --quiet
python3 experiment.py >/dev/null 2>&1
