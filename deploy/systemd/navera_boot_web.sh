#!/usr/bin/env bash
#
# navera_boot_web.sh — lance le bridge ROS→web NAVERA au boot (appelé par navera-web.service).
# Le bridge est le SEUL processus qui lie le port HTTP 8181 : l'isoler dans son propre service
# permet aux pipelines de localisation de coexister (un seul bind du port). CPU-only (HTTP +
# rclpy + lecture mbtiles, AUCUN torch) → PAS d'exports CUDA (≠ navera_boot_pipeline_day.sh).
#
# Tourne sur l'HÔTE, pas dans le conteneur (comme les capteurs et l'ancien navera_boot_day.sh).
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
#    SIGTERM transmis au launch). Topics/port épelés (= défauts de bridge.launch.py, rendus
#    visibles ici pour que le câblage "day" + le port soient auditables en un endroit).
#    Comportement STRICTEMENT identique à day_sim aujourd'hui : mêmes topics, port 8181.
exec ros2 launch simulation_web bridge.launch.py \
    status_topic:=/day/day_status \
    fix_topic:=/day/position_estimate \
    start_topic:=/day/camera/start \
    web_port:=8181
