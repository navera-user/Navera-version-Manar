#!/usr/bin/env bash
#
# navera_boot_pipeline_day.sh — day localization pipeline (camera + DINOv2), GPU.
# Called by navera-pipeline-day.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_cuda
navera_prune_logs
navera_check_swap
navera_require NAVERA_MBTILES DAY_DATASET_DIR
exec ros2 launch simulation_web day_pipeline.launch.py
