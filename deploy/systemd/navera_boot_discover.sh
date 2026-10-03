#!/usr/bin/env bash
#
# navera_boot_discover.sh — find what is connected (navera_common.discovery) and write the
# settings left to "auto". Called by navera-discover.service, once per boot. A failure
# leaves the previous result in place and never blocks the other units.
source "$(dirname "$(readlink -f "$0")")/navera_boot_lib.sh"

navera_env
mkdir -p /var/lib/navera 2>/dev/null
python3 -m navera_common.discovery --env-out /var/lib/navera/discovered.env \
    --json-out /var/lib/navera/discovery.json || navera_log "discovery failed: previous result kept"
exit 0
