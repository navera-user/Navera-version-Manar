#!/bin/bash
# box.sh — a NAVERA Lite box on your bench, simulated with small scripts (lab 02, Session 1).
#
#   ./box.sh start    start the box (an earlier box is stopped first)
#   ./box.sh stop     stop everything the box started
#
# What runs: for each service (nmea, camera, arbiter) a "supervise" process, which starts the service's
# program and starts it again when it ends, as systemd does on a real box. The programs are pretend
# nodes (box/bin/): they write their messages in box/log/journal.log, and the arbiter writes its
# decisions in box/log/decisions.log. Each start keeps the logs of the earlier runs in box/old/.
# You may read everything here; you do not need to change anything.
cd "$(dirname "$0")" || exit 1
BOX="$PWD/box"
NAME=box.sh
. box/bin/_common.sh

ours() {        # is PID one of the box's processes? (never touch anything else)
    [ -r "/proc/$1/cmdline" ] && tr '\0' ' ' < "/proc/$1/cmdline" | grep -q "box/bin/"
}

stop_box() {
    local pids="" f pid
    [ -d box/run ] || return 0
    touch box/run/stopping
    for f in box/run/*.pid; do
        [ -e "$f" ] || continue
        pid="$(cat "$f")"
        if ours "$pid"; then
            pids="$pids $pid"
        fi
    done
    [ -n "$pids" ] || return 0
    [ -d box/log ] && say "stop requested: SIGTERM to$pids"
    kill -TERM $pids 2> /dev/null
    sleep 2
    for pid in $pids; do
        if ours "$pid"; then
            [ -d box/log ] && say "pid $pid still running 2 s after SIGTERM: SIGKILL"
            kill -KILL "$pid" 2> /dev/null
        fi
    done
    sleep 0.5
    [ -d box/log ] && say "box stopped"
    return 0
}

case "$1" in
    start)
        stop_box
        if [ -d box/log ]; then                    # keep the earlier run
            mkdir -p box/old
            mv box/log "box/old/run-$(date +%Y%m%d-%H%M%S)"
        fi
        rm -rf box/run
        mkdir -p box/log box/run
        say "starting the bench box"
        for service in nmea camera arbiter; do
            setsid box/bin/supervise "$service" < /dev/null > /dev/null 2>&1 &
        done
        sleep 4
        setsid box/bin/sim_launcher < /dev/null > /dev/null 2>&1 &   # a simulator test started later
        sleep 2
        echo "The bench box is running."
        echo "  its messages (like systemd's journal):  box/log/journal.log"
        echo "  the arbiter's decisions:                box/log/decisions.log"
        ;;
    stop)
        stop_box
        rm -f box/run/*.pid
        echo "The bench box is stopped."
        ;;
    *)
        echo "usage: $0 start|stop" >&2
        exit 2
        ;;
esac
