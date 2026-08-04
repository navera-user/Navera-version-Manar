#!/usr/bin/env bash
#
# navera_boot_rtc.sh — lance le node RTC NAVERA au boot (appelé par navera-rtc.service).
# La RTC (DS3231, I2C 0x68) tourne en permanence comme le GPS et l'IMU : elle fournit la
# référence temporelle dont l'astrométrie a besoin quand il n'y a pas de réseau (donc pas
# de NTP). CPU-only → PAS d'exports CUDA.
#
# Tourne sur l'HÔTE, pas dans le conteneur : les libs Adafruit (blinka, ds3231, register)
# doivent être installées sur l'hôte. Le conteneur a les mêmes libs (Dockerfile.navera)
# pour la parité, mais ce service ne les utilise pas.
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
#    Bus 1 = pins 27 (SDA) / 28 (SCL), partagé avec l'IMU. Adresse 0x68 (figée en silicium).
export ROS_LOCALHOST_ONLY=1   # decouverte DDS via loopback uniquement (fix multicast Wi-Fi)
exec ros2 launch rtc_pkg rtc.launch.py i2c_bus:=1 publish_rate:=1.0
