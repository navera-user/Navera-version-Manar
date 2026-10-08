#!/bin/bash
# preflight.sh — a small pre-flight check of the NAVERA box (training version).
# Usage:  ./preflight.sh
# It needs the execute permission (x) to run like that. Exit code 0 = ready.

problems=0

echo "ROS domain       : ${ROS_DOMAIN_ID:-NOT SET}"
echo "ROS localhost    : ${ROS_LOCALHOST_ONLY:-NOT SET}"
if [ -z "$ROS_DOMAIN_ID" ]; then
    echo "  !! ROS_DOMAIN_ID is not set"
    problems=$((problems + 1))
fi

for f in "$NAVERA_MBTILES" "$HOME/navera/navera_msgs/msg/PositionEstimate.msg"; do
    if [ -e "$f" ]; then
        echo "found            : $f"
    elif [ "$f" = "$NAVERA_MBTILES" ]; then
        echo "  !! missing     : $f"
        echo "     (the map lives on the data disk: ask the teacher to connect it — not your mistake)"
        problems=$((problems + 1))
    else
        echo "  !! missing     : $f"
        problems=$((problems + 1))
    fi
done

if [ "$problems" -eq 0 ]; then
    echo "PRE-FLIGHT OK"
    exit 0
else
    echo "PRE-FLIGHT FAILED: $problems problem(s)"
    exit 1
fi
