#!/usr/bin/env bash
#
# navera_boot_gps.sh — lance le node GPS NAVERA au boot (appelé par navera-gps.service).
# Le GPS est la source de position PRIMAIRE : il tourne en permanence, indépendamment
# de tout pipeline visuel (navera-day). CPU-only → PAS d'exports CUDA (≠ navera_boot_day.sh).
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
#    SIGTERM transmis au launch). serial_port/baud_rate explicites (= défauts du launch,
#    mais rendus visibles ici pour que la config du port soit auditable en un endroit).
exec ros2 launch gps_pkg gps.launch.py serial_port:=/dev/ttyTHS1 baud_rate:=9600
