#!/usr/bin/env bash
#
# navera_boot_gps.sh — GPS driver (NMEA on the Jetson UART).
# Called by navera-gps.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
exec ros2 launch gps_pkg gps.launch.py \
    serial_port:="${NAVERA_GPS_PORT:-/dev/ttyTHS1}" baud_rate:="${NAVERA_GPS_BAUD:-9600}"
