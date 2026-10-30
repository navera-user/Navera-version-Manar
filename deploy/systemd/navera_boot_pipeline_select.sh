#!/usr/bin/env bash
# navera_boot_pipeline_select.sh — NAVERA's automatic pipeline choice (day / night / celestial).
# Called by navera-pipeline-select.service (root: it starts the chosen pipeline unit and stops
# the others). The rules are in navera_tools/pipeline_select.py.
NAVERA_WS="${NAVERA_WS:-/home/navera/isaac_ros_common}"
exec /usr/bin/python3 -I "$NAVERA_WS/navera_tools/pipeline_select.py"
