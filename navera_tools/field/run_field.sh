#!/bin/bash
# Start the field test server (prints the addresses to open on the phone) and its supervisor
# (~/navera-field/STATUS.txt and ALERTS.log, read-only).
#   navera_tools/field/run_field.sh
# Tests are saved in ~/navera-field (NAVERA_FIELD_DIR). Stop with Ctrl-C: a running test is finished and reported.
cd "$(dirname "$0")/../.." || exit 1
source /opt/ros/humble/setup.bash 2>/dev/null
export PYTHONPATH="$PWD:$PWD/navera_common:$PWD/cn_pkg:${PYTHONPATH:-}"
(sleep 10; exec nice -n 10 python3 -m navera_tools.field.supervisor) &
SUP=$!
trap 'kill $SUP 2>/dev/null' EXIT
python3 navera_tools/field/server.py
