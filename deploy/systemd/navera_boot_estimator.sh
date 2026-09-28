#!/usr/bin/env bash
#
# navera_boot_estimator.sh — NAVERA position arbiter (GPS > day > night > celestial).
# Called by navera-estimator.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
exec ros2 launch navera_estimator estimator.launch.py
