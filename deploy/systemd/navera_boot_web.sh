#!/usr/bin/env bash
#
# navera_boot_web.sh — web bridge (operator view + dashboard on :8181), wired to the
# pipeline selected by NAVERA_PIPELINE (day | night | cn) in /etc/navera/navera.env.
# NAVERA_WEB_PORT (default 8181) moves the port, e.g. for a staged test beside a live box.
# Called by navera-web.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
case "${NAVERA_PIPELINE:-day}" in
  day)   exec ros2 launch simulation_web bridge.launch.py web_port:="${NAVERA_WEB_PORT:-8181}" \
             status_topic:=/day/day_status fix_topic:=/day/position_estimate \
             start_topic:=/day/camera/start ready_topic:=/day/localizer_ready ;;
  night) exec ros2 launch simulation_web bridge.launch.py web_port:="${NAVERA_WEB_PORT:-8181}" \
             status_topic:=/night/night_status fix_topic:=/night/position_estimate \
             start_topic:=/thermal/camera/start ready_topic:=/night/localizer_ready ;;
  cn)    exec ros2 launch simulation_web bridge.launch.py web_port:="${NAVERA_WEB_PORT:-8181}" \
             bridge_executable:=navera_stellar_bridge.py bridge_name:=navera_stellar_bridge \
             status_topic:=/cn/cn_status fix_topic:=/cn/position_estimate \
             start_topic:=/celestial/camera/start ;;
  *)     navera_log "unknown NAVERA_PIPELINE=${NAVERA_PIPELINE}"; exit 1 ;;
esac
