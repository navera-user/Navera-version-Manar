#!/usr/bin/env bash
#
# navera_boot_imu.sh — lance le node IMU NAVERA au boot (appelé par navera-imu.service).
# L'IMU (BNO085, I2C) tourne en permanence comme le GPS : c'est une source de secours
# (dead-reckoning) + la référence d'attitude pour le céleste. CPU-only → PAS d'exports CUDA.
#
# Tourne sur l'HÔTE, pas dans le conteneur : les libs Adafruit (blinka, bno08x) et
# Jetson.GPIO>=2.1.12 doivent être installées sur l'hôte. Le conteneur a les mêmes
# libs (Dockerfile.navera) pour la parité, mais ce service ne les utilise pas.
#
# NB: pas de `set -euo pipefail` : les setup.bash de ROS référencent des variables non
# définies ; set -e/-u tuerait le lancement à tort. On reste comme un shell de login.

# 1) Workspace (mêmes chemins relatifs que la séquence validée)
cd /home/navera/isaac_ros_common || exit 1

# 2) Sourcer ROS Humble puis l'overlay du workspace (fournit AMENT_PREFIX_PATH,
#    PYTHONPATH, ROS_DISTRO, ROS_VERSION… absents sous systemd car ~/.bashrc
#    n'est jamais sourcé dans un service).
source /opt/ros/humble/setup.bash
source install/setup.bash

# 3) exec → ros2 launch devient le MainPID vu par systemd (stop/restart propres,
#    SIGTERM transmis au launch). i2c_bus/publish_rate explicites (= défauts du launch,
#    mais rendus visibles ici pour que le câblage soit auditable en un endroit).
#    Bus 1 = pins 27 (SDA) / 28 (SCL) du header 40 broches. Adresse 0x4A (défaut YAML).
export ROS_LOCALHOST_ONLY=1   # decouverte DDS via loopback uniquement (fix multicast Wi-Fi)
exec ros2 launch imu_pkg imu.launch.py i2c_bus:=1 publish_rate:=50.0
