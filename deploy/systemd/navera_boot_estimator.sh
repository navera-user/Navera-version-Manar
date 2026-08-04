#!/usr/bin/env bash
#
# navera_boot_estimator.sh — lance le node arbitre NAVERA au boot (appelé par navera-estimator.service).
# L'estimator est le CERVEAU décisionnel : il s'abonne aux estimés par source
# (/navera/estimate/*) et publie /navera/position + /navera/nav_status. Il tolère
# l'apparition/disparition de n'importe quelle source PAR CONSTRUCTION (gate de
# fraîcheur + état NO_FIX de première classe) → aucun ordre de démarrage requis vis-à-vis
# des services capteurs/pipelines. CPU-only (rclpy + arithmétique, AUCUN torch) →
# PAS d'exports CUDA (≠ navera_boot_pipeline_day.sh).
#
# Tourne sur l'HÔTE, pas dans le conteneur (comme les capteurs et le bridge web).
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
#    SIGTERM transmis au launch). Paramètres laissés aux défauts du launch
#    (publish_rate_hz=5.0, gps_timeout_s=3.0, day_timeout_s=3.0, imu_timeout_s=1.0 ;
#    déclarés dans estimator.launch.py + config/estimator_params.yaml).
export ROS_LOCALHOST_ONLY=1   # decouverte DDS via loopback uniquement (fix multicast Wi-Fi)
exec ros2 launch navera_estimator estimator.launch.py
