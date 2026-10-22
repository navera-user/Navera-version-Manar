#!/usr/bin/env bash
#
# navera_boot_insta360.sh — the Insta360 kit: the One R in USB "Android" mode as the day camera's
# straight-down view AND the attitude (its own IMU), from one process (camera_pkg insta360_node).
# Called by navera-insta360.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
if [ "${NAVERA_SENSOR_SOURCE:-}" != "insta360" ] && [ "${NAVERA_CAMERA_INPUT:-}" != "insta360" ]; then
    # neither the attitude nor the camera is the Insta360 (navera.env, or navera-discover found
    # no One R in USB Android mode): idle instead of a restart loop, until navera-hotplug finds
    # one plugged in later (discovered.env changes: the unit restarts with it)
    navera_idle_until_discovered "the Insta360 kit is not used (NAVERA_SENSOR_SOURCE=${NAVERA_SENSOR_SOURCE:-} NAVERA_CAMERA_INPUT=${NAVERA_CAMERA_INPUT:-}): service idle"
fi
exec ros2 launch camera_pkg insta360.launch.py
