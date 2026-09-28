#!/usr/bin/env bash
#
# navera_boot_rtc.sh — Real-time clock driver (DS3231, I2C bus 1).
# Called by navera-rtc.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
exec ros2 launch rtc_pkg rtc.launch.py i2c_bus:=1 publish_rate:=1.0
