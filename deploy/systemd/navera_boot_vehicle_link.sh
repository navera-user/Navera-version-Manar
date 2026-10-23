#!/usr/bin/env bash
#
# navera_boot_vehicle_link.sh — read the vehicle's sensors from its autopilot (MAVLink).
# Called by navera-vehicle-link.service.
# Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
if [ -z "${NAVERA_VEHICLE_MAVLINK_URL:-}" ]; then
    # no autopilot found at boot (navera-discover) nor configured: wait quietly instead of
    # restarting in a loop, until navera-hotplug finds one (or a reboot, or
    # `systemctl restart navera-discover navera-vehicle-link`)
    navera_idle_until_discovered "no autopilot found or configured (NAVERA_VEHICLE_MAVLINK_URL): vehicle link idle"
fi
# the autopilot's first GPS is read only for NAVERA_GPS_SOURCE=vehicle_gps1 (and only while the
# autopilot says NAVERA does not feed it: checked by the node); an NMEA GPS1 may be NAVERA's
# own NMEA output when that is on
nmea_out=false
case "${NAVERA_NMEA_PORT:-}" in ""|off|none) ;; *) nmea_out=true ;; esac
read_gps1=false
[ "${NAVERA_GPS_SOURCE:-}" = vehicle_gps1 ] && read_gps1=true
exec ros2 run navera_output vehicle_link_node.py --ros-args \
    -p mavlink_url:="${NAVERA_VEHICLE_MAVLINK_URL}" -p source_system:="${NAVERA_MAVLINK_SYSID:-1}" \
    -p read_gps1:=$read_gps1 -p navera_nmea_output:=$nmea_out
