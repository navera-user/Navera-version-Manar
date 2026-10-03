#!/usr/bin/env bash
#
# navera_boot_discover.sh — find what is connected (navera_common.discovery) and write the
# settings left to "auto". Called by navera-discover.service, once per boot. A failure
# leaves the previous result in place and never blocks the other units.
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

# the ROS network settings AS WRITTEN (navera_env turns ROS_DOMAIN_ID=auto into the
# isolated default for the nodes; discovery must see "auto" to join a vehicle it finds)
written_domain="${ROS_DOMAIN_ID:-}" written_local="${ROS_LOCALHOST_ONLY:-}"
navera_env
mkdir -p /var/lib/navera 2>/dev/null
ROS_DOMAIN_ID="$written_domain" ROS_LOCALHOST_ONLY="$written_local" \
python3 -m navera_common.discovery --env-out /var/lib/navera/discovered.env \
    --json-out /var/lib/navera/discovery.json || navera_log "discovery failed: previous result kept"
exit 0
