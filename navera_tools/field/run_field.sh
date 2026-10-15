#!/bin/bash
# Start the field test server (prints the address to open on the phone).
#   navera_tools/field/run_field.sh
# Tests are saved in ~/navera-field (NAVERA_FIELD_DIR). Stop with Ctrl-C: a running test is finished and reported.
cd "$(dirname "$0")/../.." || exit 1
source /opt/ros/humble/setup.bash 2>/dev/null
export PYTHONPATH="$PWD:$PWD/navera_common:$PWD/cn_pkg:${PYTHONPATH:-}"
exec python3 navera_tools/field/server.py
