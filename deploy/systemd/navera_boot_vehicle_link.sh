#!/usr/bin/env bash
#
# navera_boot_vehicle_link.sh — read the vehicle's sensors from its autopilot (MAVLink).
# Called by navera-vehicle-link.service (only for NAVERA_SENSOR_SOURCE=vehicle).
# Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
if [ -z "${NAVERA_VEHICLE_MAVLINK_URL}" ]; then
    navera_log "NAVERA_VEHICLE_MAVLINK_URL is not set (see /etc/navera/navera.env)"
    exit 1
fi
exec ros2 run navera_output vehicle_link_node.py --ros-args \
    -p mavlink_url:="${NAVERA_VEHICLE_MAVLINK_URL}"
