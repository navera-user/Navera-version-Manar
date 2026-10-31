#!/usr/bin/env bash
#
# navera_boot_pipeline_night.sh — night localization pipeline (thermal camera + STHN), GPU.
# Called by navera-pipeline-night.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_cuda
navera_prune_logs
navera_check_swap
navera_require NAVERA_MBTILES NAVERA_STHN_DIR NAVERA_STHN_WEIGHTS
# No thermal camera yet (and no lens for the main camera): wait for one instead of failing in a
# loop. The automatic choice runs this pipeline at night; a thermal camera plugged in later is
# found by navera-hotplug (discovered.env changes) and the pipeline starts with it.
if [ -z "${NAVERA_THERMAL_CAMERA_INPUT:-}" ] && [ -z "${NAVERA_CAMERA_HFOV_DEG:-}" ] \
   && [ -z "${NAVERA_CAMERA_CALIBRATION:-}" ]; then
    navera_idle_until_discovered "no thermal camera found or configured: night pipeline waits for one"
fi
exec ros2 launch simulation_web night_pipeline.launch.py
