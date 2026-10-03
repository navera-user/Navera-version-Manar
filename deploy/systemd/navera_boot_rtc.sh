#!/usr/bin/env bash
#
# navera_boot_rtc.sh — Real-time clock driver (DS3231, I2C bus 1).
# Called by navera-rtc.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
if [ "${NAVERA_BOX_RTC:-1}" = "0" ]; then
    navera_log "no DS3231 clock found at boot (NAVERA_BOX_RTC=0): clock service idle"
    exec sleep infinity
fi
exec ros2 launch rtc_pkg rtc.launch.py i2c_bus:="${NAVERA_BOX_RTC_BUS:-1}" publish_rate:=1.0
