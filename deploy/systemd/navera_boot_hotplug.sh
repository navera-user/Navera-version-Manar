#!/usr/bin/env bash
#
# navera_boot_hotplug.sh — fill the sources navera-discover left idle (no GPS, no autopilot,
# no camera, no attitude) when a device is connected after boot (navera_common.hotplug).
# Called by navera-hotplug.service. Only idle needs are filled, the GPS never while armed;
# the idle units restart by themselves when discovered.env changes.
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

# the ROS network settings AS WRITTEN (as navera_boot_discover.sh: decide() must see "auto")
export NAVERA_WRITTEN_ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-}" NAVERA_WRITTEN_ROS_LOCALHOST_ONLY="${ROS_LOCALHOST_ONLY:-}"
navera_env
exec python3 -m navera_common.hotplug --env-out /var/lib/navera/discovered.env \
    --json /var/lib/navera/discovery.json
