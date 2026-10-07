#!/bin/bash
# log_report.sh — a 7-line summary of one NAVERA (ROS 2 console) log.
# usage: log_report.sh LOGFILE
set -e

if [ $# -ne 1 ]; then
    echo "usage: $0 LOGFILE" >&2
    exit 2
fi
log="$1"
if [ ! -f "$log" ]; then
    echo "no such file: $log" >&2
    exit 1
fi

echo "file: $(basename "$log")"
echo "lines: $(wc -l < "$log")"
for level in INFO WARN ERROR; do
    echo "$level: $(grep -c "^\[$level\]" "$log" || true)"
done
echo "nodes: $(cut -d' ' -f3 "$log" | sort -u | wc -l)"
echo "no_fix: $(grep -c "state NO_FIX" "$log" || true)"
