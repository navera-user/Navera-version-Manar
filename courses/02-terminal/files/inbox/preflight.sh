#!/bin/bash
# preflight.sh — pre-flight check of a NAVERA Lite box (training version, lab 02).
# Usage:  ./preflight.sh      (it needs the execute permission, x, to run like that)
# Exit code 0 = ready; 1 = at least one problem.

problems=0
here="$(cd "$(dirname "$0")" && pwd)"
tree=/data/academy/02-terminal/navera_lite_tree
unit="$here/../deploy/navera_lite-gps.service"

echo "ROS domain       : ${ROS_DOMAIN_ID:-NOT SET}"
echo "ROS localhost    : ${ROS_LOCALHOST_ONLY:-NOT SET}"
if [ -z "$ROS_DOMAIN_ID" ]; then
    echo "  !! ROS_DOMAIN_ID is not set"
    problems=$((problems + 1))
fi

if [ -n "$NAVERA_LITE_MAP" ] && [ -e "$NAVERA_LITE_MAP" ]; then
    echo "map              : $NAVERA_LITE_MAP"
else
    echo "  !! map missing : ${NAVERA_LITE_MAP:-NAVERA_LITE_MAP is not set}"
    echo "     (the map lives on the data disk: ask the teacher to connect it — not your mistake)"
    problems=$((problems + 1))
fi

if [ -f "$tree/navera_lite.yaml" ]; then
    echo "stack skeleton   : $tree"
else
    echo "  !! missing     : $tree (ask the teacher)"
    problems=$((problems + 1))
fi

# the group of the GPS serial port, as the test engineer saved it (the fourth column of ls -l)
port_group="$(awk '$1 ~ /^c/ {print $4}' /data/academy/02-terminal/evidence/ls_dev.txt 2> /dev/null)"
if [ ! -f "$unit" ]; then
    echo "  !! GPS service : no unit file mission/deploy/navera_lite-gps.service yet"
    problems=$((problems + 1))
elif sed -n '/^\[Service\]/,/^\[Install\]/p' "$unit" \
        | grep -Eq "^SupplementaryGroups *= *([^#]* )?${port_group:-?}( [^#]*)?$"; then
    echo "GPS service      : its user may open the serial port (group $port_group)"
else
    echo "  !! GPS service : its user may not open the serial port /dev/ttyTHS1"
    if grep -q "SupplementaryGroups" "$unit"; then
        echo "     (a SupplementaryGroups line exists: is it in [Service], with the port's group?)"
    fi
    if grep -q "^SupplementaryGroups.*#" "$unit"; then
        echo "     (a '#' after the value is not a comment in a unit file: systemd reads it as group names)"
    fi
    problems=$((problems + 1))
fi

if [ "$problems" -eq 0 ]; then
    echo "PRE-FLIGHT OK"
    exit 0
else
    echo "PRE-FLIGHT FAILED: $problems problem(s)"
    exit 1
fi
