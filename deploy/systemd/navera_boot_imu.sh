#!/usr/bin/env bash
#
# navera_boot_imu.sh — IMU driver (BNO085, I2C bus 1).
# Called by navera-imu.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
exec ros2 launch imu_pkg imu.launch.py i2c_bus:=1 publish_rate:=50.0
