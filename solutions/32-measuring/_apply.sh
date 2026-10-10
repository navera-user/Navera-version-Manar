#!/bin/bash
# the solution's outputs: results_*.json, error_*.png (measure.py) and coverage.json (bootstrap.py)
python3 measure.py /data/academy/32-measuring/flight_target.csv /data/academy/32-measuring/flight_measured.csv \
    /data/academy/32-measuring/flight_selective.csv > /dev/null
python3 bootstrap.py --coverage > /dev/null
