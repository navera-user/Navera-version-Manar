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

# navera_restart_backoff — systemd restarts a NAVERA unit 1 s after it exits (RestartSec=1:
# a crash in flight must be back before the output's 10 s bridge ends, B23) and never gives
# up (StartLimitIntervalSec=0: the mission must not end). A unit that fails at every start
# (data disk not mounted, device gone, bad setting) would then restart once a second for
# hours: past NAVERA_BACKOFF_FREE starts (default 5) within NAVERA_BACKOFF_WINDOW_S (60 s)
# the wrapper first waits 2, 4, 8... s, at most NAVERA_BACKOFF_MAX_S (30 s). A single crash
# is back after 1 s. The start times live in RAM (NAVERA_RUN_DIR, default /dev/shm), one file
# per wrapper, user and workspace. Never fails: a backoff must not stop navigation.
navera_restart_backoff() {
    local dir="${NAVERA_RUN_DIR:-/dev/shm}" name now f n=0 wait keep=() t
    name="$(basename "${1:-$0}" .sh)-$(id -u)-$(printf '%s' "$NAVERA_WS" | cksum | cut -d' ' -f1)"
    f="$dir/navera-starts-$name"
    now=$(date +%s)
    if [ -r "$f" ]; then
        while read -r t; do
            [[ "$t" =~ ^[0-9]+$ ]] && [ $(( now - t )) -lt "${NAVERA_BACKOFF_WINDOW_S:-60}" ] && keep+=("$t")
        done < "$f"
    fi
    keep+=("$now")
    printf '%s\n' "${keep[@]}" > "$f.$$" 2>/dev/null && mv -f "$f.$$" "$f" 2>/dev/null
    n=${#keep[@]}
    if [ "$n" -gt "${NAVERA_BACKOFF_FREE:-5}" ]; then
        wait=$(( 1 << (n - ${NAVERA_BACKOFF_FREE:-5}) ))
        [ "$wait" -gt "${NAVERA_BACKOFF_MAX_S:-30}" ] && wait=${NAVERA_BACKOFF_MAX_S:-30}
        navera_log "restart loop: $n starts in ${NAVERA_BACKOFF_WINDOW_S:-60} s — waiting $wait s before this one"
        sleep "$wait"
    fi
    return 0
}

# Enter the workspace and source ROS 2 + the NAVERA overlay. Every wrapper calls it first:
# the restart backoff (above) happens here.
navera_env() {
    navera_restart_backoff "$0"
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

# Every ros2 launch creates a log folder; a restart loop (one start per second) would fill
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

# The GPU pipelines need swap on disk (F5: the day pipeline was OOM-killed on the 8 GB Jetson
# without it; JetPack's zram lives in RAM and does not count). Warns in the journal at every
# start of a pipeline when the active disk swap is below NAVERA_MIN_SWAP_MB (default 4096);
# never stops the pipeline (navigating with a risk beats not navigating).
# Fix: sudo /home/navera/isaac_ros_common/deploy/setup_swap.sh
navera_check_swap() {
    local have
    have=$(awk 'NR > 1 && $1 !~ /^\/dev\/zram/ { kb += $3 } END { print int(kb / 1024) }' \
           "${NAVERA_SWAPS:-/proc/swaps}" 2>/dev/null)
    if [ "${have:-0}" -lt "${NAVERA_MIN_SWAP_MB:-4096}" ]; then
        navera_log "WARNING: only ${have:-0} MB of swap on disk (need ${NAVERA_MIN_SWAP_MB:-4096} MB): the pipeline may be OOM-killed (F5) — sudo $NAVERA_WS/deploy/setup_swap.sh"
    fi
    return 0
}

# navera_require VAR... — each named variable must point to an existing path.
# If the data disk is not mounted yet, exit 1: systemd retries (1 s, then backing off to 30 s), and the
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

# navera_idle_until_discovered "why" — an idle unit (nothing found to run) waits here instead
# of restarting in a loop. When navera-hotplug finds the missing device later and rewrites
# discovered.env, the wrapper exits 0: systemd (Restart=always) restarts the unit, which
# reads the new settings. NAVERA_DISCOVERED_ENV, NAVERA_IDLE_POLL_S: for tests.
navera_idle_until_discovered() {
    local f="${NAVERA_DISCOVERED_ENV:-/var/lib/navera/discovered.env}" before now
    navera_log "$1"
    before=$(stat -c %Y.%s "$f" 2>/dev/null || echo none)
    while sleep "${NAVERA_IDLE_POLL_S:-5}"; do
        now=$(stat -c %Y.%s "$f" 2>/dev/null || echo none)
        if [ "$now" != "$before" ]; then
            navera_log "discovered settings changed ($f): restarting with them"
            exit 0
        fi
    done
}
