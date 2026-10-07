#!/bin/bash
# the solution plays the three attacks to the real arbiter, as the student does
for s in jump drift jamspoof; do python3 spoof_real.py $s > /dev/null || exit 1; done
