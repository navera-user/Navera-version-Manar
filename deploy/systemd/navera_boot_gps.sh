#!/usr/bin/env bash
#
# navera_boot_gps.sh — NAVERA's GPS source. Called by navera-gps.service.
# Shared steps: navera_boot_lib.sh (installed next to it).
#   NAVERA_GPS_SOURCE=serial   (default) the box's receiver, NMEA on NAVERA_GPS_PORT
#   NAVERA_GPS_SOURCE=vehicle  the autopilot's SECOND GPS, read by navera-vehicle-link
#   NAVERA_GPS_SOURCE=ros      a NavSatFix topic of the vehicle (NAVERA_ROS_GPS_TOPIC)
#   NAVERA_GPS_SOURCE=none     none found (navera-discover): idle
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
case "${NAVERA_GPS_SOURCE:-serial}" in
  none|auto)
    # none: navera-discover found no GPS; auto: it has not decided (it did not run).
    # Never open a default port, which may be the autopilot's link.
    navera_log "no GPS found or configured (NAVERA_GPS_SOURCE=${NAVERA_GPS_SOURCE}): GPS idle"
    exec sleep infinity ;;
  serial)
    exec ros2 launch gps_pkg gps.launch.py \
        serial_port:="${NAVERA_GPS_PORT:-/dev/ttyTHS1}" baud_rate:="${NAVERA_GPS_BAUD:-9600}" ;;
  vehicle)
    exec ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/navera/vehicle/gps2 ;;
  ros)
    [ -n "${NAVERA_ROS_GPS_TOPIC:-}" ] || { echo "NAVERA_GPS_SOURCE=ros needs NAVERA_ROS_GPS_TOPIC" >&2; exit 1; }
    exec ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:="$NAVERA_ROS_GPS_TOPIC" ;;
  *)
    echo "NAVERA_GPS_SOURCE=${NAVERA_GPS_SOURCE}: expected serial, vehicle or ros" >&2; exit 1 ;;
esac
