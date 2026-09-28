#!/usr/bin/env bash
#
# navera_boot_pipeline_cn.sh — celestial localization pipeline (star camera + astrometry.net).
# Called by navera-pipeline-cn.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
exec ros2 launch simulation_web cn_pipeline.launch.py
