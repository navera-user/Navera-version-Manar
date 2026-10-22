#!/usr/bin/env bash
#
# navera_boot_gps.sh — NAVERA's GPS source. Called by navera-gps.service.
# Shared steps: navera_boot_lib.sh (installed next to it).
#   NAVERA_GPS_SOURCE=serial        (default) a receiver on a serial port, NMEA and/or u-blox UBX
#                                   (recognised automatically): NAVERA_GPS_PORT / NAVERA_GPS_BAUD
#   NAVERA_GPS_SOURCE=network       NMEA / UBX over the network: NAVERA_GPS_URL (tcp:host:port, udp:port)
#   NAVERA_GPS_SOURCE=dronecan      a DroneCAN GNSS (Fix2) on NAVERA_GPS_CAN_IFACE (default can0),
#                                   node NAVERA_GPS_CAN_NODE (default: the first with a fix)
#   NAVERA_GPS_SOURCE=vehicle       the autopilot's SECOND GPS, read by navera-vehicle-link
#   NAVERA_GPS_SOURCE=vehicle_gps1  the autopilot's FIRST GPS, read by navera-vehicle-link only
#                                   while the autopilot says NAVERA does not feed it
#   NAVERA_GPS_SOURCE=ros           a NavSatFix topic of the vehicle (NAVERA_ROS_GPS_TOPIC)
#   NAVERA_GPS_SOURCE=none          none found (navera-discover): idle until navera-hotplug finds one
# NAVERA_GPS_CONFIGURE=1: NAVERA may turn on UBX NAV-PVT in the receiver (RAM only). Default:
# never written to. NAVERA_GPS_CAN_ALLOCATE=1: NAVERA gives DroneCAN node ids (a GPS alone on
# its CAN bus); default: passive listener.
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
truthy() { case "${1,,}" in 1|true|yes|on) echo true ;; *) echo false ;; esac; }
case "${NAVERA_GPS_SOURCE:-serial}" in
  none|auto)
    # none: navera-discover found no GPS; auto: it has not decided (it did not run).
    # Never open a default port, which may be the autopilot's link.
    navera_idle_until_discovered "no GPS found or configured (NAVERA_GPS_SOURCE=${NAVERA_GPS_SOURCE}): GPS idle" ;;
  serial)
    exec ros2 launch gps_pkg gps.launch.py \
        serial_port:="${NAVERA_GPS_PORT:-/dev/ttyTHS1}" baud_rate:="${NAVERA_GPS_BAUD:-9600}" \
        configure_receiver:="$(truthy "${NAVERA_GPS_CONFIGURE:-0}")" ;;
  network)
    [ -n "${NAVERA_GPS_URL:-}" ] || { echo "NAVERA_GPS_SOURCE=network needs NAVERA_GPS_URL" >&2; exit 1; }
    exec ros2 launch gps_pkg gps.launch.py url:="$NAVERA_GPS_URL" \
        configure_receiver:="$(truthy "${NAVERA_GPS_CONFIGURE:-0}")" ;;
  dronecan)
    exec ros2 run gps_pkg dronecan_gps_node.py --ros-args \
        -p can_interface:="${NAVERA_GPS_CAN_IFACE:-can0}" -p node_id:="${NAVERA_GPS_CAN_NODE:-0}" \
        -p allocate_node_ids:="$(truthy "${NAVERA_GPS_CAN_ALLOCATE:-0}")" \
        -p allocation_db:=/var/lib/navera/dronecan_node_ids.db ;;
  vehicle)
    exec ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/navera/vehicle/gps2 ;;
  vehicle_gps1)
    exec ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:=/navera/vehicle/gps1 \
        -p satellites_topic:=/navera/vehicle/gps1_satellites ;;
  ros)
    [ -n "${NAVERA_ROS_GPS_TOPIC:-}" ] || { echo "NAVERA_GPS_SOURCE=ros needs NAVERA_ROS_GPS_TOPIC" >&2; exit 1; }
    exec ros2 run gps_pkg ros_gps_node.py --ros-args -p fix_topic:="$NAVERA_ROS_GPS_TOPIC" ;;
  *)
    echo "NAVERA_GPS_SOURCE=${NAVERA_GPS_SOURCE}: expected serial, network, dronecan, vehicle, vehicle_gps1 or ros" >&2
    exit 1 ;;
esac
