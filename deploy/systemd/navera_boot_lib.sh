#!/usr/bin/env bash
# navera_boot_lib.sh — shared steps of the NAVERA boot wrappers (sourced, not run).
#
# systemd provides /etc/navera/navera.env (EnvironmentFile=) but never sources
# ~/.bashrc, so each wrapper: enters the workspace, sources ROS, prunes old
# ROS log folders, checks its data is really there, then `exec`s its launch
# (the launch becomes the unit's main process: clean stop/restart).
#
# No `set -u`: the ROS setup scripts reference unset variables.

NAVERA_WS="${NAVERA_WS:-/home/navera/isaac_ros_common}"

navera_log() { echo "[navera-boot] $*" >&2; }

# Enter the workspace and source ROS 2 + the NAVERA overlay.
navera_env() {
    cd "$NAVERA_WS" || { navera_log "workspace $NAVERA_WS not found"; exit 1; }
    # ROS_DOMAIN_ID=auto: join a ROS vehicle navera-discover found (discovered.env sets the
    # number); none found: NAVERA stays on its own isolated domain
    if [[ ! "${ROS_DOMAIN_ID:-0}" =~ ^[0-9]+$ ]]; then
        export ROS_DOMAIN_ID=42 ROS_LOCALHOST_ONLY=1
    fi
    source /opt/ros/humble/setup.bash
    source install/setup.bash
}

# CUDA for the GPU pipelines (normally added by ~/.bashrc, absent under systemd).
navera_cuda() {
    export PATH=/usr/local/cuda/bin:$PATH
    export LD_LIBRARY_PATH=/usr/local/cuda/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
}

# Every ros2 launch creates a log folder; a restart loop (one start per 10 s) would fill
# the disk. Keep the last 7 days, then at most NAVERA_LOG_MAX_MB (default 1024): the oldest
# entries go first. Warn when the log disk has less than NAVERA_MIN_FREE_MB (default 2048)
# free. Never fails: logs must not stop navigation.
navera_prune_logs() {
    local d="${ROS_LOG_DIR:-$HOME/.ros/log}" max_kb used oldest prev="" free_kb
    [ -d "$d" ] || return 0
    find "$d" -mindepth 1 -maxdepth 1 -mtime +7 -exec rm -rf {} + 2>/dev/null
    max_kb=$(( ${NAVERA_LOG_MAX_MB:-1024} * 1024 ))
    used=$(du -sk "$d" 2>/dev/null | cut -f1)
    while [ "${used:-0}" -gt "$max_kb" ]; do
        oldest=$(find "$d" -mindepth 1 -maxdepth 1 -printf '%T@ %p\n' 2>/dev/null | sort -n | head -1 | cut -d' ' -f2-)
        [ -n "$oldest" ] && [ "$oldest" != "$prev" ] || break      # nothing left, or not removable
        prev=$oldest
        rm -rf -- "$oldest" 2>/dev/null
        used=$(du -sk "$d" 2>/dev/null | cut -f1)
    done
    free_kb=$(df -Pk "$d" 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -n "$free_kb" ] && [ "$free_kb" -lt $(( ${NAVERA_MIN_FREE_MB:-2048} * 1024 )) ]; then
        navera_log "WARNING: only $(( free_kb / 1024 )) MB free on the disk of $d (NAVERA_MIN_FREE_MB=${NAVERA_MIN_FREE_MB:-2048})"
    fi
    return 0
}

# navera_require VAR... — each named variable must point to an existing path.
# If the data disk is not mounted yet, exit 1: systemd retries in 10 s, and the
# pipeline never starts half-blind.
navera_require() {
    local v missing=0
    for v in "$@"; do
        if [ -z "${!v}" ]; then
            navera_log "$v is not set (see /etc/navera/navera.env)"; missing=1
        elif [ ! -e "${!v}" ]; then
            navera_log "$v=${!v} does not exist (data disk not mounted?)"; missing=1
        fi
    done
    [ "$missing" -eq 0 ] || exit 1
}
