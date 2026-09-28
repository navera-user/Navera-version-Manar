#!/usr/bin/env bash
#
# navera_boot_output.sh — NAVERA output to the autopilot (NMEA and/or MAVLink).
# Called by navera-output.service. Shared steps: navera_boot_lib.sh (installed next to it).
# Outputs come from NAVERA_NMEA_PORT / NAVERA_NMEA_BAUD / NAVERA_MAVLINK_URL in navera.env.
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
exec ros2 launch navera_output vehicle_output.launch.py
