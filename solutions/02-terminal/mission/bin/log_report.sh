#!/bin/bash
# log_report.sh — a 7-line summary of one log in the ROS 2 console format.
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
    n=$(grep -c "^\[$level\]" "$log" || true)
    echo "$level: $n"
done
echo "nodes: $(cut -d' ' -f3 "$log" | sort -u | wc -l)"
n=$(grep -c "state NO_FIX" "$log" || true)
echo "no_fix: $n"
