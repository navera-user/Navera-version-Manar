#!/usr/bin/env bash
#
# navera_boot_web.sh — web bridge (operator view + dashboard on :8181), wired to the
# pipeline selected by NAVERA_PIPELINE (day | night | cn) in /etc/navera/navera.env.
# NAVERA_WEB_PORT (default 8181) moves the port, e.g. for a staged test beside a live box;
# NAVERA_WEB_HOST chooses the network it listens on (navera_boot_lib.sh::navera_web_host).
# Called by navera-web.service. Shared steps: navera_boot_lib.sh (installed next to it).
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
navera_prune_logs
host=$(navera_web_host)
if [ "${NAVERA_PRODUCT_MODE:-0}" = 1 ] && [ -z "${NAVERA_WEB_TOKEN:-}" ]; then
  navera_log "product mode without NAVERA_WEB_TOKEN: the web page is read-only (no control)"
fi
# The automatic choice (navera-pipeline-select) writes the running pipeline in
# /var/lib/navera/pipeline.env (NAVERA_PIPELINE_ACTIVE, loaded by navera-web.service) and restarts
# this unit when it switches: the page then follows the pipeline that really runs.
pipe="${NAVERA_PIPELINE_ACTIVE:-${NAVERA_PIPELINE:-day}}"
case "$pipe" in day|night|cn) ;; *) navera_log "unknown pipeline '$pipe': web page wired to day"; pipe=day ;; esac
case "$pipe" in
  day)   exec ros2 launch simulation_web bridge.launch.py web_port:="${NAVERA_WEB_PORT:-8181}" web_host:="$host" \
             status_topic:=/day/day_status fix_topic:=/day/position_estimate \
             start_topic:=/day/camera/start ready_topic:=/day/localizer_ready ;;
  night) exec ros2 launch simulation_web bridge.launch.py web_port:="${NAVERA_WEB_PORT:-8181}" web_host:="$host" \
             status_topic:=/night/night_status fix_topic:=/night/position_estimate \
             start_topic:=/thermal/camera/start ready_topic:=/night/localizer_ready ;;
  # celestial: the same full page (operator view, mission, automatic mode), wired to the cn topics
  cn)    exec ros2 launch simulation_web bridge.launch.py web_port:="${NAVERA_WEB_PORT:-8181}" web_host:="$host" \
             status_topic:=/cn/cn_status fix_topic:=/cn/position_estimate \
             start_topic:=/celestial/camera/start ;;
esac
