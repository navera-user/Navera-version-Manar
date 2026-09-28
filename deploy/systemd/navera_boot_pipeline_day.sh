#!/usr/bin/env bash
#
# navera_boot_pipeline_day.sh — lance le pipeline de localisation NAVERA "day" SANS bridge au
# boot (appelé par navera-pipeline-day.service). Le bridge est un service séparé (navera-web) :
# un seul processus lie le port 8181, ce qui permet la coexistence des pipelines. Reproduit
# l'environnement que systemd ne charge pas (~/.bashrc jamais sourcé dans un service).
#
# GPU : day_subscriber charge DINOv2 → CUDA 12.6 remis dans PATH/LD_LIBRARY_PATH (normalement
# fait par ~/.bashrc, ABSENT sous systemd), comme l'ancien navera_boot_day.sh. C'est la seule
# différence avec navera_boot_web.sh, qui est CPU-only.
#
# NB: pas de `set -euo pipefail` : les setup.bash de ROS référencent des variables non
# définies ; set -e/-u tuerait le lancement à tort. On reste comme un shell de login.

# 1) Workspace (mêmes chemins relatifs que la séquence validée)
cd /home/navera/isaac_ros_common || exit 1

# 2) CUDA 12.6 — normalement ajouté par ~/.bashrc, ABSENT sous systemd. À remettre ici.
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}

# 3) Sourcer ROS Humble puis l'overlay du workspace (fournit AMENT_PREFIX_PATH,
#    PYTHONPATH, ROS_DISTRO, ROS_VERSION…).
source /opt/ros/humble/setup.bash
source install/setup.bash

# 4) exec → ros2 launch devient le MainPID vu par systemd (stop/restart propres, SIGTERM
#    transmis au launch). Pipeline SEUL (day_pipeline, PAS day_sim) : caméra(day) +
#    day_subscriber, sans bridge. Défauts inchangés → comportement identique à aujourd'hui.
exec ros2 launch simulation_web day_pipeline.launch.py
