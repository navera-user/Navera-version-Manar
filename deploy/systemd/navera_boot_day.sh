#!/usr/bin/env bash
#
# navera_boot_day.sh — lance le pipeline NAVERA "day" au boot (appelé par navera-day.service).
# Reproduit EXACTEMENT la séquence validée au runtime, en fournissant l'environnement
# que systemd ne charge pas (pas de shell interactif → ~/.bashrc n'est jamais sourcé).

# NB: pas de `set -euo pipefail` : les scripts setup.bash de ROS référencent des
# variables non définies et peuvent renvoyer un code != 0 ; `set -e/-u` tuerait le
# lancement à tort. On reste donc sans, comme dans un shell de connexion normal.

# 1) Aller dans le workspace (mêmes chemins relatifs que la séquence qui marche)
cd /home/navera/isaac_ros_common || exit 1

# 2) CUDA 12.6 — normalement ajouté par ~/.bashrc, ABSENT sous systemd. À remettre ici.
export PATH=/usr/local/cuda/bin:$PATH
export LD_LIBRARY_PATH=/usr/local/cuda/lib64:$LD_LIBRARY_PATH

# 3) Sourcer ROS Humble puis l'overlay du workspace (fournit AMENT_PREFIX_PATH,
#    PYTHONPATH, ROS_DISTRO, ROS_VERSION, ROS_PYTHON_VERSION, ROS_LOCALHOST_ONLY…)
source /opt/ros/humble/setup.bash
source install/setup.bash

# 4) Lancer le pipeline. `exec` remplace le shell par ros2 launch : celui-ci devient
#    le processus principal (MainPID) vu par systemd → arrêt/redémarrage propres,
#    signaux (SIGTERM au stop) transmis directement au launch.
exec ros2 launch simulation_web day_sim.launch.py
