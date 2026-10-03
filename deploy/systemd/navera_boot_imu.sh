#!/usr/bin/env bash
#
# navera_boot_imu.sh — IMU driver (BNO085, I2C bus 1).
# Called by navera-imu.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
if [ "${NAVERA_BOX_IMU:-1}" = "0" ]; then
    # navera-discover found no BNO085 on I2C: idle instead of a restart loop
    navera_log "no box IMU found at boot (NAVERA_BOX_IMU=0): IMU service idle"
    exec sleep infinity
fi
exec ros2 launch imu_pkg imu.launch.py i2c_bus:="${NAVERA_BOX_IMU_BUS:-1}" publish_rate:=50.0
